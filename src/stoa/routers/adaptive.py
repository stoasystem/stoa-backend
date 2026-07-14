"""Adaptive learning memory and reviewed assignment routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from stoa.db.repositories import adaptive_learning_repo, user_repo
from stoa.deps import get_actor
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    AuthorizedResource,
    CurrentAuthorizationFactRepository,
    ResourceRef,
    ResourceType,
    authorize_and_resolve,
)
from stoa.security.errors import SecurityDecisionError
from stoa.security.identity import Actor, CanonicalRole
from stoa.security.route_authorization import (
    get_authorization_fact_repository,
    authorized_student_resource_dependency,
)
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

_my_adaptive_read = authorized_student_resource_dependency(
    resource_type=ResourceType.ADAPTIVE_PROFILE,
    action=AuthorizationAction.READ,
    purposes={CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE},
    self_route=True,
)
_adaptive_read = authorized_student_resource_dependency(
    resource_type=ResourceType.ADAPTIVE_PROFILE,
    action=AuthorizationAction.READ,
    purposes=_ADAPTIVE_READ,
)
_adaptive_refresh = authorized_student_resource_dependency(
    resource_type=ResourceType.ADAPTIVE_PROFILE,
    action=AuthorizationAction.UPDATE,
    purposes=_ADAPTIVE_REFRESH,
)
_automation_preview = authorized_student_resource_dependency(
    resource_type=ResourceType.ADAPTIVE_PROFILE,
    action=AuthorizationAction.READ,
    purposes=_AUTOMATION_PREVIEW,
)
_automation_execute = authorized_student_resource_dependency(
    resource_type=ResourceType.ADAPTIVE_PROFILE,
    action=AuthorizationAction.CREATE,
    purposes=_AUTOMATION_EXECUTE,
)
_parent_progress = authorized_student_resource_dependency(
    resource_type=ResourceType.ADAPTIVE_PROFILE,
    action=AuthorizationAction.READ,
    purposes={CanonicalRole.PARENT: AuthorizationPurpose.PARENT_OVERSIGHT},
)


def _actor_projection(actor: Actor) -> dict[str, Any]:
    projection = {
        "sub": actor.user_id,
        "user_id": actor.user_id,
        "role": actor.role.value,
        "account_status": actor.account_status.value,
        "capabilities": {
            grant.capability: "granted" for grant in actor.current_grants
        },
    }
    projection.update(dict(actor.auth_context))
    return projection


async def _authorize_loaded_resource(
    *,
    actor: Actor,
    facts: CurrentAuthorizationFactRepository,
    resource_type: ResourceType,
    resource_id: str,
    student_id: str,
    value: dict | None,
    action: AuthorizationAction,
    purposes: dict[CanonicalRole, AuthorizationPurpose],
) -> AuthorizedResource:
    purpose = purposes.get(actor.role)
    if purpose is None:
        from stoa.security.errors import SecurityErrorCode

        error = SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
        raise HTTPException(status_code=error.status_code, detail=error.public_body())

    async def resolve(_resource_id: str):
        if not value:
            return None
        return AuthorizedResource(
            ResourceRef(resource_type, resource_id, student_id),
            value,
        )

    spec = AuthorizationSpec(resource_type, action, purpose, resolve)
    try:
        return await authorize_and_resolve(
            actor=actor,
            resource_id=resource_id,
            spec=spec,
            fact_repository=facts,
        )
    except SecurityDecisionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.public_body()) from error


def _assignment_dependency(
    action: AuthorizationAction,
    purposes: dict[CanonicalRole, AuthorizationPurpose],
):
    async def dependency(
        assignment_id: str,
        actor: Actor = Depends(get_actor),
        facts: CurrentAuthorizationFactRepository = Depends(
            get_authorization_fact_repository
        ),
    ) -> AuthorizedResource:
        item = adaptive_learning_repo.get_assignment(assignment_id)
        return await _authorize_loaded_resource(
            actor=actor,
            facts=facts,
            resource_type=ResourceType.ADAPTIVE_PROFILE,
            resource_id=assignment_id,
            student_id=str((item or {}).get("student_id") or ""),
            value=item,
            action=action,
            purposes=purposes,
        )

    async def metadata_resolver(resource_id: str):
        return adaptive_learning_repo.get_assignment(resource_id)

    dependency.authorization_specs = tuple(  # type: ignore[attr-defined]
        AuthorizationSpec(ResourceType.ADAPTIVE_PROFILE, action, purpose, metadata_resolver)
        for purpose in purposes.values()
    )
    return dependency


_assignment_read = _assignment_dependency(AuthorizationAction.READ, _ASSIGNMENT_READ)
_assignment_student_update = _assignment_dependency(
    AuthorizationAction.UPDATE, _ASSIGNMENT_STUDENT_UPDATE
)
_assignment_operator_update = _assignment_dependency(
    AuthorizationAction.UPDATE, _ASSIGNMENT_OPERATOR_UPDATE
)


async def _authorized_assignment_create(
    body: AssignmentCreateRequest,
    actor: Actor = Depends(get_actor),
    facts: CurrentAuthorizationFactRepository = Depends(get_authorization_fact_repository),
) -> AuthorizedResource:
    student = user_repo.get_user(body.student_id)
    return await _authorize_loaded_resource(
        actor=actor,
        facts=facts,
        resource_type=ResourceType.ADAPTIVE_PROFILE,
        resource_id=body.student_id,
        student_id=body.student_id,
        value=student,
        action=AuthorizationAction.ASSIGN,
        purposes=_ASSIGNMENT_OPERATOR_UPDATE,
    )


async def _student_metadata_resolver(resource_id: str):
    return user_repo.get_user(resource_id)


_authorized_assignment_create.authorization_specs = tuple(  # type: ignore[attr-defined]
    AuthorizationSpec(
        ResourceType.ADAPTIVE_PROFILE,
        AuthorizationAction.ASSIGN,
        purpose,
        _student_metadata_resolver,
    )
    for purpose in _ASSIGNMENT_OPERATOR_UPDATE.values()
)


@router.get("/students/me/memory")
async def get_my_memory(
    subject: str | None = Query(default=None),
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_my_adaptive_read),
):
    """Student-facing adaptive memory and next-practice recommendations."""
    return adaptive_learning_service.get_memory_summary(
        student_id=authorized_student.ref.student_id,
        user=_actor_projection(actor),
        subject=subject,
    )


@router.get("/students/me/assignments")
async def list_my_assignments(
    status: str | None = Query(default=None),
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_my_adaptive_read),
):
    """Student-facing reviewed assignments."""
    return adaptive_learning_service.list_assignments(
        student_id=authorized_student.ref.student_id,
        user=_actor_projection(actor),
        status=status,
    )


@router.get("/students/{student_id}/memory")
async def get_student_memory(
    student_id: str,
    subject: str | None = Query(default=None),
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_adaptive_read),
):
    """Role-scoped memory summary for student, parent, teacher, or admin."""
    return adaptive_learning_service.get_memory_summary(
        student_id=authorized_student.ref.student_id,
        user=_actor_projection(actor),
        subject=subject,
    )


@router.post("/students/{student_id}/memory/refresh")
async def refresh_student_memory(
    student_id: str,
    subject: str | None = Query(default=None),
    actor: Actor = Depends(get_actor),
    authorized_student: AuthorizedResource = Depends(_adaptive_refresh),
):
    """Persist a durable memory snapshot from current learning evidence."""
    return adaptive_learning_service.get_memory_summary(
        student_id=authorized_student.ref.student_id,
        user=_actor_projection(actor),
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
        user=_actor_projection(actor),
        subject=subject,
    )
    return {
        "studentId": authorized_student.ref.student_id,
        "items": summary["recommendations"],
        "sequencingSummary": summary["sequencingSummary"],
        "reviewRequired": True,
        "autonomousDecision": False,
        "locale": adaptive_learning_service.locale_contract(_actor_projection(actor)),
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
        user=_actor_projection(actor),
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
        user=_actor_projection(actor),
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
        user=_actor_projection(actor),
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
        user=_actor_projection(actor),
    )


@router.get("/assignments/{assignment_id}")
async def get_assignment(
    assignment_id: str,
    actor: Actor = Depends(get_actor),
    authorized_assignment: AuthorizedResource = Depends(_assignment_read),
):
    return adaptive_learning_service.get_assignment(
        assignment_id,
        _actor_projection(actor),
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
        user=_actor_projection(actor),
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
        user=_actor_projection(actor),
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
        user=_actor_projection(actor),
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
        user=_actor_projection(actor),
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
        authorized_student.ref.student_id, _actor_projection(actor)
    )
