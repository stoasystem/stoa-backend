#!/usr/bin/env python3
"""Put the help requests written before #608 in the two indexes they are found through.

A help request carries the keys of GSI-SweepPending while it is not yet ended,
and of GSI-TeacherId while a teacher holds it, from the backend release that
writes them on (`help_requests.index_fields`). Requests written before that
release have neither, so a reader of the indexes would not find them until
this script writes them. Run it once that release is deployed, and before the
release that reads the indexes instead of scanning the table.

    python scripts/backfill_help_request_index.py            # dry run: counts, writes nothing
    python scripts/backfill_help_request_index.py --apply    # writes the records the dry run counted
    python scripts/backfill_help_request_index.py --verify   # reads the indexes back, writes nothing

It reads every help request with the one scan the indexes replace. Each write
is `help_requests.reindex`: one conditional update on the version the record was
read at, so a request that moved meanwhile is left alone and counted - the
write that moved it set the keys itself - and the next dry run says whether
anything is left. `--verify` compares both indexes with the scan; the indexes
are eventually consistent, so a record just written may take a moment to appear.
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

from stoa.security.aws_operator_identity import require_sso_operator_session  # noqa: E402
from stoa.services import help_requests  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"


def _in_place(record: Mapping[str, Any]) -> bool:
    carried = {name: record[name] for name in help_requests.INDEX_FIELDS if name in record}
    return carried == help_requests.index_fields(record)


def count(records: Sequence[Mapping[str, Any]]) -> Counter[str]:
    """How many requests there are, by what the indexes should hold and whether they do."""
    counts: Counter[str] = Counter()
    for record in records:
        counts["requests"] += 1
        fields = help_requests.index_fields(record)
        if "sweep_bucket" in fields:
            counts["not ended"] += 1
        if help_requests.HOLDER_INDEX_FIELD in fields:
            counts["held by a teacher"] += 1
        counts["in place" if _in_place(record) else "to write"] += 1
    return counts


def apply(table: Any, records: Sequence[Mapping[str, Any]]) -> Counter[str]:
    """Write every record's index keys; one that moved since it was read is skipped."""
    outcome: Counter[str] = Counter()
    for record in records:
        try:
            written = help_requests.reindex(record, table=table)
        except help_requests.HelpRequestConflict:
            outcome["changed meanwhile, skipped"] += 1
            continue
        outcome["written" if written else "in place"] += 1
    return outcome


def verify(table: Any, records: Sequence[Mapping[str, Any]]) -> list[str]:
    """The requests an index should hold and does not, or holds and should not."""
    problems: list[str] = []
    expected_open = {
        str(record["conversation_id"])
        for record in records
        if help_requests.stored_status(record) in help_requests.OPEN
    }
    found_open = {
        str(record["conversation_id"]) for record in help_requests.list_unended(table=table)
    }
    problems.extend(f"not ended, missing from the index: {name}" for name in sorted(expected_open - found_open))
    problems.extend(f"ended, still in the index: {name}" for name in sorted(found_open - expected_open))
    held: dict[str, set[str]] = {}
    for record in records:
        teacher_id = str(record.get("teacher_id") or "")
        if teacher_id:
            held.setdefault(teacher_id, set()).add(str(record["conversation_id"]))
    for teacher_id, expected in sorted(held.items()):
        found = {
            str(record["conversation_id"])
            for record in help_requests.list_held_by(teacher_id, table=table)
        }
        # Named by request only: a teacher's id stays out of the output.
        problems.extend(f"held, missing from its teacher's index: {name}" for name in sorted(expected - found))
        problems.extend(f"in a teacher's index, not held: {name}" for name in sorted(found - expected))
    return problems


def run(table: Any, *, apply_writes: bool, verify_index: bool) -> int:
    records = help_requests.list_all(table=table)
    counts = count(records)
    print(
        " | ".join(
            f"{name}: {counts[name]}"
            for name in ("requests", "not ended", "held by a teacher", "in place", "to write")
        )
    )
    if verify_index:
        problems = verify(table, records)
        print(f"Index problems: {len(problems)}")
        for line in problems[:50]:
            print(f"  {line}")
        return 1 if problems or counts["to write"] else 0
    if not apply_writes:
        print("[DRY RUN] Nothing written. Run again with --apply to write these records.")
        return 0
    outcome = apply(table, records)
    print(" | ".join(f"{name}: {number}" for name, number in sorted(outcome.items())) or "Nothing to write.")
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
    mode.add_argument("--apply", action="store_true", help="write the records the dry run counts")
    mode.add_argument("--verify", action="store_true", help="read the indexes back, write nothing")
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
