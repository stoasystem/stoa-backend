"""How `test_notification_happenings_686.py` tells each kind of happening.

The one part of the snapshot test that names the notification code's entry
points; everything it records is read from the table and the provider doubles.
"""

from __future__ import annotations

from typing import Any

from stoa.services import notification_service

STUDENT = "student-686"
TEACHER = "teacher-686"
PARENT = "parent-686"
ADMIN = "admin-686"
GENERATION = 4
CONVERSATION = {
    "conversation_id": "conv-686",
    "student_id": STUDENT,
    "escalation_request_id": "req-686",
    "account_fence_generation": GENERATION,
    "subject": "math",
}
CASE = {
    "case_id": "case-686",
    "question_id": "question-686",
    "reporter_id": STUDENT,
    "reporter_role": "student",
    "status": "in_review",
    "severity": "high",
    "reason": "offensive",
}
REQUEST = {
    "request_id": "subreq-686",
    "parent_id": PARENT,
    "requested_tier": "family",
    "request_type": "upgrade",
    "status": "requested",
    "account_fence_generation": GENERATION,
}


def switch_push_on(user_id: str) -> None:
    notification_service.update_preferences(
        user_id,
        {
            category: {"in_app": True, "realtime": True, "push": True}
            for category in ("admin_operations", "teacher_responses")
        },
    )


def register_push_device(actor: dict[str, str], token: str) -> None:
    notification_service.register_push_token(actor, platform="ios", token=token)


def bell(actor: dict[str, str]) -> list[dict[str, Any]]:
    return notification_service.list_user_events(actor, limit=50)


def teacher_took(*, mode: str) -> None:
    notification_service.emit_teacher_help_takeover(
        conversation=CONVERSATION, teacher_id=TEACHER, mode=mode
    )


def teacher_replied() -> None:
    notification_service.emit_teacher_help_reply(
        conversation=CONVERSATION, teacher_id=TEACHER, reply_id="reply-686"
    )


def request_expired(*, case_returned: bool) -> None:
    notification_service.emit_teacher_help_expired(
        conversation=CONVERSATION, case_returned=case_returned
    )


def help_offered(*, standing: bool) -> None:
    notification_service.emit_teacher_help_dispatched(
        conversation=CONVERSATION,
        teacher_id=TEACHER,
        dispatch_id="dispatch-686",
        deadline_at="2026-11-28T10:10:00+00:00",
        accept_minutes=10,
        standing=standing,
    )


def teacher_paused() -> None:
    notification_service.emit_teacher_dispatch_paused(
        teacher_id=TEACHER, dispatch_id="dispatch-686", accept_minutes=10
    )


def offer_closed(state: str) -> None:
    help_offered(standing=False)
    notification_service.close_teacher_help_offer(
        dispatch_id="dispatch-686", state=state, now="2026-11-28T10:11:00+00:00"
    )


def moderation_opened() -> None:
    notification_service.emit_moderation_created(
        case_item=dict(CASE),
        actor_id=STUDENT,
        actor_role="student",
        owner_id=STUDENT,
        privacy_generation=GENERATION,
    )


def moderation_updated() -> None:
    notification_service.emit_moderation_update(
        case_item=dict(CASE),
        actor_id=ADMIN,
        actor_role="admin",
        owner_id=STUDENT,
        privacy_generation=GENERATION,
    )


def moderation_updated_admin_report() -> None:
    # A case an admin or moderation itself opened has nobody to tell (#139).
    notification_service.emit_moderation_update(
        case_item={**CASE, "reporter_id": ADMIN, "reporter_role": "admin"},
        actor_id=ADMIN,
        actor_role="admin",
        owner_id=STUDENT,
        privacy_generation=GENERATION,
    )


def subscription_requested() -> None:
    notification_service.emit_subscription_update(
        request_item=dict(REQUEST),
        recipient_id=None,
        recipient_role="admin",
        actor_id=PARENT,
        actor_role="parent",
    )


def subscription_approved() -> None:
    notification_service.emit_subscription_update(
        request_item={**REQUEST, "status": "approved"},
        recipient_id=PARENT,
        recipient_role="parent",
        actor_id=ADMIN,
        actor_role="admin",
    )
