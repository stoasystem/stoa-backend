from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings
from stoa.routers import notifications, questions, teachers
from stoa.services import notification_service, teacher_assistance_service, websocket_service
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
        events[item["event_id"]] = dict(item)

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
    monkeypatch.setattr(notification_service.notification_repo, "list_events", list_events)
    monkeypatch.setattr(notification_service.notification_repo, "update_event", update_event)
    monkeypatch.setattr(notification_service.notification_repo, "put_preferences", put_preferences)
    monkeypatch.setattr(notification_service.notification_repo, "get_preferences", get_preferences)
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
    assert result["providerResult"]["apiKey"] == "configured"


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
    assert failure_attempt["status"] == "failed"
    assert failure_attempt["provider_result"] == {"error": "RuntimeError"}
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


def test_request_teacher_emits_teacher_and_admin_events(monkeypatch):
    updates = []
    emitted = []
    monkeypatch.setattr(
        questions.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "subject": "math",
            "status": "ai_answered",
        },
    )
    monkeypatch.setattr(
        questions.question_repo,
        "update_status",
        lambda question_id, status, **attrs: updates.append((question_id, status, attrs)),
    )
    monkeypatch.setattr(questions.notify_service, "enqueue_teacher_request", lambda **kwargs: None)
    monkeypatch.setattr(questions.usage_ledger_service, "record_usage_event", lambda **kwargs: None)
    monkeypatch.setattr(
        questions.notification_service,
        "create_event_safe",
        lambda **kwargs: emitted.append(kwargs),
    )

    client = _app(questions.router, "/questions", {"sub": "student-1", "role": "student"})
    response = client.post("/questions/question-1/request-teacher")

    assert response.status_code == 202
    assert updates[0][1] == "escalated"
    assert {event["recipient_role"] for event in emitted} == {"teacher", "admin"}
    assert {event["event_type"] for event in emitted} == {"teacher_requested"}


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
