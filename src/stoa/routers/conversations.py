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
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Literal, NamedTuple, NoReturn, cast

from boto3.dynamodb.conditions import Attr, Key
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from stoa.db.repositories.security_audit_repo import AuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.db.dynamodb import get_table
from stoa.db.repositories import (
    account_deletion_repo,
    attachment_repo,
    practice_repo,
    user_repo,
)
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    AuthorizedResource,
    ResourceType,
)
from stoa.security.identity import Actor
from stoa.models.error import (
    AttachmentErrorResponse,
    FirstMessageRefusalResponse,
    NotFoundResponse,
    SecurityErrorResponse,
)
from stoa.security.attachment_errors import (
    AttachmentDecisionError,
    AttachmentErrorCode,
    log_attachment_failure,
)
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
    ask_question,
    attachment_service,
    help_requests,
    learning_profile_service,
    message_catalog,
    practice_context_service,
    teacher_dispatch_service,
    teacher_support_allowance_service,
    usage_ledger_service,
)
from stoa.services.ask_question._answering import (
    _active_conversation_generation,
    _student_locale,
)
from stoa.services.ask_question._transcript import (
    _DynamoConversationTable,
    _conv_pk,
    _conversation_grade,
    _conversation_response_items,
    _get_conversation,
    _get_messages,
    _msg_sk,
)
from stoa.services.ask_question.models import (
    ChatMessage,
    GenerationProgressResponse,
    MessageAcceptedResponse,
    MessageQuote,
    PracticeContextReference,
    SendMessageRequest,
    SendMessageResponse,
    _stored_quote,
    _stored_structured,
    _structured_payload,
    _target_unit,
    message_request_fingerprint,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _required_conversation_text(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _conversation_title(record: Mapping[str, object]) -> str:
    """The name the conversation has, which is none until a question gives it one.

    A conversation opened without a first message is stored untitled and the
    client names it in the language it is drawn in (#124). Refusing an empty
    title here would be the `_conversation_grade` defect again: accepted at the
    door and unreadable ever after. A value of the wrong type is still refused.
    """
    value = record.get("title")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _conversation_record(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _raise_conversation_allowance_failure(
    error: ask_question.AllowanceFailure,
    *,
    correlation_id: str,
) -> None:
    raise HTTPException(
        status_code=error.http_status,
        detail={
            "code": error.code,
            "message": error.message,
            "action": error.action,
        },
        headers={"X-Correlation-ID": correlation_id},
    ) from error


# ── DynamoDB helpers ───────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# List budget: at most 25 index pages and 200 conversations per request.
_CONVERSATION_LIST_LIMIT = 200
_CONVERSATION_LIST_PAGE_BUDGET = 25


class ConversationListPage(NamedTuple):
    """Conversations in hand, plus whether older ones were left unread."""

    items: list[dict]
    truncated: bool


def _list_conversations(
    student_id: str,
    *,
    limit: int = _CONVERSATION_LIST_LIMIT,
    page_budget: int = _CONVERSATION_LIST_PAGE_BUDGET,
) -> ConversationListPage:
    """List this student's conversations, newest first.

    GSI-StudentId carries every row holding the student id - messages, usage
    events, reports - so a page can be consumed entirely by rows the filter drops
    and still leave conversations behind the continuation key. Follow the key
    instead of trusting one page, but stop at an explicit budget so a heavy
    history cannot turn the list into an unbounded table walk; descending order
    means a truncated answer is the most recent conversations, and the caller is
    told it was truncated.
    """
    table = cast(_DynamoConversationTable, get_table())
    items: list[dict] = []
    cursor: object = None
    for _page in range(page_budget):
        request: dict[str, object] = {
            "IndexName": "GSI-StudentId",
            "KeyConditionExpression": Key("student_id").eq(student_id),
            "FilterExpression": Attr("entity_type").eq("conversation"),
            "ScanIndexForward": False,
        }
        if cursor is not None:
            request["ExclusiveStartKey"] = cursor
        resp = table.query(**request)
        items.extend(_conversation_response_items(resp))
        cursor = resp.get("LastEvaluatedKey")
        if cursor is None:
            return ConversationListPage(items[:limit], len(items) > limit)
        if not isinstance(cursor, dict) or not cursor:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        if len(items) >= limit:
            return ConversationListPage(items[:limit], True)
    return ConversationListPage(items[:limit], True)


# ── Request / Response models ──────────────────────────────────────────────────

class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    grade: str
    initialMessage: str | None = Field(default=None, min_length=1, max_length=10_000)
    practiceContext: PracticeContextReference | None = None


def _resolved_practice_context(
    student_id: str, requested: PracticeContextReference | None
) -> dict[str, object] | None:
    """Look the exercise up by its ids, or refuse the request (#61).

    Nothing the client wrote about the exercise is kept: these three ids are
    the whole of what it may say. An id that names nothing this student can be
    shown is a 422, not an answer about an exercise nobody can see.
    """
    if requested is None:
        return None
    try:
        return practice_context_service.resolve(
            student_id,
            challenge_id=requested.challengeId,
            lesson_id=requested.lessonId,
            unit_id=requested.unitId,
            locale=_student_locale(student_id),
        )
    except practice_context_service.PracticeContextUnresolved:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="practiceContext does not name an exercise available to this student",
        ) from None


def _checked_quote_part(conv_id: str, quote: MessageQuote | None) -> None:
    """Refuse a part that names no section of an answer in this conversation (#132).

    The model is told which step or hint the student is asking about, so the
    part is looked up rather than believed: it must name an entry of a full
    answer this conversation holds. The key scopes the read to the
    conversation the route already authorized. A quote without a part is not
    looked up, as before parts existed.
    """
    part = None if quote is None else quote.source.part
    if quote is None or part is None:
        return
    table = cast(_DynamoConversationTable, get_table())
    item = table.get_item(
        Key={"PK": _conv_pk(conv_id), "SK": _msg_sk(quote.source.id)},
        ConsistentRead=True,
    ).get("Item")
    # Only an assistant answer is stored with sections.
    structured = _stored_structured(item.get("structured")) if isinstance(item, Mapping) else None
    if (
        structured is None
        or structured.kind != "answer"
        or (
            part.index is not None
            and part.index >= len(getattr(structured, part.section))
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="quote.source.part does not name a section of an answer in this conversation",
        )


async def _message_command_dependency(
    conv_id: str,
    body: SendMessageRequest,
    actor: Actor = Depends(get_actor),
) -> dict:
    """What `ask_question.submit` takes from the request, before any command is read.

    First of all: an exercise this student cannot be shown is refused before
    the command is looked up, let alone claimed. `submit` then compares the
    fingerprint against a stored command before attachments are resolved.
    """
    practice_context = _resolved_practice_context(actor.user_id, body.practiceContext)
    _checked_quote_part(conv_id, body.quote)
    return {
        "actor": actor,
        "fingerprint": message_request_fingerprint(body),
        "practice_context": practice_context,
    }


async def _attachment_inventory_resolver(resource_id: str):
    return {"student_id": resource_id}


async def _practice_context_challenge_resolver(resource_id: str):
    return practice_repo.get_challenge(resource_id)


# A message may now name the exercise it was asked beside (#61), so these
# routes read a practice resource and say so. The reading itself is narrow:
# `practice_context_service` only resolves content the student can be shown.
_PRACTICE_CONTEXT_SPEC = AuthorizationSpec(
    ResourceType.PRACTICE,
    AuthorizationAction.READ,
    AuthorizationPurpose.SELF_SERVICE,
    _practice_context_challenge_resolver,
)


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
    _PRACTICE_CONTEXT_SPEC,
)


def _conversation_create_dependency():
    """The create route's actor, plus the practice read a `practiceContext` is."""
    base = student_create_actor_dependency(ResourceType.CONVERSATION)

    async def dependency(actor: Actor = Depends(base)) -> Actor:
        return actor

    dependency.authorization_specs = (_PRACTICE_CONTEXT_SPEC,)  # type: ignore[attr-defined]
    return dependency


_conversation_create_actor = _conversation_create_dependency()


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
    truncated: bool = False


class TeacherHelpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversationId: str
    message: str | None = None


# What a student's request for a teacher can be, as the status card reads it
# (#65): `help_requests.student_view` derives the first three,
# the teacher's writes give in_progress and resolved, withdrawing and expiry
# the last two.
StudentHelpStatus = Literal[
    "pending",
    "waiting_no_teacher",
    "assigned",
    "in_progress",
    "resolved",
    "withdrawn",
    "expired",
]


class TeacherHelpResponse(BaseModel):
    requestId: str
    conversationId: str
    status: StudentHelpStatus = "pending"
    teacherName: str | None = None
    createdAt: str
    updatedAt: str | None = None


class TeacherSupportStanding(BaseModel):
    """Whether this student can still ask a teacher this Zurich week (#144).

    `blockedReason` is the code `POST /teacher-help/request` would refuse with:
    `teacher_support_allowance_exhausted` comes back at `resetsAt`;
    `teacher_support_not_included` does not come back with the week, so it has
    no `resetsAt`.
    """

    canRequest: bool
    blockedReason: (
        Literal["teacher_support_allowance_exhausted", "teacher_support_not_included"]
        | None
    ) = None
    remainingCases: int
    weeklyCases: int
    resetsAt: str | None = None


class TeacherAvailabilityResponse(BaseModel):
    online: bool
    availableTeachers: int
    nextWindow: str | None = None
    responseTime: str | None = None
    # The caller's own week. Null when it cannot be read right now; the request
    # route still applies the allowance.
    teacherSupport: TeacherSupportStanding | None = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    actor: Actor = Depends(
        student_actor_dependency(ResourceType.CONVERSATION, AuthorizationAction.READ)
    ),
):
    student_id = actor.user_id
    page = _list_conversations(student_id)
    summaries = [
        ConversationSummary(
            id=item["conversation_id"],
            # An untitled conversation stays untitled: falling back to the
            # subject id put the stored `math` in the sidebar as if it were a
            # name, which is the placeholder #124 removed.
            title=_conversation_title(item),
            subject=item.get("subject", ""),
            grade=item.get("grade", ""),
            updatedAt=item.get("updated_at", item.get("created_at", _now())),
            lastMessagePreview=item.get("last_message_preview"),
        )
        for item in page.items
    ]
    return ConversationListResponse(items=summaries, truncated=page.truncated)


def _subject_display_label(subject: object) -> str:
    """The subject named the way students see it, not the id it is stored under."""
    try:
        return learning_profile_service.subject_metadata(str(subject))["label"]
    except (ValueError, KeyError):
        return str(subject)


def _default_conversation_title(subject: object, grade: object) -> str:
    """No title at all until the student's first question names the conversation.

    It used to be `subject – grade`, which filled the sidebar with
    `Mathematik – Grade 6` repeated: a stored id and a grade spelling, neither
    of which is a name. The client already renders an untitled conversation in
    the language it is drawn in (`ask.list.untitled`, four locales), so the
    neutral phrase belongs there and not in a German string shipped from a
    backend that does not know what language the reader is in (#124).

    The arguments are kept: `_placeholder_conversation_titles` still needs the
    subject and grade to recognise the rows written before this.
    """
    return ""


def _placeholder_conversation_titles(subject: object, grade: object) -> tuple[str, ...]:
    """Every shape the generated placeholder has had, so older rows stay claimable."""
    return tuple(
        dict.fromkeys(
            (
                _default_conversation_title(subject, grade),
                f"{subject} – {grade}",
            )
        )
    )


def _teacher_help_system_message(message: object, locale: str) -> str:
    """The line that opens a help request, in the student's own language.

    It used to be a hardcoded `Teacher help requested.` glued onto the front of
    the student's German question, which is what the teacher then read (#124).
    The row also carries `system_event`, so a client can draw its own label
    without this stored text ever being rewritten.
    """
    return " ".join(
        part
        for part in (
            message_catalog.text("teacher_help.system_message.prefix", locale),
            str(message or "").strip(),
        )
        if part
    )


def _title_from_question(question: str, *, limit: int = 48) -> str:
    """Name a conversation after the question that started it."""
    condensed = " ".join(question.split())
    if len(condensed) <= limit:
        return condensed
    cut = condensed[:limit].rsplit(" ", 1)[0] or condensed[:limit]
    return f"{cut}…"


def _adopt_question_as_title(
    conv_id: str, conversation: Mapping[str, object], question: str
) -> None:
    """Retitle a conversation still carrying its subject-and-grade placeholder.

    Every conversation opened the same way was listed under the same name, so a
    student could not tell one from another. Best effort: a title is worth less
    than the answer that was just delivered.
    """
    title = _title_from_question(question)
    if not title:
        return
    placeholders = _placeholder_conversation_titles(
        conversation.get("subject"), conversation.get("grade")
    )
    current = conversation.get("title")
    if not isinstance(current, str) or current not in placeholders:
        return
    attachment_repo.retitle_conversation(
        conv_id, title=title, expected_title=current, now_iso=_now()
    )


def _naming_the_conversation(refusal: HTTPException, conv_id: str) -> HTTPException:
    """The first message's refusal, saying which conversation was already made (#61).

    The conversation is stored before its first message is committed, so a
    refused first message leaves it behind. With its id the client can send the
    message again into it, under the same key `initial-<id>`, instead of making
    another. Only a structured body can carry it; a plain-text one is left as it
    is, and neither helps a client that never received the response.
    """
    if not isinstance(refusal.detail, dict):
        return refusal
    return HTTPException(
        status_code=refusal.status_code,
        detail={**refusal.detail, "conversationId": conv_id},
        headers=refusal.headers,
    )


@router.post(
    "",
    response_model=ConversationDetail,
    status_code=status.HTTP_201_CREATED,
    responses={
        # 409 and 503 also come from the identity check, before any
        # conversation exists, with no conversationId to give.
        status.HTTP_409_CONFLICT: {"model": SecurityErrorResponse | FirstMessageRefusalResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": FirstMessageRefusalResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": SecurityErrorResponse | FirstMessageRefusalResponse
        },
    },
)
async def create_conversation(
    body: CreateConversationRequest,
    actor: Actor = Depends(_conversation_create_actor),
    correlation_id: str = Depends(get_request_correlation_id),
):
    student_id = actor.user_id
    # Before anything is written: an id that names no exercise this student can
    # be shown leaves no half-opened conversation behind.
    practice_context = _resolved_practice_context(student_id, body.practiceContext)
    conv_id = str(uuid.uuid4())
    now = _now()
    title = (
        _title_from_question(body.initialMessage)
        if body.initialMessage
        else _default_conversation_title(body.subject, body.grade)
    )

    table = get_table()
    conv_item: dict[str, object] = {
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
    generation = _active_conversation_generation(student_id, table)
    attachment_repo.create_conversation_record(
        conv_item,
        owner_id=student_id,
        generation=generation,
        table=table,
    )

    messages: list[ChatMessage] = []
    if body.initialMessage:
        request = SendMessageRequest(
            content=body.initialMessage,
            idempotencyKey=f"initial-{conv_id}",
            practiceContext=body.practiceContext,
        )
        try:
            result = ask_question.submit(
                actor,
                conv_item,
                request,
                message_request_fingerprint(request),
                conversation_id=conv_id,
                student_id=student_id,
                practice_context=practice_context,
                new_conversation_generation=generation,
            )
        except ask_question.AllowanceFailure as error:
            try:
                _raise_conversation_allowance_failure(
                    error,
                    correlation_id=correlation_id,
                )
            except HTTPException as refusal:
                raise _naming_the_conversation(refusal, conv_id) from error
        except AttachmentDecisionError as error:
            # The daily message limit, among others: the same conversion the
            # message routes make, then the conversation's id.
            try:
                _raise_attachment(error, correlation_id)
            except HTTPException as refusal:
                raise _naming_the_conversation(refusal, conv_id) from error
        except HTTPException as refusal:
            raise _naming_the_conversation(refusal, conv_id) from refusal
        messages = (
            # The answer follows; it is read at /generation with this key.
            [result.studentMessage]
            if isinstance(result, MessageAcceptedResponse)
            else [result.studentMessage, result.assistantMessage]
        )

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
    conv = _conversation_record(authorized.value)

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
            authorName=_author_name(m),
            quote=_stored_quote(m.get("quote")),
            structured=_stored_structured(m.get("structured")),
            targetUnit=_target_unit(m.get("target_unit_id")),
        )
        for m in raw_messages
    ]

    return ConversationDetail(
        id=conv_id,
        title=_conversation_title(conv),
        subject=_required_conversation_text(conv, "subject"),
        grade=_conversation_grade(conv),
        updatedAt=_required_conversation_text(conv, "updated_at"),
        messages=messages,
    )


