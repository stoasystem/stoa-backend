"""The question's own rows, tested where they are written: `ask_question._store`.

These drive `_store`'s functions against table doubles, moto and the shared
`FakeTable`, and assert on what reaches DynamoDB: the keys, the condition and
update expressions, their values, and the order of each transaction's
operations. Every test of the question that runs its entry points instead is
elsewhere; this is the only test module that imports `_store` (#204, decisions
14 and 18). A test elsewhere that needs to reach the store does it through
`fakes.ask_question` (`store_call`, `patch_store`, `fail_store`).

Each section below was moved here from the file its banner names (#220),
unchanged but for how it names the shared helpers it now imports.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from fakes.ask_question import (
    CONV,
    _called,
    _command_row,
    _commit,
    _deliver,
    _expire_lease,
    _Killed,
    _last_attempt_kept_its_answer,
    _message_command,
    _minutes_ago,
)
from fakes.ask_question import DELETED_STUDENT as STUDENT_ID
from fakes.ask_question import DELETION_NOW as NOW
from fakes.ask_question import PRIVATE_CONVERSATION as CONVERSATION_ID
from fakes.ask_question import _private_message as _message
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.dynamodb import from_wire
from stoa.db.repositories import attachment_repo
from stoa.services import learning_session
from stoa.services.ask_question import _store as ask_question_store


# ── from tests/test_phase473_message_command.py: claim, completion, rejection, classification ────


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

        TransactItems = from_wire(TransactItems)  # noqa: N806
        self.transactions.append(TransactItems)
        if self.transact_error is not None:
            raise self.transact_error
        return {}


def test_repository_claim_persists_one_complete_command_usage_identity() -> None:
    table = _ClaimTable(counter=2)

    result = ask_question_store.claim_message_command_and_quota(
        command=_message_command(),
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
    assert command_put["usage_event_id"] == _message_command()["usage_event_id"]
    assert command_put["requested_attachments"] == _message_command()["requested_attachments"]
    assert command_put["deterministic_attachment_ids"] == ["attachment-1"]
    assert command_put["history_anchor_message_id"] == "student-message-1"
    assert command_put["student_message_id"] == "student-message-1"
    assert command_put["assistant_message_id"] == "assistant-message-1"


def test_claim_cas_contention_rereads_same_fingerprint_instead_of_false_429() -> None:
    existing = _message_command(counter_value=4)
    # One reason per operation, the owner registry Put the fenced write adds
    # included (#397).
    error = _transaction_cancel(
        ["None", "ConditionalCheckFailed", "None", "None", "None"]
    )
    table = _ClaimTable(counter=3, transact_error=error, reread_command=existing)

    result = ask_question_store.claim_message_command_and_quota(
        command=_message_command(),
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
        command=_message_command(),
        owner_id="student-1",
        quota_period="2026-07-17",
        limit=8,
        expires_at=1784505599,
        table=table,
    )
    assert result.disposition is ask_question_store.MessageCommandDisposition.QUOTA_EXCEEDED
    assert result.counter_value == 8
    assert table.transactions == []


def _student_message_put(created_at: str) -> dict[str, object]:
    return learning_session.append(
        "conv-1",
        role="student",
        message_id="student-message-1",
        student_id="student-1",
        generation=1,
        content="question",
        created_at=created_at,
        attachment_ids=[],
    )


def _assistant_message_put(message_id: str) -> dict[str, object]:
    return learning_session.append(
        "conv-1",
        role="assistant",
        message_id=message_id,
        student_id="student-1",
        generation=1,
        content="answer",
        created_at="2026-07-18T00:00:03+00:00",
        structured=None,
    )


def test_bind_transaction_uses_persisted_period_and_puts_usage_with_message_effects() -> None:
    command = _message_command(counter_value=3)
    operations = attachment_repo.build_message_attachment_transaction(
        message_put=_student_message_put("2026-07-18T00:00:02+00:00"),
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

        TransactItems = from_wire(TransactItems)  # noqa: N806
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
        command=_message_command(status="ai_running", leaseOwner="lease-1", attempt=1),
        commit_then_raise=commit_then_raise,
    )
    result = ask_question_store.complete_message_command(
        conversation_id="conv-1",
        idempotency_key="message-key",
        owner_id="student-1",
        lease_owner="lease-1",
        assistant_message_put=_assistant_message_put("assistant-message-1"),
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
        self.command = _message_command(counter_value=3)

    def transact_write_items(self, *, TransactItems):  # noqa: N803

        TransactItems = from_wire(TransactItems)  # noqa: N806
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
    command = _message_command(status=status_value)
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
    command = _message_command(status="failed", attempt=attempt, failure_category="deadline_exceeded")
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
        _message_command(fingerprint="0" * 64),
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=1784307600,
    )
    assert missing.disposition is ask_question_store.MessageCommandDisposition.MISSING
    assert conflict.disposition is ask_question_store.MessageCommandDisposition.IDEMPOTENCY_CONFLICT


def test_command_state_classifier_rejects_unversioned_rows() -> None:
    command = _message_command(status="claimed")
    command.pop("schema_version")

    result = ask_question_store.classify_message_command(
        command,
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=1784307600,
    )

    assert result.disposition is ask_question_store.MessageCommandDisposition.RETRYABLE


def test_cross_midnight_replay_uses_original_quota_and_usage_identity() -> None:
    before_midnight = _message_command(counter_value=5)
    classified = ask_question_store.classify_message_command(
        before_midnight,
        owner_id="student-1",
        fingerprint="f" * 64,
        now_epoch=int(datetime(2026, 7, 18, 0, 0, 5, tzinfo=timezone.utc).timestamp()),
    )
    assert classified.command is not None
    operations = attachment_repo.build_message_attachment_transaction(
        message_put=_student_message_put("2026-07-18T00:00:05+00:00"),
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


# ── from tests/test_attachment_security.py: the claim transaction and the AI lease ────


def test_message_command_claim_groups_command_quota_operation_and_counter() -> None:
    command: dict[str, object] = {
        "command_id": "opaque-command",
        "conversation_id": "opaque-conversation",
        "idempotency_key": "safe-key",
        "owner_id": "student-1",
        "fingerprint": "f" * 64,
        "status": "claimed",
        "created_at": "2026-07-16T00:00:00Z",
    }
    operations = ask_question_store.build_message_command_claim_transaction(
        command=command,
        owner_id="student-1",
        quota_period="2026-07-16",
        expected_counter=4,
        limit=8,
        expires_at=2_000_000_000,
    )
    # The account fence is put in front when the claim is sent (#297).
    assert [operation.kind for operation in operations] == [
        attachment_repo.TransactionOperationKind.MESSAGE_COMMAND_PUT,
        attachment_repo.TransactionOperationKind.CHAT_QUOTA_OPERATION_PUT,
        attachment_repo.TransactionOperationKind.CHAT_QUOTA_UPDATE,
    ]
    put = operations[0]["Put"]
    assert isinstance(put, dict)
    command_item = put["Item"]
    assert isinstance(command_item, dict)
    assert command_item["fingerprint"] == "f" * 64
    assert command_item["counter_value"] == 5
    assert "content" not in command_item and "attachment_ids" not in command_item
    quota_put = operations[1]["Put"]
    assert isinstance(quota_put, dict)
    quota_item = quota_put["Item"]
    assert isinstance(quota_item, dict)
    assert quota_item["SK"] == "CHAT_QUOTA_OP#opaque-command"
    update = operations[2]["Update"]
    assert isinstance(update, dict)
    update_values = update["ExpressionAttributeValues"]
    assert isinstance(update_values, dict)
    assert update_values[":next"] == 5


class _LeaseTable:
    def __init__(self, command):
        self.command = dict(command)

    def get_item(self, **_kwargs):
        return {"Item": dict(self.command)}

    def transact_write_items(self, *, TransactItems):  # noqa: N803

        TransactItems = from_wire(TransactItems)  # noqa: N806
        assert TransactItems[0]["ConditionCheck"]["Key"] == {
            "PK": "USER#student-1",
            "SK": "ACCOUNT_FENCE",
        }
        for operation in TransactItems[1:]:
            if "Update" in operation:
                self.update_item(**operation["Update"])

    def update_item(self, **kwargs):
        values = kwargs["ExpressionAttributeValues"]
        expression = kwargs["UpdateExpression"]
        valid = self.command.get("owner_id") == values[":owner"]
        if "leaseOwner=:lease_owner" in expression:
            valid = valid and (
                self.command.get("status") == "message_committed"
                or (
                    self.command.get("status") == "ai_running"
                    and int(self.command.get("expiresAt", 0)) <= values[":now"]
                    and int(self.command.get("attempt", 0)) < values[":max_attempts"]
                )
            )
            if valid:
                self.command.update(
                    status="ai_running",
                    leaseOwner=values[":lease_owner"],
                    claimedAt=values[":claimed"],
                    expiresAt=values[":expires"],
                    attempt=values[":attempt"],
                )
        elif expression.startswith("SET claimedAt"):
            valid = (
                valid
                and self.command.get("status") == "ai_running"
                and self.command.get("leaseOwner") == values[":lease_owner"]
                and int(self.command.get("expiresAt", 0)) > values[":now"]
            )
            if valid:
                self.command.update(claimedAt=values[":now"], expiresAt=values[":expires"])
        else:
            valid = valid and self.command.get("attempt", 0) >= values[":max"]
            if valid:
                self.command.update(status="terminal_failed")
        if not valid:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "private"}},
                "UpdateItem",
            )
        return {}


def test_ai_lease_excludes_active_owner_renews_takes_over_and_terminates() -> None:
    table = _LeaseTable(
        {
            "owner_id": "student-1",
            "account_fence_generation": 1,
            "status": "message_committed",
            "attempt": 0,
        }
    )
    first = ask_question_store.claim_message_ai_lease(
        conversation_id="conv-1", idempotency_key="key", owner_id="student-1",
        lease_owner="owner-a", now_epoch=100, expires_at=220, table=table,
    )
    assert first.disposition is ask_question_store.MessageCommandDisposition.CLAIMED
    assert first.attempt == 1
    held = ask_question_store.claim_message_ai_lease(
        conversation_id="conv-1", idempotency_key="key", owner_id="student-1",
        lease_owner="owner-b", now_epoch=150, expires_at=270, table=table,
    )
    assert held.disposition is ask_question_store.MessageCommandDisposition.LEASE_HELD
    assert held.attempt == 1
    assert ask_question_store.renew_message_ai_lease(
        conversation_id="conv-1", idempotency_key="key", owner_id="student-1",
        lease_owner="owner-a", now_epoch=160, expires_at=280, table=table,
    ) is True
    assert ask_question_store.renew_message_ai_lease(
        conversation_id="conv-1", idempotency_key="key", owner_id="student-1",
        lease_owner="stale-owner", now_epoch=170, expires_at=290, table=table,
    ) is False
    takeover = ask_question_store.claim_message_ai_lease(
        conversation_id="conv-1", idempotency_key="key", owner_id="student-1",
        lease_owner="owner-b", now_epoch=281, expires_at=401, table=table,
    )
    assert takeover.disposition is ask_question_store.MessageCommandDisposition.CLAIMED
    assert takeover.attempt == 2
    table.command["expiresAt"] = 400
    final_claim = ask_question_store.claim_message_ai_lease(
        conversation_id="conv-1", idempotency_key="key", owner_id="student-1",
        lease_owner="owner-c", now_epoch=401, expires_at=521, table=table,
    )
    assert final_claim.disposition is ask_question_store.MessageCommandDisposition.CLAIMED
    assert final_claim.attempt == 3
    table.command["expiresAt"] = 520
    terminal = ask_question_store.claim_message_ai_lease(
        conversation_id="conv-1", idempotency_key="key", owner_id="student-1",
        lease_owner="owner-d", now_epoch=521, expires_at=641, table=table,
    )
    assert terminal.disposition is ask_question_store.MessageCommandDisposition.TERMINAL
    assert terminal.attempt == 3
    marked = ask_question_store.mark_message_command_terminal(
        conversation_id="conv-1", idempotency_key="key", owner_id="student-1",
        now_iso="2026-07-16T00:00:00Z", table=table,
    )
    assert marked.disposition is ask_question_store.MessageCommandDisposition.TERMINAL
    assert table.command["status"] == "terminal_failed"


# ── from tests/test_phase473_conversation_replay.py: the completion's condition ────


def test_completion_condition_binds_lease_owner_generation_and_unexpired_deadline(
    monkeypatch,
) -> None:
    captured: list[attachment_repo.TransactionOperation] = []

    def transact(operations, **_kwargs):
        captured.extend(operations)

    monkeypatch.setattr(attachment_repo, "transact", transact)
    result = ask_question_store.complete_message_command(
        conversation_id="conv-1",
        idempotency_key="message-key",
        owner_id="student-1",
        lease_owner="lease-old",
        lease_attempt=1,
        completed_epoch=219,
        assistant_message_put=_assistant_message_put("assistant"),
        result_json='{"studentMessage":{},"assistantMessage":{}}',
        completed_at="2026-07-17T00:00:00Z",
        table=object(),
    )
    assert result.disposition is ask_question_store.MessageCommandDisposition.COMPLETED
    update_operation = next(
        operation
        for operation in captured
        if operation.kind is attachment_repo.TransactionOperationKind.MESSAGE_COMMAND_UPDATE
    )
    assert isinstance(update_operation.item, dict)
    update = update_operation.item["Update"]
    assert isinstance(update, dict)
    assert "leaseOwner=:lease_owner" in update["ConditionExpression"]
    assert "attempt=:lease_attempt" in update["ConditionExpression"]
    assert "expiresAt>:completed_epoch" in update["ConditionExpression"]
    values = update["ExpressionAttributeValues"]
    assert isinstance(values, dict)
    assert values[":lease_attempt"] == 1
    assert values[":completed_epoch"] == 219


def test_stale_worker_result_is_refused_after_deterministic_takeover(monkeypatch) -> None:
    command = {
        "owner_id": "student-1",
        "status": "ai_running",
        "leaseOwner": "lease-new",
        "attempt": 2,
        "expiresAt": 401,
    }

    class Table:
        def transact_write_items(self, **_kwargs):
            raise attachment_repo.ClientError(
                {
                    "Error": {
                        "Code": "ConditionalCheckFailedException",
                        "Message": "private",
                    }
                },
                "TransactWriteItems",
            )

        def get_item(self, **_kwargs):
            return {"Item": dict(command)}

    result = ask_question_store.complete_message_command(
        conversation_id="conv-1",
        idempotency_key="message-key",
        owner_id="student-1",
        lease_owner="lease-old",
        lease_attempt=1,
        completed_epoch=281,
        assistant_message_put=_assistant_message_put("assistant"),
        result_json='{"studentMessage":{},"assistantMessage":{}}',
        completed_at="2026-07-17T00:00:00Z",
        table=Table(),
    )
    assert result.disposition is ask_question_store.MessageCommandDisposition.RETRYABLE


# ── from tests/test_conversation_generation_worker.py: failure, lease claim, terminal ────


def test_a_recorded_failure_clears_what_the_attempt_left_behind(table, model) -> None:
    """Its outcome is known, so neither its mark nor any kept text should outlive it."""
    _commit("key-1")
    row = dict(_command_row(table, "key-1"))
    row.update(
        status="ai_running",
        leaseOwner="owner-1",
        attempt=1,
        expiresAt=2_000_000_000,
        provider_invoked_attempt=1,
        provider_result_attempt=1,
        provider_result_json='{"content":"private answer","allowance":null}',
    )
    table.seed(row)

    failed = ask_question_store.fail_message_command(
        conversation_id=CONV,
        idempotency_key="key-1",
        owner_id="student-1",
        lease_owner="owner-1",
        lease_attempt=1,
        failure_category="provider_error",
        retryable=True,
        now_iso="2026-09-25T08:00:00+00:00",
    )

    assert failed is True
    stored = _command_row(table, "key-1")
    for field in ("provider_invoked_attempt", "provider_result_attempt", "provider_result_json"):
        assert field not in stored


def test_a_claim_does_not_act_on_a_copy_read_before_a_call_was_marked(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    _commit("key-1")
    model.outcomes = [_called(_Killed())]
    with pytest.raises(_Killed):
        _deliver("key-1")
    _expire_lease(table, "key-1")
    stale = dict(_command_row(table, "key-1"))
    stale.pop("provider_invoked_attempt")
    read = ask_question_store.get_message_command
    monkeypatch.setattr(
        ask_question_store, "get_message_command", lambda *_a, **_k: dict(stale)
    )

    claimed = ask_question_store.claim_message_ai_lease(
        conversation_id=CONV,
        idempotency_key="key-1",
        owner_id="student-1",
        lease_owner="late",
        now_epoch=2_000_000_000,
        expires_at=2_000_000_300,
        account_fence_generation=1,
    )

    monkeypatch.setattr(ask_question_store, "get_message_command", read)
    assert claimed.disposition is not ask_question_store.MessageCommandDisposition.CLAIMED
    assert _command_row(table, "key-1").get("leaseOwner") != "late"


def test_a_command_that_kept_its_answer_is_not_ended_terminal(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The request's own terminal branch must not drop it either."""
    _last_attempt_kept_its_answer(table, model, monkeypatch, "last")
    _expire_lease(table, "last")

    ended = ask_question_store.mark_message_command_terminal(
        conversation_id=CONV,
        idempotency_key="last",
        owner_id=_command_row(table, "last")["owner_id"],
        now_iso=_minutes_ago(0),
    )

    assert ended.disposition is not ask_question_store.MessageCommandDisposition.TERMINAL
    assert _command_row(table, "last")["status"] == "ai_running"


