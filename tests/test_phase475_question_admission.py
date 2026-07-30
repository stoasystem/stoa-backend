"""Lower-boundary proof for atomic question-submission admission."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Mapping
from typing import TypeGuard

import pytest
from botocore.exceptions import ClientError

from stoa.db.repositories import attachment_repo, question_submission_repo
from stoa.services import usage_ledger_service


def _fingerprint(
    *, content: str = "Wie löse ich x + 1 = 3?", attachments: tuple[str, ...] = ()
) -> str:
    return question_submission_repo.question_submission_fingerprint(
        subject=" Mathematik ",
        original_content=content,
        corrected_content=None,
        attachment_identities=attachments,
    )


def _command_digest(
    *, student_id: str = "student-1", caller_key: str = "request-123"
) -> str:
    return question_submission_repo.question_submission_command_digest(
        student_id, caller_key
    )


def _question(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "question_id": "question-1",
        "student_id": "student-1",
        "subject": "math",
        "content": "Wie löse ich x + 1 = 3?",
        "original_content": "Wie löse ich x + 1 = 3?",
        "corrected_text": None,
        "attachment_source_identity": None,
        "status": "pending",
        "created_at": "2026-07-21T20:00:00+00:00",
    }
    item.update(overrides)
    return item


def _usage(*, counter_value: int = 1) -> dict[str, object]:
    return usage_ledger_service.build_question_usage_event(
        student_id="student-1",
        question_id="question-1",
        quota_period="2026-07-21",
        idempotency_digest=_command_digest(),
        counter_key="USAGE#student-1/QUESTION#2026-07-21",
        counter_value=counter_value,
        quantity=1,
        entitlement={
            "effectivePlan": "free_trial",
            "source": "local",
            "limits": {"dailyAiQuestionLimit": 2},
        },
        created_at="2026-07-21T20:00:00+00:00",
    )


def _conditional_error() -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": "TransactionCanceledException",
                "Message": "private-provider-canary",
            },
            "CancellationReasons": [],
        },
        "TransactWriteItems",
    )


def _is_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping) and all(
        isinstance(key, str) for key in value
    )


def _required_mapping(value: object) -> Mapping[str, object]:
    if not _is_object_mapping(value):
        raise _conditional_error()
    return value


def _is_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _required_dict(value: object) -> dict[str, object]:
    if not _is_object_dict(value):
        raise _conditional_error()
    return value


def _required_str(value: object) -> str:
    if not isinstance(value, str):
        raise _conditional_error()
    return value


def _required_int(value: object) -> int:
    if type(value) is not int:
        raise _conditional_error()
    return value


class _AdmissionTable:
    """Atomic high-level fake with failure injection and strong reads."""

    def __init__(
        self,
        *,
        counter: int = 0,
        failure: str | None = None,
        synchronize_initial_reads: bool = False,
    ) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {
            ("USER#student-1", "ACCOUNT_FENCE"): {
                "PK": "USER#student-1",
                "SK": "ACCOUNT_FENCE",
                "status": "active",
                "generation": 1,
            }
        }
        if counter:
            self.items[("USAGE#student-1", "QUESTION#2026-07-21")] = {
                "PK": "USAGE#student-1",
                "SK": "QUESTION#2026-07-21",
                "count": counter,
            }
        self.failure = failure
        self.transactions: list[list[dict[str, object]]] = []
        self._lock = threading.Lock()
        self._read_barrier = (
            threading.Barrier(2) if synchronize_initial_reads else None
        )
        self._initial_command_reads = 0

    def get_item(self, *, Key, ConsistentRead=True):  # noqa: N803
        assert ConsistentRead is True
        key = (Key["PK"], Key["SK"])
        with self._lock:
            item = self.items.get(key)
            snapshot = dict(item) if item is not None else None
            synchronize = (
                self._read_barrier is not None
                and key[1].startswith("QUESTION_SUBMISSION#")
                and self._initial_command_reads < 2
            )
            if synchronize:
                self._initial_command_reads += 1
        if synchronize:
            self._read_barrier.wait(timeout=5)
        return {"Item": snapshot} if snapshot is not None else {}

    def transact_write_items(self, *, TransactItems):  # noqa: N803
        operations = [dict(operation) for operation in TransactItems]
        with self._lock:
            self.transactions.append(operations)
            if self.failure == "before_commit":
                raise TimeoutError("pre-commit-private-provider-canary")
            self._apply(operations)
            if self.failure == "after_commit":
                raise TimeoutError("post-commit-private-provider-canary")
        return {}

    def _apply(self, operations: list[dict[str, object]]) -> None:
        for operation in operations:
            if "ConditionCheck" in operation:
                check = _required_mapping(operation["ConditionCheck"])
                check_key = _required_mapping(check["Key"])
                key = (
                    _required_str(check_key["PK"]),
                    _required_str(check_key["SK"]),
                )
                item = self.items.get(key)
                generation = _required_mapping(
                    check.get("ExpressionAttributeValues", {})
                ).get(
                    ":generation"
                )
                if (
                    item is None
                    or item.get("status") != "active"
                    or (generation is not None and item.get("generation") != generation)
                ):
                    raise _conditional_error()
            elif "Put" in operation:
                put = _required_mapping(operation["Put"])
                item = _required_dict(put["Item"])
                key = (_required_str(item["PK"]), _required_str(item["SK"]))
                if key in self.items:
                    raise _conditional_error()
            elif "Update" in operation:
                update = _required_mapping(operation["Update"])
                update_key = _required_mapping(update["Key"])
                key = (
                    _required_str(update_key["PK"]),
                    _required_str(update_key["SK"]),
                )
                values = _required_mapping(update["ExpressionAttributeValues"])
                current = self.items.get(key)
                expected = values.get(":expected")
                count = _required_int(current.get("count", 0)) if current else 0
                if expected is None and current is not None:
                    raise _conditional_error()
                if expected is not None and count != expected:
                    raise _conditional_error()
                if _required_int(values[":next"]) > _required_int(values[":limit"]):
                    raise _conditional_error()
        for operation in operations:
            if "Put" in operation:
                put = _required_mapping(operation["Put"])
                item = dict(_required_mapping(put["Item"]))
                self.items[(
                    _required_str(item["PK"]),
                    _required_str(item["SK"]),
                )] = item
            elif "Update" in operation:
                update = _required_mapping(operation["Update"])
                update_key = _required_mapping(update["Key"])
                key = (
                    _required_str(update_key["PK"]),
                    _required_str(update_key["SK"]),
                )
                values = _required_mapping(update["ExpressionAttributeValues"])
                item = self.items.setdefault(
                    key, {"PK": key[0], "SK": key[1]}
                )
                item["count"] = values[":next"]
                item["expires_at"] = values[":expires"]
                item["usage_type"] = values[":usage_type"]


def _admit(
    table: _AdmissionTable,
    *,
    fingerprint: str | None = None,
    question: dict[str, object] | None = None,
) -> question_submission_repo.QuestionAdmissionResult:
    return question_submission_repo.admit_question_submission(
        student_id="student-1",
        idempotency_digest=_command_digest(),
        fingerprint=fingerprint or _fingerprint(),
        question=question or _question(),
        usage_event=_usage(),
        quota_period="2026-07-21",
        limit=2,
        expires_at=1784844000,
        created_at="2026-07-21T20:00:00+00:00",
        table=table,
    )


def test_fingerprint_normalizes_subject_but_binds_exact_bytes_and_order() -> None:
    canonical = _fingerprint(attachments=("upload:one", "attachment:two"))
    same = question_submission_repo.question_submission_fingerprint(
        subject="math",
        original_content="Wie löse ich x + 1 = 3?",
        corrected_content=None,
        attachment_identities=("upload:one", "attachment:two"),
    )

    assert canonical == same
    assert canonical != _fingerprint(content="Wie löse ich x + 1 = 4?")
    assert canonical != _fingerprint(
        attachments=("attachment:two", "upload:one")
    )


def test_question_command_digest_is_stable_opaque_and_student_bound() -> None:
    caller_key = "student.private@example.test / Wie loese ich diese Aufgabe?"

    first = question_submission_repo.question_submission_command_digest(
        "student-1", caller_key
    )
    replay = question_submission_repo.question_submission_command_digest(
        "student-1", caller_key
    )
    other_student = question_submission_repo.question_submission_command_digest(
        "student-2", caller_key
    )
    other_key = question_submission_repo.question_submission_command_digest(
        "student-1", caller_key + " edited"
    )

    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert first == replay
    assert first != other_student
    assert first != other_key


def test_arbitrary_caller_key_is_absent_from_every_admission_item() -> None:
    caller_key = "student.private@example.test / Wie loese ich diese Aufgabe?"
    digest = question_submission_repo.question_submission_command_digest(
        "student-1", caller_key
    )
    table = _AdmissionTable()
    usage_event = usage_ledger_service.build_question_usage_event(
        student_id="student-1",
        question_id="question-1",
        quota_period="2026-07-21",
        idempotency_digest=digest,
        counter_key="USAGE#student-1/QUESTION#2026-07-21",
        counter_value=1,
        quantity=1,
        entitlement={
            "effectivePlan": "free_trial",
            "source": "local",
            "limits": {"dailyAiQuestionLimit": 2},
        },
        created_at="2026-07-21T20:00:00+00:00",
    )

    result = question_submission_repo.admit_question_submission(
        student_id="student-1",
        idempotency_digest=digest,
        fingerprint=_fingerprint(),
        question=_question(),
        usage_event=usage_event,
        quota_period="2026-07-21",
        limit=2,
        expires_at=1784844000,
        created_at="2026-07-21T20:00:00+00:00",
        table=table,
    )

    encoded = json.dumps(
        {
            "transactions": table.transactions,
            "items": list(table.items.values()),
            "command": result.command,
            "question": result.question,
        },
        sort_keys=True,
    )
    assert caller_key not in encoded
    assert digest in encoded
    command = table.items[("USER#student-1", f"QUESTION_SUBMISSION#{digest}")]
    assert command["idempotency_digest"] == digest
    assert "idempotency_key" not in command
    ledger = next(
        item
        for item in table.items.values()
        if item.get("entity_type") == "usage_ledger_event"
    )
    assert ledger["idempotency_digest"] == digest
    assert "idempotency_key" not in ledger
    assert {
        command["command_id"],
        ledger["event_id"],
        ledger["idempotency_digest"],
    } == {digest}


def test_repository_rejects_raw_or_legacy_command_identity_without_echo() -> None:
    caller_key = "student.private@example.test / Wie loese ich diese Aufgabe?"
    digest = _command_digest(caller_key=caller_key)

    with pytest.raises(ValueError) as error:
        question_submission_repo.question_submission_command_key(
            "student-1", caller_key
        )

    assert caller_key not in str(error.value)
    legacy = question_submission_repo.classify_question_submission_command(
        {
            "entity_type": "question_submission_command",
            "schema_version": "question-submission-command.v1",
            "command_id": f"student-1:{caller_key}",
            "student_id": "student-1",
            "idempotency_key": caller_key,
            "fingerprint": _fingerprint(),
            "question_id": "question-legacy",
            "status": "processing",
        },
        student_id="student-1",
        idempotency_digest=digest,
        fingerprint=_fingerprint(),
    )
    assert legacy is not None
    assert legacy.disposition is question_submission_repo.QuestionAdmissionDisposition.RETRYABLE
    assert legacy.command is None
    assert caller_key not in repr(legacy)


def test_transaction_has_one_counter_update_and_no_duplicate_targets() -> None:
    account_fence = attachment_repo.TransactionOperation(
        attachment_repo.TransactionOperationKind.ACCOUNT_RETENTION_FENCE_CHECK,
        {
            "ConditionCheck": {
                "Key": {"PK": "USER#student-1", "SK": "ACCOUNT_FENCE"},
                "ConditionExpression": "#status=:active",
            }
        },
    )
    duplicate_question = attachment_repo.TransactionOperation(
        attachment_repo.TransactionOperationKind.QUESTION_PUT,
        {"Put": {"Item": {"PK": "QUESTION#question-1", "SK": "META"}}},
    )
    association = attachment_repo.TransactionOperation(
        attachment_repo.TransactionOperationKind.ASSOCIATION_PUT,
        {
            "Put": {
                "Item": {
                    "PK": "ATTACHMENT#attachment-1",
                    "SK": "REF#QUESTION#question-1",
                }
            }
        },
    )
    command: dict[str, object] = {
        "idempotency_digest": _command_digest(),
        "entity_type": "question_submission_command",
        "schema_version": "question-submission-command.v2",
        "command_id": _command_digest(),
    }

    operations = question_submission_repo.build_question_admission_transaction(
        command=command,
        question=_question(),
        usage_event=_usage(),
        student_id="student-1",
        quota_period="2026-07-21",
        expected_counter=0,
        limit=2,
        expires_at=1784844000,
        account_fence_generation=1,
        attachment_operations=(account_fence, duplicate_question, association),
    )

    targets = [
        question_submission_repo._operation_key(operation)  # noqa: SLF001
        for operation in operations
    ]
    assert len(targets) == len(set(targets))
    assert sum("Update" in operation for operation in operations) == 1
    counter = _required_mapping(
        next(operation["Update"] for operation in operations if "Update" in operation)
    )
    assert counter["ConditionExpression"] == (
        "(attribute_not_exists(#count) OR #count=:expected) AND :next<=:limit"
    )
    assert _required_mapping(counter["ExpressionAttributeValues"])[":expected"] == 0
    assert ("ATTACHMENT#attachment-1", "REF#QUESTION#question-1") in targets


def test_concurrent_identical_keys_commit_one_complete_admission() -> None:
    table = _AdmissionTable(synchronize_initial_reads=True)
    results: list[question_submission_repo.QuestionAdmissionResult] = []

    def run() -> None:
        results.append(_admit(table))

    workers = [threading.Thread(target=run), threading.Thread(target=run)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)
        assert not worker.is_alive()

    assert {result.disposition for result in results} == {
        question_submission_repo.QuestionAdmissionDisposition.ADMITTED,
        question_submission_repo.QuestionAdmissionDisposition.RESUME,
    }
    entity_types = [item.get("entity_type") for item in table.items.values()]
    assert entity_types.count("question_submission_command") == 1
    assert entity_types.count("usage_ledger_event") == 1
    assert sum(key[0].startswith("QUESTION#") for key in table.items) == 1
    assert table.items[("USAGE#student-1", "QUESTION#2026-07-21")]["count"] == 1


def test_changed_payload_is_mismatch_before_another_mutation() -> None:
    table = _AdmissionTable()
    assert _admit(table).disposition is question_submission_repo.QuestionAdmissionDisposition.ADMITTED
    transaction_count = len(table.transactions)

    result = _admit(
        table,
        fingerprint=_fingerprint(content="Geänderter Inhalt"),
        question=_question(content="Geänderter Inhalt", original_content="Geänderter Inhalt"),
    )

    assert result.disposition is question_submission_repo.QuestionAdmissionDisposition.PAYLOAD_MISMATCH
    assert len(table.transactions) == transaction_count
    assert table.items[("QUESTION#question-1", "META")]["content"] == "Wie löse ich x + 1 = 3?"


def test_commit_then_timeout_reconciles_to_resume() -> None:
    table = _AdmissionTable(failure="after_commit")

    result = _admit(table)

    assert result.disposition is question_submission_repo.QuestionAdmissionDisposition.RESUME
    assert result.command is not None
    assert result.command["status"] == "processing"
    assert len(table.transactions) == 1


def test_precommit_dependency_failure_is_retryable_without_partial_state() -> None:
    table = _AdmissionTable(failure="before_commit")

    result = _admit(table)

    assert result.disposition is question_submission_repo.QuestionAdmissionDisposition.RETRYABLE
    assert ("QUESTION#question-1", "META") not in table.items
    assert ("USAGE#student-1", "QUESTION#2026-07-21") not in table.items


def test_full_quota_is_durable_and_counter_is_unchanged() -> None:
    table = _AdmissionTable(counter=2)

    result = _admit(table)

    assert result.disposition is question_submission_repo.QuestionAdmissionDisposition.QUOTA_EXCEEDED
    assert result.counter_value == 2
    assert table.items[("USAGE#student-1", "QUESTION#2026-07-21")]["count"] == 2
    assert table.transactions == []


def test_question_usage_builder_contains_no_private_content_or_coordinates() -> None:
    event = _usage()
    encoded = json.dumps(event, sort_keys=True)
    private_values = (
        "private question canary",
        "s3://private-coordinate-canary",
    )

    metadata = _required_mapping(event["metadata"])
    privacy = _required_mapping(event["privacy"])
    assert metadata["write_order"] == "question_admission_transaction"
    assert privacy["raw_content_stored"] is False
    for forbidden_key in (
        "original_content",
        "corrected_text",
        "ocr_text",
        "provider_payload",
        "immutable_object_key",
    ):
        assert forbidden_key not in event
        assert forbidden_key not in metadata
    for private_value in private_values:
        assert private_value not in encoded
