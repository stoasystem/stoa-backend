"""Redacted provider facts and exact-once paid activation persistence."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo
from stoa.models.billing import BillingFact, BillingFactKind, BillingPlanId


type BillingItem = dict[str, object]

EVENT_INBOX_SCHEMA_VERSION = "billing_event_inbox.v1"
SEMANTIC_DEDUPE_SCHEMA_VERSION = "billing_semantic_dedupe.v1"
OBJECT_FACT_SCHEMA_VERSION = "billing_object_fact.v1"
RECONCILIATION_LEASE_SCHEMA_VERSION = "billing_reconciliation_lease.v1"
ACTIVATION_RECEIPT_SCHEMA_VERSION = "billing_activation_receipt.v1"

_EVENT_ID_DOMAIN = b"stoa.billing.provider-event.v1"
_OBJECT_ID_DOMAIN = b"stoa.billing.provider-object.v1"
_SEMANTIC_DOMAIN = b"stoa.billing.semantic-event.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_LEASE_SECONDS = 300


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


class BillingEventDisposition(StrEnum):
    REGISTERED = "registered"
    EVENT_DUPLICATE = "event_duplicate"
    SEMANTIC_DUPLICATE = "semantic_duplicate"
    RETRYABLE = "retryable_dependency"


class FactRecordDisposition(StrEnum):
    CREATED = "created"
    ADVANCED = "advanced"
    DUPLICATE = "duplicate"
    STALE = "stale"
    RETRYABLE = "retryable_dependency"


class ReconciliationDisposition(StrEnum):
    CLAIMED = "claimed"
    LEASE_BUSY = "lease_busy"
    RETRYABLE = "retryable_dependency"


class ActivationDisposition(StrEnum):
    COMMITTED = "committed"
    ALREADY_COMMITTED = "already_committed"
    CONFLICT = "conditional_conflict"
    RETRYABLE = "retryable_dependency"


@dataclass(frozen=True, slots=True)
class BillingEventResult:
    disposition: BillingEventDisposition
    receipt: BillingItem | None = None
    operations: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class FactRecordResult:
    disposition: FactRecordDisposition
    fact: BillingFact | None = None
    operations: tuple[dict[str, Any], ...] = ()

    @property
    def accepted(self) -> bool:
        return self.disposition in {
            FactRecordDisposition.CREATED,
            FactRecordDisposition.ADVANCED,
            FactRecordDisposition.DUPLICATE,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationClaim:
    command_id: str
    lease_owner: str
    lease_generation: int
    lease_expires_at: int


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    disposition: ReconciliationDisposition
    claim: ReconciliationClaim | None = None
    operations: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class PaidActivationRequest:
    command_id: str
    parent_id: str
    expected_command_version: int
    provider_customer_id_digest: str
    price_id: str
    environment: str
    plan_id: BillingPlanId
    plan_version: int
    allowance_version: int
    activation_version: int
    paid_invoice_fact_id: str
    active_subscription_fact_id: str
    activated_at: str
    provider_livemode: bool = False
    provider_subscription_id_digest: str = ""


@dataclass(frozen=True, slots=True)
class ActivationResult:
    disposition: ActivationDisposition
    receipt: BillingItem | None = None
    operations: tuple[dict[str, Any], ...] = ()


def _required_text(value: object, field: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} is invalid")
    if value != value.strip() or not 1 <= len(value) <= maximum:
        raise ValueError(f"{field} is invalid")
    return value


def _positive_integer(value: object, field: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} is invalid")
    return value


def _digest(value: object, field: str) -> str:
    text = _required_text(value, field, maximum=64)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{field} is invalid")
    return text


def _timestamp(value: object, field: str) -> str:
    text = _required_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} is invalid")
    return text


def _model_timestamp(value: datetime, field: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} is invalid")
    return value.isoformat()


def _length_prefixed(parts: tuple[str, ...]) -> bytes:
    encoded = bytearray()
    for part in parts:
        value = part.encode("utf-8")
        encoded.extend(len(value).to_bytes(4, "big"))
        encoded.extend(value)
    return bytes(encoded)


def _domain_digest(domain: bytes, *parts: str) -> str:
    return hashlib.sha256(domain + b"\x00" + _length_prefixed(tuple(parts))).hexdigest()


def _event_digest(provider_event_id: str) -> str:
    return _domain_digest(_EVENT_ID_DOMAIN, _required_text(provider_event_id, "provider_event_id"))


def _object_digest(provider_object_id: str) -> str:
    return _domain_digest(
        _OBJECT_ID_DOMAIN,
        _required_text(provider_object_id, "provider_object_id"),
    )


def _semantic_digest(event_type: str, provider_object_id: str) -> str:
    return _domain_digest(
        _SEMANTIC_DOMAIN,
        _required_text(event_type, "event_type", maximum=100),
        _required_text(provider_object_id, "provider_object_id"),
    )


def _event_key(provider_event_id_digest: str) -> dict[str, str]:
    return {"PK": f"BILLING_EVENT_INBOX#{provider_event_id_digest}", "SK": "EVENT"}


def _semantic_key(semantic_identity: str) -> dict[str, str]:
    return {"PK": f"BILLING_SEMANTIC#{semantic_identity}", "SK": "DEDUPE"}


def _command_partition(command_id: str) -> str:
    return f"BILLING_ACTIVATION#{_required_text(command_id, 'command_id')}"


def _fact_key(fact: BillingFact) -> dict[str, str]:
    return {
        "PK": _command_partition(fact.checkout_command_id),
        "SK": f"OBJECT_FACT#{fact.kind}#{fact.provider_object_id_digest}",
    }


def _lease_key(command_id: str) -> dict[str, str]:
    return {"PK": _command_partition(command_id), "SK": "RECONCILIATION_LEASE"}


def _receipt_key(command_id: str, activation_version: int) -> dict[str, str]:
    return {
        "PK": _command_partition(command_id),
        "SK": f"ACTIVATION_RECEIPT#{activation_version:020d}",
    }


def _command_key(command_id: str) -> dict[str, str]:
    return {"PK": f"CHECKOUT_COMMAND#{command_id}", "SK": "COMMAND"}


def _mapping(value: object) -> BillingItem | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError("billing dependency returned malformed data")
    return {str(key): member for key, member in value.items()}


def _strong_get(table: object, key: Mapping[str, str]) -> BillingItem | None:
    if not isinstance(table, _GetTable):
        raise ValueError("billing persistence is unavailable")
    response = table.get_item(Key=dict(key), ConsistentRead=True)
    if not isinstance(response, Mapping):
        raise ValueError("billing dependency returned malformed data")
    return _mapping(response.get("Item"))


def _create_only(item: Mapping[str, object]) -> dict[str, Any]:
    return {
        "Put": {
            "Item": dict(item),
            "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
        }
    }


def _transact(operations: Sequence[dict[str, Any]], *, table: object) -> None:
    account_deletion_repo.transact(operations, table=table)


def _event_receipt_matches(
    item: Mapping[str, object],
    *,
    provider_event_id_digest: str,
    semantic_identity: str,
) -> bool:
    return (
        item.get("schema_version") == EVENT_INBOX_SCHEMA_VERSION
        and item.get("provider_event_id_digest") == provider_event_id_digest
        and item.get("semantic_identity") == semantic_identity
    )


def register_provider_event(
    *,
    provider_event_id: str,
    event_type: str,
    provider_object_id: str,
    object_version: int,
    fact_observed_at: str,
    table: object | None = None,
) -> BillingEventResult:
    """Register one redacted event receipt and one semantic side-effect identity."""
    event_kind = _required_text(event_type, "event_type", maximum=100)
    version = _positive_integer(object_version, "object_version")
    observed = _timestamp(fact_observed_at, "fact_observed_at")
    event_id_digest = _event_digest(provider_event_id)
    object_id_digest = _object_digest(provider_object_id)
    semantic_identity = _semantic_digest(event_kind, provider_object_id)
    target = table or get_table()
    key = _event_key(event_id_digest)
    try:
        existing_event = _strong_get(target, key)
    except Exception:
        return BillingEventResult(BillingEventDisposition.RETRYABLE)
    if existing_event is not None:
        disposition = (
            BillingEventDisposition.EVENT_DUPLICATE
            if _event_receipt_matches(
                existing_event,
                provider_event_id_digest=event_id_digest,
                semantic_identity=semantic_identity,
            )
            else BillingEventDisposition.RETRYABLE
        )
        return BillingEventResult(disposition, receipt=existing_event)

    receipt: BillingItem = {
        **key,
        "entity_type": "billing_event_inbox",
        "schema_version": EVENT_INBOX_SCHEMA_VERSION,
        "provider_event_id_digest": event_id_digest,
        "semantic_identity": semantic_identity,
        "provider_object_id_digest": object_id_digest,
        "event_type": event_kind,
        "object_version": version,
        "fact_observed_at": observed,
        "processing_result": BillingEventDisposition.REGISTERED,
    }
    semantic: BillingItem = {
        **_semantic_key(semantic_identity),
        "entity_type": "billing_semantic_dedupe",
        "schema_version": SEMANTIC_DEDUPE_SCHEMA_VERSION,
        "semantic_identity": semantic_identity,
        "provider_object_id_digest": object_id_digest,
        "event_type": event_kind,
        "object_version": version,
        "fact_observed_at": observed,
        "processing_result": BillingEventDisposition.REGISTERED,
    }
    operations = [_create_only(receipt), _create_only(semantic)]
    try:
        _transact(operations, table=target)
    except Exception:
        try:
            replay = _strong_get(target, key)
            if replay is not None:
                disposition = (
                    BillingEventDisposition.EVENT_DUPLICATE
                    if _event_receipt_matches(
                        replay,
                        provider_event_id_digest=event_id_digest,
                        semantic_identity=semantic_identity,
                    )
                    else BillingEventDisposition.RETRYABLE
                )
                return BillingEventResult(disposition, receipt=replay)
            existing_semantic = _strong_get(target, _semantic_key(semantic_identity))
        except Exception:
            return BillingEventResult(BillingEventDisposition.RETRYABLE)
        if (
            existing_semantic is None
            or existing_semantic.get("schema_version") != SEMANTIC_DEDUPE_SCHEMA_VERSION
            or existing_semantic.get("semantic_identity") != semantic_identity
            or existing_semantic.get("event_type") != event_kind
            or existing_semantic.get("provider_object_id_digest") != object_id_digest
        ):
            return BillingEventResult(BillingEventDisposition.RETRYABLE)
        duplicate_receipt = {
            **receipt,
            "processing_result": BillingEventDisposition.SEMANTIC_DUPLICATE,
        }
        audit_operation = _create_only(duplicate_receipt)
        try:
            _transact([audit_operation], table=target)
        except Exception:
            try:
                replay = _strong_get(target, key)
            except Exception:
                return BillingEventResult(BillingEventDisposition.RETRYABLE)
            if replay is None or not _event_receipt_matches(
                replay,
                provider_event_id_digest=event_id_digest,
                semantic_identity=semantic_identity,
            ):
                return BillingEventResult(BillingEventDisposition.RETRYABLE)
            duplicate_receipt = replay
        return BillingEventResult(
            BillingEventDisposition.SEMANTIC_DUPLICATE,
            receipt=duplicate_receipt,
            operations=(audit_operation,),
        )
    return BillingEventResult(
        BillingEventDisposition.REGISTERED,
        receipt=receipt,
        operations=tuple(operations),
    )


def _fact_item(fact: BillingFact) -> BillingItem:
    return {
        **_fact_key(fact),
        "entity_type": "billing_object_fact",
        "schema_version": OBJECT_FACT_SCHEMA_VERSION,
        "fact_id": fact.fact_id,
        "checkout_command_id": fact.checkout_command_id,
        "kind": fact.kind,
        "provider_event_id_digest": fact.provider_event_id_digest,
        "provider_object_id_digest": fact.provider_object_id_digest,
        "object_version": fact.fact_version,
        "fact_observed_at": _model_timestamp(fact.observed_at, "observed_at"),
        "processing_result": "current",
    }


def billing_fact_from_item(item: Mapping[str, object]) -> BillingFact:
    """Rebuild the closed model while keeping verification/live flags out of storage."""
    if (
        item.get("entity_type") != "billing_object_fact"
        or item.get("schema_version") != OBJECT_FACT_SCHEMA_VERSION
    ):
        raise ValueError("billing fact row is malformed")
    return BillingFact(
        factId=item.get("fact_id"),
        checkoutCommandId=item.get("checkout_command_id"),
        kind=item.get("kind"),
        providerEventIdDigest=item.get("provider_event_id_digest"),
        providerObjectIdDigest=item.get("provider_object_id_digest"),
        signatureVerified=True,
        providerLivemode=False,
        factVersion=item.get("object_version"),
        observedAt=item.get("fact_observed_at"),
    )


def _classify_fact_replay(
    item: BillingItem | None,
    fact: BillingFact,
) -> FactRecordResult:
    if item is None:
        return FactRecordResult(FactRecordDisposition.RETRYABLE)
    try:
        current = billing_fact_from_item(item)
    except (ValueError, TypeError):
        return FactRecordResult(FactRecordDisposition.RETRYABLE)
    if current.fact_version > fact.fact_version:
        return FactRecordResult(FactRecordDisposition.STALE, fact=current)
    if current.fact_version == fact.fact_version:
        disposition = (
            FactRecordDisposition.DUPLICATE
            if current == fact
            else FactRecordDisposition.STALE
        )
        return FactRecordResult(disposition, fact=current)
    return FactRecordResult(FactRecordDisposition.RETRYABLE, fact=current)


def record_provider_fact(
    fact: BillingFact,
    *,
    table: object | None = None,
) -> FactRecordResult:
    """Create or monotonically advance one provider-object fact."""
    if not isinstance(fact, BillingFact):
        raise ValueError("BillingFact is required")
    target = table or get_table()
    item = _fact_item(fact)
    key = _fact_key(fact)
    try:
        current_item = _strong_get(target, key)
    except Exception:
        return FactRecordResult(FactRecordDisposition.RETRYABLE)
    if current_item is None:
        operation = _create_only(item)
        try:
            _transact([operation], table=target)
        except Exception:
            try:
                replay = _strong_get(target, key)
            except Exception:
                return FactRecordResult(FactRecordDisposition.RETRYABLE)
            return _classify_fact_replay(replay, fact)
        return FactRecordResult(
            FactRecordDisposition.CREATED,
            fact=fact,
            operations=(operation,),
        )

    classified = _classify_fact_replay(current_item, fact)
    if classified.disposition is not FactRecordDisposition.RETRYABLE:
        return classified
    try:
        current = billing_fact_from_item(current_item)
    except (ValueError, TypeError):
        return FactRecordResult(FactRecordDisposition.RETRYABLE)
    operation = {
        "Put": {
            "Item": item,
            "ConditionExpression": (
                "entity_type=:entity AND schema_version=:schema "
                "AND object_version=:expected_object_version "
                "AND object_version<:next_object_version"
            ),
            "ExpressionAttributeValues": {
                ":entity": "billing_object_fact",
                ":schema": OBJECT_FACT_SCHEMA_VERSION,
                ":expected_object_version": current.fact_version,
                ":next_object_version": fact.fact_version,
            },
        }
    }
    try:
        _transact([operation], table=target)
    except Exception:
        try:
            replay = _strong_get(target, key)
        except Exception:
            return FactRecordResult(FactRecordDisposition.RETRYABLE)
        classified = _classify_fact_replay(replay, fact)
        if classified.disposition is FactRecordDisposition.DUPLICATE:
            return FactRecordResult(FactRecordDisposition.ADVANCED, fact=fact)
        return classified
    return FactRecordResult(
        FactRecordDisposition.ADVANCED,
        fact=fact,
        operations=(operation,),
    )


def load_activation_facts(
    command_id: str,
    *,
    table: object | None = None,
) -> tuple[BillingFact, ...]:
    """Strongly load the current independent object facts for one command."""
    partition = _command_partition(command_id)
    target = table or get_table()
    if not isinstance(target, _QueryTable):
        raise ValueError("billing fact query is unavailable")
    response = target.query(
        KeyConditionExpression="PK=:pk",
        ExpressionAttributeValues={":pk": partition},
        ConsistentRead=True,
    )
    if not isinstance(response, Mapping) or not isinstance(response.get("Items"), list):
        raise ValueError("billing fact query returned malformed data")
    facts = [
        billing_fact_from_item(item)
        for item in response["Items"]
        if isinstance(item, Mapping)
        and item.get("schema_version") == OBJECT_FACT_SCHEMA_VERSION
    ]
    return tuple(
        sorted(
            facts,
            key=lambda fact: (str(fact.kind), fact.provider_object_id_digest),
        )
    )


def _claim_from_item(item: Mapping[str, object]) -> ReconciliationClaim:
    if (
        item.get("entity_type") != "billing_reconciliation_lease"
        or item.get("schema_version") != RECONCILIATION_LEASE_SCHEMA_VERSION
    ):
        raise ValueError("reconciliation lease is malformed")
    return ReconciliationClaim(
        command_id=_required_text(item.get("command_id"), "command_id"),
        lease_owner=_required_text(item.get("lease_owner"), "lease_owner"),
        lease_generation=_positive_integer(
            item.get("lease_generation"), "lease_generation"
        ),
        lease_expires_at=_positive_integer(
            item.get("lease_expires_at"), "lease_expires_at", allow_zero=True
        ),
    )


def claim_fact_reconciliation(
    command_id: str,
    *,
    lease_owner: str,
    now_epoch: int,
    lease_seconds: int,
    now_iso: str,
    table: object | None = None,
) -> ReconciliationResult:
    """Acquire a short generation-fenced lease for missing-fact reconciliation."""
    command = _required_text(command_id, "command_id")
    owner = _required_text(lease_owner, "lease_owner")
    now = _positive_integer(now_epoch, "now_epoch", allow_zero=True)
    duration = _positive_integer(lease_seconds, "lease_seconds")
    if duration > _MAX_LEASE_SECONDS:
        raise ValueError("lease_seconds exceeds the bounded maximum")
    timestamp = _timestamp(now_iso, "now_iso")
    expiry = now + duration
    target = table or get_table()
    key = _lease_key(command)
    try:
        current = _strong_get(target, key)
    except Exception:
        return ReconciliationResult(ReconciliationDisposition.RETRYABLE)
    if current is None:
        item: BillingItem = {
            **key,
            "entity_type": "billing_reconciliation_lease",
            "schema_version": RECONCILIATION_LEASE_SCHEMA_VERSION,
            "command_id": command,
            "lease_owner": owner,
            "lease_generation": 1,
            "lease_expires_at": expiry,
            "updated_at": timestamp,
        }
        operation = _create_only(item)
        try:
            _transact([operation], table=target)
        except Exception:
            try:
                current = _strong_get(target, key)
            except Exception:
                return ReconciliationResult(ReconciliationDisposition.RETRYABLE)
            if current is None:
                return ReconciliationResult(ReconciliationDisposition.RETRYABLE)
            claim = _claim_from_item(current)
            disposition = (
                ReconciliationDisposition.CLAIMED
                if claim.lease_owner == owner
                else ReconciliationDisposition.LEASE_BUSY
            )
            return ReconciliationResult(disposition, claim=claim)
        return ReconciliationResult(
            ReconciliationDisposition.CLAIMED,
            claim=ReconciliationClaim(command, owner, 1, expiry),
            operations=(operation,),
        )

    try:
        current_claim = _claim_from_item(current)
    except ValueError:
        return ReconciliationResult(ReconciliationDisposition.RETRYABLE)
    if current_claim.lease_expires_at > now:
        return ReconciliationResult(
            ReconciliationDisposition.LEASE_BUSY,
            claim=current_claim,
        )
    next_generation = current_claim.lease_generation + 1
    operation = {
        "Update": {
            "Key": key,
            "UpdateExpression": (
                "SET lease_owner=:lease_owner, lease_generation=:next_generation, "
                "lease_expires_at=:lease_expires_at, updated_at=:updated_at"
            ),
            "ConditionExpression": (
                "entity_type=:entity AND schema_version=:schema "
                "AND lease_generation=:expected_generation "
                "AND lease_expires_at<=:now_epoch"
            ),
            "ExpressionAttributeValues": {
                ":entity": "billing_reconciliation_lease",
                ":schema": RECONCILIATION_LEASE_SCHEMA_VERSION,
                ":expected_generation": current_claim.lease_generation,
                ":now_epoch": now,
                ":lease_owner": owner,
                ":next_generation": next_generation,
                ":lease_expires_at": expiry,
                ":updated_at": timestamp,
            },
        }
    }
    try:
        _transact([operation], table=target)
    except Exception:
        try:
            replay = _strong_get(target, key)
        except Exception:
            return ReconciliationResult(ReconciliationDisposition.RETRYABLE)
        if replay is None:
            return ReconciliationResult(ReconciliationDisposition.RETRYABLE)
        claim = _claim_from_item(replay)
        disposition = (
            ReconciliationDisposition.CLAIMED
            if claim.lease_owner == owner and claim.lease_generation == next_generation
            else ReconciliationDisposition.LEASE_BUSY
        )
        return ReconciliationResult(disposition, claim=claim)
    return ReconciliationResult(
        ReconciliationDisposition.CLAIMED,
        claim=ReconciliationClaim(command, owner, next_generation, expiry),
        operations=(operation,),
    )


def _activation_request(request: PaidActivationRequest) -> PaidActivationRequest:
    if not isinstance(request, PaidActivationRequest):
        raise ValueError("PaidActivationRequest is required")
    _required_text(request.command_id, "command_id")
    _required_text(request.parent_id, "parent_id")
    _positive_integer(request.expected_command_version, "expected_command_version")
    _digest(request.provider_customer_id_digest, "provider_customer_id_digest")
    _required_text(request.price_id, "price_id")
    environment = _required_text(request.environment, "environment", maximum=32)
    if request.provider_livemode is not False or environment == "production":
        raise ValueError("paid activation requires a sandbox test-mode provider object")
    if not isinstance(request.plan_id, BillingPlanId) or request.plan_id is BillingPlanId.FREE_TRIAL:
        raise ValueError("plan_id is not a paid plan")
    _positive_integer(request.plan_version, "plan_version")
    _positive_integer(request.allowance_version, "allowance_version")
    _positive_integer(request.activation_version, "activation_version")
    _required_text(request.paid_invoice_fact_id, "paid_invoice_fact_id")
    _required_text(request.active_subscription_fact_id, "active_subscription_fact_id")
    _timestamp(request.activated_at, "activated_at")
    return request


def _activation_item(
    value: Mapping[str, object],
    *,
    entity_type: str,
    request: PaidActivationRequest,
) -> BillingItem:
    item = _mapping(value)
    if item is None:
        raise ValueError(f"{entity_type} item is required")
    _required_text(item.get("PK"), "PK")
    _required_text(item.get("SK"), "SK")
    required = {
        "entity_type": entity_type,
        "parent_id": request.parent_id,
        "plan_id": str(request.plan_id),
        "plan_version": request.plan_version,
        "allowance_version": request.allowance_version,
        "activation_version": request.activation_version,
    }
    if any(item.get(field) != expected for field, expected in required.items()):
        raise ValueError(f"{entity_type} item does not match the activation")
    return item


def _receipt_matches(item: Mapping[str, object], request: PaidActivationRequest) -> bool:
    return (
        item.get("schema_version") == ACTIVATION_RECEIPT_SCHEMA_VERSION
        and item.get("command_id") == request.command_id
        and item.get("parent_id") == request.parent_id
        and item.get("activation_version") == request.activation_version
        and item.get("paid_invoice_fact_id") == request.paid_invoice_fact_id
        and item.get("active_subscription_fact_id")
        == request.active_subscription_fact_id
    )


def _command_matches(item: Mapping[str, object], request: PaidActivationRequest) -> bool:
    return (
        item.get("command_id") == request.command_id
        and item.get("parent_id") == request.parent_id
        and item.get("command_version") == request.expected_command_version
        and item.get("provider_customer_id_digest")
        == request.provider_customer_id_digest
        and item.get("price_id") == request.price_id
        and item.get("environment") == request.environment
        and item.get("plan_id") == str(request.plan_id)
        and item.get("plan_version") == request.plan_version
    )


def commit_paid_activation(
    request: PaidActivationRequest,
    *,
    billing_projection: Mapping[str, object],
    grant_items: Sequence[Mapping[str, object]],
    allowance_item: Mapping[str, object],
    grant_operations: Sequence[Mapping[str, object]] = (),
    table: object | None = None,
) -> ActivationResult:
    """Conditionally publish command, billing, grants, allowance, and one receipt."""
    activation = _activation_request(request)
    target = table or get_table()
    projection = _activation_item(
        billing_projection,
        entity_type="billing_projection",
        request=activation,
    )
    if not isinstance(grant_items, Sequence) or isinstance(grant_items, (str, bytes)):
        raise ValueError("grant_items are invalid")
    if not 1 <= len(grant_items) <= 3:
        raise ValueError("grant_items must contain one to three explicit grants")
    grants = [
        _activation_item(
            grant,
            entity_type="beneficiary_grant",
            request=activation,
        )
        for grant in grant_items
    ]
    beneficiaries = [
        _required_text(grant.get("beneficiary_id"), "beneficiary_id")
        for grant in grants
    ]
    if len(set(beneficiaries)) != len(beneficiaries):
        raise ValueError("beneficiary grant identities must be unique")
    if not isinstance(grant_operations, Sequence) or isinstance(
        grant_operations, (str, bytes)
    ):
        raise ValueError("grant_operations are invalid")
    relationship_operations: list[dict[str, Any]] = []
    for operation in grant_operations:
        normalized = _mapping(operation)
        if normalized is None or set(normalized) != {"ConditionCheck"}:
            raise ValueError("grant_operations must contain only condition checks")
        condition = _mapping(normalized.get("ConditionCheck"))
        key = _mapping((condition or {}).get("Key"))
        if (
            condition is None
            or key is None
            or not isinstance(key.get("PK"), str)
            or not isinstance(key.get("SK"), str)
            or not isinstance(condition.get("ConditionExpression"), str)
        ):
            raise ValueError("grant condition check is invalid")
        relationship_operations.append(normalized)
    allowance = _activation_item(
        allowance_item,
        entity_type="allowance_plan",
        request=activation,
    )

    facts = load_activation_facts(activation.command_id, table=target)
    invoice = next(
        (
            fact
            for fact in facts
            if fact.kind is BillingFactKind.INVOICE_PAID
            and fact.fact_id == activation.paid_invoice_fact_id
        ),
        None,
    )
    subscription = next(
        (
            fact
            for fact in facts
            if fact.kind is BillingFactKind.SUBSCRIPTION_ACTIVE
            and fact.fact_id == activation.active_subscription_fact_id
        ),
        None,
    )
    if invoice is None or subscription is None:
        return ActivationResult(ActivationDisposition.CONFLICT)

    receipt_key = _receipt_key(
        activation.command_id, activation.activation_version
    )
    receipt: BillingItem = {
        **receipt_key,
        "entity_type": "billing_activation_receipt",
        "schema_version": ACTIVATION_RECEIPT_SCHEMA_VERSION,
        "command_id": activation.command_id,
        "parent_id": activation.parent_id,
        "activation_version": activation.activation_version,
        "plan_id": activation.plan_id,
        "plan_version": activation.plan_version,
        "allowance_version": activation.allowance_version,
        "paid_invoice_fact_id": activation.paid_invoice_fact_id,
        "active_subscription_fact_id": activation.active_subscription_fact_id,
        "fact_observed_at": activation.activated_at,
        "processing_result": ActivationDisposition.COMMITTED,
    }
    try:
        prior_receipt = _strong_get(target, receipt_key)
    except Exception:
        return ActivationResult(ActivationDisposition.RETRYABLE)
    if prior_receipt is not None:
        disposition = (
            ActivationDisposition.ALREADY_COMMITTED
            if _receipt_matches(prior_receipt, activation)
            else ActivationDisposition.CONFLICT
        )
        return ActivationResult(disposition, receipt=prior_receipt)

    command_operation = {
        "Update": {
            "Key": _command_key(activation.command_id),
            "UpdateExpression": (
                "SET command_state=:activation_recorded, "
                "command_version=:next_command_version, "
                "activation_version=:activation_version, "
                "paid_invoice_fact_id=:paid_invoice_fact_id, "
                "active_subscription_fact_id=:active_subscription_fact_id, "
                "allowance_version=:allowance_version, updated_at=:activated_at"
            ),
            "ConditionExpression": (
                "entity_type=:command_entity AND command_id=:command_id "
                "AND parent_id=:parent_id "
                "AND command_version=:expected_command_version "
                "AND provider_customer_id_digest=:provider_customer_id_digest "
                "AND price_id=:price_id AND environment=:environment "
                "AND plan_id=:plan_id AND plan_version=:plan_version "
                "AND command_state<>:activation_recorded"
            ),
            "ExpressionAttributeValues": {
                ":command_entity": "checkout_command",
                ":command_id": activation.command_id,
                ":parent_id": activation.parent_id,
                ":expected_command_version": activation.expected_command_version,
                ":provider_customer_id_digest": activation.provider_customer_id_digest,
                ":price_id": activation.price_id,
                ":environment": activation.environment,
                ":plan_id": str(activation.plan_id),
                ":plan_version": activation.plan_version,
                ":activation_recorded": "activation_recorded",
                ":next_command_version": activation.expected_command_version + 1,
                ":activation_version": activation.activation_version,
                ":paid_invoice_fact_id": activation.paid_invoice_fact_id,
                ":active_subscription_fact_id": activation.active_subscription_fact_id,
                ":allowance_version": activation.allowance_version,
                ":activated_at": activation.activated_at,
            },
        }
    }
    projected_items = [projection, *grants, allowance]
    projection_operations: list[dict[str, Any]] = [
        {
            "Put": {
                "Item": item,
                "ConditionExpression": (
                    "attribute_not_exists(PK) OR activation_version<:activation_version"
                ),
                "ExpressionAttributeValues": {
                    ":activation_version": activation.activation_version
                },
            }
        }
        for item in projected_items
    ]
    receipt_operation = _create_only(receipt)
    operations: list[dict[str, Any]] = [
        command_operation,
        *relationship_operations,
        *projection_operations,
        receipt_operation,
    ]
    targets: list[tuple[str, str]] = []
    for operation in operations:
        body = _mapping(
            operation.get("Update")
            or operation.get("Put")
            or operation.get("ConditionCheck")
        )
        key = _mapping((body or {}).get("Key"))
        item = _mapping((body or {}).get("Item"))
        target_item = key or item
        if (
            target_item is None
            or not isinstance(target_item.get("PK"), str)
            or not isinstance(target_item.get("SK"), str)
        ):
            raise ValueError("activation transaction target is invalid")
        targets.append((str(target_item["PK"]), str(target_item["SK"])))
    if len(targets) != len(set(targets)):
        raise ValueError("activation transaction item targets must be unique")

    try:
        _transact(operations, table=target)
    except Exception:
        try:
            replay_receipt = _strong_get(target, receipt_key)
            command = _strong_get(target, _command_key(activation.command_id))
        except Exception:
            return ActivationResult(ActivationDisposition.RETRYABLE)
        if replay_receipt is not None and _receipt_matches(
            replay_receipt, activation
        ):
            return ActivationResult(
                ActivationDisposition.ALREADY_COMMITTED,
                receipt=replay_receipt,
            )
        if command is not None and not _command_matches(command, activation):
            return ActivationResult(ActivationDisposition.CONFLICT)
        return ActivationResult(ActivationDisposition.RETRYABLE)
    return ActivationResult(
        ActivationDisposition.COMMITTED,
        receipt=receipt,
        operations=tuple(operations),
    )


__all__ = [
    "ActivationDisposition",
    "ActivationResult",
    "BillingEventDisposition",
    "BillingEventResult",
    "FactRecordDisposition",
    "FactRecordResult",
    "PaidActivationRequest",
    "ReconciliationClaim",
    "ReconciliationDisposition",
    "ReconciliationResult",
    "billing_fact_from_item",
    "claim_fact_reconciliation",
    "commit_paid_activation",
    "load_activation_facts",
    "record_provider_fact",
    "register_provider_event",
]
