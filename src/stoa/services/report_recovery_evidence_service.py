"""Metadata-only report recovery evidence export helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from stoa.services import report_recovery_service


logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_export_response(
    *,
    scope: str,
    request_id: str | None,
    filters: dict[str, Any],
    jobs: list[dict],
    targets: list[dict] | None = None,
    job_audit: list[dict] | None = None,
    report_audit: list[dict] | None = None,
    next_tokens: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    tokens = {
        "jobs": None,
        "targets": None,
        "job_audit": None,
        "report_audit": None,
        **(next_tokens or {}),
    }
    return {
        "exported_at": now_iso(),
        "request_id": request_id,
        "scope": scope,
        "complete": all(value is None for value in tokens.values()),
        "filters": sanitize_metadata(filters) or {},
        "jobs": [job_summary(job) for job in jobs],
        "targets": [target_summary(item) for item in (targets or [])],
        "job_audit": [audit_summary(item) for item in (job_audit or [])],
        "report_audit": [audit_summary(item) for item in (report_audit or [])],
        "next_tokens": tokens,
        "privacy": {
            "metadata_only": True,
            "private_artifact_fields_omitted": True,
        },
    }


def log_export_access(
    *,
    actor: str,
    request_id: str | None,
    scope: str,
    filters: dict[str, Any],
    result_counts: dict[str, int],
    status: str,
) -> None:
    logger.info(
        "report_recovery_evidence_export",
        extra={
            "actor": actor,
            "request_id": request_id,
            "scope": scope,
            "filters": sanitize_metadata(filters) or {},
            "result_counts": result_counts,
            "status": status,
            "read_only": True,
        },
    )


def job_summary(job: dict) -> dict[str, Any]:
    return {
        "job_id": str(job.get("job_id", "")),
        "job_type": _string_or_none(job.get("job_type")),
        "status": _string_or_none(job.get("status")),
        "reason": _redact_text(job.get("reason")),
        "created_by": _string_or_none(job.get("created_by")),
        "created_at": _string_or_none(job.get("created_at")),
        "updated_at": _string_or_none(job.get("updated_at")),
        "started_at": _string_or_none(job.get("started_at")),
        "completed_at": _string_or_none(job.get("completed_at")),
        "cancellation_requested_by": _string_or_none(job.get("cancellation_requested_by")),
        "cancellation_requested_at": _string_or_none(job.get("cancellation_requested_at")),
        "filters": sanitize_metadata(job.get("filters")),
        "target_count": _int_or_zero(job.get("target_count")),
        "pending_count": _int_or_zero(job.get("pending_count")),
        "attempted_count": _int_or_zero(job.get("attempted_count")),
        "success_count": _int_or_zero(job.get("success_count")),
        "refused_count": _int_or_zero(job.get("refused_count")),
        "not_found_count": _int_or_zero(job.get("not_found_count")),
        "failed_count": _int_or_zero(job.get("failed_count")),
        "skipped_cancelled_count": _int_or_zero(job.get("skipped_cancelled_count")),
        "stop_reason": _redact_text(job.get("stop_reason")),
    }


def target_summary(target: dict) -> dict[str, Any]:
    return {
        "target_id": str(target.get("target_id", "")),
        "report_id": _string_or_none(target.get("report_id")),
        "parent_id": _string_or_none(target.get("parent_id")),
        "student_id": _string_or_none(target.get("student_id")),
        "student_name": _string_or_none(target.get("student_name")),
        "week_start": _string_or_none(target.get("week_start")),
        "result": _string_or_none(target.get("result")),
        "status": _string_or_none(target.get("status")),
        "email_status": _string_or_none(target.get("email_status")),
        "detail": _redact_text(target.get("detail")),
        "error_class": _string_or_none(target.get("error_class")),
        "attempted_at": _string_or_none(target.get("attempted_at")),
        "completed_at": _string_or_none(target.get("completed_at")),
    }


def audit_summary(event: dict) -> dict[str, Any]:
    return {
        "event_id": str(event.get("event_id", "")),
        "event_at": str(event.get("event_at", "")),
        "report_id": _string_or_none(event.get("report_id")),
        "parent_id": _string_or_none(event.get("parent_id")),
        "student_id": _string_or_none(event.get("student_id")),
        "week_start": _string_or_none(event.get("week_start")),
        "actor": _string_or_none(event.get("actor")),
        "action": str(event.get("action", "")),
        "reason": _redact_text(event.get("reason")),
        "source": _string_or_none(event.get("source")),
        "result": str(event.get("result", "")),
        "before": sanitize_metadata(event.get("before")),
        "after": sanitize_metadata(event.get("after")),
        "error_class": _string_or_none(event.get("error_class")),
        "error_message": _redact_text(event.get("error_message")),
        "correlation_id": _string_or_none(event.get("correlation_id")),
    }


def sanitize_metadata(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    sanitized: dict[str, Any] = {}
    for key, raw in value.items():
        key_text = str(key)
        if _is_private_artifact_field(key_text):
            continue
        sanitized[key_text] = _sanitize_value(raw)
    return sanitized


def _sanitize_value(value: object) -> Any:
    if isinstance(value, dict):
        return sanitize_metadata(value) or {}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: object) -> str | None:
    return report_recovery_service.redact_private_artifact_text(value)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return _redact_text(value)


def _int_or_zero(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_private_artifact_field(key: str) -> bool:
    lowered = key.lower()
    return (
        key == "s3_key"
        or key.endswith("_s3_key")
        or "presigned" in lowered
        or lowered in {"publicurl", "public_url", "s3url", "s3_url"}
    )
