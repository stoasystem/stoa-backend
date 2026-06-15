"""Admin routes — user management, report operations, and platform statistics."""
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from stoa.config import Settings, get_settings
from stoa.db.dynamodb import get_table
from stoa.db.repositories import report_repo, user_repo
from stoa.deps import require_role
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
from stoa.models.user import SubscriptionTier
from stoa.services import (
    moderation_service,
    report_audit_retention_service,
    report_artifact_edit_service,
    report_edit_service,
    release_evidence_service,
    report_recovery_evidence_service,
    report_recovery_job_service,
    report_recovery_service,
    curriculum_analytics_service,
    curriculum_ops_service,
    support_destination_service,
    support_handoff_service,
    support_sla_service,
    subscription_service,
    teacher_reply_service,
)

router = APIRouter()


class UserUpdateRequest(BaseModel):
    subscription_tier: Optional[SubscriptionTier] = None
    is_active: Optional[bool] = None


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
    currentPeriodStart: str | None = None
    currentPeriodEnd: str | None = None
    cancelAtPeriodEnd: bool = False
    lastProviderEventId: str | None = None
    lastProviderEventType: str | None = None
    lastProviderEventAt: str | None = None
    manualOverrideAt: str | None = None
    manualOverrideBy: str | None = None
    manualOverrideSource: str | None = None
    updatedAt: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


class SubscriptionBillingListResponse(BaseModel):
    items: list[SubscriptionBillingResponse]
    count: int


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


class ParentStudentBindingRepairRequest(BaseModel):
    parent_id: str = Field(..., min_length=1, max_length=200)
    student_id: str = Field(..., min_length=1, max_length=200)
    relationship: str = Field(default="child", min_length=1, max_length=50)
    reason: str = Field(..., min_length=1, max_length=500)


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


class CurriculumExerciseDraftRequest(BaseModel):
    exercise_id: str | None = Field(default=None, alias="exerciseId", max_length=200)
    prompt: str = Field(..., min_length=1, max_length=2000)
    type: str = Field(default="text_input", min_length=1, max_length=50)
    difficulty: str = Field(default="practice", min_length=1, max_length=80)
    order: int | None = Field(default=None, ge=1, le=200)
    answer_key: str | None = Field(default=None, alias="answerKey", max_length=2000)
    explanation: str | None = Field(default=None, max_length=2000)
    skills: list[str] = Field(default_factory=list)


class CurriculumLessonDraftRequest(BaseModel):
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
    completions: int
    publishEvents: int
    archiveEvents: int
    priorityScore: int
    updatedAt: str | None = None


class CurriculumQualityResponse(BaseModel):
    items: list[CurriculumQualityMetricResponse]
    count: int
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
    return ModerationCaseListResponse(items=items, count=len(items))


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
    user: dict = Depends(require_role("admin", "tutor", "teacher")),
):
    """List internal curriculum authoring items awaiting operational action."""
    return curriculum_ops_service.list_worklist(status=status, limit=limit)


@router.get("/curriculum/analytics/content-quality", response_model=CurriculumQualityResponse)
async def get_curriculum_content_quality(
    content_type: str | None = Query(default=None, alias="contentType"),
    subject_id: str | None = Query(default=None, alias="subjectId"),
    topic_id: str | None = Query(default=None, alias="topicId"),
    limit: int = Query(default=100, ge=1, le=200),
    user: dict = Depends(require_role("admin", "tutor", "teacher")),
):
    """Return aggregate-only curriculum quality metrics for operators."""
    return curriculum_analytics_service.content_quality_summary(
        content_type=content_type,
        subject_id=subject_id,
        topic_id=topic_id,
        limit=limit,
    )


@router.post("/curriculum/lessons/drafts", response_model=CurriculumVersionResponse)
async def create_curriculum_lesson_draft(
    body: CurriculumLessonDraftRequest,
    user: dict = Depends(require_role("admin", "tutor", "teacher")),
):
    """Create an internal lesson-plus-exercises authoring draft."""
    return curriculum_ops_service.create_lesson_draft(body.model_dump(by_alias=False), user)


@router.get("/curriculum/lessons/{public_lesson_id}/preview", response_model=CurriculumVersionResponse)
async def preview_curriculum_lesson_version(
    public_lesson_id: str,
    version_id: str = Query(..., alias="versionId"),
    user: dict = Depends(require_role("admin", "tutor", "teacher")),
):
    """Preview an unpublished curriculum version without changing student reads."""
    return curriculum_ops_service.preview_lesson(public_lesson_id, version_id)


@router.post(
    "/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/submit-review",
    response_model=CurriculumVersionResponse,
)
async def submit_curriculum_lesson_review(
    public_lesson_id: str,
    version_id: str,
    user: dict = Depends(require_role("admin", "tutor", "teacher")),
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
    user: dict = Depends(require_role("admin", "tutor", "teacher")),
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
    user: dict = Depends(require_role("admin", "tutor", "teacher")),
):
    """Return a curriculum version to authoring with review notes."""
    return curriculum_ops_service.request_changes(public_lesson_id, version_id, user, body.reason)


