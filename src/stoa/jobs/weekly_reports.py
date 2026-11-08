"""Weekly report scheduled Lambda entrypoint."""

from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any
from zoneinfo import ZoneInfo

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, report_repo
from stoa.services import (
    current_relationship,
    report_artifact_service,
    report_recovery_job_service,
    report_service,
)

logger = logging.getLogger(__name__)

ZURICH_TZ = ZoneInfo("Europe/Zurich")
SKIPPED_STATUSES = {"generated", "email_sent", "email_failed"}


def _increment_count(counts: dict[str, object], field: str) -> None:
    value = counts.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"weekly report count is invalid: {field}")
    counts[field] = value + 1


def _positive_fence_generation(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RuntimeError("weekly report account fence generation is invalid")
    return value


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for the scheduled weekly report job."""
    event = event or {}
    if event.get("job") == "report_artifact_s3_smoke":
        return report_artifact_service.run_report_artifact_s3_smoke(event)
    if event.get("job") == "report_recovery_resend_email":
        job_id = str(event.get("job_id") or "")
        if not job_id:
            return {"status": "failed", "detail": "job_id is required"}
        return report_recovery_job_service.execute_resend_job(job_id, context=context)
    if event.get("job") == "report_recovery_retry_generation":
        job_id = str(event.get("job_id") or "")
        if not job_id:
            return {"status": "failed", "detail": "job_id is required"}
        return report_recovery_job_service.execute_generation_retry_job(job_id, context=context)
    if str(event.get("job", "")).startswith("report_recovery_"):
        return {"status": "failed", "detail": "Unsupported report recovery job"}
    return run_weekly_report_job(event)


def run_weekly_report_job(event: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    """Run weekly report generation for eligible parent/student pairs."""
    event = event or {}
    week_start = target_week_start_from_event(event, now=now)
    pairs = eligible_parent_student_pairs()
    counts = {
        "status": "completed",
        "week_start": week_start,
        "attempted": 0,
        "generated": 0,
        "skipped_existing": 0,
        "email_sent": 0,
        "failed": 0,
    }

    for pair in pairs:
        parent_id = pair["parent_id"]
        student_id = pair["student_id"]
        existing = report_repo.get_report_for_child_by_week(parent_id, student_id, week_start)
        if existing and existing.get("status") in SKIPPED_STATUSES:
            _increment_count(counts, "skipped_existing")
            if existing.get("status") == "email_failed":
                _increment_count(counts, "failed")
            continue

        claim = report_service.build_weekly_report_claim(parent_id, student_id, week_start)
        fence = account_deletion_repo.require_active_account_fence(student_id)
        claim["account_fence_generation"] = _positive_fence_generation(fence.get("generation"))
        if not report_repo.try_claim_report_generation(claim):
            _increment_count(counts, "skipped_existing")
            continue

        _increment_count(counts, "attempted")
        try:
            payload = report_service.build_weekly_learning_payload(parent_id, student_id, week_start)
            generated_content = report_service.generate_weekly_report_content(payload)
            stored_report = report_service.store_and_send_weekly_report(payload, generated_content)
            _increment_count(counts, "generated")
            if stored_report.get("email_status") == "sent" or stored_report.get("status") == "email_sent":
                _increment_count(counts, "email_sent")
            if stored_report.get("status") == "email_failed":
                _increment_count(counts, "failed")
        except Exception as exc:
            _increment_count(counts, "failed")
            failed_at = datetime.now(timezone.utc).isoformat()
            report_repo.update_report_status(
                claim["report_id"],
                "generation_failed",
                generation_failed_at=failed_at,
                generation_error_class=type(exc).__name__,
                generation_error_message=str(exc)[:240],
                updated_at=failed_at,
            )
            # Without the traceback the stored error class names a repository
            # conflict without saying which write raised it.
            logger.warning(
                "Weekly report pair failed parent_id=%s student_id=%s week_start=%s error_class=%s",
                parent_id,
                student_id,
                week_start,
                type(exc).__name__,
                exc_info=exc,
            )

    return counts


def target_week_start_from_event(event: dict[str, Any], *, now: datetime | None = None) -> str:
    """Return explicit or previous Zurich calendar week start as ISO date."""
    explicit = event.get("week_start") or event.get("weekStart")
    if explicit:
        return date.fromisoformat(str(explicit)).isoformat()

    event_time = event.get("time")
    if event_time:
        parsed = datetime.fromisoformat(str(event_time).replace("Z", "+00:00"))
        return previous_zurich_week_start(parsed).isoformat()
    return previous_zurich_week_start(now).isoformat()


def previous_zurich_week_start(now: datetime | None = None) -> date:
    """Return Monday of the previous Zurich calendar week."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    zurich_now = current.astimezone(ZURICH_TZ)
    this_week_start = zurich_now.date() - timedelta(days=zurich_now.weekday())
    return this_week_start - timedelta(days=7)


def eligible_parent_student_pairs() -> list[dict[str, str]]:
    """Discovered candidates narrowed to relationships that are valid right now."""
    return [
        pair
        for pair in discover_linked_parent_student_pairs()
        if current_relationship.judge(pair["parent_id"], pair["student_id"]).is_current
    ]


def discover_linked_parent_student_pairs() -> list[dict[str, str]]:
    """Candidate pairs from the link rows; `eligible_parent_student_pairs` judges them."""
    return [
        {"parent_id": parent_id, "student_id": student_id}
        for parent_id, student_id in current_relationship.candidate_pairs(table=db_table.table())
    ]


