"""Parent-student relationships: who may link, who must confirm, who may read.

A link is data visibility. A self-service request therefore only ever reaches
`pending`, and `pending` grants nothing until the other side confirms.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from stoa.db.repositories import parent_link_repo, user_repo
from stoa.models import user as user_model


STATUS_PENDING: Final = parent_link_repo.STATUS_PENDING
STATUS_ACTIVE: Final = parent_link_repo.STATUS_ACTIVE
STATUS_REJECTED: Final = parent_link_repo.STATUS_REJECTED

INITIATOR_ADMIN: Final = parent_link_repo.INITIATOR_ADMIN
INITIATOR_PARENT: Final = parent_link_repo.INITIATOR_PARENT
INITIATOR_STUDENT: Final = parent_link_repo.INITIATOR_STUDENT

ROLE_PARENT: Final = "parent"
ROLE_STUDENT: Final = "student"

# A refused request may be raised again after a cooling-off period, and an
# unanswered one stops holding the pair after this long. Both are judged from
# the stored `link_updated_at` on every read and write path: the table's TTL
# sweep can lag by up to 48 hours, so it can never be the thing that decides.
REJECTED_COOLDOWN: Final = timedelta(days=7)
PENDING_REQUEST_TTL: Final = timedelta(days=14)

type LinkItem = dict[str, Any]

AccountNumberResolver = Callable[[str], str | None]

_account_number_resolver: AccountNumberResolver | None = None


class ParentLinkError(Exception):
    """A link request the caller is not allowed to make, carrying a stable code."""

    def __init__(self, code: str, **details: Any) -> None:
        super().__init__(code)
        self.code = code
        self.details: dict[str, Any] = details


def set_account_number_resolver(resolver: AccountNumberResolver | None) -> None:
    """Wire the account-number lookup owned by the numbering card."""
    global _account_number_resolver
    _account_number_resolver = resolver


def _resolve_account_number(account_number: str) -> str | None:
    if _account_number_resolver is None:
        raise ParentLinkError("account_number_lookup_unavailable")
    return _account_number_resolver(account_number)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _moment(value: object) -> datetime | None:
    """Parse a stored or injected ISO stamp; an unreadable one is not a moment."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _settled_at(link: Mapping[str, Any]) -> datetime | None:
    return _moment(link.get("link_updated_at")) or _moment(link.get("linked_at"))


def _pending_expired(link: Mapping[str, Any], at: datetime | None) -> bool:
    """An unanswered request stops holding the pair once the window has passed.

    A stamp that cannot be read counts as expired: that refuses the confirmation
    and only ever reopens a path to another `pending`, which grants nothing.
    """
    settled = _settled_at(link)
    if settled is None:
        return True
    if at is None:
        return False
    return at - settled >= PENDING_REQUEST_TTL


def _cooldown_remaining(link: Mapping[str, Any], at: datetime | None) -> timedelta:
    settled = _settled_at(link)
    if settled is None or at is None:
        return timedelta(0)
    remaining = (settled + REJECTED_COOLDOWN) - at
    return remaining if remaining > timedelta(0) else timedelta(0)


def _settled_pair(parent_id: str, student_id: str) -> LinkItem | None:
    """Both stored rows, agreeing on status, or nothing worth reasoning about."""
    forward = parent_link_repo.get_parent_side_link(parent_id, student_id)
    reverse = parent_link_repo.get_student_side_link(student_id, parent_id)
    if forward is None or reverse is None:
        return None
    if forward.get("status") != reverse.get("status"):
        return None
    if forward.get("link_updated_at") != reverse.get("link_updated_at"):
        return None
    if not forward.get("link_updated_at"):
        # No stamp, no fence: a reclaim could not be made safe against a racer.
        return None
    return forward


def _account(user_id: str, role: str) -> Mapping[str, Any]:
    profile = user_repo.get_user(user_id)
    if not _usable_account(profile, user_id, role):
        raise ParentLinkError("link_target_not_found")
    assert profile is not None
    return profile


