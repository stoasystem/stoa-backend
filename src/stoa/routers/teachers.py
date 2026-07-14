"""Teacher routes — work queue, takeover, reply, resolve."""
import uuid

import boto3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from stoa.db.repositories import question_repo, user_repo
from stoa.db.dynamodb import get_table
from stoa.deps import get_actor, require_role
from stoa.models.question import QuestionStatus
from stoa.security.authorization import (
    AuthorizationAction,
    CurrentAuthorizationFactRepository,
    AuthorizationPurpose,
    AuthorizedResource,
    ResourceType,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor, CanonicalRole
from stoa.security.route_authorization import (
    authorized_question_dependency,
    authorized_teacher_resource_dependency,
    authorize_teacher_loaded_resource,
    get_authorization_fact_repository,
    teacher_capability_dependency,
    teacher_portal_self_dependency,
)
from stoa.services import (
    ai_teacher_tools_service,
    notification_service,
    teacher_assistance_service,
    teacher_dispatch_service,
    teacher_reply_service,
)

router = APIRouter()


class TakeoverResponse(BaseModel):
    question_id: str
    session_id: str
    status: str


class ReplyRequest(BaseModel):
    content: str | None = Field(default=None, max_length=4000)
    rich_content: dict[str, Any] | None = None


class ReplyResponse(BaseModel):
    question_id: str
    teacher_response: str
    teacher_response_text: str
    teacher_response_rich: dict[str, Any]
    teacher_response_format: str
    teacher_first_replied_at: str | None = None
    teacher_first_reply_sla_bucket: str | None = None
    status: str


class DispatchPreviewRequest(BaseModel):
    question_id: str = Field(..., min_length=1)


class DispatchRunRequest(BaseModel):
    question_id: str = Field(..., min_length=1)


def _list_escalated_questions(limit: int = 50) -> list[dict]:
    """Scan for ESCALATED questions (small scale; replace with GSI for production)."""
    table = get_table()
    result = table.scan(
        FilterExpression="#s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": QuestionStatus.ESCALATED.value},
        Limit=limit,
    )
    return result.get("Items", [])


