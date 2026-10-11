#!/usr/bin/env python
"""Turn the free text in `grade` into the year-group codes the platform now reads.

The grade box took free text, and the profiles hold five different things:
nothing, a field of spaces, "Grade 6", "Sek1" and "14". The curriculum has
spelled its year groups `grade_6_primary` all along, and the one place a grade
is read - the assistant's system prompt - was being handed whatever the student
typed, so the model was told "The student is in 14".

What is written is decided by `learning_profile_service.LEGACY_GRADE_SPELLINGS`,
the same table the read path uses, so this script cannot drift from what the
prompt already understands. Three outcomes, and they are kept apart:

  * a spelling the table knows  -> the code it means
  * nothing, or only whitespace -> left exactly as it is; not saying is allowed
    and rewriting a blank to a blank would still touch `updated_at`
  * anything else               -> reported, never written. "14" is an age in a
    year-group box; no one can say which year it meant, and guessing is the
    defect this card exists to remove.

Usage:
    python scripts/backfill_student_grade_codes.py            # report only
    python scripts/backfill_student_grade_codes.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stoa.services import learning_profile_service  # noqa: E402


@dataclass
class Plan:
    """What this run would do, before anything is written."""

    rewrite: list[tuple[dict, str]] = field(default_factory=list)
    settled: list[str] = field(default_factory=list)
    blank: list[str] = field(default_factory=list)
    unmappable: list[tuple[str, str]] = field(default_factory=list)


def scan_profiles(table) -> list[dict]:
    profiles: list[dict] = []
    kwargs = {
        "FilterExpression": "SK = :sk AND begins_with(PK, :pk)",
        "ExpressionAttributeValues": {":sk": "PROFILE", ":pk": "USER#"},
    }
    while True:
        response = table.scan(**kwargs)
        profiles.extend(response.get("Items", []))
        cursor = response.get("LastEvaluatedKey")
        if not cursor:
            return profiles
        kwargs["ExclusiveStartKey"] = cursor


def planned_grade(profile: dict) -> tuple[str | None, str | None]:
    """The code this row should carry, or the reason it cannot be decided.

    A row already carrying a code, and a row carrying no grade at all, are both
    `(None, None)`: nothing to write and nothing to explain.
    """
    stored = str(profile.get("grade") or "")
    if not stored.strip():
        return None, None
    code = learning_profile_service.resolve_grade_code(stored)
    if code is None:
        return None, stored
    if code == stored:
        return None, None
    return code, None


def plan(profiles: list[dict]) -> Plan:
    result = Plan()
    for profile in profiles:
        if str(profile.get("role") or "") != "student":
            continue
        stored = str(profile.get("grade") or "")
        user_id = str(profile.get("user_id") or profile.get("PK") or "<no id>")
        code, unreadable = planned_grade(profile)
        if unreadable is not None:
            result.unmappable.append((user_id, unreadable))
        elif code is not None:
            result.rewrite.append((profile, code))
        elif not stored.strip():
            result.blank.append(user_id)
        else:
            result.settled.append(user_id)
    return result


def report(result: Plan) -> None:
    print(f"students to rewrite:      {len(result.rewrite)}")
    print(f"already a code:           {len(result.settled)}")
    print(f"no grade (left as is):    {len(result.blank)}")
    print(f"unmappable (not written): {len(result.unmappable)}")
    for profile, code in result.rewrite:
        user_id = str(profile.get("user_id") or profile.get("PK") or "<no id>")
        print(f"    {user_id:40} {str(profile.get('grade')):12} -> {code}")
    for user_id, stored in result.unmappable:
        print(f"    {user_id:40} {stored!r:12} -> UNMAPPABLE, left alone")


def write(table, result: Plan) -> int:
    for profile, code in result.rewrite:
        table.update_item(
            Key={"PK": profile["PK"], "SK": profile["SK"]},
            UpdateExpression="SET #grade = :grade",
            ExpressionAttributeNames={"#grade": "grade"},
            ExpressionAttributeValues={":grade": code},
        )
    return len(result.rewrite)


def run(table, *, apply: bool) -> Plan:
    """Read every profile, say what it would do, and write only when asked to."""
    result = plan(scan_profiles(table))
    report(result)
    if not apply:
        print("\n[REPORT ONLY] Re-run with --apply to write.")
        return result
    written = write(table, result)
    print(f"\nwrote {written} profiles")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default=os.environ.get("DYNAMODB_TABLE_NAME", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "eu-central-2"))
    parser.add_argument("--apply", action="store_true", help="write the codes")
    args = parser.parse_args()

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    run(table, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
