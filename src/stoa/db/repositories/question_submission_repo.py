"""Atomic admission boundary for quota-governed question submissions."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from stoa.db.dynamodb import get_table, stored_int
from stoa.db.repositories import attachment_repo


type QuestionAdmissionItem = dict[str, object]

_COMMAND_SCHEMA_VERSION = "question-submission-command.v2"
_QUESTION_SCHEMA_VERSION = "question.v1"
_FINGERPRINT_DOMAIN = b"stoa.question.submission.v1"
_RECONCILIATION_DIGEST_DOMAIN = "stoa.question.reconciliation.v1"
_REVERSAL_ID_DOMAIN = b"stoa.question.reversal.v1"
_MAX_EFFECT_RESULT_DEPTH = 8
_MAX_EFFECT_COLLECTION_MEMBERS = 256
_MAX_EFFECT_STRING_BYTES = 16 * 1024


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


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


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    return value


def _positive_integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} is invalid")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        parsed = int(value)
    else:
        raise ValueError(f"{field} is invalid")
    if parsed < minimum:
        raise ValueError(f"{field} is invalid")
    return parsed


def _string_mapping(value: object) -> QuestionAdmissionItem:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError("question admission dependency unavailable")
    return {str(key): member for key, member in value.items()}


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def validate_question_submission_command_digest(value: object) -> str:
    """Return one opaque command digest or fail without echoing its input."""
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("question command identity is invalid")
    return value


def question_submission_command_key(
    student_id: str, idempotency_digest: str
) -> QuestionAdmissionItem:
    return {
        "PK": f"USER#{_required_text(student_id, 'student_id')}",
        "SK": (
            "QUESTION_SUBMISSION#"
            f"{validate_question_submission_command_digest(idempotency_digest)}"
        ),
    }


def question_counter_key(student_id: str, quota_period: str) -> QuestionAdmissionItem:
    return {
        "PK": f"USAGE#{_required_text(student_id, 'student_id')}",
        "SK": f"QUESTION#{_required_text(quota_period, 'quota_period')}",
    }


def _classify_command(
    command: QuestionAdmissionItem | None,
    *,
    student_id: str,
    idempotency_digest: str,
    fingerprint: str,
) -> QuestionAdmissionResult | None:
    if command is None:
        return None
    if (
        command.get("entity_type") != "question_submission_command"
        or command.get("schema_version") != _COMMAND_SCHEMA_VERSION
        or command.get("student_id") != student_id
        or command.get("idempotency_digest") != idempotency_digest
        or command.get("command_id") != idempotency_digest
        or command.get("status") not in {"processing", "completed", "terminal_failed"}
        or not isinstance(command.get("question_id"), str)
        or not command["question_id"]
    ):
        return QuestionAdmissionResult(
            QuestionAdmissionDisposition.RETRYABLE,
        )
    if command.get("fingerprint") != fingerprint:
        return QuestionAdmissionResult(
            QuestionAdmissionDisposition.PAYLOAD_MISMATCH,
            command=dict(command),
        )
    counter_value = command.get("counter_value")
    return QuestionAdmissionResult(
        QuestionAdmissionDisposition.RESUME,
        command=dict(command),
        counter_value=stored_int(counter_value),
    )


def classify_question_submission_command(
    command: QuestionAdmissionItem | None,
    *,
    student_id: str,
    idempotency_digest: str,
    fingerprint: str,
) -> QuestionAdmissionResult | None:
    """Strictly classify an opaque command without projecting malformed rows."""
    return _classify_command(
        command,
        student_id=_required_text(student_id, "student_id"),
        idempotency_digest=validate_question_submission_command_digest(
            idempotency_digest
        ),
        fingerprint=_required_text(fingerprint, "fingerprint"),
    )


def _valid_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _bounded_json_value(value: object, *, depth: int = 0) -> object:
    if depth > _MAX_EFFECT_RESULT_DEPTH:
        raise ValueError("question effect result is too deeply nested")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Decimal):
        # A receipt read back from the table carries its numbers as Decimal,
        # and refusing them here makes every replayed completion stale.
        if not value.is_finite():
            raise ValueError("question effect result contains an unsupported value")
        integral = value.to_integral_value()
        return int(integral) if value == integral else float(value)
    if isinstance(value, str):
        if len(value.encode("utf-8")) > _MAX_EFFECT_STRING_BYTES:
            raise ValueError("question effect result string is too large")
        return value
    if isinstance(value, Mapping):
        if len(value) > _MAX_EFFECT_COLLECTION_MEMBERS or any(
            not isinstance(key, str) or not key for key in value
        ):
            raise ValueError("question effect result mapping is invalid")
        return {
            str(key): _bounded_json_value(member, depth=depth + 1)
            for key, member in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        if len(value) > _MAX_EFFECT_COLLECTION_MEMBERS:
            raise ValueError("question effect result collection is too large")
        return [_bounded_json_value(member, depth=depth + 1) for member in value]
    raise ValueError("question effect result contains an unsupported value")


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


def _optional_positive_version(value: object) -> int | None:
    parsed = stored_int(value)
    return parsed if parsed is not None and parsed >= 1 else None


def _read_item(target: object, key: QuestionAdmissionItem) -> QuestionAdmissionItem | None:
    if not isinstance(target, _GetTable):
        raise ValueError("question reconciliation dependency unavailable")
    response = _string_mapping(target.get_item(Key=key, ConsistentRead=True))
    item = response.get("Item")
    return None if item is None else _string_mapping(item)


def _usage_event_key(
    student_id: str, quota_period: str, idempotency_digest: str
) -> QuestionAdmissionItem:
    digest = validate_question_submission_command_digest(idempotency_digest)
    return {
        "PK": f"USAGE_LEDGER#{student_id}",
        "SK": f"EVENT#question_submission#{quota_period}#{digest}",
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
    idempotency_digest = validate_question_submission_command_digest(idempotency_key)
    command_id = idempotency_digest
    try:
        command = _read_item(
            target, question_submission_command_key(student_id, idempotency_digest)
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
                _usage_event_key(student_id, effective_period, idempotency_digest),
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
        # The digest is JSON, and the table returns the counter as Decimal,
        # which json.dumps refuses.
        "counter_count": stored_int(counter.get("count")) if counter else None,
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
        or command.get("idempotency_digest") != idempotency_digest
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
        or stored_int(counter.get("count")) is None
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
    counter_count = stored_int(counter.get("count"))
    assert counter_count is not None
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
        and _valid_sha256(command.get("terminal_effect_id"))
        and command.get("terminal_effect_kind") in {"ocr", "ai"}
        and question.get("status") == "pending"
        and question.get("terminal_failure_code")
        == command.get("terminal_failure_code")
        and question.get("terminal_failure_proven_at")
        == command.get("terminal_failure_proven_at")
        and question.get("terminal_effect_id") == command.get("terminal_effect_id")
        and question.get("terminal_effect_kind")
        == command.get("terminal_effect_kind")
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
                    "entity_type=:entity AND schema_version=:schema "
                    "AND student_id=:student AND command_id=:command_id "
                    "AND idempotency_digest=:command_id "
                    "AND account_fence_generation=:generation "
                    "AND #status=:terminal AND #version=:version AND fingerprint=:fingerprint "
                    "AND terminal_failure_proven_at=:proven_at "
                    "AND terminal_failure_code=:failure_code "
                    "AND terminal_effect_id=:effect_id AND terminal_effect_kind=:effect_kind "
                    "AND attribute_not_exists(reversal_id)"
                ),
                "ExpressionAttributeNames": {
                    "#status": "status",
                    "#version": "version",
                },
                "ExpressionAttributeValues": {
                    ":terminal": "terminal_failed",
                    ":entity": "question_submission_command",
                    ":schema": _COMMAND_SCHEMA_VERSION,
                    ":student": student_id,
                    ":command_id": current.command_id,
                    ":generation": command["account_fence_generation"],
                    ":version": current.observed_command_version,
                    ":next_version": current.observed_command_version + 1,
                    ":fingerprint": fingerprint,
                    ":proven_at": command["terminal_failure_proven_at"],
                    ":failure_code": command["terminal_failure_code"],
                    ":effect_id": command["terminal_effect_id"],
                    ":effect_kind": command["terminal_effect_kind"],
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
                    "entity_type=:entity AND schema_version=:schema "
                    "AND student_id=:student AND question_id=:question "
                    "AND account_fence_generation=:generation "
                    "AND #status=:pending "
                    "AND terminal_failure_code=:failure_code "
                    "AND terminal_failure_proven_at=:proven_at "
                    "AND terminal_effect_id=:effect_id "
                    "AND terminal_effect_kind=:effect_kind AND " + version_condition
                ),
                "ExpressionAttributeNames": {
                    "#status": "status",
                    "#version": "version",
                },
                "ExpressionAttributeValues": {
                    ":student": student_id,
                    ":question": current.question_id,
                    ":entity": "question",
                    ":schema": _QUESTION_SCHEMA_VERSION,
                    ":generation": command["account_fence_generation"],
                    ":pending": "pending",
                    ":failed": "submission_failed",
                    ":failure_code": command["terminal_failure_code"],
                    ":proven_at": command["terminal_failure_proven_at"],
                    ":effect_id": command["terminal_effect_id"],
                    ":effect_kind": command["terminal_effect_kind"],
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
                    "event_id=:ledger AND student_id=:student "
                    "AND idempotency_digest=:command_id AND question_id=:question "
                    "AND quantity=:one "
                    "AND (attribute_not_exists(#status) OR #status=:active) "
                    "AND attribute_not_exists(reversal_id)"
                ),
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":ledger": ledger_identity,
                    ":student": student_id,
                    ":command_id": current.command_id,
                    ":question": current.question_id,
                    ":one": 1,
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