def _is_dispatch_restricted_to_other_teacher(item: dict[str, Any], teacher_id: str, now: str) -> bool:
    return (
        item.get("dispatch_status") == "dispatched"
        and item.get("dispatched_teacher_id") not in (None, "", teacher_id)
        and not teacher_dispatch_service._deadline_expired(item.get("dispatch_deadline_at"), now)
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/queue")
async def get_queue(
    actor: Actor = Depends(teacher_portal_self_dependency()),
):
    """Return the list of questions awaiting teacher intervention."""
    now = _now()
    questions = _list_escalated_questions()
    viewer_id = actor.user_id
    if actor.role is not CanonicalRole.ADMIN:
        questions = [
            item
            for item in questions
            if not _is_dispatch_restricted_to_other_teacher(item, viewer_id, now)
        ]
    items = [teacher_dispatch_service.decorate_queue_item(item, viewer_id=viewer_id, now=now) for item in questions]
    return {"items": items, "count": len(items)}


@router.post("/dispatch/preview")
async def preview_dispatch(
    body: DispatchPreviewRequest,
    _actor: Actor = Depends(
        teacher_capability_dependency(
            capability_purpose=AuthorizationPurpose.TEACHER_DISPATCH,
            action=AuthorizationAction.READ,
        )
    ),
):
    """Preview candidate teacher dispatch without mutating state."""
    item = question_repo.get_question(body.question_id)
    if not item:
        raise HTTPException(status_code=404, detail="Question not found")
    if item.get("status") != QuestionStatus.ESCALATED.value:
        raise HTTPException(status_code=409, detail="Question is not awaiting teacher dispatch")
    return teacher_dispatch_service.plan_dispatch(item, now=_now())


@router.post("/dispatch/run")
async def run_dispatch(
    body: DispatchRunRequest,
    _actor: Actor = Depends(
        teacher_capability_dependency(
            capability_purpose=AuthorizationPurpose.TEACHER_DISPATCH,
            action=AuthorizationAction.ASSIGN,
        )
    ),
):
    """Run automatic dispatch for one escalated question."""
    result = teacher_dispatch_service.dispatch_question(body.question_id, now=_now())
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Question not found")
    if result["status"] == "not_dispatchable":
        raise HTTPException(status_code=409, detail=result["reason"])
    if result["status"] == "claim_conflict":
        raise HTTPException(status_code=409, detail="Dispatch claim conflicted with another assignment")
    return result


@router.post("/dispatch/reassign-stale")
async def reassign_stale_dispatches(
    _actor: Actor = Depends(
        teacher_capability_dependency(
            capability_purpose=AuthorizationPurpose.TEACHER_DISPATCH,
            action=AuthorizationAction.ASSIGN,
        )
    ),
):
    """Reassign stale dispatch attempts that missed their accept deadline."""
    return teacher_dispatch_service.reassign_timed_out_dispatches(now=_now())


@router.post("/questions/{question_id}/takeover", response_model=TakeoverResponse)
async def takeover(
    question_id: str,
    authorized: AuthorizedResource = Depends(
        authorized_question_dependency(
            action=AuthorizationAction.CLAIM,
            purposes={CanonicalRole.TEACHER: AuthorizationPurpose.TEACHER_HELP},
        )
    ),
):
    """Lock a question to this teacher and start a session."""
    item = dict(authorized.value)
    if item.get("status") == QuestionStatus.TEACHER_ACTIVE.value:
        raise HTTPException(status_code=409, detail="Question is already taken by a teacher")
    if item.get("status") != QuestionStatus.ESCALATED.value:
        raise HTTPException(status_code=409, detail="Question is not awaiting teacher takeover")

    teacher_id = authorized.facts.teacher.teacher_account["user_id"]
    now = _now()
    if _is_dispatch_restricted_to_other_teacher(item, teacher_id, now):
        raise HTTPException(status_code=409, detail="Question is dispatched to another teacher")
    session_id = str(uuid.uuid4())
    sla_fields = teacher_reply_service.compute_takeover_sla_fields(item, now)

    question_repo.update_status(
        question_id,
        QuestionStatus.TEACHER_ACTIVE.value,
        teacher_id=teacher_id,
        session_id=session_id,
        teacher_started_at=now,
        teacher_taken_over_at=now,
        dispatch_status="accepted" if item.get("dispatch_status") == "dispatched" else item.get("dispatch_status"),
        dispatch_accepted_at=now if item.get("dispatch_status") == "dispatched" else item.get("dispatch_accepted_at"),
        **sla_fields,
    )

    # Persist a TeacherSession record in DynamoDB
    table = get_table()
    table.put_item(Item={
        "PK": f"SESSION#{session_id}",
        "SK": "META",
        "session_id": session_id,
        "question_id": question_id,
        "teacher_id": teacher_id,
        "student_id": item["student_id"],
        "started_at": now,
        "resolved_at": None,
    })
    notification_service.emit_teacher_takeover(question=item, teacher_id=teacher_id)

    return TakeoverResponse(
        question_id=question_id,
        session_id=session_id,
        status=QuestionStatus.TEACHER_ACTIVE.value,
    )


@router.post("/questions/{question_id}/reply", response_model=ReplyResponse)
async def reply(
    question_id: str,
    body: ReplyRequest,
    authorized: AuthorizedResource = Depends(
        authorized_question_dependency(
            action=AuthorizationAction.RESPOND,
            purposes={CanonicalRole.TEACHER: AuthorizationPurpose.TEACHER_HELP},
        )
    ),
):
    """Post the teacher's reply to a question they have taken over."""
    item = dict(authorized.value)
    if item.get("status") == QuestionStatus.RESOLVED.value:
        raise HTTPException(status_code=409, detail="Question is already resolved")
    if item.get("status") != QuestionStatus.TEACHER_ACTIVE.value:
        raise HTTPException(status_code=409, detail="Question is not active with a teacher")

    try:
        reply_fields = teacher_reply_service.normalize_teacher_reply(
            body.content,
            body.rich_content,
        )
    except teacher_reply_service.TeacherReplyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = _now()
    if not item.get("teacher_first_replied_at"):
        reply_fields["teacher_first_replied_at"] = now
        reply_fields.update(teacher_reply_service.compute_sla_fields(item, now))

    question_repo.update_status(
        question_id,
        QuestionStatus.TEACHER_ACTIVE.value,
        **reply_fields,
    )
    teacher_id = str((authorized.facts.teacher.teacher_account or {})["user_id"])
    notification_service.emit_teacher_reply(question=item, teacher_id=teacher_id)
    return ReplyResponse(
        question_id=question_id,
        teacher_response=reply_fields["teacher_response"],
        teacher_response_text=reply_fields["teacher_response_text"],
        teacher_response_rich=reply_fields["teacher_response_rich"],
        teacher_response_format=reply_fields["teacher_response_format"],
        teacher_first_replied_at=reply_fields.get("teacher_first_replied_at")
        or item.get("teacher_first_replied_at"),
        teacher_first_reply_sla_bucket=reply_fields.get("teacher_first_reply_sla_bucket")
        or item.get("teacher_first_reply_sla_bucket"),
        status=QuestionStatus.TEACHER_ACTIVE.value,
    )


@router.put("/questions/{question_id}/resolve", status_code=status.HTTP_200_OK)
async def resolve(
    question_id: str,
    authorized: AuthorizedResource = Depends(
        authorized_question_dependency(
            action=AuthorizationAction.RESOLVE,
            purposes={CanonicalRole.TEACHER: AuthorizationPurpose.TEACHER_HELP},
        )
    ),
):
    """Mark a question as resolved and close the teacher session."""
    item = dict(authorized.value)
    if item.get("status") == QuestionStatus.RESOLVED.value:
        raise HTTPException(status_code=409, detail="Question is already resolved")

    now = _now()
    question_repo.update_status(
        question_id,
        QuestionStatus.RESOLVED.value,
        resolved_at=now,
        **teacher_reply_service.compute_resolved_sla_fields(item, now),
    )

    # Update session record
    session_id = item.get("session_id")
    if session_id:
        table = get_table()
        table.update_item(
            Key={"PK": f"SESSION#{session_id}", "SK": "META"},
            UpdateExpression="SET resolved_at = :r",
            ExpressionAttributeValues={":r": now},
        )

    return {"question_id": question_id, "status": QuestionStatus.RESOLVED.value, "resolved_at": now}


# Canonical teacher portal, availability, help-request, and AI-tool routes.
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conv_pk(conv_id: str) -> str:
    return f"CONV#{conv_id}"


def _get_conversation(conv_id: str) -> dict | None:
    table = get_table()
    resp = table.get_item(Key={"PK": _conv_pk(conv_id), "SK": "CONV"})
    return resp.get("Item")


def _get_messages(conv_id: str) -> list[dict]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=(
            boto3.dynamodb.conditions.Key("PK").eq(_conv_pk(conv_id)) &
            boto3.dynamodb.conditions.Key("SK").begins_with("MSG#")
        ),
        ScanIndexForward=True,
    )
    return resp.get("Items", [])


