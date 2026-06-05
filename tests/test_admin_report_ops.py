import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.db.repositories import report_repo
from stoa.deps import get_current_user
from stoa.routers import admin
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
