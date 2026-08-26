#!/usr/bin/env python
"""Give accounts created before the identity cutover the fields login demands.

On 2026-07-15 sign-in began requiring account_status to be active, and for
students and parents a registration_command and registration_role naming how
the account was created. Accounts that already existed were never given them
and no backfill shipped, so every one of them was locked out with a message
telling the account holder to contact support.

The rows are read as they stand: a profile missing account_status was never
deactivated, it was never written, and the public roles being restored here
did register through public self-service. Anything already carrying a value is
left exactly as it is.

Usage:
    python scripts/backfill_account_registration.py            # report only
    python scripts/backfill_account_registration.py --apply
    python scripts/backfill_account_registration.py --verify   # invariant check
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

PUBLIC_ROLES = frozenset({"student", "parent"})
PUBLIC_REGISTRATION_COMMAND = "public_self_service"
ACTIVE = "active"


def recorded_activation(profile: dict) -> str | None:
    """Whether this account was ever activated, under either field name.

    Older rows recorded it as account_activation_status, which almost nothing
    reads any more; a row saying pending there is pending, not unwritten.
    """
    for field in ("account_status", "account_activation_status"):
        value = profile.get(field)
        if value:
            return str(value)
    return None


def missing_fields(profile: dict) -> dict[str, str]:
    """What this profile lacks before sign-in will accept it.

    An account still waiting on its email is meant to be refused, so it is not
    something this repairs.
    """
    role = str(profile.get("role") or "")
    activation = recorded_activation(profile)
    if activation is not None and activation != ACTIVE:
        return {}
    wanted: dict[str, str] = {}
    if profile.get("account_status") != ACTIVE:
        wanted["account_status"] = ACTIVE
    if role in PUBLIC_ROLES:
        if not profile.get("registration_command"):
            wanted["registration_command"] = PUBLIC_REGISTRATION_COMMAND
        if not profile.get("registration_role"):
            wanted["registration_role"] = role
    return wanted


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the fields")
    parser.add_argument("--verify", action="store_true", help="fail if any account is blocked")
    parser.add_argument("--table", default=os.environ.get("DYNAMODB_TABLE_NAME", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "eu-central-2"))
    args = parser.parse_args()

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    profiles = scan_profiles(table)
    blocked = [(p, missing_fields(p)) for p in profiles]
    blocked = [(p, wanted) for p, wanted in blocked if wanted]

    print(f"{len(profiles)} profiles, {len(blocked)} cannot sign in\n")
    for profile, wanted in sorted(blocked, key=lambda pair: str(pair[0].get("email", ""))):
        email = profile.get("email", "<no email>")
        role = profile.get("role", "?")
        print(f"  {email:38} {role:9} + {', '.join(sorted(wanted))}")

    if args.verify:
        return 1 if blocked else 0

    if not blocked:
        print("\nnothing to do")
        return 0

    if not args.apply:
        print(f"\nreport only; pass --apply to write {len(blocked)} profiles")
        return 0

    for profile, wanted in blocked:
        names = {f"#{key}": key for key in wanted}
        values = {f":{key}": value for key, value in wanted.items()}
        table.update_item(
            Key={"PK": profile["PK"], "SK": profile["SK"]},
            UpdateExpression="SET " + ", ".join(f"#{key}=:{key}" for key in wanted),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    print(f"\nwrote {len(blocked)} profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
