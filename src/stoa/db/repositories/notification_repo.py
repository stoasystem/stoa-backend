"""Owner-fenced notification, assistance, device, and delivery persistence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4

from boto3.dynamodb.conditions import Attr, ConditionBase
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


NOTIFICATION_ENTITY = "notification_event"
SUMMARY_SEED_ENTITY = "teacher_assistance_summary_seed"
PREFERENCE_ENTITY = "notification_preference"
PUSH_TOKEN_ENTITY = "notification_push_token"
DELIVERY_INTENT_ENTITY = "notification_delivery_intent"
GLOBAL_NONPRIVATE_CONTRACT_ID = "stoa-global-nonprivate.v1"
GLOBAL_NONPRIVATE_DELIVERY_CONTRACTS = {
    GLOBAL_NONPRIVATE_CONTRACT_ID: {
        "event_types": frozenset(
            {"moderation_case_update", "subscription_request_update"}
        ),
        "target_types": frozenset({"system_status"}),
        "metadata_keys": frozenset(),
    }
}

NOTIFICATION_PRIVATE_ROW_REGISTRY = frozenset(
    {
        NOTIFICATION_ENTITY,
        SUMMARY_SEED_ENTITY,
        PREFERENCE_ENTITY,
        PUSH_TOKEN_ENTITY,
        DELIVERY_INTENT_ENTITY,
    }
)
NOTIFICATION_IDENTITY_REFERENCE_REGISTRY = {
    NOTIFICATION_ENTITY: {
        "scalar_fields": frozenset({"actor_id"}),
        "metadata_fields": frozenset({"actor_id", "teacher_id", "parent_id"}),
    }
}
NOTIFICATION_WRITER_REGISTRY = frozenset(
    {
        "put_event",
        "update_event",
        "put_summary_seed",
        "put_preferences",
        "put_push_token",
        "update_push_token",
        "register_delivery_intent",
        "claim_delivery_intent",
        "begin_delivery_effect",
        "recover_delivery_intent",
        "cancel_delivery_intent",
        "complete_delivery_intent",
    }
)
NOTIFICATION_PRIVATE_FIELDS = frozenset(
    {
        "recipient_id",
        "recipient_role",
        "actor_id",
        "actor_role",
        "event_type",
        "target_type",
        "target_id",
        "title",
        "summary",
        "metadata",
        "category",
        "question_id",
        "student_id",
        "subject",
        "student_context_summary",
        "question_summary",
        "ai_answer_summary",
        "weak_topics",
        "suggested_focus",
        "source_count",
        "created_by",
        "preferences",
        "role",
        "platform",
        "token_reference",
        "token_hash",
        "provider_token_reference",
        "device_id_hash",
        "event_ids",
        "payload_digest",
        "lease_owner",
        "lease_expires_at",
        "endpoint_url",
        "subscribed_channels",
    }
)
NOTIFICATION_TOMBSTONE_ALLOWLIST = frozenset(
    {
        "PK",
        "SK",
        "entity_type",
        "schema_version",
        "status",
        "event_id",
        "summary_id",
        "operation_id",
        "channel",
        "created_at",
        "accepted_at",
        "updated_at",
        "deleted_at",
        "owner_deletion_generation",
    }
)
EXTERNAL_DELIVERY_RETENTION_BOUNDARY = {
    "provider_accepted_or_unknown": "outside_backend_deletion_control"
}
_EXTERNAL_RECEIPT_STATES = frozenset({"accepted", "provider_acceptance_unknown"})


type NotificationItem = dict[str, object]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _SupportsInt(Protocol):
    def __int__(self) -> int: ...


def _dependency_mapping(value: object) -> NotificationItem:
    if not isinstance(value, Mapping):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed notification dependency response"
        )
    result: NotificationItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise account_deletion_repo.AccountDeletionConflict(
                "malformed notification dependency response"
            )
        result[key] = member
    return result


def _optional_item(value: object) -> NotificationItem | None:
    if value is None:
        return None
    return _dependency_mapping(value)


def _response_items(response: Mapping[str, object]) -> list[NotificationItem]:
    raw_items = response.get("Items", [])
    if not isinstance(raw_items, list):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed notification dependency response"
        )
    return [_dependency_mapping(item) for item in raw_items]


def _get_item(table: object, **kwargs: object) -> NotificationItem:
    if not isinstance(table, _GetTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification dependency unavailable"
        )
    return _dependency_mapping(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification dependency unavailable"
        )
    return table.put_item(**kwargs)


def _scan(table: object, **kwargs: object) -> NotificationItem:
    if not isinstance(table, _ScanTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification dependency unavailable"
        )
    return _dependency_mapping(table.scan(**kwargs))


def _update_item(table: object, **kwargs: object) -> NotificationItem:
    if not isinstance(table, _UpdateTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification dependency unavailable"
        )
    return _dependency_mapping(table.update_item(**kwargs))


def _required_text(
    item: Mapping[str, object], field: str, error_message: str
) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise account_deletion_repo.AccountDeletionConflict(error_message)
    return value


def _positive_integer(
    item: Mapping[str, object], field: str, error_message: str
) -> int:
    value = item.get(field)
    if not isinstance(value, (str, bytes, bytearray, _SupportsInt)):
        raise account_deletion_repo.AccountDeletionConflict(error_message)
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise account_deletion_repo.AccountDeletionConflict(error_message) from exc
    if result <= 0:
        raise account_deletion_repo.AccountDeletionConflict(error_message)
    return result


@dataclass(frozen=True, slots=True)
class NotificationPrivatePage:
    items: tuple[NotificationItem, ...]
    cursor: dict[str, str] | None = None
    scanned: int = 0


@dataclass(frozen=True, slots=True)
class DeliveryIntentScope:
    """Validated delivery classification used to bind one logical effect."""

    kind: str
    digest: str
    owner_id: str | None = None
    generation: int | None = None
    classification_seal: str | None = None

    @classmethod
    def private_owner(cls, *, owner_id: str, generation: int) -> DeliveryIntentScope:
        owner = str(owner_id).strip()
        if not owner or type(generation) is not int or generation <= 0:
            raise account_deletion_repo.AccountDeletionConflict(
                "private delivery scope is invalid"
            )
        facts = {"kind": "private_owner", "owner_id": owner, "generation": generation}
        return cls(
            kind="private_owner",
            digest=_delivery_digest(facts),
            owner_id=owner,
            generation=generation,
        )

    @classmethod
    def global_nonprivate(
        cls, *, classification_seal: str
    ) -> DeliveryIntentScope:
        seal = str(classification_seal).strip()
        if not seal:
            raise account_deletion_repo.AccountDeletionConflict(
                "global delivery classification seal is required"
            )
        facts = {"kind": "global_nonprivate", "classification_seal": seal}
        return cls(
            kind="global_nonprivate",
            digest=_delivery_digest(facts),
            classification_seal=seal,
        )


@dataclass(frozen=True, slots=True)
class DeliveryIntentClaim:
    """Opaque exact-version authority for one delivery-intent transition."""

    operation_id: str
    lease_owner: str
    intent_version: int
    lease_expires_at: int
    scope_digest: str
    payload_digest: str


class DeliveryBeginDisposition(StrEnum):
    """Closed outcomes from the final pre-provider delivery transition."""

    BEGUN = "begun"
    CLAIM_LOST = "claim_lost"
    PROVEN_ACCOUNT_DELETED = "proven_account_deleted"
    DEPENDENCY_RETRY = "dependency_retry"


@dataclass(frozen=True, slots=True)
class DeliveryBeginResult:
    """Provider-neutral result of attempting the final delivery CAS."""

    disposition: DeliveryBeginDisposition
    claim: DeliveryIntentClaim | None = None


_DELIVERY_TERMINAL_STATES = frozenset(
    {"accepted", "provider_acceptance_unknown", "canceled_account_deletion"}
)


def _delivery_digest(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _delivery_scope(
    scope: DeliveryIntentScope | None,
    *,
    owner_id: str | None = None,
    generation: int | None = None,
) -> DeliveryIntentScope:
    if isinstance(scope, DeliveryIntentScope):
        return scope
    if owner_id is not None and generation is not None:
        return DeliveryIntentScope.private_owner(
            owner_id=owner_id, generation=generation
        )
    raise account_deletion_repo.AccountDeletionConflict("delivery scope is required")


def _delivery_key(scope: DeliveryIntentScope, operation_id: str) -> dict[str, str]:
    operation = str(operation_id).strip()
    if not operation:
        raise account_deletion_repo.AccountDeletionConflict(
            "delivery operation is required"
        )
    partition = (
        scope.owner_id if scope.kind == "private_owner" else "GLOBAL_NONPRIVATE"
    )
    return {"PK": delivery_intent_pk(str(partition)), "SK": delivery_intent_sk(operation)}


def _delivery_identity_matches(
    item: Mapping[str, object],
    *,
    scope: DeliveryIntentScope,
    operation_id: str,
    payload_digest: str,
) -> bool:
    return bool(
        item.get("operation_id") == operation_id
        and item.get("scope_kind") == scope.kind
        and item.get("scope_digest") == scope.digest
        and item.get("payload_digest") == payload_digest
        and (
            scope.kind != "private_owner"
            or (
                item.get("owner_id") == scope.owner_id
                and item.get("account_fence_generation") == scope.generation
            )
        )
        and (
            scope.kind != "global_nonprivate"
            or item.get("classification_seal") == scope.classification_seal
        )
    )


def _intent_claim(item: Mapping[str, object]) -> DeliveryIntentClaim:
    claim = DeliveryIntentClaim(
        operation_id=_required_text(
            item, "operation_id", "delivery claim is malformed"
        ),
        lease_owner=_required_text(item, "lease_owner", "delivery claim is malformed"),
        intent_version=_positive_integer(
            item, "intent_version", "delivery claim is malformed"
        ),
        lease_expires_at=_positive_integer(
            item, "lease_expires_at", "delivery claim is malformed"
        ),
        scope_digest=_required_text(
            item, "scope_digest", "delivery claim is malformed"
        ),
        payload_digest=_required_text(
            item, "payload_digest", "delivery claim is malformed"
        ),
    )
    if (
        not claim.operation_id
        or not claim.lease_owner
        or claim.intent_version <= 0
        or claim.lease_expires_at <= 0
        or len(claim.scope_digest) != 64
        or len(claim.payload_digest) != 64
    ):
        raise account_deletion_repo.AccountDeletionConflict(
            "delivery claim is malformed"
        )
    return claim


def _delivery_conditional_loss(exc: Exception) -> bool:
    if isinstance(exc, account_deletion_repo.AccountDeletionConflict):
        return True
    if not isinstance(exc, ClientError):
        return False
    return str(exc.response.get("Error", {}).get("Code") or "") in {
        "ConditionalCheckFailedException",
        "TransactionCanceledException",
    }


def _delivery_client_error(exc: Exception) -> ClientError | None:
    """Return a wrapped provider error without trusting exception messages."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ClientError):
            return current
        current = current.__cause__ or current.__context__
    return None


