#!/usr/bin/env python3
"""Put the upload rows written before #611 in the cleanup's bucket of GSI-SweepPending.

An upload row carries `sweep_bucket` and `sweep_due_at` while the cleanup may
come to act on it, from the backend release that writes them on
(`stoa.services.uploads._store.cleanup_index_fields`). Rows written before that
release have neither, so the index does not hold them until this script writes
them. Run it once that release is deployed, and before the release that makes
the cleanup read the index instead of scanning the table: an upload missing
from the index would never be cleaned up.

    python scripts/backfill_upload_cleanup_index.py            # dry run: counts, writes nothing
    python scripts/backfill_upload_cleanup_index.py --apply    # writes the rows the dry run counted
    python scripts/backfill_upload_cleanup_index.py --verify   # reads the index back, writes nothing

Finding the upload rows takes one scan of the table; it is the last one. Each
write is one `UpdateItem` that sets (or, for a row that should not be in the
index, removes) the two fields, on condition that the row's state and version
are still what was read: a row the application moved on meanwhile is left alone
and counted - its own write keeps the fields right from that release on - and
the next dry run says whether anything is left. `--verify` reads the whole
bucket through the index and reports the uploads missing from it, or there with
another due time, or there and not expected; the index is eventually
consistent, so a row just written may take a moment to appear.
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

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT, ROOT / "src"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from stoa.db.repositories.attachment_repo import AttachmentRepositoryConflict  # noqa: E402
from stoa.security.aws_operator_identity import require_sso_operator_session  # noqa: E402
from stoa.services.uploads import _store  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"

OUTCOMES = ("rows", "in place", "to write", "not indexed", "unreadable")


def upload_rows(table: Any) -> Iterator[dict[str, Any]]:
    """Every upload row (`UPLOAD#{id}` / `META`) of the table, page by page."""
    request: dict[str, Any] = {
        "FilterExpression": Attr("PK").begins_with("UPLOAD#") & Attr("SK").eq("META")
    }
    while True:
        response = table.scan(**request)
        yield from response.get("Items", [])
        last = response.get("LastEvaluatedKey")
        if not last:
            break
        request["ExclusiveStartKey"] = last


def expected_fields(row: Mapping[str, Any]) -> dict[str, str] | None:
    """The index fields `row` should carry; `None` when its window cannot be read."""
    try:
        return _store.cleanup_index_fields(row)
    except AttachmentRepositoryConflict:
        return None


@dataclass
class Plan:
    """What a run would write: the rows, and a count per state and outcome."""

    writes: list[tuple[dict[str, Any], dict[str, str]]] = field(default_factory=list)
    counts: Counter[tuple[str, str]] = field(default_factory=Counter)

    def report(self) -> str:
        lines = []
        for state in sorted({state for state, _outcome in self.counts}):
            parts = [f"{outcome} {self.counts[(state, outcome)]}" for outcome in OUTCOMES]
            lines.append(f"{state}: " + " | ".join(parts))
        lines.append(f"Rows to write: {len(self.writes)}")
        return "\n".join(lines)


def plan(rows: Iterable[Mapping[str, Any]]) -> Plan:
    """Which upload rows lack their index fields, or hold ones that are not right."""
    result = Plan()
    for row in rows:
        state = str(row.get("status") or "(no status)")
        result.counts[(state, "rows")] += 1
        expected = expected_fields(row)
        if expected is None:
            result.counts[(state, "unreadable")] += 1
            continue
        current = {name: row[name] for name in _store.CLEANUP_INDEX_FIELDS if name in row}
        if expected == current:
            result.counts[(state, "in place" if expected else "not indexed")] += 1
            continue
        result.counts[(state, "to write")] += 1
        result.writes.append((dict(row), expected))
    return result


def update_request(row: Mapping[str, Any], expected: Mapping[str, str]) -> dict[str, Any]:
    """The conditional `UpdateItem` that puts `row` where `expected` says."""
    names = {"#status": "status", "#version": "version"}
    values: dict[str, Any] = {}
    conditions = ["attribute_exists(SK)"]
    for name, placeholder in (("status", "#status"), ("version", "#version")):
        if name in row:
            values[f":{name}"] = row[name]
            conditions.append(f"{placeholder} = :{name}")
        else:
            conditions.append(f"attribute_not_exists({placeholder})")
    fields = _store.CLEANUP_INDEX_FIELDS
    if expected:
        values.update({f":f{index}": expected[name] for index, name in enumerate(fields)})
        update = "SET " + ", ".join(f"{name} = :f{index}" for index, name in enumerate(fields))
    else:
        update = "REMOVE " + ", ".join(fields)
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
    return outcome


def indexed(table: Any) -> dict[tuple[str, str], str]:
    """Everything in the cleanup's bucket of the index: its due time, by base-table key."""
    found: dict[tuple[str, str], str] = {}
    request: dict[str, Any] = {
        "IndexName": _store.CLEANUP_INDEX,
        "KeyConditionExpression": Key("sweep_bucket").eq(_store.CLEANUP_BUCKET),
        "ProjectionExpression": "PK, SK, sweep_due_at",
    }
    while True:
        response = table.query(**request)
        for item in response.get("Items", []):
            found[(str(item["PK"]), str(item["SK"]))] = str(item.get("sweep_due_at"))
        last = response.get("LastEvaluatedKey")
        if not last:
            return found
        request["ExclusiveStartKey"] = last


def verify(table: Any, rows: Iterable[Mapping[str, Any]]) -> tuple[int, list[str]]:
    """How many uploads should be in the index, and each difference from what is there."""
    expected: dict[tuple[str, str], str] = {}
    for row in rows:
        fields = expected_fields(row)
        if fields:
            expected[(str(row["PK"]), str(row["SK"]))] = fields["sweep_due_at"]
    found = indexed(table)
    problems = [f"missing: {key[0]}" for key in sorted(expected.keys() - found.keys())]
    problems += [f"not expected: {key[0]}" for key in sorted(found.keys() - expected.keys())]
    problems += [
        f"due {found[key]}, expected {expected[key]}: {key[0]}"
        for key in sorted(expected.keys() & found.keys())
        if found[key] != expected[key]
    ]
    return len(expected), problems


def run(table: Any, *, apply_writes: bool, verify_index: bool) -> int:
    rows = list(upload_rows(table))
    if verify_index:
        expected, problems = verify(table, rows)
        print(f"Uploads expected in the index: {expected}")
        print(f"Differences from GSI-SweepPending ({_store.CLEANUP_BUCKET}): {len(problems)}")
        for line in problems[:50]:
            print(f"  {line}")
        return 1 if problems else 0
    planned = plan(rows)
    print(planned.report())
    if not apply_writes:
        print("[DRY RUN] Nothing written. Run again with --apply to write these rows.")
        return 0
    outcome = apply(table, planned)
    print(
        " | ".join(f"{name}: {count}" for name, count in sorted(outcome.items()))
        or "Nothing to write."
    )
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
