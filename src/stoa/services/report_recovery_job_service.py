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
RESEND_JOB_TYPE = "resend_email"
GENERATION_RETRY_JOB_TYPE = "retry_generation"
RESUME_OPERATION = "resume_recovery_job"
DEFAULT_RESUME_RESULTS = ("failed", "refused", "not_found")
RESUMABLE_TARGET_RESULTS = {"failed", "refused", "not_found", "skipped_cancelled"}
RESUMABLE_SOURCE_STATUSES = {
    "completed",
    "completed_with_failures",
    "cancelled",
    "failed",
    "stopped_failure_threshold",
    "stopped_time_floor",
}


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
    return _preview_job(
        job_type=RESEND_JOB_TYPE,
        reason=reason,
        operator=operator,
        filters=filters,
        max_targets=max_targets,
    )


def preview_generation_retry_job(
    *,
    reason: str,
    operator: str,
    filters: dict[str, Any],
    max_targets: int = MAX_TARGETS,
) -> dict[str, Any]:
    return _preview_job(
        job_type=GENERATION_RETRY_JOB_TYPE,
        reason=reason,
        operator=operator,
        filters=filters,
        max_targets=max_targets,
    )


def create_resend_job(
    *,
    reason: str,
    operator: str,
    filters: dict[str, Any],
    preview_token: str,
    max_targets: int = MAX_TARGETS,
) -> dict[str, Any]:
    preview = preview_resend_job(reason=reason, operator=operator, filters=filters, max_targets=max_targets)
    return _create_job(
        job_type=RESEND_JOB_TYPE,
        audit_action="create_resend_job",
        reason=reason,
        operator=operator,
        filters=filters,
        preview=preview,
        preview_token=preview_token,
        max_targets=max_targets,
    )


def create_generation_retry_job(
    *,
    reason: str,
    operator: str,
    filters: dict[str, Any],
    preview_token: str,
    max_targets: int = MAX_TARGETS,
) -> dict[str, Any]:
    preview = preview_generation_retry_job(reason=reason, operator=operator, filters=filters, max_targets=max_targets)
    return _create_job(
        job_type=GENERATION_RETRY_JOB_TYPE,
        audit_action="create_retry_generation_job",
        reason=reason,
        operator=operator,
        filters=filters,
        preview=preview,
        preview_token=preview_token,
        max_targets=max_targets,
    )


def preview_resume_job(
    *,
    source_job_id: str,
    reason: str,
    operator: str,
    results: list[str] | None = None,
    max_targets: int = MAX_TARGETS,
) -> dict[str, Any]:
    if not reason.strip():
        raise RecoveryJobError(422, "Recovery reason is required")
    source_job = _get_resumable_source_job(source_job_id)
    result_filters = _normalized_resume_results(results)
    targets = _collect_resume_targets(source_job_id, result_filters=result_filters, max_targets=max_targets)
    token = _encode_preview_token(
        {
            "operation": RESUME_OPERATION,
            "source_job_id": source_job_id,
            "job_type": str(source_job.get("job_type") or RESEND_JOB_TYPE),
            "reason": reason,
            "result_filters": result_filters,
            "max_targets": min(max(1, int(max_targets)), MAX_TARGETS),
            "target_ids": [target["target_id"] for target in targets],
            "target_snapshot_hash": _target_snapshot_hash(targets),
        }
    )
    return {
        "operation": RESUME_OPERATION,
        "source_job_id": source_job_id,
        "job_type": str(source_job.get("job_type") or RESEND_JOB_TYPE),
        "reason": reason,
        "requested_by": operator,
        "result_filters": result_filters,
        "max_targets": min(max(1, int(max_targets)), MAX_TARGETS),
        "scanned_targets": len(targets),
        "eligible_count": len(targets),
        "refused_count": 0,
        "missing_count": 0,
        "sample": targets[:10],
        "preview_token": token,
    }


