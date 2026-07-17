import json
import asyncio
import hashlib
import subprocess
import sys
import threading

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from datetime import datetime, timezone

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.db.repositories import attachment_repo, question_repo, user_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.config import Settings
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
        "_execute_message_command",
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
        "_execute_message_command",
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
    command_id = str(
        conversations.uuid5(
            conversations.NAMESPACE_URL,
            f"stoa.conversation.send.v1:conv-1:{body.idempotencyKey}",
        )
    )
    student_id = str(conversations.uuid5(conversations.UUID(command_id), "student-message"))
    assistant_id = str(
        conversations.uuid5(conversations.UUID(command_id), "assistant-message")
    )
    response = conversations.SendMessageResponse(
        studentMessage=conversations.ChatMessage(
            id=student_id, conversationId="conv-1", role="student",
            content=body.content, createdAt="2026-07-16T00:00:00Z",
        ),
        assistantMessage=conversations.ChatMessage(
            id=assistant_id, conversationId="conv-1", role="assistant",
            content="original answer", createdAt="2026-07-16T00:00:01Z",
        ),
    )
    requested = [
        {
            "kind": "upload" if reference.upload_id else "attachment",
            "id": str(reference.upload_id or reference.attachment_id),
            "attachment_id": (
                str(conversations.uuid5(conversations.UUID(command_id), f"attachment:{index}"))
                if reference.upload_id
                else str(reference.attachment_id)
            ),
        }
        for index, reference in enumerate(body.attachmentIds or [])
    ]
    return {
        "entity_type": "message_command",
        "schema_version": "message-command.v2",
        "command_id": command_id,
        "conversation_id": "conv-1",
        "owner_id": "student-1",
        "idempotency_key": body.idempotencyKey,
        "fingerprint": conversations.message_request_fingerprint(body),
        "status": "completed",
        "student_message_id": student_id,
        "assistant_message_id": assistant_id,
        "attachment_count": len(requested),
        "requested_attachments": requested,
        "deterministic_attachment_ids": [
            item["attachment_id"]
            for item in requested
            if item["kind"] == "upload"
        ],
        "history_message_ids": [],
        "history_fingerprint": conversations._history_snapshot_fingerprint([]),
        "history_anchor_message_id": student_id,
        "history_anchor_created_at": "2026-07-16T00:00:00Z",
        "created_at": "2026-07-16T00:00:00Z",
        "result_json": response.model_dump_json(),
    }


def test_stage_a_completed_replay_bypasses_consumed_upload_resolution(
    monkeypatch, caplog
) -> None:
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
    assert result.studentMessage.id == command["student_message_id"]
    assert result.assistantMessage.id == command["assistant_message_id"]
    assert effects == []
    assert "exact bytes" not in caplog.text
    assert "original answer" not in caplog.text


def test_title_failure_telemetry_excludes_title_input_and_provider_details(
    monkeypatch, caplog
) -> None:
    canaries = (
        "TITLE-INPUT-PRIVATE-CANARY",
        "TITLE-PROVIDER-EXCEPTION-CANARY",
        "private-model-identifier",
    )
    monkeypatch.setattr(
        conversations.boto3,
        "client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError(" ".join(canaries[1:]))
        ),
    )
    assert conversations._generate_title(
        canaries[0], "math", correlation_id="server-title-correlation"
    ) is None
    assert "event_category=title_generation_failed" in caplog.text
    assert "exception_class=RuntimeError" in caplog.text
    for canary in canaries:
        assert canary not in caplog.text


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
    monkeypatch.setattr(conversations, "_get_messages", lambda *_: [])
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


