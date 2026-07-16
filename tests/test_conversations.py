import json
import asyncio
import subprocess
import sys

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from datetime import datetime, timezone

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.db.repositories import question_repo, user_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import conversations
from stoa.models.attachment import AttachmentStatus, AttachmentSummary
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
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
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def test_send_message_records_chat_usage_without_raw_content(monkeypatch):
    ledger_calls = []
    monkeypatch.setattr(
        conversations.usage_ledger_service,
        "record_usage_event",
        lambda **kwargs: ledger_calls.append(kwargs) or {"idempotency_status": "created"},
    )

    conversations._record_chat_usage(
        student_id="student-1",
        conv_id="conv-1",
        student_message_id="student-message-1",
        subject="math",
        grade="Sek1",
        usage_counter={
            "quotaPeriod": "2026-07-04",
            "counterKey": "USAGE#student-1/CHAT#2026-07-04",
            "counterValue": 2,
        },
        created_at="2026-07-04T10:00:00+00:00",
    )
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
    created = client.post("/conversations", json={"subject": "math", "grade": "Sek1"})
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
    response = _client(conversations.router, actor=_actor(CanonicalRole.PARENT, "parent-1")).get(
        "/conversations/conv-1"
    )
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
    current = _client(conversations.router, actor=_actor(CanonicalRole.TEACHER, "teacher-1")).get(
        "/conversations/conv-1"
    )
    stale = _client(conversations.router, actor=_actor(CanonicalRole.TEACHER, "teacher-2")).get(
        "/conversations/conv-1"
    )
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
    payload = {"content": "swap", "idempotencyKey": "hidden-check"}
    hidden = client.post("/conversations/conv-real/messages/stream", json=payload)
    missing = client.post("/conversations/conv-random/messages/stream", json=payload)
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
        "/conversations/conv-1/messages", json={"content": "hello", "idempotencyKey": "store-outage"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "authorization_temporarily_unavailable"
    assert calls == []


def _attachment_summary() -> AttachmentSummary:
    return AttachmentSummary(
        attachmentId="attachment-1",
        filename="notes.pdf",
        mediaType="application/pdf",
        sizeBytes=123,
        status=AttachmentStatus.ACTIVE,
        createdAt=datetime(2026, 7, 16, tzinfo=timezone.utc),
    )


def test_message_attachment_request_is_typed_bounded_unique_and_nonempty() -> None:
    for attachments in ([], [{"uploadId": "upload-1"}, {"uploadId": "upload-1"}]):
        with pytest.raises(ValidationError):
            conversations.SendMessageRequest.model_validate(
                {"content": "hello", "attachmentIds": attachments}
            )
    with pytest.raises(ValidationError):
        conversations.SendMessageRequest.model_validate(
            {
                "content": "hello",
                "attachmentIds": [{"uploadId": f"upload-{index}"} for index in range(9)],
            }
        )


@pytest.mark.parametrize(
    "key",
    [None, "", "contains space", "x" * 65, "slash/not-safe", "ümlaut"],
)
def test_message_idempotency_key_is_required_bounded_and_safe(key) -> None:
    payload = {"content": "hello"}
    if key is not None:
        payload["idempotencyKey"] = key
    with pytest.raises(ValidationError):
        conversations.SendMessageRequest.model_validate(payload)


def test_message_fingerprint_is_versioned_typed_ordered_and_exact() -> None:
    def fingerprint(content, refs):
        payload = {"content": content, "idempotencyKey": "fingerprint"}
        if refs:
            payload["attachmentIds"] = refs
        return conversations.message_request_fingerprint(
            conversations.SendMessageRequest.model_validate(payload)
        )

    baseline = fingerprint("a|bc", [{"uploadId": "x"}, {"attachmentId": "yz"}])
    variants = {
        fingerprint("ab|c", [{"uploadId": "x"}, {"attachmentId": "yz"}]),
        fingerprint("a|bc ", [{"uploadId": "x"}, {"attachmentId": "yz"}]),
        fingerprint("a|bc", [{"attachmentId": "x"}, {"attachmentId": "yz"}]),
        fingerprint("a|bc", [{"attachmentId": "yz"}, {"uploadId": "x"}]),
        fingerprint("é", []),
        fingerprint("e\u0301", []),
        fingerprint("a|bd", [{"uploadId": "x"}, {"attachmentId": "yz"}]),
    }
    assert baseline not in variants
    assert fingerprint("é", []) != fingerprint("e\u0301", [])
    code = (
        "from stoa.routers.conversations import SendMessageRequest,message_request_fingerprint;"
        "print(message_request_fingerprint(SendMessageRequest.model_validate("
        "{'content':'a|bc','idempotencyKey':'fingerprint','attachmentIds':"
        "[{'uploadId':'x'},{'attachmentId':'yz'}]})))"
    )
    reproduced = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
    assert reproduced == baseline


def _completed_command(body: conversations.SendMessageRequest) -> dict:
    response = conversations.SendMessageResponse(
        studentMessage=conversations.ChatMessage(
            id="student-original", conversationId="conv-1", role="student",
            content=body.content, createdAt="2026-07-16T00:00:00Z",
        ),
        assistantMessage=conversations.ChatMessage(
            id="assistant-original", conversationId="conv-1", role="assistant",
            content="original answer", createdAt="2026-07-16T00:00:01Z",
        ),
    )
    return {
        "owner_id": "student-1",
        "fingerprint": conversations.message_request_fingerprint(body),
        "status": "completed",
        "result_json": response.model_dump_json(),
    }


def test_stage_a_completed_replay_bypasses_consumed_upload_resolution(monkeypatch) -> None:
    body = conversations.SendMessageRequest.model_validate(
        {
            "content": "exact bytes",
            "idempotencyKey": "replay-key",
            "attachmentIds": [{"uploadId": "now-consumed"}],
        }
    )
    command = _completed_command(body)
    effects = []
    monkeypatch.setattr(conversations, "get_table", lambda: object())
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 8)
    monkeypatch.setattr(
        conversations.attachment_service,
        "prepare_message_attachments",
        lambda *_args, **_kwargs: effects.append("prepare"),
    )
    result = conversations._execute_message_command(
        conv_id="conv-1", student_id="student-1", subject="math", grade="Sek1",
        body=body,
        command_context={
            "actor": _actor(),
            "fingerprint": conversations.message_request_fingerprint(body),
            "existing": command,
        },
    )
    assert result.studentMessage.id == "student-original"
    assert result.assistantMessage.id == "assistant-original"
    assert effects == []