def create_resume_job(
    *,
    source_job_id: str,
    reason: str,
    operator: str,
    results: list[str] | None,
    preview_token: str,
    max_targets: int = MAX_TARGETS,
) -> dict[str, Any]:
    preview = preview_resume_job(
        source_job_id=source_job_id,
        reason=reason,
        operator=operator,
        results=results,
        max_targets=max_targets,
    )
    if preview["preview_token"] != preview_token:
        raise RecoveryJobError(409, "Preview token no longer matches current recovery scope")
    if preview["eligible_count"] == 0:
        raise RecoveryJobError(422, "Resume job has no eligible targets")

    now = _now_iso()
    job_id = uuid4().hex
    job_type = str(preview["job_type"])
    resume_targets = _collect_resume_targets(
        source_job_id,
        result_filters=list(preview["result_filters"]),
        max_targets=max_targets,
    )
    targets = [
        {
            "target_id": item["target_id"],
            "report_id": item.get("report_id"),
            "parent_id": item.get("parent_id"),
            "student_id": item.get("student_id"),
            "week_start": item.get("week_start"),
            "student_name": item.get("student_name"),
            "status": item.get("status"),
            "email_status": item.get("email_status"),
            "source_job_id": source_job_id,
            "source_target_result": item.get("source_result"),
            "result": "pending",
            "created_at": now,
            "updated_at": now,
        }
        for item in resume_targets
    ]
    job = {
        "job_id": job_id,
        "job_type": job_type,
        "status": "queued",
        "reason": reason,
        "created_by": operator,
        "created_at": now,
        "updated_at": now,
        "filters": {
            "source_job_id": source_job_id,
            "result_filters": preview["result_filters"],
        },
        "source_job_id": source_job_id,
        "resume_result_filters": preview["result_filters"],
        "resume_from": {"job_id": source_job_id, "job_type": job_type},
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
    audit_metadata = {
        "source_job_id": source_job_id,
        "resumed_job_id": job_id,
        "job_type": job_type,
        "result_filters": preview["result_filters"],
        "target_count": len(targets),
    }
    _write_job_audit(
        source_job_id,
        action="create_resume_job",
        actor=operator,
        reason=reason,
        result="queued",
        source="admin_api",
        metadata=audit_metadata,
    )
    _write_job_audit(
        job_id,
        action="create_resume_job",
        actor=operator,
        reason=reason,
        result="queued",
        source="admin_api",
        metadata=audit_metadata,
    )
    invoke_weekly_report_job(job_id, job_type=job_type)
    return job


def _create_job(
    *,
    job_type: str,
    audit_action: str,
    reason: str,
    operator: str,
    filters: dict[str, Any],
    preview: dict[str, Any],
    preview_token: str,
    max_targets: int,
) -> dict[str, Any]:
    if preview["preview_token"] != preview_token:
        raise RecoveryJobError(409, "Preview token no longer matches current recovery scope")
    if preview["eligible_count"] == 0:
        raise RecoveryJobError(422, "Recovery job has no eligible targets")
    collected, _ = _collect_targets(job_type=job_type, filters=filters, max_targets=max_targets)
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
        "job_type": job_type,
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
        action=audit_action,
        actor=operator,
        reason=reason,
        result="queued",
        source="admin_api",
        metadata={"job_type": job_type, "target_count": len(targets), "filters": preview["filters"]},
    )
    invoke_weekly_report_job(job_id, job_type=job_type)
    return job


def invoke_weekly_report_job(job_id: str, *, job_type: str = RESEND_JOB_TYPE) -> dict[str, Any]:
    payload = {"job": _worker_event_name(job_type), "job_id": job_id}
    client = boto3.client("lambda", region_name=settings.aws_region)
    response = client.invoke(
        FunctionName=settings.weekly_report_function_name,
        InvocationType="Event",
        Payload=json.dumps(payload, separators=(",", ":")).encode(),
    )
    return {"status_code": response.get("StatusCode")}


def execute_resend_job(job_id: str, *, context: Any = None) -> dict[str, Any]:
    return _execute_job(
        job_id,
        expected_job_type=RESEND_JOB_TYPE,
        run_action="run_resend_job",
        complete_action="complete_resend_job",
        target_executor=_execute_resend_target,
        context=context,
    )


def execute_generation_retry_job(job_id: str, *, context: Any = None) -> dict[str, Any]:
    return _execute_job(
        job_id,
        expected_job_type=GENERATION_RETRY_JOB_TYPE,
        run_action="run_retry_generation_job",
        complete_action="complete_retry_generation_job",
        target_executor=_execute_generation_retry_target,
        context=context,
    )


