"""Owner-fenced DynamoDB access for WebSocket connection records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from boto3.dynamodb.conditions import Attr, Key

from stoa.db import data_catalog, owner_registry
from stoa.db import table as db_table
from stoa.db.dynamodb import stored_int
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


@dataclass(frozen=True, slots=True)
class ConnectionPrivatePage:
    items: tuple[ConnectionItem, ...]
    cursor: dict[str, str] | None = None
    scanned: int = 0


def connection_pk(connection_id: str) -> str:
    return f"WS_CONN#{connection_id}"


# -- Where a connection is found by whose it is (#624) --------------------------------
#
# A notification is pushed to the open connections that subscribed to its
# channel. A connection can only subscribe to its own person's channel
# (`user:{id}`) and its own role's (`role:{role}`), so the connections that can
# receive a notification are one person's or one role's. Finding them by a scan
# of the whole table read every row of `stoa-main` for every notification, kept
# the first 500 connection rows of the whole site, and stopped answering once
# the table outgrew the scan's page budget.
#
# So a connection carries two places to be found from:
# - GSI-SweepPending: `sweep_bucket` is its person's bucket, `sweep_due_at` when
#   it connected. The help requests (#608), notifications (#613) and others use
#   the same index, each in buckets of their own.
# - GSI-Listing: `listing` is its role's list, `listed_at` when it connected.
#   The administrators' list of notifications (#613) is another list there.
#
# Whose a connection is, its role and when it connected never change, so the
# keys are set by `put_connection`, and `update_connection` refuses to move
# them; it gives them to a row written before them. Account deletion deletes the
# row, and with it its place in both indexes. Expired rows leave with the
# table's TTL on `expires_at`.
USER_INDEX = "GSI-SweepPending"
USER_INDEX_FIELDS = ("sweep_bucket", "sweep_due_at")
ROLE_INDEX = "GSI-Listing"
ROLE_INDEX_FIELDS = ("listing", "listed_at")
INDEX_FIELDS = (*USER_INDEX_FIELDS, *ROLE_INDEX_FIELDS)
INDEX_SOURCE_FIELDS = frozenset({"user_id", "role", "connected_at"})
_USER_INDEX_KEY = ("PK", "SK", *USER_INDEX_FIELDS)
_ROLE_INDEX_KEY = ("PK", "SK", *ROLE_INDEX_FIELDS)


def user_bucket(user_id: str) -> str:
    """The GSI-SweepPending partition of one person's connections."""
    if not user_id:
        raise ValueError("a person's connections are found by their id")
    return f"{CONNECTION_ENTITY}#user#{user_id}"


def role_listing(role: str) -> str:
    """The GSI-Listing partition of one role's connections."""
    if not role:
        raise ValueError("a role's connections are found by the role")
    return f"{CONNECTION_ENTITY}#role#{role}"


def index_fields(item: Mapping[str, object]) -> dict[str, str]:
    """The index keys a connection row carries; none for any other row.

    Its person's bucket when it names a `user_id`, its role's list when it names
    a `role`, both ordered by when it connected. A row with no connection time
    is in neither: an index key is never written empty.
    """
    if item.get("entity_type") != CONNECTION_ENTITY:
        return {}
    connected_at = item.get("connected_at")
    if not isinstance(connected_at, str) or not connected_at:
        return {}
    fields: dict[str, str] = {}
    user_id = item.get("user_id")
    if isinstance(user_id, str) and user_id:
        fields.update(sweep_bucket=user_bucket(user_id), sweep_due_at=connected_at)
    role = item.get("role")
    if isinstance(role, str) and role:
        fields.update(listing=role_listing(role), listed_at=connected_at)
    return fields


def carried_index_fields(item: Mapping[str, object]) -> dict[str, object]:
    """The index keys a stored row holds now."""
    return {name: item[name] for name in INDEX_FIELDS if name in item}


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
    operations: list[ConnectionItem] = []
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
    supplied = stored_int(generation)
    if supplied is not None and supplied > 0:
        return supplied
    atomic = db_table.transactional(table)
    if atomic:
        return int(account_deletion_repo.require_active_account_fence(owner_id, table=table)["generation"])
    return 1


