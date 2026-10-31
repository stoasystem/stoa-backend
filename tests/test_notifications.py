import re
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings
from stoa.routers import notifications, teachers
from stoa.db.repositories import question_repo, user_repo
from stoa.services import (
    locale_service,
    message_catalog,
    notification_service,
    teacher_assistance_service,
    websocket_service,
)
from actor_helpers import install_actor_overrides


def _app(router, prefix: str, user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    install_actor_overrides(app, user)
    return TestClient(app)


def _install_notification_repo(monkeypatch):
    events: dict[str, dict] = {}
    preferences: dict[str, dict] = {}

    def put_event(item):
        stored = dict(item)
        if stored.get("owner_classification") == "private_owner":
            stored["account_fence_generation"] = int(
                stored.get("account_fence_generation") or 1
            )
        events[item["event_id"]] = stored
        return stored

    def get_event(event_id):
        return events.get(event_id)

    def list_events(limit=100):
        return list(events.values())[:limit]

    def update_event(event_id, updates):
        events[event_id].update(updates)
        return events[event_id]

    def put_preferences(item):
        preferences[item["user_id"]] = dict(item)

    def get_preferences(user_id):
        return preferences.get(user_id)

    monkeypatch.setattr(notification_service.notification_repo, "put_event", put_event)
    monkeypatch.setattr(notification_service.notification_repo, "get_event", get_event)
    monkeypatch.setattr(
        notification_service.notification_repo,
        "load_delivery_event_strong",
        get_event,
    )
    monkeypatch.setattr(notification_service.notification_repo, "list_events", list_events)
    monkeypatch.setattr(notification_service.notification_repo, "update_event", update_event)
    monkeypatch.setattr(notification_service.notification_repo, "put_preferences", put_preferences)
    monkeypatch.setattr(notification_service.notification_repo, "get_preferences", get_preferences)
    monkeypatch.setattr(
        notification_service.account_deletion_repo,
        "require_active_account_fence",
        lambda _owner_id, generation=None, **_kwargs: {
            "status": "active",
            "generation": int(generation or 1),
        },
    )

    def run_authoritative_delivery(**kwargs):
        try:
            kwargs["provider_call"]()
        except Exception:
            return {
                "status": "provider_acceptance_unknown",
                "delivery_id": "delivery-test",
            }
        return {"status": "accepted", "delivery_id": "delivery-test"}

    monkeypatch.setattr(
        notification_service,
        "run_authoritative_delivery",
        run_authoritative_delivery,
    )
    return events, preferences


def _install_push_token_repo(monkeypatch):
    tokens: dict[tuple[str, str], dict] = {}

    def put_push_token(item):
        tokens[(item["user_id"], item["token_reference"])] = dict(item)

    def get_push_token(user_id, token_reference):
        return tokens.get((user_id, token_reference))

    def list_push_tokens(user_id=None, *, status=None, limit=100):
        values = list(tokens.values())
        if user_id is not None:
            values = [token for token in values if token["user_id"] == user_id]
        if status is not None:
            values = [token for token in values if token["status"] == status]
        return values[:limit]

    def update_push_token(user_id, token_reference, updates):
        item = tokens.get((user_id, token_reference))
        if not item:
            return None
        item.update(updates)
        return item

    monkeypatch.setattr(notification_service.notification_repo, "put_push_token", put_push_token)
    monkeypatch.setattr(notification_service.notification_repo, "get_push_token", get_push_token)
    monkeypatch.setattr(notification_service.notification_repo, "list_push_tokens", list_push_tokens)
    monkeypatch.setattr(notification_service.notification_repo, "update_push_token", update_push_token)
    return tokens


def _notification_provider_settings(**overrides):
    defaults = {
        "notification_email_provider": "ses",
        "notification_email_provider_approved": True,
        "notification_email_send_enabled": True,
        "notification_push_provider": "native-relay",
        "notification_push_provider_approved": True,
        "notification_push_provider_endpoint_url": "https://push.example.test/send",
        "notification_push_send_enabled": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_notifications_list_read_and_archive_visible_events(monkeypatch):
    _install_notification_repo(monkeypatch)
    direct = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
        metadata={"subject": "math"},
        created_at="2026-06-08T10:00:00+00:00",
    )
    notification_service.create_event(
        recipient_id=None,
        recipient_role="admin",
        event_type="moderation_case_update",
        target_type="moderation_case",
        target_id="case-1",
        title="Moderation",
        summary="Case updated.",
        owner_id="admin-1",
        created_at="2026-06-08T09:00:00+00:00",
    )

    client = _app(notifications.router, "/notifications", {"sub": "student-1", "role": "student"})
    listed = client.get("/notifications")

    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["items"][0]["eventId"] == direct["eventId"]

    read = client.post(f"/notifications/{direct['eventId']}/read")
    assert read.status_code == 200
    assert read.json()["status"] == "read"
    assert read.json()["readAt"]

    archived = client.post(f"/notifications/{direct['eventId']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    assert client.get("/notifications").json()["count"] == 0
    assert client.get("/notifications?status=archived").json()["count"] == 1


def test_notification_mark_requires_visible_event(monkeypatch):
    _install_notification_repo(monkeypatch)
    event = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )

    client = _app(notifications.router, "/notifications", {"sub": "student-2", "role": "student"})
    response = client.post(f"/notifications/{event['eventId']}/read")

    assert response.status_code == 404


def test_admin_can_list_operational_notifications(monkeypatch):
    _install_notification_repo(monkeypatch)
    notification_service.create_event(
        recipient_id=None,
        recipient_role="admin",
        event_type="subscription_request_update",
        target_type="subscription_request",
        target_id="subreq-1",
        title="Subscription request updated",
        summary="Subscription request status is requested.",
        owner_id="admin-1",
    )

    client = _app(notifications.admin_router, "/admin", {"sub": "admin-1", "role": "admin"})
    response = client.get("/admin/notifications?event_type=subscription_request_update")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["items"][0]["eventType"] == "subscription_request_update"


def test_notification_preferences_default_and_update(monkeypatch):
    _, preferences = _install_notification_repo(monkeypatch)
    client = _app(notifications.router, "/notifications", {"sub": "student-1", "role": "student"})

    default_response = client.get("/notifications/preferences")
    assert default_response.status_code == 200
    default_body = default_response.json()
    assert default_body["preferences"]["teacher_responses"]["in_app"] is True
    assert default_body["preferences"]["teacher_responses"]["realtime"] is True
    assert default_body["preferences"]["teacher_responses"]["email_digest"] is False

    update_response = client.patch(
        "/notifications/preferences",
        json={"preferences": {"teacher_responses": {"realtime": False, "email_digest": True}}},
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["preferences"]["teacher_responses"]["realtime"] is False
    assert body["preferences"]["teacher_responses"]["email_digest"] is True
    assert body["preferences"]["teacher_responses"]["in_app"] is True
    assert preferences["student-1"]["preferences"]["teacher_responses"]["realtime"] is False


def test_notification_preferences_reject_invalid_channel(monkeypatch):
    _install_notification_repo(monkeypatch)
    client = _app(notifications.router, "/notifications", {"sub": "student-1", "role": "student"})

    response = client.patch(
        "/notifications/preferences",
        json={"preferences": {"teacher_responses": {"sms": True}}},
    )

    assert response.status_code == 400


def test_delivery_decision_honors_realtime_preference(monkeypatch):
    events, preferences = _install_notification_repo(monkeypatch)
    sent = []
    monkeypatch.setattr(
        notification_service.websocket_service,
        "fanout_notification_event_safe",
        lambda item: sent.append(item) or {"deliveryId": "ws-1"},
    )
    preferences["student-1"] = {
        "user_id": "student-1",
        "preferences": notification_service.default_preferences(),
    }
    preferences["student-1"]["preferences"]["teacher_responses"]["realtime"] = False
    preferences["student-1"]["preferences"]["teacher_responses"]["email_digest"] = True

    event = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )

    assert sent == []
    stored = events[event["eventId"]]
    decision = stored["metadata"]["delivery_decision"]
    assert decision["category"] == "teacher_responses"
    assert decision["channels"]["in_app"]["decision"] == "stored"
    assert decision["channels"]["realtime"]["decision"] == "skipped_preference"
    assert decision["channels"]["email_digest"]["decision"] == "deferred_digest"
    assert event["deliveryChannels"]["realtime"]["decision"] == "skipped_preference"


def test_create_event_binds_a_generation_the_table_returned(monkeypatch):
    """Callers hand create_event a generation they read off a row.

    The resource interface returns it as `Decimal`, and dropping it leaves the
    event unowned - which is what keeps a deletion from ever reaching it.
    """
    events, _preferences = _install_notification_repo(monkeypatch)

    event = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
        owner_id="student-1",
        account_fence_generation=Decimal(7),
    )
    stored = events[event["eventId"]]

    assert stored["owner_classification"] == "private_owner"
    assert stored["account_fence_generation"] == 7

    # Negative control: reading the stored shape is not reading anything.
    for malformed in ("7", True, Decimal("7.5"), 0):
        other = notification_service.create_event(
            recipient_id="student-1",
            recipient_role="student",
            event_type="teacher_reply",
            target_type="question",
            target_id="question-1",
            title="Teacher replied",
            summary="Your teacher added a reply.",
            owner_id="student-1",
            account_fence_generation=malformed,
        )
        assert events[other["eventId"]]["account_fence_generation"] != 7


