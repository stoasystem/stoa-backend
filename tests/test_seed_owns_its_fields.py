"""The practice seed writes only the fields it owns, and stamps what it wrote.

stoa-backend#352 (step 1 of #317). The seed used to replace every row whole,
which wiped the star map positions `scripts/layout_starmap.py` writes onto the
same rows. Now each row kind lists the fields the seed owns: those with a value
are SET, those without one are REMOVEd, and nothing else on the row is touched.
A hash of everything the seed owns is recorded in `PRACTICE / CURRICULUM_SEED`
so a deploy can tell whether the table still holds what the repository seeds.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from scripts import layout_starmap, seed_practice

POSITION_FIELDS = seed_practice.POSITION_FIELDS


class _Session:
    """What `require_sso_operator_session` hands back, around one fake table."""

    def __init__(self, table: FakeTable) -> None:
        self._table = table

    def resource(self, _service: str, **_kwargs: Any) -> Any:
        table = self._table

        class _Resource:
            def Table(self, _name: str) -> FakeTable:  # noqa: N802 - boto3's name
                return table

        return _Resource()


def _run_seed(monkeypatch: pytest.MonkeyPatch, table: FakeTable, **kwargs: Any) -> None:
    monkeypatch.setattr(
        seed_practice, "require_sso_operator_session", lambda **_: _Session(table)
    )
    monkeypatch.setattr(seed_practice, "git_state", lambda: ("abc123", False))
    seed_practice.seed("stoa-test", "eu-central-2", **kwargs)


def _first_unit_sort_key() -> str:
    return next(
        row["SK"] for row in seed_practice.seed_rows() if row["SK"].startswith("UNIT#")
    )


def test_owned_fields_never_name_a_position_field() -> None:
    for kind, owned in seed_practice.SEED_OWNED_FIELDS.items():
        assert not owned & POSITION_FIELDS, kind


def test_position_fields_are_the_ones_the_layout_script_writes() -> None:
    """Every field after a row key in layout_starmap.py's "What it writes" table."""
    header = layout_starmap.__doc__ or ""
    table = header.split("What it writes:", 1)[1].split("Every coordinate", 1)[0]
    written = {
        field.strip().removesuffix("'s offset")
        for line in table.strip().splitlines()
        for field in line.split(None, 1)[1].split(",")
    }
    written.discard("unit_id")  # the SKILL# offset, not a field the seed writes
    assert written == POSITION_FIELDS


def test_every_seeded_row_carries_only_owned_fields() -> None:
    for knowledge_base in (None, "preview", "live"):
        for row in seed_practice.seed_rows(
            knowledge_base=knowledge_base, knowledge_base_prerequisites=True
        ):
            owned = seed_practice.SEED_OWNED_FIELDS[seed_practice.row_kind(row)]
            assert set(row) - {"PK", "SK"} <= owned, row["SK"]


def test_a_row_with_a_field_the_seed_does_not_own_is_refused() -> None:
    row = {"PK": "PRACTICE", "SK": "UNIT#u-1", "unit_id": "u-1", "x": 0.5}

    with pytest.raises(ValueError, match="does not own x"):
        seed_practice.seed_update(row)


def test_re_seeding_keeps_positions_and_updates_seed_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit_sk = _first_unit_sort_key()
    table = FakeTable()
    table.seed(
        {
            "PK": "PRACTICE", "SK": unit_sk, "title": "Stale title",
            "x": Decimal("0.25"), "y": Decimal("0.75"), "nebula_id": "nebula-1", "layout_version": "v1",
            "updated_by": "someone-else",
        },
        {
            "PK": "PRACTICE", "SK": "SUBJECT#mathematics", "name": "Old name",
            "layout_version": "v1", "starmap_layout": {"centres": {"a": [Decimal("0.1")]}},
        },
    )

    _run_seed(monkeypatch, table)
    _run_seed(monkeypatch, table)

    unit = table.rows[("PRACTICE", unit_sk)]
    expected = next(row for row in seed_practice.seed_rows() if row["SK"] == unit_sk)
    assert unit["title"] == expected["title"]
    assert (unit["x"], unit["y"], unit["nebula_id"], unit["layout_version"]) == (
        Decimal("0.25"), Decimal("0.75"), "nebula-1", "v1"
    )
    assert unit["updated_by"] == "someone-else"
    subject = table.rows[("PRACTICE", "SUBJECT#mathematics")]
    assert subject["name"] == seed_practice.SUBJECT["name"]
    assert subject["layout_version"] == "v1"
    assert subject["starmap_layout"] == {"centres": {"a": [Decimal("0.1")]}}


