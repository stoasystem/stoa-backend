"""Parent-student relationships: who may link, who must confirm, who may read.

A link is data visibility. A self-service request therefore only ever reaches
`pending`, and `pending` grants nothing until the other side confirms.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Final

from stoa.db.repositories import parent_link_repo, user_repo


STATUS_PENDING: Final = parent_link_repo.STATUS_PENDING
STATUS_ACTIVE: Final = parent_link_repo.STATUS_ACTIVE
STATUS_REJECTED: Final = parent_link_repo.STATUS_REJECTED

INITIATOR_ADMIN: Final = parent_link_repo.INITIATOR_ADMIN
INITIATOR_PARENT: Final = parent_link_repo.INITIATOR_PARENT
INITIATOR_STUDENT: Final = parent_link_repo.INITIATOR_STUDENT

ROLE_PARENT: Final = "parent"
ROLE_STUDENT: Final = "student"

type LinkItem = dict[str, Any]

AccountNumberResolver = Callable[[str], str | None]

_account_number_resolver: AccountNumberResolver | None = None


class ParentLinkError(Exception):
    """A link request the caller is not allowed to make, carrying a stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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
    """Administrator assignment: trusted and audited, so it starts active."""
    _account(parent_id, ROLE_PARENT)
    _account(student_id, ROLE_STUDENT)
    return parent_link_repo.create_link(
        parent_id=parent_id,
        student_id=student_id,
        status=STATUS_ACTIVE,
        initiator_role=INITIATOR_ADMIN,
        created_by=actor_id,
        linked_at=now or _now(),
        relationship=relationship,
    )


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
    _account(parent_id, ROLE_PARENT)
    _account(student_id, ROLE_STUDENT)

    return parent_link_repo.create_link(
        parent_id=parent_id,
        student_id=student_id,
        status=STATUS_PENDING,
        initiator_role=initiator_role,
        created_by=requester_id,
        linked_at=now or _now(),
        relationship=relationship,
    )


def _confirmer_side(link: Mapping[str, Any]) -> str:
    initiator_role = link.get("initiator_role")
    if initiator_role == INITIATOR_PARENT:
        return str(link.get("student_id") or "")
    if initiator_role == INITIATOR_STUDENT:
        return str(link.get("parent_id") or "")
    raise ParentLinkError("link_confirmation_not_applicable")


def _pending_link(parent_id: str, student_id: str) -> LinkItem:
    link = parent_link_repo.get_parent_side_link(parent_id, student_id)
    if link is None or link.get("status") != STATUS_PENDING:
        raise ParentLinkError("link_not_pending")
    return link


def _answer_pending(
    *, parent_id: str, student_id: str, actor_id: str, next_status: str, now: str | None
) -> LinkItem:
    link = _pending_link(parent_id, student_id)
    if actor_id != _confirmer_side(link) or actor_id == link.get("created_by"):
        raise ParentLinkError("link_confirmation_not_allowed")
    return parent_link_repo.transition_link(
        parent_id=parent_id,
        student_id=student_id,
        expected_status=STATUS_PENDING,
        next_status=next_status,
        updated_by=actor_id,
        link_updated_at=now or _now(),
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
    )


def reject_link(
    *, parent_id: str, student_id: str, actor_id: str, now: str | None = None
) -> LinkItem:
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


def active_link(parent_id: str, student_id: str) -> LinkItem | None:
    """Return the link only when both directions are active and both accounts are usable."""
    if not parent_id or not student_id:
        return None
    forward = parent_link_repo.get_parent_side_link(parent_id, student_id)
    reverse = parent_link_repo.get_student_side_link(student_id, parent_id)
    if not _is_active(forward, parent_id, student_id):
        return None
    if not _is_active(reverse, parent_id, student_id):
        return None
    assert forward is not None
    if not _usable_account(user_repo.get_user(parent_id), parent_id, ROLE_PARENT):
        return None
    if not _usable_account(user_repo.get_user(student_id), student_id, ROLE_STUDENT):
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


def pending_requests_for_parent(parent_id: str) -> list[LinkItem]:
    return [
        parent_link_repo.link_fields(link)
        for link in parent_link_repo.list_links_for_parent(parent_id)
        if link.get("status") == STATUS_PENDING
    ]


def pending_requests_for_student(student_id: str) -> list[LinkItem]:
    return [
        parent_link_repo.link_fields(link)
        for link in parent_link_repo.list_links_for_student(student_id)
        if link.get("status") == STATUS_PENDING
    ]
