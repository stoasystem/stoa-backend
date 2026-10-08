#!/usr/bin/env python
"""Give the seeded practice exercises the skills the star map draws (#58).

The sixty seeded challenges were written before skill points existed and carry
no `skills`, so every knowledge point reads as having none. The assignment is
the seed's own, read from `seed_practice.CHALLENGE_SKILLS`, so this writes only
what a re-seed would write.

`skills` is part of a challenge's content, so writing it changes the content
hash: the row has to be re-versioned, its hint non-derivability decision
reissued against the new hash, and its pointer rewritten. A row that got the
skills without the rest would be refused by every catalog read, which is why
all four go out together, row by row.

Usage:
    python scripts/backfill_exercise_skills.py            # report only
    python scripts/backfill_exercise_skills.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stoa.db.dynamodb import scan_every_page  # noqa: E402
from stoa.db.repositories import practice_repo  # noqa: E402
from stoa.services import curriculum_translations  # noqa: E402

import seed_practice  # noqa: E402


def stored_challenges(table) -> list[dict]:
    """Every CHALLENGE row, across every page of the table.

    A filtered scan's `Limit` bounds the rows read, not the rows kept, so a
    capped read of a table this size answers from its first page and reports
    nothing to do.
    """
    result = scan_every_page(
        lambda target, **kwargs: target.scan(**kwargs),
        table,
        FilterExpression="begins_with(SK, :prefix)",
        ExpressionAttributeValues={":prefix": "CHALLENGE#"},
    )
    return [dict(row) for row in result.get("Items", [])]


def planned_skills(row: dict) -> tuple[list[str], str | None]:
    """The skills this row should carry, or a reason it cannot be written."""
    challenge_id = str(row.get("challenge_id") or "")
    skills = seed_practice.CHALLENGE_SKILLS.get(challenge_id)
    if not skills:
        return [], f"no skills declared for {challenge_id}"
    unit_id = str(row.get("unit_id") or "")
    for skill in skills:
        owner = curriculum_translations.skill_unit_id(skill)
        if owner is None:
            return [], f"{challenge_id}: unknown skill {skill}"
        if owner != unit_id:
            return [], f"{challenge_id}: skill {skill} belongs to {owner}, not {unit_id}"
    return list(skills), None


def rewritten(row: dict, skills: list[str]) -> tuple[dict, dict]:
    """The canonical row with its skills, new version and reissued decision."""
    canonical = dict(row)
    canonical["skills"] = skills
    decision = dict(canonical.get("hint_non_derivability_decision") or {})
    canonical = practice_repo.version_challenge(canonical)
    if decision:
        decision["challenge_version"] = canonical["challenge_version"]
        decision["content_hash"] = canonical["challenge_content_hash"]
        canonical["hint_non_derivability_decision"] = decision
    return canonical, practice_repo.challenge_pointer(canonical)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default=os.environ.get("DYNAMODB_TABLE_NAME", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "eu-central-2"))
    parser.add_argument("--apply", action="store_true", help="write the skills")
    args = parser.parse_args()

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    rows = stored_challenges(table)
    canonical_rows = [
        row
        for row in rows
        if row.get("entity_type") != practice_repo.CHALLENGE_POINTER_ENTITY
    ]

    settled: list[str] = []
    pending: list[tuple[dict, list[str]]] = []
    refused: list[str] = []
    for row in canonical_rows:
        skills, reason = planned_skills(row)
        if reason:
            refused.append(reason)
        elif list(row.get("skills") or []) == skills:
            settled.append(str(row.get("challenge_id")))
        else:
            pending.append((row, skills))

    print(f"Challenge rows: {len(canonical_rows)}")
    print(f"  already carrying their skills: {len(settled)}")
    print(f"  to write: {len(pending)}")
    print(f"  refused: {len(refused)}")
    for reason in refused:
        print(f"    {reason}")
    for row, skills in pending:
        print(f"    {row.get('challenge_id')} -> {','.join(skills)}")

    if refused:
        print("Refusing to write while any row is unexplained.")
        return 1
    if not args.apply:
        print("[REPORT ONLY] Re-run with --apply to write.")
        return 0

    for row, skills in pending:
        canonical, pointer = rewritten(row, skills)
        table.put_item(Item=canonical)
        table.put_item(Item=pointer)
    print(f"Done! {len(pending)} challenges written to {args.table}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
