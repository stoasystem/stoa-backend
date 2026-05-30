"""Shared rate-limiting helpers using DynamoDB atomic counters."""
from datetime import datetime, timezone
from fastapi import HTTPException, status
from stoa.config import settings
from stoa.db.dynamodb import get_table


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _increment_and_check(pk: str, sk: str, limit: int, label: str) -> None:
    """Atomically increment a usage counter and raise 429 if the limit is hit."""
    table = get_table()
    resp = table.update_item(
        Key={"PK": pk, "SK": sk},
        UpdateExpression="ADD #c :one SET #ttl = if_not_exists(#ttl, :exp)",
        ExpressionAttributeNames={"#c": "count", "#ttl": "expires_at"},
        ExpressionAttributeValues={
            ":one": 1,
            # Keep the counter row for 2 days so it naturally expires
            ":exp": int((datetime.now(timezone.utc).timestamp()) + 172800),
        },
        ReturnValues="UPDATED_NEW",
    )
    new_count = int(resp["Attributes"].get("count", 1))
    if new_count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily {label} limit ({limit}) reached. Try again tomorrow.",
        )


def check_and_record_chat(student_id: str) -> None:
    """Increment today's chat counter; raise 429 if limit exceeded."""
    today = _today_utc()
    _increment_and_check(
        pk=f"USAGE#{student_id}",
        sk=f"CHAT#{today}",
        limit=settings.daily_chat_message_limit,
        label="chat message",
    )


def check_and_record_hint(student_id: str, challenge_id: str) -> None:
    """Increment today's hint counter; raise 429 if limit exceeded."""
    today = _today_utc()
    _increment_and_check(
        pk=f"USAGE#{student_id}",
        sk=f"HINT#{today}",
        limit=settings.daily_hint_limit,
        label="hint",
    )
