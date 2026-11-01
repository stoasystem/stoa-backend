"""DynamoDB access patterns for the Question entity."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from boto3.dynamodb.conditions import Key
from stoa.db.repositories import account_deletion_repo
from stoa.db.dynamodb import get_table, stored_int


type QuestionItem = dict[str, object]

_TAKEOVER_CLAIM_DOMAIN = b"stoa.teacher.takeover.claim.v1"


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


