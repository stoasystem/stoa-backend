from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.db.repositories import question_repo, user_repo
from stoa.deps import get_actor
from stoa.routers import conversations
from stoa.security.identity import AccountStatus, Actor, CanonicalRole, CapabilityGrant


def _actor(role=CanonicalRole.STUDENT, user_id="student-1", grants=()):
    return Actor(
        user_id,
        "https://identity.test",
        f"{user_id}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
        tuple(grants),
    )


def _client(router, prefix: str = "/conversations", actor=None) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_actor] = lambda: actor or _actor()
    return TestClient(app)


def test_send_message_records_chat_usage_without_raw_content(monkeypatch):
    ledger_calls = []
    rate_limit_calls = []
    monkeypatch.setattr(
        conversations,
        "_get_conversation",
        lambda conv_id: {
            "conversation_id": conv_id,
            "student_id": "student-1",
            "subject": "math",
            "grade": "Sek1",
        },
    )
    monkeypatch.setattr(
        conversations,
        "check_and_record_chat",
        lambda student_id, limit=None: rate_limit_calls.append({"student_id": student_id, "limit": limit}) or {
            "quotaPeriod": "2026-07-04",
            "counterKey": "USAGE#student-1/CHAT#2026-07-04",
            "counterValue": 2,
            "limit": limit,
            "expiresAt": 1,
        },
    )
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda student_id: 8)
    monkeypatch.setattr(
        conversations,
        "_send_message_impl",
        lambda **kwargs: (
            conversations.ChatMessage(
                id="student-message-1",
                conversationId=kwargs["conv_id"],
                role="student",
                content=kwargs["content"],
                createdAt="2026-07-04T10:00:00+00:00",
            ),
            conversations.ChatMessage(
                id="assistant-message-1",
                conversationId=kwargs["conv_id"],
                role="assistant",
                content="assistant reply",
                createdAt="2026-07-04T10:00:01+00:00",
            ),
        ),
    )
    monkeypatch.setattr(
        conversations.usage_ledger_service,
        "record_usage_event",
        lambda **kwargs: ledger_calls.append(kwargs) or {"idempotency_status": "created"},
    )

    response = _client(conversations.router).post(
        "/conversations/conv-1/messages",
        json={"content": "raw student message"},
    )

    assert response.status_code == 200
    assert rate_limit_calls == [{"student_id": "student-1", "limit": 8}]
    assert ledger_calls[0]["action"] == "chat_message"
    assert ledger_calls[0]["counter_value"] == 2
    assert ledger_calls[0]["metadata"] == {
        "conversation_id": "conv-1",
        "request_id": "student-message-1",
        "subject": "math",
        "grade_level": "Sek1",
        "status": "sent",
    }
    assert "raw student message" not in str(ledger_calls[0])


def test_conversation_teacher_help_records_support_visible_usage(monkeypatch):
    ledger_calls = []

    class FakeTable:
        def update_item(self, **kwargs):
            return {}

        def put_item(self, Item):
            return {}

    monkeypatch.setattr(conversations, "get_table", lambda: FakeTable())
    monkeypatch.setattr(
        conversations,
        "_get_conversation",
        lambda conv_id: {
            "conversation_id": conv_id,
            "student_id": "student-1",
            "subject": "physics",
            "grade": "Sek1",
        },
    )
    monkeypatch.setattr(
        conversations.usage_ledger_service,
        "record_usage_event",
        lambda **kwargs: ledger_calls.append(kwargs) or {"idempotency_status": "created"},
    )

    response = _client(conversations.teacher_help_router, "/teacher-help").post(
        "/teacher-help/request",
        json={"conversationId": "conv-1", "message": "please help"},
    )

    assert response.status_code == 200
    body = response.json()
    assert ledger_calls[0]["action"] == "conversation_teacher_help_request"
    assert ledger_calls[0]["student_id"] == "student-1"
    assert ledger_calls[0]["request_correlation_id"] == body["requestId"]
    assert ledger_calls[0]["metadata"]["conversation_id"] == "conv-1"
    assert ledger_calls[0]["metadata"]["subject"] == "physics"
    assert "please help" not in str(ledger_calls[0])


def test_conversation_list_and_create_derive_owner_from_actor(monkeypatch):
    listed = []
    stored = []

    class Table:
        def put_item(self, Item):
            stored.append(Item)

    monkeypatch.setattr(
        conversations,
        "_list_conversations",
        lambda student_id: listed.append(student_id) or [],
    )
    monkeypatch.setattr(conversations, "get_table", lambda: Table())
    client = _client(conversations.router)
    assert client.get("/conversations").status_code == 200
    created = client.post(
        "/conversations", json={"subject": "math", "grade": "Sek1"}
    )
    assert created.status_code == 201
    assert listed == ["student-1"]
    assert stored[0]["student_id"] == "student-1"

    substituted = client.post(
        "/conversations",
        json={"subject": "math", "grade": "Sek1", "studentId": "student-2"},
    )
    assert substituted.status_code == 422
    assert len(stored) == 1


