"""Controlled admin report edit draft/apply workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from stoa.db.repositories import report_repo
from stoa.services import report_recovery_service

EDITABLE_FIELDS = frozenset({"admin_note", "editor_summary", "status_note"})
MAX_FIELD_LENGTH = 1200


@dataclass(frozen=True)
class ReportEditError(Exception):
    status_code: int
    detail: str
    error_class: str | None = None


def create_edit_draft(
    report: dict,
    *,
    operator: str,
    reason: str,
    proposed_fields: dict[str, Any],
    source: str = "admin_api",
    correlation_id: str | None = None,
) -> dict:
    fields = _validate_proposed_fields(proposed_fields)
    event_at = _now_iso()
    draft = {
        "draft_id": uuid4().hex,
        "report_id": report["report_id"],
        "parent_id": report.get("parent_id"),
        "student_id": report.get("student_id"),
        "week_start": report.get("week_start"),
        "source_updated_at": report.get("updated_at"),
        "created_by": operator,
        "created_at": event_at,
        "updated_at": event_at,
        "reason": _safe_text(reason, max_length=500),
        "proposed_fields": fields,
        "status": "draft",
    }
    report_repo.put_report_edit_draft(report["report_id"], draft)
    _write_report_edit_audit(
        report,
        action="create_report_edit_draft",
        actor=operator,
        reason=reason,
        source=source,
        result="draft",
        before=_metadata_snapshot(report),
        after={
            "draft_id": draft["draft_id"],
            "status": "draft",
            "proposed_fields": fields,
            "source_updated_at": draft["source_updated_at"],
        },
        event_at=event_at,
        correlation_id=correlation_id,
    )
    return sanitize_edit_draft(draft)


def get_edit_draft(report: dict, draft_id: str) -> dict:
    draft = report_repo.get_report_edit_draft(report["report_id"], draft_id)
    if not draft:
        raise ReportEditError(status_code=404, detail="Report edit draft not found")
    _assert_draft_matches_report(report, draft)
    return sanitize_edit_draft(draft)


def apply_edit_draft(
    report: dict,
    *,
    draft_id: str,
    operator: str,
    source: str = "admin_api",
    correlation_id: str | None = None,
) -> dict:
    draft = report_repo.get_report_edit_draft(report["report_id"], draft_id)
    if not draft:
        raise ReportEditError(status_code=404, detail="Report edit draft not found")
    _assert_draft_matches_report(report, draft)
    if draft.get("status") != "draft":
        raise ReportEditError(status_code=409, detail="Report edit draft is not applyable")
    if draft.get("source_updated_at") != report.get("updated_at"):
        _write_refused_apply(report, draft, operator, source, "Report changed after draft creation", correlation_id)
        raise ReportEditError(status_code=409, detail="Report changed after draft creation")

    fields = _validate_proposed_fields(draft.get("proposed_fields") or {})
    applied_at = _now_iso()
    update_fields = {
        **fields,
        "last_operation": "edit_report",
        "last_operation_at": applied_at,
        "last_operation_by": operator,
        "last_operation_result": "success",
        "updated_at": applied_at,
    }
    current_status = str(report.get("status") or "generated")
    if not report_repo.try_apply_report_edit(
        report["report_id"],
        expected_updated_at=report.get("updated_at"),
        status=current_status,
        fields=update_fields,
    ):
        _write_refused_apply(report, draft, operator, source, "Report changed after draft creation", correlation_id)
        raise ReportEditError(status_code=409, detail="Report changed after draft creation")
    if not report_repo.mark_report_edit_draft_applied(
        report["report_id"],
        draft_id,
        applied_at=applied_at,
        applied_by=operator,
    ):
        raise ReportEditError(status_code=409, detail="Report edit draft is not applyable")

    before = _metadata_snapshot(report)
    after = {**before, **fields, **update_fields, "status": current_status}
    _write_report_edit_audit(
        report,
        action="apply_report_edit",
        actor=operator,
        reason=str(draft.get("reason") or "admin_report_edit"),
        source=source,
        result="success",
        before=before,
        after={
            "draft_id": draft_id,
            "validation_result": "passed",
            "editable_fields": sorted(fields),
            **after,
        },
        event_at=applied_at,
        correlation_id=correlation_id,
    )
    applied_draft = {
        **draft,
        "status": "applied",
        "applied_at": applied_at,
        "applied_by": operator,
        "updated_at": applied_at,
    }
    return {
        "draft": sanitize_edit_draft(applied_draft),
        "report": sanitize_report_edit_result(after),
    }


def sanitize_edit_draft(draft: dict) -> dict:
    return {
        "draft_id": str(draft.get("draft_id") or ""),
        "report_id": str(draft.get("report_id") or ""),
        "parent_id": draft.get("parent_id"),
        "student_id": draft.get("student_id"),
        "week_start": draft.get("week_start"),
        "source_updated_at": draft.get("source_updated_at"),
        "created_by": draft.get("created_by"),
        "created_at": draft.get("created_at"),
        "updated_at": draft.get("updated_at"),
        "reason": report_recovery_service.redact_private_artifact_text(draft.get("reason")),
        "proposed_fields": _validate_proposed_fields(draft.get("proposed_fields") or {}),
        "status": str(draft.get("status") or ""),
        "applied_by": draft.get("applied_by"),
        "applied_at": draft.get("applied_at"),
    }


def sanitize_report_edit_result(report: dict) -> dict:
    return _metadata_snapshot(report)


def _validate_proposed_fields(proposed_fields: dict[str, Any]) -> dict[str, str | None]:
    if not isinstance(proposed_fields, dict) or not proposed_fields:
        raise ReportEditError(status_code=422, detail="At least one editable field is required")
    fields: dict[str, str | None] = {}
    for key, raw_value in proposed_fields.items():
        if key not in EDITABLE_FIELDS:
            raise ReportEditError(status_code=422, detail=f"Field is not editable: {key}")
        if raw_value is None:
            fields[key] = None
            continue
        if not isinstance(raw_value, str):
            raise ReportEditError(status_code=422, detail=f"Field must be a string: {key}")
        if _contains_private_marker(raw_value):
            raise ReportEditError(status_code=422, detail="Proposed edit contains private artifact marker")
        value = _safe_text(raw_value, max_length=MAX_FIELD_LENGTH)
        fields[key] = value
    return fields


def _assert_draft_matches_report(report: dict, draft: dict) -> None:
    if (
        draft.get("report_id") != report.get("report_id")
        or draft.get("parent_id") != report.get("parent_id")
        or draft.get("student_id") != report.get("student_id")
        or draft.get("week_start") != report.get("week_start")
    ):
        raise ReportEditError(status_code=409, detail="Report edit draft does not match report")


def _write_refused_apply(
    report: dict,
    draft: dict,
    operator: str,
    source: str,
    detail: str,
    correlation_id: str | None,
) -> None:
    event_at = _now_iso()
    before = _metadata_snapshot(report)
    _write_report_edit_audit(
        report,
        action="apply_report_edit",
        actor=operator,
        reason=str(draft.get("reason") or "admin_report_edit"),
        source=source,
        result="refused",
        before=before,
        after={
            "draft_id": draft.get("draft_id"),
            "validation_result": "failed",
            "refusal_reason": detail,
            **before,
        },
        event_at=event_at,
        error_message=detail,
        correlation_id=correlation_id,
    )


def _write_report_edit_audit(
    report: dict,
    *,
    action: str,
    actor: str,
    reason: str,
    source: str,
    result: str,
    before: dict[str, Any],
    after: dict[str, Any],
    event_at: str,
    error_class: str | None = None,
    error_message: str | None = None,
    correlation_id: str | None = None,
) -> None:
    report_repo.put_report_audit_event(
        str(report["report_id"]),
        {
            "event_id": uuid4().hex,
            "event_at": event_at,
            "report_id": report.get("report_id"),
            "parent_id": report.get("parent_id"),
            "student_id": report.get("student_id"),
            "week_start": report.get("week_start"),
            "actor": actor,
            "action": action,
            "reason": _safe_text(reason, max_length=500),
            "source": source,
            "result": result,
            "before": before,
            "after": after,
            "error_class": error_class,
            "error_message": report_recovery_service.redact_private_artifact_text(error_message),
            "correlation_id": correlation_id,
        },
    )


def _metadata_snapshot(report: dict) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "email_status": report.get("email_status"),
        "admin_note": report.get("admin_note"),
        "editor_summary": report.get("editor_summary"),
        "status_note": report.get("status_note"),
        "last_operation": report.get("last_operation"),
        "last_operation_at": report.get("last_operation_at"),
        "last_operation_by": report.get("last_operation_by"),
        "last_operation_result": report.get("last_operation_result"),
        "updated_at": report.get("updated_at"),
    }


def _safe_text(value: object, *, max_length: int) -> str:
    text = report_recovery_service.redact_private_artifact_text(value) or ""
    return text.strip()[:max_length]


def _contains_private_marker(value: str) -> bool:
    return any(
        token in value
        for token in (
            "weekly-reports/",
            "json_s3_key",
            "html_s3_key",
            "s3_key",
            "presignedUrl",
            "presigned_url",
            "X-Amz-",
            "https://s3",
            "<html",
        )
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
