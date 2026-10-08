"""Give every live `UNIT#` row the `prerequisite_unit_ids` attribute it now needs.

The planet view locks a knowledge point only from an explicit prerequisite list,
so a unit without the attribute is not "no prerequisites" to the read model - it
is a missing field the catalog has to guess at. The seed writes the attribute for
every unit it creates; rows written before this change do not have it.

The seeded relations are the source for mathematics; any other unit is filled with
an empty list, which locks nothing. Report only unless `--apply` is passed.
"""

from __future__ import annotations

import argparse
from typing import Any

from boto3.dynamodb.conditions import Key

from stoa.db.dynamodb import get_table


def seeded_prerequisites() -> dict[str, list[str]]:
    from scripts import seed_practice

    relations: dict[str, list[str]] = {}
    for build in (
        seed_practice._brueche_data,
        seed_practice._gleichungen_data,
        seed_practice._geometrie_data,
        seed_practice._prozent_data,
        seed_practice._textaufgaben_data,
    ):
        for unit in build()[1]:
            relations[str(unit["unit_id"])] = list(unit.get("prerequisite_unit_ids") or [])
    return relations


def unit_rows(table: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    key = None
    while True:
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq("PRACTICE") & Key("SK").begins_with("UNIT#")
        }
        if key:
            kwargs["ExclusiveStartKey"] = key
        response = table.query(**kwargs)
        rows.extend(response.get("Items", []))
        key = response.get("LastEvaluatedKey")
        if not key:
            break
    return rows


def repair(table: Any, unit: dict[str, Any], relations: dict[str, list[str]], *, apply: bool) -> str:
    unit_id = str(unit.get("unit_id") or "")
    if not unit_id:
        return "skipped: row has no unit_id"
    if isinstance(unit.get("prerequisite_unit_ids"), list):
        return f"ok: {unit_id} already carries the attribute"
    references = relations.get(unit_id, [])
    if not apply:
        return f"would set {unit_id} prerequisite_unit_ids={references}"
    table.update_item(
        Key={"PK": "PRACTICE", "SK": f"UNIT#{unit_id}"},
        UpdateExpression="SET #prerequisite_unit_ids = :prerequisite_unit_ids",
        ConditionExpression="attribute_not_exists(#prerequisite_unit_ids)",
        ExpressionAttributeNames={"#prerequisite_unit_ids": "prerequisite_unit_ids"},
        ExpressionAttributeValues={":prerequisite_unit_ids": references},
    )
    return f"set {unit_id} prerequisite_unit_ids={references}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()

    table = get_table()
    relations = seeded_prerequisites()
    for unit in unit_rows(table):
        print(repair(table, unit, relations, apply=arguments.apply))
    if not arguments.apply:
        print("Report only. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
