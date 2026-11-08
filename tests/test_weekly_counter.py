"""每周计数: the rules every weekly counter keeps, proven once (#244).

The token allowance and the teacher-help count each keep a counter row per
scope and Zurich week; what a row is, how it is read back, and how two writers
are kept from both winning is `weekly_counter`'s, so it is tested here and not
again by each caller.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import threading
from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from stoa.db import table as db_table
from stoa.db.repositories import weekly_counter
from stoa.db.repositories.weekly_counter import CASES, TOKENS, CounterConflict, CounterUnavailable
from stoa.models.allowance import MAX_EXACT_COUNT

NOW = datetime(2026, 3, 25, 12, tzinfo=UTC)
WEEK = weekly_counter.zurich_week(NOW)


def _commit(table: FakeTable, operation: dict[str, Any]) -> None:
    db_table.transact([operation], table=table)


def _seeded(table: FakeTable, kind=TOKENS, scope: str = "student-1", **counts: int) -> weekly_counter.Counter:
    _commit(table, weekly_counter.write(kind, scope, WEEK, None, counts=counts, at=NOW))
    counter = weekly_counter.read(kind, scope, WEEK, table=table)
    assert counter is not None
    return counter


# ── The week ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("instant", "start", "end", "hours"),
    [
        # Summer time starts in the week of 23 March 2026: 167 hours long.
        (
            datetime(2026, 3, 25, 12, tzinfo=UTC),
            "2026-03-22T23:00:00+00:00",
            "2026-03-29T22:00:00+00:00",
            167,
        ),
        # It ends in the week of 19 October 2026: 169 hours long.
        (
            datetime(2026, 10, 21, 12, tzinfo=UTC),
            "2026-10-18T22:00:00+00:00",
            "2026-10-25T23:00:00+00:00",
            169,
        ),
    ],
)
def test_a_week_runs_monday_to_monday_in_zurich_across_summer_time(
    instant: datetime, start: str, end: str, hours: int
) -> None:
    week = weekly_counter.zurich_week(instant)

    assert week.window_start.isoformat() == start
    assert week.window_end.isoformat() == end
    assert (week.window_end - week.window_start) == timedelta(hours=hours)


@pytest.mark.parametrize(
    ("instant", "identity"),
    [
        ("2026-03-29T21:59:59+00:00", "2026-W13"),
        ("2026-03-29T22:00:00+00:00", "2026-W14"),
        ("2027-01-01T12:00:00+00:00", "2026-W53"),
    ],
)
def test_a_week_is_named_by_its_iso_week(instant: str, identity: str) -> None:
    assert weekly_counter.zurich_week(datetime.fromisoformat(instant)).identity == identity


def test_a_week_needs_a_timezone() -> None:
    with pytest.raises(ValueError):
        weekly_counter.zurich_week(datetime(2026, 3, 25, 12))


def test_the_next_week_starts_without_a_counter() -> None:
    table = FakeTable()
    _seeded(table, reserved_input_tokens=30_000)

    next_week = weekly_counter.zurich_week(NOW + timedelta(days=7))

    assert weekly_counter.read(TOKENS, "student-1", next_week, table=table) is None


# ── Writing ───────────────────────────────────────────────────────────────────


def test_a_new_counter_starts_at_version_one_with_every_count_at_zero() -> None:
    table = FakeTable()

    counter = _seeded(table, reserved_input_tokens=90)

    assert counter.state_version == 1
    assert counter.count("reserved_input_tokens") == 90
    assert all(counter.count(field) == 0 for field in TOKENS.count_fields if field != "reserved_input_tokens")
    assert counter.item["PK"] == "ALLOWANCE#student-1"
    assert counter.item["SK"] == f"WEEK#{WEEK.identity}"
    assert counter.item["beneficiary_id"] == "student-1"
    assert counter.item["created_at"] == counter.item["updated_at"] == NOW.isoformat()


def test_each_kind_keeps_its_own_partition_and_scope_field() -> None:
    table = FakeTable()

    cases = _seeded(table, CASES, scope="scope-1", admitted_cases=1)

    assert cases.item["PK"] == "TEACHER_SUPPORT#scope-1"
    assert cases.item["support_scope_id"] == "scope-1"
    assert "beneficiary_id" not in cases.item


def test_a_counter_is_created_only_once() -> None:
    table = FakeTable()
    _seeded(table, reserved_input_tokens=1)

    with pytest.raises(Exception):
        _commit(table, weekly_counter.write(TOKENS, "student-1", WEEK, None, counts={}, at=NOW))


def test_a_replacement_needs_the_version_it_was_read_at() -> None:
    table = FakeTable()
    first = _seeded(table, reserved_input_tokens=1)
    _commit(table, weekly_counter.write(TOKENS, "student-1", WEEK, first, counts={"reserved_input_tokens": 2}, at=NOW))

    with pytest.raises(Exception):
        _commit(
            table,
            weekly_counter.write(TOKENS, "student-1", WEEK, first, counts={"reserved_input_tokens": 3}, at=NOW),
        )
    counter = weekly_counter.read(TOKENS, "student-1", WEEK, table=table)
    assert counter is not None
    assert counter.state_version == 2
    assert counter.count("reserved_input_tokens") == 2


def test_of_two_writers_of_the_same_version_only_one_wins() -> None:
    table = FakeTable()
    read = _seeded(table, reserved_input_tokens=0)
    start = threading.Barrier(2)

    def write(amount: int) -> bool:
        start.wait()
        try:
            _commit(
                table,
                weekly_counter.write(
                    TOKENS, "student-1", WEEK, read, counts={"reserved_input_tokens": amount}, at=NOW
                ),
            )
        except Exception:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        won = list(pool.map(write, (10, 20)))

    assert sorted(won) == [False, True]
    counter = weekly_counter.read(TOKENS, "student-1", WEEK, table=table)
    assert counter is not None and counter.state_version == 2


def test_a_replacement_keeps_created_at_and_the_callers_fields() -> None:
    table = FakeTable()
    _commit(
        table,
        weekly_counter.write(TOKENS, "student-1", WEEK, None, counts={}, fields={"plan_id": "free_trial"}, at=NOW),
    )
    first = weekly_counter.read(TOKENS, "student-1", WEEK, table=table)
    assert first is not None
    later = NOW + timedelta(hours=1)

    _commit(table, weekly_counter.write(TOKENS, "student-1", WEEK, first, counts={"reserved_input_tokens": 5}, at=later))

    counter = weekly_counter.read(TOKENS, "student-1", WEEK, table=table)
    assert counter is not None
    assert counter.item["created_at"] == NOW.isoformat()
    assert counter.item["updated_at"] == later.isoformat()
    assert counter.item["plan_id"] == "free_trial"


def test_a_row_without_created_at_is_read_and_stays_without_it() -> None:
    """Teacher-help counters written before #245 lost `created_at` on update."""
    table = FakeTable()
    counter = _seeded(table, CASES, scope="scope-1", admitted_cases=1)
    row = dict(counter.item)
    del row["created_at"]
    table.seed(row)

    read = weekly_counter.read(CASES, "scope-1", WEEK, table=table)
    assert read is not None
    _commit(table, weekly_counter.write(CASES, "scope-1", WEEK, read, counts={"admitted_cases": 2}, at=NOW))

    again = weekly_counter.read(CASES, "scope-1", WEEK, table=table)
    assert again is not None
    assert again.count("admitted_cases") == 2
    assert "created_at" not in again.item


