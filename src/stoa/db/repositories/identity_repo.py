"""Authoritative external-identity bindings and current local authority reads."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from hashlib import sha256

from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


class IdentityBindingConflict(RuntimeError):
    """The external identity is already bound to a different local user."""


type IdentityItem = dict[str, object]


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
) -> IdentityItem:
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
    if hasattr(getattr(table, "meta", None), "client"):
        fence = account_deletion_repo.require_active_account_fence(
            normalized_user_id, table=table
        )
        inventory = {
            "PK": f"USER#{normalized_user_id}",
            "SK": f"IDENTITY#{issuer_hash(normalized_issuer)}#{normalized_subject}",
            "entity_type": "user_identity_inventory",
            "issuer": normalized_issuer,
            "subject": normalized_subject,
            "user_id": normalized_user_id,
            "binding_pk": binding["PK"],
            "created_at": created_at,
        }
        try:
            account_deletion_repo.transact(
                [
                    account_deletion_repo.active_fence_condition(
                        normalized_user_id, int(fence["generation"])
                    ),
                    {
                        "Put": {
                            "Item": binding,
                            "ConditionExpression": (
                                "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                            ),
                        }
                    },
                    {
                        "Put": {
                            "Item": inventory,
                            "ConditionExpression": (
                                "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                            ),
                        }
                    },
                ],
                table=table,
            )
            return binding
        except account_deletion_repo.AccountDeletionConflict as exc:
            existing = get_identity_binding(normalized_issuer, normalized_subject)
            if existing and existing.get("user_id") == normalized_user_id:
                return existing
            raise IdentityBindingConflict("external identity is already bound") from exc
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
            _create_or_repair_identity_inventory(existing, created_at=created_at)
            return existing
        raise IdentityBindingConflict("external identity is already bound") from exc

    _create_or_repair_identity_inventory(binding, created_at=created_at)
    return binding


def _create_or_repair_identity_inventory(
    binding: Mapping[str, object], *, created_at: str
) -> None:
    """Create only the reverse row that exactly describes an authoritative binding."""

    user_id = _required_text(binding, "user_id")
    issuer = _required_text(binding, "issuer")
    subject = _required_text(binding, "subject")
    binding_pk = _required_text(binding, "PK")
    inventory = {
        "PK": f"USER#{user_id}",
        "SK": f"IDENTITY#{issuer_hash(issuer)}#{subject}",
        "entity_type": "user_identity_inventory",
        "issuer": issuer,
        "subject": subject,
        "user_id": user_id,
        "binding_pk": binding_pk,
        "created_at": created_at,
    }
    table = get_table()
    try:
        table.put_item(
            Item=inventory,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        response = table.get_item(
            Key={"PK": inventory["PK"], "SK": inventory["SK"]},
            ConsistentRead=True,
        )
        existing = _optional_item(response.get("Item")) or {}
        immutable = ("issuer", "subject", "user_id", "binding_pk")
        if any(existing.get(field) != inventory[field] for field in immutable):
            raise IdentityBindingConflict("identity inventory conflicts with binding") from exc


def get_identity_binding(issuer: str, subject: str) -> IdentityItem | None:
    response = get_table().get_item(
        Key={
            "PK": f"IDENTITY#{issuer_hash(issuer)}#{subject.strip()}",
            "SK": "BINDING",
        },
        ConsistentRead=True,
    )
    item = response.get("Item")
    return _optional_item(item)


def get_current_capability_grants(user_id: str) -> list[IdentityItem]:
    from stoa.db.repositories import capability_repo

    return capability_repo.get_current_grants(user_id, table_factory=get_table)


class DynamoIdentityRepository:
    """Async request adapter around the existing synchronous DynamoDB wrapper."""

    async def get_binding(self, issuer: str, subject: str) -> IdentityItem | None:
        return await asyncio.to_thread(get_identity_binding, issuer, subject)

    async def get_account_fence(self, user_id: str) -> IdentityItem | None:
        return await asyncio.to_thread(_get_account_fence, user_id)

    async def get_account(self, user_id: str) -> IdentityItem | None:
        return await asyncio.to_thread(_get_account, user_id)

    async def get_current_grants(self, user_id: str) -> list[IdentityItem]:
        return await asyncio.to_thread(get_current_capability_grants, user_id)


def _get_account_fence(user_id: str) -> IdentityItem | None:
    return _optional_item(account_deletion_repo.get_account_fence(user_id))


def _get_account(user_id: str) -> IdentityItem | None:
    from stoa.db.repositories import user_repo

    return _optional_item(user_repo.get_user(user_id))


def _required_text(item: Mapping[str, object], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError("malformed identity binding")
    return value


def _optional_item(value: object) -> IdentityItem | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("malformed identity repository response")
    item: IdentityItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise ValueError("malformed identity repository response")
        item[key] = member
    return item