def test_synchronized_duplicate_commands_converge_to_one_complete_effect_set(
    monkeypatch,
) -> None:
    body = conversations.SendMessageRequest.model_validate(
        {
            "content": "concurrent exact content",
            "idempotencyKey": "concurrent-key",
            "attachmentIds": [{"uploadId": "fresh-upload-1"}],
        }
    )
    fingerprint = conversations.message_request_fingerprint(body)
    command_state = {}
    effects = {"claim": 0, "bind": 0, "extract": 0, "ai": 0, "complete": 0}
    lock = threading.Lock()
    claim_barrier = threading.Barrier(2)
    summary = _attachment_summary()
    deterministic_attachment_ids = []

    monkeypatch.setattr(conversations, "get_table", lambda: object())
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 8)
    monkeypatch.setattr(conversations, "_attachment_plan_for_student", lambda *_: "free")
    monkeypatch.setattr(conversations, "_get_messages", lambda *_: [])
    monkeypatch.setattr(conversations.time, "sleep", lambda *_: threading.Event().wait(0.01))
    monkeypatch.setattr(conversations.boto3, "client", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        conversations.attachment_service,
        "prepare_message_attachments",
        lambda *_args, **_kwargs: [("upload", {"upload_id": "fresh-upload-1"})],
    )
    monkeypatch.setattr(
        conversations.attachment_service,
        "ensure_message_attachment_capacity",
        lambda *_args, **_kwargs: None,
    )

    def claim(**kwargs):
        claim_barrier.wait()
        with lock:
            effects["claim"] += 1
            if command_state:
                return attachment_repo.MessageCommandResult(
                    attachment_repo.MessageCommandDisposition.RESUME,
                    command=dict(command_state),
                    counter_value=int(command_state.get("counter_value", 0)),
                )
            command_state.update(kwargs["command"])
            command_state["counter_value"] = 1
            return True, 1

    def bind(**kwargs):
        with lock:
            effects["bind"] += 1
            deterministic_attachment_ids.append(
                tuple(kwargs["deterministic_attachment_ids"])
            )
            command_state["status"] = "message_committed"
        return [summary]

    def get_command(*_args, **_kwargs):
        with lock:
            return dict(command_state) if command_state else None

    def claim_ai(**kwargs):
        with lock:
            if command_state.get("status") != "message_committed":
                return False, int(command_state.get("attempt", 0))
            command_state.update(
                status="ai_running", leaseOwner=kwargs["lease_owner"], attempt=1
            )
            return True, 1

    def complete(**kwargs):
        with lock:
            effects["complete"] += 1
            command_state.update(status="completed", result_json=kwargs["result_json"])
        return True

    monkeypatch.setattr(conversations.attachment_repo, "claim_message_command_and_quota", claim)
    monkeypatch.setattr(conversations.attachment_repo, "get_message_command", get_command)
    monkeypatch.setattr(conversations.attachment_repo, "claim_message_ai_lease", claim_ai)
    monkeypatch.setattr(conversations.attachment_repo, "complete_message_command", complete)
    monkeypatch.setattr(conversations.attachment_service, "bind_message_attachments", bind)
    monkeypatch.setattr(
        conversations.attachment_service,
        "extract_message_attachment_context",
        lambda *_args, **_kwargs: effects.__setitem__("extract", effects["extract"] + 1) or "",
    )
    monkeypatch.setattr(
        conversations.ai_service,
        "get_ai_answer",
        lambda **_kwargs: effects.__setitem__("ai", effects["ai"] + 1)
        or {"steps": ["one"], "answer": "safe", "hints": []},
    )
    results = []
    failures = []

    def run():
        try:
            results.append(
                conversations._execute_message_command(
                    conv_id="conv-1",
                    student_id="student-1",
                    subject="math",
                    grade="Sek1",
                    body=body,
                    command_context={"actor": _actor(), "fingerprint": fingerprint, "existing": None},
                )
            )
        except Exception as exc:  # pragma: no cover - assertion reports details
            failures.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == []
    assert len(results) == 2
    assert results[0].model_dump() == results[1].model_dump()
    assert effects == {
        "claim": 2, "bind": 1, "extract": 1, "ai": 1, "complete": 1
    }
    expected_attachment_id = str(
        conversations.uuid5(
            conversations.UUID(command_state["command_id"]), "attachment:0"
        )
    )
    assert deterministic_attachment_ids == [(expected_attachment_id,)]


