"""DynamoDB access patterns for quota-governed usage ledger events."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


def put_usage_event(event: dict[str, Any]) -> bool:
    """Persist one usage ledger event, returning False when it already exists."""
    table = get_table()
    try:
        table.put_item(
            Item=event,
            ConditionExpression="attribute_not_exists(PK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_usage_event(
    *,
    student_id: str,
    action: str,
    quota_period: str,
    idempotency_key: str,
) -> dict[str, Any] | None:
    """Read a usage event by its deterministic idempotency key."""
    response = get_table().get_item(
        Key={
            "PK": f"USAGE_LEDGER#{student_id}",
            "SK": _event_sk(action=action, quota_period=quota_period, idempotency_key=idempotency_key),
        }
    )
    item = response.get("Item")
    return dict(item) if item else None


def list_usage_events(
    *,
    student_id: str,
    action: str,
    quota_period: str,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """List usage events for one student/action/period."""
    table = get_table()
    prefix = f"EVENT#{action}#{quota_period}#"
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("PK").eq(f"USAGE_LEDGER#{student_id}")
        & Key("SK").begins_with(prefix),
        "Limit": limit,
    }
    items: list[dict[str, Any]] = []
    while True:
        response = table.query(**kwargs)
        items.extend(dict(item) for item in response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key or len(items) >= limit:
            return items[:limit]
        kwargs["ExclusiveStartKey"] = last_key


def get_daily_question_counter(student_id: str, day: str) -> dict[str, Any] | None:
    """Read the existing atomic daily question counter row."""
    return get_daily_usage_counter(student_id=student_id, counter_prefix="QUESTION", day=day)


def get_daily_usage_counter(*, student_id: str, counter_prefix: str, day: str) -> dict[str, Any] | None:
    """Read an existing daily usage counter row by counter prefix."""
    response = get_table().get_item(Key={"PK": f"USAGE#{student_id}", "SK": f"{counter_prefix}#{day}"})
    item = response.get("Item")
    return dict(item) if item else None


def set_daily_question_counter(
    *,
    student_id: str,
    day: str,
    count: int,
    expires_at: int,
) -> None:
    """Repair a missing or stale daily question counter from ledger totals."""
    get_table().update_item(
        Key={"PK": f"USAGE#{student_id}", "SK": f"QUESTION#{day}"},
        UpdateExpression=(
            "SET #c = :count, #ttl = if_not_exists(#ttl, :exp), "
            "usage_type = if_not_exists(usage_type, :usage_type)"
        ),
        ExpressionAttributeNames={"#c": "count", "#ttl": "expires_at"},
        ExpressionAttributeValues={
            ":count": count,
            ":exp": expires_at,
            ":usage_type": "daily_question_submission",
        },
    )


def _event_sk(*, action: str, quota_period: str, idempotency_key: str) -> str:
    return f"EVENT#{action}#{quota_period}#{idempotency_key}"
