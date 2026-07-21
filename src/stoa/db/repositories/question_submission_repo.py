"""Atomic admission boundary for quota-governed question submissions."""

from __future__ import annotations

import hashlib
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
