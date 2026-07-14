"""Conversation routes — multi-turn AI teaching sessions.


Implements the frontend chat API contract:
  GET  /conversations                        list conversations for current student
  POST /conversations                        create conversation
  GET  /conversations/{id}                   get conversation with messages
  POST /conversations/{id}/messages          send message → Bedrock AI reply
  POST /teacher-help/request                 escalate to teacher
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import boto3
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from stoa.config import settings
from stoa.deps import require_role
from stoa.db.dynamodb import get_table
from stoa.services import (
    ai_service,
    entitlement_service,
    teacher_dispatch_service,
    usage_ledger_service,
)
from stoa.services.rate_limit import check_and_record_chat

logger = logging.getLogger(__name__)

router = APIRouter()

# ── DynamoDB helpers ───────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conv_pk(conv_id: str) -> str:
    return f"CONV#{conv_id}"


def _msg_sk(msg_id: str) -> str:
    return f"MSG#{msg_id}"


def _list_conversations(student_id: str) -> list[dict]:
    table = get_table()
    resp = table.query(
        IndexName="GSI-StudentId",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("student_id").eq(student_id),
        FilterExpression=boto3.dynamodb.conditions.Attr("entity_type").eq("conversation"),
        ScanIndexForward=False,
    )
    return resp.get("Items", [])


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
    items = resp.get("Items", [])
    # Sort by creation time so teacher notes and system messages appear in chronological order
    return sorted(items, key=lambda x: x.get("created_at", ""))


def _chat_limit_for_student(student_id: str) -> int:
    entitlement = entitlement_service.resolve_student_entitlement(student_id, settings=settings)
    limits = entitlement.get("limits") or {}
    return int(limits.get("dailyChatMessageLimit") or settings.daily_chat_message_limit)


# ── Request / Response models ──────────────────────────────────────────────────

class CreateConversationRequest(BaseModel):
    subject: str
    grade: str
    initialMessage: str | None = None


class SendMessageRequest(BaseModel):
    content: str
    attachmentIds: list[str] | None = None


class ChatMessage(BaseModel):
    id: str
    conversationId: str
    role: str
    content: str
    createdAt: str
    status: str = "sent"


class SendMessageResponse(BaseModel):
    studentMessage: ChatMessage
    assistantMessage: ChatMessage


class ConversationSummary(BaseModel):
    id: str
    title: str
    subject: str
    grade: str
    updatedAt: str
    lastMessagePreview: str | None = None


class ConversationDetail(ConversationSummary):
    messages: list[ChatMessage]


class ConversationListResponse(BaseModel):
    items: list[ConversationSummary]


class TeacherHelpRequest(BaseModel):
    conversationId: str
    message: str | None = None


class TeacherHelpResponse(BaseModel):
    requestId: str
    conversationId: str
    status: str = "pending"
    teacherName: str | None = None
    createdAt: str
    updatedAt: str | None = None


class TeacherAvailabilityResponse(BaseModel):
    online: bool
    availableTeachers: int
    nextWindow: str | None = None
    responseTime: str | None = None


def _generate_title(first_message: str, subject: str) -> str | None:
    """Call Bedrock to generate a short conversation title (max 6 words)."""
    try:
        import json as _json

        from stoa.config import get_settings

        settings = get_settings()
        bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        prompt = (
            f"Generate a concise title (max 6 words, no punctuation) for a {subject} "
            f"teaching conversation that starts with: \"{first_message[:120]}\". "
            "Respond with only the title, nothing else."
        )
        body = _json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 30,
            "messages": [{"role": "user", "content": prompt}],
        })
        resp = bedrock.invoke_model(
            modelId=settings.bedrock_model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = _json.loads(resp["body"].read())
        title = result["content"][0]["text"].strip().strip('"').strip("'")
        return title[:80] if title else None
    except Exception as exc:
        logger.warning("Title generation failed: %s", exc)
        return None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=ConversationListResponse)
async def list_conversations(user: dict = Depends(require_role("student"))):
    student_id = user["sub"]
    items = _list_conversations(student_id)
    summaries = [
        ConversationSummary(
            id=item["conversation_id"],
            title=item.get("title", item.get("subject", "")),
            subject=item.get("subject", ""),
            grade=item.get("grade", ""),
            updatedAt=item.get("updated_at", item.get("created_at", _now())),
            lastMessagePreview=item.get("last_message_preview"),
        )
        for item in items
    ]
    return ConversationListResponse(items=summaries)


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: CreateConversationRequest,
    user: dict = Depends(require_role("student")),
):
    student_id = user["sub"]
    conv_id = str(uuid.uuid4())
    now = _now()
    title = f"{body.subject} – {body.grade}"

    table = get_table()
    conv_item = {
        "PK": _conv_pk(conv_id),
        "SK": "CONV",
        "conversation_id": conv_id,
        "student_id": student_id,
        "entity_type": "conversation",
        "subject": body.subject,
        "grade": body.grade,
        "title": title,
        "created_at": now,
        "updated_at": now,
    }
    table.put_item(Item=conv_item)

    messages: list[ChatMessage] = []

    # If an initial message was provided, immediately get an AI reply
    if body.initialMessage:
        usage_counter = check_and_record_chat(student_id, limit=_chat_limit_for_student(student_id))
        student_msg, assistant_msg = _send_message_impl(
            conv_id=conv_id,
            student_id=student_id,
            subject=body.subject,
            grade=body.grade,
            content=body.initialMessage,
            table=table,
        )
        _record_chat_usage(
            student_id=student_id,
            conv_id=conv_id,
            student_message_id=student_msg.id,
            subject=body.subject,
            grade=body.grade,
            usage_counter=usage_counter,
            created_at=student_msg.createdAt,
        )
        messages = [student_msg, assistant_msg]

    return ConversationDetail(
        id=conv_id,
        title=title,
        subject=body.subject,
        grade=body.grade,
        updatedAt=now,
        messages=messages,
    )


@router.get("/{conv_id}", response_model=ConversationDetail)
async def get_conversation(
    conv_id: str,
    user: dict = Depends(require_role("student")),
):
    student_id = user["sub"]
    conv = _get_conversation(conv_id)
    if not conv or conv.get("student_id") != student_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    raw_messages = _get_messages(conv_id)
    messages = [
        ChatMessage(
            id=m["message_id"],
            conversationId=conv_id,
            role=m["role"],
            content=m["content"],
            createdAt=m["created_at"],
            status="sent",
        )
        for m in raw_messages
    ]

    return ConversationDetail(
        id=conv_id,
        title=conv.get("title", ""),
        subject=conv.get("subject", ""),
        grade=conv.get("grade", ""),
        updatedAt=conv.get("updated_at", _now()),
        messages=messages,
    )


@router.post("/{conv_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conv_id: str,
    body: SendMessageRequest,
    user: dict = Depends(require_role("student")),
):
    student_id = user["sub"]
    conv = _get_conversation(conv_id)
    if not conv or conv.get("student_id") != student_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    usage_counter = check_and_record_chat(student_id, limit=_chat_limit_for_student(student_id))
    table = get_table()
    student_msg, assistant_msg = _send_message_impl(
        conv_id=conv_id,
        student_id=student_id,
        subject=conv.get("subject", "math"),
        grade=conv.get("grade", ""),
        content=body.content,
        table=table,
    )
    _record_chat_usage(
        student_id=student_id,
        conv_id=conv_id,
        student_message_id=student_msg.id,
        subject=conv.get("subject", "math"),
        grade=conv.get("grade", ""),
        usage_counter=usage_counter,
        created_at=student_msg.createdAt,
    )
    return SendMessageResponse(studentMessage=student_msg, assistantMessage=assistant_msg)


@router.post("/{conv_id}/messages/stream")
async def stream_message(
    conv_id: str,
    body: SendMessageRequest,
    user: dict = Depends(require_role("student")),
):
    """Send a message and stream the AI reply as Server-Sent Events.

    API Gateway buffers the full response before sending, so this is
    pseudo-streaming: the client receives all SSE events at once, but
    the SSE parser handles them correctly and the UI updates as expected.
    """
    student_id = user["sub"]
    conv = _get_conversation(conv_id)
    if not conv or conv.get("student_id") != student_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    usage_counter = check_and_record_chat(student_id, limit=_chat_limit_for_student(student_id))
    table = get_table()
    student_msg, assistant_msg = _send_message_impl(
        conv_id=conv_id,
        student_id=student_id,
        subject=conv.get("subject", "math"),
        grade=conv.get("grade", ""),
        content=body.content,
        table=table,
    )
    _record_chat_usage(
        student_id=student_id,
        conv_id=conv_id,
        student_message_id=student_msg.id,
        subject=conv.get("subject", "math"),
        grade=conv.get("grade", ""),
        usage_counter=usage_counter,
        created_at=student_msg.createdAt,
    )

    def _sse(event_type: str, data: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    def generate():
        yield _sse("message_start", {
            "messageId": assistant_msg.id,
            "role": "assistant",
            "createdAt": assistant_msg.createdAt,
        })
        # Split content into ~100-char chunks so the frontend can render
        # progressively if it ever gains true streaming support.
        chunk_size = 100
        content = assistant_msg.content
        for i in range(0, len(content), chunk_size):
            yield _sse("message_delta", {
                "messageId": assistant_msg.id,
                "delta": content[i:i + chunk_size],
            })
        yield _sse("message_done", {
            "messageId": assistant_msg.id,
            "status": "completed",
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _send_message_impl(
    conv_id: str,
    student_id: str,
    subject: str,
    grade: str,
    content: str,
    table,
) -> tuple[ChatMessage, ChatMessage]:
    """Persist student message, call Bedrock, persist AI reply. Returns both messages."""
    now = _now()
    student_msg_id = str(uuid.uuid4())
    assistant_msg_id = str(uuid.uuid4())

    # Map frontend subject names to AI service expected values
    subject_map = {
        "Mathematics": "math", "Mathematik": "math", "math": "math",
        "Physics": "physics", "Physik": "physics", "physics": "physics",
        "German": "german", "Deutsch": "german", "german": "german",
        "English": "english", "english": "english",
        "French": "french", "Französisch": "french", "french": "french",
    }
    normalized_subject = subject_map.get(subject, "math")

    # Fetch conversation history BEFORE saving the new message so the model
    # sees the prior turns (student + assistant only; teacher/system excluded).
    prior_messages = _get_messages(conv_id)

    # Save student message
    table.put_item(Item={
        "PK": _conv_pk(conv_id),
        "SK": _msg_sk(student_msg_id),
        "message_id": student_msg_id,
        "conversation_id": conv_id,
        "student_id": student_id,
        "role": "student",
        "content": content,
        "created_at": now,
    })

    # Call Bedrock AI with full conversation history for multi-turn context
    try:
        ai_result = ai_service.get_ai_answer(
            content=content,
            subject=normalized_subject,
            grade=grade,
            language="de",
            history=prior_messages,
        )
        # Format AI response as human-readable text
        steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(ai_result.get("steps", [])))
        answer_text = ai_result.get("answer", "")
        hints = ai_result.get("hints", [])
        hint_text = ("\n\n**Hinweis:** " + hints[0]) if hints else ""
        ai_content = f"{steps_text}\n\n{answer_text}{hint_text}".strip()
        if not ai_content:
            ai_content = answer_text or "Entschuldigung, ich konnte keine Antwort generieren."
    except Exception as ai_err:
        logger.error("Bedrock AI call failed: %s: %s", type(ai_err).__name__, ai_err)
        err_str = str(ai_err)
        if "use case details" in err_str or "ResourceNotFound" in type(ai_err).__name__:
            # Bedrock access not yet approved — use a structured placeholder
            ai_content = (
                f"Ich helfe dir gerne mit deiner Frage zur {subject}! "
                "Unser KI-System wird gerade eingerichtet und ist in Kürze verfügbar. "
                "Für sofortige Hilfe kannst du die 'Lehrer fragen' Funktion nutzen."
            )
        else:
            ai_content = "Es gab ein technisches Problem. Bitte versuche es nochmals oder frage deinen Lehrer."

    # Save AI message
    table.put_item(Item={
        "PK": _conv_pk(conv_id),
        "SK": _msg_sk(assistant_msg_id),
        "message_id": assistant_msg_id,
        "conversation_id": conv_id,
        "student_id": student_id,
        "role": "assistant",
        "content": ai_content,
        "created_at": _now(),
    })

    # Auto-generate title on first message
    auto_title: str | None = None
    try:
        existing = _get_messages(conv_id)
        # 2 messages = this student + this assistant message (just saved above)
        if len(existing) <= 2:
            auto_title = _generate_title(content, subject)
    except Exception:
        pass

    # Update conversation's updated_at + last_message_preview (+ title if first message)
    try:
        update_expr = "SET updated_at = :u, last_message_preview = :p"
        expr_values: dict = {
            ":u": _now(),
            ":p": (ai_content[:80] + "…") if len(ai_content) > 80 else ai_content,
        }
        if auto_title:
            update_expr += ", title = :t"
            expr_values[":t"] = auto_title
        table.update_item(
            Key={"PK": _conv_pk(conv_id), "SK": "CONV"},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
        )
    except Exception:
        pass

    return (
        ChatMessage(id=student_msg_id, conversationId=conv_id, role="student",
                    content=content, createdAt=now, status="sent"),
        ChatMessage(id=assistant_msg_id, conversationId=conv_id, role="assistant",
                    content=ai_content, createdAt=_now(), status="sent"),
    )


def _record_chat_usage(
    *,
    student_id: str,
    conv_id: str,
    student_message_id: str,
    subject: str,
    grade: str,
    usage_counter: dict,
    created_at: str,
) -> None:
    usage_ledger_service.record_usage_event(
        student_id=student_id,
        action=usage_ledger_service.CHAT_MESSAGE_ACTION,
        quota_period=usage_counter["quotaPeriod"],
        idempotency_key=usage_ledger_service.build_usage_idempotency_key(
            action=usage_ledger_service.CHAT_MESSAGE_ACTION,
            resource_id=student_message_id,
        ),
        counter_key=usage_counter["counterKey"],
        counter_value=usage_counter["counterValue"],
        request_correlation_id=student_message_id,
        created_at=created_at,
        metadata={
            "conversation_id": conv_id,
            "request_id": student_message_id,
            "subject": subject,
            "grade_level": grade,
            "status": "sent",
        },
    )


# ── Teacher-help router (separate prefix: /teacher-help) ──────────────────────

teacher_help_router = APIRouter()


@teacher_help_router.get("/availability", response_model=TeacherAvailabilityResponse)
async def get_teacher_help_availability(
    user: dict = Depends(require_role("student")),
):
    """Return student-safe teacher availability for the chat indicator."""
    return teacher_dispatch_service.teacher_availability_summary()


@teacher_help_router.post("/request", response_model=TeacherHelpResponse)
async def request_teacher_help(
    body: TeacherHelpRequest,
    user: dict = Depends(require_role("student")),
):
    """Escalate a conversation to a human teacher."""
    student_id = user["sub"]
    request_id = str(uuid.uuid4())
    now = _now()

    table = get_table()
    conv = _get_conversation(body.conversationId)
    if not conv or conv.get("student_id") != student_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Mark conversation as escalated with request metadata
    try:
        table.update_item(
            Key={"PK": _conv_pk(body.conversationId), "SK": "CONV"},
            UpdateExpression=(
                "SET escalated = :e, escalated_at = :t, "
                "escalation_request_id = :r, escalation_status = :s"
                + (", escalation_message = :m" if body.message else "")
            ),
            ExpressionAttributeValues={
                ":e": True, ":t": now, ":r": request_id, ":s": "pending",
                **({":m": body.message} if body.message else {}),
            },
        )
    except Exception:
        pass

    # Save escalation request as a system message
    table.put_item(Item={
        "PK": _conv_pk(body.conversationId),
        "SK": _msg_sk(request_id),
        "message_id": request_id,
        "conversation_id": body.conversationId,
        "student_id": student_id,
        "role": "system",
        "content": f"Teacher help requested. {body.message or ''}".strip(),
        "created_at": now,
    })

    usage_ledger_service.record_usage_event(
        student_id=student_id,
        action=usage_ledger_service.CONVERSATION_TEACHER_HELP_ACTION,
        quota_period=usage_ledger_service.today_period(),
        idempotency_key=usage_ledger_service.build_usage_idempotency_key(
            action=usage_ledger_service.CONVERSATION_TEACHER_HELP_ACTION,
            resource_id=body.conversationId,
            qualifier=request_id,
        ),
        request_correlation_id=request_id,
        created_at=now,
        metadata={
            "conversation_id": body.conversationId,
            "request_id": request_id,
            "subject": conv.get("subject"),
            "grade_level": conv.get("grade"),
            "status": "pending",
        },
    )

    return TeacherHelpResponse(
        requestId=request_id,
        conversationId=body.conversationId,
        status="pending",
        createdAt=now,
        updatedAt=now,
    )
