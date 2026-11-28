"""How `test_notification_happenings_686.py` tells each kind of happening.

The one part of the snapshot test that names the notification code's entry
points; everything it records is read from the table and the provider doubles.
Before #686 these called `notification_service.emit_*`; now each is one
happening handed to `notifications.happened`.
"""

from __future__ import annotations

from typing import Any

from stoa.services import notifications

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
CHANGE_ID = "2026-11-28T10:00:00+00:00#0123456789abcdef0123456789abcdef"
REQUEST = {
    "request_id": "subreq-686",
    "parent_id": PARENT,
    "requested_tier": "family",
    "request_type": "upgrade",
    "status": "requested",
    "account_fence_generation": GENERATION,
}


def switch_push_on(user_id: str) -> None:
    notifications.update_preferences(
        user_id,
        {
            category: {"in_app": True, "realtime": True, "push": True}
            for category in ("admin_operations", "teacher_responses")
        },
    )


def register_push_device(actor: dict[str, str], token: str) -> None:
    notifications.register_push_token(actor, platform="ios", token=token)


def bell(actor: dict[str, str]) -> list[dict[str, Any]]:
    return notifications.list_user_events(actor, limit=50)


def teacher_took(*, mode: str) -> None:
    notifications.happened(
        notifications.TeacherTookHelpRequest(conversation=CONVERSATION, teacher_id=TEACHER, mode=mode)
    )


def teacher_replied() -> None:
    notifications.happened(
        notifications.TeacherReplied(conversation=CONVERSATION, teacher_id=TEACHER, reply_id="reply-686")
    )


def request_expired(*, case_returned: bool) -> None:
    notifications.happened(
        notifications.HelpRequestExpired(conversation=CONVERSATION, case_returned=case_returned)
    )


def help_offered(*, standing: bool) -> None:
    notifications.happened(
        notifications.HelpOffered(
            conversation=CONVERSATION,
            teacher_id=TEACHER,
            dispatch_id="dispatch-686",
            deadline_at="2026-11-28T10:10:00+00:00",
            accept_minutes=10,
            standing=standing,
        )
    )


def teacher_paused() -> None:
    notifications.happened(
        notifications.TeacherPausedAfterLapse(
            teacher_id=TEACHER, dispatch_id="dispatch-686", accept_minutes=10
        )
    )


def offer_closed(state: str) -> None:
    help_offered(standing=False)
    notifications.happened(
        notifications.HelpOfferClosed(
            dispatch_id="dispatch-686", state=state, now="2026-11-28T10:11:00+00:00"
        )
    )


def moderation_opened() -> None:
    notifications.happened(
        notifications.ModerationCaseOpened(
            case=dict(CASE),
            actor_id=STUDENT,
            actor_role="student",
            owner_id=STUDENT,
            privacy_generation=GENERATION,
        )
    )


def moderation_updated() -> None:
    notifications.happened(
        notifications.ModerationCaseUpdated(
            case=dict(CASE),
            actor_id=ADMIN,
            actor_role="admin",
            owner_id=STUDENT,
            privacy_generation=GENERATION,
            change_id=CHANGE_ID,
        )
    )


def moderation_updated_admin_report() -> None:
    # A case an admin or moderation itself opened has nobody to tell (#139).
    notifications.happened(
        notifications.ModerationCaseUpdated(
            case={**CASE, "reporter_id": ADMIN, "reporter_role": "admin"},
            actor_id=ADMIN,
            actor_role="admin",
            owner_id=STUDENT,
            privacy_generation=GENERATION,
            change_id=CHANGE_ID,
        )
    )


def subscription_requested() -> None:
    notifications.happened(
        notifications.SubscriptionRequestChanged(
            request=dict(REQUEST),
            recipient_id=None,
            recipient_role="admin",
            actor_id=PARENT,
            actor_role="parent",
        )
    )


def subscription_approved() -> None:
    notifications.happened(
        notifications.SubscriptionRequestChanged(
            request={**REQUEST, "status": "approved"},
            recipient_id=PARENT,
            recipient_role="parent",
            actor_id=ADMIN,
            actor_role="admin",
        )
    )