def test_admin_delivery_status_summarizes_recent_decisions(monkeypatch):
    _install_notification_repo(monkeypatch)
    notification_service.create_event(
        recipient_id=None,
        recipient_role="admin",
        event_type="moderation_case_update",
        target_type="moderation_case",
        target_id="case-1",
        title="Moderation",
        summary="Case updated.",
        owner_id="admin-1",
    )
    client = _app(notifications.admin_router, "/admin", {"sub": "admin-1", "role": "admin"})

    response = client.get("/admin/notifications/delivery-status")

    assert response.status_code == 200
    body = response.json()
    assert body["recentEventCount"] == 1
    assert body["categoryCounts"]["admin_operations"] == 1
    assert "realtime" in body["preferenceChannels"]
    assert body["websocketMode"] == "local_only"
    assert "websocket_api_endpoint_missing" in body["websocketReadiness"]["configurationBlockers"]


def test_admin_delivery_status_reports_live_ready_websocket_without_secrets(monkeypatch):
    events, _ = _install_notification_repo(monkeypatch)
    test_settings = Settings(
        websocket_api_endpoint="https://abc123.execute-api.eu-central-2.amazonaws.com/prod?token=secret",
        websocket_live_routes_configured=True,
        websocket_live_deployed=True,
        websocket_live_smoke_passed=True,
    )
    monkeypatch.setattr(notification_service, "settings", test_settings)
    monkeypatch.setattr(websocket_service, "settings", test_settings)
    monkeypatch.setattr(
        websocket_service.websocket_repo,
        "list_connections",
        lambda limit=200: [
            {
                "connection_id": "fresh-conn",
                "expires_at": websocket_service.now_epoch() + 30,
            },
            {
                "connection_id": "stale-conn",
                "expires_at": websocket_service.now_epoch() - 30,
            },
        ][:limit],
    )
    events["notif-live"] = {
        "event_id": "notif-live",
        "recipient_id": "student-1",
        "recipient_role": "student",
        "event_type": "teacher_reply",
        "target_type": "question",
        "target_id": "question-1",
        "title": "Teacher replied",
        "summary": "Your teacher added a reply.",
        "status": "created",
        "created_at": "2026-06-14T10:00:00+00:00",
        "metadata": {
            "delivery_decision": notification_service.delivery_decision(
                category="teacher_responses",
                preferences=notification_service.default_preferences(),
                realtime_configured=True,
            ),
            "websocket_delivery_attempts": [
                {
                    "delivery_id": "ws-live",
                    "attempted_at": "2026-06-14T10:00:01+00:00",
                    "target_channels": ["role:student", "user:student-1"],
                    "target_count": 2,
                    "results": [
                        {"connection_id": "fresh-conn", "status": "delivered"},
                        {"connection_id": "stale-conn", "status": "stale_removed"},
                    ],
                }
            ],
        },
        "category": "teacher_responses",
    }

    client = _app(notifications.admin_router, "/admin", {"sub": "admin-1", "role": "admin"})
    response = client.get("/admin/notifications/delivery-status")

    assert response.status_code == 200
    body = response.json()
    assert body["websocketConfigured"] is True
    assert body["websocketMode"] == "live_ready"
    assert body["websocketReadiness"]["endpointHost"] == "abc123.execute-api.eu-central-2.amazonaws.com"
    assert body["websocketReadiness"]["connectionStatus"]["activeConnectionCount"] == 1
    assert body["websocketReadiness"]["connectionStatus"]["staleConnectionCount"] == 1
    assert body["websocketReadiness"]["configurationBlockers"] == []
    assert body["deliveryAttemptCounts"] == {"delivered": 1, "stale_removed": 1}
    assert body["recentDeliveryAttempts"][0]["resultCounts"] == {
        "delivered": 1,
        "stale_removed": 1,
    }
    serialized = str(body)
    assert "token=secret" not in serialized
    assert "fresh-conn" not in serialized
    assert "stale-conn" not in serialized