@router.get(
    "/{conv_id}/generation",
    response_model=GenerationProgressResponse,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": AttachmentErrorResponse,
            "description": (
                "`message_command_not_found`: no message command of this caller "
                "has this idempotency key."
            ),
        }
    },
)
async def get_generation_progress(
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.READ,
            purposes=CONVERSATION_CONTENT_READ,
            resolver=lambda conversation_id: _get_conversation(conversation_id),
        )
    ),
    idempotency_key: str | None = Query(
        default=None,
        alias="idempotencyKey",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._~-]+$",
    ),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Return the steps of an answer still being written.

    Named by its idempotency key, the message's command is reported too, with
    only the steps its current attempt wrote.
    """
    try:
        return ask_question.progress(
            authorized.ref.resource_id, idempotency_key, authorized.ref.student_id
        )
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)


@router.post(
    "/{conv_id}/messages",
    response_model=SendMessageResponse,
    responses={status.HTTP_202_ACCEPTED: {"model": MessageAcceptedResponse}},
)
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
    conv = _conversation_record(authorized.value)

    try:
        # A record the conversation cannot be read back from is refused before
        # anything is submitted, as reading it would be.
        _required_conversation_text(conv, "subject")
        _conversation_grade(conv)
        result = ask_question.submit(
            message_command["actor"],
            conv,
            body,
            message_command["fingerprint"],
            conversation_id=conv_id,
            student_id=student_id,
            practice_context=message_command["practice_context"],
        )
    except ask_question.AllowanceFailure as error:
        _raise_conversation_allowance_failure(
            error,
            correlation_id=correlation_id,
        )
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)
    _adopt_question_as_title(conv_id, conv, body.content)
    if isinstance(result, MessageAcceptedResponse):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=result.model_dump(mode="json"),
        )
    return result


@router.post(
    "/{conv_id}/messages/stream",
    responses={status.HTTP_202_ACCEPTED: {"model": MessageAcceptedResponse}},
)
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

    Events: `student_message` (a `ChatMessage`), `message_start`, one or more
    `message_delta` with the answer's text, and `message_done`, which carries
    the answer's sections as `structured` (a `StructuredAnswer`, #132) and the
    star the student asked to go to as `targetUnit` (a `TargetUnit` or null,
    #124).
    """
    conv_id = authorized.ref.resource_id
    student_id = authorized.ref.student_id
    conv = _conversation_record(authorized.value)

    try:
        # A record the conversation cannot be read back from is refused before
        # anything is submitted, as reading it would be.
        _required_conversation_text(conv, "subject")
        _conversation_grade(conv)
        result = ask_question.submit(
            message_command["actor"],
            conv,
            body,
            message_command["fingerprint"],
            conversation_id=conv_id,
            student_id=student_id,
            practice_context=message_command["practice_context"],
        )
    except ask_question.AllowanceFailure as error:
        _raise_conversation_allowance_failure(
            error,
            correlation_id=correlation_id,
        )
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)
    # Same as the non-streaming route. Only that one adopted the question, while
    # the client only ever calls this one, so every conversation it opened stayed
    # listed under the subject-and-grade placeholder.
    _adopt_question_as_title(conv_id, conv, body.content)
    if isinstance(result, MessageAcceptedResponse):
        # Stored, answer to follow from the worker: nothing to stream here.
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=result.model_dump(mode="json"),
        )
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
            "structured": _structured_payload(assistant_msg.structured),
            "targetUnit": (
                None
                if assistant_msg.targetUnit is None
                else assistant_msg.targetUnit.model_dump(mode="json")
            ),
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _raise_attachment(error: AttachmentDecisionError, correlation_id: str) -> NoReturn:
    error.correlation_id = correlation_id
    log_attachment_failure(error, route="conversations")
    headers = {"X-Correlation-ID": correlation_id}
    if error.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE:
        headers["Retry-After"] = "30"
    raise HTTPException(
        status_code=error.status_code,
        detail=error.public_body(),
        headers=headers,
    ) from error


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


