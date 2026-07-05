from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.deps import get_current_user
from stoa.routers import conversations


def _client(router, prefix: str = "/conversations") -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "student-1", "role": "student"}
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
