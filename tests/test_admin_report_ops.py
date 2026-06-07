import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings
from stoa.db.repositories import report_repo
from stoa.deps import get_current_user
from stoa.routers import admin
from stoa.services import report_artifact_edit_service
from stoa.services import report_audit_retention_service
from stoa.services import report_recovery_job_service
from stoa.services import report_recovery_service


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


def test_report_edit_draft_is_admin_only(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("non-admin edit draft should not mutate")

    monkeypatch.setattr(report_repo, "put_report_edit_draft", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/edit-drafts",
        json={"reason": "fix typo", "proposed_fields": {"admin_note": "Reviewed"}},
    )

    assert response.status_code == 403


def test_create_report_edit_draft_persists_metadata_only_and_audits(monkeypatch, audit_events):
    drafts = []
    report = {**_report(status="email_sent", email_status="sent"), "updated_at": "2026-06-05T10:00:00+00:00"}
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)
    monkeypatch.setattr(report_repo, "put_report_edit_draft", lambda report_id, draft: drafts.append((report_id, draft)))
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/edit-drafts",
        json={
            "reason": "parent requested wording adjustment",
            "proposed_fields": {"admin_note": "Reviewed by admin", "status_note": None},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    assert data["source_updated_at"] == "2026-06-05T10:00:00+00:00"
    assert data["created_by"] == "admin-sub"
    assert data["proposed_fields"] == {"admin_note": "Reviewed by admin", "status_note": None}
    assert drafts[0][0] == report["report_id"]
    assert drafts[0][1]["reason"] == "parent requested wording adjustment"
    assert audit_events[0][1]["action"] == "create_report_edit_draft"
    assert audit_events[0][1]["result"] == "draft"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(drafts)
    _assert_no_private_artifact_markers(audit_events)


def test_create_report_edit_draft_rejects_private_markers_and_unknown_fields(monkeypatch):
    report = {**_report(status="email_sent", email_status="sent"), "updated_at": "2026-06-05T10:00:00+00:00"}
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)

    def fail(*args, **kwargs):
        raise AssertionError("invalid edit draft should not persist")

    monkeypatch.setattr(report_repo, "put_report_edit_draft", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    private_response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/edit-drafts",
        json={
            "reason": "bad",
            "proposed_fields": {"admin_note": "weekly-reports/parent/student/week/report.json"},
        },
    )
    unknown_response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/edit-drafts",
        json={"reason": "bad", "proposed_fields": {"html_s3_key": "x"}},
    )

    assert private_response.status_code == 422
    assert unknown_response.status_code == 422
    _assert_no_private_artifact_markers(private_response.json())
    _assert_no_private_artifact_markers(unknown_response.json())


def test_get_report_edit_draft_returns_metadata_only(monkeypatch):
    report = {**_report(status="email_sent", email_status="sent"), "updated_at": "2026-06-05T10:00:00+00:00"}
    draft = {
        "draft_id": "draft-1",
        "report_id": report["report_id"],
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "source_updated_at": report["updated_at"],
        "created_by": "admin-sub",
        "created_at": "2026-06-05T10:01:00+00:00",
        "updated_at": "2026-06-05T10:01:00+00:00",
        "reason": "fix wording weekly-reports/private/report.html",
        "proposed_fields": {"editor_summary": "Shorter summary"},
        "status": "draft",
        "html_s3_key": "weekly-reports/private/report.html",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)
    monkeypatch.setattr(report_repo, "get_report_edit_draft", lambda report_id, draft_id: draft)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/parent-1/student-1/2026-06-01/edit-drafts/draft-1")

    assert response.status_code == 200
    data = response.json()
    assert data["draft_id"] == "draft-1"
    assert data["reason"] == "fix wording [report-artifact-key]"
    assert data["proposed_fields"] == {"editor_summary": "Shorter summary"}
    _assert_no_private_artifact_markers(data)


def test_apply_report_edit_draft_updates_report_marks_draft_and_audits(monkeypatch, audit_events):
    updates = []
    marked = []
    report = {
        **_report(status="email_sent", email_status="sent"),
        "updated_at": "2026-06-05T10:00:00+00:00",
        "admin_note": "old",
    }
    draft = {
        "draft_id": "draft-1",
        "report_id": report["report_id"],
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "source_updated_at": report["updated_at"],
        "created_by": "admin-sub",
        "created_at": "2026-06-05T10:01:00+00:00",
        "updated_at": "2026-06-05T10:01:00+00:00",
        "reason": "fix wording",
        "proposed_fields": {"admin_note": "new", "editor_summary": "Updated summary"},
        "status": "draft",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)
    monkeypatch.setattr(report_repo, "get_report_edit_draft", lambda report_id, draft_id: draft)
    monkeypatch.setattr(
        report_repo,
        "try_apply_report_edit",
        lambda report_id, **kwargs: updates.append((report_id, kwargs)) or True,
    )
    monkeypatch.setattr(
        report_repo,
        "mark_report_edit_draft_applied",
        lambda report_id, draft_id, **kwargs: marked.append((report_id, draft_id, kwargs)) or True,
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/edit-drafts/draft-1/apply")

    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "edit_report"
    assert data["operation_result"] == "success"
    assert data["draft"]["status"] == "applied"
    assert data["report"]["admin_note"] == "new"
    assert updates[0][0] == report["report_id"]
    assert updates[0][1]["expected_updated_at"] == report["updated_at"]
    assert updates[0][1]["fields"]["last_operation"] == "edit_report"
    assert updates[0][1]["fields"]["last_operation_by"] == "admin-sub"
    assert marked[0][0] == report["report_id"]
    assert marked[0][1] == "draft-1"
    event = audit_events[0][1]
    assert event["action"] == "apply_report_edit"
    assert event["result"] == "success"
    assert event["after"]["draft_id"] == "draft-1"
    assert event["after"]["validation_result"] == "passed"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_events)