@pytest.mark.parametrize(
    "counts",
    [{"admitted_cases": 1}, {"reserved_input_tokens": -1}, {"reserved_input_tokens": MAX_EXACT_COUNT + 1}],
)
def test_a_write_refuses_counts_that_are_not_this_kinds_or_out_of_range(counts: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        weekly_counter.write(TOKENS, "student-1", WEEK, None, counts=counts, at=NOW)


def test_a_write_refuses_fields_that_would_overwrite_the_counters_own() -> None:
    with pytest.raises(ValueError):
        weekly_counter.write(TOKENS, "student-1", WEEK, None, counts={}, fields={"state_version": 9}, at=NOW)


# ── Reading ───────────────────────────────────────────────────────────────────


def test_counts_stored_as_decimals_are_read_as_whole_numbers() -> None:
    table = FakeTable()
    counter = _seeded(table, reserved_input_tokens=7)
    table.seed({**counter.item, "reserved_input_tokens": Decimal(7), "state_version": Decimal(1)})

    read = weekly_counter.read(TOKENS, "student-1", WEEK, table=table)

    assert read is not None
    assert read.count("reserved_input_tokens") == 7 and read.state_version == 1


@pytest.mark.parametrize(
    "damage",
    [
        {"entity_type": "teacher_support_counter"},
        {"schema_version": "allowance_counter.v0"},
        {"beneficiary_id": "student-2"},
        {"week_identity": "2026-W12"},
        {"window_start": "2026-03-23T00:00:00+00:00"},
        {"reserved_input_tokens": -1},
        {"reserved_input_tokens": Decimal("1.5")},
        {"reserved_input_tokens": True},
        {"reserved_input_tokens": "1"},
        {"state_version": 0},
    ],
)
def test_a_damaged_row_is_refused(damage: dict[str, object]) -> None:
    table = FakeTable()
    counter = _seeded(table, reserved_input_tokens=1)
    table.seed({**counter.item, **damage})

    with pytest.raises(CounterUnavailable):
        weekly_counter.read(TOKENS, "student-1", WEEK, table=table)


def test_a_row_under_another_key_is_refused() -> None:
    counter = _seeded(FakeTable(), reserved_input_tokens=1)

    with pytest.raises(CounterUnavailable):
        weekly_counter.validate(TOKENS, {**counter.item, "SK": "WEEK#2026-W12"}, scope_id="student-1", week=WEEK)


def test_a_table_that_cannot_be_read_is_unavailable() -> None:
    class Down:
        def get_item(self, **_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("down")

    with pytest.raises(CounterUnavailable):
        weekly_counter.read(TOKENS, "student-1", WEEK, table=Down())


# ── Retrying ──────────────────────────────────────────────────────────────────


def test_an_attempt_that_loses_a_race_runs_again() -> None:
    attempts: list[int] = []

    def attempt() -> str:
        attempts.append(len(attempts))
        if len(attempts) < 3:
            raise CounterConflict()
        return "written"

    assert weekly_counter.retry(attempt, exhausted="gave up") == "written"
    assert len(attempts) == 3


def test_four_lost_races_give_the_callers_answer() -> None:
    attempts: list[int] = []

    def attempt() -> str:
        attempts.append(1)
        raise CounterConflict()

    assert weekly_counter.retry(attempt, exhausted="gave up") == "gave up"
    assert len(attempts) == weekly_counter.DEFAULT_ATTEMPTS == 4


def test_any_other_failure_is_not_retried() -> None:
    attempts: list[int] = []

    def attempt() -> str:
        attempts.append(1)
        raise RuntimeError("not a race")

    with pytest.raises(RuntimeError):
        weekly_counter.retry(attempt, exhausted="gave up")
    assert len(attempts) == 1
