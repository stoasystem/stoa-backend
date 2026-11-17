"""Admin curriculum authoring: drafts, review, publish, migration and analytics."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from stoa.deps import legacy_user
from stoa.security.admin_authorization import (
    AdminTargetProvider,
    admin_operation,
    admin_target_provider,
)
from stoa.security.identity import Actor
from stoa.models.practice import DEFAULT_CHALLENGE_TYPE
from stoa.services import (
    answer_judging,
    curriculum_analytics_service,
    curriculum_migration_service,
    curriculum_ops_service,
)


router = APIRouter()


CURRICULUM_DRAFT_TARGET = AdminTargetProvider(
    "scalar", "body", ("publicLessonId",), ("public_lesson_id",),
    reference_only=("exercises", "description"),
)


CURRICULUM_VERSION_TARGET = AdminTargetProvider(
    "scalar", "body", ("versionId",), ("version_id",),
    reference_only=("reason", "expectedPublishedVersionId"),
)


_ExerciseOption = Annotated[str, Field(min_length=1, max_length=500)]


_AcceptedAnswer = Annotated[
    str, Field(min_length=1, max_length=answer_judging.MAX_ACCEPTED_ANSWER_LENGTH)
]


class CurriculumExerciseTranslation(BaseModel):
    """One exercise in another language: what a reader in that locale sees and answers."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    prompt: str = Field(..., min_length=1, max_length=2000)
    options: list[_ExerciseOption] = Field(default_factory=list, max_length=10)
    correct_answer: str | None = Field(default=None, alias="correctAnswer", max_length=2000)
    accepted_answers: list[_AcceptedAnswer] = Field(
        default_factory=list,
        alias="acceptedAnswers",
        max_length=answer_judging.MAX_ACCEPTED_ANSWERS,
    )
    explanation: str | None = Field(default=None, max_length=2000)
    figure: str | None = Field(default=None, max_length=32_000)
    option_figures: list[str | None] = Field(default_factory=list, alias="optionFigures", max_length=10)


class CurriculumErrorCause(BaseModel):
    """Why picking one wrong option is wrong (错因, #452): its category and misconception.

    The category is checked by the validation report (`error_causes.issues`),
    so an unknown one is reported with the draft's other problems.
    """

    model_config = ConfigDict(extra="forbid")

    # structural | deviation | application | metacognitive
    category: str = Field(..., min_length=1, max_length=40)
    # One sentence per locale: de, en, fr and it.
    misconception: dict[str, str] = Field(default_factory=dict, max_length=4)


class CurriculumExerciseDraftRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    exercise_id: str | None = Field(default=None, alias="exerciseId", max_length=200)
    prompt: str = Field(..., min_length=1, max_length=2000)
    type: str = Field(default=DEFAULT_CHALLENGE_TYPE, min_length=1, max_length=50)
    difficulty: str = Field(default="practice", min_length=1, max_length=80)
    order: int | None = Field(default=None, ge=1, le=200)
    answer_key: str | None = Field(default=None, alias="answerKey", max_length=2000)
    accepted_answers: list[_AcceptedAnswer] = Field(
        default_factory=list,
        alias="acceptedAnswers",
        max_length=answer_judging.MAX_ACCEPTED_ANSWERS,
    )
    explanation: str | None = Field(default=None, max_length=2000)
    options: list[_ExerciseOption] = Field(default_factory=list, max_length=10)
    translations: dict[Literal["de", "en", "fr", "it"], CurriculumExerciseTranslation] = Field(
        default_factory=dict
    )
    correct_feedback: str | None = Field(default=None, alias="correctFeedback", max_length=500)
    incorrect_feedback: str | None = Field(default=None, alias="incorrectFeedback", max_length=500)
    knowledge_point: str | None = Field(default=None, alias="knowledgePoint", max_length=200)
    figure: str | None = Field(default=None, max_length=32_000)
    option_figures: list[str | None] = Field(default_factory=list, alias="optionFigures", max_length=10)
    # One entry per option, `null` for the right option and for an untagged one (#452).
    option_error_causes: list[CurriculumErrorCause | None] = Field(
        default_factory=list, alias="optionErrorCauses", max_length=10
    )
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
    order: int | None = Field(default=None, ge=1, le=1000)
    language: str | None = Field(default=None, max_length=30)
    extension: bool = False
    requires_points: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, alias="requiresPoints", max_length=100
    )
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
    # What is wrong, as a code the console translates with `params` (#112);
    # `message` is its English sentence.
    code: str | None = None
    params: dict[str, str] = Field(default_factory=dict)
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