def _get_escalated_conversations() -> list[dict]:
    """Scan conversations that have been escalated to a teacher."""
    table = get_table()
    resp = table.scan(
        FilterExpression=(
            boto3.dynamodb.conditions.Attr("entity_type").eq("conversation") &
            boto3.dynamodb.conditions.Attr("escalated").eq(True)
        ),
    )
    return resp.get("Items", [])


def _resolve_help_request(request_id: str) -> dict | None:
    """Resolve an external request ID to one canonical conversation/task owner."""
    conv = _get_conversation(request_id)
    if not conv or not conv.get("escalated"):
        conv = next(
            (
                item
                for item in _get_escalated_conversations()
                if item.get("escalation_request_id") == request_id
            ),
            None,
        )
    if not conv:
        return None
    return _normalize_help_request(conv)


def _normalize_help_request(conv: dict) -> dict:
    normalized = dict(conv)
    if not normalized.get("status"):
        normalized["status"] = (
            QuestionStatus.TEACHER_ACTIVE.value
            if normalized.get("teacher_id")
            else QuestionStatus.ESCALATED.value
        )
    if not normalized.get("dispatch_status"):
        normalized["dispatch_status"] = (
            "accepted" if normalized.get("teacher_id") else "unassigned"
        )
    return normalized


async def _current_help_requests(
    actor: Actor, facts: CurrentAuthorizationFactRepository
) -> list[dict]:
    current: list[dict] = []
    for raw in _get_escalated_conversations():
        conv = _normalize_help_request(raw)
        try:
            await authorize_teacher_loaded_resource(
                actor=actor,
                facts=facts,
                loaded=conv,
                resource_type=ResourceType.TEACHER_HELP_REQUEST,
                action=AuthorizationAction.READ,
            )
        except SecurityDecisionError as error:
            if error.code is SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE:
                raise HTTPException(
                    status_code=error.status_code, detail=error.public_body()
                ) from error
            continue
        current.append(conv)
    return current


