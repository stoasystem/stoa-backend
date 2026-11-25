"""The account listing backfill puts profiles written before card 133 in GSI-Listing.

A dry run counts and writes nothing; `--apply` gives each profile with neither
key both, behind its fence and only while they are absent, and a second run
writes nothing; a tombstone, a profile with one key, an account being deleted
and a profile changed meanwhile are left alone; `--verify` finds every live
profile in the list.
"""

from __future__ import annotations

from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from scripts import backfill_account_listing_index as backfill
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, user_repo


def _legacy(user_id: str, *, created_at: str | None = "2026-01-01T00:00:00+00:00", **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": "student",
        "account_status": "active",
        "version": 3,
        **extra,
    }
    if created_at is not None:
        row["created_at"] = created_at
    return row


@pytest.fixture
def table(fake_table: FakeTable) -> FakeTable:
    for user_id in ("old-1", "old-2", "no-date", "listed", "half", "closing"):
        fake_table.seed_active_account(user_id)
    fake_table.seed(
        _legacy("old-1", created_at="2026-02-01T00:00:00+00:00"),
        _legacy("old-2", created_at="2026-03-01T00:00:00+00:00"),
        _legacy("no-date", created_at=None),
        {**_legacy("listed"), **account_deletion_repo.account_listing_fields(_legacy("listed"))},
        {**_legacy("half"), "listing": "account_profile"},
        _legacy("closing"),
        {
            "PK": "USER#gone",
            "SK": "PROFILE",
            "entity_type": "private_row_deletion_tombstone",
            "status": "deleted",
            "owner_deletion_generation": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {"PK": "PRACTICE", "SK": "CHALLENGE#1", "entity_type": "challenge"},
    )
    fake_table.rows[("USER#closing", "ACCOUNT_FENCE")]["status"] = "deletion_pending"
    return fake_table


def test_the_dry_run_counts_and_writes_nothing(table: FakeTable, capsys) -> None:
    before = {key: dict(row) for key, row in table.rows.items()}

    assert backfill.run(table, apply_writes=False, verify_index=False) == 0

    out = capsys.readouterr().out
    assert "profiles: 7 | tombstones: 1 | in place: 1 | one key only: 1 | to write: 4" in out
    assert "[DRY RUN]" in out
    assert table.rows == before
    assert table.calls["update_item"] == table.calls["transact_write_items"] == 0


def test_before_the_backfill_the_check_fails(table: FakeTable, capsys) -> None:
    assert backfill.run(table, apply_writes=False, verify_index=True) == 1


def test_apply_writes_each_missing_profile_once_and_nothing_else(table: FakeTable, capsys) -> None:
    untouched = {
        key: dict(table.rows[key])
        for key in (("USER#listed", "PROFILE"), ("USER#half", "PROFILE"), ("USER#gone", "PROFILE"))
    }

    assert backfill.run(table, apply_writes=True, verify_index=False) == 0

    out = capsys.readouterr().out
    assert "account closing, skipped: 1" in out
    assert "left alone: 3" in out
    assert "written: 3" in out
    assert table.rows[("USER#old-1", "PROFILE")]["listed_at"] == "2026-02-01T00:00:00+00:00"
    assert table.rows[("USER#old-1", "PROFILE")]["listing"] == "account_profile"
    assert table.rows[("USER#old-1", "PROFILE")]["version"] == 4
    assert table.rows[("USER#no-date", "PROFILE")]["listed_at"] == (
        account_deletion_repo.ACCOUNT_LISTED_AT_UNKNOWN
    )
    assert "listing" not in table.rows[("USER#closing", "PROFILE")]
    for key, row in untouched.items():
        assert table.rows[key] == row

    after_first = {key: dict(row) for key, row in table.rows.items()}
    assert backfill.run(table, apply_writes=True, verify_index=False) == 0
    assert "written" not in capsys.readouterr().out.replace("Nothing to write", "")
    assert table.rows == after_first


def test_after_the_backfill_every_live_profile_is_listed(table: FakeTable, capsys) -> None:
    backfill.run(table, apply_writes=True, verify_index=False)
    # The two the backfill leaves for a person: one key only, and a closing account.
    del table.rows[("USER#half", "PROFILE")]
    del table.rows[("USER#closing", "PROFILE")]
    capsys.readouterr()

    assert backfill.run(table, apply_writes=False, verify_index=True) == 0
    assert "Index problems: 0" in capsys.readouterr().out
    assert [p["user_id"] for p in user_repo.list_accounts(limit=10, table=table).profiles] == [
        "old-2", "old-1", "listed", "no-date",
    ]


def test_a_profile_changed_after_the_scan_is_skipped(table: FakeTable, capsys) -> None:
    items = backfill.all_profiles(table)
    table.rows[("USER#old-1", "PROFILE")]["version"] = 9

    outcome = backfill.apply(table, items)

    assert outcome["changed meanwhile, skipped"] == 1
    assert "listing" not in table.rows[("USER#old-1", "PROFILE")]


def test_the_writer_never_overwrites_keys_a_profile_gained_meanwhile(table: FakeTable) -> None:
    stale = dict(table.rows[("USER#old-1", "PROFILE")])
    table.rows[("USER#old-1", "PROFILE")]["listing"] = "account_profile"
    table.rows[("USER#old-1", "PROFILE")]["listed_at"] = "2030-01-01"

    with pytest.raises(db_table.WriteRefused):
        user_repo.add_listing_fields(stale, table=table)
    assert table.rows[("USER#old-1", "PROFILE")]["listed_at"] == "2030-01-01"
