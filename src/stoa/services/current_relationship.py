"""The one judge of whether a parent-student relationship holds right now.

A relationship is stored as a link: one row on the parent's side
(`PARENT#<parent>/CHILD#<student>`) and its mirror on the student's side
(`STUDENT#<student>/PARENT#<parent>`). This module is the only reader of those
rows for the question "may this parent see this student now", and the only
place that closes one. Every reader that shows one party the other's private
data, or bills one for the other, asks it and nothing else (#208).

The judge answers in three states:

- **current**: both rows are active, agree with each other, and both accounts
  are usable. The answer carries where it came from and the rows' version
  (`link_updated_at`, which every write to the pair advances).
- **known**: the pair is stored on both sides but is not current - pending,
  rejected, revoked, half-agreeing, or an account is not usable. A party to it
  is refused rather than told the student does not exist.
- **unknown**: nothing is stored for the pair.

A student profile's `parent_id` is not a relationship and is never read here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final

from stoa.db.dynamodb import get_table
from stoa.db.repositories import parent_link_repo, user_repo


SOURCE_LINK: Final = parent_link_repo.ENTITY_TYPE

ROLE_PARENT: Final = "parent"
ROLE_STUDENT: Final = "student"


class Standing(StrEnum):
    CURRENT = "current"
    KNOWN = "known"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Verdict:
    """The judge's answer about one parent-student pair.

    `source` and `version` are set whenever rows were found; only a `CURRENT`
    verdict grants anything. `status` is what the parent's side stores.
    """

    standing: Standing
    parent_id: str
    student_id: str
    relationship: str | None = None
    status: str | None = None
    source: str | None = None
    version: str | None = None

    @property
    def is_current(self) -> bool:
        return self.standing is Standing.CURRENT

    @property
    def is_known(self) -> bool:
        """Current or known: a party to it gets a refusal, not a 404."""
        return self.standing is not Standing.UNKNOWN

    def about(self, parent_id: str, student_id: str) -> bool:
        return self.parent_id == parent_id and self.student_id == student_id


def usable_account(profile: Mapping[str, Any] | None, user_id: str, role: str) -> bool:
    """An account that is this user's, holds this role, and is active."""
    if not profile:
        return False
    status = profile.get("account_status") or profile.get("status")
    return (
        profile.get("user_id") == user_id
        and profile.get("role") == role
        and status == "active"
    )


def _about_pair(row: Mapping[str, Any] | None, parent_id: str, student_id: str) -> bool:
    return bool(
        row and row.get("parent_id") == parent_id and row.get("student_id") == student_id
    )


def _rows_current(forward: Mapping[str, Any], reverse: Mapping[str, Any]) -> bool:
    """Both sides active and saying the same thing about the same write."""
    return (
        forward.get("status") == parent_link_repo.STATUS_ACTIVE
        and reverse.get("status") == parent_link_repo.STATUS_ACTIVE
        and bool(forward.get("link_updated_at"))
        and all(
            forward.get(field) == reverse.get(field)
            for field in ("relationship", "link_updated_at")
        )
    )


def _verdict_from_rows(
    standing: Standing,
    parent_id: str,
    student_id: str,
    forward: Mapping[str, Any],
) -> Verdict:
    return Verdict(
        standing=standing,
        parent_id=parent_id,
        student_id=student_id,
        relationship=str(forward.get("relationship") or "child"),
        status=str(forward.get("status") or ""),
        source=SOURCE_LINK,
        version=str(forward.get("link_updated_at") or "") or None,
    )


def _judge_rows(
    parent_id: str,
    student_id: str,
    forward: Mapping[str, Any] | None,
    reverse: Mapping[str, Any] | None,
    *,
    table: Any | None,
) -> Verdict:
    if not _about_pair(forward, parent_id, student_id) or not _about_pair(
        reverse, parent_id, student_id
    ):
        return Verdict(Standing.UNKNOWN, parent_id, student_id)
    assert forward is not None and reverse is not None
    if not _rows_current(forward, reverse):
        return _verdict_from_rows(Standing.KNOWN, parent_id, student_id, forward)
    # The rows first, then the parent, then the student: a pair refused early
    # never reads the next profile, so a failure reading it cannot turn that
    # refusal into an error (#85).
    if not usable_account(
        user_repo.get_user(parent_id, table=table), parent_id, ROLE_PARENT
    ):
        return _verdict_from_rows(Standing.KNOWN, parent_id, student_id, forward)
    if not usable_account(
        user_repo.get_user(student_id, table=table), student_id, ROLE_STUDENT
    ):
        return _verdict_from_rows(Standing.KNOWN, parent_id, student_id, forward)
    return _verdict_from_rows(Standing.CURRENT, parent_id, student_id, forward)


def judge(parent_id: str, student_id: str, *, table: Any | None = None) -> Verdict:
    """Whether this parent and this student are in a relationship right now.

    Every read takes the table it is given, so a test that hands one in can be
    sure nothing here reaches for the ambient table.
    """
    if not parent_id or not student_id:
        return Verdict(Standing.UNKNOWN, parent_id or "", student_id or "")
    forward = parent_link_repo.get_parent_side_link(parent_id, student_id, table=table)
    reverse = parent_link_repo.get_student_side_link(student_id, parent_id, table=table)
    return _judge_rows(parent_id, student_id, forward, reverse, table=table)