def test_digest_preview_selects_digest_enabled_unread_notifications(monkeypatch):
    events, preferences = _install_notification_repo(monkeypatch)
    prefs = notification_service.default_preferences()
    prefs["teacher_responses"]["email_digest"] = True
    prefs["teacher_responses"]["push"] = True
    preferences["student-1"] = {
        "user_id": "student-1",
        "preferences": prefs,
    }
    created = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
        metadata={
            "subject": "math",
            "html_s3_key": "weekly-reports/private/report.html",
            "safe_count": 1,
        },
        created_at="2026-06-11T10:00:00+00:00",
    )
    notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="learning_profile_update",
        target_type="learning_profile",
        target_id="student-1",
        title="Profile updated",
        summary="Learning profile changed.",
        created_at="2026-06-11T11:00:00+00:00",
    )
    events[created["eventId"]]["status"] = "created"

    client = _app(notifications.router, "/notifications", {"sub": "student-1", "role": "student"})
    response = client.get("/notifications/digest-preview?category=teacher_responses")

    assert response.status_code == 200
    body = response.json()
    assert body["deliveryMode"] == "preview_only"
    assert body["emailProviderConfigured"] is False
    assert body["pushProviderConfigured"] is False
    assert body["pushPreferencesSupported"] is True
    assert body["count"] == 1
    assert body["items"][0]["eventId"] == created["eventId"]
    assert body["items"][0]["metadata"] == {"subject": "math", "safe_count": 1}


def test_digest_preview_requires_digest_preference(monkeypatch):
    _install_notification_repo(monkeypatch)
    notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )
    client = _app(notifications.router, "/notifications", {"sub": "student-1", "role": "student"})

    response = client.get("/notifications/digest-preview")

    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_digest_send_refuses_unconfigured_provider_and_records_evidence(monkeypatch):
    events, preferences = _install_notification_repo(monkeypatch)
    prefs = notification_service.default_preferences()
    prefs["teacher_responses"]["email_digest"] = True
    preferences["student-1"] = {"user_id": "student-1", "preferences": prefs}
    created = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )

    result = notification_service.send_digest(
        {"sub": "student-1", "role": "student", "email": "student@example.com"},
        category="teacher_responses",
    )

    assert result["status"] == "refused_provider_not_ready"
    attempts = events[created["eventId"]]["metadata"]["email_digest_delivery_attempts"]
    assert attempts[0]["status"] == "refused_provider_not_ready"
    assert attempts[0]["recipient_email_hash"]
    assert "student@example.com" not in str(result)


