"""Admin subscription requests and billing support (moved unchanged; payments are frozen)."""

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from stoa.config import Settings
from stoa import config
from stoa.deps import legacy_user
from stoa.db.repositories import checkout_command_repo
# Card 007: one switch and one refusal for the whole paid surface; see
# `stoa.routers.billing` for why it is frozen and what unfreezing takes.
from stoa.routers.billing import refuse_if_frozen
from stoa.routers.parents import get_billing_reconciliation_provider
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor
from stoa.rule_violation import RuleViolation
from stoa.services.billing_errors import BillingErrorCode
from stoa.services import (
    billing_reconciliation_service,
    subscription_service,
)
from stoa.routers.admin._common import _admin_required_text


router = APIRouter()


class SubscriptionRequestResponse(BaseModel):
    requestId: str
    parentId: str
    studentId: str | None = None
    currentTier: str
    requestedTier: str
    requestType: str
    status: str
    source: str
    parentNote: str | None = None
    adminNote: str | None = None
    createdAt: str
    updatedAt: str
    effectiveAt: str | None = None
    appliedAt: str | None = None
    appliedBy: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


class SubscriptionRequestListResponse(BaseModel):
    items: list[SubscriptionRequestResponse]
    count: int


class SubscriptionBillingResponse(BaseModel):
    parentId: str
    provider: str | None = None
    mode: str
    status: str
    subscriptionTier: str
    requestedTier: str | None = None
    providerCustomerId: str | None = None
    providerSubscriptionId: str | None = None
    providerPriceId: str | None = None
    checkoutSessionId: str | None = None
    checkoutUrl: str | None = None
    providerLivemode: bool | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    twint: dict[str, Any] = Field(default_factory=dict)
    paymentMethodType: str | None = None
    latestInvoice: dict[str, Any] = Field(default_factory=dict)
    refund: dict[str, Any] = Field(default_factory=dict)
    dunning: dict[str, Any] = Field(default_factory=dict)
    accountingHandoff: dict[str, Any] = Field(default_factory=dict)
    supportEvidence: dict[str, Any] = Field(default_factory=dict)
    currentPeriodStart: str | None = None
    currentPeriodEnd: str | None = None
    cancelAtPeriodEnd: bool = False
    lastProviderEventId: str | None = None
    lastProviderEventType: str | None = None
    lastProviderEventAt: str | None = None
    manualOverrideAt: str | None = None
    manualOverrideBy: str | None = None
    manualOverrideSource: str | None = None
    effectiveEntitlements: list[dict[str, Any]] = Field(default_factory=list)
    updatedAt: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


class SubscriptionBillingListResponse(BaseModel):
    items: list[SubscriptionBillingResponse]
    count: int


class AdminCheckoutRecheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdminCheckoutSupportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkoutRef: str
    parentId: str
    targetPlan: str
    beneficiaryIds: list[str]
    createdAt: str
    updatedAt: str
    commandState: str
    providerEffectStatus: str
    lifecycleState: str
    lastRecheckedAt: str
    safeAction: str
    failureCode: str
    providerSessionSuffix: str | None = None
    reconciliationLeaseGeneration: int


class AdminCheckoutRecheckResponse(AdminCheckoutSupportResponse):
    pass


class AdminBillingCommandLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    providerEffectStatus: str
    createdAt: str
    updatedAt: str


class AdminBillingFactLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "checkout_session_completed",
        "checkout_session_expired",
        "invoice_paid",
        "invoice_payment_failed",
        "subscription_active",
        "subscription_inactive",
    ]
    factVersion: int = Field(ge=1)
    providerEventIdDigest: str = Field(pattern=r"^[0-9a-f]{64}$")
    providerObjectIdDigest: str = Field(pattern=r"^[0-9a-f]{64}$")
    signatureVerified: Literal[True]
    providerLivemode: Literal[False]
    observedAt: str


class AdminProviderUsageEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    beneficiaryId: str
    correlationDigest: str = Field(pattern=r"^[0-9a-f]{64}$")
    providerRequestIdDigest: str = Field(pattern=r"^[0-9a-f]{64}$")
    modelIdDigest: str = Field(pattern=r"^[0-9a-f]{64}$")
    inputTokens: int = Field(ge=0)
    outputTokens: int = Field(ge=0)
    providerCostRetained: bool
    observedAt: str


class AdminPaymentReminderProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand: str
    last4: str = Field(pattern=r"^[0-9]{4}$")
    expiryMonth: int = Field(ge=1, le=12)
    expiryYear: int = Field(ge=2000, le=9999)
    reminderAt: str
    status: Literal["pending", "notified"]


class AdminBillingReconciliationProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lifecycleState: str
    lastRecheckedAt: str
    safeAction: str
    failureCode: str
    providerSessionSuffix: str | None = None
    reconciliationLeaseGeneration: int = Field(ge=0)


class AdminBillingOperationDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkoutRef: str
    parentId: str
    targetPlan: Literal["student", "teacher_supported", "family"]
    beneficiaryIds: list[str]
    commandLifecycle: AdminBillingCommandLifecycle
    factLifecycle: list[AdminBillingFactLifecycle]
    grantVersion: dict[str, int]
    allowanceVersion: dict[str, int]
    providerUsageEvidence: list[AdminProviderUsageEvidence]
    paymentReminder: AdminPaymentReminderProjection | None = None
    reconciliation: AdminBillingReconciliationProjection


class SubscriptionAccountingExportResponse(BaseModel):
    items: list[dict[str, Any]]
    count: int


class SubscriptionProviderReadinessResponse(BaseModel):
    state: str
    checkoutAllowed: bool
    refundsAllowed: bool
    providerMode: str
    credentials: dict[str, Any] = Field(default_factory=dict)
    prices: dict[str, Any] = Field(default_factory=dict)
    twint: dict[str, Any] = Field(default_factory=dict)
    webhook: dict[str, Any] = Field(default_factory=dict)
    refund: dict[str, Any] = Field(default_factory=dict)
    finance: dict[str, Any] = Field(default_factory=dict)
    rollout: dict[str, Any] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SubscriptionRefundExecutionRequest(BaseModel):
    amount: int = Field(..., ge=1)
    reason: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str = Field(..., alias="idempotencyKey", min_length=8, max_length=200)


class SubscriptionRefundExecutionResponse(BaseModel):
    idempotencyStatus: str
    refund: dict[str, Any] = Field(default_factory=dict)
    billing: dict[str, Any] = Field(default_factory=dict)


class SubscriptionRolloutControlsResponse(BaseModel):
    checkout: dict[str, Any] = Field(default_factory=dict)
    refunds: dict[str, Any] = Field(default_factory=dict)
    providerReadiness: str
    activationState: str
    rollbackAvailable: bool
    updatedAt: str | None = None
    updatedBy: str | None = None
    reason: str | None = None


class SubscriptionRolloutControlsUpdateRequest(BaseModel):
    checkout_state: str | None = Field(default=None, alias="checkoutState")
    refunds_state: str | None = Field(default=None, alias="refundsState")
    reason: str = Field(..., min_length=1, max_length=500)


class SubscriptionRequestUpdateRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)
    admin_note: str | None = Field(default=None, max_length=500)
    effective_at: str | None = Field(default=None, max_length=80)


class SubscriptionRequestApplyRequest(BaseModel):
    admin_note: str | None = Field(default=None, max_length=500)
    effective_at: str | None = Field(default=None, max_length=80)


