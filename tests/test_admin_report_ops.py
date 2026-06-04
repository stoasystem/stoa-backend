from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.db.repositories import report_repo
from stoa.deps import get_current_user
from stoa.routers import admin


def _app_for_user(user: dict) -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_current_user] = lambda: user
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
        "email_failed_at": "2026-06-04T10:00:00+00:00",
        "email_error_class": "MessageRejected",
        "email_error_message": "bad address",
    }


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
    assert data["artifact_keys"] == {
        "json_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/report.json",
        "html_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/report.html",
    }
    serialized = str(data)
    assert "<html" not in serialized
    assert "publicUrl" not in serialized
    assert "presignedUrl" not in serialized
    assert "https://s3" not in serialized


def test_resend_failed_report_uses_existing_html_artifact_and_audits(monkeypatch):
    updates = []
    sent = []

    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(),
    )
    monkeypatch.setattr(
        admin.report_artifact_service,
        "get_report_html",
        lambda key: "<html>Report</html>",
    )
    monkeypatch.setattr(
        admin.notify_service,
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


def test_resend_refuses_non_failed_report(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _report(status="email_sent", email_status="sent"),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/resend")

    assert response.status_code == 409
