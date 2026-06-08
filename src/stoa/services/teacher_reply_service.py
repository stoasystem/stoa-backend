"""Teacher reply normalization and SLA helpers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

REPLY_FORMAT = "stoa_teacher_reply_v1"
FIRST_REPLY_TARGET_SECONDS = 30 * 60
FIRST_REPLY_AT_RISK_SECONDS = 20 * 60
TAKEOVER_TARGET_SECONDS = 15 * 60

_TEXT_BLOCK_TYPES = {"paragraph", "heading", "ordered_list", "unordered_list", "quote", "code"}
_ALLOWED_BLOCK_TYPES = _TEXT_BLOCK_TYPES | {"formula"}
_TAG_PATTERN = re.compile(
    r"<\s*/?\s*(script|iframe|embed|object|style|link|meta|html|body|img|svg|video|audio|form|input|button|a)\b",
    re.IGNORECASE,
)
_EVENT_HANDLER_PATTERN = re.compile(r"\bon[a-z]+\s*=", re.IGNORECASE)
_AWS_ACCESS_KEY_PATTERN = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_SECRET_MARKERS = (
    "weekly-reports/",
    "private/",
    "s3://",
    "https://s3",
    "amazonaws.com",
    "x-amz-signature",
    "presignedurl",
    "presigned_url",
    "access_token",
    "id_token",
    "refresh_token",
    "aws_secret_access_key",
    "secretaccesskey",
    "password=",
    "cookie=",
)


class TeacherReplyValidationError(ValueError):
    """Raised when a teacher reply cannot be safely stored."""


def normalize_teacher_reply(content: str | None, rich_content: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize a plain or rich teacher reply into safe storage fields."""
    if rich_content is None:
        text = _sanitize_text(content or "", max_length=4000, field="content")
        normalized = {"version": 1, "blocks": [{"type": "paragraph", "text": text}]}
        fallback = text
    else:
        normalized = _normalize_rich_content(rich_content)
        fallback = _plain_text_fallback(normalized)
        if not fallback:
            raise TeacherReplyValidationError("teacher reply fallback is empty")
        if len(fallback) > 4000:
            raise TeacherReplyValidationError("teacher reply fallback exceeds 4000 characters")

    return {
        "teacher_response": fallback,
        "teacher_response_text": fallback,
        "teacher_response_rich": normalized,
        "teacher_response_format": REPLY_FORMAT,
    }


def compute_sla_fields(item: dict[str, Any], now: str) -> dict[str, Any]:
    """Compute per-question SLA duration fields where timestamps are available."""
    requested_at = _parse_timestamp(item.get("teacher_requested_at") or item.get("queue_visible_at"))
    taken_over_at = _parse_timestamp(item.get("teacher_taken_over_at") or item.get("teacher_started_at"))
    replied_at = _parse_timestamp(now)
    resolved_at = _parse_timestamp(item.get("resolved_at"))
    fields: dict[str, Any] = {}

    if requested_at and taken_over_at:
        fields["sla_request_to_takeover_seconds"] = _duration_seconds(requested_at, taken_over_at)
    if requested_at and replied_at:
        fields["sla_request_to_first_reply_seconds"] = _duration_seconds(requested_at, replied_at)
        fields["teacher_first_reply_sla_bucket"] = sla_bucket(fields["sla_request_to_first_reply_seconds"])
    if taken_over_at and replied_at:
        fields["sla_takeover_to_first_reply_seconds"] = _duration_seconds(taken_over_at, replied_at)
    if requested_at and resolved_at:
        fields["sla_request_to_resolved_seconds"] = _duration_seconds(requested_at, resolved_at)
    return fields


def compute_takeover_sla_fields(item: dict[str, Any], now: str) -> dict[str, Any]:
    requested_at = _parse_timestamp(item.get("teacher_requested_at") or item.get("queue_visible_at"))
    taken_over_at = _parse_timestamp(now)
    if not requested_at or not taken_over_at:
        return {}
    return {"sla_request_to_takeover_seconds": _duration_seconds(requested_at, taken_over_at)}


def compute_resolved_sla_fields(item: dict[str, Any], now: str) -> dict[str, Any]:
    requested_at = _parse_timestamp(item.get("teacher_requested_at") or item.get("queue_visible_at"))
    resolved_at = _parse_timestamp(now)
    if not requested_at or not resolved_at:
        return {}
    return {"sla_request_to_resolved_seconds": _duration_seconds(requested_at, resolved_at)}


def sla_bucket(duration_seconds: int | None) -> str:
    if duration_seconds is None:
        return "unknown"
    if duration_seconds <= FIRST_REPLY_AT_RISK_SECONDS:
        return "within_target"
    if duration_seconds <= FIRST_REPLY_TARGET_SECONDS:
        return "at_risk"
    return "breached"


