"""Amazon Bedrock — controlled AI teaching service.

Implements a lightweight AI harness:
- Prompt injection defence (input sanitisation)
- Sending a built prompt to the model, buffered or streamed, under a deadline
- Output validation (structure check + forbidden-term scan)
- Exact usage evidence for every reply that was paid for

The Ask prompt itself, and what an Ask answer is made of, is `ask_answer`'s
(#176).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import logging
import re
import time
from typing import Any, Callable, Generic, Mapping, TypeVar
import boto3
from botocore.config import Config

from stoa.config import settings
from stoa.models.allowance import MAX_EXACT_COUNT, ProviderUsageEvidence
from stoa.security.private_telemetry import emit_private_event

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
    release the student's reservation.
    """

    def __init__(self, category: str, *, usage: ProviderUsageEvidence | None = None):
        self.category = category
        self.usage = usage
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
        "src/stoa/routers/conversations.py:_generate_title": (
            AIInvocationClass.PROVIDER_COST_ONLY
        ),
        # Streaming delivers the same answer under the same admission, so it
        # is charged to the student's allowance exactly as the buffered call is.
        "src/stoa/routers/conversations.py:invoke_model_with_response_stream": (
            AIInvocationClass.USER_ALLOWANCE
        ),
        "src/stoa/services/ai_service.py:invoke_answer": (
            AIInvocationClass.USER_ALLOWANCE
        ),
        "src/stoa/services/ai_service.py:get_hint_answer": (
            AIInvocationClass.USER_ALLOWANCE
        ),
        "src/stoa/services/report_service.py:generate_weekly_report_content": (
            AIInvocationClass.PROVIDER_COST_ONLY
        ),
    }


def _digest(value: str, *, domain: str) -> str:
    return hashlib.sha256(f"stoa:{domain}:v1:{value}".encode()).hexdigest()


def _exact_provider_count(value: object) -> int:
    if type(value) is not int or value < 0 or value > MAX_EXACT_COUNT:
        raise AIInvocationFailure("malformed_provider_usage")
    return value


def parse_provider_usage(
    payload: Mapping[str, object],
    *,
    provider_request_id: str,
    inference_profile_id: str,
    effect_id: str,
    observed_at: datetime | None = None,
) -> ProviderUsageEvidence:
    """Parse exact Anthropic usage into the canonical content-free evidence model."""
    usage = payload.get("usage")
    message_id = payload.get("id")
    provider_model_id = payload.get("model")
    if (
        not isinstance(usage, Mapping)
        or not isinstance(message_id, str)
        or not message_id.strip()
        or not isinstance(provider_model_id, str)
        or not provider_model_id.strip()
        or not provider_request_id.strip()
        or not inference_profile_id.strip()
        or not effect_id.strip()
    ):
        raise AIInvocationFailure("malformed_provider_usage")
    input_tokens = _exact_provider_count(usage.get("input_tokens"))
    output_tokens = _exact_provider_count(usage.get("output_tokens"))
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise AIInvocationFailure("malformed_provider_usage")
    provider_request_id_digest = _digest(
        provider_request_id.strip(),
        domain="bedrock-provider-request",
    )
    model_id_digest = _digest(
        f"{inference_profile_id.strip()}:{provider_model_id.strip()}",
        domain="bedrock-model",
    )
    evidence_id = _digest(
        ":".join(
            (
                effect_id.strip(),
                message_id.strip(),
                provider_request_id_digest,
                model_id_digest,
                str(input_tokens),
                str(output_tokens),
            )
        ),
        domain="bedrock-provider-evidence",
    )
    try:
        return ProviderUsageEvidence(
            evidenceId=evidence_id,
            effectId=effect_id.strip(),
            providerRequestIdDigest=provider_request_id_digest,
            modelIdDigest=model_id_digest,
            inputTokens=input_tokens,
            outputTokens=output_tokens,
            providerCostRetained=True,
            observedAt=observed,
        )
    except ValueError:
        raise AIInvocationFailure("malformed_provider_usage") from None


def _provider_request_id(response: Mapping[str, object]) -> str:
    metadata = response.get("ResponseMetadata")
    if isinstance(metadata, Mapping):
        raw_request_id = metadata.get("RequestId")
        if isinstance(raw_request_id, str):
            return raw_request_id.strip()
    return ""


