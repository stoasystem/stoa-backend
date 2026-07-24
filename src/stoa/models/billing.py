"""Canonical billing contracts shared by provider, entitlement, and Web layers."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


MAX_EXACT_VERSION = (1 << 63) - 1
OpaqueText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
PositiveVersion = Annotated[int, Field(strict=True, ge=1, le=MAX_EXACT_VERSION)]


class _BillingModel(BaseModel):
    """Closed model with snake_case storage names and explicit API aliases."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BillingPlanId(StrEnum):
    FREE_TRIAL = "free_trial"
    STUDENT = "student"
    TEACHER_SUPPORTED = "teacher_supported"
    FAMILY = "family"


class PurchasablePlanId(StrEnum):
    STUDENT = "student"
    TEACHER_SUPPORTED = "teacher_supported"
    FAMILY = "family"


class CheckoutCommandState(StrEnum):
    INTENT_RECORDED = "intent_recorded"
    PROVIDER_CREATE_PENDING = "provider_create_pending"
    PROVIDER_SESSION_OPEN = "provider_session_open"
    RECONCILING = "reconciling"
    ACTIVATION_RECORDED = "activation_recorded"
    TERMINAL_WITHOUT_PAYMENT = "terminal_without_payment"
    OPERATOR_ATTENTION_REQUIRED = "operator_attention_required"


class CheckoutPublicOutcome(StrEnum):
    CONFIRMING = "confirming"
    ACTIVE = "active"
    NOT_COMPLETED = "not_completed"
    SUPPORT_NEEDED = "support_needed"


class BillingFactKind(StrEnum):
    CHECKOUT_SESSION_COMPLETED = "checkout_session_completed"
    CHECKOUT_SESSION_EXPIRED = "checkout_session_expired"
    INVOICE_PAID = "invoice_paid"
    INVOICE_PAYMENT_FAILED = "invoice_payment_failed"
    SUBSCRIPTION_ACTIVE = "subscription_active"
    SUBSCRIPTION_INACTIVE = "subscription_inactive"


class BillingLifecycleState(StrEnum):
    NO_PAID_FACT = "no_paid_fact"
    INITIAL_INVOICE_PAID = "initial_invoice_paid"
    SUBSCRIPTION_ACTIVE = "subscription_active"
    GRACE_PERIOD = "grace_period"
    ENDED = "ended"
    PROVIDER_UNKNOWN = "provider_unknown"


