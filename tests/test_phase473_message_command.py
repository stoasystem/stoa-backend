"""Lower-boundary contract for the durable conversation message command.

These tests intentionally drive repository clients and transaction responses.  They
do not replace the command executor or completion repository method with a mock.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.db.repositories import attachment_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import conversations
from stoa.security.identity import AccountStatus, Actor, CanonicalRole


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
                    "Item": {"PK": {"S": "private-coordinate-canary"}},
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
            return {"Item": dict(self.reread_command)} if self.reread_command else {}
        if Key["SK"].startswith("CHAT#"):
            return {"Item": {"count": self.counter}} if self.counter else {}
        return {}

    def transact_write_items(self, *, TransactItems):  # noqa: N803
        self.transactions.append(TransactItems)
        if self.transact_error is not None:
            raise self.transact_error
        return {}


def test_repository_claim_persists_one_complete_command_usage_identity() -> None:
    table = _ClaimTable(counter=2)

    result = attachment_repo.claim_message_command_and_quota(
        command=_command(),
        owner_id="student-1",
        quota_period="2026-07-17",
        limit=8,
        expires_at=1784505599,
        table=table,
    )

    assert result.disposition is attachment_repo.MessageCommandDisposition.CLAIMED
    assert result.counter_value == 3
    command_put = table.transactions[0][0]["Put"]["Item"]
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
    error = _transaction_cancel(["ConditionalCheckFailed", "None", "None"])
    table = _ClaimTable(counter=3, transact_error=error, reread_command=existing)

    result = attachment_repo.claim_message_command_and_quota(
        command=_command(),
        owner_id="student-1",
        quota_period="2026-07-17",
        limit=8,
        expires_at=1784505599,
        table=table,
    )

    assert result.disposition is attachment_repo.MessageCommandDisposition.RESUME
    assert result.counter_value == 4
    assert result.command == existing
    assert table.command_reads >= 1


def test_claim_true_limit_requires_durable_counter_evidence() -> None:
    table = _ClaimTable(counter=8)
    result = attachment_repo.claim_message_command_and_quota(
        command=_command(),
        owner_id="student-1",
        quota_period="2026-07-17",
        limit=8,
        expires_at=1784505599,
        table=table,
    )
    assert result.disposition is attachment_repo.MessageCommandDisposition.QUOTA_EXCEEDED
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
        command=command,
    )

    usage = next(
        operation["Put"]["Item"]
        for operation in operations
        if operation.kind is attachment_repo.TransactionOperationKind.USAGE_EVENT_PUT
    )
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
            update = TransactItems[1]["Update"]
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
    result = attachment_repo.complete_message_command(
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
        attachment_repo.MessageCommandDisposition.COMPLETED
        if commit_then_raise
        else attachment_repo.MessageCommandDisposition.RETRYABLE
    )
    assert result.disposition is expected
    assert "private-canary" not in str(result)


class _RejectTable:
    def __init__(self) -> None:
        self.transactions: list[list[dict[str, Any]]] = []

    def transact_write_items(self, *, TransactItems):  # noqa: N803
        self.transactions.append(TransactItems)
        return {}

    def get_item(self, *, Key, ConsistentRead=True):  # noqa: N803
        del Key, ConsistentRead
        return {}


@pytest.mark.parametrize(
    "code",
    ["storage_quota_exceeded", "upload_not_found"],
)
def test_deterministic_prebind_rejection_is_terminal_and_compensates_once(code: str) -> None:
    table = _RejectTable()
    result = attachment_repo.reject_message_command_and_compensate(
        conversation_id="conv-1",
        idempotency_key="message-key",
        owner_id="student-1",
        fingerprint="f" * 64,
        error_code=code,
        now_iso="2026-07-18T00:00:01+00:00",
        table=table,
    )
    assert result.disposition is attachment_repo.MessageCommandDisposition.REJECTED
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
    result = attachment_repo.classify_message_command(
        command,
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=1784307600,
    )
    assert result.disposition.value == expected


def test_command_state_classifier_distinguishes_missing_and_conflict() -> None:
    missing = attachment_repo.classify_message_command(
        None,
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=1784307600,
    )
    conflict = attachment_repo.classify_message_command(
        _command(fingerprint="0" * 64),
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=1784307600,
    )
    assert missing.disposition is attachment_repo.MessageCommandDisposition.MISSING
    assert conflict.disposition is attachment_repo.MessageCommandDisposition.IDEMPOTENCY_CONFLICT


def _route_client() -> TestClient:
    app = FastAPI()
    app.include_router(conversations.router, prefix="/conversations")
    app.dependency_overrides[get_actor] = _actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def test_create_conversation_rejects_legacy_initial_message_before_effect(monkeypatch) -> None:
    effects: list[str] = []

    class Table:
        def put_item(self, **_kwargs):
            effects.append("put")

    monkeypatch.setattr(conversations, "get_table", Table)
    response = _route_client().post(
        "/conversations",
        json={"subject": "math", "grade": "Sek1", "initialMessage": "bypass"},
    )
    assert response.status_code == 422
    assert effects == []


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
    classified = attachment_repo.classify_message_command(
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
        command=classified.command,
    )
    usage = next(
        operation["Put"]["Item"]
        for operation in operations
        if operation.kind is attachment_repo.TransactionOperationKind.USAGE_EVENT_PUT
    )
    assert usage["quota_period"] == "2026-07-17"
    assert usage["counter_value_after"] == 5
    assert usage["event_id"] == before_midnight["usage_event_id"]


def test_repository_get_item_fault_is_redacted_dependency_result() -> None:
    class Table:
        def get_item(self, **_kwargs):
            raise RuntimeError("batch-provider-private-canary")

    with pytest.raises(attachment_repo.AttachmentRepositoryConflict) as captured:
        attachment_repo.read_message_command_result(
            "conv-1",
            "message-key",
            owner_id="student-1",
            fingerprint="f" * 64,
            table=Table(),
        )
    assert captured.value.category == "dependency_failure"
    assert "private-canary" not in str(captured.value)