setattr(_teacher_help_conversation_dependency, "authorization_specs", (
    AuthorizationSpec(
        ResourceType.CONVERSATION,
        AuthorizationAction.UPDATE,
        AuthorizationPurpose.SELF_SERVICE,
        _teacher_help_conversation_metadata_resolver,
    ),
))


@teacher_help_router.get("/availability", response_model=TeacherAvailabilityResponse)
async def get_teacher_help_availability(
    actor: Actor = Depends(
        student_actor_dependency(ResourceType.CONVERSATION, AuthorizationAction.LOOKUP)
    ),
):
    """Return student-safe teacher availability for the chat indicator.

    Also the caller's own teacher-support week, so an "ask a teacher" button
    can be greyed with its reason before the student presses it (#144).
    """
    summary = teacher_dispatch_service.teacher_availability_summary()
    now = _now()
    try:
        standing = teacher_support_allowance_service.get_student_teacher_support_standing(
            beneficiary_id=actor.user_id,
            observed_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
        )
    except Exception:
        # Whatever stops the read, the indicator still answers: the request
        # route applies the allowance either way.
        logger.warning(
            "teacher_support_standing_unavailable student=%s", actor.user_id, exc_info=True
        )
        standing = None
    return {**summary, "teacherSupport": standing}


@teacher_help_router.post("/request", response_model=TeacherHelpResponse)
async def request_teacher_help(
    body: TeacherHelpRequest,
    authorized: AuthorizedResource = Depends(_teacher_help_conversation_dependency),
):
    """Ask a human teacher about this conversation (#189: one request per conversation).

    A conversation that already has a request answers with it, whatever its
    state. Otherwise a case of the week is spent, the request written and
    offered to a teacher; `help_requests.ask` does all three.
    """
    student_id = authorized.ref.student_id
    conv = {**authorized.value, "conversation_id": body.conversationId}
    now = _now()
    # The request is the student's own, so the language they are reading in
    # right now is the one the system message is written in (#124).
    student_locale = _student_locale(student_id)

    def record_help_usage(request: Mapping[str, object]) -> None:
        # Written after the case is durable and offered, so a first attempt
        # that fails here leaves the request and no row. A repeat request
        # answers with that request and still owes the row, keyed by the
        # request and its day, so once the row is there every repeat is a
        # duplicate.
        request_id = str(request.get("escalation_request_id") or body.conversationId)
        escalated_at = str(request.get("escalated_at") or now)
        usage_ledger_service.record_usage_event(
            student_id=student_id,
            action=usage_ledger_service.CONVERSATION_TEACHER_HELP_ACTION,
            quota_period=usage_ledger_service.quota_period_of(escalated_at),
            idempotency_key=usage_ledger_service.build_usage_idempotency_key(
                action=usage_ledger_service.CONVERSATION_TEACHER_HELP_ACTION,
                resource_id=body.conversationId,
                qualifier=request_id,
            ),
            request_correlation_id=request_id,
            created_at=escalated_at,
            account_fence_generation=_active_conversation_generation(student_id, get_table()),
            metadata={
                "conversation_id": body.conversationId,
                "request_id": request_id,
                "subject": request.get("subject"),
                "grade_level": request.get("grade"),
                "status": "pending",
            },
        )

    unavailable = HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "teacher_support_admission_recoverable",
            "message": "Teacher support is briefly unavailable. Please try again.",
            "action": "retry_same_case",
        },
    )
    try:
        outcome = help_requests.ask(
            conversation=conv,
            student_id=student_id,
            message=body.message,
            system_message=_teacher_help_system_message(body.message, student_locale),
            now=now,
            table=get_table(),
        )
    except (help_requests.HelpRequestUnavailable, account_deletion_repo.AccountDeletionConflict) as exc:
        raise unavailable from exc

    Disposition = teacher_support_allowance_service.TeacherSupportAdmissionDisposition
    if outcome.disposition is Disposition.PLAN_DENIED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "teacher_support_not_included",
                # Nobody can buy their way past this while the paid surface is
                # frozen, and on an assigned account there was never anything to
                # buy. Pointing at a plan sends the student somewhere that
                # cannot help them.
                "message": "Teacher support is not switched on for this account.",
                "action": "contact_administrator",
            },
        )
    if outcome.disposition is Disposition.LIMIT_EXCEEDED:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "teacher_support_allowance_exhausted",
                "message": "The weekly teacher-support allowance is used.",
                "action": "wait_for_next_week",
            },
        )
    if outcome.disposition is Disposition.IDEMPOTENCY_CONFLICT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Teacher-support case identity conflicts with prior admission",
        )
    if outcome.record is None:
        logger.warning(
            "teacher_help_admission_retryable student=%s conversation=%s",
            student_id,
            body.conversationId,
        )
        raise unavailable

    record_help_usage(outcome.record)
    return _teacher_help_response(outcome.record, fallback_created_at=now)