def test_committed_lost_response_same_fingerprint_retry_has_one_effect_set(
    monkeypatch,
) -> None:
    body = conversations.SendMessageRequest.model_validate(
        {
            "content": "exact committed content",
            "idempotencyKey": "committed-lost-response",
            "attachmentIds": [{"uploadId": "fresh-upload-1"}],
        }
    )
    fingerprint = conversations.message_request_fingerprint(body)
    command_state: dict = {}
    stored_student: dict = {}
    stored_attachments: dict[str, dict] = {}
    effects = {"claim": 0, "bind": 0, "extract": 0, "ai": 0, "complete": 0}

    class Table:
        def get_item(self, **_kwargs):
            return {"Item": dict(stored_student)} if stored_student else {}

    table = Table()
    monkeypatch.setattr(conversations, "get_table", lambda: table)
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 8)
    monkeypatch.setattr(conversations, "_attachment_plan_for_student", lambda *_: "free")
    monkeypatch.setattr(
        conversations,
        "_get_messages",
        lambda *_: [dict(stored_student)] if stored_student else [],
    )
    monkeypatch.setattr(conversations.time, "sleep", lambda *_: None)
    monkeypatch.setattr(conversations.boto3, "client", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        conversations.attachment_service,
        "prepare_message_attachments",
        lambda *_args, **_kwargs: [("upload", {"upload_id": "fresh-upload-1"})],
    )
    monkeypatch.setattr(
        conversations.attachment_service,
        "ensure_message_attachment_capacity",
        lambda *_args, **_kwargs: None,
    )

    def claim(**kwargs):
        effects["claim"] += 1
        command_state.update(kwargs["command"], counter_value=1)
        return True, 1

    def bind(**kwargs):
        effects["bind"] += 1
        attachment_id = kwargs["deterministic_attachment_ids"][0]
        stored_student.update(kwargs["message"], attachment_ids=[attachment_id])
        stored_attachments[attachment_id] = {
            "attachment_id": attachment_id,
            "owner_id": "student-1",
            "original_filename": "notes.txt",
            "detected_type": "text/plain",
            "content_length": 12,
            "created_at": "2026-07-16T00:00:00Z",
            "status": "active",
            "immutable_object_key": "private-key-canary",
            "immutable_version_id": "private-version-canary",
            "immutable_etag": "private-etag-canary",
            "content_sha256": hashlib.sha256(b"private text").hexdigest(),
        }
        command_state["status"] = "message_committed"
        raise RuntimeError("committed-response-lost-provider-private-canary")

    def get_command(*_args, **_kwargs):
        return dict(command_state) if command_state else None

    def claim_ai(**kwargs):
        command_state.update(
            status="ai_running", leaseOwner=kwargs["lease_owner"], attempt=1
        )
        return True, 1

    def complete(**kwargs):
        effects["complete"] += 1
        command_state.update(status="completed", result_json=kwargs["result_json"])
        return True

    monkeypatch.setattr(conversations.attachment_repo, "claim_message_command_and_quota", claim)
    monkeypatch.setattr(conversations.attachment_repo, "get_message_command", get_command)
    monkeypatch.setattr(
        conversations.attachment_repo,
        "get_attachments",
        lambda *_args, **_kwargs: dict(stored_attachments),
    )
    monkeypatch.setattr(conversations.attachment_service, "bind_message_attachments", bind)
    monkeypatch.setattr(conversations.attachment_repo, "claim_message_ai_lease", claim_ai)
    monkeypatch.setattr(conversations.attachment_repo, "complete_message_command", complete)
    monkeypatch.setattr(
        conversations.attachment_service,
        "extract_message_attachment_context",
        lambda *_args, **_kwargs: effects.__setitem__("extract", effects["extract"] + 1)
        or "",
    )
    monkeypatch.setattr(
        conversations.ai_service,
        "get_ai_answer",
        lambda **_kwargs: effects.__setitem__("ai", effects["ai"] + 1)
        or {"steps": [], "answer": "original safe answer", "hints": []},
    )

    first = conversations._execute_message_command(
        conv_id="conv-1",
        student_id="student-1",
        subject="math",
        grade="Sek1",
        body=body,
        command_context={"actor": _actor(), "fingerprint": fingerprint, "existing": None},
    )
    replay = conversations._execute_message_command(
        conv_id="conv-1",
        student_id="student-1",
        subject="math",
        grade="Sek1",
        body=body,
        command_context={
            "actor": _actor(),
            "fingerprint": fingerprint,
            "existing": dict(command_state),
        },
    )

    assert first.model_dump() == replay.model_dump()
    assert effects == {"claim": 1, "bind": 1, "extract": 1, "ai": 1, "complete": 1}
    assert len(stored_attachments) == 1
    assert "private-canary" not in first.model_dump_json()


