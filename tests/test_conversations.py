import hashlib
import subprocess
import sys
import threading
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from datetime import datetime, timezone

from audit_helpers import MemoryAuthorizationAuditSink
from fakes.dynamodb import as_stored as _as_stored
from stoa.db.repositories import attachment_repo, question_repo, user_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.config import Settings
from stoa.services import locale_service, message_catalog
from stoa.routers import conversations
from stoa.services.ask_question import _answering
from stoa.services.ask_question import _transcript
from stoa.models.attachment import AttachmentStatus, AttachmentSummary
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import CanonicalRole, CapabilityGrant
from stoa.services import ask_question
from stoa.services.ask_question import _store as ask_question_store
from stoa.services.ask_question import dispatch
from stoa.services import attachment_service
from uuid import UUID, uuid5
from fakes.ask_question import (
    CONV,
    QUESTION,
    _actor,
    _command_row,
    _commit,
    _messages,
    _parse_in_process,
    _submit,
    _upload,
)
from fakes.ask_question import _client as _question_client
from fakes.ask_question import _events as _sse_events
from fakes.ask_question import bucket as bucket  # noqa: F401 - the fixture
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture


@pytest.fixture(autouse=True)
def _no_memory_personalisation(stub_memory_summary) -> None:
    """Message-command tests mock every other I/O dependency; do the same for
    the adaptive-memory lookup the AI prompt enrichment performs."""


def _client(router, prefix: str = "/conversations", actor=None) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_actor] = lambda: actor or _actor()
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def _owned_conversation(monkeypatch) -> None:
    monkeypatch.setattr(
        conversations,
        "read_conversation",
        lambda conv_id: {"conversation_id": conv_id, "student_id": "student-1"},
    )


def _with_help_request(monkeypatch, **fields):
    """The conversation's help request (#189): its own record, `CONV#…/HELP`."""
    from fakes.dynamodb import FakeTable

    table = FakeTable()
    if fields.pop("asked", True):
        table.seed(
            {
                "PK": "CONV#conv-1",
                "SK": "HELP",
                "entity_type": "help_request",
                "conversation_id": "conv-1",
                "escalation_request_id": "conv-1",
                "student_id": "student-1",
                "owner_id": "student-1",
                "account_fence_generation": 1,
                "version": 1,
                "escalation_status": "pending",
                "escalated_at": "2026-08-24T08:00:00+00:00",
                "created_at": "2026-08-24T08:00:00+00:00",
                "updated_at": "2026-08-24T08:00:00+00:00",
                **fields,
            }
        )
    monkeypatch.setattr(conversations, "get_table", lambda: table)
    monkeypatch.setattr(_answering, "get_table", lambda: table)
    monkeypatch.setattr(_transcript, "get_table", lambda: table)
    _owned_conversation(monkeypatch)
    return table