def _provider_result(
    content: AIContent,
    payload: Mapping[str, object],
    *,
    response: Mapping[str, object],
    inference_profile_id: str,
    effect_id: str,
    observed_at: datetime | None,
    invocation_class: AIInvocationClass,
) -> AIProviderResult[AIContent]:
    request_id = _provider_request_id(response)
    message_id = payload.get("id")
    model_id = payload.get("model")
    stop_reason = payload.get("stop_reason")
    if (
        not isinstance(message_id, str)
        or not isinstance(model_id, str)
        or not model_id.strip()
        or not isinstance(stop_reason, str)
        or not stop_reason.strip()
    ):
        raise AIInvocationFailure("malformed_provider_usage")
    usage = parse_provider_usage(
        payload,
        provider_request_id=request_id,
        inference_profile_id=inference_profile_id,
        effect_id=effect_id,
        observed_at=observed_at,
    )
    return AIProviderResult(
        content=content,
        usage=usage,
        model_id=model_id.strip(),
        inference_profile_id=inference_profile_id,
        provider_message_id_digest=_digest(
            message_id.strip(),
            domain="bedrock-provider-message",
        ),
        stop_reason=stop_reason.strip(),
        invocation_class=invocation_class,
    )


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

    # 3. No guided steps for a question response
    if not parsed.get("steps") and not parsed.get("answer"):
        # Prose that was never JSON can stand as the answer; a JSON object
        # cannot, or the student is shown the braces.
        if _looks_like_json_object(raw_text):
            raise AIInvocationFailure("malformed_response")
        issues.append("missing_structure")
        parsed["answer"] = raw_text  # fall back to raw text

    if issues:
        emit_private_event(
            "model_output_policy_issue",
            output_size=len(raw_text),
            issue_count=len(issues),
            level=logging.WARNING,
        )

    return parsed


# ── JSON parsing ───────────────────────────────────────────────────────────────

_STEP_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"\s*(?:,|\])')


def completed_steps(partial_json: str) -> list[str]:
    """Return the steps already closed in a partly received JSON answer.

    The model answers with one JSON object, so a student cannot be shown raw
    tokens. Each step is whole the moment its closing quote arrives, which is
    the smallest piece worth showing.
    """
    if '"steps"' not in partial_json:
        return []
    tail = partial_json.split('"steps"', 1)[1]
    opening = tail.find("[")
    if opening == -1:
        return []
    steps: list[str] = []
    for match in _STEP_PATTERN.finditer(tail[opening + 1 :]):
        try:
            steps.append(json.loads(f'"{match.group(1)}"'))
        except json.JSONDecodeError:
            break
        if match.group(0).rstrip().endswith("]"):
            break
    return steps


def _stream_ai_answer(
    *,
    client: Any,
    body: str,
    on_step: Callable[[int, str], None],
    correlation_id: str | None,
    deadline_monotonic: float | None,
    clock: Callable[[], float],
    effect_id: str | None,
    observed_at: datetime | None,
    invocation_class: AIInvocationClass,
) -> AIProviderResult[dict]:
    """Invoke the model as a stream, reporting each step as it completes."""
    response = client.invoke_model_with_response_stream(
        modelId=settings.bedrock_model_id, body=body
    )
    stream = response.get("body") if isinstance(response, dict) else None
    if stream is None:
        raise AIInvocationFailure("malformed_response")
    # Opening the stream can itself take the time up; do not wait for the first
    # event to find that out.
    if deadline_monotonic is not None and clock() >= deadline_monotonic:
        raise AIInvocationFailure("deadline_exceeded")

    raw_text = ""
    reported = 0
    usage: dict[str, Any] = {}
    stop_reason = None
    # The streaming protocol splits across events what one buffered response
    # carries together, and accounting needs all of it.
    message_id = None
    model_id = None
    for event in stream:
        if deadline_monotonic is not None and clock() >= deadline_monotonic:
            raise AIInvocationFailure("deadline_exceeded")
        chunk = event.get("chunk") if isinstance(event, dict) else None
        if not chunk:
            continue
        try:
            payload = json.loads(chunk["bytes"])
        except (KeyError, TypeError, json.JSONDecodeError):
            raise AIInvocationFailure("malformed_response") from None
        kind = payload.get("type")
        if kind == "content_block_delta":
            raw_text += payload.get("delta", {}).get("text", "")
            steps = completed_steps(raw_text)
            while reported < len(steps):
                # A step that cannot be delivered is not worth losing the
                # answer over; the full result still arrives at the end.
                try:
                    on_step(reported, steps[reported])
                except Exception:
                    logger.warning("streamed step was not delivered", exc_info=True)
                reported += 1
        elif kind == "message_delta":
            usage.update(payload.get("usage") or {})
            stop_reason = (payload.get("delta") or {}).get("stop_reason", stop_reason)
        elif kind == "message_start":
            message = payload.get("message") or {}
            usage.update(message.get("usage") or {})
            message_id = message.get("id", message_id)
            model_id = message.get("model", model_id)

    if not raw_text:
        raise AIInvocationFailure("malformed_response")
    emit_private_event(
        "ai_response_received",
        output_size=len(raw_text),
        correlation_id=correlation_id,
    )
    result = {
        "id": message_id,
        "model": model_id,
        "content": [{"text": raw_text}],
        "usage": usage,
        "stop_reason": stop_reason,
    }
    return _answer_result(
        raw_text,
        result,
        response=response,
        effect_id=effect_id or correlation_id or "unbound-user-allowance-effect",
        observed_at=observed_at,
        invocation_class=invocation_class,
    )


