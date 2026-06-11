"""DynamoDB access patterns for notification events and assistance seeds."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Attr

from stoa.db.dynamodb import get_table


NOTIFICATION_ENTITY = "notification_event"
SUMMARY_SEED_ENTITY = "teacher_assistance_summary_seed"
PREFERENCE_ENTITY = "notification_preference"


def notification_pk(event_id: str) -> str:
    return f"NOTIFICATION#{event_id}"


def preference_pk(user_id: str) -> str:
    return f"NOTIFICATION_PREF#{user_id}"


def summary_seed_pk(summary_id: str) -> str:
    return f"ASSISTANCE_SUMMARY#{summary_id}"


def put_event(item: dict[str, Any]) -> None:
    get_table().put_item(Item={**item, "PK": notification_pk(item["event_id"]), "SK": "META"})


def get_event(event_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(Key={"PK": notification_pk(event_id), "SK": "META"})
    return response.get("Item")


def update_event(event_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    existing = get_event(event_id)
    if not existing:
        return None
    if not updates:
        return existing
    names = {f"#{key}": key for key in updates}
    values = {f":{key}": value for key, value in updates.items()}
    get_table().update_item(
        Key={"PK": notification_pk(event_id), "SK": "META"},
        UpdateExpression="SET " + ", ".join(f"#{key} = :{key}" for key in updates),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    return {**existing, **updates}


def list_events(limit: int = 100) -> list[dict[str, Any]]:
    response = get_table().scan(
        FilterExpression=Attr("entity_type").eq(NOTIFICATION_ENTITY),
        Limit=limit,
    )
    return response.get("Items", [])


def put_preferences(item: dict[str, Any]) -> None:
    get_table().put_item(Item={**item, "PK": preference_pk(item["user_id"]), "SK": "META"})


def get_preferences(user_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(Key={"PK": preference_pk(user_id), "SK": "META"})
    return response.get("Item")


def put_summary_seed(item: dict[str, Any]) -> None:
    get_table().put_item(Item={**item, "PK": summary_seed_pk(item["summary_id"]), "SK": "META"})