def aggregate_teacher_sla(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Return privacy-safe aggregate teacher SLA metrics for admin stats."""
    teacher_questions = [
        item
        for item in questions
        if item.get("teacher_requested_at")
        or item.get("queue_visible_at")
        or item.get("teacher_taken_over_at")
        or item.get("teacher_first_replied_at")
        or item.get("status") in {"escalated", "teacher_active", "resolved"}
    ]
    first_reply_values = _numeric_values(
        item.get("sla_request_to_first_reply_seconds") for item in teacher_questions
    )
    takeover_values = _numeric_values(
        item.get("sla_request_to_takeover_seconds") for item in teacher_questions
    )
    resolve_values = _numeric_values(
        item.get("sla_request_to_resolved_seconds") for item in teacher_questions
    )
    buckets = {"within_target": 0, "at_risk": 0, "breached": 0, "unknown": 0}
    for item in teacher_questions:
        bucket = item.get("teacher_first_reply_sla_bucket")
        if not bucket and item.get("sla_request_to_first_reply_seconds") is not None:
            bucket = sla_bucket(_int_or_none(item.get("sla_request_to_first_reply_seconds")))
        if bucket not in buckets:
            bucket = "unknown"
        buckets[bucket] += 1

    return {
        "tracked_questions": len(teacher_questions),
        "first_reply": _duration_summary(first_reply_values),
        "takeover": _duration_summary(takeover_values),
        "resolved": _duration_summary(resolve_values),
        "buckets": buckets,
        "targets": {
            "first_reply_seconds": FIRST_REPLY_TARGET_SECONDS,
            "first_reply_at_risk_seconds": FIRST_REPLY_AT_RISK_SECONDS,
            "takeover_seconds": TAKEOVER_TARGET_SECONDS,
        },
    }


def _normalize_rich_content(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TeacherReplyValidationError("rich_content must be an object")
    if payload.get("version") != 1:
        raise TeacherReplyValidationError("rich_content version must be 1")
    blocks = payload.get("blocks")
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 20:
        raise TeacherReplyValidationError("rich_content blocks must contain 1 to 20 blocks")

    normalized_blocks = []
    for block in blocks:
        if not isinstance(block, dict):
            raise TeacherReplyValidationError("rich_content block must be an object")
        block_type = block.get("type")
        if block_type not in _ALLOWED_BLOCK_TYPES:
            raise TeacherReplyValidationError("unsupported rich_content block type")
        if block_type == "formula":
            normalized_blocks.append(
                {
                    "type": "formula",
                    "latex": _sanitize_text(str(block.get("latex") or ""), max_length=500, field="latex"),
                }
            )
        else:
            normalized_blocks.append(
                {
                    "type": block_type,
                    "text": _sanitize_text(str(block.get("text") or ""), max_length=2000, field="text"),
                }
            )
    return {"version": 1, "blocks": normalized_blocks}


def _sanitize_text(value: str, *, max_length: int, field: str) -> str:
    text = value.strip()
    if not text:
        raise TeacherReplyValidationError(f"{field} is required")
    if len(text) > max_length:
        raise TeacherReplyValidationError(f"{field} exceeds {max_length} characters")
    _assert_no_private_or_unsafe_markers(text)
    return text


def _assert_no_private_or_unsafe_markers(text: str) -> None:
    lowered = text.lower()
    if _TAG_PATTERN.search(text) or _EVENT_HANDLER_PATTERN.search(text):
        raise TeacherReplyValidationError("teacher reply contains unsafe raw HTML")
    if _AWS_ACCESS_KEY_PATTERN.search(text):
        raise TeacherReplyValidationError("teacher reply contains private credentials")
    for marker in _SECRET_MARKERS:
        if marker in lowered:
            raise TeacherReplyValidationError("teacher reply contains private markers")


def _plain_text_fallback(payload: dict[str, Any]) -> str:
    parts = []
    for block in payload.get("blocks", []):
        if block.get("type") == "formula":
            parts.append(str(block.get("latex", "")).strip())
        else:
            parts.append(str(block.get("text", "")).strip())
    return "\n".join(part for part in parts if part).strip()


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _duration_seconds(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds()))


def _numeric_values(values: Any) -> list[int]:
    result = []
    for value in values:
        parsed = _int_or_none(value)
        if parsed is not None:
            result.append(parsed)
    return result


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _duration_summary(values: list[int]) -> dict[str, int | None]:
    if not values:
        return {"count": 0, "average_seconds": None, "max_seconds": None}
    return {
        "count": len(values),
        "average_seconds": round(sum(values) / len(values)),
        "max_seconds": max(values),
    }
