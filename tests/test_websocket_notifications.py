import hashlib

from fakes.dynamodb import FakeTable

from stoa.db import table as db_table
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa import config

from stoa.config import Settings
from stoa.services import websocket_service
from stoa.services.notifications import _bell, _ledger, _realtime
from stoa.db.repositories import account_deletion_repo, notification_repo


def _install_notification_repo(monkeypatch):
    events: dict[str, dict] = {}
    preferences: dict[str, dict] = {}

    def put_event(item):
        stored = dict(item)
        stored.setdefault("schema_version", "notification-event.v3")
        stored.setdefault("event_version", 1)
        stored.setdefault("owner_classification", "private_owner")
        if not stored.get("owner_id"):
            stored["owner_id"] = stored.get("recipient_id") or "student-owner"
        if type(stored.get("account_fence_generation")) is not int:
            stored["account_fence_generation"] = 1
        events[item["event_id"]] = stored
        return stored

    def get_event(event_id):
        return events.get(event_id)

    def load_delivery_event_strong(event_id):
        item = dict(events[event_id])
        item.setdefault("PK", f"NOTIFICATION#{event_id}")
        item.setdefault("SK", "META")
        item.setdefault("entity_type", "notification_event")
        item.setdefault("schema_version", "notification-event.v3")
        item.setdefault("event_version", 1)
        item.setdefault("owner_classification", "private_owner")
        if not item.get("owner_id"):
            item["owner_id"] = item.get("recipient_id") or "student-owner"
        if type(item.get("account_fence_generation")) is not int:
            item["account_fence_generation"] = 1
        return item

    def list_inbox(*, user_id="", role="", want=None, keep=None, table=None):
        # One person's notifications and their role's, as the index finds them (#613).
        return [
            dict(event)
            for event in events.values()
            if (
                event.get("recipient_id") == user_id
                or (event.get("recipient_id") in {None, ""} and event.get("recipient_role") == role)
            )
            and (keep is None or keep(event))
        ]

    def list_site_events(*, want, keep=None, table=None):
        # The site's list, newest first, as its own index finds it (#613).
        newest = sorted(events.values(), key=lambda event: event.get("created_at", ""), reverse=True)
        return [dict(event) for event in newest if keep is None or keep(event)][:want]

    def update_event(event_id, updates):
        events[event_id].update(updates)
        return events[event_id]

    def put_preferences(item):
        preferences[item["user_id"]] = dict(item)

    def get_preferences(user_id):
        return preferences.get(user_id)

    monkeypatch.setattr(notification_repo, "put_event", put_event)
    monkeypatch.setattr(notification_repo, "get_event", get_event)
    monkeypatch.setattr(
        notification_repo,
        "load_delivery_event_strong",
        load_delivery_event_strong,
    )
    monkeypatch.setattr(notification_repo, "list_inbox", list_inbox)
    monkeypatch.setattr(notification_repo, "list_site_events", list_site_events)
    monkeypatch.setattr(notification_repo, "update_event", update_event)
    monkeypatch.setattr(notification_repo, "put_preferences", put_preferences)
    monkeypatch.setattr(notification_repo, "get_preferences", get_preferences)
    monkeypatch.setattr(notification_repo, "update_event", update_event)
    monkeypatch.setattr(
        account_deletion_repo,
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
            return {"status": "provider_acceptance_unknown"}
        return {"status": "accepted"}

    monkeypatch.setattr(
        _ledger,
        "run_authoritative_delivery",
        run_authoritative_delivery,
    )
    return events


def _connection_ref(connection_id: str) -> str:
    digest = hashlib.sha256(
        ("stoa.websocket-evidence.v1\x00" + connection_id).encode("utf-8")
    ).hexdigest()
    return f"connection-{digest[:16]}"


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

    # One person's connections and one role's, as the indexes find them (#624).
    def list_user_connections(user_id, *, table=None):
        return [item for item in connections.values() if item.get("user_id") == user_id]

    def list_role_connections(role, *, table=None):
        return [item for item in connections.values() if item.get("role") == role]

    def list_site_connections(*, table=None):
        return list(connections.values())

    def delete_stale_connections(*, now_epoch):
        removed = []
        for connection_id, item in list(connections.items()):
            if int(item.get("expires_at") or 0) <= now_epoch:
                removed.append(connection_id)
                connections.pop(connection_id, None)
        return removed

    monkeypatch.setattr(websocket_service.websocket_repo, "put_connection", put_connection)
    monkeypatch.setattr(websocket_service.websocket_repo, "get_connection", get_connection)
    monkeypatch.setattr(websocket_service.websocket_repo, "update_connection", update_connection)
    monkeypatch.setattr(websocket_service.websocket_repo, "delete_connection", delete_connection)
    for reader in (list_user_connections, list_role_connections, list_site_connections):
        monkeypatch.setattr(websocket_service.websocket_repo, reader.__name__, reader)
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
    except SecurityDecisionError as exc:
        assert exc.code is SecurityErrorCode.ACTION_NOT_ALLOWED
    else:
        raise AssertionError("unauthorized subscription should fail")

    removed = websocket_service.disconnect_connection("conn-1")
    assert removed == {"connectionId": "conn-1", "removed": True}
    assert "conn-1" not in connections


def test_teacher_connection_receives_teacher_role_broadcast(monkeypatch):
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
        "recipient_role": "teacher",
        "event_type": "teacher_requested",
        "target_type": "question",
        "target_id": "question-1",
        "title": "Teacher help requested",
        "summary": "A student requested help.",
        "created_at": "2026-06-09T10:00:00+00:00",
        "metadata": {},
    }
    events[event["event_id"]] = dict(event)

    result = _realtime.fanout_notification_event(
        event,
        post_func=lambda connection, envelope: sent.append((connection, envelope)),
    )

    assert result["results"] == [
        {"connection_id": _connection_ref("teacher-conn"), "status": "delivered"}
    ]
    assert sent[0][1]["eventId"] == "notif-1"
    assert sent[0][1]["deliveryId"].startswith("websocket-")
    assert "role:teacher" in sent[0][0]["subscribed_channels"]


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

    _realtime.fanout_notification_event(event, post_func=lambda connection, envelope: None)

    attempts = events["notif-2"]["metadata"]["websocket_delivery_attempts"]
    # The person's channel only: not every student's (#624).
    assert attempts[0]["target_channels"] == ["user:student-1"]
    assert attempts[0]["results"] == [
        {"connection_id": _connection_ref("student-conn"), "status": "delivered"}
    ]