# ── from tests/test_chat_quota_zero_count_moto.py: the day's chat counter, against moto ────
#
# #102 against moto: a day's chat counter that reads 0 because its row holds 0.
#
# The claim reads the counter, and on 0 it took the row to be missing and
# conditioned the increment on `attribute_not_exists(#count)`. A row that exists
# with `count = 0` fails that every time, so every message for the rest of the day
# answered 503 `upload_service_unavailable`. Such a row is what the compensation
# for a rejected first message leaves (`SET #count=#count-:one`, 1 -> 0), and what
# a hand reset to 0 left on 2026-10-10 (stoa-frontend#26).
#
# The hand-written claim doubles do not evaluate condition expressions, which is
# how this passed them; moto does.


OWNER = "student-1"
PERIOD = "2026-10-10"
EXPIRES = 1791767772


def _table():
    table = boto3.resource("dynamodb", region_name="eu-central-2").create_table(
        TableName="chat-quota-zero",
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                   {"AttributeName": "SK", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"},
                              {"AttributeName": "SK", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.put_item(Item={"PK": f"USER#{OWNER}", "SK": "ACCOUNT_FENCE",
                         "status": "active", "generation": 1})
    return table


def _command(key: str) -> dict[str, Any]:
    message = f"student-message-{key}"
    return {
        "entity_type": "message_command",
        "schema_version": "message-command.v2",
        "command_id": f"command-{key}",
        "conversation_id": "conv-1",
        "owner_id": OWNER,
        "idempotency_key": key,
        "fingerprint": "f" * 64,
        "status": "claimed",
        "student_message_id": message,
        "assistant_message_id": f"assistant-message-{key}",
        "deterministic_attachment_ids": [],
        "requested_attachments": [],
        "quota_period": PERIOD,
        "usage_action": "chat_message",
        "usage_resource_id": message,
        "usage_idempotency_key": f"chat_message:{message}",
        "usage_event_id": f"{OWNER}:chat_message:{PERIOD}:chat_message:{message}",
        "history_anchor_message_id": message,
        "history_anchor_created_at": "2026-10-10T08:55:00+00:00",
        "attempt": 0,
        "created_at": "2026-10-10T08:55:00+00:00",
        "expires_at": EXPIRES,
    }


def _claim(table, key: str) -> ask_question_store.MessageCommandResult:
    return ask_question_store.claim_message_command_and_quota(
        command=_command(key),
        owner_id=OWNER,
        quota_period=PERIOD,
        limit=8,
        expires_at=EXPIRES,
        table=table,
    )


def _count(table) -> int | None:
    item = table.get_item(Key=ask_question_store.chat_quota_key(OWNER, PERIOD),
                          ConsistentRead=True).get("Item")
    return None if item is None else int(item["count"])


@mock_aws
def test_a_day_with_no_counter_row_claims_and_starts_it_at_one():
    table = _table()

    result = _claim(table, "first")

    assert result.disposition is ask_question_store.MessageCommandDisposition.CLAIMED
    assert result.counter_value == 1
    assert _count(table) == 1


@mock_aws
def test_a_counter_row_that_holds_zero_claims_like_a_missing_one():
    table = _table()
    table.put_item(Item={**ask_question_store.chat_quota_key(OWNER, PERIOD),
                         "count": 0, "expires_at": EXPIRES})

    result = _claim(table, "after-reset")

    assert result.disposition is ask_question_store.MessageCommandDisposition.CLAIMED
    assert result.counter_value == 1
    assert _count(table) == 1


@mock_aws
def test_the_next_message_claims_after_the_first_was_rejected_and_compensated():
    table = _table()
    assert _claim(table, "first").disposition is ask_question_store.MessageCommandDisposition.CLAIMED

    rejected = ask_question_store.reject_message_command_and_compensate(
        conversation_id="conv-1",
        idempotency_key="first",
        owner_id=OWNER,
        fingerprint="f" * 64,
        error_code="upload_not_found",
        now_iso="2026-10-10T08:55:01+00:00",
        table=table,
    )
    assert rejected.disposition is ask_question_store.MessageCommandDisposition.REJECTED
    assert _count(table) == 0

    second = _claim(table, "second")

    assert second.disposition is ask_question_store.MessageCommandDisposition.CLAIMED
    assert second.counter_value == 1
    assert _count(table) == 1


@mock_aws
def test_a_zero_row_still_refuses_a_claim_that_raced_past_it():
    # The compare-and-set still holds at zero: once another claim has moved the
    # row to 1, a claim built on the 0 it read cannot write 1 over it.
    table = _table()
    table.put_item(Item={**ask_question_store.chat_quota_key(OWNER, PERIOD),
                         "count": 0, "expires_at": EXPIRES})
    stale = ask_question_store.build_message_command_claim_transaction(
        command=_command("stale"),
        owner_id=OWNER,
        quota_period=PERIOD,
        expected_counter=0,
        limit=8,
        expires_at=EXPIRES,
    )
    assert _claim(table, "winner").counter_value == 1

    try:
        attachment_repo.transact(stale, table=table, owner=OWNER, generation=1)
    except attachment_repo.AttachmentTransactionError:
        pass
    else:
        raise AssertionError("a claim built on a stale 0 was written")
    assert _count(table) == 1


# ── from tests/test_phase473_conversation_deletion.py: the account fence, the cancel ────


def test_command_claim_and_text_only_message_commit_share_account_fence() -> None:
    command = {
        "command_id": "command-private",
        "conversation_id": CONVERSATION_ID,
        "idempotency_key": "idem",
        "fingerprint": "f" * 64,
        "created_at": NOW,
        "usage_action": "chat_message",
        "usage_idempotency_key": "usage-private",
        "usage_event_id": "event-private",
        "usage_resource_id": "request-private",
        "quota_period": "2026-07-18",
        "counter_value": 1,
        "expires_at": 100,
    }
    claim = ask_question_store.build_message_command_claim_transaction(
        command=command,
        owner_id=STUDENT_ID,
        quota_period="2026-07-18",
        expected_counter=0,
        limit=10,
        expires_at=100,
        account_fence_generation=7,
    )
    # The claim, like the commit below, is sent behind the fence at its generation.
    assert all(
        operation.kind is not attachment_repo.TransactionOperationKind.ACCOUNT_RETENTION_FENCE_CHECK
        for operation in claim
    )
    claimed: list[dict[str, Any]] = []

    class _ClaimCapture:
        def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
            claimed.extend(from_wire(TransactItems))

    attachment_repo.transact(claim, owner=STUDENT_ID, generation=7, table=_ClaimCapture())
    assert claimed[0]["ConditionCheck"]["Key"] == {"PK": f"USER#{STUDENT_ID}", "SK": "ACCOUNT_FENCE"}
    assert claimed[0]["ConditionCheck"]["ExpressionAttributeValues"][":generation"] == 7

    private = _message()
    commit = attachment_repo.build_message_attachment_transaction(
        message_put=learning_session.append(
            CONVERSATION_ID,
            role="student",
            message_id=private["message_id"],
            student_id=STUDENT_ID,
            generation=7,
            content=private["content"],
            created_at=private["created_at"],
            attachment_ids=private["attachment_ids"],
        ),
        fresh=[],
        reused=[],
        associations=[],
        owner_id=STUDENT_ID,
        limit_bytes=100,
        now_iso=NOW,
        trailing_operations=ask_question_store.message_committed_operations(
            {**command, "owner_id": STUDENT_ID}, owner_id=STUDENT_ID, now_iso=NOW
        ),
    )
    # The commit is sent behind the fence the message was stamped with.
    assert all(
        operation.kind is not attachment_repo.TransactionOperationKind.ACCOUNT_RETENTION_FENCE_CHECK
        for operation in commit
    )
    sent: list[dict[str, Any]] = []

    class _Capture:
        def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
            sent.extend(from_wire(TransactItems))

    attachment_repo.transact(commit, owner=STUDENT_ID, generation=7, table=_Capture())
    assert sent[0]["ConditionCheck"]["Key"] == {"PK": f"USER#{STUDENT_ID}", "SK": "ACCOUNT_FENCE"}
    assert sent[0]["ConditionCheck"]["ExpressionAttributeValues"][":generation"] == 7


def test_stale_command_cancel_removes_result_fingerprint_and_lease() -> None:
    cancel = ask_question_store.cancel_stale_message_command
    updates: list[dict[str, Any]] = []

    class _Table:
        def cancel_stale_message_command(self, **kwargs: Any) -> None:
            updates.append(kwargs)

    command = _message(
        "MESSAGE_COMMAND#idem",
        entity_type="message_command",
        status="ai_running",
        result_json='{"private":"assistant"}',
        fingerprint="f" * 64,
        leaseOwner="worker-private",
    )
    result = cancel(
        command,
        owner_id=STUDENT_ID,
        deletion_generation=7,
        now_iso=NOW,
        table=_Table(),
    )
    assert result["status"] == "canceled"
    assert updates and set(updates[0]["remove_fields"]) >= {
        "result_json",
        "fingerprint",
        "leaseOwner",
        "claimedAt",
        "expiresAt",
    }


# ── from tests/test_conversations.py: who may read the progress ───────────────


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


# ── from tests/test_phase473_provider_cleanup.py: stored attempts, claim conditions ────


# When the provider cleanup tests run; the claim below expires two days after it.
NOW_EPOCH = int(datetime(2026, 7, 17, tzinfo=UTC).timestamp())


def test_stored_lease_attempt_accepts_decimal() -> None:
    assert ask_question_store._optional_positive_int(Decimal(3)) == 3
    assert ask_question_store._optional_positive_int(Decimal("3.5")) is None
    assert ask_question_store._optional_positive_int(True) is None


def _comparison_operands(expression: str) -> list[tuple[str, str]]:
    import re

    return re.findall(r"(\S+?)\s*(?:<=|>=|<|>)\s*(\S+)", expression or "")


def test_claim_conditions_compare_a_path_not_two_placeholders() -> None:
    """DynamoDB needs a document path on the left of a comparator.

    Comparing two placeholders is rejected before the condition is ever
    evaluated, so a claim built this way fails for every student. Fakes accept
    it because they never parse the expression.
    """
    for expected_counter in (0, 7):
        operations = ask_question_store.build_message_command_claim_transaction(
            command={
                "command_id": "command-1",
                "conversation_id": "conversation-1",
                "idempotency_key": "idempotency-1",
                "created_at": "2026-08-25T00:00:00+00:00",
            },
            owner_id="student-1",
            quota_period="2026-08-25",
            expected_counter=expected_counter,
            limit=50,
            expires_at=NOW_EPOCH + 172800,
            account_fence_generation=1,
        )
        for operation in operations:
            body = next(iter(operation.item.values()))
            condition = body.get("ConditionExpression", "")
            for left, right in _comparison_operands(condition):
                assert not (left.startswith(":") and right.startswith(":")), (
                    f"comparison between two placeholders: {left} vs {right}"
                )
