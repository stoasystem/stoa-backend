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
from dataclasses import dataclass
from datetime import datetime, timezone

import boto3
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from stoa.config import settings
from stoa.db.repositories.security_audit_repo import AuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.db.dynamodb import get_table
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    AuthorizedResource,
    ResourceType,
)
from stoa.security.identity import Actor
from stoa.models.attachment import AttachmentReference, AttachmentSummary
from stoa.security.attachment_errors import AttachmentDecisionError
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.route_authorization import (
    CONVERSATION_CONTENT_READ,
    STUDENT_SELF,
    authorize_conversation_resource,
    authorized_conversation_dependency,
    get_authorization_fact_repository,
    student_actor_dependency,
    student_create_actor_dependency,
)
from stoa.services import (
    ai_service,
    entitlement_service,
    teacher_dispatch_service,
    usage_ledger_service,
    attachment_service,
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


def _attachment_plan_for_student(student_id: str) -> str:
    entitlement = entitlement_service.resolve_student_entitlement(student_id, settings=settings)
    return str(entitlement.get("effectivePlan") or "free")


# ── Request / Response models ──────────────────────────────────────────────────

class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    grade: str
    initialMessage: str | None = None


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    attachmentIds: list[AttachmentReference] | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def unique_attachments(self) -> "SendMessageRequest":
        if self.attachmentIds is not None and not self.attachmentIds:
            raise ValueError("attachmentIds must be omitted or contain at least one reference")
        identities = [reference.identity for reference in self.attachmentIds or []]
        if len(identities) != len(set(identities)):
            raise ValueError("attachment references must be unique")
        return self


@dataclass(frozen=True, slots=True)
class PreparedMessageAttachments:
    actor: Actor
    items: list[tuple[str, dict]]
    effective_plan: str


async def _message_attachment_dependency(
    body: SendMessageRequest,
    actor: Actor = Depends(get_actor),
    correlation_id: str = Depends(get_request_correlation_id),
) -> PreparedMessageAttachments:
    try:
        prepared = attachment_service.prepare_message_attachments(
            body.attachmentIds or [], actor
        )
        effective_plan = "free"
        if body.attachmentIds:
            effective_plan = _attachment_plan_for_student(actor.user_id)
            attachment_service.ensure_message_attachment_capacity(
                prepared, actor.user_id, effective_plan
            )
        return PreparedMessageAttachments(actor, prepared, effective_plan)
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)


async def _attachment_inventory_resolver(resource_id: str):
    return {"student_id": resource_id}


_message_attachment_dependency.authorization_specs = (  # type: ignore[attr-defined]
    AuthorizationSpec(
        ResourceType.UPLOAD,
        AuthorizationAction.UPDATE,
        AuthorizationPurpose.SELF_SERVICE,
        _attachment_inventory_resolver,
    ),
    AuthorizationSpec(
        ResourceType.ATTACHMENT,
        AuthorizationAction.READ,
        AuthorizationPurpose.SELF_SERVICE,
        _attachment_inventory_resolver,
    ),
)