def _strong_delivery_intent(
    *, scope: DeliveryIntentScope, claim: DeliveryIntentClaim, table: object
) -> NotificationItem | None:
    response = _get_item(
        table,
        Key=_delivery_key(scope, claim.operation_id),
        ConsistentRead=True,
    )
    return _optional_item(response.get("Item"))


def _begun_claim_from_intent(
    item: Mapping[str, object] | None,
    *,
    scope: DeliveryIntentScope,
    claim: DeliveryIntentClaim,
) -> DeliveryIntentClaim | None:
    if (
        item is None
        or not _delivery_identity_matches(
            item,
            scope=scope,
            operation_id=claim.operation_id,
            payload_digest=claim.payload_digest,
        )
        or item.get("effect_state") != "effect_inflight"
        or item.get("lease_owner") != claim.lease_owner
        or item.get("intent_version") != claim.intent_version + 1
    ):
        return None
    try:
        return _intent_claim(item)
    except account_deletion_repo.AccountDeletionConflict:
        return None


def classify_delivery_transaction_failure(
    exc: Exception,
    *,
    scope: DeliveryIntentScope,
    claim: DeliveryIntentClaim,
    operation_count: int,
    fence_operation_index: int | None,
    intent_operation_index: int,
    table: object | None = None,
) -> DeliveryBeginResult:
    """Classify a failed begin using ordered reasons and authoritative strong reads.

    A transaction/provider exception is never itself evidence of account deletion.
    The deletion outcome requires both an exact fence-condition cancellation reason
    and a strong read of the permanent fence in a deletion state.
    """
    target = table or get_table()
    try:
        intent = _strong_delivery_intent(scope=scope, claim=claim, table=target)
    except Exception:
        return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)

    begun_claim = _begun_claim_from_intent(intent, scope=scope, claim=claim)
    if begun_claim is not None:
        return DeliveryBeginResult(DeliveryBeginDisposition.BEGUN, begun_claim)

    provider_error = _delivery_client_error(exc)
    if provider_error is None:
        return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)
    error_code = str(provider_error.response.get("Error", {}).get("Code") or "")
    if error_code != "TransactionCanceledException":
        return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)
    reasons = provider_error.response.get("CancellationReasons")
    if not isinstance(reasons, list) or len(reasons) != operation_count:
        return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)

    conditional_indexes: list[int] = []
    for index, reason in enumerate(reasons):
        if not isinstance(reason, Mapping):
            return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)
        code = reason.get("Code")
        if not isinstance(code, str):
            return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)
        if code == "None":
            continue
        if code == "ConditionalCheckFailed":
            conditional_indexes.append(index)
            continue
        return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)

    if fence_operation_index is not None and fence_operation_index in conditional_indexes:
        if scope.kind != "private_owner":
            return DeliveryBeginResult(DeliveryBeginDisposition.CLAIM_LOST)
        try:
            fence = account_deletion_repo.get_account_fence(
                str(scope.owner_id), table=target
            )
        except Exception:
            return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)
        if (
            fence is not None
            and fence.get("user_id") == scope.owner_id
            and fence.get("generation") == scope.generation
            and fence.get("status") in {"deletion_pending", "deleted"}
        ):
            return DeliveryBeginResult(
                DeliveryBeginDisposition.PROVEN_ACCOUNT_DELETED
            )
        if fence is None or fence.get("status") != "active":
            return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)

    if intent_operation_index in conditional_indexes:
        return DeliveryBeginResult(DeliveryBeginDisposition.CLAIM_LOST)
    if any(
        index not in {fence_operation_index, intent_operation_index}
        for index in conditional_indexes
    ):
        return DeliveryBeginResult(DeliveryBeginDisposition.CLAIM_LOST)
    return DeliveryBeginResult(DeliveryBeginDisposition.DEPENDENCY_RETRY)


