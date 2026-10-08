"""The repair that gives existing `UNIT#` rows their prerequisite list (#56).

The attribute is new, so every unit already in the table is without it, and a
unit without it locks nothing. The repair exists because there is no Alembic
here: the script is the migration, and the only thing standing between a
report and a write is the `--apply` flag.
"""

from __future__ import annotations

from typing import Any

from fakes.dynamodb import FakeTable, as_stored

from scripts import backfill_unit_prerequisites as backfill


def _unit(unit_id: str, **extra: Any) -> dict[str, Any]:
    return {"PK": "PRACTICE", "SK": f"UNIT#{unit_id}", "unit_id": unit_id, **extra}


def _table(*units: dict[str, Any]) -> FakeTable:
    table = FakeTable()
    for unit in units:
        table.rows[(unit["PK"], unit["SK"])] = as_stored(unit)
    return table


def _stored(table: FakeTable, unit_id: str) -> Any:
    return table.rows[("PRACTICE", f"UNIT#{unit_id}")].get("prerequisite_unit_ids")


def test_a_report_writes_nothing() -> None:
    # The whole safety of this script is that the default run cannot write.
    table = _table(_unit("brueche-u2"))

    line = backfill.repair(table, _unit("brueche-u2"), backfill.seeded_prerequisites(), apply=False)

    assert line.startswith("would set brueche-u2")
    assert _stored(table, "brueche-u2") is None
    assert table.calls.get("update_item", 0) == 0


def test_applying_writes_the_relation_the_seed_names() -> None:
    table = _table(_unit("brueche-u2"))

    backfill.repair(table, _unit("brueche-u2"), backfill.seeded_prerequisites(), apply=True)

    assert _stored(table, "brueche-u2") == ["brueche-u1"]


def test_a_unit_the_seed_says_nothing_about_gets_an_empty_list() -> None:
    # Not "no attribute": an empty list is the answer "nothing comes first",
    # and the read model tells the two apart.
    table = _table(_unit("physik-u1"))

    backfill.repair(table, _unit("physik-u1"), backfill.seeded_prerequisites(), apply=True)

    assert _stored(table, "physik-u1") == []


def test_a_unit_that_already_has_one_is_left_alone() -> None:
    table = _table(_unit("brueche-u2", prerequisite_unit_ids=["something-else"]))

    line = backfill.repair(
        table,
        dict(table.rows[("PRACTICE", "UNIT#brueche-u2")]),
        backfill.seeded_prerequisites(),
        apply=True,
    )

    assert "already carries" in line
    assert _stored(table, "brueche-u2") == ["something-else"]
    assert table.calls.get("update_item", 0) == 0


def test_running_it_twice_writes_once() -> None:
    table = _table(_unit("brueche-u2"))

    for _ in range(2):
        for row in backfill.unit_rows(table):
            backfill.repair(table, dict(row), backfill.seeded_prerequisites(), apply=True)

    assert table.calls.get("update_item", 0) == 1
    assert _stored(table, "brueche-u2") == ["brueche-u1"]


def test_a_row_without_a_unit_id_is_skipped_rather_than_guessed() -> None:
    table = _table({"PK": "PRACTICE", "SK": "UNIT#", "unit_id": ""})

    line = backfill.repair(table, {"PK": "PRACTICE", "SK": "UNIT#"}, {}, apply=True)

    assert line.startswith("skipped")
    assert table.calls.get("update_item", 0) == 0


def test_every_unit_is_read_even_when_the_table_answers_in_pages() -> None:
    # A page of the table is not a page of matches. Ten units behind a cap of
    # three is where a single-page read would have stopped at three.
    units = [_unit(f"u-{index:02d}") for index in range(10)]
    table = _table(*units)
    table.page_item_cap = 3

    rows = backfill.unit_rows(table)

    assert sorted(str(row["unit_id"]) for row in rows) == sorted(u["unit_id"] for u in units)


def test_the_seed_relations_point_only_at_units_that_exist() -> None:
    relations = backfill.seeded_prerequisites()

    unknown = {
        reference
        for references in relations.values()
        for reference in references
        if reference not in relations
    }
    assert unknown == set()
