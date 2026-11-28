"""What can happen that somebody is told about, and the one fixed id each happening has.

A caller builds one of these and hands it to `notifications.happened` (#686).
It says only what happened; the package decides who is told, in which words,
on which channels, and under which id. Building one checks what only the
caller can get wrong (an offer state that does not exist, a moderation case
without its owner) and raises then, before anything is written; `happened`
itself never raises.

The id is derived from the happening, never random (#638 decision 3), so the
same happening told twice - a retried write, a job that runs again - is
refused by the store the second time and reaches nobody twice:

- the five help-request happenings keep the ids they had (no migration);
- a moderation case opened: the case; updated: the case and the change (the
  case history entry the update or note wrote), so each update still reaches
  the reporter once, and a retry of the same one does not;
- a subscription request: the request and the status it reached.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from stoa.services.notification_errors import NotificationErrorCode as _N, NotificationViolation

#: What became of an offer whose notification no longer offers anything (#391):
#: it lapsed or the request expired, it went to another teacher, or the student
#: took the request back.
OFFER_STATES = frozenset({"expired", "reassigned", "withdrawn"})


def dispatched_event_id(dispatch_id: str) -> str:
    return f"teacher-help-dispatched-{dispatch_id}"


def _short_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class TeacherTookHelpRequest:
    """A teacher took a student's chat help request (#65); `mode` is the request's (#480)."""

    conversation: Mapping[str, Any]
    teacher_id: str
    mode: str = "text"

    event_type = "teacher_takeover"

    @property
    def event_id(self) -> str:
        request_id = str(self.conversation.get("escalation_request_id") or "")
        return f"teacher-help-takeover-{request_id}-{self.teacher_id}"


@dataclass(frozen=True)
class TeacherReplied:
    """A teacher answered in the student's conversation (#65); one per reply."""

    conversation: Mapping[str, Any]
    teacher_id: str
    reply_id: str

    event_type = "teacher_reply"

    @property
    def event_id(self) -> str:
        return f"teacher-help-reply-{self.reply_id}"


@dataclass(frozen=True)
class HelpRequestExpired:
    """A student's request for a teacher expired (#87); `case_returned` when the week's case came back."""

    conversation: Mapping[str, Any]
    case_returned: bool

    event_type = "teacher_help_expired"

    @property
    def event_id(self) -> str:
        request_id = str(self.conversation.get("escalation_request_id") or "")
        return f"teacher-help-expired-{request_id}"


@dataclass(frozen=True)
class HelpOffered:
    """A chat help request was offered to a teacher (#141); `standing` when re-offered with nobody else free (#391)."""

    conversation: Mapping[str, Any]
    teacher_id: str
    dispatch_id: str
    deadline_at: str
    accept_minutes: int
    standing: bool = False

    event_type = "teacher_help_dispatched"

    @property
    def event_id(self) -> str:
        return dispatched_event_id(self.dispatch_id)


@dataclass(frozen=True)
class TeacherPausedAfterLapse:
    """A teacher was paused for an offer they let lapse (#472)."""

    teacher_id: str
    dispatch_id: str
    accept_minutes: int

    event_type = "teacher_dispatch_paused"

    @property
    def event_id(self) -> str:
        return f"teacher-dispatch-paused-{self.dispatch_id}"


@dataclass(frozen=True)
class HelpOfferClosed:
    """An offer no longer offers anything (#391): its notification says what became of it."""

    dispatch_id: str
    state: str
    now: str | None = None

    event_type = "teacher_help_dispatched"

    def __post_init__(self) -> None:
        if self.state not in OFFER_STATES:
            raise ValueError(f"unsupported offer state: {self.state}")

    @property
    def event_id(self) -> str:
        return dispatched_event_id(self.dispatch_id)


def _require_moderation_owner(owner_id: object, privacy_generation: object) -> None:
    if (
        not isinstance(owner_id, str)
        or not owner_id.strip()
        or isinstance(privacy_generation, bool)
        or not isinstance(privacy_generation, int)
        or privacy_generation <= 0
    ):
        raise NotificationViolation(_N.NOTIFICATION_OWNER_REQUIRED)


@dataclass(frozen=True)
class ModerationCaseOpened:
    """A moderation case was opened; every admin is told, each in their own language (#108)."""

    case: Mapping[str, Any]
    actor_id: str
    actor_role: str
    owner_id: str
    privacy_generation: int

    event_type = "moderation_case_update"

    def __post_init__(self) -> None:
        _require_moderation_owner(self.owner_id, self.privacy_generation)

    @property
    def event_id(self) -> str:
        return f"moderation-case-opened-{self.case.get('case_id') or ''}"


@dataclass(frozen=True)
class ModerationCaseUpdated:
    """A moderation case was updated or noted; its reporter is told, unless nobody reported it (#139).

    `change_id` names this update: the id of the case history entry it wrote.
    """

    case: Mapping[str, Any]
    actor_id: str
    actor_role: str
    owner_id: str
    privacy_generation: int
    change_id: str

    event_type = "moderation_case_update"

    def __post_init__(self) -> None:
        _require_moderation_owner(self.owner_id, self.privacy_generation)
        if not str(self.change_id or "").strip():
            raise NotificationViolation(_N.NOTIFICATION_EVENT_ID_REQUIRED)

    @property
    def event_id(self) -> str:
        # The history entry's id carries a timestamp and `#`; an event id is a
        # path segment of the bell's read and archive routes, so it is digested.
        return (
            f"moderation-case-update-{self.case.get('case_id') or ''}-"
            f"{_short_digest(self.change_id)}"
        )


@dataclass(frozen=True)
class SubscriptionRequestChanged:
    """A subscription request was made or moved to a new status; `recipient_id=None` tells the role."""

    request: Mapping[str, Any]
    recipient_id: str | None
    recipient_role: str
    actor_id: str
    actor_role: str

    event_type = "subscription_request_update"

    @property
    def event_id(self) -> str:
        return (
            f"subscription-request-{self.request.get('request_id') or ''}-"
            f"{self.request.get('status') or ''}"
        )


Happening = (
    TeacherTookHelpRequest
    | TeacherReplied
    | HelpRequestExpired
    | HelpOffered
    | TeacherPausedAfterLapse
    | HelpOfferClosed
    | ModerationCaseOpened
    | ModerationCaseUpdated
    | SubscriptionRequestChanged
)