def test_stage_a_mismatch_fails_before_attachment_lookup(monkeypatch) -> None:
    body = conversations.SendMessageRequest.model_validate(
        {"content": "changed", "idempotencyKey": "same-key"}
    )
    effects = []
    monkeypatch.setattr(
        conversations.attachment_repo,
        "get_message_command",
        lambda *_args, **_kwargs: {
            "owner_id": "student-1", "fingerprint": "0" * 64, "status": "completed"
        },
    )
    monkeypatch.setattr(
        conversations.attachment_service,
        "prepare_message_attachments",
        lambda *_args, **_kwargs: effects.append("prepare"),
    )
    with pytest.raises(HTTPException) as captured:
        asyncio.run(
            conversations._message_command_dependency(
                "conv-1", body, _actor(), "correlation-1"
            )
        )
    assert captured.value.detail["code"] == "message_idempotency_conflict"
    assert effects == []


def test_new_foreign_attachment_has_zero_command_quota_or_ai_effect(monkeypatch) -> None:
    body = conversations.SendMessageRequest.model_validate(
        {
            "content": "private",
            "idempotencyKey": "foreign-new",
            "attachmentIds": [{"attachmentId": "foreign"}],
        }
    )
    effects = []
    monkeypatch.setattr(conversations, "get_table", lambda: object())
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 8)
    monkeypatch.setattr(
        conversations.attachment_service,
        "prepare_message_attachments",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
        ),
    )
    monkeypatch.setattr(
        conversations.attachment_repo,
        "claim_message_command_and_quota",
        lambda **_kwargs: effects.append("claim"),
    )
    monkeypatch.setattr(
        conversations.ai_service, "get_ai_answer", lambda **_kwargs: effects.append("ai")
    )
    with pytest.raises(AttachmentDecisionError) as captured:
        conversations._execute_message_command(
            conv_id="conv-1", student_id="student-1", subject="math", grade="Sek1",
            body=body,
            command_context={
                "actor": _actor(),
                "fingerprint": conversations.message_request_fingerprint(body),
                "existing": None,
            },
        )
    assert captured.value.code is AttachmentErrorCode.UPLOAD_NOT_FOUND
    assert effects == []


