#!/usr/bin/env python3
"""Bootstrap or disaster-recovery a bounded production administrator.

Routine administrator lifecycle belongs to the authenticated application API.
This script is intentionally isolated from request-path authority.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
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
    parser.add_argument(
        "--purpose",
        required=True,
        choices=("first_admin", "disaster_recovery"),
        help="Restricted bootstrap purpose; routine administration is not allowed.",
    )
    parser.add_argument(
        "--incident-reason",
        required=True,
        help="Internal bootstrap incident/change reason recorded in redacted evidence.",
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
        raise ProvisioningError("Existing Cognito identity has a conflicting role.")
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
        "account_status": "active",
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
    status, _item = ensure_dynamodb_profile_record(
        table,
        email=email,
        name=name,
        update_existing_profile=update_existing_profile,
        dry_run=dry_run,
    )
    return status


def ensure_dynamodb_profile_record(
    table: Any,
    *,
    email: str,
    name: str,
    update_existing_profile: bool,
    dry_run: bool,
) -> tuple[str, dict[str, Any]]:
    existing = get_profile_by_email(table, email)
    if existing and existing.get("role") != ADMIN_ROLE:
        raise ProvisioningError("Existing local identity has a conflicting role.")
    if existing and not update_existing_profile and existing.get("account_status") == "active":
        return "existing", existing

    item = build_admin_profile(email=email, name=name, existing=existing)
    if dry_run:
        return ("would_create" if not existing else "would_update"), item
    if existing:
        table.put_item(Item=item)
    else:
        _put_idempotent(table, item)
    return ("created" if not existing else "updated"), item


def ensure_identity_binding_and_evidence(
    table: Any,
    *,
    user_id: str,
    issuer: str,
    subject: str,
    purpose: str,
    incident_reason: str,
    dry_run: bool,
) -> str:
    """Persist explicit identity binding plus safe bootstrap evidence."""
    if dry_run:
        return "would_reconcile"
    timestamp = now_iso()
    issuer_digest = sha256(issuer.strip().rstrip("/").encode()).hexdigest()
    binding = {
        "PK": f"IDENTITY#{issuer_digest}#{subject}",
        "SK": "BINDING",
        "entity_type": "identity_binding",
        "issuer": issuer.strip().rstrip("/"),
        "subject": subject,
        "user_id": user_id,
        "status": "active",
        "version": 1,
        "created_at": timestamp,
        "created_by": f"bootstrap:{purpose}",
    }
    inventory = {
        "PK": f"USER#{user_id}",
        "SK": f"IDENTITY#{issuer_digest}#{subject}",
        "entity_type": "user_identity_inventory",
        "issuer": binding["issuer"],
        "subject": subject,
        "user_id": user_id,
        "binding_pk": binding["PK"],
        "created_at": timestamp,
    }
    evidence_id = sha256(f"{purpose}:{incident_reason}:{user_id}".encode()).hexdigest()
    evidence = {
        "PK": f"SECURITY_AUDIT#{user_id}",
        "SK": f"EVENT#bootstrap_{evidence_id[:24]}",
        "entity_type": "security_audit_event",
        "event_id": f"bootstrap_{evidence_id[:24]}",
        "event_type": "bootstrap_admin_reconciled",
        "actor_id": f"bootstrap:{purpose}",
        "actor_role": "admin",
        "target_id": user_id,
        "target_type": "admin_identity",
        "result_code": "active",
        "version": 1,
        "reason_code": purpose,
        "evidence_reference": f"bootstrap-evidence:{evidence_id[:24]}",
        "created_at": timestamp,
    }
    for item in (binding, inventory, evidence):
        _put_idempotent(table, item)
    return "reconciled"


def _put_idempotent(table: Any, item: dict[str, Any]) -> None:
    existing = table.get_item(Key={"PK": item["PK"], "SK": item["SK"]}).get("Item")
    if existing:
        stable_keys = {key for key in item if key not in {"created_at", "updated_at"}}
        if all(existing.get(key) == item.get(key) for key in stable_keys):
            return
        raise ProvisioningError("Existing bootstrap record conflicts with requested identity.")
    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if _client_error_code(exc) == "ConditionalCheckFailedException":
            raise ProvisioningError("Concurrent bootstrap record conflict.") from exc
        raise


def validate_inputs(args: argparse.Namespace) -> str:
    if not args.confirm_production:
        raise ProvisioningError("Refusing to run without --confirm-production.")
    if getattr(args, "purpose", None) not in {"first_admin", "disaster_recovery"}:
        raise ProvisioningError("A bootstrap --purpose is required.")
    if not str(getattr(args, "incident_reason", "") or "").strip():
        raise ProvisioningError("A non-empty --incident-reason is required.")
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
        profile_status, profile = ensure_dynamodb_profile_record(
            table,
            email=args.email,
            name=args.name,
            update_existing_profile=args.update_existing_profile,
            dry_run=args.dry_run,
        )
        user = get_cognito_user(cognito, user_pool_id=args.user_pool_id, email=args.email)
        user_id = str((profile or {}).get("user_id") or "dry-run-user")
        attributes = {
            item.get("Name"): item.get("Value") for item in (user or {}).get("UserAttributes", [])
        }
        subject = str(attributes.get("sub") or (user or {}).get("Username") or "dry-run-subject")
        issuer = f"https://cognito-idp.{args.region}.amazonaws.com/{args.user_pool_id}"
        binding_status = ensure_identity_binding_and_evidence(
            table,
            user_id=user_id,
            issuer=issuer,
            subject=subject,
            purpose=args.purpose,
            incident_reason=args.incident_reason,
            dry_run=args.dry_run,
        )
    except ClientError:
        print("ERROR: provider operation failed safely.", file=sys.stderr)
        return 1
    except ProvisioningError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Production admin provisioning complete.")
    print(f"cognito_user={cognito_status}")
    print(f"cognito_group={group_status}")
    print(f"dynamodb_profile={profile_status}")
    print(f"identity_binding={binding_status}")
    print(f"purpose={args.purpose}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
