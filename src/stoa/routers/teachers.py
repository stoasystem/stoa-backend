"""Teacher routes — work queue, takeover, reply, resolve."""
import logging

from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, NamedTuple, Protocol, runtime_checkable

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from stoa import aws
from stoa.aws import Kind
from stoa.config import Settings
from stoa import config
from stoa.db.repositories import (
    asked_knowledge_repo,
    attachment_repo,
    user_repo,
)
from stoa.db import table as db_table
from stoa.observability import telemetry
from stoa.deps import get_actor
from stoa.models.attachment import AttachmentSummary, ReplyImageReference
from stoa.models.classroom import ClassroomEntry
from stoa.security.attachment_errors import (
    AttachmentDecisionError,
    AttachmentErrorCode,
)
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizedResource,
    ResourceRef,
    ResourceType,
)
from stoa.security.declared_authorization import (
    SELF,
    AuthorizationContext,
    authorize_loaded,
    authorized,
    get_authorization_context,
    loaded_declaration,
    path,
    service_enforced,
    teacher_task_resource,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor, CanonicalRole
from stoa.security.request_correlation import get_request_correlation_id
from stoa.services import (
    attachment_service,
    classroom,
    help_requests,
    knowledge_mastery_service,
    learning_session,
    locale_service,
    student_evidence,
    teacher_dispatch_service,
    teacher_help_prep,
    teacher_reply_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)

type TeacherItem = dict[str, object]


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


def _teacher_mapping(value: object) -> TeacherItem:
    if not isinstance(value, Mapping):
        raise RuntimeError("teacher data dependency unavailable")
    result: TeacherItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise RuntimeError("teacher data dependency unavailable")
        result[key] = member
    return result


def _teacher_put(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise RuntimeError("teacher data dependency unavailable")
    return table.put_item(**kwargs)



def _text(value: object, *, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError("teacher data dependency unavailable")
    return value


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _refuse_unless_held(conv: dict, teacher_id: str) -> None:
    """Only the teacher who holds or was offered a request changes it."""
    if not help_requests.holder_or_offered(conv, teacher_id):
        raise help_requests.HelpRequestConflict(
            "teacher neither holds nor was offered the request",
            code=help_requests.HelpRequestErrorCode.HELP_REQUEST_NOT_HELD,
        )


# Canonical teacher portal, availability, and help-request routes.

#: The teacher's own portal record (an admin has one too).
_PORTAL_SELF = {
    CanonicalRole.TEACHER: AuthorizationPurpose.SELF_SERVICE,
    CanonicalRole.ADMIN: AuthorizationPurpose.SELF_SERVICE,
}
#: A help request, and what was sent in it, is read and answered for help.
_TEACHER_HELP = {CanonicalRole.TEACHER: AuthorizationPurpose.TEACHER_HELP}

_portal_read = authorized(
    ResourceType.TEACHER_PORTAL, AuthorizationAction.READ, SELF, _PORTAL_SELF
)
_portal_update = authorized(
    ResourceType.TEACHER_PORTAL, AuthorizationAction.UPDATE, SELF, _PORTAL_SELF
)


def _help_request(action: AuthorizationAction):
    """The help request the route's `request_id` names, loaded once, as stored (#234)."""
    return authorized(
        ResourceType.TEACHER_HELP_REQUEST, action, path("request_id"), _TEACHER_HELP
    )


async def _current_help_requests(
    actor: Actor, context: AuthorizationContext
) -> list[TeacherItem]:
    """The help requests this teacher may read, each one decided as it is listed."""
    current: list[TeacherItem] = []
    for record in help_requests.list_for_teacher(actor.user_id, table=db_table.table()):
        conv = _teacher_mapping(record)
        loaded = teacher_task_resource(ResourceType.TEACHER_HELP_REQUEST, conv)
        try:
            await authorize_loaded(
                actor, loaded.ref, conv, AuthorizationAction.READ, _TEACHER_HELP, context
            )
        except SecurityDecisionError as error:
            if error.code is SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE:
                raise
            continue
        current.append(conv)
    return current


def _get_student_name(student_id: str) -> str:
    """What a teacher is shown in place of a student's name.

    It fell back to the student's email address, so a student who had not
    filled in a name had their email shown to every teacher who saw the
    request — a contact detail nobody asked to share, in a field that means
    "what to call this person" (#94, user's decision 2026-10-06). A name of
    spaces is no name either.
    """
    profile = user_repo.get_user(student_id)
    name = profile.get("name") if profile else None
    return name.strip() if isinstance(name, str) and name.strip() else "Student"


def _parse_time(value: object) -> datetime | None:
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


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class TeacherHelpRequestSummary(BaseModel):
    requestId: str
    conversationId: str
    # The student the request is from: what the teacher assigns practice to (#495).
    studentId: str
    studentName: str
    subject: str
    grade: str
    status: str
    # How the student asked to be helped (#480); the teacher cannot change it.
    mode: help_requests.HelpMode = help_requests.TEXT
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
    # What the student sent with the message (#140); the content is read at
    # GET /teachers/me/help-requests/{requestId}/attachments/{attachmentId}/content.
    attachments: list[AttachmentSummary] = Field(default_factory=list)


def message_out(
    message: learning_session.Message,
    attachment_summaries: Mapping[str, AttachmentSummary],
) -> MessageOut:
    """The teacher's view of a stored message, with the attachments it carries."""
    return MessageOut(
        id=message.id,
        conversationId=message.conversation_id,
        role=message.role,
        content=message.content,
        createdAt=message.created_at,
        attachments=[
            attachment_summaries[value]
            for value in message.attachment_ids
            if value in attachment_summaries
        ],
    )


class TeacherNoteOut(BaseModel):
    id: str
    note: str
    createdAt: str
    teacher: dict
    richContent: dict | None = None
    responseFormat: str | None = None
    # The images the reply carries (#145), read as each message's are.
    attachments: list[AttachmentSummary] = Field(default_factory=list)


class TeacherErrorCause(BaseModel):
    """Why the student's recent wrong answers were wrong, most often (错因, #452)."""

    # structural | deviation | application | metacognitive
    category: str
    misconception: str
    # How many of the recent wrong answers had this cause, and how many were read.
    count: int
    recentMistakes: int


class TeacherAiHelpedStar(BaseModel):
    """A lit star whose right answers came mostly after asking AI (#451)."""

    unitId: str
    title: str
    # Its exercises answered right independently, and only after asking AI.
    independent: int
    askedAi: int


class TeacherPrepQuestion(BaseModel):
    """One of the student's questions as the prep table shows it (#517)."""

    messageId: str
    content: str
    createdAt: str
    # The files this message carries.
    attachments: list[AttachmentSummary] = Field(default_factory=list)


class TeacherAskedStar(BaseModel):
    """A star the conversation's Ask answers named (#517)."""

    unitId: str
    # In the teacher's language.
    title: str


class TeacherHelpRequestDetail(BaseModel):
    requestId: str
    conversationId: str
    student: dict
    subject: str
    status: str
    mode: help_requests.HelpMode = help_requests.TEXT
    requestMessage: str | None = None
    messages: list[MessageOut]
    notes: list[TeacherNoteOut]
    firstTeacherActionAt: str | None = None
    sla: dict | None = None
    # The prep for a help request raised from Ask (#143): the knowledge points
    # the answers in this conversation named, newest first, as the prep summary
    # of a question names its topics. Empty when none were recorded.
    weakTopics: list[str] = Field(default_factory=list)
    # The student's commonest error cause among their recent wrong answers
    # (#452), with its misconception in the teacher's language; `null` when
    # none of them is tagged with a cause.
    commonErrorCause: TeacherErrorCause | None = None
    # The student's lit stars where more than half of the exercises answered
    # right were answered after asking AI (#451), in the catalog's order, titled
    # in the teacher's language. Empty when there are none.
    aiHelpedStars: list[TeacherAiHelpedStar] = Field(default_factory=list)
    # The prep table (#517), by the rules of `teacher_help_prep`: the
    # student's first question; their last one before asking for a teacher,
    # `null` when it is the first; every file they sent in the conversation;
    # and the stars the conversation's Ask answers named, newest first.
    firstQuestion: TeacherPrepQuestion | None = None
    lastQuestion: TeacherPrepQuestion | None = None
    uploads: list[AttachmentSummary] = Field(default_factory=list)
    askedStars: list[TeacherAskedStar] = Field(default_factory=list)


def _help_request_summary(
    view: help_requests.TeacherView, *, student_name: str
) -> TeacherHelpRequestSummary:
    return TeacherHelpRequestSummary(
        requestId=view.request_id,
        conversationId=view.conversation_id,
        studentId=view.student_id,
        studentName=student_name,
        subject=view.subject,
        grade=view.grade,
        status=view.status,
        mode=view.mode,
        requestMessage=view.request_message,
        createdAt=view.created_at,
        firstTeacherActionAt=view.first_teacher_action_at,
        sla=view.sla,
    )


def _note_out(
    reply: help_requests.Reply, attachments: list[AttachmentSummary]
) -> TeacherNoteOut:
    return TeacherNoteOut(
        id=reply.id,
        note=reply.content,
        createdAt=reply.created_at,
        teacher={"id": reply.teacher_id, "name": reply.teacher_name},
        richContent=reply.rich,
        responseFormat=reply.format,
        attachments=attachments,
    )


class UpdateStatusRequest(BaseModel):
    # Taking the request (`in_progress`) and finishing it (`resolved`) are the
    # only moves a teacher makes; anything else used to be stored verbatim.
    status: Literal["in_progress", "resolved"]
    resolutionNote: str | None = None


class AddNoteRequest(BaseModel):
    content: str
    richContent: dict[str, Any] | None = None
    # The teacher's own `help_reply_image` uploads, completed (#145).
    attachmentIds: list[ReplyImageReference] | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def unique_attachments(self) -> "AddNoteRequest":
        upload_ids = [reference.upload_id for reference in self.attachmentIds or []]
        if len(set(upload_ids)) != len(upload_ids):
            raise ValueError("attachment references must be unique")
        return self


class TeacherAvailabilitySlot(BaseModel):
    dayOfWeek: str
    startTime: str
    endTime: str


class TeacherAvailability(BaseModel):
    weeklyAvailability: list[TeacherAvailabilitySlot] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    # Whether this teacher takes dispatch. Omitted on a save, the stored value is
    # kept; `null` in a response means the teacher has never set it.
    status: Literal["available", "paused"] | None = None


class TeacherAvailabilityUpdate(BaseModel):
    # Each field left out is kept as stored; `[]` clears a list on purpose.
    weeklyAvailability: list[TeacherAvailabilitySlot] | None = None
    subjects: list[str] | None = None
    status: Literal["available", "paused"] | None = None


class TeacherProfile(BaseModel):
    id: str
    userId: str
    name: str
    email: str
    accountStatus: str
    availabilityStatus: str
    subjects: list[str] = Field(default_factory=list)
    weeklyAvailability: list[TeacherAvailabilitySlot] = Field(default_factory=list)
    maxActiveSessions: int | None = None
    createdAt: str
    updatedAt: str


class TeacherStats(BaseModel):
    pendingRequests: int
    resolvedToday: int
    averageResponseTimeMinutes: int


@loaded_declaration(ResourceType.TEACHER_HELP_REQUEST, AuthorizationAction.READ, _TEACHER_HELP)
async def _help_list_actor(
    actor: Actor = Depends(_portal_read),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> tuple[Actor, AuthorizationContext]:
    """The teacher's own portal; each listed request is decided in `_current_help_requests`."""
    return actor, context


class _HelpRequestAttachment(NamedTuple):
    help_request: TeacherItem
    attachment: TeacherItem


def _sent_in_help_request(
    conv: Mapping[str, object], attachment_id: str
) -> TeacherItem | None:
    """The live attachment, if a message of this request carries it.

    Whose it is is the policy's to judge: only the student's own is read.
    """
    conv_id = _required_text(conv.get("conversation_id"))
    if not any(
        attachment_id in m.attachment_ids for m in learning_session.history(conv_id)
    ):
        return None
    item = attachment_repo.get_attachment(attachment_id)
    return item if attachment_service.is_live_attachment(item) else None


@loaded_declaration(ResourceType.ATTACHMENT, AuthorizationAction.READ, _TEACHER_HELP)
async def _help_request_attachment_dependency(
    request: AuthorizedResource = Depends(_help_request(AuthorizationAction.READ)),
    attachment_id: str = Path(),
    actor: Actor = Depends(get_actor),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> _HelpRequestAttachment:
    """An attachment, read under the help request it was sent in (#140).

    Whoever may read the request may read what the student sent in it: the
    teacher it is offered to and the teacher who took it. Anyone else is
    refused exactly as the request refuses them, before the attachment is
    looked up, so a refusal says nothing about the attachment.
    """
    try:
        conv = _teacher_mapping(request.value)
        item = _sent_in_help_request(conv, attachment_id)
        if item is None:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
        ref = ResourceRef(
            ResourceType.ATTACHMENT,
            attachment_id,
            _required_text(conv.get("student_id")),
            owner_id=_text(item.get("owner_id")),
            question_id=_required_text(conv.get("conversation_id")),
        )
        await authorize_loaded(
            actor, ref, conv, AuthorizationAction.READ, _TEACHER_HELP, context
        )
        return _HelpRequestAttachment(conv, item)
    except (AttachmentDecisionError, SecurityDecisionError):
        raise
    except Exception as exc:
        raise SecurityDecisionError(
            SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
            context.correlation_id,
            internal_detail=type(exc).__name__,
        ) from exc


# A reply's images are the replying teacher's own uploads, consumed by it
# (#145): `attachment_service.prepare_reply_images` resolves them under the
# teacher's ownership, as the files routes' upload service does.
_reply_upload_actor = service_enforced(
    "attachment_service.prepare_reply_images",
    ResourceType.UPLOAD,
    AuthorizationAction.UPDATE,
    {CanonicalRole.TEACHER: AuthorizationPurpose.SELF_SERVICE},
)


def _availability_response(profile: dict[str, Any] | None) -> TeacherAvailability:
    profile = profile or {}
    subjects = user_repo.stored_teacher_subjects(profile)
    weekly_availability = profile.get("weekly_availability") or profile.get("weeklyAvailability") or []
    slots = [
        TeacherAvailabilitySlot(
            dayOfWeek=str(slot["dayOfWeek"]),
            startTime=str(slot["startTime"]),
            endTime=str(slot["endTime"]),
        )
        for slot in weekly_availability
        if isinstance(slot, dict)
        and slot.get("dayOfWeek")
        and slot.get("startTime")
        and slot.get("endTime")
    ]
    return TeacherAvailability(
        subjects=subjects,
        weeklyAvailability=slots,
        status=teacher_dispatch_service.teacher_availability_status(profile),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _stored_session_limit(value: object) -> int | None:
    """The stored limit comes back from DynamoDB as Decimal."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    return None


@router.get("/me/profile", response_model=TeacherProfile)
async def get_my_profile(
    actor: Actor = Depends(_portal_read),
):
    """Return the teacher's own profile as it is actually stored."""
    profile = user_repo.get_user(actor.user_id) or {}
    availability = _availability_response(profile)
    return TeacherProfile(
        id=actor.user_id,
        userId=actor.user_id,
        name=_text(profile.get("name")),
        email=_text(profile.get("email")),
        accountStatus=_text(profile.get("account_status")) or "active",
        availabilityStatus=(
            _text(profile.get("availability_status"))
            or _text(profile.get("availability"))
            or "unavailable"
        ),
        subjects=availability.subjects,
        weeklyAvailability=availability.weeklyAvailability,
        maxActiveSessions=_stored_session_limit(profile.get("max_active_sessions")),
        createdAt=_text(profile.get("created_at")),
        updatedAt=_text(profile.get("updated_at")),
    )


@router.get("/me/availability", response_model=TeacherAvailability)
async def get_my_availability(
    actor: Actor = Depends(_portal_read),
):
    """Return the current teacher availability profile used for dispatch."""
    return _availability_response(user_repo.get_user(actor.user_id))


@router.patch("/me/availability", response_model=TeacherAvailability)
async def update_my_availability(
    body: TeacherAvailabilityUpdate,
    actor: Actor = Depends(_portal_update),
):
    """Persist teacher availability so student support status can reflect it."""
    updated = user_repo.update_teacher_availability(
        actor.user_id,
        subjects=(
            None
            if body.subjects is None
            else [subject.strip() for subject in body.subjects if subject.strip()]
        ),
        weekly_availability=(
            None
            if body.weeklyAvailability is None
            else [slot.model_dump() for slot in body.weeklyAvailability]
        ),
        updated_at=_now(),
        status=body.status,
    )
    # Saving is also a heartbeat (#472): a teacher who just set themselves
    # available is online at once, not only from their next poll.
    teacher_dispatch_service.record_seen_if_teacher(actor)
    return _availability_response(updated)


@router.get("/me/stats", response_model=TeacherStats)
async def get_stats(
    portal: tuple[Actor, AuthorizationContext] = Depends(_help_list_actor),
):
    views = [
        help_requests.teacher_view(c)
        for c in await _current_help_requests(*portal)
    ]
    pending = sum(1 for view in views if view.status == "pending")
    response_times = [
        view.sla["requestToFirstActionMinutes"]
        for view in views
        if isinstance(view.sla["requestToFirstActionMinutes"], int)
    ]
    resolved_today_count = sum(
        1 for view in views
        if view.status == "resolved"
        and (view.resolved_at or "")[:10] == datetime.now(timezone.utc).date().isoformat()
    )
    return TeacherStats(
        pendingRequests=pending,
        resolvedToday=resolved_today_count,
        averageResponseTimeMinutes=round(sum(response_times) / len(response_times)) if response_times else 0,
    )


@router.get("/me/help-requests", response_model=dict)
async def list_help_requests(
    portal: tuple[Actor, AuthorizationContext] = Depends(_help_list_actor),
):
    """Return only help requests currently assigned to this Actor."""
    # The queue polls this while the teacher's tab is shown, so each read is
    # also their heartbeat (#472).
    teacher_dispatch_service.record_seen_if_teacher(portal[0])
    escalated = await _current_help_requests(*portal)
    items = []
    for conv in sorted(
        escalated,
        key=lambda candidate: _text(candidate.get("escalated_at")),
        reverse=True,
    ):
        view = help_requests.teacher_view(conv)
        items.append(
            _help_request_summary(view, student_name=_get_student_name(view.student_id)).model_dump()
        )
    return {"items": items}


@router.get("/me/help-requests/{request_id}", response_model=TeacherHelpRequestDetail)
async def get_help_request(
    request_id: str,
    authorized: AuthorizedResource = Depends(_help_request(AuthorizationAction.READ)),
    actor: Actor = Depends(get_actor),
    view_mode: Literal["full", "live"] = Query(default="full", alias="view"),
):
    """Get full detail of a specific help request including conversation messages.

    `view=live` is the poll: it leaves the student's evidence unread, so
    `commonErrorCause` and `aiHelpedStars` come back empty.
    """
    table = db_table.table()

    view = help_requests.teacher_view(authorized.value)

    conv_id = _required_text(view.conversation_id)
    student_id = _required_text(view.student_id)
    student_profile = user_repo.get_user(student_id)
    student_name = _text(
        (student_profile or {}).get("name"), default="Student"
    )

    history = learning_session.history(conv_id)
    try:
        attachment_summaries = attachment_service.list_attachment_summaries(
            [value for m in history for value in m.attachment_ids]
        )
    except attachment_repo.AttachmentRepositoryConflict as exc:
        # The request opens without them rather than not at all: before #140
        # the detail never read attachments.
        logger.warning(
            "help_request_attachment_summaries_unavailable category=%s", exc
        )
        attachment_summaries = {}
    messages = [message_out(m, attachment_summaries) for m in history]
    notes = [
        _note_out(
            reply,
            [
                attachment_summaries[value]
                for value in reply.attachment_ids
                if value in attachment_summaries
            ],
        )
        for reply in help_requests.replies(conv_id, table=table)
    ]
    # One evidence for the prep's items, read lazily: each reads what it needs once.
    locale = locale_service.reader_locale(actor.user_id)
    evidence = (
        student_evidence.for_student(student_id, locale=locale) if view_mode == "full" else None
    )
    content = evidence.content if evidence is not None else student_evidence.Content(locale=locale)
    asked_records = _asked_records(conv_id)
    asked = teacher_help_prep.questions(
        history, asked_at=_text(authorized.value.get("escalated_at")) or None
    )

    return TeacherHelpRequestDetail(
        requestId=view.request_id,
        conversationId=conv_id,
        student={
            "id": student_id,
            "name": student_name,
            "grade": view.grade,
        },
        subject=view.subject,
        status=view.status,
        mode=view.mode,
        requestMessage=view.request_message,
        messages=messages,
        notes=notes,
        firstTeacherActionAt=view.first_teacher_action_at,
        sla=view.sla,
        weakTopics=_asked_topics(asked_records),
        commonErrorCause=_common_error_cause(evidence, locale) if evidence is not None else None,
        aiHelpedStars=_ai_helped_stars(evidence) if evidence is not None else [],
        firstQuestion=_prep_question(asked.first, attachment_summaries),
        lastQuestion=_prep_question(asked.last, attachment_summaries),
        uploads=[
            attachment_summaries[value]
            for value in teacher_help_prep.uploads(history)
            if value in attachment_summaries
        ],
        askedStars=_asked_stars(asked_records, content),
    )


# As many topics as a question's prep summary names.
_PREP_TOPIC_LIMIT = 5


def _asked_records(conversation_id: str) -> list[dict[str, Any]]:
    """The asked-knowledge records of this conversation, newest first.

    The request opens without them rather than not at all, as it does without
    its attachments: its asked topics and stars are then empty.
    """
    try:
        return asked_knowledge_repo.list_for_conversation(conversation_id)
    except Exception as exc:
        logger.warning(
            "help_request_asked_topics_unavailable error_class=%s", type(exc).__name__
        )
        return []


def _asked_topics(records: list[dict[str, Any]]) -> list[str]:
    """What the questions of this conversation asked about, newest first, once each."""
    topics: dict[str, str] = {}
    for record in records:
        for name in record.get("knowledge_points") or []:
            if isinstance(name, str) and name.casefold() not in topics:
                topics[name.casefold()] = name
    return list(topics.values())[:_PREP_TOPIC_LIMIT]


def _prep_question(
    message: learning_session.Message | None,
    attachment_summaries: Mapping[str, AttachmentSummary],
) -> TeacherPrepQuestion | None:
    if message is None:
        return None
    return TeacherPrepQuestion(
        messageId=message.id,
        content=message.content,
        createdAt=message.created_at,
        attachments=[
            attachment_summaries[value]
            for value in message.attachment_ids
            if value in attachment_summaries
        ],
    )


def _asked_stars(
    records: list[dict[str, Any]], content: student_evidence.Content
) -> list[TeacherAskedStar]:
    """The stars the conversation's Ask answers named, newest first (#517).

    Titled from the catalog in the teacher's language; a star the catalog no
    longer has is left out. As the asked topics, the request opens without
    them rather than not at all.
    """
    unit_ids = teacher_help_prep.asked_star_ids(records)
    if not unit_ids:
        return []
    try:
        titles = {str(unit.get("id") or ""): unit.get("title") for unit in content.units}
    except Exception as exc:
        logger.warning(
            "help_request_asked_stars_unavailable error_class=%s", type(exc).__name__
        )
        return []
    return [
        TeacherAskedStar(unitId=unit_id, title=_text(titles.get(unit_id)) or unit_id)
        for unit_id in unit_ids
        if unit_id in titles
    ][:_PREP_TOPIC_LIMIT]


def _common_error_cause(
    evidence: student_evidence.StudentEvidence, locale: str
) -> TeacherErrorCause | None:
    """The student's commonest recent error cause, from their answer receipts (#452).

    As the asked topics, the request opens without it rather than not at all.
    """
    try:
        common = evidence.most_common_error_cause
        recent = sum(item.count for item in evidence.recent_error_causes)
    except Exception as exc:
        logger.warning(
            "help_request_error_causes_unavailable error_class=%s", type(exc).__name__
        )
        return None
    if common is None:
        return None
    return TeacherErrorCause(
        category=common.category,
        misconception=common.misconception_in(locale),
        count=common.count,
        recentMistakes=recent,
    )


def _ai_helped_stars(evidence: student_evidence.StudentEvidence) -> list[TeacherAiHelpedStar]:
    """The lit stars the student answered right mostly after asking AI (#451).

    The rule is `knowledge_mastery_service.lit_mostly_with_ai`. As the asked
    topics, the request opens without them rather than not at all.
    """
    try:
        unit_ids = knowledge_mastery_service.lit_mostly_with_ai(evidence)
        counts = evidence.right_answers_by_unit
        titles = {str(unit.get("id") or ""): unit.get("title") for unit in evidence.content.units}
    except Exception as exc:
        logger.warning(
            "help_request_ai_helped_stars_unavailable error_class=%s", type(exc).__name__
        )
        return []
    return [
        TeacherAiHelpedStar(
            unitId=unit_id,
            title=_text(titles.get(unit_id)) or unit_id,
            independent=counts[unit_id].independent,
            askedAi=counts[unit_id].asked_ai,
        )
        for unit_id in unit_ids
    ]


@router.get("/me/help-requests/{request_id}/attachments/{attachment_id}/content")
async def download_help_request_attachment(
    loaded: _HelpRequestAttachment = Depends(_help_request_attachment_dependency),
    settings: Settings = Depends(config.settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """The content of an attachment the student sent in this help request (#140)."""
    prepared = attachment_service.prepare_saved_attachment_download(
        dict(loaded.attachment), s3=aws.client(Kind.S3), settings=settings
    )
    return StreamingResponse(
        prepared.iter_bytes(),
        media_type=prepared.media_type,
        headers={
            **prepared.public_headers(),
            "X-Correlation-ID": correlation_id,
        },
    )


@router.patch("/me/help-requests/{request_id}", response_model=TeacherHelpRequestSummary)
async def update_help_request(
    request_id: str,
    body: UpdateStatusRequest,
    authorized: AuthorizedResource = Depends(_help_request(AuthorizationAction.RESOLVE)),
    actor: Actor = Depends(get_actor),
):
    """Take a help request (`in_progress`) or finish it (`resolved`).

    The teacher it is offered to takes it with their first write, and finishing
    it straight from the offer takes and finishes it at once (#66).
    """
    conv = dict(authorized.value)
    _refuse_unless_held(conv, actor.user_id)
    written = help_requests.take_or_finish(
        conv,
        teacher_id=actor.user_id,
        target=body.status,
        now=_now(),
        resolution_note=body.resolutionNote,
        table=db_table.table(),
    )
    view = help_requests.teacher_view(written)
    return _help_request_summary(view, student_name=_get_student_name(view.student_id))


@router.post("/me/help-requests/{request_id}/classroom", response_model=ClassroomEntry)
async def enter_classroom(
    request_id: str,
    authorized: AuthorizedResource = Depends(_help_request(AuthorizationAction.RESPOND)),
    actor: Actor = Depends(get_actor),
):
    """The teacher's credentials for this help request's classroom (#467).

    Only the teacher holding the request, while it is in progress, and only
    one asked in the classroom mode (#481); an offer alone does not let a
    teacher in.
    """
    help_requests.admit_teacher_to_classroom(authorized.value, actor.user_id)
    credentials = classroom.enter(
        authorized.ref.resource_id,
        user_name=classroom.display_name(actor.user_id, fallback="Teacher"),
    )
    return ClassroomEntry.of(credentials)


@router.post("/me/help-requests/{request_id}/notes", response_model=TeacherNoteOut)
async def add_note(
    request_id: str,
    body: AddNoteRequest,
    authorized: AuthorizedResource = Depends(_help_request(AuthorizationAction.RESPOND)),
    actor: Actor = Depends(_reply_upload_actor),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Add a teacher note to a help request (stored in the conversation).

    Only the teacher the request is with posts into it, and its images with it
    (#145): the request's authorization is settled before an upload is looked at.
    The teacher it is only offered to accepts it first (`PATCH status=in_progress`);
    their reply is refused `help_request_not_accepted` and changes nothing (#479).
    """
    conv = dict(authorized.value)
    teacher_id = actor.user_id
    teacher_profile = user_repo.get_user(teacher_id)
    reply_fields = teacher_reply_service.normalize_teacher_reply(body.content, body.richContent)
    reply_images = attachment_service.prepare_reply_images(
        [reference.upload_id for reference in body.attachmentIds or []], actor
    )
    _refuse_unless_held(conv, teacher_id)
    written = help_requests.reply(
        conv,
        teacher_id=teacher_id,
        author_name=_optional_text((teacher_profile or {}).get("name")),
        content=reply_fields["teacher_response"],
        rich=reply_fields["teacher_response_rich"],
        format=reply_fields["teacher_response_format"],
        images=reply_images,
        now=_now(),
        table=db_table.table(),
    )
    with suppress(Exception):
        telemetry.record(
            "teacher_replied",
            actor_user_id=teacher_id,
            role="teacher",
            response_ms=telemetry.since_ms(conv.get("escalated_at")),
        )
    return _note_out(written, written.attachments)
