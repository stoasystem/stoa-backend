from fastapi import HTTPException

from stoa.services import notification_service, websocket_service


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
    monkeypatch.setattr(websocket_service.notification_repo, "update_event", update_event)
    return events


def _install_websocket_repo(monkeypatch):
    connections: dict[str, dict] = {}

    def put_connection(item):
        connections[item["connection_id"]] = dict(item)

    def get_connection(connection_id):
        return connections.get(connection_id)

    def update_connection(connection_id, updates):
        connections[connection_id].update(updates)
        return connections[connection_id]

    def delete_connection(connection_id):
        connections.pop(connection_id, None)

    def list_connections(limit=200):
        return list(connections.values())[:limit]

    def delete_stale_connections(*, now_epoch, limit=200):
        removed = []
        for connection_id, item in list(connections.items())[:limit]:
            if int(item.get("expires_at") or 0) <= now_epoch:
                removed.append(connection_id)
                connections.pop(connection_id, None)
        return removed

    monkeypatch.setattr(websocket_service.websocket_repo, "put_connection", put_connection)
    monkeypatch.setattr(websocket_service.websocket_repo, "get_connection", get_connection)
    monkeypatch.setattr(websocket_service.websocket_repo, "update_connection", update_connection)
    monkeypatch.setattr(websocket_service.websocket_repo, "delete_connection", delete_connection)
    monkeypatch.setattr(websocket_service.websocket_repo, "list_connections", list_connections)
    monkeypatch.setattr(
        websocket_service.websocket_repo,
        "delete_stale_connections",
        delete_stale_connections,
    )
    return connections


def test_connection_lifecycle_and_subscription_authorization(monkeypatch):
    connections = _install_websocket_repo(monkeypatch)
    user = {"sub": "student-1", "role": "student"}

    created = websocket_service.register_connection(connection_id="conn-1", user=user)

    assert created["connectionId"] == "conn-1"
    assert set(created["subscribedChannels"]) == {"user:student-1", "role:student"}
    assert connections["conn-1"]["entity_type"] == "websocket_connection"

    refreshed = websocket_service.refresh_connection("conn-1", user)
    assert refreshed["expiresAt"] >= created["expiresAt"]

    updated = websocket_service.subscribe_connection("conn-1", user, ["user:student-1"])
    assert updated["subscribedChannels"] == ["user:student-1"]

    try:
        websocket_service.subscribe_connection("conn-1", user, ["role:admin"])
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("unauthorized subscription should fail")

    removed = websocket_service.disconnect_connection("conn-1")
    assert removed == {"connectionId": "conn-1", "removed": True}
    assert "conn-1" not in connections


def test_teacher_connection_receives_tutor_role_broadcast(monkeypatch):
    events = _install_notification_repo(monkeypatch)
    _install_websocket_repo(monkeypatch)
    sent = []
    websocket_service.register_connection(
        connection_id="teacher-conn",
        user={"sub": "teacher-1", "role": "teacher"},
    )
    event = {
        "event_id": "notif-1",
        "recipient_id": None,
        "recipient_role": "tutor",
        "event_type": "teacher_requested",
        "target_type": "question",
        "target_id": "question-1",
        "title": "Teacher help requested",
        "summary": "A student requested help.",
        "created_at": "2026-06-09T10:00:00+00:00",
        "metadata": {},
    }
    events[event["event_id"]] = dict(event)

    result = websocket_service.fanout_notification_event(
        event,
        post_func=lambda connection, envelope: sent.append((connection, envelope)),
    )

    assert result["results"] == [{"connection_id": "teacher-conn", "status": "delivered"}]
    assert sent[0][1]["eventId"] == "notif-1"
    assert sent[0][1]["deliveryId"] == result["deliveryId"]
    assert "role:tutor" in sent[0][0]["subscribed_channels"]


def test_direct_user_fanout_records_delivery_attempt_metadata(monkeypatch):
    events = _install_notification_repo(monkeypatch)
    _install_websocket_repo(monkeypatch)
    websocket_service.register_connection(
        connection_id="student-conn",
        user={"sub": "student-1", "role": "student"},
    )
    event = {
        "event_id": "notif-2",
        "recipient_id": "student-1",
        "recipient_role": "student",
        "event_type": "teacher_reply",
        "target_type": "question",
        "target_id": "question-1",
        "title": "Teacher replied",
        "summary": "Your teacher added a reply.",
        "created_at": "2026-06-09T10:00:00+00:00",
        "metadata": {"subject": "math"},
    }
    events[event["event_id"]] = dict(event)

    websocket_service.fanout_notification_event(event, post_func=lambda connection, envelope: None)

    attempts = events["notif-2"]["metadata"]["websocket_delivery_attempts"]
    assert attempts[0]["target_channels"] == ["role:student", "user:student-1"]
    assert attempts[0]["results"] == [{"connection_id": "student-conn", "status": "delivered"}]


def test_delivery_failure_does_not_break_durable_notification(monkeypatch):
    events = _install_notification_repo(monkeypatch)
    _install_websocket_repo(monkeypatch)
    websocket_service.register_connection(
        connection_id="student-conn",
        user={"sub": "student-1", "role": "student"},
    )

    event = notification_service.create_event(
        recipient_id="student-1",
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )

    assert event["eventId"] in events
    assert events[event["eventId"]]["status"] == "created"
    attempts = events[event["eventId"]]["metadata"]["websocket_delivery_attempts"]
    assert attempts[0]["results"] == [
        {"connection_id": "student-conn", "status": "skipped_no_endpoint"}
    ]


def test_stale_cleanup_removes_expired_connections(monkeypatch):
    connections = _install_websocket_repo(monkeypatch)
    connections["old"] = {"connection_id": "old", "expires_at": 10}
    connections["fresh"] = {"connection_id": "fresh", "expires_at": 30}

    result = websocket_service.cleanup_stale_connections(current_epoch=20)

    assert result == {"removedConnectionIds": ["old"], "count": 1}
    assert set(connections) == {"fresh"}