def _usable_account(profile: Mapping[str, Any] | None, user_id: str, role: str) -> bool:
    if not profile:
        return False
    status = profile.get("account_status") or profile.get("status")
    return (
        profile.get("user_id") == user_id
        and profile.get("role") == role
        and status == "active"
    )


def _refuse_self_service_when_minor(
    *profiles: Mapping[str, Any] | None, at: datetime | None
) -> None:
    """Card 008: a link with a minor on either side is the administrator's to make.

    Self-service is "one side proposes, the other confirms", and the whole
    justification for it is that both parties can consent. A minor student
    clicking confirm to establish a supervision relationship that binds them is
    not a consent that stands up, so the self-service path is closed and
    `assign_link` - an administrative act that starts active and asks nobody to
    confirm - is the only way in.

    A birthday that is not known counts as a minor. The rule exists to protect
    minors, and "not known" is precisely the case to be conservative about.
    """
    for profile in profiles:
        if user_model.account_is_minor(profile, at=at):
            raise ParentLinkError("link_requires_administrator")


def _role_of(user_id: str) -> str:
    profile = user_repo.get_user(user_id)
    role = profile.get("role") if profile else None
    if not isinstance(role, str) or not role:
        raise ParentLinkError("link_target_not_found")
    return role


def assign_link(
    *,
    parent_id: str,
    student_id: str,
    actor_id: str,
    relationship: str = "child",
    now: str | None = None,
) -> LinkItem:
    """Administrator assignment: trusted and audited, so it starts active.

    Assignment is an administrative act, not a request, so neither a refusal nor
    an abandoned request stands in its way and no cooling-off period applies.
    """
    _account(parent_id, ROLE_PARENT)
    _account(student_id, ROLE_STUDENT)
    moment = now or _now()
    settled = _settled_pair(parent_id, student_id)
    if settled is not None and _reclaimable_for_admin(settled, _moment(moment)):
        return parent_link_repo.reclaim_link(
            parent_id=parent_id,
            student_id=student_id,
            expected_status=str(settled.get("status") or ""),
            expected_link_updated_at=str(settled.get("link_updated_at") or ""),
            status=STATUS_ACTIVE,
            initiator_role=INITIATOR_ADMIN,
            created_by=actor_id,
            linked_at=moment,
            relationship=relationship,
        )
    return parent_link_repo.create_link(
        parent_id=parent_id,
        student_id=student_id,
        status=STATUS_ACTIVE,
        initiator_role=INITIATOR_ADMIN,
        created_by=actor_id,
        linked_at=moment,
        relationship=relationship,
    )


def _reclaimable_for_admin(link: Mapping[str, Any], at: datetime | None) -> bool:
    status = link.get("status")
    if status == STATUS_REJECTED:
        return True
    return status == STATUS_PENDING and _pending_expired(link, at)


def request_link(
    *,
    requester_id: str,
    counterpart_id: str | None = None,
    counterpart_number: str | None = None,
    relationship: str = "child",
    now: str | None = None,
) -> LinkItem:
    """Self-service request from either side. It stops at `pending` on purpose."""
    requester_role = _role_of(requester_id)
    if requester_role not in {ROLE_PARENT, ROLE_STUDENT}:
        raise ParentLinkError("link_initiator_not_allowed")

    target_id = counterpart_id
    if target_id is None:
        if not counterpart_number:
            raise ParentLinkError("link_target_not_found")
        target_id = _resolve_account_number(counterpart_number)
    if not target_id or target_id == requester_id:
        raise ParentLinkError("link_target_not_found")

    if requester_role == ROLE_PARENT:
        parent_id, student_id = requester_id, target_id
        initiator_role = INITIATOR_PARENT
    else:
        parent_id, student_id = target_id, requester_id
        initiator_role = INITIATOR_STUDENT
    parent_profile = _account(parent_id, ROLE_PARENT)
    student_profile = _account(student_id, ROLE_STUDENT)

    moment = now or _now()
    # After the existence checks above, so the refusal says nothing about an
    # account number that resolves to nothing.
    _refuse_self_service_when_minor(
        parent_profile, student_profile, at=_moment(moment)
    )
    settled = _settled_pair(parent_id, student_id)
    if settled is not None:
        _refuse_unless_reclaimable(settled, _moment(moment))
        return parent_link_repo.reclaim_link(
            parent_id=parent_id,
            student_id=student_id,
            expected_status=str(settled.get("status") or ""),
            expected_link_updated_at=str(settled.get("link_updated_at") or ""),
            status=STATUS_PENDING,
            initiator_role=initiator_role,
            created_by=requester_id,
            linked_at=moment,
            relationship=relationship,
        )

    return parent_link_repo.create_link(
        parent_id=parent_id,
        student_id=student_id,
        status=STATUS_PENDING,
        initiator_role=initiator_role,
        created_by=requester_id,
        linked_at=moment,
        relationship=relationship,
    )


