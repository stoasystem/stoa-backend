"""Tutor/teacher routes — help-request queue, detail, status updates, notes.

Frontend API contract (tutorApi.ts):
  GET  /tutors/me/help-requests          list requests (teacher sees all pending)
  GET  /tutors/me/help-requests/{id}     detail + messages + notes
  PATCH /tutors/me/help-requests/{id}    update status
  POST /tutors/me/help-requests/{id}/notes  add a tutor note
  GET  /tutors/me/stats                  quick stats card
"""
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from stoa.db.dynamodb import get_table
from stoa.db.repositories import user_repo
from stoa.deps import require_role
from stoa.services import ai_teacher_tools_service, teacher_assistance_service, teacher_reply_service

router = APIRouter()


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


def _get_student_name(student_id: str) -> str:
    profile = user_repo.get_user(student_id)
    if profile:
        return profile.get("name") or profile.get("email", "Student")
    return "Student"


def _sla_snapshot(conv: dict) -> dict[str, int | str | None]:
    requested_at = _parse_time(conv.get("escalated_at") or conv.get("created_at"))
    first_action_at = _parse_time(conv.get("first_tutor_action_at"))
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

class TutorHelpRequestSummary(BaseModel):
    requestId: str
    conversationId: str
    studentName: str
    subject: str
    grade: str
    status: str
    requestMessage: str | None = None
    priority: str = "medium"
    createdAt: str
    firstTutorActionAt: str | None = None
    sla: dict | None = None


class MessageOut(BaseModel):
    id: str
    conversationId: str
    role: str
    content: str
    createdAt: str
    status: str = "sent"


class TutorNoteOut(BaseModel):
    id: str
    note: str
    createdAt: str
    tutor: dict
    richContent: dict | None = None
    responseFormat: str | None = None


class TutorHelpRequestDetail(BaseModel):
    requestId: str
    conversationId: str
    student: dict
    subject: str
    status: str
    requestMessage: str | None = None
    messages: list[MessageOut]
    notes: list[TutorNoteOut]
    firstTutorActionAt: str | None = None
    sla: dict | None = None


class UpdateStatusRequest(BaseModel):
    status: str
    resolutionNote: str | None = None


class AddNoteRequest(BaseModel):
    content: str
    richContent: dict[str, Any] | None = None


class TutorAvailabilitySlot(BaseModel):
    dayOfWeek: str
    startTime: str
    endTime: str


class TutorAvailability(BaseModel):
    weeklyAvailability: list[TutorAvailabilitySlot] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)


class TutorStats(BaseModel):
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


def _availability_response(profile: dict[str, Any] | None) -> TutorAvailability:
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
    return TutorAvailability(subjects=subjects, weeklyAvailability=slots)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/me/availability", response_model=TutorAvailability)
async def get_my_availability(user: dict = Depends(require_role("teacher", "tutor", "admin"))):
    """Return the current teacher availability profile used for dispatch."""
    return _availability_response(user_repo.get_user(user["sub"]))


@router.patch("/me/availability", response_model=TutorAvailability)
async def update_my_availability(
    body: TutorAvailability,
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
):
    """Persist teacher availability so student support status can reflect it."""
    updated = user_repo.update_tutor_availability(
        user["sub"],
        subjects=[subject.strip() for subject in body.subjects if subject.strip()],
        weekly_availability=[slot.model_dump() for slot in body.weeklyAvailability],
        updated_at=_now(),
    )
    return _availability_response(updated)


@router.get("/me/stats", response_model=TutorStats)
async def get_stats(user: dict = Depends(require_role("teacher", "tutor", "admin"))):
    escalated = _get_escalated_conversations()
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
    return TutorStats(
        pendingRequests=pending,
        resolvedToday=resolved_today_count,
        averageResponseTimeMinutes=round(sum(response_times) / len(response_times)) if response_times else 0,
    )


@router.get("/questions/{question_id}/assistance-summary", response_model=AssistanceSummaryResponse)
async def get_question_assistance_summary(
    question_id: str,
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
):
    """Build a bounded teacher assistance summary seed for an accessible question."""
    return teacher_assistance_service.build_summary_seed(question_id, user)


@router.post("/questions/{question_id}/ai-tools/summary-draft", response_model=AiTeacherDraftResponse)
async def create_question_summary_draft(
    question_id: str,
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
):
    """Create a reviewed AI teacher summary draft for an accessible question."""
    return ai_teacher_tools_service.create_summary_draft(question_id, user)


@router.post("/ai-tools/exercise-drafts", response_model=AiTeacherDraftResponse)
async def create_exercise_draft(
    body: ExerciseDraftRequest,
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
):
    """Create a reviewed practice exercise draft from tutor-visible learning context."""
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
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
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
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
):
    """Return one visible reviewed AI teacher tool draft."""
    return ai_teacher_tools_service.get_draft(draft_id, user)


@router.post("/ai-tools/drafts/{draft_id}/regenerate", response_model=AiTeacherDraftResponse)
async def regenerate_ai_teacher_draft(
    draft_id: str,
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
):
    """Create a new draft version while preserving prior draft metadata."""
    return ai_teacher_tools_service.regenerate_draft(draft_id, user)


@router.post("/ai-tools/drafts/{draft_id}/accept", response_model=AiTeacherDraftResponse)
async def accept_ai_teacher_draft(
    draft_id: str,
    body: ReviewDraftRequest | None = None,
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
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
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
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
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
):
    """Archive a draft from the active teacher workflow without deleting evidence."""
    return ai_teacher_tools_service.review_draft(
        draft_id=draft_id,
        action="archive",
        user=user,
        note=body.note if body else None,
    )


