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

_COMMAND_SCHEMA_VERSION = "question-submission-command.v2"
_QUESTION_SCHEMA_VERSION = "question.v1"
_FINGERPRINT_DOMAIN = b"stoa.question.submission.v1"
_COMMAND_IDENTITY_DOMAIN = b"stoa.question.submission.command.v1"
_RECONCILIATION_DIGEST_DOMAIN = "stoa.question.reconciliation.v1"
_REVERSAL_ID_DOMAIN = b"stoa.question.reversal.v1"
_EFFECT_IDENTITY_DOMAIN = b"stoa.question.provider-effect.v1"
_EFFECT_SCHEMA_VERSION = "question-provider-effect.v1"
_MAX_EFFECT_RESULT_BYTES = 64 * 1024
_MAX_EFFECT_RESULT_DEPTH = 8
_MAX_EFFECT_COLLECTION_MEMBERS = 256
_MAX_EFFECT_STRING_BYTES = 16 * 1024
_MAX_ADMISSION_ATTEMPTS = 4


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


class QuestionEffectKind(StrEnum):
    """Closed provider effects owned by one question-submission command."""

    OCR = "ocr"
    AI = "ai"


class QuestionEffectDisposition(StrEnum):
    """Closed outcomes across the provider-effect persistence boundary."""

    INVOKE_PROVIDER = "invoke_provider"
    PROVIDER_INFLIGHT = "provider_inflight"
    RESULT_READY = "result_ready"
    COMPLETED = "completed"
    PRE_PROVIDER_DEPENDENCY_FAILURE = "pre_provider_dependency_failure"
    TERMINAL_PROVIDER_REJECTION = "terminal_provider_rejection"
    PROVIDER_OUTCOME_UNKNOWN = "provider_outcome_unknown"
    RESULT_RECEIPT_AMBIGUOUS = "result_receipt_ambiguous"
    COMPLETION_DEPENDENCY_FAILURE = "completion_dependency_failure"
    COMPLETION_COMMITTED_RESPONSE_LOST = "completion_committed_response_lost"
    STALE_RECEIPT = "stale_receipt"


@dataclass(frozen=True, slots=True)
class QuestionEffectResult:
    disposition: QuestionEffectDisposition
    effect: QuestionAdmissionItem | None = None
    question: QuestionAdmissionItem | None = None
    command: QuestionAdmissionItem | None = None


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


def validate_question_submission_command_digest(value: object) -> str:
    """Return one opaque command digest or fail without echoing its input."""
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("question command identity is invalid")
    return value


def question_submission_command_digest(
    student_id: str, caller_idempotency_key: str
) -> str:
    """Derive the sole durable identity from canonical owner and caller key."""
    framed = bytearray(_COMMAND_IDENTITY_DOMAIN)
    framed.extend(_frame(_required_text(student_id, "student_id")))
    framed.extend(
        _frame(_required_text(caller_idempotency_key, "caller_idempotency_key"))
    )
    return hashlib.sha256(bytes(framed)).hexdigest()


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


def _effect_kind(value: QuestionEffectKind | str) -> QuestionEffectKind:
    try:
        return QuestionEffectKind(value)
    except (TypeError, ValueError):
        raise ValueError("question effect kind is invalid") from None


def _effect_command_identity(
    command: Mapping[str, object], *, require_processing: bool = False
) -> tuple[str, str, str, int, int]:
    student_id = _required_text(command.get("student_id"), "student_id")
    command_id = validate_question_submission_command_digest(
        command.get("command_id")
    )
    if (
        command.get("entity_type") != "question_submission_command"
        or command.get("schema_version") != _COMMAND_SCHEMA_VERSION
        or command.get("idempotency_digest") != command_id
        or command.get("fingerprint") is None
        or command.get("question_id") is None
        or (require_processing and command.get("status") != "processing")
    ):
        raise ValueError("question command schema is invalid")
    fingerprint = _required_text(command.get("fingerprint"), "fingerprint")
    _required_text(command.get("question_id"), "question_id")
    generation = _positive_integer(
        command.get("account_fence_generation"),
        "account_fence_generation",
        minimum=1,
    )
    version = _positive_integer(command.get("version"), "command version", minimum=1)
    return student_id, command_id, fingerprint, generation, version


def question_effect_identity(
    command: Mapping[str, object], kind: QuestionEffectKind | str
) -> str:
    """Derive one non-guessable effect identity from every immutable owner fact."""
    student_id, command_id, fingerprint, generation, _ = _effect_command_identity(
        command
    )
    question_id = _required_text(command.get("question_id"), "question_id")
    effect_kind = _effect_kind(kind)
    payload = bytearray(_EFFECT_IDENTITY_DOMAIN)
    for value in (
        student_id,
        command_id,
        fingerprint,
        question_id,
        str(generation),
        effect_kind.value,
    ):
        payload.extend(_frame(value))
    return hashlib.sha256(bytes(payload)).hexdigest()