class EntitlementLifecycleState(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    SCHEDULED_END = "scheduled_end"
    PAUSED = "paused"


class BillingSafeAction(StrEnum):
    RECHECK_PAYMENT = "recheck_payment"
    CONTACT_SUPPORT = "contact_support"
    VIEW_BILLING = "view_billing"
    VIEW_PARENT_HOME = "view_parent_home"
    START_CHECKOUT = "start_checkout"


class CheckoutIntent(_BillingModel):
    command_id: OpaqueText = Field(alias="commandId")
    parent_id: OpaqueText = Field(alias="parentId")
    idempotency_key: OpaqueText = Field(alias="idempotencyKey")
    plan_id: PurchasablePlanId = Field(alias="planId")
    beneficiary_ids: tuple[OpaqueText, ...] = Field(
        alias="beneficiaryIds",
        min_length=1,
        max_length=3,
    )
    price_catalog_version: PositiveVersion = Field(alias="priceCatalogVersion")
    plan_version: PositiveVersion = Field(alias="planVersion")
    created_at: datetime = Field(alias="createdAt")

    @model_validator(mode="after")
    def validate_beneficiary_scope(self) -> "CheckoutIntent":
        if len(set(self.beneficiary_ids)) != len(self.beneficiary_ids):
            raise ValueError("beneficiary IDs must be unique")
        if self.plan_id in {PurchasablePlanId.STUDENT, PurchasablePlanId.TEACHER_SUPPORTED}:
            if len(self.beneficiary_ids) != 1:
                raise ValueError("selected plan requires exactly one beneficiary")
        return self


class CheckoutCommandProjection(_BillingModel):
    checkout_ref: OpaqueText = Field(alias="checkoutRef")
    command_state: CheckoutCommandState = Field(alias="commandState")
    public_outcome: CheckoutPublicOutcome = Field(alias="publicOutcome")
    billing_lifecycle_state: BillingLifecycleState = Field(alias="billingLifecycleState")
    entitlement_state: EntitlementLifecycleState = Field(alias="entitlementState")
    state_version: PositiveVersion = Field(alias="stateVersion")
    target_plan_id: PurchasablePlanId = Field(alias="targetPlanId")
    beneficiary_ids: tuple[OpaqueText, ...] = Field(
        alias="beneficiaryIds",
        min_length=1,
        max_length=3,
    )
    safe_actions: tuple[BillingSafeAction, ...] = Field(alias="safeActions", max_length=5)
    paid_invoice_fact_id: OpaqueText | None = Field(default=None, alias="paidInvoiceFactId")
    active_subscription_fact_id: OpaqueText | None = Field(
        default=None,
        alias="activeSubscriptionFactId",
    )
    effective_plan_id: BillingPlanId | None = Field(default=None, alias="effectivePlanId")
    plan_version: PositiveVersion | None = Field(default=None, alias="planVersion")
    allowance_version: PositiveVersion | None = Field(default=None, alias="allowanceVersion")

    @model_validator(mode="after")
    def require_authoritative_activation_coordinates(self) -> "CheckoutCommandProjection":
        if len(set(self.beneficiary_ids)) != len(self.beneficiary_ids):
            raise ValueError("beneficiary IDs must be unique")
        if self.public_outcome is not CheckoutPublicOutcome.ACTIVE:
            return self
        if self.command_state is not CheckoutCommandState.ACTIVATION_RECORDED:
            raise ValueError("active outcome requires a recorded activation")
        if self.billing_lifecycle_state is not BillingLifecycleState.SUBSCRIPTION_ACTIVE:
            raise ValueError("active outcome requires an active subscription fact")
        if self.entitlement_state is not EntitlementLifecycleState.ACTIVE:
            raise ValueError("active outcome requires an active entitlement")
        authoritative_coordinates = (
            self.paid_invoice_fact_id,
            self.active_subscription_fact_id,
            self.effective_plan_id,
            self.plan_version,
            self.allowance_version,
        )
        if any(coordinate is None for coordinate in authoritative_coordinates):
            raise ValueError("active outcome requires complete authoritative coordinates")
        if self.effective_plan_id is not BillingPlanId(self.target_plan_id):
            raise ValueError("effective plan must match the checkout target plan")
        return self


class BillingFact(_BillingModel):
    fact_id: OpaqueText = Field(alias="factId")
    checkout_command_id: OpaqueText = Field(alias="checkoutCommandId")
    kind: BillingFactKind
    provider_event_id_digest: Sha256Digest = Field(alias="providerEventIdDigest")
    provider_object_id_digest: Sha256Digest = Field(alias="providerObjectIdDigest")
    signature_verified: Literal[True] = Field(alias="signatureVerified")
    provider_livemode: Literal[False] = Field(alias="providerLivemode")
    fact_version: PositiveVersion = Field(alias="factVersion")
    observed_at: datetime = Field(alias="observedAt")


class BeneficiaryGrant(_BillingModel):
    grant_id: OpaqueText = Field(alias="grantId")
    parent_id: OpaqueText = Field(alias="parentId")
    beneficiary_id: OpaqueText = Field(alias="beneficiaryId")
    plan_id: BillingPlanId = Field(alias="planId")
    plan_version: PositiveVersion = Field(alias="planVersion")
    allowance_version: PositiveVersion = Field(alias="allowanceVersion")
    state_version: PositiveVersion = Field(alias="stateVersion")
    active_from: datetime = Field(alias="activeFrom")
    active_until: datetime | None = Field(default=None, alias="activeUntil")

    @model_validator(mode="after")
    def validate_active_period(self) -> "BeneficiaryGrant":
        if self.active_until is not None and self.active_until <= self.active_from:
            raise ValueError("activeUntil must be later than activeFrom")
        return self


class ScheduledPlanTransition(_BillingModel):
    transition_id: OpaqueText = Field(alias="transitionId")
    subscription_id_digest: Sha256Digest = Field(alias="subscriptionIdDigest")
    from_plan_id: BillingPlanId = Field(alias="fromPlanId")
    to_plan_id: BillingPlanId = Field(alias="toPlanId")
    from_plan_version: PositiveVersion = Field(alias="fromPlanVersion")
    to_plan_version: PositiveVersion = Field(alias="toPlanVersion")
    state_version: PositiveVersion = Field(alias="stateVersion")
    effective_at: datetime = Field(alias="effectiveAt")

    @model_validator(mode="after")
    def validate_transition(self) -> "ScheduledPlanTransition":
        if self.from_plan_id is self.to_plan_id:
            raise ValueError("scheduled transition must change the plan")
        if self.to_plan_version <= self.from_plan_version:
            raise ValueError("scheduled transition must advance the plan version")
        return self


class MaskedPaymentMethod(_BillingModel):
    payment_method_id_digest: Sha256Digest = Field(alias="paymentMethodIdDigest")
    brand: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=30),
    ]
    last_four: Annotated[str, StringConstraints(pattern=r"^[0-9]{4}$")] = Field(
        alias="lastFour"
    )
    expiry_month: Annotated[int, Field(strict=True, ge=1, le=12)] = Field(
        alias="expiryMonth"
    )
    expiry_year: Annotated[int, Field(strict=True, ge=2000, le=9999)] = Field(
        alias="expiryYear"
    )
    source_subscription_id_digest: Sha256Digest = Field(alias="sourceSubscriptionIdDigest")
    observation_version: PositiveVersion = Field(alias="observationVersion")
    observed_at: datetime = Field(alias="observedAt")


