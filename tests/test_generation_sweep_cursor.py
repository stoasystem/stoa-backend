"""The generation sweep keeps its place between runs (#496).

The sweep finds its commands with a filtered scan of the whole table, at most
`GENERATION_SWEEP_MAX_PAGES` pages a run. Every run started at the top, and a
scan's order is fixed, so once the published curriculum made the table longer
than that, every run read the same first pages: a command further down was
never answered or settled by the sweep, and `scanned_to_end` stayed False.

The sweep now stores where it stopped in one control row guarded by a version,
as the deletion sweep does (#7), and the next run carries on from there. The
place is claimed before any command is acted on, so a run that dies leaves a
count behind; after `SLICE_ATTEMPT_LIMIT` such runs the slice is passed over
instead of read again for ever. A run that loses the claim to an overlapping
run leaves the slice to it.

These run the real worker, store and sweep against the shared table double,
whose scan pages are cut at a known row count. Only the model call and the
entitlement read are replaced.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fakes.ask_question import CONV, _command_row, _commit, _Killed
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from stoa.jobs import conversation_generation
from stoa.services import ask_question
from stoa.services.ask_question import _store

ROWS_PER_PAGE = 10
#: More than three runs' worth of pages, all before the conversation in scan order.
FILLER = ROWS_PER_PAGE * _store.GENERATION_SWEEP_MAX_PAGES * 2 + 300


def _sweep() -> dict[str, Any]:
    return conversation_generation.handler(
        {"source": "stoa.scheduler", "job": "conversation_generation_sweep"}, None
    )


def _place() -> _store.GenerationSweepPlace:
    return _store.get_generation_sweep_place()


def _lost_question(table, key: str = "key-1") -> None:
    """A question whose direct invoke never arrived, committed two minutes ago."""
    _commit(key)
    row = dict(_command_row(table, key))
    assert row["status"] == "message_committed"
    row["message_committed_at"] = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    table.seed(row)


@pytest.fixture
def long_table(table):
    """The conversation's rows after more pages than one run may read."""
    table.seed(
        *(
            {"PK": f"A#{index:06d}", "SK": "CONTENT", "entity_type": "practice_content"}
            for index in range(FILLER)
        )
    )
    table.page_item_cap = ROWS_PER_PAGE
    return table


def test_a_command_past_the_page_limit_is_reached_by_a_later_run(long_table, model) -> None:
    _lost_question(long_table)

    summaries = [_sweep() for _ in range(3)]

    assert [summary["scanned_to_end"] for summary in summaries] == [False, False, True]
    assert sum(summary["completed"] for summary in summaries) == 1
    assert _command_row(long_table, "key-1")["status"] == "completed"
    # The pass is complete; the next run starts again from the top.
    assert _place().cursor is None


def test_the_next_cycle_finds_a_command_written_behind_the_place(long_table, model) -> None:
    for _ in range(3):
        _sweep()
    _sweep()  # the next cycle has begun, past where the conversation is not
    _lost_question(long_table)

    summaries = [_sweep() for _ in range(3)]

    assert sum(summary["completed"] for summary in summaries) == 1


def test_a_run_that_dies_reads_its_slice_again(
    long_table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sweep()
    _sweep()
    _lost_question(long_table)
    before = _place()

    def killed(*_args: Any) -> str:
        raise _Killed

    monkeypatch.setattr(ask_question, "answer", killed)
    with pytest.raises(_Killed):
        _sweep()

    after_crash = _place()
    assert after_crash.cursor == before.cursor
    assert after_crash.attempts == 1
    monkeypatch.undo()
    monkeypatch.setattr(ask_question, "answer", ask_question.answer)

    summary = _sweep()

    assert summary["completed"] == 1
    assert summary["scanned_to_end"] is True
    assert _place().cursor is None
    assert _place().attempts == 0


def test_a_slice_that_kills_every_run_is_passed_over_not_read_for_ever(
    long_table, model, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _sweep()
    _sweep()
    _lost_question(long_table)
    stuck_at = _place().cursor

    def killed(*_args: Any) -> str:
        raise _Killed

    monkeypatch.setattr(ask_question, "answer", killed)
    for _ in range(_store.SLICE_ATTEMPT_LIMIT):
        with pytest.raises(_Killed):
            _sweep()
        assert _place().cursor == stuck_at

    # This run moves the place past the slice before it touches a command,
    # so dying again cannot hold it there.
    with pytest.raises(_Killed):
        _sweep()

    assert _place().cursor is None
    assert _place().attempts == 0
    assert "conversation_generation_sweep_slice_passed_over" in caplog.text


def test_overlapping_runs_neither_skip_nor_repeat_a_slice(
    long_table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second run starting while the first acts on the same slice."""
    _sweep()
    _sweep()
    _lost_question(long_table)
    start = _place()
    answer = ask_question.answer
    inner: list[dict[str, Any]] = []
    started: list[bool] = []

    def answer_while_another_run_starts(conversation_id: str, key: str) -> str:
        if not started:
            started.append(True)
            # The second run reads the place the first one claimed.
            inner.append(_sweep())
        return answer(conversation_id, key)

    monkeypatch.setattr(ask_question, "answer", answer_while_another_run_starts)

    outer = _sweep()

    assert inner[0]["scanned_to_end"] is True and outer["scanned_to_end"] is True
    assert inner[0]["completed"] + outer["completed"] == 1
    assert _command_row(long_table, "key-1")["status"] == "completed"
    # The place moved exactly one slice: to the top of the next cycle.
    place = _place()
    assert place.cursor is None
    assert place.version is not None and start.version is not None
    assert place.version > start.version


def test_a_run_that_read_an_older_place_cannot_overwrite_a_newer_one(long_table) -> None:
    _sweep()
    old = _place()
    _sweep()
    newer = _place()

    stored = _store.store_generation_sweep_place(
        expected_version=old.version,
        cursor=None,
        cycle_started_at=None,
        attempts=0,
        updated_at=datetime.now(UTC).isoformat(),
    )

    assert stored is False
    assert _place() == newer


def test_a_short_table_is_read_to_the_end_every_run(table, model) -> None:
    _lost_question(table)

    summary = _sweep()

    assert summary["scanned_to_end"] is True
    assert summary["completed"] == 1
    assert _place().cursor is None
    assert CONV
