#!/usr/bin/env python3
"""Delete the adaptive memory snapshots `/memory/refresh` stored before #675.

`POST /adaptive/students/{id}/memory/refresh` stored each snapshot as a row in
the student's `LEARNING_MEMORY#<student id>` partition. #675 retired the route
and computes the snapshots on every read, so nothing reads or writes these rows
any more. Run this once the release that stopped reading them is deployed.

    python scripts/delete_learning_memory_snapshots.py           # dry run: counts, deletes nothing
    python scripts/delete_learning_memory_snapshots.py --apply   # deletes the rows the dry run counted

It finds the rows with one scan of the table for the `LEARNING_MEMORY#`
partitions. It deletes only rows whose `entity_type` is
`learning_memory_snapshot`, each on the condition that it still is one: a row
an account deletion has meanwhile turned into its tombstone is left, as is any
other kind of row in those partitions; the counts say how many. Student ids are
counted, never printed.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT, ROOT / "src"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from boto3.dynamodb.conditions import Attr  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

from stoa.security.aws_operator_identity import require_sso_operator_session  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"
PARTITION = "LEARNING_MEMORY#"
SNAPSHOT = "learning_memory_snapshot"


def find(table: Any) -> list[dict[str, Any]]:
    """Every row of a `LEARNING_MEMORY#` partition: its key and entity type."""
    rows: list[dict[str, Any]] = []
    request: dict[str, Any] = {
        "FilterExpression": Attr("PK").begins_with(PARTITION),
        "ProjectionExpression": "PK, SK, entity_type",
    }
    while True:
        response = table.scan(**request)
        rows.extend(response.get("Items", []))
        cursor = response.get("LastEvaluatedKey")
        if cursor is None:
            return rows
        request["ExclusiveStartKey"] = cursor


def count(rows: Sequence[Mapping[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    counts["students"] = len({str(row["PK"]) for row in rows})
    counts["rows"] = len(rows)
    for row in rows:
        kind = str(row.get("entity_type") or "(none)")
        counts["snapshots" if kind == SNAPSHOT else f"other: {kind}"] += 1
    return counts


def delete(table: Any, rows: Sequence[Mapping[str, Any]]) -> Counter[str]:
    """Delete each snapshot row; one that is no longer a snapshot is left and counted."""
    outcome: Counter[str] = Counter()
    for row in rows:
        if row.get("entity_type") != SNAPSHOT:
            outcome["left, not a snapshot"] += 1
            continue
        try:
            table.delete_item(
                Key={"PK": row["PK"], "SK": row["SK"]},
                ConditionExpression=Attr("entity_type").eq(SNAPSHOT),
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            outcome["changed meanwhile, left"] += 1
            continue
        outcome["deleted"] += 1
    return outcome


def _line(counts: Mapping[str, int]) -> str:
    return " | ".join(f"{name}: {number}" for name, number in counts.items())


def run(table: Any, *, apply_deletes: bool) -> int:
    rows = find(table)
    print(_line(count(rows)))
    if not apply_deletes:
        print("[DRY RUN] Nothing deleted. Run again with --apply to delete the snapshots counted.")
        return 0
    print(_line(delete(table, rows)) or "Nothing to delete.")
    left = find(table)
    print(f"After: {_line(count(left))}")
    return 1 if any(row.get("entity_type") == SNAPSHOT for row in left) else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--table", default=os.environ.get("STOA_TABLE", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "eu-central-2"))
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "stoa"))
    parser.add_argument(
        "--account-id", default=os.environ.get("AWS_ACCOUNT_ID", DEFAULT_AWS_ACCOUNT_ID)
    )
    parser.add_argument("--apply", action="store_true", help="delete the snapshots the dry run counts")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    session = require_sso_operator_session(
        profile_name=args.profile,
        region_name=args.region,
        expected_account_id=args.account_id,
    )
    table = session.resource("dynamodb", region_name=args.region).Table(args.table)
    return run(table, apply_deletes=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
