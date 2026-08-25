#!/usr/bin/env python
"""Give seeded practice challenges the content version their readers require.

Challenges written before content versioning carry no challenge_version or
challenge_content_hash. Every catalog read validates both and raises, so the
practice surfaces answer 500 until the stored rows carry them.

The version is derived from the content itself, so this only writes what the
row already implies, and it refuses to touch a row that is already versioned.

Usage:
    python scripts/backfill_challenge_versions.py            # report only
    python scripts/backfill_challenge_versions.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stoa.db.repositories import practice_repo  # noqa: E402


def stored_challenges(table) -> list[dict]:
    items: list[dict] = []
    start_key = None
    while True:
        kwargs = {
            "FilterExpression": "begins_with(SK, :prefix)",
            "ExpressionAttributeValues": {":prefix": "CHALLENGE#"},
        }
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        start_key = response.get("LastEvaluatedKey")
        if not start_key:
            return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default=os.environ.get("DYNAMODB_TABLE_NAME", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "eu-central-2"))
    parser.add_argument("--apply", action="store_true", help="write the versions")
    args = parser.parse_args()

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    rows = stored_challenges(table)

    already_versioned = 0
    pointers = 0
    to_write: list[tuple[dict, dict]] = []
    for row in rows:
        item = dict(row)
        if item.get("entity_type") == practice_repo.CHALLENGE_POINTER_ENTITY:
            pointers += 1
            continue
        if practice_repo._valid_versioned_challenge(item):
            already_versioned += 1
            continue
        to_write.append((item, practice_repo.version_challenge(item)))

    print(f"scanned {len(rows)} rows below CHALLENGE#")
    print(f"  {pointers} pointer rows, skipped")
    print(f"  {already_versioned} already versioned")
    print(f"  {len(to_write)} need a version")

    if not to_write:
        return 0
    if not args.apply:
        for item, versioned in to_write[:5]:
            print(f"    {item.get('challenge_id')} -> {versioned['challenge_version'][:23]}...")
        print("\nre-run with --apply to write these")
        return 0

    written = 0
    for _item, versioned in to_write:
        table.put_item(Item=versioned)
        written += 1
    print(f"\nwrote {written} versions")

    remaining = [
        row
        for row in stored_challenges(table)
        if dict(row).get("entity_type") != practice_repo.CHALLENGE_POINTER_ENTITY
        and not practice_repo._valid_versioned_challenge(dict(row))
    ]
    print(f"unversioned rows remaining: {len(remaining)}")
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
