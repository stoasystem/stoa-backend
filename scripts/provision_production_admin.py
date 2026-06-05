#!/usr/bin/env python3
"""Provision a real production admin account in Cognito and DynamoDB.

This script is for long-lived operator/admin accounts only. Do not use it to
create temporary smoke-test users.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import sys
import uuid
from typing import Any

import boto3
from botocore.exceptions import ClientError


ADMIN_GROUP = "admins"
ADMIN_ROLE = "admin"


class ProvisioningError(RuntimeError):
    """Raised when the account cannot be provisioned safely."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create or verify a long-lived production admin user in Cognito, "
            "add it to the admins group, and ensure a DynamoDB admin profile exists."
        )
    )
    parser.add_argument("--email", required=True, help="Admin email address / Cognito username.")
    parser.add_argument("--name", default="", help="Display name for the DynamoDB profile.")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "eu-central-2"))
    parser.add_argument(
        "--user-pool-id",
        default=os.environ.get("COGNITO_USER_POOL_ID", "eu-central-2_Ss93YQzjJ"),
    )
    parser.add_argument(
        "--table-name",
        default=os.environ.get("DYNAMODB_TABLE_NAME", "stoa-main"),
    )
    parser.add_argument(
        "--password-env",
        default="STOA_PRODUCTION_ADMIN_PASSWORD",
        help="Environment variable containing the initial permanent password.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the actions that would be taken without changing AWS resources.",
    )
    parser.add_argument(
        "--update-existing-profile",
        action="store_true",
        help="Update name/language metadata when an admin DynamoDB profile already exists.",
    )
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="Required guard acknowledging this changes production auth state.",
    )
    return parser.parse_args()


def _client_error_code(exc: ClientError) -> str:
    return exc.response.get("Error", {}).get("Code", "")


def get_cognito_user(cognito: Any, *, user_pool_id: str, email: str) -> dict[str, Any] | None:
    try:
        return cognito.admin_get_user(UserPoolId=user_pool_id, Username=email)
    except ClientError as exc:
        if _client_error_code(exc) == "UserNotFoundException":
            return None
        raise


def create_or_update_cognito_user(
    cognito: Any,
    *,
    user_pool_id: str,
    email: str,
    password: str,
    dry_run: bool,
) -> str:
    user = get_cognito_user(cognito, user_pool_id=user_pool_id, email=email)
    if user is None:
        if dry_run:
            return "would_create"
        cognito.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            TemporaryPassword=password,
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:role", "Value": ADMIN_ROLE},
                {"Name": "custom:subscription_tier", "Value": "free"},
            ],
        )
        cognito.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=password,
            Permanent=True,
        )
        return "created"

    attrs = {item["Name"]: item["Value"] for item in user.get("UserAttributes", [])}
    role = attrs.get("custom:role")
    if role and role != ADMIN_ROLE:
        raise ProvisioningError(
            f"Cognito user {email!r} exists with custom:role={role!r}, not {ADMIN_ROLE!r}."
        )
    if not dry_run:
        cognito.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=password,
            Permanent=True,
        )
    return "existing_password_set"


def add_user_to_admin_group(
    cognito: Any,
    *,
    user_pool_id: str,
    email: str,
    dry_run: bool,
) -> str:
    if dry_run:
        return "would_add"
    cognito.admin_add_user_to_group(
        UserPoolId=user_pool_id,
        Username=email,
        GroupName=ADMIN_GROUP,
    )
    return "ensured"


def get_profile_by_email(table: Any, email: str) -> dict[str, Any] | None:
    response = table.query(
        IndexName="GSI-Email",
        KeyConditionExpression="email = :email",
        ExpressionAttributeValues={":email": email},
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None


def build_admin_profile(
    *,
    email: str,
    name: str,
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    timestamp = now_iso()
    user_id = str(existing.get("user_id") if existing else uuid.uuid4())
    created_at = str(existing.get("created_at") if existing else timestamp)
    return {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "email": email,
        "name": name or (existing or {}).get("name") or email.split("@")[0],
        "role": ADMIN_ROLE,
        "language": (existing or {}).get("language") or "de",
        "subscription_tier": (existing or {}).get("subscription_tier") or "free",
        "created_at": created_at,
        "updated_at": timestamp,
    }


def ensure_dynamodb_profile(
    table: Any,
    *,
    email: str,
    name: str,
    update_existing_profile: bool,
    dry_run: bool,
) -> str:
    existing = get_profile_by_email(table, email)
    if existing and existing.get("role") != ADMIN_ROLE:
        raise ProvisioningError(
            f"DynamoDB profile for {email!r} exists with role={existing.get('role')!r}."
        )
    if existing and not update_existing_profile:
        return "existing"

    item = build_admin_profile(email=email, name=name, existing=existing)
    if dry_run:
        return "would_create" if not existing else "would_update"
    table.put_item(Item=item)
    return "created" if not existing else "updated"


def validate_inputs(args: argparse.Namespace) -> str:
    if not args.confirm_production:
        raise ProvisioningError("Refusing to run without --confirm-production.")
    password = os.environ.get(args.password_env, "")
    if not password:
        raise ProvisioningError(f"Missing password environment variable: {args.password_env}")
    if len(password) < 8:
        raise ProvisioningError("Password must be at least 8 characters.")
    if not any(char.islower() for char in password):
        raise ProvisioningError("Password must contain a lowercase letter.")
    if not any(char.isupper() for char in password):
        raise ProvisioningError("Password must contain an uppercase letter.")
    if not any(char.isdigit() for char in password):
        raise ProvisioningError("Password must contain a digit.")
    return password


def main() -> int:
    args = parse_args()
    try:
        password = validate_inputs(args)
        cognito = boto3.client("cognito-idp", region_name=args.region)
        dynamodb = boto3.resource("dynamodb", region_name=args.region)
        table = dynamodb.Table(args.table_name)

        cognito_status = create_or_update_cognito_user(
            cognito,
            user_pool_id=args.user_pool_id,
            email=args.email,
            password=password,
            dry_run=args.dry_run,
        )
        group_status = add_user_to_admin_group(
            cognito,
            user_pool_id=args.user_pool_id,
            email=args.email,
            dry_run=args.dry_run,
        )
        profile_status = ensure_dynamodb_profile(
            table,
            email=args.email,
            name=args.name,
            update_existing_profile=args.update_existing_profile,
            dry_run=args.dry_run,
        )
    except (ClientError, ProvisioningError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Production admin provisioning complete.")
    print(f"email={args.email}")
    print(f"cognito_user={cognito_status}")
    print(f"cognito_group={group_status}")
    print(f"dynamodb_profile={profile_status}")
    print("password=redacted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