def _answer_result(
    raw_text: str,
    payload: Mapping[str, object],
    *,
    response: Mapping[str, object],
    effect_id: str,
    observed_at: datetime | None,
    invocation_class: AIInvocationClass,
) -> AIProviderResult[dict]:
    """Turn a structured answer into a result, or a failure that keeps its usage.

    A reply cut off at `max_tokens` is refused before it is parsed: a cut can
    land where the JSON happens to close, and the answer is still unfinished.
    """
    if payload.get("stop_reason") == "max_tokens":
        failure = AIInvocationFailure("incomplete_output")
    else:
        try:
            validated = _validate_output(_parse_ai_response(raw_text), raw_text)
        except AIInvocationFailure as exc:
            failure = exc
        else:
            return _provider_result(
                validated,
                payload,
                response=response,
                inference_profile_id=settings.bedrock_model_id,
                effect_id=effect_id,
                observed_at=observed_at,
                invocation_class=invocation_class,
            )
    # The provider was paid for this reply, so the failure carries the usage
    # evidence; the caller needs it to release the student's reservation.
    failure.usage = parse_provider_usage(
        payload,
        provider_request_id=_provider_request_id(response),
        inference_profile_id=settings.bedrock_model_id,
        effect_id=effect_id,
        observed_at=observed_at,
    )
    raise failure


def _looks_like_json_object(text: str) -> bool:
    return _strip_code_fence(text).startswith("{")


def _strip_code_fence(text: str) -> str:
    stripped = re.sub(r"^```(?:json)?\s*", "", text.strip())
    return re.sub(r"\s*```$", "", stripped)


