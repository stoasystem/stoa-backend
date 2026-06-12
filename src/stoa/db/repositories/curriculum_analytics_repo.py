"""DynamoDB helpers for bounded curriculum quality analytics."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Attr

from stoa.db.dynamodb import get_table


SIGNAL_ENTITY = "curriculum_analytics_signal"
METRIC_ENTITY = "curriculum_analytics_metric"


def put_signal(item: dict[str, Any]) -> None:
    table = get_table()
    table.put_item(
        Item={
            "PK": f"CURRICULUM_SIGNAL#{item['public_id']}",
            "SK": f"SIGNAL#{item['created_at']}#{item['signal_id']}",
            "entity_type": SIGNAL_ENTITY,
            **item,
        }
    )


def increment_metric(item: dict[str, Any]) -> None:
    table = get_table()
    signal_field = f"signal_{item['signal_type']}_count"
    source_field = f"source_{item['source_type']}_count"
    names = {
        "#entity_type": "entity_type",
        "#public_id": "public_id",
        "#content_type": "content_type",
        "#version_id": "version_id",
        "#subject_id": "subject_id",
        "#topic_id": "topic_id",
        "#updated_at": "updated_at",
        "#total_count": "total_count",
        "#signal_count": signal_field,
        "#source_count": source_field,
    }
    values: dict[str, Any] = {
        ":entity_type": METRIC_ENTITY,
        ":public_id": item["public_id"],
        ":content_type": item["content_type"],
        ":version_id": item.get("version_id") or "unknown",
        ":subject_id": item.get("subject_id") or "",
        ":topic_id": item.get("topic_id") or "",
        ":updated_at": item["created_at"],
        ":one": 1,
    }
    table.update_item(
        Key={
            "PK": f"CURRICULUM_METRIC#{item['content_type']}#{item['public_id']}",
            "SK": f"VERSION#{item.get('version_id') or 'unknown'}",
        },
        UpdateExpression=(
            "SET #entity_type = :entity_type, #public_id = :public_id, "
            "#content_type = :content_type, #version_id = :version_id, "
            "#subject_id = :subject_id, #topic_id = :topic_id, #updated_at = :updated_at "
            "ADD #total_count :one, #signal_count :one, #source_count :one"
        ),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def list_metrics(
    *,
    content_type: str | None = None,
    subject_id: str | None = None,
    topic_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    table = get_table()
    filter_expr = Attr("entity_type").eq(METRIC_ENTITY)
    if content_type:
        filter_expr = filter_expr & Attr("content_type").eq(content_type)
    if subject_id:
        filter_expr = filter_expr & Attr("subject_id").eq(subject_id)
    if topic_id:
        filter_expr = filter_expr & Attr("topic_id").eq(topic_id)
    resp = table.scan(FilterExpression=filter_expr, Limit=limit)
    return resp.get("Items", [])