def _refuse_unless_reclaimable(link: Mapping[str, Any], at: datetime | None) -> None:
    """Raise unless this settled pair may be proposed again right now."""
    status = link.get("status")
    if status == STATUS_ACTIVE:
        raise ParentLinkError("link_already_active")
    if status == STATUS_PENDING:
        if not _pending_expired(link, at):
            raise ParentLinkError("link_request_pending")
        return
    if status == STATUS_REJECTED:
        remaining = _cooldown_remaining(link, at)
        if remaining > timedelta(0):
            settled = _settled_at(link)
            assert settled is not None
            raise ParentLinkError(
                "link_rejected_cooldown",
                retryAfterSeconds=int(remaining.total_seconds()),
                retryAt=(settled + REJECTED_COOLDOWN).isoformat(),
            )
        return
    raise ParentLinkError("link_request_pending")


def _confirmer_side(link: Mapping[str, Any]) -> str:
    initiator_role = link.get("initiator_role")
    if initiator_role == INITIATOR_PARENT:
        return str(link.get("student_id") or "")
    if initiator_role == INITIATOR_STUDENT:
        return str(link.get("parent_id") or "")
    raise ParentLinkError("link_confirmation_not_applicable")


def _pending_link(parent_id: str, student_id: str, at: datetime | None) -> LinkItem:
    link = parent_link_repo.get_parent_side_link(parent_id, student_id)
    if link is None or link.get("status") != STATUS_PENDING:
        raise ParentLinkError("link_not_pending")
    if _pending_expired(link, at):
        # An abandoned request must not still be convertible into visibility.
        raise ParentLinkError("link_request_expired")
    return link


def _answer_pending(
    *,
    parent_id: str,
    student_id: str,
    actor_id: str,
    next_status: str,
    now: str | None,
    needs_capable_consent: bool = False,
) -> LinkItem:
    moment = now or _now()
    link = _pending_link(parent_id, student_id, _moment(moment))
    if actor_id != _confirmer_side(link) or actor_id == link.get("created_by"):
        raise ParentLinkError("link_confirmation_not_allowed")
    if needs_capable_consent:
        # After the party check, so a stranger learns nothing about either side.
        _refuse_self_service_when_minor(
            user_repo.get_user(parent_id),
            user_repo.get_user(student_id),
            at=_moment(moment),
        )
    return parent_link_repo.transition_link(
        parent_id=parent_id,
        student_id=student_id,
        expected_status=STATUS_PENDING,
        next_status=next_status,
        updated_by=actor_id,
        link_updated_at=moment,
    )


def confirm_link(
    *, parent_id: str, student_id: str, actor_id: str, now: str | None = None
) -> LinkItem:
    """Only the side that did not ask can turn a request into visibility."""
    return _answer_pending(
        parent_id=parent_id,
        student_id=student_id,
        actor_id=actor_id,
        next_status=STATUS_ACTIVE,
        now=now,
        needs_capable_consent=True,
    )


def reject_link(
    *, parent_id: str, student_id: str, actor_id: str, now: str | None = None
) -> LinkItem:
    """Refusing is not consenting, so a minor is left able to refuse.

    Blocking this would only trap a minor under a request they cannot answer,
    and the refusal grants nothing that needs protecting.
    """
    return _answer_pending(
        parent_id=parent_id,
        student_id=student_id,
        actor_id=actor_id,
        next_status=STATUS_REJECTED,
        now=now,
    )


