"""Controlled AI teaching service: what is checked on the way to the model and back.

- Prompt injection defence (input sanitisation)
- Reading a model call's result as an answer (`provider_result`): the tool
  input parsed and checked (structure check + forbidden-term scan), with the
  exact usage evidence of every reply that was paid for

The model is called through `model_call` (#436). The Ask prompt itself, and
what an Ask answer is made of, is `ask_answer`'s (#176); the answer checks here
move there with #437.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import logging
import re
from typing import Generic, TypeVar

from stoa.models.allowance import ProviderUsageEvidence
from stoa.security.private_telemetry import emit_private_event
from stoa.services import model_call

logger = logging.getLogger(__name__)

# Naming the language beats passing a bare ISO code: the model followed "de"
# unevenly and fell back to the language the prompt itself is written in.
_LANGUAGE_NAMES = {
    "de": "German",
    "en": "English",
    "fr": "French",
    "it": "Italian",
}
DEFAULT_LANGUAGE_NAME = "German"


def language_name(language: str) -> str:
    """The plain name of the answer language, for the prompt to refer to."""
    base = str(language or "").strip().replace("_", "-").split("-", 1)[0].lower()
    return _LANGUAGE_NAMES.get(base, DEFAULT_LANGUAGE_NAME)


# ── Prompt injection defence ───────────────────────────────────────────────────

# Patterns that attempt to override the system prompt or leak internals
_INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions?|rules?|prompts?)",
    r"(system|assistant)\s*:\s*",
    r"<\|?(?:im_start|im_end|endoftext)\|?>",
    r"you are now",
    r"new\s+instructions?",
    r"disregard\s+(your|all)",
    r"forget\s+(your|all|previous)",
    r"act\s+as\s+(?!a\s+student|a\s+teacher)",  # allow "act as a student/teacher" only
    r"jailbreak",
    r"DAN\b",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

# Terms that should never appear in AI output (leaked internals)
_FORBIDDEN_OUTPUT_TERMS = [
    "anthropic", "claude", "bedrock", "openai", "gpt", "llm",
    "system prompt", "ignore previous", "harness", "STOA internal",
]

# Max characters accepted from a single student message
_MAX_INPUT_CHARS = 2000

class AIInvocationFailure(Exception):
    """Closed model-boundary failure without provider diagnostics.

    `usage` is set when the provider did answer and was paid for, but the
    answer cannot be used, so the caller can still account for the cost and
    release the student's reservation. `retryable` says whether the same
    answer may be asked for again, as the model call decided it: never once a
    reply was paid for. `detail` is for diagnostics only.
    """

    def __init__(
        self,
        category: str,
        *,
        usage: ProviderUsageEvidence | None = None,
        retryable: bool | None = None,
        detail: str | None = None,
    ):
        self.category = category
        self.usage = usage
        self.retryable = (usage is None) if retryable is None else retryable
        self.detail = detail
        super().__init__(category)


class AIInvocationClass(StrEnum):
    """Closed cost attribution class for each direct InvokeModel caller."""

    USER_ALLOWANCE = "user_allowance"
    PROVIDER_COST_ONLY = "provider_cost_only"


@dataclass(frozen=True, slots=True)
class PromptImage:
    """One image the student attached, handed to the model as it is (#135)."""

    media_type: str
    data: bytes


AIContent = TypeVar("AIContent")


@dataclass(frozen=True, slots=True)
class AIProviderResult(Generic[AIContent]):
    """Validated content separated from immutable, content-free usage evidence."""

    content: AIContent
    usage: ProviderUsageEvidence
    model_id: str
    inference_profile_id: str
    provider_message_id_digest: str
    stop_reason: str
    invocation_class: AIInvocationClass


def inventory_ai_invocation_classes() -> dict[str, AIInvocationClass]:
    """Return the exhaustive direct InvokeModel caller inventory."""
    return {
        # The Ask answer, through 模型调用 under the allowance's admission (#436).
        "src/stoa/services/model_call/bedrock.py:invoke_model_with_response_stream": (
            AIInvocationClass.USER_ALLOWANCE
        ),
        "src/stoa/services/report_service.py:generate_weekly_report_content": (
            AIInvocationClass.PROVIDER_COST_ONLY
        ),
    }


# ── Input sanitisation ─────────────────────────────────────────────────────────

def sanitise_input(text: str, *, correlation_id: str | None = None) -> str:
    """Strip injection attempts and enforce length cap."""
    cleaned = text.strip()
    if len(cleaned) > _MAX_INPUT_CHARS:
        cleaned = cleaned[:_MAX_INPUT_CHARS]
        emit_private_event(
            "prompt_input_truncated",
            input_size=len(text),
            correlation_id=correlation_id,
            level=logging.WARNING,
        )

    if _INJECTION_RE.search(cleaned):
        emit_private_event(
            "prompt_injection_neutralized",
            input_size=len(cleaned),
            correlation_id=correlation_id,
            level=logging.WARNING,
        )
        # Replace the offending portion so the model only sees the innocent remainder
        cleaned = _INJECTION_RE.sub("[removed]", cleaned).strip()

    return cleaned


def scrub_injections(text: str) -> str:
    """Take out what reads as an attempt to override the prompt, without logging it."""
    return _INJECTION_RE.sub("[removed]", text)



# ── Output validation ──────────────────────────────────────────────────────────

def _validate_output(parsed: dict, raw_text: str) -> dict:
    """Apply post-generation policy checks and repair obvious violations."""
    issues = []

    # 1. Empty / trivially short response
    all_text = " ".join(parsed.get("steps", [])) + " " + parsed.get("answer", "")
    if len(all_text.strip()) < 10:
        issues.append("empty_response")

    # 2. Leaked internal terms
    lower_raw = raw_text.lower()
    leaked = [t for t in _FORBIDDEN_OUTPUT_TERMS if t in lower_raw]
    if leaked:
        issues.append(f"leaked_terms:{','.join(leaked)}")
        # Redact from output
        for term in leaked:
            raw_text = re.sub(re.escape(term), "[AI]", raw_text, flags=re.IGNORECASE)
        parsed = _parse_ai_response(raw_text)

    # 3. Neither steps nor an answer: nothing a student could be shown.
    if not parsed.get("steps") and not parsed.get("answer"):
        raise AIInvocationFailure("malformed_response")

    if issues:
        emit_private_event(
            "model_output_policy_issue",
            output_size=len(raw_text),
            issue_count=len(issues),
            level=logging.WARNING,
        )

    return parsed


# ── Reading the tool call ──────────────────────────────────────────────────────

_STEP_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
_WHITESPACE = re.compile(r"\s*")


def completed_steps(partial_json: str) -> list[str]:
    """Return the steps already closed in a partly received answer.

    The answer arrives as the input of a tool call, streamed piece by piece
    (#412), so a student cannot be shown raw tokens. Each step is whole the
    moment its closing quote and the `,` or `]` after it arrive, which is the
    smallest piece worth showing.

    The array is read from its start, one string after the other. A string
    that is not followed by `,` or `]` ends the reading: the input is broken
    there. Searching on past it could take an inner quote for an opening one
    and cut a step from the middle of a sentence (#389).
    """
    if '"steps"' not in partial_json:
        return []
    tail = partial_json.split('"steps"', 1)[1]
    opening = tail.find("[")
    if opening == -1 or tail[:opening].strip() != ":":
        return []
    rest = tail[opening + 1 :]
    position = _WHITESPACE.match(rest).end()
    steps: list[str] = []
    while position < len(rest) and rest[position] == '"':
        match = _STEP_STRING.match(rest, position)
        if match is None:
            break
        after = _WHITESPACE.match(rest, match.end()).end()
        if after >= len(rest) or rest[after] not in ",]":
            break
        try:
            steps.append(json.loads(match.group(0)))
        except json.JSONDecodeError:
            break
        if rest[after] == "]":
            break
        position = _WHITESPACE.match(rest, after + 1).end()
    return steps


def _parse_ai_response(text: str) -> dict:
    """Read the tool input as the answer it must be, or refuse it.

    The API writes the input, constrained to the tool's schema (#412), so
    nothing is repaired here: an input that does not read as one object (one
    that never closed), or whose `steps` or `answer` is missing or of the
    wrong shape, is `malformed_response`, and no part of it is shown.
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if not _is_answer(parsed):
        emit_private_event(
            "model_output_parse_failed", output_size=len(text), level=logging.WARNING
        )
        raise AIInvocationFailure("malformed_response")
    return parsed


def _is_answer(parsed: object) -> bool:
    """An object with the two sections every answer is shown by.

    The other sections are `ask_answer`'s to check: an entry of the wrong
    shape there is left out rather than failing an answer already paid for.
    """
    if not isinstance(parsed, dict):
        return False
    steps = parsed.get("steps")
    if not isinstance(steps, list) or any(not isinstance(step, str) for step in steps):
        return False
    return isinstance(parsed.get("answer"), str)


# ── Reading a model call's result ──────────────────────────────────────────────


def provider_result(
    result: model_call.Result,
    *,
    effect_id: str,
    invocation_class: AIInvocationClass = AIInvocationClass.USER_ALLOWANCE,
) -> AIProviderResult[dict]:
    """The answer a model call gave, parsed and checked, with its usage.

    Raises `AIInvocationFailure` when there is none: one that carries the
    usage when the reply was paid for (never retryable), one that says
    whether the call may be made again when it was not.
    """
    if isinstance(result, model_call.NotSent):
        raise AIInvocationFailure(
            result.category, retryable=result.retryable, detail=result.detail
        )
    try:
        usage = result.usage.evidence(effect_id=effect_id)
    except ValueError:
        raise AIInvocationFailure("malformed_provider_usage", retryable=True) from None
    if isinstance(result, model_call.PaidUnusable):
        raise AIInvocationFailure(result.category, usage=usage, retryable=False)
    raw_text = result.tool_input
    try:
        validated = _validate_output(_parse_ai_response(raw_text), raw_text)
    except AIInvocationFailure as failure:
        # The provider was paid for this reply, so the failure carries the
        # usage evidence; the caller needs it to release the reservation.
        failure.usage = usage
        failure.retryable = False
        raise
    return AIProviderResult(
        content=validated,
        usage=usage,
        model_id=result.usage.model,
        inference_profile_id=result.usage.inference_profile_id,
        provider_message_id_digest=result.usage.message_id_digest,
        stop_reason=result.stop_reason,
        invocation_class=invocation_class,
    )
