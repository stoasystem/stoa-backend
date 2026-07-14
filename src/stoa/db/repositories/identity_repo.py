"""Authoritative external-identity bindings and current local authority reads."""

from __future__ import annotations

import asyncio
from hashlib import sha256
from typing import Any

from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


class IdentityBindingConflict(RuntimeError):
    """The external identity is already bound to a different local user."""


def issuer_hash(issuer: str) -> str:
    normalized = issuer.strip().rstrip("/")
    if not normalized:
        raise ValueError("issuer is required")
    return sha256(normalized.encode("utf-8")).hexdigest()


def create_identity_binding(
    *,
    issuer: str,
    subject: str,
    user_id: str,
    created_at: str,
    created_by: str,
) -> dict[str, Any]:
    normalized_issuer = issuer.strip().rstrip("/")
    normalized_subject = subject.strip()
    normalized_user_id = user_id.strip()
    if not normalized_subject or not normalized_user_id:
        raise ValueError("subject and user_id are required")
    binding = {
        "PK": f"IDENTITY#{issuer_hash(normalized_issuer)}#{normalized_subject}",
        "SK": "BINDING",
        "entity_type": "identity_binding",
        "issuer": normalized_issuer,
        "subject": normalized_subject,
        "user_id": normalized_user_id,
        "status": "active",
        "version": 1,
        "created_at": created_at,
        "created_by": created_by,
    }
    table = get_table()
    try:
        table.put_item(
            Item=binding,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        existing = get_identity_binding(normalized_issuer, normalized_subject)
        if existing and existing.get("user_id") == normalized_user_id:
            return existing
        raise IdentityBindingConflict("external identity is already bound") from exc

    table.put_item(
        Item={
            "PK": f"USER#{normalized_user_id}",
            "SK": f"IDENTITY#{issuer_hash(normalized_issuer)}#{normalized_subject}",
            "entity_type": "user_identity_inventory",
            "issuer": normalized_issuer,
            "subject": normalized_subject,
            "user_id": normalized_user_id,
            "binding_pk": binding["PK"],
            "created_at": created_at,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )
    return binding


def get_identity_binding(issuer: str, subject: str) -> dict[str, Any] | None:
    response = get_table().get_item(
        Key={
            "PK": f"IDENTITY#{issuer_hash(issuer)}#{subject.strip()}",
            "SK": "BINDING",
        },
        ConsistentRead=True,
    )
    item = response.get("Item")
    return dict(item) if item else None


def get_current_capability_grants(user_id: str) -> list[dict[str, Any]]:
    from stoa.db.repositories import capability_repo

    return capability_repo.get_current_grants(user_id, table_factory=get_table)


class DynamoIdentityRepository:
    """Async request adapter around the existing synchronous DynamoDB wrapper."""

    async def get_binding(self, issuer: str, subject: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(get_identity_binding, issuer, subject)

    async def get_account(self, user_id: str) -> dict[str, Any] | None:
        from stoa.db.repositories import user_repo

        return await asyncio.to_thread(user_repo.get_user, user_id)

    async def get_current_grants(self, user_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(get_current_capability_grants, user_id)