def _is_active(link: Mapping[str, Any] | None, parent_id: str, student_id: str) -> bool:
    """The single status filter guarding parent visibility."""
    if not link:
        return False
    return (
        link.get("status") == STATUS_ACTIVE
        and link.get("parent_id") == parent_id
        and link.get("student_id") == student_id
    )


def active_link(
    parent_id: str, student_id: str, *, table: object | None = None
) -> LinkItem | None:
    """Return the link only when both directions are active and both accounts are usable.

    Every read here takes the table it is given. This function taking the
    ambient one instead is how `pytest` came to send reads to the live table:
    the module-level binding in `parent_link_repo` could not be reached from
    anywhere a test was stubbing, so nothing a test did could stop it.
    """
    if not parent_id or not student_id:
        return None
    forward = parent_link_repo.get_parent_side_link(parent_id, student_id, table=table)
    reverse = parent_link_repo.get_student_side_link(student_id, parent_id, table=table)
    if not _is_active(forward, parent_id, student_id):
        return None
    if not _is_active(reverse, parent_id, student_id):
        return None
    assert forward is not None
    if not _usable_account(
        user_repo.get_user(parent_id, table=table), parent_id, ROLE_PARENT
    ):
        return None
    if not _usable_account(
        user_repo.get_user(student_id, table=table), student_id, ROLE_STUDENT
    ):
        return None
    return parent_link_repo.link_fields(forward)


def known_link(parent_id: str, student_id: str) -> LinkItem | None:
    """Return the link in whatever status it holds, for parties that already know it exists."""
    if not parent_id or not student_id:
        return None
    forward = parent_link_repo.get_parent_side_link(parent_id, student_id)
    reverse = parent_link_repo.get_student_side_link(student_id, parent_id)
    if forward is None or reverse is None:
        return None
    if forward.get("parent_id") != parent_id or forward.get("student_id") != student_id:
        return None
    return parent_link_repo.link_fields(forward)


def active_children(parent_id: str) -> list[LinkItem]:
    """Active children only; a pending request must never reach a parent's list."""
    children: list[LinkItem] = []
    for link in parent_link_repo.list_links_for_parent(parent_id):
        student_id = str(link.get("student_id") or "")
        if not _is_active(link, parent_id, student_id):
            continue
        confirmed = active_link(parent_id, student_id)
        if confirmed is not None:
            children.append(confirmed)
    return children


def _live_pending(link: Mapping[str, Any], at: datetime | None) -> bool:
    return link.get("status") == STATUS_PENDING and not _pending_expired(link, at)


def pending_requests_for_parent(parent_id: str, *, now: str | None = None) -> list[LinkItem]:
    at = _moment(now or _now())
    return [
        parent_link_repo.link_fields(link)
        for link in parent_link_repo.list_links_for_parent(parent_id)
        if _live_pending(link, at)
    ]


def pending_requests_for_student(student_id: str, *, now: str | None = None) -> list[LinkItem]:
    at = _moment(now or _now())
    return [
        parent_link_repo.link_fields(link)
        for link in parent_link_repo.list_links_for_student(student_id)
        if _live_pending(link, at)
    ]


# --- The one judge of "is this relationship valid right now" -----------------
#
# Two key spaces hold parent-student relationships: the new bidirectional
# `parent_student_link` rows and the legacy `parent_student_binding` rows. A
# student profile's `parent_id` is a third thing and is not one of them: it is a
# projection of a binding that may since have been revoked or deleted, so
# holding that identifier is not a grant. Every read path that shows one party
# the other's private data asks the functions below and nothing else.

RELATIONSHIP_SOURCE_LINK: Final = parent_link_repo.ENTITY_TYPE
RELATIONSHIP_SOURCE_BINDING: Final = "parent_student_binding"

# The coordinates both legacy rows must agree on before either is believed.
_BINDING_COORDINATES: Final = ("parent_id", "student_id", "relationship", "version")


def _relationship(
    row: Mapping[str, Any], source: str, parent_id: str, student_id: str
) -> LinkItem:
    return {
        "parent_id": parent_id,
        "student_id": student_id,
        "relationship": row.get("relationship") or "child",
        "status": STATUS_ACTIVE,
        "source": source,
    }


