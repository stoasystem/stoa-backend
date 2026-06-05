"""Shared report recovery operations and append-only audit evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4

from stoa.db.repositories import report_repo
from stoa.services import notify_service, report_artifact_service, report_service


@dataclass(frozen=True)
class ReportRecoveryError(Exception):
    status_code: int
    detail: str
    result: str = "failed"
    error_class: str | None = None


@dataclass(frozen=True)
class ReportRecoveryResult:
    report_id: str
    status: str
    email_status: str | None
    operation: str
    operation_result: str
    updated_at: str
    artifacts: dict[str, bool] | None = None


def resend_report_email(
    report: dict,
    *,
    operator: str,
    reason: str = "admin_single_resend",
    source: str = "admin_api",
    correlation_id: str | None = None,
) -> ReportRecoveryResult:
    """Resend one failed report email and write append-only audit evidence."""
    if report.get("status") != "email_failed" and report.get("email_status") != "failed":
        raise _refused(report, "resend_email", operator, reason, source, "Report delivery is not failed")

    html_key = report.get("html_s3_key") or report.get("s3_key")
    parent_email = report.get("parent_email")
    if not html_key or not parent_email:
        raise _refused(
            report,
            "resend_email",
            operator,
            reason,
            source,
            "Report is missing email or HTML artifact metadata",
            status_code=422,
        )

    before = _audit_snapshot(report)
    attempted_at = _now_iso()
    try:
        html = report_artifact_service.get_report_html(str(html_key))
        notify_service.send_weekly_report_email(
            str(parent_email),
            html,
            subject=f"STOA weekly report for {report.get('student_name') or 'Student'}",
        )
    except Exception as exc:
        failed_at = _now_iso()
        fields = {
            "email_status": "failed",
            "email_failed_at": failed_at,
            "email_error_class": type(exc).__name__,
            "email_error_message": safe_error_message(exc),
            "resend_attempted_at": attempted_at,
            "last_operation": "resend_email",
            "last_operation_at": failed_at,
            "last_operation_by": operator,
            "last_operation_result": "failed",
            "updated_at": failed_at,
        }
        report_repo.update_report_status(report["report_id"], "email_failed", **fields)
        _write_report_audit(
            report,
            action="resend_email",
            actor=operator,
            reason=reason,
            source=source,
            result="failed",
            before=before,
            after={**before, "status": "email_failed", **fields},
            event_at=failed_at,
            error_class=type(exc).__name__,
            error_message=safe_error_message(exc),
            correlation_id=correlation_id,
        )
        raise ReportRecoveryError(
            status_code=502,
            detail="Report resend failed",
            result="failed",
            error_class=type(exc).__name__,
        ) from exc

    sent_at = _now_iso()
    fields = {
        "email_status": "sent",
        "email_sent_at": sent_at,
        "resend_attempted_at": attempted_at,
        "resend_completed_at": sent_at,
        "last_operation": "resend_email",
        "last_operation_at": sent_at,
        "last_operation_by": operator,
        "last_operation_result": "success",
        "updated_at": sent_at,
    }
    report_repo.update_report_status(report["report_id"], "email_sent", **fields)
    _write_report_audit(
        report,
        action="resend_email",
        actor=operator,
        reason=reason,
        source=source,
        result="success",
        before=before,
        after={**before, "status": "email_sent", **fields},
        event_at=sent_at,
        correlation_id=correlation_id,
    )
    return ReportRecoveryResult(
        report_id=report["report_id"],
        status="email_sent",
        email_status="sent",
        operation="resend_email",
        operation_result="success",
        updated_at=sent_at,
    )


def retry_report_generation(
    report: dict,
    *,
    parent_id: str,
    student_id: str,
    week_start: str,
    operator: str,
    reason: str = "admin_single_generation_retry",
    source: str = "admin_api",
    correlation_id: str | None = None,
) -> ReportRecoveryResult:
    """Retry one generation-failed report and write append-only audit evidence."""
    if report.get("status") != "generation_failed":
        raise _refused(report, "retry_generation", operator, reason, source, "Report generation is not failed")

    before = _audit_snapshot(report)
    attempted_at = _now_iso()
    if not report_repo.try_start_generation_retry(report["report_id"], operator=operator, attempted_at=attempted_at):
        raise _refused(
            report,
            "retry_generation",
            operator,
            reason,
            source,
            "Report generation retry is already in progress or no longer failed",
        )
    try:
        payload = report_service.build_weekly_learning_payload(parent_id, student_id, week_start)
        generated_content = report_service.generate_weekly_report_content(payload)
        stored_report = report_service.store_and_send_weekly_report(payload, generated_content)
        if stored_report.get("report_id") != report.get("report_id"):
            raise ValueError("Retry generated a mismatched report id")
    except Exception as exc:
        failed_at = _now_iso()
        fields = {
            "generation_failed_at": failed_at,
            "generation_error_class": type(exc).__name__,
            "generation_error_message": safe_error_message(exc),
            "generation_retry_attempted_at": attempted_at,
            "last_operation": "retry_generation",
            "last_operation_at": failed_at,
            "last_operation_by": operator,
            "last_operation_result": "failed",
            "updated_at": failed_at,
        }
        report_repo.update_report_status(report["report_id"], "generation_failed", **fields)
        _write_report_audit(
            report,
            action="retry_generation",
            actor=operator,
            reason=reason,
            source=source,
            result="failed",
            before=before,
            after={**before, "status": "generation_failed", **fields},
            event_at=failed_at,
            error_class=type(exc).__name__,
            error_message=safe_error_message(exc),
            correlation_id=correlation_id,
        )
        raise ReportRecoveryError(
            status_code=502,
            detail="Report generation retry failed",
            result="failed",
            error_class=type(exc).__name__,
        ) from exc

    completed_at = _now_iso()
    fields = {
        "email_status": stored_report.get("email_status"),
        "generation_retry_attempted_at": attempted_at,
        "generation_retry_completed_at": completed_at,
        "last_operation": "retry_generation",
        "last_operation_at": completed_at,
        "last_operation_by": operator,
        "last_operation_result": "success",
        "updated_at": completed_at,
    }
    status = stored_report.get("status", "generated")
    report_repo.update_report_status(stored_report["report_id"], status, **fields)
    _write_report_audit(
        stored_report,
        action="retry_generation",
        actor=operator,
        reason=reason,
        source=source,
        result="success",
        before=before,
        after={**_audit_snapshot(stored_report), **fields},
        event_at=completed_at,
        correlation_id=correlation_id,
    )
    return ReportRecoveryResult(
        report_id=stored_report["report_id"],
        status=status,
        email_status=stored_report.get("email_status"),
        operation="retry_generation",
        operation_result="success",
        updated_at=completed_at,
        artifacts={
            "json_available": bool(stored_report.get("json_s3_key")),
            "html_available": bool(stored_report.get("html_s3_key") or stored_report.get("s3_key")),
        },
    )


def safe_error_message(exc: Exception) -> str:
    return redact_private_artifact_text(str(exc))[:240] or type(exc).__name__


def redact_private_artifact_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"https?://[^\s'\"<>]*(?:s3|X-Amz-)[^\s'\"<>]*", "[report-artifact-url]", text)
    text = re.sub(r"weekly-reports/[^\s'\"<>]+", "[report-artifact-key]", text)
    for token in ("json_s3_key", "html_s3_key", "s3_key"):
        text = text.replace(token, "[report-artifact-field]")
    return text


def _refused(
    report: dict,
    action: str,
    actor: str,
    reason: str,
    source: str,
    detail: str,
    *,
    status_code: int = 409,
) -> ReportRecoveryError:
    event_at = _now_iso()
    before = _audit_snapshot(report)
    _write_report_audit(
        report,
        action=action,
        actor=actor,
        reason=reason,
        source=source,
        result="refused",
        before=before,
        after=before,
        event_at=event_at,
        error_message=detail,
    )
    return ReportRecoveryError(status_code=status_code, detail=detail, result="refused")


def _write_report_audit(
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
    report_id = str(report["report_id"])
    report_repo.put_report_audit_event(
        report_id,
        {
            "event_id": uuid4().hex,
            "event_at": event_at,
            "report_id": report_id,
            "parent_id": report.get("parent_id"),
            "student_id": report.get("student_id"),
            "week_start": report.get("week_start"),
            "actor": actor,
            "action": action,
            "reason": reason,
            "source": source,
            "result": result,
            "before": before,
            "after": after,
            "error_class": error_class,
            "error_message": redact_private_artifact_text(error_message),
            "correlation_id": correlation_id,
        },
    )


def _audit_snapshot(report: dict) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "email_status": report.get("email_status"),
        "last_operation": report.get("last_operation"),
        "last_operation_at": report.get("last_operation_at"),
        "last_operation_by": report.get("last_operation_by"),
        "last_operation_result": report.get("last_operation_result"),
        "generation_failed_at": report.get("generation_failed_at"),
        "email_failed_at": report.get("email_failed_at"),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
