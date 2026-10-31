"""DynamoDB access patterns for the Question entity."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from boto3.dynamodb.conditions import Key
from stoa.db.repositories import account_deletion_repo
from stoa.db.dynamodb import get_table, stored_int


type QuestionItem = dict[str, object]

_TAKEOVER_CLAIM_DOMAIN = b"stoa.teacher.takeover.claim.v1"


class QuestionMutationDisposition(StrEnum):
    """Identity-safe outcomes from the question state/version CAS boundary."""

    APPLIED = "applied"
    STALE = "stale"
    INVALID_TRANSITION = "invalid_transition"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class QuestionMutationResult:
    disposition: QuestionMutationDisposition
    question_id: str
    question: QuestionItem | None = None


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


def _table(candidate: object | None = None) -> object:
    return candidate or get_table()


def _get_item(table: object, **kwargs: object) -> QuestionItem:
    if not isinstance(table, _GetTable):
        raise account_deletion_repo.AccountDeletionConflict("question dependency unavailable")
    return _response(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise account_deletion_repo.AccountDeletionConflict("question dependency unavailable")
    return table.put_item(**kwargs)


def _query(table: object, **kwargs: object) -> QuestionItem:
    if not isinstance(table, _QueryTable):
        raise account_deletion_repo.AccountDeletionConflict("question dependency unavailable")
    return _response(table.query(**kwargs))


def _update_item(table: object, **kwargs: object) -> QuestionItem:
    if not isinstance(table, _UpdateTable):
        raise account_deletion_repo.AccountDeletionConflict("question dependency unavailable")
    result = table.update_item(**kwargs)
    return {} if result is None else _response(result)


def _response(value: object) -> QuestionItem:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise account_deletion_repo.AccountDeletionConflict("question dependency unavailable")
    return {key: item for key, item in value.items() if isinstance(key, str)}


def question_item(item: QuestionItem) -> QuestionItem:
    """Build the canonical question transaction item without persisting it."""
    return {"PK": f"QUESTION#{item['question_id']}", "SK": "META", **item}


def get_question(
    question_id: str, *, table: object | None = None
) -> QuestionItem | None:
    table = _table(table)
    resp = _get_item(table,
        Key={"PK": f"QUESTION#{question_id}", "SK": "META"},
        ConsistentRead=True,
    )
    item = resp.get("Item")
    return _response(item) if isinstance(item, dict) else None


def get_teacher_session(
    session_id: str, *, table: object | None = None
) -> QuestionItem | None:
    """Read a current teacher-session snapshot without changing its lifecycle."""
    if not session_id:
        return None
    response = _get_item(_table(table),
        Key={"PK": f"SESSION#{session_id}", "SK": "META"},
        ConsistentRead=True,
    )
    item = response.get("Item")
    return _response(item) if isinstance(item, dict) else None


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    return value


def teacher_takeover_claim_id(question_id: str, teacher_id: str) -> str:
    """Derive one opaque durable claim identity for a teacher and question."""
    payload = (
        _TAKEOVER_CLAIM_DOMAIN
        + _frame(_required_text(question_id, "question_id"))
        + _frame(_required_text(teacher_id, "teacher_id"))
    )
    return hashlib.sha256(payload).hexdigest()


def _question_version(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, Decimal) and value == value.to_integral_value():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def get_teacher_assignment(teacher_id: str, student_id: str) -> QuestionItem | None:
    """Read the existing scoped assignment row; Phase 475 owns its writes."""
    if not teacher_id or not student_id:
        return None
    response = _get_item(_table(),
        Key={
            "PK": f"TEACHER_ASSIGNMENT#{teacher_id}",
            "SK": f"STUDENT#{student_id}",
        },
        ConsistentRead=True,
    )
    item = response.get("Item")
    return _response(item) if isinstance(item, dict) else None


def get_teacher_curriculum_assignment(teacher_id: str) -> QuestionItem | None:
    """Read the current teacher curriculum-scope projection consistently.

    Phase 475 owns assignment write consistency. This read deliberately uses one
    current projection and fails closed when it is absent or unavailable.
    """
    if not teacher_id:
        return None
    response = _get_item(_table(),
        Key={
            "PK": f"TEACHER_ASSIGNMENT#{teacher_id}",
            "SK": "CURRICULUM#CURRENT",
        },
        ConsistentRead=True,
    )
    item = response.get("Item")
    if not isinstance(item, dict):
        return None
    # DynamoDB returns the stored version as Decimal, so it is normalized here,
    # at the trusted boundary, and handed onward as the int the policy requires.
    version = stored_int(item.get("version"))
    if (
        item.get("PK") != f"TEACHER_ASSIGNMENT#{teacher_id}"
        or item.get("SK") != "CURRICULUM#CURRENT"
        or item.get("entity_type") != "teacher_curriculum_assignment"
        or item.get("teacher_id") != teacher_id
        or version is None
        or version <= 0
    ):
        return None
    row = _response(item)
    row["version"] = version
    return row


def is_question_record(row: object) -> bool:
    """Tell a question apart from the other records sharing the student index.

    GSI-StudentId carries every record holding a student_id, including
    conversations, messages, usage ledger events, upload intents and weekly
    reports. Counting a page of it as questions overstates them severalfold.
    """
    if not isinstance(row, Mapping):
        return False
    return (
        row.get("SK") == "META"
        and str(row.get("PK", "")).startswith("QUESTION#")
        # A chat help request's queue row is shaped like a question but is not
        # one: it is counted and shown through its conversation (user
        # decision on #77, 2026-09-29).
        and row.get("source") != "conversation_escalation"
    )


QUESTION_READ_MAX_PAGES = 10


def list_questions_by_student(
    student_id: str,
    *,
    limit: int = 20,
    last_key: QuestionItem | None = None,
    max_pages: int = QUESTION_READ_MAX_PAGES,
) -> QuestionItem:
    """Up to `limit` of a student's questions, newest first, read past other rows.

    `GSI-StudentId` is shared with every row carrying a student_id, and
    `Limit` counts rows read, so one page of it was often empty of questions
    while more waited. This reads on, at most `max_pages` pages, until
    `limit` questions are in hand. `LastEvaluatedKey` resumes right after the
    last question returned, or where reading stopped (#77).
    """
    items: list[QuestionItem] = []
    cursor = last_key
    for _page in range(max_pages):
        page = list_by_student(student_id, limit=max(limit, 50), last_key=cursor)
        raw = page.get("Items", []) if isinstance(page, Mapping) else []
        for row in raw if isinstance(raw, list) else []:
            if not is_question_record(row):
                continue
            items.append(row)
            if len(items) == limit:
                return {"Items": items, "LastEvaluatedKey": _student_index_key(row)}
        cursor = page.get("LastEvaluatedKey") if isinstance(page, Mapping) else None
        if not cursor:
            return {"Items": items}
    return {"Items": items, "LastEvaluatedKey": cursor}


def _student_index_key(row: Mapping[str, object]) -> QuestionItem:
    """The GSI-StudentId position of a row, to resume a query right after it."""
    return {field: row[field] for field in ("PK", "SK", "student_id", "created_at") if field in row}


def list_by_student(
    student_id: str, limit: int = 20, last_key: QuestionItem | None = None
) -> QuestionItem:
    table = _table()
    kwargs: dict[str, object] = {
        "IndexName": "GSI-StudentId",
        "KeyConditionExpression": Key("student_id").eq(student_id),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _query(table, **kwargs)


def build_question_update_transaction(
    question: QuestionItem,
    *,
    status: str,
    expected_generation: int,
    condition_expression: str | None = None,
    condition_names: dict[str, str] | None = None,
    condition_values: QuestionItem | None = None,
    extra_attrs: Mapping[str, object] | None = None,
) -> list[QuestionItem]:
    """Build the legacy-compatible shape through the state/version CAS contract."""
    question_id = str(question.get("question_id") or "")
    student_id = str(question.get("student_id") or "")
    source_status = str(question.get("status") or status)
    expected_version = _question_version(question.get("version")) or 1
    update_expr = "SET #s = :s, #version=:next_version"
    attr_names = {"#s": "status", "#version": "version"}
    attr_names.update(condition_names or {})
    attr_values = {
        ":s": status,
        ":source_status": source_status,
        ":expected_version": expected_version,
        ":next_version": expected_version + 1,
        **(condition_values or {}),
    }
    removals = [k for k, v in (extra_attrs or {}).items() if v is None]
    for k, v in (extra_attrs or {}).items():
        if v is None:
            continue  # cleared below; a SET would name a value the serializer drops
        update_expr += f", {k} = :{k}"
        attr_values[f":{k}"] = v
    if removals:
        update_expr += " REMOVE " + ", ".join(removals)
    row_condition = (
        "attribute_exists(PK) AND attribute_exists(SK) AND student_id=:owner "
        "AND #s=:source_status AND #version=:expected_version"
    )
    attr_values[":owner"] = student_id
    if condition_expression:
        row_condition += f" AND ({condition_expression})"
    return [
        account_deletion_repo.active_fence_condition(student_id, expected_generation),
        {
            "Update": {
                "Key": {"PK": f"QUESTION#{question_id}", "SK": "META"},
                "UpdateExpression": update_expr,
                "ConditionExpression": row_condition,
                "ExpressionAttributeNames": attr_names,
                "ExpressionAttributeValues": attr_values,
            }
        },
    ]


_PROTECTED_QUESTION_FIELDS = frozenset(
    {"PK", "SK", "question_id", "student_id", "status", "version"}
)


def _mutation_identity(
    question: Mapping[str, object], allowed_source_statuses: frozenset[str]
) -> tuple[str, str, str]:
    question_id = _required_text(question.get("question_id"), "question_id")
    student_id = _required_text(question.get("student_id"), "student_id")
    source_status = _required_text(question.get("status"), "status")
    if not allowed_source_statuses or any(
        not isinstance(value, str) or not value for value in allowed_source_statuses
    ):
        raise ValueError("allowed_source_statuses must be a closed non-empty set")
    if question.get("PK", f"QUESTION#{question_id}") != f"QUESTION#{question_id}":
        raise ValueError("question identity does not match its partition key")
    if question.get("SK", "META") != "META":
        raise ValueError("question identity does not match its sort key")
    return question_id, student_id, source_status


def _mutation_fields(extra_attrs: Mapping[str, object] | None) -> QuestionItem:
    fields = dict(extra_attrs or {})
    protected = _PROTECTED_QUESTION_FIELDS.intersection(fields)
    if protected:
        raise ValueError("question mutation cannot replace identity, owner, state, or version")
    if any(not isinstance(key, str) or not key.isidentifier() for key in fields):
        raise ValueError("question mutation field names must be identifiers")
    return fields


def _question_mutation_operation(
    *,
    question_id: str,
    student_id: str,
    source_status: str,
    expected_version: int | None,
    status: str,
    extra_attrs: Mapping[str, object],
) -> QuestionItem:
    names: dict[str, str] = {"#status": "status", "#version": "version"}
    values: QuestionItem = {
        ":owner": student_id,
        ":expected_status": source_status,
        ":next_status": _required_text(status, "status"),
        ":next_version": 1 if expected_version is None else expected_version + 1,
    }
    updates = ["#status=:next_status", "#version=:next_version"]
    condition = (
        "attribute_exists(PK) AND attribute_exists(SK) AND student_id=:owner "
        "AND #status=:expected_status AND "
    )
    if expected_version is None:
        condition += "attribute_not_exists(#version)"
    else:
        condition += "#version=:expected_version"
        values[":expected_version"] = expected_version
    removals: list[str] = []
    for index, (field, value) in enumerate(extra_attrs.items()):
        name_token = f"#field_{index}"
        names[name_token] = field
        if value is None:
            # `None` clears the field. Written as a SET it named a value the
            # serializer drops, and DynamoDB refused the whole write (#75).
            removals.append(name_token)
            continue
        value_token = f":field_{field}"
        values[value_token] = value
        updates.append(f"{name_token}={value_token}")
    expression = "SET " + ", ".join(updates)
    if removals:
        expression += " REMOVE " + ", ".join(removals)
    return {
        "Update": {
            "Key": {"PK": f"QUESTION#{question_id}", "SK": "META"},
            "UpdateExpression": expression,
            "ConditionExpression": condition,
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
        }
    }


def _matching_applied_mutation(
    question: Mapping[str, object],
    *,
    question_id: str,
    student_id: str,
    expected_version: int | None,
    status: str,
    extra_attrs: Mapping[str, object],
) -> bool:
    next_version = 1 if expected_version is None else expected_version + 1
    return (
        question.get("question_id") == question_id
        and question.get("student_id") == student_id
        and _question_version(question.get("version")) == next_version
        and question.get("status") == status
        and all(question.get(key) == value for key, value in extra_attrs.items())
    )


def _classify_question_mutation_loss(
    *,
    question_id: str,
    student_id: str,
    source_status: str,
    expected_version: int | None,
    status: str,
    extra_attrs: Mapping[str, object],
    table: object,
) -> QuestionMutationResult:
    try:
        refreshed = get_question(question_id, table=table)
    except Exception:
        refreshed = None
    if not refreshed or (
        refreshed.get("question_id") != question_id
        or refreshed.get("student_id") != student_id
    ):
        return QuestionMutationResult(QuestionMutationDisposition.RETRYABLE, question_id)
    if _matching_applied_mutation(
        refreshed,
        question_id=question_id,
        student_id=student_id,
        expected_version=expected_version,
        status=status,
        extra_attrs=extra_attrs,
    ):
        return QuestionMutationResult(
            QuestionMutationDisposition.APPLIED, question_id, dict(refreshed)
        )
    refreshed_version = _question_version(refreshed.get("version"))
    if refreshed_version != expected_version:
        return QuestionMutationResult(QuestionMutationDisposition.STALE, question_id)
    if refreshed.get("status") != source_status:
        return QuestionMutationResult(
            QuestionMutationDisposition.INVALID_TRANSITION, question_id
        )
    return QuestionMutationResult(QuestionMutationDisposition.RETRYABLE, question_id)


def mutate_question(
    question: Mapping[str, object],
    *,
    status: str,
    allowed_source_statuses: frozenset[str],
    additional_conditions: tuple[QuestionItem, ...] = (),
    additional_operations: tuple[QuestionItem, ...] = (),
    extra_attrs: Mapping[str, object] | None = None,
    table: object | None = None,
) -> QuestionMutationResult:
    """Apply one owner/state/version CAS from a caller-observed snapshot."""
    question_id, student_id, source_status = _mutation_identity(
        question, allowed_source_statuses
    )
    if source_status not in allowed_source_statuses:
        return QuestionMutationResult(
            QuestionMutationDisposition.INVALID_TRANSITION, question_id
        )
    expected_version = _question_version(question.get("version"))
    if expected_version is None:
        raise ValueError("legacy questions require explicit version initialization")
    fields = _mutation_fields(extra_attrs)
    target = _table(table)
    try:
        fence = account_deletion_repo.require_active_account_fence(
            student_id, table=target
        )
        operations: list[QuestionItem] = [
            account_deletion_repo.active_fence_condition(
                student_id, int(fence["generation"])
            ),
            *additional_conditions,
            *additional_operations,
            _question_mutation_operation(
                question_id=question_id,
                student_id=student_id,
                source_status=source_status,
                expected_version=expected_version,
                status=status,
                extra_attrs=fields,
            ),
        ]
        account_deletion_repo.transact(
            operations,
            table=target,
        )
    except Exception:
        return _classify_question_mutation_loss(
            question_id=question_id,
            student_id=student_id,
            source_status=source_status,
            expected_version=expected_version,
            status=status,
            extra_attrs=fields,
            table=target,
        )
    applied: QuestionItem = {
        **question,
        "status": status,
        "version": expected_version + 1,
        **fields,
    }
    return QuestionMutationResult(
        QuestionMutationDisposition.APPLIED, question_id, applied
    )


def initialize_legacy_question_version(
    question: Mapping[str, object],
    *,
    allowed_source_statuses: frozenset[str],
    table: object | None = None,
) -> QuestionMutationResult:
    """Initialize an unversioned legacy row without performing its next mutation."""
    question_id, student_id, source_status = _mutation_identity(
        question, allowed_source_statuses
    )
    if source_status not in allowed_source_statuses:
        return QuestionMutationResult(
            QuestionMutationDisposition.INVALID_TRANSITION, question_id
        )
    if _question_version(question.get("version")) is not None:
        raise ValueError("question already has a positive version")
    target = _table(table)
    try:
        fence = account_deletion_repo.require_active_account_fence(
            student_id, table=target
        )
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(
                    student_id, int(fence["generation"])
                ),
                _question_mutation_operation(
                    question_id=question_id,
                    student_id=student_id,
                    source_status=source_status,
                    expected_version=None,
                    status=source_status,
                    extra_attrs={},
                ),
            ],
            table=target,
        )
    except Exception:
        return _classify_question_mutation_loss(
            question_id=question_id,
            student_id=student_id,
            source_status=source_status,
            expected_version=None,
            status=source_status,
            extra_attrs={},
            table=target,
        )
    initialized = {**question, "version": 1}
    return QuestionMutationResult(
        QuestionMutationDisposition.APPLIED, question_id, initialized
    )