def _get_student_name(student_id: str) -> str:
    profile = user_repo.get_user(student_id)
    if profile:
        return profile.get("name") or profile.get("email", "Student")
    return "Student"


def _sla_snapshot(conv: dict) -> dict[str, int | str | None]:
    requested_at = _parse_time(conv.get("escalated_at") or conv.get("created_at"))
    first_action_at = _parse_time(conv.get("first_teacher_action_at"))
    seconds = None
    if requested_at and first_action_at:
        seconds = max(0, int((first_action_at - requested_at).total_seconds()))
    return {
        "status": teacher_reply_service.sla_bucket(seconds),
        "requestToFirstActionMinutes": round(seconds / 60) if seconds is not None else None,
        "targetMinutes": 30,
    }


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _list_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (set, tuple)):
        return list(value)
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class TeacherHelpRequestSummary(BaseModel):
    requestId: str
    conversationId: str
    studentName: str
    subject: str
    grade: str
    status: str
    requestMessage: str | None = None
    priority: str = "medium"
    createdAt: str
    firstTeacherActionAt: str | None = None
    sla: dict | None = None


class MessageOut(BaseModel):
    id: str
    conversationId: str
    role: str
    content: str
    createdAt: str
    status: str = "sent"


class TeacherNoteOut(BaseModel):
    id: str
    note: str
    createdAt: str
    teacher: dict
    richContent: dict | None = None
    responseFormat: str | None = None


class TeacherHelpRequestDetail(BaseModel):
    requestId: str
    conversationId: str
    student: dict
    subject: str
    status: str
    requestMessage: str | None = None
    messages: list[MessageOut]
    notes: list[TeacherNoteOut]
    firstTeacherActionAt: str | None = None
    sla: dict | None = None


class UpdateStatusRequest(BaseModel):
    status: str
    resolutionNote: str | None = None


class AddNoteRequest(BaseModel):
    content: str
    richContent: dict[str, Any] | None = None


class TeacherAvailabilitySlot(BaseModel):
    dayOfWeek: str
    startTime: str
    endTime: str


class TeacherAvailability(BaseModel):
    weeklyAvailability: list[TeacherAvailabilitySlot] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)


class TeacherStats(BaseModel):
    pendingRequests: int
    resolvedToday: int
    averageResponseTimeMinutes: int


class AssistanceSummaryResponse(BaseModel):
    summaryId: str
    questionId: str
    studentId: str
    subject: str
    studentContextSummary: str
    questionSummary: str
    aiAnswerSummary: str
    weakTopics: list[str]
    suggestedFocus: str
    sourceCount: int
    createdAt: str


