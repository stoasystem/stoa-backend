"""模型调用 (#435, #436): ask Claude once, before a deadline, for one forced tool answer.

`call` is the one way in. The caller hands over the system prompt, the
messages (images ride in them), the one tool the answer must come through, the
output limit and temperature, the deadline, and optionally an admission hook,
a callback for the partial tool input and a correlation id. The model id is
read from the configuration.

The system prompt comes in two parts (#442). `system` is what every call of
its kind shares, word for word; with the tool, which is sent ahead of it, it
is the prefix the provider caches, so only the first call in a while pays full
price for it. `system_tail`, when given, is what changes from call to call
(who is asking, in which subject, in which language), sent after the cache
point. A prefix shorter than the model's minimum (1024 tokens on Sonnet 4.6)
is simply not cached: the call is the same, and nothing is written or read.

Inside, the order is fixed:

1. build the request: the body that is sent, and from it the body that is
   counted (`_count_body`, the one place the two differ);
2. count its input tokens, when there is an admission hook to tell;
3. ask the admission hook, once, with the input tokens and the output limit;
4. check the deadline;
5. send it, streamed, once.

The result is one of three, closed:

- `Answered`: the tool's input as the model wrote it (JSON text), with the usage;
- `PaidUnusable`: the reply came back and was paid for, but cannot be used
  (cut off at the output limit, or no call of the tool), with the usage;
- `NotSent`: nothing usable was paid for, and whether the same call may be
  tried again.

Who pays follows from the admission hook (`CostClass`): a call made with
one is charged to the allowance the hook reserved from (an Ask answer, a
weekly report, #557), one made without is the provider's cost to STOA alone
(the probes). The usage of every paid reply carries it.

The call does not know what the tool's input means: whether an answer is good
is the caller's to judge. Failure categories are the strings the rest of the
service already stores (`provider_token_count_unavailable`,
`deadline_exceeded`, `provider_error`, ...).

Where the provider is reached is the adapter's (`adapter.Adapter`): Bedrock in
production (`bedrock.BedrockAdapter`), the in-memory fake in tests
(`fake.FakeAdapter`). `install` is the one place a test puts its adapter, as
`stoa.aws.install` is for clients.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import logging
import time
from typing import Any

from stoa import config
from stoa.models.allowance import MAX_EXACT_COUNT, ProviderUsageEvidence
from stoa.security.private_telemetry import emit_private_event
from stoa.services.model_call.adapter import Adapter, MalformedStream, ProviderError

logger = logging.getLogger(__name__)

ANTHROPIC_VERSION = "bedrock-2023-05-31"

# Tool fields that shape only how the reply is streamed. CountTokens refuses
# them ("Extra inputs are not permitted", measured against production Bedrock
# on 2026-11-15, #430) and they add no input tokens, so the count is asked
# without them.
_STREAM_ONLY_TOOL_FIELDS = frozenset({"eager_input_streaming"})

# The failure categories the call itself decides. A refusal of the admission
# hook carries the hook's own.
TOKEN_COUNT_UNAVAILABLE = "provider_token_count_unavailable"
DEADLINE_EXCEEDED = "deadline_exceeded"
PROVIDER_ERROR = "provider_error"
MALFORMED_RESPONSE = "malformed_response"
MALFORMED_PROVIDER_USAGE = "malformed_provider_usage"
INCOMPLETE_OUTPUT = "incomplete_output"

# Bedrock's error text is cut to about this many characters before it is logged.
_PROVIDER_MESSAGE_CHARS = 300

# Where the shared prefix ends (#442): the default five-minute cache, renewed
# by every call that reads it.
CACHE_POINT = {"type": "ephemeral"}


# ── What the caller hands over ────────────────────────────────────────────────


class CostClass(StrEnum):
    """Who pays for a call, as its admission hook says: there is one, or there is none."""

    # Admitted by the hook, so charged to the allowance it reserved from.
    USER_ALLOWANCE = "user_allowance"
    # No hook: STOA pays the provider and no one's allowance is touched.
    PROVIDER_COST_ONLY = "provider_cost_only"

    @classmethod
    def of(cls, admission: AdmissionHook | None) -> CostClass:
        return cls.PROVIDER_COST_ONLY if admission is None else cls.USER_ALLOWANCE


@dataclass(frozen=True, slots=True)
class Tool:
    """The one tool the answer is handed over through; the request forces it."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    # The provider holds the input to `input_schema`.
    strict: bool = False


@dataclass(frozen=True, slots=True)
class Admit:
    """The admission hook's yes: the call may be sent."""


