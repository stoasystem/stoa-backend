#!/usr/bin/env python3
"""Return the platform to a known set of accounts.

Everything a person owns is removed - identities, conversations, attempts,
uploads, reports, usage and the analytics derived from them - and five
accounts are created in their place: an administrator, one of each role to
demonstrate with, and one for the agent's own tests. The curriculum and the
security audit trail are not touched.

This deletes real accounts and their work irreversibly. It reports what it
would do and changes nothing until asked twice.

Usage:
    python scripts/reset_accounts.py                      # report only
    python scripts/reset_accounts.py --apply --yes-delete-every-account
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

REGION = os.environ.get("AWS_REGION", "eu-central-2")
TABLE = os.environ.get("DYNAMODB_TABLE_NAME", "stoa-main")
USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "eu-central-2_Ss93YQzjJ")
COGNITO_ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
PASSWORD = os.environ.get("STOA_RESET_PASSWORD", "StoaTest2026!")

PUBLIC_REGISTRATION_COMMAND = "public_self_service"
DOMAIN = "test.stoaedu.ch"

# The curriculum is content, and the audit trail is evidence; neither belongs
# to any of the people being removed.
# The curriculum rows carry no identifier in the partition key, so these are
# matched exactly as well as by prefix.
KEEP_EXACT = ("PRACTICE", "PRACTICE_CHALLENGE_LOOKUP")
KEEP_PREFIXES = ("SECURITY_AUDIT#", "AUDIT_RETENTION#")

# A student profile is read strictly: a missing grade is refused rather than
# defaulted, and the reader reports it as an authorization failure.
STUDENT_FIELDS = {
    "grade": "Grade 8",
    "school_system": "Swiss Gymnasium",
    "preferred_locale": "en",
    "language": "en",
    "primary_subjects": ["Mathematics", "Physics"],
    "subjects": ["Mathematics", "Physics"],
}

ACCOUNTS = [
    {"email": f"admin@{DOMAIN}", "role": "admin", "name": "STOA Admin"},
    {"email": f"student@{DOMAIN}", "role": "student", "name": "Demo Student"},
    {"email": f"parent@{DOMAIN}", "role": "parent", "name": "Demo Parent"},
    {"email": f"teacher@{DOMAIN}", "role": "teacher", "name": "Demo Teacher"},
    {"email": f"agent@{DOMAIN}", "role": "student", "name": "Agent Test Student"},
]

ROLE_TO_GROUP = {"parent": "parents", "student": "students", "admin": "admins", "teacher": "teachers"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def issuer_hash(issuer: str) -> str:
    """The digest the resolver actually looks the binding up by.

    A truncated digest writes a key nothing will ever find, so this defers to
    the repository rather than reimplementing it.
    """
    from stoa.db.repositories.identity_repo import issuer_hash as canonical

    return canonical(issuer)


def kept(pk: str) -> bool:
    return pk in KEEP_EXACT or any(pk.startswith(prefix) for prefix in KEEP_PREFIXES)


def scan_rows(table) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    kwargs: dict[str, Any] = {"ProjectionExpression": "PK, SK"}
    while True:
        response = table.scan(**kwargs)
        rows.extend(response.get("Items", []))
        cursor = response.get("LastEvaluatedKey")
        if not cursor:
            return rows
        kwargs["ExclusiveStartKey"] = cursor


def list_cognito_users(cognito) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {"UserPoolId": USER_POOL_ID, "Limit": 60}
    while True:
        response = cognito.list_users(**kwargs)
        users.extend(response.get("Users", []))
        token = response.get("PaginationToken")
        if not token:
            return users
        kwargs["PaginationToken"] = token


def attribute(user: dict[str, Any], name: str) -> str:
    for attr in user.get("Attributes", []):
        if attr.get("Name") == name:
            return str(attr.get("Value") or "")
    return ""


def create_cognito_user(cognito, email: str, role: str) -> str:
    try:
        cognito.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:role", "Value": role},
            ],
            MessageAction="SUPPRESS",
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "UsernameExistsException":
            raise
    cognito.admin_set_user_password(
        UserPoolId=USER_POOL_ID, Username=email, Password=PASSWORD, Permanent=True
    )
    created = cognito.admin_get_user(UserPoolId=USER_POOL_ID, Username=email)
    subject = ""
    for attr in created.get("UserAttributes", []):
        if attr.get("Name") == "sub":
            subject = str(attr.get("Value"))
    group = ROLE_TO_GROUP.get(role)
    if group:
        try:
            cognito.admin_add_user_to_group(
                UserPoolId=USER_POOL_ID, Username=email, GroupName=group
            )
        except ClientError:
            pass
    return subject


def write_identity(table, *, user_id: str, email: str, role: str, name: str) -> None:
    """Everything sign-in reads before it will accept this account."""
    now = now_iso()
    digest = issuer_hash(COGNITO_ISSUER)
    binding_pk = f"IDENTITY#{digest}#{user_id}"

    table.put_item(Item={
        "PK": f"USER#{user_id}", "SK": "PROFILE",
        "entity_type": "user_profile",
        "user_id": user_id, "email": email, "role": role, "name": name,
        "subscription_tier": "free_trial",
        "account_status": "active",
        "account_activation_status": "active",
        "registration_command": PUBLIC_REGISTRATION_COMMAND,
        "registration_role": role,
        "email_verification_status": "verified",
        "version": 1, "created_at": now, "updated_at": now,
        **(STUDENT_FIELDS if role == "student" else {}),
    })
    table.put_item(Item={
        "PK": f"USER#{user_id}", "SK": "ACCOUNT_FENCE",
        "entity_type": "account_fence", "schema_version": "account-fence.v1",
        "user_id": user_id, "status": "active", "generation": 1, "version": 1,
        "created_at": now, "updated_at": now,
    })
    table.put_item(Item={
        "PK": binding_pk, "SK": "BINDING",
        "entity_type": "identity_binding",
        "issuer": COGNITO_ISSUER.rstrip("/"), "subject": user_id,
        "user_id": user_id, "status": "active", "version": 1,
        "created_at": now, "created_by": "reset_accounts",
    })
    table.put_item(Item={
        "PK": f"USER#{user_id}", "SK": f"IDENTITY#{digest}#{user_id}",
        "entity_type": "user_identity_inventory",
        "issuer": COGNITO_ISSUER.rstrip("/"), "subject": user_id,
        "user_id": user_id, "binding_pk": binding_pk, "created_at": now,
    })


def bind_parent_and_child(table, parent_id: str, student_id: str, student_email: str) -> None:
    now = now_iso()
    table.put_item(Item={
        "PK": f"USER#{parent_id}", "SK": f"CHILD#{student_id}",
        "entity_type": "parent_child", "parent_id": parent_id,
        "student_id": student_id, "child_id": student_id,
        "student_email": student_email, "status": "active",
        # Both directions describe the same thing: a child link.
        "relationship": "child", "version": 1, "created_at": now, "updated_at": now,
    })
    table.put_item(Item={
        "PK": f"USER#{student_id}", "SK": f"PARENT#{parent_id}",
        "entity_type": "child_parent", "parent_id": parent_id,
        "student_id": student_id, "status": "active",
        "relationship": "child", "version": 1, "created_at": now, "updated_at": now,
    })
    # The bindings alone are not the link; readers look for these on the
    # student's own profile.
    table.update_item(
        Key={"PK": f"USER#{student_id}", "SK": "PROFILE"},
        UpdateExpression=(
            "SET parent_id = :parent, relationship = :rel, "
            "parent_binding_status = :status, parent_email = :email"
        ),
        ExpressionAttributeValues={
            ":parent": parent_id,
            ":rel": "child",
            ":status": "active",
            ":email": f"parent@{DOMAIN}",
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes-delete-every-account", action="store_true")
    args = parser.parse_args()

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE)
    cognito = boto3.client("cognito-idp", region_name=REGION)

    rows = scan_rows(table)
    doomed = [row for row in rows if not kept(str(row["PK"]))]
    users = list_cognito_users(cognito)

    print(f"table {TABLE}: {len(rows)} rows, {len(doomed)} to delete, {len(rows) - len(doomed)} kept")
    print(f"cognito {USER_POOL_ID}: {len(users)} users to delete")
    print("\nwill create:")
    for account in ACCOUNTS:
        print(f"  {account['email']:34} {account['role']}")

    if not (args.apply and args.yes_delete_every_account):
        print("\nreport only; pass --apply --yes-delete-every-account to do it")
        return 0

    print("\ndeleting cognito users")
    for user in users:
        cognito.admin_delete_user(UserPoolId=USER_POOL_ID, Username=user["Username"])
    print(f"  deleted {len(users)}")

    print("deleting owned rows")
    with table.batch_writer() as batch:
        for row in doomed:
            batch.delete_item(Key={"PK": row["PK"], "SK": row["SK"]})
    print(f"  deleted {len(doomed)}")

    print("creating accounts")
    created: dict[str, str] = {}
    for account in ACCOUNTS:
        subject = create_cognito_user(cognito, account["email"], account["role"])
        write_identity(
            table,
            user_id=subject,
            email=account["email"],
            role=account["role"],
            name=account["name"],
        )
        created[account["email"]] = subject
        print(f"  {account['email']:34} {account['role']:9} {subject[:8]}")

    bind_parent_and_child(
        table,
        created[f"parent@{DOMAIN}"],
        created[f"student@{DOMAIN}"],
        f"student@{DOMAIN}",
    )
    print(f"  linked parent@{DOMAIN} to student@{DOMAIN}")

    print("\ndone. Run enable_teacher_support_testing.py to open the human-teacher path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
