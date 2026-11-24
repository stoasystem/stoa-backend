"""The scheduled deletion job finds its commands in the pending registry, and only there (#611).

Discovery used to walk the whole table with a stored cursor (#7), about 2,500
rows every five minutes, to find deletion commands; since #397 every accepted
command has a row in `ACCOUNT_DELETION_PENDING`, and the walk was kept only for
the commands accepted before that. Production held none on 2026-11-24, so the
walk, its cursor row and the registry backfill are gone: a run reads the
registry partition and each command it names, by key, whatever the table's size.

These tests run the real repository against the shared table double.
"""

from __future__ import annotations

from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo
from stoa.jobs import account_deletion as job


def _unrelated(count: int) -> list[dict[str, Any]]:
    return [
        {"PK": f"ROW#{index:05d}", "SK": "DATA", "entity_type": "unrelated"}
        for index in range(count)
    ]


def _command(command_id: str, *, user: str = "late", registered: bool = True) -> list[dict[str, Any]]:
    """A pending command and, as the accepting transaction writes it, its registry row."""
    rows: list[dict[str, Any]] = [
        {
            "PK": f"USER#{user}",
            "SK": f"DELETE_COMMAND#{command_id}",
            "entity_type": "account_deletion_command",
            "command_id": command_id,
            "user_id": user,
            "generation": 1,
            "status": "pending",
            "version": 1,
        }
    ]
    if registered:
        rows.append(
            {
                **account_deletion_repo.pending_registry_key(user, command_id),
                "entity_type": "account_deletion_pending",
                "deletion_user_id": user,
                "deletion_command_id": command_id,
            }
        )
    return rows


class _Worker:
    def __init__(self, *, failing: frozenset[str] = frozenset()) -> None:
        self.continued: list[str] = []
        self.failing = failing

    def continue_command(self, claim: account_deletion_repo.DeletionCommandClaim) -> None:
        if claim.command_id in self.failing:
            raise RuntimeError("the worker died")
        self.continued.append(claim.command_id)


@pytest.fixture
def table() -> FakeTable:
    built = FakeTable()
    db_table.install(built)
    return built


def _run(worker: _Worker, **kwargs: Any) -> job.DeletionJobSummary:
    return job.run_pending_deletions(service_factory=lambda: worker, **kwargs)


def _operations(table: FakeTable) -> set[str]:
    return {operation for operation, _request in table.requests}


# ── Discovery is the registry's query ─────────────────────────────────────────


def test_a_registered_command_is_found_wherever_its_row_is_and_nothing_is_scanned(
    table: FakeTable,
) -> None:
    table.seed(*_unrelated(3_000), *_command("late-command"))
    worker = _Worker()

    summary = _run(worker)

    assert worker.continued == ["late-command"]
    assert summary == job.DeletionJobSummary(discovered=1, claimed=1, continued=1, retryable=0)
    assert "scan" not in _operations(table)


def test_a_run_with_nothing_registered_reads_one_partition_and_writes_nothing(
    table: FakeTable,
) -> None:
    table.seed(*_unrelated(50))
    before = dict(table.rows)

    summary = _run(_Worker())

    assert summary == job.DeletionJobSummary()
    assert _operations(table) == {"query"}
    assert table.rows == before
    # The cursor row of the old walk is neither read nor written.
    assert ("JOB#account_deletion", "SCAN_CURSOR") not in table.rows


def test_a_command_without_a_registry_row_is_not_looked_for(table: FakeTable) -> None:
    """What the removed walk was for. Every accepting transaction writes the row."""
    table.seed(*_command("unregistered", registered=False))
    worker = _Worker()

    summary = _run(worker)

    assert worker.continued == []
    assert summary.discovered == 0
    assert account_deletion_repo.list_pending_deletions() == []


def test_a_registry_row_whose_command_is_finished_is_dropped(table: FakeTable) -> None:
    command, registry = _command("finished")
    table.seed({**command, "status": "complete"}, registry)

    summary = _run(_Worker())

    assert summary.discovered == 0
    assert account_deletion_repo.list_pending_deletions() == []


# ── A command that fails is the next run's ────────────────────────────────────


def test_a_command_that_fails_is_counted_logged_and_tried_again_next_run(
    table: FakeTable, caplog: pytest.LogCaptureFixture
) -> None:
    table.seed(*_command("a-fails", user="a"), *_command("b-works", user="b"))
    worker = _Worker(failing=frozenset({"a-fails"}))

    first = _run(worker)

    # One command's failure does not cost the other its turn.
    assert worker.continued == ["b-works"]
    assert first.discovered == 2 and first.claimed == 2 and first.retryable == 1
    assert "account_deletion_command_failed command_id=a-fails" in caplog.text
    assert {entry.command_id for entry in account_deletion_repo.list_pending_deletions()} == {
        "a-fails",
        "b-works",
    }


