#!/usr/bin/env python3
"""Write every student's answer rollups and their marker (card 135).

The star map reads one rollup row per lesson and knowledge point
(`ATTEMPTS#{student}` / `ROLLUP#L#{lesson}#U#{unit}`) instead of every answer,
but only under the marker `ROLLUP#!STATE`: without it, it reads every answer as
before. Every judged answer from the release that writes rollups moves its
row in the answer's own transaction; the answers before it are in no rollup
until this script adds them. Run it once that release is deployed.

    python scripts/backfill_attempt_rollups.py            # dry run: reports, writes nothing
    python scripts/backfill_attempt_rollups.py --apply    # writes what the dry run reported

The accounts come from GSI-Listing (`listing = account_profile`), not a scan.
For each, every answer is read (strongly consistent, the star map's fields
only) and the rollups it makes are worked out by the star map's own rules
(`student_evidence.expected_attempt_rollups`), then compared with the rollup
rows and the marker. `--apply`, behind the account's fence, per row: adds the
exercise sets (an `ADD`, which a second run or a live answer cannot undo),
sets `last_judged_at` only where the stored one is missing or older, and last
writes the marker. A second run reports nothing to write.

Nothing printed names a person but the account ids of the first rows that
differ.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT, ROOT / "src"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from stoa.db import table as db_table  # noqa: E402
from stoa.db import owner_registry  # noqa: E402
from stoa.db.repositories import account_deletion_repo, practice_repo, user_repo  # noqa: E402
from stoa.security.aws_operator_identity import require_sso_operator_session  # noqa: E402
from stoa.services import student_evidence  # noqa: E402
from stoa.services.student_evidence import AttemptRollup  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"
SHOWN_ACCOUNTS = 20
COUNTED = (
    "accounts",
    "in agreement",
    "rollup missing",
    "exercises missing",
    "exercises extra",
    "last judged differs",
    "marker missing",
)


def account_ids(table: Any) -> list[str]:
    """Every student with a profile, from GSI-Listing."""
    found: list[str] = []
    for row in db_table.rows(
        "query",
        table=table,
        key=user_repo.ACCOUNT_LIST_INDEX_KEY,
        page_budget=10_000,
        IndexName=user_repo.ACCOUNT_LIST_INDEX,
        KeyConditionExpression="#listing = :listing",
        FilterExpression="SK = :profile AND #role = :student",
        ExpressionAttributeNames={"#listing": "listing", "#pk": "PK", "#role": "role"},
        ExpressionAttributeValues={
            ":listing": account_deletion_repo.ACCOUNT_LISTING,
            ":profile": "PROFILE",
            ":student": "student",
        },
        ProjectionExpression="#pk",
    ):
        pk = str(row.get("PK") or "")
        if pk.startswith("USER#") and len(pk) > len("USER#"):
            found.append(pk.removeprefix("USER#"))
    return sorted(set(found))


def differences(
    expected: Mapping[tuple[str, str], AttemptRollup],
    stored: Mapping[tuple[str, str], AttemptRollup],
    *,
    marked: bool,
) -> Counter[str]:
    """What the stored rollups lack against the ones the answers make."""
    found: Counter[str] = Counter()
    for place, want in expected.items():
        have = stored.get(place)
        if have is None:
            found["rollup missing"] += 1
            continue
        if not (want.right_alone <= have.right_alone and want.right_asked <= have.right_asked):
            found["exercises missing"] += 1
        if have.right_alone - want.right_alone or have.right_asked - want.right_asked:
            found["exercises extra"] += 1
        if have.last_judged_at != want.last_judged_at:
            found["last judged differs"] += 1
    extra = set(stored) - set(expected)
    if extra:
        found["exercises extra"] += len(extra)
    if not marked:
        found["marker missing"] += 1
    return +found


def _add_operation(
    student_id: str, place: tuple[str, str], rollup: AttemptRollup, generation: int
) -> dict[str, Any]:
    """The row's owner fields set and its exercises added; no condition on what it held."""
    lesson_id, unit_id = place
    values: dict[str, Any] = {
        ":entity_type": practice_repo.ATTEMPT_ROLLUP_ENTITY,
        ":student": student_id,
        ":generation": generation,
        ":lesson": lesson_id,
        ":unit": unit_id,
    }
    added: list[str] = []
    if rollup.right_alone:
        values[":alone"] = set(rollup.right_alone)
        added.append("right_alone :alone")
    if rollup.right_asked:
        values[":asked"] = set(rollup.right_asked)
        added.append("right_asked :asked")
    expression = (
        "SET entity_type = :entity_type, student_id = :student, user_id = :student, "
        "owner_id = :student, account_fence_generation = :generation, "
        "lesson_id = :lesson, unit_id = :unit"
    )
    if added:
        expression += " ADD " + ", ".join(added)
    return {
        "Update": {
            "Key": practice_repo.attempt_rollup_key(student_id, lesson_id, unit_id),
            "UpdateExpression": expression,
            "ConditionExpression": "attribute_not_exists(PK) OR owner_id = :student",
            "ExpressionAttributeValues": values,
        }
    }


