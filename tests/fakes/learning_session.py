"""Planting a learning session's rows on a `FakeTable`, in the shape the module writes them (#228).

A test that arranges a conversation seeds its record and messages through these
helpers instead of writing the rows by hand, so a change to the shape
`learning_session` stores reaches every fixture at once (#205, decision 10):

- `seed_conversation` plants the record `learning_session.open` stores, owner-
  and fence-stamped the way the record's fenced write stamps it.
- `seed_message` plants a row made by `learning_session.append`.
- `patch_session_table` installs the fake in the table gateway (decision 8):
  every session read and write goes through `stoa.db.table`.

Teacher-note rows (`NOTE#…`) belong to the help request: `fakes.help_requests.seed_reply`
plants them (#233).
"""

from __future__ import annotations

from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from stoa.db import table as db_table
from stoa.services import learning_session
from stoa.services.learning_session import _store

NOW = "2026-09-24T08:00:00+00:00"

# What each role must be given, when the test does not say.
_ROLE_DEFAULTS: dict[str, dict[str, object]] = {
    "student": {"attachment_ids": []},
    "assistant": {"structured": None},
    "teacher": {
        "teacher_response_rich": {"version": 1, "blocks": []},
        "teacher_response_format": "stoa_teacher_reply_v1",
    },
    "system": {"system_event": "teacher_help_requested"},
}


def seed_conversation(
    table: FakeTable,
    *,
    conversation_id: str,
    student_id: str,
    subject: str = "Mathematik",
    grade: str = "Grade 6",
    title: str | None = None,
    now: str = NOW,
    generation: int = 1,
    **extra: Any,
) -> dict[str, Any]:
    """Plant the session's record as `learning_session.open` stores it; returns the row.

    `title` defaults to the placeholder the console opens a session with.
    `extra` is laid over the stored record: the help request's own fields
    (`escalated`, `escalation_status`, `status`, …), which `help_requests`
    writes onto the record, or `updated_at` when it differs from `now`.
    """
    record = learning_session._record(
        conversation_id,
        student_id,
        subject=subject,
        grade=grade,
        title=f"{subject} · {grade}" if title is None else title,
        now=now,
    )
    write = _store.build_conversation_write_transaction(
        item=record, owner_id=student_id, generation=generation
    )
    row = {**write[0]["Put"]["Item"], **extra}
    table.seed(row)
    return row


def seed_message(
    table: FakeTable,
    *,
    conversation_id: str,
    role: learning_session.Role,
    message_id: str,
    student_id: str,
    content: str,
    created_at: str,
    generation: int = 1,
    **role_fields: Any,
) -> dict[str, Any]:
    """Plant a message row made by `learning_session.append`; returns the row.

    A role's required field the test leaves out gets an empty value
    (no attachments, no structure, an empty teacher reply, the help request's
    system event).
    """
    fields = {**_ROLE_DEFAULTS[role], **role_fields}
    row = learning_session.append(
        conversation_id,
        role=role,
        message_id=message_id,
        student_id=student_id,
        generation=generation,
        content=content,
        created_at=created_at,
        **fields,
    )["Put"]["Item"]
    table.seed(row)
    return row


def patch_session_table(monkeypatch: pytest.MonkeyPatch, table: object) -> None:
    """Have every read and write of the session's rows reach `table`.

    It is the gateway's table for the rest of the test, so every other row the
    test reads or writes is on it too.
    """
    db_table.install(table)
