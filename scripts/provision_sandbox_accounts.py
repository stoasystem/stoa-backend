#!/usr/bin/env python3
"""Provision isolated sandbox test accounts for Phase 476 payment testing.

Creates the following test identities in the stoa-sandbox Cognito User Pool
and stoa-sandbox DynamoDB table, including all identity records required by
the new public_identity_service authentication flow:

  - 1 parent     sandbox.parent@stoaedu.ch
  - 3 students   sandbox.student1..3@stoaedu.ch
  - 1 admin      sandbox.admin@stoaedu.ch

Usage:
    export SANDBOX_TEST_PASSWORD="SandboxTest2026!"
    python scripts/provision_sandbox_accounts.py

    # Dry-run (print actions, change nothing):
    python scripts/provision_sandbox_accounts.py --dry-run

    # Tear down sandbox accounts after testing:
    python scripts/provision_sandbox_accounts.py --teardown
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

import boto3
from botocore.exceptions import ClientError

# ── Sandbox resource identifiers ──────────────────────────────────────────────
DEFAULT_REGION = "eu-central-2"
DEFAULT_USER_POOL_ID = "eu-central-2_FCpWgVayX"
DEFAULT_TABLE = "stoa-sandbox"
SANDBOX_DOMAIN = "stoaedu.ch"
COGNITO_ISSUER = f"https://cognito-idp.{DEFAULT_REGION}.amazonaws.com/{DEFAULT_USER_POOL_ID}"

PUBLIC_REGISTRATION_COMMAND = "public_self_service"

PARENT_EMAIL = f"sandbox.parent@{SANDBOX_DOMAIN}"
ADMIN_EMAIL = f"sandbox.admin@{SANDBOX_DOMAIN}"
STUDENT_EMAILS = [
    f"sandbox.student1@{SANDBOX_DOMAIN}",
    f"sandbox.student2@{SANDBOX_DOMAIN}",
    f"sandbox.student3@{SANDBOX_DOMAIN}",
]

PARENT_DISPLAY_NAME = "Sandbox Parent"
ADMIN_DISPLAY_NAME = "Sandbox Admin"
STUDENT_DISPLAY_NAMES = ["Sandbox Student 1", "Sandbox Student 2", "Sandbox Student 3"]

# Cognito group names → DynamoDB role values (must match identity.py _GROUP_ROLES)
ROLE_TO_GROUP = {"parent": "parents", "student": "students", "admin": "admins"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def log(msg: str) -> None:
    print(f"[sandbox-provision] {msg}", flush=True)


def require_password() -> str:
    pw = os.environ.get("SANDBOX_TEST_PASSWORD", "").strip()
    if not pw:
        sys.exit(
            "ERROR: Set SANDBOX_TEST_PASSWORD env var before running.\n"
            "Example: export SANDBOX_TEST_PASSWORD='SandboxTest2026!'"
        )
    return pw


def issuer_hash(issuer: str) -> str:
    normalized = issuer.strip().rstrip("/")
    return sha256(normalized.encode("utf-8")).hexdigest()


# ── Cognito helpers ───────────────────────────────────────────────────────────

def cognito_ensure_groups(cognito_client: Any, user_pool_id: str, *, dry_run: bool) -> None:
    """Ensure required Cognito groups exist."""
    existing_resp = cognito_client.list_groups(UserPoolId=user_pool_id)
    existing = {g["GroupName"] for g in existing_resp.get("Groups", [])}
    for group_name in ROLE_TO_GROUP.values():
        if group_name not in existing:
            if dry_run:
                log(f"  [DRY-RUN] Would create Cognito group: {group_name}")
            else:
                cognito_client.create_group(UserPoolId=user_pool_id, GroupName=group_name)
                log(f"  Created Cognito group: {group_name}")
        else:
            log(f"  Cognito group already exists: {group_name}")


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
            a["Value"] for a in resp["User"]["Attributes"] if a["Name"] == "sub"
        )
        log(f"  Created Cognito user: {email}  sub={sub[:8]}...")
    except ClientError as e:
        if e.response["Error"]["Code"] != "UsernameExistsException":
            raise
        log(f"  User already exists, resetting: {email}")
        resp = cognito_client.admin_get_user(UserPoolId=user_pool_id, Username=email)
        sub = next(
            a["Value"] for a in resp["UserAttributes"] if a["Name"] == "sub"
        )

    # Ensure permanent password
    cognito_client.admin_set_user_password(
        UserPoolId=user_pool_id, Username=email, Password=password, Permanent=True
    )

    # Add to role group
    group_name = ROLE_TO_GROUP.get(role)
    if group_name:
        try:
            cognito_client.admin_add_user_to_group(
                UserPoolId=user_pool_id, Username=email, GroupName=group_name
            )
            log(f"  Added {email} to Cognito group: {group_name}")
        except ClientError as e:
            if e.response["Error"]["Code"] != "EntityAlreadyExists":
                raise
            log(f"  Already in group {group_name}: {email}")

    return sub


def cognito_delete(
    cognito_client: Any, user_pool_id: str, email: str, *, dry_run: bool
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

def dynamo_put_full_identity(
    table: Any,
    user_id: str,
    email: str,
    role: str,
    name: str,
    issuer: str,
    subject: str,
    extra: dict[str, Any] | None = None,
    *,
    dry_run: bool,
) -> None:
    """Write all required DynamoDB records for a fully authenticated user.

    Creates:
      - PROFILE record with account_status=active and registration fields
      - ACCOUNT_FENCE record (required by resolve_actor)
      - IDENTITY binding record (maps issuer/subject → user_id)
      - USER identity inventory record
    """
    now = now_iso()
    ih = issuer_hash(issuer)

    profile_item: dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "entity_type": "user_profile",
        "user_id": user_id,
        "email": email,
        "role": role,
        "name": name,
        "subscription_tier": "free_trial",
        "account_status": "active",
        "registration_command": PUBLIC_REGISTRATION_COMMAND,
        "registration_role": role,
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "_sandbox": True,
    }
    if extra:
        profile_item.update(extra)

    fence_item: dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": "ACCOUNT_FENCE",
        "entity_type": "account_fence",
        "schema_version": "account-fence.v1",
        "user_id": user_id,
        "status": "active",
        "generation": 1,
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "_sandbox": True,
    }

    binding_pk = f"IDENTITY#{ih}#{subject}"
    binding_item: dict[str, Any] = {
        "PK": binding_pk,
        "SK": "BINDING",
        "entity_type": "identity_binding",
        "issuer": issuer.strip().rstrip("/"),
        "subject": subject,
        "user_id": user_id,
        "status": "active",
        "version": 1,
        "created_at": now,
        "created_by": "sandbox_provisioner",
        "_sandbox": True,
    }

    inventory_item: dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": f"IDENTITY#{ih}#{subject}",
        "entity_type": "user_identity_inventory",
        "issuer": issuer.strip().rstrip("/"),
        "subject": subject,
        "user_id": user_id,
        "binding_pk": binding_pk,
        "created_at": now,
        "_sandbox": True,
    }

    if dry_run:
        log(f"  [DRY-RUN] Would put PROFILE+FENCE+IDENTITY for {email} ({role})")
        return

    # Write all records
    table.put_item(Item=profile_item)
    log(f"  Wrote PROFILE: PK=USER#{user_id[:8]}... role={role} account_status=active")

    table.put_item(Item=fence_item)
    log("  Wrote ACCOUNT_FENCE: generation=1 status=active")

    table.put_item(Item=binding_item)
    log(f"  Wrote IDENTITY BINDING: {binding_pk[:32]}...")

    table.put_item(Item=inventory_item)
    log(f"  Wrote IDENTITY INVENTORY: USER#{user_id[:8]}...→IDENTITY#...")


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

    parent_child_item = {
        "PK": f"USER#{parent_id}",
        "SK": f"CHILD#{student_id}",
        "parent_id": parent_id,
        "student_id": student_id,
        "student_email": student_email,
        "relationship": "child",
        "status": "active",
        "binding_status": "confirmed",
        "created_at": now,
        "_sandbox": True,
    }
    child_parent_item = {
        "PK": f"USER#{student_id}",
        "SK": f"PARENT#{parent_id}",
        "student_id": student_id,
        "parent_id": parent_id,
        "relationship": "child",
        "status": "active",
        "binding_status": "confirmed",
        "created_at": now,
        "_sandbox": True,
    }

    if dry_run:
        log(f"  [DRY-RUN] Would write parent→child: {parent_id[:8]}→{student_id[:8]}")
        return

    table.put_item(Item=parent_child_item)
    table.put_item(Item=child_parent_item)
    log(f"  Wrote binding: parent={parent_id[:8]}... ↔ student={student_id[:8]}...")


def dynamo_delete_user(
    dynamo_client: Any, table_name: str, user_id: str, issuer: str, subject: str, *, dry_run: bool
) -> None:
    if dry_run:
        log(f"  [DRY-RUN] Would delete DynamoDB items for user: {user_id[:8]}...")
        return

    ih = issuer_hash(issuer)
    binding_pk = f"IDENTITY#{ih}#{subject}"

    # Delete the identity binding
    try:
        dynamo_client.delete_item(
            TableName=table_name,
            Key={"PK": {"S": binding_pk}, "SK": {"S": "BINDING"}},
        )
    except ClientError:
        pass

    # Delete all USER# items
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
    count = len(resp.get("Items", []))
    log(f"  Deleted {count} DynamoDB items for user: {user_id[:8]}...")


# ── Main provision/teardown ───────────────────────────────────────────────────

def provision(args: argparse.Namespace) -> dict[str, Any]:
    password = require_password()
    cognito_client = boto3.client("cognito-idp", region_name=args.region)
    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    table = dynamodb.Table(args.table_name)

    issuer = f"https://cognito-idp.{args.region}.amazonaws.com/{args.user_pool_id}"
    log(f"Provisioning sandbox accounts in pool={args.user_pool_id}, table={args.table_name}")
    log(f"Issuer: {issuer}")
    log(f"dry_run={args.dry_run}")

    result: dict[str, Any] = {
        "sandbox_user_pool_id": args.user_pool_id,
        "sandbox_table": args.table_name,
        "cognito_issuer": issuer,
        "parent": {},
        "students": [],
        "admin": {},
        "password_hint": "(see SANDBOX_TEST_PASSWORD env var)",
    }

    # Ensure Cognito groups exist
    log("\n[0/3] Ensuring Cognito groups exist")
    cognito_ensure_groups(cognito_client, args.user_pool_id, dry_run=args.dry_run)

    # ── Admin account ─────────────────────────────────────────────────────────
    log("\n[1/3] Admin account")
    admin_sub = cognito_create_or_reset(
        cognito_client, args.user_pool_id, ADMIN_EMAIL, "admin", password, dry_run=args.dry_run
    )
    dynamo_put_full_identity(
        table, admin_sub, ADMIN_EMAIL, "admin", ADMIN_DISPLAY_NAME,
        issuer=issuer, subject=admin_sub,
        dry_run=args.dry_run,
    )
    result["admin"] = {"email": ADMIN_EMAIL, "sub": admin_sub, "role": "admin"}

    # ── Student accounts ──────────────────────────────────────────────────────
    log("\n[2/3] Student accounts")
    student_subs: list[str] = []
    for email, display_name in zip(STUDENT_EMAILS, STUDENT_DISPLAY_NAMES):
        sub = cognito_create_or_reset(
            cognito_client, args.user_pool_id, email, "student", password, dry_run=args.dry_run
        )
        dynamo_put_full_identity(
            table, sub, email, "student", display_name,
            issuer=issuer, subject=sub,
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
    dynamo_put_full_identity(
        table, parent_sub, PARENT_EMAIL, "parent", PARENT_DISPLAY_NAME,
        issuer=issuer, subject=parent_sub,
        dry_run=args.dry_run,
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
    issuer = f"https://cognito-idp.{args.region}.amazonaws.com/{args.user_pool_id}"

    all_accounts = [
        (ADMIN_EMAIL, "admin"),
        (PARENT_EMAIL, "parent"),
        *[(e, "student") for e in STUDENT_EMAILS],
    ]
    for email, _role in all_accounts:
        log(f"\nDeleting {email}...")
        try:
            resp = cognito_client.admin_get_user(UserPoolId=args.user_pool_id, Username=email)
            sub = next(a["Value"] for a in resp["UserAttributes"] if a["Name"] == "sub")
            dynamo_delete_user(
                dynamo_client, args.table_name, sub, issuer, sub, dry_run=args.dry_run
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "UserNotFoundException":
                log(f"  Not found in Cognito: {email}")
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
        default=os.environ.get("SANDBOX_COGNITO_USER_POOL_ID", DEFAULT_USER_POOL_ID),
        help="Sandbox Cognito User Pool ID.",
    )
    parser.add_argument(
        "--table-name",
        default=os.environ.get("SANDBOX_DYNAMODB_TABLE", DEFAULT_TABLE),
    )
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--teardown", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.teardown:
        teardown(args)
    else:
        provision(args)


if __name__ == "__main__":
    main()
