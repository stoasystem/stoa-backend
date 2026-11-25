#!/usr/bin/env python3
"""Put the push devices registered before #624 in the indexes they are found through.

A push device row carries the keys of GSI-SweepPending - whose device it is -
and of GSI-Listing - which device it is - from the backend releases that write
them on (`notification_repo.push_token_index_fields`). Rows registered before
have none of them, so a reader of the indexes would not find them until this
script writes them. Run it once the release that writes the keys is deployed.

    python scripts/backfill_push_token_index.py            # dry run: counts, writes nothing
    python scripts/backfill_push_token_index.py --apply    # writes the rows the dry run counted
    python scripts/backfill_push_token_index.py --verify   # reads the indexes back, writes nothing

It reads every push device row with the one scan the indexes replace. Each
write is `notification_repo.reindex_push_token`, behind the row's owner's
account fence. One whose owner's account deletion got there first is skipped
and counted - its tombstone belongs in no index - and the next dry run says
whether anything is left. `--verify` reads every person's bucket and every
device's list the scan names and compares; the indexes are eventually
consistent, so a row just written may take a moment to appear.

Websocket connections need no backfill: a connection row lives for the
connection TTL (ten minutes), and a refresh gives a row written before the
keys its keys (`websocket_repo.update_connection`).

Nothing printed names a person or a device: rows are named by a hash of their key.
"""

from __future__ import annotations

import argparse
import hashlib
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

from stoa.db.repositories import account_deletion_repo, notification_repo  # noqa: E402
from stoa.security.aws_operator_identity import require_sso_operator_session  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"
COUNTED = ("push devices", "active", "in no index", "in place", "to write")


def _name(item: Mapping[str, Any]) -> str:
    """A row's name in the output: a hash of its key, which holds a person's id."""
    key = f"{item.get('PK')}\x00{item.get('SK')}"
    return "device-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _in_place(item: Mapping[str, Any]) -> bool:
    return notification_repo.carried_push_token_index_fields(
        item
    ) == notification_repo.push_token_index_fields(item)


def count(items: Sequence[Mapping[str, Any]]) -> Counter[str]:
    """How many push device rows there are, and whether their index keys are in place."""
    counts: Counter[str] = Counter()
    for item in items:
        counts["push devices"] += 1
        if item.get("status") == "active":
            counts["active"] += 1
        if not notification_repo.push_token_index_fields(item):
            counts["in no index"] += 1
        counts["in place" if _in_place(item) else "to write"] += 1
    return counts


def apply(table: Any, items: Sequence[Mapping[str, Any]]) -> Counter[str]:
    """Write every row's index keys; one whose account is closing is skipped."""
    outcome: Counter[str] = Counter()
    for item in items:
        try:
            written = notification_repo.reindex_push_token(item, table=table)
        except account_deletion_repo.AccountDeletionConflict:
            outcome["account closing or changed meanwhile, skipped"] += 1
            continue
        outcome["written" if written else "in place"] += 1
    return outcome


def verify(table: Any, items: Sequence[Mapping[str, Any]]) -> list[str]:
    """The rows a person's bucket or a device's list should hold and does not, or the reverse."""
    by_user: dict[str, set[str]] = {}
    by_device: dict[str, set[str]] = {}
    for item in items:
        fields = notification_repo.push_token_index_fields(item)
        if "sweep_bucket" in fields:
            by_user.setdefault(str(item.get("user_id")), set()).add(_name(item))
        if "listing" in fields:
            device_key = notification_repo.push_token_device_key(item)
            by_device.setdefault(device_key, set()).add(_name(item))
    problems: list[str] = []
    for user_id, wanted in sorted(by_user.items()):
        found = {_name(row) for row in notification_repo.list_user_push_tokens(user_id, table=table)}
        problems.extend(f"missing from its person's bucket: {name}" for name in sorted(wanted - found))
        problems.extend(f"in a person's bucket it does not belong in: {name}" for name in sorted(found - wanted))
    for device_key, wanted in sorted(by_device.items()):
        found = {_name(row) for row in notification_repo.list_device_push_tokens({device_key}, table=table)}
        problems.extend(f"missing from its device's list: {name}" for name in sorted(wanted - found))
        problems.extend(f"in a device's list it does not belong in: {name}" for name in sorted(found - wanted))
    return problems


def run(table: Any, *, apply_writes: bool, verify_index: bool) -> int:
    items = notification_repo.list_all_push_tokens(table=table)
    counts = count(items)
    print(" | ".join(f"{name}: {counts[name]}" for name in COUNTED))
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
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--table", default=os.environ.get("STOA_TABLE", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "eu-central-2"))
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "stoa"))
    parser.add_argument(
        "--account-id", default=os.environ.get("AWS_ACCOUNT_ID", DEFAULT_AWS_ACCOUNT_ID)
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write the rows the dry run counts")
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