@router.get("/subscriptions/requests", response_model=SubscriptionRequestListResponse)
async def list_subscription_requests(
    limit: int = Query(default=50, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    requested_tier: Optional[str] = Query(default=None),
    parent_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    actor: Actor = Depends(admin_operation),
):
    """List manual subscription requests for admin processing.

    Frozen by card 007: parents can no longer submit a request.
    """
    refuse_if_frozen()
    items = subscription_service.list_admin_requests(
        limit=limit,
        status=status,
        requested_tier=requested_tier,
        parent_id=parent_id,
        date_from=date_from,
        date_to=date_to,
    )
    responses = [SubscriptionRequestResponse.model_validate(item) for item in items]
    return SubscriptionRequestListResponse(items=responses, count=len(responses))


@router.get("/subscriptions/requests/{request_id}", response_model=SubscriptionRequestResponse)
async def get_subscription_request(
    request_id: str,
    actor: Actor = Depends(admin_operation),
):
    """Open one manual subscription request with lifecycle history.

    Frozen by card 007: the manual request flow is closed.
    """
    refuse_if_frozen()
    return subscription_service.get_request(request_id)


def _load_admin_checkout_command(
    checkout_ref: str,
    *,
    parent_id: str,
) -> Mapping[str, object]:
    try:
        lookup = checkout_command_repo.get_checkout_command_by_public_ref(
            checkout_ref,
            parent_id=parent_id,
        )
    except (TypeError, ValueError) as exc:
        raise RuleViolation(BillingErrorCode.CHECKOUT_NOT_FOUND) from exc
    except Exception as exc:
        raise RuleViolation(BillingErrorCode.CHECKOUT_TEMPORARILY_UNAVAILABLE) from exc
    if lookup.disposition is checkout_command_repo.CheckoutCommandDisposition.NOT_FOUND:
        raise RuleViolation(BillingErrorCode.CHECKOUT_NOT_FOUND)
    if (
        lookup.disposition
        is not checkout_command_repo.CheckoutCommandDisposition.REPLAYED
        or lookup.command is None
    ):
        raise RuleViolation(BillingErrorCode.CHECKOUT_TEMPORARILY_UNAVAILABLE)
    return lookup.command


def _admin_checkout_projection(
    checkout_ref: str,
    *,
    command: Mapping[str, object],
    result: billing_reconciliation_service.BillingReconciliationResult,
    response_type: type[AdminCheckoutSupportResponse] = AdminCheckoutSupportResponse,
) -> AdminCheckoutSupportResponse:
    support = billing_reconciliation_service.project_checkout_support_state(result)
    beneficiary_ids = command.get("beneficiary_ids")
    lease_generation = support["reconciliationLeaseGeneration"]
    if type(lease_generation) is not int or lease_generation < 0:
        raise RuntimeError("billing reconciliation dependency unavailable")
    return response_type(
        checkoutRef=checkout_ref,
        parentId=_admin_required_text(command.get("parent_id")),
        targetPlan=_admin_required_text(command.get("plan_id")),
        beneficiaryIds=[
            beneficiary
            for beneficiary in (
                beneficiary_ids if isinstance(beneficiary_ids, list) else []
            )
            if isinstance(beneficiary, str)
        ],
        createdAt=_admin_required_text(command.get("created_at")),
        updatedAt=_admin_required_text(command.get("updated_at")),
        commandState=_admin_required_text(command.get("command_state")),
        providerEffectStatus=_admin_required_text(
            command.get("provider_effect_status")
        ),
        lifecycleState=str(support["lifecycleState"]),
        lastRecheckedAt=str(support["lastRecheckedAt"]),
        safeAction=str(support["safeAction"]),
        failureCode=str(support["failureClass"]),
        providerSessionSuffix=(
            str(support["providerSessionSuffix"])
            if support["providerSessionSuffix"] is not None
            else None
        ),
        reconciliationLeaseGeneration=lease_generation,
    )


def _reconcile_admin_checkout(
    checkout_ref: str,
    *,
    parent_id: str,
    provider: billing_reconciliation_service.BillingReconciliationProvider,
) -> billing_reconciliation_service.BillingReconciliationResult:
    now = datetime.now(timezone.utc)
    result = billing_reconciliation_service.reconcile_checkout_command(
        checkout_ref,
        parent_id=parent_id,
        lease_owner=f"admin-checkout-recheck-{uuid4().hex}",
        provider=provider,
        now_epoch=int(now.timestamp()),
        now_iso=now.isoformat(),
    )
    if (
        result.disposition
        is billing_reconciliation_service.BillingReconciliationDisposition.NOT_FOUND
    ):
        raise RuleViolation(BillingErrorCode.CHECKOUT_NOT_FOUND)
    return result


@router.get(
    "/billing/checkouts/{checkout_ref}",
    response_model=AdminCheckoutSupportResponse | AdminBillingOperationDetail,
)
async def get_billing_checkout_support(
    checkout_ref: str,
    parent_id: str = Query(..., alias="parentId", min_length=1, max_length=200),
    detail: bool = Query(default=False),
    actor: Actor = Depends(admin_operation),
    provider: billing_reconciliation_service.BillingReconciliationProvider = Depends(
        get_billing_reconciliation_provider
    ),
):
    """Inspect one checkout through the billing-support capability.

    Frozen by card 007: no checkout can exist to support.
    """
    refuse_if_frozen()
    del actor
    command = _load_admin_checkout_command(
        checkout_ref,
        parent_id=parent_id,
    )
    result = _reconcile_admin_checkout(
        checkout_ref,
        parent_id=parent_id,
        provider=provider,
    )
    if detail:
        try:
            return subscription_service.get_admin_billing_operation_detail(
                checkout_ref=checkout_ref,
                command=command,
                reconciliation=billing_reconciliation_service.project_checkout_support_state(
                    result
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuleViolation(BillingErrorCode.BILLING_PROJECTION_TEMPORARILY_UNAVAILABLE) from exc
    return _admin_checkout_projection(
        checkout_ref,
        command=command,
        result=result,
    )


@router.post(
    "/billing/checkouts/{checkout_ref}/recheck",
    response_model=AdminCheckoutRecheckResponse,
)
async def recheck_billing_checkout_support(
    checkout_ref: str,
    body: AdminCheckoutRecheckRequest,
    parent_id: str = Query(..., alias="parentId", min_length=1, max_length=200),
    actor: Actor = Depends(admin_operation),
    provider: billing_reconciliation_service.BillingReconciliationProvider = Depends(
        get_billing_reconciliation_provider
    ),
):
    """Reconcile one original checkout without payment-creation authority.

    Frozen by card 007: reconciliation calls the payment provider.
    """
    refuse_if_frozen()
    del body, actor
    command = _load_admin_checkout_command(
        checkout_ref,
        parent_id=parent_id,
    )
    result = _reconcile_admin_checkout(
        checkout_ref,
        parent_id=parent_id,
        provider=provider,
    )
    return _admin_checkout_projection(
        checkout_ref,
        command=command,
        result=result,
        response_type=AdminCheckoutRecheckResponse,
    )


@router.get("/subscriptions/billing", response_model=SubscriptionBillingListResponse)
async def list_subscription_billing(
    limit: int = Query(default=50, ge=1, le=100),
    parent_id: Optional[str] = Query(default=None),
    billing_status: Optional[str] = Query(default=None),
    billing_provider: Optional[str] = Query(default=None),
    settings: Settings = Depends(config.settings),
    actor: Actor = Depends(admin_operation),
):
    """List provider billing records for admin visibility.

    Frozen by card 007: the admin billing view is gone from the frontend.
    """
    refuse_if_frozen()
    items = subscription_service.list_admin_billing(
        limit=limit,
        parent_id=parent_id,
        billing_status=billing_status,
        billing_provider=billing_provider,
        settings=settings,
    )
    responses = [SubscriptionBillingResponse.model_validate(item) for item in items]
    return SubscriptionBillingListResponse(items=responses, count=len(responses))


@router.get("/subscriptions/billing/accounting-export", response_model=SubscriptionAccountingExportResponse)
async def list_subscription_accounting_export(
    limit: int = Query(default=100, ge=1, le=500),
    parent_id: Optional[str] = Query(default=None),
    settings: Settings = Depends(config.settings),
    actor: Actor = Depends(admin_operation),
):
    """List redacted provider billing rows for Swiss accounting handoff.

    Frozen by card 007: there is no revenue to hand off.
    """
    refuse_if_frozen()
    items = subscription_service.list_admin_accounting_handoff(
        limit=limit,
        parent_id=parent_id,
        settings=settings,
    )
    return SubscriptionAccountingExportResponse(items=items, count=len(items))


@router.get("/subscriptions/billing/provider-readiness", response_model=SubscriptionProviderReadinessResponse)
async def get_subscription_provider_readiness(
    settings: Settings = Depends(config.settings),
    actor: Actor = Depends(admin_operation),
):
    """Inspect redacted live provider readiness without creating provider mutations.

    Frozen by card 007: the provider is deliberately not provisioned.
    """
    refuse_if_frozen()
    return subscription_service.get_provider_readiness(settings)


@router.get("/subscriptions/billing/rollout-controls", response_model=SubscriptionRolloutControlsResponse)
async def get_subscription_rollout_controls(
    settings: Settings = Depends(config.settings),
    actor: Actor = Depends(admin_operation),
):
    """Inspect effective checkout/refund rollout controls.

    Frozen by card 007: there is no rollout left to control.
    """
    refuse_if_frozen()
    return subscription_service.get_payment_rollout_controls(settings)


@router.patch("/subscriptions/billing/rollout-controls", response_model=SubscriptionRolloutControlsResponse)
async def update_subscription_rollout_controls(
    body: SubscriptionRolloutControlsUpdateRequest,
    settings: Settings = Depends(config.settings),
    actor: Actor = Depends(admin_operation),
):
    """Update checkout/refund rollout controls for new live-changing operations.

    Frozen by card 007: this switch could otherwise re-open checkout or refunds.
    """
    refuse_if_frozen()
    return subscription_service.update_payment_rollout_controls(
        checkout_state=body.checkout_state,
        refunds_state=body.refunds_state,
        reason=body.reason,
        user=legacy_user(actor),
        settings=settings,
    )


@router.get("/subscriptions/billing/{parent_id}", response_model=SubscriptionBillingResponse)
async def get_subscription_billing(
    parent_id: str,
    settings: Settings = Depends(config.settings),
    actor: Actor = Depends(admin_operation),
):
    """Open one parent provider billing record with recent event history.

    Frozen by card 007: the parent billing record is legacy data only.
    """
    refuse_if_frozen()
    return subscription_service.get_admin_billing(parent_id, settings=settings)


@router.post("/subscriptions/billing/{parent_id}/refunds", response_model=SubscriptionRefundExecutionResponse)
async def execute_subscription_refund(
    parent_id: str,
    body: SubscriptionRefundExecutionRequest,
    settings: Settings = Depends(config.settings),
    actor: Actor = Depends(admin_operation),
):
    """Execute a gated provider refund for an eligible billing record.

    Frozen by card 007: a refund is a live provider mutation.
    """
    refuse_if_frozen()
    return subscription_service.execute_billing_refund(
        parent_id=parent_id,
        amount=body.amount,
        reason=body.reason,
        idempotency_key=body.idempotency_key,
        user=legacy_user(actor),
        settings=settings,
    )


@router.patch("/subscriptions/requests/{request_id}", response_model=SubscriptionRequestResponse)
async def update_subscription_request(
    request_id: str,
    body: SubscriptionRequestUpdateRequest,
    actor: Actor = Depends(admin_operation),
):
    """Move a subscription request through review lifecycle states.

    Frozen by card 007: the manual request flow is closed.
    """
    refuse_if_frozen()
    return subscription_service.update_request_status(
        request_id=request_id,
        status=body.status,
        admin_note=body.admin_note,
        effective_at=body.effective_at,
        user=legacy_user(actor),
    )


@router.post("/subscriptions/requests/{request_id}/apply", response_model=SubscriptionRequestResponse)
async def apply_subscription_request(
    request_id: str,
    body: SubscriptionRequestApplyRequest = Body(default_factory=SubscriptionRequestApplyRequest),
    actor: Actor = Depends(admin_operation),
):
    """Apply an approved manual request and update the parent's subscription tier.

    Frozen by card 007: assignment, not an approved request, sets a tier.
    """
    refuse_if_frozen()
    return subscription_service.apply_request(
        request_id=request_id,
        admin_note=body.admin_note,
        effective_at=body.effective_at,
        user=legacy_user(actor),
    )