@router.post("/curriculum/lessons/{public_lesson_id}/publish")
async def publish_curriculum_lesson_version(
    public_lesson_id: str,
    body: CurriculumPublishRequest,
    user: dict = Depends(require_role("admin")),
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
async def rollback_curriculum_lesson_version(
    public_lesson_id: str,
    body: CurriculumPublishRequest,
    user: dict = Depends(require_role("admin")),
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
async def archive_curriculum_lesson_version(
    public_lesson_id: str,
    body: CurriculumPublishRequest,
    user: dict = Depends(require_role("admin")),
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


@router.get("/users")
async def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    role: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """Paginated list of all platform users."""
    table = get_table()

    filter_expr = "#entity = :profile"
    attr_names = {"#entity": "SK"}
    attr_values = {":profile": "PROFILE"}

    if role:
        filter_expr += " AND #role = :role"
        attr_names["#role"] = "role"
        attr_values[":role"] = role

    result = table.scan(
        FilterExpression=filter_expr,
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
        Limit=limit,
    )
    users = result.get("Items", [])
    # Strip PK/SK from response
    for u in users:
        u.pop("PK", None)
        u.pop("SK", None)

    return {"items": users, "count": len(users)}


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

    table = get_table()
    update_parts = []
    attr_values: dict = {}

    if body.subscription_tier is not None:
        update_parts.append("subscription_tier = :tier")
        attr_values[":tier"] = body.subscription_tier.value
    if body.is_active is not None:
        update_parts.append("is_active = :active")
        attr_values[":active"] = body.is_active

    if not update_parts:
        return {"user_id": user_id, "message": "Nothing to update"}

    table.update_item(
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        UpdateExpression="SET " + ", ".join(update_parts),
        ExpressionAttributeValues=attr_values,
    )
    return {"user_id": user_id, "updated": {k.lstrip(":"): v for k, v in attr_values.items()}}


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
    """List manual subscription requests for admin processing."""
    items = subscription_service.list_admin_requests(
        limit=limit,
        status=status,
        requested_tier=requested_tier,
        parent_id=parent_id,
        date_from=date_from,
        date_to=date_to,
    )
    return SubscriptionRequestListResponse(items=items, count=len(items))


@router.get("/subscriptions/requests/{request_id}", response_model=SubscriptionRequestResponse)
async def get_subscription_request(
    request_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Open one manual subscription request with lifecycle history."""
    return subscription_service.get_request(request_id)


@router.get("/subscriptions/billing", response_model=SubscriptionBillingListResponse)
async def list_subscription_billing(
    limit: int = Query(default=50, ge=1, le=100),
    parent_id: Optional[str] = Query(default=None),
    billing_status: Optional[str] = Query(default=None),
    billing_provider: Optional[str] = Query(default=None),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """List provider billing records for admin visibility."""
    items = subscription_service.list_admin_billing(
        limit=limit,
        parent_id=parent_id,
        billing_status=billing_status,
        billing_provider=billing_provider,
        settings=settings,
    )
    return SubscriptionBillingListResponse(items=items, count=len(items))


@router.get("/subscriptions/billing/accounting-export", response_model=SubscriptionAccountingExportResponse)
async def list_subscription_accounting_export(
    limit: int = Query(default=100, ge=1, le=500),
    parent_id: Optional[str] = Query(default=None),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """List redacted provider billing rows for Swiss accounting handoff."""
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
    """Inspect redacted live provider readiness without creating provider mutations."""
    return subscription_service.get_provider_readiness(settings)


@router.get("/subscriptions/billing/rollout-controls", response_model=SubscriptionRolloutControlsResponse)
async def get_subscription_rollout_controls(
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Inspect effective checkout/refund rollout controls."""
    return subscription_service.get_payment_rollout_controls(settings)


@router.patch("/subscriptions/billing/rollout-controls", response_model=SubscriptionRolloutControlsResponse)
async def update_subscription_rollout_controls(
    body: SubscriptionRolloutControlsUpdateRequest,
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Update checkout/refund rollout controls for new live-changing operations."""
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
    """Open one parent provider billing record with recent event history."""
    return subscription_service.get_admin_billing(parent_id, settings=settings)


@router.post("/subscriptions/billing/{parent_id}/refunds", response_model=SubscriptionRefundExecutionResponse)
async def execute_subscription_refund(
    parent_id: str,
    body: SubscriptionRefundExecutionRequest,
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Execute a gated provider refund for an eligible billing record."""
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
    """Move a subscription request through review lifecycle states."""
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
    """Apply an approved manual request and update the parent's subscription tier."""
    return subscription_service.apply_request(
        request_id=request_id,
        admin_note=body.admin_note,
        effective_at=body.effective_at,
        user=user,
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(user: dict = Depends(require_role("admin"))):
    """Return aggregate platform metrics (full-table scan — small scale only)."""
    table = get_table()

    # Count user profiles
    user_scan = table.scan(
        FilterExpression="SK = :profile",
        ExpressionAttributeValues={":profile": "PROFILE"},
        ProjectionExpression="#role",
        ExpressionAttributeNames={"#role": "role"},
    )
    users = user_scan.get("Items", [])

    counts = {"student": 0, "parent": 0, "teacher": 0}
    for u in users:
        r = u.get("role", "")
        if r in counts:
            counts[r] += 1

    # Count questions by status
    q_scan = table.scan(
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
    questions = [
        q for q in q_scan.get("Items", [])
        if q.get("status") in (s.value for s in QuestionStatus)
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
    )


def _binding_response(item: dict[str, Any]) -> ParentStudentBindingResponse:
    return ParentStudentBindingResponse(
        parent_id=item.get("parent_id", ""),
        student_id=item.get("student_id", ""),
        relationship=item.get("relationship", "child"),
        status=item.get("status", "active"),
        source=item.get("source"),
        updated_at=item.get("updated_at"),
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


@router.post("/parent-bindings/repair", response_model=ParentStudentBindingResponse)
async def repair_parent_binding(
    body: ParentStudentBindingRepairRequest,
    user: dict = Depends(require_role("admin")),
):
    """Repair a parent/student binding and mirror the legacy student parent_id."""
    parent = user_repo.get_user(body.parent_id)
    if not parent or parent.get("role") != "parent":
        raise HTTPException(status_code=404, detail="Parent profile not found")
    student = user_repo.get_user(body.student_id)
    if not student or student.get("role") != "student":
        raise HTTPException(status_code=404, detail="Student profile not found")
    now = report_audit_retention_service.now_iso()
    user_repo.update_student_parent_link(body.student_id, body.parent_id, body.relationship)
    binding = user_repo.put_parent_student_binding(
        parent_id=body.parent_id,
        student_id=body.student_id,
        relationship=body.relationship,
        status="active",
        source="admin_repair",
        actor=str(user.get("sub") or user.get("username") or "admin"),
        created_at=now,
    )
    return _binding_response(binding)


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
    items = [_report_operation_response(report) for report in result.get("Items", [])]
    return ReportOperationListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_admin_page_token(result.get("LastEvaluatedKey")),
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


@router.get("/reports/recovery-evidence")
async def export_recovery_evidence(
    request: Request,
    job_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    include_targets: bool = Query(default=True),
    include_job_audit: bool = Query(default=True),
    target_limit: int = Query(default=50, ge=1, le=100),
    audit_limit: int = Query(default=50, ge=1, le=100),
    next_target_token: Optional[str] = Query(default=None),
    next_audit_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """Export metadata-only report recovery evidence for release/support review."""
    request_id = _request_id(request)
    operator = _operator_id(user)
    try:
        if job_id:
            response = _export_recovery_job_evidence(
                job_id=job_id,
                request_id=request_id,
                include_targets=include_targets,
                include_job_audit=include_job_audit,
                target_limit=target_limit,
                audit_limit=audit_limit,
                next_target_token=next_target_token,
                next_audit_token=next_audit_token,
            )
        else:
            response = _export_recent_recovery_jobs(
                request_id=request_id,
                status=status,
                limit=limit,
                next_token=next_token,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

    report_recovery_evidence_service.log_export_access(
        actor=operator,
        request_id=request_id,
        scope=response["scope"],
        filters=response["filters"],
        result_counts={
            "jobs": len(response["jobs"]),
            "targets": len(response["targets"]),
            "job_audit": len(response["job_audit"]),
            "report_audit": len(response["report_audit"]),
        },
        status="success",
    )
    return response


@router.get("/reports/recovery-jobs/{job_id}/support-package")
async def export_recovery_job_support_package(
    request: Request,
    job_id: str,
    include_targets: bool = Query(default=True),
    include_job_audit: bool = Query(default=True),
    include_report_audit: bool = Query(default=False),
    target_limit: int = Query(default=50, ge=1, le=100),
    audit_limit: int = Query(default=50, ge=1, le=100),
    next_target_token: Optional[str] = Query(default=None),
    next_audit_token: Optional[str] = Query(default=None),
    note: Optional[str] = Query(default=None, max_length=500),
    user: dict = Depends(require_role("admin")),
):
    """Export a support-safe metadata package for one recovery job."""
    request_id = _request_id(request)
    operator = _operator_id(user)
    try:
        response = _export_recovery_job_support_package(
            job_id=job_id,
            request_id=request_id,
            include_targets=include_targets,
            include_job_audit=include_job_audit,
            include_report_audit=include_report_audit,
            target_limit=target_limit,
            audit_limit=audit_limit,
            next_target_token=next_target_token,
            next_audit_token=next_audit_token,
            operator_note=note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

    report_recovery_evidence_service.log_export_access(
        actor=operator,
        request_id=request_id,
        scope=response["scope"],
        filters={"job_id": job_id, "source_job_id": response.get("source_job", {}).get("job_id") if response.get("source_job") else None},
        result_counts={
            "targets": len(response["targets"]),
            "job_audit": len(response["job_audit"]),
            "report_audit": len(response["report_audit"]),
        },
        status="success",
    )
    return response


@router.post("/reports/support-handoff-package")
async def create_support_handoff_package(
    request: Request,
    body: SupportHandoffPackageRequest,
    user: dict = Depends(require_role("admin")),
):
    """Generate a support-safe handoff package without direct external writes."""
    request_id = _request_id(request)
    operator = _operator_id(user)
    destination = body.destination_mode.strip()
    if destination not in support_handoff_service.ALLOWED_DESTINATIONS | support_handoff_service.REFUSED_DESTINATIONS:
        raise HTTPException(status_code=422, detail=f"Unsupported destination mode: {destination or 'missing'}")

    recovery_sections: list[dict[str, Any]] = []
    fixture_response: dict[str, Any] | None = None

    if destination not in support_handoff_service.REFUSED_DESTINATIONS:
        try:
            recovery_sections = [
                _support_handoff_recovery_section(
                    job_id=job_id,
                    request_id=request_id,
                    include_targets=body.include_targets,
                    include_job_audit=body.include_job_audit,
                    include_report_audit=body.include_report_audit,
                    target_limit=body.target_limit,
                    audit_limit=body.audit_limit,
                )
                for job_id in body.recovery_job_ids
            ]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

        if body.fixture:
            fixture_response = _support_handoff_fixture_response(body.fixture)

    try:
        package = support_handoff_service.build_package(
            reason=body.reason,
            destination_mode=destination,
            generated_by=operator,
            request_id=request_id,
            recovery_sections=recovery_sections,
            release_evidence=body.release_evidence,
            fixture=fixture_response,
            operator_note=body.operator_note,
        )
    except support_handoff_service.SupportHandoffError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    support_handoff_service.write_audit_event(
        package,
        actor=operator,
        reason=body.reason,
        request_id=request_id,
    )
    return package


@router.post("/reports/support-handoff-delivery")
async def create_support_handoff_delivery(
    request: Request,
    body: SupportHandoffPackageRequest,
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Deliver or refuse a support-safe handoff package for an approved destination."""
    request_id = _request_id(request)
    operator = _operator_id(user)
    destination = body.destination_mode.strip()
    contract_defined_destinations = (
        {
            support_destination_service.INTERNAL_QUEUE_DESTINATION,
            support_destination_service.THIRD_PARTY_SUPPORT_DESTINATION,
        }
        | support_destination_service.CONTRACT_DEFINED_REFUSED_DESTINATIONS
    )
    if destination not in contract_defined_destinations:
        raise HTTPException(status_code=422, detail=f"Unsupported destination mode: {destination or 'missing'}")

    if destination in support_destination_service.CONTRACT_DEFINED_REFUSED_DESTINATIONS:
        delivery = support_destination_service.refuse_destination(
            destination_mode=destination,
            actor=operator,
            reason=body.reason,
            request_id=request_id,
            refusal_reason="destination is contract-defined but not approved for Phase 149 delivery",
        )
        return {"package": None, "delivery": delivery}

    if (
        destination == support_destination_service.INTERNAL_QUEUE_DESTINATION
        and not settings.support_internal_queue_approved
    ):
        delivery = support_destination_service.refuse_destination(
            destination_mode=destination,
            actor=operator,
            reason=body.reason,
            request_id=request_id,
            refusal_reason="support internal queue delivery is not approved",
        )
        return {"package": None, "delivery": delivery}

    if destination == support_destination_service.THIRD_PARTY_SUPPORT_DESTINATION and (
        not settings.support_third_party_provider_approved
        or not settings.support_third_party_provider_api_key.strip()
    ):
        delivery = support_destination_service.refuse_destination(
            destination_mode=destination,
            actor=operator,
            reason=body.reason,
            request_id=request_id,
            refusal_reason="third-party support provider is not approved or credentials are missing",
        )
        return {"package": None, "delivery": delivery}

    recovery_sections: list[dict[str, Any]] = []
    fixture_response: dict[str, Any] | None = None
    try:
        recovery_sections = [
            _support_handoff_recovery_section(
                job_id=job_id,
                request_id=request_id,
                include_targets=body.include_targets,
                include_job_audit=body.include_job_audit,
                include_report_audit=body.include_report_audit,
                target_limit=body.target_limit,
                audit_limit=body.audit_limit,
            )
            for job_id in body.recovery_job_ids
        ]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

    if body.fixture:
        fixture_response = _support_handoff_fixture_response(body.fixture)

    try:
        package = support_handoff_service.build_package(
            reason=body.reason,
            destination_mode=destination,
            generated_by=operator,
            request_id=request_id,
            recovery_sections=recovery_sections,
            release_evidence=body.release_evidence,
            fixture=fixture_response,
            operator_note=body.operator_note,
        )
    except support_handoff_service.SupportHandoffError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    support_handoff_service.write_audit_event(
        package,
        actor=operator,
        reason=body.reason,
        request_id=request_id,
    )
    if destination == support_destination_service.THIRD_PARTY_SUPPORT_DESTINATION:
        delivery = support_destination_service.deliver_third_party_support(
            package=package,
            actor=operator,
            reason=body.reason,
            request_id=request_id,
            settings=settings,
        )
    else:
        delivery = support_destination_service.deliver_internal_queue(
            package=package,
            actor=operator,
            reason=body.reason,
            request_id=request_id,
            settings=settings,
        )
    return {"package": package, "delivery": delivery}


@router.get("/reports/support-handoff-deliveries")
async def list_support_handoff_deliveries(
    status: str | None = Query(default=None),
    destination_mode: str | None = Query(default=None),
    package_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    next_token: str | None = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List recent support handoff delivery lifecycle records for operators."""
    if status and status not in support_destination_service.DELIVERY_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported delivery status")
    allowed_destinations = (
        {
            support_destination_service.INTERNAL_QUEUE_DESTINATION,
            support_destination_service.THIRD_PARTY_SUPPORT_DESTINATION,
        }
        | support_destination_service.CONTRACT_DEFINED_REFUSED_DESTINATIONS
    )
    if destination_mode and destination_mode not in allowed_destinations:
        raise HTTPException(status_code=400, detail="Unsupported destination mode")
    try:
        last_key = report_repo.decode_support_handoff_delivery_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc
    result = report_repo.list_support_handoff_delivery_summaries(
        status=status,
        destination_mode=destination_mode,
        package_id=package_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        last_key=last_key,
    )
    items = [
        support_destination_service.support_handoff_delivery_response(item)
        for item in result.get("Items", [])
    ]
    return {
        "items": items,
        "count": len(items),
        "next_token": report_repo.encode_support_handoff_delivery_page_token(result.get("LastEvaluatedKey")),
        "filters": {
            "status": status,
            "destination_mode": destination_mode,
            "package_id": package_id,
            "date_from": date_from,
            "date_to": date_to,
        },
    }


@router.get("/reports/support-handoff-sla")
async def get_support_handoff_sla(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Return metadata-only support handoff SLA and messaging analytics."""
    return support_sla_service.build_support_sla_analytics(
        settings=settings,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/reports/support-handoff-deliveries/{delivery_id}")
async def get_support_handoff_delivery_detail(
    delivery_id: str,
    audit_limit: int = Query(default=25, ge=1, le=100),
    audit_next_token: str | None = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """Inspect one support handoff delivery summary plus bounded lifecycle audit events."""
    try:
        last_key = report_repo.decode_support_handoff_delivery_page_token(audit_next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc
    record = report_repo.get_support_handoff_delivery_record(delivery_id)
    if not record:
        raise HTTPException(status_code=404, detail="Support handoff delivery not found")
    audit_result = report_repo.list_support_handoff_delivery_audit_events(
        delivery_id,
        limit=audit_limit,
        last_key=last_key,
    )
    audit_events = [
        support_destination_service.support_handoff_delivery_audit_response(event)
        for event in audit_result.get("Items", [])
    ]
    return {
        "delivery": support_destination_service.support_handoff_delivery_response(record),
        "audit_events": audit_events,
        "audit_count": len(audit_events),
        "audit_next_token": report_repo.encode_support_handoff_delivery_page_token(
            audit_result.get("LastEvaluatedKey")
        ),
    }


@router.post("/reports/support-handoff-deliveries/{delivery_id}/retry")
async def retry_support_handoff_delivery(
    delivery_id: str,
    request: Request,
    body: SupportHandoffRetryRequest | None = Body(default=None),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Retry one failed third-party support delivery without duplicating tickets."""
    retry_request = body or SupportHandoffRetryRequest()
    delivery = support_destination_service.retry_provider_delivery(
        delivery_id=delivery_id,
        actor=_operator_id(user),
        request_id=_request_id(request),
        settings=settings,
    )
    if not delivery:
        raise HTTPException(status_code=404, detail="Support handoff delivery not found")
    return {"delivery": delivery, "reason": retry_request.reason}


@router.post("/reports/support-handoff-deliveries/{delivery_id}/provider-sync")
async def sync_support_handoff_delivery_provider_status(
    delivery_id: str,
    request: Request,
    body: SupportHandoffProviderSyncRequest,
    user: dict = Depends(require_role("admin")),
):
    """Normalize one provider ticket update without storing raw provider payloads."""
    delivery = support_destination_service.sync_provider_ticket(
        delivery_id=delivery_id,
        provider_event_id=body.provider_event_id,
        provider_status=body.provider_status,
        provider_updated_at=body.provider_updated_at,
        provider_assignee=body.provider_assignee,
        provider_priority=body.provider_priority,
        actor=_operator_id(user),
        request_id=_request_id(request),
    )
    if not delivery:
        raise HTTPException(status_code=404, detail="Support handoff delivery not found")
    return {"delivery": delivery}


@router.post("/reports/support-handoff-deliveries/{delivery_id}/messages")
async def send_support_handoff_message(
    delivery_id: str,
    request: Request,
    body: SupportHandoffMessageRequest,
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_role("admin")),
):
    """Persist one controlled support/customer message outcome."""
    message = support_sla_service.send_support_message(
        delivery_id=delivery_id,
        template=body.template,
        destination=body.destination,
        trigger=body.trigger,
        actor=_operator_id(user),
        request_id=_request_id(request),
        settings=settings,
        customer_opted_out=body.customer_opted_out,
    )
    if not message:
        raise HTTPException(status_code=404, detail="Support handoff delivery not found")
    return {"message": message}


@router.post("/reports/audit-retention/status")
async def get_audit_retention_status(
    request: Request,
    body: AuditRetentionStatusRequest,
    user: dict = Depends(require_role("admin")),
):
    """Inspect metadata-only audit retention status for allowlisted scopes."""
    return report_audit_retention_service.build_status_response(
        references=[ref.model_dump(exclude_none=True) for ref in body.references],
        request_id=_request_id(request),
        limit=body.limit,
    )


@router.post("/reports/audit-retention/manifest")
async def create_audit_retention_manifest(
    request: Request,
    body: AuditRetentionManifestRequest,
    user: dict = Depends(require_role("admin")),
):
    """Generate a metadata-only sealed audit retention manifest."""
    try:
        return report_audit_retention_service.build_manifest(
            reason=body.reason,
            generated_by=_operator_id(user),
            request_id=_request_id(request),
            references=[ref.model_dump(exclude_none=True) for ref in body.references],
            retention_category=body.retention_category,
            retention_action=body.retention_action,
            target_limit=body.target_limit,
            audit_limit=body.audit_limit,
        )
    except report_audit_retention_service.AuditRetentionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/reports/immutable-evidence/status")
async def get_immutable_evidence_status(
    request: Request,
    body: AuditRetentionStatusRequest,
    user: dict = Depends(require_role("admin")),
):
    """Inspect immutable evidence and legal hold metadata status for allowlisted scopes."""
    return report_audit_retention_service.build_immutable_status_response(
        references=[ref.model_dump(exclude_none=True) for ref in body.references],
        request_id=_request_id(request),
        limit=body.limit,
    )


@router.post("/reports/immutable-evidence/persist")
async def persist_immutable_evidence_manifest(
    request: Request,
    body: ImmutableEvidencePersistRequest,
    user: dict = Depends(require_role("admin")),
):
    """Persist a metadata-only manifest reference when CDK-managed immutable storage is configured."""
    try:
        return report_audit_retention_service.persist_immutable_manifest(
            reason=body.reason,
            generated_by=_operator_id(user),
            request_id=_request_id(request),
            references=[ref.model_dump(exclude_none=True) for ref in body.references],
            retention_category=body.retention_category,
            target_limit=body.target_limit,
            audit_limit=body.audit_limit,
        )
    except report_audit_retention_service.ImmutableEvidenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/reports/retention-governance/status")
async def get_retention_governance_status(
    request: Request,
    body: RetentionGovernanceStatusRequest,
    user: dict = Depends(require_role("admin")),
):
    """Inspect metadata-only retention approval and legal-hold review status."""
    return report_audit_retention_service.build_governance_status_response(
        policy_version=body.policy_version,
        references=[ref.model_dump(exclude_none=True) for ref in body.references],
        request_id=_request_id(request),
        limit=body.limit,
    )


@router.post("/reports/retention-governance/approval")
async def record_retention_governance_approval(
    request: Request,
    body: RetentionApprovalMetadataRequest,
    user: dict = Depends(require_role("admin")),
):
    """Record metadata-only retention approval or refusal evidence."""
    try:
        return report_audit_retention_service.record_retention_approval_metadata(
            policy_version=body.policy_version,
            retention_mode=body.retention_mode,
            retention_days=body.retention_days,
            policy_owner=body.policy_owner,
            legal_compliance_approver=body.legal_compliance_approver,
            approval_state=body.approval_state,
            reason=body.reason,
            actor=_operator_id(user),
            request_id=_request_id(request),
            evidence_references=body.evidence_references,
            next_review_due_at=body.next_review_due_at,
        )
    except report_audit_retention_service.ImmutableEvidenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/reports/legal-holds/status")
async def get_legal_hold_status(
    request: Request,
    body: AuditRetentionStatusRequest,
    user: dict = Depends(require_role("admin")),
):
    """Inspect metadata-only legal hold state for allowlisted evidence scopes."""
    return report_audit_retention_service.build_legal_hold_status_response(
        references=[ref.model_dump(exclude_none=True) for ref in body.references],
        request_id=_request_id(request),
        limit=body.limit,
    )


@router.post("/reports/legal-holds")
async def apply_legal_hold_metadata(
    request: Request,
    body: LegalHoldMetadataRequest,
    user: dict = Depends(require_role("admin")),
):
    """Apply or release metadata-only legal hold state without deleting audit evidence."""
    try:
        return report_audit_retention_service.apply_legal_hold_metadata(
            references=[ref.model_dump(exclude_none=True) for ref in body.references],
            action=body.action,
            reason=body.reason,
            actor=_operator_id(user),
            request_id=_request_id(request),
            policy_id=body.policy_id,
            limit=10,
        )
    except report_audit_retention_service.ImmutableEvidenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/reports/legal-holds/review")
async def record_legal_hold_review_metadata(
    request: Request,
    body: LegalHoldReviewMetadataRequest,
    user: dict = Depends(require_role("admin")),
):
    """Record metadata-only legal-hold review evidence without deleting audit rows."""
    try:
        return report_audit_retention_service.record_legal_hold_review_metadata(
            references=[ref.model_dump(exclude_none=True) for ref in body.references],
            owner=body.owner,
            reviewer=body.reviewer,
            review_cadence=body.review_cadence,
            outcome=body.outcome,
            reason=body.reason,
            actor=_operator_id(user),
            request_id=_request_id(request),
            next_review_due_at=body.next_review_due_at,
            break_glass=body.break_glass,
            limit=10,
        )
    except report_audit_retention_service.ImmutableEvidenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


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
            audit_result = report_repo.list_report_audit_events(report["report_id"], limit=10)
            audit_events = audit_result.get("Items", [])

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
    items = [_recovery_job_response(item) for item in result.get("Items", [])]
    return RecoveryJobListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_recovery_job_page_token(result.get("LastEvaluatedKey")),
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
    items = [_recovery_job_target_response(item) for item in result.get("Items", [])]
    return RecoveryJobTargetsResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_recovery_job_page_token(result.get("LastEvaluatedKey")),
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
        email_status=result.email_status,
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


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/edit-drafts",
    response_model=ReportEditDraftResponse,
)
async def create_report_edit_draft(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    body: ReportEditDraftRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded metadata-only report edit draft."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        draft = report_edit_service.create_edit_draft(
            report,
            operator=_operator_id(user),
            reason=body.reason,
            proposed_fields=body.proposed_fields,
            correlation_id=_request_id(request),
        )
    except report_edit_service.ReportEditError as exc:
        raise _report_edit_http_error(exc) from exc
    return ReportEditDraftResponse(**draft)


@router.get(
    "/reports/{parent_id}/{student_id}/{week_start}/edit-drafts/{draft_id}",
    response_model=ReportEditDraftResponse,
)
async def get_report_edit_draft(
    parent_id: str,
    student_id: str,
    week_start: str,
    draft_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Read a metadata-only report edit draft."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        draft = report_edit_service.get_edit_draft(report, draft_id)
    except report_edit_service.ReportEditError as exc:
        raise _report_edit_http_error(exc) from exc
    return ReportEditDraftResponse(**draft)


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/edit-drafts/{draft_id}/apply",
    response_model=ReportEditApplyResponse,
)
async def apply_report_edit_draft(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    draft_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Apply one valid metadata-only report edit draft."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        result = report_edit_service.apply_edit_draft(
            report,
            draft_id=draft_id,
            operator=_operator_id(user),
            correlation_id=_request_id(request),
        )
    except report_edit_service.ReportEditError as exc:
        raise _report_edit_http_error(exc) from exc
    return ReportEditApplyResponse(
        operation="edit_report",
        operation_result="success",
        draft=ReportEditDraftResponse(**result["draft"]),
        report=result["report"],
    )


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-edit-previews",
    response_model=ReportArtifactEditPreviewResponse,
)
async def create_report_artifact_edit_preview(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    body: ReportArtifactEditPreviewRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded report artifact edit preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        preview = report_artifact_edit_service.create_artifact_edit_preview(
            report,
            operator=_operator_id(user),
            reason=body.reason,
            proposed_fields=body.proposed_fields,
            correlation_id=_request_id(request),
        )
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactEditPreviewResponse(**preview)


@router.get(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-edit-previews/{draft_id}",
    response_model=ReportArtifactEditPreviewResponse,
)
async def get_report_artifact_edit_preview(
    parent_id: str,
    student_id: str,
    week_start: str,
    draft_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Read a bounded report artifact edit preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        preview = report_artifact_edit_service.get_artifact_edit_preview(report, draft_id)
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactEditPreviewResponse(**preview)


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-edit-previews/{draft_id}/apply",
    response_model=ReportArtifactEditApplyResponse,
)
async def apply_report_artifact_edit_preview(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    draft_id: str,
    body: ReportArtifactEditApplyRequest,
    user: dict = Depends(require_role("admin")),
):
    """Apply one bounded report artifact edit preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        result = report_artifact_edit_service.apply_artifact_edit_preview(
            report,
            draft_id=draft_id,
            operator=_operator_id(user),
            reason=body.reason,
            correlation_id=_request_id(request),
        )
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactEditApplyResponse(
        operation="edit_report_artifact",
        operation_result="success",
        draft=ReportArtifactEditPreviewResponse(**result["draft"]),
        report=result["report"],
    )


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-rollback-previews",
    response_model=ReportArtifactRollbackPreviewResponse,
)
async def create_report_artifact_rollback_preview(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    body: ReportArtifactRollbackPreviewRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded report artifact rollback preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        preview = report_artifact_edit_service.create_artifact_rollback_preview(
            report,
            operator=_operator_id(user),
            reason=body.reason,
            correlation_id=_request_id(request),
        )
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactRollbackPreviewResponse(**preview)


@router.get(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-rollback-previews/{preview_id}",
    response_model=ReportArtifactRollbackPreviewResponse,
)
async def get_report_artifact_rollback_preview(
    parent_id: str,
    student_id: str,
    week_start: str,
    preview_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Read a bounded report artifact rollback preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        preview = report_artifact_edit_service.get_artifact_rollback_preview(report, preview_id)
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactRollbackPreviewResponse(**preview)


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-rollback-previews/{preview_id}/apply",
    response_model=ReportArtifactRollbackApplyResponse,
)
async def apply_report_artifact_rollback_preview(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    preview_id: str,
    body: ReportArtifactRollbackApplyRequest,
    user: dict = Depends(require_role("admin")),
):
    """Apply one bounded report artifact rollback preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        result = report_artifact_edit_service.apply_artifact_rollback_preview(
            report,
            preview_id=preview_id,
            operator=_operator_id(user),
            reason=body.reason,
            correlation_id=_request_id(request),
        )
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactRollbackApplyResponse(
        operation="rollback_report_artifact",
        operation_result="success",
        preview=ReportArtifactRollbackPreviewResponse(**result["preview"]),
        report=result["report"],
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

    result = report_repo.list_report_audit_events(report["report_id"], limit=limit, last_key=last_key)
    items = [_report_audit_event_response(item) for item in result.get("Items", [])]
    return ReportAuditListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_audit_page_token(result.get("LastEvaluatedKey")),
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
    items = [_report_audit_event_response(item) for item in result.get("Items", [])]
    return ReportAuditListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_audit_page_token(result.get("LastEvaluatedKey")),
        scope="recovery_job",
    )


def _get_report_or_404(parent_id: str, student_id: str, week_start: str) -> dict:
    report = report_repo.get_report_for_child_by_week(parent_id, student_id, week_start)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _export_recovery_job_evidence(
    *,
    job_id: str,
    request_id: str | None,
    include_targets: bool,
    include_job_audit: bool,
    target_limit: int,
    audit_limit: int,
    next_target_token: str | None,
    next_audit_token: str | None,
) -> dict[str, Any]:
    job = report_repo.get_recovery_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Recovery job not found")

    targets: list[dict] = []
    target_next_token = None
    if include_targets:
        target_last_key = report_repo.decode_recovery_job_page_token(next_target_token)
        target_result = report_repo.list_recovery_job_targets(
            job_id,
            limit=target_limit,
            last_key=target_last_key,
        )
        targets = target_result.get("Items", [])
        target_next_token = report_repo.encode_recovery_job_page_token(target_result.get("LastEvaluatedKey"))

    job_audit: list[dict] = []
    audit_next_token = None
    if include_job_audit:
        audit_last_key = report_repo.decode_audit_page_token(next_audit_token)
        audit_result = report_repo.list_recovery_job_audit_events(
            job_id,
            limit=audit_limit,
            last_key=audit_last_key,
        )
        job_audit = audit_result.get("Items", [])
        audit_next_token = report_repo.encode_audit_page_token(audit_result.get("LastEvaluatedKey"))

    return report_recovery_evidence_service.build_export_response(
        scope="recovery_job",
        request_id=request_id,
        filters={
            "job_id": job_id,
            "include_targets": include_targets,
            "include_job_audit": include_job_audit,
            "target_limit": target_limit,
            "audit_limit": audit_limit,
        },
        jobs=[job],
        targets=targets,
        job_audit=job_audit,
        next_tokens={
            "targets": target_next_token,
            "job_audit": audit_next_token,
        },
    )


def _export_recovery_job_support_package(
    *,
    job_id: str,
    request_id: str | None,
    include_targets: bool,
    include_job_audit: bool,
    include_report_audit: bool,
    target_limit: int,
    audit_limit: int,
    next_target_token: str | None,
    next_audit_token: str | None,
    operator_note: str | None,
) -> dict[str, Any]:
    job = report_repo.get_recovery_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Recovery job not found")
    source_job = None
    source_job_id = job.get("source_job_id")
    if source_job_id:
        source_job = report_repo.get_recovery_job(str(source_job_id))

    targets: list[dict] = []
    target_next_token = None
    if include_targets or include_report_audit:
        target_last_key = report_repo.decode_recovery_job_page_token(next_target_token)
        target_result = report_repo.list_recovery_job_targets(
            job_id,
            limit=target_limit,
            last_key=target_last_key,
        )
        targets = target_result.get("Items", [])
        target_next_token = report_repo.encode_recovery_job_page_token(target_result.get("LastEvaluatedKey"))

    job_audit: list[dict] = []
    audit_next_token = None
    if include_job_audit:
        audit_last_key = report_repo.decode_audit_page_token(next_audit_token)
        audit_result = report_repo.list_recovery_job_audit_events(
            job_id,
            limit=audit_limit,
            last_key=audit_last_key,
        )
        job_audit = audit_result.get("Items", [])
        audit_next_token = report_repo.encode_audit_page_token(audit_result.get("LastEvaluatedKey"))

    report_audit: list[dict] = []
    if include_report_audit:
        remaining = audit_limit
        for target in targets:
            if remaining <= 0:
                break
            report_id = target.get("report_id")
            if not report_id:
                continue
            audit_result = report_repo.list_report_audit_events(str(report_id), limit=remaining)
            events = audit_result.get("Items", [])
            report_audit.extend(events)
            remaining -= len(events)

    return report_recovery_evidence_service.build_support_package_response(
        request_id=request_id,
        job=job,
        source_job=source_job,
        targets=targets if include_targets else [],
        job_audit=job_audit,
        report_audit=report_audit,
        operator_note=operator_note,
        next_tokens={
            "targets": target_next_token if include_targets else None,
            "job_audit": audit_next_token,
            "report_audit": None,
        },
    )


def _support_handoff_recovery_section(
    *,
    job_id: str,
    request_id: str | None,
    include_targets: bool,
    include_job_audit: bool,
    include_report_audit: bool,
    target_limit: int,
    audit_limit: int,
) -> dict[str, Any]:
    try:
        data = _export_recovery_job_support_package(
            job_id=job_id,
            request_id=request_id,
            include_targets=include_targets,
            include_job_audit=include_job_audit,
            include_report_audit=include_report_audit,
            target_limit=target_limit,
            audit_limit=audit_limit,
            next_target_token=None,
            next_audit_token=None,
            operator_note=None,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            return {"job_id": job_id, "missing": True}
        raise
    return {"job_id": job_id, "data": data}


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
            audit_result = report_repo.list_report_audit_events(report["report_id"], limit=10)
            audit_events = audit_result.get("Items", [])
    return release_evidence_service.build_fixture_inventory_response(
        fixture_name=fixture.fixture_name,
        report=report,
        audit_events=audit_events,
        expected_artifact_version_id=fixture.expected_artifact_version,
    )


def _export_recent_recovery_jobs(
    *,
    request_id: str | None,
    status: str | None,
    limit: int,
    next_token: str | None,
) -> dict[str, Any]:
    last_key = report_repo.decode_recovery_job_page_token(next_token)
    result = report_repo.list_recovery_jobs(limit=limit, last_key=last_key)
    jobs = result.get("Items", [])
    if status:
        jobs = [job for job in jobs if job.get("status") == status]
    return report_recovery_evidence_service.build_export_response(
        scope="recent_recovery_jobs",
        request_id=request_id,
        filters={
            "status": status,
            "limit": limit,
        },
        jobs=jobs,
        next_tokens={
            "jobs": report_repo.encode_recovery_job_page_token(result.get("LastEvaluatedKey")),
        },
    )


def _request_id(request: Request) -> str | None:
    for header in ("x-request-id", "x-amzn-requestid", "x-amzn-trace-id", "x-correlation-id"):
        value = request.headers.get(header)
        if value:
            return report_audit_retention_service.sanitize_request_id(value)
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


def _report_edit_http_error(exc: report_edit_service.ReportEditError) -> HTTPException:
    detail = report_recovery_service.redact_private_artifact_text(exc.detail) or "Report edit operation failed"
    return HTTPException(status_code=exc.status_code, detail=detail)


def _report_artifact_edit_http_error(
    exc: report_artifact_edit_service.ReportArtifactEditError,
) -> HTTPException:
    detail = (
        report_recovery_service.redact_private_artifact_text(exc.detail)
        or "Report artifact edit operation failed"
    )
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
