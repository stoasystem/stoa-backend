"""The knowledge points a student's Ask questions named (#143).

Each new question an Ask answer took up leaves one record of the knowledge
points it named, so the readers the old 「交一道题」 flow fed - weak topics,
adaptive memory, the weekly report, the parent dashboard and a teacher's prep -
read them too, without a question row behind them (#148 retired that flow).

A record holds the subject, the names and the unit ids of the points that are
stars on the student's map. It never holds the question: a parent reads these
names, and the question stays the student's. A name the model wrote freely is
text the student can steer it into writing, and it travels on - to the parent,
the weekly report's prompt, the teacher, the next answer's prompt - so one that
looks like personal data (`knowledge_gap_repo.looks_personal`) is not recorded;
a star's name is the catalog's and always is. It is written inside the
transaction that stores the answer (`attachment_repo.complete_message_command`),
whose assistant-message put only succeeds once, so an answer replayed, retried
or finished by another attempt records once, and a follow-up records nothing.

The record lives in the conversation's partition, beside its messages, and
carries the student as owner: deleting the account scrubs it with them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from stoa.db.dynamodb import get_table
from stoa.db.repositories import knowledge_gap_repo

ENTITY_TYPE = "asked_knowledge_points"
SCHEMA_VERSION = "asked-knowledge-points.v1"
#: Longer than any knowledge point's name; a longer one is cut, not refused.
MAX_NAME_CHARS = 120
#: Most points one question records.
MAX_PER_QUESTION = 10
#: Most records one read of a student keeps, newest first, as the question
#: readers keep 500 questions.
READ_LIMIT = 500
#: Most index pages one read of a student follows.
READ_PAGE_BUDGET = 25


def record_key(conversation_id: str, message_id: str) -> dict[str, str]:
    return {"PK": f"CONV#{conversation_id}", "SK": f"KNOWLEDGE#{message_id}"}


def _written(name: str) -> str:
    return " ".join(name.split())[:MAX_NAME_CHARS]


def record_put(
    *,
    conversation_id: str,
    message_id: str,
    student_id: str,
    subject: str,
    points: Sequence[tuple[str, str | None]],
    asked_at: str,
) -> dict[str, object] | None:
    """The transaction put that records one question's points, or None if it named none.

    `points` are `(name, unit id or None)` in the order the answer named them;
    `asked_at` is when the answer was stored.
    """
    names: list[str] = []
    unit_ids: list[str] = []
    seen: set[str] = set()
    for name, unit_id in points:
        written = _written(name)
        if not written or written.casefold() in seen:
            continue
        if not unit_id and knowledge_gap_repo.looks_personal(name):
            continue
        seen.add(written.casefold())
        names.append(written)
        if unit_id:
            unit_ids.append(unit_id)
        if len(names) == MAX_PER_QUESTION:
            break
    if not names:
        return None
    return {
        "Put": {
            "Item": {
                **record_key(conversation_id, message_id),
                "entity_type": ENTITY_TYPE,
                "schema_version": SCHEMA_VERSION,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "owner_id": student_id,
                "student_id": student_id,
                "subject": subject,
                "knowledge_points": names,
                "unit_ids": unit_ids,
                "created_at": asked_at,
            },
            "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
        }
    }


def _is_record(row: object) -> bool:
    # A record the account's deletion scrubbed keeps its key but none of its names.
    return (
        isinstance(row, dict)
        and row.get("entity_type") == ENTITY_TYPE
        and row.get("status") != "deleted"
        and isinstance(row.get("knowledge_points"), list)
    )


def list_for_student(
    student_id: str, *, since: str | None = None, table: Any | None = None
) -> list[dict[str, Any]]:
    """The student's records, newest first; only those asked at or after `since`, if given.

    `GSI-StudentId` holds every row carrying the student id, so a page can be
    spent entirely on messages: reading goes on until `READ_LIMIT` records are
    in hand or `READ_PAGE_BUDGET` pages are read.
    """
    target = table or get_table()
    condition = Key("student_id").eq(student_id)
    if since is not None:
        condition = condition & Key("created_at").gte(since)
    request: dict[str, Any] = {
        "IndexName": "GSI-StudentId",
        "KeyConditionExpression": condition,
        "FilterExpression": Attr("entity_type").eq(ENTITY_TYPE),
        "ScanIndexForward": False,
    }
    records: list[dict[str, Any]] = []
    for _page in range(READ_PAGE_BUDGET):
        response = target.query(**request)
        records.extend(dict(row) for row in response.get("Items", []) if _is_record(row))
        cursor = response.get("LastEvaluatedKey")
        if len(records) >= READ_LIMIT or not cursor:
            break
        request["ExclusiveStartKey"] = cursor
    return records[:READ_LIMIT]


def list_for_conversation(
    conversation_id: str, *, table: Any | None = None
) -> list[dict[str, Any]]:
    """The records of one conversation's questions, newest first."""
    target = table or get_table()
    request: dict[str, Any] = {
        "KeyConditionExpression": (
            Key("PK").eq(f"CONV#{conversation_id}") & Key("SK").begins_with("KNOWLEDGE#")
        ),
    }
    records: list[dict[str, Any]] = []
    for _page in range(READ_PAGE_BUDGET):
        response = target.query(**request)
        records.extend(dict(row) for row in response.get("Items", []) if _is_record(row))
        cursor = response.get("LastEvaluatedKey")
        if not cursor:
            break
        request["ExclusiveStartKey"] = cursor
    return sorted(records, key=lambda row: str(row.get("created_at") or ""), reverse=True)
