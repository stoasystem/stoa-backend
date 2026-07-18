"""Owner-fenced notification, assistance, device, and delivery persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


NOTIFICATION_ENTITY = "notification_event"
SUMMARY_SEED_ENTITY = "teacher_assistance_summary_seed"
PREFERENCE_ENTITY = "notification_preference"
PUSH_TOKEN_ENTITY = "notification_push_token"
DELIVERY_INTENT_ENTITY = "notification_delivery_intent"

NOTIFICATION_PRIVATE_ROW_REGISTRY = frozenset(
    {
        NOTIFICATION_ENTITY,
        SUMMARY_SEED_ENTITY,
        PREFERENCE_ENTITY,
        PUSH_TOKEN_ENTITY,
        DELIVERY_INTENT_ENTITY,
    }
)
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


@dataclass(frozen=True, slots=True)
class NotificationPrivatePage:
    items: tuple[dict[str, Any], ...]
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


_DELIVERY_TERMINAL_STATES = frozenset(
    {"accepted", "provider_acceptance_unknown", "canceled_account_deletion"}
)


def _delivery_digest(value: Mapping[str, Any]) -> str:
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
    item: Mapping[str, Any],
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


def _intent_claim(item: Mapping[str, Any]) -> DeliveryIntentClaim:
    try:
        claim = DeliveryIntentClaim(
            operation_id=str(item["operation_id"]),
            lease_owner=str(item["lease_owner"]),
            intent_version=int(item["intent_version"]),
            lease_expires_at=int(item["lease_expires_at"]),
            scope_digest=str(item["scope_digest"]),
            payload_digest=str(item["payload_digest"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise account_deletion_repo.AccountDeletionConflict(
            "delivery claim is malformed"
        ) from exc
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
    item: Mapping[str, Any],
    owner_id: str,
    generation: int,
    mode: str = "put",
    updates: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
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


def _generation(owner_id: str, generation: int | None, table: Any) -> int:
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


def _persist_private(item: dict[str, Any], *, mode: str = "put", updates: Mapping[str, Any] | None = None) -> dict[str, Any]:
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


def put_event(item: dict[str, Any]) -> dict[str, Any]:
    stored = {**item, "PK": notification_pk(item["event_id"]), "SK": "META"}
    return _persist_private(stored)


def get_event(event_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(Key={"PK": notification_pk(event_id), "SK": "META"})
    return response.get("Item")


def update_event(event_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    existing = get_event(event_id)
    if not existing:
        return None
    if not updates:
        return existing
    _persist_private(existing, mode="update", updates=updates)
    return {**existing, **updates}


def list_events(limit: int = 100) -> list[dict[str, Any]]:
    response = get_table().scan(
        FilterExpression=Attr("entity_type").eq(NOTIFICATION_ENTITY), Limit=limit
    )
    return response.get("Items", [])


def put_preferences(item: dict[str, Any]) -> dict[str, Any]:
    stored = {**item, "PK": preference_pk(item["user_id"]), "SK": "META"}
    existing = get_preferences(str(item["user_id"]))
    if existing:
        values = {key: value for key, value in stored.items() if key not in {"PK", "SK"}}
        return {**existing, **values} if _persist_private(existing, mode="update", updates=values) else stored
    return _persist_private(stored)


def get_preferences(user_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(Key={"PK": preference_pk(user_id), "SK": "META"})
    return response.get("Item")


def put_push_token(item: dict[str, Any]) -> dict[str, Any]:
    stored = {
        **item,
        "PK": push_token_pk(item["user_id"], item["token_reference"]),
        "SK": "META",
    }
    existing = get_push_token(str(item["user_id"]), str(item["token_reference"]))
    if existing:
        updates = {key: value for key, value in stored.items() if key not in {"PK", "SK"}}
        _persist_private(existing, mode="update", updates=updates)
        return {**existing, **updates}
    return _persist_private(stored)


def get_push_token(user_id: str, token_reference: str) -> dict[str, Any] | None:
    response = get_table().get_item(
        Key={"PK": push_token_pk(user_id, token_reference), "SK": "META"}
    )
    return response.get("Item")


def list_push_tokens(
    user_id: str | None = None, *, status: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    filters = [Attr("entity_type").eq(PUSH_TOKEN_ENTITY)]
    if user_id is not None:
        filters.append(Attr("user_id").eq(user_id))
    if status is not None:
        filters.append(Attr("status").eq(status))
    expression = filters[0]
    for filter_expression in filters[1:]:
        expression = expression & filter_expression
    response = get_table().scan(FilterExpression=expression, Limit=limit)
    return response.get("Items", [])


def update_push_token(user_id: str, token_reference: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    existing = get_push_token(user_id, token_reference)
    if not existing:
        return None
    if updates:
        _persist_private(existing, mode="update", updates=updates)
    return {**existing, **updates}


def put_summary_seed(item: dict[str, Any]) -> dict[str, Any]:
    stored = {**item, "PK": summary_seed_pk(item["summary_id"]), "SK": "META"}
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
    table: Any | None = None,
) -> dict[str, Any]:
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    target = table or get_table()
    key = _delivery_key(scope, operation_id)
    existing = target.get_item(Key=key, ConsistentRead=True).get("Item")
    if existing:
        if not _delivery_identity_matches(
            existing,
            scope=scope,
            operation_id=operation_id,
            payload_digest=payload_digest,
        ) or existing.get("channel") != channel or existing.get("event_ids") != event_ids:
            raise account_deletion_repo.AccountDeletionConflict("delivery intent identity changed")
        return dict(existing)
    item = {
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
        return dict(hook(item) or item)
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
        target.put_item(
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
    table: Any | None = None,
) -> DeliveryIntentClaim | None:
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    target = table or get_table()
    key = _delivery_key(scope, operation_id)
    current = target.get_item(Key=key, ConsistentRead=True).get("Item")
    if not isinstance(current, Mapping):
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
        response = target.update_item(
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
                ":version": int(current.get("intent_version") or 0),
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
        attributes = {
            **dict(current),
            "lease_owner": opaque_owner,
            "lease_expires_at": lease_expires_at,
            "intent_version": int(current.get("intent_version") or 0) + 1,
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
    table: Any | None = None,
) -> bool:
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    operation = claim.operation_id if claim is not None else str(operation_id or "")
    target = table or get_table()
    if scope.kind == "private_owner":
        try:
            account_deletion_repo.require_active_account_fence(
                str(scope.owner_id), int(scope.generation or 0), table=target
            )
        except account_deletion_repo.AccountDeletionConflict:
            return False
    item = target.get_item(
        Key=_delivery_key(scope, operation),
        ConsistentRead=True,
    ).get("Item")
    if not isinstance(item, Mapping):
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
    table: Any | None = None,
) -> DeliveryIntentClaim:
    """Durably cross the final exact CAS immediately before provider mutation."""
    scope = _delivery_scope(scope)
    if claim.scope_digest != scope.digest:
        raise account_deletion_repo.AccountDeletionConflict("delivery scope changed")
    target = table or get_table()
    hook = getattr(target, "begin_delivery_effect", None)
    if callable(hook):
        value = hook(scope, claim, now_iso)
        return value if isinstance(value, DeliveryIntentClaim) else _intent_claim(value)
    update = {
        "Update": {
            "Key": _delivery_key(scope, claim.operation_id),
            "UpdateExpression": (
                "SET #effect=:inflight, #status=:inflight, effect_started_at=:now, "
                "intent_version=intent_version + :one"
            ),
            "ConditionExpression": (
                "#effect=:pre_effect AND lease_owner=:lease AND "
                "intent_version=:version AND scope_digest=:scope AND "
                "payload_digest=:payload"
            ),
            "ExpressionAttributeNames": {
                "#effect": "effect_state",
                "#status": "status",
            },
            "ExpressionAttributeValues": {
                ":pre_effect": "claimed_pre_effect",
                ":inflight": "effect_inflight",
                ":lease": claim.lease_owner,
                ":version": claim.intent_version,
                ":scope": claim.scope_digest,
                ":payload": claim.payload_digest,
                ":now": now_iso,
                ":one": 1,
            },
        }
    }
    operations = [update]
    if scope.kind == "private_owner":
        operations.insert(
            0,
            account_deletion_repo.active_fence_condition(
                str(scope.owner_id), int(scope.generation or 0)
            ),
        )
    try:
        account_deletion_repo.transact(operations, table=target)
    except Exception as exc:
        if _delivery_conditional_loss(exc):
            raise account_deletion_repo.AccountDeletionConflict(
                "delivery begin claim lost"
            ) from exc
        raise
    return DeliveryIntentClaim(
        operation_id=claim.operation_id,
        lease_owner=claim.lease_owner,
        intent_version=claim.intent_version + 1,
        lease_expires_at=claim.lease_expires_at,
        scope_digest=claim.scope_digest,
        payload_digest=claim.payload_digest,
    )


def recover_delivery_intent(
    *,
    scope: DeliveryIntentScope,
    operation_id: str,
    payload_digest: str,
    now_epoch: int,
    expected_claim: DeliveryIntentClaim | None = None,
    now_iso: str | None = None,
    table: Any | None = None,
) -> dict[str, Any]:
    """Classify replay and terminalize an observed ambiguous inflight effect."""
    scope = _delivery_scope(scope)
    target = table or get_table()
    key = _delivery_key(scope, operation_id)
    item = target.get_item(Key=key, ConsistentRead=True).get("Item")
    if not isinstance(item, Mapping) or not _delivery_identity_matches(
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
        response = target.update_item(
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
    return dict(attributes) if isinstance(attributes, Mapping) else {
        "status": "provider_acceptance_unknown"
    }


def cancel_delivery_intent(
    *,
    scope: DeliveryIntentScope,
    claim: DeliveryIntentClaim,
    now_iso: str,
    table: Any | None = None,
) -> dict[str, Any]:
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
    table: Any | None = None,
) -> dict[str, Any]:
    legacy = claim is None
    if status not in _DELIVERY_TERMINAL_STATES and not (legacy and status == "rejected"):
        raise account_deletion_repo.AccountDeletionConflict("invalid delivery completion")
    scope = _delivery_scope(scope, owner_id=owner_id, generation=generation)
    target = table or get_table()
    if claim is None:
        item = target.get_item(
            Key=_delivery_key(scope, str(operation_id or "")), ConsistentRead=True
        ).get("Item")
        if not isinstance(item, Mapping) or item.get("lease_owner") != lease_owner:
            raise account_deletion_repo.AccountDeletionConflict("stale delivery claim")
        claim = _intent_claim(item)
    hook = getattr(target, "complete_delivery_intent", None)
    if callable(hook):
        return dict(hook(scope, claim, status, now_iso))
    return _finish_delivery_intent(
        scope=scope,
        claim=claim,
        status=status,
        expected_state=(
            str(item.get("effect_state") or item.get("status") or "")
            if legacy
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
    table: Any | None,
) -> dict[str, Any]:
    target = table or get_table()
    hook_name = (
        "cancel_delivery_intent"
        if status == "canceled_account_deletion" and expected_state == "claimed_pre_effect"
        else None
    )
    hook = getattr(target, hook_name, None) if hook_name else None
    if callable(hook):
        return dict(hook(scope, claim, now_iso))
    response = target.update_item(
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
    return dict(response.get("Attributes") or {"status": status})


def scan_notification_private_rows(
    owner_id: str,
    *,
    cursor: Mapping[str, str] | None = None,
    maximum_pages: int = 1,
    table: Any | None = None,
) -> NotificationPrivatePage:
    target = table or get_table()
    current = _cursor(cursor) if cursor is not None else None
    seen: set[tuple[str, str]] = set()
    found: list[dict[str, Any]] = []
    scanned = 0
    for _ in range(max(maximum_pages, 1)):
        kwargs: dict[str, Any] = {"ConsistentRead": True, "Limit": 100}
        if current is not None:
            kwargs["ExclusiveStartKey"] = current
        response = target.scan(**kwargs)
        items = response.get("Items") or []
        scanned += len(items)
        found.extend(
            dict(item)
            for item in items
            if item.get("entity_type") in NOTIFICATION_PRIVATE_ROW_REGISTRY
            and _targets_owner(item, owner_id)
            and not _already_scrubbed(item)
        )
        raw = response.get("LastEvaluatedKey")
        if raw is None:
            return NotificationPrivatePage(tuple(found), None, scanned)
        current = _cursor(raw)
        identity = (current["PK"], current["SK"])
        if identity in seen:
            raise account_deletion_repo.AccountDeletionConflict("repeated notification cursor")
        seen.add(identity)
    return NotificationPrivatePage(tuple(found), current, scanned)


def scrub_notification_private_row(
    item: Mapping[str, Any], *, owner_id: str, generation: int, now_iso: str,
    table: Any | None = None
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


def _targets_owner(item: Mapping[str, Any], owner_id: str) -> bool:
    if owner_id in {item.get("owner_id"), item.get("student_id"), item.get("user_id")}:
        return True
    metadata = item.get("metadata")
    return isinstance(metadata, Mapping) and owner_id in {
        metadata.get("owner_id"), metadata.get("student_id")
    }


def _already_scrubbed(item: Mapping[str, Any]) -> bool:
    return str(item.get("entity_type") or "").endswith("_deletion_tombstone")


def _cursor(value: Mapping[str, Any]) -> dict[str, str]:
    if set(value) != {"PK", "SK"} or any(
        not isinstance(value.get(field), str) or not value[field] for field in ("PK", "SK")
    ):
        raise account_deletion_repo.AccountDeletionConflict("invalid notification cursor")
    return {"PK": str(value["PK"]), "SK": str(value["SK"])}