def test_a_claim_lost_to_another_run_is_not_a_failure(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    table.seed(*_command("held"))
    monkeypatch.setattr(account_deletion_repo, "claim_deletion_command", lambda *_a, **_k: None)
    worker = _Worker()

    summary = _run(worker)

    assert worker.continued == []
    assert summary == job.DeletionJobSummary(discovered=1, claimed=0, continued=0, retryable=0)


def test_a_registry_that_cannot_be_read_is_reported_not_an_empty_success(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    table.seed(*_command("waiting"))

    def unavailable(**_kwargs: Any) -> Any:
        raise account_deletion_repo.AccountDeletionConflict("pending deletion registry unavailable")

    monkeypatch.setattr(account_deletion_repo, "list_pending_deletions", unavailable)

    summary = _run(_Worker())

    assert summary == job.DeletionJobSummary(discovered=0, claimed=0, continued=0, retryable=1)
    assert "account_deletion_registry_unavailable" in caplog.text


def test_a_command_that_cannot_be_read_is_reported_and_the_others_go_on(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    table.seed(*_command("unreadable", user="a"), *_command("fine", user="b"))
    load = account_deletion_repo.get_deletion_command

    def flaky(user_id: str, command_id: str, **kwargs: Any) -> Any:
        if command_id == "unreadable":
            raise account_deletion_repo.AccountDeletionConflict("dependency unavailable")
        return load(user_id, command_id, **kwargs)

    monkeypatch.setattr(account_deletion_repo, "get_deletion_command", flaky)
    worker = _Worker()

    summary = _run(worker)

    assert worker.continued == ["fine"]
    assert summary.discovered == 1 and summary.retryable == 1
    assert "account_deletion_registry_read_failed command_id=unreadable" in caplog.text


# ── One run's bounds ──────────────────────────────────────────────────────────


def test_one_run_takes_on_at_most_its_limit_and_says_more_is_waiting(table: FakeTable) -> None:
    for index in range(4):
        table.seed(*_command(f"c-{index}", user=f"u-{index}"))
    worker = _Worker()

    summary = _run(worker, limit=3)

    assert len(worker.continued) == 3
    assert summary.discovered == 4 and summary.claimed == 3 and summary.retryable == 1


def test_a_run_short_of_time_claims_no_further_command(table: FakeTable) -> None:
    table.seed(*_command("a", user="a"), *_command("b", user="b"))
    worker = _Worker()

    summary = _run(worker, remaining_seconds=lambda: job.MIN_REMAINING_SECONDS - 1)

    assert worker.continued == []
    assert summary == job.DeletionJobSummary(discovered=2, claimed=0, continued=0, retryable=1)


# ── A repository without a method the run calls is refused, not humoured ─────


class _RecordingRepository:
    """A repository double that records every call it receives."""

    def __init__(self, *, omit: str) -> None:
        self.calls: list[str] = []
        self._omit = omit

    def __getattr__(self, name: str) -> Any:
        if name == self._omit or name not in _REQUIRED_METHODS:
            raise AttributeError(name)

        def record(*_args: Any, **_kwargs: Any) -> Any:
            self.calls.append(name)
            raise AssertionError(f"{name} must not be reached")

        return record


_REQUIRED_METHODS = (
    "list_pending_deletions",
    "get_deletion_command",
    "claim_deletion_command",
)


def test_the_required_methods_are_the_ones_the_job_names() -> None:
    assert _REQUIRED_METHODS == job._REQUIRED_REPOSITORY_METHODS


@pytest.mark.parametrize("missing", _REQUIRED_METHODS)
def test_a_repository_missing_a_method_is_refused_before_any_read_or_claim(
    missing: str,
) -> None:
    repository = _RecordingRepository(omit=missing)

    with pytest.raises(account_deletion_repo.AccountDeletionConflict, match=missing):
        job.run_pending_deletions(repository=repository, service_factory=_Worker)

    assert repository.calls == []


def test_the_scan_its_cursor_and_the_registry_backfill_are_gone() -> None:
    for name in (
        "scan_pending_deletion_commands",
        "get_deletion_scan_cursor",
        "advance_deletion_scan_cursor",
        "register_pending_deletion",
        "DELETION_SCAN_CURSOR_KEY",
    ):
        assert not hasattr(account_deletion_repo, name), name
    assert not hasattr(job, "_backfill_registry")


# ── The claim is the table's, never a same-named method's (ticket 13, E23) ────


class _LookalikeTable:
    """A table double that answers the job's calls by name, not as a table.

    It has no `update_item`. The repository used to hand the claim to such
    same-named methods, so a double could replace their semantics without
    anything noticing.
    """

    def __init__(self) -> None:
        self.adopted: list[str] = []

    def claim_deletion_command(self, *_args: Any, **_kwargs: Any) -> Any:
        self.adopted.append("claim_deletion_command")
        return None

    def renew_deletion_command_claim(self, *_args: Any, **_kwargs: Any) -> Any:
        self.adopted.append("renew_deletion_command_claim")
        return None


def test_a_table_that_only_answers_by_name_is_refused_for_the_claim() -> None:
    table = _LookalikeTable()
    command = {
        "PK": "USER#student-1",
        "SK": "DELETE_COMMAND#c-1",
        "command_id": "c-1",
        "generation": 1,
        "version": 1,
    }

    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        account_deletion_repo.claim_deletion_command(
            command,
            lease_owner="sweep-1",
            now_epoch=1_000,
            lease_expires_at=1_300,
            now_iso="2026-09-25T08:00:00+00:00",
            table=table,
        )

    assert table.adopted == []


def test_a_table_that_only_answers_by_name_is_refused_for_the_renewal() -> None:
    """The renewal keeps the claim alive, so it is the claim's to guard too."""
    table = _LookalikeTable()
    command = {
        "PK": "USER#student-1",
        "SK": "DELETE_COMMAND#c-1",
        "command_id": "c-1",
        "generation": 1,
        "version": 2,
    }
    claim = account_deletion_repo.DeletionCommandClaim(
        command_id="c-1",
        generation=1,
        lease_owner="sweep-1",
        lease_expires_at=1_300,
        command_version=2,
        branch_results_digest=account_deletion_repo.branch_results_digest({}),
    )

    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        account_deletion_repo.renew_deletion_command_claim(
            command,
            claim=claim,
            now_epoch=1_100,
            lease_expires_at=1_400,
            now_iso="2026-09-25T08:00:00+00:00",
            table=table,
        )

    assert table.adopted == []