class CurriculumLessonVersionResponse(CurriculumVersionResponse):
    """A version next to its lesson's live version, as the worklist and preview give it.

    `publishedVersionId` is the version the lesson's pointer names, or null when the
    lesson has never been published; send it as `expectedPublishedVersionId`.
    `state` is read against it: `published` for the live version only, `superseded`
    for one a later publish replaced (#111)."""

    publishedVersionId: str | None = None


class CurriculumWorklistResponse(BaseModel):
    items: list[CurriculumLessonVersionResponse]
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


@router.get("/curriculum/worklist", response_model=CurriculumWorklistResponse)
async def list_curriculum_authoring_worklist(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    actor: Actor = Depends(admin_operation),
):
    """List internal curriculum authoring items awaiting operational action."""
    return curriculum_ops_service.list_worklist(status=status, limit=limit)


@router.get("/curriculum/analytics/content-quality", response_model=CurriculumQualityResponse)
async def get_curriculum_content_quality(
    content_type: str | None = Query(default=None, alias="contentType"),
    subject_id: str | None = Query(default=None, alias="subjectId"),
    topic_id: str | None = Query(default=None, alias="topicId"),
    limit: int = Query(default=100, ge=1, le=200),
    actor: Actor = Depends(admin_operation),
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
    actor: Actor = Depends(admin_operation),
):
    """Return local warehouse analytics readiness without requiring live BI infrastructure."""
    return curriculum_analytics_service.warehouse_readiness()


@router.get("/curriculum/analytics/warehouse-export", response_model=CurriculumWarehouseExportResponse)
async def get_curriculum_warehouse_export(
    content_type: str | None = Query(default=None, alias="contentType"),
    subject_id: str | None = Query(default=None, alias="subjectId"),
    topic_id: str | None = Query(default=None, alias="topicId"),
    limit: int = Query(default=100, ge=1, le=250),
    actor: Actor = Depends(admin_operation),
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
    actor: Actor = Depends(admin_operation),
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
    actor: Actor = Depends(admin_operation),
):
    """Create an internal lesson-plus-exercises authoring draft."""
    return curriculum_ops_service.create_lesson_draft(body.model_dump(by_alias=False), legacy_user(actor))


@router.post(
    "/curriculum/migrations/dry-run",
    response_model=CurriculumMigrationDryRunResponse,
)
async def dry_run_curriculum_migration(
    manifest: dict[str, Any] = Body(...),
    actor: Actor = Depends(admin_operation),
):
    """Validate a curriculum migration manifest without mutating content state."""
    return curriculum_migration_service.dry_run(manifest, legacy_user(actor))


@router.post(
    "/curriculum/migrations/{migration_id}/apply",
    response_model=CurriculumMigrationEvidenceResponse,
)
async def apply_curriculum_migration(
    migration_id: str,
    body: CurriculumMigrationApplyRequest,
    actor: Actor = Depends(admin_operation),
):
    """Apply a confirmed curriculum migration manifest and persist evidence."""
    return curriculum_migration_service.apply_migration(
        migration_id,
        body.manifest,
        body.confirmation_token,
        legacy_user(actor),
    )


@router.get(
    "/curriculum/migrations/{migration_id}",
    response_model=CurriculumMigrationEvidenceResponse,
)
async def read_curriculum_migration(
    migration_id: str,
    actor: Actor = Depends(admin_operation),
):
    """Read evidence for an applied curriculum migration."""
    return curriculum_migration_service.get_migration(migration_id, legacy_user(actor))


@router.get(
    "/curriculum/lessons/{public_lesson_id}/preview",
    response_model=CurriculumLessonVersionResponse,
)
async def preview_curriculum_lesson_version(
    public_lesson_id: str,
    version_id: str = Query(..., alias="versionId"),
    actor: Actor = Depends(admin_operation),
):
    """Preview an unpublished curriculum version without changing student reads."""
    return curriculum_ops_service.preview_lesson(public_lesson_id, version_id)


@router.get("/curriculum/lessons/{public_lesson_id}/diff", response_model=CurriculumDiffResponse)
async def diff_curriculum_lesson_versions(
    public_lesson_id: str,
    from_version_id: str = Query(..., alias="fromVersionId"),
    to_version_id: str = Query(..., alias="toVersionId"),
    actor: Actor = Depends(admin_operation),
):
    """Return a bounded structural diff between two curriculum versions."""
    return curriculum_ops_service.diff_lesson_versions(
        public_lesson_id,
        from_version_id,
        to_version_id,
        legacy_user(actor),
    )


