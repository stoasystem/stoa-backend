"""Manual subscription operations for the MVP billing workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from boto3.dynamodb.types import TypeSerializer
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from fastapi import HTTPException

from stoa.db.dynamodb import get_table
from stoa.db.repositories import user_repo
from stoa.models.user import SubscriptionTier
from stoa.services import notification_service


REQUEST_ENTITY = "subscription_request"
OPEN_GUARD_ENTITY = "subscription_request_open_guard"
REQUEST_STATUSES = {"requested", "in_review", "approved", "applied", "rejected", "cancelled"}
OPEN_STATUSES = {"requested", "in_review", "approved"}
TERMINAL_STATUSES = {"applied", "rejected", "cancelled"}
REQUEST_TYPES = {"upgrade", "downgrade", "cancel"}

ALLOWED_TRANSITIONS = {
    "requested": {"in_review", "approved", "rejected", "cancelled"},
    "in_review": {"approved", "rejected", "cancelled"},
    "approved": {"applied", "rejected", "cancelled"},
    "applied": set(),
    "rejected": set(),
    "cancelled": set(),
}

PLAN_BENEFITS: dict[str, dict[str, Any]] = {
    "free": {
        "label": "Free",
        "dailyAiQuestionLimit": 5,
        "teacherSupport": "none",
        "weeklyReport": "none",
    },
    "standard": {
        "label": "Standard",
        "dailyAiQuestionLimit": 30,
        "teacherSupport": "text_support",
        "weeklyReport": "enabled",
    },
    "premium": {
        "label": "Premium",
        "dailyAiQuestionLimit": 100,
        "teacherSupport": "priority_support",
        "weeklyReport": "enhanced",
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_parent_subscription(parent_id: str) -> dict[str, Any]:
    profile = _require_parent(parent_id)
    current_tier = _normalize_tier(profile.get("subscription_tier"))
    return {
        "parentId": parent_id,
        "currentTier": current_tier,
        "plans": PLAN_BENEFITS,
        "pendingRequest": _request_response(_latest_open_request(parent_id)),
    }


def create_parent_request(
    *,
    parent_id: str,
    request_type: str,
    requested_tier: str | None,
    parent_note: str | None,
    source: str = "parent_portal",
) -> dict[str, Any]:
    profile = _require_parent(parent_id)
    request_type = _require_choice(request_type, REQUEST_TYPES, "request_type")
    current_tier = _normalize_tier(profile.get("subscription_tier"))
    target_tier = _target_tier(request_type, requested_tier)

    if request_type == "upgrade" and _tier_rank(target_tier) <= _tier_rank(current_tier):
        raise HTTPException(status_code=400, detail="Upgrade request must target a higher tier")
    if request_type == "downgrade" and _tier_rank(target_tier) >= _tier_rank(current_tier):
        raise HTTPException(status_code=400, detail="Downgrade request must target a lower tier")
    if request_type == "cancel" and target_tier != SubscriptionTier.FREE.value:
        raise HTTPException(status_code=400, detail="Cancellation requests target the free tier")

    created_at = now_iso()
    request_id = f"subreq-{uuid4().hex}"
    item = {
        "PK": _request_pk(request_id),
        "SK": "SUMMARY",
        "entity_type": REQUEST_ENTITY,
        "request_id": request_id,
        "parent_id": parent_id,
        "student_id": None,
        "current_tier": current_tier,
        "requested_tier": target_tier,
        "request_type": request_type,
        "status": "requested",
        "source": source,
        "parent_note": _clean_note(parent_note),
        "admin_note": None,
        "created_at": created_at,
        "updated_at": created_at,
        "effective_at": None,
        "applied_at": None,
        "applied_by": None,
    }
    event = _event(
        request_id,
        "requested",
        actor_id=parent_id,
        actor_role="parent",
        at=created_at,
        note=item["parent_note"],
        changes={"requested_tier": target_tier, "request_type": request_type},
    )
    item["history"] = [event]
    event_item = {**event, "PK": _request_pk(request_id), "SK": _event_sk(created_at, event["event_id"])}
    guard = {
        **_open_guard_key(parent_id),
        "entity_type": OPEN_GUARD_ENTITY,
        "parent_id": parent_id,
        "request_id": request_id,
        "status": "requested",
        "created_at": created_at,
        "updated_at": created_at,
    }
    try:
        _transact_write(
            [
                {"Put": {"Item": item, "ConditionExpression": "attribute_not_exists(PK)"}},
                {"Put": {"Item": event_item, "ConditionExpression": "attribute_not_exists(PK)"}},
                {"Put": {"Item": guard, "ConditionExpression": "attribute_not_exists(PK)"}},
            ]
        )
    except ClientError as exc:
        if _is_conditional_failure(exc):
            raise HTTPException(
                status_code=409,
                detail="Parent already has an open subscription request",
            ) from exc
        raise
    notification_service.emit_subscription_update(
        request_item=item,
        recipient_id=None,
        recipient_role="admin",
        actor_id=parent_id,
        actor_role="parent",
    )
    return _request_response(item)


def list_parent_requests(parent_id: str, limit: int = 25) -> list[dict[str, Any]]:
    _require_parent(parent_id)
    return [_request_response(item) for item in _list_requests(parent_id=parent_id, limit=limit)]


def list_admin_requests(
    *,
    limit: int = 50,
    status: str | None = None,
    requested_tier: str | None = None,
    parent_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    if status is not None:
        _require_choice(status, REQUEST_STATUSES, "status")
    if requested_tier is not None:
        _normalize_tier(requested_tier)
    return [
        _request_response(item)
        for item in _list_requests(
            limit=limit,
            status=status,
            requested_tier=requested_tier,
            parent_id=parent_id,
            date_from=date_from,
            date_to=date_to,
        )
    ]


def get_request(request_id: str) -> dict[str, Any]:
    item = _get_request_item(request_id)
    item = dict(item)
    item["history"] = _list_events(request_id) or item.get("history") or []
    return _request_response(item)


def update_request_status(
    *,
    request_id: str,
    status: str,
    admin_note: str | None,
    effective_at: str | None,
    user: dict[str, Any],
) -> dict[str, Any]:
    status = _require_choice(status, REQUEST_STATUSES - {"applied"}, "status")
    item = _get_request_item(request_id)
    current = item.get("status", "requested")
    if status == current and not admin_note and not effective_at:
        return get_request(request_id)
    _require_transition(current, status)

    now = now_iso()
    updates: dict[str, Any] = {"status": status, "updated_at": now}
    if admin_note is not None:
        updates["admin_note"] = _clean_note(admin_note)
    if effective_at is not None:
        updates["effective_at"] = effective_at

    event = _event(
        request_id,
        status,
        actor_id=_actor_id(user),
        actor_role=str(user.get("role") or "admin"),
        at=now,
        note=updates.get("admin_note"),
        changes={key: value for key, value in updates.items() if key != "updated_at"},
    )
    updated = _update_request_item(
        item,
        updates,
        event,
        expected_status=current,
        clear_open_guard=status in TERMINAL_STATUSES,
    )
    notification_service.emit_subscription_update(
        request_item=updated,
        recipient_id=str(updated.get("parent_id") or ""),
        recipient_role="parent",
        actor_id=_actor_id(user),
        actor_role=str(user.get("role") or "admin"),
    )
    return _request_response(updated)


def apply_request(
    *,
    request_id: str,
    admin_note: str | None,
    effective_at: str | None,
    user: dict[str, Any],
) -> dict[str, Any]:
    item = _get_request_item(request_id)
    if item.get("status") != "approved":
        raise HTTPException(status_code=409, detail="Only approved subscription requests can be applied")

    parent_id = item.get("parent_id")
    if not parent_id:
        raise HTTPException(status_code=400, detail="Subscription request is missing parent_id")
    _require_parent(parent_id)

    requested_tier = _normalize_tier(item.get("requested_tier"))
    now = now_iso()
    actor = _actor_id(user)
    updates = {
        "status": "applied",
        "updated_at": now,
        "effective_at": effective_at or item.get("effective_at") or now,
        "applied_at": now,
        "applied_by": actor,
    }
    if admin_note is not None:
        updates["admin_note"] = _clean_note(admin_note)
    event = _event(
        request_id,
        "applied",
        actor_id=actor,
        actor_role=str(user.get("role") or "admin"),
        at=now,
        note=updates.get("admin_note"),
        changes={"subscription_tier": requested_tier, "effective_at": updates["effective_at"]},
    )
    updated = _apply_request_item(
        item,
        parent_id=parent_id,
        requested_tier=requested_tier,
        updates=updates,
        event=event,
    )
    notification_service.emit_subscription_update(
        request_item=updated,
        recipient_id=str(updated.get("parent_id") or ""),
        recipient_role="parent",
        actor_id=actor,
        actor_role=str(user.get("role") or "admin"),
    )
    return _request_response(updated)


def _request_pk(request_id: str) -> str:
    return f"SUBSCRIPTION_REQUEST#{request_id}"


def _open_guard_key(parent_id: str) -> dict[str, str]:
    return {"PK": f"SUBSCRIPTION_OPEN#{parent_id}", "SK": "GUARD"}


def _event_sk(at: str, event_id: str) -> str:
    return f"EVENT#{at}#{event_id}"


def _require_parent(parent_id: str) -> dict[str, Any]:
    profile = user_repo.get_user(parent_id)
    if not profile or profile.get("role") != "parent":
        raise HTTPException(status_code=404, detail="Parent profile not found")
    return profile


def _get_request_item(request_id: str) -> dict[str, Any]:
    response = get_table().get_item(Key={"PK": _request_pk(request_id), "SK": "SUMMARY"})
    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Subscription request not found")
    return item


def _list_requests(
    *,
    limit: int,
    status: str | None = None,
    requested_tier: str | None = None,
    parent_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    scan_kwargs: dict[str, Any] = dict(
        FilterExpression="entity_type = :entity",
        ExpressionAttributeValues={":entity": REQUEST_ENTITY},
    )
    items: list[dict[str, Any]] = []
    while True:
        response = get_table().scan(**scan_kwargs)
        items.extend(
            item
            for item in response.get("Items", [])
            if item.get("SK") == "SUMMARY"
            and _matches(item, "status", status)
            and _matches(item, "requested_tier", requested_tier)
            and _matches(item, "parent_id", parent_id)
            and _within_dates(item.get("created_at"), date_from, date_to)
        )
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]


def _latest_open_request(parent_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(Key=_open_guard_key(parent_id))
    guard = response.get("Item")
    if not guard or not guard.get("request_id"):
        return None
    item = _get_request_item(str(guard["request_id"]))
    if item.get("status") in OPEN_STATUSES:
        return item
    return None


def _list_events(request_id: str) -> list[dict[str, Any]]:
    response = get_table().query(
        KeyConditionExpression=Key("PK").eq(_request_pk(request_id)) & Key("SK").begins_with("EVENT#"),
    )
    return sorted(response.get("Items", []), key=lambda item: item.get("event_at", ""))


def _update_request_item(
    item: dict[str, Any],
    updates: dict[str, Any],
    event: dict[str, Any],
    *,
    expected_status: str,
    clear_open_guard: bool,
) -> dict[str, Any]:
    expression_names = {f"#{key}": key for key in updates}
    expression_values = {f":{key}": value for key, value in updates.items()}
    update_expression = "SET " + ", ".join(
        f"#{key} = :{key}" for key in updates
    )
    expression_names["#current_status"] = "status"
    expression_values[":current_status"] = expected_status
    event_item = {**event, "PK": item["PK"], "SK": _event_sk(event["event_at"], event["event_id"])}
    transaction = [
        {
            "Update": {
                "Key": {"PK": item["PK"], "SK": "SUMMARY"},
                "UpdateExpression": update_expression,
                "ExpressionAttributeNames": expression_names,
                "ExpressionAttributeValues": expression_values,
                "ConditionExpression": "#current_status = :current_status",
            }
        },
        {"Put": {"Item": event_item, "ConditionExpression": "attribute_not_exists(PK)"}},
    ]
    if clear_open_guard:
        transaction.append({"Delete": {"Key": _open_guard_key(str(item["parent_id"]))}})
    try:
        _transact_write(transaction)
    except ClientError as exc:
        if _is_conditional_failure(exc):
            raise HTTPException(
                status_code=409,
                detail="Subscription request changed before update could be applied",
            ) from exc
        raise
    updated = {**item, **updates}
    updated["history"] = _list_events(updated["request_id"]) or updated.get("history") or [event]
    return updated


def _apply_request_item(
    item: dict[str, Any],
    *,
    parent_id: str,
    requested_tier: str,
    updates: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    expression_names = {f"#{key}": key for key in updates}
    expression_names["#current_status"] = "status"
    expression_values = {f":{key}": value for key, value in updates.items()}
    expression_values[":current_status"] = "approved"
    expression_values[":tier"] = requested_tier
    update_expression = "SET " + ", ".join(f"#{key} = :{key}" for key in updates)
    event_item = {**event, "PK": item["PK"], "SK": _event_sk(event["event_at"], event["event_id"])}
    try:
        _transact_write(
            [
                {
                    "Update": {
                        "Key": {"PK": f"USER#{parent_id}", "SK": "PROFILE"},
                        "UpdateExpression": "SET subscription_tier = :tier",
                        "ExpressionAttributeValues": {":tier": requested_tier},
                        "ConditionExpression": "attribute_exists(PK)",
                    }
                },
                {
                    "Update": {
                        "Key": {"PK": item["PK"], "SK": "SUMMARY"},
                        "UpdateExpression": update_expression,
                        "ExpressionAttributeNames": expression_names,
                        "ExpressionAttributeValues": expression_values,
                        "ConditionExpression": "#current_status = :current_status",
                    }
                },
                {"Put": {"Item": event_item, "ConditionExpression": "attribute_not_exists(PK)"}},
                {"Delete": {"Key": _open_guard_key(parent_id)}},
            ]
        )
    except ClientError as exc:
        if _is_conditional_failure(exc):
            raise HTTPException(
                status_code=409,
                detail="Subscription request changed before apply could complete",
            ) from exc
        raise
    updated = {**item, **updates}
    updated["history"] = _list_events(updated["request_id"]) or updated.get("history") or [event]
    return updated


def _request_response(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    history = [
        {
            "eventId": event.get("event_id"),
            "eventAt": event.get("event_at"),
            "eventType": event.get("event_type"),
            "actorId": event.get("actor_id"),
            "actorRole": event.get("actor_role"),
            "note": event.get("note"),
            "changes": event.get("changes") or {},
        }
        for event in item.get("history") or []
    ]
    return {
        "requestId": item.get("request_id"),
        "parentId": item.get("parent_id"),
        "studentId": item.get("student_id"),
        "currentTier": item.get("current_tier"),
        "requestedTier": item.get("requested_tier"),
        "requestType": item.get("request_type"),
        "status": item.get("status"),
        "source": item.get("source"),
        "parentNote": item.get("parent_note"),
        "adminNote": item.get("admin_note"),
        "createdAt": item.get("created_at"),
        "updatedAt": item.get("updated_at"),
        "effectiveAt": item.get("effective_at"),
        "appliedAt": item.get("applied_at"),
        "appliedBy": item.get("applied_by"),
        "history": history,
    }


def _event(
    request_id: str,
    event_type: str,
    *,
    actor_id: str,
    actor_role: str,
    at: str,
    note: str | None,
    changes: dict[str, Any],
) -> dict[str, Any]:
    return {
        "entity_type": "subscription_request_event",
        "event_id": f"subevt-{uuid4().hex}",
        "request_id": request_id,
        "event_type": event_type,
        "event_at": at,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "note": _clean_note(note),
        "changes": changes,
    }


def _actor_id(user: dict[str, Any]) -> str:
    return str(user.get("sub") or user.get("username") or "admin")


def _clean_note(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _require_choice(value: str, allowed: set[str], field: str) -> str:
    if value not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid {field}: {value}")
    return value


def _require_transition(current: str, target: str) -> None:
    if current in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="Subscription request is already terminal")
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=400, detail=f"Invalid transition from {current} to {target}")


def _normalize_tier(value: Any) -> str:
    raw = value.value if isinstance(value, SubscriptionTier) else str(value or SubscriptionTier.FREE.value)
    if raw not in {tier.value for tier in SubscriptionTier}:
        raise HTTPException(status_code=400, detail=f"Invalid subscription tier: {raw}")
    return raw


def _target_tier(request_type: str, requested_tier: str | None) -> str:
    if request_type == "cancel":
        return SubscriptionTier.FREE.value if requested_tier is None else _normalize_tier(requested_tier)
    if requested_tier is None:
        raise HTTPException(status_code=400, detail="requested_tier is required")
    return _normalize_tier(requested_tier)


def _tier_rank(value: str) -> int:
    return {
        SubscriptionTier.FREE.value: 0,
        SubscriptionTier.STANDARD.value: 1,
        SubscriptionTier.PREMIUM.value: 2,
    }[value]


def _matches(item: dict[str, Any], field: str, expected: str | None) -> bool:
    return expected is None or item.get(field) == expected


def _within_dates(value: str | None, date_from: str | None, date_to: str | None) -> bool:
    if not value:
        return False
    if date_from and value < date_from:
        return False
    if date_to and value > date_to:
        return False
    return True


def _transact_write(operations: list[dict[str, Any]]) -> None:
    table = get_table()
    if hasattr(table, "transact_write_items"):
        table.transact_write_items(TransactItems=operations)
        return

    table_name = getattr(table, "name", None)
    if not table_name:
        table_name = getattr(table, "table_name", None)
    if not table_name:
        raise RuntimeError("DynamoDB table name is unavailable for transaction")

    serializer = TypeSerializer()
    client_ops: list[dict[str, Any]] = []
    for operation in operations:
        if "Put" in operation:
            put = operation["Put"]
            client_ops.append(
                {
                    "Put": {
                        "TableName": table_name,
                        "Item": _serialize_map(put["Item"], serializer),
                        **_transaction_common(put, serializer),
                    }
                }
            )
        elif "Update" in operation:
            update = operation["Update"]
            client_ops.append(
                {
                    "Update": {
                        "TableName": table_name,
                        "Key": _serialize_map(update["Key"], serializer),
                        "UpdateExpression": update["UpdateExpression"],
                        **_transaction_common(update, serializer),
                    }
                }
            )
        elif "Delete" in operation:
            delete = operation["Delete"]
            client_ops.append(
                {
                    "Delete": {
                        "TableName": table_name,
                        "Key": _serialize_map(delete["Key"], serializer),
                        **_transaction_common(delete, serializer),
                    }
                }
            )
        else:
            raise ValueError(f"Unsupported transaction operation: {operation}")

    table.meta.client.transact_write_items(TransactItems=client_ops)


def _transaction_common(operation: dict[str, Any], serializer: TypeSerializer) -> dict[str, Any]:
    common: dict[str, Any] = {}
    if operation.get("ConditionExpression"):
        common["ConditionExpression"] = operation["ConditionExpression"]
    if operation.get("ExpressionAttributeNames"):
        common["ExpressionAttributeNames"] = operation["ExpressionAttributeNames"]
    if operation.get("ExpressionAttributeValues"):
        common["ExpressionAttributeValues"] = _serialize_map(
            operation["ExpressionAttributeValues"],
            serializer,
        )
    return common


def _serialize_map(values: dict[str, Any], serializer: TypeSerializer) -> dict[str, Any]:
    return {key: serializer.serialize(value) for key, value in values.items()}


def _is_conditional_failure(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") in {
        "ConditionalCheckFailedException",
        "TransactionCanceledException",
    }
