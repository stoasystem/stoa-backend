"""DynamoDB access patterns for moderation cases."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from stoa.db.dynamodb import get_table


def put_case(item: dict[str, Any]) -> None:
    table = get_table()
    table.put_item(Item={"PK": f"MODERATION#{item['case_id']}", "SK": "SUMMARY", **item})


def put_event(case_id: str, event: dict[str, Any]) -> None:
    table = get_table()
    table.put_item(Item={"PK": f"MODERATION#{case_id}", "SK": f"EVENT#{event['event_id']}", **event})


def get_case(case_id: str) -> dict[str, Any] | None:
    table = get_table()
    resp = table.get_item(Key={"PK": f"MODERATION#{case_id}", "SK": "SUMMARY"})
    return resp.get("Item")


def list_case_events(case_id: str, limit: int = 100) -> list[dict[str, Any]]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"MODERATION#{case_id}") & Key("SK").begins_with("EVENT#"),
        Limit=limit,
        ScanIndexForward=True,
    )
    return resp.get("Items", [])


def list_cases(limit: int = 50) -> list[dict[str, Any]]:
    table = get_table()
    resp = table.scan(
        FilterExpression=Attr("entity_type").eq("moderation_case"),
        Limit=limit,
    )
    return resp.get("Items", [])


def update_case(case_id: str, attrs: dict[str, Any]) -> dict[str, Any] | None:
    if not attrs:
        return get_case(case_id)
    table = get_table()
    names = {f"#{key}": key for key in attrs}
    values = {f":{key}": value for key, value in attrs.items()}
    expression = "SET " + ", ".join(f"#{key} = :{key}" for key in attrs)
    resp = table.update_item(
        Key={"PK": f"MODERATION#{case_id}", "SK": "SUMMARY"},
        UpdateExpression=expression,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")