def test_an_owned_field_without_a_value_is_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ZAP unit has no description, so one left from an earlier seed goes."""
    zap_unit = next(
        row for row in seed_practice.seed_rows()
        if row["SK"].startswith("UNIT#") and "description" not in row
    )
    table = FakeTable()
    table.seed({**zap_unit, "description": "left over", "x": Decimal("0.5")})

    _run_seed(monkeypatch, table)

    stored = table.rows[("PRACTICE", zap_unit["SK"])]
    assert "description" not in stored
    assert stored["x"] == Decimal("0.5")


def test_no_write_names_a_position_field(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable()

    _run_seed(monkeypatch, table, knowledge_base="live")

    assert table.calls["update_item"] > 0
    for operation, request in table.requests:
        if operation == "update_item":
            named = set(request.get("ExpressionAttributeNames", {}).values())
            assert not named & POSITION_FIELDS
            for field in POSITION_FIELDS:
                assert field not in request["UpdateExpression"]
        elif operation == "put_item":
            assert request["Item"]["SK"] == "CURRICULUM_SEED"
            assert not set(request["Item"]) & POSITION_FIELDS


def test_the_seed_writes_its_stamp(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable()

    _run_seed(monkeypatch, table, knowledge_base="preview")

    stamp = table.rows[("PRACTICE", "CURRICULUM_SEED")]
    rows = seed_practice.seed_rows(knowledge_base="preview")
    assert stamp["seed_hash"] == seed_practice.seed_hash(rows)
    assert stamp["git_commit"] == "abc123"
    assert stamp["git_dirty"] is False
    assert stamp["knowledge_base"] == "preview"
    assert stamp["knowledge_base_prerequisites"] is False
    assert stamp["seeded_at"]


def test_the_stamp_is_written_after_every_row(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable()

    _run_seed(monkeypatch, table)

    assert table.requests[-1][0] == "put_item"
    assert table.requests[-1][1]["Item"]["SK"] == "CURRICULUM_SEED"


def test_the_hash_is_stable_across_runs() -> None:
    assert seed_practice.seed_hash(seed_practice.seed_rows()) == seed_practice.seed_hash(
        seed_practice.seed_rows()
    )


def test_the_hash_ignores_row_order() -> None:
    rows = seed_practice.seed_rows()

    assert seed_practice.seed_hash(list(reversed(rows))) == seed_practice.seed_hash(rows)


def test_a_new_title_changes_the_hash() -> None:
    rows = seed_practice.seed_rows()
    changed = [dict(row) for row in rows]
    unit = next(row for row in changed if row["SK"].startswith("UNIT#"))
    unit["title"] = unit["title"] + " (neu)"

    assert seed_practice.seed_hash(changed) != seed_practice.seed_hash(rows)


def test_a_position_on_a_row_does_not_change_the_hash() -> None:
    rows = seed_practice.seed_rows()
    placed = [
        {**row, "x": 0.5, "y": 0.5, "layout_version": "v2"}
        if row["SK"].startswith("UNIT#") else row
        for row in rows
    ]

    assert seed_practice.seed_hash(placed) == seed_practice.seed_hash(rows)


def test_the_knowledge_base_mode_changes_the_hash() -> None:
    assert seed_practice.seed_hash(seed_practice.seed_rows()) != seed_practice.seed_hash(
        seed_practice.seed_rows(knowledge_base="preview")
    )


def test_a_dry_run_prints_the_hash_twice_alike_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(**_: Any) -> None:
        raise AssertionError("a dry run must not open an AWS session")

    monkeypatch.setattr(seed_practice, "require_sso_operator_session", refuse)
    expected = seed_practice.seed_hash(seed_practice.seed_rows())

    seed_practice.seed("stoa-test", "eu-central-2", dry_run=True)
    first = capsys.readouterr().out
    seed_practice.seed("stoa-test", "eu-central-2", dry_run=True)
    second = capsys.readouterr().out

    assert f"Seed hash: {expected}" in first
    assert f"Seed hash: {expected}" in second
