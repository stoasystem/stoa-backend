"""Durable, immutable commands for public student and parent identity convergence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


PUBLIC_REGISTRATION_COMMAND = "public_self_service"
PUBLIC_ROLES = frozenset({"student", "parent"})


class PublicIdentityCommandConflict(RuntimeError):
    """A retry attempted to change an immutable public identity command."""


def normalized_email_digest(email: str) -> str:
    normalized = str(email).strip().casefold()
    if not normalized or "@" not in normalized:
        raise ValueError("email is required")
    return sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PublicIdentityCommandState:
    email_digest: str
    email: str
    issuer: str
    subject: str
    user_id: str
    role: str
    registration_command: str
    fingerprint: str
    provider_signup_complete: bool = True
    pending_profile_complete: bool = False
    binding_complete: bool = False
    canonical_group_complete: bool = False
    email_verification_complete: bool = False
    activation_complete: bool = False
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> "PublicIdentityCommandState":
        fields = {field: item.get(field) for field in cls.__dataclass_fields__}
        for flag in (
            "provider_signup_complete",
            "pending_profile_complete",
            "binding_complete",
            "canonical_group_complete",
            "email_verification_complete",
            "activation_complete",
        ):
            fields[flag] = bool(fields[flag])
        fields["version"] = int(fields["version"] or 0)
        return cls(**fields)

    def as_item(self) -> dict[str, Any]:
        return {
            "PK": f"PUBLIC_IDENTITY#{self.email_digest}",
            "SK": "COMMAND",
            "entity_type": "public_identity_command",
            **asdict(self),
        }


def _fingerprint(*, issuer: str, subject: str, user_id: str, role: str, command: str) -> str:
    payload = "\x1f".join((issuer, subject, user_id, role, command))
    return sha256(payload.encode("utf-8")).hexdigest()


def create_or_get_public_identity_command(
    *,
    email: str,
    issuer: str,
    subject: str,
    user_id: str,
    role: str,
    registration_command: str = PUBLIC_REGISTRATION_COMMAND,
    created_at: str,
) -> PublicIdentityCommandState:
    normalized_email = str(email).strip().casefold()
    normalized_issuer = str(issuer).strip().rstrip("/")
    normalized_subject = str(subject).strip()
    normalized_user_id = str(user_id).strip()
    normalized_role = str(role).strip()
    normalized_command = str(registration_command).strip()
    if normalized_role not in PUBLIC_ROLES or normalized_command != PUBLIC_REGISTRATION_COMMAND:
        raise PublicIdentityCommandConflict("public identity role or command is not allowed")
    if not all((normalized_issuer, normalized_subject, normalized_user_id)):
        raise ValueError("issuer, subject, and user_id are required")
    digest = normalized_email_digest(normalized_email)
    fingerprint = _fingerprint(
        issuer=normalized_issuer,
        subject=normalized_subject,
        user_id=normalized_user_id,
        role=normalized_role,
        command=normalized_command,
    )
    command = PublicIdentityCommandState(
        email_digest=digest,
        email=normalized_email,
        issuer=normalized_issuer,
        subject=normalized_subject,
        user_id=normalized_user_id,
        role=normalized_role,
        registration_command=normalized_command,
        fingerprint=fingerprint,
        created_at=created_at,
        updated_at=created_at,
    )
    table = get_table()
    if hasattr(getattr(table, "meta", None), "client"):
        try:
            fence = account_deletion_repo.require_active_account_fence(
                normalized_user_id, table=table
            )
            account_deletion_repo.transact(
                [
                    account_deletion_repo.active_fence_condition(
                        normalized_user_id, int(fence["generation"])
                    ),
                    {
                        "Put": {
                            "Item": command.as_item(),
                            "ConditionExpression": (
                                "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                            ),
                        }
                    },
                ],
                table=table,
            )
            return command
        except account_deletion_repo.AccountDeletionConflict as exc:
            existing = get_public_identity_command(email)
            if existing and existing.fingerprint == fingerprint:
                return existing
            raise PublicIdentityCommandConflict(
                "public identity command conflicts"
            ) from exc
    try:
        table.put_item(
            Item=command.as_item(),
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        return command
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        existing = get_public_identity_command(email)
        if existing and existing.fingerprint == fingerprint:
            return existing
        raise PublicIdentityCommandConflict("public identity command conflicts") from exc


def get_public_identity_command(email: str) -> PublicIdentityCommandState | None:
    digest = normalized_email_digest(email)
    response = get_table().get_item(
        Key={"PK": f"PUBLIC_IDENTITY#{digest}", "SK": "COMMAND"},
        ConsistentRead=True,
    )
    item = response.get("Item")
    return PublicIdentityCommandState.from_item(dict(item)) if item else None


def require_command_fence(command: PublicIdentityCommandState) -> int:
    table = get_table()
    if not hasattr(getattr(table, "meta", None), "client"):
        return 1
    fence = account_deletion_repo.require_active_account_fence(
        command.user_id, table=table
    )
    return int(fence["generation"])


def advance_public_identity_command(
    email: str,
    *,
    expected_version: int,
    updated_at: str,
    pending_profile_complete: bool | None = None,
    binding_complete: bool | None = None,
    canonical_group_complete: bool | None = None,
    email_verification_complete: bool | None = None,
    activation_complete: bool | None = None,
) -> PublicIdentityCommandState:
    updates = {
        key: value
        for key, value in {
            "pending_profile_complete": pending_profile_complete,
            "binding_complete": binding_complete,
            "canonical_group_complete": canonical_group_complete,
            "email_verification_complete": email_verification_complete,
            "activation_complete": activation_complete,
        }.items()
        if value is not None
    }
    if not updates or any(value is not True for value in updates.values()):
        raise ValueError("command transitions may only mark convergence steps complete")
    names = {"#version": "version", "#updated_at": "updated_at"}
    values: dict[str, Any] = {
        ":expected_version": expected_version,
        ":next_version": expected_version + 1,
        ":updated_at": updated_at,
        ":false": False,
        ":true": True,
    }
    assignments = ["#version = :next_version", "#updated_at = :updated_at"]
    conditions = ["#version = :expected_version"]
    for index, field in enumerate(updates):
        name = f"#step{index}"
        names[name] = field
        assignments.append(f"{name} = :true")
        conditions.append(f"(attribute_not_exists({name}) OR {name} = :false)")
    try:
        response = get_table().update_item(
            Key={
                "PK": f"PUBLIC_IDENTITY#{normalized_email_digest(email)}",
                "SK": "COMMAND",
            },
            UpdateExpression="SET " + ", ".join(assignments),
            ConditionExpression=" AND ".join(conditions),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise PublicIdentityCommandConflict("stale public identity command transition") from exc
        raise
    return PublicIdentityCommandState.from_item(dict(response.get("Attributes") or {}))
