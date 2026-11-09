"""Adaptive learning memory and reviewed assignment routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, model_validator

from stoa.db.repositories import user_repo
from stoa.deps import get_actor
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizedResource,
    ResourceRef,
    ResourceType,
)
from stoa.security.declared_authorization import (
    ASSIGNMENT,
    SELF,
    AuthorizationContext,
    authorize_loaded,
    authorized,
    get_authorization_context,
    loaded_declaration,
    path,
)
from stoa.security.identity import Actor, CanonicalRole
from stoa.services import adaptive_learning_service
from stoa.services.adaptive_learning_service import actor_projection

router = APIRouter()


class AssignmentCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    student_id: str = Field(..., alias="studentId", min_length=1)
    source_type: str = Field(..., alias="sourceType", min_length=1)
    source_id: str = Field(..., alias="sourceId", min_length=1)
    title: str | None = Field(default=None, max_length=200)
    status: str = "assigned"
    due_at: str | None = Field(default=None, alias="dueAt")
    note: str | None = Field(default=None, max_length=500)


class AssignmentTransitionRequest(BaseModel):
    student_answer: str | None = Field(default=None, alias="studentAnswer", max_length=4000)
    correct: bool | None = None
    note: str | None = Field(default=None, max_length=500)


class AssignmentAutomationPolicyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    policy_id: str | None = Field(default=None, alias="policyId", max_length=120)
    name: str | None = Field(default=None, max_length=200)
    status: str = "active"
    autonomy_level: str = Field(default="suggest_only", alias="autonomyLevel")
    student_ids: list[str] = Field(default_factory=list, alias="studentIds")
    subject_ids: list[str] = Field(default_factory=list, alias="subjectIds")
    topic_ids: list[str] = Field(default_factory=list, alias="topicIds")
    source_types: list[str] = Field(default_factory=list, alias="sourceTypes")
    max_assignments_per_student: int = Field(default=3, alias="maxAssignmentsPerStudent", ge=1, le=20)
    confidence_threshold: str = Field(default="medium", alias="confidenceThreshold")
    freshness_days: int = Field(default=14, alias="freshnessDays", ge=1, le=180)
    due_in_days: int = Field(default=7, alias="dueInDays", ge=1, le=365)
    delivery_mode: str = Field(default="recommended", alias="deliveryMode")
    paused_reason: str | None = Field(default=None, alias="pausedReason", max_length=500)


class AssignmentAutomationPreviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    policy: AssignmentAutomationPolicyRequest = Field(default_factory=AssignmentAutomationPolicyRequest)
    subject: str | None = None


class AssignmentAutomationCandidateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    candidate_id: str = Field(..., alias="candidateId", min_length=1)
    type: str | None = None
    source_type: str = Field(..., alias="sourceType", min_length=1)
    source_id: str = Field(..., alias="sourceId", min_length=1)
    title: str | None = Field(default=None, max_length=200)
    subject: str | None = None
    topic_id: str | None = Field(default=None, alias="topicId")
    topic_ids: list[str] = Field(default_factory=list, alias="topicIds")
    confidence: str = "medium"
    rationale: str | None = None
    expected_impact: str | None = Field(default=None, alias="expectedImpact")
    review_status: str | None = Field(default=None, alias="reviewStatus")
    proposed_status: str | None = Field(default=None, alias="proposedStatus")
    due_at: str | None = Field(default=None, alias="dueAt")
    source_signals: dict[str, Any] = Field(default_factory=dict, alias="sourceSignals")
    review_required: bool = Field(default=True, alias="reviewRequired")
    autonomous_decision: bool = Field(default=False, alias="autonomousDecision")
    approved: bool = True


class AssignmentAutomationExecuteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    batch_id: str = Field(..., alias="batchId", min_length=1, max_length=160)
    approved: bool = Field(...)
    policy: AssignmentAutomationPolicyRequest = Field(default_factory=AssignmentAutomationPolicyRequest)
    candidates: list[AssignmentAutomationCandidateRequest] = Field(default_factory=list)
    subject: str | None = None


# The memory summary as `adaptive_learning_service._memory_response` builds it.
# Closed at the top level so a key added there fails the model test rather than
# vanishing from the response. List items declare the fields the service always
# writes and the frontend reads, and keep any others as they are: a parent's
# weak topics leave out the evidence, and snapshots differ by role, so the
# frontend treats snapshots and strength topics as opaque.
class _MemoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _MemoryItem(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class MemorySubject(_MemoryItem):
    id: str
    label: str
    rollout_state: str = Field(alias="rolloutState")


class MemorySubjectActivity(_MemoryItem):
    subject: str
    label: str
    rollout_state: str = Field(alias="rolloutState")
    question_count: int = Field(alias="questionCount")
    ai_resolved_count: int = Field(alias="aiResolvedCount")
    teacher_escalation_count: int = Field(alias="teacherEscalationCount")
    feedback_average: float | None = Field(alias="feedbackAverage")


class MemoryWeakTopic(_MemoryItem):
    subject: str
    topic_id: str = Field(alias="topicId")
    label: str
    count: int
    latest_evidence_at: str | None = Field(alias="latestEvidenceAt")
    # Absent, not null, in a parent's view; the routes leave unset fields out.
    evidence_question_ids: list[str] | None = Field(default=None, alias="evidenceQuestionIds")


class MemoryRecommendationFreshness(_MemoryItem):
    status: str
    last_evidence_at: str | None = Field(alias="lastEvidenceAt")
    source: str


class MemoryRecommendation(_MemoryItem):
    candidate_id: str = Field(alias="candidateId")
    type: str
    source_type: str = Field(alias="sourceType")
    source_id: str = Field(alias="sourceId")
    subject: str
    topic_id: str = Field(alias="topicId")
    label: str
    rationale: str
    confidence: Literal["high", "medium", "low"]
    freshness: MemoryRecommendationFreshness
    source_signals: dict[str, Any] = Field(alias="sourceSignals")
    review_required: bool = Field(alias="reviewRequired")
    autonomous_decision: bool = Field(alias="autonomousDecision")
    review_flags: list[str] = Field(alias="reviewFlags")


class MemoryLocale(_MemoryModel):
    effective_locale: str = Field(alias="effectiveLocale")
    content_language: str = Field(alias="contentLanguage")
    supported_locales: list[str] = Field(alias="supportedLocales")
    canonical_values_stable: bool = Field(alias="canonicalValuesStable")


class MemorySequencingSummary(_MemoryModel):
    recommended_count: int = Field(alias="recommendedCount")
    top_candidate_type: str | None = Field(alias="topCandidateType")
    top_topic_id: str | None = Field(alias="topTopicId")
    top_confidence: str | None = Field(alias="topConfidence")
    active_assignments: int = Field(alias="activeAssignments")
    completed_assignments: int = Field(alias="completedAssignments")
    skipped_assignments: int = Field(alias="skippedAssignments")
    archived_assignments: int = Field(alias="archivedAssignments")
    explanation: str


class MemoryFreshness(_MemoryModel):
    status: str
    stale_count: int = Field(alias="staleCount")


class MemorySummaryResponse(_MemoryModel):
    student_id: str = Field(alias="studentId")
    role_view: str = Field(alias="roleView")
    locale: MemoryLocale
    subjects: list[MemorySubject]
    subject_activity: list[MemorySubjectActivity] = Field(alias="subjectActivity")
    weak_topics: list[MemoryWeakTopic] = Field(alias="weakTopics")
    strength_topics: list[dict[str, Any]] = Field(alias="strengthTopics")
    memory_snapshots: list[dict[str, Any]] = Field(alias="memorySnapshots")
    recommendations: list[MemoryRecommendation]
    sequencing_summary: MemorySequencingSummary = Field(alias="sequencingSummary")
    freshness: MemoryFreshness
    updated_at: str = Field(alias="updatedAt")

    @model_validator(mode="before")
    @classmethod
    def _as_sent_without_a_model(cls, data: Any) -> Any:
        # Stored snapshots come back from DynamoDB with Decimal numbers. Before
        # this model, FastAPI's encoder sent them as JSON numbers; Pydantic would
        # send a Decimal inside an open dict as a string. Encode first, as then.
        return jsonable_encoder(data) if isinstance(data, dict) else data


_ADAPTIVE_READ = {
    CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE,
    CanonicalRole.PARENT: AuthorizationPurpose.PARENT_OVERSIGHT,
    CanonicalRole.TEACHER: AuthorizationPurpose.LEARNING_ASSIGNMENT,
    CanonicalRole.ADMIN: AuthorizationPurpose.LEARNING_ASSIGNMENT,
}
_ADAPTIVE_REFRESH = {
    CanonicalRole.TEACHER: AuthorizationPurpose.LEARNING_ASSIGNMENT,
    CanonicalRole.ADMIN: AuthorizationPurpose.LEARNING_ASSIGNMENT,
}
_AUTOMATION_PREVIEW = {
    CanonicalRole.TEACHER: AuthorizationPurpose.ASSIGNMENT_AUTOMATION_PREVIEW,
    CanonicalRole.ADMIN: AuthorizationPurpose.ASSIGNMENT_AUTOMATION_PREVIEW,
}
_AUTOMATION_EXECUTE = {
    CanonicalRole.TEACHER: AuthorizationPurpose.ASSIGNMENT_AUTOMATION_EXECUTE,
    CanonicalRole.ADMIN: AuthorizationPurpose.ASSIGNMENT_AUTOMATION_EXECUTE,
}
_ASSIGNMENT_READ = _ADAPTIVE_READ
_ASSIGNMENT_STUDENT_UPDATE = {
    CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE,
}
_ASSIGNMENT_OPERATOR_UPDATE = {
    CanonicalRole.TEACHER: AuthorizationPurpose.LEARNING_ASSIGNMENT,
    CanonicalRole.ADMIN: AuthorizationPurpose.LEARNING_ASSIGNMENT,
}

_PROFILE = ResourceType.ADAPTIVE_PROFILE
_STUDENT_ID = path("student_id")
_my_adaptive_read = authorized(
    _PROFILE,
    AuthorizationAction.READ,
    SELF,
    {CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE},
)
_adaptive_read = authorized(_PROFILE, AuthorizationAction.READ, _STUDENT_ID, _ADAPTIVE_READ)
_adaptive_refresh = authorized(
    _PROFILE, AuthorizationAction.UPDATE, _STUDENT_ID, _ADAPTIVE_REFRESH
)
_automation_preview = authorized(
    _PROFILE, AuthorizationAction.READ, _STUDENT_ID, _AUTOMATION_PREVIEW
)
_automation_execute = authorized(
    _PROFILE, AuthorizationAction.CREATE, _STUDENT_ID, _AUTOMATION_EXECUTE
)
_parent_progress = authorized(
    _PROFILE,
    AuthorizationAction.READ,
    _STUDENT_ID,
    {CanonicalRole.PARENT: AuthorizationPurpose.PARENT_OVERSIGHT},
)

_ASSIGNMENT_ID = path("assignment_id")
_assignment_read = authorized(
    _PROFILE, AuthorizationAction.READ, _ASSIGNMENT_ID, _ASSIGNMENT_READ, kind=ASSIGNMENT
)
_assignment_student_update = authorized(
    _PROFILE,
    AuthorizationAction.UPDATE,
    _ASSIGNMENT_ID,
    _ASSIGNMENT_STUDENT_UPDATE,
    kind=ASSIGNMENT,
)
_assignment_operator_update = authorized(
    _PROFILE,
    AuthorizationAction.UPDATE,
    _ASSIGNMENT_ID,
    _ASSIGNMENT_OPERATOR_UPDATE,
    kind=ASSIGNMENT,
)


@loaded_declaration(_PROFILE, AuthorizationAction.ASSIGN, _ASSIGNMENT_OPERATOR_UPDATE)
async def _authorized_assignment_create(
    body: AssignmentCreateRequest,
    actor: Actor = Depends(get_actor),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> AuthorizedResource:
    """The student an assignment is for: named in the body, so load, then decide."""
    return await authorize_loaded(
        actor,
        ResourceRef(_PROFILE, body.student_id, body.student_id),
        user_repo.get_user(body.student_id),
        AuthorizationAction.ASSIGN,
        _ASSIGNMENT_OPERATOR_UPDATE,
        context,
    )


@router.get(
    "/students/me/memory",
    response_model=MemorySummaryResponse,
    response_model_exclude_unset=True,
)
async def get_my_memory(
    subject: str | None = Query(default=None),
    actor: Actor = Depends(_my_adaptive_read),
):
    """Student-facing adaptive memory and next-practice recommendations."""
    return adaptive_learning_service.get_memory_summary(
        student_id=actor.user_id,
        user=actor_projection(actor),
        subject=subject,
    )


@router.get("/students/me/assignments")
async def list_my_assignments(
    status: str | None = Query(default=None),
    actor: Actor = Depends(_my_adaptive_read),
):
    """Student-facing reviewed assignments."""
    return adaptive_learning_service.list_assignments(
        student_id=actor.user_id,
        user=actor_projection(actor),
        status=status,
    )


@router.get(
    "/students/{student_id}/memory",
    response_model=MemorySummaryResponse,
    response_model_exclude_unset=True,
)
async def get_student_memory(
    student_id: str,
    subject: str | None = Query(default=None),
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_adaptive_read),
):
    """Role-scoped memory summary for student, parent, teacher, or admin."""
    return adaptive_learning_service.get_memory_summary(
        student_id=authorized_student.ref.student_id,
        user=actor_projection(actor),
        subject=subject,
    )


@router.post(
    "/students/{student_id}/memory/refresh",
    response_model=MemorySummaryResponse,
    response_model_exclude_unset=True,
)
async def refresh_student_memory(
    student_id: str,
    subject: str | None = Query(default=None),
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_adaptive_refresh),
):
    """Persist a durable memory snapshot from current learning evidence."""
    return adaptive_learning_service.get_memory_summary(
        student_id=authorized_student.ref.student_id,
        user=actor_projection(actor),
        subject=subject,
        persist=True,
    )


@router.get("/students/{student_id}/recommendations")
async def get_student_recommendations(
    student_id: str,
    subject: str | None = Query(default=None),
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_adaptive_read),
):
    """Next-practice recommendations without autonomous assignment claims."""
    summary = adaptive_learning_service.get_memory_summary(
        student_id=authorized_student.ref.student_id,
        user=actor_projection(actor),
        subject=subject,
    )
    return {
        "studentId": authorized_student.ref.student_id,
        "items": summary["recommendations"],
        "sequencingSummary": summary["sequencingSummary"],
        "reviewRequired": True,
        "autonomousDecision": False,
        "locale": adaptive_learning_service.locale_contract(actor_projection(actor)),
    }


@router.get("/students/{student_id}/assignments")
async def list_student_assignments(
    student_id: str,
    status: str | None = Query(default=None),
    include_archived: bool = Query(default=False, alias="includeArchived"),
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_adaptive_read),
):
    """Role-scoped assignment list for teacher/admin review and parent progress views."""
    return adaptive_learning_service.list_assignments(
        student_id=authorized_student.ref.student_id,
        user=actor_projection(actor),
        status=status,
        include_archived=include_archived,
    )


@router.post("/students/{student_id}/assignment-automation/batches/preview")
async def preview_assignment_automation_batch(
    student_id: str,
    body: AssignmentAutomationPreviewRequest | None = None,
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_automation_preview),
):
    """Preview policy-bounded assignment automation candidates without creating assignments."""
    body = body or AssignmentAutomationPreviewRequest()
    return adaptive_learning_service.preview_assignment_automation_batch(
        student_id=authorized_student.ref.student_id,
        policy=body.policy.model_dump(by_alias=True, exclude_unset=True),
        subject=body.subject,
        user=actor_projection(actor),
    )


@router.post("/students/{student_id}/assignment-automation/batches/execute")
async def execute_assignment_automation_batch(
    student_id: str,
    body: AssignmentAutomationExecuteRequest,
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_automation_execute),
):
    """Create reviewed assignments from an approved automation batch."""
    return adaptive_learning_service.execute_assignment_automation_batch(
        student_id=authorized_student.ref.student_id,
        batch_id=body.batch_id,
        approved=body.approved,
        policy=body.policy.model_dump(by_alias=True, exclude_unset=True),
        candidates=[candidate.model_dump(by_alias=True) for candidate in body.candidates],
        subject=body.subject,
        user=actor_projection(actor),
    )


@router.post("/assignments")
async def create_assignment(
    body: AssignmentCreateRequest,
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_authorized_assignment_create),
):
    """Create a reviewed assignment from curriculum content or an accepted AI draft."""
    return adaptive_learning_service.create_assignment(
        student_id=authorized_student.ref.student_id,
        source_type=body.source_type,
        source_id=body.source_id,
        title=body.title,
        status=body.status,
        due_at=body.due_at,
        note=body.note,
        user=actor_projection(actor),
    )


@router.get("/assignments/{assignment_id}")
async def get_assignment(
    assignment_id: str,
    actor: Actor = Depends(get_actor),
    authorized_assignment: AuthorizedResource = Depends(_assignment_read),
):
    return adaptive_learning_service.get_assignment(
        assignment_id,
        actor_projection(actor),
        item=dict(authorized_assignment.value),
    )


@router.post("/assignments/{assignment_id}/start")
async def start_assignment(
    assignment_id: str,
    actor: Actor = Depends(get_actor),
    authorized_assignment: AuthorizedResource = Depends(_assignment_student_update),
):
    return adaptive_learning_service.transition_assignment(
        assignment_id=assignment_id,
        action="start",
        user=actor_projection(actor),
        item=dict(authorized_assignment.value),
    )


@router.post("/assignments/{assignment_id}/complete")
async def complete_assignment(
    assignment_id: str,
    body: AssignmentTransitionRequest | None = None,
    actor: Actor = Depends(get_actor),
    authorized_assignment: AuthorizedResource = Depends(_assignment_student_update),
):
    body = body or AssignmentTransitionRequest()
    return adaptive_learning_service.transition_assignment(
        assignment_id=assignment_id,
        action="complete",
        user=actor_projection(actor),
        item=dict(authorized_assignment.value),
        student_answer=body.student_answer,
        correct=body.correct,
        note=body.note,
    )


@router.post("/assignments/{assignment_id}/skip")
async def skip_assignment(
    assignment_id: str,
    body: AssignmentTransitionRequest | None = None,
    actor: Actor = Depends(get_actor),
    authorized_assignment: AuthorizedResource = Depends(_assignment_student_update),
):
    body = body or AssignmentTransitionRequest()
    return adaptive_learning_service.transition_assignment(
        assignment_id=assignment_id,
        action="skip",
        user=actor_projection(actor),
        item=dict(authorized_assignment.value),
        note=body.note,
    )


@router.post("/assignments/{assignment_id}/archive")
async def archive_assignment(
    assignment_id: str,
    body: AssignmentTransitionRequest | None = None,
    actor: Actor = Depends(get_actor),
    authorized_assignment: AuthorizedResource = Depends(_assignment_operator_update),
):
    body = body or AssignmentTransitionRequest()
    return adaptive_learning_service.transition_assignment(
        assignment_id=assignment_id,
        action="archive",
        user=actor_projection(actor),
        item=dict(authorized_assignment.value),
        note=body.note,
    )


@router.get("/parents/me/children/{student_id}/progress")
async def get_parent_child_progress(
    student_id: str,
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_parent_progress),
):
    """Parent-facing progress signals for adaptive memory and assignments."""
    return adaptive_learning_service.parent_progress_signal(
        authorized_student.ref.student_id, actor_projection(actor)
    )
