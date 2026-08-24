
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings, get_settings
from stoa.db.repositories import report_repo
from stoa.routers import admin
from stoa.security import admin_authorization
from stoa.services import report_recovery_job_service
from stoa.services import report_recovery_service
from actor_helpers import install_actor_overrides


def _app_for_user(user: dict, settings: Settings | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, user)
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    return app


def _report(status: str = "email_failed", email_status: str = "failed") -> dict:
    return {
        "report_id": "report-parent-1-student-1-2026-06-01",
        "parent_id": "parent-1",
        "student_id": "student-1",
        "student_name": "Student",
        "parent_email": "parent@example.com",
        "week_start": "2026-06-01",
        "status": status,
        "email_status": email_status,
        "html_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/report.html",
        "json_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/report.json",
        "generation_failed_at": "2026-06-04T09:00:00+00:00" if status == "generation_failed" else None,
        "generation_error_class": "RuntimeError" if status == "generation_failed" else None,
        "generation_error_message": "bedrock failed" if status == "generation_failed" else None,
        "email_failed_at": "2026-06-04T10:00:00+00:00",
        "email_error_class": "MessageRejected",
        "email_error_message": "bad address",
    }


def _assert_no_private_artifact_markers(data):
    serialized = str(data)
    assert "<html" not in serialized
    assert "weekly-reports/" not in serialized
    assert "json_s3_key" not in serialized
    assert "html_s3_key" not in serialized
    assert "s3_key" not in serialized
    assert "presignedUrl" not in serialized
    assert "presigned_url" not in serialized
    assert "https://s3" not in serialized
    assert "access_token" not in serialized
    assert "id_token" not in serialized
    assert "refresh_token" not in serialized
    assert "authorization" not in serialized.lower()
    assert "cookie" not in serialized.lower()


def _report_json_artifact() -> dict:
    return {
        "report": {
            "reportId": "report-parent-1-student-1-2026-06-01",
            "parentId": "parent-1",
            "studentId": "student-1",
            "studentName": "Student",
            "weekStart": "2026-06-01",
            "weekEnd": "2026-06-07",
            "generatedAt": "2026-06-01T08:00:00+00:00",
            "status": "email_sent",
            "emailStatus": "sent",
        },
        "stats": {},
        "content": {
            "summary": "Original summary",
            "strengths": ["Original strength"],
            "weakTopics": [{"topic": "fractions", "note": "Review this."}],
            "recommendations": ["Original recommendation"],
            "teacherNote": None,
        },
        "sourceCounts": {},
        "activities": [],
    }


@pytest.fixture(autouse=True)
def _fenced_report_recovery_compat(monkeypatch):
    monkeypatch.setattr(
        report_recovery_service.account_deletion_repo,
        "require_active_account_fence",
        lambda _owner: {"status": "active", "generation": 7},
    )
    monkeypatch.setattr(
        report_recovery_service.notify_service,
        "send_fenced_weekly_report_email",
        lambda parent_email, report_html, **kwargs: (
            report_recovery_service.notify_service.send_weekly_report_email(
                parent_email,
                report_html,
                subject=kwargs.get("subject"),
            )
            or "accepted"
        ),
    )


@pytest.fixture(autouse=True)
def audit_events(monkeypatch):
    events = []
    monkeypatch.setattr(
        report_repo,
        "put_report_audit_event",
        lambda report_id, event: events.append((report_id, event)),
    )
    return events


def test_report_ops_metadata_is_admin_only(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(),
    )
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.get("/admin/reports/parent-1/student-1/2026-06-01/ops")

    assert response.status_code == 403