@dataclass(frozen=True, slots=True)
class Refuse:
    """The admission hook's no, under the failure category the caller stores.

    `detail` is for the caller's own diagnostics; it is never shown.
    """

    category: str
    detail: str | None = None


AdmissionHook = Callable[[int, int], "Admit | Refuse"]
"""Called once, after the count: (input tokens, output limit) -> Admit or Refuse.

It reserves what the call may cost and records that the call is about to be
made; anything it raises is the caller's and is not caught here.
"""


# ── What comes back ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Usage:
    """What one paid reply cost, exactly as the provider reported it.

    `input_tokens` is every input token the reply read, as many as the request
    is counted at; of them, `cache_write_input_tokens` were written to the
    provider's prompt cache and `cache_read_input_tokens` read from it (#442).
    The three are priced differently (a write at about 1.25 times a plain input
    token, a read at about a tenth); a student's weekly allowance counts them
    all alike, as `input_tokens`.
    """

    input_tokens: int
    output_tokens: int
    request_id: str
    message_id: str
    model: str
    inference_profile_id: str
    observed_at: datetime
    cost_class: CostClass
    cache_write_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def message_id_digest(self) -> str:
        return _digest(self.message_id, domain="bedrock-provider-message")

    def evidence(self, *, effect_id: str) -> ProviderUsageEvidence:
        """The content-free usage evidence of this reply, charged to `effect_id`.

        Raises `ValueError` for a blank `effect_id`.
        """
        effect = effect_id.strip()
        if not effect:
            raise ValueError("effect_id")
        request_id_digest = _digest(self.request_id, domain="bedrock-provider-request")
        model_id_digest = _digest(
            f"{self.inference_profile_id}:{self.model}", domain="bedrock-model"
        )
        evidence_id = _digest(
            ":".join(
                (
                    effect,
                    self.message_id,
                    request_id_digest,
                    model_id_digest,
                    str(self.input_tokens),
                    str(self.output_tokens),
                )
            ),
            domain="bedrock-provider-evidence",
        )
        return ProviderUsageEvidence(
            evidenceId=evidence_id,
            effectId=effect,
            providerRequestIdDigest=request_id_digest,
            modelIdDigest=model_id_digest,
            inputTokens=self.input_tokens,
            outputTokens=self.output_tokens,
            cacheWriteInputTokens=self.cache_write_input_tokens,
            cacheReadInputTokens=self.cache_read_input_tokens,
            providerCostRetained=True,
            observedAt=self.observed_at,
        )


@dataclass(frozen=True, slots=True)
class Answered:
    """The tool was called: its input as the model wrote it, as JSON text."""

    tool_input: str
    usage: Usage
    stop_reason: str


@dataclass(frozen=True, slots=True)
class PaidUnusable:
    """A reply came back and was paid for, and cannot be used."""

    category: str
    usage: Usage


@dataclass(frozen=True, slots=True)
class NotSent:
    """Nothing usable was paid for; `retryable` says whether the same call may be made again."""

    category: str
    retryable: bool
    detail: str | None = None


Result = Answered | PaidUnusable | NotSent


# ── The adapter in use ────────────────────────────────────────────────────────


class NotInstalled(LookupError):
    """A test made a model call without installing an adapter."""

    def __init__(self) -> None:
        super().__init__(
            "no model-call adapter is installed for this test; "
            "call stoa.services.model_call.install(<adapter>)"
        )


_UNSET: Any = object()
_installed: Any = None


def install(adapter: Adapter | None) -> None:
    """Put a test's adapter where `call` finds it; `None` for Bedrock again."""
    global _installed
    _installed = adapter


def reset_for_test() -> None:
    """No adapter: `call` raises `NotInstalled` until a test installs one."""
    global _installed
    _installed = _UNSET


def _adapter() -> Adapter:
    installed = _installed
    if installed is _UNSET:
        raise NotInstalled()
    if installed is not None:
        return installed
    from stoa.services.model_call.bedrock import BedrockAdapter

    return BedrockAdapter()


# ── The call ──────────────────────────────────────────────────────────────────


