#!/usr/bin/env python3
"""Put the account profiles written before card 133 in GSI-Listing.

A profile carries the keys of GSI-Listing - `listing = "account_profile"` and
`listed_at`, its creation time - from the backend release that writes them on
(`account_deletion_repo.account_listing_fields`). The administrators' account
list reads that index (so did the role census of `/admin/stats` until #697), so
a profile written before is missing from it until this script writes its keys. Run it once the
release that writes the keys is deployed.

    python scripts/backfill_account_listing_index.py            # dry run: counts, writes nothing
    python scripts/backfill_account_listing_index.py --apply    # writes the rows the dry run counted
    python scripts/backfill_account_listing_index.py --verify   # reads the index back, writes nothing

It reads every profile with one scan of the table. Each write is
`user_repo.add_listing_fields`: behind the account's fence, on the version
that was read, and only while neither key is there - it adds, never
overwrites, so a second run writes nothing. A deletion tombstone is never given
the keys. A profile whose account deletion began, or that changed between the
scan and the write, is skipped and counted; the next dry run says whether
anything is left. `--verify` compares the index with the scan; the index is
eventually consistent, so a row just written may take a moment to appear.

Nothing printed names a person: only counts, and user ids for a mismatch.
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

from stoa.db import table as db_table  # noqa: E402
from stoa.db.repositories import account_deletion_repo, user_repo  # noqa: E402
from stoa.security.aws_operator_identity import require_sso_operator_session  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"
COUNTED = ("profiles", "tombstones", "in place", "one key only", "to write")
LISTING_FIELDS = account_deletion_repo.ACCOUNT_LISTING_FIELDS


def all_profiles(table: Any) -> list[dict[str, Any]]:
    return db_table.rows(
        "scan",
        table=table,
        FilterExpression="SK = :profile",
        ExpressionAttributeValues={":profile": "PROFILE"},
    )


def state(item: Mapping[str, Any]) -> str:
    """Which of `COUNTED` a profile row falls under, besides "profiles"."""
    if account_deletion_repo.is_deletion_tombstone(item):
        return "tombstones"
    carried = [name for name in LISTING_FIELDS if name in item]
    if len(carried) == len(LISTING_FIELDS):
        return "in place"
    if carried:
        return "one key only"
    return "to write"


def count(items: Sequence[Mapping[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in items:
        counts["profiles"] += 1
        counts[state(item)] += 1
    return counts


def apply(table: Any, items: Sequence[Mapping[str, Any]]) -> Counter[str]:
    """Write the keys of every profile that has neither; anything else is left alone."""
    outcome: Counter[str] = Counter()
    for item in items:
        if state(item) != "to write":
            outcome["left alone"] += 1
            continue
        try:
            written = user_repo.add_listing_fields(item, table=table)
        except ValueError:
            outcome["not a profile row, skipped"] += 1
            continue
        except account_deletion_repo.AccountDeletionConflict:
            outcome["account closing, skipped"] += 1
            continue
        except db_table.WriteRefused:
            outcome["changed meanwhile, skipped"] += 1
            continue
        outcome["written" if written else "in place"] += 1
    return outcome


def verify(table: Any, items: Sequence[Mapping[str, Any]]) -> list[str]:
    """The profiles the index should list and does not, or lists and should not."""
    wanted = {
        str(item.get("user_id"))
        for item in items
        if state(item) == "in place"
    }
    found: set[str] = set()
    cursor: str | None = None
    while True:
        page = user_repo.list_accounts(limit=200, cursor=cursor, table=table)
        found.update(str(profile.get("user_id")) for profile in page.profiles)
        cursor = page.next_cursor
        if not cursor:
            break
    problems = [f"profile missing from the list: {user_id}" for user_id in sorted(wanted - found)]
    problems += [f"listed, not a live profile: {user_id}" for user_id in sorted(found - wanted)]
    return problems


def run(table: Any, *, apply_writes: bool, verify_index: bool) -> int:
    items = all_profiles(table)
    counts = count(items)
    print(" | ".join(f"{name}: {counts[name]}" for name in COUNTED))
    if verify_index:
        problems = verify(table, items)
        print(f"Index problems: {len(problems)}")
        for line in problems[:50]:
            print(f"  {line}")
        return 1 if problems or counts["to write"] or counts["one key only"] else 0
    if not apply_writes:
        print("[DRY RUN] Nothing written. Run again with --apply to write these rows.")
        return 0
    outcome = apply(table, items)
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
