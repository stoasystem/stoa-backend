"""What every part of the notification package shares: the kinds, the one visibility rule, small helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from stoa import config
from stoa.security.identity import Actor
from stoa.services import locale_service, message_catalog

EVENT_CATEGORY_BY_TYPE = {
    "teacher_takeover": "teacher_responses",
    "teacher_reply": "teacher_responses",
    "teacher_help_expired": "teacher_responses",
    "teacher_help_dispatched": "teacher_responses",
    "teacher_dispatch_paused": "teacher_responses",
    "moderation_case_update": "admin_operations",
    "subscription_request_update": "admin_operations",
}
EVENT_TYPES = set(EVENT_CATEGORY_BY_TYPE)
STATUSES = {"created", "read", "archived", "failed"}
# Stored in the bell whatever the reader's in-app preference says. An offer
# lapses in minutes, so a teacher who switched the bell off for the category
# would let every one of them lapse unseen (#141); the email is what they can
# switch off instead.
#
# A teacher paused for an offer they let lapse (#472) is told the same way: a
# bell they switched off would leave them paused without knowing why.
ALWAYS_IN_APP_EVENT_TYPES = frozenset({"teacher_help_dispatched", "teacher_dispatch_paused"})


def visible_to_user(item: Mapping[str, Any], *, user_id: str, role: str) -> bool:
    """Who may see a notification: the one rule, for the bell and for realtime.

    One with a `recipient_id` is that person's alone; one without is for
    everyone in its `recipient_role`.
    """
    return item.get("recipient_id") == user_id or (
        item.get("recipient_id") in {None, ""} and item.get("recipient_role") == role
    )


def recipient_locale(recipient_id: str | None) -> str:
    """The language the reader stored, not the language of the request.

    A notification is written by somebody else's request - a teacher's reply, a
    job that found a request expired - so the request's language names the
    wrong person here (#124).
    """
    return locale_service.stored_locale(recipient_id)


def _moderation_created_message(params: Mapping[str, Any], locale: str) -> tuple[str, str]:
    summary_key = f"moderation.created.summary.{params.get('severity')}"
    if summary_key not in message_catalog.TEXT:
        summary_key = "moderation.created.summary"
    return (
        message_catalog.text("moderation.created.title", locale),
        message_catalog.text(summary_key, locale),
    )


# Events written once for a whole role (`recipient_id=None`) have no reader
# whose language is known when they are written. The row keeps one of these
# keys and its raw parameters, and each reader is shown the title and summary
# in their own language when they read it (#108). The stored title and summary
# are the English, for whatever shows a row without a reader to render it for.
ROLE_MESSAGES = {
    "moderation.created": _moderation_created_message,
}
ROLE_MESSAGE_STORED_LOCALE = "en"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def best_effort_disabled() -> bool:
    if config.settings().environment.strip().lower() in {"production", "prod"}:
        return False
    return not config.settings().stoa_enable_best_effort_notifications


def safe_text(value: Any) -> str:
    return str(value or "").strip()


def hash_value(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def user_id_of(user: dict[str, Any] | Actor) -> str:
    return str(user.user_id if isinstance(user, Actor) else user.get("sub") or user.get("user_id") or "")


def user_role_of(user: dict[str, Any] | Actor) -> str:
    return user.role.value if isinstance(user, Actor) else str(user.get("role") or "")