def _execute_job(
    job_id: str,
    *,
    expected_job_type: str,
    run_action: str,
    complete_action: str,
    target_executor: Any,
    context: Any = None,
) -> dict[str, Any]:
    job = report_repo.get_recovery_job(job_id)
    if not job:
        return {"status": "not_found", "job_id": job_id}
    actual_job_type = str(job.get("job_type") or RESEND_JOB_TYPE)
    if actual_job_type != expected_job_type:
        return {
            "status": "ignored",
            "job_id": job_id,
            "job_type": actual_job_type,
            "expected_job_type": expected_job_type,
        }

    now = _now_iso()
    if job.get("status") == "cancellation_requested":
        return _cancel_job(job, "cancelled_before_start", now, complete_action=complete_action)
    if job.get("status") == "queued" and not report_repo.try_claim_recovery_job(job_id, started_at=now):
        job = report_repo.get_recovery_job(job_id) or job
    if job.get("status") not in {"queued", "running"}:
        return {"status": "ignored", "job_id": job_id, "job_status": job.get("status")}

    _write_job_audit(
        job_id,
        action=run_action,
        actor="weekly-report-worker",
        reason=job.get("reason"),
        result="started",
        source="weekly_report_lambda",
        metadata={"job_type": expected_job_type},
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
        outcome = target_executor(job, target, attempted_at=attempted_at)
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
        action=complete_action,
        actor="weekly-report-worker",
        reason=job.get("reason"),
        result=final_status,
        source="weekly_report_lambda",
        metadata=fields,
    )
    return {"status": final_status, "job_id": job_id, **fields}


def cancel_resend_job(job_id: str, *, operator: str) -> dict[str, Any]:
    return cancel_recovery_job(job_id, operator=operator)


def cancel_recovery_job(job_id: str, *, operator: str) -> dict[str, Any]:
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


