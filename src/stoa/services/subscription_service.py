"""Subscription operations for manual and provider-managed billing workflows."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from boto3.dynamodb.types import TypeSerializer
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from fastapi import HTTPException

from stoa.config import Settings
from stoa.db.dynamodb import get_table
from stoa.db.repositories import user_repo
from stoa.models.user import SubscriptionTier
from stoa.services import notification_service


REQUEST_ENTITY = "subscription_request"
OPEN_GUARD_ENTITY = "subscription_request_open_guard"
BILLING_ENTITY = "subscription_billing"
BILLING_EVENT_ENTITY = "subscription_billing_event"
BILLING_EVENT_DEDUPE_ENTITY = "subscription_billing_event_dedupe"
REQUEST_STATUSES = {"requested", "in_review", "approved", "applied", "rejected", "cancelled"}
OPEN_STATUSES = {"requested", "in_review", "approved"}
TERMINAL_STATUSES = {"applied", "rejected", "cancelled"}
REQUEST_TYPES = {"upgrade", "downgrade", "cancel"}
BILLING_STATUSES = {
    "none",
    "checkout_pending",
    "active",
    "past_due",
    "canceled",
    "payment_failed",
    "manual_override",
    "provider_unknown",
}
PROVIDER_EVENT_TYPES = {
    "checkout.session.completed",
    "checkout.session.expired",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
    "customer.updated",
}

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
    billing = _billing_response(_get_billing_item(parent_id), parent_id=parent_id)
    if billing["status"] == "none":
        billing["subscriptionTier"] = current_tier
    return {
        "parentId": parent_id,
        "currentTier": current_tier,
        "plans": PLAN_BENEFITS,
        "pendingRequest": _request_response(_latest_open_request(parent_id)),
        "billing": billing,
    }


def create_checkout_session(
    *,
    parent_id: str,
    requested_tier: str,
    success_url: str | None,
    cancel_url: str | None,
    settings: Settings,
) -> dict[str, Any]:
    profile = _require_parent(parent_id)
    requested_tier = _normalize_tier(requested_tier)
    if requested_tier == SubscriptionTier.FREE.value:
        raise HTTPException(status_code=400, detail="Checkout is only available for paid tiers")

    provider_mode = _provider_mode(settings)
    price_id = _price_id_for_tier(requested_tier, settings)
    now = now_iso()
    existing = _get_billing_item(parent_id) or {}
    customer_id = existing.get("provider_customer_id") or f"cus_test_{uuid4().hex[:24]}"
    session_id = f"cs_{provider_mode}_{uuid4().hex}"
    checkout_url = _checkout_url(session_id)
    item = {
        **_billing_key(parent_id),
        "entity_type": BILLING_ENTITY,
        "parent_id": parent_id,
        "subscription_tier": _normalize_tier(profile.get("subscription_tier")),
        "requested_tier": requested_tier,
        "billing_provider": "stripe",
        "billing_mode": provider_mode,
        "billing_status": "checkout_pending",
        "provider_customer_id": customer_id,
        "provider_subscription_id": existing.get("provider_subscription_id"),
        "provider_price_id": price_id,
        "checkout_session_id": session_id,
        "checkout_url": checkout_url,
        "success_url": _safe_url(success_url) or settings.stripe_checkout_success_url,
        "cancel_url": _safe_url(cancel_url) or settings.stripe_checkout_cancel_url,
        "current_period_start": existing.get("current_period_start"),
        "current_period_end": existing.get("current_period_end"),
        "cancel_at_period_end": bool(existing.get("cancel_at_period_end") or False),
        "last_provider_event_id": existing.get("last_provider_event_id"),
        "last_provider_event_type": existing.get("last_provider_event_type"),
        "last_provider_event_at": existing.get("last_provider_event_at"),
        "manual_override_at": existing.get("manual_override_at"),
        "manual_override_by": existing.get("manual_override_by"),
        "manual_override_source": existing.get("manual_override_source"),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
    }
    get_table().put_item(Item=item)
    _put_billing_event(
        parent_id,
        {
            "event_id": f"local_checkout_{session_id}",
            "event_type": "checkout_session_created",
            "event_at": now,
            "provider": "stripe",
            "provider_mode": provider_mode,
            "billing_status": "checkout_pending",
            "requested_tier": requested_tier,
            "provider_session_id": session_id,
        },
    )
    return {
        "parentId": parent_id,
        "checkoutSessionId": session_id,
        "checkoutUrl": checkout_url,
        "provider": "stripe",
        "mode": provider_mode,
        "requestedTier": requested_tier,
        "billingStatus": "checkout_pending",
    }


def get_parent_billing(parent_id: str) -> dict[str, Any]:
    profile = _require_parent(parent_id)
    item = _get_billing_item(parent_id)
    response = _billing_response(item, parent_id=parent_id, include_events=True)
    if response["status"] == "none":
        response["subscriptionTier"] = _normalize_tier(profile.get("subscription_tier"))
    return response


def list_admin_billing(
    *,
    limit: int = 50,
    parent_id: str | None = None,
    billing_status: str | None = None,
    billing_provider: str | None = None,
) -> list[dict[str, Any]]:
    if billing_status is not None:
        _require_choice(billing_status, BILLING_STATUSES, "billing_status")
    scan_kwargs: dict[str, Any] = dict(
        FilterExpression="entity_type = :entity",
        ExpressionAttributeValues={":entity": BILLING_ENTITY},
    )
    items: list[dict[str, Any]] = []
    while True:
        response = get_table().scan(**scan_kwargs)
        items.extend(
            item
            for item in response.get("Items", [])
            if item.get("SK") == "SUMMARY"
            and _matches(item, "parent_id", parent_id)
            and _matches(item, "billing_status", billing_status)
            and _matches(item, "billing_provider", billing_provider)
        )
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return [
        _billing_response(item, parent_id=str(item.get("parent_id") or ""), include_events=True)
        for item in sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)[:limit]
    ]


def get_admin_billing(parent_id: str) -> dict[str, Any]:
    profile = _require_parent(parent_id)
    response = _billing_response(_get_billing_item(parent_id), parent_id=parent_id, include_events=True)
    if response["status"] == "none":
        response["subscriptionTier"] = _normalize_tier(profile.get("subscription_tier"))
    return response


def handle_stripe_webhook(
    *,
    payload: bytes,
    signature_header: str | None,
    settings: Settings,
) -> dict[str, Any]:
    event = _parse_provider_event(payload, signature_header, settings)
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Provider event id and type are required")
    if event_type not in PROVIDER_EVENT_TYPES:
        return {"received": True, "ignored": True, "eventId": event_id, "eventType": event_type}

    event_object = ((event.get("data") or {}).get("object") or {})
    if not isinstance(event_object, dict):
        raise HTTPException(status_code=400, detail="Provider event object is required")

    parent_id = _parent_id_from_provider_object(event_object)
    if not parent_id:
        parent_id = _find_parent_id_for_provider_object(event_object)
    if not parent_id:
        raise HTTPException(status_code=400, detail="Unable to resolve parent for provider event")
    _require_parent(parent_id)

    existing = _get_billing_item(parent_id) or {}
    if _provider_event_seen(event_id):
        return {
            "received": True,
            "deduplicated": True,
            "eventId": event_id,
            "eventType": event_type,
            "parentId": parent_id,
            "billingStatus": existing.get("billing_status") or "none",
        }

    now = now_iso()
    transition = _billing_transition(event_type, event_object, existing)
    updated = _apply_billing_transition(
        parent_id=parent_id,
        event_id=event_id,
        event_type=event_type,
        event_created=event.get("created"),
        event_object=event_object,
        transition=transition,
        existing=existing,
        now=now,
    )
    return {
        "received": True,
        "deduplicated": False,
        "eventId": event_id,
        "eventType": event_type,
        "parentId": parent_id,
        "billingStatus": updated.get("billing_status"),
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
    _record_manual_override(
        parent_id=parent_id,
        requested_tier=requested_tier,
        actor_id=actor,
        source_request_id=request_id,
        at=now,
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


def _billing_key(parent_id: str) -> dict[str, str]:
    return {"PK": f"SUBSCRIPTION_BILLING#{parent_id}", "SK": "SUMMARY"}


def _billing_event_sk(at: str, event_id: str) -> str:
    return f"EVENT#{at}#{event_id}"


def _provider_event_key(event_id: str) -> dict[str, str]:
    return {"PK": f"BILLING_PROVIDER_EVENT#stripe#{event_id}", "SK": "SUMMARY"}


def _get_billing_item(parent_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(Key=_billing_key(parent_id))
    item = response.get("Item")
    return dict(item) if item else None


def _list_billing_events(parent_id: str, limit: int = 25) -> list[dict[str, Any]]:
    response = get_table().query(
        KeyConditionExpression=Key("PK").eq(_billing_key(parent_id)["PK"]) & Key("SK").begins_with("EVENT#"),
    )
    events = sorted(response.get("Items", []), key=lambda item: item.get("event_at", ""), reverse=True)
    return events[:limit]


def _billing_response(
    item: dict[str, Any] | None,
    *,
    parent_id: str,
    include_events: bool = False,
) -> dict[str, Any]:
    if item is None:
        response = {
            "parentId": parent_id,
            "provider": None,
            "mode": "manual",
            "status": "none",
            "subscriptionTier": SubscriptionTier.FREE.value,
            "requestedTier": None,
            "providerCustomerId": None,
            "providerSubscriptionId": None,
            "providerPriceId": None,
            "checkoutSessionId": None,
            "checkoutUrl": None,
            "currentPeriodStart": None,
            "currentPeriodEnd": None,
            "cancelAtPeriodEnd": False,
            "lastProviderEventId": None,
            "lastProviderEventType": None,
            "lastProviderEventAt": None,
            "manualOverrideAt": None,
            "manualOverrideBy": None,
            "manualOverrideSource": None,
            "updatedAt": None,
        }
    else:
        response = {
            "parentId": parent_id,
            "provider": item.get("billing_provider"),
            "mode": item.get("billing_mode") or "manual",
            "status": item.get("billing_status") or "none",
            "subscriptionTier": item.get("subscription_tier") or SubscriptionTier.FREE.value,
            "requestedTier": item.get("requested_tier"),
            "providerCustomerId": item.get("provider_customer_id"),
            "providerSubscriptionId": item.get("provider_subscription_id"),
            "providerPriceId": item.get("provider_price_id"),
            "checkoutSessionId": item.get("checkout_session_id"),
            "checkoutUrl": item.get("checkout_url"),
            "currentPeriodStart": item.get("current_period_start"),
            "currentPeriodEnd": item.get("current_period_end"),
            "cancelAtPeriodEnd": bool(item.get("cancel_at_period_end") or False),
            "lastProviderEventId": item.get("last_provider_event_id"),
            "lastProviderEventType": item.get("last_provider_event_type"),
            "lastProviderEventAt": item.get("last_provider_event_at"),
            "manualOverrideAt": item.get("manual_override_at"),
            "manualOverrideBy": item.get("manual_override_by"),
            "manualOverrideSource": item.get("manual_override_source"),
            "updatedAt": item.get("updated_at"),
        }
    if include_events:
        response["events"] = [
            {
                "eventId": event.get("event_id"),
                "eventAt": event.get("event_at"),
                "eventType": event.get("event_type"),
                "provider": event.get("provider"),
                "providerMode": event.get("provider_mode"),
                "billingStatus": event.get("billing_status"),
                "requestedTier": event.get("requested_tier"),
                "providerEventId": event.get("provider_event_id"),
            }
            for event in _list_billing_events(parent_id)
        ]
    return response


def _provider_mode(settings: Settings) -> str:
    if settings.stripe_live_charges_enabled and settings.is_production:
        return "live"
    return "test"


def _price_id_for_tier(tier: str, settings: Settings) -> str:
    configured = {
        SubscriptionTier.STANDARD.value: settings.stripe_standard_price_id,
        SubscriptionTier.PREMIUM.value: settings.stripe_premium_price_id,
    }[tier]
    return configured or f"price_test_stoa_{tier}_monthly"


def _checkout_url(session_id: str) -> str:
    return f"https://checkout.stripe.com/c/pay/{session_id}"


def _safe_url(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not (cleaned.startswith("https://") or cleaned.startswith("http://localhost")):
        raise HTTPException(status_code=400, detail="Checkout return URL must use HTTPS or localhost")
    return cleaned


def _put_billing_event(parent_id: str, event: dict[str, Any]) -> None:
    item = {
        **event,
        "PK": _billing_key(parent_id)["PK"],
        "SK": _billing_event_sk(str(event["event_at"]), str(event["event_id"])),
        "entity_type": BILLING_EVENT_ENTITY,
        "parent_id": parent_id,
    }
    get_table().put_item(Item=item)


def _provider_event_seen(event_id: str) -> bool:
    return bool(get_table().get_item(Key=_provider_event_key(event_id)).get("Item"))


def _parse_provider_event(
    payload: bytes,
    signature_header: str | None,
    settings: Settings,
) -> dict[str, Any]:
    if settings.stripe_webhook_secret:
        _verify_stripe_signature(payload, signature_header, settings.stripe_webhook_secret)
    elif settings.is_production:
        raise HTTPException(status_code=400, detail="Stripe webhook signing secret is required")
    try:
        event = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid provider event payload") from exc
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Provider event must be a JSON object")
    return event


def _verify_stripe_signature(payload: bytes, signature_header: str | None, secret: str) -> None:
    if not signature_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")
    parts: dict[str, list[str]] = {}
    for raw_part in signature_header.split(","):
        if "=" not in raw_part:
            continue
        key, value = raw_part.split("=", 1)
        parts.setdefault(key.strip(), []).append(value.strip())
    timestamp_values = parts.get("t") or []
    signatures = parts.get("v1") or []
    if not timestamp_values or not signatures:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature header")
    try:
        timestamp = int(timestamp_values[0])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature timestamp") from exc
    if abs(time.time() - timestamp) > 300:
        raise HTTPException(status_code=400, detail="Stripe signature timestamp is outside tolerance")
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise HTTPException(status_code=400, detail="Stripe signature verification failed")


def _parent_id_from_provider_object(event_object: dict[str, Any]) -> str | None:
    metadata = event_object.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return (
        metadata.get("stoa_parent_id")
        or metadata.get("parent_id")
        or event_object.get("client_reference_id")
    )


def _find_parent_id_for_provider_object(event_object: dict[str, Any]) -> str | None:
    customer_id = event_object.get("customer")
    subscription_id = event_object.get("subscription") or event_object.get("id")
    session_id = event_object.get("id") if str(event_object.get("object") or "") == "checkout.session" else None
    response = get_table().scan(
        FilterExpression="entity_type = :entity",
        ExpressionAttributeValues={":entity": BILLING_ENTITY},
    )
    for item in response.get("Items", []):
        if item.get("SK") != "SUMMARY":
            continue
        if customer_id and item.get("provider_customer_id") == customer_id:
            return str(item.get("parent_id"))
        if subscription_id and item.get("provider_subscription_id") == subscription_id:
            return str(item.get("parent_id"))
        if session_id and item.get("checkout_session_id") == session_id:
            return str(item.get("parent_id"))
    return None


def _billing_transition(
    event_type: str,
    event_object: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    metadata = event_object.get("metadata") if isinstance(event_object.get("metadata"), dict) else {}
    requested_tier = _normalize_tier(metadata.get("requested_tier") or existing.get("requested_tier"))
    status = existing.get("billing_status") or "none"
    if event_type == "checkout.session.completed":
        status = "active"
    elif event_type == "checkout.session.expired":
        status = "canceled"
    elif event_type in {"customer.subscription.created", "customer.subscription.updated"}:
        status = _status_from_provider_subscription(event_object.get("status"))
    elif event_type == "customer.subscription.deleted":
        status = "canceled"
    elif event_type == "invoice.paid":
        status = "active"
    elif event_type == "invoice.payment_failed":
        status = "payment_failed"
    elif event_type == "customer.updated":
        status = existing.get("billing_status") or "provider_unknown"
    return {
        "billing_status": status,
        "requested_tier": requested_tier,
        "provider_customer_id": event_object.get("customer") or existing.get("provider_customer_id"),
        "provider_subscription_id": event_object.get("subscription")
        or (event_object.get("id") if str(event_object.get("object") or "") == "subscription" else None)
        or existing.get("provider_subscription_id"),
        "provider_price_id": _price_from_provider_object(event_object) or existing.get("provider_price_id"),
        "checkout_session_id": event_object.get("id")
        if str(event_object.get("object") or "") == "checkout.session"
        else existing.get("checkout_session_id"),
        "current_period_start": _timestamp_to_iso(event_object.get("current_period_start"))
        or existing.get("current_period_start"),
        "current_period_end": _timestamp_to_iso(event_object.get("current_period_end"))
        or existing.get("current_period_end"),
        "cancel_at_period_end": bool(event_object.get("cancel_at_period_end") or False),
    }


def _status_from_provider_subscription(status: Any) -> str:
    return {
        "trialing": "active",
        "active": "active",
        "past_due": "past_due",
        "unpaid": "payment_failed",
        "canceled": "canceled",
        "incomplete": "checkout_pending",
        "incomplete_expired": "canceled",
    }.get(str(status or ""), "provider_unknown")


def _price_from_provider_object(event_object: dict[str, Any]) -> str | None:
    price = event_object.get("price")
    if isinstance(price, dict):
        return price.get("id")
    items = ((event_object.get("items") or {}).get("data") or [])
    if items and isinstance(items[0], dict):
        nested_price = items[0].get("price")
        if isinstance(nested_price, dict):
            return nested_price.get("id")
    return None


def _timestamp_to_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _apply_billing_transition(
    *,
    parent_id: str,
    event_id: str,
    event_type: str,
    event_created: Any,
    event_object: dict[str, Any],
    transition: dict[str, Any],
    existing: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    current_status = existing.get("billing_status")
    manual_override_active = current_status == "manual_override"
    status = current_status if manual_override_active else transition["billing_status"]
    tier = existing.get("subscription_tier") or SubscriptionTier.FREE.value
    if not manual_override_active and status == "active":
        tier = transition["requested_tier"]
    elif not manual_override_active and status == "canceled":
        tier = SubscriptionTier.FREE.value

    updated = {
        **_billing_key(parent_id),
        "entity_type": BILLING_ENTITY,
        "parent_id": parent_id,
        "subscription_tier": tier,
        "requested_tier": transition["requested_tier"],
        "billing_provider": "stripe",
        "billing_mode": existing.get("billing_mode") or "test",
        "billing_status": status,
        "provider_customer_id": transition.get("provider_customer_id"),
        "provider_subscription_id": transition.get("provider_subscription_id"),
        "provider_price_id": transition.get("provider_price_id"),
        "checkout_session_id": transition.get("checkout_session_id"),
        "checkout_url": existing.get("checkout_url"),
        "success_url": existing.get("success_url"),
        "cancel_url": existing.get("cancel_url"),
        "current_period_start": transition.get("current_period_start"),
        "current_period_end": transition.get("current_period_end"),
        "cancel_at_period_end": transition.get("cancel_at_period_end"),
        "last_provider_event_id": event_id,
        "last_provider_event_type": event_type,
        "last_provider_event_at": _timestamp_to_iso(event_created) or now,
        "manual_override_at": existing.get("manual_override_at"),
        "manual_override_by": existing.get("manual_override_by"),
        "manual_override_source": existing.get("manual_override_source"),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
    }
    event = {
        "PK": updated["PK"],
        "SK": _billing_event_sk(now, event_id),
        "entity_type": BILLING_EVENT_ENTITY,
        "parent_id": parent_id,
        "event_id": f"stripe_{event_id}",
        "provider_event_id": event_id,
        "event_type": event_type,
        "event_at": now,
        "provider": "stripe",
        "provider_mode": updated["billing_mode"],
        "billing_status": status,
        "requested_tier": transition["requested_tier"],
    }
    dedupe = {
        **_provider_event_key(event_id),
        "entity_type": BILLING_EVENT_DEDUPE_ENTITY,
        "provider": "stripe",
        "provider_event_id": event_id,
        "event_type": event_type,
        "parent_id": parent_id,
        "created_at": now,
    }
    operations: list[dict[str, Any]] = [
        {"Put": {"Item": dedupe, "ConditionExpression": "attribute_not_exists(PK)"}},
        {"Put": {"Item": updated}},
        {"Put": {"Item": event, "ConditionExpression": "attribute_not_exists(PK)"}},
    ]
    if not manual_override_active and status in {"active", "canceled"}:
        operations.append(
            {
                "Update": {
                    "Key": {"PK": f"USER#{parent_id}", "SK": "PROFILE"},
                    "UpdateExpression": "SET subscription_tier = :tier",
                    "ExpressionAttributeValues": {":tier": tier},
                    "ConditionExpression": "attribute_exists(PK)",
                }
            }
        )
    try:
        _transact_write(operations)
    except ClientError as exc:
        if _is_conditional_failure(exc):
            return _get_billing_item(parent_id) or updated
        raise
    return updated


def _record_manual_override(
    *,
    parent_id: str,
    requested_tier: str,
    actor_id: str,
    source_request_id: str,
    at: str,
) -> None:
    existing = _get_billing_item(parent_id) or {}
    item = {
        **_billing_key(parent_id),
        "entity_type": BILLING_ENTITY,
        "parent_id": parent_id,
        "subscription_tier": requested_tier,
        "requested_tier": requested_tier,
        "billing_provider": existing.get("billing_provider"),
        "billing_mode": "manual",
        "billing_status": "manual_override",
        "provider_customer_id": existing.get("provider_customer_id"),
        "provider_subscription_id": existing.get("provider_subscription_id"),
        "provider_price_id": existing.get("provider_price_id"),
        "checkout_session_id": existing.get("checkout_session_id"),
        "checkout_url": existing.get("checkout_url"),
        "success_url": existing.get("success_url"),
        "cancel_url": existing.get("cancel_url"),
        "current_period_start": existing.get("current_period_start"),
        "current_period_end": existing.get("current_period_end"),
        "cancel_at_period_end": bool(existing.get("cancel_at_period_end") or False),
        "last_provider_event_id": existing.get("last_provider_event_id"),
        "last_provider_event_type": existing.get("last_provider_event_type"),
        "last_provider_event_at": existing.get("last_provider_event_at"),
        "manual_override_at": at,
        "manual_override_by": actor_id,
        "manual_override_source": source_request_id,
        "created_at": existing.get("created_at") or at,
        "updated_at": at,
    }
    get_table().put_item(Item=item)
    _put_billing_event(
        parent_id,
        {
            "event_id": f"manual_override_{source_request_id}",
            "event_type": "manual_override",
            "event_at": at,
            "provider": item.get("billing_provider") or "manual",
            "provider_mode": "manual",
            "billing_status": "manual_override",
            "requested_tier": requested_tier,
            "provider_event_id": None,
        },
    )


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