@router.get("/curriculum/lessons/{public_lesson_id}/audit", response_model=CurriculumAuditResponse)
async def read_curriculum_lesson_audit(
    public_lesson_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    actor: Actor = Depends(admin_operation),
):
    """Read bounded lifecycle audit events for one curriculum lesson."""
    return curriculum_ops_service.audit_lesson(public_lesson_id, legacy_user(actor), limit=limit)


@router.patch(
    "/curriculum/lessons/{public_lesson_id}/drafts/{version_id}",
    response_model=CurriculumVersionResponse,
)
async def patch_curriculum_lesson_draft(
    public_lesson_id: str,
    version_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    actor: Actor = Depends(admin_operation),
):
    """Patch a draft curriculum lesson without changing published student reads."""
    return curriculum_ops_service.patch_lesson_draft(public_lesson_id, version_id, body, legacy_user(actor))


@router.post(
    "/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/validation-preview",
    response_model=CurriculumValidationPreviewResponse,
)
async def preview_curriculum_lesson_validation(
    public_lesson_id: str,
    version_id: str,
    actor: Actor = Depends(admin_operation),
):
    """Validate draft publish readiness without mutating the curriculum version."""
    return curriculum_ops_service.validation_preview(public_lesson_id, version_id, legacy_user(actor))


@router.post(
    "/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/submit-review",
    response_model=CurriculumVersionResponse,
)
async def submit_curriculum_lesson_review(
    public_lesson_id: str,
    version_id: str,
    actor: Actor = Depends(admin_operation),
):
    """Move a draft curriculum version into QA review."""
    return curriculum_ops_service.submit_review(public_lesson_id, version_id, legacy_user(actor))


@router.post(
    "/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/approve",
    response_model=CurriculumVersionResponse,
)
async def approve_curriculum_lesson_version(
    public_lesson_id: str,
    version_id: str,
    actor: Actor = Depends(admin_operation),
):
    """Approve a reviewed curriculum version for admin publish."""
    return curriculum_ops_service.approve(public_lesson_id, version_id, legacy_user(actor))


@router.post(
    "/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/request-changes",
    response_model=CurriculumVersionResponse,
)
async def request_curriculum_lesson_changes(
    public_lesson_id: str,
    version_id: str,
    body: CurriculumReviewNoteRequest,
    actor: Actor = Depends(admin_operation),
):
    """Return a curriculum version to authoring with review notes."""
    return curriculum_ops_service.request_changes(public_lesson_id, version_id, legacy_user(actor), body.reason)


@router.post("/curriculum/lessons/{public_lesson_id}/publish")
@admin_target_provider(CURRICULUM_VERSION_TARGET)
async def publish_curriculum_lesson_version(
    public_lesson_id: str,
    body: CurriculumPublishRequest,
    actor: Actor = Depends(admin_operation),
):
    """Publish an approved curriculum version through a conditional manifest update."""
    return curriculum_ops_service.publish(
        public_lesson_id,
        body.version_id,
        legacy_user(actor),
        expected_published_version_id=body.expected_published_version_id,
        reason=body.reason,
    )


@router.post("/curriculum/lessons/{public_lesson_id}/rollback")
@admin_target_provider(CURRICULUM_VERSION_TARGET)
async def rollback_curriculum_lesson_version(
    public_lesson_id: str,
    body: CurriculumPublishRequest,
    actor: Actor = Depends(admin_operation),
):
    """Rollback the published curriculum pointer to a previous safe version."""
    return curriculum_ops_service.rollback(
        public_lesson_id,
        body.version_id,
        legacy_user(actor),
        expected_published_version_id=body.expected_published_version_id,
        reason=body.reason or "rollback requested",
    )


@router.post("/curriculum/lessons/{public_lesson_id}/archive")
@admin_target_provider(CURRICULUM_VERSION_TARGET)
async def archive_curriculum_lesson_version(
    public_lesson_id: str,
    body: CurriculumPublishRequest,
    actor: Actor = Depends(admin_operation),
):
    """Archive a curriculum version when no active assignments block it."""
    return curriculum_ops_service.archive(
        public_lesson_id,
        body.version_id,
        legacy_user(actor),
        reason=body.reason or "archive requested",
    )