class _ConversationBodySpy:
    def __init__(
        self,
        data: bytes,
        *,
        read_exception: Exception | None = None,
        close_exception: Exception | None = None,
    ) -> None:
        self.data = data
        self.offset = 0
        self.read_exception = read_exception
        self.close_exception = close_exception
        self.close_count = 0

    def read(self, limit: int) -> bytes:
        if self.read_exception is not None:
            raise self.read_exception
        value = self.data[self.offset : self.offset + limit]
        self.offset += len(value)
        return value

    def close(self) -> None:
        self.close_count += 1
        if self.close_exception is not None:
            raise self.close_exception


class _MalformedConversationBodySpy:
    def __init__(self, read_shape: str) -> None:
        self.read_shape = read_shape
        self.close_count = 0

    def __getattribute__(self, name: str):
        if name == "read":
            shape = object.__getattribute__(self, "read_shape")
            if shape == "missing":
                raise AttributeError(name)
            if shape == "property_raises":
                raise RuntimeError("conversation-read-property-private-canary")
            if shape == "non_callable":
                return None
        return object.__getattribute__(self, name)

    def close(self) -> None:
        self.close_count += 1


@pytest.mark.parametrize("read_shape", ["missing", "non_callable", "property_raises"])
def test_conversation_non_readable_body_ownership_closes_once(
    read_shape: str,
) -> None:
    body = _MalformedConversationBodySpy(read_shape)

    class S3:
        def get_object(self, **kwargs):
            assert kwargs["VersionId"] == "immutable-version"
            return {
                "Body": body,
                "ETag": "immutable-etag",
                "ContentLength": len(b"private text"),
            }

    result = conversations.attachment_service.extract_message_attachment_context(
        [
            (
                "attachment",
                {
                    "immutable_object_key": "private-key-canary",
                    "immutable_version_id": "immutable-version",
                    "immutable_etag": "immutable-etag",
                    "content_sha256": hashlib.sha256(b"private text").hexdigest(),
                    "content_length": len(b"private text"),
                    "detected_type": "text/plain",
                    "original_filename": "private.txt",
                },
            )
        ],
        s3=S3(),
        settings=Settings(s3_images_bucket="private-bucket"),
    )

    assert result == "[attachment:service_unavailable]"
    assert body.close_count == 1
    assert "private-canary" not in result


@pytest.mark.parametrize(
    "case,disposition,expected,error_code",
    [
        ("success", "ready", "private text", None),
        ("checksum", "retryable", "", AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE),
        ("parser", "invalid", "", AttachmentErrorCode.UPLOAD_INVALID),
        (
            "read_exception",
            "retryable",
            "",
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE,
        ),
        (
            "close_exception",
            "retryable",
            "",
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE,
        ),
    ],
)
def test_conversation_exact_version_body_closes_once_on_every_extraction_exit(
    monkeypatch, case: str, disposition: str, expected: str, error_code
) -> None:
    data = b"private text"
    body = _ConversationBodySpy(
        data,
        read_exception=(RuntimeError("read-provider-canary") if case == "read_exception" else None),
        close_exception=(RuntimeError("close-provider-canary") if case == "close_exception" else None),
    )

    class S3:
        def get_object(self, **kwargs):
            assert kwargs["VersionId"] == "immutable-version"
            return {
                "Body": body,
                "ETag": "immutable-etag",
                "ContentLength": len(data),
            }

    if case == "parser":
        monkeypatch.setattr(
            conversations.attachment_service,
            "parse_document_isolated",
            lambda *_args, **_kwargs: __import__(
                "stoa.services.document_parser_worker", fromlist=["ParserResult"]
            ).ParserResult(category="invalid_document"),
        )
    checksum = hashlib.sha256(data).hexdigest()
    if case == "checksum":
        checksum = "0" * 64
    item = {
        "immutable_object_key": "private-key-canary",
        "immutable_version_id": "immutable-version",
        "immutable_etag": "immutable-etag",
        "content_sha256": checksum,
        "content_length": len(data),
        "detected_type": "text/plain",
        "original_filename": "private.txt",
    }
    result = conversations.attachment_service.extract_message_attachment_context(
        [("attachment", item)],
        s3=S3(),
        settings=Settings(s3_images_bucket="private-bucket"),
    )
    assert result.disposition.value == disposition
    assert result.context == expected
    assert result.error_code is error_code
    assert body.close_count == 1
    assert "provider-canary" not in result


