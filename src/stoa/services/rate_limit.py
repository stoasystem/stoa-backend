"""Shared rate-limiting helpers using DynamoDB atomic counters."""
from datetime import datetime, timezone
from fastapi import HTTPException, status
from stoa.config import settings
from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _increment_and_check(
    pk: str,
    sk: str,
    limit: int,
    label: str,
    *,
    owner_id: str | None = None,
    account_fence_generation: int | None = None,
) -> dict:
    """Atomically increment a usage counter and raise 429 if the limit is hit."""
    table = get_table()
    expires_at_value = int((datetime.now(timezone.utc).timestamp()) + 172800)
    atomic = callable(getattr(table, "transact_account_deletion", None)) or bool(
        getattr(getattr(table, "meta", None), "client", None)
        and getattr(table, "name", None)
    )
    if owner_id and atomic:
        if account_fence_generation is None:
            fence = account_deletion_repo.require_active_account_fence(
                owner_id, table=table
            )
            account_fence_generation = int(fence["generation"])
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(
                    owner_id, account_fence_generation
                ),
                {
                    "Update": {
                        "Key": {"PK": pk, "SK": sk},
                        "UpdateExpression": (
                            "ADD #c :one SET #ttl=if_not_exists(#ttl,:exp), "
                            "retention_basis=:basis, owner_id=:owner, "
                            "account_fence_generation=:generation"
                        ),
                        "ExpressionAttributeNames": {
                            "#c": "count",
                            "#ttl": "expires_at",
                        },
                        "ExpressionAttributeValues": {
                            ":one": 1,
                            ":exp": expires_at_value,
                            ":basis": "usage_accounting",
                            ":owner": owner_id,
                            ":generation": account_fence_generation,
                        },
                    }
                },
            ],
            table=table,
        )
        resp = table.get_item(Key={"PK": pk, "SK": sk}, ConsistentRead=True)
        resp = {"Attributes": resp.get("Item") or {}}
    else:
        resp = table.update_item(
            Key={"PK": pk, "SK": sk},
            UpdateExpression="ADD #c :one SET #ttl = if_not_exists(#ttl, :exp)",
            ExpressionAttributeNames={"#c": "count", "#ttl": "expires_at"},
            ExpressionAttributeValues={":one": 1, ":exp": expires_at_value},
            ReturnValues="UPDATED_NEW",
        )
    new_count = int(resp["Attributes"].get("count", 1))
    expires_at = int(resp["Attributes"].get("expires_at") or 0)
    if new_count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily {label} limit ({limit}) reached. Try again tomorrow.",
        )
    return {
        "quotaPeriod": sk.split("#", 1)[1] if "#" in sk else _today_utc(),
        "counterKey": f"{pk}/{sk}",
        "counterValue": new_count,
        "limit": limit,
        "expiresAt": expires_at,
    }


def check_and_record_chat(student_id: str, limit: int | None = None) -> dict:
    """Increment today's chat counter; raise 429 if limit exceeded."""
    today = _today_utc()
    return _increment_and_check(
        pk=f"USAGE#{student_id}",
        sk=f"CHAT#{today}",
        limit=limit if limit is not None else settings.daily_chat_message_limit,
        label="chat message",
    )


def check_and_record_hint(student_id: str, challenge_id: str, limit: int | None = None) -> dict:
    """Increment today's hint counter; raise 429 if limit exceeded."""
    today = _today_utc()
    return _increment_and_check(
        pk=f"USAGE#{student_id}",
        sk=f"HINT#{today}",
        limit=limit if limit is not None else settings.daily_hint_limit,
        label="hint",
        owner_id=student_id,
    )