def _teacher_help_response(
    record: Mapping[str, Any], *, fallback_created_at: str
) -> TeacherHelpResponse:
    """Describe a request the way the waiting student should read it."""
    help_status, teacher_id = help_requests.student_view(record)
    conversation_id = str(record.get("conversation_id") or "")
    return TeacherHelpResponse(
        requestId=str(record.get("escalation_request_id") or conversation_id),
        conversationId=conversation_id,
        status=cast(StudentHelpStatus, help_status),
        teacherName=_teacher_name(teacher_id),
        createdAt=str(record.get("escalated_at") or fallback_created_at),
        updatedAt=str(record.get("updated_at") or fallback_created_at),
    )


def _author_name(message: Mapping[str, Any]) -> str | None:
    """The name a teacher message was written under; no other message has one."""
    name = message.get("author_name")
    if message.get("role") != "teacher" or not isinstance(name, str):
        return None
    return name.strip() or None


def _teacher_name(teacher_id: object) -> str | None:
    if not isinstance(teacher_id, str) or not teacher_id:
        return None
    profile = user_repo.get_user(teacher_id) or {}
    # Never the email: a student sees this name (#65). Without one the
    # frontend says "teacher".
    name = profile.get("name")
    return name.strip() or None if isinstance(name, str) else None


