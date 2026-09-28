"""A student's conversation deletion can finish: stoasystem/stoa-backend#78.

The conversation branch counts a pass as clean only when its scan returns
nothing. The tombstone it writes keeps the row's keys and the student as
owner, and the scan matched on owner and key prefix alone, so every pass
found the previous pass's tombstones and deletion never sealed. The phase-473
tests mocked the scan, so none of them ran into it.
"""

from __future__ import annotations

from fakes.dynamodb import FakeTable

from stoa.db.repositories import attachment_repo

STUDENT = "student-78"


def test_the_scan_skips_tombstones_but_not_live_rows():
    table = FakeTable()
    table.seed(
        {"PK": "CONV#live", "SK": "CONV", "owner_id": STUDENT, "student_id": STUDENT, "title": "t"},
        {
            "PK": "CONV#gone",
            "SK": "CONV",
            "owner_id": STUDENT,
            "student_id": STUDENT,
            "status": "deleted",
            "owner_deletion_generation": 1,
        },
        # A live row that merely has a status of its own is still found.
        {"PK": "CONV#live", "SK": "MSG#1", "owner_id": STUDENT, "student_id": STUDENT, "status": "sent"},
    )

    page = attachment_repo.scan_conversation_private_rows(STUDENT, table=table)

    assert sorted((item["PK"], item["SK"]) for item in page.items) == [
        ("CONV#live", "CONV"),
        ("CONV#live", "MSG#1"),
    ]
