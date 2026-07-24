"""Parent routes - child list and weekly learning reports."""
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

from boto3.dynamodb.conditions import Attr, Key
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from stoa.config import Settings, get_settings
from stoa.db.dynamodb import get_table
from stoa.db.repositories import practice_repo, question_repo, report_repo, user_repo
from stoa.db.repositories.security_audit_repo import AuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.models.billing import PurchasablePlanId
from stoa.models.user import SubscriptionTier
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    AuthorizedResource,
    CurrentAuthorizationFactRepository,
    ParentAuthorizationFacts,
    ResourceRef,
    ResourceType,
    authorize_and_resolve,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor, CanonicalRole
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.security.request_correlation import get_request_correlation_id
from stoa.services import (
    account_operations_service,
    learning_profile_service,
    subscription_service,
    usage_ledger_service,
)

router = APIRouter()


@dataclass(frozen=True)
class ResolvedParent:
    claims_sub: str
    email: str
    parent_user_id: str
    profile: dict[str, Any]


class ChildSummary(BaseModel):
    id: str
    userId: str
    name: str
    email: str
    grade: str | None
    subjects: list[str]
    relationship: str = "child"


class ChildListResponse(BaseModel):
    items: list[ChildSummary]


class LegacyChildSummary(BaseModel):
    user_id: str
    email: str
    grade: str | None
    subjects: list[str]


class ParentChildActivity(BaseModel):
    id: str
    type: str
    title: str
    summary: str
    subject: str | None = None
    createdAt: str


class ParentChildSummaryStudent(BaseModel):
    id: str
    name: str
    grade: str | None = None


class ParentChildSummaryResponse(BaseModel):
    student: ParentChildSummaryStudent
    questionsAskedThisWeek: int
    aiResolvedThisWeek: int
    teacherHelpRequestsThisWeek: int
    practiceLessonsCompletedThisWeek: int
    weakTopics: list[str]
    recentActivity: list[ParentChildActivity]


class LearningSubjectDefinition(BaseModel):
    id: str
    label: str
    rolloutState: str


class LearningSubjectActivity(BaseModel):
    subject: str
    label: str
    rolloutState: str
    questionCount: int
    aiResolvedCount: int
    teacherEscalationCount: int
    feedbackAverage: float | None = None


class LearningWeakTopic(BaseModel):
    subject: str
    topicId: str
    label: str
    count: int
    latestEvidenceAt: str | None = None
    evidenceQuestionIds: list[str] = Field(default_factory=list)


class LearningProfileResponse(BaseModel):
    studentId: str
    subjects: list[LearningSubjectDefinition]
    subjectActivity: list[LearningSubjectActivity]
    weakTopics: list[LearningWeakTopic]
    strengthTopics: list[dict] = Field(default_factory=list)
    updatedAt: str


class ParentChildHistoryEvent(BaseModel):
    id: str
    type: str
    title: str
    summary: str
    subject: str | None = None
    createdAt: str


class ParentChildHistoryResponse(BaseModel):
    items: list[ParentChildHistoryEvent]


class ParentChildReportStats(BaseModel):
    questionsAsked: int = 0
    aiResolved: int = 0
    teacherHelpRequests: int = 0
    practiceLessonsCompleted: int = 0
    mistakesLogged: int = 0


class ParentChildReportWeakTopic(BaseModel):
    topic: str
    note: str = ""


class ParentChildReportDetail(BaseModel):
    reportId: str
    parentId: str
    studentId: str
    weekStart: str
    weekEnd: str | None = None
    usageCount: int = 0
    aiResolved: int = 0
    teacherResolved: int = 0
    weakKnowledgePoints: list[str] = Field(default_factory=list)
    recommendations: str = ""
    recommendationItems: list[str] = Field(default_factory=list)
    stats: ParentChildReportStats = Field(default_factory=ParentChildReportStats)
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weakTopics: list[ParentChildReportWeakTopic] = Field(default_factory=list)
    teacherNote: str | None = None
    generatedAt: str | None = None
    emailStatus: str | None = None
    reportStatus: str | None = None
    emailErrorClass: str | None = None
    emailErrorMessage: str | None = None
    generationErrorClass: str | None = None
    generationErrorMessage: str | None = None


