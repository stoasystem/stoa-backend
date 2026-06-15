"""Adaptive learning memory and reviewed assignment routes."""

from __future__ import annotations

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
    """Role-scoped memory summary for student, parent, tutor, teacher, or admin."""
    return adaptive_learning_service.get_memory_summary(
        student_id=student_id,
        user=user,
        subject=subject,
    )


@router.post("/students/{student_id}/memory/refresh")
async def refresh_student_memory(
    student_id: str,
    subject: str | None = Query(default=None),
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
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
    """Role-scoped assignment list for tutor/admin review and parent progress views."""
    return adaptive_learning_service.list_assignments(
        student_id=student_id,
        user=user,
        status=status,
        include_archived=include_archived,
    )


@router.post("/assignments")
async def create_assignment(
    body: AssignmentCreateRequest,
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
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
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
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
