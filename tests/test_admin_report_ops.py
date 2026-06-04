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
        "generation_failed_at": "2026-06-04T09:00:00+00:00" if status == "generation_failed" else None,
        "generation_error_class": "RuntimeError" if status == "generation_failed" else None,
        "generation_error_message": "bedrock failed" if status == "generation_failed" else None,
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

    monkeypatch.setattr(report_repo, "decode_page_token", lambda token: {"PK": "REPORT#prev", "SK": "SUMMARY"})
    monkeypatch.setattr(report_repo, "encode_page_token", lambda key: "encoded-next" if key else None)

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
            "last_key": {"PK": "REPORT#prev", "SK": "SUMMARY"},
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
    monkeypatch.setattr(report_repo, "decode_page_token", lambda token: (_ for _ in ()).throw(ValueError("bad")))
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/ops", params={"next_token": "bad"})

    assert response.status_code == 400


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