def _parse_ai_response(text: str) -> dict:
    """Parse AI response, handling possible markdown code block wrappers."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    stripped = _strip_code_fence(text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    emit_private_event(
        "model_output_parse_failed", output_size=len(text), level=logging.WARNING
    )
    if stripped.startswith("{"):
        # An object that does not close was cut off or garbled. Shown as the
        # answer, the student reads half a JSON document.
        raise AIInvocationFailure("malformed_response")
    return {"steps": [], "answer": text, "hints": [], "similar_exercises": [], "suggest_teacher": False}



# ── Public API ─────────────────────────────────────────────────────────────────

def bedrock_runtime_config(remaining: float | None) -> Config:
    """Transport limits for one answer: one attempt, reads bounded by the time left.

    Every client that carries an answer uses this, the allowance wrapper
    included, so no path waits on a socket past its deadline or retries behind
    the caller's back.
    """
    read_timeout = max(1, min(90, int((remaining or 90) - 5)))
    return Config(
        connect_timeout=5,
        read_timeout=read_timeout,
        retries={"total_max_attempts": 1, "mode": "standard"},
    )


def invoke_answer(
    system_prompt: str,
    messages: list[dict],
    *,
    input_size: int,
    attachment_count: int = 0,
    correlation_id: str | None = None,
    deadline_monotonic: float | None = None,
    clock: Callable[[], float] | None = None,
    client: Any | None = None,
    effect_id: str | None = None,
    observed_at: datetime | None = None,
    invocation_class: AIInvocationClass = AIInvocationClass.USER_ALLOWANCE,
    on_step: Callable[[int, str], None] | None = None,
) -> AIProviderResult[dict]:
    """Ask the model for one structured answer to a prompt already built.

    The prompt is the caller's (`ask_answer` builds the Ask one, #176); this
    sends it, streamed when `on_step` is given, under the deadline, and turns
    the reply into a parsed answer with its usage, or a failure that keeps the
    usage of a reply that was paid for. `input_size` and `attachment_count`
    describe the student's turn for telemetry only.
    """
    clock = clock or time.monotonic
    remaining = None
    if deadline_monotonic is not None:
        remaining = deadline_monotonic - clock()
        if remaining <= 0:
            raise AIInvocationFailure("deadline_exceeded")
        # A wrapping client (the allowance wrapper) does work of its own before
        # the model is called; it is held to this deadline, not one of its own.
        bind_deadline = getattr(client, "bind_deadline", None)
        if callable(bind_deadline):
            bind_deadline(deadline_monotonic, clock)
    if client is None:
        client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            config=bedrock_runtime_config(remaining),
        )
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": settings.bedrock_max_tokens,
        "temperature": 0.4,
        "system": system_prompt,
        "messages": messages,
    })

    emit_private_event(
        "ai_request_started",
        input_size=input_size,
        attachment_count=attachment_count,
        correlation_id=correlation_id,
    )
    if deadline_monotonic is not None and clock() >= deadline_monotonic:
        raise AIInvocationFailure("deadline_exceeded")
    if on_step is not None:
        return _stream_ai_answer(
            client=client,
            body=body,
            on_step=on_step,
            correlation_id=correlation_id,
            deadline_monotonic=deadline_monotonic,
            clock=clock,
            effect_id=effect_id,
            observed_at=observed_at,
            invocation_class=invocation_class,
        )
    response = client.invoke_model(modelId=settings.bedrock_model_id, body=body)
    if deadline_monotonic is not None and clock() >= deadline_monotonic:
        raise AIInvocationFailure("deadline_exceeded")
    response_body = None
    close_ok = True
    try:
        if not isinstance(response, dict):
            raise AIInvocationFailure("malformed_response")
        response_body = response.get("body")
        read = getattr(response_body, "read", None)
        if not callable(read):
            raise AIInvocationFailure("malformed_response")
        result = json.loads(read())
        if not isinstance(result, dict):
            raise AIInvocationFailure("malformed_response")
        raw_text = result["content"][0]["text"]
    except AIInvocationFailure:
        raise
    except Exception:
        raise AIInvocationFailure("malformed_response") from None
    finally:
        try:
            close = getattr(response_body, "close", None)
            if not callable(close):
                close_ok = False
            else:
                close()
        except Exception:
            close_ok = False
    if not close_ok:
        raise AIInvocationFailure("response_cleanup_failed")
    if not isinstance(raw_text, str) or not raw_text:
        raise AIInvocationFailure("malformed_response")
    emit_private_event(
        "ai_response_received",
        output_size=len(raw_text),
        correlation_id=correlation_id,
    )

    return _answer_result(
        raw_text,
        result,
        response=response,
        effect_id=effect_id or correlation_id or "unbound-user-allowance-effect",
        observed_at=observed_at,
        invocation_class=invocation_class,
    )


def get_hint_answer(
    prompt: str,
    subject: str = "Mathematik",
    grade: str = "6. Klasse",
    *,
    language: str = "de",
    correlation_id: str | None = None,
    effect_id: str | None = None,
    observed_at: datetime | None = None,
    invocation_class: AIInvocationClass = AIInvocationClass.USER_ALLOWANCE,
    client: Any | None = None,
) -> AIProviderResult[str]:
    """Generate a short 1-2 sentence hint for a practice challenge."""
    safe_prompt = sanitise_input(prompt, correlation_id=correlation_id)
    system = (
        "You are a helpful Swiss maths teacher. "
        f"Write the hint in {language_name(language)} ({language}) and in no other language. "
        "Give a concise hint (1-2 sentences). "
        "Guide the student without revealing the answer. No JSON, just plain text."
    )
    client = client or boto3.client("bedrock-runtime", region_name=settings.aws_region)
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 120,
        "temperature": 0.3,
        "system": system,
        "messages": [{"role": "user", "content": safe_prompt}],
    })
    try:
        response = client.invoke_model(modelId=settings.bedrock_model_id, body=body)
        if not isinstance(response, dict):
            raise AIInvocationFailure("malformed_response")
        response_body = response.get("body")
        read = getattr(response_body, "read", None)
        if not callable(read):
            raise AIInvocationFailure("malformed_response")
        try:
            result = json.loads(read())
        finally:
            close = getattr(response_body, "close", None)
            if not callable(close):
                raise AIInvocationFailure("response_cleanup_failed")
            close()
        if not isinstance(result, dict):
            raise AIInvocationFailure("malformed_response")
        text = result["content"][0]["text"]
        if not isinstance(text, str) or not text.strip():
            raise AIInvocationFailure("malformed_response")
        logical_effect_id = effect_id or correlation_id or "unbound-user-allowance-hint"
        return _provider_result(
            text.strip(),
            result,
            response=response,
            inference_profile_id=settings.bedrock_model_id,
            effect_id=logical_effect_id,
            observed_at=observed_at,
            invocation_class=invocation_class,
        )
    except AIInvocationFailure:
        raise
    except Exception as exc:
        emit_private_event(
            "hint_generation_failed",
            exception=exc,
            input_size=len(prompt),
            correlation_id=correlation_id,
            level=logging.ERROR,
        )
        raise AIInvocationFailure("provider_dependency_error") from None
