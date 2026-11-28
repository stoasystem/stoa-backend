"""The "something happened" entry: one happening in, everything it means out.

`happened` looks up what the happening's kind tells, to whom, in which words and
under which fixed id, and hands that to the bell (`_bell.create_event`), which
fans out to realtime and push. It never raises to the caller: a failure is
logged with the happening's event type and the exception type only, never its
text, which can carry a student's content (#79).

The dispatch reminder email still goes out as before, through `notify_service`
(#687 makes it a channel of the package).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from stoa.services import (
    curriculum_service,
    learning_profile_service,
    message_catalog,
    notify_service,
)
from stoa.services.notifications import _bell, _preferences
from stoa.services.notifications._common import (
    ROLE_MESSAGE_STORED_LOCALE,
    ROLE_MESSAGES,
    best_effort_disabled,
    recipient_locale,
    safe_text,
)
from stoa.services.notifications._happenings import (
    Happening,
    HelpOfferClosed,
    HelpOffered,
    HelpRequestExpired,
    ModerationCaseOpened,
    ModerationCaseUpdated,
    SubscriptionRequestChanged,
    TeacherPausedAfterLapse,
    TeacherReplied,
    TeacherTookHelpRequest,
)

logger = _bell.logger


def happened(happening: Happening) -> None:
    """Tell everyone a happening concerns, on every channel it goes out on; never raises."""
    try:
        _HANDLERS[type(happening)](happening)
    except Exception as exc:  # noqa: BLE001 - best effort by contract
        logger.warning(
            "Best-effort notification failed: event_type=%s error=%s",
            getattr(happening, "event_type", None),
            type(exc).__name__,
        )


def _role_message_text(message_key: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """The `create_event` arguments for a role message, its stored text in English."""
    title, summary = ROLE_MESSAGES[message_key](params, ROLE_MESSAGE_STORED_LOCALE)
    return {
        "title": title,
        "summary": summary,
        "message_key": message_key,
        "message_params": dict(params),
    }


def _teacher_took(happening: TeacherTookHelpRequest) -> None:
    """The student hears a teacher took their chat help request (#65), once.

    For the classroom it tells the student to enter it (#480).
    """
    conversation = happening.conversation
    student_id = str(conversation.get("student_id") or "")
    request_id = str(conversation.get("escalation_request_id") or "")
    locale = recipient_locale(student_id)
    _bell.create_event_safe(
        recipient_id=student_id,
        recipient_role="student",
        event_type=happening.event_type,
        target_type="conversation",
        target_id=str(conversation.get("conversation_id") or ""),
        title=message_catalog.text("teacher_help.takeover.title", locale),
        summary=message_catalog.text(
            "teacher_help.takeover.summary_classroom"
            if happening.mode == "classroom"
            else "teacher_help.takeover.summary",
            locale,
        ),
        metadata={
            "request_id": request_id,
            "teacher_id": happening.teacher_id,
            "mode": happening.mode,
        },
        actor_id=happening.teacher_id,
        actor_role="teacher",
        owner_id=student_id,
        account_fence_generation=conversation.get("account_fence_generation"),
        event_id=happening.event_id,
    )


def _teacher_replied(happening: TeacherReplied) -> None:
    """The student hears a teacher answered in their conversation (#65), once per reply.

    A reply never takes the request (#479): the take-over was its own happening.
    """
    conversation = happening.conversation
    student_id = str(conversation.get("student_id") or "")
    locale = recipient_locale(student_id)
    _bell.create_event_safe(
        recipient_id=student_id,
        recipient_role="student",
        event_type=happening.event_type,
        target_type="conversation",
        target_id=str(conversation.get("conversation_id") or ""),
        title=message_catalog.text("teacher_help.reply.title", locale),
        summary=message_catalog.text("teacher_help.reply.summary", locale),
        metadata={
            "request_id": str(conversation.get("escalation_request_id") or ""),
            "teacher_id": happening.teacher_id,
        },
        actor_id=happening.teacher_id,
        actor_role="teacher",
        owner_id=student_id,
        account_fence_generation=conversation.get("account_fence_generation"),
        event_id=happening.event_id,
    )


def _request_expired(happening: HelpRequestExpired) -> None:
    """The student hears their request for a teacher expired (#87), once.

    It says the week's case came back only when it went back into the current
    week: a request that crossed into a new week returns its case to the week
    it was asked in, which the student can no longer use.
    """
    conversation = happening.conversation
    student_id = str(conversation.get("student_id") or "")
    request_id = str(conversation.get("escalation_request_id") or "")
    locale = recipient_locale(student_id)
    _bell.create_event_safe(
        recipient_id=student_id,
        recipient_role="student",
        event_type=happening.event_type,
        target_type="conversation",
        target_id=str(conversation.get("conversation_id") or ""),
        title=message_catalog.text("teacher_help.expired.title", locale),
        summary=message_catalog.text(
            "teacher_help.expired.summary_returned"
            if happening.case_returned
            else "teacher_help.expired.summary",
            locale,
        ),
        metadata={"request_id": request_id},
        actor_role="system",
        owner_id=student_id,
        account_fence_generation=conversation.get("account_fence_generation"),
        event_id=happening.event_id,
    )


def _help_offered(happening: HelpOffered) -> None:
    """The teacher hears a chat help request waits for them (#141).

    Every offer, the first and each re-offer, leaves one bell notification,
    which the teacher cannot switch off, and - unless they switched it off -
    one reminder email. Both are in the teacher's own language and name the
    subject and nothing of the student. Neither ever fails the offer: a failed
    send is logged with its exception type only.

    A ``standing`` offer is one made again to a teacher who let it lapse,
    because nobody else is free (#391). It stays open until the request
    expires, so its notification says the request still waits for them rather
    than naming minutes, and no email is sent: they had one with the first.
    """
    conversation = happening.conversation
    teacher_id = happening.teacher_id
    request_id = str(conversation.get("escalation_request_id") or "")
    locale = recipient_locale(teacher_id)
    subject_name = learning_profile_service.subject_name(conversation.get("subject"), locale)
    summary = (
        message_catalog.text("teacher_help.dispatched.summary_standing", locale, subject=subject_name)
        if happening.standing
        else message_catalog.text(
            "teacher_help.dispatched.summary",
            locale,
            subject=subject_name,
            minutes=happening.accept_minutes,
        )
    )
    metadata: dict[str, Any] = {
        "request_id": request_id,
        "dispatch_id": happening.dispatch_id,
        "deadline_at": happening.deadline_at,
    }
    # Kept so a closed offer's summary can still name it (#455).
    subject_id = curriculum_service.subject_id(conversation.get("subject"))
    if subject_id:
        metadata["subject"] = subject_id
    if happening.standing:
        metadata["standing"] = True
    _bell.create_event_safe(
        recipient_id=teacher_id,
        recipient_role="teacher",
        event_type=happening.event_type,
        target_type="question",
        target_id=request_id,
        title=message_catalog.text("teacher_help.dispatched.title", locale),
        summary=summary,
        metadata=metadata,
        actor_role="system",
        # The request is the student's: their account's deletion takes this with it.
        owner_id=str(conversation.get("student_id") or ""),
        account_fence_generation=conversation.get("account_fence_generation"),
        event_id=happening.event_id,
    )
    if happening.standing or best_effort_disabled():
        return
    try:
        if not _preferences.dispatch_email_enabled(teacher_id):
            return
        from stoa.db.repositories import user_repo

        recipient = safe_text((user_repo.get_user(teacher_id) or {}).get("email"))
        if not recipient:
            logger.warning("dispatch_reminder_email_skipped reason=no_address")
            return
        notify_service.send_dispatch_reminder_email(
            recipient,
            recipient_user_id=teacher_id,
            subject_name=subject_name,
            request_id=request_id,
            minutes=happening.accept_minutes,
            locale=locale,
        )
    except Exception as exc:  # noqa: BLE001 - best effort by contract
        logger.warning("dispatch_reminder_email_failed error=%s", type(exc).__name__)


def _teacher_paused(happening: TeacherPausedAfterLapse) -> None:
    """The teacher hears they were paused for an offer they let lapse (#472).

    One bell notification in the teacher's own language, which they cannot
    switch off; it names nothing of the request or the student, only why and
    how to come back. One per lapsed offer: its id is the offer's.
    """
    teacher_id = happening.teacher_id
    locale = recipient_locale(teacher_id)
    _bell.create_event_safe(
        recipient_id=teacher_id,
        recipient_role="teacher",
        event_type=happening.event_type,
        target_type="teacher_availability",
        target_id=teacher_id,
        title=message_catalog.text("teacher_dispatch.paused.title", locale),
        summary=message_catalog.text(
            "teacher_dispatch.paused.summary", locale, minutes=happening.accept_minutes
        ),
        metadata={"dispatch_id": happening.dispatch_id},
        actor_role="system",
        owner_id=teacher_id,
        event_id=happening.event_id,
    )


def _offer_closed(happening: HelpOfferClosed) -> None:
    _bell.close_teacher_help_offer(
        dispatch_id=happening.dispatch_id, state=happening.state, now=happening.now
    )


def _moderation_opened(happening: ModerationCaseOpened) -> None:
    # Addressed to the admin role rather than to one administrator, so there is
    # no reader whose language this could be written in: each admin is shown it
    # in theirs (#108).
    case = happening.case
    _bell.create_event_safe(
        recipient_id=None,
        recipient_role="admin",
        event_type=happening.event_type,
        target_type="moderation_case",
        target_id=str(case.get("case_id") or ""),
        **_role_message_text("moderation.created", {"severity": case.get("severity", "medium")}),
        metadata={
            "question_id": case.get("question_id"),
            "reason": case.get("reason"),
            "owner_id": happening.owner_id,
            "privacy_generation": happening.privacy_generation,
        },
        actor_id=happening.actor_id,
        actor_role=happening.actor_role,
        owner_id=happening.owner_id,
        account_fence_generation=happening.privacy_generation,
        event_id=happening.event_id,
    )


def _moderation_updated(happening: ModerationCaseUpdated) -> None:
    case = happening.case
    # A case moderation opened itself (#139) has no person to tell.
    if not case.get("reporter_id") or case.get("reporter_role") in {"admin", "system"}:
        return
    reporter_id = str(case["reporter_id"])
    locale = recipient_locale(reporter_id)
    _bell.create_event_safe(
        recipient_id=reporter_id,
        recipient_role=str(case.get("reporter_role") or "student"),
        event_type=happening.event_type,
        target_type="moderation_case",
        target_id=str(case.get("case_id") or ""),
        title=message_catalog.text("moderation.update.title", locale),
        summary=message_catalog.text(
            "moderation.update.summary",
            locale,
            status=case.get("status", "updated"),
        ),
        metadata={
            "question_id": case.get("question_id"),
            "status": case.get("status"),
            "owner_id": happening.owner_id,
            "privacy_generation": happening.privacy_generation,
        },
        actor_id=happening.actor_id,
        actor_role=happening.actor_role,
        owner_id=happening.owner_id,
        account_fence_generation=happening.privacy_generation,
        event_id=happening.event_id,
    )


def _subscription_changed(happening: SubscriptionRequestChanged) -> None:
    request = happening.request
    owner_id = str(
        request.get("student_id") or request.get("parent_id") or happening.recipient_id or ""
    )
    locale = recipient_locale(happening.recipient_id)
    _bell.create_event_safe(
        recipient_id=happening.recipient_id,
        recipient_role=happening.recipient_role,
        event_type=happening.event_type,
        target_type="subscription_request",
        target_id=str(request.get("request_id") or ""),
        title=message_catalog.text("subscription.update.title", locale),
        summary=message_catalog.text(
            "subscription.update.summary",
            locale,
            status=request.get("status", "updated"),
        ),
        metadata={
            "requested_tier": request.get("requested_tier"),
            "request_type": request.get("request_type"),
            "status": request.get("status"),
        },
        actor_id=happening.actor_id,
        actor_role=happening.actor_role,
        owner_id=owner_id,
        account_fence_generation=request.get("account_fence_generation"),
        event_id=happening.event_id,
    )


_HANDLERS: dict[type, Callable[[Any], None]] = {
    TeacherTookHelpRequest: _teacher_took,
    TeacherReplied: _teacher_replied,
    HelpRequestExpired: _request_expired,
    HelpOffered: _help_offered,
    TeacherPausedAfterLapse: _teacher_paused,
    HelpOfferClosed: _offer_closed,
    ModerationCaseOpened: _moderation_opened,
    ModerationCaseUpdated: _moderation_updated,
    SubscriptionRequestChanged: _subscription_changed,
}