class ParentChildReportState(BaseModel):
    status: str
    report: ParentChildReportDetail | None
    message: str | None = None


class ParentSubscriptionRequestCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request_type: str = Field(..., alias="requestType", min_length=1, max_length=50)
    requested_tier: SubscriptionTier | None = Field(default=None, alias="requestedTier")
    parent_note: str | None = Field(default=None, alias="parentNote", max_length=500)


class ParentSubscriptionRequestResponse(BaseModel):
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


class ParentSubscriptionRequestListResponse(BaseModel):
    items: list[ParentSubscriptionRequestResponse]
    count: int


class ParentSubscriptionResponse(BaseModel):
    parentId: str
    currentTier: str
    plans: dict[str, dict[str, Any]]
    pendingRequest: ParentSubscriptionRequestResponse | None = None
    billing: dict[str, Any] = Field(default_factory=dict)
    effectiveEntitlements: list[dict[str, Any]] = Field(default_factory=list)


class ParentCheckoutCommandCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    plan: PurchasablePlanId
    beneficiary_ids: tuple[str, ...] = Field(
        ...,
        alias="beneficiaryIds",
        min_length=1,
        max_length=3,
    )


class ParentCheckoutCommandResponse(BaseModel):
    checkoutRef: str
    commandState: str
    checkoutSessionId: str
    checkoutUrl: str
    safeActions: list[str]
    targetPlan: PurchasablePlanId
    beneficiaries: list[str]


class ParentBillingResponse(BaseModel):
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


class ParentChildUsageSummaryResponse(BaseModel):
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


class ParentAccountOperationsResponse(BaseModel):
    parentId: str
    parent: dict[str, Any] = Field(default_factory=dict)
    billing: dict[str, Any] = Field(default_factory=dict)
    children: list[dict[str, Any]] = Field(default_factory=list)
    usage: list[dict[str, Any]] = Field(default_factory=list)
    supportState: dict[str, Any] = Field(default_factory=dict)


def _parent_account_dependency(action: AuthorizationAction):
    async def resolve(resource_id: str):
        return {"student_id": resource_id}

    async def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.role is not CanonicalRole.PARENT:
            error = SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
            raise HTTPException(status_code=error.status_code, detail=error.public_body())
        return actor

    dependency.authorization_specs = (  # type: ignore[attr-defined]
        AuthorizationSpec(
            ResourceType.PARENT_BINDING,
            action,
            AuthorizationPurpose.SELF_SERVICE,
            resolve,
        ),
    )
    return dependency


_parent_account_read = _parent_account_dependency(AuthorizationAction.READ)
_parent_account_create = _parent_account_dependency(AuthorizationAction.CREATE)
async def _parent_child_read(
    child_id: str,
    actor: Actor = Depends(get_actor),
    facts: CurrentAuthorizationFactRepository = Depends(get_authorization_fact_repository),
    correlation_id: str = Depends(get_request_correlation_id),
    audit_sink: AuthorizationAuditSink = Depends(get_authorization_audit_sink),
) -> AuthorizedResource:
    async def resolve(resource_id: str):
        profile = user_repo.get_user(resource_id)
        if not profile or profile.get("role") not in {None, "student"}:
            return None
        return AuthorizedResource(
            ResourceRef(ResourceType.STUDENT, resource_id, resource_id),
            profile,
        )

    spec = AuthorizationSpec(
        ResourceType.STUDENT,
        AuthorizationAction.READ,
        AuthorizationPurpose.PARENT_OVERSIGHT,
        resolve,
    )
    try:
        return await authorize_and_resolve(
            actor=actor,
            resource_id=child_id,
            spec=spec,
            fact_repository=facts,
            correlation_id=correlation_id,
            audit_sink=audit_sink,
        )
    except SecurityDecisionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.public_body()) from error