def _judged_at_operation(
    student_id: str, place: tuple[str, str], judged_at: str
) -> dict[str, Any]:
    """`last_judged_at` moved forward only: a live answer may have set a later one."""
    return {
        "Update": {
            "Key": practice_repo.attempt_rollup_key(student_id, *place),
            "UpdateExpression": "SET last_judged_at = :at",
            "ConditionExpression": (
                "owner_id = :student AND "
                "(attribute_not_exists(last_judged_at) OR last_judged_at < :at)"
            ),
            "ExpressionAttributeValues": {":student": student_id, ":at": judged_at},
        }
    }


def _write(table: Any, student_id: str, operation: dict[str, Any], generation: int) -> None:
    db_table.fenced(
        student_id,
        [operation],
        generation=generation,
        rows=owner_registry.rows_after(operation["Update"]["Key"], [operation]),
        resend_own_conflicts=True,
        table=table,
    )


def apply_account(
    table: Any,
    student_id: str,
    expected: Mapping[tuple[str, str], AttemptRollup],
    outcome: Counter[str],
) -> None:
    """Add what the answers say to the rollups, then mark them complete."""
    try:
        generation = int(
            account_deletion_repo.require_active_account_fence(student_id, table=table)[
                "generation"
            ]
        )
        for place, rollup in expected.items():
            _write(table, student_id, _add_operation(student_id, place, rollup, generation), generation)
            outcome["rows added to"] += 1
            if rollup.last_judged_at:
                try:
                    _write(
                        table,
                        student_id,
                        _judged_at_operation(student_id, place, rollup.last_judged_at),
                        generation,
                    )
                    outcome["last judged moved"] += 1
                except db_table.WriteRefused:
                    outcome["last judged already later"] += 1
        practice_repo.mark_attempt_rollups_complete(student_id, table=table)
        outcome["marked"] += 1
    except account_deletion_repo.AccountDeletionConflict:
        outcome["account not writable, skipped"] += 1
    except db_table.WriteRefused:
        # A rollup row another account owns, or a row still busy after every resend.
        outcome["refused, skipped"] += 1


def read_account(
    table: Any, student_id: str
) -> tuple[dict[tuple[str, str], AttemptRollup], dict[tuple[str, str], AttemptRollup], bool]:
    """The rollups the answers make, the ones stored, and whether the marker stands."""
    attempts = practice_repo.list_attempt_facts(student_id, table=table)
    rollups = practice_repo.list_attempt_rollups(student_id, table=table)
    return (
        student_evidence.expected_attempt_rollups(attempts),
        student_evidence.stored_attempt_rollups(rollups),
        student_evidence.attempt_rollups_complete(rollups),
    )


def run(
    table: Any,
    *,
    apply_writes: bool,
    accounts: Callable[[Any], Sequence[str]] = account_ids,
) -> int:
    counts: Counter[str] = Counter()
    outcome: Counter[str] = Counter()
    differing: list[str] = []
    for student_id in accounts(table):
        counts["accounts"] += 1
        expected, stored, marked = read_account(table, student_id)
        found = differences(expected, stored, marked=marked)
        if not found:
            counts["in agreement"] += 1
            continue
        counts.update(found)
        if len(differing) < SHOWN_ACCOUNTS:
            differing.append(student_id)
        if apply_writes:
            apply_account(table, student_id, expected, outcome)
    print(" | ".join(f"{name}: {counts[name]}" for name in COUNTED))
    if differing:
        print("First accounts that differ: " + ", ".join(differing))
    if not apply_writes:
        print("[DRY RUN] Nothing written. Run again with --apply to write these rows.")
        return 0
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
    parser.add_argument("--apply", action="store_true", help="write what the dry run reports")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    session = require_sso_operator_session(
        profile_name=args.profile,
        region_name=args.region,
        expected_account_id=args.account_id,
    )
    table = session.resource("dynamodb", region_name=args.region).Table(args.table)
    db_table.install(table)
    return run(table, apply_writes=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