def test_digest_send_selects_enabled_items_and_redacts_provider_result(monkeypatch):
    events, preferences = _install_notification_repo(monkeypatch)
    monkeypatch.setattr(notification_service, "settings", _notification_provider_settings())
    prefs = notification_service.default_preferences()
    prefs["teacher_responses"]["email_digest"] = True
    preferences["student-1"] = {"user_id": "student-1", "preferences": prefs}
    created = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )
    sent = []

    def send_func(payload):
        sent.append(payload)
        return {"messageId": "msg-1", "apiKey": "provider-secret"}

    result = notification_service.send_digest(
        {"sub": "student-1", "role": "student", "email": "student@example.com"},
        category="teacher_responses",
        send_func=send_func,
    )

    assert result["status"] == "sent"
    assert result["eventIds"] == [created["eventId"]]
    assert sent[0]["recipientEmail"] == "student@example.com"
    assert events[created["eventId"]]["metadata"]["email_digest_delivery_attempts"][0]["status"] == "sent"
    assert "provider-secret" not in str(result)
    assert result["providerResult"] == {}


def test_digest_send_honors_email_digest_opt_out(monkeypatch):
    _install_notification_repo(monkeypatch)
    monkeypatch.setattr(notification_service, "settings", _notification_provider_settings())
    notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )

    result = notification_service.send_digest(
        {"sub": "student-1", "role": "student", "email": "student@example.com"},
        category="teacher_responses",
        send_func=lambda payload: (_ for _ in ()).throw(AssertionError("send should not run")),
    )

    assert result["status"] == "refused_no_digest_items"
    assert result["itemCount"] == 0


