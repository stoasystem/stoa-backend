"""Closed content-safe telemetry for private student and model flows."""

from __future__ import annotations

import logging
import re
from typing import Any


_EVENTS = frozenset(
    {
        "prompt_input_truncated",
        "prompt_injection_neutralized",
        "model_output_policy_issue",
        "model_output_parse_failed",
        "ai_request_started",
        "ai_response_received",
        # The provider refused a model call or failed to answer it (#435).
        "model_call_provider_failed",
        "title_generation_failed",
        "conversation_ai_failed",
        "conversation_ai_needs_reconciliation",
        "conversation_ai_needs_reconciliation_settled",
        "conversation_ai_attempts_exhausted",
        "question_ocr_failed",
        "question_ai_failed",
        "message_replay_wait_exhausted",
        # A chat help request nobody could be offered, waiting past the alert
        # limit (#88). stoa-infra pages stoa-alerts on this exact string.
        "teacher_help_waiting_no_candidate",
    }
)
_SAFE_TOKEN = re.compile(r"[^A-Za-z0-9._:-]")
logger = logging.getLogger("stoa.private_telemetry")


def _safe_token(value: Any, *, fallback: str, limit: int = 96) -> str:
    normalized = _SAFE_TOKEN.sub("_", str(value or ""))[:limit]
    return normalized or fallback


def emit_private_event(
    event_category: str,
    *,
    exception: BaseException | type[BaseException] | None = None,
    input_size: int | None = None,
    output_size: int | None = None,
    attachment_count: int | None = None,
    correlation_id: str | None = None,
    issue_count: int | None = None,
    wait_minutes: int | None = None,
    stage: str | None = None,
    provider_error_code: str | None = None,
    http_status: int | None = None,
    provider_request_id: str | None = None,
    provider_message: str | None = None,
    level: int = logging.INFO,
) -> None:
    """Emit only closed categories, class names, numeric sizes, and opaque IDs.

    The one exception is `provider_message`, the provider's own error text of a
    failed model call (#435): cut to 300 characters and reduced to the same
    safe characters as every other value, so it cannot forge a field.
    """
    if event_category not in _EVENTS:
        raise ValueError("unsupported private telemetry category")
    fields = [f"event_category={event_category}"]
    if exception is not None:
        exception_type = exception if isinstance(exception, type) else type(exception)
        fields.append(
            f"exception_class={_safe_token(exception_type.__name__, fallback='Exception', limit=64)}"
        )
    for name, value in (
        ("input_size", input_size),
        ("output_size", output_size),
        ("attachment_count", attachment_count),
        ("issue_count", issue_count),
        ("wait_minutes", wait_minutes),
    ):
        if value is not None:
            fields.append(f"{name}={max(0, int(value))}")
    for name, token, limit in (
        ("stage", stage, 32),
        ("provider_error_code", provider_error_code, 96),
        ("provider_request_id", provider_request_id, 96),
    ):
        if token:
            fields.append(f"{name}={_safe_token(token, fallback='-', limit=limit)}")
    if http_status is not None:
        fields.append(f"http_status={max(0, int(http_status))}")
    if provider_message:
        fields.append(
            f"provider_message={_safe_token(provider_message, fallback='-', limit=300)}"
        )
    if correlation_id:
        fields.append(
            f"correlation_id={_safe_token(correlation_id, fallback='server', limit=96)}"
        )
    logger.log(level, " ".join(fields))
