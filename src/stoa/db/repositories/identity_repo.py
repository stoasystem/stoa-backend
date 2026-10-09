"""Authoritative external-identity bindings and current local authority reads."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from hashlib import sha256
from typing import Protocol, runtime_checkable

from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


class IdentityBindingConflict(RuntimeError):
    """The external identity is already bound to a different local user."""


type IdentityItem = dict[str, object]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _DeleteTable(Protocol):
    def delete_item(self, **kwargs: object) -> object: ...


def _response_mapping(value: object) -> IdentityItem:
    if not isinstance(value, Mapping):
        raise ValueError("malformed identity repository response")
    response: IdentityItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise ValueError("malformed identity repository response")
        response[key] = member
    return response


def _get_item(table: object, **kwargs: object) -> IdentityItem:
    if not isinstance(table, _GetTable):
        raise ValueError("identity repository dependency is unavailable")
    return _response_mapping(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise ValueError("identity repository dependency is unavailable")
    return table.put_item(**kwargs)


def _update_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _UpdateTable):
        raise ValueError("identity repository dependency is unavailable")
    return table.update_item(**kwargs)


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
        _put_item(
            table,
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
        _put_item(
            table,
            Item=inventory,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        response = _get_item(
            table,
            Key={"PK": inventory["PK"], "SK": inventory["SK"]},
            ConsistentRead=True,
        )
        existing = _optional_item(response.get("Item")) or {}
        immutable = ("issuer", "subject", "user_id", "binding_pk")
        if any(existing.get(field) != inventory[field] for field in immutable):
            raise IdentityBindingConflict("identity inventory conflicts with binding") from exc


def get_identity_binding(issuer: str, subject: str) -> IdentityItem | None:
    response = _get_item(
        get_table(),
        Key={
            "PK": f"IDENTITY#{issuer_hash(issuer)}#{subject.strip()}",
            "SK": "BINDING",
        },
        ConsistentRead=True,
    )
    item = response.get("Item")
    return _optional_item(item)


def record_session_revocation(issuer: str, subject: str, revoked_before: int) -> int:
    """Raise the binding's session cut-off, never lower it.

    An unbound identity is a no-op rather than an error: there is no local
    session to end, and every protected route already refuses such a token.
    """
    cutoff = int(revoked_before)
    if cutoff <= 0:
        raise ValueError("session revocation cut-off must be positive")
    key = {
        "PK": f"IDENTITY#{issuer_hash(issuer)}#{subject.strip()}",
        "SK": "BINDING",
    }
    try:
        _update_item(
            get_table(),
            Key=key,
            UpdateExpression="SET revoked_before = :cutoff",
            ConditionExpression=(
                "attribute_exists(PK) AND ("
                "attribute_not_exists(revoked_before) OR revoked_before < :cutoff)"
            ),
            ExpressionAttributeValues={":cutoff": cutoff},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
    return cutoff


# One sign-in, named by the `origin_jti` Cognito puts on every access token the
# same refresh token mints. Two rows hang off it and they are deliberately in
# different partitions:
#
#   IDENTITY#{issuer}#{subject} / SIGNIN_REVOKED#{origin_jti}
#       the application-side fact that this sign-in is over. Keyed by what the
#       token itself carries, so the authorization path can read it without
#       first resolving a user id, and so it still answers when the binding is
#       gone.
#   USER#{user_id} / SIGNIN#{origin_jti}
#       custody of that sign-in's refresh token, which is the only thing that
#       lets sign-out call the provider's RevokeToken for one sign-in instead of
#       signing every device out.
SIGN_IN_REVOCATION_SK_PREFIX = "SIGNIN_REVOKED#"
SIGN_IN_SESSION_SK_PREFIX = "SIGNIN#"

# How long a revocation record has to outlive the sign-in it ends. Not the access
# token's hour: the refresh token held by whoever was signed out can keep minting
# access tokens carrying the same `origin_jti` for as long as the pool allows,
# and RevokeToken is best effort - the row is what makes the refusal certain. So
# the record has to outlast the refresh token, not the access token, or the TTL
# itself becomes the way back in. This is the pool's 30 days plus a day of slack,
# and it is the number to raise if that setting is raised.
SIGN_IN_REVOCATION_TTL_SECONDS = 31 * 24 * 60 * 60

# The refresh token in custody dies with the provider's copy, so the row may not
# outlive it: a row nobody can act on is only a stored credential.
SIGN_IN_SESSION_TTL_SECONDS = SIGN_IN_REVOCATION_TTL_SECONDS


def _sign_in_identity_key(issuer: str, subject: str, origin_jti: str) -> dict[str, str]:
    normalized = origin_jti.strip()
    if not normalized:
        raise ValueError("origin_jti is required")
    return {
        "PK": f"IDENTITY#{issuer_hash(issuer)}#{subject.strip()}",
        "SK": f"{SIGN_IN_REVOCATION_SK_PREFIX}{normalized}",
    }


def _sign_in_session_key(user_id: str, origin_jti: str) -> dict[str, str]:
    normalized_user = user_id.strip()
    normalized_jti = origin_jti.strip()
    if not normalized_user or not normalized_jti:
        raise ValueError("user_id and origin_jti are required")
    return {
        "PK": f"USER#{normalized_user}",
        "SK": f"{SIGN_IN_SESSION_SK_PREFIX}{normalized_jti}",
    }


def get_sign_in_revocation(
    issuer: str, subject: str, origin_jti: str | None
) -> IdentityItem | None:
    """Read the record that ends exactly one sign-in.

    A token with no `origin_jti` has no sign-in to look up: it predates the pool
    emitting one. It is not refused here - the per-account cut-off is what still
    judges it - so this answers None rather than guessing at a key.
    """
    if not origin_jti or not origin_jti.strip():
        return None
    response = _get_item(
        get_table(),
        Key=_sign_in_identity_key(issuer, subject, origin_jti),
        ConsistentRead=True,
    )
    return _optional_item(response.get("Item"))


def record_sign_in_revocation(
    issuer: str, subject: str, origin_jti: str, expires_at: int
) -> None:
    """Write the sign-in's own end, touching no other sign-in of this account.

    Unconditional on purpose: a second sign-out of the same sign-in has to land
    on the same fact, and there is nothing a later write could say that would be
    weaker than the earlier one.
    """
    ttl = int(expires_at)
    if ttl <= 0:
        raise ValueError("session revocation expiry must be positive")
    _put_item(
        get_table(),
        Item={
            **_sign_in_identity_key(issuer, subject, origin_jti),
            "entity_type": "auth_sign_in_revocation",
            "origin_jti": origin_jti.strip(),
            "expires_at": ttl,
        },
    )


def put_sign_in_refresh_token(
    *, user_id: str, origin_jti: str, refresh_token: str, expires_at: int
) -> None:
    """Take custody of one sign-in's refresh token so sign-out can revoke it.

    It is stored because the alternative was handing it to the browser, and it is
    stored under the sign-in rather than the account so that reading it back can
    never reach another device's token.
    """
    token = refresh_token.strip()
    ttl = int(expires_at)
    if not token:
        raise ValueError("refresh token is required")
    if ttl <= 0:
        raise ValueError("session expiry must be positive")
    _put_item(
        get_table(),
        Item={
            **_sign_in_session_key(user_id, origin_jti),
            "entity_type": "auth_sign_in_session",
            "origin_jti": origin_jti.strip(),
            "refresh_token": token,
            "expires_at": ttl,
        },
    )


def take_sign_in_refresh_token(user_id: str, origin_jti: str) -> str | None:
    """Read the sign-in's refresh token and drop the row in the same breath.

    Dropping it is not tidying: once sign-out has the token in hand the row is a
    stored credential with nothing left to do, and the provider call that follows
    is the last use it will ever have.
    """
    if not user_id or not origin_jti or not origin_jti.strip():
        return None
    key = _sign_in_session_key(user_id, origin_jti)
    table = get_table()
    response = _get_item(table, Key=key, ConsistentRead=True)
    item = _optional_item(response.get("Item"))
    if not item:
        return None
    if not isinstance(table, _DeleteTable):
        raise ValueError("identity repository dependency is unavailable")
    table.delete_item(Key=key)
    token = item.get("refresh_token")
    return token if isinstance(token, str) and token else None


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

    async def record_session_revocation(
        self, issuer: str, subject: str, revoked_before: int
    ) -> int:
        return await asyncio.to_thread(
            record_session_revocation, issuer, subject, revoked_before
        )

    async def get_session_revocation(
        self, issuer: str, subject: str, origin_jti: str | None
    ) -> IdentityItem | None:
        return await asyncio.to_thread(
            get_sign_in_revocation, issuer, subject, origin_jti
        )

    async def record_sign_in_revocation(
        self, issuer: str, subject: str, origin_jti: str, expires_at: int
    ) -> None:
        await asyncio.to_thread(
            record_sign_in_revocation, issuer, subject, origin_jti, expires_at
        )

    async def put_sign_in_refresh_token(
        self, user_id: str, origin_jti: str, refresh_token: str, expires_at: int
    ) -> None:
        await asyncio.to_thread(
            lambda: put_sign_in_refresh_token(
                user_id=user_id,
                origin_jti=origin_jti,
                refresh_token=refresh_token,
                expires_at=expires_at,
            )
        )

    async def take_sign_in_refresh_token(
        self, user_id: str, origin_jti: str
    ) -> str | None:
        return await asyncio.to_thread(
            take_sign_in_refresh_token, user_id, origin_jti
        )


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