def test_push_token_registration_and_revocation_redacts_raw_token(monkeypatch):
    _install_push_token_repo(monkeypatch)
    client = _app(notifications.router, "/notifications", {"sub": "student-1", "role": "student"})

    response = client.post(
        "/notifications/push-tokens",
        json={
            "platform": "ios",
            "token": "native-token-secret",
            "providerTokenReference": "provider-token-ref",
            "deviceId": "device-secret",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "ios"
    assert body["status"] == "active"
    assert body["hasProviderReference"] is True
    assert "native-token-secret" not in response.text
    revoked = client.delete(f"/notifications/push-tokens/{body['tokenReference']}")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_push_token_reference_is_hidden_from_unrelated_actor(monkeypatch):
    _install_push_token_repo(monkeypatch)
    owner = _app(notifications.router, "/notifications", {"sub": "student-1", "role": "student"})
    created = owner.post(
        "/notifications/push-tokens",
        json={"platform": "ios", "providerTokenReference": "provider-owned-reference"},
    ).json()
    other = _app(notifications.router, "/notifications", {"sub": "student-2", "role": "student"})

    denied = other.delete(f"/notifications/push-tokens/{created['tokenReference']}")
    collision = other.post(
        "/notifications/push-tokens",
        json={"platform": "ios", "providerTokenReference": "provider-owned-reference"},
    )

    assert denied.status_code == 404
    assert collision.status_code == 404
    assert owner.delete(f"/notifications/push-tokens/{created['tokenReference']}").status_code == 200


def test_notification_event_missing_and_authorization_outage_fail_before_mutation(monkeypatch):
    events, _ = _install_notification_repo(monkeypatch)
    client = _app(notifications.router, "/notifications", {"sub": "student-1", "role": "student"})
    assert client.post("/notifications/missing/read").status_code == 404

    updates = []
    monkeypatch.setattr(
        notification_service.notification_repo,
        "get_event",
        lambda event_id: (_ for _ in ()).throw(RuntimeError("store unavailable")),
    )
    monkeypatch.setattr(
        notification_service.notification_repo,
        "update_event",
        lambda event_id, values: updates.append((event_id, values)),
    )
    response = client.post("/notifications/notif-1/archive")
    assert response.status_code == 503
    assert updates == []
    assert events == {}


def test_push_delivery_records_missing_token_without_breaking_event(monkeypatch):
    events, preferences = _install_notification_repo(monkeypatch)
    _install_push_token_repo(monkeypatch)
    monkeypatch.setattr(notification_service, "settings", _notification_provider_settings())
    prefs = notification_service.default_preferences()
    prefs["teacher_responses"]["push"] = True
    preferences["student-1"] = {"user_id": "student-1", "preferences": prefs}

    event = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )

    attempts = events[event["eventId"]]["metadata"]["push_delivery_attempts"]
    assert attempts[0]["status"] == "refused_missing_token"
    assert event["status"] == "created"


def test_push_delivery_records_success_and_provider_failure_redacted(monkeypatch):
    events, preferences = _install_notification_repo(monkeypatch)
    _install_push_token_repo(monkeypatch)
    monkeypatch.setattr(notification_service, "settings", _notification_provider_settings())
    prefs = notification_service.default_preferences()
    prefs["teacher_responses"]["push"] = True
    preferences["student-1"] = {"user_id": "student-1", "preferences": prefs}
    notification_service.register_push_token(
        {"sub": "student-1", "role": "student"},
        platform="ios",
        provider_token_reference="provider-token-secret",
    )
    monkeypatch.setattr(
        notification_service,
        "_send_push_provider",
        lambda payload: {"messageId": "push-token-secret"},
    )
    success = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-success",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )

    assert events[success["eventId"]]["metadata"]["push_delivery_attempts"][0]["status"] == "sent"
    assert "provider-token-secret" not in str(events[success["eventId"]]["metadata"])
    assert "push-token-secret" not in str(events[success["eventId"]]["metadata"])

    def fail_push(payload):
        raise RuntimeError("push failed with provider-token-secret")

    monkeypatch.setattr(notification_service, "_send_push_provider", fail_push)
    failed = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-failed",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )

    failure_attempt = events[failed["eventId"]]["metadata"]["push_delivery_attempts"][0]
    assert failure_attempt["status"] == "provider_acceptance_unknown"
    assert failure_attempt["provider_result"] == {}
    assert "provider-token-secret" not in str(failure_attempt)


def test_digest_preview_filters_by_time_window(monkeypatch):
    _events, preferences = _install_notification_repo(monkeypatch)
    prefs = notification_service.default_preferences()
    prefs["teacher_responses"]["email_digest"] = True
    preferences["student-1"] = {
        "user_id": "student-1",
        "preferences": prefs,
    }
    older = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Older reply",
        summary="This reply is before the digest window.",
        created_at="2026-06-10T10:00:00+00:00",
    )
    selected = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-2",
        title="Selected reply",
        summary="This reply is inside the digest window.",
        created_at="2026-06-11T10:00:00+00:00",
    )

    client = _app(notifications.router, "/notifications", {"sub": "student-1", "role": "student"})
    response = client.get(
        "/notifications/digest-preview"
        "?since=2026-06-11T00:00:00+00:00"
        "&until=2026-06-11T23:59:59+00:00"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["eventId"] == selected["eventId"]
    assert body["items"][0]["eventId"] != older["eventId"]


def test_teacher_can_build_assistance_summary_seed(monkeypatch):
    stored = []
    monkeypatch.setattr(
        teachers.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "status": "teacher_active",
            "teacher_id": "teacher-1",
            "subject": "physics",
            "content": "Why is friction opposite to motion?",
            "ai_response": {"answer": "Friction resists relative motion."},
            "topic_seeds": [{"label": "Forces and friction"}],
            "knowledge_points": ["free-body diagrams"],
        },
    )
    monkeypatch.setattr(
        teacher_assistance_service.notification_repo,
        "put_summary_seed",
        lambda item: stored.append(item),
    )

    client = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})
    response = client.get("/teachers/questions/question-1/assistance-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["questionId"] == "question-1"
    assert body["subject"] == "physics"
    assert body["weakTopics"] == ["Forces and friction", "free-body diagrams"]
    assert "Forces and friction" in body["suggestedFocus"]
    assert stored[0]["entity_type"] == "teacher_assistance_summary_seed"


# ── notification copy follows the reader's language (#124) ────────────────


def _profiles(monkeypatch, locales: dict):
    """Give each user id a stored language preference, and nothing else."""
    # Best-effort notifications are off outside production unless asked for.
    monkeypatch.setenv("STOA_ENABLE_BEST_EFFORT_NOTIFICATIONS", "true")
    monkeypatch.setattr(
        user_repo,
        "get_user",
        lambda user_id, **_kwargs: (
            {"user_id": user_id, "preferred_locale": locales[user_id]}
            if user_id in locales
            else None
        ),
    )


def test_every_line_of_notification_copy_exists_in_every_supported_language():
    """The whole table against the whole locale set, not one line in one language.

    A key that gained a German sentence and no French one would otherwise hide
    behind the fallback until a French student read it.
    """
    supported = locale_service.SUPPORTED_LOCALES

    assert {
        key: set(variants) for key, variants in message_catalog.TEXT.items()
    } == {key: set(supported) for key in message_catalog.TEXT}
    assert all(
        text.strip()
        for variants in message_catalog.TEXT.values()
        for text in variants.values()
    )


def test_no_line_is_one_language_copied_into_all_four_slots():
    """The negative control for the table.

    A key holding the English string under all four locales would satisfy the
    test above while putting English in a German panel exactly as production
    did. Two locales genuinely sharing a word is allowed - `Questions` is the
    same in English and French - so what is refused is a key with no variation
    in it at all.
    """
    unvaried = {
        key
        for key, variants in message_catalog.TEXT.items()
        if len(set(variants.values())) < 2
    }

    assert unvaried == set()
    # German is the fallback and must never be the English line by accident.
    assert {
        key
        for key, variants in message_catalog.TEXT.items()
        if variants["de"] == variants["en"]
    } == set()


def test_an_expired_teacher_request_is_written_in_the_student_s_language(monkeypatch):
    """All four languages driven, and the four results compared as a set.

    The student reads the panel in their own language while the request that
    expired the case was somebody else's - a scheduled job's - so the copy
    can only come from the recipient's stored preference.
    """
    events, _ = _install_notification_repo(monkeypatch)
    locales = {f"student-{locale}": locale for locale in locale_service.SUPPORTED_LOCALES}
    _profiles(monkeypatch, locales)

    titles = {}
    for student_id, locale in locales.items():
        events.clear()
        notification_service.emit_teacher_help_expired(
            conversation={
                "student_id": student_id,
                "conversation_id": f"conv-{locale}",
                "escalation_request_id": f"req-{locale}",
                "account_fence_generation": 1,
            },
            case_returned=True,
        )
        stored = list(events.values())[0]
        titles[locale] = (stored["title"], stored["summary"])

    expected = {
        locale: (
            message_catalog.TEXT["teacher_help.expired.title"][locale],
            message_catalog.TEXT["teacher_help.expired.summary_returned"][locale],
        )
        for locale in locales.values()
    }
    assert titles == expected
    # Four distinct pairs: a locale-blind implementation collapses them to one.
    assert len(set(titles.values())) == len(locales)


def test_the_week_s_case_coming_back_is_said_only_when_it_did(monkeypatch):
    """The two summaries are different sentences, in every language."""
    events, _ = _install_notification_repo(monkeypatch)
    _profiles(monkeypatch, {"student-1": "de"})

    said = {}
    for case_returned in (True, False):
        events.clear()
        notification_service.emit_teacher_help_expired(
            conversation={
                "student_id": "student-1",
                "conversation_id": "conv-1",
                "escalation_request_id": f"req-{case_returned}",
                "account_fence_generation": 1,
            },
            case_returned=case_returned,
        )
        said[case_returned] = list(events.values())[0]["summary"]

    assert said[True] != said[False]
    assert said[True] == message_catalog.TEXT[
        "teacher_help.expired.summary_returned"
    ]["de"]
    assert said[False] == message_catalog.TEXT[
        "teacher_help.expired.summary"
    ]["de"]


def test_the_reader_s_stored_language_wins_over_the_request_s(monkeypatch):
    """A teacher answering in English must not write the student an English line.

    `locale_service.request_locale()` is the language of whoever is making the
    request, which for a notification is never the person who will read it.
    """
    events, _ = _install_notification_repo(monkeypatch)
    _profiles(monkeypatch, {"student-1": "fr"})
    locale_service.set_request_locale("en")
    try:
        notification_service.emit_teacher_help_reply(
            conversation={
                "student_id": "student-1",
                "conversation_id": "conv-1",
                "escalation_request_id": "req-1",
                "account_fence_generation": 1,
            },
            teacher_id="teacher-1",
            reply_id="reply-1",
        )
    finally:
        locale_service.set_request_locale(None)

    stored = list(events.values())[0]
    assert stored["title"] == message_catalog.TEXT[
        "teacher_help.reply.title"
    ]["fr"]


def test_a_reader_with_no_stored_language_still_gets_a_notification(monkeypatch):
    """A profile that cannot be read costs the language, never the message."""
    events, _ = _install_notification_repo(monkeypatch)

    def refuse(_user_id, **_kwargs):
        raise RuntimeError("profile table unavailable")

    monkeypatch.setenv("STOA_ENABLE_BEST_EFFORT_NOTIFICATIONS", "true")
    monkeypatch.setattr(user_repo, "get_user", refuse)

    notification_service.emit_teacher_help_takeover(
        conversation={
            "student_id": "student-1",
            "conversation_id": "conv-1",
            "escalation_request_id": "req-1",
            "account_fence_generation": 1,
        },
        teacher_id="teacher-1",
    )

    stored = list(events.values())[0]
    assert stored["title"] == message_catalog.TEXT[
        "teacher_help.takeover.title"
    ][locale_service.DEFAULT_LOCALE]


def test_notifications_already_written_are_left_as_they_were(monkeypatch):
    """History is not re-rendered: a stored row is what somebody was told."""
    events, _ = _install_notification_repo(monkeypatch)
    _profiles(monkeypatch, {"student-1": "it"})
    events["notif-old"] = {
        "event_id": "notif-old",
        "recipient_id": "student-1",
        "title": "No teacher was available",
        "summary": "Your request for a teacher expired.",
    }

    assert notification_service.notification_repo.get_event("notif-old")["title"] == (
        "No teacher was available"
    )


# ── what a teacher is shown beside a help request (#124) ──────────────────


def _seed_in(monkeypatch, locale: str, question: dict) -> dict:
    """One assistance seed, built for a teacher reading in `locale`."""
    from stoa.security.authorization import AuthorizedResource

    monkeypatch.setattr(
        teacher_assistance_service.notification_repo, "put_summary_seed", lambda item: item
    )
    monkeypatch.setattr(
        user_repo, "get_user", lambda user_id, **_k: {"user_id": user_id, "preferred_locale": locale}
    )
    locale_service.set_request_locale(None)
    authorized = AuthorizedResource(
        ref=type("Ref", (), {"resource_id": "question-1", "student_id": "student-1"})(),
        value=question,
    )
    actor = type("Actor", (), {"user_id": "teacher-1"})()
    return teacher_assistance_service.build_summary_seed(authorized, actor)


# What `_bare_question`'s subject is called in each language (#105).
SUBJECT_NAMES = {
    "de": "Mathematik",
    "en": "Mathematics",
    "fr": "Mathématiques",
    "it": "Matematica",
}


def _bare_question() -> dict:
    return {
        "student_id": "student-1",
        "subject": "mathematics",
        "content": "Bitte hilf mir beim Dividieren.",
        "account_fence_generation": 1,
    }


def test_the_seed_is_written_in_the_language_of_the_teacher_reading_it(monkeypatch):
    """All four languages driven, and the four results compared as a set.

    The seed is rebuilt on every request by the teacher about to read it, so
    the reader is known at generation time and no second rendering pass is
    needed. Four distinct results: a hardcoded sentence collapses them to one.
    """
    produced = {
        locale: (
            _seed_in(monkeypatch, locale, _bare_question())["studentContextSummary"],
            _seed_in(monkeypatch, locale, _bare_question())["suggestedFocus"],
        )
        for locale in sorted(locale_service.SUPPORTED_LOCALES)
    }

    assert produced == {
        locale: (
            message_catalog.text(
                "assistance.context.without_topics", locale, subject=SUBJECT_NAMES[locale]
            ),
            message_catalog.text("assistance.focus.default", locale),
        )
        for locale in locale_service.SUPPORTED_LOCALES
    }
    assert len(set(produced.values())) == len(locale_service.SUPPORTED_LOCALES)


def test_every_branch_of_the_seed_has_its_own_sentence(monkeypatch):
    """The negative control: four different situations, four different lines.

    Without it a `_suggested_focus` that returned the same sentence whatever
    the question held would pass the locale test above.
    """
    cases = {
        "bare": _bare_question(),
        "with_topics": {**_bare_question(), "topic_seeds": [{"label": "Brüche"}]},
        "after_reply": {**_bare_question(), "teacher_response": {"answer": "..."}},
    }

    produced = {
        name: (
            _seed_in(monkeypatch, "de", question)["studentContextSummary"],
            _seed_in(monkeypatch, "de", question)["suggestedFocus"],
        )
        for name, question in cases.items()
    }

    assert len(set(produced.values())) == len(cases)


def test_the_student_s_own_words_are_passed_through_not_rewritten(monkeypatch):
    """Content is not copy: the question and the topic labels go through as they are."""
    question = {**_bare_question(), "topic_seeds": [{"label": "Brüche"}]}

    seed = _seed_in(monkeypatch, "fr", question)

    assert seed["questionSummary"] == "Bitte hilf mir beim Dividieren."
    assert seed["weakTopics"] == ["Brüche"]


# ── the subject is named, not its id (#105) ───────────────────────────────


def _summary_over_http(monkeypatch, language: str, question: dict) -> dict:
    """The assistance summary as the teacher's client fetches it, in `language`."""
    from stoa.main import RequestLocaleMiddleware

    monkeypatch.setattr(
        teachers.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "status": "teacher_active",
            "teacher_id": "teacher-1",
            **question,
        },
    )
    monkeypatch.setattr(
        teacher_assistance_service.notification_repo, "put_summary_seed", lambda item: item
    )
    # No stored preference: the language the client is rendering decides.
    monkeypatch.setattr(user_repo, "get_user", lambda user_id, **_k: {"user_id": user_id})
    app = FastAPI()
    app.add_middleware(RequestLocaleMiddleware)
    app.include_router(teachers.router, prefix="/teachers")
    install_actor_overrides(app, {"sub": "teacher-1", "role": "teacher"})
    response = TestClient(app).get(
        "/teachers/questions/question-1/assistance-summary",
        headers={"Accept-Language": language},
    )
    locale_service.set_request_locale(None)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_context_sentence_names_the_subject_in_the_teacher_s_language(monkeypatch):
    """Both sentences, all four languages: «… in Mathematik …», never «… in mathematics …».

    `mathematics` is how rows from the question lane spell the subject; the
    sentence around it was already translated, the subject was not.
    """
    with_topics = {**_bare_question(), "topic_seeds": [{"label": "Brüche"}]}

    produced = {
        language: (
            _summary_over_http(monkeypatch, language, with_topics)["studentContextSummary"],
            _summary_over_http(monkeypatch, language, _bare_question())["studentContextSummary"],
        )
        for language in SUBJECT_NAMES
    }

    for language, sentences in produced.items():
        for sentence in sentences:
            assert SUBJECT_NAMES[language] in sentence, (language, sentence)
            assert "mathematics" not in sentence, (language, sentence)
    assert produced["de"] == (
        "Die Schülerin oder der Schüler zeigt Hinweise in Mathematik rund um Brüche.",
        "Die Schülerin oder der Schüler hat eine offene Anfrage in Mathematik, "
        "noch ohne ausreichende Hinweise auf ein Thema.",
    )


