"""DynamoDB access patterns for reviewed AI teacher tool drafts."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Attr

from stoa.db.dynamodb import get_table


DRAFT_ENTITY = "ai_teacher_draft"


def draft_pk(draft_id: str) -> str:
    return f"AI_TEACHER_DRAFT#{draft_id}"


def put_draft(item: dict[str, Any]) -> None:
    get_table().put_item(Item={**item, "PK": draft_pk(item["draft_id"]), "SK": "META"})


def get_draft(draft_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(Key={"PK": draft_pk(draft_id), "SK": "META"})
    return response.get("Item")


def update_draft(
    draft_id: str,
    updates: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    existing = existing or get_draft(draft_id)
    if not existing:
        return None
    if not updates:
        return existing
    names = {f"#{key}": key for key in updates}
    values = {f":{key}": value for key, value in updates.items()}
    get_table().update_item(
        Key={"PK": draft_pk(draft_id), "SK": "META"},
        UpdateExpression="SET " + ", ".join(f"#{key} = :{key}" for key in updates),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    return {**existing, **updates}


def list_drafts(
    *,
    student_id: str | None = None,
    status: str | None = None,
    draft_type: str | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    filter_expr = Attr("entity_type").eq(DRAFT_ENTITY)
    if student_id is not None:
        filter_expr = filter_expr & Attr("student_id").eq(student_id)
    if status is not None:
        filter_expr = filter_expr & Attr("status").eq(status)
    if draft_type is not None:
        filter_expr = filter_expr & Attr("draft_type").eq(draft_type)
    scan_kwargs: dict[str, Any] = {"FilterExpression": filter_expr}
    if limit:
        scan_kwargs["Limit"] = limit
    items: list[dict[str, Any]] = []
    while True:
        response = get_table().scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        if limit and len(items) >= limit:
            items = items[:limit]
            break
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)