@router.get("/me/help-requests", response_model=dict)
async def list_help_requests(user: dict = Depends(require_role("teacher", "tutor", "admin"))):
    """Return all escalated conversations as help-request summaries."""
    escalated = _get_escalated_conversations()
    items = []
    for conv in sorted(escalated, key=lambda c: c.get("escalated_at", ""), reverse=True):
        conv_id = conv.get("conversation_id", "")
        student_name = _get_student_name(conv.get("student_id", ""))
        esc_status = conv.get("escalation_status", "pending")
        items.append(TutorHelpRequestSummary(
            requestId=conv.get("escalation_request_id", conv_id),
            conversationId=conv_id,
            studentName=student_name,
            subject=conv.get("subject", "General"),
            grade=conv.get("grade", ""),
            status=esc_status,
            requestMessage=conv.get("escalation_message"),
            createdAt=conv.get("escalated_at", conv.get("updated_at", _now())),
            firstTutorActionAt=conv.get("first_tutor_action_at"),
            sla=_sla_snapshot(conv),
        ).model_dump())
    return {"items": items}


@router.get("/me/help-requests/{request_id}", response_model=TutorHelpRequestDetail)
async def get_help_request(
    request_id: str,
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
):
    """Get full detail of a specific help request including conversation messages."""
    table = get_table()

    # request_id may be the conv_id or a dedicated escalation_request_id
    # Try by conv_id first, then scan by request_id field
    conv = _get_conversation(request_id)
    if not conv or not conv.get("escalated"):
        # Search by escalation_request_id
        escalated = _get_escalated_conversations()
        conv = next((c for c in escalated if c.get("escalation_request_id") == request_id), None)

    if not conv:
        raise HTTPException(status_code=404, detail="Help request not found")

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
        TutorNoteOut(
            id=n["note_id"],
            note=n["content"],
            createdAt=n["created_at"],
            tutor={"id": n.get("teacher_id", ""), "name": n.get("teacher_name", "Teacher")},
            richContent=n.get("teacher_response_rich"),
            responseFormat=n.get("teacher_response_format"),
        )
        for n in notes_resp.get("Items", [])
    ]

    # Mark first teacher access time
    first_tutor_action_at = conv.get("first_tutor_action_at")
    if not first_tutor_action_at:
        first_tutor_action_at = _now()
        try:
            table.update_item(
                Key={"PK": _conv_pk(conv_id), "SK": "CONV"},
                UpdateExpression="SET first_tutor_action_at = :t",
                ConditionExpression="attribute_not_exists(first_tutor_action_at)",
                ExpressionAttributeValues={":t": first_tutor_action_at},
            )
        except Exception:
            pass
        conv = {**conv, "first_tutor_action_at": first_tutor_action_at}

    return TutorHelpRequestDetail(
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
        firstTutorActionAt=first_tutor_action_at,
        sla=_sla_snapshot(conv),
    )


@router.patch("/me/help-requests/{request_id}", response_model=TutorHelpRequestSummary)
async def update_help_request(
    request_id: str,
    body: UpdateStatusRequest,
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
):
    """Update the status of a help request (pending → in_progress → resolved)."""
    table = get_table()
    conv = _get_conversation(request_id)
    if not conv or not conv.get("escalated"):
        escalated = _get_escalated_conversations()
        conv = next((c for c in escalated if c.get("escalation_request_id") == request_id), None)
    if not conv:
        raise HTTPException(status_code=404, detail="Help request not found")

    conv_id = conv.get("conversation_id", "")
    now = _now()
    update_parts = ["escalation_status = :s", "updated_at = :u"]
    expr_values: dict = {":s": body.status, ":u": now}
    if not conv.get("first_tutor_action_at"):
        update_parts.append("first_tutor_action_at = :f")
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
    return TutorHelpRequestSummary(
        requestId=conv.get("escalation_request_id", conv_id),
        conversationId=conv_id,
        studentName=student_name,
        subject=conv.get("subject", "General"),
        grade=conv.get("grade", ""),
        status=body.status,
        requestMessage=conv.get("escalation_message"),
        createdAt=conv.get("escalated_at", now),
        firstTutorActionAt=conv.get("first_tutor_action_at") or now,
        sla=_sla_snapshot({**conv, "first_tutor_action_at": conv.get("first_tutor_action_at") or now}),
    )


@router.post("/me/help-requests/{request_id}/notes", response_model=TutorNoteOut)
async def add_note(
    request_id: str,
    body: AddNoteRequest,
    user: dict = Depends(require_role("teacher", "tutor", "admin")),
):
    """Add a tutor note to a help request (stored in the conversation)."""
    table = get_table()
    conv = _get_conversation(request_id)
    if not conv or not conv.get("escalated"):
        escalated = _get_escalated_conversations()
        conv = next((c for c in escalated if c.get("escalation_request_id") == request_id), None)
    if not conv:
        raise HTTPException(status_code=404, detail="Help request not found")

    conv_id = conv.get("conversation_id", "")
    teacher_id = user["sub"]
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

    return TutorNoteOut(
        id=note_id,
        note=reply_fields["teacher_response"],
        createdAt=now,
        tutor={"id": teacher_id, "name": teacher_name},
        richContent=reply_fields["teacher_response_rich"],
        responseFormat=reply_fields["teacher_response_format"],
    )