def question_effect_key(
    student_id: str, effect_id: str
) -> QuestionAdmissionItem:
    return {
        "PK": f"USER#{_required_text(student_id, 'student_id')}",
        "SK": (
            "QUESTION_EFFECT#"
            f"{validate_question_submission_command_digest(effect_id)}"
        ),
    }


def _effect_row_matches(
    effect: Mapping[str, object],
    command: Mapping[str, object],
    kind: QuestionEffectKind | str,
) -> bool:
    try:
        student_id, command_id, fingerprint, generation, _ = _effect_command_identity(
            command
        )
        effect_kind = _effect_kind(kind)
        effect_id = question_effect_identity(command, effect_kind)
        version = _positive_integer(effect.get("version"), "effect version", minimum=1)
    except ValueError:
        return False
    return bool(
        version
        and effect.get("entity_type") == "question_provider_effect"
        and effect.get("schema_version") == _EFFECT_SCHEMA_VERSION
        and effect.get("effect_id") == effect_id
        and effect.get("effect_kind") == effect_kind.value
        and effect.get("student_id") == student_id
        and effect.get("command_id") == command_id
        and effect.get("idempotency_digest") == command_id
        and effect.get("fingerprint") == fingerprint
        and effect.get("question_id") == command.get("question_id")
        and effect.get("account_fence_generation") == generation
    )


def _effect_disposition(effect: Mapping[str, object]) -> QuestionEffectDisposition:
    statuses = {
        "inflight": QuestionEffectDisposition.PROVIDER_INFLIGHT,
        "result_ready": QuestionEffectDisposition.RESULT_READY,
        "completed": QuestionEffectDisposition.COMPLETED,
        "provider_outcome_unknown": QuestionEffectDisposition.PROVIDER_OUTCOME_UNKNOWN,
        "terminal_rejected": QuestionEffectDisposition.TERMINAL_PROVIDER_REJECTION,
    }
    return statuses.get(
        str(effect.get("status") or ""), QuestionEffectDisposition.STALE_RECEIPT
    )


def get_question_effect(
    command: Mapping[str, object],
    kind: QuestionEffectKind | str,
    *,
    table: object | None = None,
) -> QuestionEffectResult | None:
    """Strongly read and strictly bind one private provider-effect receipt."""
    target = table or get_table()
    student_id, _, _, _, _ = _effect_command_identity(command)
    effect_kind = _effect_kind(kind)
    effect_id = question_effect_identity(command, effect_kind)
    effect = _read_item(target, question_effect_key(student_id, effect_id))
    if effect is None:
        return None
    if not _effect_row_matches(effect, command, effect_kind):
        return QuestionEffectResult(QuestionEffectDisposition.STALE_RECEIPT)
    return QuestionEffectResult(_effect_disposition(effect), effect=dict(effect))


def get_question_submission_command(
    student_id: str,
    idempotency_digest: str,
    *,
    table: object | None = None,
) -> QuestionAdmissionItem | None:
    """Strongly read one durable question-submission command."""
    target = table or get_table()
    if not isinstance(target, _GetTable):
        raise ValueError("question admission dependency unavailable")
    response = _string_mapping(
        target.get_item(
            Key=question_submission_command_key(student_id, idempotency_digest),
            ConsistentRead=True,
        )
    )
    item = response.get("Item")
    return None if item is None else _string_mapping(item)


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
        counter_value=(
            counter_value
            if isinstance(counter_value, int) and not isinstance(counter_value, bool)
            else None
        ),
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


def _question_status_matches_command(
    command_status: object, question_status: object
) -> bool:
    allowed = {
        "processing": frozenset({"pending"}),
        "completed": frozenset(
            {"ai_answered", "escalated", "teacher_active", "resolved"}
        ),
        "terminal_failed": frozenset({"submission_failed"}),
    }
    return isinstance(command_status, str) and question_status in allowed.get(
        command_status, frozenset()
    )


