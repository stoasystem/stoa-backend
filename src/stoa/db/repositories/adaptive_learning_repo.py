"""DynamoDB access patterns for adaptive learning memory and assignments."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from stoa.db.dynamodb import get_table


MEMORY_ENTITY = "learning_memory_snapshot"
ASSIGNMENT_ENTITY = "learning_assignment"


def put_memory_snapshot(item: dict[str, Any]) -> None:
    table = get_table()
    table.put_item(
        Item={
            "PK": f"LEARNING_MEMORY#{item['student_id']}",
            "SK": f"SUBJECT#{item['subject']}#TOPIC#{item['topic_id']}",
            "entity_type": MEMORY_ENTITY,
            **item,
        }
    )


def list_memory_snapshots(student_id: str, subject: str | None = None) -> list[dict[str, Any]]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"LEARNING_MEMORY#{student_id}") & Key("SK").begins_with("SUBJECT#")
        )
    )
    items = resp.get("Items", [])
    if subject:
        items = [item for item in items if item.get("subject") == subject]
    return items


def put_assignment(item: dict[str, Any]) -> None:
    table = get_table()
    table.put_item(
        Item={
            "PK": f"ASSIGNMENT#{item['assignment_id']}",
            "SK": "META",
            "entity_type": ASSIGNMENT_ENTITY,
            **item,
        }
    )


def get_assignment(assignment_id: str) -> dict[str, Any] | None:
    table = get_table()
    resp = table.get_item(Key={"PK": f"ASSIGNMENT#{assignment_id}", "SK": "META"})
    return resp.get("Item")


def update_assignment(assignment_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    table = get_table()
    update_expr = "SET " + ", ".join(f"#{key} = :{key}" for key in updates)
    resp = table.update_item(
        Key={"PK": f"ASSIGNMENT#{assignment_id}", "SK": "META"},
        UpdateExpression=update_expr,
        ExpressionAttributeNames={f"#{key}": key for key in updates},
        ExpressionAttributeValues={f":{key}": value for key, value in updates.items()},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def list_assignments(
    *,
    student_id: str,
    status: str | None = None,
    include_archived: bool = False,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    table = get_table()
    filter_expr = Attr("entity_type").eq(ASSIGNMENT_ENTITY) & Attr("student_id").eq(student_id)
    if status:
        filter_expr = filter_expr & Attr("status").eq(status)
    if not include_archived:
        filter_expr = filter_expr & Attr("status").ne("archived")
    scan_kwargs: dict[str, Any] = {"FilterExpression": filter_expr}
    if limit:
        scan_kwargs["Limit"] = limit
    items: list[dict[str, Any]] = []
    while True:
        resp = table.scan(**scan_kwargs)
        items.extend(resp.get("Items", []))
        if limit and len(items) >= limit:
            items = items[:limit]
            break
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)
