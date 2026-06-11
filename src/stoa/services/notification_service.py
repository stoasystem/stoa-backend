"""In-product notification event helpers."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from stoa.config import settings
from stoa.db.repositories import notification_repo
from stoa.services import websocket_service


EVENT_TYPES = {
    "teacher_requested",
    "teacher_takeover",
    "teacher_reply",
    "moderation_case_update",
    "subscription_request_update",
    "learning_profile_update",
    "assignment_update",
    "weekly_report_update",
}
STATUSES = {"created", "read", "archived", "failed"}
PREFERENCE_CATEGORIES = {
    "learning_updates",
    "teacher_responses",
    "assignments",
    "weekly_reports",
    "admin_operations",
}
PREFERENCE_CHANNELS = {"in_app", "realtime", "email_digest", "push"}
EVENT_CATEGORY_BY_TYPE = {
    "teacher_requested": "teacher_responses",
    "teacher_takeover": "teacher_responses",
    "teacher_reply": "teacher_responses",
    "moderation_case_update": "admin_operations",
    "subscription_request_update": "admin_operations",
    "learning_profile_update": "learning_updates",
    "assignment_update": "assignments",
    "weekly_report_update": "weekly_reports",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_event(
    *,
    recipient_id: str | None,
    recipient_role: str,
    event_type: str,
    target_type: str,
    target_id: str,
    title: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
    actor_id: str | None = None,
    actor_role: str | None = None,
    status: str = "created",
    created_at: str | None = None,
) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported notification event type")
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported notification status")
    if not recipient_role:
        raise HTTPException(status_code=400, detail="Notification recipient role is required")

    category = category_for_event(event_type=event_type, target_type=target_type)
    preferences = get_preferences_for_user(recipient_id) if recipient_id else default_preferences()
    delivery = delivery_decision(
        category=category,
        preferences=preferences,
        realtime_configured=bool(settings.websocket_api_endpoint),
    )
    event_status = status
    if not delivery["channels"]["in_app"]["enabled"] and status == "created":
        event_status = "archived"

    item = {
        "entity_type": notification_repo.NOTIFICATION_ENTITY,
        "event_id": f"notif-{uuid4().hex}",
        "recipient_id": recipient_id,
        "recipient_role": recipient_role,
        "event_type": event_type,
        "target_type": target_type,
        "target_id": target_id,
        "title": _clean_text(title, limit=140),
        "summary": _clean_text(summary, limit=500),
        "status": event_status,
        "created_at": created_at or now_iso(),
        "read_at": now_iso() if event_status == "archived" else None,
        "archived_at": now_iso() if event_status == "archived" else None,
        "metadata": {
            **_clean_metadata(metadata or {}),
            "delivery_decision": delivery,
        },
        "actor_id": actor_id,
        "actor_role": actor_role,
        "category": category,
    }
    notification_repo.put_event(item)
    if delivery["channels"]["realtime"]["decision"] == "attempted":
        websocket_service.fanout_notification_event_safe(item)
    return event_response(item)


def create_event_safe(**kwargs: Any) -> dict[str, Any] | None:
    if _best_effort_disabled():
        return None
    try:
        return create_event(**kwargs)
    except Exception:
        return None


def emit_teacher_requested(*, question_id: str, student_id: str, subject: str) -> None:
    for recipient_role in ("tutor", "admin"):
        create_event_safe(
            recipient_id=None,
            recipient_role=recipient_role,
            event_type="teacher_requested",
            target_type="question",
            target_id=question_id,
            title="Teacher help requested",
            summary=f"A student requested help for a {subject} question.",
            metadata={"student_id": student_id, "subject": subject},
            actor_id=student_id,
            actor_role="student",
        )


def emit_teacher_takeover(*, question: dict[str, Any], teacher_id: str) -> None:
    create_event_safe(
        recipient_id=str(question.get("student_id") or ""),
        recipient_role="student",
        event_type="teacher_takeover",
        target_type="question",
        target_id=str(question.get("question_id") or ""),
        title="Teacher joined your question",
        summary="A teacher has started working on your question.",
        metadata={"subject": question.get("subject"), "teacher_id": teacher_id},
        actor_id=teacher_id,
        actor_role="teacher",
    )


def emit_teacher_reply(*, question: dict[str, Any], teacher_id: str) -> None:
    create_event_safe(
        recipient_id=str(question.get("student_id") or ""),
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id=str(question.get("question_id") or ""),
        title="Teacher replied",
        summary="Your teacher added a reply to your question.",
        metadata={"subject": question.get("subject"), "teacher_id": teacher_id},
        actor_id=teacher_id,
        actor_role="teacher",
    )


def emit_moderation_update(*, case_item: dict[str, Any], actor_id: str, actor_role: str) -> None:
    if case_item.get("reporter_id") and case_item.get("reporter_role") != "admin":
        create_event_safe(
            recipient_id=str(case_item["reporter_id"]),
            recipient_role=str(case_item.get("reporter_role") or "student"),
            event_type="moderation_case_update",
            target_type="moderation_case",
            target_id=str(case_item.get("case_id") or ""),
            title="Moderation case updated",
            summary=f"Moderation case status is {case_item.get('status', 'updated')}.",
            metadata={"question_id": case_item.get("question_id"), "status": case_item.get("status")},
            actor_id=actor_id,
            actor_role=actor_role,
        )


def emit_moderation_created(*, case_item: dict[str, Any], actor_id: str, actor_role: str) -> None:
    create_event_safe(
        recipient_id=None,
        recipient_role="admin",
        event_type="moderation_case_update",
        target_type="moderation_case",
        target_id=str(case_item.get("case_id") or ""),
        title="New moderation case",
        summary=f"{case_item.get('severity', 'medium')} moderation case reported.",
        metadata={"question_id": case_item.get("question_id"), "reason": case_item.get("reason")},
        actor_id=actor_id,
        actor_role=actor_role,
    )


def emit_subscription_update(
    *,
    request_item: dict[str, Any],
    recipient_id: str | None,
    recipient_role: str,
    actor_id: str,
    actor_role: str,
) -> None:
    create_event_safe(
        recipient_id=recipient_id,
        recipient_role=recipient_role,
        event_type="subscription_request_update",
        target_type="subscription_request",
        target_id=str(request_item.get("request_id") or ""),
        title="Subscription request updated",
        summary=f"Subscription request status is {request_item.get('status', 'updated')}.",
        metadata={
            "requested_tier": request_item.get("requested_tier"),
            "request_type": request_item.get("request_type"),
            "status": request_item.get("status"),
        },
        actor_id=actor_id,
        actor_role=actor_role,
    )


def list_user_events(
    user: dict[str, Any],
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported notification status")
    user_id = str(user.get("sub") or "")
    role = str(user.get("role") or "")
    items = [
        item for item in notification_repo.list_events(limit=max(limit, 100))
        if _visible_to_user(item, user_id=user_id, role=role)
        and (status is None and item.get("status") != "archived" or status == item.get("status"))
    ]
    return [event_response(item) for item in _sort_events(items)[:limit]]


def list_admin_events(
    *,
    status: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported notification status")
    if event_type is not None and event_type not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported notification event type")
    items = [
        item for item in notification_repo.list_events(limit=max(limit, 100))
        if (status is None or item.get("status") == status)
        and (event_type is None or item.get("event_type") == event_type)
    ]
    return [event_response(item) for item in _sort_events(items)[:limit]]


def default_preferences() -> dict[str, Any]:
    return {
        category: {
            "in_app": True,
            "realtime": True,
            "email_digest": False,
            "push": False,
        }
        for category in sorted(PREFERENCE_CATEGORIES)
    }


def get_preferences_for_user(user_id: str | None) -> dict[str, Any]:
    if not user_id:
        return default_preferences()
    stored = notification_repo.get_preferences(user_id) or {}
    return _merged_preferences(stored.get("preferences"))


def preferences_response(user_id: str) -> dict[str, Any]:
    stored = notification_repo.get_preferences(user_id) or {}
    return {
        "userId": user_id,
        "preferences": _merged_preferences(stored.get("preferences")),
        "supportedCategories": sorted(PREFERENCE_CATEGORIES),
        "supportedChannels": sorted(PREFERENCE_CHANNELS),
        "updatedAt": stored.get("updated_at"),
    }


def update_preferences(user_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
    merged = _merged_preferences(None)
    for category, channel_updates in preferences.items():
        if category not in PREFERENCE_CATEGORIES:
            raise HTTPException(status_code=400, detail="Unsupported notification preference category")
        if not isinstance(channel_updates, dict):
            raise HTTPException(status_code=400, detail="Notification preference channels must be an object")
        for channel, enabled in channel_updates.items():
            if channel not in PREFERENCE_CHANNELS:
                raise HTTPException(status_code=400, detail="Unsupported notification preference channel")
            if not isinstance(enabled, bool):
                raise HTTPException(status_code=400, detail="Notification preference value must be boolean")
            merged[category][channel] = enabled

    updated_at = now_iso()
    notification_repo.put_preferences(
        {
            "entity_type": notification_repo.PREFERENCE_ENTITY,
            "user_id": user_id,
            "preferences": merged,
            "updated_at": updated_at,
        }
    )
    return {
        "userId": user_id,
        "preferences": merged,
        "supportedCategories": sorted(PREFERENCE_CATEGORIES),
        "supportedChannels": sorted(PREFERENCE_CHANNELS),
        "updatedAt": updated_at,
    }


def category_for_event(*, event_type: str, target_type: str) -> str:
    if event_type in EVENT_CATEGORY_BY_TYPE:
        return EVENT_CATEGORY_BY_TYPE[event_type]
    if target_type in {"assignment", "recommendation"}:
        return "assignments"
    if target_type in {"weekly_report", "report"}:
        return "weekly_reports"
    return "learning_updates"


def delivery_decision(
    *,
    category: str,
    preferences: dict[str, Any],
    realtime_configured: bool,
) -> dict[str, Any]:
    category_prefs = _merged_preferences(preferences).get(category, default_preferences()[category])
    return {
        "category": category,
        "channels": {
            "in_app": {
                "enabled": bool(category_prefs["in_app"]),
                "decision": "stored" if category_prefs["in_app"] else "skipped_preference",
            },
            "realtime": {
                "enabled": bool(category_prefs["realtime"]),
                "decision": (
                    "attempted"
                    if category_prefs["realtime"]
                    else "skipped_preference"
                ),
                "configured": realtime_configured,
            },
            "email_digest": {
                "enabled": bool(category_prefs["email_digest"]),
                "decision": "deferred_digest" if category_prefs["email_digest"] else "skipped_preference",
            },
            "push": {
                "enabled": bool(category_prefs["push"]),
                "decision": "deferred_push" if category_prefs["push"] else "skipped_preference",
            },
        },
    }


def delivery_status(*, limit: int = 100) -> dict[str, Any]:
    items = list_admin_events(limit=limit)
    category_counts: dict[str, int] = {}
    realtime_counts: dict[str, int] = {}
    for item in items:
        category = str(item.get("deliveryCategory") or "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        realtime = item.get("deliveryChannels", {}).get("realtime", {})
        decision = str(realtime.get("decision") or "unknown")
        realtime_counts[decision] = realtime_counts.get(decision, 0) + 1
    return {
        "websocketConfigured": bool(settings.websocket_api_endpoint),
        "preferenceCategories": sorted(PREFERENCE_CATEGORIES),
        "preferenceChannels": sorted(PREFERENCE_CHANNELS),
        "recentEventCount": len(items),
        "categoryCounts": category_counts,
        "realtimeDecisionCounts": realtime_counts,
    }


def digest_preview(
    user: dict[str, Any],
    *,
    category: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    if category is not None and category not in PREFERENCE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Unsupported notification preference category")
    user_id = str(user.get("sub") or "")
    role = str(user.get("role") or "")
    preferences = get_preferences_for_user(user_id)
    items = []
    for item in _sort_events(notification_repo.list_events(limit=max(limit, 100))):
        if not _visible_to_user(item, user_id=user_id, role=role):
            continue
        if item.get("status") != "created":
            continue
        item_category = item.get("category") or category_for_event(
            event_type=str(item.get("event_type") or ""),
            target_type=str(item.get("target_type") or ""),
        )
        if category and item_category != category:
            continue
        created_at = str(item.get("created_at") or "")
        if since and created_at < since:
            continue
        if until and created_at > until:
            continue
        category_prefs = _merged_preferences(preferences)[item_category]
        if not category_prefs["email_digest"]:
            continue
        items.append(digest_item(item, category=item_category))
        if len(items) >= limit:
            break
    return {
        "userId": user_id,
        "category": category,
        "window": {"since": since, "until": until},
        "count": len(items),
        "items": items,
        "deliveryMode": "preview_only",
        "emailProviderConfigured": False,
        "pushProviderConfigured": False,
        "pushPreferencesSupported": True,
    }


def digest_item(item: dict[str, Any], *, category: str) -> dict[str, Any]:
    return {
        "eventId": item.get("event_id"),
        "eventType": item.get("event_type"),
        "category": category,
        "targetType": item.get("target_type"),
        "targetId": item.get("target_id"),
        "title": item.get("title"),
        "summary": item.get("summary"),
        "createdAt": item.get("created_at"),
        "metadata": _digest_safe_metadata(item.get("metadata") or {}),
    }


def mark_event(event_id: str, user: dict[str, Any], next_status: str) -> dict[str, Any]:
    if next_status not in {"read", "archived"}:
        raise HTTPException(status_code=400, detail="Unsupported notification transition")
    item = notification_repo.get_event(event_id)
    if not item:
        raise HTTPException(status_code=404, detail="Notification not found")
    if not _visible_to_user(item, user_id=str(user.get("sub") or ""), role=str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="Notification is not visible to this user")

    now = now_iso()
    updates: dict[str, Any] = {"status": next_status}
    if next_status == "read":
        updates["read_at"] = item.get("read_at") or now
    if next_status == "archived":
        updates["archived_at"] = item.get("archived_at") or now
        updates["read_at"] = item.get("read_at") or now
    updated = notification_repo.update_event(event_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    return event_response(updated)


def event_response(item: dict[str, Any]) -> dict[str, Any]:
    delivery = (item.get("metadata") or {}).get("delivery_decision") or {}
    return {
        "eventId": item.get("event_id"),
        "recipientId": item.get("recipient_id"),
        "recipientRole": item.get("recipient_role"),
        "eventType": item.get("event_type"),
        "targetType": item.get("target_type"),
        "targetId": item.get("target_id"),
        "title": item.get("title"),
        "summary": item.get("summary"),
        "status": item.get("status"),
        "createdAt": item.get("created_at"),
        "readAt": item.get("read_at"),
        "archivedAt": item.get("archived_at"),
        "metadata": item.get("metadata") or {},
        "actorId": item.get("actor_id"),
        "actorRole": item.get("actor_role"),
        "deliveryCategory": item.get("category") or delivery.get("category"),
        "deliveryChannels": delivery.get("channels") or {},
    }


def _visible_to_user(item: dict[str, Any], *, user_id: str, role: str) -> bool:
    return item.get("recipient_id") == user_id or (
        item.get("recipient_id") in {None, ""} and item.get("recipient_role") == role
    )


def _sort_events(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def _best_effort_disabled() -> bool:
    if settings.environment.strip().lower() in {"production", "prod"}:
        return False
    return os.getenv("STOA_ENABLE_BEST_EFFORT_NOTIFICATIONS") != "true"


def _clean_text(value: str, *, limit: int) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    return cleaned[:limit]


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): value for key, value in metadata.items()
        if value is not None and "s3_key" not in str(key).lower()
    }


def _digest_safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    private_markers = ("s3", "artifact", "presigned", "weekly-reports/", "html", "raw")
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        key_text = str(key)
        value_text = str(value)
        combined = f"{key_text} {value_text}".lower()
        if any(marker in combined for marker in private_markers):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key_text] = value
    return safe


def _merged_preferences(raw: Any) -> dict[str, dict[str, bool]]:
    merged = default_preferences()
    if not isinstance(raw, dict):
        return merged
    for category, channels in raw.items():
        if category not in PREFERENCE_CATEGORIES or not isinstance(channels, dict):
            continue
        for channel, enabled in channels.items():
            if channel in PREFERENCE_CHANNELS and isinstance(enabled, bool):
                merged[category][channel] = enabled
    return merged