def classify_question_submission_replay(
    *,
    student_id: str,
    idempotency_digest: str,
    fingerprint: str,
    table: object | None = None,
) -> QuestionAdmissionResult | None:
    """Strongly validate one command, owner fence, and question before replay."""
    target = table or get_table()
    student_id = _required_text(student_id, "student_id")
    idempotency_digest = validate_question_submission_command_digest(
        idempotency_digest
    )
    fingerprint = _required_text(fingerprint, "fingerprint")
    expected_key = question_submission_command_key(student_id, idempotency_digest)
    try:
        command = get_question_submission_command(
            student_id, idempotency_digest, table=target
        )
    except Exception:
        return QuestionAdmissionResult(QuestionAdmissionDisposition.RETRYABLE)
    if command is None:
        return None
    generation = command.get("account_fence_generation")
    version = command.get("version")
    if (
        command.get("PK") != expected_key["PK"]
        or command.get("SK") != expected_key["SK"]
        or command.get("entity_type") != "question_submission_command"
        or command.get("schema_version") != _COMMAND_SCHEMA_VERSION
        or command.get("student_id") != student_id
        or command.get("idempotency_digest") != idempotency_digest
        or command.get("command_id") != idempotency_digest
        or not _valid_sha256(command.get("fingerprint"))
        or command.get("status")
        not in {"processing", "completed", "terminal_failed"}
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 1
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version < 1
        or not isinstance(command.get("question_id"), str)
        or not command["question_id"]
    ):
        return QuestionAdmissionResult(QuestionAdmissionDisposition.RETRYABLE)
    try:
        account_deletion_repo.require_active_account_fence(
            student_id, generation, table=target
        )
    except Exception:
        return QuestionAdmissionResult(QuestionAdmissionDisposition.RETRYABLE)
    if command.get("fingerprint") != fingerprint:
        return QuestionAdmissionResult(
            QuestionAdmissionDisposition.PAYLOAD_MISMATCH,
            command=dict(command),
        )
    question_id = str(command["question_id"])
    try:
        question = question_repo.get_question(question_id, table=target)
    except Exception:
        question = None
    question_version = question.get("version") if question is not None else None
    if (
        question is None
        or question.get("PK") != f"QUESTION#{question_id}"
        or question.get("SK") != "META"
        or question.get("entity_type") != "question"
        or question.get("schema_version") != _QUESTION_SCHEMA_VERSION
        or question.get("question_id") != question_id
        or question.get("student_id") != student_id
        or question.get("account_fence_generation") != generation
        or isinstance(question_version, bool)
        or not isinstance(question_version, int)
        or question_version < 1
        or not _question_status_matches_command(
            command.get("status"), question.get("status")
        )
    ):
        return QuestionAdmissionResult(QuestionAdmissionDisposition.RETRYABLE)
    counter_value = command.get("counter_value")
    return QuestionAdmissionResult(
        QuestionAdmissionDisposition.RESUME,
        command=dict(command),
        question=dict(question),
        counter_value=(
            counter_value
            if isinstance(counter_value, int) and not isinstance(counter_value, bool)
            else None
        ),
    )


def _bounded_json_value(value: object, *, depth: int = 0) -> object:
    if depth > _MAX_EFFECT_RESULT_DEPTH:
        raise ValueError("question effect result is too deeply nested")
    if value is None or isinstance(value, (bool, int, float)):
        return value
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