def test_conversation_owner_and_exact_admin_capability_positive_controls(monkeypatch):
    conv = {
        "conversation_id": "conv-1",
        "student_id": "student-1",
        "subject": "math",
        "grade": "Sek1",
        "title": "Private chat",
        "created_at": "2026-07-15T00:00:00Z",
        "updated_at": "2026-07-15T00:00:00Z",
    }
    monkeypatch.setattr(conversations, "_get_conversation", lambda *_: conv)
    monkeypatch.setattr(conversations, "_get_messages", lambda *_: [])
    owner = _client(conversations.router).get("/conversations/conv-1")
    grant = CapabilityGrant("student_content_review", "student:student-1", 1)
    admin = _client(
        conversations.router,
        actor=_actor(CanonicalRole.ADMIN, "admin-1", (grant,)),
    ).get("/conversations/conv-1")
    assert owner.status_code == admin.status_code == 200
    role_only = _client(
        conversations.router,
        actor=_actor(CanonicalRole.ADMIN, "admin-1"),
    ).get("/conversations/conv-1")
    assert role_only.status_code == 403
    assert role_only.json()["detail"]["code"] == "action_not_allowed"


def test_unrelated_parent_conversation_is_hidden(monkeypatch):
    conv = {"conversation_id": "conv-1", "student_id": "student-1"}
    monkeypatch.setattr(conversations, "_get_conversation", lambda *_: conv)
    monkeypatch.setattr(user_repo, "get_parent_student_binding", lambda *_: None)
    monkeypatch.setattr(user_repo, "get_student_parent_binding", lambda *_: None)
    monkeypatch.setattr(
        user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "role": "parent" if user_id == "parent-1" else "student",
            "account_status": "active",
        },
    )
    response = _client(
        conversations.router, actor=_actor(CanonicalRole.PARENT, "parent-1")
    ).get("/conversations/conv-1")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "resource_not_found"


def test_current_linked_teacher_can_read_but_stale_teacher_is_hidden(monkeypatch):
    conv = {
        "conversation_id": "conv-1",
        "student_id": "student-1",
        "question_id": "question-1",
        "subject": "math",
        "grade": "Sek1",
        "title": "Help chat",
        "created_at": "2026-07-15T00:00:00Z",
        "updated_at": "2026-07-15T00:00:00Z",
    }
    question = {
        "question_id": "question-1",
        "conversation_id": "conv-1",
        "student_id": "student-1",
        "teacher_id": "teacher-1",
        "dispatch_status": "accepted",
        "status": "teacher_active",
    }
    accounts = {
        "student-1": {"user_id": "student-1", "role": "student", "account_status": "active"},
        "teacher-1": {"user_id": "teacher-1", "role": "teacher", "account_status": "active"},
        "teacher-2": {"user_id": "teacher-2", "role": "teacher", "account_status": "active"},
    }
    monkeypatch.setattr(conversations, "_get_conversation", lambda *_: conv)
    monkeypatch.setattr(conversations, "_get_messages", lambda *_: [])
    monkeypatch.setattr(question_repo, "get_question", lambda *_: question)
    monkeypatch.setattr(question_repo, "get_teacher_session", lambda *_: None)
    monkeypatch.setattr(question_repo, "get_teacher_assignment", lambda *_: None)
    monkeypatch.setattr(user_repo, "get_user", lambda user_id: accounts.get(user_id))
    current = _client(
        conversations.router, actor=_actor(CanonicalRole.TEACHER, "teacher-1")
    ).get("/conversations/conv-1")
    stale = _client(
        conversations.router, actor=_actor(CanonicalRole.TEACHER, "teacher-2")
    ).get("/conversations/conv-1")
    assert current.status_code == 200
    assert stale.status_code == 404
    assert stale.json()["detail"]["code"] == "resource_not_found"


def test_other_actor_and_random_conversation_are_hidden_before_stream_bytes(monkeypatch):
    calls = []
    real = {"conversation_id": "conv-real", "student_id": "student-1"}
    monkeypatch.setattr(
        conversations,
        "_get_conversation",
        lambda conv_id: real if conv_id == "conv-real" else None,
    )
    monkeypatch.setattr(
        conversations,
        "_send_message_impl",
        lambda **_kwargs: calls.append("message") or None,
    )
    client = _client(conversations.router, actor=_actor(user_id="student-2"))
    hidden = client.post(
        "/conversations/conv-real/messages/stream", json={"content": "swap"}
    )
    missing = client.post(
        "/conversations/conv-random/messages/stream", json={"content": "swap"}
    )
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["detail"]["code"] == missing.json()["detail"]["code"]
    assert calls == []


def test_conversation_store_outage_returns_503_before_message_mutation(monkeypatch):
    calls = []
    monkeypatch.setattr(
        conversations,
        "_get_conversation",
        lambda *_: (_ for _ in ()).throw(TimeoutError("store canary")),
    )
    monkeypatch.setattr(
        conversations,
        "_send_message_impl",
        lambda **_kwargs: calls.append("message") or None,
    )
    response = _client(conversations.router).post(
        "/conversations/conv-1/messages", json={"content": "hello"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "authorization_temporarily_unavailable"
    assert calls == []
