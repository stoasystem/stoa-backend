"""The one-off cleanup of the memory snapshots #675 stopped storing.

A dry run counts and deletes nothing; `--apply` deletes the snapshot rows of
every `LEARNING_MEMORY#` partition and nothing else - not a tombstone an
account deletion left there, not a row of another partition - and a row that
stopped being a snapshot between the scan and its delete is left.
"""

from __future__ import annotations

from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from scripts import delete_learning_memory_snapshots as cleanup


def _snapshot(student: str, topic: str) -> dict[str, Any]:
    return {
        "PK": f"LEARNING_MEMORY#{student}",
        "SK": f"SUBJECT#math#TOPIC#{topic}",
        "entity_type": "learning_memory_snapshot",
        "student_id": student,
        "owner_id": student,
        "topic_id": topic,
    }


@pytest.fixture
def table() -> FakeTable:
    table = FakeTable(page_item_cap=2)
    table.seed(
        _snapshot("s1", "brueche"),
        _snapshot("s1", "kr-fte"),
        _snapshot("s2", "general"),
        {
            "PK": "LEARNING_MEMORY#s3",
            "SK": "SUBJECT#math#TOPIC#zahlen",
            "entity_type": "learning_memory_snapshot_deletion_tombstone",
            "status": "deleted",
        },
        {"PK": "USER#s1", "SK": "PROFILE", "entity_type": "user_profile", "user_id": "s1"},
        {"PK": "ASSIGNMENT#a1", "SK": "META", "entity_type": "learning_assignment"},
    )
    return table


def test_a_dry_run_counts_and_deletes_nothing(
    table: FakeTable, capsys: pytest.CaptureFixture[str]
) -> None:
    before = {key: dict(row) for key, row in table.rows.items()}

    assert cleanup.run(table, apply_deletes=False) == 0

    assert table.rows == before
    out = capsys.readouterr().out
    assert (
        "students: 3 | rows: 4 | snapshots: 3 | "
        "other: learning_memory_snapshot_deletion_tombstone: 1"
    ) in out
    assert "[DRY RUN]" in out
    # Counted, never named.
    assert "s1" not in out and "s2" not in out


def test_apply_deletes_the_snapshots_and_nothing_else(
    table: FakeTable, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cleanup.run(table, apply_deletes=True) == 0

    assert sorted(table.rows) == [
        ("ASSIGNMENT#a1", "META"),
        ("LEARNING_MEMORY#s3", "SUBJECT#math#TOPIC#zahlen"),
        ("USER#s1", "PROFILE"),
    ]
    out = capsys.readouterr().out
    assert "deleted: 3 | left, not a snapshot: 1" in out
    assert "After: students: 1 | rows: 1 | other: learning_memory_snapshot_deletion_tombstone: 1" in out
    # A second run finds nothing left to delete.
    assert cleanup.run(table, apply_deletes=True) == 0


def test_a_row_that_stopped_being_a_snapshot_is_left(table: FakeTable) -> None:
    rows = cleanup.find(table)
    # An account deletion tombstones one after the scan.
    key = ("LEARNING_MEMORY#s2", "SUBJECT#math#TOPIC#general")
    table.rows[key] = {
        "PK": key[0],
        "SK": key[1],
        "entity_type": "learning_memory_snapshot_deletion_tombstone",
    }

    outcome = cleanup.delete(table, rows)

    assert outcome == {"deleted": 2, "changed meanwhile, left": 1, "left, not a snapshot": 1}
    assert key in table.rows
