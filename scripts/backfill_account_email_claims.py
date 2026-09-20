#!/usr/bin/env python
"""Give accounts that predate the email claim row the claim that now guards them.

Card 009 made (email, role) unique by writing an EMAIL#<address>#<role> row in
the same transaction as the profile, so two administrators opening the same
address concurrently lose the race in the store rather than in a stale read.
That guard only exists for accounts opened after it shipped. Every account that
already existed has no claim row, so for those addresses the only thing
standing between two concurrent opens is the read-before-write the card
replaced -- against an eventually consistent index.

The rows are read as they stand. An account is claimed for the address its
profile carries and the role it holds; a profile parked by a failed opening
(its address rewritten to provisioning_failed:<id>, no "@") never held an
address and is skipped. Where a claim already exists it is left alone, so this
can be run again without deciding anything twice.

Two accounts already sharing one (address, role) is the thing the claim was
introduced to prevent, and it cannot be resolved by writing a row: only one of
them can hold the claim, and which one is a question about those two people.
Such pairs are reported and skipped rather than half-repaired.

Usage:
    python scripts/backfill_account_email_claims.py            # report only
    python scripts/backfill_account_email_claims.py --apply
    python scripts/backfill_account_email_claims.py --verify   # invariant check
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import os
import sys

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stoa.db.repositories import account_email_claim_repo  # noqa: E402

# The key and the condition come from the repository that writes them at run
# time. Spelling either of them again here would mean the guard and the
# backfill could drift apart, and the first anyone would learn of it is an
# address that two accounts both believe they hold.
CLAIM_CONDITION = account_email_claim_repo.CLAIM_CONDITION


def claim_key(email: str, role: str) -> dict[str, str]:
    return account_email_claim_repo.claim_key(email=email, role=role)


def holds_an_address(profile: dict) -> bool:
    """Whether this profile ever held the address it carries.

    A half-opened account is parked with its address rewritten to a value with
    no "@" precisely so it stops matching a normalized email. Claiming that
    value would hand it a guard over a string nobody can ever register.
    """
    email = str(profile.get("email") or "")
    return "@" in email and bool(str(profile.get("role") or "").strip())


def _scan_family(table, *, sk: str, pk_prefix: str) -> list[dict]:
    rows: list[dict] = []
    kwargs = {
        # The invariant is read off the base table, so it is read strongly. An
        # eventually consistent page can report a row written moments ago as
        # missing, and both directions of this check would call that a defect in
        # the data rather than in the reading.
        "ConsistentRead": True,
        "FilterExpression": "SK = :sk AND begins_with(PK, :pk)",
        "ExpressionAttributeValues": {":sk": sk, ":pk": pk_prefix},
    }
    while True:
        response = table.scan(**kwargs)
        rows.extend(response.get("Items", []))
        cursor = response.get("LastEvaluatedKey")
        if not cursor:
            return rows
        kwargs["ExclusiveStartKey"] = cursor


def scan_profiles(table) -> list[dict]:
    return _scan_family(table, sk="PROFILE", pk_prefix="USER#")


def scan_claims(table) -> list[dict]:
    return _scan_family(table, sk=account_email_claim_repo.CLAIM_SK, pk_prefix="EMAIL#")


def orphan_claims(profiles: list[dict], claims: list[dict]) -> list[dict]:
    """Placeholders no live account stands behind.

    The other direction of the same invariant. An account is deleted by replacing its
    profile with a tombstone that carries no address, so a placeholder left behind
    names a pair that reads free and is refused by the store, with nothing left to
    point at. Reported, never written: which rows to remove is a judgement about real
    accounts, and this script does not make those.
    """
    held: dict[str, set[str]] = defaultdict(set)
    for profile in profiles:
        if not holds_an_address(profile):
            continue
        key = claim_key(str(profile["email"]), str(profile["role"]))["PK"]
        held[key].add(str(profile.get("user_id") or profile["PK"]).removeprefix("USER#"))

    orphans = []
    for claim in claims:
        owners = held.get(str(claim.get("PK") or ""), set())
        if str(claim.get("account_id") or "") not in owners:
            orphans.append(claim)
    return orphans


def pairs_to_claim(profiles: list[dict]) -> tuple[list[dict], list[tuple[str, list[dict]]]]:
    """Split the profiles into ones a claim can be written for, and collisions."""
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for profile in profiles:
        if not holds_an_address(profile):
            continue
        email = str(profile["email"]).strip().casefold()
        by_pair[(email, str(profile["role"]).strip())].append(profile)

    claimable: list[dict] = []
    collisions: list[tuple[str, list[dict]]] = []
    for (email, role), holders in sorted(by_pair.items()):
        if len(holders) > 1:
            collisions.append((f"{email} as {role}", holders))
            continue
        claimable.append(holders[0])
    return claimable, collisions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the claim rows")
    parser.add_argument("--verify", action="store_true", help="fail if any account lacks one")
    parser.add_argument("--table", default=os.environ.get("DYNAMODB_TABLE_NAME", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "eu-central-2"))
    args = parser.parse_args()

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    profiles = scan_profiles(table)
    claimable, collisions = pairs_to_claim(profiles)
    orphans = orphan_claims(profiles, scan_claims(table))

    missing = []
    for profile in claimable:
        key = claim_key(str(profile["email"]), str(profile["role"]))
        if "Item" not in table.get_item(Key=key, ConsistentRead=True):
            missing.append(profile)

    print(f"{len(profiles)} profiles, {len(missing)} without a claim row\n")
    for profile in sorted(missing, key=lambda row: str(row.get("email", ""))):
        print(f"  {str(profile.get('email')):38} {str(profile.get('role')):9} {profile['PK']}")

    if collisions:
        print(f"\n{len(collisions)} pairs already held by more than one account:")
        for label, holders in collisions:
            print(f"  {label}: {', '.join(str(h['PK']) for h in holders)}")
        print("  no claim written for these; deciding which account keeps the address")
        print("  is not something a backfill can answer")

    if orphans:
        print(f"\n{len(orphans)} claim rows no live account stands behind:")
        for claim in sorted(orphans, key=lambda row: str(row.get("PK", ""))):
            print(f"  {str(claim.get('PK')):48} account_id={claim.get('account_id')}")
        print("  deciding whether to free these is a judgement about real accounts")

    if args.verify:
        return 1 if missing or collisions or orphans else 0

    if not missing:
        print("\nnothing to do")
        return 1 if collisions or orphans else 0

    if not args.apply:
        print(f"\nreport only; pass --apply to write {len(missing)} claim rows")
        return 0

    written = 0
    for profile in missing:
        email = str(profile["email"])
        role = str(profile["role"])
        try:
            table.put_item(
                Item=account_email_claim_repo.claim_item(
                    email=email,
                    role=role,
                    account_id=str(
                        profile.get("user_id") or profile["PK"]
                    ).removeprefix("USER#"),
                    created_at=str(profile.get("created_at") or ""),
                ),
                ConditionExpression=CLAIM_CONDITION,
            )
            written += 1
        except ClientError as error:
            # Someone opened an account on this pair between the read above and
            # this write. The live claim is the right one; this script must not
            # overwrite a guard that is already doing its job.
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            print(f"  skipped {email} as {role}: claimed while this ran")

    print(f"\nwrote {written} claim rows")
    return 1 if collisions or orphans else 0


if __name__ == "__main__":
    raise SystemExit(main())
