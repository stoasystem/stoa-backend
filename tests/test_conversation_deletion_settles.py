"""A student's conversation deletion can finish: stoasystem/stoa-backend#78.

A deletion pass counts as clean only when it finds nothing left to do. The
tombstone it writes keeps the row's keys and the student as owner, and the old
conversation scan matched on owner and key prefix alone, so every pass found
the previous pass's tombstones and deletion never sealed. The flow asks the
catalog what a row still needs (#641); a tombstone needs nothing, a live row
with a status of its own still does.
"""

from __future__ import annotations

from fakes.dynamodb import FakeTable
from fakes.learning_session import seed_conversation, seed_message

from stoa.services import account_deletion_flow as flow

STUDENT = "student-78"


def test_a_pass_skips_tombstones_but_not_live_rows():
    table = FakeTable()
    seed_conversation(table, conversation_id="live", student_id=STUDENT, title="t")
    # A tombstone the deletion wrote: not a session record any more.
    table.seed(
        {
            "PK": "CONV#gone",
            "SK": "CONV",
            "entity_type": "conversation",
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

    still_to_do = sorted(
        (row["PK"], row["SK"])
        for row in table.rows.values()
        if flow.action_for(row, STUDENT) is not None
    )

    assert still_to_do == [("CONV#live", "CONV"), ("CONV#live", "MSG#1")]
