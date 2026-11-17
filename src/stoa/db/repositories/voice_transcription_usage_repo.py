"""How many recordings a student had transcribed on one day (#477).

One counter row per student and UTC day, in the student's own partition
(`STUDENT#<student>/VOICE_TRANSCRIPTIONS_DAY#<YYYY-MM-DD>`), which account
deletion already sweeps; it carries `student_id` for that, and no `created_at`,
so it stays out of GSI-StudentId. `expires_at`, the table's TTL attribute, lets
the row go a day after its day ends.

Only the count is kept: never the recording, its length or what was said.
"""

from __future__ import annotations

from typing import Any, Final

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo


ENTITY_TYPE: Final = "voice_transcription_day"
SK_PREFIX: Final = "VOICE_TRANSCRIPTIONS_DAY#"


class DailyLimitReached(RuntimeError):
    """The student has used every transcription of the day."""


class AccountNotWritable(RuntimeError):
    """The student's account is being deleted."""


class UsageUnavailable(RuntimeError):
    """The counter could not be read or written; nothing was counted."""


def _partition(student_id: str) -> str:
    if not isinstance(student_id, str) or not student_id.strip():
        raise ValueError("student_id is required")
    return f"STUDENT#{student_id}"


def day_key(student_id: str, day: str) -> dict[str, str]:
    if not isinstance(day, str) or len(day) != 10:
        raise ValueError("day is YYYY-MM-DD")
    return {"PK": _partition(student_id), "SK": f"{SK_PREFIX}{day}"}


def _fenced(student_id: str, operation: dict[str, Any], table: Any | None) -> None:
    try:
        db_table.fenced(
            student_id, [operation], any_generation=True, table=table or db_table.table()
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise AccountNotWritable("account is not writable") from exc


def admit(
    student_id: str,
    day: str,
    *,
    limit: int,
    expires_at: int,
    table: Any | None = None,
) -> None:
    """Count one transcription, unless `limit` were already counted today."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    operation = {
        "Update": {
            "Key": day_key(student_id, day),
            "UpdateExpression": (
                "SET entity_type=:entity, student_id=:student, #day=:day, expires_at=:expires "
                "ADD #count :one"
            ),
            "ConditionExpression": "attribute_not_exists(#count) OR #count < :limit",
            "ExpressionAttributeNames": {"#count": "count", "#day": "day"},
            "ExpressionAttributeValues": {
                ":entity": ENTITY_TYPE,
                ":student": student_id,
                ":day": day,
                ":expires": expires_at,
                ":one": 1,
                ":limit": limit,
            },
        }
    }
    try:
        _fenced(student_id, operation, table)
    except db_table.WriteRefused as exc:
        if any(reason.kind is db_table.ReasonKind.CONDITION_FAILED for reason in exc.reasons):
            raise DailyLimitReached("daily limit reached") from exc
        raise UsageUnavailable("counter refused") from exc
    except db_table.TableUnavailable as exc:
        raise UsageUnavailable("table unavailable") from exc


def give_back(student_id: str, day: str, *, table: Any | None = None) -> None:
    """Uncount one transcription the model failed; never below zero."""
    operation = {
        "Update": {
            "Key": day_key(student_id, day),
            "UpdateExpression": "ADD #count :minus_one",
            "ConditionExpression": "#count > :zero",
            "ExpressionAttributeNames": {"#count": "count"},
            "ExpressionAttributeValues": {":minus_one": -1, ":zero": 0},
        }
    }
    try:
        _fenced(student_id, operation, table)
    except (db_table.WriteRefused, db_table.TableUnavailable) as exc:
        raise UsageUnavailable("counter not given back") from exc


def count(student_id: str, day: str, *, table: Any | None = None) -> int:
    item = db_table.get(
        table=table or db_table.table(), Key=day_key(student_id, day), ConsistentRead=True
    )
    if item is None or item.get("entity_type") != ENTITY_TYPE:
        return 0
    return int(item.get("count") or 0)