async def _parent_child_metadata_resolver(resource_id: str):
    return user_repo.get_user(resource_id)


_parent_child_read.authorization_specs = (  # type: ignore[attr-defined]
    AuthorizationSpec(
        ResourceType.STUDENT,
        AuthorizationAction.READ,
        AuthorizationPurpose.PARENT_OVERSIGHT,
        _parent_child_metadata_resolver,
    ),
)


def _list_children_for_parent(parent_user_id: str) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    parent = user_repo.get_user(parent_user_id)
    for binding in user_repo.list_parent_student_bindings(parent_user_id):
        student_id = binding.get("student_id")
        if not student_id:
            continue
        reverse = user_repo.get_student_parent_binding(str(student_id), parent_user_id)
        profile = user_repo.get_user(str(student_id))
        facts = ParentAuthorizationFacts(binding, reverse, parent, profile)
        if facts.matches(parent_user_id, str(student_id)):
            children.append(
                {
                    **profile,
                    "relationship": binding.get(
                        "relationship", profile.get("relationship", "child")
                    ),
                }
            )
    return children


def _subjects_from_profile(profile: dict[str, Any]) -> list[str]:
    subjects = profile.get("primary_subjects")
    if subjects is None:
        subjects = profile.get("subjects", [])
    return subjects if isinstance(subjects, list) else []


def _child_summary_from_profile(profile: dict[str, Any]) -> ChildSummary:
    email = profile.get("email", "")
    name = profile.get("name") or (email.split("@")[0] if email else "")
    user_id = profile.get("user_id", "")
    return ChildSummary(
        id=user_id,
        userId=user_id,
        name=name,
        email=email,
        grade=profile.get("grade"),
        subjects=_subjects_from_profile(profile),
        relationship=profile.get("relationship", "child"),
    )


