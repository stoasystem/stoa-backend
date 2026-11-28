"""The bell: one stored row per notification, the channels it fans out to, and how readers see it.

Inside the notification package (#686). `create_event` writes the row under its
fixed id (a second write of the same id is refused by the store, so a retried
happening leaves one row and fans out once), then hands it to the realtime and
push channels as the reader's preferences decide.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from stoa import config
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import notification_repo
from stoa.security.identity import Actor
from stoa.services import curriculum_service, learning_profile_service, locale_service, message_catalog, websocket_service
from stoa.services.notification_errors import NotificationErrorCode as _N, NotificationViolation
from stoa.services.notifications import _ledger, _preferences, _push, _realtime
from stoa.services.notifications._happenings import OFFER_STATES, dispatched_event_id
from stoa.services.notifications._common import (
    ALWAYS_IN_APP_EVENT_TYPES,
    EVENT_CATEGORY_BY_TYPE,
    EVENT_TYPES,
    ROLE_MESSAGES,
    STATUSES,
    best_effort_disabled as _best_effort_disabled,
    now_iso,
    recipient_locale as _recipient_locale,
    user_id_of as _user_id,
    user_role_of as _user_role,
    visible_to_user as _visible_to_user,
)

logger = logging.getLogger("stoa.services.notifications")


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
    event_id: str,
    owner_id: str | None = None,
    account_fence_generation: int | None = None,
    global_nonprivate: bool = False,
    message_key: str | None = None,
    message_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise NotificationViolation(_N.NOTIFICATION_EVENT_TYPE_UNSUPPORTED)
    # Derived from what happened (`_happenings`), never random (#686): the
    # store refuses a second row under it, so a retry tells nobody twice.
    if not str(event_id or "").strip():
        raise NotificationViolation(_N.NOTIFICATION_EVENT_ID_REQUIRED)
    if status not in STATUSES:
        raise NotificationViolation(_N.NOTIFICATION_STATUS_UNSUPPORTED)
    if not recipient_role:
        raise NotificationViolation(_N.NOTIFICATION_RECIPIENT_ROLE_REQUIRED)

    raw_metadata = dict(metadata or {})
    inferred_owner = str(
        owner_id
        or raw_metadata.get("owner_id")
        or raw_metadata.get("student_id")
        or recipient_id
        or ""
    ).strip()
    raw_generation = (
        account_fence_generation
        if account_fence_generation is not None
        else raw_metadata.get("privacy_generation")
        or raw_metadata.get("account_fence_generation")
    )
    stored_generation = stored_int(raw_generation)
    generation = stored_generation if stored_generation is not None and stored_generation > 0 else None
    if inferred_owner and generation is not None:
        ownership = _ledger.classify_notification_owner(
            recipient_id=recipient_id,
            target_type=target_type,
            target_id=target_id,
            metadata=raw_metadata,
            owner_id=inferred_owner,
            generation=generation,
            global_nonprivate=False,
        )
    elif inferred_owner:
        # The repository resolves the current generation on the real atomic
        # table.  This compatibility path exists for older unit fakes only.
        ownership = {
            "owner_id": inferred_owner,
            "account_fence_generation": None,
            "target_type": target_type,
            "target_id": target_id,
            "classification": "private_owner",
        }
    elif global_nonprivate:
        ownership = {
            "owner_id": None,
            "account_fence_generation": None,
            "target_type": target_type,
            "target_id": target_id,
            "classification": "global_nonprivate",
        }
    else:
        raise NotificationViolation(_N.NOTIFICATION_OWNER_REQUIRED)

    category = EVENT_CATEGORY_BY_TYPE[event_type]
    preferences = (
        _preferences.get_preferences_for_user(recipient_id)
        if recipient_id
        else _preferences.default_preferences()
    )
    delivery = _preferences.delivery_decision(
        category=category,
        preferences=preferences,
        realtime_configured=bool(config.settings().websocket_api_endpoint),
    )
    if event_type in ALWAYS_IN_APP_EVENT_TYPES:
        delivery["channels"]["in_app"] = {"enabled": True, "decision": "stored"}
    event_status = status
    if not delivery["channels"]["in_app"]["enabled"] and status == "created":
        event_status = "archived"

    item = {
        "entity_type": notification_repo.NOTIFICATION_ENTITY,
        "schema_version": "notification-event.v3",
        "event_version": 1,
        "event_id": event_id,
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
        "metadata": (
            {}
            if ownership["classification"] == "global_nonprivate"
            else {
                **_clean_metadata(raw_metadata),
                "delivery_decision": delivery,
            }
        ),
        "actor_id": actor_id,
        "actor_role": actor_role,
        "category": category,
        "owner_id": ownership["owner_id"],
        "account_fence_generation": ownership["account_fence_generation"],
        "owner_classification": ownership["classification"],
    }
    if ownership["classification"] == "private_owner":
        item.update(
            owner_target_type=ownership["target_type"],
            owner_target_id=ownership["target_id"],
        )
    if message_key in ROLE_MESSAGES:
        item.update(
            message_key=message_key,
            message_params={
                str(name): str(value)
                for name, value in (message_params or {}).items()
                if value is not None
            },
        )
    persisted = notification_repo.put_event(item)
    if isinstance(persisted, dict):
        item = persisted
    if delivery["channels"]["realtime"]["decision"] == "attempted":
        _realtime.fanout_notification_event_safe(item)
    if delivery["channels"]["push"]["decision"] == "deferred_push":
        _push.attempt_push_delivery_safe(item)
    return event_response(item)


def create_event_safe(**kwargs: Any) -> dict[str, Any] | None:
    """Create a notification without ever failing the caller.

    A failure is logged with the event type and the exception type only:
    swallowed silently, a notification failing in production would go
    unnoticed (stoasystem/stoa-backend#79). No title, summary or metadata
    is logged, since they can carry a student's content.
    """
    if _best_effort_disabled():
        return None
    try:
        return create_event(**kwargs)
    except Exception as exc:  # noqa: BLE001 - best effort by contract
        logger.warning(
            "Best-effort notification failed: event_type=%s error=%s",
            kwargs.get("event_type"),
            type(exc).__name__,
        )
        return None


def close_teacher_help_offer(*, dispatch_id: str, state: str, now: str | None = None) -> None:
    """Mark an offer's notification as no longer open, saying what became of it (#391).

    Its metadata gains `offer_state` (one of `OFFER_STATES`) and
    `offer_closed_at`, so the teacher's bell shows "expired" or "passed on"
    instead of a request that opens onto nothing, and an unread one is marked
    read, so a lapsed offer does not stay in the unread count. Its title and
    summary are rewritten in the teacher's language to say what became of the
    offer, so it no longer asks them to accept within minutes (#455); the
    subject is named when the notification kept it. Only the closed offer's
    own notification changes: an open one, a standing offer among them, keeps
    its text. A notification already closed is left as it was. Written
    through the notification repository, behind the student's account fence
    (#397); best effort: a failure is logged with its exception type only.
    """
    if state not in OFFER_STATES:
        raise ValueError(f"unsupported offer state: {state}")
    if not dispatch_id or _best_effort_disabled():
        return
    try:
        event_id = dispatched_event_id(dispatch_id)
        item = notification_repo.get_event(event_id)
        if not item:
            return
        metadata = dict(item.get("metadata") or {})
        if metadata.get("offer_state"):
            return
        timestamp = now or now_iso()
        updates: dict[str, Any] = {
            "metadata": {**metadata, "offer_state": state, "offer_closed_at": timestamp},
            **_closed_offer_text(item, metadata, state),
        }
        if item.get("status") == "created":
            updates["status"] = "read"
            updates["read_at"] = item.get("read_at") or timestamp
        notification_repo.update_event(event_id, updates)
    except Exception as exc:  # noqa: BLE001 - best effort by contract
        logger.warning("teacher_help_offer_close_failed error=%s", type(exc).__name__)


def _closed_offer_text(
    item: Mapping[str, Any], metadata: Mapping[str, Any], state: str
) -> dict[str, str]:
    """A closed offer's title and summary in its teacher's language (#455)."""
    locale = _recipient_locale(str(item.get("recipient_id") or "") or None)
    closed = message_catalog.text(f"teacher_help.dispatched.closed.{state}", locale)
    summary = closed
    if curriculum_service.subject_id(metadata.get("subject")):
        subject_line = message_catalog.text(
            "teacher_help.dispatched.subject_line",
            locale,
            subject=learning_profile_service.subject_name(metadata.get("subject"), locale),
        )
        summary = f"{subject_line} {closed}"
    return {
        "title": message_catalog.text("teacher_help.dispatched.title_closed", locale),
        "summary": summary,
    }


def list_user_events(
    user: dict[str, Any] | Actor,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if status is not None and status not in STATUSES:
        raise NotificationViolation(_N.NOTIFICATION_STATUS_UNSUPPORTED)
    user_id = _user_id(user)
    role = _user_role(user)
    locale = locale_service.reader_locale(user_id)
    # This person's own inbox and their role's, read from the index (#613): the
    # bell polls this, and a scan of the table read every row of it each time
    # and saw only the first hundred notifications of the whole site. Only the
    # newest `limit` that are shown are read, not the whole history (card 133).
    def shown(item: Mapping[str, Any]) -> bool:
        return _visible_to_user(dict(item), user_id=user_id, role=role) and (
            status is None and item.get("status") != "archived" or status == item.get("status")
        )

    items = [
        item
        for item in notification_repo.list_inbox(user_id=user_id, role=role, want=limit, keep=shown)
        if shown(item)
    ]
    return [event_response(item, locale=locale) for item in _sort_events(items)[:limit]]


def list_admin_events(
    *,
    status: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
    locale: str | None = None,
) -> list[dict[str, Any]]:
    if status is not None and status not in STATUSES:
        raise NotificationViolation(_N.NOTIFICATION_STATUS_UNSUPPORTED)
    if event_type is not None and event_type not in EVENT_TYPES:
        raise NotificationViolation(_N.NOTIFICATION_EVENT_TYPE_UNSUPPORTED)
    # Every notification of the site, whoever it is for, read newest first from
    # the site's list in its own index (#613), not by a scan of the table.
    items = notification_repo.list_site_events(
        want=limit,
        keep=lambda item: (status is None or item.get("status") == status)
        and (event_type is None or item.get("event_type") == event_type),
    )
    return [event_response(item, locale=locale) for item in _sort_events(items)[:limit]]


def delivery_status(*, limit: int = 100) -> dict[str, Any]:
    items = list_admin_events(limit=limit)
    category_counts: dict[str, int] = {}
    realtime_counts: dict[str, int] = {}
    delivery_attempt_counts: dict[str, int] = {}
    recent_delivery_attempts: list[dict[str, Any]] = []
    for item in items:
        category = str(item.get("deliveryCategory") or "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        realtime = item.get("deliveryChannels", {}).get("realtime", {})
        decision = str(realtime.get("decision") or "unknown")
        realtime_counts[decision] = realtime_counts.get(decision, 0) + 1
        for attempt in _websocket_delivery_attempts(item):
            result_counts = _delivery_attempt_result_counts(attempt)
            for status, count in result_counts.items():
                delivery_attempt_counts[status] = delivery_attempt_counts.get(status, 0) + count
            recent_delivery_attempts.append(
                {
                    "eventId": item.get("eventId"),
                    "deliveryId": attempt.get("delivery_id"),
                    "attemptedAt": attempt.get("attempted_at"),
                    "targetChannels": attempt.get("target_channels") or [],
                    "targetCount": _safe_int(attempt.get("target_count")),
                    "resultCounts": result_counts,
                }
            )
    websocket_readiness = websocket_service.readiness_status()
    return {
        "websocketConfigured": bool(config.settings().websocket_api_endpoint),
        "websocketMode": websocket_readiness["mode"],
        "websocketReadiness": websocket_readiness,
        "pushProvider": _push.push_provider_readiness(),
        "preferenceCategories": sorted(_preferences.PREFERENCE_CATEGORIES),
        "preferenceChannels": sorted(_preferences.PREFERENCE_CHANNELS),
        "recentEventCount": len(items),
        "categoryCounts": category_counts,
        "realtimeDecisionCounts": realtime_counts,
        "deliveryAttemptCounts": delivery_attempt_counts,
        "recentDeliveryAttempts": recent_delivery_attempts[-10:],
    }


def _websocket_delivery_attempts(item: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = item.get("metadata") or {}
    attempts = metadata.get("websocket_delivery_attempts") or []
    return [attempt for attempt in attempts if isinstance(attempt, dict)]


def _delivery_attempt_result_counts(attempt: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in attempt.get("results") or []:
        if not isinstance(result, dict):
            continue
        status = str(result.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _event_text(item: dict[str, Any], locale: str | None) -> tuple[Any, Any]:
    """An event's title and summary; a role message rendered in `locale` when given."""
    render = ROLE_MESSAGES.get(str(item.get("message_key") or ""))
    if locale and render:
        return render(item.get("message_params") or {}, locale)
    return item.get("title"), item.get("summary")



def mark_authorized_event(item: Mapping[str, object], next_status: str) -> dict[str, Any]:
    if next_status not in {"read", "archived"}:
        raise NotificationViolation(_N.NOTIFICATION_TRANSITION_UNSUPPORTED)
    event_id = str(item.get("event_id") or "")
    now = now_iso()
    updates: dict[str, Any] = {"status": next_status}
    if next_status == "read":
        updates["read_at"] = item.get("read_at") or now
    else:
        updates["archived_at"] = item.get("archived_at") or now
        updates["read_at"] = item.get("read_at") or now
    updated = notification_repo.update_event(event_id, updates)
    if not updated:
        raise NotificationViolation(_N.NOTIFICATION_NOT_FOUND)
    return event_response(updated)


def event_response(item: dict[str, Any], *, locale: str | None = None) -> dict[str, Any]:
    """One event as the API shows it; a role message in `locale` when given."""
    delivery = (item.get("metadata") or {}).get("delivery_decision") or {}
    title, summary = _event_text(item, locale)
    return {
        "eventId": item.get("event_id"),
        "recipientId": item.get("recipient_id"),
        "recipientRole": item.get("recipient_role"),
        "eventType": item.get("event_type"),
        "targetType": item.get("target_type"),
        "targetId": item.get("target_id"),
        "title": title,
        "summary": summary,
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


def _sort_events(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def _clean_text(value: str, *, limit: int) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    return cleaned[:limit]


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): value for key, value in metadata.items()
        if value is not None and "s3_key" not in str(key).lower()
    }
