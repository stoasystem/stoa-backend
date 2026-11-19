"""The topic shelf backfill puts rows written before #513 on their shelf, and only those.

Run against the production-sized fixture with the shelf fields taken off, as the
table holds the curriculum before the backfill: a dry run counts and writes
nothing, `--apply` writes each row once and leaves its exercise version valid,
a row rewritten meanwhile is skipped, and `--verify` finds every row in the index.
"""

from __future__ import annotations

from typing import Any

import pytest

from fakes.published_curriculum import ReadCountingTable, curriculum_rows
from scripts import backfill_topic_shelf as backfill
from stoa.db import table as db_table
from stoa.db.repositories import practice_repo


def _before_the_writers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {k: v for k, v in row.items() if k not in practice_repo.TOPIC_SHELF_FIELDS} for row in rows
    ]


@pytest.fixture
def table() -> ReadCountingTable:
    table = ReadCountingTable()
    rows = _before_the_writers(curriculum_rows(0.02))
    # One unit already in place, one lesson that lost its topic but kept a stale shelf.
    unit = next(row for row in rows if row["SK"].startswith("UNIT#"))
    unit.update(practice_repo.topic_shelf_fields(unit))
    lesson = next(row for row in rows if row["SK"].startswith("LESSON#"))
    lesson.update(practice_repo.topic_shelf_fields(lesson))
    del lesson["topic_id"]
    table.seed(*rows)
    db_table.install(table)
    return table


def _curriculum(table: ReadCountingTable) -> list[dict[str, Any]]:
    return [
        row
        for (pk, sk), row in table.rows.items()
        if pk == "PRACTICE" and sk.split("#", 1)[0] in practice_repo.TOPIC_SHELF_KINDS
    ]


def test_a_dry_run_counts_and_writes_nothing(
    table: ReadCountingTable, capsys: pytest.CaptureFixture[str]
) -> None:
    before = {key: dict(row) for key, row in table.rows.items()}

    assert backfill.run(table, apply_writes=False, verify_index=False) == 0

    assert table.rows == before
    out = capsys.readouterr().out
    rows = _curriculum(table)
    units = sum(1 for row in rows if row["SK"].startswith("UNIT#"))
    assert f"UNIT: rows {units} | in place 1 | to write {units - 1} | no topic 0" in out
    assert f"Rows to write: {len(rows) - 1}" in out
    assert "[DRY RUN]" in out


def test_apply_puts_every_row_on_its_shelf_and_keeps_exercises_valid(
    table: ReadCountingTable,
) -> None:
    assert backfill.run(table, apply_writes=True, verify_index=False) == 0

    for row in _curriculum(table):
        expected = practice_repo.topic_shelf_fields(row)
        assert {k: row[k] for k in practice_repo.TOPIC_SHELF_FIELDS if k in row} == expected
    exercise = next(row for row in _curriculum(table) if row["SK"].startswith("CHALLENGE#"))
    assert practice_repo.get_challenge(exercise["challenge_id"]) is not None
    # Nothing is left to write, and every row is found through the index.
    assert backfill.plan(_curriculum(table)).writes == []
    assert backfill.verify(table, _curriculum(table)) == []


def test_verify_names_the_rows_missing_from_the_index(
    table: ReadCountingTable, capsys: pytest.CaptureFixture[str]
) -> None:
    assert backfill.run(table, apply_writes=False, verify_index=True) == 1

    out = capsys.readouterr().out
    assert f"Missing from GSI-TopicShelf: {len(_curriculum(table)) - 2}" in out


def test_a_row_rewritten_meanwhile_is_skipped(table: ReadCountingTable) -> None:
    planned = backfill.plan(backfill.curriculum_rows(table))
    row, _expected = next(
        (row, expected) for row, expected in planned.writes if row["SK"].startswith("LESSON#")
        and "topic_id" in row
    )
    # A publish moves the lesson to another topic between the read and the write.
    table.rows[(row["PK"], row["SK"])]["topic_id"] = "elsewhere"

    outcome = backfill.apply(table, planned)

    assert outcome["changed meanwhile, skipped"] == 1
    assert outcome["written"] == len(planned.writes) - 1
    assert "topic_shelf" not in table.rows[(row["PK"], row["SK"])]
    assert backfill.plan(_curriculum(table)).writes == [
        (table.rows[(row["PK"], row["SK"])], practice_repo.topic_shelf_fields(
            table.rows[(row["PK"], row["SK"])]
        ))
    ]
