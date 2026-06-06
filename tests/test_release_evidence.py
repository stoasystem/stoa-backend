from __future__ import annotations

from argparse import Namespace
import importlib.util
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.db.repositories import report_repo
from stoa.deps import get_current_user
from stoa.routers import admin
from stoa.services import release_evidence_service


def _app_for_user(user: dict) -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _minimal_bundle() -> dict:
    section = {"status": "passed", "summary": "ok"}
    return {
        "schema_version": "v1",
        "milestone": "v2.3",
        "phase": 65,
        "generated_at": "2026-06-06T21:00:00+00:00",
        "environment": "production",
        "backend": {"status": "passed", "commit_sha": "abc123", "deploy_run_id": "run-1"},
        "frontend": {"status": "passed", "commit_sha": "def456", "deploy_run_id": "run-2"},
        "infra": {"status": "passed", "cdk_diff": "lambda code asset drift only"},
        "api_checks": [section],
        "browser_smoke": section,
        "privacy": {"status": "passed", "denylist_checked": True},
        "quality_gates": [section],
    }


def _fixture_report() -> dict:
    return {
        "report_id": "report-safe-fixture",
        "parent_id": "safe-fixture-parent-v2-2",
        "student_id": "safe-fixture-student-v2-2",
        "week_start": "2026-06-01",
        "status": "email_sent",
        "email_status": "sent",
        "artifact_version_id": "original",
        "previous_artifact_version_id": "v20260606T184730Z-cb0b33d1",
        "json_s3_key": "weekly-reports/private/report.json",
        "html_s3_key": "weekly-reports/private/report.html",
        "last_operation": "rollback_report_artifact",
        "updated_at": "2026-06-06T18:50:00+00:00",
    }


def _assert_no_private_markers(data):
    serialized = json.dumps(data, sort_keys=True)
    assert "weekly-reports/" not in serialized
    assert "json_s3_key" not in serialized
    assert "html_s3_key" not in serialized
    assert "presignedUrl" not in serialized
    assert "presigned_url" not in serialized
    assert "<html" not in serialized


def _load_script():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "release_evidence.py"
    spec = importlib.util.spec_from_file_location("release_evidence", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_release_bundle_passes_minimal_metadata_bundle():
    result = release_evidence_service.validate_release_bundle(_minimal_bundle())

    assert result["status"] == "passed"
    assert result["missing_required_fields"] == []
    assert result["privacy"]["passed"] is True


def test_validate_release_bundle_fails_closed_on_private_markers():
    bundle = _minimal_bundle()
    bundle["backend"]["json_s3_key"] = "weekly-reports/parent/student/week/report.json"

    result = release_evidence_service.validate_release_bundle(bundle)

    assert result["status"] == "failed"
    assert result["privacy"]["violation_count"] >= 1
    assert "json_s3_key" not in result["bundle"]["backend"]
    _assert_no_private_markers(result["bundle"])


def test_fixture_inventory_is_sanitized_and_ready():
    result = release_evidence_service.build_fixture_inventory_response(
        fixture_name="stoa-safe-fixture-v2-2-rollback-2026-06-06",
        report=_fixture_report(),
        audit_events=[
            {
                "event_id": "event-1",
                "event_at": "2026-06-06T18:50:00+00:00",
                "action": "apply_report_artifact_rollback",
                "result": "success",
                "after": {"json_s3_key": "weekly-reports/private/report.json"},
            }
        ],
    )

    assert result["status"] == "ready"
    assert result["artifact_versions"]["current"] == "original"
    assert result["privacy"]["passed"] is True
    _assert_no_private_markers(result)


def test_mutation_refusal_requires_approved_fixture_mode_and_ready_status():
    assert release_evidence_service.mutation_refusal_reasons(
        fixture_name=None,
        mutation_mode=None,
        fixture_status="ready",
    ) == ["missing fixture name", "missing mutation mode"]
    assert release_evidence_service.mutation_refusal_reasons(
        fixture_name="unknown",
        mutation_mode="artifact_edit_rollback",
        fixture_status="ready",
    ) == ["fixture name is not approved"]
    assert release_evidence_service.mutation_refusal_reasons(
        fixture_name="stoa-safe-fixture-v2-2-rollback-2026-06-06",
        mutation_mode="artifact_edit_rollback",
        fixture_status="dirty",
    ) == ["fixture status dirty is not mutation-ready"]


def test_release_evidence_validate_endpoint_is_admin_only():
    client = TestClient(_app_for_user({"sub": "parent-sub", "role": "parent"}))

    response = client.post("/admin/reports/release-evidence/validate", json=_minimal_bundle())

    assert response.status_code == 403


def test_release_evidence_validate_endpoint_returns_redacted_result():
    bundle = _minimal_bundle()
    bundle["frontend"]["raw_html"] = "<html>private</html>"
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.post("/admin/reports/release-evidence/validate", json=bundle)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["privacy"]["violation_count"] >= 1
    _assert_no_private_markers(data["bundle"])


def test_fixture_status_endpoint_returns_sanitized_inventory(monkeypatch):
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: _fixture_report(),
    )
    monkeypatch.setattr(
        report_repo,
        "list_report_audit_events",
        lambda report_id, limit=10, last_key=None: {
            "Items": [
                {
                    "event_id": "event-1",
                    "event_at": "2026-06-06T18:50:00+00:00",
                    "action": "apply_report_artifact_rollback",
                    "result": "success",
                }
            ]
        },
    )
    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))

    response = client.get(
        "/admin/reports/release-evidence/fixture-status",
        params={"fixture_name": "stoa-safe-fixture-v2-2-rollback-2026-06-06"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["privacy"]["passed"] is True
    _assert_no_private_markers(data)


def test_release_evidence_cli_validate_returns_failure_for_private_markers(tmp_path):
    script = _load_script()
    bundle = _minimal_bundle()
    bundle["backend"]["json_s3_key"] = "weekly-reports/private/report.json"
    input_path = tmp_path / "bundle.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(json.dumps(bundle), encoding="utf-8")

    status = script.command_validate(Namespace(input=str(input_path), output=str(output_path)))

    assert status == 2
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    _assert_no_private_markers(result["bundle"])
