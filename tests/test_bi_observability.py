from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings, get_settings
from stoa.deps import get_current_user
from stoa.routers import admin
from stoa.services import bi_observability_service


def _settings(**overrides) -> Settings:
    return Settings(cognito_user_pool_id="pool", s3_images_bucket="images", **overrides)


def _app_for_user(user: dict, settings: Settings | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: settings or _settings()
    return app


def _patch_sources(monkeypatch):
    monkeypatch.setattr(
        bi_observability_service.curriculum_analytics_service,
        "warehouse_readiness",
        lambda: {
            "state": "api-ready",
            "blockers": ["live_warehouse_not_configured"],
            "warnings": [],
            "privacy": {"aggregateOnly": True},
        },
    )
    monkeypatch.setattr(
        bi_observability_service.curriculum_analytics_service,
        "warehouse_export",
        lambda **kwargs: {
            "count": 1,
            "items": [
                {
                    "metricId": "exercise:public-1:v1",
                    "metrics": {"totalSignals": 7},
                    "publicId": "public-1",
                }
            ],
            "privacy": {"aggregateOnly": True},
        },
    )
    monkeypatch.setattr(
        bi_observability_service.curriculum_analytics_service,
        "operator_dashboard",
        lambda **kwargs: {
            "sampleSize": 1,
            "summary": {"totalSignals": 7, "qualityHotspots": 1},
            "emptyState": None,
            "privacy": {"aggregateOnly": True},
        },
    )
    monkeypatch.setattr(
        bi_observability_service.external_activation_service,
        "build_payment_auth_smoke_report",
        lambda settings: {
            "overallState": "read_only_verifiable",
            "payment": {"classification": "live_ready", "blockers": []},
            "cognitoEmail": {
                "classification": "locally_ready",
                "blockers": ["production_cognito_email_delivery_smoke_not_recorded"],
            },
            "blockers": ["production_cognito_email_delivery_smoke_not_recorded"],
            "warnings": [],
            "privacy": {"rawProviderPayloadsIncluded": False},
        },
    )
    monkeypatch.setattr(
        bi_observability_service.external_activation_service,
        "build_notification_support_smoke_report",
        lambda settings: {
            "overallState": "blocked",
            "notification": {"classification": "blocked", "blockers": ["missing_notification_push_provider"]},
            "support": {"classification": "read_only_verifiable", "blockers": []},
            "blockers": ["missing_notification_push_provider"],
            "warnings": [],
            "privacy": {"rawProviderPayloadsIncluded": False},
        },
    )
    monkeypatch.setattr(
        bi_observability_service.external_activation_service,
        "build_production_readiness_smoke_report",
        lambda settings: {
            "overallState": "locally_ready",
            "blockers": ["production_environment_not_selected"],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        bi_observability_service.notification_service,
        "delivery_status",
        lambda **kwargs: {
            "recentEventCount": 2,
            "websocketMode": "configured",
            "emailProvider": {"mode": "configured", "blockers": []},
            "pushProvider": {"mode": "disabled", "blockers": ["missing_notification_push_provider"]},
        },
    )
    monkeypatch.setattr(
        bi_observability_service.support_sla_service,
        "build_support_sla_analytics",
        lambda **kwargs: {
            "sample_size": 0,
            "status_counts": {},
            "provider": {"failure_count": 0},
            "retry": {"backlog_count": 0},
        },
    )
    monkeypatch.setattr(
        bi_observability_service.subscription_service,
        "get_provider_readiness",
        lambda settings: {
            "state": "live_ready_but_blocked",
            "checkoutAllowed": False,
            "refundsAllowed": False,
            "providerMode": "live",
            "blockers": ["stripe_live_charges_disabled"],
        },
    )


def test_bi_taxonomy_declares_privacy_boundary():
    contract = bi_observability_service.build_taxonomy_contract()

    assert "live_ready" in contract["taxonomy"]
    assert "unknown" in contract["taxonomy"]
    assert contract["privacy"]["aggregateOnly"] is True
    assert "provider_payload" in contract["privacy"]["forbiddenFields"]
    assert "verification_code" in contract["privacy"]["forbiddenFields"]


def test_bi_warehouse_export_is_idempotent_bounded_and_support_safe(monkeypatch):
    _patch_sources(monkeypatch)

    first = bi_observability_service.build_warehouse_export(
        settings=_settings(),
        period="2026-07-05",
        limit=10,
    )
    second = bi_observability_service.build_warehouse_export(
        settings=_settings(),
        period="2026-07-05",
        limit=10,
    )

    assert first["schemaVersion"] == "stoa.bi_observability.v1"
    assert first["idempotencyKey"] == second["idempotencyKey"]
    assert first["bounded"] is True
    assert first["count"] <= 10
    assert {row["productSurface"] for row in first["rows"]} >= {
        "curriculum_analytics",
        "release_smoke",
        "billing_provider",
        "notification_support",
    }
    assert first["privacy"]["rawStudentContentIncluded"] is False
    assert "raw answer" not in str(first).lower()
    assert "provider_payload" in first["privacy"]["forbiddenFields"]


def test_admin_bi_dashboard_exposes_blockers_without_private_payloads(monkeypatch):
    _patch_sources(monkeypatch)
    client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    response = client.get("/admin/bi/dashboard")

    assert response.status_code == 200
    body = response.json()
    sections = {section["name"]: section for section in body["sections"]}
    assert body["summary"]["sectionCount"] == 7
    assert sections["warehouse_export"]["state"] == "blocked"
    assert "live_bi_warehouse_not_configured" in sections["warehouse_export"]["blockers"]
    assert sections["usage_quota"]["aggregate"]["ledgerActions"] > 0
    assert body["privacy"]["rawProviderPayloadsIncluded"] is False
    assert "support-secret" not in response.text
    assert "student@example.com" not in response.text


def test_admin_bi_alert_routing_uses_low_cardinality_dimensions(monkeypatch):
    _patch_sources(monkeypatch)
    client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    response = client.get("/admin/bi/alert-routing")

    assert response.status_code == 200
    body = response.json()
    assert body["overallState"] == "blocked"
    assert "missing_apm_provider" in body["blockers"]
    route = next(item for item in body["routes"] if item["surface"] == "warehouse_export")
    assert route["alertClass"] == "provider_blocker"
    assert route["lowCardinalityDimensions"] == {
        "surface": "warehouse_export",
        "state": "blocked",
        "alertClass": "provider_blocker",
        "severity": "sev3",
    }
    assert "parent-1" not in response.text
    assert "student-1" not in response.text


def test_bi_routes_are_admin_only(monkeypatch):
    _patch_sources(monkeypatch)
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))

    response = client.get("/admin/bi/warehouse-readiness")

    assert response.status_code == 403
