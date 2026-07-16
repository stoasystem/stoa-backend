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
        "hint_generation_failed",
        "title_generation_failed",
        "conversation_ai_failed",
        "question_ocr_failed",
        "question_ai_failed",
        "message_replay_wait_exhausted",
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
    level: int = logging.INFO,
) -> None:
    """Emit only closed categories, class names, numeric sizes, and opaque IDs."""
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
    ):
        if value is not None:
            fields.append(f"{name}={max(0, int(value))}")
    if correlation_id:
        fields.append(
            f"correlation_id={_safe_token(correlation_id, fallback='server', limit=96)}"
        )
    logger.log(level, " ".join(fields))
