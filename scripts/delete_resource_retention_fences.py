#!/usr/bin/env python3
"""Count, then delete, the per-resource retention fences nothing reads any more (#655).

The old account deletion opened one fence row per conversation whose
attachments it released: `OWNER#<account id>` / `RETENTION#RESOURCE#<type>#<id>`,
`entity_type` `attachment_retention_fence`. Account deletion now handles every
row on its own, behind the account fence alone (#636), and #655 removed the
code that wrote, read and checked these rows. Run this once that release is
deployed; when it reports none left, the `attachment_retention_fence` entry can
leave the data type catalog.

    python scripts/delete_resource_retention_fences.py                    # count: read-only
    python scripts/delete_resource_retention_fences.py --delete           # dry run: what a delete would do
    python scripts/delete_resource_retention_fences.py --delete --apply   # deletes the fences counted

It finds the rows with one consistent scan of the table for `OWNER#` partitions
whose sort key starts with `RETENTION#RESOURCE#`. It deletes only rows whose
`entity_type` is `attachment_retention_fence`, each on the condition that it
still is one; any other kind of row under that key is left and counted. The
account fence (`USER#<id>` / `ACCOUNT_FENCE`) is another row and is never
touched. Account and resource ids are counted, never printed.
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
PARTITION = "OWNER#"
SORT_KEY = "RETENTION#RESOURCE#"
FENCE = "attachment_retention_fence"


def find(table: Any) -> list[dict[str, Any]]:
    """Every row under a resource fence's key: its key, entity type and status."""
    rows: list[dict[str, Any]] = []
    request: dict[str, Any] = {
        "FilterExpression": Attr("PK").begins_with(PARTITION) & Attr("SK").begins_with(SORT_KEY),
        "ProjectionExpression": "PK, SK, entity_type, #status",
        "ExpressionAttributeNames": {"#status": "status"},
        "ConsistentRead": True,
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
    counts["accounts"] = len({str(row["PK"]) for row in rows})
    counts["rows"] = len(rows)
    counts["fences"] = 0
    for row in rows:
        kind = str(row.get("entity_type") or "(none)")
        if kind == FENCE:
            counts["fences"] += 1
            counts[f"fence status {row.get('status') or '(none)'}"] += 1
        else:
            counts[f"other: {kind}"] += 1
    return counts


def delete(table: Any, rows: Sequence[Mapping[str, Any]], *, apply_deletes: bool) -> Counter[str]:
    """Delete each fence row; one that is not a fence (any more) is left and counted."""
    outcome: Counter[str] = Counter()
    for row in rows:
        if row.get("entity_type") != FENCE:
            outcome["left, not a fence"] += 1
            continue
        if not apply_deletes:
            outcome["would delete"] += 1
            continue
        try:
            table.delete_item(
                Key={"PK": row["PK"], "SK": row["SK"]},
                ConditionExpression=Attr("entity_type").eq(FENCE),
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


def run(table: Any, *, delete_fences: bool = False, apply_deletes: bool = False) -> int:
    rows = find(table)
    print(_line(count(rows)))
    if not delete_fences:
        print("[READ ONLY] Nothing written.")
        return 0
    print(_line(delete(table, rows, apply_deletes=apply_deletes)) or "Nothing to delete.")
    if not apply_deletes:
        print("[DRY RUN] Nothing deleted. Run again with --delete --apply to delete the fences.")
        return 0
    left = find(table)
    print(f"After: {_line(count(left))}")
    return 1 if any(row.get("entity_type") == FENCE for row in left) else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--table", default=os.environ.get("STOA_TABLE", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "eu-central-2"))
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "stoa"))
    parser.add_argument(
        "--account-id", default=os.environ.get("AWS_ACCOUNT_ID", DEFAULT_AWS_ACCOUNT_ID)
    )
    parser.add_argument(
        "--delete", action="store_true", help="go through the delete; a dry run without --apply"
    )
    parser.add_argument(
        "--apply", action="store_true", help="with --delete: delete the fences the dry run counts"
    )
    args = parser.parse_args(argv)
    if args.apply and not args.delete:
        parser.error("--apply only goes with --delete")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    session = require_sso_operator_session(
        profile_name=args.profile,
        region_name=args.region,
        expected_account_id=args.account_id,
    )
    table = session.resource("dynamodb", region_name=args.region).Table(args.table)
    return run(table, delete_fences=args.delete, apply_deletes=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