@teacher_help_router.post(
    "/conversations/{conv_id}/request/withdraw", response_model=TeacherHelpResponse
)
async def withdraw_teacher_help_request(
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.UPDATE,
            purposes=STUDENT_SELF,
            resolver=lambda conversation_id: _get_conversation(conversation_id),
        )
    ),
):
    """Take back a teacher-help request no teacher has taken yet (#86).

    Both rows end and the week's case is given back, in one write. Once a
    teacher has taken the request it can no longer be withdrawn. Asking again
    in the same conversation is not possible afterwards; a new chat is.
    """
    conversation_id = authorized.ref.resource_id
    try:
        withdrawn = help_requests.withdraw(
            conversation_id, student_id=authorized.ref.student_id, table=get_table()
        )
    except help_requests.HelpRequestEndingRefused as refused:
        code = refused.code
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
                if code == "teacher_help_request_not_found"
                else status.HTTP_409_CONFLICT
            ),
            detail={"code": code},
        ) from refused
    except help_requests.HelpRequestEndingUnavailable as unavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "teacher_help_withdrawal_unavailable",
                "message": "Withdrawing is briefly unavailable. Please try again.",
                "action": "retry_same_case",
            },
        ) from unavailable
    return _teacher_help_response(withdrawn, fallback_created_at="")


@teacher_help_router.get(
    "/conversations/{conv_id}/request",
    response_model=TeacherHelpResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": NotFoundResponse,
            "description": (
                "The conversation was never escalated to a teacher (a sentence), "
                "or the caller may not see it (`resource_not_found`)."
            ),
        }
    },
)
async def get_teacher_help_status(
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.READ,
            purposes=CONVERSATION_CONTENT_READ,
            resolver=lambda conversation_id: _get_conversation(conversation_id),
        )
    ),
):
    """Report where a student's request stands, for the waiting indicator."""
    try:
        record = help_requests.get(authorized.ref.resource_id, table=get_table())
    except help_requests.HelpRequestUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The request could not be read. Please try again.",
        ) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This conversation was never escalated to a teacher",
        )
    return _teacher_help_response(record, fallback_created_at="")
