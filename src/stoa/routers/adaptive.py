"""Adaptive learning memory and reviewed assignment routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from stoa.deps import get_current_user, require_role
from stoa.services import adaptive_learning_service

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


@router.get("/students/me/memory")
async def get_my_memory(
    subject: str | None = Query(default=None),
    user: dict = Depends(require_role("student")),
):
    """Student-facing adaptive memory and next-practice recommendations."""
    return adaptive_learning_service.get_memory_summary(
        student_id=user["sub"],
        user=user,
        subject=subject,
    )


@router.get("/students/me/assignments")
async def list_my_assignments(
    status: str | None = Query(default=None),
    user: dict = Depends(require_role("student")),
):
    """Student-facing reviewed assignments."""
    return adaptive_learning_service.list_assignments(
        student_id=user["sub"],
        user=user,
        status=status,
    )


@router.get("/students/{student_id}/memory")
async def get_student_memory(
    student_id: str,
    subject: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """Role-scoped memory summary for student, parent, teacher, or admin."""
    return adaptive_learning_service.get_memory_summary(
        student_id=student_id,
        user=user,
        subject=subject,
    )


@router.post("/students/{student_id}/memory/refresh")
async def refresh_student_memory(
    student_id: str,
    subject: str | None = Query(default=None),
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Persist a durable memory snapshot from current learning evidence."""
    return adaptive_learning_service.get_memory_summary(
        student_id=student_id,
        user=user,
        subject=subject,
        persist=True,
    )


@router.get("/students/{student_id}/recommendations")
async def get_student_recommendations(
    student_id: str,
    subject: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """Next-practice recommendations without autonomous assignment claims."""
    summary = adaptive_learning_service.get_memory_summary(
        student_id=student_id,
        user=user,
        subject=subject,
    )
    return {
        "studentId": student_id,
        "items": summary["recommendations"],
        "sequencingSummary": summary["sequencingSummary"],
        "reviewRequired": True,
        "autonomousDecision": False,
        "locale": adaptive_learning_service.locale_contract(user),
    }


@router.get("/students/{student_id}/assignments")
async def list_student_assignments(
    student_id: str,
    status: str | None = Query(default=None),
    include_archived: bool = Query(default=False, alias="includeArchived"),
    user: dict = Depends(get_current_user),
):
    """Role-scoped assignment list for teacher/admin review and parent progress views."""
    return adaptive_learning_service.list_assignments(
        student_id=student_id,
        user=user,
        status=status,
        include_archived=include_archived,
    )


@router.post("/students/{student_id}/assignment-automation/batches/preview")
async def preview_assignment_automation_batch(
    student_id: str,
    body: AssignmentAutomationPreviewRequest | None = None,
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Preview policy-bounded assignment automation candidates without creating assignments."""
    body = body or AssignmentAutomationPreviewRequest()
    return adaptive_learning_service.preview_assignment_automation_batch(
        student_id=student_id,
        policy=body.policy.model_dump(by_alias=True, exclude_unset=True),
        subject=body.subject,
        user=user,
    )


@router.post("/students/{student_id}/assignment-automation/batches/execute")
async def execute_assignment_automation_batch(
    student_id: str,
    body: AssignmentAutomationExecuteRequest,
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Create reviewed assignments from an approved automation batch."""
    return adaptive_learning_service.execute_assignment_automation_batch(
        student_id=student_id,
        batch_id=body.batch_id,
        approved=body.approved,
        policy=body.policy.model_dump(by_alias=True, exclude_unset=True),
        candidates=[candidate.model_dump(by_alias=True) for candidate in body.candidates],
        subject=body.subject,
        user=user,
    )


@router.post("/assignments")
async def create_assignment(
    body: AssignmentCreateRequest,
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Create a reviewed assignment from curriculum content or an accepted AI draft."""
    return adaptive_learning_service.create_assignment(
        student_id=body.student_id,
        source_type=body.source_type,
        source_id=body.source_id,
        title=body.title,
        status=body.status,
        due_at=body.due_at,
        note=body.note,
        user=user,
    )


@router.get("/assignments/{assignment_id}")
async def get_assignment(
    assignment_id: str,
    user: dict = Depends(get_current_user),
):
    return adaptive_learning_service.get_assignment(assignment_id, user)


@router.post("/assignments/{assignment_id}/start")
async def start_assignment(
    assignment_id: str,
    user: dict = Depends(require_role("student")),
):
    return adaptive_learning_service.transition_assignment(
        assignment_id=assignment_id,
        action="start",
        user=user,
    )


@router.post("/assignments/{assignment_id}/complete")
async def complete_assignment(
    assignment_id: str,
    body: AssignmentTransitionRequest | None = None,
    user: dict = Depends(require_role("student")),
):
    body = body or AssignmentTransitionRequest()
    return adaptive_learning_service.transition_assignment(
        assignment_id=assignment_id,
        action="complete",
        user=user,
        student_answer=body.student_answer,
        correct=body.correct,
        note=body.note,
    )


@router.post("/assignments/{assignment_id}/skip")
async def skip_assignment(
    assignment_id: str,
    body: AssignmentTransitionRequest | None = None,
    user: dict = Depends(require_role("student")),
):
    body = body or AssignmentTransitionRequest()
    return adaptive_learning_service.transition_assignment(
        assignment_id=assignment_id,
        action="skip",
        user=user,
        note=body.note,
    )


@router.post("/assignments/{assignment_id}/archive")
async def archive_assignment(
    assignment_id: str,
    body: AssignmentTransitionRequest | None = None,
    user: dict = Depends(require_role("teacher", "admin")),
):
    body = body or AssignmentTransitionRequest()
    return adaptive_learning_service.transition_assignment(
        assignment_id=assignment_id,
        action="archive",
        user=user,
        note=body.note,
    )


@router.get("/parents/me/children/{student_id}/progress")
async def get_parent_child_progress(
    student_id: str,
    user: dict = Depends(require_role("parent")),
):
    """Parent-facing progress signals for adaptive memory and assignments."""
    return adaptive_learning_service.parent_progress_signal(student_id, user)
