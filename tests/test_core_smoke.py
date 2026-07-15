from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.routers import admin
from stoa.services import core_smoke_service
from actor_helpers import install_actor_overrides


def test_core_smoke_report_classifies_expected_blocks_without_private_payloads():
    report = core_smoke_service.build_core_smoke_report()
    checks = {item["check_id"]: item for item in report["checks"]}

    assert report["status"] == "ready_with_expected_blocks"
    assert report["summary"] == {
        "checkCount": 7,
        "passed": 1,
        "expectedBlocked": 6,
        "regressions": 0,
    }
    assert set(checks) == {
        "service-health",
        "auth-login",
        "parent-entitlement",
        "curriculum-read",
        "question-submit",
        "teacher-help",
        "admin-account-operations",
    }
    assert checks["service-health"]["status"] == "passed"
    assert checks["question-submit"]["expected_blocker"] == "student_auth_quota_or_ai_provider_required"
    assert checks["admin-account-operations"]["route"] == "/admin/account-operations/parents/{parent_id}"
    assert report["privacy"]["rawContentStored"] is False
    assert "raw student answer" not in str(report)
    assert "authorization" not in str(report).lower()


def test_admin_core_smoke_endpoint_requires_admin_and_returns_matrix():
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, {"sub": "admin-1", "role": "admin"})

    response = TestClient(app).get("/admin/core-smoke")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready_with_expected_blocks"
    assert body["summary"]["checkCount"] == 7
    assert body["checks"][0]["route"] == "/health"
