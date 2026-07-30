#!/usr/bin/env python3
"""Provision isolated sandbox test accounts for Phase 476 payment testing.

Creates the following test identities in the stoa-sandbox Cognito User Pool
and stoa-sandbox DynamoDB table:

  - 1 parent     sandbox.parent@stoaedu.test
  - 3 students   sandbox.student1..3@stoaedu.test
  - 1 admin      sandbox.admin@stoaedu.test

All accounts share the password supplied via SANDBOX_TEST_PASSWORD env var.
Parent ↔ student bindings are written directly to DynamoDB so the accounts
are ready for checkout testing without manual in-app linking.

Usage:
    export SANDBOX_TEST_PASSWORD="SandboxTest123!"
    python scripts/provision_sandbox_accounts.py

    # Dry-run (print actions, change nothing):
    python scripts/provision_sandbox_accounts.py --dry-run

    # Tear down sandbox accounts after testing:
    python scripts/provision_sandbox_accounts.py --teardown

Prerequisites:
    - AWS credentials with access to the stoa-sandbox Cognito pool and table.
    - The stoa-sandbox CDK stacks have been deployed.
    - boto3 installed (included in uv dev extras).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

# ── Sandbox resource identifiers ──────────────────────────────────────────────
# Override via CLI flags or environment variables after deploying sandbox stacks.
DEFAULT_REGION = "eu-central-2"
DEFAULT_TABLE = "stoa-sandbox"

SANDBOX_DOMAIN = "stoaedu.test"
PARENT_EMAIL = f"sandbox.parent@{SANDBOX_DOMAIN}"
ADMIN_EMAIL = f"sandbox.admin@{SANDBOX_DOMAIN}"
STUDENT_EMAILS = [
    f"sandbox.student1@{SANDBOX_DOMAIN}",
    f"sandbox.student2@{SANDBOX_DOMAIN}",
    f"sandbox.student3@{SANDBOX_DOMAIN}",
]
TEST_ACCOUNTS = {
    "parent": [PARENT_EMAIL],
    "student": STUDENT_EMAILS,
    "admin": [ADMIN_EMAIL],
}

PARENT_DISPLAY_NAME = "Sandbox Parent"
ADMIN_DISPLAY_NAME = "Sandbox Admin"
STUDENT_DISPLAY_NAMES = ["Sandbox Student 1", "Sandbox Student 2", "Sandbox Student 3"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_uuid() -> str:
    return str(uuid.uuid4())


def log(msg: str) -> None:
    print(f"[sandbox-provision] {msg}", flush=True)


def require_password() -> str:
    pw = os.environ.get("SANDBOX_TEST_PASSWORD", "").strip()
    if not pw:
        sys.exit(
            "ERROR: Set SANDBOX_TEST_PASSWORD env var before running.\n"
            "Example: export SANDBOX_TEST_PASSWORD='SandboxTest123!'"
        )
    return pw


# ── Cognito helpers ───────────────────────────────────────────────────────────

def cognito_create_or_reset(
    cognito_client: Any,
    user_pool_id: str,
    email: str,
    role: str,
    password: str,
    *,
    dry_run: bool,
) -> str:
    """Create a confirmed Cognito user (or reset password if exists). Returns sub."""
    if dry_run:
        log(f"  [DRY-RUN] Would create Cognito user: {email} (role={role})")
        return f"dry-run-sub-{email}"

    try:
        resp = cognito_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            TemporaryPassword=password,
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:role", "Value": role},
                {"Name": "custom:subscription_tier", "Value": "free_trial"},
            ],
        )
        sub = next(
            a["Value"]
            for a in resp["User"]["Attributes"]
            if a["Name"] == "sub"
        )
        log(f"  Created Cognito user: {email}  sub={sub[:8]}...")
    except ClientError as e:
        if e.response["Error"]["Code"] != "UsernameExistsException":
            raise
        log(f"  User already exists, resetting password: {email}")
        cognito_client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=password,
            Permanent=True,
        )
        resp = cognito_client.admin_get_user(
            UserPoolId=user_pool_id, Username=email
        )
        sub = next(
            a["Value"]
            for a in resp["UserAttributes"]
            if a["Name"] == "sub"
        )

    # Ensure password is permanent (no force-change on first login)
    cognito_client.admin_set_user_password(
        UserPoolId=user_pool_id,
        Username=email,
        Password=password,
        Permanent=True,
    )
    return sub


def cognito_delete(
    cognito_client: Any,
    user_pool_id: str,
    email: str,
    *,
    dry_run: bool,
) -> None:
    if dry_run:
        log(f"  [DRY-RUN] Would delete Cognito user: {email}")
        return
    try:
        cognito_client.admin_delete_user(UserPoolId=user_pool_id, Username=email)
        log(f"  Deleted Cognito user: {email}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "UserNotFoundException":
            log(f"  User not found (already deleted?): {email}")
        else:
            raise


# ── DynamoDB helpers ──────────────────────────────────────────────────────────

def dynamo_put_profile(
    table: Any,
    user_id: str,
    email: str,
    role: str,
    name: str,
    extra: dict[str, Any] | None = None,
    *,
    dry_run: bool,
) -> None:
    item: dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "email": email,
        "role": role,
        "name": name,
        "subscription_tier": "free_trial",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "_sandbox": True,
    }
    if extra:
        item.update(extra)

    if dry_run:
        log(f"  [DRY-RUN] Would put DynamoDB profile: {json.dumps(item, indent=2)}")
        return

    table.put_item(Item=item)
    log(f"  Wrote DynamoDB profile: PK=USER#{user_id[:8]}... role={role}")


def dynamo_put_parent_child_binding(
    table: Any,
    parent_id: str,
    student_id: str,
    student_email: str,
    *,
    dry_run: bool,
) -> None:
    """Write bidirectional parent ↔ student binding records."""
    now = now_iso()

    # Parent → child binding
    parent_child_item = {
        "PK": f"USER#{parent_id}",
        "SK": f"CHILD#{student_id}",
        "parent_id": parent_id,
        "student_id": student_id,
        "student_email": student_email,
        "relationship": "child",
        "binding_status": "confirmed",
        "created_at": now,
        "_sandbox": True,
    }

    # Child → parent binding
    child_parent_item = {
        "PK": f"USER#{student_id}",
        "SK": f"PARENT#{parent_id}",
        "student_id": student_id,
        "parent_id": parent_id,
        "binding_status": "confirmed",
        "created_at": now,
        "_sandbox": True,
    }

    if dry_run:
        log(f"  [DRY-RUN] Would write parent→child binding: {parent_id[:8]}→{student_id[:8]}")
        return

    table.put_item(Item=parent_child_item)
    table.put_item(Item=child_parent_item)
    log(f"  Wrote bidirectional binding: parent={parent_id[:8]}... ↔ student={student_id[:8]}...")


def dynamo_delete_user(
    dynamo_client: Any,
    table_name: str,
    user_id: str,
    *,
    dry_run: bool,
) -> None:
    if dry_run:
        log(f"  [DRY-RUN] Would delete DynamoDB items for user: {user_id[:8]}...")
        return

    resp = dynamo_client.query(
        TableName=table_name,
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": {"S": f"USER#{user_id}"}},
        ProjectionExpression="PK, SK",
    )
    for item in resp.get("Items", []):
        dynamo_client.delete_item(
            TableName=table_name,
            Key={"PK": item["PK"], "SK": item["SK"]},
        )
    log(f"  Deleted {len(resp.get('Items', []))} DynamoDB items for user: {user_id[:8]}...")


# ── Main provision/teardown ───────────────────────────────────────────────────

def provision(args: argparse.Namespace) -> dict[str, Any]:
    password = require_password()
    cognito_client = boto3.client("cognito-idp", region_name=args.region)
    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    table = dynamodb.Table(args.table_name)

    log(f"Provisioning sandbox accounts in pool={args.user_pool_id}, table={args.table_name}")
    log(f"dry_run={args.dry_run}")

    result: dict[str, Any] = {
        "sandbox_user_pool_id": args.user_pool_id,
        "sandbox_table": args.table_name,
        "parent": {},
        "students": [],
        "admin": {},
        "password_hint": "(see SANDBOX_TEST_PASSWORD env var)",
    }

    # ── Admin account ─────────────────────────────────────────────────────────
    log("\n[1/3] Admin account")
    admin_sub = cognito_create_or_reset(
        cognito_client, args.user_pool_id, ADMIN_EMAIL, "admin", password, dry_run=args.dry_run
    )
    dynamo_put_profile(
        table, admin_sub, ADMIN_EMAIL, "admin", ADMIN_DISPLAY_NAME, dry_run=args.dry_run
    )
    result["admin"] = {"email": ADMIN_EMAIL, "sub": admin_sub, "role": "admin"}

    # ── Student accounts ──────────────────────────────────────────────────────
    log("\n[2/3] Student accounts")
    student_subs: list[str] = []
    for email, display_name in zip(STUDENT_EMAILS, STUDENT_DISPLAY_NAMES):
        sub = cognito_create_or_reset(
            cognito_client, args.user_pool_id, email, "student", password, dry_run=args.dry_run
        )
        dynamo_put_profile(
            table, sub, email, "student", display_name,
            extra={"grade": "8", "school_system": "Lehrplan 21", "language": "de"},
            dry_run=args.dry_run,
        )
        student_subs.append(sub)
        result["students"].append({"email": email, "sub": sub, "role": "student"})

    # ── Parent account + bindings ─────────────────────────────────────────────
    log("\n[3/3] Parent account and bindings")
    parent_sub = cognito_create_or_reset(
        cognito_client, args.user_pool_id, PARENT_EMAIL, "parent", password, dry_run=args.dry_run
    )
    dynamo_put_profile(
        table, parent_sub, PARENT_EMAIL, "parent", PARENT_DISPLAY_NAME, dry_run=args.dry_run
    )
    result["parent"] = {"email": PARENT_EMAIL, "sub": parent_sub, "role": "parent"}

    for student_sub, student_email in zip(student_subs, STUDENT_EMAILS):
        dynamo_put_parent_child_binding(
            table, parent_sub, student_sub, student_email, dry_run=args.dry_run
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    log("\n── Sandbox accounts ready ──────────────────────────────────────────")
    log(f"  Admin:   {ADMIN_EMAIL}")
    log(f"  Parent:  {PARENT_EMAIL}")
    for e in STUDENT_EMAILS:
        log(f"  Student: {e}")
    log("  Password: (from SANDBOX_TEST_PASSWORD env var)")
    log("\nSave this manifest for the Phase 476-28 evidence bundle:")
    print(json.dumps(result, indent=2))
    return result


def teardown(args: argparse.Namespace) -> None:
    log("Tearing down sandbox test accounts...")
    cognito_client = boto3.client("cognito-idp", region_name=args.region)
    dynamo_client = boto3.client("dynamodb", region_name=args.region)

    all_emails = [ADMIN_EMAIL, PARENT_EMAIL] + STUDENT_EMAILS
    for email in all_emails:
        log(f"\nDeleting {email}...")
        try:
            resp = cognito_client.admin_get_user(
                UserPoolId=args.user_pool_id, Username=email
            )
            sub = next(
                a["Value"] for a in resp["UserAttributes"] if a["Name"] == "sub"
            )
            dynamo_delete_user(dynamo_client, args.table_name, sub, dry_run=args.dry_run)
        except ClientError as e:
            if e.response["Error"]["Code"] == "UserNotFoundException":
                log(f"  Not found in Cognito, skipping DynamoDB cleanup: {email}")
            else:
                raise
        cognito_delete(cognito_client, args.user_pool_id, email, dry_run=args.dry_run)

    log("\nSandbox accounts removed.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provision or teardown Phase 476 sandbox test accounts."
    )
    parser.add_argument(
        "--user-pool-id",
        default=os.environ.get("SANDBOX_COGNITO_USER_POOL_ID", ""),
        help="Sandbox Cognito User Pool ID (or set SANDBOX_COGNITO_USER_POOL_ID).",
    )
    parser.add_argument(
        "--table-name",
        default=os.environ.get("SANDBOX_DYNAMODB_TABLE", DEFAULT_TABLE),
        help="Sandbox DynamoDB table name (default: stoa-sandbox).",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without modifying AWS resources.",
    )
    parser.add_argument(
        "--teardown",
        action="store_true",
        help="Delete sandbox test accounts instead of creating them.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.user_pool_id:
        sys.exit(
            "ERROR: Provide --user-pool-id or set SANDBOX_COGNITO_USER_POOL_ID.\n"
            "Find it after deploying: aws cloudformation describe-stacks "
            "--stack-name StoaSandboxAuthStack --query "
            "'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' --output text"
        )

    if args.teardown:
        teardown(args)
    else:
        provision(args)


if __name__ == "__main__":
    main()