def test_regular_and_stream_message_use_identical_safe_attachment_summary(monkeypatch) -> None:
    summary = _attachment_summary()
    conv = {
        "conversation_id": "conv-1",
        "student_id": "student-1",
        "subject": "math",
        "grade": "Sek1",
    }
    calls = []
    monkeypatch.setattr(conversations, "_get_conversation", lambda *_: conv)
    monkeypatch.setattr(
        conversations.attachment_service,
        "prepare_message_attachments",
        lambda references, actor: calls.append((references, actor.user_id)) or [],
    )
    monkeypatch.setattr(
        conversations,
        "check_and_record_chat",
        lambda *_args, **_kwargs: {
            "quotaPeriod": "2026-07-16",
            "counterKey": "counter",
            "counterValue": 1,
        },
    )
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 8)
    monkeypatch.setattr(conversations, "_attachment_plan_for_student", lambda *_: "free")
    monkeypatch.setattr(
        conversations.attachment_service,
        "ensure_message_attachment_capacity",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(conversations, "_record_chat_usage", lambda **_kwargs: None)
    monkeypatch.setattr(
        conversations,
        "_send_message_impl",
        lambda **kwargs: (
            conversations.ChatMessage(
                id="student-message",
                conversationId=kwargs["conv_id"],
                role="student",
                content=kwargs["content"],
                createdAt="2026-07-16T00:00:00Z",
                attachments=[summary],
            ),
            conversations.ChatMessage(
                id="assistant-message",
                conversationId=kwargs["conv_id"],
                role="assistant",
                content="reply",
                createdAt="2026-07-16T00:00:01Z",
            ),
        ),
    )
    payload = {"content": "use notes", "idempotencyKey": "attachment-parity", "attachmentIds": [{"attachmentId": "attachment-1"}]}
    monkeypatch.setattr(conversations.attachment_repo, "get_message_command", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        conversations,
        "_execute_message_command",
        lambda **kwargs: conversations.SendMessageResponse(
            studentMessage=conversations.ChatMessage(
                id="student-message", conversationId=kwargs["conv_id"], role="student",
                content=kwargs["body"].content, createdAt="2026-07-16T00:00:00Z",
                attachments=[summary],
            ),
            assistantMessage=conversations.ChatMessage(
                id="assistant-message", conversationId=kwargs["conv_id"], role="assistant",
                content="reply", createdAt="2026-07-16T00:00:01Z",
            ),
        ),
    )
    regular = _client(conversations.router).post("/conversations/conv-1/messages", json=payload)
    streamed = _client(conversations.router).post(
        "/conversations/conv-1/messages/stream", json=payload
    )
    safe = regular.json()["studentMessage"]["attachments"][0]
    assert safe == summary.model_dump(mode="json", by_alias=True)
    assert "event: student_message" in streamed.text
    assert f'"attachments": [{json.dumps(safe, separators=(",", ":"))}]' not in streamed.text
    for key, value in safe.items():
        assert json.dumps(value) in streamed.text
    assert "object_key" not in regular.text + streamed.text
    assert len(calls) == 0


def test_conversation_history_batch_projects_only_safe_attachment_summaries(monkeypatch) -> None:
    summary = _attachment_summary()
    monkeypatch.setattr(
        conversations,
        "_get_conversation",
        lambda *_: {
            "conversation_id": "conv-1",
            "student_id": "student-1",
            "subject": "math",
            "grade": "Sek1",
        },
    )
    monkeypatch.setattr(
        conversations,
        "_get_messages",
        lambda *_: [
            {
                "message_id": "message-1",
                "role": "student",
                "content": "my document",
                "created_at": "2026-07-16T00:00:00Z",
                "attachment_ids": ["attachment-1"],
                "object_key": "uploads/private/provider-canary.pdf",
                "extracted_text": "raw extracted canary",
            }
        ],
    )
    monkeypatch.setattr(
        conversations.attachment_service,
        "list_attachment_summaries",
        lambda ids: {"attachment-1": summary} if ids == ["attachment-1"] else {},
    )
    response = _client(conversations.router).get("/conversations/conv-1")
    assert response.status_code == 200
    assert response.json()["messages"][0]["attachments"] == [
        summary.model_dump(mode="json", by_alias=True)
    ]
    assert "provider-canary" not in response.text
    assert "raw extracted canary" not in response.text


def test_bound_attachment_context_reaches_ai_only_after_transaction(monkeypatch) -> None:
    events = []
    stored = []

    class Table:
        def put_item(self, Item):
            stored.append(Item)

        def update_item(self, **_kwargs):
            return {}

    monkeypatch.setattr(conversations, "_get_messages", lambda *_: [])
    monkeypatch.setattr(conversations, "_generate_title", lambda *_: None)
    monkeypatch.setattr(
        conversations.attachment_service,
        "bind_message_attachments",
        lambda **_kwargs: events.append("bind") or [_attachment_summary()],
    )
    monkeypatch.setattr(
        conversations.attachment_service,
        "extract_message_attachment_context",
        lambda *_args, **_kwargs: events.append("extract") or "internal extracted canary",
    )
    monkeypatch.setattr(conversations.boto3, "client", lambda *_args, **_kwargs: object())

    def ai_answer(**kwargs):
        events.append("ai")
        assert kwargs["attachment_context"] == "internal extracted canary"
        return {"steps": ["safe step"], "answer": "safe reply", "hints": []}

    monkeypatch.setattr(conversations.ai_service, "get_ai_answer", ai_answer)
    student, assistant = conversations._send_message_impl(
        conv_id="conv-1",
        student_id="student-1",
        subject="math",
        grade="Sek1",
        content="use my file",
        table=Table(),
        actor=_actor(),
        prepared_attachments=[("attachment", {"attachment_id": "attachment-1"})],
        effective_plan="free",
    )
    assert events == ["bind", "extract", "ai"]
    assert student.attachments == [_attachment_summary()]
    assert (
        "internal extracted canary"
        not in str(stored) + student.model_dump_json() + assistant.model_dump_json()
    )


def test_conversation_dependency_cancellation_stable_error_has_zero_message_ai_effect(
    monkeypatch,
) -> None:
    effects = []
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
        lambda *args, **kwargs: {
            "quotaPeriod": "2026-07-16",
            "counterKey": "opaque-counter",
            "counterValue": 1,
        },
    )
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 8)
    monkeypatch.setattr(conversations, "_get_messages", lambda *_: [])
    monkeypatch.setattr(
        conversations.attachment_repo,
        "get_message_command",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        conversations,
        "_execute_message_command",
        lambda **_kwargs: (_ for _ in ()).throw(
            AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        ),
    )
    monkeypatch.setattr(
        conversations, "_record_chat_usage", lambda **kwargs: effects.append("usage")
    )
    monkeypatch.setattr(
        conversations.attachment_service,
        "bind_message_attachments",
        lambda **kwargs: (_ for _ in ()).throw(
            AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        ),
    )
    monkeypatch.setattr(
        conversations.attachment_service,
        "extract_message_attachment_context",
        lambda *args, **kwargs: effects.append("extract"),
    )
    monkeypatch.setattr(
        conversations.ai_service,
        "get_ai_answer",
        lambda **kwargs: effects.append("ai"),
    )
    response = _client(conversations.router).post(
        "/conversations/conv-1/messages",
        json={"content": "private-message-canary", "idempotencyKey": "dependency-cancel"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "upload_service_unavailable"
    assert response.json()["detail"]["message"] == (
        "Uploads are temporarily unavailable. Try again later."
    )
    assert effects == []
    assert "private-message-canary" not in response.text
