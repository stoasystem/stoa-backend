"""The one-off cleanup of the per-resource retention fences #655 stopped using.

Without a flag it counts and writes nothing; `--delete` alone says what a
delete would do and deletes nothing; `--delete --apply` deletes the fence rows
(`OWNER#<id>` / `RETENTION#RESOURCE#...`) and nothing else - not the account
fence, not another row of the table - and a row that stopped being a fence
between the scan and its delete is left.
"""

from __future__ import annotations

from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from scripts import delete_resource_retention_fences as cleanup


def _fence(owner: str, conversation: str, status: str = "complete") -> dict[str, Any]:
    return {
        "PK": f"OWNER#{owner}",
        "SK": f"RETENTION#RESOURCE#conversation#{conversation}",
        "entity_type": "attachment_retention_fence",
        "schema_version": "attachment-retention.v1",
        "owner_id": owner,
        "status": status,
        "generation": 1,
    }


OTHER_KIND = {
    "PK": "OWNER#s3",
    "SK": "RETENTION#RESOURCE#conversation#c9",
    "entity_type": "something_else",
}


@pytest.fixture
def table() -> FakeTable:
    table = FakeTable(page_item_cap=2)
    table.seed(
        _fence("s1", "c1"),
        _fence("s1", "c2", status="active"),
        _fence("s2", "c3"),
        OTHER_KIND,
        {
            "PK": "USER#s1", "SK": "ACCOUNT_FENCE", "entity_type": "account_fence",
            "user_id": "s1", "status": "deleted", "generation": 2,
        },
        {"PK": "OWNER#s1", "SK": "SOMETHING#ELSE", "entity_type": "unrelated"},
        {"PK": "ATTACHMENT#a1", "SK": "META", "entity_type": "attachment", "owner_id": "s1"},
    )
    return table


def _snapshot(table: FakeTable) -> dict[Any, dict[str, Any]]:
    return {key: dict(row) for key, row in table.rows.items()}


def test_counting_writes_nothing(table: FakeTable, capsys: pytest.CaptureFixture[str]) -> None:
    before = _snapshot(table)

    assert cleanup.run(table) == 0

    assert table.rows == before
    out = capsys.readouterr().out
    assert (
        "accounts: 3 | rows: 4 | fences: 3 | fence status complete: 2 | "
        "fence status active: 1 | other: something_else: 1"
    ) in out
    assert "[READ ONLY]" in out
    # Counted, never named.
    assert "s1" not in out and "c1" not in out


def test_a_dry_run_says_what_it_would_delete_and_deletes_nothing(
    table: FakeTable, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _snapshot(table)

    assert cleanup.run(table, delete_fences=True) == 0

    assert table.rows == before
    out = capsys.readouterr().out
    assert "would delete: 3 | left, not a fence: 1" in out
    assert "[DRY RUN]" in out


def test_apply_deletes_the_fences_and_nothing_else(
    table: FakeTable, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cleanup.run(table, delete_fences=True, apply_deletes=True) == 0

    assert sorted(table.rows) == [
        ("ATTACHMENT#a1", "META"),
        ("OWNER#s1", "SOMETHING#ELSE"),
        ("OWNER#s3", "RETENTION#RESOURCE#conversation#c9"),
        ("USER#s1", "ACCOUNT_FENCE"),
    ]
    out = capsys.readouterr().out
    assert "deleted: 3 | left, not a fence: 1" in out
    assert "After: accounts: 1 | rows: 1 | fences: 0 | other: something_else: 1" in out
    # A second run finds nothing left to delete.
    assert cleanup.run(table, delete_fences=True, apply_deletes=True) == 0


def test_a_row_that_stopped_being_a_fence_is_left(table: FakeTable) -> None:
    rows = cleanup.find(table)
    key = ("OWNER#s2", "RETENTION#RESOURCE#conversation#c3")
    table.rows[key] = {"PK": key[0], "SK": key[1], "entity_type": "something_else"}

    outcome = cleanup.delete(table, rows, apply_deletes=True)

    assert outcome == {"deleted": 2, "changed meanwhile, left": 1, "left, not a fence": 1}
    assert key in table.rows


def test_an_empty_table_reports_none(capsys: pytest.CaptureFixture[str]) -> None:
    assert cleanup.run(FakeTable(), delete_fences=True, apply_deletes=True) == 0

    out = capsys.readouterr().out
    assert "accounts: 0 | rows: 0 | fences: 0" in out
    assert "Nothing to delete." in out


def test_apply_needs_delete_and_the_profile_defaults_to_stoa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with pytest.raises(SystemExit):
        cleanup.parse_args(["--apply"])
    plain = cleanup.parse_args([])
    assert (plain.profile, plain.delete, plain.apply) == ("stoa", False, False)
    args = cleanup.parse_args(["--delete", "--apply"])
    assert args.delete and args.apply
