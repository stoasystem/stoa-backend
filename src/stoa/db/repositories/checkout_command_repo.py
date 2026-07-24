"""Durable command-first persistence for one parent checkout operation."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo
from stoa.models.billing import CheckoutCommandState, CheckoutIntent


type CheckoutItem = dict[str, object]

COMMAND_SCHEMA_VERSION = "checkout_command.v1"
OPEN_GUARD_SCHEMA_VERSION = "checkout_open_guard.v1"
PUBLIC_LOOKUP_SCHEMA_VERSION = "checkout_public_lookup.v1"
PROVIDER_KEY_VERSION = 1

_COMMAND_ID_DOMAIN = b"stoa.checkout.command.v1"
_FINGERPRINT_DOMAIN = "stoa.checkout.intent.v1"
_PROVIDER_KEY_DOMAIN = b"stoa.checkout.provider-key.v1"
_SESSION_ID_DOMAIN = b"stoa.checkout.provider-session.v1"
_PUBLIC_REF_PATTERN = re.compile(r"^co_[A-Za-z0-9_-]{32,100}$")
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[\x21-\x7e]{8,128}$")
_TERMINAL_STATES = frozenset(
    {
        CheckoutCommandState.ACTIVATION_RECORDED,
        CheckoutCommandState.TERMINAL_WITHOUT_PAYMENT,
    }
)
_CLAIMABLE_EFFECT_STATES = frozenset(
    {"not_started", "create_claimed", "provider_outcome_unknown"}
)


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


class CheckoutCommandDisposition(StrEnum):
    """Closed outcomes from checkout command persistence operations."""

    CREATED = "created"
    REPLAYED = "replayed"
    IDENTITY_MISMATCH = "identity_mismatch"
    OPEN_COMMAND_EXISTS = "open_command_exists"
    NOT_FOUND = "not_found"
    MALFORMED = "malformed"
    CLAIMED = "claimed"
    LEASE_BUSY = "lease_busy"
    ATTACHED = "attached"
    ALREADY_ATTACHED = "already_attached"
    PROVIDER_OUTCOME_UNKNOWN = "provider_outcome_unknown"
    STALE_LEASE = "stale_lease"
    STALE_VERSION = "stale_version"
    RELEASED = "released"
    NOT_TERMINAL = "not_terminal"
    RETRYABLE = "retryable_dependency"


class CheckoutSupersessionDisposition(StrEnum):
    """Closed outcomes for one confirmed checkout plan change."""

    EXPIRATION_CLAIMED = "expiration_claimed"
    EXPIRATION_BUSY = "expiration_busy"
    NONPAYABLE_PROVEN = "nonpayable_proven"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    PROVIDER_UNKNOWN = "provider_unknown"
    SUPERSEDED = "superseded"
    IDENTITY_MISMATCH = "identity_mismatch"
    NOT_FOUND = "not_found"
    MALFORMED = "malformed"
    STALE_VERSION = "stale_version"
    RETRYABLE = "retryable_dependency"


@dataclass(frozen=True, slots=True)
class ProviderCreateClaim:
    command_id: str
    parent_id: str
    command_version: int
    lease_owner: str
    lease_generation: int
    lease_expires_at: int
    provider_key_digest: str


@dataclass(frozen=True, slots=True)
class CheckoutCommandResult:
    disposition: CheckoutCommandDisposition
    command: CheckoutItem | None = None
    provider_claim: ProviderCreateClaim | None = None
    operations: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class CheckoutSupersessionResult:
    disposition: CheckoutSupersessionDisposition
    command: CheckoutItem | None = None
    operations: tuple[dict[str, Any], ...] = ()


def _required_text(
    value: object,
    field: str,
    *,
    minimum: int = 1,
    maximum: int = 200,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} is invalid")
    cleaned = value.strip()
    if cleaned != value or not minimum <= len(cleaned) <= maximum:
        raise ValueError(f"{field} is invalid")
    return cleaned


def _positive_integer(value: object, field: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} is invalid")
    return value


def _length_prefixed(parts: tuple[str, ...]) -> bytes:
    encoded = bytearray()
    for part in parts:
        value = part.encode("utf-8")
        encoded.extend(len(value).to_bytes(4, "big"))
        encoded.extend(value)
    return bytes(encoded)


def _domain_digest(domain: bytes, *parts: str) -> str:
    return hashlib.sha256(domain + b"\x00" + _length_prefixed(tuple(parts))).hexdigest()


def checkout_command_id(parent_id: str, idempotency_key: str) -> str:
    """Derive the non-reversible logical command identity."""
    parent = _required_text(parent_id, "parent_id")
    key = _required_text(idempotency_key, "idempotency_key", minimum=8, maximum=128)
    if _IDEMPOTENCY_KEY_PATTERN.fullmatch(key) is None:
        raise ValueError("idempotency_key is invalid")
    return f"checkout-{_domain_digest(_COMMAND_ID_DOMAIN, parent, key)}"


def checkout_intent_fingerprint(
    intent: CheckoutIntent,
    *,
    price_id: str,
    environment: str,
) -> str:
    """Fingerprint the immutable provider parameter identity canonically."""
    if not isinstance(intent, CheckoutIntent):
        raise ValueError("checkout intent is required")
    expected_command_id = checkout_command_id(intent.parent_id, intent.idempotency_key)
    if intent.command_id != expected_command_id:
        raise ValueError("checkout command identity is invalid")
    price = _required_text(price_id, "price_id")
    deployment = _required_text(environment, "environment", maximum=32).lower()
    return _canonical_intent_fingerprint(
        parent_id=intent.parent_id,
        plan_id=str(intent.plan_id),
        beneficiary_ids=intent.beneficiary_ids,
        price_id=price,
        price_catalog_version=intent.price_catalog_version,
        plan_version=intent.plan_version,
        environment=deployment,
    )


def _canonical_intent_fingerprint(
    *,
    parent_id: str,
    plan_id: str,
    beneficiary_ids: Sequence[str],
    price_id: str,
    price_catalog_version: int,
    plan_version: int,
    environment: str,
) -> str:
    beneficiaries = list(beneficiary_ids)
    if (
        not beneficiaries
        or len(beneficiaries) > 3
        or len(set(beneficiaries)) != len(beneficiaries)
        or any(not isinstance(member, str) or not member for member in beneficiaries)
    ):
        raise ValueError("beneficiary_ids are invalid")
    payload = {
        "domain": _FINGERPRINT_DOMAIN,
        "parent_id": _required_text(parent_id, "parent_id"),
        "plan_id": _required_text(plan_id, "plan_id", maximum=32),
        "beneficiary_ids": sorted(beneficiaries),
        "price_id": _required_text(price_id, "price_id"),
        "price_catalog_version": _positive_integer(
            price_catalog_version, "price_catalog_version"
        ),
        "plan_version": _positive_integer(plan_version, "plan_version"),
        "environment": _required_text(
            environment, "environment", maximum=32
        ).lower(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _provider_key_digest(command_id: str, intent_fingerprint: str) -> str:
    return _domain_digest(
        _PROVIDER_KEY_DOMAIN,
        command_id,
        intent_fingerprint,
        str(PROVIDER_KEY_VERSION),
    )


def _provider_session_id_digest(provider_session_id: str) -> str:
    return _domain_digest(_SESSION_ID_DOMAIN, provider_session_id)


def _new_public_ref() -> str:
    return f"co_{secrets.token_urlsafe(32)}"


def _command_key(command_id: str) -> dict[str, str]:
    return {"PK": f"CHECKOUT_COMMAND#{command_id}", "SK": "COMMAND"}


def _open_guard_key(parent_id: str) -> dict[str, str]:
    return {"PK": f"CHECKOUT_OPEN#{parent_id}", "SK": "GUARD"}


def _public_lookup_key(checkout_ref: str) -> dict[str, str]:
    return {"PK": f"CHECKOUT_PUBLIC#{checkout_ref}", "SK": "LOOKUP"}


def _mapping(value: object) -> CheckoutItem | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError("checkout dependency returned malformed data")
    return {str(key): member for key, member in value.items()}


def _strong_get(table: object, key: Mapping[str, str]) -> CheckoutItem | None:
    if not isinstance(table, _GetTable):
        raise ValueError("checkout persistence is unavailable")
    response = table.get_item(Key=dict(key), ConsistentRead=True)
    if not isinstance(response, Mapping):
        raise ValueError("checkout dependency returned malformed data")
    return _mapping(response.get("Item"))


def _strong_command(
    command_id: str,
    *,
    table: object,
) -> CheckoutItem | None:
    return _strong_get(table, _command_key(command_id))


def _command_integrity(
    item: Mapping[str, object],
    *,
    command_id: str,
    parent_id: str | None = None,
    intent_fingerprint: str | None = None,
) -> CheckoutCommandDisposition | None:
    try:
        if (
            item.get("entity_type") != "checkout_command"
            or item.get("schema_version") != COMMAND_SCHEMA_VERSION
            or item.get("command_id") != command_id
            or item.get("PK") != _command_key(command_id)["PK"]
            or item.get("SK") != "COMMAND"
        ):
            return CheckoutCommandDisposition.MALFORMED
        if parent_id is not None and item.get("parent_id") != parent_id:
            return CheckoutCommandDisposition.IDENTITY_MISMATCH
        if (
            intent_fingerprint is not None
            and item.get("intent_fingerprint") != intent_fingerprint
        ):
            return CheckoutCommandDisposition.IDENTITY_MISMATCH
        _positive_integer(item.get("command_version"), "command_version")
        _positive_integer(
            item.get("provider_key_version"), "provider_key_version"
        )
        _positive_integer(
            item.get("lease_generation"), "lease_generation", allow_zero=True
        )
        provider_key = item.get("provider_key_digest")
        fingerprint = item.get("intent_fingerprint")
        checkout_ref = item.get("checkout_ref")
        if (
            item.get("provider_key_version") != PROVIDER_KEY_VERSION
            or not isinstance(provider_key, str)
            or re.fullmatch(r"[0-9a-f]{64}", provider_key) is None
            or not isinstance(fingerprint, str)
            or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None
            or not isinstance(checkout_ref, str)
            or _PUBLIC_REF_PATTERN.fullmatch(checkout_ref) is None
        ):
            return CheckoutCommandDisposition.MALFORMED
        stored_fingerprint = _canonical_intent_fingerprint(
            parent_id=_required_text(item.get("parent_id"), "parent_id"),
            plan_id=_required_text(item.get("plan_id"), "plan_id", maximum=32),
            beneficiary_ids=item.get("beneficiary_ids")
            if isinstance(item.get("beneficiary_ids"), Sequence)
            and not isinstance(item.get("beneficiary_ids"), (str, bytes))
            else (),
            price_id=_required_text(item.get("price_id"), "price_id"),
            price_catalog_version=_positive_integer(
                item.get("price_catalog_version"), "price_catalog_version"
            ),
            plan_version=_positive_integer(
                item.get("plan_version"), "plan_version"
            ),
            environment=_required_text(
                item.get("environment"), "environment", maximum=32
            ),
        )
        if (
            fingerprint != stored_fingerprint
            or provider_key != _provider_key_digest(command_id, fingerprint)
        ):
            return CheckoutCommandDisposition.MALFORMED
        CheckoutCommandState(str(item.get("command_state") or ""))
    except (TypeError, ValueError):
        return CheckoutCommandDisposition.MALFORMED
    return None


def _provider_claim(item: Mapping[str, object]) -> ProviderCreateClaim:
    return ProviderCreateClaim(
        command_id=_required_text(item.get("command_id"), "command_id"),
        parent_id=_required_text(item.get("parent_id"), "parent_id"),
        command_version=_positive_integer(
            item.get("command_version"), "command_version"
        ),
        lease_owner=_required_text(item.get("lease_owner"), "lease_owner"),
        lease_generation=_positive_integer(
            item.get("lease_generation"), "lease_generation"
        ),
        lease_expires_at=_positive_integer(
            item.get("lease_expires_at"), "lease_expires_at"
        ),
        provider_key_digest=_required_text(
            item.get("provider_key_digest"),
            "provider_key_digest",
            minimum=64,
            maximum=64,
        ),
    )


def _validate_public_ref(checkout_ref: str) -> str:
    value = _required_text(checkout_ref, "checkout_ref", minimum=35, maximum=103)
    if _PUBLIC_REF_PATTERN.fullmatch(value) is None:
        raise ValueError("checkout_ref is invalid")
    return value


def _classify_registration_replay(
    *,
    table: object,
    command_id: str,
    parent_id: str,
    intent_fingerprint: str,
    checkout_ref: str | None = None,
) -> CheckoutCommandResult:
    try:
        command = _strong_command(command_id, table=table)
    except Exception:
        return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
    if command is not None:
        integrity = _command_integrity(
            command,
            command_id=command_id,
            parent_id=parent_id,
            intent_fingerprint=intent_fingerprint,
        )
        if integrity is not None:
            return CheckoutCommandResult(integrity)
        try:
            guard = _strong_get(table, _open_guard_key(parent_id))
            lookup = _strong_get(
                table, _public_lookup_key(str(command["checkout_ref"]))
            )
        except Exception:
            return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
        try:
            state = CheckoutCommandState(str(command.get("command_state") or ""))
        except ValueError:
            return CheckoutCommandResult(CheckoutCommandDisposition.MALFORMED)
        guard_valid = (
            guard is not None
            and guard.get("schema_version") == OPEN_GUARD_SCHEMA_VERSION
            and guard.get("command_id") == command_id
            and guard.get("parent_id") == parent_id
        )
        if (
            (state not in _TERMINAL_STATES and not guard_valid)
            or (state in _TERMINAL_STATES and guard is not None and not guard_valid)
            or lookup is None
            or lookup.get("schema_version") != PUBLIC_LOOKUP_SCHEMA_VERSION
            or lookup.get("command_id") != command_id
            or lookup.get("parent_id") != parent_id
            or lookup.get("checkout_ref") != command.get("checkout_ref")
        ):
            return CheckoutCommandResult(CheckoutCommandDisposition.MALFORMED)
        return CheckoutCommandResult(
            CheckoutCommandDisposition.REPLAYED, command=dict(command)
        )
    try:
        guard = _strong_get(table, _open_guard_key(parent_id))
        lookup = (
            _strong_get(table, _public_lookup_key(checkout_ref))
            if checkout_ref is not None
            else None
        )
    except Exception:
        return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
    if guard is not None:
        if (
            guard.get("schema_version") == OPEN_GUARD_SCHEMA_VERSION
            and guard.get("parent_id") == parent_id
            and isinstance(guard.get("command_id"), str)
            and guard.get("command_id") != command_id
        ):
            return CheckoutCommandResult(
                CheckoutCommandDisposition.OPEN_COMMAND_EXISTS
            )
        return CheckoutCommandResult(CheckoutCommandDisposition.MALFORMED)
    if lookup is not None:
        return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
    return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)


def register_checkout_command(
    intent: CheckoutIntent,
    *,
    price_id: str,
    environment: str,
    now_iso: str | None = None,
    table: object | None = None,
) -> CheckoutCommandResult:
    """Create command, one-open guard, and public lookup before provider access."""
    if not isinstance(intent, CheckoutIntent):
        raise ValueError("checkout intent is required")
    target = table or get_table()
    command_id = checkout_command_id(intent.parent_id, intent.idempotency_key)
    fingerprint = checkout_intent_fingerprint(
        intent, price_id=price_id, environment=environment
    )
    try:
        replay = _strong_command(command_id, table=target)
    except Exception:
        return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
    if replay is not None:
        return _classify_registration_replay(
            table=target,
            command_id=command_id,
            parent_id=intent.parent_id,
            intent_fingerprint=fingerprint,
        )

    reference = _new_public_ref()
    timestamp = _required_text(
        now_iso or intent.created_at.astimezone(timezone.utc).isoformat(),
        "now_iso",
        maximum=64,
    )
    try:
        fence = account_deletion_repo.require_active_account_fence(
            intent.parent_id, table=target
        )
    except Exception:
        return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
    generation = _positive_integer(
        fence.get("generation"), "account_fence_generation"
    )
    command_key = _command_key(command_id)
    command: CheckoutItem = {
        **command_key,
        "entity_type": "checkout_command",
        "schema_version": COMMAND_SCHEMA_VERSION,
        "command_id": command_id,
        "parent_id": intent.parent_id,
        "account_fence_generation": generation,
        "intent_fingerprint": fingerprint,
        "idempotency_key_digest": hashlib.sha256(
            intent.idempotency_key.encode("utf-8")
        ).hexdigest(),
        "checkout_ref": reference,
        "plan_id": str(intent.plan_id),
        "beneficiary_ids": sorted(intent.beneficiary_ids),
        "price_id": _required_text(price_id, "price_id"),
        "price_catalog_version": intent.price_catalog_version,
        "plan_version": intent.plan_version,
        "environment": _required_text(
            environment, "environment", maximum=32
        ).lower(),
        "command_state": CheckoutCommandState.INTENT_RECORDED,
        "command_version": 1,
        "provider_key_version": PROVIDER_KEY_VERSION,
        "provider_key_digest": _provider_key_digest(command_id, fingerprint),
        "provider_effect_status": "not_started",
        "expiration_effect_status": "not_started",
        "lease_generation": 0,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    guard: CheckoutItem = {
        **_open_guard_key(intent.parent_id),
        "entity_type": "checkout_open_guard",
        "schema_version": OPEN_GUARD_SCHEMA_VERSION,
        "parent_id": intent.parent_id,
        "account_fence_generation": generation,
        "command_id": command_id,
        "command_version": 1,
        "intent_fingerprint": fingerprint,
        "created_at": timestamp,
    }
    lookup: CheckoutItem = {
        **_public_lookup_key(reference),
        "entity_type": "checkout_public_lookup",
        "schema_version": PUBLIC_LOOKUP_SCHEMA_VERSION,
        "checkout_ref": reference,
        "parent_id": intent.parent_id,
        "account_fence_generation": generation,
        "command_id": command_id,
        "intent_fingerprint": fingerprint,
        "created_at": timestamp,
    }
    operations: list[dict[str, Any]] = [
        account_deletion_repo.active_fence_condition(intent.parent_id, generation),
        *[
            {
                "Put": {
                    "Item": item,
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            }
            for item in (command, guard, lookup)
        ],
    ]
    try:
        account_deletion_repo.transact(operations, table=target)
    except Exception:
        return _classify_registration_replay(
            table=target,
            command_id=command_id,
            parent_id=intent.parent_id,
            intent_fingerprint=fingerprint,
            checkout_ref=reference,
        )
    return CheckoutCommandResult(
        CheckoutCommandDisposition.CREATED,
        command=command,
        operations=tuple(operations),
    )


def get_checkout_command_by_public_ref(
    checkout_ref: str,
    *,
    parent_id: str,
    table: object | None = None,
) -> CheckoutCommandResult:
    """Resolve an opaque reference only for its authenticated parent owner."""
    reference = _validate_public_ref(checkout_ref)
    parent = _required_text(parent_id, "parent_id")
    target = table or get_table()
    try:
        lookup = _strong_get(target, _public_lookup_key(reference))
    except Exception:
        return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
    if lookup is None or lookup.get("parent_id") != parent:
        return CheckoutCommandResult(CheckoutCommandDisposition.NOT_FOUND)
    if (
        lookup.get("entity_type") != "checkout_public_lookup"
        or lookup.get("schema_version") != PUBLIC_LOOKUP_SCHEMA_VERSION
        or lookup.get("checkout_ref") != reference
        or not isinstance(lookup.get("command_id"), str)
    ):
        return CheckoutCommandResult(CheckoutCommandDisposition.MALFORMED)
    command_id = str(lookup["command_id"])
    try:
        command = _strong_command(command_id, table=target)
    except Exception:
        return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
    if command is None:
        return CheckoutCommandResult(CheckoutCommandDisposition.MALFORMED)
    integrity = _command_integrity(
        command,
        command_id=command_id,
        parent_id=parent,
        intent_fingerprint=str(lookup.get("intent_fingerprint") or ""),
    )
    if integrity is not None or command.get("checkout_ref") != reference:
        return CheckoutCommandResult(
            integrity or CheckoutCommandDisposition.MALFORMED
        )
    return CheckoutCommandResult(
        CheckoutCommandDisposition.REPLAYED, command=dict(command)
    )


def _active_lease(item: Mapping[str, object], now_epoch: int) -> bool:
    expiry = item.get("lease_expires_at")
    return (
        item.get("provider_effect_status")
        in {"create_claimed", "provider_outcome_unknown"}
        and type(expiry) is int
        and expiry > now_epoch
    )


def claim_provider_create(
    command: Mapping[str, object] | None,
    *,
    lease_owner: str,
    now_epoch: int,
    lease_expires_at: int,
    now_iso: str,
    table: object | None = None,
) -> CheckoutCommandResult:
    """Persist one versioned provider-create call intent before the effect."""
    if not isinstance(command, Mapping):
        return CheckoutCommandResult(CheckoutCommandDisposition.NOT_FOUND)
    owner = _required_text(lease_owner, "lease_owner")
    now = _positive_integer(now_epoch, "now_epoch", allow_zero=True)
    expiry = _positive_integer(lease_expires_at, "lease_expires_at")
    if expiry <= now:
        raise ValueError("lease_expires_at is invalid")
    timestamp = _required_text(now_iso, "now_iso", maximum=64)
    command_id = _required_text(command.get("command_id"), "command_id")
    target = table or get_table()
    try:
        current = _strong_command(command_id, table=target)
    except Exception:
        return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
    if current is None:
        return CheckoutCommandResult(CheckoutCommandDisposition.NOT_FOUND)
    integrity = _command_integrity(current, command_id=command_id)
    if integrity is not None:
        return CheckoutCommandResult(integrity)
    if current.get("provider_effect_status") == "session_attached":
        return CheckoutCommandResult(
            CheckoutCommandDisposition.ALREADY_ATTACHED, command=current
        )
    if _active_lease(current, now):
        return CheckoutCommandResult(
            CheckoutCommandDisposition.LEASE_BUSY, command=current
        )
    status = str(current.get("provider_effect_status") or "")
    if status not in _CLAIMABLE_EFFECT_STATES:
        return CheckoutCommandResult(
            CheckoutCommandDisposition.RETRYABLE, command=current
        )
    version = _positive_integer(current.get("command_version"), "command_version")
    lease_generation = (
        _positive_integer(
            current.get("lease_generation"), "lease_generation", allow_zero=True
        )
        + 1
    )
    values: CheckoutItem = {
        ":entity": "checkout_command",
        ":schema": COMMAND_SCHEMA_VERSION,
        ":command_id": command_id,
        ":parent_id": current["parent_id"],
        ":expected_version": version,
        ":expected_effect_status": status,
        ":now_epoch": now,
        ":claimed": "create_claimed",
        ":pending_state": CheckoutCommandState.PROVIDER_CREATE_PENDING,
        ":lease_owner": owner,
        ":next_lease_generation": lease_generation,
        ":lease_expires_at": expiry,
        ":next_version": version + 1,
        ":updated_at": timestamp,
    }
    operation = {
        "Update": {
            "Key": _command_key(command_id),
            "UpdateExpression": (
                "SET provider_effect_status=:claimed, "
                "command_state=:pending_state, lease_owner=:lease_owner, "
                "lease_generation=:next_lease_generation, "
                "lease_expires_at=:lease_expires_at, "
                "command_version=:next_version, updated_at=:updated_at"
            ),
            "ConditionExpression": (
                "entity_type=:entity AND schema_version=:schema "
                "AND command_id=:command_id AND parent_id=:parent_id "
                "AND command_version=:expected_version "
                "AND provider_effect_status=:expected_effect_status "
                "AND (provider_effect_status=:not_started "
                "OR lease_expires_at<=:now_epoch)"
            ),
            "ExpressionAttributeValues": {
                **values,
                ":not_started": "not_started",
            },
        }
    }
    operations = [
        account_deletion_repo.active_fence_condition(
            str(current["parent_id"]),
            _positive_integer(
                current.get("account_fence_generation"),
                "account_fence_generation",
            ),
        ),
        operation,
    ]
    try:
        account_deletion_repo.transact(operations, table=target)
    except Exception:
        try:
            refreshed = _strong_command(command_id, table=target)
        except Exception:
            return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
        if (
            refreshed is not None
            and refreshed.get("lease_owner") == owner
            and refreshed.get("lease_generation") == lease_generation
            and refreshed.get("provider_effect_status") == "create_claimed"
        ):
            return CheckoutCommandResult(
                CheckoutCommandDisposition.CLAIMED,
                command=refreshed,
                provider_claim=_provider_claim(refreshed),
            )
        if refreshed is not None and _active_lease(refreshed, now):
            return CheckoutCommandResult(
                CheckoutCommandDisposition.LEASE_BUSY, command=refreshed
            )
        return CheckoutCommandResult(
            CheckoutCommandDisposition.RETRYABLE, command=refreshed
        )
    claimed = {
        **current,
        "provider_effect_status": "create_claimed",
        "command_state": CheckoutCommandState.PROVIDER_CREATE_PENDING,
        "lease_owner": owner,
        "lease_generation": lease_generation,
        "lease_expires_at": expiry,
        "command_version": version + 1,
        "updated_at": timestamp,
    }
    return CheckoutCommandResult(
        CheckoutCommandDisposition.CLAIMED,
        command=claimed,
        provider_claim=_provider_claim(claimed),
        operations=tuple(operations),
    )


def attach_provider_session(
    claim: ProviderCreateClaim,
    *,
    provider_session_id: str,
    provider_session_url: str,
    now_iso: str,
    table: object | None = None,
) -> CheckoutCommandResult:
    """Attach exactly one provider Session under the active lease generation."""
    if not isinstance(claim, ProviderCreateClaim):
        raise ValueError("provider claim is required")
    session_id = _required_text(
        provider_session_id, "provider_session_id", maximum=255
    )
    session_url = _required_text(
        provider_session_url, "provider_session_url", maximum=2048
    )
    if not session_url.startswith("https://") or any(
        character.isspace() for character in session_url
    ):
        raise ValueError("provider_session_url is invalid")
    timestamp = _required_text(now_iso, "now_iso", maximum=64)
    session_digest = _provider_session_id_digest(session_id)
    target = table or get_table()
    try:
        current = _strong_command(claim.command_id, table=target)
    except Exception:
        return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
    if current is None:
        return CheckoutCommandResult(CheckoutCommandDisposition.NOT_FOUND)
    if current.get("provider_effect_status") == "session_attached":
        disposition = (
            CheckoutCommandDisposition.ALREADY_ATTACHED
            if current.get("provider_session_id_digest") == session_digest
            else CheckoutCommandDisposition.STALE_LEASE
        )
        return CheckoutCommandResult(disposition, command=current)
    if (
        current.get("command_version") != claim.command_version
        or current.get("lease_owner") != claim.lease_owner
        or current.get("lease_generation") != claim.lease_generation
        or current.get("provider_key_digest") != claim.provider_key_digest
        or current.get("provider_effect_status") != "create_claimed"
    ):
        return CheckoutCommandResult(
            CheckoutCommandDisposition.STALE_LEASE, command=current
        )
    values: CheckoutItem = {
        ":entity": "checkout_command",
        ":schema": COMMAND_SCHEMA_VERSION,
        ":command_id": claim.command_id,
        ":parent_id": claim.parent_id,
        ":expected_version": claim.command_version,
        ":expected_effect_status": "create_claimed",
        ":expected_lease_owner": claim.lease_owner,
        ":expected_lease_generation": claim.lease_generation,
        ":provider_key_digest": claim.provider_key_digest,
        ":attached": "session_attached",
        ":open_state": CheckoutCommandState.PROVIDER_SESSION_OPEN,
        ":provider_session_id": session_id,
        ":provider_session_url": session_url,
        ":provider_session_id_digest": session_digest,
        ":next_version": claim.command_version + 1,
        ":updated_at": timestamp,
    }
    operation = {
        "Update": {
            "Key": _command_key(claim.command_id),
            "UpdateExpression": (
                "SET provider_effect_status=:attached, command_state=:open_state, "
                "provider_session_id=:provider_session_id, "
                "provider_session_url=:provider_session_url, "
                "provider_session_id_digest=:provider_session_id_digest, "
                "command_version=:next_version, updated_at=:updated_at"
            ),
            "ConditionExpression": (
                "entity_type=:entity AND schema_version=:schema "
                "AND command_id=:command_id AND parent_id=:parent_id "
                "AND command_version=:expected_version "
                "AND provider_effect_status=:expected_effect_status "
                "AND lease_owner=:expected_lease_owner "
                "AND lease_generation=:expected_lease_generation "
                "AND provider_key_digest=:provider_key_digest"
            ),
            "ExpressionAttributeValues": values,
        }
    }
    operations = [
        account_deletion_repo.active_fence_condition(
            claim.parent_id,
            _positive_integer(
                current.get("account_fence_generation"),
                "account_fence_generation",
            ),
        ),
        operation,
    ]
    try:
        account_deletion_repo.transact(operations, table=target)
    except Exception:
        try:
            refreshed = _strong_command(claim.command_id, table=target)
        except Exception:
            return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
        if (
            refreshed is not None
            and refreshed.get("provider_effect_status") == "session_attached"
            and refreshed.get("provider_session_id_digest") == session_digest
        ):
            return CheckoutCommandResult(
                CheckoutCommandDisposition.ATTACHED, command=refreshed
            )
        return CheckoutCommandResult(
            CheckoutCommandDisposition.STALE_LEASE
            if refreshed is not None
            else CheckoutCommandDisposition.RETRYABLE,
            command=refreshed,
        )
    attached = {
        **current,
        "provider_effect_status": "session_attached",
        "command_state": CheckoutCommandState.PROVIDER_SESSION_OPEN,
        "provider_session_id": session_id,
        "provider_session_url": session_url,
        "provider_session_id_digest": session_digest,
        "command_version": claim.command_version + 1,
        "updated_at": timestamp,
    }
    return CheckoutCommandResult(
        CheckoutCommandDisposition.ATTACHED,
        command=attached,
        operations=tuple(operations),
    )


def mark_provider_outcome_unknown(
    claim: ProviderCreateClaim,
    *,
    now_iso: str,
    table: object | None = None,
) -> CheckoutCommandResult:
    """Persist ambiguity without releasing the parent one-open guard."""
    if not isinstance(claim, ProviderCreateClaim):
        raise ValueError("provider claim is required")
    timestamp = _required_text(now_iso, "now_iso", maximum=64)
    target = table or get_table()
    try:
        current = _strong_command(claim.command_id, table=target)
    except Exception:
        return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
    if current is None:
        return CheckoutCommandResult(CheckoutCommandDisposition.NOT_FOUND)
    if current.get("provider_effect_status") == "session_attached":
        return CheckoutCommandResult(
            CheckoutCommandDisposition.ALREADY_ATTACHED, command=current
        )
    if (
        current.get("provider_effect_status") == "provider_outcome_unknown"
        and current.get("lease_owner") == claim.lease_owner
        and current.get("lease_generation") == claim.lease_generation
    ):
        return CheckoutCommandResult(
            CheckoutCommandDisposition.PROVIDER_OUTCOME_UNKNOWN,
            command=current,
        )
    if (
        current.get("command_version") != claim.command_version
        or current.get("lease_owner") != claim.lease_owner
        or current.get("lease_generation") != claim.lease_generation
        or current.get("provider_key_digest") != claim.provider_key_digest
        or current.get("provider_effect_status") != "create_claimed"
    ):
        return CheckoutCommandResult(
            CheckoutCommandDisposition.STALE_LEASE, command=current
        )
    values: CheckoutItem = {
        ":entity": "checkout_command",
        ":schema": COMMAND_SCHEMA_VERSION,
        ":command_id": claim.command_id,
        ":parent_id": claim.parent_id,
        ":expected_version": claim.command_version,
        ":expected_effect_status": "create_claimed",
        ":expected_lease_owner": claim.lease_owner,
        ":expected_lease_generation": claim.lease_generation,
        ":provider_key_digest": claim.provider_key_digest,
        ":unknown": "provider_outcome_unknown",
        ":attention_state": CheckoutCommandState.OPERATOR_ATTENTION_REQUIRED,
        ":next_version": claim.command_version + 1,
        ":updated_at": timestamp,
    }
    operation = {
        "Update": {
            "Key": _command_key(claim.command_id),
            "UpdateExpression": (
                "SET provider_effect_status=:unknown, "
                "command_state=:attention_state, "
                "command_version=:next_version, updated_at=:updated_at"
            ),
            "ConditionExpression": (
                "entity_type=:entity AND schema_version=:schema "
                "AND command_id=:command_id AND parent_id=:parent_id "
                "AND command_version=:expected_version "
                "AND provider_effect_status=:expected_effect_status "
                "AND lease_owner=:expected_lease_owner "
                "AND lease_generation=:expected_lease_generation "
                "AND provider_key_digest=:provider_key_digest"
            ),
            "ExpressionAttributeValues": values,
        }
    }
    operations = [
        account_deletion_repo.active_fence_condition(
            claim.parent_id,
            _positive_integer(
                current.get("account_fence_generation"),
                "account_fence_generation",
            ),
        ),
        operation,
    ]
    try:
        account_deletion_repo.transact(operations, table=target)
    except Exception:
        try:
            refreshed = _strong_command(claim.command_id, table=target)
        except Exception:
            return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
        if (
            refreshed is not None
            and refreshed.get("provider_effect_status") == "provider_outcome_unknown"
            and refreshed.get("lease_owner") == claim.lease_owner
            and refreshed.get("lease_generation") == claim.lease_generation
        ):
            return CheckoutCommandResult(
                CheckoutCommandDisposition.PROVIDER_OUTCOME_UNKNOWN,
                command=refreshed,
            )
        return CheckoutCommandResult(
            CheckoutCommandDisposition.STALE_LEASE
            if refreshed is not None
            else CheckoutCommandDisposition.RETRYABLE,
            command=refreshed,
        )
    unknown = {
        **current,
        "provider_effect_status": "provider_outcome_unknown",
        "command_state": CheckoutCommandState.OPERATOR_ATTENTION_REQUIRED,
        "command_version": claim.command_version + 1,
        "updated_at": timestamp,
    }
    return CheckoutCommandResult(
        CheckoutCommandDisposition.PROVIDER_OUTCOME_UNKNOWN,
        command=unknown,
        operations=tuple(operations),
    )


def release_open_guard_for_terminal_command(
    command: Mapping[str, object] | None,
    *,
    table: object | None = None,
) -> CheckoutCommandResult:
    """Release one guard only with current terminal command/version proof."""
    if not isinstance(command, Mapping):
        return CheckoutCommandResult(CheckoutCommandDisposition.NOT_FOUND)
    command_id = _required_text(command.get("command_id"), "command_id")
    target = table or get_table()
    try:
        current = _strong_command(command_id, table=target)
    except Exception:
        return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
    if current is None:
        return CheckoutCommandResult(CheckoutCommandDisposition.NOT_FOUND)
    integrity = _command_integrity(current, command_id=command_id)
    if integrity is not None:
        return CheckoutCommandResult(integrity)
    try:
        state = CheckoutCommandState(str(current.get("command_state") or ""))
    except ValueError:
        return CheckoutCommandResult(CheckoutCommandDisposition.MALFORMED)
    if state not in _TERMINAL_STATES:
        return CheckoutCommandResult(
            CheckoutCommandDisposition.NOT_TERMINAL, command=current
        )
    version = _positive_integer(current.get("command_version"), "command_version")
    if command.get("command_version") != version:
        return CheckoutCommandResult(
            CheckoutCommandDisposition.STALE_VERSION, command=current
        )
    parent_id = _required_text(current.get("parent_id"), "parent_id")
    operations: list[dict[str, Any]] = [
        {
            "ConditionCheck": {
                "Key": _command_key(command_id),
                "ConditionExpression": (
                    "entity_type=:entity AND schema_version=:schema "
                    "AND command_id=:command_id AND parent_id=:parent_id "
                    "AND command_version=:expected_command_version "
                    "AND command_state IN (:activated,:without_payment)"
                ),
                "ExpressionAttributeValues": {
                    ":entity": "checkout_command",
                    ":schema": COMMAND_SCHEMA_VERSION,
                    ":command_id": command_id,
                    ":parent_id": parent_id,
                    ":expected_command_version": version,
                    ":activated": CheckoutCommandState.ACTIVATION_RECORDED,
                    ":without_payment": CheckoutCommandState.TERMINAL_WITHOUT_PAYMENT,
                },
            }
        },
        {
            "Delete": {
                "Key": _open_guard_key(parent_id),
                "ConditionExpression": (
                    "entity_type=:guard_entity AND schema_version=:guard_schema "
                    "AND parent_id=:parent_id AND command_id=:command_id"
                ),
                "ExpressionAttributeValues": {
                    ":guard_entity": "checkout_open_guard",
                    ":guard_schema": OPEN_GUARD_SCHEMA_VERSION,
                    ":parent_id": parent_id,
                    ":command_id": command_id,
                },
            }
        },
    ]
    try:
        account_deletion_repo.transact(operations, table=target)
    except Exception:
        try:
            guard = _strong_get(target, _open_guard_key(parent_id))
        except Exception:
            return CheckoutCommandResult(CheckoutCommandDisposition.RETRYABLE)
        if guard is None:
            return CheckoutCommandResult(
                CheckoutCommandDisposition.RELEASED, command=current
            )
        return CheckoutCommandResult(
            CheckoutCommandDisposition.RETRYABLE, command=current
        )
    return CheckoutCommandResult(
        CheckoutCommandDisposition.RELEASED,
        command=current,
        operations=tuple(operations),
    )


def _supersession_disposition(
    command: Mapping[str, object],
) -> CheckoutSupersessionDisposition | None:
    status = command.get("expiration_effect_status")
    if status == "nonpayable_proven":
        return CheckoutSupersessionDisposition.NONPAYABLE_PROVEN
    if status == "payment_reconciliation_required":
        return CheckoutSupersessionDisposition.RECONCILIATION_REQUIRED
    if status == "expiration_outcome_unknown":
        return CheckoutSupersessionDisposition.PROVIDER_UNKNOWN
    if status == "expire_claimed":
        return CheckoutSupersessionDisposition.EXPIRATION_BUSY
    return None


def claim_session_expiration(
    command: Mapping[str, object] | None,
    *,
    now_iso: str,
    table: object | None = None,
) -> CheckoutSupersessionResult:
    """Conditionally persist the one allowed provider Session expiration intent."""
    if not isinstance(command, Mapping):
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.NOT_FOUND
        )
    command_id = _required_text(command.get("command_id"), "command_id")
    timestamp = _required_text(now_iso, "now_iso", maximum=64)
    target = table or get_table()
    try:
        current = _strong_command(command_id, table=target)
    except Exception:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.RETRYABLE
        )
    if current is None:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.NOT_FOUND
        )
    integrity = _command_integrity(
        current,
        command_id=command_id,
        parent_id=str(command.get("parent_id") or ""),
    )
    if integrity is not None:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.IDENTITY_MISMATCH
            if integrity is CheckoutCommandDisposition.IDENTITY_MISMATCH
            else CheckoutSupersessionDisposition.MALFORMED,
            command=current,
        )
    known = _supersession_disposition(current)
    if known is not None:
        return CheckoutSupersessionResult(known, command=current)
    if (
        current.get("provider_effect_status") != "session_attached"
        or not isinstance(current.get("provider_session_id"), str)
        or current.get("expiration_effect_status", "not_started") != "not_started"
    ):
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.MALFORMED,
            command=current,
        )
    version = _positive_integer(current.get("command_version"), "command_version")
    parent_id = _required_text(current.get("parent_id"), "parent_id")
    operation = {
        "Update": {
            "Key": _command_key(command_id),
            "UpdateExpression": (
                "SET expiration_effect_status=:expire_claimed, "
                "command_version=:next_version, updated_at=:updated_at"
            ),
            "ConditionExpression": (
                "entity_type=:entity AND schema_version=:schema "
                "AND command_id=:command_id AND parent_id=:parent_id "
                "AND command_version=:expected_version "
                "AND provider_effect_status=:session_attached "
                "AND (attribute_not_exists(expiration_effect_status) "
                "OR expiration_effect_status=:not_started) "
                "AND attribute_not_exists(superseded_by_command_id)"
            ),
            "ExpressionAttributeValues": {
                ":entity": "checkout_command",
                ":schema": COMMAND_SCHEMA_VERSION,
                ":command_id": command_id,
                ":parent_id": parent_id,
                ":expected_version": version,
                ":session_attached": "session_attached",
                ":not_started": "not_started",
                ":expire_claimed": "expire_claimed",
                ":next_version": version + 1,
                ":updated_at": timestamp,
            },
        }
    }
    operations = [
        account_deletion_repo.active_fence_condition(
            parent_id,
            _positive_integer(
                current.get("account_fence_generation"),
                "account_fence_generation",
            ),
        ),
        operation,
    ]
    try:
        account_deletion_repo.transact(operations, table=target)
    except Exception:
        try:
            refreshed = _strong_command(command_id, table=target)
        except Exception:
            return CheckoutSupersessionResult(
                CheckoutSupersessionDisposition.RETRYABLE
            )
        if refreshed is None:
            return CheckoutSupersessionResult(
                CheckoutSupersessionDisposition.RETRYABLE
            )
        disposition = _supersession_disposition(refreshed)
        return CheckoutSupersessionResult(
            disposition or CheckoutSupersessionDisposition.STALE_VERSION,
            command=refreshed,
        )
    claimed = {
        **current,
        "expiration_effect_status": "expire_claimed",
        "command_version": version + 1,
        "updated_at": timestamp,
    }
    return CheckoutSupersessionResult(
        CheckoutSupersessionDisposition.EXPIRATION_CLAIMED,
        command=claimed,
        operations=tuple(operations),
    )


def record_session_expiration(
    command: Mapping[str, object] | None,
    *,
    provider_session_status: str,
    now_iso: str,
    table: object | None = None,
) -> CheckoutSupersessionResult:
    """Persist provider-authoritative expired, complete, or unknown evidence."""
    if not isinstance(command, Mapping):
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.NOT_FOUND
        )
    status = _required_text(
        provider_session_status,
        "provider_session_status",
        maximum=32,
    )
    outcome = {
        "expired": (
            "nonpayable_proven",
            CheckoutCommandState.TERMINAL_WITHOUT_PAYMENT,
            CheckoutSupersessionDisposition.NONPAYABLE_PROVEN,
        ),
        "complete": (
            "payment_reconciliation_required",
            CheckoutCommandState.RECONCILING,
            CheckoutSupersessionDisposition.RECONCILIATION_REQUIRED,
        ),
        "unknown": (
            "expiration_outcome_unknown",
            CheckoutCommandState.OPERATOR_ATTENTION_REQUIRED,
            CheckoutSupersessionDisposition.PROVIDER_UNKNOWN,
        ),
    }.get(status)
    if outcome is None:
        raise ValueError("provider_session_status is invalid")
    effect_status, command_state, disposition = outcome
    timestamp = _required_text(now_iso, "now_iso", maximum=64)
    command_id = _required_text(command.get("command_id"), "command_id")
    target = table or get_table()
    try:
        current = _strong_command(command_id, table=target)
    except Exception:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.RETRYABLE
        )
    if current is None:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.NOT_FOUND
        )
    integrity = _command_integrity(
        current,
        command_id=command_id,
        parent_id=str(command.get("parent_id") or ""),
    )
    if integrity is not None:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.IDENTITY_MISMATCH
            if integrity is CheckoutCommandDisposition.IDENTITY_MISMATCH
            else CheckoutSupersessionDisposition.MALFORMED,
            command=current,
        )
    known = _supersession_disposition(current)
    if known is not None and known is not CheckoutSupersessionDisposition.EXPIRATION_BUSY:
        return CheckoutSupersessionResult(known, command=current)
    if current.get("provider_effect_status") != "session_attached":
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.MALFORMED,
            command=current,
        )
    current_effect = str(current.get("expiration_effect_status") or "not_started")
    if current_effect not in {"not_started", "expire_claimed"}:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.STALE_VERSION,
            command=current,
        )
    version = _positive_integer(current.get("command_version"), "command_version")
    parent_id = _required_text(current.get("parent_id"), "parent_id")
    operation = {
        "Update": {
            "Key": _command_key(command_id),
            "UpdateExpression": (
                "SET expiration_effect_status=:effect_status, "
                "command_state=:command_state, command_version=:next_version, "
                "updated_at=:updated_at"
            ),
            "ConditionExpression": (
                "entity_type=:entity AND schema_version=:schema "
                "AND command_id=:command_id AND parent_id=:parent_id "
                "AND command_version=:expected_version "
                "AND provider_effect_status=:session_attached "
                "AND (expiration_effect_status=:expected_effect_status "
                "OR (attribute_not_exists(expiration_effect_status) "
                "AND :expected_effect_status=:not_started)) "
                "AND attribute_not_exists(superseded_by_command_id)"
            ),
            "ExpressionAttributeValues": {
                ":entity": "checkout_command",
                ":schema": COMMAND_SCHEMA_VERSION,
                ":command_id": command_id,
                ":parent_id": parent_id,
                ":expected_version": version,
                ":session_attached": "session_attached",
                ":expected_effect_status": current_effect,
                ":not_started": "not_started",
                ":effect_status": effect_status,
                ":command_state": command_state,
                ":next_version": version + 1,
                ":updated_at": timestamp,
            },
        }
    }
    operations = [
        account_deletion_repo.active_fence_condition(
            parent_id,
            _positive_integer(
                current.get("account_fence_generation"),
                "account_fence_generation",
            ),
        ),
        operation,
    ]
    try:
        account_deletion_repo.transact(operations, table=target)
    except Exception:
        try:
            refreshed = _strong_command(command_id, table=target)
        except Exception:
            return CheckoutSupersessionResult(
                CheckoutSupersessionDisposition.RETRYABLE
            )
        if refreshed is not None:
            refreshed_disposition = _supersession_disposition(refreshed)
            if refreshed_disposition is not None:
                return CheckoutSupersessionResult(
                    refreshed_disposition,
                    command=refreshed,
                )
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.STALE_VERSION,
            command=refreshed,
        )
    recorded = {
        **current,
        "expiration_effect_status": effect_status,
        "command_state": command_state,
        "command_version": version + 1,
        "updated_at": timestamp,
    }
    return CheckoutSupersessionResult(
        disposition,
        command=recorded,
        operations=tuple(operations),
    )


def _classify_supersession_replay(
    *,
    table: object,
    old_command_id: str,
    new_command_id: str,
    parent_id: str,
    new_fingerprint: str,
) -> CheckoutSupersessionResult:
    try:
        old = _strong_command(old_command_id, table=table)
        new = _strong_command(new_command_id, table=table)
        guard = _strong_get(table, _open_guard_key(parent_id))
    except Exception:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.RETRYABLE
        )
    if (
        old is not None
        and new is not None
        and old.get("superseded_by_command_id") == new_command_id
        and guard is not None
        and guard.get("command_id") == new_command_id
        and _command_integrity(
            new,
            command_id=new_command_id,
            parent_id=parent_id,
            intent_fingerprint=new_fingerprint,
        )
        is None
    ):
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.SUPERSEDED,
            command=new,
        )
    if old is not None and isinstance(old.get("superseded_by_command_id"), str):
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.IDENTITY_MISMATCH,
            command=old,
        )
    return CheckoutSupersessionResult(
        CheckoutSupersessionDisposition.RETRYABLE,
        command=old,
    )


def supersede_checkout_command(
    old_command: Mapping[str, object] | None,
    new_intent: CheckoutIntent,
    *,
    price_id: str,
    environment: str,
    now_iso: str,
    table: object | None = None,
) -> CheckoutSupersessionResult:
    """Atomically terminalize the old command and transfer its guard."""
    if not isinstance(old_command, Mapping):
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.NOT_FOUND
        )
    if not isinstance(new_intent, CheckoutIntent):
        raise ValueError("checkout intent is required")
    old_command_id = _required_text(old_command.get("command_id"), "command_id")
    parent_id = _required_text(old_command.get("parent_id"), "parent_id")
    if new_intent.parent_id != parent_id or new_intent.command_id == old_command_id:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.IDENTITY_MISMATCH
        )
    timestamp = _required_text(now_iso, "now_iso", maximum=64)
    new_command_id = checkout_command_id(
        new_intent.parent_id,
        new_intent.idempotency_key,
    )
    if new_intent.command_id != new_command_id:
        raise ValueError("checkout command identity is invalid")
    new_fingerprint = checkout_intent_fingerprint(
        new_intent,
        price_id=price_id,
        environment=environment,
    )
    target = table or get_table()
    try:
        current = _strong_command(old_command_id, table=target)
        guard = _strong_get(target, _open_guard_key(parent_id))
    except Exception:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.RETRYABLE
        )
    if current is None:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.NOT_FOUND
        )
    integrity = _command_integrity(
        current,
        command_id=old_command_id,
        parent_id=parent_id,
    )
    if integrity is not None:
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.IDENTITY_MISMATCH
            if integrity is CheckoutCommandDisposition.IDENTITY_MISMATCH
            else CheckoutSupersessionDisposition.MALFORMED,
            command=current,
        )
    if isinstance(current.get("superseded_by_command_id"), str):
        return _classify_supersession_replay(
            table=target,
            old_command_id=old_command_id,
            new_command_id=new_command_id,
            parent_id=parent_id,
            new_fingerprint=new_fingerprint,
        )
    if (
        current.get("expiration_effect_status") != "nonpayable_proven"
        or current.get("command_state")
        not in {
            CheckoutCommandState.TERMINAL_WITHOUT_PAYMENT,
            CheckoutCommandState.TERMINAL_WITHOUT_PAYMENT.value,
        }
    ):
        return CheckoutSupersessionResult(
            _supersession_disposition(current)
            or CheckoutSupersessionDisposition.STALE_VERSION,
            command=current,
        )
    version = _positive_integer(current.get("command_version"), "command_version")
    generation = _positive_integer(
        current.get("account_fence_generation"),
        "account_fence_generation",
    )
    if (
        guard is None
        or guard.get("entity_type") != "checkout_open_guard"
        or guard.get("schema_version") != OPEN_GUARD_SCHEMA_VERSION
        or guard.get("parent_id") != parent_id
        or guard.get("command_id") != old_command_id
    ):
        return CheckoutSupersessionResult(
            CheckoutSupersessionDisposition.MALFORMED,
            command=current,
        )
    guard_version = _positive_integer(
        guard.get("command_version"),
        "guard_command_version",
    )
    reference = _new_public_ref()
    new_command: CheckoutItem = {
        **_command_key(new_command_id),
        "entity_type": "checkout_command",
        "schema_version": COMMAND_SCHEMA_VERSION,
        "command_id": new_command_id,
        "parent_id": parent_id,
        "account_fence_generation": generation,
        "intent_fingerprint": new_fingerprint,
        "idempotency_key_digest": hashlib.sha256(
            new_intent.idempotency_key.encode("utf-8")
        ).hexdigest(),
        "checkout_ref": reference,
        "plan_id": str(new_intent.plan_id),
        "beneficiary_ids": sorted(new_intent.beneficiary_ids),
        "price_id": _required_text(price_id, "price_id"),
        "price_catalog_version": new_intent.price_catalog_version,
        "plan_version": new_intent.plan_version,
        "environment": _required_text(
            environment,
            "environment",
            maximum=32,
        ).lower(),
        "command_state": CheckoutCommandState.INTENT_RECORDED,
        "command_version": 1,
        "provider_key_version": PROVIDER_KEY_VERSION,
        "provider_key_digest": _provider_key_digest(
            new_command_id,
            new_fingerprint,
        ),
        "provider_effect_status": "not_started",
        "expiration_effect_status": "not_started",
        "lease_generation": 0,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    lookup: CheckoutItem = {
        **_public_lookup_key(reference),
        "entity_type": "checkout_public_lookup",
        "schema_version": PUBLIC_LOOKUP_SCHEMA_VERSION,
        "checkout_ref": reference,
        "parent_id": parent_id,
        "account_fence_generation": generation,
        "command_id": new_command_id,
        "intent_fingerprint": new_fingerprint,
        "created_at": timestamp,
    }
    operations: list[dict[str, Any]] = [
        account_deletion_repo.active_fence_condition(parent_id, generation),
        {
            "Update": {
                "Key": _command_key(old_command_id),
                "UpdateExpression": (
                    "SET superseded_by_command_id=:new_command_id, "
                    "superseded_at=:superseded_at, command_version=:next_version, "
                    "updated_at=:superseded_at"
                ),
                "ConditionExpression": (
                    "entity_type=:entity AND schema_version=:schema "
                    "AND command_id=:old_command_id AND parent_id=:parent_id "
                    "AND command_version=:expected_version "
                    "AND expiration_effect_status=:nonpayable "
                    "AND command_state=:terminal "
                    "AND attribute_not_exists(superseded_by_command_id)"
                ),
                "ExpressionAttributeValues": {
                    ":entity": "checkout_command",
                    ":schema": COMMAND_SCHEMA_VERSION,
                    ":old_command_id": old_command_id,
                    ":parent_id": parent_id,
                    ":expected_version": version,
                    ":nonpayable": "nonpayable_proven",
                    ":terminal": CheckoutCommandState.TERMINAL_WITHOUT_PAYMENT,
                    ":new_command_id": new_command_id,
                    ":next_version": version + 1,
                    ":superseded_at": timestamp,
                },
            }
        },
        {
            "Update": {
                "Key": _open_guard_key(parent_id),
                "UpdateExpression": (
                    "SET command_id=:new_command_id, command_version=:new_version, "
                    "intent_fingerprint=:new_fingerprint, created_at=:created_at"
                ),
                "ConditionExpression": (
                    "entity_type=:guard_entity AND schema_version=:guard_schema "
                    "AND parent_id=:parent_id AND command_id=:old_command_id "
                    "AND command_version=:expected_old_version"
                ),
                "ExpressionAttributeValues": {
                    ":guard_entity": "checkout_open_guard",
                    ":guard_schema": OPEN_GUARD_SCHEMA_VERSION,
                    ":parent_id": parent_id,
                    ":old_command_id": old_command_id,
                    ":expected_old_version": guard_version,
                    ":new_command_id": new_command_id,
                    ":new_version": 1,
                    ":new_fingerprint": new_fingerprint,
                    ":created_at": timestamp,
                },
            }
        },
        {
            "Put": {
                "Item": new_command,
                "ConditionExpression": (
                    "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                ),
            }
        },
        {
            "Put": {
                "Item": lookup,
                "ConditionExpression": (
                    "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                ),
            }
        },
    ]
    try:
        account_deletion_repo.transact(operations, table=target)
    except Exception:
        return _classify_supersession_replay(
            table=target,
            old_command_id=old_command_id,
            new_command_id=new_command_id,
            parent_id=parent_id,
            new_fingerprint=new_fingerprint,
        )
    return CheckoutSupersessionResult(
        CheckoutSupersessionDisposition.SUPERSEDED,
        command=new_command,
        operations=tuple(operations),
    )


__all__ = [
    "CheckoutCommandDisposition",
    "CheckoutCommandResult",
    "CheckoutSupersessionDisposition",
    "CheckoutSupersessionResult",
    "ProviderCreateClaim",
    "attach_provider_session",
    "checkout_command_id",
    "checkout_intent_fingerprint",
    "claim_session_expiration",
    "claim_provider_create",
    "get_checkout_command_by_public_ref",
    "mark_provider_outcome_unknown",
    "record_session_expiration",
    "register_checkout_command",
    "release_open_guard_for_terminal_command",
    "supersede_checkout_command",
]