def _validated_effect_result(
    kind: QuestionEffectKind, value: Mapping[str, object]
) -> QuestionAdmissionItem:
    result = _string_mapping(value)
    if kind is QuestionEffectKind.OCR:
        if set(result) != {"ai_content", "ocr_text", "ocr_metadata"}:
            raise ValueError("OCR effect result schema is invalid")
        if not isinstance(result["ai_content"], str) or not result["ai_content"]:
            raise ValueError("OCR effect content is invalid")
        if result["ocr_text"] is not None and not isinstance(result["ocr_text"], str):
            raise ValueError("OCR effect text is invalid")
        metadata = result["ocr_metadata"]
        if not isinstance(metadata, Mapping) or set(metadata) != {
            "status",
            "source",
            "text_length",
            "correction_applied",
            "failure_class",
        }:
            raise ValueError("OCR effect metadata is invalid")
    else:
        if set(result) != {"ai_response", "knowledge_points", "topic_seeds"}:
            raise ValueError("AI effect result schema is invalid")
        if not isinstance(result["ai_response"], Mapping):
            raise ValueError("AI effect response is invalid")
        if not isinstance(result["knowledge_points"], Sequence) or isinstance(
            result["knowledge_points"], (str, bytes, bytearray)
        ):
            raise ValueError("AI effect knowledge points are invalid")
        if not isinstance(result["topic_seeds"], Sequence) or isinstance(
            result["topic_seeds"], (str, bytes, bytearray)
        ):
            raise ValueError("AI effect topic seeds are invalid")
    bounded = _bounded_json_value(result)
    assert isinstance(bounded, dict)
    encoded = json.dumps(
        bounded,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > _MAX_EFFECT_RESULT_BYTES:
        raise ValueError("question effect result is too large")
    return bounded


def _effect_result_digest(result: Mapping[str, object]) -> str:
    encoded = json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def begin_question_effect(
    command: Mapping[str, object],
    question: Mapping[str, object],
    kind: QuestionEffectKind | str,
    *,
    started_at: str,
    table: object | None = None,
) -> QuestionEffectResult:
    """Persist one exact intent before permitting a provider invocation."""
    target = table or get_table()
    effect_kind = _effect_kind(kind)
    try:
        student_id, command_id, fingerprint, generation, command_version = (
            _effect_command_identity(command, require_processing=True)
        )
        question_id = _required_text(question.get("question_id"), "question_id")
        question_version = _positive_integer(
            question.get("version"), "question version", minimum=1
        )
        question_status = _required_text(question.get("status"), "question status")
        if (
            question_id != command.get("question_id")
            or question.get("student_id") != student_id
            or question_status != "pending"
        ):
            raise ValueError("question effect snapshot is stale")
        effect_id = question_effect_identity(command, effect_kind)
        effect: QuestionAdmissionItem = {
            **question_effect_key(student_id, effect_id),
            "entity_type": "question_provider_effect",
            "schema_version": _EFFECT_SCHEMA_VERSION,
            "effect_id": effect_id,
            "effect_kind": effect_kind.value,
            "student_id": student_id,
            "command_id": command_id,
            "idempotency_digest": command_id,
            "fingerprint": fingerprint,
            "question_id": question_id,
            "account_fence_generation": generation,
            "command_version": command_version,
            "question_version": question_version,
            "question_status": question_status,
            "status": "inflight",
            "version": 1,
            "started_at": _required_text(started_at, "started_at"),
            "updated_at": started_at,
        }
        operations: list[QuestionAdmissionItem] = [
            account_deletion_repo.active_fence_condition(student_id, generation),
            {
                "ConditionCheck": {
                    "Key": question_submission_command_key(student_id, command_id),
                    "ConditionExpression": (
                        "entity_type=:entity AND schema_version=:schema "
                        "AND student_id=:student AND command_id=:command_id "
                        "AND idempotency_digest=:command_id AND fingerprint=:fingerprint "
                        "AND question_id=:question AND account_fence_generation=:generation "
                        "AND #status=:processing AND #version=:command_version"
                    ),
                    "ExpressionAttributeNames": {
                        "#status": "status",
                        "#version": "version",
                    },
                    "ExpressionAttributeValues": {
                        ":entity": "question_submission_command",
                        ":schema": _COMMAND_SCHEMA_VERSION,
                        ":student": student_id,
                        ":command_id": command_id,
                        ":fingerprint": fingerprint,
                        ":question": question_id,
                        ":generation": generation,
                        ":processing": "processing",
                        ":command_version": command_version,
                    },
                }
            },
            {
                "ConditionCheck": {
                    "Key": {"PK": f"QUESTION#{question_id}", "SK": "META"},
                    "ConditionExpression": (
                        "student_id=:student AND question_id=:question "
                        "AND #status=:expected_status AND #version=:question_version"
                    ),
                    "ExpressionAttributeNames": {
                        "#status": "status",
                        "#version": "version",
                    },
                    "ExpressionAttributeValues": {
                        ":student": student_id,
                        ":question": question_id,
                        ":expected_status": question_status,
                        ":question_version": question_version,
                    },
                }
            },
            {
                "Put": {
                    "Item": effect,
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
        ]
        attachment_repo.transact(operations, table=target)
        return QuestionEffectResult(
            QuestionEffectDisposition.INVOKE_PROVIDER, effect=effect
        )
    except Exception:
        try:
            existing = get_question_effect(command, effect_kind, table=target)
        except Exception:
            existing = None
        if existing is not None:
            return existing
        return QuestionEffectResult(
            QuestionEffectDisposition.PRE_PROVIDER_DEPENDENCY_FAILURE
        )


def _effect_update_values(effect: Mapping[str, object]) -> QuestionAdmissionItem:
    return {
        ":schema": _EFFECT_SCHEMA_VERSION,
        ":student": effect["student_id"],
        ":command_id": effect["command_id"],
        ":fingerprint": effect["fingerprint"],
        ":question": effect["question_id"],
        ":generation": effect["account_fence_generation"],
        ":effect_id": effect["effect_id"],
        ":effect_kind": effect["effect_kind"],
        ":effect_version": effect["version"],
        ":expected_status": effect["status"],
    }


def _reread_effect(effect: Mapping[str, object], *, table: object) -> QuestionAdmissionItem | None:
    try:
        return _read_item(
            table,
            question_effect_key(str(effect["student_id"]), str(effect["effect_id"])),
        )
    except Exception:
        return None


def _transition_effect(
    effect: Mapping[str, object],
    *,
    status: str,
    time_field: str,
    at: str,
    disposition: QuestionEffectDisposition,
    extra_values: Mapping[str, object] | None = None,
    extra_updates: Sequence[str] = (),
    table: object,
) -> QuestionEffectResult:
    if not isinstance(table, _UpdateTable):
        return QuestionEffectResult(QuestionEffectDisposition.RESULT_RECEIPT_AMBIGUOUS)
    values = {
        **_effect_update_values(effect),
        ":next_status": status,
        ":next_version": int(effect["version"]) + 1,
        ":observed_at": _required_text(at, time_field),
        **dict(extra_values or {}),
    }
    updates = [
        "#status=:next_status",
        "#version=:next_version",
        f"{time_field}=:observed_at",
        "updated_at=:observed_at",
        *extra_updates,
    ]
    try:
        table.update_item(
            Key=question_effect_key(str(effect["student_id"]), str(effect["effect_id"])),
            UpdateExpression="SET " + ", ".join(updates),
            ConditionExpression=(
                "entity_type=:entity AND schema_version=:schema "
                "AND student_id=:student AND command_id=:command_id "
                "AND fingerprint=:fingerprint AND question_id=:question "
                "AND account_fence_generation=:generation AND effect_id=:effect_id "
                "AND effect_kind=:effect_kind AND #status=:expected_status "
                "AND #version=:effect_version"
            ),
            ExpressionAttributeNames={"#status": "status", "#version": "version"},
            ExpressionAttributeValues={
                **values,
                ":entity": "question_provider_effect",
            },
        )
    except Exception:
        refreshed = _reread_effect(effect, table=table)
        if refreshed and refreshed.get("status") == status:
            return QuestionEffectResult(disposition, effect=refreshed)
        return QuestionEffectResult(QuestionEffectDisposition.RESULT_RECEIPT_AMBIGUOUS)
    refreshed = {**effect, "status": status, "version": values[":next_version"], time_field: at, "updated_at": at}
    for token, member in dict(extra_values or {}).items():
        if token.startswith(":"):
            field = token.removeprefix(":")
            refreshed[field] = member
    return QuestionEffectResult(disposition, effect=refreshed)


def mark_question_effect_outcome_unknown(
    effect: Mapping[str, object],
    *,
    observed_at: str,
    table: object | None = None,
) -> QuestionEffectResult:
    target = table or get_table()
    return _transition_effect(
        effect,
        status="provider_outcome_unknown",
        time_field="outcome_unknown_at",
        at=observed_at,
        disposition=QuestionEffectDisposition.PROVIDER_OUTCOME_UNKNOWN,
        table=target,
    )


def mark_question_effect_terminal(
    effect: Mapping[str, object],
    *,
    failure_code: str,
    failed_at: str,
    table: object | None = None,
) -> QuestionEffectResult:
    target = table or get_table()
    return _transition_effect(
        effect,
        status="terminal_rejected",
        time_field="terminal_at",
        at=failed_at,
        disposition=QuestionEffectDisposition.TERMINAL_PROVIDER_REJECTION,
        extra_values={":failure_code": _required_text(failure_code, "failure_code")},
        extra_updates=("terminal_failure_code=:failure_code",),
        table=target,
    )


def record_question_effect_result(
    effect: Mapping[str, object],
    result: Mapping[str, object],
    *,
    recorded_at: str,
    table: object | None = None,
) -> QuestionEffectResult:
    """Store one strict bounded private result before any public question update."""
    target = table or get_table()
    try:
        kind = _effect_kind(effect.get("effect_kind"))
        if effect.get("status") != "inflight" or not isinstance(
            effect.get("version"), int
        ):
            raise ValueError("question effect intent is stale")
        validated = _validated_effect_result(kind, result)
        digest = _effect_result_digest(validated)
        if not isinstance(target, _UpdateTable):
            raise ValueError("question effect dependency unavailable")
        target.update_item(
            Key=question_effect_key(str(effect["student_id"]), str(effect["effect_id"])),
            UpdateExpression=(
                "SET #status=:result_ready, #result=:result, "
                "result_digest=:result_digest, result_recorded_at=:recorded_at, "
                "updated_at=:recorded_at, #version=:next_version"
            ),
            ConditionExpression=(
                "entity_type=:entity AND schema_version=:schema "
                "AND student_id=:student AND command_id=:command_id "
                "AND fingerprint=:fingerprint AND question_id=:question "
                "AND account_fence_generation=:generation AND effect_id=:effect_id "
                "AND effect_kind=:effect_kind AND #status=:expected_status "
                "AND #version=:effect_version"
            ),
            ExpressionAttributeNames={
                "#status": "status",
                "#result": "result",
                "#version": "version",
            },
            ExpressionAttributeValues={
                **_effect_update_values(effect),
                ":entity": "question_provider_effect",
                ":result_ready": "result_ready",
                ":result": validated,
                ":result_digest": digest,
                ":recorded_at": _required_text(recorded_at, "recorded_at"),
                ":next_version": int(effect["version"]) + 1,
            },
        )
    except ValueError:
        raise
    except Exception:
        refreshed = _reread_effect(effect, table=target)
        if (
            refreshed
            and refreshed.get("status") == "result_ready"
            and refreshed.get("result_digest") == digest
            and refreshed.get("result") == validated
        ):
            return QuestionEffectResult(
                QuestionEffectDisposition.RESULT_RECEIPT_AMBIGUOUS,
                effect=refreshed,
            )
        return mark_question_effect_outcome_unknown(
            effect, observed_at=recorded_at, table=target
        )
    persisted = {
        **effect,
        "status": "result_ready",
        "result": validated,
        "result_digest": digest,
        "result_recorded_at": recorded_at,
        "updated_at": recorded_at,
        "version": int(effect["version"]) + 1,
    }
    return QuestionEffectResult(
        QuestionEffectDisposition.RESULT_READY, effect=persisted
    )


def _effect_completion_fields(
    kind: QuestionEffectKind, result: Mapping[str, object]
) -> tuple[str, QuestionAdmissionItem]:
    validated = _validated_effect_result(kind, result)
    if kind is QuestionEffectKind.OCR:
        return "pending", {
            "ocr_text": validated["ocr_text"],
            "ocr_metadata": validated["ocr_metadata"],
        }
    return "ai_answered", {
        "ai_response": validated["ai_response"],
        "knowledge_points": validated["knowledge_points"],
        "topic_seeds": validated["topic_seeds"],
    }


def _matching_effect_completion(
    *,
    effect: Mapping[str, object] | None,
    command: Mapping[str, object] | None,
    question: Mapping[str, object] | None,
    expected_effect: Mapping[str, object],
    next_question_status: str,
    fields: Mapping[str, object],
) -> bool:
    if effect is None or command is None or question is None:
        return False
    kind = _effect_kind(expected_effect.get("effect_kind"))
    expected_command_status = (
        "completed" if kind is QuestionEffectKind.AI else "processing"
    )
    return bool(
        effect.get("status") == "completed"
        and effect.get("version") == int(expected_effect["version"]) + 1
        and effect.get("result_digest") == expected_effect.get("result_digest")
        and command.get("status") == expected_command_status
        and command.get("version") == int(expected_effect["command_version"]) + 1
        and command.get("last_effect_id") == expected_effect.get("effect_id")
        and command.get("last_effect_kind") == kind.value
        and question.get("status") == next_question_status
        and question.get("version") == int(expected_effect["question_version"]) + 1
        and all(question.get(field) == value for field, value in fields.items())
    )


def complete_question_effect(
    effect: Mapping[str, object],
    *,
    completed_at: str,
    table: object | None = None,
) -> QuestionEffectResult:
    """Atomically project one receipt into the public question and command."""
    target = table or get_table()
    try:
        kind = _effect_kind(effect.get("effect_kind"))
        effect_version = _positive_integer(
            effect.get("version"), "effect version", minimum=1
        )
        command_version = _positive_integer(
            effect.get("command_version"), "command version", minimum=1
        )
        question_version = _positive_integer(
            effect.get("question_version"), "question version", minimum=1
        )
        student_id = _required_text(effect.get("student_id"), "student_id")
        command_id = validate_question_submission_command_digest(
            effect.get("command_id")
        )
        question_id = _required_text(effect.get("question_id"), "question_id")
        fingerprint = _required_text(effect.get("fingerprint"), "fingerprint")
        generation = _positive_integer(
            effect.get("account_fence_generation"),
            "account_fence_generation",
            minimum=1,
        )
        effect_id = validate_question_submission_command_digest(effect.get("effect_id"))
        if (
            effect.get("entity_type") != "question_provider_effect"
            or effect.get("schema_version") != _EFFECT_SCHEMA_VERSION
            or effect.get("status") != "result_ready"
            or effect.get("idempotency_digest") != command_id
            or effect.get("question_status") != "pending"
            or not isinstance(effect.get("result"), Mapping)
        ):
            raise ValueError("question effect receipt is stale")
        result = _validated_effect_result(kind, effect["result"])
        result_digest = _effect_result_digest(result)
        if result_digest != effect.get("result_digest"):
            raise ValueError("question effect receipt digest is invalid")
        next_question_status, fields = _effect_completion_fields(kind, result)
        command = _read_item(
            target, question_submission_command_key(student_id, command_id)
        )
        question = _read_item(
            target, {"PK": f"QUESTION#{question_id}", "SK": "META"}
        )
        if (
            command is None
            or question is None
            or command.get("entity_type") != "question_submission_command"
            or command.get("schema_version") != _COMMAND_SCHEMA_VERSION
            or command.get("student_id") != student_id
            or command.get("command_id") != command_id
            or command.get("idempotency_digest") != command_id
            or command.get("fingerprint") != fingerprint
            or command.get("question_id") != question_id
            or command.get("account_fence_generation") != generation
            or command.get("status") != "processing"
            or command.get("version") != command_version
            or question.get("student_id") != student_id
            or question.get("question_id") != question_id
            or question.get("status") != "pending"
            or question.get("version") != question_version
        ):
            return QuestionEffectResult(QuestionEffectDisposition.STALE_RECEIPT)
        completed_at = _required_text(completed_at, "completed_at")
    except ValueError:
        return QuestionEffectResult(QuestionEffectDisposition.STALE_RECEIPT)

    effect_update: QuestionAdmissionItem = {
        "Update": {
            "Key": question_effect_key(student_id, effect_id),
            "UpdateExpression": (
                "SET #status=:completed, completed_at=:completed_at, "
                "updated_at=:completed_at, #version=:next_effect_version"
            ),
            "ConditionExpression": (
                "entity_type=:entity AND schema_version=:schema "
                "AND student_id=:student AND command_id=:command_id "
                "AND fingerprint=:fingerprint AND question_id=:question "
                "AND account_fence_generation=:generation AND effect_id=:effect_id "
                "AND effect_kind=:effect_kind AND #status=:result_ready "
                "AND result_digest=:result_digest AND #version=:effect_version"
            ),
            "ExpressionAttributeNames": {"#status": "status", "#version": "version"},
            "ExpressionAttributeValues": {
                ":entity": "question_provider_effect",
                ":schema": _EFFECT_SCHEMA_VERSION,
                ":student": student_id,
                ":command_id": command_id,
                ":fingerprint": fingerprint,
                ":question": question_id,
                ":generation": generation,
                ":effect_id": effect_id,
                ":effect_kind": kind.value,
                ":result_ready": "result_ready",
                ":result_digest": result_digest,
                ":effect_version": effect_version,
                ":completed": "completed",
                ":completed_at": completed_at,
                ":next_effect_version": effect_version + 1,
            },
        }
    }
    question_names: QuestionAdmissionItem = {
        "#status": "status",
        "#version": "version",
    }
    question_values: QuestionAdmissionItem = {
        ":student": student_id,
        ":question": question_id,
        ":expected_status": "pending",
        ":question_version": question_version,
        ":next_status": next_question_status,
        ":next_question_version": question_version + 1,
    }
    question_updates = [
        "#status=:next_status",
        "#version=:next_question_version",
    ]
    for index, (field, value) in enumerate(fields.items()):
        name = f"#field_{index}"
        token = f":field_{field}"
        question_names[name] = field
        question_values[token] = value
        question_updates.append(f"{name}={token}")
    question_update: QuestionAdmissionItem = {
        "Update": {
            "Key": {"PK": f"QUESTION#{question_id}", "SK": "META"},
            "UpdateExpression": "SET " + ", ".join(question_updates),
            "ConditionExpression": (
                "student_id=:student AND question_id=:question "
                "AND #status=:expected_status AND #version=:question_version"
            ),
            "ExpressionAttributeNames": question_names,
            "ExpressionAttributeValues": question_values,
        }
    }
    next_command_status = "completed" if kind is QuestionEffectKind.AI else "processing"
    command_update: QuestionAdmissionItem = {
        "Update": {
            "Key": question_submission_command_key(student_id, command_id),
            "UpdateExpression": (
                "SET #status=:next_command_status, #version=:next_command_version, "
                "updated_at=:completed_at, last_effect_id=:effect_id, "
                "last_effect_kind=:effect_kind"
            ),
            "ConditionExpression": (
                "entity_type=:entity AND schema_version=:schema "
                "AND student_id=:student AND command_id=:command_id "
                "AND idempotency_digest=:command_id AND fingerprint=:fingerprint "
                "AND question_id=:question AND account_fence_generation=:generation "
                "AND #status=:processing AND #version=:command_version"
            ),
            "ExpressionAttributeNames": {"#status": "status", "#version": "version"},
            "ExpressionAttributeValues": {
                ":entity": "question_submission_command",
                ":schema": _COMMAND_SCHEMA_VERSION,
                ":student": student_id,
                ":command_id": command_id,
                ":fingerprint": fingerprint,
                ":question": question_id,
                ":generation": generation,
                ":processing": "processing",
                ":command_version": command_version,
                ":next_command_status": next_command_status,
                ":next_command_version": command_version + 1,
                ":completed_at": completed_at,
                ":effect_id": effect_id,
                ":effect_kind": kind.value,
            },
        }
    }
    try:
        attachment_repo.transact(
            [
                account_deletion_repo.active_fence_condition(student_id, generation),
                effect_update,
                question_update,
                command_update,
            ],
            table=target,
        )
    except Exception:
        refreshed_effect = _reread_effect(effect, table=target)
        try:
            refreshed_command = _read_item(
                target, question_submission_command_key(student_id, command_id)
            )
            refreshed_question = _read_item(
                target, {"PK": f"QUESTION#{question_id}", "SK": "META"}
            )
        except Exception:
            refreshed_command = refreshed_question = None
        if _matching_effect_completion(
            effect=refreshed_effect,
            command=refreshed_command,
            question=refreshed_question,
            expected_effect=effect,
            next_question_status=next_question_status,
            fields=fields,
        ):
            return QuestionEffectResult(
                QuestionEffectDisposition.COMPLETION_COMMITTED_RESPONSE_LOST,
                effect=refreshed_effect,
                command=refreshed_command,
                question=refreshed_question,
            )
        return QuestionEffectResult(
            QuestionEffectDisposition.COMPLETION_DEPENDENCY_FAILURE,
            effect=refreshed_effect,
            command=refreshed_command,
            question=refreshed_question,
        )
    completed_effect = {
        **effect,
        "status": "completed",
        "version": effect_version + 1,
        "completed_at": completed_at,
        "updated_at": completed_at,
    }
    completed_question = {
        **question,
        "status": next_question_status,
        "version": question_version + 1,
        **fields,
    }
    completed_command = {
        **command,
        "status": next_command_status,
        "version": command_version + 1,
        "updated_at": completed_at,
        "last_effect_id": effect_id,
        "last_effect_kind": kind.value,
    }
    return QuestionEffectResult(
        QuestionEffectDisposition.COMPLETED,
        effect=completed_effect,
        command=completed_command,
        question=completed_question,
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
    question_version = _positive_integer(
        question.get("version", 1), "question version", minimum=1
    )
    if question.get("student_id") != student_id:
        raise ValueError("question owner mismatch")
    idempotency_digest = validate_question_submission_command_digest(
        command.get("idempotency_digest")
    )
    if (
        command.get("entity_type") != "question_submission_command"
        or command.get("schema_version") != _COMMAND_SCHEMA_VERSION
        or command.get("command_id") != idempotency_digest
    ):
        raise ValueError("question command schema is invalid")
    usage_digest = validate_question_submission_command_digest(
        usage_event.get("idempotency_digest")
    )
    expected_usage_key = _usage_event_key(
        student_id, quota_period, idempotency_digest
    )
    if (
        usage_digest != idempotency_digest
        or usage_event.get("event_id") != idempotency_digest
        or usage_event.get("PK") != expected_usage_key["PK"]
        or usage_event.get("SK") != expected_usage_key["SK"]
    ):
        raise ValueError("question usage identity is invalid")
    command_item = {
        **question_submission_command_key(student_id, idempotency_digest),
        **command,
        "student_id": student_id,
        "account_fence_generation": generation,
        "counter_value": next_counter,
        "quota_period": quota_period,
    }
    question_item = question_repo.question_item(
        {
            **question,
            "entity_type": "question",
            "schema_version": _QUESTION_SCHEMA_VERSION,
            "account_fence_generation": generation,
            "version": question_version,
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
    idempotency_digest: str,
    fingerprint: str,
    table: object,
) -> QuestionAdmissionResult | None:
    return classify_question_submission_replay(
        student_id=student_id,
        idempotency_digest=idempotency_digest,
        fingerprint=fingerprint,
        table=table,
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
    idempotency_digest: str,
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
    idempotency_digest = validate_question_submission_command_digest(
        idempotency_digest
    )
    fingerprint = _required_text(fingerprint, "fingerprint")
    quota_period = _required_text(quota_period, "quota_period")
    created_at = _required_text(created_at, "created_at")
    limit = _positive_integer(limit, "limit", minimum=1)
    question_id = _required_text(question.get("question_id"), "question_id")
    initial = _safe_reread(
        student_id=student_id,
        idempotency_digest=idempotency_digest,
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
                idempotency_digest=idempotency_digest,
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
            "command_id": idempotency_digest,
            "student_id": student_id,
            "idempotency_digest": idempotency_digest,
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
                idempotency_digest=idempotency_digest,
                fingerprint=fingerprint,
                table=target,
            )
            if replay is not None:
                return replay
            continue
        persisted_command = {
            **question_submission_command_key(student_id, idempotency_digest),
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