def _execute_generation_retry_target(job: dict, target: dict, *, attempted_at: str) -> str:
    report = report_repo.get_report_for_child_by_week(
        target["parent_id"],
        target["student_id"],
        target["week_start"],
    )
    if not report:
        _finish_target(job, target, "not_found", detail="Report not found")
        return "not_found"
    try:
        result = report_recovery_service.retry_report_generation(
            report,
            parent_id=str(target["parent_id"]),
            student_id=str(target["student_id"]),
            week_start=str(target["week_start"]),
            operator=str(job.get("created_by") or "recovery-job"),
            reason=str(job.get("reason") or "recovery_job_retry_generation"),
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
        action=_target_audit_action(str(job.get("job_type") or RESEND_JOB_TYPE)),
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


def _preview_job(
    *,
    job_type: str,
    reason: str,
    operator: str,
    filters: dict[str, Any],
    max_targets: int,
) -> dict[str, Any]:
    if not reason.strip():
        raise RecoveryJobError(422, "Recovery reason is required")
    targets, scanned_pages = _collect_targets(job_type=job_type, filters=filters, max_targets=max_targets)
    eligible = [target for target in targets if target["eligibility"] == "eligible"]
    refused = [target for target in targets if target["eligibility"] != "eligible"]
    token = _encode_preview_token(
        {
            "operation": job_type,
            "filters": _normalized_filters(filters, job_type=job_type),
            "reason": reason,
            "target_ids": [target["target_id"] for target in eligible],
        }
    )
    return {
        "operation": job_type,
        "reason": reason,
        "requested_by": operator,
        "filters": _normalized_filters(filters, job_type=job_type),
        "max_targets": min(max(1, int(max_targets)), MAX_TARGETS),
        "scanned_pages": scanned_pages,
        "eligible_count": len(eligible),
        "refused_count": len(refused),
        "missing_count": 0,
        "sample": targets[:10],
        "preview_token": token,
    }


def _collect_targets(*, job_type: str, filters: dict[str, Any], max_targets: int) -> tuple[list[dict[str, Any]], int]:
    filters = _normalized_filters(filters, job_type=job_type)
    if filters.get("status") != _required_status(job_type):
        raise RecoveryJobError(422, _unsupported_status_detail(job_type))
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
            target = _target_preview(report, job_type=job_type)
            targets.append(target)
            if len(targets) >= max_targets:
                break
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
    return targets, pages


def _collect_resend_targets(*, filters: dict[str, Any], max_targets: int) -> tuple[list[dict[str, Any]], int]:
    return _collect_targets(job_type=RESEND_JOB_TYPE, filters=filters, max_targets=max_targets)


def _get_resumable_source_job(source_job_id: str) -> dict[str, Any]:
    source_job = report_repo.get_recovery_job(source_job_id)
    if not source_job:
        raise RecoveryJobError(404, "Source recovery job not found")
    if str(source_job.get("job_type") or RESEND_JOB_TYPE) not in {RESEND_JOB_TYPE, GENERATION_RETRY_JOB_TYPE}:
        raise RecoveryJobError(422, "Source recovery job type cannot be resumed")
    if source_job.get("status") not in RESUMABLE_SOURCE_STATUSES:
        raise RecoveryJobError(409, "Source recovery job is not terminal")
    return source_job


def _normalized_resume_results(results: list[str] | None) -> list[str]:
    raw = list(results or DEFAULT_RESUME_RESULTS)
    normalized = sorted({str(item) for item in raw if str(item)})
    if not normalized:
        raise RecoveryJobError(422, "At least one resume result filter is required")
    unsupported = [item for item in normalized if item not in RESUMABLE_TARGET_RESULTS]
    if unsupported:
        raise RecoveryJobError(422, f"Unsupported resume result filter: {unsupported[0]}")
    return normalized


def _collect_resume_targets(
    source_job_id: str,
    *,
    result_filters: list[str],
    max_targets: int,
) -> list[dict[str, Any]]:
    max_targets = min(max(1, int(max_targets)), MAX_TARGETS)
    targets: list[dict[str, Any]] = []
    for target in _list_all_job_targets(source_job_id):
        if target.get("result") not in result_filters:
            continue
        targets.append(_resume_target_preview(target))
        if len(targets) >= max_targets:
            break
    return targets


def _resume_target_preview(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_id": str(target.get("target_id") or uuid4().hex),
        "report_id": target.get("report_id"),
        "parent_id": target.get("parent_id"),
        "student_id": target.get("student_id"),
        "student_name": target.get("student_name"),
        "week_start": target.get("week_start"),
        "status": target.get("status"),
        "email_status": target.get("email_status"),
        "source_result": target.get("result"),
        "detail": report_recovery_service.redact_private_artifact_text(target.get("detail")),
        "error_class": target.get("error_class"),
        "artifacts": {"html_available": False, "json_available": False},
        "eligibility": "eligible",
        "refusal_reason": None,
    }


def _target_snapshot_hash(targets: list[dict[str, Any]]) -> str:
    payload = [
        {
            "target_id": target.get("target_id"),
            "source_result": target.get("source_result"),
            "report_id": target.get("report_id"),
            "parent_id": target.get("parent_id"),
            "student_id": target.get("student_id"),
            "week_start": target.get("week_start"),
        }
        for target in targets
    ]
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _target_preview(report: dict, *, job_type: str = RESEND_JOB_TYPE) -> dict[str, Any]:
    html_available = bool(report.get("html_s3_key") or report.get("s3_key"))
    json_available = bool(report.get("json_s3_key"))
    if job_type == GENERATION_RETRY_JOB_TYPE:
        eligible = report.get("status") == "generation_failed"
        refusal_reason = "Report is not in generation_failed state"
    else:
        email_available = bool(report.get("parent_email"))
        eligible = (
            report.get("status") == "email_failed" or report.get("email_status") == "failed"
        ) and html_available and email_available
        refusal_reason = "Report is missing failed delivery state, parent email, or HTML artifact"
    return {
        "target_id": str(report.get("report_id") or uuid4().hex),
        "report_id": report.get("report_id"),
        "parent_id": report.get("parent_id"),
        "student_id": report.get("student_id"),
        "student_name": report.get("student_name"),
        "week_start": report.get("week_start"),
        "status": report.get("status"),
        "email_status": report.get("email_status"),
        "artifacts": {"html_available": html_available, "json_available": json_available},
        "eligibility": "eligible" if eligible else "refused",
        "refusal_reason": None if eligible else refusal_reason,
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


def _cancel_job(job: dict, reason: str, cancelled_at: str, *, complete_action: str = "complete_resend_job") -> dict[str, Any]:
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
        action=complete_action,
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


def _normalized_filters(filters: dict[str, Any], *, job_type: str = RESEND_JOB_TYPE) -> dict[str, Any]:
    return {
        "status": filters.get("status") or _required_status(job_type),
        "week_start": filters.get("week_start"),
        "parent_id": filters.get("parent_id"),
        "student_id": filters.get("student_id"),
    }


def _required_status(job_type: str) -> str:
    if job_type == GENERATION_RETRY_JOB_TYPE:
        return "generation_failed"
    return "email_failed"


def _unsupported_status_detail(job_type: str) -> str:
    if job_type == GENERATION_RETRY_JOB_TYPE:
        return "Only generation_failed retry recovery is supported"
    return "Only email_failed resend recovery is supported"


def _worker_event_name(job_type: str) -> str:
    if job_type == GENERATION_RETRY_JOB_TYPE:
        return "report_recovery_retry_generation"
    return "report_recovery_resend_email"


def _target_audit_action(job_type: str) -> str:
    if job_type == GENERATION_RETRY_JOB_TYPE:
        return "retry_generation_target"
    return "resend_target"


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
