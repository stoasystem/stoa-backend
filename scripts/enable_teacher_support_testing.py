#!/usr/bin/env python3
"""Open the human-teacher path for test accounts without a payment provider.

Two independent gates block the flow on a fresh environment:

1. ``teacher_support_allowance_service`` admits a case only when the beneficiary
   has an active ``PAID_GRANT#`` whose plan carries teacher-support cases. Only
   ``teacher_supported`` and ``family`` do; ``free_trial`` and ``student`` carry
   zero. That grant is written exclusively by the provider activation path, so
   an administrator tier change alone never unlocks teacher support.
2. ``teacher_dispatch_service`` counts a teacher as dispatchable only when the
   profile carries an available status and at least one subject.

This script closes both for named test identities. It is an operator tool and is
deliberately isolated from request-path authority.

Usage:
    python scripts/enable_teacher_support_testing.py --dry-run
    python scripts/enable_teacher_support_testing.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

import boto3

REGION = "eu-central-2"
TABLE_NAME = "stoa-main"
USER_POOL_ID = "eu-central-2_Ss93YQzjJ"

PARENT_EMAIL = "parent@test.stoaedu.ch"
STUDENT_EMAIL = "student@test.stoaedu.ch"
TEACHER_EMAIL = "teacher@test.stoaedu.ch"

PLAN_ID = "teacher_supported"
GRANT_SCHEMA_VERSION = "paid_beneficiary_grant.v1"

TEACHER_SUBJECTS = ["mathematics", "physics"]
TEACHER_MAX_ACTIVE_SESSIONS = 3


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def log(message: str) -> None:
    print(f"[teacher-support] {message}", flush=True)


def find_profile(table: Any, cognito: Any, email: str) -> dict[str, Any]:
    """Resolve through the Cognito subject, the way the request path resolves identity.

    Legacy profiles share these email addresses under user ids that no longer map
    to any provider identity, so an email scan is ambiguous.
    """
    response = cognito.admin_get_user(UserPoolId=USER_POOL_ID, Username=email)
    subject = next(
        attribute["Value"]
        for attribute in response["UserAttributes"]
        if attribute["Name"] == "sub"
    )
    item = table.get_item(
        Key={"PK": f"USER#{subject}", "SK": "PROFILE"}, ConsistentRead=True
    ).get("Item")
    if not item:
        raise SystemExit(f"{email} has Cognito subject {subject} but no PROFILE")
    if item.get("user_id") != subject:
        raise SystemExit(f"{email} profile user_id does not match its Cognito subject")
    return item


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"precondition failed: {message}")


def fence_generation(table: Any, user_id: str) -> int:
    item = table.get_item(
        Key={"PK": f"USER#{user_id}", "SK": "ACCOUNT_FENCE"}, ConsistentRead=True
    ).get("Item")
    require(bool(item), f"{user_id} has no ACCOUNT_FENCE")
    require(item.get("status") == "active", f"{user_id} fence is not active")
    generation = int(item.get("generation") or 0)
    require(generation > 0, f"{user_id} fence generation is not positive")
    return generation


def binding(table: Any, pk_user: str, sk: str, label: str) -> dict[str, Any]:
    item = table.get_item(
        Key={"PK": f"USER#{pk_user}", "SK": sk}, ConsistentRead=True
    ).get("Item")
    require(bool(item), f"{label} binding is missing")
    require(item.get("status") == "active", f"{label} binding is not active")
    require(item.get("relationship") == "child", f"{label} binding is not a child link")
    version = int(item.get("version") or 0)
    require(version > 0, f"{label} binding version is not positive")
    return item


def enable_teacher_dispatch(table: Any, teacher: dict[str, Any], *, dry_run: bool) -> None:
    teacher_id = str(teacher["user_id"])
    if dry_run:
        log(f"  [DRY-RUN] would mark {teacher_id[:8]}... available for {TEACHER_SUBJECTS}")
        return
    table.update_item(
        Key={"PK": f"USER#{teacher_id}", "SK": "PROFILE"},
        UpdateExpression=(
            "SET availability_status = :status, primary_subjects = :subjects, "
            "max_active_sessions = :sessions, dispatch_active_count = :zero, "
            "updated_at = :now"
        ),
        ExpressionAttributeValues={
            ":status": "available",
            ":subjects": TEACHER_SUBJECTS,
            ":sessions": TEACHER_MAX_ACTIVE_SESSIONS,
            ":zero": 0,
            ":now": now_iso(),
        },
    )
    log(f"  marked teacher {teacher_id[:8]}... available for {TEACHER_SUBJECTS}")


def grant_paid_entitlement(
    table: Any,
    parent: dict[str, Any],
    student: dict[str, Any],
    *,
    dry_run: bool,
) -> None:
    parent_id = str(parent["user_id"])
    student_id = str(student["user_id"])

    require(parent.get("role") == "parent", "parent profile role")
    require(parent.get("account_status") == "active", "parent account status")
    require(student.get("role") == "student", "student profile role")
    require(student.get("account_status") == "active", "student account status")
    require(student.get("parent_id") == parent_id, "student parent_id linkage")
    require(
        student.get("parent_binding_status") == "active",
        "student parent_binding_status",
    )

    parent_version = int(parent.get("version") or 0)
    student_version = int(student.get("version") or 0)
    require(parent_version > 0, "parent profile version")
    require(student_version > 0, "student profile version")

    forward = binding(table, parent_id, f"CHILD#{student_id}", "parent->student")
    reverse = binding(table, student_id, f"PARENT#{parent_id}", "student->parent")

    parent_generation = fence_generation(table, parent_id)
    student_generation = fence_generation(table, student_id)

    # The read path only requires a 64-hex digest; deriving it from the identity
    # pair keeps the record reproducible without inventing a provider id.
    subscription_digest = sha256(
        f"stoa:manual-test-entitlement:v1:{parent_id}:{student_id}".encode()
    ).hexdigest()

    grant = {
        "PK": f"PAID_GRANT#{parent_id}",
        "SK": f"BENEFICIARY#{student_id}",
        "entity_type": "beneficiary_grant",
        "schema_version": GRANT_SCHEMA_VERSION,
        "parent_id": parent_id,
        "beneficiary_id": student_id,
        "grant_status": "active",
        "command_id": f"manual-test-{subscription_digest[:16]}",
        "subscription_id_digest": subscription_digest,
        "grant_version": 1,
        "plan_id": PLAN_ID,
        "plan_version": 1,
        "allowance_version": 1,
        "activation_version": 1,
        "activated_at": now_iso(),
        "parent_profile_version": parent_version,
        "parent_account_fence_generation": parent_generation,
        "student_profile_version": student_version,
        "student_account_fence_generation": student_generation,
        "forward_relationship_version": int(forward["version"]),
        "reverse_relationship_version": int(reverse["version"]),
    }

    if dry_run:
        log(f"  [DRY-RUN] would grant {PLAN_ID} to {student_id[:8]}... under {parent_id[:8]}...")
        return

    table.put_item(Item=grant)
    log(f"  wrote PAID_GRANT {PLAN_ID}: parent {parent_id[:8]}... -> student {student_id[:8]}...")

    for user_id, label in ((parent_id, "parent"), (student_id, "student")):
        table.update_item(
            Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
            UpdateExpression="SET subscription_tier = :tier, updated_at = :now",
            ExpressionAttributeValues={":tier": PLAN_ID, ":now": now_iso()},
        )
        log(f"  set {label} subscription_tier = {PLAN_ID}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)
    cognito = boto3.client("cognito-idp", region_name=REGION)
    log(f"table={TABLE_NAME} plan={PLAN_ID} dry_run={args.dry_run}")

    parent = find_profile(table, cognito, PARENT_EMAIL)
    student = find_profile(table, cognito, STUDENT_EMAIL)
    teacher = find_profile(table, cognito, TEACHER_EMAIL)
    log(f"resolved parent={parent['user_id']}")
    log(f"resolved student={student['user_id']}")
    log(f"resolved teacher={teacher['user_id']}")

    log("\n[1/2] paid entitlement grant")
    grant_paid_entitlement(table, parent, student, dry_run=args.dry_run)

    log("\n[2/2] teacher dispatch eligibility")
    enable_teacher_dispatch(table, teacher, dry_run=args.dry_run)

    log("\ndone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
