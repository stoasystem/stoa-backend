"""The scheduled deletion sweep keeps its place between runs (#7).

Each run used to start its scan from the top of the table and stop after 100
pages. `Limit` counts rows read, not commands found, so on a table of any size
a command that lived past the first 2,500 rows was never reached by the
schedule. The sweep now stores where it stopped in one control row, guarded by
a version, and the next run carries on from there.

These tests run the real repository against the shared table double, whose
scan applies `Limit` before the filter and whose conditions are evaluated.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from stoa.db.repositories import account_deletion_repo
from stoa.jobs import account_deletion as job


BUDGET_ROWS = 100 * 25  # pages per run x rows per page at the scheduled limit


def _unrelated(count: int) -> list[dict[str, Any]]:
    return [
        {"PK": f"ROW#{index:05d}", "SK": "DATA", "entity_type": "unrelated"}
        for index in range(count)
    ]


def _command(command_id: str, *, user: str = "late") -> dict[str, Any]:
    return {
        "PK": f"USER#{user}",
        "SK": f"DELETE_COMMAND#{command_id}",
        "entity_type": "account_deletion_command",
        "command_id": command_id,
        "user_id": user,
        "generation": 1,
        "status": "pending",
        "version": 1,
    }


class _Worker:
    def __init__(self) -> None:
        self.continued: list[str] = []

    def continue_command(self, claim: account_deletion_repo.DeletionCommandClaim) -> None:
        self.continued.append(claim.command_id)


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    built = FakeTable()
    monkeypatch.setattr(account_deletion_repo, "get_table", lambda: built)
    return built


def _run(worker: _Worker, limit: int = 25) -> job.DeletionJobSummary:
    return job.run_pending_deletions(service_factory=lambda: worker, limit=limit)


def _scan_starts(table: FakeTable) -> list[dict[str, str] | None]:
    return [
        request.get("ExclusiveStartKey")
        for operation, request in table.requests
        if operation == "scan"
    ]


def _stored() -> account_deletion_repo.DeletionScanCursor:
    return account_deletion_repo.get_deletion_scan_cursor()


def test_a_command_beyond_one_runs_budget_is_found_by_the_next_run(table: FakeTable) -> None:
    table.seed(*_unrelated(2_600), _command("late-command"))
    worker = _Worker()

    first = _run(worker)
    assert first.discovered == 0
    assert first.retryable == 1  # the run stopped short and says so
    assert _stored().cursor == {"PK": f"ROW#{BUDGET_ROWS - 1:05d}", "SK": "DATA"}

    second = _run(worker)
    assert second.discovered == 1 and second.claimed == 1
    assert worker.continued == ["late-command"]
    assert _scan_starts(table)[100] == {"PK": f"ROW#{BUDGET_ROWS - 1:05d}", "SK": "DATA"}


def test_pages_with_no_command_on_them_do_not_end_the_run(table: FakeTable) -> None:
    table.seed(*_unrelated(300), _command("after-empty-pages"))
    worker = _Worker()

    summary = _run(worker)

    assert worker.continued == ["after-empty-pages"]
    assert summary.retryable == 0
    assert len(_scan_starts(table)) == 13  # twelve empty pages, then the command


def test_reaching_the_end_starts_the_next_cycle_from_the_top(table: FakeTable) -> None:
    table.seed(*_unrelated(2_600), _command("late-command"))
    worker = _Worker()
    _run(worker)
    before = _stored().version

    _run(worker)
    after_cycle = _stored()
    assert after_cycle.cursor is None
    assert after_cycle.version == before + 1
    assert after_cycle.cycle_started_at is None

    scans_so_far = len(_scan_starts(table))
    _run(worker)
    assert _scan_starts(table)[scans_so_far] is None
    assert _stored().cycle_started_at is not None


def test_a_late_write_from_before_the_reset_is_refused(table: FakeTable) -> None:
    table.seed(*_unrelated(2_600))
    worker = _Worker()
    _run(worker)
    stale = _stored()
    _run(worker)  # reaches the end and resets
    assert _stored().cursor is None

    written = account_deletion_repo.advance_deletion_scan_cursor(
        expected_version=stale.version,
        cursor={"PK": "ROW#00100", "SK": "DATA"},
        cycle_started_at=stale.cycle_started_at,
        updated_at="2026-09-24T10:00:00+00:00",
    )

    assert written is False
    assert _stored().cursor is None


def test_a_run_that_dies_after_scanning_leaves_the_stored_place_alone(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    table.seed(*_unrelated(6_000))
    worker = _Worker()
    _run(worker)
    saved = _stored()
    assert saved.cursor is not None

    def interrupted(**_kwargs: Any) -> bool:
        raise RuntimeError("the invocation ended here")

    monkeypatch.setattr(account_deletion_repo, "advance_deletion_scan_cursor", interrupted)
    with pytest.raises(RuntimeError):
        _run(worker)
    assert _stored() == saved

    monkeypatch.undo()
    monkeypatch.setattr(account_deletion_repo, "get_table", lambda: table)
    scans_so_far = len(_scan_starts(table))
    _run(worker)
    assert _scan_starts(table)[scans_so_far] == saved.cursor


def test_two_overlapping_runs_store_only_one_place(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    table.seed(*_unrelated(30), _command("shared-command", user="early"))
    barrier = threading.Barrier(2)
    read = account_deletion_repo.get_deletion_scan_cursor
    advance = account_deletion_repo.advance_deletion_scan_cursor
    outcomes: list[bool] = []

    def read_together(**kwargs: Any) -> account_deletion_repo.DeletionScanCursor:
        state = read(**kwargs)
        barrier.wait(timeout=5)
        return state

    def record(**kwargs: Any) -> bool:
        written = advance(**kwargs)
        outcomes.append(written)
        return written

    monkeypatch.setattr(account_deletion_repo, "get_deletion_scan_cursor", read_together)
    monkeypatch.setattr(account_deletion_repo, "advance_deletion_scan_cursor", record)
    worker = _Worker()
    threads = [threading.Thread(target=_run, args=(worker,)) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes) == [False, True]
    assert read().version == 1
    assert worker.continued == ["shared-command"]  # the claim itself is conditional too


def test_a_malformed_stored_place_is_read_as_the_top_of_the_table(table: FakeTable) -> None:
    table.seed(
        {**account_deletion_repo.DELETION_SCAN_CURSOR_KEY, "cursor": "garbage", "version": 4},
        _command("first-command", user="early"),
    )
    worker = _Worker()

    _run(worker)

    assert _scan_starts(table)[0] is None
    assert worker.continued == ["first-command"]
    assert _stored().version == 5