def test_message_polling_is_bounded_to_twenty_fifty_millisecond_waits(monkeypatch) -> None:
    sleeps = []
    monkeypatch.setattr(
        conversations.attachment_repo,
        "get_message_command",
        lambda *_args, **_kwargs: {
            "entity_type": "message_command",
            "schema_version": "message-command.v2",
            "status": "ai_running",
            "owner_id": "student-1",
            "fingerprint": "f" * 64,
        },
    )
    monkeypatch.setattr(conversations.time, "sleep", lambda value: sleeps.append(value))
    with pytest.raises(AttachmentDecisionError) as captured:
        conversations._wait_for_message_command(
            "conv-1",
            "bounded-key",
            "f" * 64,
            table=object(),
            owner_id="student-1",
        )
    assert captured.value.code is AttachmentErrorCode.MESSAGE_IN_PROGRESS
    assert sleeps == [0.05] * 20


def _transport_body() -> conversations.SendMessageRequest:
    return conversations.SendMessageRequest.model_validate(
        {"content": "transport-private-canary", "idempotencyKey": "transport-key"}
    )


def _install_transport_happy_path(monkeypatch) -> None:
    monkeypatch.setattr(conversations, "get_table", lambda: object())
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 8)
    monkeypatch.setattr(conversations, "_get_messages", lambda *_: [])
    monkeypatch.setattr(
        conversations.attachment_service,
        "prepare_message_attachments",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        conversations.attachment_repo,
        "claim_message_command_and_quota",
        lambda **_kwargs: (True, 1),
    )
    monkeypatch.setattr(
        conversations.attachment_service,
        "bind_message_attachments",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        conversations.attachment_repo,
        "claim_message_ai_lease",
        lambda **_kwargs: (True, 1),
    )
    monkeypatch.setattr(
        conversations.ai_service,
        "get_ai_answer",
        lambda **_kwargs: {"steps": [], "answer": "safe", "hints": []},
    )
    monkeypatch.setattr(
        conversations.attachment_repo,
        "complete_message_command",
        lambda **_kwargs: True,
    )


def test_stage_a_transport_is_structured_retry_without_diagnostics(monkeypatch) -> None:
    body = _transport_body()
    monkeypatch.setattr(
        conversations.attachment_repo,
        "get_message_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("stage-a-provider-table-private-canary")
        ),
    )

    with pytest.raises(HTTPException) as captured:
        asyncio.run(
            conversations._message_command_dependency(
                "conv-1", body, _actor(), "server-correlation"
            )
        )

    assert captured.value.status_code == 503
    assert captured.value.detail == {
        "code": "upload_service_unavailable",
        "message": "Uploads are temporarily unavailable. Try again later.",
        "correlationId": "server-correlation",
    }
    assert captured.value.headers == {
        "X-Correlation-ID": "server-correlation",
        "Retry-After": "30",
    }
    assert "private-canary" not in str(captured.value.detail)


def test_regular_sse_stage_a_transport_has_identical_structured_retry(
    monkeypatch,
) -> None:
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
        conversations.attachment_repo,
        "get_message_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("regular-sse-stage-a-provider-private-canary")
        ),
    )
    payload = {
        "content": "request-private-canary",
        "idempotencyKey": "regular-sse-transport",
    }
    client = _client(conversations.router)

    regular = client.post("/conversations/conv-1/messages", json=payload)
    streamed = client.post("/conversations/conv-1/messages/stream", json=payload)

    for response in (regular, streamed):
        assert response.status_code == 503
        assert set(response.json()["detail"]) == {"code", "message", "correlationId"}
        assert response.json()["detail"]["code"] == "upload_service_unavailable"
        assert response.headers["Retry-After"] == "30"
        assert response.headers["X-Correlation-ID"] == response.json()["detail"][
            "correlationId"
        ]
        assert "private-canary" not in response.text
    assert regular.json()["detail"]["message"] == streamed.json()["detail"]["message"]