class CreateSummaryDraftResponse(BaseModel):
    draftId: str
    draftType: str
    status: str
    studentId: str | None = None
    questionId: str | None = None
    subject: str | None = None
    topicIds: list[str] = Field(default_factory=list)
    sessionSummary: str | None = None
    misconceptionSummary: str | None = None
    suggestedTeachingFocus: str | None = None
    draftFollowupExplanation: str | None = None
    sourceContext: dict[str, Any] = Field(default_factory=dict)
    promptVersion: str | None = None
    createdBy: str | None = None
    createdByRole: str | None = None
    createdAt: str | None = None
    generatedAt: str | None = None
    updatedAt: str | None = None
    reviewedBy: str | None = None
    reviewedAt: str | None = None
    reviewNote: str | None = None
    previousDraftId: str | None = None
    studentDeliveryStatus: str = "not_delivered"


class ExerciseDraftRequest(BaseModel):
    studentId: str
    subject: str
    topicIds: list[str]
    difficulty: str
    exerciseCount: int
    questionId: str | None = None


class ReviewDraftRequest(BaseModel):
    note: str | None = None


class AiTeacherDraftResponse(CreateSummaryDraftResponse):
    difficulty: str | None = None
    exerciseCount: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)
    answerKey: list[dict[str, Any]] = Field(default_factory=list)
    explanations: list[dict[str, Any]] = Field(default_factory=list)


class AiTeacherDraftListResponse(BaseModel):
    items: list[AiTeacherDraftResponse]
    count: int


def _availability_response(profile: dict[str, Any] | None) -> TeacherAvailability:
    profile = profile or {}
    subjects = [
        str(subject).strip()
        for subject in _list_value(
            profile.get("dispatch_subjects")
            or profile.get("primary_subjects")
            or profile.get("subjects")
            or profile.get("subject_ids")
        )
        if str(subject).strip()
    ]
    weekly_availability = profile.get("weekly_availability") or profile.get("weeklyAvailability") or []
    slots = [
        {
            "dayOfWeek": str(slot["dayOfWeek"]),
            "startTime": str(slot["startTime"]),
            "endTime": str(slot["endTime"]),
        }
        for slot in weekly_availability
        if isinstance(slot, dict)
        and slot.get("dayOfWeek")
        and slot.get("startTime")
        and slot.get("endTime")
    ]
    return TeacherAvailability(subjects=subjects, weeklyAvailability=slots)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/me/availability", response_model=TeacherAvailability)
async def get_my_availability(
    actor: Actor = Depends(teacher_portal_self_dependency()),
):
    """Return the current teacher availability profile used for dispatch."""
    return _availability_response(user_repo.get_user(actor.user_id))


@router.patch("/me/availability", response_model=TeacherAvailability)
async def update_my_availability(
    body: TeacherAvailability,
    actor: Actor = Depends(teacher_portal_self_dependency()),
):
    """Persist teacher availability so student support status can reflect it."""
    updated = user_repo.update_teacher_availability(
        actor.user_id,
        subjects=[subject.strip() for subject in body.subjects if subject.strip()],
        weekly_availability=[slot.model_dump() for slot in body.weeklyAvailability],
        updated_at=_now(),
    )
    return _availability_response(updated)


@router.get("/me/stats", response_model=TeacherStats)
async def get_stats(
    actor: Actor = Depends(teacher_portal_self_dependency()),
    facts: CurrentAuthorizationFactRepository = Depends(
        get_authorization_fact_repository
    ),
):
    escalated = await _current_help_requests(actor, facts)
    pending = sum(1 for c in escalated if c.get("escalation_status", "pending") == "pending")
    response_times = [
        snapshot["requestToFirstActionMinutes"]
        for snapshot in (_sla_snapshot(c) for c in escalated)
        if isinstance(snapshot["requestToFirstActionMinutes"], int)
    ]
    resolved_today_count = sum(
        1 for c in escalated
        if c.get("escalation_status") == "resolved"
        and c.get("escalation_resolved_at", "")[:10] == datetime.now(timezone.utc).date().isoformat()
    )
    return TeacherStats(
        pendingRequests=pending,
        resolvedToday=resolved_today_count,
        averageResponseTimeMinutes=round(sum(response_times) / len(response_times)) if response_times else 0,
    )