class BillingSupportProjection(_BillingModel):
    checkout_ref: OpaqueText = Field(alias="checkoutRef")
    state_version: PositiveVersion = Field(alias="stateVersion")
    command_state: CheckoutCommandState = Field(alias="commandState")
    public_outcome: CheckoutPublicOutcome = Field(alias="publicOutcome")
    target_plan_id: PurchasablePlanId = Field(alias="targetPlanId")
    beneficiary_ids: tuple[OpaqueText, ...] = Field(
        alias="beneficiaryIds",
        min_length=1,
        max_length=3,
    )
    safe_actions: tuple[BillingSafeAction, ...] = Field(alias="safeActions", max_length=5)
    failure_code: OpaqueText | None = Field(default=None, alias="failureCode")
    payment_method: MaskedPaymentMethod | None = Field(default=None, alias="paymentMethod")
    updated_at: datetime = Field(alias="updatedAt")

    @model_validator(mode="after")
    def validate_beneficiaries(self) -> "BillingSupportProjection":
        if len(set(self.beneficiary_ids)) != len(self.beneficiary_ids):
            raise ValueError("beneficiary IDs must be unique")
        return self


__all__ = [
    "BeneficiaryGrant",
    "BillingFact",
    "BillingFactKind",
    "BillingLifecycleState",
    "BillingPlanId",
    "BillingSafeAction",
    "BillingSupportProjection",
    "CheckoutCommandProjection",
    "CheckoutCommandState",
    "CheckoutIntent",
    "CheckoutPublicOutcome",
    "EntitlementLifecycleState",
    "MaskedPaymentMethod",
    "PurchasablePlanId",
    "ScheduledPlanTransition",
]