def call(
    *,
    system: str,
    system_tail: str = "",
    messages: Sequence[Mapping[str, Any]],
    tool: Tool,
    max_tokens: int,
    temperature: float,
    deadline: float,
    admission: AdmissionHook | None = None,
    on_partial: Callable[[str], None] | None = None,
    correlation_id: str | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Result:
    """Ask the model once for `tool`'s input, done by `deadline` (on `clock`).

    `on_partial` is told the tool input received so far each time more of it
    arrives. Only what the admission hook raises comes out as an exception.
    """
    if clock() >= deadline:
        return NotSent(DEADLINE_EXCEEDED, retryable=True)
    model_id = config.settings().bedrock_model_id
    body = _invoke_body(
        system=system,
        system_tail=system_tail,
        messages=messages,
        tool=tool,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    connection = _adapter().connect(deadline - clock())
    if admission is not None:
        try:
            input_tokens = connection.count(model_id, _count_body(body))
        except Exception as error:
            _record_provider_error("count", error, correlation_id)
            return NotSent(TOKEN_COUNT_UNAVAILABLE, retryable=True)
        decision = admission(input_tokens, max_tokens)
        if isinstance(decision, Refuse):
            return NotSent(decision.category, retryable=True, detail=decision.detail)
        # Counting and admission can take the time up; a generation started now
        # would only be cut off.
        if clock() >= deadline:
            return NotSent(DEADLINE_EXCEEDED, retryable=True)
    try:
        stream = connection.stream(model_id, body)
    except MalformedStream:
        return NotSent(MALFORMED_RESPONSE, retryable=True)
    except Exception as error:
        _record_provider_error("invoke", error, correlation_id)
        return NotSent(PROVIDER_ERROR, retryable=True)
    # Opening the stream can itself take the time up; do not wait for the
    # first event to find that out.
    if clock() >= deadline:
        return NotSent(DEADLINE_EXCEEDED, retryable=True)
    return _read(
        stream.events,
        request_id=stream.request_id,
        tool_name=tool.name,
        inference_profile_id=model_id,
        cost_class=CostClass.of(admission),
        deadline=deadline,
        clock=clock,
        on_partial=on_partial,
        correlation_id=correlation_id,
    )


def _invoke_body(
    *,
    system: str,
    system_tail: str = "",
    messages: Sequence[Mapping[str, Any]],
    tool: Tool,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    """The body that is sent: the tool forced, its input streamed as it is written.

    The tool is sent ahead of the system prompt, so the one cache point, at the
    end of the shared part of the system prompt, covers both.
    """
    return {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": [
            {"type": "text", "text": system, "cache_control": dict(CACHE_POINT)},
            *([{"type": "text", "text": system_tail}] if system_tail else []),
        ],
        "messages": [dict(message) for message in messages],
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "strict": tool.strict,
                "eager_input_streaming": True,
                "input_schema": dict(tool.input_schema),
            }
        ],
        "tool_choice": {"type": "tool", "name": tool.name},
    }


def _count_body(body: Mapping[str, Any]) -> dict[str, Any]:
    """The body that is counted: the one sent, without the stream-only tool fields.

    The one place the two bodies differ (#430).
    """
    tools = body.get("tools")
    return {
        **body,
        "tools": [
            {key: value for key, value in tool.items() if key not in _STREAM_ONLY_TOOL_FIELDS}
            for tool in (tools if isinstance(tools, list) else [])
        ],
    }


