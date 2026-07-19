"""DynamoDB access patterns for quota-governed usage ledger events."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


PRIVATE_LEARNING_ACTIONS = frozenset(
    {
        "hint_request",
        "practice_teacher_help_request",
        "practice_answer",
        "practice_lesson_completion",
        "assignment_started",
        "assignment_completed",
        "assignment_skipped",
        "assignment_archived",
        "reviewed_assignment_generation",
    }
)


type UsageItem = dict[str, object]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


def _table(candidate: object | None = None) -> object:
    return candidate or get_table()


def _get_item(table: object, **kwargs: object) -> UsageItem:
    if not isinstance(table, _GetTable):
        raise ValueError("usage ledger dependency unavailable")
    return _response(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise ValueError("usage ledger dependency unavailable")
    return table.put_item(**kwargs)


def _query(table: object, **kwargs: object) -> UsageItem:
    if not isinstance(table, _QueryTable):
        raise ValueError("usage ledger dependency unavailable")
    return _response(table.query(**kwargs))


def _update_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _UpdateTable):
        raise ValueError("usage ledger dependency unavailable")
    return table.update_item(**kwargs)


def _response(value: object) -> UsageItem:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("usage ledger dependency unavailable")
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _atomic_table(table: object) -> bool:
    return callable(getattr(table, "transact_account_deletion", None)) or bool(
        getattr(getattr(table, "meta", None), "client", None)
        and getattr(table, "name", None)
    )


def put_usage_event(
    event: UsageItem,
    *,
    account_fence_generation: int | None = None,
    table: object | None = None,
) -> bool:
    """Persist one usage ledger event, returning False when it already exists."""
    target = _table(table)
    if account_fence_generation is None and event.get("action") in PRIVATE_LEARNING_ACTIONS:
        owner_id = str(event.get("student_id") or "")
        if not owner_id:
            raise ValueError("student_id is required for private learning usage")
        if _atomic_table(target):
            fence = account_deletion_repo.require_active_account_fence(
                owner_id, table=target
            )
            account_fence_generation = int(fence["generation"])
        else:
            account_fence_generation = 1
    if account_fence_generation is not None:
        owner_id = str(event.get("student_id") or "")
        if not owner_id:
            raise ValueError("student_id is required for a fenced usage event")
        event = {
            **event,
            "owner_id": owner_id,
            "account_fence_generation": account_fence_generation,
        }
        if not _atomic_table(target):
            try:
                _put_item(target,
                    Item=event,
                    ConditionExpression="attribute_not_exists(PK)",
                )
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                    return False
                raise
            return True
        try:
            account_deletion_repo.transact(
                [
                    account_deletion_repo.active_fence_condition(
                        owner_id, account_fence_generation
                    ),
                    {
                        "Put": {
                            "Item": event,
                            "ConditionExpression": (
                                "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                            ),
                        }
                    },
                ],
                table=target,
            )
            return True
        except account_deletion_repo.AccountDeletionConflict:
            return False
    try:
        _put_item(target,
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
) -> UsageItem | None:
    """Read a usage event by its deterministic idempotency key."""
    response = _get_item(_table(),
        Key={
            "PK": f"USAGE_LEDGER#{student_id}",
            "SK": _event_sk(action=action, quota_period=quota_period, idempotency_key=idempotency_key),
        }
    )
    item = response.get("Item")
    return _response(item) if item is not None else None


def list_usage_events(
    *,
    student_id: str,
    action: str,
    quota_period: str,
    limit: int = 500,
) -> list[UsageItem]:
    """List usage events for one student/action/period."""
    table = _table()
    prefix = f"EVENT#{action}#{quota_period}#"
    kwargs: dict[str, object] = {
        "KeyConditionExpression": Key("PK").eq(f"USAGE_LEDGER#{student_id}")
        & Key("SK").begins_with(prefix),
        "Limit": limit,
    }
    items: list[UsageItem] = []
    while True:
        response = _query(table, **kwargs)
        raw_items = response.get("Items", [])
        if not isinstance(raw_items, list) or any(not isinstance(item, dict) for item in raw_items):
            raise ValueError("usage ledger dependency unavailable")
        items.extend(_response(item) for item in raw_items)
        last_key = response.get("LastEvaluatedKey")
        if not last_key or len(items) >= limit:
            return items[:limit]
        kwargs["ExclusiveStartKey"] = last_key


def get_daily_question_counter(student_id: str, day: str) -> UsageItem | None:
    """Read the existing atomic daily question counter row."""
    return get_daily_usage_counter(student_id=student_id, counter_prefix="QUESTION", day=day)


def get_daily_usage_counter(*, student_id: str, counter_prefix: str, day: str) -> UsageItem | None:
    """Read an existing daily usage counter row by counter prefix."""
    response = _get_item(
        _table(),
        Key={"PK": f"USAGE#{student_id}", "SK": f"{counter_prefix}#{day}"},
    )
    item = response.get("Item")
    return _response(item) if item is not None else None


def set_daily_question_counter(
    *,
    student_id: str,
    day: str,
    count: int,
    expires_at: int,
) -> None:
    """Repair a missing or stale daily question counter from ledger totals."""
    _update_item(_table(),
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
