"""An unexpected failure: a route raised something nothing else handles.

A refusal the platform means to send is a `RuleViolation`; a 422 is FastAPI's
validation. Anything else a route or its dependencies raise used to fall
through to Starlette's `ServerErrorMiddleware`, which answers a bare
`Internal Server Error` with no body to read, no correlation header and no
CORS headers, so the client had nothing to match against the log (#543's
draft-accept 500).

`UnexpectedFailureMiddleware` sits just inside `CorrelationMiddleware`, so the
failure is answered with the standard body, `{"detail": {"code",
"message", "correlationId"}}` under the code `internal_error`, the header is
set on the way out, and CORS still wraps the response. The traceback is
logged at ERROR, once, with the same correlation id as the body written into
the line itself (Lambda's Text format keeps only the message, #503).

A Starlette handler for bare `Exception` would not do: it runs in
`ServerErrorMiddleware`, outside every other middleware, after the
correlation scope has closed.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from starlette.requests import Request

from stoa.rule_violation import (
    RuleContract,
    RuleViolation,
    register_codes,
    request_correlation_id,
    violation_response,
)
from stoa.services import locale_service

logger = logging.getLogger(__name__)


class ServerErrorCode(StrEnum):
    INTERNAL_ERROR = "internal_error"

    @property
    def contract(self) -> RuleContract:
        return SERVER_ERROR_REGISTRY[self]


# Its message is the catalog's `error.internal_error`
# (`stoa.services.message_catalog.errors.server`). Not retryable: the request
# may have done part of its work before it failed, so a client does not send
# it again by itself; the person may try later, or quote the reference.
SERVER_ERROR_REGISTRY: dict[ServerErrorCode, RuleContract] = {
    ServerErrorCode.INTERNAL_ERROR: RuleContract(500, "retry_later"),
}

register_codes("server", ServerErrorCode, SERVER_ERROR_REGISTRY)


class UnexpectedFailureMiddleware:
    """Answer an unhandled exception with the standard 500 body.

    Must be added before `CorrelationMiddleware` (so it runs inside it). An
    exception after the response has started cannot be answered again; it is
    raised on, as before, for Mangum to log and close.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_tracking(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking)
        except Exception:
            if started:
                raise
            request = Request(scope)
            correlation_id = request_correlation_id(request)
            route = getattr(scope.get("route"), "path", None) or request.url.path
            logger.exception(
                "unexpected_failure method=%s route=%s correlation_id=%s",
                request.method,
                route,
                correlation_id,
            )
            response = violation_response(
                RuleViolation(ServerErrorCode.INTERNAL_ERROR),
                correlation_id,
                locale_service.locale_from_accept_language(
                    request.headers.get("accept-language")
                )
                or locale_service.request_locale(),
            )
            await response(scope, receive, send)
