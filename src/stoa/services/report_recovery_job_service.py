"""Async report recovery job orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
from typing import Any
from uuid import uuid4

import boto3

from stoa.config import settings
from stoa.db.repositories import report_repo
from stoa.services import report_recovery_service

MAX_TARGETS = 25
MAX_SCAN_PAGES = 5
FAILURE_THRESHOLD = 5
TIME_REMAINING_FLOOR_MS = 30_000


@dataclass(frozen=True)
class RecoveryJobError(Exception):
    status_code: int
    detail: str


def preview_resend_job(
    *,
    reason: str,
    operator: str,
    filters: dict[str, Any],
    max_targets: int = MAX_TARGETS,
) -> dict[str, Any]:
    if not reason.strip():
        raise RecoveryJobError(422, "Recovery reason is required")
    targets, scanned_pages = _collect_resend_targets(filters=filters, max_targets=max_targets)
    eligible = [target for target in targets if target["eligibility"] == "eligible"]
    refused = [target for target in targets if target["eligibility"] != "eligible"]
    token = _encode_preview_token(
        {
            "filters": _normalized_filters(filters),
            "reason": reason,
            "target_ids": [target["target_id"] for target in eligible],
        }
    )
    return {
        "operation": "resend_email",
        "reason": reason,
        "requested_by": operator,
        "filters": _normalized_filters(filters),
        "max_targets": max_targets,
        "scanned_pages": scanned_pages,
        "eligible_count": len(eligible),
        "refused_count": len(refused),
        "missing_count": 0,
        "sample": targets[:10],
        "preview_token": token,
    }


def create_resend_job(
    *,
    reason: str,
    operator: str,
    filters: dict[str, Any],
    preview_token: str,
    max_targets: int = MAX_TARGETS,
) -> dict[str, Any]:
    preview = preview_resend_job(reason=reason, operator=operator, filters=filters, max_targets=max_targets)
    if preview["preview_token"] != preview_token:
        raise RecoveryJobError(409, "Preview token no longer matches current recovery scope")
    if preview["eligible_count"] == 0:
        raise RecoveryJobError(422, "Recovery job has no eligible targets")
    collected, _ = _collect_resend_targets(filters=filters, max_targets=max_targets)
    eligible_targets = [item for item in collected if item["eligibility"] == "eligible"]

    now = _now_iso()
    job_id = uuid4().hex
    targets = [
        {
            "target_id": item["target_id"],
            "report_id": item["report_id"],
            "parent_id": item["parent_id"],
            "student_id": item["student_id"],
            "week_start": item["week_start"],
            "student_name": item.get("student_name"),
            "status": item.get("status"),
            "email_status": item.get("email_status"),
            "result": "pending",
            "created_at": now,
            "updated_at": now,
        }
        for item in eligible_targets
    ]
    job = {
        "job_id": job_id,
        "job_type": "resend_email",
        "status": "queued",
        "reason": reason,
        "created_by": operator,
        "created_at": now,
        "updated_at": now,
        "filters": preview["filters"],
        "target_count": len(targets),
        "pending_count": len(targets),
        "attempted_count": 0,
        "success_count": 0,
        "refused_count": 0,
        "not_found_count": 0,
        "failed_count": 0,
        "skipped_cancelled_count": 0,
        "failure_threshold": FAILURE_THRESHOLD,
        "preview_token": preview_token,
    }
    report_repo.put_recovery_job(job, targets)
    _write_job_audit(
        job_id,
        action="create_resend_job",
        actor=operator,
        reason=reason,
        result="queued",
        source="admin_api",
        metadata={"target_count": len(targets), "filters": preview["filters"]},
    )
    invoke_weekly_report_job(job_id)
    return job


def invoke_weekly_report_job(job_id: str) -> dict[str, Any]:
    payload = {"job": "report_recovery_resend_email", "job_id": job_id}
    client = boto3.client("lambda", region_name=settings.aws_region)
    response = client.invoke(
        FunctionName=settings.weekly_report_function_name,
        InvocationType="Event",
        Payload=json.dumps(payload, separators=(",", ":")).encode(),
    )
    return {"status_code": response.get("StatusCode")}


def execute_resend_job(job_id: str, *, context: Any = None) -> dict[str, Any]:
    job = report_repo.get_recovery_job(job_id)
    if not job:
        return {"status": "not_found", "job_id": job_id}

    now = _now_iso()
    if job.get("status") == "cancellation_requested":
        return _cancel_job(job, "cancelled_before_start", now)
    if job.get("status") == "queued" and not report_repo.try_claim_recovery_job(job_id, started_at=now):
        job = report_repo.get_recovery_job(job_id) or job
    if job.get("status") not in {"queued", "running"}:
        return {"status": "ignored", "job_id": job_id, "job_status": job.get("status")}

    _write_job_audit(
        job_id,
        action="run_resend_job",
        actor="weekly-report-worker",
        reason=job.get("reason"),
        result="started",
        source="weekly_report_lambda",
    )
    targets = _list_all_job_targets(job_id)
    counts = {
        "attempted_count": 0,
        "success_count": 0,
        "refused_count": 0,
        "not_found_count": 0,
        "failed_count": 0,
        "skipped_cancelled_count": 0,
    }
    stop_reason = None

    for target in targets:
        if target.get("result") != "pending":
            continue
        current_job = report_repo.get_recovery_job(job_id) or job
        if current_job.get("status") == "cancellation_requested":
            counts["skipped_cancelled_count"] += 1
            report_repo.update_recovery_job_target(
                job_id,
                target["SK"],
                "skipped_cancelled",
                detail="Cancellation requested before target attempt",
                updated_at=_now_iso(),
            )
            continue
        if _remaining_time_ms(context) < TIME_REMAINING_FLOOR_MS:
            stop_reason = "lambda_time_remaining_floor"
            break
        attempted_at = _now_iso()
        if not report_repo.try_claim_recovery_job_target(job_id, target["SK"], attempted_at=attempted_at):
            continue
        counts["attempted_count"] += 1
        outcome = _execute_resend_target(job, target, attempted_at=attempted_at)
        counts[f"{outcome}_count"] += 1
        if counts["failed_count"] >= int(job.get("failure_threshold") or FAILURE_THRESHOLD):
            stop_reason = "failure_threshold"
            break

    completed_at = _now_iso()
    final_status = _final_job_status(counts, stop_reason)
    completed_targets = (
        counts["success_count"]
        + counts["refused_count"]
        + counts["not_found_count"]
        + counts["failed_count"]
        + counts["skipped_cancelled_count"]
    )
    fields = {
        **counts,
        "pending_count": max(0, int(job.get("target_count") or 0) - completed_targets),
        "completed_at": completed_at,
        "updated_at": completed_at,
    }
    if stop_reason:
        fields["stop_reason"] = stop_reason
    report_repo.update_recovery_job_status(job_id, final_status, **fields)
    _write_job_audit(
        job_id,
        action="complete_resend_job",
        actor="weekly-report-worker",
        reason=job.get("reason"),
        result=final_status,
        source="weekly_report_lambda",
        metadata=fields,
    )
    return {"status": final_status, "job_id": job_id, **fields}


def cancel_resend_job(job_id: str, *, operator: str) -> dict[str, Any]:
    job = report_repo.get_recovery_job(job_id)
    if not job:
        raise RecoveryJobError(404, "Recovery job not found")
    requested_at = _now_iso()
    if job.get("status") in {"completed", "completed_with_failures", "cancelled", "failed"}:
        raise RecoveryJobError(409, "Recovery job is already terminal")
    if not report_repo.request_recovery_job_cancellation(job_id, requested_by=operator, requested_at=requested_at):
        raise RecoveryJobError(409, "Recovery job cannot be cancelled")
    _write_job_audit(
        job_id,
        action="request_cancellation",
        actor=operator,
        reason=job.get("reason"),
        result="cancellation_requested",
        source="admin_api",
    )
    return {**job, "status": "cancellation_requested", "cancellation_requested_by": operator, "updated_at": requested_at}


def _execute_resend_target(job: dict, target: dict, *, attempted_at: str) -> str:
    report = report_repo.get_report_for_child_by_week(
        target["parent_id"],
        target["student_id"],
        target["week_start"],
    )
    if not report:
        _finish_target(job, target, "not_found", detail="Report not found")
        return "not_found"
    if not report_repo.try_claim_report_resend(
        report["report_id"],
        operator=str(job.get("created_by") or "recovery-job"),
        attempted_at=attempted_at,
    ):
        _finish_target(job, target, "refused", report_id=report.get("report_id"), detail="Report is no longer eligible")
        return "refused"
    try:
        result = report_recovery_service.resend_report_email(
            report,
            operator=str(job.get("created_by") or "recovery-job"),
            reason=str(job.get("reason") or "recovery_job_resend"),
            source="recovery_job",
            correlation_id=str(job["job_id"]),
        )
    except report_recovery_service.ReportRecoveryError as exc:
        outcome = "failed" if exc.status_code >= 500 else "refused"
        _finish_target(
            job,
            target,
            outcome,
            report_id=report.get("report_id"),
            detail=report_recovery_service.redact_private_artifact_text(exc.detail),
            error_class=exc.error_class,
        )
        return outcome
    _finish_target(
        job,
        target,
        "success",
        report_id=result.report_id,
        status=result.status,
        email_status=result.email_status,
    )
    return "success"


def _finish_target(
    job: dict,
    target: dict,
    result: str,
    *,
    report_id: str | None = None,
    status: str | None = None,
    email_status: str | None = None,
    detail: str | None = None,
    error_class: str | None = None,
) -> None:
    completed_at = _now_iso()
    fields = {
        "report_id": report_id or target.get("report_id"),
        "status": status,
        "email_status": email_status,
        "detail": report_recovery_service.redact_private_artifact_text(detail),
        "error_class": error_class,
        "completed_at": completed_at,
        "updated_at": completed_at,
    }
    report_repo.update_recovery_job_target(job["job_id"], target["SK"], result, **fields)
    _write_job_audit(
        job["job_id"],
        action="resend_target",
        actor="weekly-report-worker",
        reason=job.get("reason"),
        result=result,
        source="weekly_report_lambda",
        metadata={
            "target_id": target.get("target_id"),
            "parent_id": target.get("parent_id"),
            "student_id": target.get("student_id"),
            "week_start": target.get("week_start"),
            "detail": fields["detail"],
        },
    )


def _collect_resend_targets(*, filters: dict[str, Any], max_targets: int) -> tuple[list[dict[str, Any]], int]:
    filters = _normalized_filters(filters)
    if filters.get("status") != "email_failed":
        raise RecoveryJobError(422, "Only email_failed resend recovery is supported")
    max_targets = min(max(1, int(max_targets)), MAX_TARGETS)
    targets: list[dict[str, Any]] = []
    last_key = None
    pages = 0
    while pages < MAX_SCAN_PAGES and len(targets) < max_targets:
        result = report_repo.list_reports_for_admin(
            status=filters.get("status"),
            week_start=filters.get("week_start"),
            parent_id=filters.get("parent_id"),
            student_id=filters.get("student_id"),
            limit=max_targets,
            last_key=last_key,
        )
        pages += 1
        for report in result.get("Items", []):
            target = _target_preview(report)
            targets.append(target)
            if len(targets) >= max_targets:
                break
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
    return targets, pages


def _target_preview(report: dict) -> dict[str, Any]:
    html_available = bool(report.get("html_s3_key") or report.get("s3_key"))
    email_available = bool(report.get("parent_email"))
    eligible = (report.get("status") == "email_failed" or report.get("email_status") == "failed") and html_available and email_available
    return {
        "target_id": str(report.get("report_id") or uuid4().hex),
        "report_id": report.get("report_id"),
        "parent_id": report.get("parent_id"),
        "student_id": report.get("student_id"),
        "student_name": report.get("student_name"),
        "week_start": report.get("week_start"),
        "status": report.get("status"),
        "email_status": report.get("email_status"),
        "artifacts": {"html_available": html_available, "json_available": bool(report.get("json_s3_key"))},
        "eligibility": "eligible" if eligible else "refused",
        "refusal_reason": None if eligible else "Report is missing failed delivery state, parent email, or HTML artifact",
    }


def _list_all_job_targets(job_id: str) -> list[dict]:
    targets: list[dict] = []
    last_key = None
    while True:
        result = report_repo.list_recovery_job_targets(job_id, limit=MAX_TARGETS, last_key=last_key)
        targets.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            return targets


def _cancel_job(job: dict, reason: str, cancelled_at: str) -> dict[str, Any]:
    targets = _list_all_job_targets(job["job_id"])
    skipped = 0
    for target in targets:
        if target.get("result") == "pending":
            skipped += 1
            report_repo.update_recovery_job_target(
                job["job_id"],
                target["SK"],
                "skipped_cancelled",
                detail="Cancellation requested before target attempt",
                updated_at=cancelled_at,
            )
    fields = {
        "skipped_cancelled_count": skipped,
        "pending_count": 0,
        "cancelled_at": cancelled_at,
        "completed_at": cancelled_at,
        "updated_at": cancelled_at,
        "stop_reason": reason,
    }
    report_repo.update_recovery_job_status(job["job_id"], "cancelled", **fields)
    _write_job_audit(
        job["job_id"],
        action="complete_resend_job",
        actor="weekly-report-worker",
        reason=job.get("reason"),
        result="cancelled",
        source="weekly_report_lambda",
        metadata=fields,
    )
    return {"status": "cancelled", "job_id": job["job_id"], **fields}


def _final_job_status(counts: dict[str, int], stop_reason: str | None) -> str:
    if counts["skipped_cancelled_count"] > 0:
        return "cancelled"
    if stop_reason == "failure_threshold":
        return "failed"
    if counts["failed_count"] or counts["refused_count"] or counts["not_found_count"] or stop_reason:
        return "completed_with_failures"
    return "completed"


def _write_job_audit(
    job_id: str,
    *,
    action: str,
    actor: str,
    reason: str | None,
    result: str,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    event_at = _now_iso()
    report_repo.put_recovery_job_audit_event(
        job_id,
        {
            "event_id": uuid4().hex,
            "event_at": event_at,
            "job_id": job_id,
            "actor": actor,
            "action": action,
            "reason": reason,
            "source": source,
            "result": result,
            "metadata": _redact_metadata(metadata or {}),
        },
    )


def _redact_metadata(value: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): report_recovery_service.redact_private_artifact_text(raw) if isinstance(raw, str) else raw
        for key, raw in value.items()
        if not str(key).endswith("_s3_key") and str(key) != "s3_key"
    }


def _normalized_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": filters.get("status") or "email_failed",
        "week_start": filters.get("week_start"),
        "parent_id": filters.get("parent_id"),
        "student_id": filters.get("student_id"),
    }


def _encode_preview_token(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    encoded = {"scope": "report_recovery_preview", "digest": digest}
    return base64.urlsafe_b64encode(json.dumps(encoded, separators=(",", ":"), sort_keys=True).encode()).decode()


def _remaining_time_ms(context: Any) -> int:
    if context is None or not hasattr(context, "get_remaining_time_in_millis"):
        return TIME_REMAINING_FLOOR_MS + 1
    return int(context.get_remaining_time_in_millis())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
