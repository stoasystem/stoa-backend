"""Atomic admission boundary for quota-governed question submissions."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo, attachment_repo, question_repo


type QuestionAdmissionItem = dict[str, object]

_COMMAND_SCHEMA_VERSION = "question-submission-command.v1"
_FINGERPRINT_DOMAIN = b"stoa.question.submission.v1"
_RECONCILIATION_DIGEST_DOMAIN = "stoa.question.reconciliation.v1"
_REVERSAL_ID_DOMAIN = b"stoa.question.reversal.v1"
_MAX_ADMISSION_ATTEMPTS = 4


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


class QuestionAdmissionDisposition(StrEnum):
    """Closed, coordinate-free outcomes from the admission boundary."""

    ADMITTED = "admitted"
    RESUME = "resume"
    PAYLOAD_MISMATCH = "payload_mismatch"
    QUOTA_EXCEEDED = "quota_exceeded"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class QuestionAdmissionResult:
    disposition: QuestionAdmissionDisposition
    command: QuestionAdmissionItem | None = None
    question: QuestionAdmissionItem | None = None
    counter_value: int | None = None
    operations: tuple[QuestionAdmissionItem, ...] = ()


class QuestionReconciliationDisposition(StrEnum):
    """Closed outcomes for one bounded question-submission coordinate."""

    COMMITTED = "committed"
    RECOVERABLE_PROCESSING = "recoverable_processing"
    LEGACY_PARTIAL = "legacy_counter_ledger_without_question"
    TERMINAL_FAILURE = "proven_terminal_failure"
    CONFLICTING = "conflicting_evidence"
    CHANGED = "changed_after_preview"
    RETRYABLE = "retryable_dependency"


@dataclass(frozen=True, slots=True)
class QuestionReconciliationPreview:
    """Coordinate-free, version-bound reconciliation proposal."""

    disposition: QuestionReconciliationDisposition
    command_id: str
    question_id: str | None
    observed_command_version: int | None
    observed_question_version: int | None
    observed_digest: str
    proposed_action: str
    mutation_count: int = 0


@dataclass(frozen=True, slots=True)
class QuestionReconciliationCoordinate:
    """One explicit bounded lookup; no table-wide discovery is permitted."""

    student_id: str
    idempotency_key: str
    question_id: str | None = None
    quota_period: str | None = None


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    return value


def _positive_integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} is invalid")
    return value


def _string_mapping(value: object) -> QuestionAdmissionItem:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError("question admission dependency unavailable")
    return {str(key): member for key, member in value.items()}


def _normalized_subject(subject: str) -> str:
    value = subject.strip().lower()
    aliases = {
        "mathematics": "math",
        "mathematik": "math",
        "deutsch": "german",
        "englisch": "english",
    }
    value = aliases.get(value, value)
    if value not in {"math", "physics", "german", "english"}:
        raise ValueError("unsupported question subject")
    return value


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def question_submission_fingerprint(
    *,
    subject: str,
    original_content: str,
    corrected_content: str | None,
    attachment_identities: Sequence[str] | None = None,
) -> str:
    """Hash exact question bytes and ordered opaque attachment identities."""
    framed = bytearray(_FINGERPRINT_DOMAIN)
    framed.extend(_frame(_normalized_subject(subject)))
    framed.extend(_frame(_required_text(original_content, "original_content")))
    if corrected_content is None:
        framed.extend(b"\x00")
    else:
        framed.extend(b"\x01")
        framed.extend(_frame(_required_text(corrected_content, "corrected_content")))
    identities = tuple(attachment_identities or ())
    framed.extend(struct.pack(">I", len(identities)))
    for identity in identities:
        framed.extend(_frame(_required_text(identity, "attachment_identity")))
    return hashlib.sha256(bytes(framed)).hexdigest()


def question_submission_command_key(
    student_id: str, idempotency_key: str
) -> QuestionAdmissionItem:
    return {
        "PK": f"USER#{_required_text(student_id, 'student_id')}",
        "SK": f"QUESTION_SUBMISSION#{_required_text(idempotency_key, 'idempotency_key')}",
    }


def question_counter_key(student_id: str, quota_period: str) -> QuestionAdmissionItem:
    return {
        "PK": f"USAGE#{_required_text(student_id, 'student_id')}",
        "SK": f"QUESTION#{_required_text(quota_period, 'quota_period')}",
    }


def get_question_submission_command(
    student_id: str,
    idempotency_key: str,
    *,
    table: object | None = None,
) -> QuestionAdmissionItem | None:
    """Strongly read one durable question-submission command."""
    target = table or get_table()
    if not isinstance(target, _GetTable):
        raise ValueError("question admission dependency unavailable")
    response = _string_mapping(
        target.get_item(
            Key=question_submission_command_key(student_id, idempotency_key),
            ConsistentRead=True,
        )
    )
    item = response.get("Item")
    return None if item is None else _string_mapping(item)


def _classify_command(
    command: QuestionAdmissionItem | None,
    *,
    student_id: str,
    idempotency_key: str,
    fingerprint: str,
) -> QuestionAdmissionResult | None:
    if command is None:
        return None
    if command.get("student_id") != student_id:
        return QuestionAdmissionResult(QuestionAdmissionDisposition.RETRYABLE)
    if command.get("idempotency_key") != idempotency_key:
        return QuestionAdmissionResult(QuestionAdmissionDisposition.RETRYABLE)
    if command.get("fingerprint") != fingerprint:
        return QuestionAdmissionResult(
            QuestionAdmissionDisposition.PAYLOAD_MISMATCH,
            command=dict(command),
        )
    if (
        command.get("entity_type") != "question_submission_command"
        or command.get("schema_version") != _COMMAND_SCHEMA_VERSION
        or command.get("status") not in {"processing", "completed", "terminal_failed"}
        or not isinstance(command.get("question_id"), str)
        or not command["question_id"]
    ):
        return QuestionAdmissionResult(
            QuestionAdmissionDisposition.RETRYABLE,
            command=dict(command),
        )
    counter_value = command.get("counter_value")
    return QuestionAdmissionResult(
        QuestionAdmissionDisposition.RESUME,
        command=dict(command),
        counter_value=(
            counter_value
            if isinstance(counter_value, int) and not isinstance(counter_value, bool)
            else None
        ),
    )


def _operation_item(operation: object) -> QuestionAdmissionItem:
    if isinstance(operation, attachment_repo.TransactionOperation):
        return dict(operation.item)
    return _string_mapping(operation)


def _operation_key(operation: QuestionAdmissionItem) -> tuple[str, str] | None:
    if len(operation) != 1:
        raise ValueError("invalid transaction operation")
    body = _string_mapping(next(iter(operation.values())))
    raw_key = body.get("Key")
    if raw_key is None and "Item" in body:
        item = _string_mapping(body["Item"])
        raw_key = {"PK": item.get("PK"), "SK": item.get("SK")}
    if raw_key is None:
        return None
    key = _string_mapping(raw_key)
    pk = _required_text(key.get("PK"), "transaction PK")
    sk = _required_text(key.get("SK"), "transaction SK")
    return pk, sk


def build_question_admission_transaction(
    *,
    command: QuestionAdmissionItem,
    question: QuestionAdmissionItem,
    usage_event: QuestionAdmissionItem,
    student_id: str,
    quota_period: str,
    expected_counter: int,
    limit: int,
    expires_at: int,
    account_fence_generation: int,
    attachment_operations: Sequence[object] = (),
) -> list[QuestionAdmissionItem]:
    """Build one capped transaction without duplicate item targets."""
    expected_counter = _positive_integer(expected_counter, "expected_counter")
    limit = _positive_integer(limit, "limit", minimum=1)
    expires_at = _positive_integer(expires_at, "expires_at", minimum=1)
    generation = _positive_integer(
        account_fence_generation, "account_fence_generation", minimum=1
    )
    if expected_counter >= limit:
        raise ValueError("question quota is already exhausted")
    next_counter = expected_counter + 1
    question_id = _required_text(question.get("question_id"), "question_id")
    if question.get("student_id") != student_id:
        raise ValueError("question owner mismatch")
    command_item = {
        **question_submission_command_key(student_id, str(command["idempotency_key"])),
        **command,
        "student_id": student_id,
        "account_fence_generation": generation,
        "counter_value": next_counter,
        "quota_period": quota_period,
    }
    question_item = question_repo.question_item(
        {
            **question,
            "account_fence_generation": generation,
        }
    )
    usage_item = {
        **usage_event,
        "owner_id": student_id,
        "student_id": student_id,
        "account_fence_generation": generation,
        "counter_value_after": next_counter,
    }
    expected_exists = expected_counter > 0
    counter_condition = (
        "#count=:expected AND #count<:limit"
        if expected_exists
        else "attribute_not_exists(#count) AND :next<=:limit"
    )
    counter_values: QuestionAdmissionItem = {
        ":next": next_counter,
        ":limit": limit,
        ":expires": expires_at,
        ":usage_type": "daily_question_submission",
    }
    if expected_exists:
        counter_values[":expected"] = expected_counter
    operations: list[QuestionAdmissionItem] = [
        account_deletion_repo.active_fence_condition(student_id, generation),
        {
            "Put": {
                "Item": command_item,
                "ConditionExpression": (
                    "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                ),
            }
        },
        {
            "Update": {
                "Key": question_counter_key(student_id, quota_period),
                "UpdateExpression": (
                    "SET #count=:next, #ttl=if_not_exists(#ttl,:expires), "
                    "usage_type=if_not_exists(usage_type,:usage_type)"
                ),
                "ConditionExpression": counter_condition,
                "ExpressionAttributeNames": {"#count": "count", "#ttl": "expires_at"},
                "ExpressionAttributeValues": counter_values,
            }
        },
        {
            "Put": {
                "Item": usage_item,
                "ConditionExpression": (
                    "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                ),
            }
        },
        {
            "Put": {
                "Item": question_item,
                "ConditionExpression": (
                    "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                ),
            }
        },
    ]
    base_keys = {key for operation in operations if (key := _operation_key(operation))}
    account_fence_key = _operation_key(operations[0])
    question_key = (f"QUESTION#{question_id}", "META")
    for described in attachment_operations:
        operation = _operation_item(described)
        key = _operation_key(operation)
        if key in {account_fence_key, question_key}:
            continue
        if key is not None and key in base_keys:
            raise ValueError("transaction targets the same item twice")
        operations.append(operation)
        if key is not None:
            base_keys.add(key)
    return operations


def _counter_value(
    student_id: str, quota_period: str, *, table: object
) -> int:
    if not isinstance(table, _GetTable):
        raise ValueError("question admission dependency unavailable")
    response = _string_mapping(
        table.get_item(
            Key=question_counter_key(student_id, quota_period),
            ConsistentRead=True,
        )
    )
    item = response.get("Item")
    if item is None:
        return 0
    count = _string_mapping(item).get("count", 0)
    return _positive_integer(count, "question counter")


def _safe_reread(
    *,
    student_id: str,
    idempotency_key: str,
    fingerprint: str,
    table: object,
) -> QuestionAdmissionResult | None:
    try:
        command = get_question_submission_command(
            student_id, idempotency_key, table=table
        )
    except Exception:
        return QuestionAdmissionResult(QuestionAdmissionDisposition.RETRYABLE)
    return _classify_command(
        command,
        student_id=student_id,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )


def _optional_positive_version(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _read_item(target: object, key: QuestionAdmissionItem) -> QuestionAdmissionItem | None:
    if not isinstance(target, _GetTable):
        raise ValueError("question reconciliation dependency unavailable")
    response = _string_mapping(target.get_item(Key=key, ConsistentRead=True))
    item = response.get("Item")
    return None if item is None else _string_mapping(item)


def _usage_event_key(
    student_id: str, quota_period: str, idempotency_key: str
) -> QuestionAdmissionItem:
    return {
        "PK": f"USAGE_LEDGER#{student_id}",
        "SK": f"EVENT#question_submission#{quota_period}#{idempotency_key}",
    }


def _reconciliation_digest(facts: Mapping[str, object]) -> str:
    body = json.dumps(
        {"domain": _RECONCILIATION_DIGEST_DOMAIN, **facts},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _row_digest(item: Mapping[str, object] | None) -> str | None:
    if item is None:
        return None
    encoded = json.dumps(
        item,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reversal_identity(command_id: str, fingerprint: str) -> str:
    return hashlib.sha256(
        _REVERSAL_ID_DOMAIN + _frame(command_id) + _frame(fingerprint)
    ).hexdigest()


def _question_has_durable_result(question: Mapping[str, object]) -> bool:
    status = str(question.get("status") or "")
    return status not in {"", "pending", "submission_failed"} or isinstance(
        question.get("ai_response"), Mapping
    )


def _preview_result(
    *,
    disposition: QuestionReconciliationDisposition,
    command_id: str,
    question_id: str | None,
    command_version: int | None,
    question_version: int | None,
    proposed_action: str,
    facts: Mapping[str, object],
) -> QuestionReconciliationPreview:
    return QuestionReconciliationPreview(
        disposition=disposition,
        command_id=command_id,
        question_id=question_id,
        observed_command_version=command_version,
        observed_question_version=question_version,
        observed_digest=_reconciliation_digest(facts),
        proposed_action=proposed_action,
    )


def preview_question_submission_reconciliation(
    *,
    student_id: str,
    idempotency_key: str,
    question_id: str | None = None,
    quota_period: str | None = None,
    table: object | None = None,
) -> QuestionReconciliationPreview:
    """Strongly inspect exactly one command/ledger coordinate without writes."""
    target = table or get_table()
    student_id = _required_text(student_id, "student_id")
    idempotency_key = _required_text(idempotency_key, "idempotency_key")
    command_id = f"{student_id}:{idempotency_key}"
    try:
        command = _read_item(
            target, question_submission_command_key(student_id, idempotency_key)
        )
        effective_question_id = (
            str(command.get("question_id") or "") if command else str(question_id or "")
        )
        effective_period = (
            str(command.get("quota_period") or "") if command else str(quota_period or "")
        )
        question = (
            _read_item(
                target, {"PK": f"QUESTION#{effective_question_id}", "SK": "META"}
            )
            if effective_question_id
            else None
        )
        ledger = (
            _read_item(
                target,
                _usage_event_key(student_id, effective_period, idempotency_key),
            )
            if effective_period
            else None
        )
        counter = (
            _read_item(target, question_counter_key(student_id, effective_period))
            if effective_period
            else None
        )
    except Exception:
        return _preview_result(
            disposition=QuestionReconciliationDisposition.RETRYABLE,
            command_id=command_id,
            question_id=question_id,
            command_version=None,
            question_version=None,
            proposed_action="retry_same_coordinate",
            facts={"dependency": "unavailable"},
        )

    command_version = _optional_positive_version(
        command.get("version") if command else None
    )
    question_version = _optional_positive_version(
        question.get("version") if question else None
    )
    facts: dict[str, object] = {
        "command_present": command is not None,
        "command_status": command.get("status") if command else None,
        "command_version": command_version,
        "fingerprint": command.get("fingerprint") if command else None,
        "question_id": effective_question_id or None,
        "question_present": question is not None,
        "question_status": question.get("status") if question else None,
        "question_version": question_version,
        "durable_result": bool(question and _question_has_durable_result(question)),
        "quota_period": effective_period or None,
        "ledger_present": ledger is not None,
        "ledger_status": ledger.get("status") if ledger else None,
        "ledger_identity": ledger.get("event_id") if ledger else None,
        "counter_present": counter is not None,
        "counter_count": counter.get("count") if counter else None,
        "command_row_digest": _row_digest(command),
        "question_row_digest": _row_digest(question),
        "ledger_row_digest": _row_digest(ledger),
        "counter_row_digest": _row_digest(counter),
    }

    if command is None:
        disposition = (
            QuestionReconciliationDisposition.LEGACY_PARTIAL
            if ledger is not None and counter is not None and question is None
            else QuestionReconciliationDisposition.CONFLICTING
        )
        return _preview_result(
            disposition=disposition,
            command_id=command_id,
            question_id=effective_question_id or None,
            command_version=None,
            question_version=question_version,
            proposed_action="report_only",
            facts=facts,
        )

    expected_ledger_identity = command.get("ledger_identity")
    conflicting = (
        command.get("entity_type") != "question_submission_command"
        or command.get("schema_version") != _COMMAND_SCHEMA_VERSION
        or command.get("student_id") != student_id
        or command.get("idempotency_key") != idempotency_key
        or command.get("command_id") != command_id
        or command_version is None
        or not effective_question_id
        or not effective_period
        or question is None
        or question.get("student_id") != student_id
        or question.get("question_id") != effective_question_id
        or ledger is None
        or ledger.get("student_id") != student_id
        or ledger.get("question_id") != effective_question_id
        or ledger.get("event_id") != expected_ledger_identity
        or counter is None
        or isinstance(counter.get("count"), bool)
        or not isinstance(counter.get("count"), int)
    )
    if conflicting:
        return _preview_result(
            disposition=QuestionReconciliationDisposition.CONFLICTING,
            command_id=command_id,
            question_id=effective_question_id or None,
            command_version=command_version,
            question_version=question_version,
            proposed_action="report_only",
            facts=facts,
        )

    assert question is not None
    assert ledger is not None
    assert counter is not None
    counter_count = counter.get("count")
    assert isinstance(counter_count, int) and not isinstance(counter_count, bool)
    command_status = str(command.get("status") or "")
    ledger_status = str(ledger.get("status") or "active")
    if command_status == "completed":
        disposition = QuestionReconciliationDisposition.COMMITTED
        action = "none"
    elif command_status == "processing":
        disposition = QuestionReconciliationDisposition.RECOVERABLE_PROCESSING
        action = (
            "mark_command_completed"
            if _question_has_durable_result(question)
            else "resume_processing"
        )
    elif (
        command_status == "terminal_failed"
        and isinstance(command.get("terminal_failure_code"), str)
        and bool(command.get("terminal_failure_code"))
        and isinstance(command.get("terminal_failure_proven_at"), str)
        and bool(command.get("terminal_failure_proven_at"))
        and ledger_status != "reversed"
        and counter_count > 0
    ):
        disposition = QuestionReconciliationDisposition.TERMINAL_FAILURE
        action = "reverse_question_admission"
    elif (
        command_status == "terminal_failed"
        and ledger_status == "reversed"
        and isinstance(command.get("reversal_id"), str)
        and bool(command.get("reversal_id"))
        and question.get("status") == "submission_failed"
    ):
        disposition = QuestionReconciliationDisposition.COMMITTED
        action = "none"
    else:
        disposition = QuestionReconciliationDisposition.CONFLICTING
        action = "report_only"
    return _preview_result(
        disposition=disposition,
        command_id=command_id,
        question_id=effective_question_id,
        command_version=command_version,
        question_version=question_version,
        proposed_action=action,
        facts=facts,
    )


def _condition_for_version(
    observed: int | None,
) -> tuple[str, dict[str, object]]:
    if observed is None:
        return "attribute_not_exists(#version)", {}
    return "#version=:question_version", {":question_version": observed}


def reverse_terminal_question_admission(
    preview: QuestionReconciliationPreview,
    *,
    student_id: str,
    idempotency_key: str,
    reversed_at: str,
    table: object | None = None,
) -> QuestionReconciliationPreview:
    """Atomically reverse one proven terminal admission, excluding attachments."""
    target = table or get_table()
    current = preview_question_submission_reconciliation(
        student_id=student_id,
        idempotency_key=idempotency_key,
        table=target,
    )
    if current.observed_digest != preview.observed_digest:
        return QuestionReconciliationPreview(
            disposition=QuestionReconciliationDisposition.CHANGED,
            command_id=current.command_id,
            question_id=current.question_id,
            observed_command_version=current.observed_command_version,
            observed_question_version=current.observed_question_version,
            observed_digest=current.observed_digest,
            proposed_action="report_changed",
        )
    if (
        current.disposition is not QuestionReconciliationDisposition.TERMINAL_FAILURE
        or current.question_id is None
        or current.observed_command_version is None
    ):
        return current
    command = _read_item(
        target, question_submission_command_key(student_id, idempotency_key)
    )
    if command is None:
        return current
    quota_period = _required_text(command.get("quota_period"), "quota_period")
    fingerprint = _required_text(command.get("fingerprint"), "fingerprint")
    ledger_identity = _required_text(command.get("ledger_identity"), "ledger_identity")
    counter = _read_item(target, question_counter_key(student_id, quota_period))
    if counter is None:
        return current
    expected_count = _positive_integer(counter.get("count"), "counter count", minimum=1)
    reversal_id = _reversal_identity(current.command_id, fingerprint)
    version_condition, question_version_values = _condition_for_version(
        current.observed_question_version
    )
    operations: list[QuestionAdmissionItem] = [
        {
            "Update": {
                "Key": question_submission_command_key(student_id, idempotency_key),
                "UpdateExpression": (
                    "SET reversal_id=:reversal, reversed_at=:reversed_at, "
                    "updated_at=:reversed_at, #version=:next_version"
                ),
                "ConditionExpression": (
                    "#status=:terminal AND #version=:version AND fingerprint=:fingerprint "
                    "AND terminal_failure_proven_at=:proven_at "
                    "AND attribute_not_exists(reversal_id)"
                ),
                "ExpressionAttributeNames": {
                    "#status": "status",
                    "#version": "version",
                },
                "ExpressionAttributeValues": {
                    ":terminal": "terminal_failed",
                    ":version": current.observed_command_version,
                    ":next_version": current.observed_command_version + 1,
                    ":fingerprint": fingerprint,
                    ":proven_at": command["terminal_failure_proven_at"],
                    ":reversal": reversal_id,
                    ":reversed_at": _required_text(reversed_at, "reversed_at"),
                },
            }
        },
        {
            "Update": {
                "Key": {"PK": f"QUESTION#{current.question_id}", "SK": "META"},
                "UpdateExpression": (
                    "SET #status=:failed, failure_code=:failure_code, "
                    "failed_at=:reversed_at, #version=if_not_exists(#version,:zero)+:one"
                ),
                "ConditionExpression": (
                    "student_id=:student AND question_id=:question AND "
                    "#status<>:failed AND " + version_condition
                ),
                "ExpressionAttributeNames": {
                    "#status": "status",
                    "#version": "version",
                },
                "ExpressionAttributeValues": {
                    ":student": student_id,
                    ":question": current.question_id,
                    ":failed": "submission_failed",
                    ":failure_code": command["terminal_failure_code"],
                    ":reversed_at": reversed_at,
                    ":zero": 0,
                    ":one": 1,
                    **question_version_values,
                },
            }
        },
        {
            "Update": {
                "Key": question_counter_key(student_id, quota_period),
                "UpdateExpression": "SET #count=#count-:one",
                "ConditionExpression": "#count=:expected AND #count>=:one",
                "ExpressionAttributeNames": {"#count": "count"},
                "ExpressionAttributeValues": {
                    ":expected": expected_count,
                    ":one": 1,
                },
            }
        },
        {
            "Update": {
                "Key": _usage_event_key(student_id, quota_period, idempotency_key),
                "UpdateExpression": (
                    "SET #status=:reversed, reversal_id=:reversal, "
                    "reversed_at=:reversed_at, updated_at=:reversed_at"
                ),
                "ConditionExpression": (
                    "event_id=:ledger AND question_id=:question "
                    "AND (attribute_not_exists(#status) OR #status=:active) "
                    "AND attribute_not_exists(reversal_id)"
                ),
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":ledger": ledger_identity,
                    ":question": current.question_id,
                    ":active": "active",
                    ":reversed": "reversed",
                    ":reversal": reversal_id,
                    ":reversed_at": reversed_at,
                },
            }
        },
    ]
    try:
        attachment_repo.transact(operations, table=target)
    except Exception:
        refreshed = preview_question_submission_reconciliation(
            student_id=student_id,
            idempotency_key=idempotency_key,
            table=target,
        )
        if refreshed.disposition is QuestionReconciliationDisposition.COMMITTED:
            return refreshed
        return QuestionReconciliationPreview(
            disposition=QuestionReconciliationDisposition.CHANGED,
            command_id=refreshed.command_id,
            question_id=refreshed.question_id,
            observed_command_version=refreshed.observed_command_version,
            observed_question_version=refreshed.observed_question_version,
            observed_digest=refreshed.observed_digest,
            proposed_action="report_changed",
        )
    refreshed = preview_question_submission_reconciliation(
        student_id=student_id,
        idempotency_key=idempotency_key,
        table=target,
    )
    return QuestionReconciliationPreview(
        disposition=refreshed.disposition,
        command_id=refreshed.command_id,
        question_id=refreshed.question_id,
        observed_command_version=refreshed.observed_command_version,
        observed_question_version=refreshed.observed_question_version,
        observed_digest=refreshed.observed_digest,
        proposed_action=refreshed.proposed_action,
        mutation_count=len(operations),
    )


def apply_question_submission_reconciliation(
    preview: QuestionReconciliationPreview,
    *,
    student_id: str,
    idempotency_key: str,
    applied_at: str,
    table: object | None = None,
) -> QuestionReconciliationPreview:
    """Apply only the still-current proposal represented by ``preview``."""
    target = table or get_table()
    current = preview_question_submission_reconciliation(
        student_id=student_id,
        idempotency_key=idempotency_key,
        table=target,
    )
    if current.observed_digest != preview.observed_digest:
        return QuestionReconciliationPreview(
            disposition=QuestionReconciliationDisposition.CHANGED,
            command_id=current.command_id,
            question_id=current.question_id,
            observed_command_version=current.observed_command_version,
            observed_question_version=current.observed_question_version,
            observed_digest=current.observed_digest,
            proposed_action="report_changed",
        )
    if current.disposition is QuestionReconciliationDisposition.TERMINAL_FAILURE:
        return reverse_terminal_question_admission(
            current,
            student_id=student_id,
            idempotency_key=idempotency_key,
            reversed_at=applied_at,
            table=target,
        )
    if current.proposed_action != "mark_command_completed":
        return current
    if current.observed_command_version is None or current.question_id is None:
        return current
    question = _read_item(
        target, {"PK": f"QUESTION#{current.question_id}", "SK": "META"}
    )
    if question is None:
        return current
    version_condition, question_version_values = _condition_for_version(
        current.observed_question_version
    )
    result_condition = "attribute_exists(ai_response)" if isinstance(
        question.get("ai_response"), Mapping
    ) else "#question_status=:question_status"
    question_values: QuestionAdmissionItem = {
        ":student": student_id,
        ":question": current.question_id,
        **question_version_values,
    }
    if result_condition.startswith("#question_status"):
        question_values[":question_status"] = question.get("status")
    question_names = {"#version": "version"}
    if result_condition.startswith("#question_status"):
        question_names["#question_status"] = "status"
    operation: QuestionAdmissionItem = {
        "Update": {
            "Key": question_submission_command_key(student_id, idempotency_key),
            "UpdateExpression": (
                "SET #status=:completed, completed_at=:applied_at, "
                "updated_at=:applied_at, #version=:next_version"
            ),
            "ConditionExpression": (
                "#status=:processing AND #version=:version "
                "AND question_id=:question"
            ),
            "ExpressionAttributeNames": {
                "#status": "status",
                "#version": "version",
            },
            "ExpressionAttributeValues": {
                ":processing": "processing",
                ":completed": "completed",
                ":version": current.observed_command_version,
                ":next_version": current.observed_command_version + 1,
                ":question": current.question_id,
                ":applied_at": _required_text(applied_at, "applied_at"),
            },
        }
    }
    result_check: QuestionAdmissionItem = {
        "ConditionCheck": {
            "Key": {"PK": f"QUESTION#{current.question_id}", "SK": "META"},
            "ConditionExpression": (
                "student_id=:student AND question_id=:question AND "
                + result_condition
                + " AND "
                + version_condition
            ),
            "ExpressionAttributeNames": question_names,
            "ExpressionAttributeValues": question_values,
        }
    }
    try:
        attachment_repo.transact([result_check, operation], table=target)
    except Exception:
        changed = preview_question_submission_reconciliation(
            student_id=student_id,
            idempotency_key=idempotency_key,
            table=target,
        )
        return QuestionReconciliationPreview(
            disposition=QuestionReconciliationDisposition.CHANGED,
            command_id=changed.command_id,
            question_id=changed.question_id,
            observed_command_version=changed.observed_command_version,
            observed_question_version=changed.observed_question_version,
            observed_digest=changed.observed_digest,
            proposed_action="report_changed",
        )
    refreshed = preview_question_submission_reconciliation(
        student_id=student_id,
        idempotency_key=idempotency_key,
        table=target,
    )
    return QuestionReconciliationPreview(
        disposition=refreshed.disposition,
        command_id=refreshed.command_id,
        question_id=refreshed.question_id,
        observed_command_version=refreshed.observed_command_version,
        observed_question_version=refreshed.observed_question_version,
        observed_digest=refreshed.observed_digest,
        proposed_action=refreshed.proposed_action,
        mutation_count=1,
    )


def admit_question_submission(
    *,
    student_id: str,
    idempotency_key: str,
    fingerprint: str,
    question: QuestionAdmissionItem,
    usage_event: QuestionAdmissionItem,
    quota_period: str,
    limit: int,
    expires_at: int,
    attachment_identities: Sequence[str] = (),
    attachment_operations: Sequence[object] = (),
    created_at: str,
    table: object | None = None,
) -> QuestionAdmissionResult:
    """Admit one exact submission or replay the durable original command."""
    target = table or get_table()
    student_id = _required_text(student_id, "student_id")
    idempotency_key = _required_text(idempotency_key, "idempotency_key")
    fingerprint = _required_text(fingerprint, "fingerprint")
    quota_period = _required_text(quota_period, "quota_period")
    created_at = _required_text(created_at, "created_at")
    limit = _positive_integer(limit, "limit", minimum=1)
    question_id = _required_text(question.get("question_id"), "question_id")
    initial = _safe_reread(
        student_id=student_id,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        table=target,
    )
    if initial is not None:
        return initial
    try:
        fence = account_deletion_repo.require_active_account_fence(
            student_id, table=target
        )
        generation = _positive_integer(
            fence.get("generation"), "account_fence_generation", minimum=1
        )
    except Exception:
        return QuestionAdmissionResult(QuestionAdmissionDisposition.RETRYABLE)

    for _ in range(_MAX_ADMISSION_ATTEMPTS):
        try:
            expected_counter = _counter_value(
                student_id, quota_period, table=target
            )
        except Exception:
            return QuestionAdmissionResult(QuestionAdmissionDisposition.RETRYABLE)
        if expected_counter >= limit:
            replay = _safe_reread(
                student_id=student_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                table=target,
            )
            if replay is not None:
                return replay
            return QuestionAdmissionResult(
                QuestionAdmissionDisposition.QUOTA_EXCEEDED,
                counter_value=expected_counter,
            )
        next_counter = expected_counter + 1
        command: QuestionAdmissionItem = {
            "entity_type": "question_submission_command",
            "schema_version": _COMMAND_SCHEMA_VERSION,
            "command_id": f"{student_id}:{idempotency_key}",
            "student_id": student_id,
            "idempotency_key": idempotency_key,
            "fingerprint": fingerprint,
            "question_id": question_id,
            "quota_period": quota_period,
            "counter_value": next_counter,
            "ledger_identity": _required_text(usage_event.get("event_id"), "ledger_identity"),
            "attachment_identities": list(attachment_identities),
            "created_at": created_at,
            "updated_at": created_at,
            "status": "processing",
            "version": 1,
        }
        operations = build_question_admission_transaction(
            command=command,
            question=question,
            usage_event=usage_event,
            student_id=student_id,
            quota_period=quota_period,
            expected_counter=expected_counter,
            limit=limit,
            expires_at=expires_at,
            account_fence_generation=generation,
            attachment_operations=attachment_operations,
        )
        try:
            attachment_repo.transact(operations, table=target)
        except Exception:
            replay = _safe_reread(
                student_id=student_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                table=target,
            )
            if replay is not None:
                return replay
            continue
        persisted_command = {
            **question_submission_command_key(student_id, idempotency_key),
            **command,
            "student_id": student_id,
            "account_fence_generation": generation,
            "counter_value": next_counter,
            "quota_period": quota_period,
        }
        return QuestionAdmissionResult(
            QuestionAdmissionDisposition.ADMITTED,
            command=persisted_command,
            question=dict(question),
            counter_value=next_counter,
            operations=tuple(operations),
        )
    return QuestionAdmissionResult(QuestionAdmissionDisposition.RETRYABLE)
