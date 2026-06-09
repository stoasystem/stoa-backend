"""DynamoDB access patterns for WebSocket connection records."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Attr

from stoa.db.dynamodb import get_table


CONNECTION_ENTITY = "websocket_connection"


def connection_pk(connection_id: str) -> str:
    return f"WS_CONN#{connection_id}"


def put_connection(item: dict[str, Any]) -> None:
    get_table().put_item(
        Item={**item, "PK": connection_pk(item["connection_id"]), "SK": "META"}
    )


def get_connection(connection_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(Key={"PK": connection_pk(connection_id), "SK": "META"})
    return response.get("Item")


def update_connection(connection_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    existing = get_connection(connection_id)
    if not existing:
        return None
    if not updates:
        return existing
    names = {f"#{key}": key for key in updates}
    values = {f":{key}": value for key, value in updates.items()}
    get_table().update_item(
        Key={"PK": connection_pk(connection_id), "SK": "META"},
        UpdateExpression="SET " + ", ".join(f"#{key} = :{key}" for key in updates),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    return {**existing, **updates}


def delete_connection(connection_id: str) -> None:
    get_table().delete_item(Key={"PK": connection_pk(connection_id), "SK": "META"})


def list_connections(limit: int = 200) -> list[dict[str, Any]]:
    response = get_table().scan(
        FilterExpression=Attr("entity_type").eq(CONNECTION_ENTITY),
        Limit=limit,
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