def _legacy_child_summary_from_profile(profile: dict[str, Any]) -> LegacyChildSummary:
    return LegacyChildSummary(
        user_id=profile.get("user_id", ""),
        email=profile.get("email", ""),
        grade=profile.get("grade"),
        subjects=_subjects_from_profile(profile),
    )


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_week_start(now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    current = current.astimezone(timezone.utc)
    return (current - timedelta(days=current.weekday())).date()


def _is_current_week(value: Any) -> bool:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return False
    return _utc_week_start(parsed) == _utc_week_start()


def _list_conversations_for_child(child_id: str, limit: int = 50) -> list[dict[str, Any]]:
    table = get_table()
    result = table.query(
        IndexName="GSI-StudentId",
        KeyConditionExpression=Key("student_id").eq(child_id),
        FilterExpression=Attr("entity_type").eq("conversation"),
        Limit=limit,
        ScanIndexForward=False,
    )
    return result.get("Items", [])


def _latest_report_for_child(parent_user_id: str, child_id: str) -> dict[str, Any] | None:
    last_key = None
    while True:
        result = report_repo.list_reports_for_parent(parent_user_id, last_key=last_key)
        for report in result.get("Items", []):
            if report.get("student_id") == child_id:
                return report
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            return None


def _question_activity(question: dict[str, Any]) -> ParentChildActivity | None:
    created_at = question.get("created_at") or question.get("createdAt")
    if not _parse_iso_datetime(created_at):
        return None
    status = question.get("status", "")
    title = "Question answered" if status == "ai_answered" else "Question asked"
    if status in ("escalated", "teacher_requested"):
        title = "Teacher help requested"
    return ParentChildActivity(
        id=question.get("question_id") or question.get("id") or f"question-{created_at}",
        type="teacher_help" if status in ("escalated", "teacher_requested") else "question",
        title=title,
        summary=question.get("summary") or question.get("prompt") or question.get("question", ""),
        subject=question.get("subject"),
        createdAt=created_at,
    )


def _history_event_from_activity(activity: ParentChildActivity) -> ParentChildHistoryEvent:
    return ParentChildHistoryEvent(**activity.model_dump())


def _practice_activity(item: dict[str, Any], event_type: str) -> ParentChildActivity | None:
    created_at = (
        item.get("completed_at")
        or item.get("created_at")
        or item.get("updated_at")
        or item.get("createdAt")
    )
    if not _parse_iso_datetime(created_at):
        return None
    title = "Practice lesson completed" if event_type == "practice" else "Practice mistake logged"
    return ParentChildActivity(
        id=item.get("lesson_id") or item.get("challenge_id") or f"{event_type}-{created_at}",
        type=event_type,
        title=title,
        summary=item.get("lesson_title") or item.get("topic_id") or item.get("subject_id") or "",
        subject=item.get("subject_id"),
        createdAt=created_at,
    )


def _conversation_activity(item: dict[str, Any]) -> ParentChildActivity | None:
    created_at = item.get("updated_at") or item.get("created_at")
    if not _parse_iso_datetime(created_at):
        return None
    escalated = bool(item.get("escalated"))
    return ParentChildActivity(
        id=item.get("conversation_id") or f"conversation-{created_at}",
        type="teacher_help" if escalated else "conversation",
        title="Teacher help requested" if escalated else "AI conversation",
        summary=item.get("last_message_preview") or item.get("title") or "",
        subject=item.get("subject"),
        createdAt=created_at,
    )


def _report_activity(report: dict[str, Any]) -> ParentChildActivity | None:
    created_at = report.get("created_at") or report.get("week_start")
    if not created_at:
        return None
    if len(str(created_at)) == 10:
        created_at = f"{created_at}T00:00:00+00:00"
    if not _parse_iso_datetime(created_at):
        return None
    return ParentChildActivity(
        id=report.get("report_id") or f"report-{created_at}",
        type="report",
        title="Weekly report available",
        summary=report.get("summary") or report.get("recommendations", ""),
        subject=None,
        createdAt=created_at,
    )


def _sort_activities(activities: list[ParentChildActivity], limit: int) -> list[ParentChildActivity]:
    return sorted(
        activities,
        key=lambda item: (_parse_iso_datetime(item.createdAt) or datetime.min.replace(tzinfo=timezone.utc), item.id),
        reverse=True,
    )[:limit]


def _question_history_events(child_id: str, limit: int = 100) -> list[ParentChildActivity]:
    result = question_repo.list_by_student(child_id, limit=limit)
    return [
        activity
        for question in result.get("Items", [])
        if (activity := _question_activity(question)) is not None
    ]


def _practice_history_events(child_id: str) -> list[ParentChildActivity]:
    activities: list[ParentChildActivity] = []
    for progress in practice_repo.get_progress(child_id):
        activity = _practice_activity(progress, "practice")
        if activity:
            activities.append(activity)
    for mistake in practice_repo.get_mistakes(child_id):
        activity = _practice_activity(mistake, "practice_mistake")
        if activity:
            activities.append(activity)
    return activities


def _conversation_history_events(child_id: str) -> list[ParentChildActivity]:
    return [
        activity
        for conversation in _list_conversations_for_child(child_id)
        if (activity := _conversation_activity(conversation)) is not None
    ]


def _report_history_events(parent_user_id: str, child_id: str) -> list[ParentChildActivity]:
    activities: list[ParentChildActivity] = []
    last_key = None
    while True:
        result = report_repo.list_reports_for_parent(parent_user_id, last_key=last_key)
        for report in result.get("Items", []):
            if report.get("student_id") != child_id:
                continue
            activity = _report_activity(report)
            if activity:
                activities.append(activity)
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            return activities


def _report_detail_from_item(report: dict[str, Any]) -> ParentChildReportDetail:
    stats = report.get("stats") or {}
    weak_topics = report.get("weak_topics") or []
    recommendation_items = report.get("recommendation_items")
    if not isinstance(recommendation_items, list):
        recommendation_items = [report.get("recommendations", "")] if report.get("recommendations") else []
    return ParentChildReportDetail(
        reportId=report.get("report_id", ""),
        parentId=report.get("parent_id", ""),
        studentId=report.get("student_id", ""),
        weekStart=report.get("week_start", ""),
        weekEnd=report.get("week_end"),
        usageCount=report.get("usage_count", 0),
        aiResolved=report.get("ai_resolved", 0),
        teacherResolved=report.get("teacher_resolved", 0),
        weakKnowledgePoints=report.get("weak_knowledge_points", []),
        recommendations=report.get("recommendations", ""),
        recommendationItems=[str(item) for item in recommendation_items if item],
        stats=ParentChildReportStats(
            questionsAsked=stats.get("questionsAsked", report.get("usage_count", 0)),
            aiResolved=stats.get("aiResolved", report.get("ai_resolved", 0)),
            teacherHelpRequests=stats.get("teacherHelpRequests", report.get("teacher_resolved", 0)),
            practiceLessonsCompleted=stats.get("practiceLessonsCompleted", report.get("practice_lessons_completed", 0)),
            mistakesLogged=stats.get("mistakesLogged", report.get("mistakes_logged", 0)),
        ),
        summary=report.get("summary", ""),
        strengths=[str(item) for item in report.get("strengths", []) if item],
        weakTopics=[
            ParentChildReportWeakTopic(
                topic=str(item.get("topic", "")),
                note=str(item.get("note", "")),
            )
            for item in weak_topics
            if isinstance(item, dict) and item.get("topic")
        ],
        teacherNote=report.get("teacher_note"),
        generatedAt=report.get("generated_at"),
        emailStatus=report.get("email_status"),
        reportStatus=report.get("status"),
        emailErrorClass=report.get("email_error_class"),
        emailErrorMessage=report.get("email_error_message"),
        generationErrorClass=report.get("generation_error_class"),
        generationErrorMessage=None,
    )


def _missing_report_state() -> ParentChildReportState:
    return ParentChildReportState(
        status="missing",
        report=None,
        message="No weekly report is available yet.",
    )


def _available_report_state(report: dict[str, Any]) -> ParentChildReportState:
    return ParentChildReportState(status="available", report=_report_detail_from_item(report))


def _failed_report_state(report: dict[str, Any]) -> ParentChildReportState:
    return ParentChildReportState(
        status="failed",
        report=_report_detail_from_item(report),
        message="Weekly report generation failed.",
    )


def _pending_report_state(report: dict[str, Any]) -> ParentChildReportState:
    return ParentChildReportState(
        status="pending",
        report=_report_detail_from_item(report),
        message="Weekly report generation is still in progress.",
    )


def _report_state_from_item(report: dict[str, Any]) -> ParentChildReportState:
    if report.get("status") == "generation_claimed":
        return _pending_report_state(report)
    if report.get("status") == "generation_failed":
        return _failed_report_state(report)
    return _available_report_state(report)


@router.get("/me/children", response_model=ChildListResponse)
async def list_my_children(
    actor: Actor = Depends(_parent_account_read),
):
    """Return children linked to the authenticated parent."""
    try:
        children = _list_children_for_parent(actor.user_id)
    except Exception as exc:
        error = SecurityDecisionError(
            SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
            internal_detail=type(exc).__name__,
        )
        raise HTTPException(status_code=error.status_code, detail=error.public_body()) from exc
    return ChildListResponse(items=[_child_summary_from_profile(child) for child in children])


@router.get("/me/subscription", response_model=ParentSubscriptionResponse)
async def get_my_subscription(
    actor: Actor = Depends(_parent_account_read),
    settings: Settings = Depends(get_settings),
):
    """Return the authenticated parent's current plan and MVP plan options."""
    return subscription_service.get_parent_subscription(actor.user_id, settings=settings)


@router.post(
    "/me/subscription/checkout",
    response_model=ParentCheckoutCommandResponse,
    status_code=201,
)
async def create_my_subscription_checkout(
    body: ParentCheckoutCommandCreate,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=8,
            max_length=128,
            pattern=r"^[\x21-\x7e]+$",
        ),
    ],
    actor: Actor = Depends(_parent_account_create),
    settings: Settings = Depends(get_settings),
):
    """Create or resume one durable sandbox checkout command."""
    return subscription_service.create_or_resume_checkout_command(
        parent_id=actor.user_id,
        idempotency_key=idempotency_key,
        plan=body.plan.value,
        beneficiary_ids=body.beneficiary_ids,
        settings=settings,
    )


