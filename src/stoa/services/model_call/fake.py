"""The in-memory adapter of 模型调用 (#436), for tests.

`FakeAdapter` stands where Bedrock stands and holds every body it is handed to
the rules measured against production Bedrock (#430, 2026-11-15):

- a body has `messages` (a non-empty list), and the body that is sent also an
  `anthropic_version` and a whole `max_tokens`;
- `tools` is a list of tools, each with a `name` and an `input_schema`, and
  `tool_choice`, when given, names one of them;
- CountTokens takes only a tool's `name`, `description`, `input_schema` and
  `strict`: any other field, such as `eager_input_streaming`, is a
  `ValidationException` reading `tools.<n>.custom.<field>: Extra inputs are
  not permitted`. InvokeModel takes `eager_input_streaming` as well.
- `system` is a string or a list of text blocks; a block's `cache_control` is
  `{"type": "ephemeral"}`, and a body has at most four of them (#442).
  CountTokens takes `cache_control` as InvokeModel does, and counts the body
  the same with it or without it (measured 2026-11-20, #442).

A body the rules refuse raises `ProviderError` as Bedrock would. Otherwise each
sent body takes the next of `outcomes`:

- a dict is the input of the forced tool call, a string the raw text of it;
- `Prose(text)` is a reply that calls no tool;
- `Reply(...)` sets the stop reason or the usage as well;
- an exception is raised when the body is sent;
- `Unsent(exception)` is raised while the tokens are counted instead.

With none left, `respond(body)` answers when given, else `answer`. A `gate`,
when set, holds every reply until it opens; `pieces` is how many
`input_json_delta` pieces the tool input is cut into.

`cached_tokens`, when set, makes the fake a prompt cache (#442): the tools and
the system blocks up to the last cache point are the prefix, and a reply whose
prefix was sent before reads that many tokens from the cache, one whose
prefix is new writes them. Either way, the reply reads `input_tokens` more.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
import json
import threading
from typing import Any

from stoa.services.model_call.adapter import ProviderError, Stream

COUNTED_TOOL_FIELDS = frozenset({"name", "description", "input_schema", "strict"})
SENT_TOOL_FIELDS = COUNTED_TOOL_FIELDS | {"eager_input_streaming"}

INPUT_TOKENS = 90
OUTPUT_TOKENS = 30

# Bedrock takes at most this many cache points in one body.
MAX_CACHE_POINTS = 4


@dataclass(frozen=True)
class Prose:
    """A reply of plain text, without the tool call it was asked for."""

    text: str


@dataclass(frozen=True)
class Reply:
    """A reply with its stop reason and usage set: `input` as a dict or string outcome is."""

    input: Any = None
    text: str | None = None
    stop_reason: str = "tool_use"
    usage: Mapping[str, Any] = field(
        default_factory=lambda: {"input_tokens": INPUT_TOKENS, "output_tokens": OUTPUT_TOKENS}
    )


class Unsent:
    """An outcome that ends the call while its tokens are counted."""

    def __init__(self, exception: BaseException) -> None:
        self.exception = exception


def _refused(message: str, request_id: str) -> ProviderError:
    return ProviderError(
        "ValidationException", http_status=400, request_id=request_id, message=message
    )


def check_body(body: Mapping[str, Any], *, counted: bool, request_id: str = "fake") -> None:
    """Raise as Bedrock does for a body it refuses: the count's rules when `counted`."""
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise _refused("messages: Field required", request_id)
    if not counted:
        if not isinstance(body.get("anthropic_version"), str):
            raise _refused("anthropic_version: Field required", request_id)
        if type(body.get("max_tokens")) is not int or body["max_tokens"] < 1:
            raise _refused("max_tokens: Field required", request_id)
    system = body.get("system", "")
    if not isinstance(system, (str, list)):
        raise _refused("system: Input should be a valid list", request_id)
    cache_points = 0
    for index, block in enumerate(system if isinstance(system, list) else []):
        if (
            not isinstance(block, Mapping)
            or block.get("type") != "text"
            or not isinstance(block.get("text"), str)
            or not block["text"].strip()
        ):
            raise _refused(f"system.{index}: text content blocks must be non-empty", request_id)
        if "cache_control" in block:
            if block["cache_control"] != {"type": "ephemeral"}:
                raise _refused(f"system.{index}.cache_control: Input tag invalid", request_id)
            cache_points += 1
    if cache_points > MAX_CACHE_POINTS:
        raise _refused(
            f"A maximum of {MAX_CACHE_POINTS} blocks with cache_control may be provided",
            request_id,
        )
    tools = body.get("tools", [])
    if not isinstance(tools, list):
        raise _refused("tools: Input should be a valid list", request_id)
    allowed = COUNTED_TOOL_FIELDS if counted else SENT_TOOL_FIELDS
    names = []
    for index, tool in enumerate(tools):
        if not isinstance(tool, Mapping):
            raise _refused(f"tools.{index}: Input should be a valid dictionary", request_id)
        extra = sorted(set(tool).difference(allowed))
        if extra:
            raise _refused(
                f"tools.{index}.custom.{extra[0]}: Extra inputs are not permitted", request_id
            )
        if not isinstance(tool.get("name"), str) or not isinstance(tool.get("input_schema"), Mapping):
            raise _refused(f"tools.{index}.custom: Field required", request_id)
        names.append(tool["name"])
    choice = body.get("tool_choice")
    if choice is not None and (
        not isinstance(choice, Mapping)
        or choice.get("type") != "tool"
        or choice.get("name") not in names
    ):
        raise _refused("tool_choice: Tool not found", request_id)


