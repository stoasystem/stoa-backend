from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.deps import get_current_user
from stoa.routers import notifications, questions, tutors
from stoa.services import notification_service, teacher_assistance_service


def _app(router, prefix: str, user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_current_user] = lambda: user
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

    assert response.status_code == 403


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


def test_request_teacher_emits_tutor_and_admin_events(monkeypatch):
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
    monkeypatch.setattr(
        questions.notification_service,
        "create_event_safe",
        lambda **kwargs: emitted.append(kwargs),
    )

    client = _app(questions.router, "/questions", {"sub": "student-1", "role": "student"})
    response = client.post("/questions/question-1/request-teacher")

    assert response.status_code == 202
    assert updates[0][1] == "escalated"
    assert {event["recipient_role"] for event in emitted} == {"tutor", "admin"}
    assert {event["event_type"] for event in emitted} == {"teacher_requested"}


def test_tutor_can_build_assistance_summary_seed(monkeypatch):
    stored = []
    monkeypatch.setattr(
        teacher_assistance_service.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "status": "escalated",
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

    client = _app(tutors.router, "/tutors", {"sub": "tutor-1", "role": "tutor"})
    response = client.get("/tutors/questions/question-1/assistance-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["questionId"] == "question-1"
    assert body["subject"] == "physics"
    assert body["weakTopics"] == ["Forces and friction", "free-body diagrams"]
    assert "Forces and friction" in body["suggestedFocus"]
    assert stored[0]["entity_type"] == "teacher_assistance_summary_seed"