@pytest.mark.parametrize(
    "stage",
    [
        "command_claim_transport",
        "attachment_transaction_transport",
        "race_reread_transport",
        "ai_lease_transport",
        "ai_lease_reread_transport",
        "terminal_transport",
        "completion_transport",
        "completion_lost_response_reread_transport",
    ],
)
def test_conversation_repository_transport_stages_are_structured_retry(
    monkeypatch, stage: str
) -> None:
    body = _transport_body()
    _install_transport_happy_path(monkeypatch)
    failure = RuntimeError(f"{stage}-provider-table-private-canary")

    if stage == "command_claim_transport":
        monkeypatch.setattr(
            conversations.attachment_repo,
            "claim_message_command_and_quota",
            lambda **_kwargs: (_ for _ in ()).throw(failure),
        )
    elif stage == "attachment_transaction_transport":
        monkeypatch.setattr(
            conversations.attachment_service,
            "bind_message_attachments",
            lambda **_kwargs: (_ for _ in ()).throw(failure),
        )
    elif stage == "race_reread_transport":
        monkeypatch.setattr(
            conversations.attachment_repo,
            "claim_message_command_and_quota",
            lambda **_kwargs: (False, 0),
        )
        monkeypatch.setattr(
            conversations.attachment_repo,
            "get_message_command",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
        )
    elif stage == "ai_lease_transport":
        monkeypatch.setattr(
            conversations.attachment_repo,
            "claim_message_ai_lease",
            lambda **_kwargs: (_ for _ in ()).throw(failure),
        )
    elif stage == "ai_lease_reread_transport":
        monkeypatch.setattr(
            conversations.attachment_repo,
            "claim_message_ai_lease",
            lambda **_kwargs: (False, 1),
        )
        monkeypatch.setattr(
            conversations.attachment_repo,
            "get_message_command",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
        )
    elif stage == "terminal_transport":
        monkeypatch.setattr(
            conversations.attachment_repo,
            "claim_message_ai_lease",
            lambda **_kwargs: (False, 3),
        )
        monkeypatch.setattr(
            conversations.attachment_repo,
            "get_message_command",
            lambda *_args, **_kwargs: {
                "entity_type": "message_command",
                "schema_version": "message-command.v2",
                "status": "ai_running",
                "owner_id": "student-1",
                "expiresAt": 0,
                "attempt": 3,
                "fingerprint": conversations.message_request_fingerprint(body),
            },
        )
        monkeypatch.setattr(
            conversations.attachment_repo,
            "mark_message_command_terminal",
            lambda **_kwargs: (_ for _ in ()).throw(failure),
        )
    elif stage == "completion_transport":
        monkeypatch.setattr(
            conversations.attachment_repo,
            "complete_message_command",
            lambda **_kwargs: (_ for _ in ()).throw(failure),
        )
    else:
        monkeypatch.setattr(
            conversations.attachment_repo,
            "complete_message_command",
            lambda **_kwargs: False,
        )
        monkeypatch.setattr(
            conversations.attachment_repo,
            "get_message_command",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
        )

    with pytest.raises(AttachmentDecisionError) as captured:
        conversations._execute_message_command(
            conv_id="conv-1",
            student_id="student-1",
            subject="math",
            grade="Sek1",
            body=body,
            command_context={
                "actor": _actor(),
                "fingerprint": conversations.message_request_fingerprint(body),
                "existing": None,
            },
        )

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert "private-canary" not in str(captured.value)


def test_replay_poll_transport_is_structured_retry(monkeypatch) -> None:
    monkeypatch.setattr(
        conversations.attachment_repo,
        "get_message_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("replay-poll-provider-table-private-canary")
        ),
    )

    with pytest.raises(AttachmentDecisionError) as captured:
        conversations._wait_for_message_command(
            "conv-1", "transport-key", "f" * 64, table=object()
        )

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert "private-canary" not in str(captured.value)


def test_resume_stored_message_transport_is_structured_retry(monkeypatch) -> None:
    body = _transport_body()
    _install_transport_happy_path(monkeypatch)
    monkeypatch.setattr(
        conversations,
        "_get_messages",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("stored-message-provider-table-private-canary")
        ),
    )

    with pytest.raises(AttachmentDecisionError) as captured:
        conversations._execute_message_command(
            conv_id="conv-1",
            student_id="student-1",
            subject="math",
            grade="Sek1",
            body=body,
            command_context={
                "actor": _actor(),
                "fingerprint": conversations.message_request_fingerprint(body),
                "existing": {
                    "status": "message_committed",
                    "owner_id": "student-1",
                    "fingerprint": conversations.message_request_fingerprint(body),
                    "created_at": "2026-07-16T00:00:00Z",
                },
            },
        )

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert "private-canary" not in str(captured.value)


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
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 8)
    monkeypatch.setattr(conversations, "_attachment_plan_for_student", lambda *_: "free")
    monkeypatch.setattr(
        conversations.attachment_service,
        "ensure_message_attachment_capacity",
        lambda *_args, **_kwargs: None,
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
