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


def test_notification_support_smoke_blocks_missing_provider_configuration():
    client = TestClient(
        _app_for_user(
            {"sub": "admin-1", "role": "admin"},
            _settings(
                websocket_api_endpoint="",
                notification_email_provider="",
                notification_push_provider="",
                support_internal_queue_approved=False,
                support_third_party_provider_approved=False,
                support_third_party_provider_api_key="",
                support_third_party_provider_endpoint_url="",
                support_crm_messaging_approved=False,
                support_crm_destination_approved=False,
                support_crm_approved_templates=[],
            ),
        )
    )

    response = client.get("/admin/external-activation/notification-support-smoke")

    assert response.status_code == 200
    body = response.json()
    assert body["overallState"] == "blocked"
    assert body["safeToMutate"] is False
    assert body["notification"]["classification"] == "blocked"
    assert body["support"]["classification"] == "blocked"
    assert "missing_notification_email_provider" in body["blockers"]
    assert "missing_notification_push_provider" in body["blockers"]
    assert "support_internal_queue_not_approved" in body["blockers"]
    assert "support_third_party_provider_not_approved" in body["blockers"]
    assert "support_crm_messaging_not_approved" in body["blockers"]
    assert body["privacy"]["rawProviderPayloadsIncluded"] is False


def test_notification_support_smoke_reports_configured_read_only_until_send_flags_enabled():
    client = TestClient(
        _app_for_user(
            {"sub": "admin-1", "role": "admin"},
            _settings(
                websocket_api_endpoint="wss://ws.example.test/dev",
                websocket_live_routes_configured=True,
                websocket_live_deployed=True,
                websocket_live_smoke_passed=True,
                notification_email_provider="ses",
                notification_email_provider_approved=True,
                notification_email_send_enabled=False,
                notification_push_provider="native-relay",
                notification_push_provider_approved=True,
                notification_push_provider_api_key="push-secret",
                notification_push_provider_endpoint_url="https://push.example.test/send",
                notification_push_send_enabled=False,
                support_internal_queue_approved=True,
                support_third_party_provider_approved=True,
                support_third_party_provider_api_key="support-secret",
                support_third_party_provider_endpoint_url="https://support.example.test/tickets",
                support_crm_messaging_approved=True,
                support_crm_destination_approved=True,
                support_crm_approved_templates=["support_receipt", "status_update"],
            ),
        )
    )

    response = client.get("/admin/external-activation/notification-support-smoke")

    assert response.status_code == 200
    body = response.json()
    assert body["overallState"] == "read_only_verifiable"
    assert body["safeToMutate"] is False
    assert body["notification"]["classification"] == "read_only_verifiable"
    assert body["notification"]["emailDigest"]["classification"] == "read_only_verifiable"
    assert "notification_email_send_disabled" in body["warnings"]
    assert "notification_push_send_disabled" in body["warnings"]
    assert body["support"]["classification"] == "live_ready"
    assert body["support"]["thirdPartyProvider"]["retryMaxAttempts"] == 3
    assert body["support"]["deliveryLifecycle"]["retrySupported"] is True
    assert "push-secret" not in response.text
    assert "support-secret" not in response.text


def test_notification_support_smoke_reports_live_ready_when_all_provider_flags_enabled():
    client = TestClient(
        _app_for_user(
            {"sub": "admin-1", "role": "admin"},
            _settings(
                websocket_api_endpoint="wss://ws.example.test/dev",
                websocket_live_routes_configured=True,
                websocket_live_deployed=True,
                websocket_live_smoke_passed=True,
                notification_email_provider="ses",
                notification_email_provider_approved=True,
                notification_email_send_enabled=True,
                notification_push_provider="native-relay",
                notification_push_provider_approved=True,
                notification_push_provider_api_key="push-secret",
                notification_push_provider_endpoint_url="https://push.example.test/send",
                notification_push_send_enabled=True,
                support_internal_queue_approved=True,
                support_third_party_provider_approved=True,
                support_third_party_provider_api_key="support-secret",
                support_third_party_provider_endpoint_url="https://support.example.test/tickets",
                support_crm_messaging_approved=True,
                support_crm_destination_approved=True,
                support_crm_approved_templates=["support_receipt", "status_update"],
            ),
        )
    )

    response = client.get("/admin/external-activation/notification-support-smoke")

    assert response.status_code == 200
    body = response.json()
    assert body["overallState"] == "live_ready"
    assert body["safeToMutate"] is True
    assert body["notification"]["safeToMutate"] is True
    assert body["support"]["safeToMutate"] is True
    assert body["blockers"] == []


def test_notification_support_smoke_is_admin_only():
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))

    response = client.get("/admin/external-activation/notification-support-smoke")

    assert response.status_code == 403
