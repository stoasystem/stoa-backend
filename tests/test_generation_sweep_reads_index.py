"""The generation sweep reads its commands from `GSI-SweepPending` (#502).

It used to find them with a filtered scan of the whole of `stoa-main`, which
the published curriculum made too long for one run (#496); #500 kept a cursor
so successive runs covered the table, but a pass still took longer the larger
the table grew. The sweep now queries the sparse index, which holds only the
commands it may act on, for those due by now, earliest due first. What a run
reads follows how many commands are waiting, not how large the table is, and
there is no place to keep between runs.

These run the real worker, store and sweep against the shared table double.
Only the model call and the entitlement read are replaced.
"""

from __future__ import annotations

import functools
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fakes.ask_question import _command_key, _command_row, _commit
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.dynamodb import FakeTable
from stoa.jobs import conversation_generation
from stoa.services.ask_question import _store


def _sweep() -> dict[str, Any]:
    return conversation_generation.handler(
        {"source": "stoa.scheduler", "job": "conversation_generation_sweep"}, None
    )


def _lost_question(table, key: str, *, minutes_ago: float = 2) -> None:
    """A question whose direct invoke never arrived, committed `minutes_ago`."""
    _commit(key)
    row = dict(_command_row(table, key))
    assert row["status"] == "message_committed"
    row["message_committed_at"] = (
        datetime.now(UTC) - timedelta(minutes=minutes_ago)
    ).isoformat()
    table.seed(row)


def _fill(table, rows: int) -> None:
    """Rows of everything else the table holds: published curriculum, say."""
    table.seed(
        *(
            {"PK": f"A#{index:06d}", "SK": "CONTENT", "entity_type": "practice_content"}
            for index in range(rows)
        )
    )


def _finding_reads(table) -> list[tuple[str, dict[str, Any]]]:
    """The reads one sweep run makes to find its commands.

    Scans of any kind, and queries of the sweep's index. Answering a question
    reads its conversation too, which grows with the conversation and has
    nothing to do with how the sweep finds it.
    """
    table.requests.clear()
    summary = _sweep()
    assert summary["completed"] == 1
    return [
        (operation, request)
        for operation, request in table.requests
        if operation == "scan"
        or (operation == "query" and request.get("IndexName") == _store.SWEEP_PENDING_INDEX)
    ]


def test_the_sweeps_reads_do_not_grow_with_the_table(table, model) -> None:
    """The same lost question is found with the same reads beside 0 rows and 3,000."""
    table.page_item_cap = 10
    _lost_question(table, "small")
    small = _finding_reads(table)

    _fill(table, 3_000)
    _lost_question(table, "large")
    large = _finding_reads(table)

    # One query of the index each time; a scan of the filler alone would be
    # 300 pages at ten rows a page.
    assert [operation for operation, _ in small] == ["query"]
    assert [operation for operation, _ in large] == ["query"]
    assert _command_row(table, "large")["status"] == "completed"


def test_a_lost_question_is_answered_by_the_first_run_however_long_the_table(
    table, model
) -> None:
    """#496 put a lost question past the pages one run read; now nothing is past it."""
    _fill(table, 3_000)
    table.page_item_cap = 10
    _lost_question(table, "key-1")

    summary = _sweep()

    assert summary["completed"] == 1
    assert summary["read_all"] is True
    assert _command_row(table, "key-1")["status"] == "completed"


def test_a_command_is_read_only_once_it_is_due(table) -> None:
    _commit("fresh")
    committed = datetime.fromisoformat(
        str(_command_row(table, "fresh")["message_committed_at"])
    )

    early, early_complete = _store.query_generation_sweep_commands(now=committed)
    due, _ = _store.query_generation_sweep_commands(
        now=committed + _store.UNCLAIMED_AFTER + timedelta(seconds=1)
    )

    assert early == [] and early_complete is True
    assert [command["idempotency_key"] for command in due] == ["fresh"]


def test_commands_come_earliest_due_first(table) -> None:
    for key, minutes_ago in (("newer", 3), ("oldest", 9), ("older", 6)):
        _lost_question(table, key, minutes_ago=minutes_ago)

    commands, complete = _store.query_generation_sweep_commands(now=datetime.now(UTC))

    assert complete is True
    assert [command["idempotency_key"] for command in commands] == [
        "oldest",
        "older",
        "newer",
    ]


def test_a_run_stops_at_its_page_limit_and_the_next_reads_the_rest(
    table, model, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _lost_question(table, "first", minutes_ago=3)
    _lost_question(table, "second", minutes_ago=2)
    table.page_item_cap = 1
    monkeypatch.setattr(
        _store,
        "query_generation_sweep_commands",
        functools.partial(_store.query_generation_sweep_commands, max_pages=1),
    )

    with caplog.at_level(logging.WARNING):
        first_run = _sweep()

    assert first_run["read_all"] is False
    assert first_run["completed"] == 1
    assert "conversation_generation_sweep_page_limit" in caplog.text
    assert _command_row(table, "first")["status"] == "completed"
    # Answered, it left the index, so the next run's one page is the other.
    second_run = _sweep()
    assert second_run["completed"] == 1
    assert _command_row(table, "second")["status"] == "completed"


def test_an_entry_a_write_left_behind_costs_a_read_and_nothing_else(table, model) -> None:
    """The risk the issue names: a transition that forgot to remove the attributes."""
    _lost_question(table, "key-1")
    _sweep()
    row = dict(_command_row(table, "key-1"))
    assert row["status"] == "completed"
    # Planted past the shared double, which would tidy it as the writes do.
    FakeTable.seed(
        table,
        {
            **row,
            "sweep_bucket": _store.SWEEP_PENDING_BUCKET,
            "sweep_due_at": _store.sweep_due_at(datetime.now(UTC) - timedelta(minutes=5)),
        },
    )
    before = dict(_command_row(table, "key-1"))

    summary = _sweep()

    assert summary["candidates"] == 0 and summary["completed"] == 0
    assert dict(_command_row(table, "key-1")) == before


def test_no_place_is_kept_between_runs(table, model) -> None:
    """The cursor row #500 kept is gone; nothing is written for the sweep itself."""
    _lost_question(table, "key-1")
    _sweep()

    assert ("JOB#conversation_generation", "SCAN_CURSOR") not in table.rows
    assert not hasattr(_store, "scan_generation_sweep_commands")
    assert not hasattr(_store, "get_generation_sweep_place")
    assert tuple(_command_key("conv-1", "key-1").values()) in table.rows
