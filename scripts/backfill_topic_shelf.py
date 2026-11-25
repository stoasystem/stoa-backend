#!/usr/bin/env python3
"""Put the curriculum rows written before #513 on their topic's shelf.

Curriculum unit, lesson and exercise rows carry `topic_shelf` and `topic_order`,
the keys of GSI-TopicShelf, from the backend release that writes them on (the
seed and the curriculum publish projection, `practice_repo.topic_shelf_fields`).
Rows written before that release have neither, so they are in no topic's list
until this script writes them. Run it once that release is deployed - never
before: the exercise content hash leaves the two fields out only from then on,
and an exercise whose hash no longer matches drops out of every practice read.

    python scripts/backfill_topic_shelf.py            # dry run: counts, writes nothing
    python scripts/backfill_topic_shelf.py --apply    # writes the rows the dry run counted
    python scripts/backfill_topic_shelf.py --verify   # reads the index back, writes nothing

Each write is one `UpdateItem` that sets (or, for a row that lost its topic,
removes) the two fields, on condition that the fields they are derived from are
still what was read: a row a publish rewrote meanwhile is left alone and counted,
and the next dry run says whether anything is left. `--verify` queries every
topic's shelf through the index and reports the rows missing from it; the index
is eventually consistent, so a row just written may take a moment to appear.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT, ROOT / "src"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from stoa.db.repositories import practice_repo  # noqa: E402
from stoa.security.aws_operator_identity import require_sso_operator_session  # noqa: E402
from stoa.services import curriculum_cache  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"

#: The fields `topic_shelf_fields` derives the two from, per row kind.
_SOURCE_FIELDS = {
    "UNIT": ("topic_id",),
    "LESSON": ("topic_id",),
    "CHALLENGE": ("topic_id", "lesson_id", "order", "challenge_id"),
}


def _kind(row: Mapping[str, Any]) -> str:
    return str(row.get("SK") or "").split("#", 1)[0]


def curriculum_rows(table: Any) -> Iterator[dict[str, Any]]:
    """Every unit, lesson and exercise row of the practice partition, page by page."""
    for kind in practice_repo.TOPIC_SHELF_KINDS:
        request: dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq("PRACTICE") & Key("SK").begins_with(f"{kind}#")
        }
        while True:
            response = table.query(**request)
            yield from response.get("Items", [])
            last = response.get("LastEvaluatedKey")
            if not last:
                break
            request["ExclusiveStartKey"] = last


@dataclass
class Plan:
    """What a run would write: the rows, and a count per kind and outcome."""

    writes: list[tuple[dict[str, Any], dict[str, str]]] = field(default_factory=list)
    counts: Counter[tuple[str, str]] = field(default_factory=Counter)

    def report(self) -> str:
        lines = []
        for kind in practice_repo.TOPIC_SHELF_KINDS:
            parts = [
                f"{outcome} {self.counts[(kind, outcome)]}"
                for outcome in ("rows", "in place", "to write", "no topic")
            ]
            lines.append(f"{kind}: " + " | ".join(parts))
        lines.append(f"Rows to write: {len(self.writes)}")
        return "\n".join(lines)


def plan(rows: Iterable[Mapping[str, Any]]) -> Plan:
    """Which rows lack their shelf fields, or hold ones that are no longer right."""
    result = Plan()
    for row in rows:
        kind = _kind(row)
        if kind not in practice_repo.TOPIC_SHELF_KINDS:
            continue
        result.counts[(kind, "rows")] += 1
        expected = practice_repo.topic_shelf_fields(row)
        current = {name: row[name] for name in practice_repo.TOPIC_SHELF_FIELDS if name in row}
        if expected == current:
            result.counts[(kind, "in place" if expected else "no topic")] += 1
            continue
        result.counts[(kind, "to write")] += 1
        result.writes.append((dict(row), expected))
    return result


def update_request(row: Mapping[str, Any], expected: Mapping[str, str]) -> dict[str, Any]:
    """The conditional `UpdateItem` that puts `row` where `expected` says."""
    names: dict[str, str] = {}
    values: dict[str, Any] = {}
    conditions = ["attribute_exists(SK)"]
    for index, source in enumerate(_SOURCE_FIELDS[_kind(row)]):
        names[f"#s{index}"] = source
        if source in row:
            values[f":s{index}"] = row[source]
            conditions.append(f"#s{index} = :s{index}")
        else:
            conditions.append(f"attribute_not_exists(#s{index})")
    for index, name in enumerate(practice_repo.TOPIC_SHELF_FIELDS):
        names[f"#f{index}"] = name
    if expected:
        values.update({f":f{index}": expected[name] for index, name in enumerate(practice_repo.TOPIC_SHELF_FIELDS)})
        update = "SET " + ", ".join(
            f"#f{index} = :f{index}" for index in range(len(practice_repo.TOPIC_SHELF_FIELDS))
        )
    else:
        update = "REMOVE " + ", ".join(
            f"#f{index}" for index in range(len(practice_repo.TOPIC_SHELF_FIELDS))
        )
    request: dict[str, Any] = {
        "Key": {"PK": row["PK"], "SK": row["SK"]},
        "UpdateExpression": update,
        "ConditionExpression": " AND ".join(conditions),
        "ExpressionAttributeNames": names,
    }
    if values:
        request["ExpressionAttributeValues"] = values
    return request


def apply(table: Any, planned: Plan) -> Counter[str]:
    """Write every planned row; a row changed since it was read is skipped."""
    outcome: Counter[str] = Counter()
    for row, expected in planned.writes:
        try:
            table.update_item(**update_request(row, expected))
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            outcome["changed meanwhile, skipped"] += 1
            continue
        outcome["written"] += 1
    curriculum_cache.touch_catalog_stamp(table)
    return outcome


def verify(table: Any, rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """The keys of rows that should be on a shelf and are not found there."""
    expected: dict[str, set[tuple[str, str]]] = {}
    for row in rows:
        fields = practice_repo.topic_shelf_fields(row)
        if fields:
            expected.setdefault(fields["topic_shelf"], set()).add(
                (str(row["PK"]), str(row["SK"]))
            )
    missing: list[str] = []
    for shelf, keys in sorted(expected.items()):
        found: set[tuple[str, str]] = set()
        request: dict[str, Any] = {
            "IndexName": practice_repo.TOPIC_SHELF_INDEX,
            "KeyConditionExpression": Key("topic_shelf").eq(shelf),
            "ProjectionExpression": "PK, SK",
        }
        while True:
            response = table.query(**request)
            found.update((str(item["PK"]), str(item["SK"])) for item in response.get("Items", []))
            last = response.get("LastEvaluatedKey")
            if not last:
                break
            request["ExclusiveStartKey"] = last
        missing.extend(f"{shelf}: {sort_key}" for _pk, sort_key in sorted(keys - found))
    return missing


def run(table: Any, *, apply_writes: bool, verify_index: bool) -> int:
    rows = list(curriculum_rows(table))
    if verify_index:
        missing = verify(table, rows)
        print(f"Rows expected on a shelf: {sum(1 for row in rows if practice_repo.topic_shelf_fields(row))}")
        print(f"Missing from GSI-TopicShelf: {len(missing)}")
        for line in missing[:50]:
            print(f"  {line}")
        return 1 if missing else 0
    planned = plan(rows)
    print(planned.report())
    if not apply_writes:
        print("[DRY RUN] Nothing written. Run again with --apply to write these rows.")
        return 0
    outcome = apply(table, planned)
    print(" | ".join(f"{name}: {count}" for name, count in sorted(outcome.items())) or "Nothing to write.")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--table", default=os.environ.get("STOA_TABLE", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "eu-central-2"))
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "stoa"))
    parser.add_argument(
        "--account-id", default=os.environ.get("AWS_ACCOUNT_ID", DEFAULT_AWS_ACCOUNT_ID)
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write the rows the dry run counts")
    mode.add_argument("--verify", action="store_true", help="read the index back, write nothing")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    session = require_sso_operator_session(
        profile_name=args.profile,
        region_name=args.region,
        expected_account_id=args.account_id,
    )
    table = session.resource("dynamodb", region_name=args.region).Table(args.table)
    return run(table, apply_writes=args.apply, verify_index=args.verify)


if __name__ == "__main__":
    raise SystemExit(main())
