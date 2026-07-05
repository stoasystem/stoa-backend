from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings, get_settings
from stoa.deps import get_current_user
from stoa.routers import admin
from stoa.services import external_activation_service


def _settings(**overrides) -> Settings:
    values = {"cognito_user_pool_id": "pool", "s3_images_bucket": "images", **overrides}
    return Settings(**values)


def _app_for_user(user: dict, settings: Settings | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: settings or _settings()
    return app


def _payment_readiness(**overrides):
    readiness = {
        "state": "live_enabled",
        "checkoutAllowed": True,
        "refundsAllowed": False,
        "providerMode": "live",
        "credentials": {
            "apiKeyMode": "live",
            "apiKey": "configured",
            "webhookSecretConfigured": True,
            "standardPriceConfigured": True,
            "premiumPriceConfigured": True,
        },
        "webhook": {"endpointMode": "https", "signingSecretConfigured": True},
        "twint": {"status": "eligible", "providerCapability": "active"},
        "finance": {"accountingExportAvailable": True},
        "refund": {"status": "rollout_disabled"},
        "rollout": {
            "checkout": {"state": "enabled", "allowed": True},
            "refunds": {"state": "disabled", "allowed": False},
            "providerReadiness": "ready",
            "activationState": "activated",
            "rollbackAvailable": True,
        },
        "blockers": [],
        "warnings": [],
    }
    readiness.update(overrides)
    return readiness


def test_payment_auth_smoke_blocks_missing_provider_and_cognito_config(monkeypatch):
    monkeypatch.setattr(
        external_activation_service.subscription_service,
        "get_provider_readiness",
        lambda settings: _payment_readiness(
            state="not_configured",
            checkoutAllowed=False,
            providerMode="missing",
            credentials={"apiKeyMode": "missing", "apiKey": "missing"},
            blockers=["missing_stripe_api_key", "missing_stripe_webhook_secret"],
        ),
    )
    client = TestClient(
        _app_for_user(
            {"sub": "admin-1", "role": "admin"},
            _settings(
                environment="production",
                cognito_user_pool_id="",
                cognito_student_client_id="",
                cognito_parent_client_id="",
                cognito_teacher_client_id="",
                cognito_admin_client_id="",
            ),
        )
    )

    response = client.get("/admin/external-activation/payment-auth-smoke")

    assert response.status_code == 200
    body = response.json()
    assert body["overallState"] == "blocked"
    assert body["safeToMutate"] is False
    assert body["payment"]["classification"] == "blocked"
    assert body["payment"]["smoke"]["customerMutationAllowed"] is False
    assert "missing_stripe_api_key" in body["blockers"]
    assert "missing_cognito_user_pool_id" in body["blockers"]
    assert "missing_cognito_parent_client_id" in body["blockers"]
    assert body["privacy"]["secretsRedacted"] is True


def test_payment_auth_smoke_reports_live_payment_and_blocked_email_delivery(monkeypatch):
    monkeypatch.setattr(
        external_activation_service.subscription_service,
        "get_provider_readiness",
        lambda settings: _payment_readiness(),
    )
    client = TestClient(
        _app_for_user(
            {"sub": "admin-1", "role": "admin"},
            _settings(
                environment="production",
                stripe_live_charges_enabled=True,
                cognito_user_pool_id="pool",
                cognito_student_client_id="student-client",
                cognito_parent_client_id="parent-client",
                cognito_teacher_client_id="teacher-client",
                cognito_admin_client_id="admin-client",
            ),
        )
    )

    response = client.get("/admin/external-activation/payment-auth-smoke")

    assert response.status_code == 200
    body = response.json()
    assert body["overallState"] == "read_only_verifiable"
    assert body["safeToMutate"] is False
    assert body["payment"]["classification"] == "live_ready"
    assert body["payment"]["safeToMutate"] is True
    assert body["cognitoEmail"]["classification"] == "locally_ready"
    assert body["cognitoEmail"]["localAuthBehavior"]["tokensBlockedUntilVerified"] is True
    assert body["cognitoEmail"]["liveDelivery"]["classification"] == "blocked"
    assert "approved_email_delivery_test_inbox_required" in body["blockers"]
    assert "production_cognito_email_delivery_smoke_not_recorded" in body["blockers"]
    assert "sk_live" not in response.text
    assert body["privacy"]["loginCodesIncluded"] is False


def test_payment_auth_smoke_is_admin_only(monkeypatch):
    monkeypatch.setattr(
        external_activation_service.subscription_service,
        "get_provider_readiness",
        lambda settings: _payment_readiness(),
    )
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))

    response = client.get("/admin/external-activation/payment-auth-smoke")

    assert response.status_code == 403