@router.get("/me/subscription/billing", response_model=ParentBillingResponse)
async def get_my_subscription_billing(
    actor: Actor = Depends(_parent_account_read),
    settings: Settings = Depends(get_settings),
):
    """Return provider billing status for the authenticated parent."""
    return subscription_service.get_parent_billing(actor.user_id, settings=settings)


@router.get("/me/account-operations", response_model=ParentAccountOperationsResponse)
async def get_my_account_operations(
    day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    actor: Actor = Depends(_parent_account_read),
    settings: Settings = Depends(get_settings),
):
    """Return a consolidated parent account operations summary."""
    return account_operations_service.build_parent_operations_summary(
        actor.user_id,
        settings=settings,
        day=day,
    )


@router.post(
    "/me/subscription/requests",
    response_model=ParentSubscriptionRequestResponse,
    status_code=201,
)
async def create_my_subscription_request(
    body: ParentSubscriptionRequestCreate,
    actor: Actor = Depends(_parent_account_create),
    settings: Settings = Depends(get_settings),
):
    """Submit a manual subscription request for internal admin processing."""
    return subscription_service.create_parent_request(
        parent_id=actor.user_id,
        request_type=body.request_type,
        requested_tier=body.requested_tier.value if body.requested_tier else None,
        parent_note=body.parent_note,
    )