@router.get("/questions/{question_id}/assistance-summary", response_model=AssistanceSummaryResponse)
async def get_question_assistance_summary(
    question_id: str,
    authorized: AuthorizedResource = Depends(
        authorized_question_dependency(
            action=AuthorizationAction.READ,
            purposes={CanonicalRole.TEACHER: AuthorizationPurpose.TEACHER_HELP},
        )
    ),
    actor: Actor = Depends(get_actor),
):
    """Build a bounded teacher assistance summary seed for an accessible question."""
    return teacher_assistance_service.build_summary_seed(authorized, actor)


@router.post("/questions/{question_id}/ai-tools/summary-draft", response_model=AiTeacherDraftResponse)
async def create_question_summary_draft(
    question_id: str,
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Create a reviewed AI teacher summary draft for an accessible question."""
    return ai_teacher_tools_service.create_summary_draft(question_id, user)


@router.post("/ai-tools/exercise-drafts", response_model=AiTeacherDraftResponse)
async def create_exercise_draft(
    body: ExerciseDraftRequest,
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Create a reviewed practice exercise draft from teacher-visible learning context."""
    return ai_teacher_tools_service.create_exercise_draft(
        student_id=body.studentId,
        subject=body.subject,
        topic_ids=body.topicIds,
        difficulty=body.difficulty,
        exercise_count=body.exerciseCount,
        question_id=body.questionId,
        user=user,
    )


@router.get("/ai-tools/drafts", response_model=AiTeacherDraftListResponse)
async def list_ai_teacher_drafts(
    student_id: str | None = None,
    status: str | None = None,
    draft_type: str | None = None,
    limit: int = 50,
    user: dict = Depends(require_role("teacher", "admin")),
):
    """List visible reviewed AI teacher tool drafts."""
    items = ai_teacher_tools_service.list_drafts(
        user=user,
        student_id=student_id,
        status=status,
        draft_type=draft_type,
        limit=limit,
    )
    return AiTeacherDraftListResponse(items=items, count=len(items))


@router.get("/ai-tools/drafts/{draft_id}", response_model=AiTeacherDraftResponse)
async def get_ai_teacher_draft(
    draft_id: str,
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Return one visible reviewed AI teacher tool draft."""
    return ai_teacher_tools_service.get_draft(draft_id, user)


@router.post("/ai-tools/drafts/{draft_id}/regenerate", response_model=AiTeacherDraftResponse)
async def regenerate_ai_teacher_draft(
    draft_id: str,
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Create a new draft version while preserving prior draft metadata."""
    return ai_teacher_tools_service.regenerate_draft(draft_id, user)


@router.post("/ai-tools/drafts/{draft_id}/accept", response_model=AiTeacherDraftResponse)
async def accept_ai_teacher_draft(
    draft_id: str,
    body: ReviewDraftRequest | None = None,
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Mark a draft as reviewed and accepted without delivering it to students."""
    return ai_teacher_tools_service.review_draft(
        draft_id=draft_id,
        action="accept",
        user=user,
        note=body.note if body else None,
    )


@router.post("/ai-tools/drafts/{draft_id}/reject", response_model=AiTeacherDraftResponse)
async def reject_ai_teacher_draft(
    draft_id: str,
    body: ReviewDraftRequest | None = None,
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Mark a draft as rejected without deleting evidence."""
    return ai_teacher_tools_service.review_draft(
        draft_id=draft_id,
        action="reject",
        user=user,
        note=body.note if body else None,
    )


@router.post("/ai-tools/drafts/{draft_id}/archive", response_model=AiTeacherDraftResponse)
async def archive_ai_teacher_draft(
    draft_id: str,
    body: ReviewDraftRequest | None = None,
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Archive a draft from the active teacher workflow without deleting evidence."""
    return ai_teacher_tools_service.review_draft(
        draft_id=draft_id,
        action="archive",
        user=user,
        note=body.note if body else None,
    )


@router.get("/me/help-requests", response_model=dict)
async def list_help_requests(
    actor: Actor = Depends(teacher_portal_self_dependency()),
    facts: CurrentAuthorizationFactRepository = Depends(
        get_authorization_fact_repository
    ),
):
    """Return only help requests currently assigned to this Actor."""
    escalated = await _current_help_requests(actor, facts)
    items = []
    for conv in sorted(escalated, key=lambda c: c.get("escalated_at", ""), reverse=True):
        conv_id = conv.get("conversation_id", "")
        student_name = _get_student_name(conv.get("student_id", ""))
        esc_status = conv.get("escalation_status", "pending")
        items.append(TeacherHelpRequestSummary(
            requestId=conv.get("escalation_request_id", conv_id),
            conversationId=conv_id,
            studentName=student_name,
            subject=conv.get("subject", "General"),
            grade=conv.get("grade", ""),
            status=esc_status,
            requestMessage=conv.get("escalation_message"),
            createdAt=conv.get("escalated_at", conv.get("updated_at", _now())),
            firstTeacherActionAt=conv.get("first_teacher_action_at"),
            sla=_sla_snapshot(conv),
        ).model_dump())
    return {"items": items}


@router.get("/me/help-requests/{request_id}", response_model=TeacherHelpRequestDetail)
async def get_help_request(
    request_id: str,
    authorized: AuthorizedResource = Depends(
        authorized_teacher_resource_dependency(
            resource_type=ResourceType.TEACHER_HELP_REQUEST,
            action=AuthorizationAction.READ,
            resolver=_resolve_help_request,
        )
    ),
):
    """Get full detail of a specific help request including conversation messages."""
    table = get_table()

    conv = dict(authorized.value)

    conv_id = conv.get("conversation_id", "")
    student_id = conv.get("student_id", "")
    student_profile = user_repo.get_user(student_id)
    student_name = (student_profile or {}).get("name", "Student")

    raw_messages = _get_messages(conv_id)
    messages = [
        MessageOut(
            id=m["message_id"],
            conversationId=conv_id,
            role=m["role"],
            content=m["content"],
            createdAt=m["created_at"],
        )
        for m in raw_messages
    ]

    # Load notes stored as NOTE# items in the conversation
    notes_resp = table.query(
        KeyConditionExpression=(
            boto3.dynamodb.conditions.Key("PK").eq(_conv_pk(conv_id)) &
            boto3.dynamodb.conditions.Key("SK").begins_with("NOTE#")
        ),
        ScanIndexForward=True,
    )
    notes = [
        TeacherNoteOut(
            id=n["note_id"],
            note=n["content"],
            createdAt=n["created_at"],
            teacher={"id": n.get("teacher_id", ""), "name": n.get("teacher_name", "Teacher")},
            richContent=n.get("teacher_response_rich"),
            responseFormat=n.get("teacher_response_format"),
        )
        for n in notes_resp.get("Items", [])
    ]

    # Mark first teacher access time
    first_teacher_action_at = conv.get("first_teacher_action_at")
    if not first_teacher_action_at:
        first_teacher_action_at = _now()
        try:
            table.update_item(
                Key={"PK": _conv_pk(conv_id), "SK": "CONV"},
                UpdateExpression="SET first_teacher_action_at = :t",
                ConditionExpression="attribute_not_exists(first_teacher_action_at)",
                ExpressionAttributeValues={":t": first_teacher_action_at},
            )
        except Exception:
            pass
        conv = {**conv, "first_teacher_action_at": first_teacher_action_at}

    return TeacherHelpRequestDetail(
        requestId=conv.get("escalation_request_id", conv_id),
        conversationId=conv_id,
        student={
            "id": student_id,
            "name": student_name,
            "grade": conv.get("grade", ""),
        },
        subject=conv.get("subject", "General"),
        status=conv.get("escalation_status", "pending"),
        requestMessage=conv.get("escalation_message"),
        messages=messages,
        notes=notes,
        firstTeacherActionAt=first_teacher_action_at,
        sla=_sla_snapshot(conv),
    )


@router.patch("/me/help-requests/{request_id}", response_model=TeacherHelpRequestSummary)
async def update_help_request(
    request_id: str,
    body: UpdateStatusRequest,
    authorized: AuthorizedResource = Depends(
        authorized_teacher_resource_dependency(
            resource_type=ResourceType.TEACHER_HELP_REQUEST,
            action=AuthorizationAction.RESOLVE,
            resolver=_resolve_help_request,
        )
    ),
):
    """Update the status of a help request (pending → in_progress → resolved)."""
    table = get_table()
    conv = dict(authorized.value)

    conv_id = conv.get("conversation_id", "")
    now = _now()
    update_parts = ["escalation_status = :s", "updated_at = :u"]
    expr_values: dict = {":s": body.status, ":u": now}
    if not conv.get("first_teacher_action_at"):
        update_parts.append("first_teacher_action_at = :f")
        expr_values[":f"] = now

    if body.resolutionNote:
        update_parts.append("resolution_note = :r")
        expr_values[":r"] = body.resolutionNote

    table.update_item(
        Key={"PK": _conv_pk(conv_id), "SK": "CONV"},
        UpdateExpression="SET " + ", ".join(update_parts),
        ExpressionAttributeValues=expr_values,
    )

    student_name = _get_student_name(conv.get("student_id", ""))
    return TeacherHelpRequestSummary(
        requestId=conv.get("escalation_request_id", conv_id),
        conversationId=conv_id,
        studentName=student_name,
        subject=conv.get("subject", "General"),
        grade=conv.get("grade", ""),
        status=body.status,
        requestMessage=conv.get("escalation_message"),
        createdAt=conv.get("escalated_at", now),
        firstTeacherActionAt=conv.get("first_teacher_action_at") or now,
        sla=_sla_snapshot({**conv, "first_teacher_action_at": conv.get("first_teacher_action_at") or now}),
    )


@router.post("/me/help-requests/{request_id}/notes", response_model=TeacherNoteOut)
async def add_note(
    request_id: str,
    body: AddNoteRequest,
    authorized: AuthorizedResource = Depends(
        authorized_teacher_resource_dependency(
            resource_type=ResourceType.TEACHER_HELP_REQUEST,
            action=AuthorizationAction.RESPOND,
            resolver=_resolve_help_request,
        )
    ),
    actor: Actor = Depends(get_actor),
):
    """Add a teacher note to a help request (stored in the conversation)."""
    table = get_table()
    conv = dict(authorized.value)

    conv_id = conv.get("conversation_id", "")
    teacher_id = actor.user_id
    teacher_profile = user_repo.get_user(teacher_id)
    teacher_name = (teacher_profile or {}).get("name", "Teacher")
    note_id = str(uuid.uuid4())
    now = _now()
    try:
        reply_fields = teacher_reply_service.normalize_teacher_reply(body.content, body.richContent)
    except teacher_reply_service.TeacherReplyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    table.put_item(Item={
        "PK": _conv_pk(conv_id),
        "SK": f"NOTE#{note_id}",
        "note_id": note_id,
        "conversation_id": conv_id,
        "teacher_id": teacher_id,
        "teacher_name": teacher_name,
        "content": reply_fields["teacher_response"],
        "teacher_response_rich": reply_fields["teacher_response_rich"],
        "teacher_response_format": reply_fields["teacher_response_format"],
        "created_at": now,
    })

    # Also add the teacher's reply as a message in the conversation
    msg_id = str(uuid.uuid4())
    table.put_item(Item={
        "PK": _conv_pk(conv_id),
        "SK": f"MSG#{msg_id}",
        "message_id": msg_id,
        "conversation_id": conv_id,
        "student_id": conv.get("student_id", ""),
        "role": "teacher",
        "content": reply_fields["teacher_response"],
        "teacher_response_rich": reply_fields["teacher_response_rich"],
        "teacher_response_format": reply_fields["teacher_response_format"],
        "created_at": now,
    })

    return TeacherNoteOut(
        id=note_id,
        note=reply_fields["teacher_response"],
        createdAt=now,
        teacher={"id": teacher_id, "name": teacher_name},
        richContent=reply_fields["teacher_response_rich"],
        responseFormat=reply_fields["teacher_response_format"],
    )