def test_every_subject_id_and_alias_has_its_own_name(monkeypatch):
    """The other subjects, the `math` id itself, a row with no subject at all,
    and one whose subject is not text (DynamoDB hands numbers back as Decimal).

    Without this a summary that wrote «Mathematik» whatever the subject was
    would pass the test above.
    """
    names = {
        subject: _summary_over_http(
            monkeypatch, "de", {**_bare_question(), "subject": subject}
        )["studentContextSummary"]
        for subject in ("math", "physics", "german", "english", None, Decimal(7))
    }

    assert {subject: sentence.split(" in ")[1].split(",")[0] for subject, sentence in names.items()} == {
        "math": "Mathematik",
        "physics": "Physik",
        "german": "Deutsch",
        "english": "Englisch",
        None: "Allgemein",
        Decimal(7): "Allgemein",
    }


# ── events sent to a whole role, read in each reader's language (#108) ─────

ROLE_READER_LOCALES = sorted(locale_service.SUPPORTED_LOCALES)


def _words(text: str) -> set[str]:
    """The words of a sentence, lowercased; `medium-severity` stays one word."""
    return {word.lower() for word in re.findall(r"[\w-]+", text)}


def _moderation_case_created(severity: str = "medium") -> None:
    notification_service.emit_moderation_created(
        case_item={"case_id": "case-1", "question_id": "question-1", "severity": severity},
        actor_id="student-1",
        actor_role="student",
        owner_id="student-1",
        privacy_generation=1,
    )