class ChatMessage(BaseModel):
    id: str
    conversationId: str
    role: str
    content: str
    createdAt: str
    status: str = "sent"
    attachments: list[AttachmentSummary] = Field(default_factory=list)


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
    model_config = ConfigDict(extra="forbid")

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
async def list_conversations(
    actor: Actor = Depends(
        student_actor_dependency(ResourceType.CONVERSATION, AuthorizationAction.READ)
    ),
):
    student_id = actor.user_id
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
    actor: Actor = Depends(student_create_actor_dependency(ResourceType.CONVERSATION)),
):
    student_id = actor.user_id
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
            actor=actor,
            prepared_attachments=[],
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
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.READ,
            purposes=CONVERSATION_CONTENT_READ,
            resolver=lambda conversation_id: _get_conversation(conversation_id),
        )
    ),
):
    conv_id = authorized.ref.resource_id
    conv = authorized.value

    raw_messages = _get_messages(conv_id)
    attachment_ids = [value for message in raw_messages for value in message.get("attachment_ids", [])]
    attachment_summaries = attachment_service.list_attachment_summaries(attachment_ids)
    messages = [
        ChatMessage(
            id=m["message_id"],
            conversationId=conv_id,
            role=m["role"],
            content=m["content"],
            createdAt=m["created_at"],
            status="sent",
            attachments=[
                attachment_summaries[value]
                for value in m.get("attachment_ids", [])
                if value in attachment_summaries
            ],
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
    body: SendMessageRequest,
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.RESPOND,
            purposes=STUDENT_SELF,
            resolver=lambda conversation_id: _get_conversation(conversation_id),
        )
    ),
    attachment_command: PreparedMessageAttachments = Depends(
        _message_attachment_dependency
    ),
    correlation_id: str = Depends(get_request_correlation_id),
):
    conv_id = authorized.ref.resource_id
    student_id = authorized.ref.student_id
    conv = authorized.value

    actor = attachment_command.actor
    prepared = attachment_command.items
    effective_plan = attachment_command.effective_plan
    usage_counter = check_and_record_chat(student_id, limit=_chat_limit_for_student(student_id))
    table = get_table()
    try:
        student_msg, assistant_msg = _send_message_impl(
            conv_id=conv_id,
            student_id=student_id,
            subject=conv.get("subject", "math"),
            grade=conv.get("grade", ""),
            content=body.content,
            actor=actor,
            prepared_attachments=prepared,
            effective_plan=effective_plan,
            table=table,
        )
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)
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
    body: SendMessageRequest,
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.RESPOND,
            purposes=STUDENT_SELF,
            resolver=lambda conversation_id: _get_conversation(conversation_id),
        )
    ),
    attachment_command: PreparedMessageAttachments = Depends(
        _message_attachment_dependency
    ),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Send a message and stream the AI reply as Server-Sent Events.

    API Gateway buffers the full response before sending, so this is
    pseudo-streaming: the client receives all SSE events at once, but
    the SSE parser handles them correctly and the UI updates as expected.
    """
    conv_id = authorized.ref.resource_id
    student_id = authorized.ref.student_id
    conv = authorized.value

    actor = attachment_command.actor
    prepared = attachment_command.items
    effective_plan = attachment_command.effective_plan
    usage_counter = check_and_record_chat(student_id, limit=_chat_limit_for_student(student_id))
    table = get_table()
    try:
        student_msg, assistant_msg = _send_message_impl(
            conv_id=conv_id,
            student_id=student_id,
            subject=conv.get("subject", "math"),
            grade=conv.get("grade", ""),
            content=body.content,
            actor=actor,
            prepared_attachments=prepared,
            effective_plan=effective_plan,
            table=table,
        )
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)
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
        yield _sse("student_message", student_msg.model_dump(mode="json", by_alias=True))
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
    actor: Actor,
    prepared_attachments: list[tuple[str, dict]] | None = None,
    effective_plan: str | None = None,
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

    student_item = {
        "PK": _conv_pk(conv_id),
        "SK": _msg_sk(student_msg_id),
        "message_id": student_msg_id,
        "conversation_id": conv_id,
        "student_id": student_id,
        "role": "student",
        "content": content,
        "created_at": now,
    }
    effective_plan = effective_plan or _attachment_plan_for_student(student_id)
    attachments = attachment_service.bind_message_attachments(
        message=student_item,
        conversation_id=conv_id,
        actor=actor,
        prepared=prepared_attachments or [],
        effective_plan=str(effective_plan),
    )
    attachment_context = ""
    if prepared_attachments:
        attachment_context = attachment_service.extract_message_attachment_context(
            prepared_attachments,
            s3=boto3.client("s3", region_name=settings.aws_region),
            settings=settings,
        )

    # Call Bedrock AI with full conversation history for multi-turn context
    try:
        ai_result = ai_service.get_ai_answer(
            content=content,
            subject=normalized_subject,
            grade=grade,
            language="de",
            history=prior_messages,
            attachment_context=attachment_context,
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
                    content=content, createdAt=now, status="sent", attachments=attachments),
        ChatMessage(id=assistant_msg_id, conversationId=conv_id, role="assistant",
                    content=ai_content, createdAt=_now(), status="sent"),
    )


def _raise_attachment(error: AttachmentDecisionError, correlation_id: str) -> None:
    error.correlation_id = correlation_id
    raise HTTPException(
        status_code=error.status_code,
        detail=error.public_body(),
        headers={"X-Correlation-ID": correlation_id},
    ) from error


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


async def _teacher_help_conversation_dependency(
    body: TeacherHelpRequest,
    actor: Actor = Depends(get_actor),
    facts=Depends(get_authorization_fact_repository),
    correlation_id: str = Depends(get_request_correlation_id),
    audit_sink: AuthorizationAuditSink = Depends(get_authorization_audit_sink),
) -> AuthorizedResource:
    return await authorize_conversation_resource(
        conversation_id=body.conversationId,
        actor=actor,
        facts=facts,
        correlation_id=correlation_id,
        audit_sink=audit_sink,
        action=AuthorizationAction.UPDATE,
        purposes=STUDENT_SELF,
        resolver=_get_conversation,
    )


async def _teacher_help_conversation_metadata_resolver(conversation_id: str):
    return _get_conversation(conversation_id)


_teacher_help_conversation_dependency.authorization_specs = (
    AuthorizationSpec(
        ResourceType.CONVERSATION,
        AuthorizationAction.UPDATE,
        AuthorizationPurpose.SELF_SERVICE,
        _teacher_help_conversation_metadata_resolver,
    ),
)


@teacher_help_router.get("/availability", response_model=TeacherAvailabilityResponse)
async def get_teacher_help_availability(
    _actor: Actor = Depends(
        student_actor_dependency(ResourceType.CONVERSATION, AuthorizationAction.LOOKUP)
    ),
):
    """Return student-safe teacher availability for the chat indicator."""
    return teacher_dispatch_service.teacher_availability_summary()


@teacher_help_router.post("/request", response_model=TeacherHelpResponse)
async def request_teacher_help(
    body: TeacherHelpRequest,
    authorized: AuthorizedResource = Depends(_teacher_help_conversation_dependency),
):
    """Escalate a conversation to a human teacher."""
    student_id = authorized.ref.student_id
    request_id = str(uuid.uuid4())
    now = _now()

    table = get_table()
    conv = authorized.value

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