def test_report_ops_metadata_exposes_status_without_raw_content_or_urls(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/parent-1/student-1/2026-06-01/ops")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "email_failed"
    assert data["email_status"] == "failed"
    assert data["generation"] == {
        "generated_at": None,
        "generation_failed_at": None,
        "generation_error_class": None,
        "generation_error_message": None,
    }
    assert data["artifacts"] == {"json_available": True, "html_available": True}
    assert data["actions"]["resend_email"]["enabled"] is True
    assert data["actions"]["retry_generation"]["enabled"] is False
    serialized = str(data)
    assert "<html" not in serialized
    assert "artifact_keys" not in data
    assert "json_s3_key" not in serialized
    assert "html_s3_key" not in serialized
    assert "s3_key" not in serialized
    assert "weekly-reports/" not in serialized
    assert "publicUrl" not in serialized
    assert "presignedUrl" not in serialized
    assert "https://s3" not in serialized


def test_report_ops_metadata_exposes_generation_retry_eligibility(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(status="generation_failed", email_status="not_sent"),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/parent-1/student-1/2026-06-01/ops")

    assert response.status_code == 200
    data = response.json()
    assert data["generation"]["generation_error_class"] == "RuntimeError"
    assert data["generation"]["generation_error_message"] == "bedrock failed"
    assert data["actions"]["retry_generation"] == {"enabled": True, "reason": None}
    assert data["actions"]["resend_email"]["enabled"] is False


def test_report_ops_list_is_admin_only(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "list_reports_for_admin",
        lambda **kwargs: {"Items": [_report()]},
    )
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.get("/admin/reports/ops")

    assert response.status_code == 403


def test_report_ops_list_returns_metadata_filters_and_next_token(monkeypatch):
    calls = []

    monkeypatch.setattr(report_repo, "decode_admin_page_token", lambda token: {"PK": "PRACTICE", "SK": "CHALLENGE#prev"})
    monkeypatch.setattr(report_repo, "encode_admin_page_token", lambda key: "encoded-next" if key else None)

    def list_reports_for_admin(**kwargs):
        calls.append(kwargs)
        return {"Items": [_report(status="generation_failed", email_status="not_sent")], "LastEvaluatedKey": {"PK": "REPORT#next"}}

    monkeypatch.setattr(report_repo, "list_reports_for_admin", list_reports_for_admin)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get(
        "/admin/reports/ops",
        params={
            "status": "generation_failed",
            "week_start": "2026-06-01",
            "parent_id": "parent-1",
            "student_id": "student-1",
            "limit": 10,
            "next_token": "encoded-prev",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["next_token"] == "encoded-next"
    assert data["access_pattern"] == "parent_gsi"
    assert data["items"][0]["status"] == "generation_failed"
    assert data["items"][0]["generation"]["generation_error_class"] == "RuntimeError"
    assert calls == [
        {
            "status": "generation_failed",
            "week_start": "2026-06-01",
            "parent_id": "parent-1",
            "student_id": "student-1",
            "limit": 10,
            "last_key": {"PK": "PRACTICE", "SK": "CHALLENGE#prev"},
        }
    ]
    serialized = str(data)
    assert "<html" not in serialized
    assert "json_s3_key" not in serialized
    assert "html_s3_key" not in serialized
    assert "s3_key" not in serialized
    assert "weekly-reports/" not in serialized
    assert "publicUrl" not in serialized
    assert "presignedUrl" not in serialized
    assert "https://s3" not in serialized


def test_report_ops_list_rejects_invalid_pagination_token(monkeypatch):
    monkeypatch.setattr(report_repo, "decode_admin_page_token", lambda token: (_ for _ in ()).throw(ValueError("bad")))
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/ops", params={"next_token": "bad"})

    assert response.status_code == 400


def test_report_ops_list_round_trips_non_report_scan_key_next_token(monkeypatch):
    first_key = {"PK": "PRACTICE", "SK": "CHALLENGE#fractions"}
    calls = []

    def list_reports_for_admin(**kwargs):
        calls.append(kwargs)
        return {"Items": [], "LastEvaluatedKey": first_key}

    monkeypatch.setattr(report_repo, "list_reports_for_admin", list_reports_for_admin)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/ops", params={"limit": 5})

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["count"] == 0
    assert report_repo.decode_admin_page_token(data["next_token"]) == first_key
    assert calls == [
        {
            "status": None,
            "week_start": None,
            "parent_id": None,
            "student_id": None,
            "limit": 5,
            "last_key": None,
        }
    ]


def test_resend_failed_report_uses_existing_html_artifact_and_audits(monkeypatch, audit_events):
    updates = []
    sent = []

    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(),
    )
    monkeypatch.setattr(
        report_recovery_service.report_artifact_service,
        "get_report_html",
        lambda key: "<html>Report</html>",
    )
    monkeypatch.setattr(
        report_recovery_service.notify_service,
        "send_weekly_report_email",
        lambda email, html, **kwargs: sent.append((email, html, kwargs.get("subject"))),
    )
    monkeypatch.setattr(
        report_repo,
        "update_report_status",
        lambda report_id, status, **fields: updates.append((report_id, status, fields)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/resend")

    assert response.status_code == 200
    assert sent == [("parent@example.com", "<html>Report</html>", "STOA weekly report for Student")]
    assert updates[0][1] == "email_sent"
    assert updates[0][2]["email_status"] == "sent"
    assert updates[0][2]["last_operation"] == "resend_email"
    assert updates[0][2]["last_operation_by"] == "admin-sub"
    assert updates[0][2]["last_operation_result"] == "success"
    assert response.json()["operation_result"] == "success"
    assert audit_events[0][0] == _report()["report_id"]
    event = audit_events[0][1]
    assert event["action"] == "resend_email"
    assert event["result"] == "success"
    assert event["actor"] == "admin-sub"
    assert event["before"]["status"] == "email_failed"
    assert event["after"]["status"] == "email_sent"
    assert "weekly-reports/" not in str(event)


def test_resend_failed_report_is_admin_only(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(),
    )

    def fail(*args, **kwargs):
        raise AssertionError("resend pipeline should not run")

    monkeypatch.setattr(report_recovery_service.report_artifact_service, "get_report_html", fail)
    monkeypatch.setattr(report_recovery_service.notify_service, "send_weekly_report_email", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/resend")

    assert response.status_code == 403


def test_resend_refuses_non_failed_report(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(status="email_sent", email_status="sent"),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/resend")

    assert response.status_code == 409


def test_bulk_resend_is_admin_only(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("bulk resend should not query reports")

    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.post(
        "/admin/reports/bulk-resend",
        json={"reports": [{"parent_id": "parent-1", "student_id": "student-1", "week_start": "2026-06-01"}]},
    )

    assert response.status_code == 403


def test_bulk_resend_enforces_batch_size(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("oversized bulk resend should not query reports")

    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/bulk-resend",
        json={
            "reports": [
                {"parent_id": "parent-1", "student_id": f"student-{index}", "week_start": "2026-06-01"}
                for index in range(26)
            ]
        },
    )

    assert response.status_code == 422


def test_bulk_resend_returns_mixed_results_and_continues(monkeypatch):
    updates = []
    sent = []
    html_reads = []

    success = {
        **_report(),
        "student_id": "student-success",
        "report_id": "report-success",
        "html_s3_key": "weekly-reports/parent-1/student-success/2026-06-01/report.html",
    }
    refused = {
        **_report(status="email_sent", email_status="sent"),
        "student_id": "student-refused",
        "report_id": "report-refused",
    }
    failed = {
        **_report(),
        "student_id": "student-failed",
        "report_id": "report-failed",
        "parent_email": "fail@example.com",
        "html_s3_key": "weekly-reports/parent-1/student-failed/2026-06-01/report.html",
    }
    reports = {
        "student-success": success,
        "student-refused": refused,
        "student-failed": failed,
    }

    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: reports.get(student_id),
    )

    def get_html(key):
        html_reads.append(key)
        return "<html>Report</html>"

    def send_email(email, html, **kwargs):
        sent.append((email, html, kwargs.get("subject")))
        if email == "fail@example.com":
            raise RuntimeError("SES failed weekly-reports/private/report.html")

    monkeypatch.setattr(report_recovery_service.report_artifact_service, "get_report_html", get_html)
    monkeypatch.setattr(report_recovery_service.notify_service, "send_weekly_report_email", send_email)
    monkeypatch.setattr(
        report_repo,
        "update_report_status",
        lambda report_id, status, **fields: updates.append((report_id, status, fields)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/bulk-resend",
        json={
            "reports": [
                {"parent_id": "parent-1", "student_id": "student-success", "week_start": "2026-06-01"},
                {"parent_id": "parent-1", "student_id": "student-refused", "week_start": "2026-06-01"},
                {"parent_id": "parent-1", "student_id": "student-missing", "week_start": "2026-06-01"},
                {"parent_id": "parent-1", "student_id": "student-failed", "week_start": "2026-06-01"},
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "bulk_resend_email"
    assert data["count"] == 4
    assert [item["result"] for item in data["results"]] == ["success", "refused", "not_found", "failed"]
    assert [item["operation_result"] for item in data["results"]] == [
        "success",
        "refused",
        "not_found",
        "failed",
    ]
    assert data["results"][0]["report_id"] == "report-success"
    assert data["results"][2]["detail"] == "Report not found"
    assert sent == [
        ("parent@example.com", "<html>Report</html>", "STOA weekly report for Student"),
        ("fail@example.com", "<html>Report</html>", "STOA weekly report for Student"),
    ]
    assert html_reads == [
        "weekly-reports/parent-1/student-success/2026-06-01/report.html",
        "weekly-reports/parent-1/student-failed/2026-06-01/report.html",
    ]
    assert [(update[0], update[1], update[2]["last_operation_result"]) for update in updates] == [
        ("report-success", "email_sent", "success"),
        ("report-failed", "email_failed", "failed"),
    ]
    assert updates[0][2]["last_operation_by"] == "admin-sub"
    assert updates[1][2]["email_error_message"] == "SES failed [report-artifact-key]"
    serialized = str(data)
    assert "<html" not in serialized
    assert "weekly-reports/" not in serialized
    assert "json_s3_key" not in serialized
    assert "html_s3_key" not in serialized
    assert "presignedUrl" not in serialized
    assert "https://s3" not in serialized


def test_retry_generation_failed_report_runs_single_report_pipeline_and_audits(monkeypatch, audit_events):
    updates = []
    calls = []
    report = _report(status="generation_failed", email_status="not_sent")

    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: report,
    )

    def build_payload(parent_id, student_id, week_start):
        calls.append(("payload", parent_id, student_id, week_start))
        return {"parent": {"id": parent_id}, "student": {"id": student_id}, "week": {"start": week_start}}

    def generate(payload):
        calls.append(("generate", payload["student"]["id"]))
        return {"summary": "ok"}

    def store(payload, generated_content):
        calls.append(("store", payload["parent"]["id"], payload["student"]["id"], payload["week"]["start"]))
        return {
            **report,
            "status": "email_sent",
            "email_status": "sent",
            "report_id": report["report_id"],
        }

    monkeypatch.setattr(report_recovery_service.report_service, "build_weekly_learning_payload", build_payload)
    monkeypatch.setattr(report_recovery_service.report_service, "generate_weekly_report_content", generate)
    monkeypatch.setattr(report_recovery_service.report_service, "store_and_send_weekly_report", store)
    monkeypatch.setattr(report_repo, "try_start_generation_retry", lambda report_id, **kwargs: True)
    monkeypatch.setattr(
        report_repo,
        "update_report_status",
        lambda report_id, status, **fields: updates.append((report_id, status, fields)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/retry-generation")

    assert response.status_code == 200
    assert calls == [
        ("payload", "parent-1", "student-1", "2026-06-01"),
        ("generate", "student-1"),
        ("store", "parent-1", "student-1", "2026-06-01"),
    ]
    assert updates[0][0] == report["report_id"]
    assert updates[0][1] == "email_sent"
    assert updates[0][2]["email_status"] == "sent"
    assert updates[0][2]["last_operation"] == "retry_generation"
    assert updates[0][2]["last_operation_by"] == "admin-sub"
    assert updates[0][2]["last_operation_result"] == "success"
    assert updates[0][2]["generation_retry_attempted_at"]
    assert updates[0][2]["generation_retry_completed_at"]
    data = response.json()
    assert data["operation_result"] == "success"
    assert data["artifacts"] == {"json_available": True, "html_available": True}
    assert audit_events[0][0] == report["report_id"]
    event = audit_events[0][1]
    assert event["action"] == "retry_generation"
    assert event["result"] == "success"
    assert event["actor"] == "admin-sub"
    assert "weekly-reports/" not in str(event)
    serialized = str(data)
    assert "json_s3_key" not in serialized
    assert "html_s3_key" not in serialized
    assert "weekly-reports/" not in serialized


def test_retry_generation_is_admin_only(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(status="generation_failed", email_status="not_sent"),
    )

    def fail(*args, **kwargs):
        raise AssertionError("retry pipeline should not run")

    monkeypatch.setattr(report_repo, "try_start_generation_retry", fail)
    monkeypatch.setattr(report_recovery_service.report_service, "build_weekly_learning_payload", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/retry-generation")

    assert response.status_code == 403


def test_retry_generation_refuses_when_atomic_claim_fails(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(status="generation_failed", email_status="not_sent"),
    )
    monkeypatch.setattr(report_repo, "try_start_generation_retry", lambda report_id, **kwargs: False)

    def fail(*args, **kwargs):
        raise AssertionError("retry pipeline should not run")

    monkeypatch.setattr(report_recovery_service.report_service, "build_weekly_learning_payload", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/retry-generation")

    assert response.status_code == 409


@pytest.mark.parametrize(
    ("status", "email_status"),
    [
        ("generated", "pending"),
        ("email_sent", "sent"),
        ("email_failed", "failed"),
        ("generation_claimed", "not_started"),
    ],
)
def test_retry_generation_refuses_non_generation_failed_report(monkeypatch, status, email_status):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(status=status, email_status=email_status),
    )

    def fail(*args, **kwargs):
        raise AssertionError("retry pipeline should not run")

    monkeypatch.setattr(report_recovery_service.report_service, "build_weekly_learning_payload", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/retry-generation")

    assert response.status_code == 409


def test_retry_generation_failure_preserves_failed_status_and_audits(monkeypatch, audit_events):
    updates = []
    report = _report(status="generation_failed", email_status="not_sent")
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: report,
    )
    monkeypatch.setattr(
        report_recovery_service.report_service,
        "build_weekly_learning_payload",
        lambda parent_id, student_id, week_start: (_ for _ in ()).throw(RuntimeError("bad generation")),
    )
    monkeypatch.setattr(
        report_repo,
        "update_report_status",
        lambda report_id, status, **fields: updates.append((report_id, status, fields)),
    )
    monkeypatch.setattr(report_repo, "try_start_generation_retry", lambda report_id, **kwargs: True)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/retry-generation")

    assert response.status_code == 502
    assert updates[0][0] == report["report_id"]
    assert updates[0][1] == "generation_failed"
    assert updates[0][2]["generation_error_class"] == "RuntimeError"
    assert updates[0][2]["generation_error_message"] == "bad generation"
    assert updates[0][2]["last_operation"] == "retry_generation"
    assert updates[0][2]["last_operation_by"] == "admin-sub"
    assert updates[0][2]["last_operation_result"] == "failed"
    assert updates[0][2]["generation_retry_attempted_at"]
    event = audit_events[0][1]
    assert event["action"] == "retry_generation"
    assert event["result"] == "failed"
    assert event["error_class"] == "RuntimeError"
    assert event["error_message"] == "bad generation"


def test_retry_generation_failure_redacts_private_artifact_keys(monkeypatch):
    updates = []
    report = _report(status="generation_failed", email_status="not_sent")
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: report,
    )
    monkeypatch.setattr(report_repo, "try_start_generation_retry", lambda report_id, **kwargs: True)
    monkeypatch.setattr(
        report_recovery_service.report_service,
        "build_weekly_learning_payload",
        lambda parent_id, student_id, week_start: {
            "parent": {"id": parent_id},
            "student": {"id": student_id},
            "week": {"start": week_start},
        },
    )
    monkeypatch.setattr(report_recovery_service.report_service, "generate_weekly_report_content", lambda payload: {"summary": "ok"})
    monkeypatch.setattr(
        report_recovery_service.report_service,
        "store_and_send_weekly_report",
        lambda payload, generated: (_ for _ in ()).throw(
            RuntimeError("failed weekly-reports/parent-1/student-1/2026-06-01/report.html json_s3_key")
        ),
    )
    monkeypatch.setattr(
        report_repo,
        "update_report_status",
        lambda report_id, status, **fields: updates.append((report_id, status, fields)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/retry-generation")

    assert response.status_code == 502
    message = updates[0][2]["generation_error_message"]
    assert "[report-artifact-key]" in message
    assert "[report-artifact-field]" in message
    assert "weekly-reports/" not in message
    assert "json_s3_key" not in message


def test_report_ops_metadata_redacts_persisted_private_artifact_error(monkeypatch):
    report = _report(status="generation_failed", email_status="not_sent")
    report["generation_error_message"] = (
        "failed weekly-reports/parent-1/student-1/2026-06-01/report.html html_s3_key"
    )
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: report,
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/parent-1/student-1/2026-06-01/ops")

    assert response.status_code == 200
    message = response.json()["generation"]["generation_error_message"]
    assert "[report-artifact-key]" in message
    assert "[report-artifact-field]" in message
    serialized = str(response.json())
    assert "weekly-reports/" not in serialized
    assert "html_s3_key" not in serialized


def test_report_audit_timeline_is_admin_only(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(),
    )

    def fail(*args, **kwargs):
        raise AssertionError("audit timeline should not query events")

    monkeypatch.setattr(report_repo, "list_report_audit_events", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.get("/admin/reports/parent-1/student-1/2026-06-01/audit")

    assert response.status_code == 403


def test_report_audit_timeline_returns_metadata_only(monkeypatch):
    calls = []
    next_key = {"PK": "REPORT#report-parent-1-student-1-2026-06-01", "SK": "AUDIT#2026-06-04T10:00:00#next"}
    event = {
        "PK": "REPORT#report-parent-1-student-1-2026-06-01",
        "SK": "AUDIT#2026-06-04T10:00:00#event-1",
        "event_id": "event-1",
        "event_at": "2026-06-04T10:00:00+00:00",
        "report_id": "report-parent-1-student-1-2026-06-01",
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "actor": "admin-sub",
        "action": "resend_email",
        "reason": "admin_single_resend",
        "source": "admin_api",
        "result": "success",
        "before": {
            "status": "email_failed",
            "html_s3_key": "weekly-reports/private/report.html",
        },
        "after": {
            "status": "email_sent",
            "email_error_message": "failed weekly-reports/private/report.html html_s3_key",
        },
        "error_class": None,
        "error_message": "failed weekly-reports/private/report.html html_s3_key",
        "correlation_id": "corr-1",
    }

    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(),
    )

    def list_audit(report_id, **kwargs):
        calls.append((report_id, kwargs))
        return {"Items": [event], "LastEvaluatedKey": next_key}

    monkeypatch.setattr(report_repo, "list_report_audit_events", list_audit)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/parent-1/student-1/2026-06-01/audit", params={"limit": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "report"
    assert data["count"] == 1
    assert report_repo.decode_audit_page_token(data["next_token"]) == next_key
    assert data["items"][0]["action"] == "resend_email"
    assert data["items"][0]["before"] == {"status": "email_failed"}
    assert data["items"][0]["after"]["email_error_message"] == (
        "failed [report-artifact-key] [report-artifact-field]"
    )
    assert calls == [
        (
            "report-parent-1-student-1-2026-06-01",
            {"limit": 10, "last_key": None},
        )
    ]
    serialized = str(data)
    assert "weekly-reports/" not in serialized
    assert "html_s3_key" not in serialized
    assert "json_s3_key" not in serialized
    assert "s3_key" not in serialized


def test_report_audit_timeline_rejects_invalid_token(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/parent-1/student-1/2026-06-01/audit", params={"next_token": "bad"})

    assert response.status_code == 400


def test_recovery_job_audit_timeline_returns_job_scope(monkeypatch):
    calls = []
    monkeypatch.setattr(
        report_repo,
        "get_recovery_job",
        lambda job_id: {"job_id": job_id, "filters": {}},
    )
    monkeypatch.setattr(
        report_repo,
        "list_recovery_job_audit_events",
        lambda job_id, **kwargs: calls.append((job_id, kwargs)) or {"Items": []},
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/recovery-jobs/job-1/audit", params={"limit": 5})

    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0, "next_token": None, "scope": "recovery_job"}
    assert calls == [("job-1", {"limit": 5, "last_key": None})]


def test_resend_recovery_job_preview_is_admin_only(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("preview should not query reports")

    monkeypatch.setattr(report_repo, "list_reports_for_admin", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.post(
        "/admin/reports/recovery-jobs/resend-email/preview",
        json={"reason": "incident resend", "filters": {"status": "email_failed"}},
    )

    assert response.status_code == 403


def test_resend_recovery_job_preview_returns_metadata_only(monkeypatch):
    calls = []
    original_authorize_admin_refs = admin_authorization._authorize_admin_refs

    def list_reports_for_admin(**kwargs):
        calls.append(("target_read", kwargs))
        return {"Items": [_report()]}

    async def authorize_admin_refs(**kwargs):
        calls.append(("authorize", tuple(ref.resource_id for ref in kwargs["refs"])))
        return await original_authorize_admin_refs(**kwargs)

    monkeypatch.setattr(report_repo, "list_reports_for_admin", list_reports_for_admin)
    monkeypatch.setattr(admin_authorization, "_authorize_admin_refs", authorize_admin_refs)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/recovery-jobs/resend-email/preview",
        json={
            "reason": "incident resend",
            "filters": {"status": "email_failed", "week_start": "2026-06-01"},
            "max_targets": 5,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "resend_email"
    assert data["eligible_count"] == 1
    assert data["refused_count"] == 0
    assert data["sample"][0]["artifacts"] == {"html_available": True, "json_available": True}
    assert data["preview_token"]
    expected_read = {
        "status": "email_failed",
        "week_start": "2026-06-01",
        "parent_id": None,
        "student_id": None,
        "limit": 5,
        "last_key": None,
    }
    assert calls == [
        ("target_read", expected_read),
        (
            "authorize",
            (
                "v1|9:parent_id8:parent-110:student_id9:student-110:week_start10:2026-06-019:report_id36:report-parent-1-student-1-2026-06-01",
            ),
        ),
        ("target_read", expected_read),
    ]
    serialized = str(data)
    assert "weekly-reports/" not in serialized
    assert "html_s3_key" not in serialized
    assert "json_s3_key" not in serialized


def test_create_resend_recovery_job_persists_snapshot_and_invokes_worker(monkeypatch):
    persisted = []
    audits = []
    invoked = []
    monkeypatch.setattr(report_repo, "list_reports_for_admin", lambda **kwargs: {"Items": [_report()]})
    monkeypatch.setattr(report_repo, "put_recovery_job", lambda job, targets: persisted.append((job, targets)))
    monkeypatch.setattr(
        report_repo,
        "put_recovery_job_audit_event",
        lambda job_id, event: audits.append((job_id, event)),
    )
    monkeypatch.setattr(
        report_recovery_job_service,
        "invoke_weekly_report_job",
        lambda job_id, **kwargs: invoked.append((job_id, kwargs.get("job_type"))),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    preview = client.post(
        "/admin/reports/recovery-jobs/resend-email/preview",
        json={"reason": "incident resend", "filters": {"status": "email_failed"}},
    ).json()
    response = client.post(
        "/admin/reports/recovery-jobs/resend-email",
        json={
            "reason": "incident resend",
            "filters": {"status": "email_failed"},
            "preview_token": preview["preview_token"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["target_count"] == 1
    assert persisted[0][0]["created_by"] == "admin-sub"
    assert persisted[0][1][0]["result"] == "pending"
    assert persisted[0][1][0]["parent_id"] == "parent-1"
    assert invoked == [(persisted[0][0]["job_id"], "resend_email")]
    assert audits[0][1]["action"] == "create_resend_job"
    serialized = str(data) + str(persisted)
    assert "weekly-reports/" not in serialized


def test_create_resend_recovery_job_requires_matching_preview(monkeypatch):
    calls = []
    original_authorize_admin_refs = admin_authorization._authorize_admin_refs

    def list_reports_for_admin(**kwargs):
        calls.append("target_read")
        return {"Items": [_report()]}

    async def authorize_admin_refs(**kwargs):
        calls.append("authorize")
        return await original_authorize_admin_refs(**kwargs)

    monkeypatch.setattr(report_repo, "list_reports_for_admin", list_reports_for_admin)
    monkeypatch.setattr(admin_authorization, "_authorize_admin_refs", authorize_admin_refs)
    monkeypatch.setattr(
        report_repo,
        "put_recovery_job",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stale preview must not create a job")),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/recovery-jobs/resend-email",
        json={
            "reason": "incident resend",
            "filters": {"status": "email_failed"},
            "preview_token": "stale",
        },
    )

    assert response.status_code == 409
    assert calls == ["target_read", "authorize", "target_read"]


def test_generation_retry_recovery_job_preview_returns_metadata_only(monkeypatch):
    calls = []

    def list_reports_for_admin(**kwargs):
        calls.append(kwargs)
        return {"Items": [_report(status="generation_failed", email_status="not_sent")]}

    monkeypatch.setattr(report_repo, "list_reports_for_admin", list_reports_for_admin)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/recovery-jobs/retry-generation/preview",
        json={
            "reason": "incident generation retry",
            "filters": {"status": "generation_failed", "week_start": "2026-06-01"},
            "max_targets": 5,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "retry_generation"
    assert data["eligible_count"] == 1
    assert data["refused_count"] == 0
    assert data["sample"][0]["status"] == "generation_failed"
    assert data["sample"][0]["artifacts"] == {"html_available": True, "json_available": True}
    assert data["preview_token"]
    expected_read = {
        "status": "generation_failed",
        "week_start": "2026-06-01",
        "parent_id": None,
        "student_id": None,
        "limit": 5,
        "last_key": None,
    }
    assert calls == [expected_read, expected_read]
    _assert_no_private_artifact_markers(data)


def test_generation_retry_recovery_job_preview_rejects_wrong_status(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("wrong status should be rejected before querying reports")

    monkeypatch.setattr(report_repo, "list_reports_for_admin", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/recovery-jobs/retry-generation/preview",
        json={"reason": "incident generation retry", "filters": {"status": "email_failed"}},
    )

    assert response.status_code == 422


def test_create_generation_retry_recovery_job_persists_snapshot_and_invokes_worker(monkeypatch):
    persisted = []
    audits = []
    invoked = []
    monkeypatch.setattr(
        report_repo,
        "list_reports_for_admin",
        lambda **kwargs: {"Items": [_report(status="generation_failed", email_status="not_sent")]},
    )
    monkeypatch.setattr(report_repo, "put_recovery_job", lambda job, targets: persisted.append((job, targets)))
    monkeypatch.setattr(
        report_repo,
        "put_recovery_job_audit_event",
        lambda job_id, event: audits.append((job_id, event)),
    )
    monkeypatch.setattr(
        report_recovery_job_service,
        "invoke_weekly_report_job",
        lambda job_id, **kwargs: invoked.append((job_id, kwargs.get("job_type"))),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    preview = client.post(
        "/admin/reports/recovery-jobs/retry-generation/preview",
        json={"reason": "incident generation retry", "filters": {"status": "generation_failed"}},
    ).json()
    response = client.post(
        "/admin/reports/recovery-jobs/retry-generation",
        json={
            "reason": "incident generation retry",
            "filters": {"status": "generation_failed"},
            "preview_token": preview["preview_token"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_type"] == "retry_generation"
    assert data["status"] == "queued"
    assert data["target_count"] == 1
    assert persisted[0][0]["created_by"] == "admin-sub"
    assert persisted[0][0]["job_type"] == "retry_generation"
    assert persisted[0][1][0]["result"] == "pending"
    assert persisted[0][1][0]["status"] == "generation_failed"
    assert invoked == [(persisted[0][0]["job_id"], "retry_generation")]
    assert audits[0][1]["action"] == "create_retry_generation_job"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(persisted)


def test_resume_recovery_job_preview_and_create_persist_linked_job(monkeypatch):
    persisted = []
    audits = []
    invoked = []
    source_job = {
        "job_id": "job-source",
        "job_type": "retry_generation",
        "status": "completed_with_failures",
        "reason": "source incident",
        "target_count": 3,
        "failure_threshold": 5,
    }
    source_targets = [
        {
            "SK": "TARGET#00000#target-1",
            "target_id": "target-1",
            "report_id": "report-1",
            "parent_id": "parent-1",
            "student_id": "student-1",
            "student_name": "Student One",
            "week_start": "2026-06-01",
            "status": "generation_failed",
            "email_status": "not_sent",
            "result": "failed",
            "detail": "provider failed weekly-reports/private/report.json",
        },
        {
            "SK": "TARGET#00001#target-2",
            "target_id": "target-2",
            "report_id": "report-2",
            "parent_id": "parent-2",
            "student_id": "student-2",
            "week_start": "2026-06-01",
            "status": "generation_failed",
            "email_status": "not_sent",
            "result": "refused",
        },
        {
            "SK": "TARGET#00002#target-3",
            "target_id": "target-3",
            "report_id": "report-3",
            "parent_id": "parent-3",
            "student_id": "student-3",
            "week_start": "2026-06-01",
            "status": "generated",
            "email_status": "sent",
            "result": "success",
        },
    ]

    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: source_job if job_id == "job-source" else None)
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": source_targets})
    monkeypatch.setattr(report_repo, "put_recovery_job", lambda job, targets: persisted.append((job, targets)))
    monkeypatch.setattr(
        report_repo,
        "put_recovery_job_audit_event",
        lambda job_id, event: audits.append((job_id, event)),
    )
    monkeypatch.setattr(
        report_recovery_job_service,
        "invoke_weekly_report_job",
        lambda job_id, **kwargs: invoked.append((job_id, kwargs.get("job_type"))),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    preview = client.post(
        "/admin/reports/recovery-jobs/job-source/resume/preview",
        json={"reason": "resume failed subset", "results": ["failed", "refused"], "max_targets": 25},
    )
    assert preview.status_code == 200
    preview_data = preview.json()
    assert preview_data["operation"] == "resume_recovery_job"
    assert preview_data["source_job_id"] == "job-source"
    assert preview_data["job_type"] == "retry_generation"
    assert preview_data["eligible_count"] == 2
    assert preview_data["sample"][0]["source_result"] == "failed"

    response = client.post(
        "/admin/reports/recovery-jobs/job-source/resume",
        json={
            "reason": "resume failed subset",
            "results": ["failed", "refused"],
            "preview_token": preview_data["preview_token"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_type"] == "retry_generation"
    assert data["source_job_id"] == "job-source"
    assert data["resume_result_filters"] == ["failed", "refused"]
    assert persisted[0][0]["source_job_id"] == "job-source"
    assert persisted[0][0]["resume_from"] == {"job_id": "job-source", "job_type": "retry_generation"}
    assert [target["result"] for target in persisted[0][1]] == ["pending", "pending"]
    assert [target["source_target_result"] for target in persisted[0][1]] == ["failed", "refused"]
    assert audits[0][0] == "job-source"
    assert audits[0][1]["action"] == "create_resume_job"
    assert audits[1][0] == persisted[0][0]["job_id"]
    assert invoked == [(persisted[0][0]["job_id"], "retry_generation")]
    _assert_no_private_artifact_markers(preview_data)
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(persisted)


def test_resume_recovery_job_rejects_non_terminal_source(monkeypatch):
    calls = []
    original_authorize_admin_refs = admin_authorization._authorize_admin_refs

    def get_recovery_job(job_id):
        calls.append("source_read")
        return {"job_id": job_id, "job_type": "resend_email", "status": "running"}

    async def authorize_admin_refs(**kwargs):
        calls.append("authorize")
        return await original_authorize_admin_refs(**kwargs)

    monkeypatch.setattr(
        report_repo,
        "get_recovery_job",
        get_recovery_job,
    )
    monkeypatch.setattr(admin_authorization, "_authorize_admin_refs", authorize_admin_refs)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/recovery-jobs/job-running/resume/preview",
        json={"reason": "resume failed subset", "results": ["failed"]},
    )

    assert response.status_code == 409
    assert calls == ["source_read", "authorize", "source_read"]


@pytest.mark.parametrize("status", ["stopped_failure_threshold", "stopped_time_floor"])
def test_resume_recovery_job_allows_historical_stopped_source_statuses(monkeypatch, status):
    source_job = {
        "job_id": "job-stopped",
        "job_type": "resend_email",
        "status": status,
        "failure_threshold": 5,
    }
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: source_job if job_id == "job-stopped" else None)
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": []})
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/recovery-jobs/job-stopped/resume/preview",
        json={"reason": "resume after remediation", "results": ["failed"]},
    )

    assert response.status_code == 200
    assert response.json()["job_type"] == "resend_email"


@pytest.mark.parametrize("missing_field", ["job_type", "failure_threshold"])
def test_resume_recovery_job_rejects_incomplete_historical_source_without_mutation(monkeypatch, missing_field):
    source_job = {
        "job_id": "job-incomplete",
        "job_type": "resend_email",
        "status": "stopped_failure_threshold",
        "failure_threshold": 5,
    }
    source_job.pop(missing_field)
    writes = []
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: source_job if job_id == "job-incomplete" else None)
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda *args, **kwargs: {"Items": []})
    monkeypatch.setattr(report_repo, "put_recovery_job", lambda *args, **kwargs: writes.append((args, kwargs)))
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/recovery-jobs/job-incomplete/resume/preview",
        json={"reason": "resume after repair", "results": ["failed"]},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Source recovery job record is incomplete and needs repair"}
    assert writes == []
    assert missing_field not in source_job


def test_create_resume_job_revalidates_source_record_before_mutation(monkeypatch):
    source_job = {
        "job_id": "job-source",
        "job_type": "resend_email",
        "status": "stopped_failure_threshold",
        "failure_threshold": 5,
    }
    source_targets = [{"target_id": "target-1", "result": "failed"}]
    writes = []
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: source_job if job_id == "job-source" else None)
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda *args, **kwargs: {"Items": source_targets})
    monkeypatch.setattr(report_repo, "put_recovery_job", lambda *args, **kwargs: writes.append((args, kwargs)))

    preview = report_recovery_job_service.preview_resume_job(
        source_job_id="job-source",
        reason="resume after remediation",
        operator="admin-sub",
        results=["failed"],
    )
    source_job.pop("failure_threshold")

    with pytest.raises(report_recovery_job_service.RecoveryJobError) as error:
        report_recovery_job_service.create_resume_job(
            source_job_id="job-source",
            reason="resume after remediation",
            operator="admin-sub",
            results=["failed"],
            preview_token=preview["preview_token"],
        )

    assert error.value.status_code == 422
    assert error.value.detail == "Source recovery job record is incomplete and needs repair"
    assert writes == []


def test_recovery_job_list_detail_results_and_cancel(monkeypatch):
    updates = []
    audits = []
    job = {
        "job_id": "job-1",
        "job_type": "resend_email",
        "status": "queued",
        "reason": "incident resend",
        "created_by": "admin-sub",
        "created_at": "2026-06-04T10:00:00+00:00",
        "updated_at": "2026-06-04T10:00:00+00:00",
        "filters": {"status": "email_failed"},
        "target_count": 1,
        "pending_count": 1,
    }
    target = {
        "PK": "REPORT_RECOVERY_JOB#job-1",
        "SK": "TARGET#00000#target-1",
        "target_id": "target-1",
        "report_id": "report-1",
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "result": "pending",
        "detail": "failed weekly-reports/private/report.html html_s3_key",
    }
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: job if job_id == "job-1" else None)
    monkeypatch.setattr(report_repo, "list_recovery_jobs", lambda **kwargs: {"Items": [job]})
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": [target]})
    monkeypatch.setattr(
        report_repo,
        "request_recovery_job_cancellation",
        lambda job_id, **kwargs: updates.append((job_id, kwargs)) or True,
    )
    monkeypatch.setattr(
        report_repo,
        "put_recovery_job_audit_event",
        lambda job_id, event: audits.append((job_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    assert client.get("/admin/reports/recovery-jobs").status_code == 200
    detail = client.get("/admin/reports/recovery-jobs/job-1")
    results = client.get("/admin/reports/recovery-jobs/job-1/results")
    cancel = client.post("/admin/reports/recovery-jobs/job-1/cancel")

    assert detail.status_code == 200
    assert results.status_code == 200
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancellation_requested"
    assert updates[0][0] == "job-1"
    assert audits[0][1]["action"] == "request_cancellation"
    serialized = str(results.json())
    assert "weekly-reports/" not in serialized
    assert "html_s3_key" not in serialized


def _minimal_release_bundle() -> dict:
    section = {"status": "passed", "summary": "ok"}
    return {
        "schema_version": "v1",
        "milestone": "v2.4",
        "phase": 67,
        "generated_at": "2026-06-07T10:00:00+00:00",
        "environment": "production",
        "backend": {"status": "passed", "commit_sha": "abc123", "deploy_run_id": "run-1"},
        "frontend": {"status": "skipped", "summary": "backend phase"},
        "infra": {"status": "passed", "cdk_diff": "no resource changes"},
        "api_checks": [section],
        "browser_smoke": {"status": "skipped", "summary": "backend phase"},
        "privacy": {"status": "passed", "denylist_checked": True},
        "quality_gates": [section],
    }


def _patch_support_delivery_repo(monkeypatch):
    delivery_rows = {}
    delivery_audits = []

    def put_delivery(delivery_id, delivery):
        if delivery_id in delivery_rows:
            return delivery_rows[delivery_id], False
        row = dict(delivery)
        delivery_rows[delivery_id] = row
        return row, True

    monkeypatch.setattr(report_repo, "put_support_handoff_delivery_record", put_delivery)
    monkeypatch.setattr(
        report_repo,
        "put_support_handoff_delivery_audit_event",
        lambda delivery_id, event: delivery_audits.append((delivery_id, event)),
    )
    return delivery_rows, delivery_audits