def test_fanout_skips_malformed_persisted_channel_records(monkeypatch):
    events = _install_notification_repo(monkeypatch)
    connections = _install_websocket_repo(monkeypatch)
    connections["malformed"] = {
        "connection_id": "malformed",
        "user_id": "student-1",
        "role": "student",
        "subscribed_channels": "user:student-1",
        "expires_at": 4_102_444_800,
    }
    event = {
        "event_id": "notif-malformed-channel",
        "recipient_id": "student-1",
        "recipient_role": "student",
        "event_type": "teacher_reply",
        "target_type": "question",
        "target_id": "question-1",
        "title": "Teacher replied",
        "summary": "Your teacher added a reply.",
        "created_at": "2026-06-09T10:00:00+00:00",
        "metadata": {},
    }
    events[event["event_id"]] = dict(event)
    sent: list[dict] = []

    result = _realtime.fanout_notification_event(
        event,
        post_func=lambda connection, _envelope: sent.append(connection),
    )

    assert result["results"] == []
    assert sent == []


def test_delivery_failure_does_not_break_durable_notification(monkeypatch):
    events = _install_notification_repo(monkeypatch)
    _install_websocket_repo(monkeypatch)
    websocket_service.register_connection(
        connection_id="student-conn",
        user={"sub": "student-1", "role": "student"},
    )

    event = _bell.create_event(
        event_id="evt-303",
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
        {
            "connection_id": _connection_ref("student-conn"),
            "status": "skipped_no_endpoint",
        }
    ]


def test_stale_cleanup_removes_expired_connections(monkeypatch):
    connections = _install_websocket_repo(monkeypatch)
    connections["old"] = {"connection_id": "old", "expires_at": 10}
    connections["fresh"] = {"connection_id": "fresh", "expires_at": 30}

    result = websocket_service.cleanup_stale_connections(current_epoch=20)

    assert result == {"removedConnectionIds": ["old"], "count": 1}
    assert set(connections) == {"fresh"}


def test_readiness_status_distinguishes_live_rollout_modes(monkeypatch):
    _install_websocket_repo(monkeypatch)
    scenarios = [
        ({}, "local_only"),
        (
            {
                "websocket_api_endpoint": "https://abc.execute-api.eu-central-2.amazonaws.com/prod",
            },
            "provider_blocked",
        ),
        (
            {
                "websocket_api_endpoint": "https://abc.execute-api.eu-central-2.amazonaws.com/prod",
                "websocket_live_routes_configured": True,
            },
            "configured",
        ),
        (
            {
                "websocket_api_endpoint": "https://abc.execute-api.eu-central-2.amazonaws.com/prod",
                "websocket_live_routes_configured": True,
                "websocket_live_deployed": True,
            },
            "deployed",
        ),
        (
            {
                "websocket_api_endpoint": "https://abc.execute-api.eu-central-2.amazonaws.com/prod",
                "websocket_live_routes_configured": True,
                "websocket_live_deployed": True,
                "websocket_live_smoke_passed": True,
            },
            "live_ready",
        ),
    ]

    for settings_kwargs, expected_mode in scenarios:
        config.install(Settings(**settings_kwargs))

        status = websocket_service.readiness_status()

        assert status["mode"] == expected_mode


