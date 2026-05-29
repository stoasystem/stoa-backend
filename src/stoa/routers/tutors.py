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

import boto3
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from stoa.db.dynamodb import get_table
from stoa.db.repositories import user_repo
from stoa.deps import require_role

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


class UpdateStatusRequest(BaseModel):
    status: str
    resolutionNote: str | None = None


class AddNoteRequest(BaseModel):
    content: str


class TutorStats(BaseModel):
    pendingRequests: int
    resolvedToday: int
    averageResponseTimeMinutes: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/me/stats", response_model=TutorStats)
async def get_stats(user: dict = Depends(require_role("teacher", "tutor", "admin"))):
    escalated = _get_escalated_conversations()
    pending = sum(1 for c in escalated if c.get("escalation_status", "pending") == "pending")
    resolved_today_count = sum(
        1 for c in escalated
        if c.get("escalation_status") == "resolved"
        and c.get("escalation_resolved_at", "")[:10] == datetime.now(timezone.utc).date().isoformat()
    )
    return TutorStats(
        pendingRequests=pending,
        resolvedToday=resolved_today_count,
        averageResponseTimeMinutes=15,
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
        )
        for n in notes_resp.get("Items", [])
    ]

    # Mark first teacher access time
    if not conv.get("first_tutor_action_at"):
        try:
            table.update_item(
                Key={"PK": _conv_pk(conv_id), "SK": "CONV"},
                UpdateExpression="SET first_tutor_action_at = :t",
                ConditionExpression="attribute_not_exists(first_tutor_action_at)",
                ExpressionAttributeValues={":t": _now()},
            )
        except Exception:
            pass

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
        firstTutorActionAt=conv.get("first_tutor_action_at"),
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

    table.put_item(Item={
        "PK": _conv_pk(conv_id),
        "SK": f"NOTE#{note_id}",
        "note_id": note_id,
        "conversation_id": conv_id,
        "teacher_id": teacher_id,
        "teacher_name": teacher_name,
        "content": body.content,
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
        "content": body.content,
        "created_at": now,
    })

    return TutorNoteOut(
        id=note_id,
        note=body.content,
        createdAt=now,
        tutor={"id": teacher_id, "name": teacher_name},
    )