@router.get("/me/subscription/requests", response_model=ParentSubscriptionRequestListResponse)
async def list_my_subscription_requests(
    limit: int = Query(default=25, ge=1, le=50),
    actor: Actor = Depends(_parent_account_read),
):
    """Return the authenticated parent's recent manual subscription requests."""
    items = subscription_service.list_parent_requests(actor.user_id, limit=limit)
    return ParentSubscriptionRequestListResponse(items=items, count=len(items))


@router.get("/me/children/{child_id}/summary", response_model=ParentChildSummaryResponse)
async def get_child_summary(
    child_id: str,
    actor: Actor = Depends(get_actor),
    authorized_child: AuthorizedResource = Depends(_parent_child_read),
):
    child = dict(authorized_child.value)
    child_id = authorized_child.ref.student_id

    questions = question_repo.list_by_student(child_id, limit=500).get("Items", [])
    progress = practice_repo.get_progress(child_id)
    mistakes = practice_repo.get_mistakes(child_id)
    conversations = _list_conversations_for_child(child_id)
    latest_report = _latest_report_for_child(actor.user_id, child_id)

    current_week_questions = [item for item in questions if _is_current_week(item.get("created_at"))]
    current_week_progress = [
        item
        for item in progress
        if item.get("status") == "completed" and _is_current_week(item.get("completed_at"))
    ]
    ai_resolved = sum(1 for item in current_week_questions if item.get("status") == "ai_answered")
    teacher_help = sum(
        1
        for item in current_week_questions
        if item.get("status") in ("escalated", "teacher_requested", "teacher_help")
        or item.get("teacher_help_requested")
    )
    teacher_help += sum(
        1
        for item in conversations
        if item.get("escalated")
        and _is_current_week(item.get("escalated_at") or item.get("updated_at"))
    )

    weak_topics_counter: Counter[str] = Counter()
    for question in questions:
        weak_topics_counter.update(question.get("knowledge_points", []))
    for mistake in mistakes:
        for key in ("topic_id", "subject_id"):
            if mistake.get(key):
                weak_topics_counter[mistake[key]] += 1
    if latest_report:
        weak_topics_counter.update(latest_report.get("weak_knowledge_points", []))

    activities = []
    activities.extend(_question_history_events(child_id, limit=20))
    activities.extend(_practice_history_events(child_id))
    activities.extend(_conversation_history_events(child_id))
    if latest_report and (report_activity := _report_activity(latest_report)):
        activities.append(report_activity)

    return ParentChildSummaryResponse(
        student=ParentChildSummaryStudent(
            id=child.get("user_id", child_id),
            name=child.get("name") or child.get("email", "").split("@")[0],
            grade=child.get("grade"),
        ),
        questionsAskedThisWeek=len(current_week_questions),
        aiResolvedThisWeek=ai_resolved,
        teacherHelpRequestsThisWeek=teacher_help,
        practiceLessonsCompletedThisWeek=len(current_week_progress),
        weakTopics=[
            topic
            for topic, _ in sorted(weak_topics_counter.items(), key=lambda item: (-item[1], item[0]))
        ][:10],
        recentActivity=_sort_activities(activities, limit=5),
    )


