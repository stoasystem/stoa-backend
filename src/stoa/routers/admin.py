"""Admin routes — user management, report operations, and platform statistics."""
import base64
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from functools import lru_cache, partial
from typing import Any, Literal, Optional, Protocol, runtime_checkable
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from stoa.config import Settings, get_settings
from stoa.db.dynamodb import get_table, stored_int
from stoa.db.repositories import (
    account_deletion_repo,
    account_invitation_repo,
    checkout_command_repo,
    parent_link_repo,
    report_repo,
    security_audit_repo,
    user_repo,
)
# Card 007: one switch and one refusal for the whole paid surface; see
# `stoa.routers.billing` for why it is frozen and what unfreezing takes.
from stoa.routers.billing import refuse_if_frozen
from stoa.routers.parents import get_billing_reconciliation_provider
from stoa.security.admin_authorization import (
    AdminTargetProvider,
    admin_operation,
    admin_target_provider,
)
from stoa.security.errors import normalize_correlation_id
from stoa.security.identity import MUST_CHANGE_PASSWORD_FIELD
from stoa.models.question import QuestionStatus
from stoa.models.moderation import (
    ModerationCaseListResponse,
    ModerationCaseNoteRequest,
    ModerationCaseResponse,
    ModerationCaseUpdateRequest,
    ModerationReason,
    ModerationSeverity,
    ModerationStatus,
)
from stoa.models import user as user_model
from stoa.models.user import SubscriptionTier
from stoa.services import (
    account_provisioning_service,
    teacher_support_allowance_service,
    locale_service,
    notify_service,
    parent_link_service,
    public_identity_service,
    moderation_service,
    release_evidence_service,
    report_recovery_job_service,
    report_recovery_service,
    account_operations_service,
    privileged_identity_service,
    billing_reconciliation_service,
    curriculum_analytics_service,
    curriculum_migration_service,
    curriculum_ops_service,
    teacher_dispatch_service,
    subscription_service,
    teacher_reply_service,
    account_verification_service,
    usage_ledger_service,
)
from stoa.services.teacher_identity_provider import CognitoTeacherIdentityProvider

router = APIRouter()


type AdminItem = dict[str, object]


@runtime_checkable
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _admin_mapping(value: object) -> AdminItem:
    if not isinstance(value, Mapping):
        raise RuntimeError("admin data dependency unavailable")
    result: AdminItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise RuntimeError("admin data dependency unavailable")
        result[key] = member
    return result


def _admin_scan(table: object, **kwargs: object) -> AdminItem:
    if not isinstance(table, _ScanTable):
        raise RuntimeError("admin data dependency unavailable")
    return _admin_mapping(table.scan(**kwargs))


def _admin_query(table: object, **kwargs: object) -> AdminItem:
    if not isinstance(table, _QueryTable):
        raise RuntimeError("admin data dependency unavailable")
    return _admin_mapping(table.query(**kwargs))


def _admin_items(response: Mapping[str, object]) -> list[AdminItem]:
    raw_items = response.get("Items", [])
    if not isinstance(raw_items, list):
        raise RuntimeError("admin data dependency unavailable")
    return [_admin_mapping(item) for item in raw_items]


def _admin_cursor(response: Mapping[str, object]) -> AdminItem | None:
    raw_cursor = response.get("LastEvaluatedKey")
    if raw_cursor is None:
        return None
    return _admin_mapping(raw_cursor)


def _admin_scan_every_page(
    table: object, *, page_budget: int, **kwargs: object
) -> tuple[list[AdminItem], bool]:
    """Every row the filter admits, and whether the walk finished.

    A single scan answers from at most one megabyte of rows read, so on any table
    past that size one call is a sample and not a census. Counting from a sample
    produces a number that looks like an answer, which is worse than no number.
    """
    rows: list[AdminItem] = []
    request = dict(kwargs)
    for _page in range(page_budget):
        result = _admin_scan(table, **request)
        rows.extend(_admin_items(result))
        cursor = _admin_cursor(result)
        if not cursor:
            return rows, True
        request["ExclusiveStartKey"] = cursor
    return rows, False


def _admin_required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError("admin data dependency unavailable")
    return value

# All historical role dependencies below resolve through the exact registered
# method/path capability table.  The name remains local only to keep the route
# signatures stable while removing role as authority.
def require_role(*_roles: str):
    return admin_operation


CURRICULUM_DRAFT_TARGET = AdminTargetProvider(
    "scalar", "body", ("publicLessonId",), ("public_lesson_id",),
    reference_only=("exercises", "description"),
)
CURRICULUM_VERSION_TARGET = AdminTargetProvider(
    "scalar", "body", ("versionId",), ("version_id",),
    reference_only=("reason", "expectedPublishedVersionId"),
)
PARENT_BINDING_TARGET = AdminTargetProvider(
    "scalar", "body", ("parent_id", "student_id"), ("parent_id", "student_id"),
    reference_only=(
        "relationship",
        "reason",
        "preview_id",
        "expected_status",
        "expected_version",
        "status",
    ),
)
BULK_REPORT_TARGETS = AdminTargetProvider(
    "collection", "request",
    ("reports.parent_id", "reports.student_id", "reports.week_start"),
    ("reports.parent_id", "reports.student_id", "reports.week_start"),
    maximum=25,
    collection_path="reports",
)
RECOVERY_FILTER_TARGETS = AdminTargetProvider(
    "resolver_collection", "request",
    ("filters.parent_id", "filters.student_id", "filters.week_start"),
    ("filters.parent_id", "filters.student_id", "filters.week_start"),
    maximum=25,
    reference_only=("reason", "max_targets", "preview_token", "filters.status"),
    resolver="report_recovery_filters",
)
RECOVERY_FILTER_PREVIEW_TARGETS = AdminTargetProvider(
    "resolver_collection", "request",
    ("filters.parent_id", "filters.student_id", "filters.week_start"),
    ("filters.parent_id", "filters.student_id", "filters.week_start"),
    maximum=25,
    required=False,
    reference_only=("reason", "max_targets", "filters.status"),
    resolver="report_recovery_filters",
)
RECOVERY_RESUME_TARGETS = AdminTargetProvider(
    "resolver_collection", "request", (),
    ("parent_id", "student_id", "week_start", "report_id"),
    maximum=25,
    reference_only=("reason", "results", "max_targets", "preview_token"),
    resolver="report_recovery_resume",
)
RECOVERY_RESUME_PREVIEW_TARGETS = AdminTargetProvider(
    "resolver_collection", "request", (),
    ("parent_id", "student_id", "week_start", "report_id"),
    maximum=25,
    required=False,
    reference_only=("reason", "results", "max_targets"),
    resolver="report_recovery_resume",
)
HANDOFF_FIXTURE_TARGET = AdminTargetProvider(
    "scalar", "body",
    ("fixture.parent_id", "fixture.student_id", "fixture.week_start"),
    ("fixture.parent_id", "fixture.student_id", "fixture.week_start"),
    required=False,
    reference_only=("reason", "operator_note", "release_evidence", "fixture.fixture_name"),
    resolver="support_handoff",
)
GOVERNANCE_REFERENCE_TARGETS = AdminTargetProvider(
    "collection", "body",
    ("references.job_id", "references.parent_id", "references.student_id", "references.week_start"),
    ("references.job_id", "references.parent_id", "references.student_id", "references.week_start"),
    maximum=10,
    required=False,
    collection_path="references",
    reference_only=("reason", "release_evidence", "break_glass", "evidence_references"),
)


class AdminProvisionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    target_email: str
    issuer: str
    subject: str
    reason: str = Field(min_length=1, max_length=1000)


class AdminStatusCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    operation: str
    provider_username: str
    reason: str = Field(min_length=1, max_length=1000)


class TeacherSupportAllowanceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekly_cases: int = Field(ge=0, le=teacher_support_allowance_service.ASSIGNED_WEEKLY_CASES_MAXIMUM)
    reason: str = Field(min_length=1, max_length=1000)


@router.get("/teacher-support/allowances/{student_id}")
async def read_teacher_support_allowance(
    student_id: str,
    user: dict = Depends(require_role("admin")),
):
    """How many teacher-support cases this student has in a week, and from where."""
    del user
    # The same 404 the write gives. Answering "7, by default" for an id that is
    # not an account made "look it up, then change it" contradict itself.
    profile = _account_profile_or_404(student_id)
    if str(profile.get("role") or "") != "student":
        raise HTTPException(status_code=409, detail={"code": "account_not_a_student"})
    table = get_table()
    raised = _admin_mapping(
        table.get_item(
            Key={
                "PK": f"USER#{student_id}",
                "SK": teacher_support_allowance_service.ASSIGNED_ALLOWANCE_SK,
            },
            ConsistentRead=True,
        )
    ).get("Item")
    stored = _admin_mapping(raised) if isinstance(raised, dict) else None
    return {
        "studentId": student_id,
        "weeklyCases": teacher_support_allowance_service.assigned_weekly_cases(stored),
        "source": "administrator" if stored else "default",
        "default": teacher_support_allowance_service.ASSIGNED_WEEKLY_TEACHER_SUPPORT_CASES,
        "maximum": teacher_support_allowance_service.ASSIGNED_WEEKLY_CASES_MAXIMUM,
    }


@router.put("/teacher-support/allowances/{student_id}")
async def set_teacher_support_allowance(
    student_id: str,
    body: TeacherSupportAllowanceCommand,
    user: dict = Depends(require_role("admin")),
):
    """Set this student's weekly figure, replacing whatever it was.

    The write carries the version it read, so two administrators changing the
    same student at once cannot both believe they set it. The admission path
    fences the same version, so a case can never be spent against a figure that
    was replaced between reading it and writing the case.
    """
    profile = _account_profile_or_404(student_id)
    if str(profile.get("role") or "") != "student":
        raise HTTPException(status_code=409, detail={"code": "account_not_a_student"})

    table = get_table()
    key = {
        "PK": f"USER#{student_id}",
        "SK": teacher_support_allowance_service.ASSIGNED_ALLOWANCE_SK,
    }
    existing = _admin_mapping(
        table.get_item(Key=key, ConsistentRead=True)
    ).get("Item")
    previous = _admin_mapping(existing) if isinstance(existing, dict) else None
    next_version = (stored_int((previous or {}).get("state_version")) or 0) + 1
    now = datetime.now(timezone.utc).isoformat()
    item = {
        **key,
        "entity_type": "teacher_support_assigned_allowance",
        "schema_version": teacher_support_allowance_service.ASSIGNED_ALLOWANCE_SCHEMA_VERSION,
        "student_id": student_id,
        "weekly_cases": body.weekly_cases,
        "state_version": next_version,
        "updated_at": now,
        "updated_by": str(user.get("sub") or user.get("user_id") or ""),
    }
    condition = (
        "attribute_not_exists(PK)"
        if previous is None
        else "state_version = :expected"
    )
    values = {} if previous is None else {":expected": next_version - 1}
    try:
        table.put_item(
            Item=item,
            ConditionExpression=condition,
            **({"ExpressionAttributeValues": values} if values else {}),
        )
    except ClientError as exc:
        # A concurrent administrator got there first. Their figure stands; this
        # one is refused rather than silently overwriting it.
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise HTTPException(
                status_code=409, detail={"code": "allowance_version_conflict"}
            ) from exc
        raise

    _record_account_admin_event(
        actor=user,
        target_id=student_id,
        event_type="teacher_support_allowance_set",
        action="set_teacher_support_allowance",
        reason_code="teacher_support_allowance_set",
        evidence_reference=f"weekly_cases={body.weekly_cases};state_version={next_version}",
    )
    return {
        "studentId": student_id,
        "weeklyCases": body.weekly_cases,
        "source": "administrator",
        "stateVersion": next_version,
    }


class CapabilityGrantCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    grant_id: str
    capability: str
    scope: str
    reason: str = Field(min_length=1, max_length=1000)
    effective_at: str
    expected_generation: int = Field(ge=0)
    expires_at: str | None = None


class CapabilityTransitionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    grant_id: str
    capability: str
    scope: str
    expected_generation: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    changed_at: str


@lru_cache(maxsize=1)
def get_privileged_identity_provider(settings: Settings = Depends(get_settings)) -> Any:
    return boto3.client("cognito-idp", region_name=settings.aws_region)