def _bell(monkeypatch, user_id: str, role: str, locale: str) -> list[dict]:
    """The reader's bell, read with their stored language and nothing else."""
    reader = {"user_id": user_id, "role": role, "account_status": "active", "preferred_locale": locale}
    monkeypatch.setattr(
        user_repo, "get_user", lambda wanted, **_kwargs: reader if wanted == user_id else None
    )
    # A teacher's facts are looked up even for their own bell; they hold none here.
    monkeypatch.setattr(question_repo, "get_teacher_session", lambda *_a, **_k: None)
    monkeypatch.setattr(question_repo, "get_teacher_assignment", lambda *_a, **_k: None)
    client = _app(notifications.router, "/notifications", {"sub": user_id, "role": role})
    response = client.get("/notifications")
    assert response.status_code == 200, response.text
    return response.json()["items"]


@pytest.mark.parametrize("locale", ROLE_READER_LOCALES)
def test_a_new_moderation_case_reads_in_the_admin_s_language(monkeypatch, locale):
    """Written once for the admin role, read by every admin in their own language."""
    _install_notification_repo(monkeypatch)
    _profiles(monkeypatch, {})
    _moderation_case_created("medium")

    [item] = _bell(monkeypatch, f"admin-{locale}", "admin", locale)

    assert item["eventType"] == "moderation_case_update"
    assert (item["title"], item["summary"]) == (
        message_catalog.TEXT["moderation.created.title"][locale],
        message_catalog.TEXT["moderation.created.summary.medium"][locale],
    )
    # Not the stored enum dropped into a sentence, in any language.
    assert _words(item["summary"]).isdisjoint({"low", "medium", "high"})


