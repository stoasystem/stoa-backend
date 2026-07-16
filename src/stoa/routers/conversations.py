"""Conversation routes — multi-turn AI teaching sessions.


Implements the frontend chat API contract:
  GET  /conversations                        list conversations for current student
  POST /conversations                        create conversation
  GET  /conversations/{id}                   get conversation with messages
  POST /conversations/{id}/messages          send message → Bedrock AI reply
  POST /teacher-help/request                 escalate to teacher
"""
import json
import hashlib
import logging
import struct
import time
import uuid
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

import boto3
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from stoa.config import settings
from stoa.db.repositories.security_audit_repo import AuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.db.dynamodb import get_table
from stoa.db.repositories import attachment_repo
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    AuthorizedResource,
    ResourceType,
)
from stoa.security.identity import Actor
from stoa.models.attachment import AttachmentReference, AttachmentSummary
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.private_telemetry import emit_private_event
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
    idempotencyKey: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._~-]+$")
    attachmentIds: list[AttachmentReference] | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def unique_attachments(self) -> "SendMessageRequest":
        if self.attachmentIds is not None and not self.attachmentIds:
            raise ValueError("attachmentIds must be omitted or contain at least one reference")
        identities = [reference.identity for reference in self.attachmentIds or []]
        if len(identities) != len(set(identities)):
            raise ValueError("attachment references must be unique")
        return self


async def _message_command_dependency(
    conv_id: str,
    body: SendMessageRequest,
    actor: Actor = Depends(get_actor),
    correlation_id: str = Depends(get_request_correlation_id),
) -> dict:
    """Stage A: compute and compare the command before attachment resolution."""
    fingerprint = message_request_fingerprint(body)
    existing = attachment_repo.get_message_command(conv_id, body.idempotencyKey)
    if existing and existing.get("owner_id") != actor.user_id:
        existing = None
    if existing and existing.get("fingerprint") != fingerprint:
        _raise_attachment(
            AttachmentDecisionError(AttachmentErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT),
            correlation_id,
        )
    return {"actor": actor, "fingerprint": fingerprint, "existing": existing}


async def _attachment_inventory_resolver(resource_id: str):
    return {"student_id": resource_id}


_message_command_dependency.authorization_specs = (  # type: ignore[attr-defined]
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


def message_request_fingerprint(body: SendMessageRequest) -> str:
    """Canonical v1 fingerprint over exact UTF-8 content and ordered typed IDs."""
    content = body.content.encode("utf-8")
    framed = bytearray(b"stoa.conversation.send.v1")
    framed.extend(struct.pack(">I", len(content)))
    framed.extend(content)
    references = body.attachmentIds or []
    framed.extend(struct.pack(">I", len(references)))
    for reference in references:
        type_byte = b"\x01" if reference.upload_id is not None else b"\x02"
        opaque_id = str(reference.upload_id or reference.attachment_id).encode("utf-8")
        framed.extend(type_byte)
        framed.extend(struct.pack(">I", len(opaque_id)))
        framed.extend(opaque_id)
    return hashlib.sha256(bytes(framed)).hexdigest()


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


def _generate_title(
    first_message: str, subject: str, *, correlation_id: str | None = None
) -> str | None:
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
        emit_private_event(
            "title_generation_failed",
            exception=exc,
            input_size=len(first_message),
            correlation_id=correlation_id,
            level=logging.WARNING,
        )
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
    message_command: dict = Depends(_message_command_dependency),
    correlation_id: str = Depends(get_request_correlation_id),
):
    conv_id = authorized.ref.resource_id
    student_id = authorized.ref.student_id
    conv = authorized.value

    try:
        result = _execute_message_command(
            conv_id=conv_id,
            student_id=student_id,
            subject=conv.get("subject", "math"),
            grade=conv.get("grade", ""),
            body=body,
            command_context=message_command,
        )
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)
    return result


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
    message_command: dict = Depends(_message_command_dependency),
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

    try:
        result = _execute_message_command(
            conv_id=conv_id,
            student_id=student_id,
            subject=conv.get("subject", "math"),
            grade=conv.get("grade", ""),
            body=body,
            command_context=message_command,
        )
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)
    student_msg = result.studentMessage
    assistant_msg = result.assistantMessage

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


_MESSAGE_POLL_ATTEMPTS = 20
_MESSAGE_POLL_SECONDS = 0.05
_AI_LEASE_SECONDS = 120


def _completed_command_response(command: dict) -> SendMessageResponse | None:
    if command.get("status") != "completed" or not command.get("result_json"):
        return None
    try:
        return SendMessageResponse.model_validate_json(str(command["result_json"]))
    except (ValueError, TypeError):
        return None


def _wait_for_message_command(
    conversation_id: str,
    idempotency_key: str,
    fingerprint: str,
    *,
    table,
) -> SendMessageResponse:
    for _ in range(_MESSAGE_POLL_ATTEMPTS):
        command = attachment_repo.get_message_command(
            conversation_id, idempotency_key, table=table
        )
        if command and command.get("fingerprint") != fingerprint:
            raise AttachmentDecisionError(
                AttachmentErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT
            )
        if command and (result := _completed_command_response(command)) is not None:
            return result
        time.sleep(_MESSAGE_POLL_SECONDS)
    emit_private_event(
        "message_replay_wait_exhausted",
        correlation_id=str((command or {}).get("command_id") or "message-command"),
        level=logging.WARNING,
    )
    raise AttachmentDecisionError(AttachmentErrorCode.MESSAGE_IN_PROGRESS)


