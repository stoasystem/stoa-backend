"""Teacher routes — work queue, takeover, reply, resolve."""
import logging

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, NamedTuple, Protocol, runtime_checkable

from fastapi import APIRouter, Depends, Path
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
from stoa.deps import get_actor
from stoa.models.attachment import AttachmentSummary, ReplyImageReference
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
    by_grant,
    get_authorization_context,
    loaded_declaration,
    path,
    service_enforced,
    teacher_task_resource,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor, CanonicalRole
from stoa.security.request_correlation import get_request_correlation_id
from stoa.services.ai_teacher_tools_errors import AiTeacherToolsViolation
from stoa.services import (
    ai_teacher_tools_service,
    attachment_service,
    help_requests,
    learning_session,
    teacher_assistance_service,
    teacher_dispatch_service,
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


# Canonical teacher portal, availability, help-request, and AI-tool routes.

#: The teacher's own portal record (an admin has one too).
_PORTAL_SELF = {
    CanonicalRole.TEACHER: AuthorizationPurpose.SELF_SERVICE,
    CanonicalRole.ADMIN: AuthorizationPurpose.SELF_SERVICE,
}
#: A help request, and what was sent in it, is read and answered for help.
_TEACHER_HELP = {CanonicalRole.TEACHER: AuthorizationPurpose.TEACHER_HELP}
#: The AI teacher tools: under their own purpose only for a holder of the grant.
_TOOL_PURPOSE = by_grant(
    "ai_teacher_tools_operator",
    AuthorizationPurpose.AI_TEACHER_TOOLS,
    otherwise=AuthorizationPurpose.TEACHER_HELP,
)
_TEACHER_TOOLS = {CanonicalRole.TEACHER: _TOOL_PURPOSE, CanonicalRole.ADMIN: _TOOL_PURPOSE}

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


def _ai_teacher_draft(action: AuthorizationAction):
    """A draft, by the route's `draft_id`, bound to its student and request."""
    return authorized(ResourceType.AI_TEACHER_DRAFT, action, path("draft_id"), _TEACHER_TOOLS)


async def _current_help_requests(
    actor: Actor, context: AuthorizationContext
) -> list[TeacherItem]:
    """The help requests this teacher may read, each one decided as it is listed."""
    current: list[TeacherItem] = []
    for record in help_requests.list_all(table=db_table.table()):
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
    # The prep for a help request raised from Ask (#143): the knowledge points
    # the answers in this conversation named, newest first, as the prep summary
    # of a question names its topics. Empty when none were recorded.
    weakTopics: list[str] = Field(default_factory=list)


def _help_request_summary(
    view: help_requests.TeacherView, *, student_name: str
) -> TeacherHelpRequestSummary:
    return TeacherHelpRequestSummary(
        requestId=view.request_id,
        conversationId=view.conversation_id,
        studentName=student_name,
        subject=view.subject,
        grade=view.grade,
        status=view.status,
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


async def _authorize_ai_question_context(
    question_id: str, actor: Actor, context: AuthorizationContext
) -> AuthorizedResource:
    """The help request an exercise draft is for, loaded first (a body names it)."""
    # A question id is a help request's id (#189).
    question = help_requests.get(question_id)
    ref = (
        teacher_task_resource(ResourceType.QUESTION, question).ref
        if question
        else ResourceRef(ResourceType.QUESTION, question_id, question_id)
    )
    return await authorize_loaded(
        actor, ref, question, AuthorizationAction.CREATE, _TEACHER_TOOLS, context
    )


_ai_question_context = authorized(
    ResourceType.QUESTION, AuthorizationAction.CREATE, path("question_id"), _TEACHER_TOOLS
)


@loaded_declaration(ResourceType.AI_TEACHER_DRAFT, AuthorizationAction.CREATE, _TEACHER_TOOLS)
async def _exercise_context_dependency(
    body: ExerciseDraftRequest,
    actor: Actor = Depends(get_actor),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> AuthorizedResource:
    """What an exercise draft is made for: a help request, else one student."""
    try:
        if body.questionId:
            return await _authorize_ai_question_context(body.questionId, actor, context)
        student = user_repo.get_user(body.studentId)
        if not student or student.get("role") not in {None, "student"}:
            student_context = None
        else:
            student_context = {
                "draft_id": f"student-context:{body.studentId}",
                "student_id": body.studentId,
                "account_status": student.get("account_status") or student.get("status"),
            }
        ref = ResourceRef(
            ResourceType.AI_TEACHER_DRAFT,
            f"student-context:{body.studentId}",
            str(body.studentId or ""),
        )
        return await authorize_loaded(
            actor, ref, student_context, AuthorizationAction.CREATE, _TEACHER_TOOLS, context
        )
    except SecurityDecisionError:
        raise
    except Exception as exc:
        raise SecurityDecisionError(
            SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
            internal_detail=type(exc).__name__,
        ) from exc


@loaded_declaration(ResourceType.TEACHER_HELP_REQUEST, AuthorizationAction.READ, _TEACHER_HELP)
async def _help_list_actor(
    actor: Actor = Depends(_portal_read),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> tuple[Actor, AuthorizationContext]:
    """The teacher's own portal; each listed request is decided in `_current_help_requests`."""
    return actor, context


@loaded_declaration(ResourceType.AI_TEACHER_DRAFT, AuthorizationAction.READ, _TEACHER_TOOLS)
async def _ai_draft_list_actor(
    actor: Actor = Depends(_portal_read),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> tuple[Actor, AuthorizationContext]:
    """The teacher's own portal; each listed draft is decided in the route."""
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


@router.get("/questions/{question_id}/assistance-summary", response_model=AssistanceSummaryResponse)
async def get_question_assistance_summary(
    question_id: str,
    authorized: AuthorizedResource = Depends(
        authorized(
            ResourceType.QUESTION,
            AuthorizationAction.READ,
            path("question_id"),
            _TEACHER_HELP,
        )
    ),
    actor: Actor = Depends(get_actor),
):
    """Build a bounded teacher assistance summary seed for an accessible question."""
    return teacher_assistance_service.build_summary_seed(authorized, actor)


@router.post("/questions/{question_id}/ai-tools/summary-draft", response_model=AiTeacherDraftResponse)
async def create_question_summary_draft(
    question_id: str,
    authorized: AuthorizedResource = Depends(_ai_question_context),
    actor: Actor = Depends(get_actor),
):
    """Create a reviewed AI teacher summary draft for an accessible question."""
    return ai_teacher_tools_service.create_summary_draft(authorized, actor)


@router.post("/ai-tools/exercise-drafts", response_model=AiTeacherDraftResponse)
async def create_exercise_draft(
    body: ExerciseDraftRequest,
    authorized: AuthorizedResource = Depends(_exercise_context_dependency),
    actor: Actor = Depends(get_actor),
):
    """Create a reviewed practice exercise draft from teacher-visible learning context."""
    return ai_teacher_tools_service.create_exercise_draft(
        student_id=body.studentId,
        subject=body.subject,
        topic_ids=body.topicIds,
        difficulty=body.difficulty,
        exercise_count=body.exerciseCount,
        question_id=body.questionId,
        actor=actor,
        authorized_context=authorized,
    )


@router.get("/ai-tools/drafts", response_model=AiTeacherDraftListResponse)
async def list_ai_teacher_drafts(
    student_id: str | None = None,
    status: str | None = None,
    draft_type: str | None = None,
    limit: int = 50,
    portal: tuple[Actor, AuthorizationContext] = Depends(_ai_draft_list_actor),
):
    """List visible reviewed AI teacher tool drafts."""
    actor, context = portal
    try:
        candidates = ai_teacher_tools_service.list_drafts(
            student_id=student_id,
            status=status,
            draft_type=draft_type,
            limit=limit,
        )
    except AiTeacherToolsViolation:
        raise
    except Exception as exc:
        raise SecurityDecisionError(
            SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
            internal_detail=type(exc).__name__,
        ) from exc
    items: list[AiTeacherDraftResponse] = []
    for candidate in candidates:
        try:
            loaded = teacher_task_resource(ResourceType.AI_TEACHER_DRAFT, candidate)
            authorized = await authorize_loaded(
                actor,
                loaded.ref,
                candidate,
                AuthorizationAction.READ,
                _TEACHER_TOOLS,
                context,
            )
        except SecurityDecisionError as error:
            if error.code is SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE:
                raise
            continue
        items.append(
            AiTeacherDraftResponse.model_validate(
                ai_teacher_tools_service.get_draft(authorized)
            )
        )
    return AiTeacherDraftListResponse(items=items, count=len(items))


@router.get("/ai-tools/drafts/{draft_id}", response_model=AiTeacherDraftResponse)
async def get_ai_teacher_draft(
    draft_id: str,
    authorized: AuthorizedResource = Depends(_ai_teacher_draft(AuthorizationAction.READ)),
):
    """Return one visible reviewed AI teacher tool draft."""
    return ai_teacher_tools_service.get_draft(authorized)


@router.post("/ai-tools/drafts/{draft_id}/regenerate", response_model=AiTeacherDraftResponse)
async def regenerate_ai_teacher_draft(
    draft_id: str,
    authorized: AuthorizedResource = Depends(_ai_teacher_draft(AuthorizationAction.CREATE)),
    actor: Actor = Depends(get_actor),
):
    """Create a new draft version while preserving prior draft metadata."""
    return ai_teacher_tools_service.regenerate_draft(authorized, actor)


@router.post("/ai-tools/drafts/{draft_id}/accept", response_model=AiTeacherDraftResponse)
async def accept_ai_teacher_draft(
    draft_id: str,
    body: ReviewDraftRequest | None = None,
    authorized: AuthorizedResource = Depends(_ai_teacher_draft(AuthorizationAction.UPDATE)),
    actor: Actor = Depends(get_actor),
):
    """Mark a draft as reviewed and accepted without delivering it to students."""
    return ai_teacher_tools_service.review_draft(
        authorized=authorized,
        action="accept",
        actor=actor,
        note=body.note if body else None,
    )


@router.post("/ai-tools/drafts/{draft_id}/reject", response_model=AiTeacherDraftResponse)
async def reject_ai_teacher_draft(
    draft_id: str,
    body: ReviewDraftRequest | None = None,
    authorized: AuthorizedResource = Depends(_ai_teacher_draft(AuthorizationAction.UPDATE)),
    actor: Actor = Depends(get_actor),
):
    """Mark a draft as rejected without deleting evidence."""
    return ai_teacher_tools_service.review_draft(
        authorized=authorized,
        action="reject",
        actor=actor,
        note=body.note if body else None,
    )


@router.post("/ai-tools/drafts/{draft_id}/archive", response_model=AiTeacherDraftResponse)
async def archive_ai_teacher_draft(
    draft_id: str,
    body: ReviewDraftRequest | None = None,
    authorized: AuthorizedResource = Depends(_ai_teacher_draft(AuthorizationAction.UPDATE)),
    actor: Actor = Depends(get_actor),
):
    """Archive a draft from the active teacher workflow without deleting evidence."""
    return ai_teacher_tools_service.review_draft(
        authorized=authorized,
        action="archive",
        actor=actor,
        note=body.note if body else None,
    )


@router.get("/me/help-requests", response_model=dict)
async def list_help_requests(
    portal: tuple[Actor, AuthorizationContext] = Depends(_help_list_actor),
):
    """Return only help requests currently assigned to this Actor."""
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
):
    """Get full detail of a specific help request including conversation messages."""
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
        requestMessage=view.request_message,
        messages=messages,
        notes=notes,
        firstTeacherActionAt=view.first_teacher_action_at,
        sla=view.sla,
        weakTopics=_asked_topics(conv_id),
    )


# As many topics as a question's prep summary names.
_PREP_TOPIC_LIMIT = 5


def _asked_topics(conversation_id: str) -> list[str]:
    """What the questions of this conversation asked about, newest first, once each.

    The request opens without them rather than not at all, as it does without
    its attachments.
    """
    try:
        records = asked_knowledge_repo.list_for_conversation(conversation_id)
    except Exception as exc:
        logger.warning(
            "help_request_asked_topics_unavailable error_class=%s", type(exc).__name__
        )
        return []
    topics: dict[str, str] = {}
    for record in records:
        for name in record.get("knowledge_points") or []:
            if isinstance(name, str) and name.casefold() not in topics:
                topics[name.casefold()] = name
    return list(topics.values())[:_PREP_TOPIC_LIMIT]


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
    return _note_out(written, written.attachments)