def test_one_role_event_is_read_differently_by_two_readers(monkeypatch):
    """One stored row, two admins: neither is handed the other's language."""
    _install_notification_repo(monkeypatch)
    _profiles(monkeypatch, {})
    _moderation_case_created("high")

    [german] = _bell(monkeypatch, "admin-de", "admin", "de")
    [french] = _bell(monkeypatch, "admin-fr", "admin", "fr")

    assert german["eventId"] == french["eventId"]
    assert german["summary"] == message_catalog.TEXT["moderation.created.summary.high"]["de"]
    assert french["summary"] == message_catalog.TEXT["moderation.created.summary.high"]["fr"]


def test_each_severity_says_its_own_sentence(monkeypatch):
    """A summary that ignored the severity would pass every test above with `medium`."""
    events, _ = _install_notification_repo(monkeypatch)
    _profiles(monkeypatch, {})
    for severity in ("low", "medium", "high"):
        _moderation_case_created(severity)
        for event_id in list(events):
            events[f"{severity}-{event_id}"] = {**events.pop(event_id), "event_id": f"{severity}-{event_id}"}

    summaries = {item["summary"] for item in _bell(monkeypatch, "admin-it", "admin", "it")}

    assert summaries == {
        message_catalog.TEXT[f"moderation.created.summary.{severity}"]["it"]
        for severity in ("low", "medium", "high")
    }


def test_the_admin_operations_list_answers_in_the_admin_s_language(monkeypatch):
    _install_notification_repo(monkeypatch)
    _profiles(monkeypatch, {"admin-fr": "fr"})
    _moderation_case_created()

    client = _app(notifications.admin_router, "/admin", {"sub": "admin-fr", "role": "admin"})
    response = client.get("/admin/notifications?event_type=moderation_case_update")

    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == (
        message_catalog.TEXT["moderation.created.title"]["fr"]
    )


def test_a_role_row_written_before_message_keys_is_shown_as_stored(monkeypatch):
    """The frontend still translates these by their exact English (#518)."""
    events, _ = _install_notification_repo(monkeypatch)
    events["notif-old"] = {
        "event_id": "notif-old",
        "recipient_id": None,
        "recipient_role": "admin",
        "event_type": "moderation_case_update",
        "target_type": "moderation_case",
        "target_id": "case-1",
        "title": "New moderation case",
        "summary": "medium moderation case reported.",
        "status": "created",
        "created_at": "2026-10-01T10:00:00+00:00",
    }

    [item] = _bell(monkeypatch, "admin-de", "admin", "de")

    assert (item["title"], item["summary"]) == (
        "New moderation case",
        "medium moderation case reported.",
    )


def test_a_role_event_cannot_be_marked_by_one_reader(monkeypatch):
    """Read and archive never answer with a role message, so they need no language.

    A role row has no single recipient to bind it to. Should that change, the
    answer would carry the stored English: render it there too.
    """
    events, _ = _install_notification_repo(monkeypatch)
    _profiles(monkeypatch, {"admin-de": "de"})
    _moderation_case_created()
    [event_id] = events

    client = _app(notifications.router, "/notifications", {"sub": "admin-de", "role": "admin"})

    assert client.post(f"/notifications/{event_id}/read").status_code == 404
    assert client.post(f"/notifications/{event_id}/archive").status_code == 404
