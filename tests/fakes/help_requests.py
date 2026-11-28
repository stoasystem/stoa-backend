"""Planting a help request's rows on a `FakeTable`, in the shape the module writes them (#233).

A teacher's reply is a `NOTE#` row of the help request (#215 decision 5). A
test that arranges replies seeds them through `seed_reply` instead of writing
the rows by hand, so a change to the shape `help_requests.reply` stores
reaches every fixture at once. `seed_request` plants the request itself, in
any state (#693).
"""

from __future__ import annotations

from typing import Any

from fakes.dynamodb import FakeTable
from stoa.services import help_requests, learning_session


def seed_reply(
    table: FakeTable,
    *,
    conversation_id: str,
    note_id: str,
    teacher_id: str,
    teacher_name: str,
    content: str,
    created_at: str,
    student_id: str,
    generation: int = 1,
    rich: dict[str, Any] | None = None,
    format: str | None = None,
    attachment_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Plant a reply's `NOTE#` row as `help_requests.reply` writes it; returns the row.

    The row is owner- and fence-stamped the way the reply's write stamps it.
    `rich` and `format` default to an empty teacher reply.
    """
    row = help_requests._reply_row(
        conversation_id=conversation_id,
        note_id=note_id,
        teacher_id=teacher_id,
        teacher_name=teacher_name,
        content=content,
        rich={"version": 1, "blocks": []} if rich is None else rich,
        format="stoa_teacher_reply_v1" if format is None else format,
        created_at=created_at,
        attachment_ids=attachment_ids,
    )
    write = learning_session.build_conversation_write_transaction(
        item=row, owner_id=student_id, generation=generation
    )
    stamped = dict(write[0]["Put"]["Item"])
    table.seed(stamped)
    return stamped


def seed_request(
    table: FakeTable,
    *,
    conversation_id: str,
    student_id: str,
    status: str,
    asked_at: str,
    subject: str = "math",
    mode: str = "text",
    teacher_id: str | None = None,
    generation: int = 1,
) -> dict[str, Any]:
    """Plant a help request's record as `help_requests.ask` writes it, now in `status`.

    The record is owner- and fence-stamped the way the request's write stamps
    it and carries the index keys its state gives it; returns the row.
    """
    record: dict[str, Any] = {
        **help_requests.key(conversation_id),
        "entity_type": help_requests.ENTITY_TYPE,
        "schema_version": help_requests.SCHEMA_VERSION,
        "conversation_id": conversation_id,
        "escalation_request_id": conversation_id,
        "student_id": student_id,
        "version": 1,
        "escalated": True,
        "escalation_status": status,
        "mode": mode,
        "escalated_at": asked_at,
        "created_at": asked_at,
        "updated_at": asked_at,
        "subject": subject,
        "grade": "",
    }
    if teacher_id:
        record["teacher_id"] = teacher_id
        record["started_at"] = asked_at
    record.update(help_requests.index_fields(record))
    record.update(help_requests.listing_fields(record))
    write = learning_session.build_conversation_write_transaction(
        item=record, owner_id=student_id, generation=generation
    )
    stamped = dict(write[0]["Put"]["Item"])
    table.seed(stamped)
    return stamped
