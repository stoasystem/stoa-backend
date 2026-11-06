"""规则违反 (rule violation): a request broke one of the platform's rules.

A rule violation is the one way the platform refuses a request: an exception
naming a stable `code`, raised wherever the rule is decided and rendered here,
once, into the response. It replaces the hand-written conversions every router
used to make from a domain error to an `HTTPException`.

Each domain keeps its own codes (`SecurityErrorCode`, `AttachmentErrorCode`,
`AskQuestionErrorCode`, ...) and gives each one a `RuleContract`: the HTTP
status, what a client should do about it, whether and when it may retry, and
which public fields its body may carry. Its message is not in the contract but
in the message catalog, under `error.<code>`, in four languages. The domain
registers its codes here, and no string may name two codes, whichever domains
they are in: the client reads the code alone.

The body is always `{"detail": {"code", "message", "correlationId", ...}}`,
with the public fields the contract declares after those three. `params` fill
the message and never reach the body. `X-Correlation-ID` is always set, and is
the same id the request carried throughout (`CorrelationMiddleware`); a
`Retry-After` header is set only when the contract carries a retry time.

`message` is rendered in the language the request asked for
(`Accept-Language`), falling back to the catalog's default, German (#273). A
client that translates by code ignores it; the English web client shows it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, Self
from uuid import uuid4

from stoa.services import locale_service, message_catalog

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

CORRELATION_HEADER = "X-Correlation-ID"

# The fields a body may carry besides code, message and correlationId. A
# contract names the ones its code uses; anything else stays off the wire.
PUBLIC_FIELDS = frozenset({"conversationId", "retryAt", "retryAfterSeconds", "action", "fields"})

# Retry-After is a hint to wait: at least a second, at most a day.
_RETRY_AFTER_BOUNDS = (1, 86_400)


@dataclass(frozen=True, slots=True)
class RuleContract:
    """What a client is told about one code.

    Generalised from the upload subsystem's `AttachmentErrorContract`: status,
    client action, then retry. The message it once carried is the catalog's
    `error.<code>` (#273); `catalog_key` names it.

    `retry_after_seconds` sets the `Retry-After` header; a raise site may give
    a different time for the one instance (`RuleViolation.retrying_after`) but
    only for a code whose contract carries one. `public_fields` is the closed
    set of extra body fields this code may carry.
    """

    http_status: int
    action: str | None = None
    retryable: bool = False
    idempotent_only: bool = False
    max_attempts: int = 0
    retry_after_seconds: int | None = None
    public_fields: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not 400 <= self.http_status <= 599:
            raise ValueError(f"a rule violation answers 4xx or 5xx, not {self.http_status}")
        unknown = set(self.public_fields) - PUBLIC_FIELDS
        if unknown:
            raise ValueError(f"undeclared public fields: {sorted(unknown)}")
        if self.retry_after_seconds is not None:
            _check_retry_after(self.retry_after_seconds)

    @property
    def client_action(self) -> str | None:
        """The upload contract's name for `action`."""
        return self.action


def _check_retry_after(seconds: int) -> None:
    low, high = _RETRY_AFTER_BOUNDS
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not low <= seconds <= high:
        raise ValueError(f"Retry-After must be {low} to {high} seconds")


class RuleCode(Protocol):
    """A domain's code: its stable string, and the contract it is sent under."""

    @property
    def value(self) -> str: ...

    @property
    def contract(self) -> RuleContract: ...


def catalog_key(code: RuleCode | str) -> str:
    """The message catalog key for a code (`error.<code>`)."""
    return f"error.{code if isinstance(code, str) else code.value}"


def render_message(
    code: RuleCode | str, locale: str | None = None, **params: object
) -> str:
    """A code's message in `locale`, else the request's language, else German."""
    resolved = locale or locale_service.request_locale() or locale_service.DEFAULT_LOCALE
    return message_catalog.text(catalog_key(code), resolved, **params)


# ── Code registry ────────────────────────────────────────────────────────────

_REGISTRY: dict[str, tuple[str, RuleCode]] = {}


def register_codes(domain: str, codes: type[StrEnum], contracts: Mapping[Any, RuleContract]) -> None:
    """Enter one domain's codes, refusing a string another code already names.

    Called where each domain defines its codes, so importing the application
    fails on a collision rather than a client misreading one code as another.
    The contracts must cover the domain's codes exactly.
    """
    members = set(codes)
    if set(contracts) != members:
        missing = sorted(str(code) for code in members - set(contracts))
        extra = sorted(str(code) for code in set(contracts) - members)
        raise RuntimeError(
            f"{domain} error contracts are not exhaustive: missing={missing}, extra={extra}"
        )
    for code in codes:
        if not isinstance(contracts[code], RuleContract):
            raise RuntimeError(f"{domain} code {code.value} has no RuleContract")
        owner = _REGISTRY.get(code.value)
        if owner is not None and owner[1] is not code:
            raise RuntimeError(
                f"error code {code.value!r} is registered by both {owner[0]} and {domain}"
            )
    for code in codes:
        _REGISTRY[code.value] = (domain, code)


def registered_codes() -> dict[str, tuple[str, RuleCode]]:
    """Every registered code string, with its domain and code."""
    return dict(_REGISTRY)


def registered_code(value: str) -> RuleCode:
    """The code a string names. Raises `KeyError` for an unregistered one."""
    return _REGISTRY[value][1]


# ── Correlation ──────────────────────────────────────────────────────────────

_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_current_correlation_id: ContextVar[str | None] = ContextVar("stoa_correlation_id", default=None)


def new_correlation_id() -> str:
    return str(uuid4())


def normalize_correlation_id(value: str | None) -> str:
    """Keep a bounded opaque id; replace malformed input without echoing it."""
    candidate = str(value or "").strip()
    return candidate if _CORRELATION_ID.fullmatch(candidate) else new_correlation_id()


def current_correlation_id() -> str:
    """The id of the request being served, or a fresh one outside any request."""
    return _current_correlation_id.get() or new_correlation_id()


@contextmanager
def correlation_scope(correlation_id: str) -> Iterator[str]:
    """Serve one request under `correlation_id` (also for tests and workers)."""
    token = _current_correlation_id.set(correlation_id)
    try:
        yield correlation_id
    finally:
        _current_correlation_id.reset(token)


def request_correlation_id(request: Request) -> str:
    """The request's one correlation id, minted at the door.

    `CorrelationMiddleware` puts it on `request.state`; an application without
    the middleware (a test's bare app) gets one minted on first use and kept.
    A client's own `X-Correlation-ID` is never taken.
    """
    existing = getattr(request.state, "stoa_correlation_id", None)
    if existing:
        return str(existing)
    correlation_id = _current_correlation_id.get() or new_correlation_id()
    request.state.stoa_correlation_id = correlation_id
    return correlation_id


class CorrelationMiddleware:
    """Mint one correlation id per request and send it back on every response.

    The id is on `request.state` and in a ContextVar for the whole request, so
    an authorization audit record, a log line and the refusal's body all name
    the same one; the response header carries it whether the request succeeded
    or not. An inbound `X-Correlation-ID` is ignored. Plain ASGI for the same
    reasons as the application's other middleware.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        correlation_id = new_correlation_id()
        scope.setdefault("state", {})["stoa_correlation_id"] = correlation_id

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                from starlette.datastructures import MutableHeaders

                MutableHeaders(scope=message)[CORRELATION_HEADER] = correlation_id
            await send(message)

        with correlation_scope(correlation_id):
            await self.app(scope, receive, send_with_id)


# ── The exception ────────────────────────────────────────────────────────────


class RuleViolation(Exception):
    """A request broke a rule; `code` says which.

    Domain subclasses (`SecurityDecisionError`, `AttachmentDecisionError`, ...)
    keep their own constructors; one written fresh can use this one:
    `RuleViolation(code, internal_detail=..., params={...}, conversationId=...)`.

    - `params` fill the code's message and never reach the body.
    - public fields are the contract-declared extras of the body.
    - `internal_detail` is for logs only.
    """

    code: RuleCode
    internal_detail: str | None
    correlation_id: str | None

    def __init__(
        self,
        code: RuleCode,
        *,
        internal_detail: str | None = None,
        params: Mapping[str, object] | None = None,
        **public: object,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.internal_detail = internal_detail
        self.correlation_id = None
        if params:
            self.with_params(**params)
        if public:
            self.with_public(**public)

    # Subclasses are slotted dataclasses; what the base adds lives in the
    # instance dict every exception has, created on first write.

    @property
    def contract(self) -> RuleContract:
        return self.code.contract

    @property
    def status_code(self) -> int:
        return self.contract.http_status

    @property
    def catalog_key(self) -> str:
        return catalog_key(self.code)

    @property
    def params(self) -> Mapping[str, object]:
        return dict(self.__dict__.get("_rule_params", {}))

    @property
    def public(self) -> dict[str, object]:
        return dict(self.__dict__.get("_rule_public", {}))

    @property
    def retry_after_seconds(self) -> int | None:
        return self.__dict__.get("_rule_retry_after", self.contract.retry_after_seconds)

    def with_params(self, **values: object) -> Self:
        self.__dict__.setdefault("_rule_params", {}).update(values)
        return self

    def with_public(self, **fields: object) -> Self:
        """Add public body fields; only those the contract declares are allowed."""
        undeclared = set(fields) - set(self.contract.public_fields)
        if undeclared:
            raise ValueError(
                f"{self.code.value} does not declare public fields {sorted(undeclared)}"
            )
        self.__dict__.setdefault("_rule_public", {}).update(fields)
        return self

    def retrying_after(self, seconds: int) -> Self:
        """Ask the client to wait `seconds`, for a code whose contract retries."""
        if self.contract.retry_after_seconds is None:
            raise ValueError(f"{self.code.value} carries no retry time")
        _check_retry_after(seconds)
        self.__dict__["_rule_retry_after"] = seconds
        return self

    def message(self, locale: str | None = None) -> str:
        """The code's message, filled with `params`, in `locale` or the request's."""
        return render_message(self.code, locale, **self.params)

    def public_body(self, locale: str | None = None) -> dict[str, object]:
        """The `detail` this violation is sent as."""
        body: dict[str, object] = {
            "code": self.code.value,
            "message": self.message(locale),
            "correlationId": normalize_correlation_id(self.correlation_id)
            if self.correlation_id
            else current_correlation_id(),
        }
        declared = self.contract.public_fields
        body.update(
            (name, value) for name, value in self.public.items() if name in declared
        )
        return body

    def headers(self) -> dict[str, str]:
        retry_after = self.retry_after_seconds
        return {"Retry-After": str(retry_after)} if retry_after is not None else {}

    def log(self, route: str) -> None:
        """Record the violation as it leaves; a domain may say more."""


def violation_response(
    violation: RuleViolation,
    correlation_id: str | None = None,
    locale: str | None = None,
) -> JSONResponse:
    """Render a violation: the one place a rule's refusal becomes HTTP."""
    from starlette.responses import JSONResponse

    if correlation_id is not None:
        violation.correlation_id = correlation_id
    elif not violation.correlation_id:
        violation.correlation_id = current_correlation_id()
    body = violation.public_body(locale)
    return JSONResponse(
        status_code=violation.status_code,
        content={"detail": body},
        headers={**violation.headers(), CORRELATION_HEADER: str(body["correlationId"])},
    )


async def handle_rule_violation(request: Request, exc: Exception) -> JSONResponse:
    """The application's handler for every `RuleViolation`."""
    assert isinstance(exc, RuleViolation)
    correlation_id = request_correlation_id(request)
    exc.correlation_id = correlation_id
    route = getattr(request.scope.get("route"), "path", None) or request.url.path
    exc.log(route)
    return violation_response(exc, correlation_id, _request_locale(request))


def _request_locale(request: Request) -> str | None:
    """The language the request asked for.

    `RequestLocaleMiddleware` binds it for the application; a test's bare app
    has no such middleware, so the header is read here as well.
    """
    return locale_service.locale_from_accept_language(
        request.headers.get("accept-language")
    ) or locale_service.request_locale()


def install_rule_violation_handler(app) -> None:
    """Render every `RuleViolation` raised by a route or its dependencies."""
    app.add_exception_handler(RuleViolation, handle_rule_violation)