def put_connection(item: ConnectionItem) -> ConnectionItem:
    target = db_table.table()
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
    stored.update(index_fields(stored))
    db_table.fenced(
        owner_id,
        build_connection_write_transaction(
            item=stored, owner_id=owner_id, generation=generation, mode="put"
        ),
        generation=generation,
        table=target,
    )
    return stored


def get_connection(connection_id: str) -> ConnectionItem | None:
    response = _get_item(
        db_table.table(), Key={"PK": connection_pk(connection_id), "SK": "META"}
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
    if any(
        updates[name] != existing.get(name)
        for name in (INDEX_SOURCE_FIELDS | set(INDEX_FIELDS)) & updates.keys()
    ):
        # Its places in the indexes follow from these; nothing moves a
        # connection to another person, role or time.
        raise ValueError("a connection's person, role and connection time do not change")
    # A row written before the index keys (#624) gets them with its next
    # refresh: a connection that is never refreshed expires within the TTL.
    updates = {
        **updates,
        **{
            name: value
            for name, value in index_fields(existing).items()
            if existing.get(name) != value
        },
    }
    target = db_table.table()
    owner_id = str(existing.get("owner_id") or existing.get("user_id") or "")
    generation = _generation(owner_id, existing.get("account_fence_generation"), target)
    operations = build_connection_write_transaction(
        item=existing,
        owner_id=owner_id,
        generation=generation,
        mode="update",
        updates=updates,
    )
    db_table.fenced(
        owner_id,
        operations,
        generation=generation,
        rows=owner_registry.rows_after(existing, operations),
        table=target,
    )
    return {**existing, **updates}


def delete_connection(connection_id: str) -> None:
    _delete_item(
        db_table.table(), Key={"PK": connection_pk(connection_id), "SK": "META"}
    )


def list_user_connections(
    user_id: str, *, table: object | None = None
) -> list[ConnectionItem]:
    """One person's connections, expired ones included, from GSI-SweepPending (#624).

    One query of the person's bucket, every page of it, so what it reads follows
    how many connections the person has, not the size of the table or how many
    the whole site has. Eventually consistent: a connection opened a moment ago
    may be missing.
    """
    return [
        dict(item)
        for item in db_table.rows(
            "query",
            table=table or db_table.table(),
            key=_USER_INDEX_KEY,
            IndexName=USER_INDEX,
            KeyConditionExpression=Key("sweep_bucket").eq(user_bucket(user_id)),
        )
        # The row itself says whose it is; the bucket only found it.
        if item.get("entity_type") == CONNECTION_ENTITY and item.get("user_id") == user_id
    ]


def list_role_connections(role: str, *, table: object | None = None) -> list[ConnectionItem]:
    """Every connection of one role, expired ones included, from GSI-Listing (#624).

    One query of the role's list, every page of it: what it reads follows how
    many connections the role has, not the size of the table. Eventually
    consistent.
    """
    return [
        dict(item)
        for item in db_table.rows(
            "query",
            table=table or db_table.table(),
            key=_ROLE_INDEX_KEY,
            IndexName=ROLE_INDEX,
            KeyConditionExpression=Key("listing").eq(role_listing(role)),
        )
        if item.get("entity_type") == CONNECTION_ENTITY and item.get("role") == role
    ]


def list_connections(limit: int = 200) -> list[ConnectionItem]:
    return db_table.rows(
        "scan",
        table=db_table.table(),
        want=limit,
        FilterExpression=Attr("entity_type").eq(CONNECTION_ENTITY),
    )


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
    target = table or db_table.table()
    current = cursor
    seen: set[tuple[str, str]] = set()
    found: list[ConnectionItem] = []
    scanned = 0
    for page in account_deletion_repo.sweep_pages(
        "connection",
        table=target,
        cursor=cursor,
        page_limit=100,
        maximum_pages=max(maximum_pages, 1),
    ):
        items = page.items
        scanned += len(items)
        found.extend(
            dict(item)
            for item in items
            if item.get("entity_type") == CONNECTION_ENTITY
            and data_catalog.owns(item, account_deletion_repo.deletion_account(owner_id))
        )
        if page.last_key is None:
            return ConnectionPrivatePage(tuple(found), None, scanned)
        current = page.last_key
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
    target = table or db_table.table()
    hook = getattr(target, "delete_connection_for_account", None)
    if callable(hook):
        hook(dict(item), owner_id, generation)
        return
    db_table.transact(
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