def _judged(pairs: list[tuple[str, str]], *, table: Any | None) -> list[Verdict]:
    verdicts: list[Verdict] = []
    seen: set[tuple[str, str]] = set()
    for parent_id, student_id in pairs:
        if not parent_id or not student_id or (parent_id, student_id) in seen:
            continue
        seen.add((parent_id, student_id))
        verdicts.append(judge(parent_id, student_id, table=table))
    return verdicts


def _parent_side_pairs(
    parent_id: str, *, table: Any | None, active_only: bool = False
) -> list[tuple[str, str]]:
    return [
        (parent_id, str(row.get("student_id") or ""))
        for row in parent_link_repo.list_links_for_parent(parent_id, table=table)
        if not active_only or row.get("status") == parent_link_repo.STATUS_ACTIVE
    ]


def children_of(parent_id: str, *, table: Any | None = None) -> list[Verdict]:
    """Every student this parent is currently in a relationship with.

    A listed side that is not active cannot be current, so it is not judged:
    a parent's pending and refused requests cost the list nothing.
    """
    if not parent_id:
        return []
    pairs = _parent_side_pairs(parent_id, table=table, active_only=True)
    return [verdict for verdict in _judged(pairs, table=table) if verdict.is_current]


def parents_of(student_id: str, *, table: Any | None = None) -> list[Verdict]:
    """Every parent currently in a relationship with this student."""
    if not student_id:
        return []
    pairs = [
        (str(row.get("parent_id") or ""), student_id)
        for row in parent_link_repo.list_links_for_student(student_id, table=table)
        if row.get("status") == parent_link_repo.STATUS_ACTIVE
    ]
    return [verdict for verdict in _judged(pairs, table=table) if verdict.is_current]


def known_children_of(parent_id: str, *, table: Any | None = None) -> list[Verdict]:
    """Every pair the parent's side stores, current or not, each judged.

    For the administrator's view of an account, which has to show a
    relationship that is no longer current in order to close it.
    """
    if not parent_id:
        return []
    return [
        verdict
        for verdict in _judged(_parent_side_pairs(parent_id, table=table), table=table)
        if verdict.is_known
    ]


def candidate_pairs(*, table: Any | None = None) -> list[tuple[str, str]]:
    """Every (parent, student) pair whose parent side says active, unjudged.

    Candidates, not relationships: a job that runs over every family scans
    for them here and asks `judge` about each before acting on one.
    """
    target = table or get_table()
    request: dict[str, Any] = {
        "FilterExpression": (
            "#entity = :link AND #status = :active AND begins_with(#sk, :child)"
        ),
        "ExpressionAttributeNames": {
            "#entity": "entity_type",
            "#status": "status",
            "#sk": "SK",
        },
        "ExpressionAttributeValues": {
            ":link": SOURCE_LINK,
            ":active": parent_link_repo.STATUS_ACTIVE,
            ":child": "CHILD#",
        },
    }
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    while True:
        result = target.scan(**request)
        rows = result.get("Items")
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, Mapping):
                continue
            parent_id = row.get("parent_id")
            student_id = row.get("student_id")
            if not isinstance(parent_id, str) or not isinstance(student_id, str):
                continue
            if (parent_id, student_id) not in seen:
                seen.add((parent_id, student_id))
                pairs.append((parent_id, student_id))
        cursor = result.get("LastEvaluatedKey")
        if not isinstance(cursor, Mapping) or not cursor:
            return pairs
        request["ExclusiveStartKey"] = dict(cursor)


# --- Closing a relationship ---------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat()


def revoke(
    parent_id: str,
    student_id: str,
    *,
    actor_id: str,
    now: str | None = None,
    table: Any | None = None,
) -> Verdict | None:
    """Close both sides of a link in one transaction.

    Only a link is closed here; a pair with no open side has nothing to revoke
    and answers `None`. A link whose account is no longer usable, but whose rows
    are still active, is closed all the same: that is exactly the relationship
    an administrator has to be able to end. Each side is conditioned on the
    status and version that was read, so a racer on either side refuses the
    whole write with `parent_link_repo.ParentLinkConflict` and nothing commits.
    """
    if not parent_id or not student_id:
        return None
    forward = parent_link_repo.get_parent_side_link(parent_id, student_id, table=table)
    reverse = parent_link_repo.get_student_side_link(student_id, parent_id, table=table)
    sides = [side for side in (forward, reverse) if _about_pair(side, parent_id, student_id)]
    if not any(side.get("status") == parent_link_repo.STATUS_ACTIVE for side in sides):
        return None
    closed = parent_link_repo.close_link(
        parent_id=parent_id,
        student_id=student_id,
        parent_side=forward if _about_pair(forward, parent_id, student_id) else None,
        student_side=reverse if _about_pair(reverse, parent_id, student_id) else None,
        updated_by=actor_id,
        link_updated_at=now or _now(),
        table=table,
    )
    return _verdict_from_rows(Standing.KNOWN, parent_id, student_id, closed)


# --- Where a parent's copy of a report may go ----------------------------------

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
    if not judge(parent_id, student_id).is_current:
        return ParentRecipient(refusal=RECIPIENT_RELATIONSHIP_REVOKED)
    parent = user_repo.get_user(parent_id) or {}
    email = str(parent.get("email") or "").strip()
    if not email:
        return ParentRecipient(refusal=RECIPIENT_MISSING)
    return ParentRecipient(email=email)