@router.get("/me/children/{child_id}/learning-profile", response_model=LearningProfileResponse)
async def get_child_learning_profile(
    child_id: str,
    authorized_child: AuthorizedResource = Depends(_parent_child_read),
):
    """Return subject-level profile seeds for an authorized child."""
    child_id = authorized_child.ref.student_id

    questions = question_repo.list_by_student(child_id, limit=500).get("Items", [])
    mistakes = practice_repo.get_mistakes(child_id)
    return learning_profile_service.build_learning_profile(
        student_id=child_id,
        questions=questions,
        mistakes=mistakes,
    )


@router.get("/me/children/{child_id}/usage", response_model=ParentChildUsageSummaryResponse)
async def get_child_usage_summary(
    child_id: str,
    day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    actor: Actor = Depends(get_actor),
    authorized_child: AuthorizedResource = Depends(_parent_child_read),
    settings: Settings = Depends(get_settings),
):
    """Return a privacy-safe quota usage summary for an authorized child."""
    child_id = authorized_child.ref.student_id
    summary = usage_ledger_service.build_student_usage_summary(
        student_id=child_id,
        settings=settings,
        day=day,
    )
    if summary.get("parentId") not in (None, actor.user_id):
        raise HTTPException(status_code=403, detail="Not your child usage")
    return summary


@router.get("/me/children/{child_id}/history", response_model=ParentChildHistoryResponse)
async def get_child_history(
    child_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    actor: Actor = Depends(get_actor),
    authorized_child: AuthorizedResource = Depends(_parent_child_read),
):
    child_id = authorized_child.ref.student_id

    activities = []
    activities.extend(_question_history_events(child_id, limit=100))
    activities.extend(_practice_history_events(child_id))
    activities.extend(_conversation_history_events(child_id))
    activities.extend(_report_history_events(actor.user_id, child_id))

    return ParentChildHistoryResponse(
        items=[_history_event_from_activity(activity) for activity in _sort_activities(activities, limit)]
    )


@router.get("/me/children/{child_id}/report", response_model=ParentChildReportState)
async def get_child_report(
    child_id: str,
    actor: Actor = Depends(get_actor),
    authorized_child: AuthorizedResource = Depends(_parent_child_read),
):
    child_id = authorized_child.ref.student_id
    report = _latest_report_for_child(actor.user_id, child_id)
    if report and report.get("student_id") != child_id:
        report = None
    return _report_state_from_item(report) if report else _missing_report_state()


@router.get("/me/children/{child_id}/reports/{week}", response_model=ParentChildReportState)
async def get_child_report_by_week(
    child_id: str,
    week: str,
    actor: Actor = Depends(get_actor),
    authorized_child: AuthorizedResource = Depends(_parent_child_read),
):
    child_id = authorized_child.ref.student_id
    report = report_repo.get_report_for_child_by_week(actor.user_id, child_id, week)
    if not report or report.get("student_id") != child_id:
        return _missing_report_state()
    return _report_state_from_item(report)
