"""What each reader wants: the category x channel matrix, the two email switches, the unsubscribe link.

Inside the notification package (#686); the reader door re-exports the reads
and writes the settings page and the unsubscribe page call.
"""

from __future__ import annotations

from typing import Any, Mapping

from stoa.db.repositories import account_deletion_repo, notification_repo
from stoa.services import email_unsubscribe
from stoa.services.notification_errors import NotificationErrorCode as _N, NotificationViolation
from stoa.services.notifications._common import EVENT_CATEGORY_BY_TYPE, now_iso

# The categories an event falls into. The weekly report email has its own switch
# (`weekly_report_email`), not a category.
PREFERENCE_CATEGORIES = set(EVENT_CATEGORY_BY_TYPE.values())
PREFERENCE_CHANNELS = {"in_app", "realtime", "push"}
# What an older settings page still sends back with the whole matrix (#684): the
# digest email channel, never sent and retired, and the three categories no event
# ever fell into. Taken and ignored, so such a page saves without an error; stored
# rows keep them, and `_merged_preferences` drops them on reading.
RETIRED_PREFERENCE_CATEGORIES = frozenset({"learning_updates", "assignments", "weekly_reports"})
RETIRED_PREFERENCE_CHANNELS = frozenset({"email_digest"})
# The switch for the dispatch reminder email (#141), on until the teacher turns
# it off. It is not a category x channel cell: the bell for the same offer
# cannot be turned off.
DISPATCH_EMAIL_DEFAULT = True
# The parent's weekly report email (#363); on until they switch it off.
WEEKLY_REPORT_EMAIL_DEFAULT = True


def default_preferences() -> dict[str, Any]:
    return {
        category: {
            "in_app": True,
            "realtime": True,
            "push": False,
        }
        for category in sorted(PREFERENCE_CATEGORIES)
    }


def get_preferences_for_user(user_id: str | None) -> dict[str, Any]:
    if not user_id:
        return default_preferences()
    stored = notification_repo.get_preferences(user_id) or {}
    return _merged_preferences(stored.get("preferences"))


def _stored_dispatch_email(stored: Mapping[str, Any]) -> bool:
    value = stored.get("dispatch_email")
    return value if isinstance(value, bool) else DISPATCH_EMAIL_DEFAULT


def dispatch_email_enabled(user_id: str) -> bool:
    """Whether this teacher wants the dispatch reminder email (#141)."""
    return _stored_dispatch_email(notification_repo.get_preferences(user_id) or {})


def _stored_weekly_report_email(stored: Mapping[str, Any]) -> bool:
    value = stored.get("weekly_report_email")
    return value if isinstance(value, bool) else WEEKLY_REPORT_EMAIL_DEFAULT


def weekly_report_email_enabled(user_id: str) -> bool:
    """Whether this parent wants the weekly report by email (#363).

    Switched off, the report is still generated and readable in STOA; only the
    email is not sent.
    """
    return _stored_weekly_report_email(notification_repo.get_preferences(user_id) or {})


def preferences_response(user_id: str) -> dict[str, Any]:
    stored = notification_repo.get_preferences(user_id) or {}
    return {
        "userId": user_id,
        "preferences": _merged_preferences(stored.get("preferences")),
        "dispatchEmail": _stored_dispatch_email(stored),
        "weeklyReportEmail": _stored_weekly_report_email(stored),
        "supportedCategories": sorted(PREFERENCE_CATEGORIES),
        "supportedChannels": sorted(PREFERENCE_CHANNELS),
        "updatedAt": stored.get("updated_at"),
    }


def update_preferences(
    user_id: str,
    preferences: dict[str, Any] | None,
    *,
    dispatch_email: bool | None = None,
    weekly_report_email: bool | None = None,
) -> dict[str, Any]:
    """Write the matrix and the email switches; a part left out keeps what is stored.

    A client that only knows the matrix must not turn a teacher's dispatch
    email back on, and one that only flips a switch must not reset the matrix.
    """
    stored = notification_repo.get_preferences(user_id) or {}
    if preferences is None:
        merged = _merged_preferences(stored.get("preferences"))
        preferences = {}
    else:
        merged = _merged_preferences(None)
    if dispatch_email is None:
        dispatch_email = _stored_dispatch_email(stored)
    if weekly_report_email is None:
        weekly_report_email = _stored_weekly_report_email(stored)
    for category, channel_updates in preferences.items():
        if category not in PREFERENCE_CATEGORIES | RETIRED_PREFERENCE_CATEGORIES:
            raise NotificationViolation(_N.NOTIFICATION_PREFERENCE_CATEGORY_UNSUPPORTED)
        if not isinstance(channel_updates, dict):
            raise NotificationViolation(_N.NOTIFICATION_PREFERENCE_CHANNELS_INVALID)
        for channel, enabled in channel_updates.items():
            if channel not in PREFERENCE_CHANNELS | RETIRED_PREFERENCE_CHANNELS:
                raise NotificationViolation(_N.NOTIFICATION_PREFERENCE_CHANNEL_UNSUPPORTED)
            if not isinstance(enabled, bool):
                raise NotificationViolation(_N.NOTIFICATION_PREFERENCE_VALUE_INVALID)
            if category in PREFERENCE_CATEGORIES and channel in PREFERENCE_CHANNELS:
                merged[category][channel] = enabled

    updated_at = now_iso()
    notification_repo.put_preferences(
        {
            "entity_type": notification_repo.PREFERENCE_ENTITY,
            "user_id": user_id,
            "owner_id": user_id,
            "preferences": merged,
            "dispatch_email": dispatch_email,
            "weekly_report_email": weekly_report_email,
            "updated_at": updated_at,
        }
    )
    return {
        "userId": user_id,
        "preferences": merged,
        "dispatchEmail": dispatch_email,
        "weeklyReportEmail": weekly_report_email,
        "supportedCategories": sorted(PREFERENCE_CATEGORIES),
        "supportedChannels": sorted(PREFERENCE_CHANNELS),
        "updatedAt": updated_at,
    }


def set_email_subscription(token: str, *, subscribed: bool) -> dict[str, Any]:
    """Follow an unsubscribe link from a notification email, or undo it (#363).

    The token, not a session, names whose preference changes and which one;
    any doubt about it is the one `email_unsubscribe_link_invalid`. Each kind
    writes the preference the settings page already shows:

    - dispatch reminder: `dispatch_email`;
    - weekly report: `weekly_report_email`.
    """
    target = email_unsubscribe.read_token(token)
    user_id = target.user_id
    # The repository merges these fields onto the stored row.
    item: dict[str, Any] = {
        "entity_type": notification_repo.PREFERENCE_ENTITY,
        "user_id": user_id,
        "owner_id": user_id,
        "updated_at": now_iso(),
    }
    if target.kind is email_unsubscribe.EmailKind.DISPATCH_REMINDER:
        item["dispatch_email"] = subscribed
    else:
        item["weekly_report_email"] = subscribed
    try:
        notification_repo.put_preferences(item)
    except account_deletion_repo.AccountDeletionConflict as exc:
        # The account was deleted since the email: the write is fenced off, and
        # the link answers as any other that no longer works.
        raise email_unsubscribe.invalid_link() from exc
    return {"kind": target.kind.value, "subscribed": subscribed}


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
            "push": {
                "enabled": bool(category_prefs["push"]),
                "decision": "deferred_push" if category_prefs["push"] else "skipped_preference",
            },
        },
    }


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
