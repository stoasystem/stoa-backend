"""Owner-fenced DynamoDB access for WebSocket connection records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from boto3.dynamodb.conditions import Attr

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


CONNECTION_ENTITY = "websocket_connection"
WEBSOCKET_WRITER_REGISTRY = frozenset(
    {
        "put_connection",
        "refresh_connection",
        "subscribe_connection",
        "fanout_notification_event",
    }
)
WEBSOCKET_PRIVATE_FIELDS = frozenset(
    {
        "connection_id",
        "user_id",
        "role",
        "endpoint_url",
        "subscribed_channels",
        "delivery_state",
        "last_seen_at",
        "expires_at",
    }
)


@dataclass(frozen=True, slots=True)
class ConnectionPrivatePage:
    items: tuple[dict[str, Any], ...]
    cursor: dict[str, str] | None = None
    scanned: int = 0


def connection_pk(connection_id: str) -> str:
    return f"WS_CONN#{connection_id}"


def build_connection_write_transaction(
    *,
    item: Mapping[str, Any],
    owner_id: str,
    generation: int,
    mode: str = "put",
    updates: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not owner_id or type(generation) is not int or generation <= 0:
        raise account_deletion_repo.AccountDeletionConflict("connection owner is invalid")
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
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            }
        )
        return operations
    if mode != "update" or not updates:
        raise ValueError("connection write mode is invalid")
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


def _generation(owner_id: str, generation: Any, table: Any) -> int:
    if type(generation) is int and generation > 0:
        return generation
    atomic = callable(getattr(table, "transact_account_deletion", None)) or bool(
        getattr(getattr(table, "meta", None), "client", None)
        and getattr(table, "name", None)
    )
    if atomic:
        return int(account_deletion_repo.require_active_account_fence(owner_id, table=table)["generation"])
    return 1


def put_connection(item: dict[str, Any]) -> dict[str, Any]:
    target = get_table()
    owner_id = str(item.get("owner_id") or item.get("user_id") or "")
    generation = _generation(owner_id, item.get("account_fence_generation"), target)
    stored = {
        **item,
        "PK": connection_pk(item["connection_id"]),
        "SK": "META",
        "owner_id": owner_id,
        "account_fence_generation": generation,
    }
    account_deletion_repo.transact(
        build_connection_write_transaction(
            item=stored, owner_id=owner_id, generation=generation, mode="put"
        ),
        table=target,
    )
    return stored


def get_connection(connection_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(Key={"PK": connection_pk(connection_id), "SK": "META"})
    return response.get("Item")


def update_connection(connection_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    existing = get_connection(connection_id)
    if not existing:
        return None
    if not updates:
        return existing
    target = get_table()
    owner_id = str(existing.get("owner_id") or existing.get("user_id") or "")
    generation = _generation(owner_id, existing.get("account_fence_generation"), target)
    account_deletion_repo.transact(
        build_connection_write_transaction(
            item=existing,
            owner_id=owner_id,
            generation=generation,
            mode="update",
            updates=updates,
        ),
        table=target,
    )
    return {**existing, **updates}


def delete_connection(connection_id: str) -> None:
    get_table().delete_item(Key={"PK": connection_pk(connection_id), "SK": "META"})


def list_connections(limit: int = 200) -> list[dict[str, Any]]:
    response = get_table().scan(
        FilterExpression=Attr("entity_type").eq(CONNECTION_ENTITY), Limit=limit
    )
    return response.get("Items", [])


def delete_stale_connections(*, now_epoch: int, limit: int = 200) -> list[str]:
    removed: list[str] = []
    for item in list_connections(limit=limit):
        connection_id = str(item.get("connection_id") or "")
        if not connection_id:
            continue
        try:
            expires_at = int(item.get("expires_at") or 0)
        except (TypeError, ValueError):
            expires_at = 0
        if expires_at <= now_epoch:
            delete_connection(connection_id)
            removed.append(connection_id)
    return removed


def scan_account_connections(
    owner_id: str,
    *,
    cursor: Mapping[str, str] | None = None,
    maximum_pages: int = 1,
    table: Any | None = None,
) -> ConnectionPrivatePage:
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
            if item.get("entity_type") == CONNECTION_ENTITY
            and owner_id in {item.get("owner_id"), item.get("user_id")}
        )
        raw = response.get("LastEvaluatedKey")
        if raw is None:
            return ConnectionPrivatePage(tuple(found), None, scanned)
        current = _cursor(raw)
        identity = (current["PK"], current["SK"])
        if identity in seen:
            raise account_deletion_repo.AccountDeletionConflict("repeated connection cursor")
        seen.add(identity)
    return ConnectionPrivatePage(tuple(found), current, scanned)


def revoke_account_connection(
    item: Mapping[str, Any], *, owner_id: str, generation: int, table: Any | None = None
) -> None:
    if owner_id not in {item.get("owner_id"), item.get("user_id")}:
        raise account_deletion_repo.AccountDeletionConflict("connection owner changed")
    target = table or get_table()
    hook = getattr(target, "delete_connection_for_account", None)
    if callable(hook):
        hook(dict(item), owner_id, generation)
        return
    account_deletion_repo.transact(
        [
            account_deletion_repo.deletion_fence_condition(owner_id, generation),
            {
                "Delete": {
                    "Key": {"PK": item["PK"], "SK": item["SK"]},
                    "ConditionExpression": (
                        "attribute_exists(PK) AND attribute_exists(SK) AND "
                        "(owner_id=:owner OR user_id=:owner)"
                    ),
                    "ExpressionAttributeValues": {":owner": owner_id},
                }
            },
        ],
        table=target,
    )


def _cursor(value: Mapping[str, Any]) -> dict[str, str]:
    if set(value) != {"PK", "SK"} or any(
        not isinstance(value.get(field), str) or not value[field] for field in ("PK", "SK")
    ):
        raise account_deletion_repo.AccountDeletionConflict("invalid connection cursor")
    return {"PK": str(value["PK"]), "SK": str(value["SK"])}