def test_a_persons_notification_is_not_sent_to_others_of_their_role(monkeypatch):
    """Every connection subscribes to its role's channel; a person's notification is theirs (#624)."""
    events = _install_notification_repo(monkeypatch)
    _install_websocket_repo(monkeypatch)
    for connection_id, user_id in (("mine", "student-1"), ("theirs", "student-2")):
        websocket_service.register_connection(
            connection_id=connection_id, user={"sub": user_id, "role": "student"}
        )
    event = {
        "event_id": "notif-personal",
        "recipient_id": "student-1",
        "recipient_role": "student",
        "event_type": "teacher_reply",
        "target_type": "question",
        "target_id": "question-1",
        "title": "Teacher replied",
        "summary": "Your teacher added a reply.",
        "created_at": "2026-11-25T10:00:00+00:00",
        "metadata": {},
    }
    events[event["event_id"]] = dict(event)
    sent: list[str] = []

    _realtime.fanout_notification_event(
        event, post_func=lambda connection, _envelope: sent.append(connection["connection_id"])
    )

    assert sent == ["mine"]


def test_a_role_broadcast_reaches_every_connection_of_the_role_and_no_other(monkeypatch):
    events = _install_notification_repo(monkeypatch)
    _install_websocket_repo(monkeypatch)
    for connection_id, user_id, role in (
        ("t1", "teacher-1", "teacher"),
        ("t2", "teacher-2", "teacher"),
        ("s1", "student-1", "student"),
    ):
        websocket_service.register_connection(
            connection_id=connection_id, user={"sub": user_id, "role": role}
        )
    event = {
        "event_id": "notif-broadcast",
        "recipient_id": None,
        "recipient_role": "teacher",
        "event_type": "teacher_requested",
        "target_type": "question",
        "target_id": "question-1",
        "title": "Teacher help requested",
        "summary": "A student requested help.",
        "created_at": "2026-11-25T10:00:00+00:00",
        "metadata": {},
    }
    events[event["event_id"]] = dict(event)
    sent: list[str] = []

    _realtime.fanout_notification_event(
        event, post_func=lambda connection, _envelope: sent.append(connection["connection_id"])
    )

    assert sorted(sent) == ["t1", "t2"]


def _seed_connection(table, connection_id, user_id, role, *, expires_at=4_102_444_800):
    row = {
        "PK": websocket_service.websocket_repo.connection_pk(connection_id),
        "SK": "META",
        "entity_type": websocket_service.websocket_repo.CONNECTION_ENTITY,
        "connection_id": connection_id,
        "user_id": user_id,
        "owner_id": user_id,
        "role": role,
        "subscribed_channels": [f"user:{user_id}", f"role:{role}"],
        "connected_at": "2026-11-25T10:00:00+00:00",
        "expires_at": expires_at,
    }
    table.seed({**row, **websocket_service.websocket_repo.index_fields(row)})


def test_a_persons_notification_reaches_them_among_more_than_500_connections(monkeypatch):
    """The scan kept the site's first 500 connection rows; the rest were never pushed to (#624)."""
    events = _install_notification_repo(monkeypatch)
    table = FakeTable()
    for number in range(520):
        _seed_connection(table, f"a-{number:04d}", f"student-{number + 100}", "student")
    # Sorts after all of them, where the scan never got to.
    _seed_connection(table, "z-mine", "student-1", "student")
    event = {
        "event_id": "notif-crowded",
        "recipient_id": "student-1",
        "recipient_role": "student",
        "event_type": "teacher_reply",
        "target_type": "question",
        "target_id": "question-1",
        "title": "Teacher replied",
        "summary": "Your teacher added a reply.",
        "created_at": "2026-11-25T10:00:00+00:00",
        "metadata": {},
    }
    events[event["event_id"]] = dict(event)
    sent: list[str] = []
    db_table.install(table)
    try:
        result = _realtime.fanout_notification_event(
            event, post_func=lambda connection, _envelope: sent.append(connection["connection_id"])
        )
    finally:
        db_table.install(None)

    assert sent == ["z-mine"]
    assert result["results"] == [{"connection_id": _connection_ref("z-mine"), "status": "delivered"}]


def test_readiness_counts_every_connection_of_every_role(monkeypatch):
    table = FakeTable()
    now = websocket_service.now_epoch()
    for number, role in enumerate(("student", "parent", "teacher", "admin")):
        _seed_connection(table, f"live-{role}", f"{role}-1", role, expires_at=now + 60)
        _seed_connection(table, f"old-{role}", f"{role}-2", role, expires_at=now - 60 - number)
    db_table.install(table)
    try:
        status = websocket_service.readiness_status()["connectionStatus"]
        removed = websocket_service.cleanup_stale_connections()
    finally:
        db_table.install(None)

    assert status == {"activeConnectionCount": 4, "staleConnectionCount": 4, "error": None}
    assert sorted(removed["removedConnectionIds"]) == [
        "old-admin", "old-parent", "old-student", "old-teacher"
    ]


def test_every_role_a_user_can_have_has_its_list_of_connections():
    from stoa.models.user import UserRole

    assert set(websocket_service.websocket_repo.CONNECTION_ROLES) == {role.value for role in UserRole}
