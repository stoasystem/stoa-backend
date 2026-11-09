"""Error bodies as they are sent, declared so OpenAPI can describe them.

A rule violation is rendered by `stoa.rule_violation` as
`{"detail": {code, message, correlationId, ...public fields}}`; every route
declares that as its default error response (`RuleViolationResponse`). The
models below name narrower shapes some routes declare per status. A route's own
`HTTPException` still answers `{"detail": ...}` with whatever it was given.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from stoa.security.attachment_errors import AttachmentErrorCode
from stoa.security.errors import SecurityErrorCode
from stoa.services.ask_question_errors import AskQuestionErrorCode


class _ErrorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SecurityErrorBody(_ErrorModel):
    """`safe_error_body`: an authentication or authorization refusal."""

    code: SecurityErrorCode
    message: str
    correlation_id: str = Field(alias="correlationId")


class AttachmentErrorBody(_ErrorModel):
    """`safe_attachment_error_body`: an upload or message-command failure."""

    code: AttachmentErrorCode | AskQuestionErrorCode
    message: str
    correlation_id: str = Field(alias="correlationId")


class UnauthenticatedResponse(_ErrorModel):
    """401: no usable bearer token.

    A request with no bearer header is refused by `HTTPBearer` itself with the
    sentence "Not authenticated"; a token that is malformed, expired or from
    the wrong issuer is refused with the security body.
    """

    detail: str | SecurityErrorBody


class SecurityErrorResponse(_ErrorModel):
    detail: SecurityErrorBody


class NotFoundResponse(_ErrorModel):
    """404: either a route's own sentence or a hidden or missing resource."""

    detail: str | SecurityErrorBody


class AttachmentErrorResponse(_ErrorModel):
    detail: AttachmentErrorBody


class FirstMessageRefusalBody(_ErrorModel):
    """A new conversation's first message was refused; the conversation exists (#61).

    The refusal is the allowance's (`action`) or an attachment decision's
    (`correlationId`) body, with the id of the conversation already made, so a
    client sends the message again into it under the key `initial-<id>`.
    """

    code: str
    message: str
    conversation_id: str = Field(alias="conversationId")
    correlation_id: str | None = Field(default=None, alias="correlationId")
    action: str | None = None


class FirstMessageRefusalResponse(_ErrorModel):
    detail: FirstMessageRefusalBody


class RuleViolationBody(_ErrorModel):
    """Any rule violation: a registered code, its message and the request's id.

    The optional fields are sent only by the codes whose contract declares them.
    """

    code: str = Field(description="A registered rule violation code; stable, never renamed.")
    message: str
    correlation_id: str = Field(alias="correlationId")
    conversation_id: str | None = Field(default=None, alias="conversationId")
    retry_at: str | None = Field(default=None, alias="retryAt")
    retry_after_seconds: int | None = Field(default=None, alias="retryAfterSeconds")
    action: str | None = None
    fields: list[str] | None = Field(
        default=None,
        description="The input fields that broke the rule (`validation_failed`, `invalid_manifest`).",
    )


class RuleViolationResponse(_ErrorModel):
    """The error any route may answer with (#211)."""

    detail: RuleViolationBody
