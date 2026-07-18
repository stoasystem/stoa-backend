"""Owner-fenced notification, assistance, device, and delivery persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from boto3.dynamodb.conditions import Attr

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
    owner_id: str,
    generation: int,
    operation_id: str,
    channel: str,
    event_ids: list[str],
    payload_digest: str,
    now_iso: str,
    table: Any | None = None,
) -> dict[str, Any]:
    target = table or get_table()
    key = {"PK": delivery_intent_pk(owner_id), "SK": delivery_intent_sk(operation_id)}
    existing = target.get_item(Key=key, ConsistentRead=True).get("Item")
    if existing:
        if (
            existing.get("owner_id") != owner_id
            or existing.get("account_fence_generation") != generation
            or existing.get("channel") != channel
            or existing.get("event_ids") != event_ids
            or existing.get("payload_digest") != payload_digest
        ):
            raise account_deletion_repo.AccountDeletionConflict("delivery intent identity changed")
        return dict(existing)
    item = {
        **key,
        "entity_type": DELIVERY_INTENT_ENTITY,
        "schema_version": "notification-delivery-intent.v1",
        "operation_id": operation_id,
        "owner_id": owner_id,
        "account_fence_generation": generation,
        "channel": channel,
        "event_ids": list(event_ids),
        "payload_digest": payload_digest,
        "status": "registered",
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    hook = getattr(target, "register_delivery_intent", None)
    if callable(hook):
        return dict(hook(item) or item)
    account_deletion_repo.transact(
        build_notification_write_transaction(
            item=item, owner_id=owner_id, generation=generation, mode="put"
        ),
        table=target,
    )
    return item


def claim_delivery_intent(
    *, owner_id: str, generation: int, operation_id: str, lease_owner: str, lease_expires_at: int,
    now_iso: str, table: Any | None = None
) -> dict[str, Any] | None:
    target = table or get_table()
    hook = getattr(target, "claim_delivery_intent", None)
    if callable(hook):
        value = hook(owner_id, generation, operation_id, lease_owner, lease_expires_at, now_iso)
        return dict(value) if isinstance(value, Mapping) else value
    account_deletion_repo.require_active_account_fence(owner_id, generation, table=target)
    key = {"PK": delivery_intent_pk(owner_id), "SK": delivery_intent_sk(operation_id)}
    try:
        response = target.update_item(
            Key=key,
            UpdateExpression="SET #status=:claimed, lease_owner=:lease, lease_expires_at=:expiry, updated_at=:now",
            ConditionExpression="#status=:registered AND owner_id=:owner AND account_fence_generation=:generation",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":registered": "registered", ":claimed": "claimed", ":owner": owner_id,
                ":generation": generation, ":lease": lease_owner, ":expiry": lease_expires_at,
                ":now": now_iso,
            },
            ReturnValues="ALL_NEW",
        )
    except Exception:
        return None
    return response.get("Attributes")


def delivery_intent_sendable(
    *, owner_id: str, generation: int, operation_id: str, lease_owner: str,
    table: Any | None = None
) -> bool:
    target = table or get_table()
    try:
        account_deletion_repo.require_active_account_fence(owner_id, generation, table=target)
    except account_deletion_repo.AccountDeletionConflict:
        return False
    item = target.get_item(
        Key={"PK": delivery_intent_pk(owner_id), "SK": delivery_intent_sk(operation_id)},
        ConsistentRead=True,
    ).get("Item")
    return bool(
        item
        and item.get("status") == "claimed"
        and item.get("lease_owner") == lease_owner
        and item.get("account_fence_generation") == generation
    )


def complete_delivery_intent(
    *, owner_id: str, generation: int, operation_id: str, lease_owner: str,
    status: str, now_iso: str, table: Any | None = None
) -> dict[str, Any]:
    if status not in {"accepted", "provider_acceptance_unknown", "canceled_account_deletion", "rejected"}:
        raise account_deletion_repo.AccountDeletionConflict("invalid delivery completion")
    target = table or get_table()
    hook = getattr(target, "complete_delivery_intent", None)
    if callable(hook):
        return dict(hook(owner_id, generation, operation_id, lease_owner, status, now_iso))
    response = target.update_item(
        Key={"PK": delivery_intent_pk(owner_id), "SK": delivery_intent_sk(operation_id)},
        UpdateExpression="SET #status=:status, updated_at=:now REMOVE lease_owner, lease_expires_at",
        ConditionExpression="owner_id=:owner AND account_fence_generation=:generation AND lease_owner=:lease",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": status, ":now": now_iso, ":owner": owner_id,
            ":generation": generation, ":lease": lease_owner,
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