class FakeAdapter:
    def __init__(
        self,
        *outcomes: Any,
        answer: Any = None,
        respond: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.outcomes: list[Any] = list(outcomes)
        self.answer = answer
        self.respond = respond
        # Every body sent, and every body counted, in order.
        self.requests: list[dict[str, Any]] = []
        self.counted_bodies: list[dict[str, Any]] = []
        # What the connections were opened with: the time each call had left.
        self.connections: list[float] = []
        self.gate: threading.Event | None = None
        self.pieces = 2
        self.input_tokens = INPUT_TOKENS
        self.cached_tokens = 0
        self._cached_prefixes: set[str] = set()

    # ── What a test reads back ───────────────────────────────────────────────

    @property
    def calls(self) -> list[dict[str, Any]]:
        """Every body the model was sent, in order."""
        return self.requests

    @property
    def counted(self) -> int:
        """How many times tokens were counted."""
        return len(self.counted_bodies)

    def system(self, index: int = -1) -> str:
        """The whole system prompt of a sent body, its blocks put back together."""
        return system_text(self.requests[index])

    def cached_system(self, index: int = -1) -> str:
        """The part of a sent body's system prompt up to its last cache point."""
        return "".join(block["text"] for block in _cached_blocks(self.requests[index]))

    def student_turn(self, index: int = -1) -> str:
        """The text of the latest turn of a sent body, images left out."""
        content = self.requests[index]["messages"][-1]["content"]
        if isinstance(content, str):
            return content
        return "".join(block.get("text", "") for block in content if block.get("type") == "text")

    def images(self, index: int = -1) -> list[dict[str, Any]]:
        content = self.requests[index]["messages"][-1]["content"]
        if isinstance(content, str):
            return []
        return [block for block in content if block.get("type") == "image"]

    # ── The adapter ──────────────────────────────────────────────────────────

    def connect(self, remaining_seconds: float) -> FakeAdapter:
        self.connections.append(remaining_seconds)
        return self

    def count_tokens(self, model_id: str, body: Mapping[str, Any]) -> int:
        recorded = json.loads(json.dumps(body))
        self.counted_bodies.append(recorded)
        if self.outcomes and isinstance(self.outcomes[0], Unsent):
            raise self.outcomes.pop(0).exception
        check_body(recorded, counted=True, request_id=f"count-{self.counted}")
        return self.input_tokens

    def stream(self, model_id: str, body: Mapping[str, Any]) -> Stream:
        request = json.loads(json.dumps(body))
        self.requests.append(request)
        number = len(self.requests)
        check_body(request, counted=False, request_id=f"req-{number}")
        if self.gate is not None:
            self.gate.wait(5)
        outcome = self._next(request)
        if isinstance(outcome, BaseException):
            raise outcome
        reply = outcome if isinstance(outcome, Reply) else (
            Reply(text=outcome.text) if isinstance(outcome, Prose) else Reply(input=outcome)
        )
        # A `Reply` says its own usage; any other outcome is given the cache's.
        if self.cached_tokens and not isinstance(outcome, Reply):
            reply = Reply(
                input=reply.input,
                text=reply.text,
                stop_reason=reply.stop_reason,
                usage={**reply.usage, **self._cache_usage(request)},
            )
        return Stream(
            request_id=f"req-{number}",
            events=self._events(reply, request, model_id=model_id, number=number),
        )

    def _cache_usage(self, request: dict[str, Any]) -> dict[str, int]:
        blocks = _cached_blocks(request)
        if not blocks:
            return {}
        prefix = json.dumps([request.get("tools"), blocks], sort_keys=True)
        if prefix in self._cached_prefixes:
            return {"cache_read_input_tokens": self.cached_tokens}
        self._cached_prefixes.add(prefix)
        return {"cache_creation_input_tokens": self.cached_tokens}

    def _next(self, request: dict[str, Any]) -> Any:
        if self.outcomes:
            return self.outcomes.pop(0)
        if self.respond is not None:
            return self.respond(request)
        return self.answer

    def _events(
        self, reply: Reply, request: dict[str, Any], *, model_id: str, number: int
    ) -> Iterator[Mapping[str, Any]]:
        usage = dict(reply.usage)
        # As Bedrock streams it: every input count when the message starts.
        start_usage = {key: value for key, value in usage.items() if key in _START_USAGE}
        end_usage = {key: value for key, value in usage.items() if key not in _START_USAGE}
        yield {
            "type": "message_start",
            "message": {"id": f"msg_{number}", "model": model_id, "usage": start_usage},
        }
        if reply.text is not None:
            yield {"type": "content_block_start", "index": 0,
                   "content_block": {"type": "text", "text": ""}}
            yield {"type": "content_block_delta", "index": 0,
                   "delta": {"type": "text_delta", "text": reply.text}}
            yield {"type": "content_block_stop", "index": 0}
        if reply.input is not None:
            text = reply.input if isinstance(reply.input, str) else json.dumps(
                reply.input, ensure_ascii=False
            )
            choice = request.get("tool_choice") or {}
            yield {"type": "content_block_start", "index": 0, "content_block": {
                "type": "tool_use", "id": "toolu_fake", "name": choice.get("name"), "input": {},
            }}
            size = max(1, -(-len(text) // max(1, self.pieces)))
            for start in range(0, len(text), size):
                yield {"type": "content_block_delta", "index": 0,
                       "delta": {"type": "input_json_delta",
                                 "partial_json": text[start : start + size]}}
            yield {"type": "content_block_stop", "index": 0}
        yield {"type": "message_delta", "delta": {"stop_reason": reply.stop_reason},
               "usage": end_usage}


_START_USAGE = frozenset(
    {"input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"}
)


def system_text(body: Mapping[str, Any]) -> str:
    """The whole system prompt of a body, as one string."""
    system = body.get("system", "")
    if isinstance(system, str):
        return system
    return "".join(block.get("text", "") for block in system)


def _cached_blocks(body: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The system blocks up to and including the last one with a cache point."""
    system = body.get("system")
    if not isinstance(system, list):
        return []
    points = [index for index, block in enumerate(system) if "cache_control" in block]
    return list(system[: points[-1] + 1]) if points else []


__all__ = [
    "COUNTED_TOOL_FIELDS",
    "FakeAdapter",
    "Prose",
    "Reply",
    "SENT_TOOL_FIELDS",
    "Unsent",
    "check_body",
    "system_text",
]
