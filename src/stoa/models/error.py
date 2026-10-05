"""Error bodies as they are sent, declared so OpenAPI can describe them.

The bodies themselves are built in `stoa.security.errors` and
`stoa.security.attachment_errors`; these models only name their shape. FastAPI
wraps an `HTTPException` detail as `{"detail": ...}`, so most response models
carry that envelope; the sign-in refusals sent as a bare `JSONResponse` do not.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, RootModel

from stoa.security.attachment_errors import AttachmentErrorCode
from stoa.security.errors import SecurityErrorCode


class _ErrorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SecurityErrorBody(_ErrorModel):
    """`safe_error_body`: an authentication or authorization refusal."""

    code: SecurityErrorCode
    message: str
    correlation_id: str = Field(alias="correlationId")


class AttachmentErrorBody(_ErrorModel):
    """`safe_attachment_error_body`: an upload or message-command failure."""

    code: AttachmentErrorCode
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


class SignInUnauthorizedResponse(RootModel[SecurityErrorBody | SecurityErrorResponse]):
    """401 from sign-in and refresh, which take no bearer token.

    The identity provider's refusal (`invalid_credentials`, `invalid_token`) is
    sent by `public_auth_error_response` as the security body itself, with no
    `detail` envelope. A token the provider issued that then fails verification
    here is refused inside `detail`, like any other route.
    """


class NotFoundResponse(_ErrorModel):
    """404: either a route's own sentence or a hidden or missing resource."""

    detail: str | SecurityErrorBody


class AttachmentErrorResponse(_ErrorModel):
    detail: AttachmentErrorBody