@router.post("/privileged-identities/admins")
def provision_privileged_admin(
    payload: AdminProvisionCommand,
    user: dict[str, Any] = Depends(require_role("admin")),
    provider: Any = Depends(get_privileged_identity_provider),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return privileged_identity_service.provision_admin(
        actor=user,
        provider=provider,
        user_pool_id=settings.cognito_user_pool_id,
        **payload.model_dump(),
    )


@router.post("/privileged-identities/admins/{target_id}/status")
def change_privileged_admin_status(
    target_id: str,
    payload: AdminStatusCommand,
    user: dict[str, Any] = Depends(require_role("admin")),
    provider: Any = Depends(get_privileged_identity_provider),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return privileged_identity_service.change_admin_status(
        actor=user,
        target_id=target_id,
        provider=provider,
        user_pool_id=settings.cognito_user_pool_id,
        **payload.model_dump(),
    )


@router.post("/privileged-identities/{target_id}/capabilities")
def grant_privileged_capability(
    target_id: str,
    payload: CapabilityGrantCommand,
    user: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    return privileged_identity_service.grant_capability(
        actor=user,
        target_id=target_id,
        **payload.model_dump(),
    )


@router.post("/privileged-identities/{target_id}/capabilities/revoke")
def revoke_privileged_capability(
    target_id: str,
    payload: CapabilityTransitionCommand,
    user: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    return privileged_identity_service.revoke_capability(
        actor=user,
        target_id=target_id,
        **payload.model_dump(),
    )


@router.post("/privileged-identities/{target_id}/capabilities/restore")
def restore_privileged_capability(
    target_id: str,
    payload: CapabilityTransitionCommand,
    user: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    return privileged_identity_service.restore_capability(
        actor=user,
        target_id=target_id,
        **payload.model_dump(),
    )


class UserUpdateRequest(BaseModel):
    subscription_tier: Optional[SubscriptionTier] = None
    is_active: Optional[bool] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    grade: Optional[str] = Field(default=None, min_length=1, max_length=40)
    school: Optional[str] = Field(default=None, min_length=1, max_length=160)


ACCOUNT_STATUS_INVITED = "invited"
ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_SUSPENDED = "suspended"
ACCOUNT_STATUS_ARCHIVED = "archived"

# No physical delete: an archived account keeps its number and its history.
ACCOUNT_STATUS_TRANSITIONS = {
    ACCOUNT_STATUS_ACTIVE: (ACCOUNT_STATUS_SUSPENDED, ACCOUNT_STATUS_ARCHIVED),
    ACCOUNT_STATUS_SUSPENDED: (ACCOUNT_STATUS_ACTIVE, ACCOUNT_STATUS_ARCHIVED),
    ACCOUNT_STATUS_INVITED: (ACCOUNT_STATUS_ARCHIVED,),
    ACCOUNT_STATUS_ARCHIVED: (),
}


class AccountInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1, max_length=20)
    email: str = Field(min_length=3, max_length=320)
    fullName: str = Field(default="", max_length=120)
    # Shape-checked here only; the calendar check belongs to the service, which
    # refuses by code so the rejected date never travels back out.
    dateOfBirth: Optional[str] = Field(default=None, max_length=32)
    expirySeconds: Optional[int] = Field(default=None, ge=60, le=1209600)
    locale: Optional[str] = Field(default=None, min_length=2, max_length=8)


class AccountAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1, max_length=20)
    email: str = Field(min_length=3, max_length=320)
    fullName: str = Field(default="", max_length=120)
    dateOfBirth: Optional[str] = Field(default=None, max_length=32)


class AccountInvitationReissueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expirySeconds: Optional[int] = Field(default=None, ge=60, le=1209600)
    locale: Optional[str] = Field(default=None, min_length=2, max_length=8)


class AccountPasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


class AccountStatusChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "suspended", "archived"]
    reason: str = Field(min_length=1, max_length=500)


class AdminParentLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: str = Field(min_length=1, max_length=120)
    student_id: str = Field(min_length=1, max_length=120)
    relationship: str = Field(default="child", min_length=1, max_length=40)


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


class UsageSummaryResponse(BaseModel):
    studentId: str
    parentId: str | None = None
    quotaPeriod: str
    action: str
    consumed: int
    limit: int
    remaining: int
    effectivePlan: str | None = None
    entitlementSource: str | None = None
    billingState: str | None = None
    reconciliation: dict[str, Any] = Field(default_factory=dict)
    supportAction: str | None = None
    explanation: str | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    groups: list[dict[str, Any]] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)
    partial: bool = False
    stale: bool = False
    unreconciled: bool = False


class UsageEventListResponse(BaseModel):
    items: list[dict[str, Any]]
    count: int


class UsageReconciliationResponse(BaseModel):
    studentId: str
    action: str
    quotaPeriod: str
    counterKey: str | None = None
    counterCount: int
    ledgerCount: int
    eventCount: int
    status: str
    drift: int = 0
    stale: bool = False
    supportAction: str | None = None
    explanation: str | None = None
    repairMode: str
    repaired: bool
    partial: bool


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


class ParentStudentBindingResponse(BaseModel):
    parent_id: str
    student_id: str
    relationship: str = "child"
    status: str = "active"
    source: str | None = None
    updated_at: str | None = None


class ParentStudentBindingListResponse(BaseModel):
    items: list[ParentStudentBindingResponse]
    count: int


class ParentBindingRepairPreviewRequest(BaseModel):
    parent_id: str = Field(..., min_length=1, max_length=200)
    student_id: str = Field(..., min_length=1, max_length=200)
    relationship: str = Field(default="child", min_length=1, max_length=50)
    reason: str = Field(..., min_length=1, max_length=500)


class ParentStudentBindingRepairRequest(ParentBindingRepairPreviewRequest):
    preview_id: str = Field(..., min_length=64, max_length=64)


class ParentBindingStatusTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: str = Field(..., min_length=1, max_length=200)
    student_id: str = Field(..., min_length=1, max_length=200)
    relationship: str = Field(default="child", min_length=1, max_length=50)
    expected_status: Literal[
        "active", "active_pending_verification", "inactive", "revoked"
    ]
    expected_version: int = Field(..., ge=1)
    status: Literal["active", "active_pending_verification", "inactive", "revoked"]
    reason: str = Field(..., min_length=1, max_length=500)


class ParentBindingRepairObservation(BaseModel):
    coordinate: str
    version: int | None = None
    digest: str


class ParentBindingRepairPreview(BaseModel):
    pair_id: str
    preview_id: str
    classification: user_repo.ParentBindingRepairClassification
    proposed_action: str | None = None
    observations: list[ParentBindingRepairObservation]


class ParentBindingRepairApplyResponse(BaseModel):
    disposition: user_repo.ParentBindingRepairApplyDisposition
    pair_id: str
    preview_id: str
    classification: user_repo.ParentBindingRepairClassification
    mutated: bool


class ParentBindingStatusTransitionResponse(BaseModel):
    disposition: user_repo.ParentBindingStatusDisposition
    status: str
    version: int


class AccountVerificationSupportResponse(BaseModel):
    userId: str
    email: str
    role: str
    emailVerificationStatus: str
    emailVerificationRequired: bool
    accountActivationStatus: str
    emailVerificationPolicy: str
    emailVerifiedAt: str | None = None
    emailVerificationRequestedAt: str | None = None
    emailVerificationLastResendAt: str | None = None
    emailVerificationResendCount: int = 0
    resendAllowed: bool = False
    supportRecoveryState: str
    supportAction: str
    parentBindingStatus: str | None = None


class AccountOperationsParentDetailResponse(BaseModel):
    parentId: str
    parent: dict[str, Any] = Field(default_factory=dict)
    billing: dict[str, Any] = Field(default_factory=dict)
    children: list[dict[str, Any]] = Field(default_factory=list)
    usage: list[dict[str, Any]] = Field(default_factory=list)
    supportState: dict[str, Any] = Field(default_factory=dict)


class StatsResponse(BaseModel):
    total_users: int
    total_students: int
    total_parents: int
    total_teachers: int
    total_questions: int
    ai_resolved: int
    teacher_resolved: int
    escalated: int
    teacher_sla: dict[str, Any]
    # False when a census stopped at its page budget, so the counts below are a
    # floor rather than a total. Additive: absent means the walk finished.
    counts_complete: bool = True


class CurriculumExerciseDraftRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    exercise_id: str | None = Field(default=None, alias="exerciseId", max_length=200)
    prompt: str = Field(..., min_length=1, max_length=2000)
    type: str = Field(default="text_input", min_length=1, max_length=50)
    difficulty: str = Field(default="practice", min_length=1, max_length=80)
    order: int | None = Field(default=None, ge=1, le=200)
    answer_key: str | None = Field(default=None, alias="answerKey", max_length=2000)
    explanation: str | None = Field(default=None, max_length=2000)
    skills: list[str] = Field(default_factory=list)


class CurriculumLessonDraftRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    public_lesson_id: str = Field(..., alias="publicLessonId", min_length=1, max_length=200)
    title: str = Field(..., min_length=1, max_length=300)
    objective: str = Field(..., min_length=1, max_length=1000)
    description: str | None = Field(default=None, max_length=2000)
    subject_id: str = Field(..., alias="subjectId", min_length=1, max_length=100)
    topic_id: str = Field(..., alias="topicId", min_length=1, max_length=200)
    unit_id: str | None = Field(default=None, alias="unitId", max_length=200)
    grade_level: str = Field(..., alias="gradeLevel", min_length=1, max_length=100)
    difficulty: str = Field(default="practice", min_length=1, max_length=80)
    estimated_minutes: int = Field(default=10, alias="estimatedMinutes", ge=1, le=240)
    language: str | None = Field(default=None, max_length=30)
    exercises: list[CurriculumExerciseDraftRequest] = Field(default_factory=list)


class CurriculumPublishRequest(BaseModel):
    version_id: str = Field(..., alias="versionId", min_length=1, max_length=200)
    expected_published_version_id: str | None = Field(
        default=None,
        alias="expectedPublishedVersionId",
        max_length=200,
    )
    reason: str | None = Field(default=None, max_length=500)


class CurriculumReviewNoteRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class CurriculumValidationIssueResponse(BaseModel):
    severity: str
    field: str
    message: str
    hint: str | None = None


class CurriculumValidationPreviewResponse(BaseModel):
    publicLessonId: str
    versionId: str
    status: str
    publishReady: bool
    issues: list[CurriculumValidationIssueResponse]
    issueCount: int


class CurriculumDiffResponse(BaseModel):
    publicLessonId: str
    fromVersionId: str
    toVersionId: str
    changes: list[dict[str, Any]]
    changeCount: int


class CurriculumAuditEventResponse(BaseModel):
    eventId: str
    publicLessonId: str
    versionId: str | None = None
    operation: str
    fromState: str | None = None
    toState: str | None = None
    reason: str | None = None
    actorId: str
    actorRole: str | None = None
    actorCapabilities: list[str] = Field(default_factory=list)
    createdAt: str | None = None


class CurriculumAuditResponse(BaseModel):
    publicLessonId: str
    items: list[CurriculumAuditEventResponse]
    count: int
    nextToken: str | None = None


class CurriculumMigrationDryRunResponse(BaseModel):
    migrationId: str
    confirmationToken: str
    source: dict[str, Any] = Field(default_factory=dict)
    operatorNote: str | None = None
    summary: dict[str, int]
    rows: list[dict[str, Any]]
    publishReady: bool


class CurriculumMigrationApplyRequest(BaseModel):
    manifest: dict[str, Any]
    confirmation_token: str = Field(..., alias="confirmationToken", min_length=1)


class CurriculumMigrationEvidenceResponse(BaseModel):
    migrationId: str
    status: str
    source: dict[str, Any] = Field(default_factory=dict)
    operatorNote: str | None = None
    summary: dict[str, int] = Field(default_factory=dict)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    appliedBy: str | None = None
    appliedAt: str | None = None
    idempotent: bool | None = None


class CurriculumVersionResponse(BaseModel):
    publicLessonId: str
    versionId: str
    state: str
    reviewState: str | None = None
    updatedAt: str | None = None
    updatedBy: str | None = None
    lesson: dict[str, Any] | None = None
    exercises: list[dict[str, Any]] | None = None


class CurriculumWorklistResponse(BaseModel):
    items: list[CurriculumVersionResponse]
    count: int


class CurriculumQualityMetricResponse(BaseModel):
    publicId: str
    contentType: str
    versionId: str
    subjectId: str | None = None
    topicId: str | None = None
    totalSignals: int
    wrongAnswers: int
    assignmentStarts: int = 0
    assignmentSkips: int
    assignmentArchives: int = 0
    assignmentCompletions: int = 0
    lessonCompletions: int = 0
    completions: int
    publishEvents: int
    archiveEvents: int
    priorityScore: int
    updatedAt: str | None = None


class CurriculumQualityResponse(BaseModel):
    items: list[CurriculumQualityMetricResponse]
    count: int
    privacy: dict[str, bool]


class CurriculumWarehouseReadinessResponse(BaseModel):
    state: str
    exportAllowed: bool
    liveWarehouseConfigured: bool
    schemaVersion: str
    sources: list[dict[str, Any]]
    sourceSchemas: dict[str, dict[str, Any]]
    lastMetricAt: str | None = None
    blockers: list[str]
    warnings: list[str]
    privacy: dict[str, bool]


class CurriculumWarehouseExportMetrics(BaseModel):
    totalSignals: int
    wrongAnswers: int
    assignmentStarts: int
    assignmentSkips: int
    assignmentArchives: int
    assignmentCompletions: int
    lessonCompletions: int
    completions: int
    publishEvents: int
    archiveEvents: int
    priorityScore: int


class CurriculumWarehouseExportRow(BaseModel):
    metricId: str
    schemaVersion: str
    publicId: str | None = None
    contentType: str | None = None
    versionId: str | None = None
    subjectId: str | None = None
    topicId: str | None = None
    metrics: CurriculumWarehouseExportMetrics
    aggregationWindow: str
    updatedAt: str | None = None


class CurriculumWarehouseExportResponse(BaseModel):
    schemaVersion: str
    sourceSchemas: dict[str, dict[str, Any]]
    items: list[CurriculumWarehouseExportRow]
    count: int
    filters: dict[str, Any]
    window: dict[str, Any]
    privacy: dict[str, bool]


class CurriculumAnalyticsDashboardResponse(BaseModel):
    generatedAt: str
    filters: dict[str, Any]
    sampleSize: int
    sampled: bool
    summary: dict[str, int]
    sequencingCoverage: dict[str, int]
    qualityHotspots: list[CurriculumQualityMetricResponse]
    interventions: list[dict[str, Any]]
    emptyState: str | None = None
    privacy: dict[str, bool]


@router.get("/moderation/cases", response_model=ModerationCaseListResponse)
async def list_moderation_cases(
    limit: int = Query(default=50, ge=1, le=100),
    status: ModerationStatus | None = Query(default=None),
    severity: ModerationSeverity | None = Query(default=None),
    reason: ModerationReason | None = Query(default=None),
    reporter_role: Optional[str] = Query(default=None),
    assignee: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List moderation cases for internal operations."""
    items = moderation_service.list_cases(
        limit=limit,
        status=status.value if status else None,
        severity=severity.value if severity else None,
        reason=reason.value if reason else None,
        reporter_role=reporter_role,
        assignee=assignee,
        date_from=date_from,
        date_to=date_to,
    )
    responses = [ModerationCaseResponse.model_validate(item) for item in items]
    return ModerationCaseListResponse(items=responses, count=len(responses))


@router.get("/moderation/cases/{case_id}", response_model=ModerationCaseResponse)
async def get_moderation_case(
    case_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Open a moderation case with context and audit history."""
    return moderation_service.get_case(case_id)


@router.patch("/moderation/cases/{case_id}", response_model=ModerationCaseResponse)
async def update_moderation_case(
    case_id: str,
    body: ModerationCaseUpdateRequest,
    user: dict = Depends(require_role("admin")),
):
    """Assign, transition, or resolve a moderation case."""
    return moderation_service.update_case(case_id, body, user)


@router.post("/moderation/cases/{case_id}/notes", response_model=ModerationCaseResponse)
async def add_moderation_case_note(
    case_id: str,
    body: ModerationCaseNoteRequest,
    user: dict = Depends(require_role("admin")),
):
    """Append an internal moderation note."""
    return moderation_service.add_note(case_id, body, user)


@router.get("/curriculum/worklist", response_model=CurriculumWorklistResponse)
async def list_curriculum_authoring_worklist(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    user: dict = Depends(require_role("admin", "teacher")),
):
    """List internal curriculum authoring items awaiting operational action."""
    return curriculum_ops_service.list_worklist(status=status, limit=limit)


@router.get("/curriculum/analytics/content-quality", response_model=CurriculumQualityResponse)
async def get_curriculum_content_quality(
    content_type: str | None = Query(default=None, alias="contentType"),
    subject_id: str | None = Query(default=None, alias="subjectId"),
    topic_id: str | None = Query(default=None, alias="topicId"),
    limit: int = Query(default=100, ge=1, le=200),
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Return aggregate-only curriculum quality metrics for operators."""
    return curriculum_analytics_service.content_quality_summary(
        content_type=content_type,
        subject_id=subject_id,
        topic_id=topic_id,
        limit=limit,
    )


@router.get("/curriculum/analytics/warehouse-readiness", response_model=CurriculumWarehouseReadinessResponse)
async def get_curriculum_warehouse_readiness(
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Return local warehouse analytics readiness without requiring live BI infrastructure."""
    return curriculum_analytics_service.warehouse_readiness()


@router.get("/curriculum/analytics/warehouse-export", response_model=CurriculumWarehouseExportResponse)
async def get_curriculum_warehouse_export(
    content_type: str | None = Query(default=None, alias="contentType"),
    subject_id: str | None = Query(default=None, alias="subjectId"),
    topic_id: str | None = Query(default=None, alias="topicId"),
    limit: int = Query(default=100, ge=1, le=250),
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Return bounded aggregate rows shaped for future warehouse ingestion."""
    return curriculum_analytics_service.warehouse_export(
        content_type=content_type,
        subject_id=subject_id,
        topic_id=topic_id,
        limit=limit,
    )


@router.get("/curriculum/analytics/dashboard", response_model=CurriculumAnalyticsDashboardResponse)
async def get_curriculum_analytics_dashboard(
    subject_id: str | None = Query(default=None, alias="subjectId"),
    topic_id: str | None = Query(default=None, alias="topicId"),
    limit: int = Query(default=100, ge=1, le=250),
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Return aggregate operator dashboard signals for curriculum and sequencing health."""
    return curriculum_analytics_service.operator_dashboard(
        subject_id=subject_id,
        topic_id=topic_id,
        limit=limit,
    )


@router.post("/curriculum/lessons/drafts", response_model=CurriculumVersionResponse)
@admin_target_provider(CURRICULUM_DRAFT_TARGET)
async def create_curriculum_lesson_draft(
    body: CurriculumLessonDraftRequest,
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Create an internal lesson-plus-exercises authoring draft."""
    return curriculum_ops_service.create_lesson_draft(body.model_dump(by_alias=False), user)


@router.post(
    "/curriculum/migrations/dry-run",
    response_model=CurriculumMigrationDryRunResponse,
)
async def dry_run_curriculum_migration(
    manifest: dict[str, Any] = Body(...),
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Validate a curriculum migration manifest without mutating content state."""
    return curriculum_migration_service.dry_run(manifest, user)


@router.post(
    "/curriculum/migrations/{migration_id}/apply",
    response_model=CurriculumMigrationEvidenceResponse,
)
async def apply_curriculum_migration(
    migration_id: str,
    body: CurriculumMigrationApplyRequest,
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Apply a confirmed curriculum migration manifest and persist evidence."""
    return curriculum_migration_service.apply_migration(
        migration_id,
        body.manifest,
        body.confirmation_token,
        user,
    )


@router.get(
    "/curriculum/migrations/{migration_id}",
    response_model=CurriculumMigrationEvidenceResponse,
)
async def read_curriculum_migration(
    migration_id: str,
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Read evidence for an applied curriculum migration."""
    return curriculum_migration_service.get_migration(migration_id, user)


@router.get("/curriculum/lessons/{public_lesson_id}/preview", response_model=CurriculumVersionResponse)
async def preview_curriculum_lesson_version(
    public_lesson_id: str,
    version_id: str = Query(..., alias="versionId"),
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Preview an unpublished curriculum version without changing student reads."""
    return curriculum_ops_service.preview_lesson(public_lesson_id, version_id)


@router.get("/curriculum/lessons/{public_lesson_id}/diff", response_model=CurriculumDiffResponse)
async def diff_curriculum_lesson_versions(
    public_lesson_id: str,
    from_version_id: str = Query(..., alias="fromVersionId"),
    to_version_id: str = Query(..., alias="toVersionId"),
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Return a bounded structural diff between two curriculum versions."""
    return curriculum_ops_service.diff_lesson_versions(
        public_lesson_id,
        from_version_id,
        to_version_id,
        user,
    )


@router.get("/curriculum/lessons/{public_lesson_id}/audit", response_model=CurriculumAuditResponse)
async def read_curriculum_lesson_audit(
    public_lesson_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Read bounded lifecycle audit events for one curriculum lesson."""
    return curriculum_ops_service.audit_lesson(public_lesson_id, user, limit=limit)


@router.patch(
    "/curriculum/lessons/{public_lesson_id}/drafts/{version_id}",
    response_model=CurriculumVersionResponse,
)
async def patch_curriculum_lesson_draft(
    public_lesson_id: str,
    version_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Patch a draft curriculum lesson without changing published student reads."""
    return curriculum_ops_service.patch_lesson_draft(public_lesson_id, version_id, body, user)


@router.post(
    "/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/validation-preview",
    response_model=CurriculumValidationPreviewResponse,
)
async def preview_curriculum_lesson_validation(
    public_lesson_id: str,
    version_id: str,
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Validate draft publish readiness without mutating the curriculum version."""
    return curriculum_ops_service.validation_preview(public_lesson_id, version_id, user)


@router.post(
    "/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/submit-review",
    response_model=CurriculumVersionResponse,
)
async def submit_curriculum_lesson_review(
    public_lesson_id: str,
    version_id: str,
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Move a draft curriculum version into QA review."""
    return curriculum_ops_service.submit_review(public_lesson_id, version_id, user)


@router.post(
    "/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/approve",
    response_model=CurriculumVersionResponse,
)
async def approve_curriculum_lesson_version(
    public_lesson_id: str,
    version_id: str,
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Approve a reviewed curriculum version for admin publish."""
    return curriculum_ops_service.approve(public_lesson_id, version_id, user)


@router.post(
    "/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/request-changes",
    response_model=CurriculumVersionResponse,
)
async def request_curriculum_lesson_changes(
    public_lesson_id: str,
    version_id: str,
    body: CurriculumReviewNoteRequest,
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Return a curriculum version to authoring with review notes."""
    return curriculum_ops_service.request_changes(public_lesson_id, version_id, user, body.reason)


@router.post("/curriculum/lessons/{public_lesson_id}/publish")
@admin_target_provider(CURRICULUM_VERSION_TARGET)
async def publish_curriculum_lesson_version(
    public_lesson_id: str,
    body: CurriculumPublishRequest,
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Publish an approved curriculum version through a conditional manifest update."""
    return curriculum_ops_service.publish(
        public_lesson_id,
        body.version_id,
        user,
        expected_published_version_id=body.expected_published_version_id,
        reason=body.reason,
    )


@router.post("/curriculum/lessons/{public_lesson_id}/rollback")
@admin_target_provider(CURRICULUM_VERSION_TARGET)
async def rollback_curriculum_lesson_version(
    public_lesson_id: str,
    body: CurriculumPublishRequest,
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Rollback the published curriculum pointer to a previous safe version."""
    return curriculum_ops_service.rollback(
        public_lesson_id,
        body.version_id,
        user,
        expected_published_version_id=body.expected_published_version_id,
        reason=body.reason or "rollback requested",
    )


@router.post("/curriculum/lessons/{public_lesson_id}/archive")
@admin_target_provider(CURRICULUM_VERSION_TARGET)
async def archive_curriculum_lesson_version(
    public_lesson_id: str,
    body: CurriculumPublishRequest,
    user: dict = Depends(require_role("admin", "teacher")),
):
    """Archive a curriculum version when no active assignments block it."""
    return curriculum_ops_service.archive(
        public_lesson_id,
        body.version_id,
        user,
        reason=body.reason or "archive requested",
    )


class ReportOperationResponse(BaseModel):
    report_id: str
    parent_id: str
    student_id: str
    student_name: str | None = None
    week_start: str
    status: str | None = None
    email_status: str | None = None
    artifacts: dict[str, bool]
    generation: dict[str, str | None]
    delivery: dict[str, str | None]
    operations: dict[str, str | None]
    actions: dict[str, dict[str, str | bool | None]]


class ReportOperationListResponse(BaseModel):
    items: list[ReportOperationResponse]
    count: int
    next_token: str | None = None
    access_pattern: str


class ReportResendResponse(BaseModel):
    report_id: str
    status: str
    email_status: str
    operation: str
    operation_result: str
    updated_at: str


class ReportResendTarget(BaseModel):
    parent_id: str
    student_id: str
    week_start: str


class BulkReportResendRequest(BaseModel):
    reports: list[ReportResendTarget] = Field(..., min_length=1, max_length=25)


class BulkReportResendItemResult(BaseModel):
    parent_id: str
    student_id: str
    week_start: str
    result: str
    report_id: str | None = None
    status: str | None = None
    email_status: str | None = None
    operation: str = "resend_email"
    operation_result: str | None = None
    updated_at: str | None = None
    detail: str | None = None
    error_class: str | None = None


class BulkReportResendResponse(BaseModel):
    operation: str
    count: int
    results: list[BulkReportResendItemResult]


class ReportGenerationRetryResponse(BaseModel):
    report_id: str
    status: str
    email_status: str | None = None
    operation: str
    operation_result: str
    updated_at: str
    artifacts: dict[str, bool]


class ReportEditDraftRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    proposed_fields: dict[str, Any] = Field(..., min_length=1)


class ReportEditDraftResponse(BaseModel):
    draft_id: str
    report_id: str
    parent_id: str | None = None
    student_id: str | None = None
    week_start: str | None = None
    source_updated_at: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    reason: str | None = None
    proposed_fields: dict[str, str | None]
    status: str
    applied_by: str | None = None
    applied_at: str | None = None


class ReportEditApplyResponse(BaseModel):
    operation: str
    operation_result: str
    draft: ReportEditDraftResponse
    report: dict[str, Any]


class ReportArtifactEditPreviewRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    proposed_fields: dict[str, Any] = Field(..., min_length=1)


class ReportArtifactEditDiffItem(BaseModel):
    field: str
    before: Any = None
    after: Any = None
    changed: bool


class ReportArtifactEditPreviewResponse(BaseModel):
    draft_id: str
    report_id: str
    parent_id: str | None = None
    student_id: str | None = None
    week_start: str | None = None
    source_updated_at: str | None = None
    source_artifact_version_id: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    reason: str | None = None
    proposed_fields: dict[str, Any]
    diff: list[ReportArtifactEditDiffItem]
    status: str
    applied_by: str | None = None
    applied_at: str | None = None
    artifact_version_id: str | None = None


class ReportArtifactEditApplyRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class ReportArtifactEditApplyResponse(BaseModel):
    operation: str
    operation_result: str
    draft: ReportArtifactEditPreviewResponse
    report: dict[str, Any]


class ReportArtifactRollbackPreviewRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class ReportArtifactRollbackPreviewResponse(BaseModel):
    preview_id: str
    report_id: str
    parent_id: str | None = None
    student_id: str | None = None
    week_start: str | None = None
    source_updated_at: str | None = None
    source_artifact_version_id: str | None = None
    target_artifact_version_id: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    reason: str | None = None
    status: str
    validation_result: str
    applied_by: str | None = None
    applied_at: str | None = None
    artifact_version_id: str | None = None


class ReportArtifactRollbackApplyRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class ReportArtifactRollbackApplyResponse(BaseModel):
    operation: str
    operation_result: str
    preview: ReportArtifactRollbackPreviewResponse
    report: dict[str, Any]


class ReportAuditEventResponse(BaseModel):
    event_id: str
    event_at: str
    report_id: str | None = None
    parent_id: str | None = None
    student_id: str | None = None
    week_start: str | None = None
    actor: str | None = None
    action: str
    reason: str | None = None
    source: str | None = None
    result: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    error_class: str | None = None
    error_message: str | None = None
    correlation_id: str | None = None


class ReportAuditListResponse(BaseModel):
    items: list[ReportAuditEventResponse]
    count: int
    next_token: str | None = None
    scope: str


class RecoveryJobFilters(BaseModel):
    status: str = "email_failed"
    week_start: str | None = None
    parent_id: str | None = None
    student_id: str | None = None


class RecoveryJobPreviewRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    filters: RecoveryJobFilters = Field(default_factory=RecoveryJobFilters)
    max_targets: int = Field(default=25, ge=1, le=25)


class RecoveryJobPreviewTarget(BaseModel):
    target_id: str
    report_id: str | None = None
    parent_id: str | None = None
    student_id: str | None = None
    student_name: str | None = None
    week_start: str | None = None
    status: str | None = None
    email_status: str | None = None
    artifacts: dict[str, bool]
    eligibility: str
    refusal_reason: str | None = None


class RecoveryJobResumePreviewTarget(RecoveryJobPreviewTarget):
    source_result: str | None = None
    detail: str | None = None
    error_class: str | None = None


class RecoveryJobPreviewResponse(BaseModel):
    operation: str
    reason: str
    requested_by: str
    filters: dict[str, str | None]
    max_targets: int
    scanned_pages: int
    eligible_count: int
    refused_count: int
    missing_count: int
    sample: list[RecoveryJobPreviewTarget]
    preview_token: str


class RecoveryJobResumePreviewRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    results: list[str] = Field(default_factory=lambda: ["failed", "refused", "not_found"])
    max_targets: int = Field(default=25, ge=1, le=25)


class RecoveryJobResumePreviewResponse(BaseModel):
    operation: str
    source_job_id: str
    job_type: str
    reason: str
    requested_by: str
    result_filters: list[str]
    max_targets: int
    scanned_targets: int
    eligible_count: int
    refused_count: int
    missing_count: int
    sample: list[RecoveryJobResumePreviewTarget]
    preview_token: str


class RecoveryJobResumeCreateRequest(RecoveryJobResumePreviewRequest):
    preview_token: str = Field(..., min_length=1)


class RecoveryJobCreateRequest(RecoveryJobPreviewRequest):
    preview_token: str = Field(..., min_length=1)


class RecoveryJobResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    reason: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    cancellation_requested_by: str | None = None
    cancellation_requested_at: str | None = None
    filters: dict[str, Any] | None = None
    target_count: int = 0
    pending_count: int = 0
    attempted_count: int = 0
    success_count: int = 0
    refused_count: int = 0
    not_found_count: int = 0
    failed_count: int = 0
    skipped_cancelled_count: int = 0
    stop_reason: str | None = None
    source_job_id: str | None = None
    resume_result_filters: list[str] | None = None


class RecoveryJobListResponse(BaseModel):
    items: list[RecoveryJobResponse]
    count: int
    next_token: str | None = None


class RecoveryJobTargetResponse(BaseModel):
    target_id: str
    report_id: str | None = None
    parent_id: str | None = None
    student_id: str | None = None
    student_name: str | None = None
    week_start: str | None = None
    result: str
    status: str | None = None
    email_status: str | None = None
    detail: str | None = None
    error_class: str | None = None
    attempted_at: str | None = None
    completed_at: str | None = None


class RecoveryJobTargetsResponse(BaseModel):
    items: list[RecoveryJobTargetResponse]
    count: int
    next_token: str | None = None


class SupportHandoffFixtureReference(BaseModel):
    fixture_name: str = Field(..., min_length=1, max_length=200)
    parent_id: str | None = None
    student_id: str | None = None
    week_start: str | None = None
    expected_artifact_version: str | None = None


class SupportHandoffPackageRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    destination_mode: str = Field(default="preview", min_length=1, max_length=50)
    recovery_job_ids: list[str] = Field(default_factory=list, max_length=5)
    include_targets: bool = True
    include_job_audit: bool = True
    include_report_audit: bool = False
    target_limit: int = Field(default=50, ge=1, le=100)
    audit_limit: int = Field(default=50, ge=1, le=100)
    release_evidence: dict[str, Any] | None = None
    fixture: SupportHandoffFixtureReference | None = None
    operator_note: str | None = Field(default=None, max_length=1000)


class SupportHandoffRetryRequest(BaseModel):
    reason: str = Field(default="retry provider delivery", min_length=1, max_length=500)


class SupportHandoffProviderSyncRequest(BaseModel):
    provider_event_id: str = Field(..., min_length=1, max_length=200)
    provider_status: str = Field(..., min_length=1, max_length=100)
    provider_updated_at: str = Field(..., min_length=1, max_length=100)
    provider_assignee: str | None = Field(default=None, max_length=200)
    provider_priority: str | None = Field(default=None, max_length=100)


class SupportHandoffMessageRequest(BaseModel):
    template: str = Field(..., min_length=1, max_length=100)
    destination: str = Field(default="customer_email", min_length=1, max_length=100)
    trigger: str = Field(default="manual", min_length=1, max_length=100)
    customer_opted_out: bool = False


class AuditRetentionReference(BaseModel):
    scope: str = Field(..., min_length=1, max_length=50)
    job_id: str | None = Field(default=None, max_length=200)
    parent_id: str | None = Field(default=None, max_length=200)
    student_id: str | None = Field(default=None, max_length=200)
    week_start: str | None = Field(default=None, max_length=50)
    package_id: str | None = Field(default=None, max_length=200)
    release_evidence: dict[str, Any] | None = None


class AuditRetentionStatusRequest(BaseModel):
    references: list[AuditRetentionReference] = Field(..., min_length=1, max_length=10)
    limit: int = Field(default=10, ge=1, le=10)


class AuditRetentionManifestRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    references: list[AuditRetentionReference] = Field(..., min_length=1, max_length=10)
    retention_category: str = Field(default="operational", min_length=1, max_length=50)
    retention_action: str = Field(default="seal_metadata", min_length=1, max_length=50)
    target_limit: int = Field(default=25, ge=1, le=100)
    audit_limit: int = Field(default=25, ge=1, le=100)


class ImmutableEvidencePersistRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    references: list[AuditRetentionReference] = Field(..., min_length=1, max_length=10)
    retention_category: str = Field(default="operational", min_length=1, max_length=50)
    target_limit: int = Field(default=25, ge=1, le=100)
    audit_limit: int = Field(default=25, ge=1, le=100)


class LegalHoldMetadataRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    references: list[AuditRetentionReference] = Field(..., min_length=1, max_length=10)
    action: str = Field(default="apply", min_length=1, max_length=50)
    policy_id: str = Field(default="operational-default", min_length=1, max_length=100)


class RetentionGovernanceStatusRequest(BaseModel):
    policy_version: str = Field(default="retention-policy-v1", min_length=1, max_length=120)
    references: list[AuditRetentionReference] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=10, ge=1, le=10)


class RetentionApprovalMetadataRequest(BaseModel):
    policy_version: str = Field(..., min_length=1, max_length=120)
    retention_mode: str = Field(..., min_length=1, max_length=50)
    retention_days: int = Field(..., ge=1, le=3650)
    policy_owner: str = Field(..., min_length=1, max_length=200)
    legal_compliance_approver: str = Field(..., min_length=1, max_length=200)
    approval_state: str = Field(..., min_length=1, max_length=50)
    reason: str = Field(..., min_length=1, max_length=500)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    next_review_due_at: str | None = Field(default=None, max_length=80)


class LegalHoldReviewMetadataRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    references: list[AuditRetentionReference] = Field(..., min_length=1, max_length=10)
    owner: str = Field(..., min_length=1, max_length=200)
    reviewer: str = Field(..., min_length=1, max_length=200)
    review_cadence: str = Field(..., min_length=1, max_length=100)
    outcome: str = Field(default="reviewed", min_length=1, max_length=50)
    next_review_due_at: str | None = Field(default=None, max_length=80)
    break_glass: dict[str, Any] | None = None


def _account_status_of(profile: Mapping[str, object]) -> str:
    stored = str(profile.get("account_status") or "").strip()
    if stored:
        return stored
    # Rows written before the status machine existed carry only `is_active`.
    return ACCOUNT_STATUS_ACTIVE if profile.get("is_active", True) else ACCOUNT_STATUS_SUSPENDED


def _account_number_of(user_id: str) -> str:
    profile = user_repo.get_user(user_id)
    return str((profile or {}).get("account_number") or "")


def _linked_counterparts(profile: Mapping[str, object]) -> list[dict[str, str]]:
    """Confirmed links only; a pending request must never read as a binding."""
    role = str(profile.get("role") or "")
    user_id = str(profile.get("user_id") or "")
    if not user_id:
        return []
    if role == "parent":
        pairs = [
            (str(link.get("student_id") or ""), link)
            for link in parent_link_service.active_children(user_id)
        ]
    elif role == "student":
        pairs = [
            (str(link.get("parent_id") or ""), link)
            for link in parent_link_repo.list_links_for_student(user_id)
            if link.get("status") == parent_link_repo.STATUS_ACTIVE
        ]
    else:
        return []
    return [
        {
            "userId": counterpart_id,
            "accountNumber": _account_number_of(counterpart_id),
            "status": str(link.get("status") or ""),
        }
        for counterpart_id, link in pairs
        if counterpart_id
    ]


# Card 002-D / B2: this list answers `student_support_lookup`, the support desk
# capability, one rung below the identity manager. The listed account is therefore
# built from the fields named here rather than from the stored row minus whatever
# looked secret, so a field a later card adds to the PROFILE row stays unpublished
# until somebody puts it on this list on purpose.
ACCOUNT_LIST_FIELDS: tuple[tuple[str, str], ...] = (
    ("userId", "user_id"),
    ("accountNumber", "account_number"),
    ("name", "name"),
    ("email", "email"),
    ("role", "role"),
    ("createdAt", "created_at"),
    ("lastLoginAt", "last_login_at"),
)


def _project_account_row(
    profile: Mapping[str, object], *, account_status: str, at: datetime | None = None
) -> dict[str, object]:
    """Construct one listed account from named scalars, never by redacting a row."""
    projected: dict[str, object] = {}
    for exposed, stored in ACCOUNT_LIST_FIELDS:
        value = profile.get(stored)
        if value is None:
            projected[exposed] = ""
            continue
        if not isinstance(value, (str, int, bool)):
            raise RuntimeError("admin data dependency unavailable")
        projected[exposed] = value if isinstance(value, str) else str(value)
    projected["accountStatus"] = account_status
    # Card 008: the console needs to know which accounts must be linked by an
    # administrator. It gets the answer, never the date - a birthday is personal
    # data, and `ACCOUNT_LIST_FIELDS` above stays the only door a stored field
    # leaves by.
    # The moment is a parameter so a test can pin one: read from the clock here,
    # the only assertion on this value would be true until the fixture's child
    # grew up, and then fail on a date nobody chose.
    projected["isMinor"] = user_model.account_is_minor(
        profile, at=at or datetime.now(timezone.utc)
    )
    # `isMinor` is fail-closed: an account with no stored birthday answers "minor"
    # so that every protection decision errs the safe way. Shown on its own that
    # reads as a fact about the person, and the console was labelling every
    # account - administrators included - a minor. This says whether anybody ever
    # told us, so the console can say "unknown" instead of guessing. Still no date.
    projected["minorKnown"] = bool(
        str(profile.get(user_model.DATE_OF_BIRTH_FIELD) or "").strip()
    )
    return projected


def _issued_invitation_id(profile: Mapping[str, object]) -> str:
    """The live invitation an `invited` account can actually be reissued from.

    Card 002-D / B5: the console used to resend against the account id, which the
    reissue command resolves through a pointer row keyed by invitation id, so the
    button could only ever answer 404. Both rows already carry the address, so the
    id is read back through the address index. The invitation id is a handle, not a
    credential - the token and its digest stay where they are.
    """
    email = str(profile.get("email") or "").strip()
    account_id = str(profile.get("user_id") or "").strip()
    if not email or not account_id:
        return ""
    response = _admin_query(
        get_table(),
        IndexName="GSI-Email",
        KeyConditionExpression=Key("email").eq(email),
        FilterExpression=(
            Attr("entity_type").eq("account_invitation")
            & Attr("status").eq(account_invitation_repo.ISSUED_STATUS)
            & Attr("account_id").eq(account_id)
        ),
    )
    live = sorted(
        _admin_items(response),
        key=lambda row: str(row.get("issued_at") or ""),
    )
    return str(live[-1].get("invitation_id") or "") if live else ""


def _keyword_matches(profile: Mapping[str, object], keyword: str) -> bool:
    needle = keyword.strip().casefold()
    if not needle:
        return True
    return any(
        needle in str(profile.get(field) or "").casefold()
        for field in ("name", "email", "account_number", "user_id")
    )


def _within_created_range(
    profile: Mapping[str, object], created_from: str | None, created_to: str | None
) -> bool:
    created_at = str(profile.get("created_at") or "")
    if created_from and created_at < created_from:
        return False
    if created_to and created_at > created_to:
        return False
    return True


# One scan page is rows read, not accounts found: `Limit` is applied before the
# filter, so on a table whose lessons and attempts outnumber its profiles a page
# can hold no account at all. The walk follows the continuation key until the
# requested page is full, and stops at a budget so it cannot become a table walk.
ADMIN_USER_SCAN_PAGE_SIZE = 200
ADMIN_USER_SCAN_MAX_PAGES = 25


@router.get("/users")
async def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    role: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    created_from: Optional[str] = Query(default=None, max_length=40),
    created_to: Optional[str] = Query(default=None, max_length=40),
    cursor: Optional[str] = Query(default=None, max_length=2000),
    user: dict = Depends(require_role("admin")),
):
    """One page of accounts, grouped by role, with their confirmed parent links.

    Card 002 #7: the links are resolved one account at a time, so the cost of a
    page is the page size times the links behind it, not the page size. Measured
    on a full page of parents with three children each: 3201 DynamoDB round trips,
    against a 29 second API Gateway ceiling. The number is pinned by
    tests/test_admin_user_list_read_amplification.py so it cannot grow unnoticed;
    batching it down needs `parent_link_service.active_link`, not this file.
    """
    table = get_table()

    filter_expr = "#entity = :profile"
    attr_names = {"#entity": "SK"}
    attr_values: dict[str, object] = {":profile": "PROFILE"}

    if role:
        filter_expr += " AND #role = :role"
        attr_names["#role"] = "role"
        attr_values[":role"] = role

    scan_kwargs: dict[str, object] = {
        "FilterExpression": filter_expr,
        "ExpressionAttributeNames": attr_names,
        "ExpressionAttributeValues": attr_values,
        "Limit": ADMIN_USER_SCAN_PAGE_SIZE,
    }
    if cursor:
        try:
            decoded = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail={"code": "cursor_invalid"}) from exc
        if not isinstance(decoded, dict):
            raise HTTPException(status_code=422, detail={"code": "cursor_invalid"})
        scan_kwargs["ExclusiveStartKey"] = decoded

    items: list[dict[str, object]] = []
    groups: dict[str, int] = {}
    next_key: Mapping[str, object] | None = None
    full = False

    for _page in range(ADMIN_USER_SCAN_MAX_PAGES):
        result = _admin_scan(table, **scan_kwargs)
        for row in _admin_items(result):
            row_key = {"PK": row.get("PK"), "SK": row.get("SK")}
            row.pop("PK", None)
            row.pop("SK", None)
            account_status = _account_status_of(row)
            if status and account_status != status:
                continue
            if q and not _keyword_matches(row, q):
                continue
            if not _within_created_range(row, created_from, created_to):
                continue
            row_role = str(row.get("role") or "unknown")
            groups[row_role] = groups.get(row_role, 0) + 1
            item = _project_account_row(row, account_status=account_status)
            item["role"] = row_role
            item["linkedAccounts"] = _linked_counterparts(row)
            if account_status == ACCOUNT_STATUS_INVITED:
                invitation_id = _issued_invitation_id(row)
                if invitation_id:
                    item["invitationId"] = invitation_id
            items.append(item)
            if len(items) >= limit:
                # Resume at the row just handed out, so the next page neither
                # repeats it nor skips the rest of the scan page it came from.
                next_key = row_key
                full = True
                break
        if full:
            break
        page_key = _admin_cursor(result)
        if not page_key:
            break
        scan_kwargs["ExclusiveStartKey"] = page_key
    else:
        # The budget ran out. Say the walk stopped rather than that it finished.
        next_key = _admin_cursor(result)

    next_cursor = (
        base64.urlsafe_b64encode(json.dumps(next_key, default=str).encode("utf-8")).decode("ascii")
        if next_key
        else None
    )
    return {
        "items": items,
        "count": len(items),
        "groups": groups,
        "nextCursor": next_cursor,
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    user: dict = Depends(require_role("admin")),
):
    """Update a user's subscription tier or active status."""
    profile = user_repo.get_user(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    update_parts = []
    attr_values: dict = {}

    attr_names: dict[str, str] = {}

    if body.subscription_tier is not None:
        update_parts.append("subscription_tier = :tier")
        attr_values[":tier"] = body.subscription_tier.value
    if body.is_active is not None:
        update_parts.append("is_active = :active")
        attr_values[":active"] = body.is_active
    if body.name is not None:
        update_parts.append("#name = :name")
        attr_names["#name"] = "name"
        attr_values[":name"] = body.name
    if body.grade is not None:
        update_parts.append("grade = :grade")
        attr_values[":grade"] = body.grade
    if body.school is not None:
        update_parts.append("school = :school")
        attr_values[":school"] = body.school

    if not update_parts:
        return {"user_id": user_id, "message": "Nothing to update"}

    changed = {
        field: present
        for field, present in (
            ("subscription_tier", body.subscription_tier is not None),
            ("is_active", body.is_active is not None),
            ("name", body.name is not None),
            ("grade", body.grade is not None),
            ("school", body.school is not None),
        )
        if present
    }
    user_repo.update_profile_fields(
        user_id,
        update_expression="SET " + ", ".join(update_parts),
        expression_attribute_values=attr_values,
        expression_attribute_names=attr_names or None,
        owned_fields=frozenset(changed),
    )
    _record_account_admin_event(
        actor=user,
        target_id=user_id,
        event_type="account_profile_edited",
        action="update_account_profile",
        reason_code=",".join(sorted(changed)),
        evidence_reference=_account_change_evidence(profile, attr_values, attr_names),
    )
    return {"user_id": user_id, "updated": {k.lstrip(":"): v for k, v in attr_values.items()}}


# ---------------------------------------------------------------------------
# Account provisioning, password reset, status machine and parent links
# ---------------------------------------------------------------------------


def get_account_identity_provider(settings: Settings = Depends(get_settings)) -> Any:
    """Role-neutral account creator; the teacher adapter already speaks this shape."""
    return CognitoTeacherIdentityProvider(
        boto3.client("cognito-idp", region_name=settings.aws_region),
        user_pool_id=settings.cognito_user_pool_id,
    )


def get_account_password_administrator(settings: Settings = Depends(get_settings)) -> Any:
    return boto3.client("cognito-idp", region_name=settings.aws_region)


def _account_issuer(settings: Settings) -> str:
    return public_identity_service.canonical_public_issuer(settings.allowed_cognito_issuers)


def _invitation_delivery(locale: str | None):
    candidate = locale or locale_service.request_locale() or locale_service.DEFAULT_LOCALE
    try:
        resolved = locale_service.normalize_locale(candidate)
    except ValueError:
        resolved = locale_service.DEFAULT_LOCALE
    return partial(notify_service.send_account_invitation_email, locale=resolved)


def _record_account_admin_event(
    *,
    actor: Mapping[str, object],
    target_id: str,
    event_type: str,
    action: str,
    reason_code: str = "",
    evidence_reference: str = "",
) -> None:
    """One durable row per administrator write against an account."""
    event: dict[str, object] = {
        "event_id": f"event_{uuid4().hex}",
        "event_type": event_type,
        "actor_id": str(actor.get("user_id") or actor.get("sub") or ""),
        "actor_role": str(actor.get("role") or ""),
        "target_id": target_id,
        "target_type": "account",
        "action": action,
        "created_at": _now_iso(),
    }
    if reason_code:
        event["reason_code"] = reason_code[:200]
    if evidence_reference:
        event["evidence_reference"] = evidence_reference[:400]
    security_audit_repo.append_event(target_id, event)


def _account_change_evidence(
    profile: Mapping[str, object],
    attr_values: Mapping[str, object],
    attr_names: Mapping[str, str],
) -> str:
    """Before and after for every field this command actually writes."""
    parts: list[str] = []
    for alias, value in attr_values.items():
        field = attr_names.get(f"#{alias.lstrip(':')}", alias.lstrip(":"))
        parts.append(f"{field}:{profile.get(field)!s}->{value!s}")
    return ";".join(sorted(parts))


def _account_profile_or_404(user_id: str) -> dict[str, Any]:
    profile = user_repo.get_user(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail={"code": "account_not_found"})
    return dict(profile)


def _account_email_or_409(profile: Mapping[str, object]) -> str:
    email = str(profile.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=409, detail={"code": "account_email_missing"})
    return email


# One census page is one scan call; the answer short-circuits on the first other
# active administrator, so the usual table never reaches the second page.
ADMIN_CENSUS_PAGE_SIZE = 200
ADMIN_CENSUS_MAX_PAGES = 25


def _another_active_admin_exists(target_id: str) -> bool:
    """True only when some administrator other than `target_id` is still active."""
    table = get_table()
    scan_kwargs: dict[str, object] = {
        "FilterExpression": "#entity = :profile AND #role = :role",
        "ExpressionAttributeNames": {"#entity": "SK", "#role": "role"},
        "ExpressionAttributeValues": {":profile": "PROFILE", ":role": "admin"},
        "Limit": ADMIN_CENSUS_PAGE_SIZE,
    }
    for _page in range(ADMIN_CENSUS_MAX_PAGES):
        result = _admin_scan(table, **scan_kwargs)
        for row in _admin_items(result):
            if str(row.get("user_id") or "") == target_id:
                continue
            if _account_status_of(row) == ACCOUNT_STATUS_ACTIVE:
                return True
        cursor = _admin_cursor(result)
        if not cursor:
            return False
        scan_kwargs["ExclusiveStartKey"] = cursor
    # A census that ran out of pages is not evidence that anyone else is active.
    return False


def _refuse_status_change(
    *, actor: Mapping[str, object], target_id: str, reason_code: str
) -> None:
    """A refused command is still a command somebody issued, so it is recorded."""
    _record_account_admin_event(
        actor=actor,
        target_id=target_id,
        event_type="account_status_change_denied",
        action="change_account_status",
        reason_code=reason_code,
        evidence_reference=f"account_status_denied:{reason_code}",
    )
    raise HTTPException(status_code=409, detail={"code": reason_code})


def _guard_admin_console_survives(
    *, actor: Mapping[str, object], target_id: str, profile: Mapping[str, object]
) -> None:
    """Card 002-D / B7: one administrator may not close the admin console down.

    `admin_identity_manager` is not an escalation - it already governs privileged
    identities - but without this judgement its holder can suspend every other
    administrator and then itself, and nobody is left who can undo it. There is no
    break-glass path here, so the refusal has to come before the write.
    """
    actor_id = str(actor.get("user_id") or actor.get("sub") or "")
    if actor_id and actor_id == target_id:
        _refuse_status_change(
            actor=actor, target_id=target_id, reason_code="account_self_deactivation_forbidden"
        )
    if str(profile.get("role") or "") != "admin":
        return
    if _another_active_admin_exists(target_id):
        return
    _refuse_status_change(
        actor=actor, target_id=target_id, reason_code="account_last_active_admin"
    )


def _refuse_password_reset(
    *, actor: Mapping[str, object], target_id: str, reason_code: str
) -> None:
    """A refused reset is still a command somebody issued, so it is recorded."""
    _record_account_admin_event(
        actor=actor,
        target_id=target_id,
        event_type="account_password_reset_denied",
        action="reset_account_password",
        reason_code=reason_code,
        evidence_reference=f"account_password_reset_denied:{reason_code}",
    )
    raise HTTPException(status_code=409, detail={"code": reason_code})


def _guard_peer_admin_credentials(
    *, actor: Mapping[str, object], target_id: str, profile: Mapping[str, object]
) -> None:
    """Card 006: an administrator may not take another administrator's credential.

    This is a different judgement from `_guard_admin_console_survives`, because the
    harm is different. Resetting someone else's password does not close the console
    down; it hands the caller a working credential for another privileged principal,
    in plaintext, in the response body, with no consent from the target and no
    notice to it - the target's own change-at-next-sign-in obligation only fires
    when the target signs in, and the caller signs in first. Administrators are not
    interchangeable either: privileged capabilities such as `admin_identity_manager`
    are granted per account, so taking over a peer can be an escalation.

    Resetting one's own password is the legitimate case and is left alone; so is
    every non-admin target, which is what this console exists to service.

    The lockout this could cause - every administrator forgetting its password with
    no peer allowed to help - is answered outside the product, not inside it. The
    user pool is reachable with AWS credentials (`admin-set-user-password`), a
    separate trust domain with its own audit trail. Keeping the break-glass there
    is the point: an attacker holding one administrator session cannot reach it.
    """
    actor_id = str(actor.get("user_id") or actor.get("sub") or "")
    if actor_id and actor_id == target_id:
        return
    if str(profile.get("role") or "") != "admin":
        return
    _refuse_password_reset(
        actor=actor,
        target_id=target_id,
        reason_code="account_peer_admin_password_reset_forbidden",
    )


@router.post("/users/invitations")
def invite_account(
    payload: AccountInvitationRequest,
    user: dict = Depends(require_role("admin")),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Open one account in `invited` state and mail its single-use activation link."""
    expiry = (
        payload.expirySeconds
        if payload.expirySeconds is not None
        else account_provisioning_service.DEFAULT_INVITATION_SECONDS
    )
    return account_provisioning_service.invite_account(
        actor=user,
        role=payload.role,
        email=payload.email,
        full_name=payload.fullName,
        date_of_birth=payload.dateOfBirth,
        invitation_expiry_seconds=expiry,
        deliver=_invitation_delivery(payload.locale),
    )


@router.post("/users")
def assign_account(
    payload: AccountAssignmentRequest,
    user: dict = Depends(require_role("admin")),
    settings: Settings = Depends(get_settings),
    provider: Any = Depends(get_account_identity_provider),
) -> dict[str, Any]:
    """Open one active account and hand its initial password back exactly once."""
    return account_provisioning_service.assign_account(
        actor=user,
        role=payload.role,
        email=payload.email,
        full_name=payload.fullName,
        date_of_birth=payload.dateOfBirth,
        provider=provider,
        issuer=_account_issuer(settings),
    )


@router.post("/users/invitations/{invitation_id}/reissue")
def reissue_account_invitation(
    invitation_id: str,
    payload: AccountInvitationReissueRequest,
    user: dict = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Replace one undelivered invitation, reusing the number already allocated."""
    expiry = (
        payload.expirySeconds
        if payload.expirySeconds is not None
        else account_provisioning_service.DEFAULT_INVITATION_SECONDS
    )
    return account_provisioning_service.reissue_invitation(
        actor=user,
        invitation_id=invitation_id,
        invitation_expiry_seconds=expiry,
        deliver=_invitation_delivery(payload.locale),
    )


@router.delete("/users/invitations/{invitation_id}")
def revoke_account_invitation(
    invitation_id: str,
    user: dict = Depends(require_role("admin")),
) -> dict[str, Any]:
    return account_provisioning_service.revoke_invitation(
        actor=user, invitation_id=invitation_id
    )


def _require_password_change_at_next_sign_in(
    user_id: str, profile: Mapping[str, object]
) -> None:
    """Raise the local flag that forces this account through a password change.

    The flag is raised before the provider password is replaced, and the order is
    deliberate. A raised flag over a still-valid old password only forces a change
    the account can complete by itself; a new temporary password with no flag
    would hand out an unforced credential, which is the failure this exists to
    prevent.
    """
    operation = user_repo.profile_update_operation(
        user_id,
        update_expression="SET #must_change_password = :required, updated_at = :now",
        expression_attribute_names={"#must_change_password": MUST_CHANGE_PASSWORD_FIELD},
        expression_attribute_values={":required": True, ":now": _now_iso()},
        expected_version=profile.get("version"),
    )
    try:
        fence = account_deletion_repo.require_active_account_fence(user_id)
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(
                    user_id, int(fence.get("generation") or 0)
                ),
                operation,
            ]
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise HTTPException(
            status_code=409, detail={"code": "account_password_reset_conflict"}
        ) from exc


@router.post("/users/{user_id}/password-reset")
def reset_account_password(
    user_id: str,
    payload: AccountPasswordResetRequest,
    user: dict = Depends(require_role("admin")),
    settings: Settings = Depends(get_settings),
    provider: Any = Depends(get_account_password_administrator),
) -> dict[str, Any]:
    """Set one temporary password the account must replace at its next sign-in.

    The provider password is set `Permanent=True` on purpose. `Permanent=False`
    parks the account in the provider's own FORCE_CHANGE_PASSWORD challenge,
    which this build has no route to answer, so the account could sign in
    nowhere. The obligation is carried locally instead: the profile flag raised
    here lets the account authenticate and then refuses every route but the
    self-service password change.

    An administrator can reset any account but a peer administrator's, so the
    audit row is written before the response is built and a failed write fails
    the command. Refusals are recorded too, from the same helper.
    """
    profile = _account_profile_or_404(user_id)
    _guard_peer_admin_credentials(actor=user, target_id=user_id, profile=profile)
    email = _account_email_or_409(profile)
    _require_password_change_at_next_sign_in(user_id, profile)
    temporary_password = account_provisioning_service.generate_initial_password()
    try:
        provider.admin_set_user_password(
            UserPoolId=settings.cognito_user_pool_id,
            Username=email,
            Password=temporary_password,
            Permanent=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail={"code": "identity_provider_unavailable"}
        ) from exc
    _record_account_admin_event(
        actor=user,
        target_id=user_id,
        event_type="account_password_reset",
        action="reset_account_password",
        reason_code=payload.reason,
        evidence_reference=f"account-number:{profile.get('account_number') or ''}",
    )
    return {
        "userId": user_id,
        "temporaryPassword": temporary_password,
        "mustChangePasswordAtNextSignIn": True,
    }


@router.post("/users/{user_id}/status")
def change_account_status(
    user_id: str,
    payload: AccountStatusChangeRequest,
    user: dict = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Move one account along the status machine. Archive is as far as it goes."""
    profile = _account_profile_or_404(user_id)
    current = _account_status_of(profile)
    if payload.status != ACCOUNT_STATUS_ACTIVE:
        _guard_admin_console_survives(actor=user, target_id=user_id, profile=profile)
    if payload.status == current:
        raise HTTPException(status_code=409, detail={"code": "account_status_unchanged"})
    if payload.status not in ACCOUNT_STATUS_TRANSITIONS.get(current, ()):
        raise HTTPException(status_code=409, detail={"code": "account_status_transition_invalid"})
    now = _now_iso()
    operation = user_repo.profile_update_operation(
        user_id,
        update_expression=(
            "SET #account_status = :next_status, is_active = :is_active, updated_at = :now"
        ),
        expression_attribute_names={"#account_status": "account_status"},
        expression_attribute_values={
            ":next_status": payload.status,
            ":expected_status": current,
            ":is_active": payload.status == ACCOUNT_STATUS_ACTIVE,
            ":now": now,
        },
        expected_version=profile.get("version"),
        additional_condition_expression=(
            "#account_status = :expected_status OR attribute_not_exists(#account_status)"
        ),
    )
    try:
        fence = account_deletion_repo.require_active_account_fence(user_id)
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(
                    user_id, int(fence.get("generation") or 0)
                ),
                operation,
            ]
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise HTTPException(
            status_code=409, detail={"code": "account_status_transition_conflict"}
        ) from exc
    _record_account_admin_event(
        actor=user,
        target_id=user_id,
        event_type="account_status_changed",
        action="change_account_status",
        reason_code=payload.reason,
        evidence_reference=f"account_status:{current}->{payload.status}",
    )
    return {"userId": user_id, "accountStatus": payload.status, "previousStatus": current}


def _parent_link_status(code: str) -> int:
    return 404 if code == "link_target_not_found" else 409


@router.post("/users/parent-links")
def assign_parent_link(
    body: AdminParentLinkRequest,
    user: dict = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Administrator assignment is trusted and audited, so it starts active."""
    try:
        link = parent_link_service.assign_link(
            parent_id=body.parent_id,
            student_id=body.student_id,
            actor_id=str(user.get("user_id") or user.get("sub") or ""),
            relationship=body.relationship,
        )
    except parent_link_service.ParentLinkError as exc:
        raise HTTPException(
            status_code=_parent_link_status(exc.code), detail={"code": exc.code}
        ) from exc
    except parent_link_repo.ParentLinkConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "link_already_exists"}) from exc
    _record_account_admin_event(
        actor=user,
        target_id=body.student_id,
        event_type="parent_link_assigned",
        action="assign_parent_link",
        reason_code=body.relationship,
        evidence_reference=f"parent-link:{body.parent_id}->{body.student_id}",
    )
    return link


@router.get("/subscriptions/requests", response_model=SubscriptionRequestListResponse)
async def list_subscription_requests(
    limit: int = Query(default=50, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    requested_tier: Optional[str] = Query(default=None),
    parent_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
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
    user: dict = Depends(require_role("admin")),
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
        raise HTTPException(
            status_code=404,
            detail={
                "code": "checkout_not_found",
                "message": "Checkout was not found.",
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "checkout_temporarily_unavailable",
                "message": "Checkout status is temporarily unavailable.",
            },
        ) from exc
    if lookup.disposition is checkout_command_repo.CheckoutCommandDisposition.NOT_FOUND:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "checkout_not_found",
                "message": "Checkout was not found.",
            },
        )
    if (
        lookup.disposition
        is not checkout_command_repo.CheckoutCommandDisposition.REPLAYED
        or lookup.command is None
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "checkout_temporarily_unavailable",
                "message": "Checkout status is temporarily unavailable.",
            },
        )
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
        raise HTTPException(
            status_code=404,
            detail={
                "code": "checkout_not_found",
                "message": "Checkout was not found.",
            },
        )
    return result


@router.get(
    "/billing/checkouts/{checkout_ref}",
    response_model=AdminCheckoutSupportResponse | AdminBillingOperationDetail,
)
async def get_billing_checkout_support(
    checkout_ref: str,
    parent_id: str = Query(..., alias="parentId", min_length=1, max_length=200),
    detail: bool = Query(default=False),
    user: dict = Depends(require_role("admin")),
    provider: billing_reconciliation_service.BillingReconciliationProvider = Depends(
        get_billing_reconciliation_provider
    ),
):
    """Inspect one checkout through the billing-support capability.

    Frozen by card 007: no checkout can exist to support.
    """
    refuse_if_frozen()
    del user
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
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "billing_projection_temporarily_unavailable",
                    "message": "Billing details are temporarily unavailable.",
                },
            ) from exc
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
    user: dict = Depends(require_role("admin")),
    provider: billing_reconciliation_service.BillingReconciliationProvider = Depends(
        get_billing_reconciliation_provider
    ),
):
    """Reconcile one original checkout without payment-creation authority.

    Frozen by card 007: reconciliation calls the payment provider.
    """
    refuse_if_frozen()
    del body, user
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
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
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
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
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
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Inspect redacted live provider readiness without creating provider mutations.

    Frozen by card 007: the provider is deliberately not provisioned.
    """
    refuse_if_frozen()
    return subscription_service.get_provider_readiness(settings)


@router.get("/subscriptions/billing/rollout-controls", response_model=SubscriptionRolloutControlsResponse)
async def get_subscription_rollout_controls(
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Inspect effective checkout/refund rollout controls.

    Frozen by card 007: there is no rollout left to control.
    """
    refuse_if_frozen()
    return subscription_service.get_payment_rollout_controls(settings)


@router.patch("/subscriptions/billing/rollout-controls", response_model=SubscriptionRolloutControlsResponse)
async def update_subscription_rollout_controls(
    body: SubscriptionRolloutControlsUpdateRequest,
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Update checkout/refund rollout controls for new live-changing operations.

    Frozen by card 007: this switch could otherwise re-open checkout or refunds.
    """
    refuse_if_frozen()
    return subscription_service.update_payment_rollout_controls(
        checkout_state=body.checkout_state,
        refunds_state=body.refunds_state,
        reason=body.reason,
        user=user,
        settings=settings,
    )


@router.get("/subscriptions/billing/{parent_id}", response_model=SubscriptionBillingResponse)
async def get_subscription_billing(
    parent_id: str,
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Open one parent provider billing record with recent event history.

    Frozen by card 007: the parent billing record is legacy data only.
    """
    refuse_if_frozen()
    return subscription_service.get_admin_billing(parent_id, settings=settings)


@router.get("/usage/students/{student_id}", response_model=UsageSummaryResponse)
async def get_student_usage_summary(
    student_id: str,
    day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Return a privacy-safe student quota usage summary for support."""
    return usage_ledger_service.build_student_usage_summary(
        student_id=student_id,
        settings=settings,
        day=day,
    )


@router.get("/usage/students/{student_id}/events", response_model=UsageEventListResponse)
async def list_student_usage_events(
    student_id: str,
    day: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(require_role("admin")),
):
    """List redacted usage ledger events for support investigation."""
    items = usage_ledger_service.list_usage_events(
        student_id=student_id,
        day=day,
        action=action,
        limit=limit,
    )
    return UsageEventListResponse(items=items, count=len(items))


@router.get("/usage/reconciliation", response_model=UsageReconciliationResponse)
async def preview_usage_reconciliation(
    student_id: str = Query(..., min_length=1),
    day: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    action: str = Query(default=usage_ledger_service.QUESTION_SUBMISSION_ACTION),
    repair: bool = Query(default=False),
    user: dict = Depends(require_role("admin")),
):
    """Preview or explicitly repair daily counter versus ledger reconciliation."""
    return usage_ledger_service.reconcile_usage_action(
        student_id=student_id,
        day=day,
        action=action,
        repair=repair,
    )


@router.get("/account-verification/{user_id}", response_model=AccountVerificationSupportResponse)
async def get_account_verification_support(
    user_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Return bounded email verification state for account support."""
    profile = user_repo.get_user(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return AccountVerificationSupportResponse(**account_verification_service.support_summary(profile))


@router.get(
    "/account-operations/parents/{parent_id}",
    response_model=AccountOperationsParentDetailResponse,
)
async def get_parent_account_operations(
    parent_id: str,
    day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Return support-grade parent account operations detail."""
    try:
        return account_operations_service.build_admin_parent_operations_detail(
            parent_id,
            settings=settings,
            day=day,
        )
    except ValueError as exc:
        if str(exc) == "parent_not_found":
            raise HTTPException(status_code=404, detail="Parent not found") from exc
        raise


@router.post("/subscriptions/billing/{parent_id}/refunds", response_model=SubscriptionRefundExecutionResponse)
async def execute_subscription_refund(
    parent_id: str,
    body: SubscriptionRefundExecutionRequest,
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
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
        user=user,
        settings=settings,
    )


@router.patch("/subscriptions/requests/{request_id}", response_model=SubscriptionRequestResponse)
async def update_subscription_request(
    request_id: str,
    body: SubscriptionRequestUpdateRequest,
    user: dict = Depends(require_role("admin")),
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
        user=user,
    )


@router.post("/subscriptions/requests/{request_id}/apply", response_model=SubscriptionRequestResponse)
async def apply_subscription_request(
    request_id: str,
    body: SubscriptionRequestApplyRequest = Body(default_factory=SubscriptionRequestApplyRequest),
    user: dict = Depends(require_role("admin")),
):
    """Apply an approved manual request and update the parent's subscription tier.

    Frozen by card 007: assignment, not an approved request, sets a tier.
    """
    refuse_if_frozen()
    return subscription_service.apply_request(
        request_id=request_id,
        admin_note=body.admin_note,
        effective_at=body.effective_at,
        user=user,
    )


# Each census below walks the whole table one megabyte at a time. The budget is
# what stops a runaway table turning the dashboard into a timeout.
ADMIN_STATS_MAX_PAGES = 50


@router.get("/stats", response_model=StatsResponse)
async def get_stats(user: dict = Depends(require_role("admin"))):
    """Return aggregate platform metrics (full-table scan — small scale only)."""
    table = get_table()

    # Count user profiles
    users, users_complete = _admin_scan_every_page(
        table,
        page_budget=ADMIN_STATS_MAX_PAGES,
        FilterExpression="SK = :profile",
        ExpressionAttributeValues={":profile": "PROFILE"},
        ProjectionExpression="#role",
        ExpressionAttributeNames={"#role": "role"},
    )

    counts = {"student": 0, "parent": 0, "teacher": 0}
    for u in users:
        r = u.get("role", "")
        if r in counts:
            counts[r] += 1

    # Count questions by status
    meta_rows, questions_complete = _admin_scan_every_page(
        table,
        page_budget=ADMIN_STATS_MAX_PAGES,
        FilterExpression="SK = :meta",
        ExpressionAttributeValues={":meta": "META"},
        ProjectionExpression=", ".join(
            [
                "#s",
                "teacher_requested_at",
                "queue_visible_at",
                "teacher_taken_over_at",
                "teacher_first_replied_at",
                "resolved_at",
                "sla_request_to_takeover_seconds",
                "sla_request_to_first_reply_seconds",
                "sla_takeover_to_first_reply_seconds",
                "sla_request_to_resolved_seconds",
                "teacher_first_reply_sla_bucket",
            ]
        ),
        ExpressionAttributeNames={"#s": "status"},
    )
    question_statuses = {status.value for status in QuestionStatus}
    questions = [
        question
        for question in meta_rows
        if isinstance(question_status := question.get("status"), str)
        and question_status in question_statuses
    ]

    ai_resolved = sum(1 for q in questions if q.get("status") == QuestionStatus.AI_ANSWERED.value)
    teacher_resolved = sum(1 for q in questions if q.get("status") == QuestionStatus.RESOLVED.value)
    escalated = sum(
        1 for q in questions
        if q.get("status") in (QuestionStatus.ESCALATED.value, QuestionStatus.TEACHER_ACTIVE.value)
    )

    return StatsResponse(
        total_users=len(users),
        total_students=counts["student"],
        total_parents=counts["parent"],
        total_teachers=counts["teacher"],
        total_questions=len(questions),
        ai_resolved=ai_resolved,
        teacher_resolved=teacher_resolved,
        escalated=escalated,
        teacher_sla=teacher_reply_service.aggregate_teacher_sla(questions),
        counts_complete=users_complete and questions_complete,
    )


@router.get("/teacher-dispatch/dashboard")
async def get_teacher_dispatch_dashboard(user: dict = Depends(require_role("admin"))):
    """Return aggregate teacher dispatch, load, and SLA-risk visibility."""
    return teacher_dispatch_service.build_dispatch_dashboard()


def _binding_response(item: dict[str, Any]) -> ParentStudentBindingResponse:
    return ParentStudentBindingResponse(
        parent_id=item.get("parent_id", ""),
        student_id=item.get("student_id", ""),
        relationship=item.get("relationship", "child"),
        status=item.get("status", "active"),
        source=item.get("source"),
        updated_at=item.get("updated_at"),
    )


def _binding_repair_preview_response(
    preview: user_repo.ParentBindingRepairPreview,
) -> ParentBindingRepairPreview:
    return ParentBindingRepairPreview(
        pair_id=preview.pair_id,
        preview_id=preview.preview_id,
        classification=preview.classification,
        proposed_action=preview.proposed_action,
        observations=[
            ParentBindingRepairObservation(
                coordinate=item.coordinate,
                version=item.version,
                digest=item.digest,
            )
            for item in preview.observations
        ],
    )


def _binding_repair_apply_response(
    result: user_repo.ParentBindingRepairApplyResult,
) -> ParentBindingRepairApplyResponse:
    return ParentBindingRepairApplyResponse(
        disposition=result.disposition,
        pair_id=result.preview.pair_id,
        preview_id=result.preview.preview_id,
        classification=result.preview.classification,
        mutated=result.mutated,
    )


@router.get("/parent-bindings", response_model=ParentStudentBindingListResponse)
async def list_parent_bindings(
    parent_id: str = Query(..., min_length=1),
    user: dict = Depends(require_role("admin")),
):
    """Inspect formal parent/student bindings for admin repair."""
    items = [
        _binding_response(item)
        for item in user_repo.list_parent_student_bindings(parent_id)
    ]
    return ParentStudentBindingListResponse(items=items, count=len(items))


@router.post(
    "/parent-bindings/repair/preview", response_model=ParentBindingRepairPreview
)
@admin_target_provider(PARENT_BINDING_TARGET)
async def preview_parent_binding_repair(
    body: ParentBindingRepairPreviewRequest,
    user: dict = Depends(require_role("admin")),
):
    """Classify one explicit historical relationship pair without mutation."""
    del user  # authorization and durable target audit complete before this body
    preview = user_repo.preview_parent_binding_repair(
        parent_id=body.parent_id,
        student_id=body.student_id,
        relationship=body.relationship,
    )
    return _binding_repair_preview_response(preview)


@router.post("/parent-bindings/repair", response_model=ParentBindingRepairApplyResponse)
@admin_target_provider(PARENT_BINDING_TARGET)
async def repair_parent_binding(
    body: ParentStudentBindingRepairRequest,
    user: dict = Depends(require_role("admin")),
):
    """Apply one unchanged repair preview through the atomic relationship writer."""
    now = _now_iso()
    result = user_repo.apply_parent_binding_repair(
        parent_id=body.parent_id,
        student_id=body.student_id,
        relationship=body.relationship,
        preview_id=body.preview_id,
        actor=str(user.get("sub") or user.get("username") or "admin"),
        created_at=now,
    )
    response = _binding_repair_apply_response(result)
    status_code = {
        user_repo.ParentBindingRepairApplyDisposition.SKIPPED_CHANGED: 409,
        user_repo.ParentBindingRepairApplyDisposition.CONFLICT: 409,
        user_repo.ParentBindingRepairApplyDisposition.SKIPPED_INVALID: 422,
        user_repo.ParentBindingRepairApplyDisposition.RETRYABLE: 503,
    }.get(result.disposition)
    if status_code is not None:
        return JSONResponse(
            status_code=status_code,
            content=response.model_dump(mode="json"),
        )
    return response
@router.post(
    "/parent-bindings/status",
    response_model=ParentBindingStatusTransitionResponse,
)
@admin_target_provider(PARENT_BINDING_TARGET)
async def transition_parent_binding_status(
    body: ParentBindingStatusTransitionRequest,
    user: dict = Depends(require_role("admin")),
):
    """Perform one canonical-admin, expected-status/version lifecycle transition."""
    context = user.get("_admin_authorization")
    correlation_id = str(getattr(context, "correlation_id", "") or "")
    if user.get("role") != "admin":
        return _relationship_status_error(
            code="action_not_allowed",
            message="You cannot perform this action.",
            correlation_id=correlation_id,
            status_code=403,
        )
    if body.status == body.expected_status:
        return _relationship_status_error(
            code="relationship_status_invalid",
            message="Choose a different relationship status.",
            correlation_id=correlation_id,
            status_code=422,
        )
    result = user_repo.transition_parent_student_relationship_status(
        parent_id=body.parent_id,
        student_id=body.student_id,
        relationship=body.relationship,
        expected_status=body.expected_status,
        expected_version=body.expected_version,
        status=body.status,
        source="admin_lifecycle",
        actor=str(user.get("sub") or user.get("user_id") or "admin"),
        updated_at=_now_iso(),
    )
    if result.disposition is user_repo.ParentBindingStatusDisposition.CONFLICT:
        return _relationship_status_error(
            code="relationship_status_conflict",
            message="The relationship changed. Refresh and retry.",
            correlation_id=correlation_id,
            status_code=409,
        )
    if result.disposition is user_repo.ParentBindingStatusDisposition.RETRYABLE:
        return _relationship_status_error(
            code="relationship_status_temporarily_unavailable",
            message="The relationship update is temporarily unavailable. Try again later.",
            correlation_id=correlation_id,
            status_code=503,
        )
    assert result.status is not None and result.version is not None
    # Visibility is the union of the legacy binding and the parent-link table, so
    # revoking only the legacy row would leave an administrator believing access was
    # withdrawn while the link table still grants it.
    if body.status != parent_link_repo.STATUS_ACTIVE and not _revoke_parent_link_side(
        parent_id=body.parent_id,
        student_id=body.student_id,
        actor=user,
    ):
        return _relationship_status_error(
            code="relationship_status_conflict",
            message="The relationship changed. Refresh and retry.",
            correlation_id=correlation_id,
            status_code=409,
        )
    return ParentBindingStatusTransitionResponse(
        disposition=result.disposition,
        status=result.status,
        version=result.version,
    )


def _revoke_parent_link_side(
    *, parent_id: str, student_id: str, actor: Mapping[str, object]
) -> bool:
    """Retire an active parent-link pair, reporting whether visibility is now closed."""
    if parent_link_service.active_link(parent_id, student_id) is None:
        return True
    try:
        parent_link_repo.transition_link(
            parent_id=parent_id,
            student_id=student_id,
            expected_status=parent_link_repo.STATUS_ACTIVE,
            next_status=parent_link_repo.STATUS_REJECTED,
            updated_by=str(actor.get("user_id") or actor.get("sub") or "admin"),
            link_updated_at=_now_iso(),
        )
    except parent_link_repo.ParentLinkConflict:
        return False
    _record_account_admin_event(
        actor=actor,
        target_id=student_id,
        event_type="parent_link_revoked",
        action="revoke_parent_link",
        evidence_reference=f"parent-link:{parent_id}->{student_id}",
    )
    return True




def _relationship_status_error(
    *, code: str, message: str, correlation_id: str | None, status_code: int
) -> JSONResponse:
    safe_correlation_id = normalize_correlation_id(correlation_id)
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "correlationId": safe_correlation_id,
        },
        headers={"X-Correlation-ID": safe_correlation_id},
    )




@router.get("/reports/ops", response_model=ReportOperationListResponse)
async def list_report_operations(
    limit: int = Query(default=50, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    week_start: Optional[str] = Query(default=None),
    parent_id: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None),
    next_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List report operation metadata for admin triage."""
    try:
        last_key = report_repo.decode_admin_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

    result = report_repo.list_reports_for_admin(
        status=status,
        week_start=week_start,
        parent_id=parent_id,
        student_id=student_id,
        limit=limit,
        last_key=last_key,
    )
    items = [_report_operation_response(report) for report in _admin_items(result)]
    return ReportOperationListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_admin_page_token(_admin_cursor(result)),
        access_pattern="parent_gsi" if parent_id else "bounded_scan",
    )


@router.get(
    "/reports/{parent_id}/{student_id}/{week_start}/ops",
    response_model=ReportOperationResponse,
)
async def get_report_operations(
    parent_id: str,
    student_id: str,
    week_start: str,
    user: dict = Depends(require_role("admin")),
):
    """Inspect report artifact and delivery metadata without exposing artifact content."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    return _report_operation_response(report)


@router.post("/reports/bulk-resend", response_model=BulkReportResendResponse)
@admin_target_provider(BULK_REPORT_TARGETS)
async def bulk_resend_report_emails(
    request: BulkReportResendRequest,
    user: dict = Depends(require_role("admin")),
):
    """Resend selected failed report emails with independent per-item results."""
    operator = _operator_id(user)
    results: list[BulkReportResendItemResult] = []

    for target in request.reports:
        report = report_repo.get_report_for_child_by_week(target.parent_id, target.student_id, target.week_start)
        if not report:
            results.append(
                BulkReportResendItemResult(
                    parent_id=target.parent_id,
                    student_id=target.student_id,
                    week_start=target.week_start,
                    result="not_found",
                    operation_result="not_found",
                    detail="Report not found",
                )
            )
            continue

        try:
            resend = report_recovery_service.resend_report_email(
                report,
                operator=operator,
                reason="admin_selected_bulk_resend",
            )
        except report_recovery_service.ReportRecoveryError as exc:
            results.append(_bulk_resend_error_result(target, report, exc))
            continue

        results.append(
            BulkReportResendItemResult(
                parent_id=target.parent_id,
                student_id=target.student_id,
                week_start=target.week_start,
                result="success",
                report_id=resend.report_id,
                status=resend.status,
                email_status=resend.email_status,
                operation=resend.operation,
                operation_result=resend.operation_result,
                updated_at=resend.updated_at,
            )
        )

    return BulkReportResendResponse(operation="bulk_resend_email", count=len(results), results=results)


@router.post(
    "/reports/recovery-jobs/resend-email/preview",
    response_model=RecoveryJobPreviewResponse,
)
@admin_target_provider(RECOVERY_FILTER_PREVIEW_TARGETS)
async def preview_resend_recovery_job(
    request: RecoveryJobPreviewRequest,
    user: dict = Depends(require_role("admin")),
):
    """Preview a bounded async resend recovery job before mutation."""
    try:
        return report_recovery_job_service.preview_resend_job(
            reason=request.reason,
            operator=_operator_id(user),
            filters=request.filters.model_dump(),
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc


@router.post(
    "/reports/recovery-jobs/resend-email",
    response_model=RecoveryJobResponse,
)
@admin_target_provider(RECOVERY_FILTER_TARGETS)
async def create_resend_recovery_job(
    request: RecoveryJobCreateRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded async resend recovery job after preview confirmation."""
    try:
        job = report_recovery_job_service.create_resend_job(
            reason=request.reason,
            operator=_operator_id(user),
            filters=request.filters.model_dump(),
            preview_token=request.preview_token,
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc
    return _recovery_job_response(job)


@router.post(
    "/reports/recovery-jobs/retry-generation/preview",
    response_model=RecoveryJobPreviewResponse,
)
@admin_target_provider(RECOVERY_FILTER_PREVIEW_TARGETS)
async def preview_generation_retry_recovery_job(
    request: RecoveryJobPreviewRequest,
    user: dict = Depends(require_role("admin")),
):
    """Preview a bounded async generation retry recovery job before mutation."""
    try:
        return report_recovery_job_service.preview_generation_retry_job(
            reason=request.reason,
            operator=_operator_id(user),
            filters=request.filters.model_dump(),
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc


@router.post(
    "/reports/recovery-jobs/retry-generation",
    response_model=RecoveryJobResponse,
)
@admin_target_provider(RECOVERY_FILTER_TARGETS)
async def create_generation_retry_recovery_job(
    request: RecoveryJobCreateRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded async generation retry recovery job after preview confirmation."""
    try:
        job = report_recovery_job_service.create_generation_retry_job(
            reason=request.reason,
            operator=_operator_id(user),
            filters=request.filters.model_dump(),
            preview_token=request.preview_token,
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc
    return _recovery_job_response(job)


@router.post(
    "/reports/recovery-jobs/{job_id}/resume/preview",
    response_model=RecoveryJobResumePreviewResponse,
)
@admin_target_provider(RECOVERY_RESUME_PREVIEW_TARGETS)
async def preview_resume_recovery_job(
    job_id: str,
    request: RecoveryJobResumePreviewRequest,
    user: dict = Depends(require_role("admin")),
):
    """Preview a bounded resume job from a prior recovery job target subset."""
    try:
        return report_recovery_job_service.preview_resume_job(
            source_job_id=job_id,
            reason=request.reason,
            operator=_operator_id(user),
            results=request.results,
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc


@router.post(
    "/reports/recovery-jobs/{job_id}/resume",
    response_model=RecoveryJobResponse,
)
@admin_target_provider(RECOVERY_RESUME_TARGETS)
async def create_resume_recovery_job(
    job_id: str,
    request: RecoveryJobResumeCreateRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded resume job from a prior recovery job target subset."""
    try:
        job = report_recovery_job_service.create_resume_job(
            source_job_id=job_id,
            reason=request.reason,
            operator=_operator_id(user),
            results=request.results,
            preview_token=request.preview_token,
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc
    return _recovery_job_response(job)








































@router.post("/reports/release-evidence/validate")
async def validate_release_evidence(
    bundle: dict[str, Any] = Body(...),
    user: dict = Depends(require_role("admin")),
):
    """Validate and redact a release evidence bundle without mutating reports."""
    return release_evidence_service.validate_release_bundle(bundle)


@router.get("/reports/release-evidence/fixture-status")
async def get_release_fixture_status(
    fixture_name: str = Query(..., min_length=1),
    parent_id: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None),
    week_start: Optional[str] = Query(default=None),
    expected_artifact_version: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """Inspect one approved safe fixture without exposing private artifact metadata."""
    approved = release_evidence_service.approved_fixture_config(fixture_name)
    resolved_parent_id = parent_id or approved.get("parent_id")
    resolved_student_id = student_id or approved.get("student_id")
    resolved_week_start = week_start or approved.get("week_start")
    report = None
    audit_events: list[dict[str, Any]] = []

    if resolved_parent_id and resolved_student_id and resolved_week_start:
        report = report_repo.get_report_for_child_by_week(
            resolved_parent_id,
            resolved_student_id,
            resolved_week_start,
        )
        if report:
            report_id = _admin_required_text(report.get("report_id"))
            audit_result = report_repo.list_report_audit_events(report_id, limit=10)
            audit_events = _admin_items(audit_result)

    return release_evidence_service.build_fixture_inventory_response(
        fixture_name=fixture_name,
        report=report,
        audit_events=audit_events,
        expected_artifact_version_id=expected_artifact_version,
    )


@router.get("/reports/recovery-jobs", response_model=RecoveryJobListResponse)
async def list_recovery_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List async report recovery jobs."""
    try:
        last_key = report_repo.decode_recovery_job_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc
    result = report_repo.list_recovery_jobs(limit=limit, last_key=last_key)
    items = [_recovery_job_response(item) for item in _admin_items(result)]
    return RecoveryJobListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_recovery_job_page_token(_admin_cursor(result)),
    )


@router.get("/reports/recovery-jobs/{job_id}", response_model=RecoveryJobResponse)
async def get_recovery_job(
    job_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Get one async report recovery job."""
    job = report_repo.get_recovery_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Recovery job not found")
    return _recovery_job_response(job)


@router.get("/reports/recovery-jobs/{job_id}/results", response_model=RecoveryJobTargetsResponse)
async def list_recovery_job_results(
    job_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List metadata-only target results for one async recovery job."""
    if not report_repo.get_recovery_job(job_id):
        raise HTTPException(status_code=404, detail="Recovery job not found")
    try:
        last_key = report_repo.decode_recovery_job_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc
    result = report_repo.list_recovery_job_targets(job_id, limit=limit, last_key=last_key)
    items = [_recovery_job_target_response(item) for item in _admin_items(result)]
    return RecoveryJobTargetsResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_recovery_job_page_token(_admin_cursor(result)),
    )


@router.post("/reports/recovery-jobs/{job_id}/cancel", response_model=RecoveryJobResponse)
async def cancel_recovery_job(
    job_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Request cooperative cancellation for an async report recovery job."""
    try:
        job = report_recovery_job_service.cancel_recovery_job(job_id, operator=_operator_id(user))
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc
    return _recovery_job_response(job)


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/resend",
    response_model=ReportResendResponse,
)
async def resend_report_email(
    parent_id: str,
    student_id: str,
    week_start: str,
    user: dict = Depends(require_role("admin")),
):
    """Resend a failed report email using the existing private HTML artifact."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        result = report_recovery_service.resend_report_email(
            report,
            operator=_operator_id(user),
            reason="admin_single_resend",
        )
    except report_recovery_service.ReportRecoveryError as exc:
        raise _report_recovery_http_error(exc) from exc
    return ReportResendResponse(
        report_id=result.report_id,
        status=result.status,
        email_status=_admin_required_text(result.email_status),
        operation=result.operation,
        operation_result=result.operation_result,
        updated_at=result.updated_at,
    )


def _bulk_resend_error_result(
    target: ReportResendTarget,
    report: dict,
    exc: report_recovery_service.ReportRecoveryError,
) -> BulkReportResendItemResult:
    result = "failed" if exc.status_code >= 500 else "refused"
    detail = report_recovery_service.redact_private_artifact_text(exc.detail) or "Report resend failed"
    return BulkReportResendItemResult(
        parent_id=target.parent_id,
        student_id=target.student_id,
        week_start=target.week_start,
        result=result,
        report_id=report.get("report_id"),
        status=report.get("status"),
        email_status=report.get("email_status"),
        operation_result=result,
        detail=detail,
        error_class=exc.error_class,
    )


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/retry-generation",
    response_model=ReportGenerationRetryResponse,
)
async def retry_report_generation(
    parent_id: str,
    student_id: str,
    week_start: str,
    user: dict = Depends(require_role("admin")),
):
    """Retry generation for one generation-failed weekly report."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        result = report_recovery_service.retry_report_generation(
            report,
            parent_id=parent_id,
            student_id=student_id,
            week_start=week_start,
            operator=_operator_id(user),
            reason="admin_single_generation_retry",
        )
    except report_recovery_service.ReportRecoveryError as exc:
        raise _report_recovery_http_error(exc) from exc
    return ReportGenerationRetryResponse(
        report_id=result.report_id,
        status=result.status,
        email_status=result.email_status,
        operation=result.operation,
        operation_result=result.operation_result,
        updated_at=result.updated_at,
        artifacts=result.artifacts or {"json_available": False, "html_available": False},
    )




















@router.get(
    "/reports/{parent_id}/{student_id}/{week_start}/audit",
    response_model=ReportAuditListResponse,
)
async def list_report_audit_events(
    parent_id: str,
    student_id: str,
    week_start: str,
    limit: int = Query(default=50, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List append-only audit events for one report recovery timeline."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        last_key = report_repo.decode_audit_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

    report_id = _admin_required_text(report.get("report_id"))
    result = report_repo.list_report_audit_events(report_id, limit=limit, last_key=last_key)
    items = [_report_audit_event_response(item) for item in _admin_items(result)]
    return ReportAuditListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_audit_page_token(_admin_cursor(result)),
        scope="report",
    )


@router.get(
    "/reports/recovery-jobs/{job_id}/audit",
    response_model=ReportAuditListResponse,
)
async def list_recovery_job_audit_events(
    job_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List append-only audit events for a report recovery job timeline."""
    try:
        last_key = report_repo.decode_audit_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

    result = report_repo.list_recovery_job_audit_events(job_id, limit=limit, last_key=last_key)
    items = [_report_audit_event_response(item) for item in _admin_items(result)]
    return ReportAuditListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_audit_page_token(_admin_cursor(result)),
        scope="recovery_job",
    )


def _get_report_or_404(parent_id: str, student_id: str, week_start: str) -> dict:
    report = report_repo.get_report_for_child_by_week(parent_id, student_id, week_start)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report








def _support_handoff_fixture_response(fixture: SupportHandoffFixtureReference) -> dict[str, Any]:
    approved = release_evidence_service.approved_fixture_config(fixture.fixture_name)
    resolved_parent_id = fixture.parent_id or approved.get("parent_id")
    resolved_student_id = fixture.student_id or approved.get("student_id")
    resolved_week_start = fixture.week_start or approved.get("week_start")
    report = None
    audit_events: list[dict[str, Any]] = []
    if resolved_parent_id and resolved_student_id and resolved_week_start:
        report = report_repo.get_report_for_child_by_week(
            resolved_parent_id,
            resolved_student_id,
            resolved_week_start,
        )
        if report:
            report_id = _admin_required_text(report.get("report_id"))
            audit_result = report_repo.list_report_audit_events(report_id, limit=10)
            audit_events = _admin_items(audit_result)
    return release_evidence_service.build_fixture_inventory_response(
        fixture_name=fixture.fixture_name,
        report=report,
        audit_events=audit_events,
        expected_artifact_version_id=fixture.expected_artifact_version,
    )




def _sanitize_request_id(value: object) -> str | None:
    """Bound and redact a caller-supplied correlation header before it is stored."""
    text = report_recovery_service.redact_private_artifact_text(value) or ""
    if release_evidence_service.private_marker_hits(text):
        return "[REDACTED]"
    return text[:240] or None


def _request_id(request: Request) -> str | None:
    for header in ("x-request-id", "x-amzn-requestid", "x-amzn-trace-id", "x-correlation-id"):
        value = request.headers.get(header)
        if value:
            return _sanitize_request_id(value)
    return None


def _report_operation_response(report: dict) -> ReportOperationResponse:
    return ReportOperationResponse(
        report_id=report.get("report_id", ""),
        parent_id=report.get("parent_id", ""),
        student_id=report.get("student_id", ""),
        student_name=report.get("student_name"),
        week_start=report.get("week_start", ""),
        status=report.get("status"),
        email_status=report.get("email_status"),
        artifacts={
            "json_available": bool(report.get("json_s3_key")),
            "html_available": bool(report.get("html_s3_key") or report.get("s3_key")),
        },
        generation={
            "generated_at": report.get("generated_at"),
            "generation_failed_at": report.get("generation_failed_at"),
            "generation_error_class": report.get("generation_error_class"),
            "generation_error_message": report_recovery_service.redact_private_artifact_text(
                report.get("generation_error_message")
            ),
        },
        delivery={
            "parent_email": report.get("parent_email"),
            "email_sent_at": report.get("email_sent_at"),
            "email_failed_at": report.get("email_failed_at"),
            "email_error_class": report.get("email_error_class"),
            "email_error_message": report_recovery_service.redact_private_artifact_text(
                report.get("email_error_message")
            ),
        },
        operations={
            "last_operation": report.get("last_operation"),
            "last_operation_at": report.get("last_operation_at"),
            "last_operation_by": report.get("last_operation_by"),
            "last_operation_result": report.get("last_operation_result"),
            "resend_attempted_at": report.get("resend_attempted_at"),
            "resend_completed_at": report.get("resend_completed_at"),
        },
        actions=_report_action_eligibility(report),
    )


def _report_action_eligibility(report: dict) -> dict[str, dict[str, str | bool | None]]:
    status = report.get("status")
    email_status = report.get("email_status")
    can_resend = status == "email_failed" or email_status == "failed"
    can_retry_generation = status == "generation_failed"
    return {
        "resend_email": {
            "enabled": can_resend,
            "reason": None if can_resend else _disabled_reason(status, "email_failed"),
        },
        "retry_generation": {
            "enabled": can_retry_generation,
            "reason": None if can_retry_generation else _disabled_reason(status, "generation_failed"),
        },
        "edit_artifact": {
            "enabled": bool(report.get("json_s3_key") and (report.get("html_s3_key") or report.get("s3_key"))),
            "reason": None
            if report.get("json_s3_key") and (report.get("html_s3_key") or report.get("s3_key"))
            else "Report is missing editable artifacts",
        },
        "rollback_artifact": {
            "enabled": bool(
                report.get("json_s3_key")
                and (report.get("html_s3_key") or report.get("s3_key"))
                and report.get("previous_json_s3_key")
                and report.get("previous_html_s3_key")
            ),
            "reason": None
            if (
                report.get("json_s3_key")
                and (report.get("html_s3_key") or report.get("s3_key"))
                and report.get("previous_json_s3_key")
                and report.get("previous_html_s3_key")
            )
            else "Report is missing rollback artifact metadata",
        },
    }


def _disabled_reason(status: str | None, required_status: str) -> str:
    if not status:
        return f"Report status is missing; requires {required_status}"
    return f"Report status is {status}; requires {required_status}"


def _operator_id(user: dict) -> str:
    return str(
        user.get("sub")
        or user.get("username")
        or user.get("email")
        or "unknown-admin"
    )


def _report_recovery_http_error(exc: report_recovery_service.ReportRecoveryError) -> HTTPException:
    detail = report_recovery_service.redact_private_artifact_text(exc.detail) or "Report recovery operation failed"
    return HTTPException(status_code=exc.status_code, detail=detail)


def _recovery_job_http_error(exc: report_recovery_job_service.RecoveryJobError) -> HTTPException:
    detail = report_recovery_service.redact_private_artifact_text(exc.detail) or "Recovery job operation failed"
    return HTTPException(status_code=exc.status_code, detail=detail)






def _recovery_job_response(job: dict) -> RecoveryJobResponse:
    return RecoveryJobResponse(
        job_id=str(job.get("job_id", "")),
        job_type=str(job.get("job_type", "")),
        status=str(job.get("status", "")),
        reason=report_recovery_service.redact_private_artifact_text(job.get("reason")),
        created_by=job.get("created_by"),
        created_at=job.get("created_at"),
        updated_at=job.get("updated_at"),
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        cancellation_requested_by=job.get("cancellation_requested_by"),
        cancellation_requested_at=job.get("cancellation_requested_at"),
        filters=_redact_audit_metadata(job.get("filters")),
        target_count=int(job.get("target_count") or 0),
        pending_count=int(job.get("pending_count") or 0),
        attempted_count=int(job.get("attempted_count") or 0),
        success_count=int(job.get("success_count") or 0),
        refused_count=int(job.get("refused_count") or 0),
        not_found_count=int(job.get("not_found_count") or 0),
        failed_count=int(job.get("failed_count") or 0),
        skipped_cancelled_count=int(job.get("skipped_cancelled_count") or 0),
        stop_reason=job.get("stop_reason"),
        source_job_id=job.get("source_job_id"),
        resume_result_filters=job.get("resume_result_filters"),
    )


def _recovery_job_target_response(item: dict) -> RecoveryJobTargetResponse:
    return RecoveryJobTargetResponse(
        target_id=str(item.get("target_id", "")),
        report_id=item.get("report_id"),
        parent_id=item.get("parent_id"),
        student_id=item.get("student_id"),
        student_name=item.get("student_name"),
        week_start=item.get("week_start"),
        result=str(item.get("result", "")),
        status=item.get("status"),
        email_status=item.get("email_status"),
        detail=report_recovery_service.redact_private_artifact_text(item.get("detail")),
        error_class=item.get("error_class"),
        attempted_at=item.get("attempted_at"),
        completed_at=item.get("completed_at"),
    )


def _report_audit_event_response(item: dict) -> ReportAuditEventResponse:
    return ReportAuditEventResponse(
        event_id=str(item.get("event_id", "")),
        event_at=str(item.get("event_at", "")),
        report_id=item.get("report_id"),
        parent_id=item.get("parent_id"),
        student_id=item.get("student_id"),
        week_start=item.get("week_start"),
        actor=item.get("actor"),
        action=str(item.get("action", "")),
        reason=item.get("reason"),
        source=item.get("source"),
        result=str(item.get("result", "")),
        before=_redact_audit_metadata(item.get("before")),
        after=_redact_audit_metadata(item.get("after")),
        error_class=item.get("error_class"),
        error_message=report_recovery_service.redact_private_artifact_text(item.get("error_message")),
        correlation_id=item.get("correlation_id"),
    )


def _redact_audit_metadata(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        str(key): report_recovery_service.redact_private_artifact_text(raw) if isinstance(raw, str) else raw
        for key, raw in value.items()
        if not str(key).endswith("_s3_key") and str(key) != "s3_key"
    }
