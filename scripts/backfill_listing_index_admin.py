#!/usr/bin/env python3
"""Put the rows the admin pages count and list in GSI-Listing (cards 133, 135).

`/admin/stats` reads the legacy questions and the help requests, and the
curriculum worklist reads the lesson versions and pointers, through GSI-Listing
instead of a scan of the whole table. A help request carries the keys from the
release that writes them on (`help_requests.listing_fields`), a version or a
pointer from every write after it (`curriculum_ops_repo.listing_fields`); a
legacy question is no longer written at all (`question_repo.listing_fields`).
Rows written before are missing from the index until this script writes them.
Run it once the release that reads the index is deployed.

Card 135 adds two lists whose readers wait for this script: the moderation
cases (`moderation_repo.listing_fields`) and the authorization allow stream the
audit retention archives (`security_audit_repo.listing_fields`). Each keeps its
old scan until `--apply` has written every row's keys and then, as its last
step, the list's marker (`listing_index.marker_key`). Run it once the release
that writes those keys is deployed everywhere, or a row an older release writes
afterwards would be missing from a list its reader already trusts.

Its second batch adds three more marked lists: the weekly report summaries and
the report recovery jobs (`report_repo.listing_fields`), read by the admin
report pages, the recovery job targets and the operator email counts; and the
curriculum metrics (`curriculum_analytics_repo.METRIC_LISTING`).

    python scripts/backfill_listing_index_admin.py            # dry run: counts, writes nothing
    python scripts/backfill_listing_index_admin.py --apply    # writes the rows the dry run counted
    python scripts/backfill_listing_index_admin.py --verify   # reads the index back, writes nothing

It reads the table with one scan, page by page. Each write sets `listing` and
`listed_at` on the condition that the row is still there and has no `listing`
(and, for a case, that it is not a privacy tombstone): a row written meanwhile
by a release that sets them is left as it is, and a second run writes nothing,
so a run cut short is finished by running it again. No other attribute is
touched. A marker is written only by a run that raised nothing.

Nothing printed names a person: rows are counted, and named by their key only
in `--verify`, whose keys hold no account id.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
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

from stoa.db import listing_index  # noqa: E402
from stoa.db import table as db_table  # noqa: E402
from stoa.db.repositories import (  # noqa: E402
    account_deletion_repo,
    curriculum_analytics_repo,
    curriculum_ops_repo,
    moderation_repo,
    question_repo,
    report_repo,
    security_audit_repo,
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
    moderation_repo.CASE_LISTING,
    security_audit_repo.ALLOWED_LISTING,
    report_repo.REPORT_LISTING,
    report_repo.RECOVERY_JOB_LISTING,
    curriculum_analytics_repo.METRIC_LISTING,
)
#: The lists whose readers keep their scan until this script's marker is there.
MARKED = (
    moderation_repo.CASE_LISTING,
    security_audit_repo.ALLOWED_LISTING,
    report_repo.REPORT_LISTING,
    report_repo.RECOVERY_JOB_LISTING,
    curriculum_analytics_repo.METRIC_LISTING,
)
#: What else a write requires of the row, by list.
_NOT_TOMBSTONE = (
    " AND (attribute_not_exists(#privacy_deleted) OR #privacy_deleted <> :deleted)",
    {"#privacy_deleted": "privacy_deleted"},
    {":deleted": True},
)
_STILL = {
    report_repo.REPORT_LISTING: _NOT_TOMBSTONE,
    report_repo.RECOVERY_JOB_LISTING: _NOT_TOMBSTONE,
    moderation_repo.CASE_LISTING: (
        " AND (attribute_not_exists(#privacy_deleted) OR #privacy_deleted <> :deleted)",
        {"#privacy_deleted": "privacy_deleted"},
        {":deleted": True},
    ),
}
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
    if entity_type == "moderation_case":
        return moderation_repo.listing_fields(item)
    if entity_type == "security_audit_event":
        return security_audit_repo.listing_fields(item)
    if entity_type == curriculum_analytics_repo.METRIC_ENTITY:
        updated_at = item.get("updated_at")
        if not isinstance(updated_at, str) or not updated_at:
            return {}
        return {"listing": curriculum_analytics_repo.METRIC_LISTING, "listed_at": updated_at}
    if report_repo.listing_fields(item):
        return report_repo.listing_fields(item)
    return question_repo.listing_fields(item)


def _untimed(item: Mapping[str, Any]) -> bool:
    """A live report, recovery job or metric row its list would leave out for want of a time."""
    if item.get("privacy_deleted") is True or account_deletion_repo.is_deletion_tombstone(item):
        return False
    pk = str(item.get("PK") or "")
    if item.get("entity_type") == curriculum_analytics_repo.METRIC_ENTITY:
        return not item.get("updated_at")
    if item.get("SK") == "SUMMARY" and pk.startswith(("REPORT#", "REPORT_RECOVERY_JOB#")):
        return not item.get("created_at")
    return False


def _row_key(item: Mapping[str, Any]) -> tuple[str, str]:
    return (str(item["PK"]), str(item["SK"]))


def count(items: Iterable[Mapping[str, Any]]) -> Counter[str]:
    """Rows by the list they belong in, and whether they are in it."""
    counts: Counter[str] = Counter()
    for item in items:
        fields = listing_fields(item)
        if not fields and _untimed(item):
            counts["no timestamp, never listed"] += 1
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
        condition, names, values = _STILL.get(fields["listing"], ("", {}, {}))
        try:
            db_table.update(
                table=table,
                Key={"PK": item["PK"], "SK": item["SK"]},
                UpdateExpression="SET #listing = :listing, #listed_at = :listed_at",
                ConditionExpression=(
                    "attribute_exists(PK) AND attribute_not_exists(#listing)" + condition
                ),
                ExpressionAttributeNames={
                    "#listing": "listing",
                    "#listed_at": "listed_at",
                    **names,
                },
                ExpressionAttributeValues={
                    ":listing": fields["listing"],
                    ":listed_at": fields["listed_at"],
                    **values,
                },
            )
        except db_table.WriteRefused:
            outcome["listed or gone meanwhile, skipped"] += 1
            continue
        outcome["written"] += 1
    return outcome


def mark(table: Any, *, at: str) -> None:
    """Tell the readers of `MARKED` that their list now holds every row."""
    for name in MARKED:
        db_table.put(
            table=table,
            Item={**listing_index.marker_key(name), "complete": True, "completed_at": at},
        )


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
    problems: list[str] = [
        f"no marker for {name}" for name in MARKED if not listing_index.backfilled(name, table=table)
    ]
    for name in LISTINGS:
        found = _listed_keys(table, name)
        problems.extend(f"missing from {name}: {pk} {sk}" for pk, sk in sorted(wanted[name] - found))
        problems.extend(f"in {name}, should not be: {pk} {sk}" for pk, sk in sorted(found - wanted[name]))
    return problems


# What `listing_fields` and `count` read; a version's content stays on the table.
_SCANNED = (
    "PK", "SK", "entity_type", "status", "owner_deletion_generation", "conversation_id",
    "created_at", "escalated_at", "updated_at", "listing", "event_type", "privacy_deleted",
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


def now() -> str:
    return datetime.now(UTC).isoformat()


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
    print(f"no timestamp, never listed: {counts['no timestamp, never listed']}")
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
    mark(table, at=now())
    print(f"Marked complete: {', '.join(MARKED)}")
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
