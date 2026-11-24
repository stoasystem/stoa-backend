#!/usr/bin/env python3
"""Put the notifications written before #613 in the indexes they are found through.

A notification carries the keys of GSI-SweepPending - who it is for, and when
it was created - and of GSI-Listing - the site's list of all of them - from
the backend releases that write them on (`notification_repo.index_fields`).
Notifications written before have some or none of them, so a reader of the
indexes would not find them until this script writes them. Run it once the
release that writes the keys is deployed.

    python scripts/backfill_notification_inbox_index.py            # dry run: counts, writes nothing
    python scripts/backfill_notification_inbox_index.py --apply    # writes the rows the dry run counted
    python scripts/backfill_notification_inbox_index.py --verify   # reads the index back, writes nothing

It reads every notification with the one scan the index replaces. Each write is
`notification_repo.reindex_event`: a private notification behind its owner's
account fence, a global one on the condition that it is still that
notification. One whose owner's account deletion got there first is skipped and
counted - its tombstone belongs in no index - and the next dry run says whether
anything is left. `--verify` reads every inbox the scan names and compares; the
index is eventually consistent, so a row just written may take a moment to appear.

Nothing printed names a person: notifications are named by their event id.
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

from stoa.db.repositories import account_deletion_repo, notification_repo  # noqa: E402
from stoa.security.aws_operator_identity import require_sso_operator_session  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"
COUNTED = ("notifications", "for one person", "for a role", "in no inbox", "in place", "to write")


def _in_place(item: Mapping[str, Any]) -> bool:
    return notification_repo.carried_index_fields(item) == notification_repo.index_fields(item)


def count(items: Sequence[Mapping[str, Any]]) -> Counter[str]:
    """How many notifications there are, by whose inbox they belong in and whether they are there."""
    counts: Counter[str] = Counter()
    for item in items:
        counts["notifications"] += 1
        fields = notification_repo.index_fields(item)
        if "sweep_bucket" not in fields:
            counts["in no inbox"] += 1
        elif item.get("recipient_id"):
            counts["for one person"] += 1
        else:
            counts["for a role"] += 1
        counts["in place" if _in_place(item) else "to write"] += 1
    return counts


def apply(table: Any, items: Sequence[Mapping[str, Any]]) -> Counter[str]:
    """Write every notification's index keys; one whose account is closing is skipped."""
    outcome: Counter[str] = Counter()
    for item in items:
        try:
            written = notification_repo.reindex_event(item, table=table)
        except account_deletion_repo.AccountDeletionConflict:
            outcome["account closing or changed meanwhile, skipped"] += 1
            continue
        outcome["written" if written else "in place"] += 1
    return outcome


def _inbox_of(item: Mapping[str, Any]) -> tuple[str, str] | None:
    """Whose inbox the row itself says it is in: (user id, "") or ("", role)."""
    if "sweep_bucket" not in notification_repo.index_fields(item):
        return None
    recipient_id = item.get("recipient_id")
    if recipient_id:
        return (str(recipient_id), "")
    return ("", str(item.get("recipient_role")))


def verify(table: Any, items: Sequence[Mapping[str, Any]]) -> list[str]:
    """The notifications an inbox should hold and does not, or holds and should not."""
    expected: dict[tuple[str, str], set[str]] = {}
    for item in items:
        inbox = _inbox_of(item)
        if inbox is not None:
            expected.setdefault(inbox, set()).add(str(item.get("event_id")))
    problems: list[str] = []
    for (user_id, role), wanted in sorted(expected.items()):
        found = {
            str(item.get("event_id"))
            for item in notification_repo.list_inbox(user_id=user_id, role=role, table=table)
        }
        # Named by event only: a person's id stays out of the output.
        problems.extend(f"missing from its inbox: {name}" for name in sorted(wanted - found))
        problems.extend(f"in an inbox it does not belong in: {name}" for name in sorted(found - wanted))
    # The site's list: every notification with a creation time, and nothing else.
    listed_wanted = {
        str(item.get("event_id")) for item in items if "listing" in notification_repo.index_fields(item)
    }
    listed_found = {
        str(item.get("event_id"))
        for item in notification_repo.list_site_events(want=len(items) + 1000, table=table)
    }
    problems.extend(f"missing from the site's list: {name}" for name in sorted(listed_wanted - listed_found))
    problems.extend(f"in the site's list, not a notification: {name}" for name in sorted(listed_found - listed_wanted))
    return problems


def run(table: Any, *, apply_writes: bool, verify_index: bool) -> int:
    items = notification_repo.list_all_events(table=table)
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
