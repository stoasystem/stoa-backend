"""A student's conversation deletion can finish: stoasystem/stoa-backend#78.

The conversation branch counts a pass as clean only when its scan returns
nothing. The tombstone it writes keeps the row's keys and the student as
owner, and the scan matched on owner and key prefix alone, so every pass
found the previous pass's tombstones and deletion never sealed. The phase-473
tests mocked the scan, so none of them ran into it.
"""

from __future__ import annotations

from fakes.dynamodb import FakeTable
from fakes.learning_session import seed_conversation, seed_message

from stoa.db.repositories import attachment_repo

STUDENT = "student-78"


def test_the_scan_skips_tombstones_but_not_live_rows():
    table = FakeTable()
    seed_conversation(table, conversation_id="live", student_id=STUDENT, title="t")
    # A tombstone the deletion wrote: not a session record any more.
    table.seed(
        {
            "PK": "CONV#gone",
            "SK": "CONV",
            "owner_id": STUDENT,
            "student_id": STUDENT,
            "status": "deleted",
            "owner_deletion_generation": 1,
        },
    )
    # A live row that merely has a status of its own is still found.
    seed_message(
        table,
        conversation_id="live",
        role="student",
        message_id="1",
        student_id=STUDENT,
        content="",
        created_at="2026-09-24T08:00:00+00:00",
    )
    table.rows[("CONV#live", "MSG#1")]["status"] = "sent"

    page = attachment_repo.scan_conversation_private_rows(STUDENT, table=table)

    assert sorted((item["PK"], item["SK"]) for item in page.items) == [
        ("CONV#live", "CONV"),
        ("CONV#live", "MSG#1"),
    ]