def test_apply_report_edit_draft_rejects_stale_source_and_audits(monkeypatch, audit_events):
    def fail(*args, **kwargs):
        raise AssertionError("stale draft should not mutate report")

    report = {**_report(status="email_sent", email_status="sent"), "updated_at": "2026-06-05T10:10:00+00:00"}
    draft = {
        "draft_id": "draft-1",
        "report_id": report["report_id"],
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "source_updated_at": "2026-06-05T10:00:00+00:00",
        "created_by": "admin-sub",
        "created_at": "2026-06-05T10:01:00+00:00",
        "reason": "fix wording",
        "proposed_fields": {"admin_note": "new"},
        "status": "draft",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)
    monkeypatch.setattr(report_repo, "get_report_edit_draft", lambda report_id, draft_id: draft)
    monkeypatch.setattr(report_repo, "try_apply_report_edit", fail)
    monkeypatch.setattr(report_repo, "mark_report_edit_draft_applied", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post("/admin/reports/parent-1/student-1/2026-06-01/edit-drafts/draft-1/apply")

    assert response.status_code == 409
    assert audit_events[0][1]["action"] == "apply_report_edit"
    assert audit_events[0][1]["result"] == "refused"
    assert audit_events[0][1]["after"]["validation_result"] == "failed"


def test_report_artifact_edit_preview_is_admin_only(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("non-admin artifact edit preview should not mutate")

    monkeypatch.setattr(report_repo, "put_report_artifact_edit_draft", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/artifact-edit-previews",
        json={"reason": "fix typo", "proposed_fields": {"summary": "Updated"}},
    )

    assert response.status_code == 403


def test_create_report_artifact_edit_preview_returns_sanitized_diff_and_audits(
    monkeypatch,
    audit_events,
):
    drafts = []
    report = {
        **_report(status="email_sent", email_status="sent"),
        "updated_at": "2026-06-05T10:00:00+00:00",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)
    monkeypatch.setattr(
        report_artifact_edit_service.report_artifact_service,
        "get_report_json",
        lambda key, **kwargs: _report_json_artifact(),
    )
    monkeypatch.setattr(
        report_repo,
        "put_report_artifact_edit_draft",
        lambda report_id, draft: drafts.append((report_id, draft)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/artifact-edit-previews",
        json={
            "reason": "parent requested wording adjustment",
            "proposed_fields": {
                "summary": "Updated summary",
                "recommendations": ["Practice fractions twice this week."],
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    assert data["source_updated_at"] == "2026-06-05T10:00:00+00:00"
    assert data["created_by"] == "admin-sub"
    assert {item["field"] for item in data["diff"]} == {"summary", "recommendations"}
    assert drafts[0][0] == report["report_id"]
    assert drafts[0][1]["source_json_s3_key"] == report["json_s3_key"]
    assert audit_events[0][1]["action"] == "create_report_artifact_edit_preview"
    assert audit_events[0][1]["result"] == "draft"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_events)


def test_create_report_artifact_edit_preview_rejects_private_markers(monkeypatch):
    report = {
        **_report(status="email_sent", email_status="sent"),
        "updated_at": "2026-06-05T10:00:00+00:00",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)

    def fail(*args, **kwargs):
        raise AssertionError("invalid artifact edit preview should not persist")

    monkeypatch.setattr(report_repo, "put_report_artifact_edit_draft", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/artifact-edit-previews",
        json={
            "reason": "bad",
            "proposed_fields": {"summary": "weekly-reports/parent/student/week/report.json"},
        },
    )

    assert response.status_code == 422
    _assert_no_private_artifact_markers(response.json())


def test_apply_report_artifact_edit_preview_writes_versioned_artifacts_and_audits(
    monkeypatch,
    audit_events,
):
    writes = []
    updates = []
    marked = []
    report = {
        **_report(status="email_sent", email_status="sent"),
        "updated_at": "2026-06-05T10:00:00+00:00",
    }
    draft = {
        "draft_id": "draft-1",
        "report_id": report["report_id"],
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "source_updated_at": report["updated_at"],
        "source_artifact_version_id": None,
        "source_json_s3_key": report["json_s3_key"],
        "source_html_s3_key": report["html_s3_key"],
        "created_by": "admin-sub",
        "created_at": "2026-06-05T10:01:00+00:00",
        "updated_at": "2026-06-05T10:01:00+00:00",
        "reason": "fix summary",
        "proposed_fields": {"summary": "Updated summary"},
        "diff": [{"field": "summary", "before": "Original summary", "after": "Updated summary", "changed": True}],
        "status": "draft",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)
    monkeypatch.setattr(report_repo, "get_report_artifact_edit_draft", lambda report_id, draft_id: draft)
    monkeypatch.setattr(
        report_artifact_edit_service.report_artifact_service,
        "get_report_json",
        lambda key, **kwargs: _report_json_artifact(),
    )
    monkeypatch.setattr(
        report_artifact_edit_service.report_artifact_service,
        "write_report_artifacts",
        lambda keys, json_artifact, html_artifact, **kwargs: writes.append(
            (keys, json_artifact, html_artifact)
        ),
    )
    monkeypatch.setattr(
        report_repo,
        "try_apply_report_artifact_edit",
        lambda report_id, **kwargs: updates.append((report_id, kwargs)) or True,
    )
    monkeypatch.setattr(
        report_repo,
        "mark_report_artifact_edit_draft_applied",
        lambda report_id, draft_id, **kwargs: marked.append((report_id, draft_id, kwargs)) or True,
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/artifact-edit-previews/draft-1/apply",
        json={"reason": "approve updated summary"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "edit_report_artifact"
    assert data["operation_result"] == "success"
    assert data["draft"]["status"] == "applied"
    assert data["report"]["artifact_version_id"].startswith("v")
    assert writes[0][0].json_key.startswith("weekly-reports/parent-1/student-1/2026-06-01/versions/v")
    assert writes[0][0].html_key.endswith("/report.html")
    assert writes[0][1]["content"]["summary"] == "Updated summary"
    assert "Updated summary" in writes[0][2]
    assert updates[0][0] == report["report_id"]
    assert updates[0][1]["expected_updated_at"] == report["updated_at"]
    assert updates[0][1]["fields"]["last_operation"] == "edit_report_artifact"
    assert updates[0][1]["fields"]["previous_json_s3_key"] == report["json_s3_key"]
    assert marked[0][0] == report["report_id"]
    assert marked[0][1] == "draft-1"
    event = audit_events[0][1]
    assert event["action"] == "apply_report_artifact_edit"
    assert event["result"] == "success"
    assert event["after"]["draft_id"] == "draft-1"
    assert event["after"]["validation_result"] == "passed"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_events)


def test_apply_report_artifact_edit_preview_rejects_stale_source_and_audits(
    monkeypatch,
    audit_events,
):
    def fail(*args, **kwargs):
        raise AssertionError("stale artifact edit should not write artifacts or update report")

    report = {
        **_report(status="email_sent", email_status="sent"),
        "updated_at": "2026-06-05T10:10:00+00:00",
    }
    draft = {
        "draft_id": "draft-1",
        "report_id": report["report_id"],
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "source_updated_at": "2026-06-05T10:00:00+00:00",
        "source_artifact_version_id": None,
        "source_json_s3_key": report["json_s3_key"],
        "source_html_s3_key": report["html_s3_key"],
        "reason": "fix summary",
        "proposed_fields": {"summary": "Updated summary"},
        "status": "draft",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)
    monkeypatch.setattr(report_repo, "get_report_artifact_edit_draft", lambda report_id, draft_id: draft)
    monkeypatch.setattr(report_artifact_edit_service.report_artifact_service, "write_report_artifacts", fail)
    monkeypatch.setattr(report_repo, "try_apply_report_artifact_edit", fail)
    monkeypatch.setattr(report_repo, "mark_report_artifact_edit_draft_applied", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/artifact-edit-previews/draft-1/apply",
        json={"reason": "approve updated summary"},
    )

    assert response.status_code == 409
    assert audit_events[0][1]["action"] == "apply_report_artifact_edit"
    assert audit_events[0][1]["result"] == "refused"
    assert audit_events[0][1]["after"]["validation_result"] == "failed"
    _assert_no_private_artifact_markers(response.json())
    _assert_no_private_artifact_markers(audit_events)


def test_report_artifact_rollback_preview_is_admin_only(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("non-admin artifact rollback preview should not mutate")

    monkeypatch.setattr(report_repo, "put_report_artifact_rollback_preview", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/artifact-rollback-previews",
        json={"reason": "restore previous artifact version"},
    )

    assert response.status_code == 403


def test_create_report_artifact_rollback_preview_returns_sanitized_metadata_and_audits(
    monkeypatch,
    audit_events,
):
    previews = []
    report = {
        **_report(status="email_sent", email_status="sent"),
        "updated_at": "2026-06-05T10:05:00+00:00",
        "artifact_version_id": "v2",
        "json_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v2/report.json",
        "html_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v2/report.html",
        "previous_artifact_version_id": "v1",
        "previous_json_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v1/report.json",
        "previous_html_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v1/report.html",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)
    monkeypatch.setattr(
        report_repo,
        "put_report_artifact_rollback_preview",
        lambda report_id, preview: previews.append((report_id, preview)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/artifact-rollback-previews",
        json={"reason": "restore prior approved version"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    assert data["validation_result"] == "passed"
    assert data["source_artifact_version_id"] == "v2"
    assert data["target_artifact_version_id"] == "v1"
    assert previews[0][0] == report["report_id"]
    assert previews[0][1]["source_json_s3_key"] == report["json_s3_key"]
    assert previews[0][1]["target_json_s3_key"] == report["previous_json_s3_key"]
    assert audit_events[0][1]["action"] == "create_report_artifact_rollback_preview"
    assert audit_events[0][1]["result"] == "draft"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_events)


def test_create_report_artifact_rollback_preview_rejects_missing_target(monkeypatch):
    report = {
        **_report(status="email_sent", email_status="sent"),
        "updated_at": "2026-06-05T10:05:00+00:00",
        "artifact_version_id": "v2",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)

    def fail(*args, **kwargs):
        raise AssertionError("invalid rollback preview should not persist")

    monkeypatch.setattr(report_repo, "put_report_artifact_rollback_preview", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/artifact-rollback-previews",
        json={"reason": "restore prior approved version"},
    )

    assert response.status_code == 422
    _assert_no_private_artifact_markers(response.json())


def test_create_report_artifact_rollback_preview_rejects_noop_target(monkeypatch):
    report = {
        **_report(status="email_sent", email_status="sent"),
        "updated_at": "2026-06-05T10:05:00+00:00",
        "artifact_version_id": "v1",
        "json_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v1/report.json",
        "html_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v1/report.html",
        "previous_artifact_version_id": "v1",
        "previous_json_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v1/report.json",
        "previous_html_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v1/report.html",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)

    def fail(*args, **kwargs):
        raise AssertionError("no-op rollback preview should not persist")

    monkeypatch.setattr(report_repo, "put_report_artifact_rollback_preview", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/artifact-rollback-previews",
        json={"reason": "restore prior approved version"},
    )

    assert response.status_code == 409
    _assert_no_private_artifact_markers(response.json())


def test_apply_report_artifact_rollback_preview_updates_metadata_and_audits(
    monkeypatch,
    audit_events,
):
    updates = []
    marked = []
    report = {
        **_report(status="email_sent", email_status="sent"),
        "updated_at": "2026-06-05T10:05:00+00:00",
        "artifact_version_id": "v2",
        "json_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v2/report.json",
        "html_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v2/report.html",
        "previous_artifact_version_id": "v1",
        "previous_json_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v1/report.json",
        "previous_html_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v1/report.html",
    }
    preview = {
        "preview_id": "rollback-1",
        "report_id": report["report_id"],
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "source_updated_at": report["updated_at"],
        "source_artifact_version_id": "v2",
        "source_json_s3_key": report["json_s3_key"],
        "source_html_s3_key": report["html_s3_key"],
        "target_artifact_version_id": "v1",
        "target_json_s3_key": report["previous_json_s3_key"],
        "target_html_s3_key": report["previous_html_s3_key"],
        "created_by": "admin-sub",
        "created_at": "2026-06-05T10:06:00+00:00",
        "updated_at": "2026-06-05T10:06:00+00:00",
        "reason": "restore prior version",
        "status": "draft",
        "validation_result": "passed",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)
    monkeypatch.setattr(report_repo, "get_report_artifact_rollback_preview", lambda report_id, preview_id: preview)
    monkeypatch.setattr(
        report_repo,
        "try_apply_report_artifact_edit",
        lambda report_id, **kwargs: updates.append((report_id, kwargs)) or True,
    )
    monkeypatch.setattr(
        report_repo,
        "mark_report_artifact_rollback_preview_applied",
        lambda report_id, preview_id, **kwargs: marked.append((report_id, preview_id, kwargs)) or True,
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/artifact-rollback-previews/rollback-1/apply",
        json={"reason": "approve rollback"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "rollback_report_artifact"
    assert data["operation_result"] == "success"
    assert data["preview"]["status"] == "applied"
    assert data["report"]["artifact_version_id"] == "v1"
    assert data["report"]["previous_artifact_version_id"] == "v2"
    assert updates[0][0] == report["report_id"]
    assert updates[0][1]["expected_artifact_version_id"] == "v2"
    assert updates[0][1]["fields"]["json_s3_key"] == report["previous_json_s3_key"]
    assert updates[0][1]["fields"]["previous_json_s3_key"] == report["json_s3_key"]
    assert updates[0][1]["fields"]["last_operation"] == "rollback_report_artifact"
    assert marked[0][0] == report["report_id"]
    assert marked[0][1] == "rollback-1"
    event = audit_events[0][1]
    assert event["action"] == "apply_report_artifact_rollback"
    assert event["result"] == "success"
    assert event["after"]["rollback_preview_id"] == "rollback-1"
    assert event["after"]["validation_result"] == "passed"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_events)


def test_apply_report_artifact_rollback_preview_rejects_stale_source_and_audits(
    monkeypatch,
    audit_events,
):
    def fail(*args, **kwargs):
        raise AssertionError("stale rollback should not update report")

    report = {
        **_report(status="email_sent", email_status="sent"),
        "updated_at": "2026-06-05T10:10:00+00:00",
        "artifact_version_id": "v2",
        "json_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v2/report.json",
        "html_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v2/report.html",
    }
    preview = {
        "preview_id": "rollback-1",
        "report_id": report["report_id"],
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "source_updated_at": "2026-06-05T10:05:00+00:00",
        "source_artifact_version_id": "v2",
        "source_json_s3_key": report["json_s3_key"],
        "source_html_s3_key": report["html_s3_key"],
        "target_artifact_version_id": "v1",
        "target_json_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v1/report.json",
        "target_html_s3_key": "weekly-reports/parent-1/student-1/2026-06-01/versions/v1/report.html",
        "reason": "restore prior version",
        "status": "draft",
        "validation_result": "passed",
    }
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda parent_id, student_id, week_start: report)
    monkeypatch.setattr(report_repo, "get_report_artifact_rollback_preview", lambda report_id, preview_id: preview)
    monkeypatch.setattr(report_repo, "try_apply_report_artifact_edit", fail)
    monkeypatch.setattr(report_repo, "mark_report_artifact_rollback_preview_applied", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/parent-1/student-1/2026-06-01/artifact-rollback-previews/rollback-1/apply",
        json={"reason": "approve rollback"},
    )

    assert response.status_code == 409
    assert audit_events[0][1]["action"] == "apply_report_artifact_rollback"
    assert audit_events[0][1]["result"] == "refused"
    assert audit_events[0][1]["after"]["validation_result"] == "failed"
    _assert_no_private_artifact_markers(response.json())
    _assert_no_private_artifact_markers(audit_events)


def test_recovery_job_audit_timeline_returns_job_scope(monkeypatch):
    calls = []
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

    def list_reports_for_admin(**kwargs):
        calls.append(kwargs)
        return {"Items": [_report()]}

    monkeypatch.setattr(report_repo, "list_reports_for_admin", list_reports_for_admin)
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
    assert calls == [
        {
            "status": "email_failed",
            "week_start": "2026-06-01",
            "parent_id": None,
            "student_id": None,
            "limit": 5,
            "last_key": None,
        }
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
    monkeypatch.setattr(report_repo, "list_reports_for_admin", lambda **kwargs: {"Items": [_report()]})
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
    assert calls == [
        {
            "status": "generation_failed",
            "week_start": "2026-06-01",
            "parent_id": None,
            "student_id": None,
            "limit": 5,
            "last_key": None,
        }
    ]
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
    monkeypatch.setattr(
        report_repo,
        "get_recovery_job",
        lambda job_id: {"job_id": job_id, "job_type": "resend_email", "status": "running"},
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/recovery-jobs/job-running/resume/preview",
        json={"reason": "resume failed subset", "results": ["failed"]},
    )

    assert response.status_code == 409


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


def test_recovery_evidence_export_is_admin_only(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("non-admin export should not query recovery evidence")

    monkeypatch.setattr(report_repo, "get_recovery_job", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.get("/admin/reports/recovery-evidence", params={"job_id": "job-1"})

    assert response.status_code == 403


def test_recovery_evidence_job_export_returns_metadata_only_and_read_only(monkeypatch):
    mutations = []
    job = {
        "PK": "REPORT_RECOVERY_JOB#job-1",
        "SK": "SUMMARY",
        "job_id": "job-1",
        "job_type": "resend_email",
        "status": "completed",
        "reason": "incident weekly-reports/private/report.html html_s3_key",
        "created_by": "admin-sub",
        "created_at": "2026-06-04T10:00:00+00:00",
        "updated_at": "2026-06-04T10:05:00+00:00",
        "filters": {"status": "email_failed", "json_s3_key": "weekly-reports/private/report.json"},
        "presignedUrl": "https://s3.amazonaws.com/private?X-Amz-Signature=secret",
        "target_count": 1,
        "success_count": 1,
    }
    target = {
        "PK": "REPORT_RECOVERY_JOB#job-1",
        "SK": "TARGET#00000#target-1",
        "target_id": "target-1",
        "report_id": "report-1",
        "parent_id": "parent-1",
        "student_id": "student-1",
        "student_name": "Student",
        "week_start": "2026-06-01",
        "result": "success",
        "status": "email_sent",
        "email_status": "sent",
        "detail": "resent weekly-reports/private/report.html html_s3_key",
        "publicUrl": "https://s3.amazonaws.com/private/report.html",
        "html_s3_key": "weekly-reports/private/report.html",
    }
    event = {
        "PK": "REPORT_RECOVERY_JOB#job-1",
        "SK": "AUDIT#2026-06-04T10:00:00#event-1",
        "event_id": "event-1",
        "event_at": "2026-06-04T10:00:00+00:00",
        "report_id": "report-1",
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "actor": "admin-sub",
        "action": "create_resend_job",
        "reason": "incident weekly-reports/private/report.html",
        "source": "admin_api",
        "result": "success",
        "before": {"status": "email_failed", "html_s3_key": "weekly-reports/private/report.html"},
        "after": {
            "status": "email_sent",
            "detail": "used weekly-reports/private/report.html html_s3_key",
            "artifact_url": "https://stoa-reports.s3.eu-central-2.amazonaws.com/private?X-Amz-Signature=secret",
        },
        "error_message": "ok weekly-reports/private/report.html",
        "correlation_id": "job-1",
    }
    target_next_key = {"PK": "REPORT_RECOVERY_JOB#job-1", "SK": "TARGET#00001#target-2"}
    audit_next_key = {"PK": "REPORT_RECOVERY_JOB#job-1", "SK": "AUDIT#2026-06-04T09:00:00#event-0"}

    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: job if job_id == "job-1" else None)
    monkeypatch.setattr(
        report_repo,
        "list_recovery_job_targets",
        lambda job_id, **kwargs: {"Items": [target], "LastEvaluatedKey": target_next_key},
    )
    monkeypatch.setattr(
        report_repo,
        "list_recovery_job_audit_events",
        lambda job_id, **kwargs: {"Items": [event], "LastEvaluatedKey": audit_next_key},
    )
    monkeypatch.setattr(report_repo, "put_recovery_job", lambda *args, **kwargs: mutations.append("put_job"))
    monkeypatch.setattr(report_repo, "update_recovery_job_status", lambda *args, **kwargs: mutations.append("job"))
    monkeypatch.setattr(report_repo, "update_recovery_job_target", lambda *args, **kwargs: mutations.append("target"))
    monkeypatch.setattr(report_repo, "update_report_status", lambda *args, **kwargs: mutations.append("report"))
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get(
        "/admin/reports/recovery-evidence",
        params={"job_id": "job-1", "target_limit": 10, "audit_limit": 5},
        headers={"x-request-id": "req-123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "req-123"
    assert data["scope"] == "recovery_job"
    assert data["complete"] is False
    assert data["privacy"] == {"metadata_only": True, "private_artifact_fields_omitted": True}
    assert data["filters"]["job_id"] == "job-1"
    assert data["jobs"][0]["reason"] == "incident [report-artifact-key] [report-artifact-field]"
    assert data["jobs"][0]["filters"] == {"status": "email_failed"}
    assert data["targets"][0]["detail"] == "resent [report-artifact-key] [report-artifact-field]"
    assert data["job_audit"][0]["before"] == {"status": "email_failed"}
    assert data["job_audit"][0]["after"]["detail"] == "used [report-artifact-key] [report-artifact-field]"
    assert data["job_audit"][0]["after"]["artifact_url"] == "[report-artifact-url]"
    assert report_repo.decode_recovery_job_page_token(data["next_tokens"]["targets"]) == target_next_key
    assert report_repo.decode_audit_page_token(data["next_tokens"]["job_audit"]) == audit_next_key
    assert mutations == []
    _assert_no_private_artifact_markers(data)


def test_recovery_job_support_package_returns_metadata_only_and_read_only(monkeypatch):
    mutations = []
    job = {
        "job_id": "job-resume",
        "job_type": "retry_generation",
        "status": "completed_with_failures",
        "reason": "resume support weekly-reports/private/report.html",
        "source_job_id": "job-source",
        "resume_result_filters": ["failed"],
        "target_count": 1,
        "failed_count": 1,
    }
    source_job = {
        "job_id": "job-source",
        "job_type": "retry_generation",
        "status": "completed_with_failures",
        "reason": "source support",
        "target_count": 1,
        "failed_count": 1,
    }
    target = {
        "target_id": "target-1",
        "report_id": "report-1",
        "parent_id": "parent-1",
        "student_id": "student-1",
        "student_name": "Student",
        "week_start": "2026-06-01",
        "result": "failed",
        "source_job_id": "job-source",
        "source_target_result": "failed",
        "detail": "failed weekly-reports/private/report.html html_s3_key",
        "html_s3_key": "weekly-reports/private/report.html",
    }
    event = {
        "event_id": "event-1",
        "event_at": "2026-06-04T10:00:00+00:00",
        "action": "create_resume_job",
        "actor": "admin-sub",
        "source": "admin_api",
        "result": "queued",
        "metadata": {"html_s3_key": "weekly-reports/private/report.html"},
    }
    report_event = {
        "event_id": "report-event-1",
        "event_at": "2026-06-04T10:00:00+00:00",
        "report_id": "report-1",
        "action": "retry_generation",
        "actor": "admin-sub",
        "source": "recovery_job",
        "result": "failed",
        "error_message": "provider weekly-reports/private/report.html",
    }

    def get_job(job_id):
        return {"job-resume": job, "job-source": source_job}.get(job_id)

    monkeypatch.setattr(report_repo, "get_recovery_job", get_job)
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": [target]})
    monkeypatch.setattr(report_repo, "list_recovery_job_audit_events", lambda job_id, **kwargs: {"Items": [event]})
    monkeypatch.setattr(report_repo, "list_report_audit_events", lambda report_id, **kwargs: {"Items": [report_event]})
    monkeypatch.setattr(report_repo, "put_recovery_job", lambda *args, **kwargs: mutations.append("put_job"))
    monkeypatch.setattr(report_repo, "update_recovery_job_status", lambda *args, **kwargs: mutations.append("job"))
    monkeypatch.setattr(report_repo, "update_recovery_job_target", lambda *args, **kwargs: mutations.append("target"))
    monkeypatch.setattr(report_repo, "update_report_status", lambda *args, **kwargs: mutations.append("report"))
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get(
        "/admin/reports/recovery-jobs/job-resume/support-package",
        params={"include_report_audit": True, "note": "support weekly-reports/private/report.html"},
        headers={"x-request-id": "req-support"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "support_package"
    assert data["request_id"] == "req-support"
    assert data["job"]["job_id"] == "job-resume"
    assert data["source_job"]["job_id"] == "job-source"
    assert data["rollup"]["failed_count"] == 1
    assert data["targets"][0]["source_job_id"] == "job-source"
    assert data["targets"][0]["source_target_result"] == "failed"
    assert data["operator_note"] == "support [report-artifact-key]"
    assert data["privacy"]["metadata_only"] is True
    assert mutations == []
    _assert_no_private_artifact_markers(data)


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


def test_support_handoff_package_is_admin_only(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("non-admin handoff should not query evidence")

    monkeypatch.setattr(report_repo, "get_recovery_job", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.post(
        "/admin/reports/support-handoff-package",
        json={"reason": "support", "recovery_job_ids": ["job-1"]},
    )

    assert response.status_code == 403


def test_support_handoff_package_composes_metadata_and_audits(monkeypatch):
    audit_rows = []
    job = {
        "job_id": "job-1",
        "job_type": "resend_email",
        "status": "completed",
        "reason": "support weekly-reports/private/report.html",
        "target_count": 1,
        "success_count": 1,
    }
    target = {
        "target_id": "target-1",
        "report_id": "report-1",
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "result": "success",
        "detail": "sent weekly-reports/private/report.html html_s3_key",
        "html_s3_key": "weekly-reports/private/report.html",
    }
    event = {
        "event_id": "event-1",
        "event_at": "2026-06-07T10:00:00+00:00",
        "action": "create_resend_job",
        "actor": "admin-sub",
        "source": "admin_api",
        "result": "success",
        "after": {"html_s3_key": "weekly-reports/private/report.html"},
    }
    fixture_report = {
        **_report(status="email_sent", email_status="sent"),
        "artifact_version_id": "original",
        "previous_artifact_version_id": "v1",
    }

    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: job if job_id == "job-1" else None)
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": [target]})
    monkeypatch.setattr(report_repo, "list_recovery_job_audit_events", lambda job_id, **kwargs: {"Items": [event]})
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda *args: fixture_report)
    monkeypatch.setattr(report_repo, "list_report_audit_events", lambda report_id, limit=10, last_key=None: {"Items": [event]})
    monkeypatch.setattr(
        report_repo,
        "put_support_handoff_audit_event",
        lambda package_id, event: audit_rows.append((package_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/support-handoff-package",
        json={
            "reason": "ticket weekly-reports/private/report.html",
            "destination_mode": "copy",
            "recovery_job_ids": ["job-1"],
            "release_evidence": _minimal_release_bundle(),
            "fixture": {"fixture_name": "stoa-safe-fixture-v2-2-rollback-2026-06-06"},
            "operator_note": "copy weekly-reports/private/report.html",
        },
        headers={"x-request-id": "req-handoff"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "v1"
    assert data["generated_by"] == "admin-sub"
    assert data["reason"] == "ticket [report-artifact-key]"
    assert data["destination"]["mode"] == "copy"
    assert data["destination"]["status"] == "ready"
    assert data["validation"]["status"] == "passed"
    assert data["validation"]["privacy"]["passed"] is True
    assert {section["type"] for section in data["sections"]} == {
        "recovery_job_support_package",
        "release_evidence_validation",
        "safe_fixture_status",
        "operator_note",
    }
    assert data["copy"]["format"] == "markdown"
    assert data["audit"]["correlation_id"] == "req-handoff"
    assert len(audit_rows) == 1
    assert audit_rows[0][0] == data["package_id"]
    audit = audit_rows[0][1]
    assert audit["result"] == "generated"
    assert audit["metadata"]["destination_mode"] == "copy"
    assert audit["metadata"]["validation_result"] == "passed"
    assert "job-1" in audit["metadata"]["evidence_reference_ids"]
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_rows)


def test_support_handoff_package_records_missing_references(monkeypatch):
    audit_rows = []
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: None)
    monkeypatch.setattr(
        report_repo,
        "put_support_handoff_audit_event",
        lambda package_id, event: audit_rows.append((package_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/support-handoff-package",
        json={"reason": "support", "recovery_job_ids": ["missing-job"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["validation"]["status"] == "refused"
    assert data["validation"]["missing_references"] == [{"type": "recovery_job", "id": "missing-job"}]
    assert data["sections"] == []
    assert audit_rows[0][1]["result"] == "refused"
    assert audit_rows[0][1]["metadata"]["evidence_reference_ids"] == ["missing-job"]
    _assert_no_private_artifact_markers(data)


def test_support_handoff_package_redacts_free_text_credentials(monkeypatch):
    audit_rows = []
    monkeypatch.setattr(
        report_repo,
        "put_support_handoff_audit_event",
        lambda package_id, event: audit_rows.append((package_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/support-handoff-package",
        json={
            "reason": "support access_token=abc123",
            "operator_note": "password=hunter2 refresh_token=rt id_token=it cookie=session secret=value",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["reason"] == "support [private-credential]"
    assert data["sections"][0]["data"]["note"] == (
        "[private-credential] [private-credential] [private-credential] "
        "[private-credential] [private-credential]"
    )
    assert audit_rows[0][1]["reason"] == "support [private-credential]"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_rows)


def test_support_handoff_package_refuses_failed_release_evidence(monkeypatch):
    audit_rows = []
    bundle = _minimal_release_bundle()
    bundle["backend"]["json_s3_key"] = "weekly-reports/private/report.json"
    monkeypatch.setattr(
        report_repo,
        "put_support_handoff_audit_event",
        lambda package_id, event: audit_rows.append((package_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/support-handoff-package",
        json={"reason": "support", "release_evidence": bundle},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["destination"]["status"] == "refused"
    assert data["validation"]["status"] == "refused"
    assert data["sections"][0]["type"] == "release_evidence_validation"
    assert data["sections"][0]["status"] == "failed"
    assert "bundle" not in data["sections"][0]["data"]
    assert data["sections"][0]["data"]["privacy"]["passed"] is False
    assert audit_rows[0][1]["result"] == "refused"
    assert audit_rows[0][1]["metadata"]["validation_result"] == "refused"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_rows)


def test_support_handoff_external_write_is_refused_without_evidence_reads(monkeypatch):
    audit_rows = []

    def fail(*args, **kwargs):
        raise AssertionError("external_write refusal should not read evidence")

    monkeypatch.setattr(report_repo, "get_recovery_job", fail)
    monkeypatch.setattr(
        report_repo,
        "put_support_handoff_audit_event",
        lambda package_id, event: audit_rows.append((package_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/support-handoff-package",
        json={
            "reason": "support",
            "destination_mode": "external_write",
            "recovery_job_ids": ["job-1"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["destination"]["status"] == "refused"
    assert data["validation"]["status"] == "refused"
    assert data["sections"] == []
    assert audit_rows[0][1]["result"] == "refused"
    assert "direct external writes require approved connector" in data["destination"]["refusal_reasons"][0]
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_rows)


def test_support_handoff_unknown_destination_rejects_before_evidence_reads(monkeypatch):
    audit_rows = []

    def fail(*args, **kwargs):
        raise AssertionError("unknown destination should stop before evidence reads")

    monkeypatch.setattr(report_repo, "get_recovery_job", fail)
    monkeypatch.setattr(
        report_repo,
        "put_support_handoff_audit_event",
        lambda package_id, event: audit_rows.append((package_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/support-handoff-package",
        json={"reason": "support", "destination_mode": "zendesk", "recovery_job_ids": ["job-1"]},
    )

    assert response.status_code == 422
    assert audit_rows == []


def test_audit_retention_status_is_admin_only(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("non-admin retention status should not read evidence")

    monkeypatch.setattr(report_repo, "get_recovery_job", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.post(
        "/admin/reports/audit-retention/status",
        json={"references": [{"scope": "recovery_job", "job_id": "job-1"}]},
    )

    assert response.status_code == 403


def test_audit_retention_status_returns_metadata_states(monkeypatch):
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: {"job_id": job_id, "status": "completed"})
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/audit-retention/status",
        json={
            "references": [
                {"scope": "recovery_job", "job_id": "job-1"},
                {"scope": "unknown_scope", "job_id": "job-2"},
            ]
        },
        headers={"x-request-id": "req-ret-status"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "req-ret-status"
    assert data["scope_count"] == 2
    assert data["items"][0]["status"] == "unsealed"
    assert data["items"][0]["counts"] == {"jobs": 1}
    assert data["items"][1]["status"] == "unsupported"
    assert data["privacy"]["passed"] is True
    _assert_no_private_artifact_markers(data)


def test_audit_retention_status_propagates_release_privacy_failure(monkeypatch):
    bundle = _minimal_release_bundle()
    bundle["backend"]["presigned_url"] = "https://s3.amazonaws.com/private?X-Amz-Signature=secret"
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/audit-retention/status",
        json={"references": [{"scope": "release_evidence", "release_evidence": bundle}]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["status"] == "refused"
    assert data["items"][0]["privacy"]["passed"] is False
    assert data["items"][0]["privacy"]["violation_count"] >= 1
    _assert_no_private_artifact_markers(data)


def test_audit_retention_manifest_generates_digests_and_audits(monkeypatch):
    audit_rows = []
    job = {
        "job_id": "job-1",
        "job_type": "resend_email",
        "status": "completed",
        "reason": "incident weekly-reports/private/report.html",
        "target_count": 1,
        "success_count": 1,
    }
    target = {
        "target_id": "target-1",
        "report_id": "report-1",
        "parent_id": "parent-1",
        "student_id": "student-1",
        "week_start": "2026-06-01",
        "result": "success",
        "detail": "sent weekly-reports/private/report.html html_s3_key",
        "html_s3_key": "weekly-reports/private/report.html",
    }
    event = {
        "event_id": "event-1",
        "event_at": "2026-06-07T10:00:00+00:00",
        "action": "create_resend_job",
        "actor": "admin-sub",
        "source": "admin_api",
        "result": "success",
        "after": {"html_s3_key": "weekly-reports/private/report.html"},
    }

    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: job if job_id == "job-1" else None)
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": [target]})
    monkeypatch.setattr(report_repo, "list_recovery_job_audit_events", lambda job_id, **kwargs: {"Items": [event]})
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_audit_event",
        lambda manifest_id, event: audit_rows.append((manifest_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/audit-retention/manifest",
        json={
            "reason": "seal incident weekly-reports/private/report.html",
            "retention_category": "incident",
            "references": [{"scope": "recovery_job", "job_id": "job-1"}],
            "target_limit": 5,
            "audit_limit": 5,
        },
        headers={"x-request-id": "req-ret-manifest"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "v1"
    assert data["generated_by"] == "admin-sub"
    assert data["reason"] == "seal incident [report-artifact-key]"
    assert data["retention_category"] == "incident"
    assert data["status"] == "sealed"
    assert data["verification"]["item_count"] == 1
    assert data["verification"]["manifest_digest"].startswith("sha256:")
    assert data["items"][0]["digest"].startswith("sha256:")
    assert data["items"][0]["summary"]["jobs"][0]["reason"] == "incident [report-artifact-key]"
    assert data["verification"]["privacy"]["passed"] is True
    assert len(audit_rows) == 1
    assert audit_rows[0][0] == data["manifest_id"]
    audit = audit_rows[0][1]
    assert audit["result"] == "generated"
    assert audit["metadata"]["manifest_digest"] == data["verification"]["manifest_digest"]
    assert audit["metadata"]["item_count"] == 1
    assert audit["metadata"]["privacy_passed"] is True
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_rows)


def test_audit_retention_manifest_refuses_destructive_actions_without_reads(monkeypatch):
    audit_rows = []

    def fail(*args, **kwargs):
        raise AssertionError("destructive retention action should not read evidence")

    monkeypatch.setattr(report_repo, "get_recovery_job", fail)
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_audit_event",
        lambda manifest_id, event: audit_rows.append((manifest_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/audit-retention/manifest",
        json={
            "reason": "delete audit",
            "retention_action": "delete",
            "references": [{"scope": "recovery_job", "job_id": "job-1"}],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "refused"
    assert data["items"] == []
    assert "not supported" in data["verification"]["refusal_reasons"][0]
    assert audit_rows[0][1]["result"] == "refused"
    assert audit_rows[0][1]["metadata"]["retention_action"] == "delete"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_rows)


def test_audit_retention_manifest_redacts_private_free_text(monkeypatch):
    audit_rows = []
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: {"job_id": job_id, "status": "completed"})
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(report_repo, "list_recovery_job_audit_events", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(report_repo, "get_legal_hold_metadata", lambda scope_key: None)
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_audit_event",
        lambda manifest_id, event: audit_rows.append((manifest_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/audit-retention/manifest",
        json={
            "reason": "seal <html> access_token=abc123 password=hunter2",
            "references": [{"scope": "recovery_job", "job_id": "job-1"}],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["reason"] == "[REDACTED]"
    assert data["verification"]["privacy"]["passed"] is True
    assert audit_rows[0][1]["reason"] == "[REDACTED]"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_rows)


def test_audit_retention_manifest_refuses_failed_release_evidence(monkeypatch):
    audit_rows = []
    bundle = _minimal_release_bundle()
    bundle["backend"]["presigned_url"] = "https://s3.amazonaws.com/private?X-Amz-Signature=secret"
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_audit_event",
        lambda manifest_id, event: audit_rows.append((manifest_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/audit-retention/manifest",
        json={
            "reason": "seal release",
            "retention_category": "release",
            "references": [{"scope": "release_evidence", "release_evidence": bundle}],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "refused"
    assert data["items"] == []
    assert "release evidence validation failed" in data["verification"]["refusal_reasons"]
    assert audit_rows[0][1]["result"] == "refused"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_rows)


def test_immutable_evidence_status_is_admin_only(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("non-admin immutable status should not read evidence")

    monkeypatch.setattr(report_repo, "get_recovery_job", fail)
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.post(
        "/admin/reports/immutable-evidence/status",
        json={"references": [{"scope": "recovery_job", "job_id": "job-1"}]},
    )

    assert response.status_code == 403


def test_immutable_evidence_status_reports_missing_cdk_config(monkeypatch):
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: {"job_id": job_id, "status": "completed"})
    monkeypatch.setattr(report_repo, "get_legal_hold_metadata", lambda scope_key: None)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/immutable-evidence/status",
        json={"references": [{"scope": "recovery_job", "job_id": "job-1"}]},
        headers={"x-request-id": "req-immutable-status"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "req-immutable-status"
    assert data["immutable_storage"]["status"] == "not_configured"
    assert data["immutable_storage"]["resource_configured"] is False
    assert data["audit_retention"]["items"][0]["status"] == "unsealed"
    assert data["legal_hold"]["items"][0]["status"] == "none"
    assert data["privacy"]["passed"] is True
    _assert_no_private_artifact_markers(data)


def test_immutable_storage_status_reads_cdk_env_without_leaking_resource(monkeypatch):
    monkeypatch.setenv("IMMUTABLE_AUDIT_STORAGE_MODE", "cdk_managed")
    monkeypatch.setenv("IMMUTABLE_AUDIT_STORAGE_CDK_MANAGED", "true")
    monkeypatch.setenv("IMMUTABLE_AUDIT_STORAGE_RESOURCE", "private-immutable-bucket")
    monkeypatch.setenv("IMMUTABLE_AUDIT_STORAGE_PREFIX", "audit-retention/")
    env_settings = Settings()
    monkeypatch.setattr(report_audit_retention_service, "settings", env_settings)

    status = report_audit_retention_service._immutable_storage_status()
    public = report_audit_retention_service._immutable_storage_public_status(status)

    assert status["status"] == "ready"
    assert status["mode"] == "cdk_managed"
    assert status["cdk_managed"] is True
    assert status["resource_configured"] is True
    assert status["prefix_configured"] is True
    assert status["missing"] == []
    assert public == {
        "status": "ready",
        "mode": "cdk_managed",
        "cdk_managed": True,
        "resource_configured": True,
        "prefix_configured": True,
        "missing": [],
    }
    assert "private-immutable-bucket" not in str(public)
    assert "audit-retention/" not in str(public)


def test_immutable_evidence_status_redacts_sensitive_request_id(monkeypatch):
    audit_rows = []
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: {"job_id": job_id, "status": "completed"})
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(report_repo, "list_recovery_job_audit_events", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(report_repo, "get_legal_hold_metadata", lambda scope_key: None)
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_audit_event",
        lambda manifest_id, event: audit_rows.append((manifest_id, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    status_response = client.post(
        "/admin/reports/immutable-evidence/status",
        json={"references": [{"scope": "recovery_job", "job_id": "job-1"}]},
        headers={"x-request-id": "access_token=abc123"},
    )
    persist_response = client.post(
        "/admin/reports/immutable-evidence/persist",
        json={"reason": "persist metadata", "references": [{"scope": "recovery_job", "job_id": "job-1"}]},
        headers={"x-request-id": "cookie=session123"},
    )

    assert status_response.status_code == 200
    assert persist_response.status_code == 200
    assert status_response.json()["request_id"] == "[private-credential]"
    assert audit_rows[-1][1]["correlation_id"] == "[private-credential]"
    _assert_no_private_artifact_markers(status_response.json())
    _assert_no_private_artifact_markers(persist_response.json())
    _assert_no_private_artifact_markers(audit_rows)


def test_immutable_manifest_persistence_refuses_without_cdk_config(monkeypatch):
    audit_rows = []
    manifest_rows = []
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: {"job_id": job_id, "status": "completed"})
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(report_repo, "list_recovery_job_audit_events", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_audit_event",
        lambda manifest_id, event: audit_rows.append((manifest_id, event)),
    )
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_manifest",
        lambda manifest_id, manifest: manifest_rows.append((manifest_id, manifest)) or True,
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/immutable-evidence/persist",
        json={
            "reason": "persist metadata weekly-reports/private/report.html",
            "references": [{"scope": "recovery_job", "job_id": "job-1"}],
        },
        headers={"x-request-id": "req-immutable-persist"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["immutable_storage"]["status"] == "not_configured"
    assert data["immutable_storage"]["reason"] == "immutable storage is not configured by CDK"
    assert data["reason"] == "persist metadata [report-artifact-key]"
    assert manifest_rows == []
    assert len(audit_rows) == 2
    assert audit_rows[-1][1]["action"] == "immutable_evidence_persist"
    assert audit_rows[-1][1]["result"] == "refused"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_rows)


def test_immutable_manifest_persistence_writes_reference_when_configured(monkeypatch):
    audit_rows = []
    manifest_rows = []
    manifest_updates = []
    object_writes = []
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: {"job_id": job_id, "status": "completed"})
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(report_repo, "list_recovery_job_audit_events", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_audit_event",
        lambda manifest_id, event: audit_rows.append((manifest_id, event)),
    )
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_manifest",
        lambda manifest_id, manifest: manifest_rows.append((manifest_id, manifest)) or True,
    )
    monkeypatch.setattr(
        report_repo,
        "update_audit_retention_manifest_status",
        lambda manifest_id, fields, expected_status: manifest_updates.append((manifest_id, fields, expected_status)) or True,
    )
    monkeypatch.setattr(
        report_audit_retention_service,
        "_write_immutable_manifest_object",
        lambda manifest, immutable_ref_id, storage_status: object_writes.append(
            (manifest, immutable_ref_id, storage_status)
        )
        or {"object_digest": "sha256:object-digest", "object_key_digest": "sha256:key-digest"},
    )
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_mode", "cdk_managed")
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_cdk_managed", True)
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_resource", "configured-resource")
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_prefix", "immutable-audit/")
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/immutable-evidence/persist",
        json={
            "reason": "persist metadata",
            "references": [{"scope": "recovery_job", "job_id": "job-1"}],
            "retention_category": "incident",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["immutable_storage"]["status"] == "persisted"
    assert data["immutable_storage"]["immutable_ref_id"].startswith("immutable-")
    assert data["immutable_storage"]["storage"]["status"] == "ready"
    assert data["immutable_storage"]["object_digest"] == "sha256:object-digest"
    assert len(object_writes) == 1
    assert object_writes[0][1] == data["immutable_storage"]["immutable_ref_id"]
    assert object_writes[0][2]["status"] == "ready"
    assert len(manifest_rows) == 1
    assert manifest_rows[0][0] == data["manifest_id"]
    assert manifest_rows[0][1]["status"] == "pending_object_write"
    assert manifest_rows[0][1]["manifest_digest"] == data["manifest_digest"]
    assert manifest_updates == [
        (
            data["manifest_id"],
            {
                "object_digest": "sha256:object-digest",
                "object_key_digest": "sha256:key-digest",
                "status": "persisted",
                "updated_at": manifest_updates[0][1]["updated_at"],
            },
            "pending_object_write",
        )
    ]
    assert "configured-resource" not in str(data)
    assert "immutable-audit/" not in str(data)
    assert audit_rows[-1][1]["result"] == "persisted"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(manifest_rows)


def test_immutable_manifest_persistence_refuses_duplicate_reference(monkeypatch):
    audit_rows = []
    object_writes = []
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: {"job_id": job_id, "status": "completed"})
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(report_repo, "list_recovery_job_audit_events", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_audit_event",
        lambda manifest_id, event: audit_rows.append((manifest_id, event)),
    )
    monkeypatch.setattr(report_repo, "put_audit_retention_manifest", lambda manifest_id, manifest: False)
    monkeypatch.setattr(
        report_audit_retention_service,
        "_write_immutable_manifest_object",
        lambda manifest, immutable_ref_id, storage_status: object_writes.append(
            (manifest, immutable_ref_id, storage_status)
        ),
    )
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_mode", "cdk_managed")
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_cdk_managed", True)
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_resource", "configured-resource")
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_prefix", "immutable-audit/")
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/immutable-evidence/persist",
        json={"reason": "persist metadata", "references": [{"scope": "recovery_job", "job_id": "job-1"}]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["immutable_storage"]["status"] == "refused"
    assert data["immutable_storage"]["reason"] == "immutable manifest reference already exists"
    assert data["immutable_storage"]["storage"]["status"] == "ready"
    assert object_writes == []
    assert audit_rows[-1][1]["result"] == "refused"
    assert "configured-resource" not in str(data)
    assert "immutable-audit/" not in str(data)
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_rows)


def test_immutable_manifest_persistence_refuses_when_object_write_fails(monkeypatch):
    audit_rows = []
    manifest_rows = []
    manifest_updates = []
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: {"job_id": job_id, "status": "completed"})
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(report_repo, "list_recovery_job_audit_events", lambda job_id, **kwargs: {"Items": []})
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_audit_event",
        lambda manifest_id, event: audit_rows.append((manifest_id, event)),
    )
    monkeypatch.setattr(
        report_repo,
        "put_audit_retention_manifest",
        lambda manifest_id, manifest: manifest_rows.append((manifest_id, manifest)) or True,
    )
    monkeypatch.setattr(
        report_repo,
        "update_audit_retention_manifest_status",
        lambda manifest_id, fields, expected_status: manifest_updates.append((manifest_id, fields, expected_status)) or True,
    )
    monkeypatch.setattr(
        report_audit_retention_service,
        "_write_immutable_manifest_object",
        lambda manifest, immutable_ref_id, storage_status: (_ for _ in ()).throw(RuntimeError("write failed")),
    )
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_mode", "cdk_managed")
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_cdk_managed", True)
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_resource", "configured-resource")
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_prefix", "immutable-audit/")
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/immutable-evidence/persist",
        json={"reason": "persist metadata", "references": [{"scope": "recovery_job", "job_id": "job-1"}]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["immutable_storage"]["status"] == "refused"
    assert data["immutable_storage"]["reason"] == "immutable object write failed"
    assert manifest_rows[0][1]["status"] == "pending_object_write"
    assert manifest_updates[0][1]["status"] == "refused"
    assert manifest_updates[0][2] == "pending_object_write"
    assert audit_rows[-1][1]["result"] == "refused"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(audit_rows)


def test_immutable_manifest_object_writer_uses_create_only_s3_and_byte_digest(monkeypatch):
    put_calls = []

    class FakeS3:
        def put_object(self, **kwargs):
            put_calls.append(kwargs)

    monkeypatch.setattr(report_audit_retention_service.boto3, "client", lambda *args, **kwargs: FakeS3())
    monkeypatch.setattr(report_audit_retention_service.settings, "aws_region", "eu-central-2")
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_resource", "immutable-bucket")
    monkeypatch.setattr(report_audit_retention_service.settings, "immutable_audit_storage_prefix", "immutable-audit/")
    manifest = {
        "schema_version": "v1",
        "manifest_id": "manifest-1",
        "generated_at": "2026-06-07T00:00:00+00:00",
        "generated_by": "admin-sub",
        "retention_category": "incident",
        "verification": {"manifest_digest": "sha256:manifest-digest"},
        "items": [],
    }

    result = report_audit_retention_service._write_immutable_manifest_object(
        manifest,
        immutable_ref_id="immutable-ref-1",
        storage_status={"status": "ready"},
    )

    assert len(put_calls) == 1
    put_call = put_calls[0]
    assert put_call["Bucket"] == "immutable-bucket"
    assert put_call["Key"] == "immutable-audit/immutable-ref-1.json"
    assert put_call["IfNoneMatch"] == "*"
    assert put_call["ServerSideEncryption"] == "AES256"
    assert put_call["ContentType"] == "application/vnd.stoa.audit-retention-manifest+json"
    assert result["object_digest"] == "sha256:" + hashlib.sha256(put_call["Body"]).hexdigest()
    assert result["object_key_digest"].startswith("sha256:")


def test_legal_hold_metadata_apply_and_status(monkeypatch):
    holds = {}
    hold_audits = []

    def put_hold(scope_key, hold, **kwargs):
        holds[scope_key] = hold
        return True

    monkeypatch.setattr(report_repo, "put_legal_hold_metadata", put_hold)
    monkeypatch.setattr(report_repo, "get_legal_hold_metadata", lambda scope_key: holds.get(scope_key))
    monkeypatch.setattr(
        report_repo,
        "put_legal_hold_audit_event",
        lambda scope_key, event: hold_audits.append((scope_key, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    apply_response = client.post(
        "/admin/reports/legal-holds",
        json={
            "reason": "case hold access_token=abc",
            "policy_id": "policy-incident",
            "references": [{"scope": "recovery_job", "job_id": "job-1"}],
        },
        headers={"x-request-id": "req-hold-apply"},
    )

    assert apply_response.status_code == 200
    apply_data = apply_response.json()
    assert apply_data["items"][0]["status"] == "active"
    assert apply_data["items"][0]["policy_id"] == "policy-incident"
    assert apply_data["items"][0]["reason"] == "case hold [private-credential]"
    assert apply_data["items"][0]["hold_version"] == 1
    assert len(holds) == 1
    assert hold_audits[0][1]["result"] == "recorded"

    status_response = client.post(
        "/admin/reports/legal-holds/status",
        json={"references": [{"scope": "recovery_job", "job_id": "job-1"}]},
    )

    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["items"][0]["status"] == "active"
    assert status_data["items"][0]["policy_id"] == "policy-incident"
    _assert_no_private_artifact_markers(apply_data)
    _assert_no_private_artifact_markers(status_data)
    _assert_no_private_artifact_markers(holds)
    _assert_no_private_artifact_markers(hold_audits)


def test_legal_hold_status_redacts_persisted_private_metadata(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_legal_hold_metadata",
        lambda scope_key: {
            "state": "active",
            "policy_id": "policy weekly-reports/private/report.html",
            "hold_id": "hold-1",
            "reason": "password=hunter2",
            "updated_at": "2026-06-07T00:00:00+00:00",
        },
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/legal-holds/status",
        json={"references": [{"scope": "recovery_job", "job_id": "job-1"}]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["policy_id"] == "policy [report-artifact-key]"
    assert data["items"][0]["reason"] == "[private-credential]"
    _assert_no_private_artifact_markers(data)


def test_legal_hold_release_preserves_hold_identity(monkeypatch):
    holds = {}
    hold_audits = []

    def put_hold(scope_key, hold, **kwargs):
        holds[scope_key] = hold
        return True

    monkeypatch.setattr(report_repo, "put_legal_hold_metadata", put_hold)
    monkeypatch.setattr(report_repo, "get_legal_hold_metadata", lambda scope_key: holds.get(scope_key))
    monkeypatch.setattr(
        report_repo,
        "put_legal_hold_audit_event",
        lambda scope_key, event: hold_audits.append((scope_key, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    apply_response = client.post(
        "/admin/reports/legal-holds",
        json={
            "reason": "case hold",
            "policy_id": "policy-incident",
            "references": [{"scope": "recovery_job", "job_id": "job-1"}],
        },
    )
    hold_id = apply_response.json()["items"][0]["hold_id"]
    release_response = client.post(
        "/admin/reports/legal-holds",
        json={
            "reason": "case released",
            "policy_id": "policy-incident",
            "action": "release",
            "references": [{"scope": "recovery_job", "job_id": "job-1"}],
        },
    )

    assert release_response.status_code == 200
    release_data = release_response.json()
    assert release_data["items"][0]["status"] == "released"
    assert release_data["items"][0]["hold_id"] == hold_id
    stored = next(iter(holds.values()))
    assert stored["hold_id"] == hold_id
    assert stored["created_by"] == "admin-sub"
    assert stored["state"] == "released"
    assert stored["released_by"] == "admin-sub"
    assert stored["hold_version"] == 2
    assert hold_audits[-1][1]["result"] == "recorded"
    _assert_no_private_artifact_markers(release_data)
    _assert_no_private_artifact_markers(holds)
    _assert_no_private_artifact_markers(hold_audits)


def test_legal_hold_metadata_refuses_stale_compare_and_set(monkeypatch):
    hold_audits = []
    existing = {
        "hold_id": "legal-hold-existing",
        "state": "active",
        "policy_id": "policy-incident",
        "reason": "case hold",
        "created_by": "admin-sub",
        "created_at": "2026-06-07T00:00:00+00:00",
        "updated_at": "2026-06-07T00:00:00+00:00",
        "hold_version": 3,
    }
    monkeypatch.setattr(report_repo, "get_legal_hold_metadata", lambda scope_key: existing)
    monkeypatch.setattr(report_repo, "put_legal_hold_metadata", lambda scope_key, hold, **kwargs: False)
    monkeypatch.setattr(
        report_repo,
        "put_legal_hold_audit_event",
        lambda scope_key, event: hold_audits.append((scope_key, event)),
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post(
        "/admin/reports/legal-holds",
        json={
            "reason": "case hold update",
            "policy_id": "policy-incident",
            "references": [{"scope": "recovery_job", "job_id": "job-1"}],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["status"] == "refused"
    assert data["items"][0]["reason"] == "legal hold metadata changed; refresh status and retry"
    assert hold_audits[-1][1]["result"] == "refused"
    _assert_no_private_artifact_markers(data)
    _assert_no_private_artifact_markers(hold_audits)


def test_recovery_evidence_recent_jobs_export_is_bounded(monkeypatch):
    calls = []
    next_key = {"PK": "REPORT_RECOVERY_JOB#job-2", "SK": "SUMMARY"}
    job = {
        "job_id": "job-1",
        "job_type": "resend_email",
        "status": "completed",
        "reason": "release evidence",
        "target_count": 1,
        "success_count": 1,
        "html_s3_key": "weekly-reports/private/report.html",
    }

    def list_jobs(**kwargs):
        calls.append(kwargs)
        return {"Items": [job], "LastEvaluatedKey": next_key}

    monkeypatch.setattr(report_repo, "list_recovery_jobs", list_jobs)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/recovery-evidence", params={"limit": 5, "status": "completed"})

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "recent_recovery_jobs"
    assert data["complete"] is False
    assert data["jobs"][0]["job_id"] == "job-1"
    assert report_repo.decode_recovery_job_page_token(data["next_tokens"]["jobs"]) == next_key
    assert calls == [{"limit": 5, "last_key": None}]
    _assert_no_private_artifact_markers(data)


def test_recovery_evidence_export_returns_404_for_missing_job(monkeypatch):
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: None)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get("/admin/reports/recovery-evidence", params={"job_id": "missing"})

    assert response.status_code == 404


def test_recovery_evidence_export_rejects_invalid_pagination_token(monkeypatch):
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: {"job_id": job_id, "status": "completed"})

    def fail(*args, **kwargs):
        raise AssertionError("invalid pagination token should stop before query")

    monkeypatch.setattr(report_repo, "list_recovery_job_targets", fail)
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get(
        "/admin/reports/recovery-evidence",
        params={"job_id": "job-1", "next_target_token": "bad"},
    )

    assert response.status_code == 400


def test_recovery_evidence_export_respects_include_flags(monkeypatch):
    calls = []
    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: {"job_id": job_id, "status": "completed"})
    monkeypatch.setattr(report_repo, "list_recovery_job_targets", lambda *args, **kwargs: calls.append("targets"))
    monkeypatch.setattr(report_repo, "list_recovery_job_audit_events", lambda *args, **kwargs: calls.append("audit"))
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get(
        "/admin/reports/recovery-evidence",
        params={"job_id": "job-1", "include_targets": False, "include_job_audit": False},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["targets"] == []
    assert data["job_audit"] == []
    assert data["complete"] is True
    assert calls == []