def notification_pk(event_id: str) -> str:
    return f"NOTIFICATION#{event_id}"


def preference_pk(user_id: str) -> str:
    return f"NOTIFICATION_PREF#{user_id}"


def push_token_pk(user_id: str, token_reference: str) -> str:
    return f"NOTIFICATION_PUSH_TOKEN#{user_id}#{token_reference}"


def summary_seed_pk(summary_id: str) -> str:
    return f"ASSISTANCE_SUMMARY#{summary_id}"


def delivery_intent_pk(owner_id: str) -> str:
    return f"NOTIFICATION_DELIVERY#{owner_id}"


def delivery_intent_sk(operation_id: str) -> str:
    return f"INTENT#{operation_id}"


def build_notification_write_transaction(
    *,
    item: Mapping[str, object],
    owner_id: str,
    generation: int,
    mode: str = "put",
    updates: Mapping[str, object] | None = None,
) -> list[NotificationItem]:
    """Build one owner-bound write behind the canonical permanent fence."""
    if not owner_id or type(generation) is not int or generation <= 0:
        raise account_deletion_repo.AccountDeletionConflict("notification owner is invalid")
    stored = {
        **dict(item),
        "owner_id": owner_id,
        "account_fence_generation": generation,
    }
    operations = [account_deletion_repo.active_fence_condition(owner_id, generation)]
    if mode == "put":
        operations.append(
            {
                "Put": {
                    "Item": stored,
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            }
        )
        return operations
    if mode != "update" or not updates:
        raise ValueError("notification write mode is invalid")
    names = {f"#{key}": key for key in updates}
    values = {f":{key}": value for key, value in updates.items()}
    values[":owner"] = owner_id
    operations.append(
        {
            "Update": {
                "Key": {"PK": stored["PK"], "SK": stored["SK"]},
                "UpdateExpression": "SET "
                + ", ".join(f"#{key}=:{key}" for key in updates),
                "ConditionExpression": (
                    "attribute_exists(PK) AND attribute_exists(SK) AND owner_id=:owner"
                ),
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        }
    )
    return operations


def _generation(owner_id: str, generation: object, table: object) -> int:
    if type(generation) is int and generation > 0:
        return generation
    atomic = callable(getattr(table, "transact_account_deletion", None)) or bool(
        getattr(getattr(table, "meta", None), "client", None)
        and getattr(table, "name", None)
    )
    if atomic:
        return int(account_deletion_repo.require_active_account_fence(owner_id, table=table)["generation"])
    # Lightweight unit fakes cannot model the permanent fence; transaction
    # builders and real table paths always require the authoritative value.
    return 1


def _persist_private(
    item: NotificationItem,
    *,
    mode: str = "put",
    updates: Mapping[str, object] | None = None,
) -> NotificationItem:
    target = get_table()
    owner_id = str(item.get("owner_id") or item.get("student_id") or item.get("user_id") or "")
    if not owner_id:
        raise account_deletion_repo.AccountDeletionConflict("notification owner is required")
    generation = _generation(owner_id, item.get("account_fence_generation"), target)
    stored = {**item, "owner_id": owner_id, "account_fence_generation": generation}
    account_deletion_repo.transact(
        build_notification_write_transaction(
            item=stored,
            owner_id=owner_id,
            generation=generation,
            mode=mode,
            updates=updates,
        ),
        table=target,
    )
    return stored


def put_event(item: NotificationItem) -> NotificationItem:
    event_id = _required_text(item, "event_id", "notification identity is invalid")
    stored = {**item, "PK": notification_pk(event_id), "SK": "META"}
    if stored.get("owner_classification") == "global_nonprivate":
        stored = seal_global_nonprivate_event(stored)
        target = get_table()
        _put_item(
            target,
            Item=stored,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        return stored
    return _persist_private(stored)


def get_event(event_id: str) -> NotificationItem | None:
    response = _get_item(
        get_table(), Key={"PK": notification_pk(event_id), "SK": "META"}
    )
    return _optional_item(response.get("Item"))


def load_delivery_event_strong(
    event_id: str, *, table: object | None = None
) -> NotificationItem | None:
    """Load the canonical event row by base key for provider delivery."""
    canonical_id = str(event_id).strip()
    if not canonical_id:
        return None
    target = table or get_table()
    response = _get_item(
        target,
        Key={"PK": notification_pk(canonical_id), "SK": "META"},
        ConsistentRead=True,
    )
    item = _optional_item(response.get("Item"))
    if item is None:
        return None
    if (
        item.get("PK") != notification_pk(canonical_id)
        or item.get("SK") != "META"
        or item.get("entity_type") != NOTIFICATION_ENTITY
        or item.get("event_id") != canonical_id
    ):
        return None
    return dict(item)


def _global_classification_facts(item: Mapping[str, object]) -> NotificationItem:
    return {
        "classification_contract": item.get("classification_contract"),
        "event_id": item.get("event_id"),
        "event_version": item.get("event_version"),
        "event_type": item.get("event_type"),
        "target_type": item.get("target_type"),
        "target_id": item.get("target_id"),
        "title": item.get("title"),
        "summary": item.get("summary"),
        "recipient_role": item.get("recipient_role"),
        "category": item.get("category"),
        "created_at": item.get("created_at"),
        "metadata": item.get("metadata"),
    }


def seal_global_nonprivate_event(item: Mapping[str, object]) -> NotificationItem:
    """Persist an exact content seal for one allowlisted ownerless event."""
    stored = dict(item)
    stored["owner_classification"] = "global_nonprivate"
    stored["classification_contract"] = GLOBAL_NONPRIVATE_CONTRACT_ID
    if not validate_global_nonprivate_event(stored, require_digest=False):
        raise account_deletion_repo.AccountDeletionConflict(
            "global delivery classification is invalid"
        )
    stored["classification_digest"] = _delivery_digest(
        _global_classification_facts(stored)
    )
    return stored


def validate_global_nonprivate_event(
    item: Mapping[str, object], *, require_digest: bool = True
) -> bool:
    contract_id = item.get("classification_contract")
    contract = GLOBAL_NONPRIVATE_DELIVERY_CONTRACTS.get(str(contract_id or ""))
    version = item.get("event_version")
    metadata = item.get("metadata")
    if (
        contract is None
        or item.get("owner_classification") != "global_nonprivate"
        or type(version) is not int
        or version <= 0
        or item.get("event_type") not in contract["event_types"]
        or item.get("target_type") not in contract["target_types"]
        or not isinstance(item.get("event_id"), str)
        or not str(item.get("event_id") or "").strip()
        or not isinstance(item.get("target_id"), str)
        or not str(item.get("target_id") or "").strip()
        or not isinstance(item.get("title"), str)
        or not isinstance(item.get("summary"), str)
        or not isinstance(metadata, Mapping)
        or set(metadata) - set(contract["metadata_keys"])
    ):
        return False
    if any(
        item.get(field) not in {None, ""}
        for field in (
            "owner_id",
            "account_fence_generation",
            "recipient_id",
            "actor_id",
            "actor_role",
        )
    ):
        return False
    if not require_digest:
        return True
    digest = item.get("classification_digest")
    return bool(
        isinstance(digest, str)
        and len(digest) == 64
        and digest == _delivery_digest(_global_classification_facts(item))
    )


def update_event(
    event_id: str, updates: NotificationItem
) -> NotificationItem | None:
    existing = get_event(event_id)
    if not existing:
        return None
    if existing.get("owner_classification") == "global_nonprivate":
        raise account_deletion_repo.AccountDeletionConflict(
            "global delivery event is immutable"
        )
    if not updates:
        return existing
    _persist_private(existing, mode="update", updates=updates)
    return {**existing, **updates}


def list_events(limit: int = 100) -> list[NotificationItem]:
    response = _scan(
        get_table(),
        FilterExpression=Attr("entity_type").eq(NOTIFICATION_ENTITY), Limit=limit
    )
    return _response_items(response)


def put_preferences(item: NotificationItem) -> NotificationItem:
    user_id = _required_text(item, "user_id", "notification identity is invalid")
    stored = {**item, "PK": preference_pk(user_id), "SK": "META"}
    existing = get_preferences(user_id)
    if existing:
        values = {key: value for key, value in stored.items() if key not in {"PK", "SK"}}
        return {**existing, **values} if _persist_private(existing, mode="update", updates=values) else stored
    return _persist_private(stored)


def get_preferences(user_id: str) -> NotificationItem | None:
    response = _get_item(
        get_table(), Key={"PK": preference_pk(user_id), "SK": "META"}
    )
    return _optional_item(response.get("Item"))


def put_push_token(item: NotificationItem) -> NotificationItem:
    user_id = _required_text(item, "user_id", "notification identity is invalid")
    token_reference = _required_text(
        item, "token_reference", "notification identity is invalid"
    )
    stored = {
        **item,
        "PK": push_token_pk(user_id, token_reference),
        "SK": "META",
    }
    existing = get_push_token(user_id, token_reference)
    if existing:
        updates = {key: value for key, value in stored.items() if key not in {"PK", "SK"}}
        _persist_private(existing, mode="update", updates=updates)
        return {**existing, **updates}
    return _persist_private(stored)


def get_push_token(user_id: str, token_reference: str) -> NotificationItem | None:
    response = _get_item(
        get_table(),
        Key={"PK": push_token_pk(user_id, token_reference), "SK": "META"}
    )
    return _optional_item(response.get("Item"))


def list_push_tokens(
    user_id: str | None = None, *, status: str | None = None, limit: int = 100
) -> list[NotificationItem]:
    filters = [Attr("entity_type").eq(PUSH_TOKEN_ENTITY)]
    if user_id is not None:
        filters.append(Attr("user_id").eq(user_id))
    if status is not None:
        filters.append(Attr("status").eq(status))
    expression: ConditionBase = filters[0]
    for filter_expression in filters[1:]:
        expression = expression & filter_expression
    response = _scan(get_table(), FilterExpression=expression, Limit=limit)
    return _response_items(response)


def update_push_token(
    user_id: str, token_reference: str, updates: NotificationItem
) -> NotificationItem | None:
    existing = get_push_token(user_id, token_reference)
    if not existing:
        return None
    if updates:
        _persist_private(existing, mode="update", updates=updates)
    return {**existing, **updates}


def put_summary_seed(item: NotificationItem) -> NotificationItem:
    summary_id = _required_text(
        item, "summary_id", "notification identity is invalid"
    )
    stored = {**item, "PK": summary_seed_pk(summary_id), "SK": "META"}
    return _persist_private(stored)


def register_delivery_intent(
    *,
    scope: DeliveryIntentScope | None = None,
    owner_id: str | None = None,
    generation: int | None = None,
    operation_id: str,
    channel: str,
    event_ids: list[str],
    payload_digest: str,
    now_iso: str,
    table: object | None = None,
) -> NotificationItem:
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    target = table or get_table()
    key = _delivery_key(scope, operation_id)
    existing = _optional_item(
        _get_item(target, Key=key, ConsistentRead=True).get("Item")
    )
    if existing:
        if not _delivery_identity_matches(
            existing,
            scope=scope,
            operation_id=operation_id,
            payload_digest=payload_digest,
        ) or existing.get("channel") != channel or existing.get("event_ids") != event_ids:
            raise account_deletion_repo.AccountDeletionConflict("delivery intent identity changed")
        return dict(existing)
    item: NotificationItem = {
        **key,
        "entity_type": DELIVERY_INTENT_ENTITY,
        "schema_version": "notification-delivery-intent.v2",
        "operation_id": operation_id,
        "scope_kind": scope.kind,
        "scope_digest": scope.digest,
        "channel": channel,
        "event_ids": list(event_ids),
        "payload_digest": payload_digest,
        "intent_version": 1,
        "effect_state": "registered",
        "status": "registered",
        "outcome_status": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    if scope.kind == "private_owner":
        item.update(
            owner_id=scope.owner_id,
            account_fence_generation=scope.generation,
        )
    else:
        item["classification_seal"] = scope.classification_seal
    hook = getattr(target, "register_delivery_intent", None)
    if callable(hook):
        persisted = hook(item)
        return item if not persisted else _dependency_mapping(persisted)
    if scope.kind == "private_owner":
        account_deletion_repo.transact(
            build_notification_write_transaction(
                item=item,
                owner_id=str(scope.owner_id),
                generation=int(scope.generation or 0),
                mode="put",
            ),
            table=target,
        )
    else:
        _put_item(
            target,
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    return item


def claim_delivery_intent(
    *,
    scope: DeliveryIntentScope | None = None,
    owner_id: str | None = None,
    generation: int | None = None,
    operation_id: str,
    payload_digest: str | None = None,
    now_epoch: int | None = None,
    lease_expires_at: int,
    lease_owner: str | None = None,
    now_iso: str | None = None,
    table: object | None = None,
) -> DeliveryIntentClaim | None:
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    target = table or get_table()
    key = _delivery_key(scope, operation_id)
    current = _optional_item(
        _get_item(target, Key=key, ConsistentRead=True).get("Item")
    )
    if current is None:
        return None
    digest = str(payload_digest or current.get("payload_digest") or "")
    if not _delivery_identity_matches(
        current,
        scope=scope,
        operation_id=operation_id,
        payload_digest=digest,
    ):
        raise account_deletion_repo.AccountDeletionConflict("delivery intent identity changed")
    if type(now_epoch) is not int:
        from time import time

        now_epoch = int(time())
    if now_epoch < 0 or type(lease_expires_at) is not int or lease_expires_at <= now_epoch:
        raise account_deletion_repo.AccountDeletionConflict("delivery lease time is invalid")
    opaque_owner = str(lease_owner or f"delivery-lease-{uuid4().hex}").strip()
    if not opaque_owner:
        raise account_deletion_repo.AccountDeletionConflict("delivery lease owner is invalid")
    hook = getattr(target, "claim_delivery_intent", None)
    if callable(hook):
        value = hook(
            scope,
            operation_id,
            digest,
            now_epoch,
            opaque_owner,
            lease_expires_at,
            now_iso,
        )
        if value is None:
            return None
        return value if isinstance(value, DeliveryIntentClaim) else _intent_claim(value)
    if scope.kind == "private_owner":
        account_deletion_repo.require_active_account_fence(
            str(scope.owner_id), int(scope.generation or 0), table=target
        )
    try:
        current_version = _positive_integer(
            current, "intent_version", "delivery claim is malformed"
        )
        response = _update_item(
            target,
            Key=key,
            UpdateExpression=(
                "SET #effect=:pre_effect, #status=:pre_effect, "
                "lease_owner=:lease, lease_expires_at=:expiry, "
                "intent_version=intent_version + :one, updated_at=:now"
            ),
            ConditionExpression=(
                "(#effect=:registered OR (#effect=:pre_effect AND "
                "lease_expires_at < :now_epoch)) AND scope_digest=:scope "
                "AND payload_digest=:payload AND intent_version=:version"
            ),
            ExpressionAttributeNames={"#effect": "effect_state", "#status": "status"},
            ExpressionAttributeValues={
                ":registered": "registered",
                ":pre_effect": "claimed_pre_effect",
                ":scope": scope.digest,
                ":payload": digest,
                ":version": current_version,
                ":lease": opaque_owner,
                ":expiry": lease_expires_at,
                ":now_epoch": now_epoch,
                ":one": 1,
                ":now": now_iso or "",
            },
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if _delivery_conditional_loss(exc):
            return None
        raise
    attributes = response.get("Attributes")
    if not isinstance(attributes, Mapping):
        current_version = _positive_integer(
            current, "intent_version", "delivery claim is malformed"
        )
        attributes = {
            **dict(current),
            "lease_owner": opaque_owner,
            "lease_expires_at": lease_expires_at,
            "intent_version": current_version + 1,
        }
    return _intent_claim(attributes)


def delivery_intent_sendable(
    *,
    scope: DeliveryIntentScope | None = None,
    claim: DeliveryIntentClaim | None = None,
    owner_id: str | None = None,
    generation: int | None = None,
    operation_id: str | None = None,
    lease_owner: str | None = None,
    table: object | None = None,
) -> bool:
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    operation = claim.operation_id if claim is not None else str(operation_id or "")
    target = table or get_table()
    item = _optional_item(
        _get_item(
            target,
            Key=_delivery_key(scope, operation),
            ConsistentRead=True,
        ).get("Item")
    )
    if item is None:
        return False
    if claim is not None:
        return bool(
            item.get("effect_state") == "claimed_pre_effect"
            and item.get("lease_owner") == claim.lease_owner
            and item.get("intent_version") == claim.intent_version
            and item.get("scope_digest") == claim.scope_digest == scope.digest
            and item.get("payload_digest") == claim.payload_digest
        )
    return bool(
        item.get("effect_state") in {"claimed_pre_effect", "claimed"}
        and item.get("lease_owner") == lease_owner
    )


def begin_delivery_effect(
    *,
    scope: DeliveryIntentScope,
    claim: DeliveryIntentClaim,
    now_iso: str,
    table: object | None = None,
) -> DeliveryBeginResult:
    """Durably cross the final exact CAS immediately before provider mutation."""
    scope = _delivery_scope(scope)
    if claim.scope_digest != scope.digest:
        return DeliveryBeginResult(DeliveryBeginDisposition.CLAIM_LOST)
    target = table or get_table()
    hook = getattr(target, "begin_delivery_effect", None)
    if callable(hook):
        try:
            value = hook(scope, claim, now_iso)
            begun = value if isinstance(value, DeliveryIntentClaim) else _intent_claim(value)
            return DeliveryBeginResult(DeliveryBeginDisposition.BEGUN, begun)
        except Exception as exc:
            return classify_delivery_transaction_failure(
                exc,
                scope=scope,
                claim=claim,
                operation_count=2,
                fence_operation_index=0 if scope.kind == "private_owner" else None,
                intent_operation_index=1,
                table=target,
            )
    condition_expression = (
        "#effect=:pre_effect AND lease_owner=:lease AND "
        "intent_version=:version AND scope_digest=:scope AND "
        "payload_digest=:payload"
    )
    expression_values: NotificationItem = {
        ":pre_effect": "claimed_pre_effect",
        ":inflight": "effect_inflight",
        ":lease": claim.lease_owner,
        ":version": claim.intent_version,
        ":scope": claim.scope_digest,
        ":payload": claim.payload_digest,
        ":now": now_iso,
        ":one": 1,
    }
    event_checks: list[NotificationItem] = []
    if scope.kind == "private_owner":
        event_checks.append(
            account_deletion_repo.active_fence_condition(
                str(scope.owner_id), int(scope.generation or 0)
            )
        )
    else:
        intent = _optional_item(
            _get_item(
                target,
                Key=_delivery_key(scope, claim.operation_id),
                ConsistentRead=True,
            ).get("Item")
        )
        raw_event_ids = intent.get("event_ids") if intent is not None else None
        if not isinstance(raw_event_ids, list) or not raw_event_ids:
            raise account_deletion_repo.AccountDeletionConflict(
                "global delivery event set is invalid"
            )
        event_ids: list[str] = []
        for raw_event_id in raw_event_ids:
            if not isinstance(raw_event_id, str) or not raw_event_id:
                raise account_deletion_repo.AccountDeletionConflict(
                    "global delivery event set is invalid"
                )
            event_ids.append(raw_event_id)
        for event_id in event_ids:
            event = load_delivery_event_strong(event_id, table=target)
            if (
                event is None
                or not validate_global_nonprivate_event(event)
                or event.get("classification_digest") != scope.classification_seal
            ):
                raise account_deletion_repo.AccountDeletionConflict(
                    "global delivery classification changed"
                )
            event_checks.append(
                {
                    "ConditionCheck": {
                        "Key": {"PK": notification_pk(event_id), "SK": "META"},
                        "ConditionExpression": (
                            "owner_classification=:global_kind AND "
                            "classification_contract=:contract AND "
                            "classification_digest=:classification_seal AND "
                            "event_version=:event_version"
                        ),
                        "ExpressionAttributeValues": {
                            ":global_kind": "global_nonprivate",
                            ":contract": GLOBAL_NONPRIVATE_CONTRACT_ID,
                            ":classification_seal": scope.classification_seal,
                            ":event_version": event["event_version"],
                        },
                    }
                }
            )
        condition_expression += (
            " AND scope_kind=:global_kind AND classification_seal=:classification_seal"
        )
        expression_values.update(
            {
                ":global_kind": "global_nonprivate",
                ":classification_seal": scope.classification_seal,
            }
        )
    update_details: NotificationItem = {
        "Key": _delivery_key(scope, claim.operation_id),
        "UpdateExpression": (
            "SET #effect=:inflight, #status=:inflight, effect_started_at=:now, "
            "intent_version=intent_version + :one"
        ),
        "ConditionExpression": condition_expression,
        "ExpressionAttributeNames": {
            "#effect": "effect_state",
            "#status": "status",
        },
        "ExpressionAttributeValues": expression_values,
    }
    update: NotificationItem = {"Update": update_details}
    operations = [*event_checks, update]
    try:
        account_deletion_repo.transact(operations, table=target)
    except Exception as exc:
        return classify_delivery_transaction_failure(
            exc,
            scope=scope,
            claim=claim,
            operation_count=len(operations),
            fence_operation_index=0 if scope.kind == "private_owner" else None,
            intent_operation_index=len(operations) - 1,
            table=target,
        )
    return DeliveryBeginResult(
        DeliveryBeginDisposition.BEGUN,
        DeliveryIntentClaim(
            operation_id=claim.operation_id,
            lease_owner=claim.lease_owner,
            intent_version=claim.intent_version + 1,
            lease_expires_at=claim.lease_expires_at,
            scope_digest=claim.scope_digest,
            payload_digest=claim.payload_digest,
        ),
    )


def recover_delivery_intent(
    *,
    scope: DeliveryIntentScope,
    operation_id: str,
    payload_digest: str,
    now_epoch: int,
    expected_claim: DeliveryIntentClaim | None = None,
    now_iso: str | None = None,
    table: object | None = None,
) -> NotificationItem:
    """Classify replay and terminalize an observed ambiguous inflight effect."""
    scope = _delivery_scope(scope)
    target = table or get_table()
    key = _delivery_key(scope, operation_id)
    item = _optional_item(
        _get_item(target, Key=key, ConsistentRead=True).get("Item")
    )
    if item is None or not _delivery_identity_matches(
        item,
        scope=scope,
        operation_id=operation_id,
        payload_digest=payload_digest,
    ):
        raise account_deletion_repo.AccountDeletionConflict("delivery intent identity changed")
    state = str(item.get("effect_state") or item.get("status") or "")
    if expected_claim is not None:
        current_claim = _intent_claim(item)
        if current_claim != expected_claim:
            raise account_deletion_repo.AccountDeletionConflict("stale delivery claim")
    if state in _DELIVERY_TERMINAL_STATES:
        return {"status": state}
    if state != "effect_inflight":
        return dict(item)
    observed = _intent_claim(item)
    try:
        response = _update_item(
            target,
            Key=key,
            UpdateExpression=(
                "SET #effect=:unknown, #status=:unknown, outcome_status=:unknown, "
                "intent_version=intent_version + :one, updated_at=:now "
                "REMOVE lease_owner, lease_expires_at"
            ),
            ConditionExpression=(
                "#effect=:inflight AND lease_owner=:lease AND intent_version=:version "
                "AND scope_digest=:scope AND payload_digest=:payload"
            ),
            ExpressionAttributeNames={"#effect": "effect_state", "#status": "status"},
            ExpressionAttributeValues={
                ":inflight": "effect_inflight",
                ":unknown": "provider_acceptance_unknown",
                ":lease": observed.lease_owner,
                ":version": observed.intent_version,
                ":scope": observed.scope_digest,
                ":payload": observed.payload_digest,
                ":one": 1,
                ":now": now_iso or "",
            },
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if _delivery_conditional_loss(exc):
            raise account_deletion_repo.AccountDeletionConflict(
                "delivery recovery claim lost"
            ) from exc
        raise
    attributes = response.get("Attributes")
    return _dependency_mapping(attributes) if isinstance(attributes, Mapping) else {
        "status": "provider_acceptance_unknown"
    }


def cancel_delivery_intent(
    *,
    scope: DeliveryIntentScope,
    claim: DeliveryIntentClaim,
    now_iso: str,
    table: object | None = None,
) -> NotificationItem:
    return _finish_delivery_intent(
        scope=scope,
        claim=claim,
        status="canceled_account_deletion",
        expected_state="claimed_pre_effect",
        now_iso=now_iso,
        table=table,
    )


def complete_delivery_intent(
    *,
    scope: DeliveryIntentScope | None = None,
    claim: DeliveryIntentClaim | None = None,
    owner_id: str | None = None,
    generation: int | None = None,
    operation_id: str | None = None,
    lease_owner: str | None = None,
    status: str,
    now_iso: str,
    table: object | None = None,
) -> NotificationItem:
    legacy = claim is None
    if status not in _DELIVERY_TERMINAL_STATES and not (legacy and status == "rejected"):
        raise account_deletion_repo.AccountDeletionConflict("invalid delivery completion")
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    target = table or get_table()
    item: NotificationItem | None = None
    if claim is None:
        item = _optional_item(
            _get_item(
                target,
                Key=_delivery_key(scope, str(operation_id or "")),
                ConsistentRead=True,
            ).get("Item")
        )
        if item is None or item.get("lease_owner") != lease_owner:
            raise account_deletion_repo.AccountDeletionConflict("stale delivery claim")
        claim = _intent_claim(item)
    hook = getattr(target, "complete_delivery_intent", None)
    if callable(hook):
        return _dependency_mapping(hook(scope, claim, status, now_iso))
    return _finish_delivery_intent(
        scope=scope,
        claim=claim,
        status=status,
        expected_state=(
            str(item.get("effect_state") or item.get("status") or "")
            if legacy and item is not None
            else "effect_inflight"
        ),
        now_iso=now_iso,
        table=target,
    )


def _finish_delivery_intent(
    *,
    scope: DeliveryIntentScope,
    claim: DeliveryIntentClaim,
    status: str,
    expected_state: str,
    now_iso: str,
    table: object | None,
) -> NotificationItem:
    target = table or get_table()
    hook_name = (
        "cancel_delivery_intent"
        if status == "canceled_account_deletion" and expected_state == "claimed_pre_effect"
        else None
    )
    hook = getattr(target, hook_name, None) if hook_name else None
    if callable(hook):
        return _dependency_mapping(hook(scope, claim, now_iso))
    response = _update_item(
        target,
        Key=_delivery_key(scope, claim.operation_id),
        UpdateExpression=(
            "SET #effect=:status, #status=:status, outcome_status=:status, "
            "intent_version=intent_version + :one, updated_at=:now "
            "REMOVE lease_owner, lease_expires_at"
        ),
        ConditionExpression=(
            "#effect=:expected AND lease_owner=:lease AND intent_version=:version "
            "AND scope_digest=:scope AND payload_digest=:payload"
        ),
        ExpressionAttributeNames={"#effect": "effect_state", "#status": "status"},
        ExpressionAttributeValues={
            ":status": status,
            ":expected": expected_state,
            ":now": now_iso,
            ":lease": claim.lease_owner,
            ":version": claim.intent_version,
            ":scope": claim.scope_digest,
            ":payload": claim.payload_digest,
            ":one": 1,
        },
        ReturnValues="ALL_NEW",
    )
    attributes = response.get("Attributes")
    return (
        {"status": status}
        if not attributes
        else _dependency_mapping(attributes)
    )


def scan_notification_private_rows(
    owner_id: str,
    *,
    cursor: Mapping[str, str] | None = None,
    maximum_pages: int = 1,
    table: object | None = None,
) -> NotificationPrivatePage:
    target = table or get_table()
    current = _cursor(cursor) if cursor is not None else None
    seen: set[tuple[str, str]] = set()
    found: list[NotificationItem] = []
    scanned = 0
    for _ in range(max(maximum_pages, 1)):
        kwargs: dict[str, object] = {"ConsistentRead": True, "Limit": 100}
        if current is not None:
            kwargs["ExclusiveStartKey"] = current
        response = _scan(target, **kwargs)
        items = _response_items(response)
        scanned += len(items)
        found.extend(
            dict(item)
            for item in items
            if item.get("entity_type") in NOTIFICATION_PRIVATE_ROW_REGISTRY
            and (
                _targets_owner(item, owner_id)
                or _targets_identity_reference(item, owner_id)
            )
            and not _already_scrubbed(item)
        )
        raw = response.get("LastEvaluatedKey")
        if raw is None:
            return NotificationPrivatePage(tuple(found), None, scanned)
        current = _cursor(_dependency_mapping(raw))
        identity = (current["PK"], current["SK"])
        if identity in seen:
            raise account_deletion_repo.AccountDeletionConflict("repeated notification cursor")
        seen.add(identity)
    return NotificationPrivatePage(tuple(found), current, scanned)


def scrub_notification_private_row(
    item: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: object | None = None,
) -> None:
    if _targets_owner(item, owner_id):
        _replace_notification_owner_tombstone(
            item,
            owner_id=owner_id,
            generation=generation,
            now_iso=now_iso,
            table=table,
        )
        return
    if _targets_identity_reference(item, owner_id):
        scrub_notification_identity_references(
            item,
            owner_id=owner_id,
            generation=generation,
            table=table,
        )
        return
    raise account_deletion_repo.AccountDeletionConflict("notification owner changed")


def _replace_notification_owner_tombstone(
    item: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: object | None,
) -> None:
    if not _targets_owner(item, owner_id):
        raise account_deletion_repo.AccountDeletionConflict("notification owner changed")
    target = table or get_table()
    entity = str(item.get("entity_type") or "notification")
    status = str(item.get("status") or "")
    tombstone = {
        "PK": item["PK"],
        "SK": item["SK"],
        "entity_type": f"{entity}_deletion_tombstone",
        "schema_version": "notification-deletion-tombstone.v1",
        "status": status if entity == DELIVERY_INTENT_ENTITY and status in _EXTERNAL_RECEIPT_STATES else "deleted",
        "owner_deletion_generation": generation,
        "deleted_at": now_iso,
    }
    for field in ("event_id", "summary_id", "operation_id", "channel", "created_at", "accepted_at"):
        if item.get(field) is not None:
            tombstone[field] = item[field]
    tombstone = {key: value for key, value in tombstone.items() if key in NOTIFICATION_TOMBSTONE_ALLOWLIST}
    hook = getattr(target, "replace_notification_tombstone", None)
    if callable(hook):
        hook(dict(item), tombstone, owner_id, generation)
        return
    account_deletion_repo.transact(
        [
            account_deletion_repo.deletion_fence_condition(owner_id, generation),
            {
                "Put": {
                    "Item": tombstone,
                    "ConditionExpression": "attribute_exists(PK) AND attribute_exists(SK) AND owner_id=:owner",
                    "ExpressionAttributeValues": {":owner": owner_id},
                }
            },
        ],
        table=target,
    )


def scrub_notification_identity_references(
    item: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    table: object | None = None,
) -> None:
    """Remove one foreign identity without mutating recipient-owned evidence."""
    if _targets_owner(item, owner_id):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification owner requires tombstone"
        )
    if not _targets_identity_reference(item, owner_id):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification identity changed"
        )

    pk = _required_identity_coordinate(item.get("PK"), "PK")
    sk = _required_identity_coordinate(item.get("SK"), "SK")
    entity = _required_identity_coordinate(item.get("entity_type"), "entity type")
    schema = _required_identity_coordinate(item.get("schema_version"), "schema version")
    status = _required_identity_coordinate(item.get("status"), "status")
    version = item.get("event_version")
    if type(version) is not int or version <= 0:
        raise account_deletion_repo.AccountDeletionConflict(
            "notification version is malformed"
        )

    metadata = item.get("metadata")
    if not isinstance(metadata, Mapping):
        raise account_deletion_repo.AccountDeletionConflict(
            "notification metadata is malformed"
        )
    metadata_snapshot = _dependency_mapping(metadata)
    metadata_digest = _notification_metadata_digest(metadata_snapshot)
    reference_fields = NOTIFICATION_IDENTITY_REFERENCE_REGISTRY[NOTIFICATION_ENTITY]
    metadata_fields = reference_fields["metadata_fields"]
    clean_metadata = {
        key: value
        for key, value in metadata_snapshot.items()
        if not (key in metadata_fields and value == owner_id)
    }
    direct_match = item.get("actor_id") == owner_id

    target = table or get_table()
    hook = getattr(target, "scrub_notification_identity_references", None)
    if callable(hook):
        hook(
            dict(item),
            clean_metadata,
            owner_id,
            generation,
            metadata_digest,
        )
        return

    condition = (
        "PK=:pk AND SK=:sk AND entity_type=:entity AND schema_version=:schema "
        "AND event_version=:version AND #status=:status AND metadata=:metadata"
    )
    values: dict[str, object] = {
        ":pk": pk,
        ":sk": sk,
        ":entity": entity,
        ":schema": schema,
        ":version": version,
        ":next_version": version + 1,
        ":status": status,
        ":metadata": metadata_snapshot,
        ":clean_metadata": clean_metadata,
    }
    update = "SET metadata=:clean_metadata, event_version=:next_version"
    if direct_match:
        condition += " AND actor_id=:identity"
        values[":identity"] = owner_id
        update += " REMOVE actor_id"

    account_deletion_repo.transact(
        [
            account_deletion_repo.deletion_fence_condition(owner_id, generation),
            {
                "Update": {
                    "Key": {"PK": pk, "SK": sk},
                    "UpdateExpression": update,
                    "ConditionExpression": condition,
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": values,
                }
            },
        ],
        table=target,
    )


def _required_identity_coordinate(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise account_deletion_repo.AccountDeletionConflict(
            f"notification {name} is malformed"
        )
    return value


def _notification_metadata_digest(metadata: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(
            dict(metadata),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise account_deletion_repo.AccountDeletionConflict(
            "notification metadata is malformed"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _targets_owner(item: Mapping[str, object], owner_id: str) -> bool:
    if owner_id in {item.get("owner_id"), item.get("student_id"), item.get("user_id")}:
        return True
    metadata = item.get("metadata")
    return isinstance(metadata, Mapping) and owner_id in {
        metadata.get("owner_id"), metadata.get("student_id")
    }


def _targets_identity_reference(
    item: Mapping[str, object], owner_id: str
) -> bool:
    fields = NOTIFICATION_IDENTITY_REFERENCE_REGISTRY.get(
        str(item.get("entity_type") or "")
    )
    if fields is None:
        return False
    if any(item.get(field) == owner_id for field in fields["scalar_fields"]):
        return True
    metadata = item.get("metadata")
    return isinstance(metadata, Mapping) and any(
        metadata.get(field) == owner_id for field in fields["metadata_fields"]
    )


def _already_scrubbed(item: Mapping[str, object]) -> bool:
    return str(item.get("entity_type") or "").endswith("_deletion_tombstone")


def _cursor(value: Mapping[str, object]) -> dict[str, str]:
    if set(value) != {"PK", "SK"} or any(
        not isinstance(value.get(field), str) or not value[field] for field in ("PK", "SK")
    ):
        raise account_deletion_repo.AccountDeletionConflict("invalid notification cursor")
    return {"PK": str(value["PK"]), "SK": str(value["SK"])}