def test_teacher_help_status_names_the_teacher_dispatch_actually_bound(monkeypatch):
    """Dispatch records the teacher on dispatched_teacher_id, not current_teacher."""
    _with_help_request(
        monkeypatch, dispatch_status="dispatched", dispatched_teacher_id="teacher-1"
    )
    monkeypatch.setattr(
        conversations.user_repo, "get_user", lambda _id, **_kwargs: {"name": "Test Teacher"}
    )

    response = _client(conversations.teacher_help_router, "/teacher-help").get(
        "/teacher-help/conversations/conv-1/request"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["teacherName"] == "Test Teacher"
    assert body["status"] == "assigned"


def test_a_teacher_without_a_name_is_not_shown_to_the_student_by_email(monkeypatch):
    # #65: with no name on the teacher's profile the status card showed the
    # teacher's email address to the student.
    _with_help_request(
        monkeypatch, dispatch_status="dispatched", dispatched_teacher_id="teacher-1"
    )
    monkeypatch.setattr(
        conversations.user_repo,
        "get_user",
        lambda _id, **_kwargs: {"name": "", "email": "frau.keller@example.com"},
    )

    response = _client(conversations.teacher_help_router, "/teacher-help").get(
        "/teacher-help/conversations/conv-1/request"
    )

    assert response.status_code == 200
    assert response.json()["teacherName"] is None
    assert "frau.keller@example.com" not in response.text


def test_teacher_help_status_is_absent_before_any_escalation(monkeypatch):
    _with_help_request(monkeypatch, asked=False)

    response = _client(conversations.teacher_help_router, "/teacher-help").get(
        "/teacher-help/conversations/conv-1/request"
    )

    assert response.status_code == 404


def test_conversation_teacher_help_records_support_visible_usage(monkeypatch):
    ledger_calls = []
    monkeypatch.setattr(
        conversations.teacher_support_allowance_service,
        "admit_teacher_support_case",
        lambda *, persist_case, **_kwargs: (
            conversations.teacher_support_allowance_service.TeacherSupportAdmissionResult(
                conversations.teacher_support_allowance_service.TeacherSupportAdmissionDisposition.ADMITTED
            )
            if persist_case(())
            else None
        ),
    )

    from stoa.services import teacher_dispatch_service

    table = _escalation_table()
    for module in (conversations, teacher_dispatch_service):
        monkeypatch.setattr(module, "get_table", lambda table=table: table)
    monkeypatch.setattr(
        conversations,
        "read_conversation",
        lambda conv_id: dict(table.rows[(f"CONV#{conv_id}", "CONV")]),
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


def test_repeat_teacher_help_replays_the_existing_escalation(monkeypatch):
    """A second request answers with the conversation's existing help request.

    It used to run admission again, where persist_case declined every attempt
    and the exhausted retry loop reached the student as a 503.
    """
    admissions = []

    def _record_admission(*, persist_case, **kwargs):
        admissions.append(kwargs)
        persist_case(())
        return conversations.teacher_support_allowance_service.TeacherSupportAdmissionResult(
            conversations.teacher_support_allowance_service.TeacherSupportAdmissionDisposition.RETRYABLE
        )

    monkeypatch.setattr(
        conversations.teacher_support_allowance_service,
        "admit_teacher_support_case",
        _record_admission,
    )
    table = _with_help_request(
        monkeypatch,
        # Dispatch writes the teacher, the status and the deadline together;
        # a teacher is named only while that offer is live (#86).
        dispatched_teacher_id="teacher-1",
        dispatch_status="dispatched",
        dispatch_deadline_at="2999-01-01T00:00:00+00:00",
        updated_at="2026-08-24T08:05:00+00:00",
    )
    table.seed_active_account("student-1")
    monkeypatch.setattr(
        conversations.user_repo, "get_user", lambda _id, **_kwargs: {"name": "Test Teacher"}
    )
    ledger_calls = []
    monkeypatch.setattr(
        conversations.usage_ledger_service,
        "record_usage_event",
        lambda **kwargs: ledger_calls.append(kwargs) or {"idempotency_status": "duplicate"},
    )

    response = _client(conversations.teacher_help_router, "/teacher-help").post(
        "/teacher-help/request",
        json={"conversationId": "conv-1", "message": "please help"},
    )

    assert response.status_code == 200
    body = response.json()
    # A help request's id is its conversation's (#189).
    assert body["requestId"] == "conv-1"
    assert body["teacherName"] == "Test Teacher"
    assert body["status"] == "assigned"
    assert admissions == []
    # The repeat still owes the usage row a failed first attempt may have left
    # unwritten, keyed by the request it answers with, not by this call.
    (ledger_call,) = ledger_calls
    assert ledger_call["request_correlation_id"] == "conv-1"
    assert ledger_call["created_at"] == "2026-08-24T08:00:00+00:00"
    assert ledger_call["quota_period"] == "2026-08-24"
    assert ledger_call["idempotency_key"].endswith("conv-1")


def test_teacher_help_retryable_admission_stays_out_of_student_words(monkeypatch):
    admissions = []
    monkeypatch.setattr(
        conversations.teacher_support_allowance_service,
        "admit_teacher_support_case",
        lambda **kwargs: admissions.append(kwargs)
        or conversations.teacher_support_allowance_service.TeacherSupportAdmissionResult(
            conversations.teacher_support_allowance_service.TeacherSupportAdmissionDisposition.RETRYABLE
        ),
    )
    table = _escalation_table()
    monkeypatch.setattr(conversations, "get_table", lambda: table)
    monkeypatch.setattr(_answering, "get_table", lambda: table)
    monkeypatch.setattr(_transcript, "get_table", lambda: table)
    monkeypatch.setattr(
        conversations,
        "read_conversation",
        lambda conv_id: dict(table.rows[(f"CONV#{conv_id}", "CONV")]),
    )

    response = _client(conversations.teacher_help_router, "/teacher-help").post(
        "/teacher-help/request",
        json={"conversationId": "conv-1"},
    )

    assert response.status_code == 503
    # The refusal came from the admission, and nothing was written for it.
    assert len(admissions) == 1
    assert ("CONV#conv-1", "HELP") not in table.rows
    detail = response.json()["detail"]
    assert detail["code"] == "teacher_support_admission_recoverable"
    assert "admission" not in detail["message"].lower()


def test_conversation_list_and_create_derive_owner_from_actor(table, monkeypatch):
    listed = []

    def stored() -> list[dict[str, Any]]:
        return [row for row in table.rows.values() if row.get("SK") == "CONV"]

    already = len(stored())
    monkeypatch.setattr(
        conversations,
        "_list_conversations",
        lambda student_id: listed.append(student_id)
        or conversations.ConversationListPage([], False),
    )
    client = _client(conversations.router)
    assert client.get("/conversations").status_code == 200
    created = client.post("/conversations", json={"subject": "math", "grade": "Sek1"})
    assert created.status_code == 201
    assert listed == ["student-1"]
    [new] = [row for row in stored() if row["conversation_id"] == created.json()["id"]]
    assert new["student_id"] == "student-1"

    substituted = client.post(
        "/conversations",
        json={"subject": "math", "grade": "Sek1", "studentId": "student-2"},
    )
    assert substituted.status_code == 422
    assert len(stored()) == already + 1


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
    monkeypatch.setattr(conversations, "read_conversation", lambda *_: conv)
    monkeypatch.setattr(conversations, "read_messages", lambda *_: [])
    monkeypatch.setattr(_answering, "read_messages", lambda *_: [])
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
    monkeypatch.setattr(conversations, "read_conversation", lambda *_: conv)
    monkeypatch.setattr(user_repo, "get_parent_student_binding", lambda *_: None)
    monkeypatch.setattr(user_repo, "get_student_parent_binding", lambda *_: None)
    monkeypatch.setattr(
        user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
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
    monkeypatch.setattr(conversations, "read_conversation", lambda *_: conv)
    monkeypatch.setattr(conversations, "read_messages", lambda *_: [])
    monkeypatch.setattr(_answering, "read_messages", lambda *_: [])
    monkeypatch.setattr(question_repo, "get_question", lambda *_: question)
    monkeypatch.setattr(question_repo, "get_teacher_session", lambda *_: None)
    monkeypatch.setattr(question_repo, "get_teacher_assignment", lambda *_: None)
    monkeypatch.setattr(user_repo, "get_user", lambda user_id, **_kwargs: accounts.get(user_id))
    current = _client(conversations.router, actor=_actor(CanonicalRole.TEACHER, "teacher-1")).get(
        "/conversations/conv-1"
    )
    stale = _client(conversations.router, actor=_actor(CanonicalRole.TEACHER, "teacher-2")).get(
        "/conversations/conv-1"
    )
    assert current.status_code == 200
    assert stale.status_code == 404
    assert stale.json()["detail"]["code"] == "resource_not_found"


def test_other_actor_and_random_conversation_are_hidden_before_stream_bytes(
    table, model
) -> None:
    client = _question_client(actor=_actor(user_id="student-2"))
    payload = {"content": "swap", "idempotencyKey": "hidden-check"}
    before = dict(table.rows)

    hidden = client.post(f"/conversations/{CONV}/messages/stream", json=payload)
    missing = client.post("/conversations/conv-random/messages/stream", json=payload)

    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["detail"]["code"] == missing.json()["detail"]["code"]
    assert table.rows == before
    assert model.calls == []


def test_conversation_store_outage_returns_503_before_message_mutation(
    table, model, monkeypatch
) -> None:
    def outage(**_kwargs: Any) -> Any:
        raise TimeoutError("store canary")

    monkeypatch.setattr(table, "get_item", outage)
    before = dict(table.rows)

    response = _question_client().post(
        f"/conversations/{CONV}/messages",
        json={"content": "hello", "idempotencyKey": "store-outage"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "authorization_temporarily_unavailable"
    assert table.rows == before
    assert model.calls == []


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


def _counted(monkeypatch, module: Any, name: str, counts: dict[str, int], key: str) -> None:
    """Count each call of `module.name`, which still runs."""
    real = getattr(module, name)

    def counted(*args: Any, **kwargs: Any) -> Any:
        counts[key] = counts.get(key, 0) + 1
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, counted)


def test_stage_a_completed_replay_bypasses_consumed_upload_resolution(
    table, model, bucket, monkeypatch, caplog
) -> None:
    _parse_in_process(monkeypatch)
    _upload(table, bucket, "now-consumed", b"private notes", filename="notes.txt", media_type="text/plain")
    effects: dict[str, int] = {}
    _counted(monkeypatch, attachment_service, "prepare_message_attachments", effects, "prepare")
    payload = {
        "content": "exact bytes",
        "idempotencyKey": "replay-key",
        "attachmentIds": [{"uploadId": "now-consumed"}],
    }
    client = _question_client()
    first = client.post(f"/conversations/{CONV}/messages", json=payload)
    assert first.status_code == 200, first.text
    caplog.clear()

    replay = client.post(f"/conversations/{CONV}/messages", json=payload)

    assert replay.status_code == 200, replay.text
    assert replay.json()["studentMessage"]["id"] == first.json()["studentMessage"]["id"]
    assert replay.json()["assistantMessage"]["id"] == first.json()["assistantMessage"]["id"]
    # The upload the first send consumed is not looked up again.
    assert effects == {"prepare": 1}
    assert len(model.calls) == 1
    assert "exact bytes" not in caplog.text
    assert "So kürzt man." not in caplog.text


def test_stage_a_mismatch_fails_before_attachment_lookup(table, model, monkeypatch) -> None:
    client = _question_client()
    sent = client.post(
        f"/conversations/{CONV}/messages",
        json={"content": "original", "idempotencyKey": "same-key"},
    )
    assert sent.status_code == 200, sent.text
    effects = []
    monkeypatch.setattr(
        attachment_service,
        "prepare_message_attachments",
        lambda *_args, **_kwargs: effects.append("prepare"),
    )

    changed = client.post(
        f"/conversations/{CONV}/messages",
        json={
            "content": "changed",
            "idempotencyKey": "same-key",
            "attachmentIds": [{"uploadId": "upload-1"}],
        },
    )

    assert changed.status_code == 409, changed.text
    assert changed.json()["detail"]["code"] == "message_idempotency_conflict"
    assert effects == []


def test_new_foreign_attachment_has_zero_command_quota_or_ai_effect(table, model) -> None:
    table.seed(
        {
            **attachment_repo.attachment_key("foreign"),
            "attachment_id": "foreign",
            "owner_id": "student-2",
            "student_id": "student-2",
            "entity_type": "attachment",
            "schema_version": "attachment.v1",
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
    )
    before = dict(table.rows)

    response = _question_client().post(
        f"/conversations/{CONV}/messages",
        json={
            "content": "private",
            "idempotencyKey": "foreign-new",
            "attachmentIds": [{"attachmentId": "foreign"}],
        },
    )

    assert response.json()["detail"]["code"] == "upload_not_found"
    assert "canary" not in response.text
    assert table.rows == before
    assert model.calls == []


def test_synchronized_duplicate_commands_converge_to_one_complete_effect_set(
    table, model, bucket, monkeypatch
) -> None:
    _parse_in_process(monkeypatch)
    monkeypatch.setattr(dispatch, "override", dispatch.in_process)
    _upload(
        table, bucket, "fresh-upload-1", b"concurrent notes", filename="notes.txt", media_type="text/plain"
    )
    claim_barrier = threading.Barrier(2, timeout=5)
    claim = ask_question_store.claim_message_command_and_quota

    def claim_together(**kwargs: Any) -> Any:
        claim_barrier.wait()
        return claim(**kwargs)

    monkeypatch.setattr(ask_question_store, "claim_message_command_and_quota", claim_together)
    effects: dict[str, int] = {}
    _counted(monkeypatch, attachment_service, "bind_message_attachments", effects, "bind")
    _counted(
        monkeypatch, attachment_service, "extract_message_attachment_context", effects, "extract"
    )
    results = []
    failures = []

    def run() -> None:
        try:
            results.append(
                _submit(
                    "concurrent-key",
                    content="concurrent exact content",
                    attachmentIds=[{"uploadId": "fresh-upload-1"}],
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
    assert effects == {"bind": 1, "extract": 1}
    assert len(model.calls) == 1
    assert len(_messages(table, "student")) == len(_messages(table, "assistant")) == 1
    [quota] = [row for key, row in table.rows.items() if key[1].startswith("CHAT#")]
    assert quota["count"] == 1
    command_id = _command_row(table, "concurrent-key")["command_id"]
    expected_attachment_id = str(uuid5(UUID(command_id), "attachment:0"))
    assert tuple(attachment_repo.attachment_key(expected_attachment_id).values()) in table.rows


def test_committed_lost_response_same_fingerprint_retry_has_one_effect_set(
    table, model, bucket, monkeypatch
) -> None:
    _parse_in_process(monkeypatch)
    monkeypatch.setattr(dispatch, "override", dispatch.in_process)
    _upload(table, bucket, "fresh-upload-1", b"private text", filename="notes.txt", media_type="text/plain")
    effects: dict[str, int] = {}
    bind = attachment_service.bind_message_attachments

    def bind_then_lose_the_response(**kwargs: Any) -> Any:
        effects["bind"] = effects.get("bind", 0) + 1
        bound = bind(**kwargs)
        if effects["bind"] == 1:
            raise RuntimeError("committed-response-lost-provider-private-canary")
        return bound

    monkeypatch.setattr(attachment_service, "bind_message_attachments", bind_then_lose_the_response)
    _counted(
        monkeypatch, attachment_service, "extract_message_attachment_context", effects, "extract"
    )
    send = {
        "content": "exact committed content",
        "attachmentIds": [{"uploadId": "fresh-upload-1"}],
    }

    first = _submit("committed-lost-response", **send)
    replay = _submit("committed-lost-response", **send)

    assert first.model_dump() == replay.model_dump()
    assert effects == {"bind": 1, "extract": 1}
    assert len(model.calls) == 1
    assert len(_messages(table, "student")) == len(_messages(table, "assistant")) == 1
    [quota] = [row for key, row in table.rows.items() if key[1].startswith("CHAT#")]
    assert quota["count"] == 1
    attachments = [row for row in table.rows.values() if row.get("entity_type") == "attachment"]
    assert len(attachments) == 1
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

    assert result.disposition.value == "retryable"
    assert result.context == ""
    assert result.error_code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert body.close_count == 1
    assert "private-canary" not in str(result)


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

    parser_result = __import__(
        "stoa.services.document_parser_worker", fromlist=["ParserResult"]
    ).ParserResult
    monkeypatch.setattr(
        conversations.attachment_service,
        "parse_document_isolated",
        lambda *_args, **_kwargs: (
            parser_result(category="invalid_document")
            if case == "parser"
            else parser_result(text=data.decode())
        ),
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
    assert "provider-canary" not in str(result)


def _held_by_another_delivery(table, key: str) -> None:
    """The command is answered elsewhere right now: its lease is live."""
    row = dict(_command_row(table, key))
    row.update(
        status="ai_running",
        attempt=1,
        leaseOwner="another-delivery",
        expiresAt=int(datetime.now(timezone.utc).timestamp()) + 300,
    )
    table.seed(row)


def test_message_polling_is_bounded_to_twenty_fifty_millisecond_waits(
    table, model, monkeypatch
) -> None:
    _commit("bounded-key")
    _held_by_another_delivery(table, "bounded-key")
    sleeps = []
    monkeypatch.setattr(_answering.time, "sleep", lambda value: sleeps.append(value))

    response = _question_client().post(
        f"/conversations/{CONV}/messages",
        json={"content": QUESTION, "idempotencyKey": "bounded-key"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "message_in_progress"
    assert sleeps == [0.05] * 20
    assert model.calls == []


def _fails_from_call(monkeypatch, module: Any, name: str, call: int, failure: Exception) -> None:
    """`module.name` runs as it does until its `call`-th call, which raises `failure`."""
    real = getattr(module, name)
    calls = {"count": 0}

    def failing(*args: Any, **kwargs: Any) -> Any:
        calls["count"] += 1
        if calls["count"] >= call:
            raise failure
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, failing)


def test_regular_sse_stage_a_transport_has_identical_structured_retry(
    table, model, monkeypatch
) -> None:
    _fails_from_call(
        monkeypatch,
        ask_question_store,
        "get_message_command",
        1,
        RuntimeError("regular-sse-stage-a-provider-private-canary"),
    )
    payload = {
        "content": "request-private-canary",
        "idempotencyKey": "regular-sse-transport",
    }
    client = _question_client()

    regular = client.post(f"/conversations/{CONV}/messages", json=payload)
    streamed = client.post(f"/conversations/{CONV}/messages/stream", json=payload)

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
    assert _messages(table, "student") == []


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
    table, model, monkeypatch, stage: str
) -> None:
    monkeypatch.setattr(dispatch, "override", dispatch.in_process)
    failure = RuntimeError(f"{stage}-provider-table-private-canary")

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise failure

    def held(**_kwargs: Any) -> Any:
        return ask_question_store.MessageCommandResult(
            ask_question_store.MessageCommandDisposition.LEASE_HELD, attempt=1
        )

    if stage == "command_claim_transport":
        monkeypatch.setattr(ask_question_store, "claim_message_command_and_quota", fail)
    elif stage == "attachment_transaction_transport":
        monkeypatch.setattr(attachment_service, "bind_message_attachments", fail)
    elif stage == "race_reread_transport":
        # Another request holds the claim; reading what it stored fails. The
        # first read is the request's own, before anything was claimed.
        monkeypatch.setattr(ask_question_store, "claim_message_command_and_quota", held)
        _fails_from_call(monkeypatch, ask_question_store, "get_message_command", 2, failure)
    elif stage == "ai_lease_transport":
        monkeypatch.setattr(ask_question_store, "claim_message_ai_lease", fail)
    elif stage == "ai_lease_reread_transport":
        monkeypatch.setattr(ask_question_store, "claim_message_ai_lease", held)
        # Read first by the request, then by the command claim; the third is the wait's.
        _fails_from_call(monkeypatch, ask_question_store, "get_message_command", 3, failure)
    elif stage == "terminal_transport":
        # The lease is refused at the last attempt, and ending the command fails.
        monkeypatch.setattr(
            ask_question_store,
            "claim_message_ai_lease",
            lambda **_kwargs: ask_question_store.MessageCommandResult(
                ask_question_store.MessageCommandDisposition.LEASE_HELD, attempt=3
            ),
        )
        monkeypatch.setattr(ask_question_store, "mark_message_command_terminal", fail)
    elif stage == "completion_transport":
        monkeypatch.setattr(ask_question_store, "complete_message_command", fail)
    else:
        # The completing transaction's response is lost, and reading back
        # whether it landed fails too.
        transact = attachment_repo.transact

        def lose_the_completion(operations: Any, *, table: Any = None) -> Any:
            if any(
                getattr(operation, "kind", None)
                is attachment_repo.TransactionOperationKind.ASSISTANT_MESSAGE_PUT
                for operation in operations
            ):
                raise attachment_repo.AttachmentTransactionError(
                    attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY
                )
            return transact(operations, table=table)

        monkeypatch.setattr(attachment_repo, "transact", lose_the_completion)
        # After the request's, the claim's and the lease's reads: the read-back.
        _fails_from_call(monkeypatch, ask_question_store, "get_message_command", 4, failure)

    with pytest.raises(AttachmentDecisionError) as captured:
        _submit("transport-key", content="transport-private-canary")

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert "private-canary" not in str(captured.value)


def test_replay_poll_transport_is_structured_retry(table, model, monkeypatch) -> None:
    _commit("transport-key")
    _held_by_another_delivery(table, "transport-key")
    monkeypatch.setattr(_answering.time, "sleep", lambda *_: None)
    # The request's own read finds the lease held; the poll after it fails.
    _fails_from_call(
        monkeypatch,
        ask_question_store,
        "get_message_command",
        2,
        RuntimeError("replay-poll-provider-table-private-canary"),
    )

    with pytest.raises(AttachmentDecisionError) as captured:
        _submit("transport-key")

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert "private-canary" not in str(captured.value)


def test_resume_stored_message_transport_is_structured_retry(table, model, monkeypatch) -> None:
    _commit("transport-key", content="transport-private-canary")

    def outage(**_kwargs: Any) -> Any:
        raise RuntimeError("stored-message-provider-table-private-canary")

    # Resuming reads the history the command was anchored to, and that read fails.
    monkeypatch.setattr(table, "query", outage)

    with pytest.raises(AttachmentDecisionError) as captured:
        _submit("transport-key", content="transport-private-canary")

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert "private-canary" not in str(captured.value)
    assert model.calls == []


def test_regular_and_stream_message_use_identical_safe_attachment_summary(
    table, model, bucket, monkeypatch
) -> None:
    _parse_in_process(monkeypatch)
    _upload(table, bucket, "upload-notes", b"my notes", filename="notes.txt", media_type="text/plain")
    payload = {
        "content": "use notes",
        "idempotencyKey": "attachment-parity",
        "attachmentIds": [{"uploadId": "upload-notes"}],
    }
    client = _question_client()

    regular = client.post(f"/conversations/{CONV}/messages", json=payload)
    streamed = client.post(f"/conversations/{CONV}/messages/stream", json=payload)

    assert regular.status_code == streamed.status_code == 200, regular.text
    [safe] = regular.json()["studentMessage"]["attachments"]
    assert safe["filename"] == "notes.txt"
    [student] = [data for name, data in _sse_events(streamed) if name == "student_message"]
    assert student["attachments"] == [safe]
    for private in ("object_key", "immutable", "etag", "sha256", "objects/private"):
        assert private not in regular.text + streamed.text


def test_conversation_history_batch_projects_only_safe_attachment_summaries(monkeypatch) -> None:
    summary = _attachment_summary()
    monkeypatch.setattr(
        conversations,
        "read_conversation",
        lambda *_: {
            "conversation_id": "conv-1",
            "student_id": "student-1",
            "subject": "math",
            "grade": "Sek1",
            "title": "Mathematics – Sek1",
            "updated_at": "2026-07-16T00:00:00Z",
        },
    )
    monkeypatch.setattr(
        conversations,
        "read_messages",
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
        _answering,
        "read_messages",
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
    table, model, monkeypatch
) -> None:
    def cancelled(**_kwargs: Any) -> Any:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)

    monkeypatch.setattr(ask_question_store, "claim_message_command_and_quota", cancelled)
    effects: dict[str, int] = {}
    _counted(
        monkeypatch, attachment_service, "extract_message_attachment_context", effects, "extract"
    )

    response = _question_client().post(
        f"/conversations/{CONV}/messages",
        json={"content": "private-message-canary", "idempotencyKey": "dependency-cancel"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "upload_service_unavailable"
    assert response.json()["detail"]["message"] == (
        "Uploads are temporarily unavailable. Try again later."
    )
    assert effects == {}
    assert model.calls == []
    assert _messages(table, "student") == []
    assert "private-message-canary" not in response.text


def test_a_conversation_is_named_after_the_question_that_started_it():
    assert conversations._title_from_question("  Wie loese ich 2x + 3 = 11?  ") == (
        "Wie loese ich 2x + 3 = 11?"
    )
    assert conversations._title_from_question("Was ist\neine Primzahl?") == (
        "Was ist eine Primzahl?"
    )
    long_title = conversations._title_from_question("word " * 40)
    assert len(long_title) <= 49 and long_title.endswith("…")


def test_only_the_placeholder_title_is_replaced(monkeypatch):
    """A student who renamed a conversation keeps that name."""
    updates = []

    monkeypatch.setattr(
        conversations.attachment_repo,
        "retitle_conversation",
        lambda conversation_id, **kwargs: updates.append(kwargs) or True,
    )

    conversations._adopt_question_as_title(
        "conv-1",
        {"title": "Mathematics – 9", "subject": "Mathematics", "grade": "9"},
        "Wie loese ich 2x + 3 = 11?",
    )
    assert updates[0]["title"] == "Wie loese ich 2x + 3 = 11?"

    conversations._adopt_question_as_title(
        "conv-1",
        {"title": "My fractions notes", "subject": "Mathematics", "grade": "9"},
        "Another question",
    )
    assert len(updates) == 1


# ── an untitled conversation is named by its first question (#124) ─────────


def test_a_conversation_opened_without_a_question_is_left_untitled():
    """No subject id and no grade spelling anywhere in the stored title.

    `Mathematik – Grade 6` filled the sidebar with the same row repeated: a
    stored id and a grade spelling, neither of them a name, neither of them in
    the language the student reads. The client has `ask.list.untitled` in all
    four locales, so the phrase is its job.
    """
    titles = {
        conversations._default_conversation_title(subject, grade)
        for subject, grade in (
            ("math", "Grade 6"),
            ("physics", "Sek1"),
            ("german", ""),
            ("english", "14"),
        )
    }

    assert titles == {""}


def test_the_first_question_names_an_untitled_conversation(monkeypatch):
    """The behaviour that must survive: empty now, the question afterwards."""
    updates = []
    monkeypatch.setattr(
        conversations.attachment_repo,
        "retitle_conversation",
        lambda conversation_id, **kwargs: updates.append(kwargs) or True,
    )

    conversations._adopt_question_as_title(
        "conv-1",
        {"title": "", "subject": "math", "grade": "Grade 6"},
        "Wie loese ich 2x + 3 = 11?",
    )

    assert updates == [
        {
            "title": "Wie loese ich 2x + 3 = 11?",
            "expected_title": "",
            "now_iso": updates[0]["now_iso"],
        }
    ]


def test_every_placeholder_a_conversation_has_ever_carried_is_still_claimable(monkeypatch):
    """The whole set of placeholder spellings, not whichever one is current.

    Rows written before #124 hold `subject – grade`; rows written after hold
    nothing. Both are the platform's own placeholder and both must give way to
    the student's question.
    """
    updates = []
    monkeypatch.setattr(
        conversations.attachment_repo,
        "retitle_conversation",
        lambda conversation_id, **kwargs: updates.append(kwargs) or True,
    )
    placeholders = conversations._placeholder_conversation_titles("math", "Grade 6")

    for placeholder in placeholders:
        conversations._adopt_question_as_title(
            "conv-1",
            {"title": placeholder, "subject": "math", "grade": "Grade 6"},
            "Wie loese ich 2x + 3 = 11?",
        )

    assert {update["expected_title"] for update in updates} == set(placeholders)
    assert len(updates) == len(placeholders)


def test_a_name_the_student_chose_is_never_taken_by_a_question(monkeypatch):
    """The negative control for the set above.

    Without it an `_adopt_question_as_title` that retitles unconditionally
    passes every assertion in this section.
    """
    updates = []
    monkeypatch.setattr(
        conversations.attachment_repo,
        "retitle_conversation",
        lambda conversation_id, **kwargs: updates.append(kwargs) or True,
    )

    for chosen in ("Meine Bruch-Notizen", " ", "math", "math – Grade 7"):
        conversations._adopt_question_as_title(
            "conv-1",
            {"title": chosen, "subject": "math", "grade": "Grade 6"},
            "Wie loese ich 2x + 3 = 11?",
        )

    assert updates == []


def test_an_untitled_conversation_can_still_be_read_back():
    """The `conversation_grade` defect, not repeated for the title.

    Creation accepted a blank grade and every later read refused it, so the
    conversation existed in a state it could not be read out of. An empty
    title is written on purpose now, so the read has to accept it.
    """
    assert conversations._conversation_title({"title": ""}) == ""
    assert conversations._conversation_title({}) == ""
    assert conversations._conversation_title({"title": "Meine Frage"}) == "Meine Frage"


def _published_steps(monkeypatch) -> list[list[str]]:
    """Every step list written to the progress record, in order; each is still written."""
    published: list[list[str]] = []
    record = ask_question_store.record_generation_progress

    def recorded(conv_id: str, **kwargs: Any) -> Any:
        published.append(list(kwargs["steps"]))
        return record(conv_id, **kwargs)

    monkeypatch.setattr(ask_question_store, "record_generation_progress", recorded)
    return published


def test_only_whole_steps_are_published(table, model, monkeypatch):
    """A student is shown a step once it is whole, never a fragment of JSON."""
    model.answer = {"steps": ["Schritt 1", "Schritt 2"], "answer": "x = 4", "hints": []}
    published = _published_steps(monkeypatch)
    monkeypatch.setattr(dispatch, "override", dispatch.in_process)

    _submit("steps-key")

    assert published == [["Schritt 1"], ["Schritt 1", "Schritt 2"]]
    progress = ask_question.progress(CONV, "steps-key", "student-1")
    assert progress.steps == ["Schritt 1", "Schritt 2"]


def test_a_step_out_of_order_is_ignored(table, model, monkeypatch):
    published = _published_steps(monkeypatch)
    answer = _answering.ask_answer.answer

    def out_of_order_first(asked: Any, asker: Any, call: Any, **kwargs: Any) -> Any:
        call.on_step(3, "out of order")
        return answer(asked, asker, call, **kwargs)

    monkeypatch.setattr(_answering.ask_answer, "answer", out_of_order_first)
    monkeypatch.setattr(dispatch, "override", dispatch.in_process)

    _submit("steps-key")

    assert ["out of order"] not in published
    assert all("out of order" not in steps for steps in published)
    assert ask_question.progress(CONV, "steps-key", "student-1").steps == [
        "Zähler und Nenner teilen",
        "Durch den ggT",
    ]


def test_progress_is_only_readable_by_the_student_who_asked():

    class _Table:
        def get_item(self, **kwargs):
            del kwargs
            return {"Item": {"owner_id": "student-1", "steps": ["Schritt 1"]}}

    steps, _updated_at = ask_question_store.read_generation_progress(
        "conv-1", owner_id="student-1", table=_Table()
    )
    assert steps == ["Schritt 1"]
    hidden, _ = ask_question_store.read_generation_progress(
        "conv-1", owner_id="another-student", table=_Table()
    )
    assert hidden == []


def test_streaming_reports_steps_and_still_returns_the_whole_answer(monkeypatch):
    """Streaming must not change what the caller finally receives."""
    import json as _json

    from stoa.services import ask_answer

    answer = {
        "steps": ["Schritt 1: erst dies", "Schritt 2: dann das"],
        "answer": "x = 4",
        "hints": [],
    }
    text = _json.dumps(answer, ensure_ascii=False)

    def _events():
        yield {"chunk": {"bytes": _json.dumps({"type": "message_start", "message": {"id": "msg-1", "model": "anthropic.claude-sonnet-4-6", "usage": {"input_tokens": 11}}}).encode()}}
        for piece in (text[i : i + 7] for i in range(0, len(text), 7)):
            yield {"chunk": {"bytes": _json.dumps({"type": "content_block_delta", "delta": {"text": piece}}).encode()}}
        yield {"chunk": {"bytes": _json.dumps({"type": "message_delta", "usage": {"output_tokens": 22}, "delta": {"stop_reason": "end_turn"}}).encode()}}

    class _Client:
        def invoke_model_with_response_stream(self, **kwargs):
            del kwargs
            return {"body": _events(), "ResponseMetadata": {"RequestId": "req-1"}}

    seen = []
    result = ask_answer.answer(
        ask_answer.Asked(content="Wie loese ich 2x = 8?"),
        ask_answer.Asker(student_id="student-1", subject="math", grade="9", locale="de"),
        ask_answer.ModelCall(
            model=_Client(), on_step=lambda index, step: seen.append((index, step))
        ),
        read_star_map=lambda *_a, **_k: None,
    )

    assert [step for _index, step in seen] == answer["steps"]
    assert result.structured.answer == "x = 4"


def test_every_message_route_adopts_the_question_as_title(table, model):
    """Both routes retitle, not just the one that happened to have the call.

    The adoption itself was covered, while the streaming route — the only one
    the client calls — never invoked it, so every conversation the client
    opened stayed listed under its subject-and-grade placeholder.
    """
    client = _question_client()
    for route, question in (
        ("messages", "Wie loese ich 2x + 3 = 11?"),
        ("messages/stream", "Was ist eine Primzahl?"),
    ):
        conversation = table.rows[(f"CONV#{CONV}", "CONV")]
        table.seed({**conversation, "title": ""})

        response = client.post(
            f"/conversations/{CONV}/{route}",
            json={"content": question, "idempotencyKey": f"title-{len(route)}"},
        )

        assert response.status_code == 200, response.text
        assert table.rows[(f"CONV#{CONV}", "CONV")]["title"] == question, route


def _index_filter_holds(condition, row) -> bool:
    """Evaluate one boto3 `Attr` filter the way the index would."""
    if condition is None:
        return True
    built = condition.get_expression()
    assert built["operator"] == "=", built["operator"]
    name, expected = built["values"]
    return row.get(name.name) == expected


class _PagedIndexTable:
    """GSI-StudentId double that cuts the page before the filter, as DynamoDB does.

    The index carries every row holding the student id, so a page can be spent
    entirely on messages and come back with no conversations at all. A double that
    filters before cutting hides exactly that, so the cut happens here first.
    """

    def __init__(self, rows, page_rows: int = 50):
        self.rows = rows
        self.page_rows = page_rows
        self.query_calls = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        assert kwargs["IndexName"] == "GSI-StudentId"
        assert kwargs["ScanIndexForward"] is False
        student_id = kwargs["KeyConditionExpression"].get_expression()["values"][1]
        partition = [row for row in self.rows if row["student_id"] == student_id]
        start = 0
        cursor = kwargs.get("ExclusiveStartKey")
        if cursor is not None:
            start = 1 + next(
                index
                for index, row in enumerate(partition)
                if (row["PK"], row["SK"]) == (cursor["PK"], cursor["SK"])
            )
        evaluated = partition[start : start + self.page_rows]
        response = {
            "Items": [
                dict(row)
                for row in evaluated
                if _index_filter_holds(kwargs.get("FilterExpression"), row)
            ]
        }
        if start + len(evaluated) < len(partition):
            last = partition[start + len(evaluated) - 1]
            response["LastEvaluatedKey"] = {
                "PK": last["PK"],
                "SK": last["SK"],
                "student_id": last["student_id"],
                "created_at": last["created_at"],
            }
        return response


def _student_index_rows(*, messages: int, conversations_count: int, student_id="student-1"):
    """Newest first, as the descending index returns them: messages, then history."""
    rows = [
        {
            "PK": f"CONV#noise-{index}",
            "SK": f"MSG#msg-{index}",
            "student_id": student_id,
            "entity_type": "conversation_message",
            "created_at": f"2026-07-20T00:{index // 60:02d}:{index % 60:02d}Z",
        }
        for index in range(messages)
    ]
    rows += [
        {
            "PK": f"CONV#history-{index}",
            "SK": "CONV",
            "conversation_id": f"history-{index}",
            "student_id": student_id,
            "entity_type": "conversation",
            "subject": "math",
            "grade": "Sek1",
            "title": f"History {index}",
            "created_at": f"2026-07-15T00:00:{index:02d}Z",
            "updated_at": f"2026-07-15T00:00:{index:02d}Z",
        }
        for index in range(conversations_count)
    ]
    return rows


def test_conversation_list_reaches_matching_row_after_filtered_gsi_page(monkeypatch):
    """Pages spent on messages must not be reported as an empty history."""
    table = _PagedIndexTable(_student_index_rows(messages=120, conversations_count=5))
    monkeypatch.setattr(conversations, "get_table", lambda: table)
    monkeypatch.setattr(_answering, "get_table", lambda: table)
    monkeypatch.setattr(_transcript, "get_table", lambda: table)

    response = _client(conversations.router).get("/conversations")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [
        "history-0",
        "history-1",
        "history-2",
        "history-3",
        "history-4",
    ]
    assert body["truncated"] is False
    assert len(table.query_calls) == 3
    assert table.query_calls[0].get("ExclusiveStartKey") is None


def test_conversation_list_reads_one_page_at_normal_volume_without_repeats(monkeypatch):
    table = _PagedIndexTable(_student_index_rows(messages=20, conversations_count=5))
    monkeypatch.setattr(conversations, "get_table", lambda: table)
    monkeypatch.setattr(_answering, "get_table", lambda: table)
    monkeypatch.setattr(_transcript, "get_table", lambda: table)

    response = _client(conversations.router).get("/conversations")

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == ["history-0", "history-1", "history-2", "history-3", "history-4"]
    assert len(ids) == len(set(ids))
    assert response.json()["truncated"] is False
    assert len(table.query_calls) == 1


def test_conversation_list_reports_an_exhausted_page_budget_as_truncated(monkeypatch):
    """A heavy history is bounded, and the caller is told it was cut short."""
    table = _PagedIndexTable(_student_index_rows(messages=400, conversations_count=2))
    monkeypatch.setattr(conversations, "get_table", lambda: table)
    monkeypatch.setattr(_answering, "get_table", lambda: table)
    monkeypatch.setattr(_transcript, "get_table", lambda: table)

    page = conversations._list_conversations("student-1", page_budget=2)

    assert page.items == []
    assert page.truncated is True
    assert len(table.query_calls) == 2


def test_conversation_list_stops_at_the_result_limit_and_says_so(monkeypatch):
    table = _PagedIndexTable(_student_index_rows(messages=0, conversations_count=250))
    monkeypatch.setattr(conversations, "get_table", lambda: table)
    monkeypatch.setattr(_answering, "get_table", lambda: table)
    monkeypatch.setattr(_transcript, "get_table", lambda: table)

    page = conversations._list_conversations("student-1")

    assert len(page.items) == 200
    assert page.truncated is True
    assert len(table.query_calls) == 4


def test_a_conversation_opened_without_a_year_group_can_be_read_back():
    """Creation accepted an empty grade and every read refused it.

    A grade is asked for on the learning profile, not when an account is opened,
    so a student an administrator opened has none and the console sends "". The
    conversation was created and then existed in a state it could never be read
    out of: the assistant's reply came back `upload_service_unavailable`, on a
    request carrying no upload. Measured on production.
    """
    conv = {
        "id": "conv-1",
        "title": "math",
        "subject": "math",
        "grade": "",
        "updated_at": "2026-09-23T00:00:00+00:00",
    }

    assert _transcript.conversation_grade(conv) == ""


def test_a_missing_year_group_reads_the_same_as_an_empty_one():
    assert _transcript.conversation_grade({"subject": "math"}) == ""


def test_a_year_group_of_the_wrong_type_is_still_refused():
    """Negative control: "nobody said" is not "the row is damaged"."""
    with pytest.raises(conversations.AttachmentDecisionError):
        _transcript.conversation_grade({"grade": 9})


def test_the_other_conversation_fields_still_refuse_an_empty_value():
    """Second negative control: only the grade was widened.

    A conversation with no subject or no title is a damaged row, and widening
    the grade must not have widened those with it.
    """
    for field in ("title", "subject", "updated_at"):
        with pytest.raises(conversations.AttachmentDecisionError):
            _transcript.required_conversation_text({field: ""}, field)


def test_escalating_a_conversation_writes_the_record_the_teacher_side_reads(monkeypatch):
    """A student asking for a teacher has to reach a teacher.

    Everything on the teacher side - the list, dispatch, the reply, the SLA
    figures - reads the conversation's help request (#189). Escalation once
    wrote a marker on the conversation and nothing else, so the request was
    accepted and `GET /teachers/queue` stayed empty. Measured in production on
    2026-09-24.
    """
    from stoa.services import help_requests

    table = _escalation_table()

    response = _escalate(monkeypatch, table)

    assert response.status_code == 200
    item = table.rows[("CONV#conv-1", "HELP")]
    assert item["entity_type"] == "help_request"
    assert item["escalation_request_id"] == "conv-1"
    assert item["escalation_status"] == "pending"
    assert item["student_id"] == "student-1"
    assert item["subject"] == "physics"
    assert item["conversation_id"] == "conv-1"
    assert item["escalation_message"] == "please help"
    # In GSI-StudentId beside the student's conversations.
    assert item["created_at"] == item["escalated_at"]
    # A version every later write is conditioned on.
    assert int(item["version"]) >= 1
    # What a reader keyed by a question id is given.
    assert help_requests.question_view(dict(item))["status"] == "escalated"


def test_escalating_the_same_conversation_twice_cannot_open_a_second_case(monkeypatch):
    """Negative control: the record is created, never overwritten."""
    from stoa.db.repositories import account_deletion_repo

    sent: list[list[dict]] = []
    original = account_deletion_repo.transact

    def recording(operations, *, table=None):
        operations = list(operations)
        sent.append(operations)
        return original(operations, table=table)

    monkeypatch.setattr(account_deletion_repo, "transact", recording)
    table = _escalation_table()

    assert _escalate(monkeypatch, table).status_code == 200

    puts = [
        operation["Put"]
        for operations in sent
        for operation in operations
        if "Put" in operation and operation["Put"]["Item"].get("SK") == "HELP"
    ]
    assert len(puts) == 1
    assert puts[0]["ConditionExpression"] == (
        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
    )


def test_the_help_request_is_written_in_the_same_transaction_as_the_case():
    """It has to be atomic with the case, or the two can disagree.

    A separate write would let a student be charged a case for a request no
    teacher can see, or leave a request behind for a case that was refused.
    """
    import ast
    from pathlib import Path

    from stoa.services import help_requests

    source = Path(help_requests.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    persist = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "persist_case"
    )
    calls = [
        node
        for node in ast.walk(persist)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "transact"
    ]
    assert len(calls) == 1
    (sent,) = calls[0].args
    assert isinstance(sent, ast.List)
    starred = {
        element.value.id
        for element in sent.elts
        if isinstance(element, ast.Starred) and isinstance(element.value, ast.Name)
    }
    # The request's own rows and the allowance's, in the one list.
    assert starred == {"rows", "allowance_operations"}


# --- The escalation actually executed, not the operations we meant to send ----
#
# Tests about the queue row once asserted on a dictionary. The shared double
# used to fall into a degraded branch that wrote the conversation header and the
# system message and **dropped every other operation in the transaction** - the
# allowance fences, the admission receipt, the counter and the queue row. Those
# assertions could not have failed no matter what the code did, because none of
# it ran.
#
# These run it: one real transaction against the shared table double, then the
# teacher-side read of help requests against the same table.


def _escalation_table():
    from fakes.dynamodb import FakeTable

    table = FakeTable()
    table.rows[("USER#student-1", "ACCOUNT_FENCE")] = _as_stored(
        {
            "PK": "USER#student-1",
            "SK": "ACCOUNT_FENCE",
            "status": "active",
            "generation": 1,
        }
    )
    table.rows[("USER#student-1", "PROFILE")] = _as_stored(
        {
            "PK": "USER#student-1",
            "SK": "PROFILE",
            "user_id": "student-1",
            "role": "student",
            "account_status": "active",
            "version": 3,
        }
    )
    table.rows[("CONV#conv-1", "CONV")] = _as_stored(
        {
            "PK": "CONV#conv-1",
            "SK": "CONV",
            "entity_type": "conversation",
            "conversation_id": "conv-1",
            "student_id": "student-1",
            "owner_id": "student-1",
            "account_fence_generation": 1,
            "subject": "physics",
            "grade": "Sek1",
        }
    )
    return table


def _conversation(table, conversation_id: str) -> None:
    table.rows[(f"CONV#{conversation_id}", "CONV")] = _as_stored(
        {
            "PK": f"CONV#{conversation_id}",
            "SK": "CONV",
            "entity_type": "conversation",
            "conversation_id": conversation_id,
            "student_id": "student-1",
            "owner_id": "student-1",
            "account_fence_generation": 1,
            "subject": "physics",
            "grade": "Sek1",
        }
    )


def _escalate(monkeypatch, table, conversation_id: str = "conv-1"):
    """Run the real route against the real admission service and one real table."""
    from stoa.routers import teachers
    from stoa.services import teacher_support_allowance_service as allowance_service

    from stoa.services import teacher_dispatch_service

    for module in (
        conversations,
        allowance_service,
        attachment_repo,
        teachers,
        teacher_dispatch_service,
    ):
        monkeypatch.setattr(module, "get_table", lambda table=table: table)
    monkeypatch.setattr(
        allowance_service.paid_entitlement_service,
        "get_active_beneficiary_grant",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        allowance_service.user_repo,
        "get_user",
        lambda user_id, **_kwargs: dict(table.rows.get((f"USER#{user_id}", "PROFILE")) or {}),
    )
    monkeypatch.setattr(
        conversations,
        "read_conversation",
        lambda conv_id: dict(table.rows[(f"CONV#{conv_id}", "CONV")]),
    )
    monkeypatch.setattr(
        conversations.usage_ledger_service,
        "record_usage_event",
        lambda **_kwargs: {"idempotency_status": "created"},
    )
    return _client(conversations.teacher_help_router, "/teacher-help").post(
        "/teacher-help/request",
        json={"conversationId": conversation_id, "message": "please help"},
    )


def test_the_escalation_lands_in_the_queue_the_teacher_actually_reads(monkeypatch):
    from stoa.services import help_requests

    table = _escalation_table()

    response = _escalate(monkeypatch, table)

    assert response.status_code == 200
    request_id = response.json()["requestId"]
    assert request_id == "conv-1"
    # One record, no queue row beside it (#189).
    assert not [key for key in table.rows if key[0].startswith("QUESTION#")]
    assert "escalated" not in table.rows[("CONV#conv-1", "CONV")]

    # The teacher side, reading the same table through its own read.
    listed = [help_requests.question_view(record) for record in help_requests.list_all(table=table)]
    assert [item["question_id"] for item in listed] == [request_id]
    assert listed[0]["subject"] == "physics"
    assert listed[0]["status"] == "escalated"


def test_the_case_the_student_spent_is_on_the_table_too(monkeypatch):
    """The receipt and the counter, not just the queue row.

    They travel in the same transaction, so a branch that dropped the queue row
    dropped these as well - and a student who was charged for help nobody can
    see is the worse half of that failure.
    """
    table = _escalation_table()

    assert _escalate(monkeypatch, table).status_code == 200

    receipts = [row for key, row in table.rows.items() if key[0].startswith("TEACHER_SUPPORT_CASE#")]
    counters = [row for key, row in table.rows.items() if key[1].startswith("WEEK#")]
    assert len(receipts) == 1
    assert len(counters) == 1
    assert int(counters[0]["admitted_cases"]) == 1
    assert int(counters[0]["limit"]) == 7


def test_an_eighth_escalation_in_one_week_is_refused_end_to_end(monkeypatch):
    """The figure is enforced by the transaction, not by the caller counting."""
    table = _escalation_table()

    for index in range(7):
        _conversation(table, f"conv-{index}")
        assert _escalate(monkeypatch, table, f"conv-{index}").status_code == 200, index

    _conversation(table, "conv-8")
    eighth = _escalate(monkeypatch, table, "conv-8")

    assert eighth.status_code == 429
    counters = [row for key, row in table.rows.items() if key[1].startswith("WEEK#")]
    assert int(counters[0]["admitted_cases"]) == 7
    # The refused one left nothing behind.
    assert ("CONV#conv-8", "HELP") not in table.rows


def test_asking_twice_about_one_conversation_spends_one_case(monkeypatch):
    """The case is the conversation, so a repeat is the same case, not a new one.

    Without this the retry a student makes when nothing seems to happen would
    quietly cost them another of the week's seven.
    """
    table = _escalation_table()

    first = _escalate(monkeypatch, table)
    second = _escalate(monkeypatch, table)

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json()["requestId"] == second.json()["requestId"]
    counters = [row for key, row in table.rows.items() if key[1].startswith("WEEK#")]
    assert int(counters[0]["admitted_cases"]) == 1


def _with_a_teacher_on_duty(table) -> None:
    table.rows[("USER#teacher-1", "PROFILE")] = _as_stored(
        {
            "PK": "USER#teacher-1",
            "SK": "PROFILE",
            "user_id": "teacher-1",
            "role": "teacher",
            "account_status": "active",
            "version": 4,
            "dispatch_availability": "available",
            "dispatch_subjects": ["physics"],
        }
    )
    table.rows[("USER#teacher-1", "ACCOUNT_FENCE")] = _as_stored(
        {"PK": "USER#teacher-1", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 2}
    )


def test_escalating_with_a_teacher_on_duty_offers_the_request_to_them(monkeypatch):
    """One escalation, one record, one offer.

    The record is what the student and the teacher both read. The offer is
    written to it under its version, so a second teacher cannot be sent to the
    same case and the SLA dashboard does not count it as never dispatched.
    """
    table = _escalation_table()
    _with_a_teacher_on_duty(table)

    request_id = _escalate(monkeypatch, table).json()["requestId"]

    record = table.rows[(f"CONV#{request_id}", "HELP")]
    assert record["dispatch_status"] == "dispatched"
    assert record["dispatched_teacher_id"] == "teacher-1"
    # Still waiting, and the version moved: the offer went through the same
    # compare-and-set every other write of the request goes through.
    assert record["escalation_status"] == "pending"
    assert int(record["version"]) == 2
    # The conversation row carries none of it.
    assert "dispatch_status" not in table.rows[("CONV#conv-1", "CONV")]


_STUDENT_HELP_STATES = {
    "pending": {},
    "waiting_no_teacher": {"dispatch_status": "no_candidate"},
    "assigned": {"teacher_id": "teacher-1"},
    "in_progress": {"escalation_status": "in_progress", "teacher_id": "teacher-1"},
    "resolved": {"escalation_status": "resolved", "teacher_id": "teacher-1"},
    "withdrawn": {"escalation_status": "withdrawn"},
    "expired": {"escalation_status": "expired"},
}


@pytest.mark.parametrize("state, fields", list(_STUDENT_HELP_STATES.items()))
def test_every_help_state_a_student_can_be_in_is_one_the_contract_names(
    monkeypatch, state, fields
):
    # #65: the status card reads this field only, so it is a closed set.
    _with_help_request(monkeypatch, **fields)
    monkeypatch.setattr(conversations.user_repo, "get_user", lambda _id, **_kwargs: {"name": "T"})

    response = _client(conversations.teacher_help_router, "/teacher-help").get(
        "/teacher-help/conversations/conv-1/request"
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == state


def test_the_help_status_contract_names_exactly_the_states_a_student_meets():
    from stoa.main import app

    schema = app.openapi()["components"]["schemas"]["TeacherHelpResponse"]["properties"]["status"]
    assert set(schema["enum"]) == set(_STUDENT_HELP_STATES)


# ── the line that opens a help request (#124) ─────────────────────────────


def test_a_help_request_opens_in_the_student_s_own_language():
    """All four languages, compared as a set against the catalog.

    What the teacher read was `Teacher help requested. Bitte hilf mir beim
    Dividieren.` - one hardcoded English sentence welded onto the front of the
    student's German. The student's words are untouched; only the line in
    front of them follows the language.
    """
    asked = "Bitte hilf mir beim Dividieren."

    opened = {
        locale: conversations._teacher_help_system_message(asked, locale)
        for locale in locale_service.SUPPORTED_LOCALES
    }

    assert opened == {
        locale: (
            message_catalog.TEXT["teacher_help.system_message.prefix"][locale] + " " + asked
        )
        for locale in locale_service.SUPPORTED_LOCALES
    }
    # Four distinct openings: a hardcoded prefix collapses them to one.
    assert len(set(opened.values())) == len(locale_service.SUPPORTED_LOCALES)
    # And the student's own words survive every one of them, unaltered.
    assert all(line.endswith(asked) for line in opened.values())


def test_a_help_request_with_nothing_written_is_the_line_alone():
    """No trailing space, no empty second half: the negative control."""
    for empty in (None, "", "   "):
        assert conversations._teacher_help_system_message(empty, "de") == (
            message_catalog.TEXT["teacher_help.system_message.prefix"]["de"]
        )


def test_the_opening_line_is_never_the_untranslated_fallback_in_every_language():
    """A locale the catalog does not carry falls back; the four it does do not."""
    rendered = {
        conversations._teacher_help_system_message("x", locale)
        for locale in locale_service.SUPPORTED_LOCALES
    }

    assert len(rendered) == len(locale_service.SUPPORTED_LOCALES)