def _read(
    events: Any,
    *,
    request_id: str,
    tool_name: str,
    inference_profile_id: str,
    cost_class: CostClass,
    deadline: float,
    clock: Callable[[], float],
    on_partial: Callable[[str], None] | None,
    correlation_id: str | None,
) -> Result:
    """Read the stream: the input of the call of `tool_name`, and what the reply cost.

    The input arrives as `input_json_delta` pieces; any other content block is
    not read. The streaming protocol splits across events what accounting
    needs together: the message id and model at the start, the usage in two
    parts, the stop reason at the end.
    """
    tool_input: str | None = None
    tool_index: object = None
    usage: dict[str, Any] = {}
    stop_reason: object = None
    message_id: object = None
    model: object = None
    try:
        for payload in events:
            if clock() >= deadline:
                return NotSent(DEADLINE_EXCEEDED, retryable=True)
            kind = payload.get("type")
            if kind == "content_block_start":
                block = payload.get("content_block") or {}
                if (
                    tool_input is None
                    and block.get("type") == "tool_use"
                    and block.get("name") == tool_name
                ):
                    tool_index = payload.get("index")
                    tool_input = ""
            elif kind == "content_block_delta":
                delta = payload.get("delta") or {}
                if (
                    tool_input is None
                    or payload.get("index") != tool_index
                    or delta.get("type") != "input_json_delta"
                ):
                    continue
                tool_input += str(delta.get("partial_json", ""))
                if on_partial is not None:
                    # A piece that cannot be delivered is not worth losing the
                    # answer over; the whole input still arrives at the end.
                    try:
                        on_partial(tool_input)
                    except Exception:
                        logger.warning("partial tool input was not delivered", exc_info=True)
            elif kind == "message_delta":
                usage.update(payload.get("usage") or {})
                stop_reason = (payload.get("delta") or {}).get("stop_reason", stop_reason)
            elif kind == "message_start":
                message = payload.get("message") or {}
                usage.update(message.get("usage") or {})
                message_id = message.get("id", message_id)
                model = message.get("model", model)
    except MalformedStream:
        return NotSent(MALFORMED_RESPONSE, retryable=True)
    except Exception as error:
        _record_provider_error("stream", error, correlation_id)
        return NotSent(PROVIDER_ERROR, retryable=True)

    if message_id is None and tool_input is None:
        # Nothing came back at all: no reply, and no usage, to read.
        return NotSent(MALFORMED_RESPONSE, retryable=True)
    emit_private_event(
        "ai_response_received",
        output_size=len(tool_input or ""),
        correlation_id=correlation_id,
    )
    paid = _usage(
        usage,
        message_id=message_id,
        model=model,
        request_id=request_id,
        inference_profile_id=inference_profile_id,
        cost_class=cost_class,
    )
    if paid is None:
        return NotSent(MALFORMED_PROVIDER_USAGE, retryable=True)
    if stop_reason == "max_tokens":
        # A cut can land where the JSON happens to close; the input is still
        # unfinished.
        return PaidUnusable(INCOMPLETE_OUTPUT, paid)
    if tool_input is None:
        # Text written instead of the tool call is never read as the answer.
        emit_private_event("model_output_parse_failed", output_size=0, level=logging.WARNING)
        return PaidUnusable(MALFORMED_RESPONSE, paid)
    if not isinstance(stop_reason, str) or not stop_reason.strip():
        return NotSent(MALFORMED_PROVIDER_USAGE, retryable=True)
    return Answered(tool_input=tool_input, usage=paid, stop_reason=stop_reason.strip())


def _usage(
    usage: Mapping[str, Any],
    *,
    message_id: object,
    model: object,
    request_id: str,
    inference_profile_id: str,
    cost_class: CostClass,
) -> Usage | None:
    """The exact usage of the reply, or None when the provider's report does not hold together.

    The provider's `input_tokens` are only those neither written to nor read
    from the cache; the reply read all three kinds, so `Usage.input_tokens` is
    their sum. A cache count the provider leaves out, or sends as null, is none.
    """
    uncached_input = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    cache_write = usage.get("cache_creation_input_tokens") or 0
    cache_read = usage.get("cache_read_input_tokens") or 0
    if not all(_exact_count(count) for count in (uncached_input, cache_write, cache_read)):
        return None
    input_tokens = uncached_input + cache_write + cache_read
    if (
        not isinstance(message_id, str)
        or not message_id.strip()
        or not isinstance(model, str)
        or not model.strip()
        or not request_id.strip()
        or not inference_profile_id.strip()
        or not _exact_count(input_tokens)
        or not _exact_count(output_tokens)
    ):
        return None
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        request_id=request_id.strip(),
        message_id=message_id.strip(),
        model=model.strip(),
        inference_profile_id=inference_profile_id.strip(),
        observed_at=datetime.now(timezone.utc),
        cost_class=cost_class,
        cache_write_input_tokens=cache_write,
        cache_read_input_tokens=cache_read,
    )


def _exact_count(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_EXACT_COUNT


def _digest(value: str, *, domain: str) -> str:
    return hashlib.sha256(f"stoa:{domain}:v1:{value}".encode()).hexdigest()


def _record_provider_error(stage: str, error: Exception, correlation_id: str | None) -> None:
    """What the provider said about a failed call, as private telemetry (#435).

    Its code, HTTP status and request id, and its own error text cut to about
    300 characters: enough to read a refusal such as #430's from the log. Only
    the provider's text: any other failure is logged by its class alone, since
    its message may quote the request.
    """
    if isinstance(error, ProviderError):
        code, status, request_id, message = (
            error.code,
            error.http_status,
            error.request_id,
            error.message,
        )
    else:
        code, status, request_id, message = type(error).__name__, None, None, ""
    emit_private_event(
        "model_call_provider_failed",
        exception=error,
        correlation_id=correlation_id,
        stage=stage,
        provider_error_code=code,
        http_status=status,
        provider_request_id=request_id,
        provider_message=message[:_PROVIDER_MESSAGE_CHARS],
        level=logging.WARNING,
    )


__all__ = [
    "Admit",
    "AdmissionHook",
    "Answered",
    "CostClass",
    "NotInstalled",
    "NotSent",
    "PaidUnusable",
    "Refuse",
    "Result",
    "Tool",
    "Usage",
    "call",
    "install",
    "reset_for_test",
]
