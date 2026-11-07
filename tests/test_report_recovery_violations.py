"""Report recovery refuses with codes, and job results record them (#285)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

import pytest

from actor_helpers import install_actor_overrides
from rule_violation_helpers import assert_violation
from stoa.db.repositories import report_repo
from stoa.main import RequestLocaleMiddleware
from stoa.routers import admin
from stoa.services import report_recovery_job_service
from stoa.services.report_recovery_errors import (
    ReportRecoveryError,
    ReportRecoveryErrorCode,
)

ADMIN = {"sub": "admin-sub", "role": "admin"}
PRIVATE_KEY = "weekly-reports/private/report.html"


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestLocaleMiddleware)
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, ADMIN)
    return TestClient(app)


def _job(**fields) -> dict:
    return {
        "job_id": "job-1",
        "job_type": "retry_generation",
        "status": "running",
        "reason": "incident",
        "created_by": "admin-sub",
        "target_count": Decimal(1),
        "failure_threshold": Decimal(5),
        **fields,
    }


def _target(**fields) -> dict:
    return {
        "PK": "REPORT_RECOVERY_JOB#job-1",
        "SK": "TARGET#00000#report-1",
        "target_id": "report-1",
        "report_id": "report-1",
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "result": "pending",
        **fields,
    }


def _record_target_writes(monkeypatch) -> tuple[list, list]:
    writes: list = []
    audits: list = []
    monkeypatch.setattr(
        report_repo,
        "update_recovery_job_target",
        lambda job_id, target_sk, result, **fields: writes.append((result, fields)),
    )
    monkeypatch.setattr(
        report_repo,
        "put_recovery_job_audit_event",
        lambda job_id, event: audits.append(event),
    )
    return writes, audits


# ── what a job's target result records ───────────────────────────────────────


def test_a_refused_target_records_the_code_beside_the_english_detail(monkeypatch):
    writes, audits = _record_target_writes(monkeypatch)
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda *args: {"report_id": "report-1", "status": "generated"},
    )

    def refuse(*args, **kwargs):
        raise ReportRecoveryError(
            ReportRecoveryErrorCode.REPORT_GENERATION_NOT_FAILED,
            result="refused",
            internal_detail=f"failed at {PRIVATE_KEY}",
        )

    monkeypatch.setattr(
        report_recovery_job_service.report_recovery_service, "retry_report_generation", refuse
    )

    outcome = report_recovery_job_service._execute_generation_retry_target(
        _job(), _target(), attempted_at="2026-06-05T10:00:00+00:00"
    )

    assert outcome == "refused"
    result, fields = writes[0]
    assert result == "refused"
    assert fields["code"] == "report_generation_not_failed"
    assert fields["params"] == {}
    assert fields["detail"] == "This report's generation has not failed, so there is nothing to retry."
    assert audits[0]["metadata"]["code"] == "report_generation_not_failed"
    assert "weekly-reports/" not in str(writes) + str(audits)


def test_a_failed_target_records_the_failure_code(monkeypatch):
    writes, _ = _record_target_writes(monkeypatch)
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda *args: {"report_id": "report-1", "status": "generation_failed"},
    )

    def fail(*args, **kwargs):
        raise ReportRecoveryError(
            ReportRecoveryErrorCode.REPORT_GENERATION_RETRY_FAILED, error_class="RuntimeError"
        )

    monkeypatch.setattr(
        report_recovery_job_service.report_recovery_service, "retry_report_generation", fail
    )

    outcome = report_recovery_job_service._execute_generation_retry_target(
        _job(), _target(), attempted_at="2026-06-05T10:00:00+00:00"
    )

    assert outcome == "failed"
    assert writes[0][1]["code"] == "report_generation_retry_failed"
    assert writes[0][1]["error_class"] == "RuntimeError"


def test_a_missing_report_records_report_not_found(monkeypatch):
    writes, _ = _record_target_writes(monkeypatch)
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda *args: None)

    outcome = report_recovery_job_service._execute_generation_retry_target(
        _job(), _target(), attempted_at="2026-06-05T10:00:00+00:00"
    )

    assert outcome == "not_found"
    assert writes[0][1]["code"] == "report_not_found"
    assert writes[0][1]["detail"] == "This report was not found."


def test_a_cancelled_job_records_the_cancellation_on_each_pending_target(monkeypatch):
    writes, _ = _record_target_writes(monkeypatch)
    monkeypatch.setattr(
        report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": [_target()]}
    )
    monkeypatch.setattr(report_repo, "update_recovery_job_status", lambda *args, **kwargs: None)

    report_recovery_job_service._cancel_job(_job(), "cancelled_before_start", "2026-06-05T10:00:00+00:00")

    result, fields = writes[0]
    assert result == "skipped_cancelled"
    assert fields["code"] == "recovery_target_cancelled"
    assert fields["detail"] == "The job was cancelled before this report was attempted."


# ── what the console reads back ──────────────────────────────────────────────


def test_results_render_a_coded_outcome_in_the_readers_language_and_keep_old_ones(monkeypatch):
    coded = _target(
        result="refused",
        code="report_generation_not_failed",
        params={},
        detail="This report's generation has not failed, so there is nothing to retry.",
    )
    legacy = _target(
        SK="TARGET#00001#report-2",
        target_id="report-2",
        result="failed",
        detail=f"Report generation retry failed at {PRIVATE_KEY}",
    )
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: _job(status="completed"))
    monkeypatch.setattr(
        report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": [coded, legacy]}
    )

    response = _client().get(
        "/admin/reports/recovery-jobs/job-1/results", headers={"Accept-Language": "fr"}
    )

    assert response.status_code == 200, response.text
    first, second = response.json()["items"]
    assert first["code"] == "report_generation_not_failed"
    assert first["params"] == {}
    assert first["detail"] == "La génération de ce rapport n'a pas échoué : il n'y a rien à relancer."
    assert second["code"] is None
    assert second["detail"] == "Report generation retry failed at [report-artifact-key]"


# ── refusals ─────────────────────────────────────────────────────────────────


def test_an_unsupported_resume_filter_is_named_without_private_artifact_text(monkeypatch):
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: _job(status="completed"))
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda *args, **kwargs: {"Items": []})

    response = _client().post(
        "/admin/reports/recovery-jobs/job-1/resume/preview",
        json={"reason": "resume", "results": [PRIVATE_KEY]},
        headers={"Accept-Language": "en"},
    )

    detail = assert_violation(response, ReportRecoveryErrorCode.RESUME_RESULT_FILTER_UNSUPPORTED)
    assert detail["message"] == "Targets with the result [report-artifact-key] cannot be resumed."
    assert "weekly-reports/" not in response.text


def test_cancelling_an_unknown_job_is_recovery_job_not_found(monkeypatch):
    # Through the route, authorization answers first (`resource_not_found`);
    # the service's own refusal covers a job that vanished in between.
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: None)

    with pytest.raises(report_recovery_job_service.RecoveryJobError) as refused:
        report_recovery_job_service.cancel_recovery_job("job-missing", operator="admin-sub")

    assert refused.value.code is ReportRecoveryErrorCode.RECOVERY_JOB_NOT_FOUND
    assert refused.value.status_code == 404


def test_cancelling_a_finished_job_is_refused(monkeypatch):
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: _job(status="completed"))

    response = _client().post("/admin/reports/recovery-jobs/job-1/cancel")

    assert_violation(response, ReportRecoveryErrorCode.RECOVERY_JOB_ALREADY_TERMINAL)


def test_a_preview_without_a_reason_is_refused(monkeypatch):
    monkeypatch.setattr(report_repo, "list_reports_for_admin", lambda **kwargs: {"Items": []})

    response = _client().post(
        "/admin/reports/recovery-jobs/resend-email/preview",
        json={"reason": "   ", "filters": {"status": "email_failed"}},
    )

    assert_violation(response, ReportRecoveryErrorCode.RECOVERY_REASON_REQUIRED)