def _active_legacy_binding(parent_id: str, student_id: str) -> LinkItem | None:
    """The legacy binding, only when both rows agree and both accounts are usable."""
    forward = user_repo.get_parent_student_binding(parent_id, student_id)
    reverse = user_repo.get_student_parent_binding(student_id, parent_id)
    if not forward or not reverse:
        return None
    if forward.get("status") != STATUS_ACTIVE or reverse.get("status") != STATUS_ACTIVE:
        return None
    if any(forward.get(key) != reverse.get(key) for key in _BINDING_COORDINATES):
        return None
    if forward.get("parent_id") != parent_id or forward.get("student_id") != student_id:
        return None
    if not _usable_account(user_repo.get_user(parent_id), parent_id, ROLE_PARENT):
        return None
    if not _usable_account(user_repo.get_user(student_id), student_id, ROLE_STUDENT):
        return None
    return dict(forward)


def current_relationship(parent_id: str, student_id: str) -> LinkItem | None:
    """Whether this parent may read this student's private data right now."""
    if not parent_id or not student_id:
        return None
    link = active_link(parent_id, student_id)
    if link is not None:
        return _relationship(link, RELATIONSHIP_SOURCE_LINK, parent_id, student_id)
    binding = _active_legacy_binding(parent_id, student_id)
    if binding is None:
        return None
    return _relationship(binding, RELATIONSHIP_SOURCE_BINDING, parent_id, student_id)


RECIPIENT_RELATIONSHIP_REVOKED: Final = "relationship_revoked"
RECIPIENT_MISSING: Final = "recipient_missing"


@dataclass(frozen=True)
class ParentRecipient:
    """Where a parent's copy of a child's report may go right now.

    Exactly one of `email` and `refusal` is set. The two refusals are kept
    apart because they call for different people: a relationship that ended
    is correct as it is, a current parent with no address needs fixing.
    """

    email: str | None = None
    refusal: str | None = None


def current_parent_recipient(parent_id: str, student_id: str) -> ParentRecipient:
    """Judge the relationship now and read the parent's address from their profile.

    Called at the moment of sending, never earlier: anything stored alongside
    the report says who was entitled when it was written, not who is now.
    """
    if current_relationship(parent_id, student_id) is None:
        return ParentRecipient(refusal=RECIPIENT_RELATIONSHIP_REVOKED)
    parent = user_repo.get_user(parent_id) or {}
    email = str(parent.get("email") or "").strip()
    if not email:
        return ParentRecipient(refusal=RECIPIENT_MISSING)
    return ParentRecipient(email=email)


def _current_from_candidates(pairs: list[tuple[str, str]]) -> list[LinkItem]:
    relationships: list[LinkItem] = []
    seen: set[tuple[str, str]] = set()
    for parent_id, student_id in pairs:
        if not parent_id or not student_id or (parent_id, student_id) in seen:
            continue
        seen.add((parent_id, student_id))
        relationship = current_relationship(parent_id, student_id)
        if relationship is not None:
            relationships.append(relationship)
    return relationships


def current_children(parent_id: str) -> list[LinkItem]:
    """Every student this parent may currently see, from both key spaces."""
    if not parent_id:
        return []
    candidates = [
        (parent_id, str(link.get("student_id") or ""))
        for link in parent_link_repo.list_links_for_parent(parent_id)
    ]
    candidates.extend(
        (parent_id, str(binding.get("student_id") or ""))
        for binding in user_repo.list_parent_student_bindings(parent_id)
    )
    return _current_from_candidates(candidates)


def current_parents(student_id: str) -> list[LinkItem]:
    """Every parent who may currently see this student, from both key spaces."""
    if not student_id:
        return []
    candidates = [
        (str(link.get("parent_id") or ""), student_id)
        for link in parent_link_repo.list_links_for_student(student_id)
    ]
    candidates.extend(
        (str(binding.get("parent_id") or ""), student_id)
        for binding in user_repo.list_student_parent_bindings(student_id)
    )
    return _current_from_candidates(candidates)
