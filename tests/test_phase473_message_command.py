"""Lower-boundary contract for the durable conversation message command.

These tests intentionally drive repository clients and transaction responses.  They
do not replace the command executor or completion repository method with a mock.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from fakes.ask_question import (
    CONV,
    STUDENT,
    AtomicAllowanceTable,
    _command_key,
    _commit,
    _patch_allowance_table,
    _submit,
)
from fakes.ask_question import _no_memory_personalisation  # noqa: F401 - the fixture
from fakes.ask_question import _client as _question_client
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from stoa.db.repositories import attachment_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import conversations
from stoa.services.ask_question import _answering
from stoa.security.attachment_errors import AttachmentDecisionError
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services.ask_question.models import SendMessageRequest, message_request_fingerprint
from stoa.services.ask_question import _store as ask_question_store


def _actor() -> Actor:
    return Actor(
        "student-1",
        "https://identity.test",
        "student-1-subject",
        CanonicalRole.STUDENT,
        AccountStatus.ACTIVE,
        "student",
        (),
    )


def _command(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "entity_type": "message_command",
        "schema_version": "message-command.v2",
        "command_id": "command-1",
        "conversation_id": "conv-1",
        "owner_id": "student-1",
        "idempotency_key": "message-key",
        "fingerprint": "f" * 64,
        "status": "claimed",
        "student_message_id": "student-message-1",
        "assistant_message_id": "assistant-message-1",
        "deterministic_attachment_ids": ["attachment-1"],
        "requested_attachments": [
            {"kind": "upload", "id": "upload-1", "attachment_id": "attachment-1"}
        ],
        "quota_period": "2026-07-17",
        "usage_action": "chat_message",
        "usage_resource_id": "student-message-1",
        "usage_idempotency_key": "chat_message:student-message-1",
        "usage_event_id": (
            "student-1:chat_message:2026-07-17:chat_message:student-message-1"
        ),
        "history_anchor_message_id": "student-message-1",
        "history_anchor_created_at": "2026-07-17T23:59:59+00:00",
        "attempt": 0,
        "created_at": "2026-07-17T23:59:59+00:00",
        "expires_at": 1784505599,
    }
    value.update(overrides)
    return value


def _transaction_cancel(codes: list[str]) -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": "TransactionCanceledException",
                "Message": "provider-table-private-canary",
            },
            "CancellationReasons": [
                {
                    "Code": code,
                    "Message": "repository-private-canary",
                }
                for code in codes
            ],
        },
        "TransactWriteItems",
    )


class _ClaimTable:
    """Stateful high-level DynamoDB boundary used by claim tests."""

    name = "private-table-canary"

    def __init__(
        self,
        *,
        counter: int = 0,
        transact_error: Exception | None = None,
        reread_command: dict[str, Any] | None = None,
    ) -> None:
        self.counter = counter
        self.transact_error = transact_error
        self.reread_command = reread_command
        self.transactions: list[list[dict[str, Any]]] = []
        self.command_reads = 0

    def get_item(self, *, Key, ConsistentRead=True):  # noqa: N803
        del ConsistentRead
        if Key["SK"].startswith("MESSAGE_COMMAND#"):
            self.command_reads += 1
            return (
                {"Item": dict(self.reread_command)}
                if self.reread_command and self.transactions
                else {}
            )
        if Key["SK"].startswith("CHAT#"):
            return {"Item": {"count": self.counter}} if self.counter else {}
        return {}

    def transact_write_items(self, *, TransactItems):  # noqa: N803
        self.transactions.append(TransactItems)
        if self.transact_error is not None:
            raise self.transact_error
        return {}


class _BatchReadTable:
    name = "private-table-canary"

    def __init__(self, *, permanently_unprocessed: bool = False) -> None:
        self.calls: list[list[dict[str, str]]] = []
        self.permanently_unprocessed = permanently_unprocessed

    def batch_get_item(self, *, RequestItems):  # noqa: N803
        keys = RequestItems[self.name]["Keys"]
        self.calls.append(keys)
        key = keys[0]
        attachment_id = key["PK"].removeprefix("ATTACHMENT#")
        if self.permanently_unprocessed or len(self.calls) == 1:
            return {
                "Responses": {self.name: []},
                "UnprocessedKeys": {self.name: {"Keys": keys}},
            }
        return {
            "Responses": {
                self.name: [
                    {
                        "PK": key["PK"],
                        "SK": key["SK"],
                        "attachment_id": attachment_id,
                        "owner_id": "student-1",
                        "status": "active",
                    }
                ]
            },
            "UnprocessedKeys": {},
        }


def test_batch_get_retries_unprocessed_keys_before_projecting_resume_state() -> None:
    table = _BatchReadTable()

    result = attachment_repo.get_attachments(["attachment-1"], table=table)

    assert list(result) == ["attachment-1"]
    assert len(table.calls) == 2


def test_batch_get_exhaustion_is_a_redacted_dependency_failure() -> None:
    table = _BatchReadTable(permanently_unprocessed=True)

    with pytest.raises(attachment_repo.AttachmentRepositoryConflict) as captured:
        attachment_repo.get_attachments(["attachment-1"], table=table)

    assert captured.value.category == "dependency_failure"
    assert len(table.calls) == 3


def test_repository_claim_persists_one_complete_command_usage_identity() -> None:
    table = _ClaimTable(counter=2)

    result = ask_question_store.claim_message_command_and_quota(
        command=_command(),
        owner_id="student-1",
        quota_period="2026-07-17",
        limit=8,
        expires_at=1784505599,
        table=table,
    )

    assert result.disposition is ask_question_store.MessageCommandDisposition.CLAIMED
    assert result.counter_value == 3
    command_put = next(
        operation["Put"]["Item"]
        for operation in table.transactions[0]
        if operation.get("Put", {}).get("Item", {}).get("entity_type")
        == "message_command"
    )
    assert command_put["quota_period"] == "2026-07-17"
    assert command_put["counter_value"] == 3
    assert command_put["fingerprint"] == "f" * 64
    assert command_put["usage_event_id"] == _command()["usage_event_id"]
    assert command_put["requested_attachments"] == _command()["requested_attachments"]
    assert command_put["deterministic_attachment_ids"] == ["attachment-1"]
    assert command_put["history_anchor_message_id"] == "student-message-1"
    assert command_put["student_message_id"] == "student-message-1"
    assert command_put["assistant_message_id"] == "assistant-message-1"


def test_claim_cas_contention_rereads_same_fingerprint_instead_of_false_429() -> None:
    existing = _command(counter_value=4)
    error = _transaction_cancel(
        ["None", "ConditionalCheckFailed", "None", "None"]
    )
    table = _ClaimTable(counter=3, transact_error=error, reread_command=existing)

    result = ask_question_store.claim_message_command_and_quota(
        command=_command(),
        owner_id="student-1",
        quota_period="2026-07-17",
        limit=8,
        expires_at=1784505599,
        table=table,
    )

    assert result.disposition is ask_question_store.MessageCommandDisposition.RESUME
    assert result.counter_value == 4
    assert result.command == existing
    assert table.command_reads >= 1


def test_claim_true_limit_requires_durable_counter_evidence() -> None:
    table = _ClaimTable(counter=8)
    result = ask_question_store.claim_message_command_and_quota(
        command=_command(),
        owner_id="student-1",
        quota_period="2026-07-17",
        limit=8,
        expires_at=1784505599,
        table=table,
    )
    assert result.disposition is ask_question_store.MessageCommandDisposition.QUOTA_EXCEEDED
    assert result.counter_value == 8
    assert table.transactions == []


def test_bind_transaction_uses_persisted_period_and_puts_usage_with_message_effects() -> None:
    command = _command(counter_value=3)
    operations = attachment_repo.build_message_attachment_transaction(
        message={"PK": "CONV#conv-1", "SK": "MSG#student-message-1"},
        fresh=[],
        reused=[],
        associations=[],
        owner_id="student-1",
        limit_bytes=5 * 1024**3,
        now_iso="2026-07-18T00:00:02+00:00",
        trailing_operations=ask_question_store.message_committed_operations(
            command, owner_id="student-1", now_iso="2026-07-18T00:00:02+00:00"
        ),
    )

    usage_operation = next(
        operation
        for operation in operations
        if operation.kind is attachment_repo.TransactionOperationKind.USAGE_EVENT_PUT
    )
    assert isinstance(usage_operation.item, dict)
    put = usage_operation.item["Put"]
    assert isinstance(put, dict)
    usage = put["Item"]
    assert isinstance(usage, dict)
    assert usage["quota_period"] == "2026-07-17"
    assert usage["counter_value_after"] == 3
    assert usage["event_id"] == command["usage_event_id"]
    assert usage["request_correlation_id"] == "student-message-1"
    assert usage["SK"].startswith("EVENT#chat_message#2026-07-17#")
    assert [operation.kind for operation in operations].count(
        attachment_repo.TransactionOperationKind.MESSAGE_COMMAND_UPDATE
    ) == 1


class _CompletionTable:
    def __init__(self, *, command: dict[str, Any], commit_then_raise: bool = False) -> None:
        self.command = dict(command)
        self.commit_then_raise = commit_then_raise
        self.calls = 0

    def transact_write_items(self, *, TransactItems):  # noqa: N803
        self.calls += 1
        if self.commit_then_raise:
            update = next(
                operation["Update"]
                for operation in TransactItems
                if "Update" in operation
            )
            self.command.update(
                status="completed",
                result_json=update["ExpressionAttributeValues"][":result"],
                completed_at=update["ExpressionAttributeValues"][":completed_at"],
            )
        raise TimeoutError("completion-provider-private-canary")

    def get_item(self, *, Key, ConsistentRead=True):  # noqa: N803
        del Key, ConsistentRead
        return {"Item": dict(self.command)}


@pytest.mark.parametrize("commit_then_raise", [False, True])
def test_completion_transport_is_typed_and_commit_then_raise_reconciles(
    commit_then_raise: bool,
) -> None:
    table = _CompletionTable(
        command=_command(status="ai_running", leaseOwner="lease-1", attempt=1),
        commit_then_raise=commit_then_raise,
    )
    result = ask_question_store.complete_message_command(
        conversation_id="conv-1",
        idempotency_key="message-key",
        owner_id="student-1",
        lease_owner="lease-1",
        assistant_message={"PK": "CONV#conv-1", "SK": "MSG#assistant-message-1"},
        result_json='{"studentMessage":{},"assistantMessage":{}}',
        completed_at="2026-07-18T00:00:03+00:00",
        table=table,
    )
    expected = (
        ask_question_store.MessageCommandDisposition.COMPLETED
        if commit_then_raise
        else ask_question_store.MessageCommandDisposition.RETRYABLE
    )
    assert result.disposition is expected
    assert "private-canary" not in str(result)


class _RejectTable:
    def __init__(self) -> None:
        self.transactions: list[list[dict[str, Any]]] = []
        self.command = _command(counter_value=3)

    def transact_write_items(self, *, TransactItems):  # noqa: N803
        self.transactions.append(TransactItems)
        return {}

    def get_item(self, *, Key, ConsistentRead=True):  # noqa: N803
        del Key, ConsistentRead
        return {"Item": dict(self.command)}


@pytest.mark.parametrize(
    "code",
    ["storage_quota_exceeded", "upload_not_found"],
)
def test_deterministic_prebind_rejection_is_terminal_and_compensates_once(code: str) -> None:
    table = _RejectTable()
    result = ask_question_store.reject_message_command_and_compensate(
        conversation_id="conv-1",
        idempotency_key="message-key",
        owner_id="student-1",
        fingerprint="f" * 64,
        error_code=code,
        now_iso="2026-07-18T00:00:01+00:00",
        table=table,
    )
    assert result.disposition is ask_question_store.MessageCommandDisposition.REJECTED
    assert result.error_code == code
    kinds = [operation.kind for operation in result.operations]
    assert kinds == [
        attachment_repo.TransactionOperationKind.MESSAGE_COMMAND_REJECT,
        attachment_repo.TransactionOperationKind.CHAT_QUOTA_OPERATION_DELETE,
        attachment_repo.TransactionOperationKind.CHAT_QUOTA_COMPENSATE,
    ]
    assert len(table.transactions) == 1


@pytest.mark.parametrize(
    ("status_value", "expected"),
    [
        ("claimed", "claimed"),
        ("message_committed", "resume"),
        ("ai_running", "lease_held"),
        ("completed", "completed"),
        ("rejected", "rejected"),
        ("terminal_failed", "terminal"),
        ("expired", "expired"),
    ],
)
def test_command_state_classifier_is_closed(status_value: str, expected: str) -> None:
    command = _command(status=status_value)
    if status_value == "completed":
        command["result_json"] = "{}"
    if status_value == "rejected":
        command["error_code"] = "upload_not_found"
    result = ask_question_store.classify_message_command(
        command,
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=1784307600,
    )
    assert result.disposition.value == expected


@pytest.mark.parametrize(
    ("retryable", "attempt", "expected"),
    [
        (True, 1, "resume"),
        (True, 2, "resume"),
        (True, 3, "terminal"),
        (False, 1, "terminal"),
        (None, 1, "terminal"),
    ],
)
def test_a_failed_command_resumes_only_when_unpaid_with_attempts_left(
    retryable: bool | None, attempt: int, expected: str
) -> None:
    command = _command(status="failed", attempt=attempt, failure_category="deadline_exceeded")
    if retryable is not None:
        command["failure_retryable"] = retryable
    result = ask_question_store.classify_message_command(
        command,
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=1784307600,
    )
    assert result.disposition.value == expected


def test_command_state_classifier_distinguishes_missing_and_conflict() -> None:
    missing = ask_question_store.classify_message_command(
        None,
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=1784307600,
    )
    conflict = ask_question_store.classify_message_command(
        _command(fingerprint="0" * 64),
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=1784307600,
    )
    assert missing.disposition is ask_question_store.MessageCommandDisposition.MISSING
    assert conflict.disposition is ask_question_store.MessageCommandDisposition.IDEMPOTENCY_CONFLICT


def test_command_state_classifier_rejects_unversioned_rows() -> None:
    command = _command(status="claimed")
    command.pop("schema_version")

    result = ask_question_store.classify_message_command(
        command,
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=1784307600,
    )

    assert result.disposition is ask_question_store.MessageCommandDisposition.RETRYABLE


def _route_client() -> TestClient:
    app = FastAPI()
    app.include_router(conversations.router, prefix="/conversations")
    app.dependency_overrides[get_actor] = _actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def test_create_conversation_routes_initial_message_through_shared_executor(
    table, model, monkeypatch
) -> None:
    """The first message is committed under the account fence generation the
    conversation was created under."""
    table.seed_active_account(STUDENT, generation=7)
    allowance = AtomicAllowanceTable()
    allowance.items[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]["generation"] = 7
    _patch_allowance_table(monkeypatch, allowance)

    response = _question_client().post(
        "/conversations",
        json={
            "subject": "math",
            "grade": "Sek1",
            "initialMessage": "through-shared-command",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert [message["role"] for message in body["messages"]] == ["student", "assistant"]
    assert body["messages"][0]["content"] == "through-shared-command"
    command = table.rows[
        tuple(
            _command_key(body["id"], f"initial-{body['id']}").values()
        )
    ]
    assert command["account_fence_generation"] == 7
    assert table.rows[(f"CONV#{body['id']}", "CONV")]["account_fence_generation"] == 7


@pytest.mark.parametrize("suffix", ["/messages", "/messages/stream"])
def test_regular_and_sse_get_item_transport_faults_share_safe_retry(
    monkeypatch, suffix: str
) -> None:
    class FaultingTable:
        def get_item(self, **_kwargs):
            raise TimeoutError("get-item-provider-coordinate-private-canary")

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
    monkeypatch.setattr(attachment_repo, "get_table", FaultingTable)
    response = _route_client().post(
        f"/conversations/conv-1{suffix}",
        json={"content": "content-private-canary", "idempotencyKey": "fault-key"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "upload_service_unavailable"
    assert set(response.json()["detail"]) == {"code", "message", "correlationId"}
    assert "private-canary" not in response.text


def test_cross_midnight_replay_uses_original_quota_and_usage_identity() -> None:
    before_midnight = _command(counter_value=5)
    classified = ask_question_store.classify_message_command(
        before_midnight,
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=int(datetime(2026, 7, 18, 0, 0, 5, tzinfo=timezone.utc).timestamp()),
    )
    assert classified.command is not None
    operations = attachment_repo.build_message_attachment_transaction(
        message={"PK": "CONV#conv-1", "SK": "MSG#student-message-1"},
        fresh=[],
        reused=[],
        associations=[],
        owner_id="student-1",
        limit_bytes=5 * 1024**3,
        now_iso="2026-07-18T00:00:05+00:00",
        trailing_operations=ask_question_store.message_committed_operations(
            classified.command, owner_id="student-1", now_iso="2026-07-18T00:00:05+00:00"
        ),
    )
    usage_operation = next(
        operation
        for operation in operations
        if operation.kind is attachment_repo.TransactionOperationKind.USAGE_EVENT_PUT
    )
    assert isinstance(usage_operation.item, dict)
    put = usage_operation.item["Put"]
    assert isinstance(put, dict)
    usage = put["Item"]
    assert isinstance(usage, dict)
    assert usage["quota_period"] == "2026-07-17"
    assert usage["counter_value_after"] == 5
    assert usage["event_id"] == before_midnight["usage_event_id"]


def test_repository_get_item_fault_is_redacted_dependency_result() -> None:
    class Table:
        def get_item(self, **_kwargs):
            raise RuntimeError("batch-provider-private-canary")

    with pytest.raises(attachment_repo.AttachmentRepositoryConflict) as captured:
        ask_question_store.read_message_command_result(
            "conv-1",
            "message-key",
            owner_id="student-1",
            fingerprint="f" * 64,
            table=Table(),
        )
    assert captured.value.category == "dependency_failure"
    assert "private-canary" not in str(captured.value)


@pytest.mark.parametrize(
    ("ending", "expected"),
    [
        ({"status": "rejected", "error_code": "upload_not_found"}, "upload_not_found"),
        ({"status": "terminal_failed"}, "message_failed"),
        ({"status": "expired"}, "message_command_expired"),
        (None, "message_command_not_found"),
        ({"status": "unknown"}, "upload_service_unavailable"),
    ],
)
def test_polling_projects_nonlive_states_without_in_progress(
    table, model, monkeypatch, ending: dict[str, Any] | None, expected: str
) -> None:
    """Waiting for another delivery, the command ends in a state that is not live."""
    _commit("message-key")
    key = tuple(_command_key(CONV, "message-key").values())
    held = dict(table.rows[key])
    held.update(
        status="ai_running",
        attempt=1,
        leaseOwner="another-delivery",
        expiresAt=int(datetime.now(timezone.utc).timestamp()) + 300,
    )
    table.seed(held)

    def the_other_delivery_ends_it(_seconds: float) -> None:
        if ending is None:
            table.rows.pop(key, None)
        else:
            table.seed({**held, **ending})

    monkeypatch.setattr(_answering.time, "sleep", the_other_delivery_ends_it)

    with pytest.raises(AttachmentDecisionError) as captured:
        _submit("message-key")

    assert captured.value.code.value == expected
    assert captured.value.code.value != "message_in_progress"


@pytest.mark.parametrize("suffix", ["/messages", "/messages/stream"])
def test_regular_and_sse_replay_exact_durable_rejection(table, model, suffix: str) -> None:
    request = SendMessageRequest.model_validate(
        {"content": "same", "idempotencyKey": "message-key"}
    )
    command_id = str(uuid5(NAMESPACE_URL, f"stoa.conversation.send.v1:{CONV}:message-key"))
    student_message_id = str(uuid5(UUID(command_id), "student-message"))
    table.seed(
        {
            **_command_key(CONV, "message-key"),
            **_command(
                status="rejected",
                error_code="storage_quota_exceeded",
                conversation_id=CONV,
                fingerprint=message_request_fingerprint(request),
                command_id=command_id,
                student_message_id=student_message_id,
                assistant_message_id=str(uuid5(UUID(command_id), "assistant-message")),
                history_anchor_message_id=student_message_id,
                history_message_ids=[],
                history_fingerprint="0" * 64,
                attachment_count=1,
            ),
        }
    )

    response = _question_client().post(
        f"/conversations/{CONV}{suffix}",
        json={"content": "same", "idempotencyKey": "message-key"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "storage_quota_exceeded"
    assert "private" not in response.text
    assert model.calls == []
