"""Owner-fenced DynamoDB access for WebSocket connection records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

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


type ConnectionItem = dict[str, object]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _DeleteTable(Protocol):
    def delete_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


@runtime_checkable
class _SupportsInt(Protocol):
    def __int__(self) -> int: ...


def _integer_or_zero(value: object) -> int:
    if not isinstance(value, (str, bytes, bytearray, _SupportsInt)):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dependency_mapping(value: object) -> ConnectionItem:
    if not isinstance(value, Mapping):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed connection dependency response"
        )
    result: ConnectionItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise account_deletion_repo.AccountDeletionConflict(
                "malformed connection dependency response"
            )
        result[key] = member
    return result


def _optional_item(value: object) -> ConnectionItem | None:
    if value is None:
        return None
    return _dependency_mapping(value)


def _response_items(response: Mapping[str, object]) -> list[ConnectionItem]:
    raw_items = response.get("Items", [])
    if not isinstance(raw_items, list):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed connection dependency response"
        )
    return [_dependency_mapping(item) for item in raw_items]


def _get_item(table: object, **kwargs: object) -> ConnectionItem:
    if not isinstance(table, _GetTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "connection dependency unavailable"
        )
    return _dependency_mapping(table.get_item(**kwargs))


def _delete_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _DeleteTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "connection dependency unavailable"
        )
    return table.delete_item(**kwargs)


def _scan(table: object, **kwargs: object) -> ConnectionItem:
    if not isinstance(table, _ScanTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "connection dependency unavailable"
        )
    return _dependency_mapping(table.scan(**kwargs))


@dataclass(frozen=True, slots=True)
class ConnectionPrivatePage:
    items: tuple[ConnectionItem, ...]
    cursor: dict[str, str] | None = None
    scanned: int = 0


def connection_pk(connection_id: str) -> str:
    return f"WS_CONN#{connection_id}"


def build_connection_write_transaction(
    *,
    item: Mapping[str, object],
    owner_id: str,
    generation: int,
    mode: str = "put",
    updates: Mapping[str, object] | None = None,
) -> list[ConnectionItem]:
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


def _generation(owner_id: str, generation: object, table: object) -> int:
    if type(generation) is int and generation > 0:
        return generation
    atomic = callable(getattr(table, "transact_account_deletion", None)) or bool(
        getattr(getattr(table, "meta", None), "client", None)
        and getattr(table, "name", None)
    )
    if atomic:
        return int(account_deletion_repo.require_active_account_fence(owner_id, table=table)["generation"])
    return 1


def put_connection(item: ConnectionItem) -> ConnectionItem:
    target = get_table()
    owner_id = str(item.get("owner_id") or item.get("user_id") or "")
    generation = _generation(owner_id, item.get("account_fence_generation"), target)
    connection_id = item.get("connection_id")
    if not isinstance(connection_id, str) or not connection_id:
        raise account_deletion_repo.AccountDeletionConflict(
            "connection identity is invalid"
        )
    stored = {
        **item,
        "PK": connection_pk(connection_id),
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


def get_connection(connection_id: str) -> ConnectionItem | None:
    response = _get_item(
        get_table(), Key={"PK": connection_pk(connection_id), "SK": "META"}
    )
    return _optional_item(response.get("Item"))


def update_connection(
    connection_id: str, updates: ConnectionItem
) -> ConnectionItem | None:
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
    _delete_item(
        get_table(), Key={"PK": connection_pk(connection_id), "SK": "META"}
    )


def list_connections(limit: int = 200) -> list[ConnectionItem]:
    response = _scan(
        get_table(),
        FilterExpression=Attr("entity_type").eq(CONNECTION_ENTITY), Limit=limit
    )
    return _response_items(response)


def delete_stale_connections(*, now_epoch: int, limit: int = 200) -> list[str]:
    removed: list[str] = []
    for item in list_connections(limit=limit):
        connection_id = str(item.get("connection_id") or "")
        if not connection_id:
            continue
        expires_at = _integer_or_zero(item.get("expires_at"))
        if expires_at <= now_epoch:
            delete_connection(connection_id)
            removed.append(connection_id)
    return removed


def scan_account_connections(
    owner_id: str,
    *,
    cursor: Mapping[str, str] | None = None,
    maximum_pages: int = 1,
    table: object | None = None,
) -> ConnectionPrivatePage:
    target = table or get_table()
    current = _cursor(cursor) if cursor is not None else None
    seen: set[tuple[str, str]] = set()
    found: list[ConnectionItem] = []
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
            if item.get("entity_type") == CONNECTION_ENTITY
            and owner_id in {item.get("owner_id"), item.get("user_id")}
        )
        raw = response.get("LastEvaluatedKey")
        if raw is None:
            return ConnectionPrivatePage(tuple(found), None, scanned)
        current = _cursor(_dependency_mapping(raw))
        identity = (current["PK"], current["SK"])
        if identity in seen:
            raise account_deletion_repo.AccountDeletionConflict("repeated connection cursor")
        seen.add(identity)
    return ConnectionPrivatePage(tuple(found), current, scanned)


def revoke_account_connection(
    item: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    table: object | None = None,
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


def _cursor(value: Mapping[str, object]) -> dict[str, str]:
    if set(value) != {"PK", "SK"} or any(
        not isinstance(value.get(field), str) or not value[field] for field in ("PK", "SK")
    ):
        raise account_deletion_repo.AccountDeletionConflict("invalid connection cursor")
    return {"PK": str(value["PK"]), "SK": str(value["SK"])}
