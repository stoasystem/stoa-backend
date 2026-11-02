"""The request and response shapes of a question, shared by the routes and the package.

Moved from `routers/conversations.py` (#218) so the package never imports the
router. Every class keeps its name: the OpenAPI schema is named after them.
"""
import hashlib
import struct
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from stoa.models.attachment import AttachmentReference, AttachmentSummary
from stoa.services import ask_answer
from stoa.services.ask_answer import StructuredAnswer


class PracticeContextReference(BaseModel):
    """The exercise a question is asked beside, named by id only (#61).

    `extra="forbid"` is the rule itself, not tidiness: the wording of a question
    is read from the store by these ids, and a client that sends its own is
    refused rather than believed.
    """

    model_config = ConfigDict(extra="forbid")

    challengeId: str = Field(min_length=1, max_length=128)
    lessonId: str = Field(min_length=1, max_length=128)
    unitId: str = Field(min_length=1, max_length=128)


class MessageQuotePart(BaseModel):
    """The section of an assistant answer a quote was taken from (#132).

    Sections are named as `StructuredAnswer` names them. `index` counts from 0
    and names one entry of a list section; `answer` is a single text and takes
    none.
    """

    model_config = ConfigDict(extra="forbid")

    section: Literal["steps", "answer", "hints", "similarExercises", "knowledgePoints"]
    index: int | None = Field(default=None, ge=0, le=99)

    @model_validator(mode="after")
    def index_matches_section(self) -> "MessageQuotePart":
        if (self.section == "answer") != (self.index is None):
            raise ValueError("index names an entry of a list section, and only of one")
        return self


class MessageQuoteSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["challenge", "message"]
    id: str = Field(min_length=1, max_length=128)
    # Which section of the quoted answer, when the student quoted one (#132).
    part: MessageQuotePart | None = None

    @model_validator(mode="after")
    def part_only_of_a_message(self) -> "MessageQuoteSource":
        if self.part is not None and self.kind != "message":
            raise ValueError("only a quoted message has parts")
        return self


class MessageQuote(BaseModel):
    """A passage the student highlighted and is asking about (#61)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=ask_answer.QUOTE_MAX_CHARS)
    source: MessageQuoteSource


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    idempotencyKey: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._~-]+$")
    attachmentIds: list[AttachmentReference] | None = Field(default=None, max_length=8)
    practiceContext: PracticeContextReference | None = None
    quote: MessageQuote | None = None

    @model_validator(mode="after")
    def unique_attachments(self) -> "SendMessageRequest":
        if self.attachmentIds is not None and not self.attachmentIds:
            raise ValueError("attachmentIds must be omitted or contain at least one reference")
        identities = [reference.identity for reference in self.attachmentIds or []]
        if len(identities) != len(set(identities)):
            raise ValueError("attachment references must be unique")
        return self


def _stored_quote(value: object) -> MessageQuote | None:
    """A quote as it was stored beside a message, or nothing if it is not one."""
    if not isinstance(value, Mapping):
        return None
    try:
        return MessageQuote.model_validate(dict(value))
    except ValueError:
        return None


def _quote_payload(quote: MessageQuote | None) -> dict[str, object] | None:
    # Without a part, stored and handed to the model exactly as before parts.
    return None if quote is None else quote.model_dump(mode="json", exclude_none=True)


def _frame(framed: bytearray, value: str) -> None:
    encoded = value.encode("utf-8")
    framed.extend(struct.pack(">I", len(encoded)))
    framed.extend(encoded)


def message_request_fingerprint(body: SendMessageRequest) -> str:
    """Canonical v1 fingerprint over exact UTF-8 content and ordered typed IDs.

    The practice context and the quote (#61) are appended only when the request
    carries them, so a request without them frames exactly the bytes it framed
    before they existed and a command in flight over a deploy still replays.
    """
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
    if body.practiceContext is not None:
        framed.extend(b"\x10")
        _frame(framed, body.practiceContext.challengeId)
        _frame(framed, body.practiceContext.lessonId)
        _frame(framed, body.practiceContext.unitId)
    if body.quote is not None:
        framed.extend(b"\x11")
        _frame(framed, body.quote.text)
        _frame(framed, body.quote.source.kind)
        _frame(framed, body.quote.source.id)
        part = body.quote.source.part
        if part is not None:
            # Appended only when present, like the fields above (#132).
            framed.extend(b"\x12")
            _frame(framed, part.section)
            framed.extend(struct.pack(">i", -1 if part.index is None else part.index))
    return hashlib.sha256(bytes(framed)).hexdigest()


def _stored_structured(value: object) -> StructuredAnswer | None:
    """The sections stored beside an answer, or nothing for one written before them."""
    if not isinstance(value, Mapping):
        return None
    try:
        return StructuredAnswer.model_validate(dict(value))
    except ValueError:
        return None


def _structured_payload(structured: StructuredAnswer | None) -> dict[str, object] | None:
    return None if structured is None else structured.model_dump(mode="json")


class TargetUnit(BaseModel):
    """The star on the student's map an answer offers to take them to (#124)."""

    unitId: str


def _target_unit(unit_id: object) -> TargetUnit | None:
    return TargetUnit(unitId=unit_id) if isinstance(unit_id, str) and unit_id else None


class ChatMessage(BaseModel):
    id: str
    conversationId: str
    role: str
    content: str
    createdAt: str
    status: str = "sent"
    attachments: list[AttachmentSummary] = Field(default_factory=list)
    # A teacher message's author, as named when it was written (#65); absent
    # on every other message and on teacher messages written before.
    authorName: str | None = None
    # The passage the student highlighted when they asked (#61); absent on
    # every other message and on messages sent before quoting existed.
    quote: MessageQuote | None = None
    # An assistant answer's sections (#132); `content` is the same answer
    # joined into text. None on every other message and on answers written
    # before sections were kept.
    structured: StructuredAnswer | None = None
    # The star the student asked to go to, on an assistant answer that
    # recognised one on their map (#124). None on every other message.
    targetUnit: TargetUnit | None = None


class SendMessageResponse(BaseModel):
    studentMessage: ChatMessage
    assistantMessage: ChatMessage


class MessageAcceptedResponse(BaseModel):
    """The message is stored and its answer is on its way (202).

    Where it stands is read at `GET /conversations/{id}/generation` with this
    idempotency key.
    """

    conversationId: str
    commandId: str
    idempotencyKey: str
    status: Literal["message_committed"] = "message_committed"
    studentMessage: ChatMessage


class GenerationProgressResponse(BaseModel):
    conversationId: str
    steps: list[str] = Field(default_factory=list)
    # When these steps were written, so a reader can tell them from the steps
    # of a previous answer in the same conversation.
    updatedAt: str = ""
    # Set only when the reader names the message's idempotency key: where that
    # command stands. A `failed` command that is `retryable` may be sent again
    # with the same key; `assistantMessageId` names the answer once `completed`.
    commandId: str | None = None
    status: Literal["message_committed", "ai_running", "completed", "failed"] | None = None
    attempt: int | None = None
    assistantMessageId: str | None = None
    failureCategory: str | None = None
    retryable: bool | None = None
