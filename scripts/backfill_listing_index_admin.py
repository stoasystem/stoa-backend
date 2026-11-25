#!/usr/bin/env python3
"""Put the rows the admin pages count and list in GSI-Listing (card 133).

`/admin/stats` reads the legacy questions and the help requests, and the
curriculum worklist reads the lesson versions and pointers, through GSI-Listing
instead of a scan of the whole table. A help request carries the keys from the
release that writes them on (`help_requests.listing_fields`), a version or a
pointer from every write after it (`curriculum_ops_repo.listing_fields`); a
legacy question is no longer written at all (`question_repo.listing_fields`).
Rows written before are missing from the index until this script writes them.
Run it once the release that reads the index is deployed.

    python scripts/backfill_listing_index_admin.py            # dry run: counts, writes nothing
    python scripts/backfill_listing_index_admin.py --apply    # writes the rows the dry run counted
    python scripts/backfill_listing_index_admin.py --verify   # reads the index back, writes nothing

It reads the table with one scan. Each write sets `listing` and `listed_at` on
the condition that the row is still there and has no `listing`: a row written
meanwhile by a release that sets them is left as it is, and a second run writes
nothing. No other attribute is touched.

Nothing printed names a person: rows are counted, and named by their key only
in `--verify`, whose keys hold no account id.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from boto3.dynamodb.conditions import Key

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT, ROOT / "src"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from stoa.db import table as db_table  # noqa: E402
from stoa.db.repositories import (  # noqa: E402
    account_deletion_repo,
    curriculum_ops_repo,
    question_repo,
)
from stoa.models.question import QuestionStatus  # noqa: E402
from stoa.security.aws_operator_identity import require_sso_operator_session  # noqa: E402
from stoa.services import help_requests  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"
LISTINGS = (
    question_repo.LISTING_NAME,
    help_requests.LISTING_NAME,
    curriculum_ops_repo.VERSION_LISTING,
    curriculum_ops_repo.POINTER_LISTING,
)
_QUESTION_STATUSES = frozenset(status.value for status in QuestionStatus)
_INDEX_KEY = ("PK", "SK", "listing", "listed_at")


def listing_fields(item: Mapping[str, Any]) -> dict[str, str]:
    """The GSI-Listing keys this row belongs under, by the writer that owns it."""
    if account_deletion_repo.is_deletion_tombstone(item):
        return {}
    entity_type = item.get("entity_type")
    if entity_type == help_requests.ENTITY_TYPE:
        return help_requests.listing_fields(item) if item.get("conversation_id") else {}
    if entity_type in {curriculum_ops_repo.VERSION_ENTITY, curriculum_ops_repo.POINTER_ENTITY}:
        return curriculum_ops_repo.listing_fields(item)
    return question_repo.listing_fields(item)


def _row_key(item: Mapping[str, Any]) -> tuple[str, str]:
    return (str(item["PK"]), str(item["SK"]))


def count(items: Iterable[Mapping[str, Any]]) -> Counter[str]:
    """Rows by the list they belong in, and whether they are in it."""
    counts: Counter[str] = Counter()
    for item in items:
        fields = listing_fields(item)
        if not fields:
            # The old census counted every META row with a question status;
            # the index holds the questions only.
            if item.get("SK") == "META" and item.get("status") in _QUESTION_STATUSES:
                counts["not a question, no longer counted"] += 1
            continue
        counts[fields["listing"]] += 1
        counts["in place" if "listing" in item else "to write"] += 1
    return counts


def apply(table: Any, items: Iterable[Mapping[str, Any]]) -> Counter[str]:
    """Write the keys onto every row that lacks them; never over keys already there."""
    outcome: Counter[str] = Counter()
    for item in items:
        fields = listing_fields(item)
        if not fields or "listing" in item:
            continue
        try:
            db_table.update(
                table=table,
                Key={"PK": item["PK"], "SK": item["SK"]},
                UpdateExpression="SET #listing = :listing, #listed_at = :listed_at",
                ConditionExpression="attribute_exists(PK) AND attribute_not_exists(#listing)",
                ExpressionAttributeNames={"#listing": "listing", "#listed_at": "listed_at"},
                ExpressionAttributeValues={
                    ":listing": fields["listing"],
                    ":listed_at": fields["listed_at"],
                },
            )
        except db_table.WriteRefused:
            outcome["listed or gone meanwhile, skipped"] += 1
            continue
        outcome["written"] += 1
    return outcome


def _listed_keys(table: Any, listing: str) -> set[tuple[str, str]]:
    return {
        _row_key(item)
        for item in db_table.rows(
            "query",
            table=table,
            key=_INDEX_KEY,
            page_budget=10_000,
            IndexName="GSI-Listing",
            KeyConditionExpression=Key("listing").eq(listing),
            ProjectionExpression="PK, SK",
        )
    }


def verify(table: Any, items: Iterable[Mapping[str, Any]]) -> list[str]:
    """The rows a list should hold and does not, or holds and should not."""
    wanted: dict[str, set[tuple[str, str]]] = {name: set() for name in LISTINGS}
    for item in items:
        fields = listing_fields(item)
        if fields:
            wanted[fields["listing"]].add(_row_key(item))
    problems: list[str] = []
    for name in LISTINGS:
        found = _listed_keys(table, name)
        problems.extend(f"missing from {name}: {pk} {sk}" for pk, sk in sorted(wanted[name] - found))
        problems.extend(f"in {name}, should not be: {pk} {sk}" for pk, sk in sorted(found - wanted[name]))
    return problems


# What `listing_fields` and `count` read; a version's content stays on the table.
_SCANNED = (
    "PK", "SK", "entity_type", "status", "owner_deletion_generation", "conversation_id",
    "created_at", "escalated_at", "updated_at", "listing",
)


def scan(table: Any) -> list[dict[str, Any]]:
    """Every row of the table, the one read the index replaces."""
    found: list[dict[str, Any]] = []
    for page in db_table.pages(
        "scan",
        table=table,
        ProjectionExpression=", ".join(f"#a{index}" for index in range(len(_SCANNED))),
        ExpressionAttributeNames={f"#a{index}": name for index, name in enumerate(_SCANNED)},
    ):
        found.extend(dict(item) for item in page.items)
    return found


def run(
    table: Any,
    *,
    apply_writes: bool,
    verify_index: bool,
    read: Callable[[Any], Sequence[Mapping[str, Any]]] = scan,
) -> int:
    items = read(table)
    counts = count(items)
    print(" | ".join(f"{name}: {counts[name]}" for name in (*LISTINGS, "in place", "to write")))
    print(f"not a question, no longer counted: {counts['not a question, no longer counted']}")
    if verify_index:
        problems = verify(table, items)
        print(f"Index problems: {len(problems)}")
        for line in problems[:50]:
            print(f"  {line}")
        return 1 if problems or counts["to write"] else 0
    if not apply_writes:
        print("[DRY RUN] Nothing written. Run again with --apply to write these rows.")
        return 0
    outcome = apply(table, items)
    print(" | ".join(f"{name}: {number}" for name, number in sorted(outcome.items())) or "Nothing to write.")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n", 1)[0])
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