def _execute_message_command(
    *,
    conv_id: str,
    student_id: str,
    subject: str,
    grade: str,
    body: SendMessageRequest,
    command_context: dict,
) -> SendMessageResponse:
    """Run the shared regular/SSE command through claim, message, and AI fences."""
    actor: Actor = command_context["actor"]
    fingerprint = str(command_context["fingerprint"])
    table = get_table()
    existing = command_context.get("existing")
    if existing and (result := _completed_command_response(existing)) is not None:
        return result
    if existing and existing.get("status") == "ai_running":
        if int(existing.get("expiresAt", 0)) > int(datetime.now(timezone.utc).timestamp()):
            return _wait_for_message_command(
                conv_id, body.idempotencyKey, fingerprint, table=table
            )
    if existing and existing.get("status") == "terminal_failed":
        raise AttachmentDecisionError(AttachmentErrorCode.MESSAGE_IN_PROGRESS)

    command_id = str(
        uuid5(NAMESPACE_URL, f"stoa.conversation.send.v1:{conv_id}:{body.idempotencyKey}")
    )
    student_msg_id = str(uuid5(UUID(command_id), "student-message"))
    assistant_msg_id = str(uuid5(UUID(command_id), "assistant-message"))
    created_at = str(existing.get("created_at")) if existing else _now()
    command = existing or {
        "entity_type": "message_command",
        "command_id": command_id,
        "conversation_id": conv_id,
        "owner_id": student_id,
        "idempotency_key": body.idempotencyKey,
        "fingerprint": fingerprint,
        "status": "claimed",
        "student_message_id": student_msg_id,
        "assistant_message_id": assistant_msg_id,
        "attachment_count": len(body.attachmentIds or []),
        "attempt": 0,
        "created_at": created_at,
    }

    quota_period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    quota_limit = _chat_limit_for_student(student_id)
    resume_after_message = bool(
        existing and existing.get("status") in {"message_committed", "ai_running"}
    )
    prior_messages: list[dict] = []
    if resume_after_message:
        prior_messages = [
            item for item in _get_messages(conv_id) if item.get("message_id") != student_msg_id
        ]
        stored_student = table.get_item(
            Key={"PK": _conv_pk(conv_id), "SK": _msg_sk(student_msg_id)},
            ConsistentRead=True,
        ).get("Item")
        if not stored_student:
            raise AttachmentDecisionError(AttachmentErrorCode.MESSAGE_IN_PROGRESS)
        attachment_ids = list(stored_student.get("attachment_ids", []))
        stored_attachments = attachment_repo.get_attachments(attachment_ids, table=table)
        prepared = [
            ("attachment", stored_attachments[value])
            for value in attachment_ids
            if value in stored_attachments
        ]
        attachments = attachment_service.attachment_summaries_for_records(
            attachment_ids, stored_attachments
        )
        counter_value = int(existing.get("counter_value", 1))
    else:
        # Stage B is entered only for an absent command, or to resume a claimed
        # command lost before its deterministic message transaction.
        prepared = attachment_service.prepare_message_attachments(
            body.attachmentIds or [], actor
        )
        effective_plan = "free"
        if body.attachmentIds:
            effective_plan = _attachment_plan_for_student(student_id)
            attachment_service.ensure_message_attachment_capacity(
                prepared, student_id, effective_plan
            )
        prior_messages = _get_messages(conv_id)
        if not existing:
            claimed, counter_value = attachment_repo.claim_message_command_and_quota(
                command=command,
                owner_id=student_id,
                quota_period=quota_period,
                limit=quota_limit,
                expires_at=int(datetime.now(timezone.utc).timestamp()) + 172800,
                table=table,
            )
            if not claimed:
                raced = attachment_repo.get_message_command(
                    conv_id, body.idempotencyKey, table=table
                )
                if raced:
                    if raced.get("fingerprint") != fingerprint:
                        raise AttachmentDecisionError(
                            AttachmentErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT
                        )
                    return _wait_for_message_command(
                        conv_id, body.idempotencyKey, fingerprint, table=table
                    )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Daily chat message limit ({quota_limit}) reached. Try again tomorrow."
                    ),
                )
        else:
            counter_value = int(existing.get("counter_value", 1))
        student_item = {
            "PK": _conv_pk(conv_id),
            "SK": _msg_sk(student_msg_id),
            "message_id": student_msg_id,
            "conversation_id": conv_id,
            "student_id": student_id,
            "role": "student",
            "content": body.content,
            "created_at": created_at,
        }
        deterministic_attachment_ids = [
            str(uuid5(UUID(command_id), f"attachment:{index}"))
            for index, (kind, _) in enumerate(prepared)
            if kind == "upload"
        ]
        try:
            attachments = attachment_service.bind_message_attachments(
                message=student_item,
                conversation_id=conv_id,
                actor=actor,
                prepared=prepared,
                effective_plan=effective_plan,
                command=command,
                deterministic_attachment_ids=deterministic_attachment_ids,
            )
        except AttachmentDecisionError:
            raced = attachment_repo.get_message_command(
                conv_id, body.idempotencyKey, table=table
            )
            if raced and raced.get("fingerprint") == fingerprint:
                return _wait_for_message_command(
                    conv_id, body.idempotencyKey, fingerprint, table=table
                )
            raise

    usage_counter = {
        "quotaPeriod": quota_period,
        "counterKey": f"USAGE#{student_id}/CHAT#{quota_period}",
        "counterValue": counter_value,
    }
    _record_chat_usage(
        student_id=student_id,
        conv_id=conv_id,
        student_message_id=student_msg_id,
        subject=subject,
        grade=grade,
        usage_counter=usage_counter,
        created_at=created_at,
    )

    lease_owner = str(uuid.uuid4())
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    lease_claimed, _attempt = attachment_repo.claim_message_ai_lease(
        conversation_id=conv_id,
        idempotency_key=body.idempotencyKey,
        owner_id=student_id,
        lease_owner=lease_owner,
        now_epoch=now_epoch,
        expires_at=now_epoch + _AI_LEASE_SECONDS,
        table=table,
    )
    if not lease_claimed:
        current = attachment_repo.get_message_command(
            conv_id, body.idempotencyKey, table=table
        ) or {}
        if (
            current.get("status") == "ai_running"
            and int(current.get("expiresAt", 0)) <= now_epoch
            and int(current.get("attempt", 0)) >= 3
        ):
            attachment_repo.mark_message_command_terminal(
                conversation_id=conv_id,
                idempotency_key=body.idempotencyKey,
                owner_id=student_id,
                now_iso=_now(),
                table=table,
            )
        return _wait_for_message_command(
            conv_id, body.idempotencyKey, fingerprint, table=table
        )

    attachment_context = ""
    if prepared:
        attachment_context = attachment_service.extract_message_attachment_context(
            prepared,
            s3=boto3.client("s3", region_name=settings.aws_region),
            settings=settings,
        )
    normalized_subject = {
        "Mathematics": "math", "Mathematik": "math", "math": "math",
        "Physics": "physics", "Physik": "physics", "physics": "physics",
        "German": "german", "Deutsch": "german", "german": "german",
        "English": "english", "english": "english",
        "French": "french", "Französisch": "french", "french": "french",
    }.get(subject, "math")
    try:
        ai_result = ai_service.get_ai_answer(
            content=body.content,
            subject=normalized_subject,
            grade=grade,
            language="de",
            history=prior_messages,
            attachment_context=attachment_context,
            correlation_id=command_id,
        )
        steps = "\n".join(
            f"{index + 1}. {value}" for index, value in enumerate(ai_result.get("steps", []))
        )
        answer = ai_result.get("answer", "")
        hints = ai_result.get("hints", [])
        hint = ("\n\n**Hinweis:** " + hints[0]) if hints else ""
        ai_content = f"{steps}\n\n{answer}{hint}".strip() or (
            answer or "Entschuldigung, ich konnte keine Antwort generieren."
        )
    except Exception as exc:
        emit_private_event(
            "conversation_ai_failed",
            exception=exc,
            input_size=len(body.content),
            attachment_count=len(prepared),
            correlation_id=command_id,
            level=logging.ERROR,
        )
        ai_content = "Es gab ein technisches Problem. Bitte versuche es nochmals oder frage deinen Lehrer."

    assistant_created_at = _now()
    student_message = ChatMessage(
        id=student_msg_id,
        conversationId=conv_id,
        role="student",
        content=body.content,
        createdAt=created_at,
        status="sent",
        attachments=attachments,
    )
    assistant_message = ChatMessage(
        id=assistant_msg_id,
        conversationId=conv_id,
        role="assistant",
        content=ai_content,
        createdAt=assistant_created_at,
        status="sent",
    )
    result = SendMessageResponse(
        studentMessage=student_message, assistantMessage=assistant_message
    )
    assistant_item = {
        "PK": _conv_pk(conv_id),
        "SK": _msg_sk(assistant_msg_id),
        "message_id": assistant_msg_id,
        "conversation_id": conv_id,
        "student_id": student_id,
        "role": "assistant",
        "content": ai_content,
        "created_at": assistant_created_at,
    }
    if not attachment_repo.complete_message_command(
        conversation_id=conv_id,
        idempotency_key=body.idempotencyKey,
        owner_id=student_id,
        lease_owner=lease_owner,
        assistant_message=assistant_item,
        result_json=result.model_dump_json(),
        completed_at=assistant_created_at,
        table=table,
    ):
        return _wait_for_message_command(
            conv_id, body.idempotencyKey, fingerprint, table=table
        )
    return result


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
        emit_private_event(
            "conversation_ai_failed",
            exception=ai_err,
            input_size=len(content),
            attachment_count=len(prepared_attachments or []),
            correlation_id=student_msg_id,
            level=logging.ERROR,
        )
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
