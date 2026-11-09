"""Account lifecycle: the one way an account's status changes (#209, #289).

Every move of a profile's `account_status` after the account was opened goes
through `transition`. It owns four things the callers used to do each in their
own way, or not at all:

* the table below - which status may follow which, and who may make the move;
* a strict expectation - the commit only lands if the row still holds the status
  the caller read, at the version it read, behind an active account fence;
* the guards - nobody deactivates their own account, and the last active
  administrator cannot be deactivated. The second is restated inside the commit as
  a condition on the other administrator's profile, so two administrators
  deactivating each other at the same moment cannot both succeed;
* an audit row in the same commit, for every move, naming the system as the actor
  when no person made it.

`activated_at` is written on the way to `active`, and only then.

Opening an account (`account_provisioning_service.open_account`, the public
registration and the privileged-identity provisioning) writes the first status,
and is not a transition.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from stoa.db import table as db_table
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import account_deletion_repo, security_audit_repo, user_repo
from stoa.security.identity import AccountStatus
from stoa.services.account_errors import AccountErrorCode, AccountViolation

__all__ = [
    "SYSTEM_ACTOR_ID",
    "TRANSITIONS",
    "LifecycleActor",
    "Trigger",
    "allowed",
    "status_of",
    "transition",
]


class Trigger(StrEnum):
    """Who moves the account: the reason a move is allowed, not just its author."""

    ADMIN = "admin"
    INVITATION_CLAIM = "invitation_claim"
    TEACHER_APPROVAL = "teacher_approval"
    PRIVILEGED_IDENTITY = "privileged_identity"
    SYSTEM = "system"


SYSTEM_ACTOR_ID = "system"


@dataclass(frozen=True, slots=True)
class LifecycleActor:
    """The trigger, and the person behind it when there is one."""

    trigger: Trigger
    user_id: str = SYSTEM_ACTOR_ID
    role: str = SYSTEM_ACTOR_ID

    def __post_init__(self) -> None:
        if not isinstance(self.trigger, Trigger):
            object.__setattr__(self, "trigger", Trigger(self.trigger))
        if not str(self.user_id or "").strip():
            object.__setattr__(self, "user_id", SYSTEM_ACTOR_ID)
            object.__setattr__(self, "role", SYSTEM_ACTOR_ID)

    @classmethod
    def system(cls) -> LifecycleActor:
        return cls(Trigger.SYSTEM)


_S = AccountStatus
_T = Trigger

# Every move there is, and who may make it. A pair that is not here is not a move.
#
# * `invited` is left by its invitee claiming it, or by an administrator archiving
#   an invitation nobody will claim.
# * `pending_review` is left when the review passes: a teacher's application, or a
#   privileged identity whose provider side has been reconciled.
# * `revoked` is the privileged-identity lifecycle's own; an administrator's console
#   suspends and archives, and archive is as far as it goes - nothing leaves it.
# * `provisioning_failed` is where the system parks an opening that died part-way
#   (an invitation, or an assignment that was already `active`). Nothing leaves it.
# * `pending_verification` belongs to the public registration, which activates the
#   account itself on verification; it is listed so the table names that move too.
TRANSITIONS: Mapping[tuple[AccountStatus, AccountStatus], frozenset[Trigger]] = {
    (_S.INVITED, _S.ACTIVE): frozenset({_T.INVITATION_CLAIM}),
    (_S.INVITED, _S.ARCHIVED): frozenset({_T.ADMIN}),
    (_S.INVITED, _S.PROVISIONING_FAILED): frozenset({_T.SYSTEM}),
    (_S.PENDING_VERIFICATION, _S.ACTIVE): frozenset({_T.SYSTEM}),
    (_S.PENDING_REVIEW, _S.ACTIVE): frozenset({_T.TEACHER_APPROVAL, _T.PRIVILEGED_IDENTITY}),
    (_S.ACTIVE, _S.SUSPENDED): frozenset({_T.ADMIN, _T.PRIVILEGED_IDENTITY}),
    (_S.ACTIVE, _S.REVOKED): frozenset({_T.PRIVILEGED_IDENTITY}),
    (_S.ACTIVE, _S.ARCHIVED): frozenset({_T.ADMIN}),
    (_S.ACTIVE, _S.PROVISIONING_FAILED): frozenset({_T.SYSTEM}),
    (_S.SUSPENDED, _S.ACTIVE): frozenset({_T.ADMIN, _T.PRIVILEGED_IDENTITY}),
    (_S.SUSPENDED, _S.REVOKED): frozenset({_T.PRIVILEGED_IDENTITY}),
    (_S.SUSPENDED, _S.ARCHIVED): frozenset({_T.ADMIN}),
    (_S.REVOKED, _S.ACTIVE): frozenset({_T.PRIVILEGED_IDENTITY}),
}


def allowed(expected: AccountStatus, next_status: AccountStatus, trigger: Trigger) -> bool:
    return trigger in TRANSITIONS.get((expected, next_status), frozenset())


def status_of(account: Mapping[str, object] | None) -> AccountStatus | None:
    """The stored status, or None for a row whose status is missing or unknown."""
    try:
        return AccountStatus(str((account or {}).get("account_status") or ""))
    except ValueError:
        return None


def transition(
    account: Mapping[str, object],
    expected: AccountStatus | str | None,
    next: AccountStatus | str,  # noqa: A002 - the name the shape decision gave it
    actor: LifecycleActor,
    reason: str = "",
    *,
    now: datetime | None = None,
    fields: Mapping[str, object] | None = None,
    also: Iterable[dict[str, Any]] = (),
) -> dict[str, object]:
    """Move `account` from `expected` to `next`, or refuse with a rule violation.

    `account` is the profile row as the caller read it; its version is what the
    commit is conditioned on, beside the status. `fields` are further profile fields
    the same move sets, and `also` further operations of the same commit - the
    parking of a failed opening gives its address back that way.

    Returns the audit row it wrote.
    """
    user_id = str(account.get("user_id") or "").strip()
    if not user_id:
        raise AccountViolation(AccountErrorCode.ACCOUNT_PROFILE_MISSING)
    target = _status(next, AccountErrorCode.ACCOUNT_STATUS_TRANSITION_INVALID)
    if target is not AccountStatus.ACTIVE and actor.user_id == user_id:
        _refuse(actor, user_id, AccountErrorCode.ACCOUNT_SELF_DEACTIVATION_FORBIDDEN)
    origin = _status(expected, AccountErrorCode.ACCOUNT_STATUS_UNEXPECTED)
    if status_of(account) is not origin:
        raise AccountViolation(AccountErrorCode.ACCOUNT_STATUS_UNEXPECTED)
    if origin is target:
        raise AccountViolation(AccountErrorCode.ACCOUNT_STATUS_UNCHANGED)
    if not allowed(origin, target, actor.trigger):
        raise AccountViolation(AccountErrorCode.ACCOUNT_STATUS_TRANSITION_INVALID)

    survivor: list[dict[str, Any]] = []
    if (
        origin is AccountStatus.ACTIVE
        and target is not AccountStatus.ACTIVE
        and account.get("role") == "admin"
    ):
        other = user_repo.find_other_active_admin(user_id)
        if other is None:
            _refuse(actor, user_id, AccountErrorCode.ACCOUNT_LAST_ACTIVE_ADMIN)
        survivor.append(user_repo.active_admin_condition(str(other)))

    instant = (now or datetime.now(UTC)).isoformat()
    names = {"#account_status": "account_status"}
    values: dict[str, object] = {
        ":next_status": target.value,
        ":expected_status": origin.value,
        ":now": instant,
    }
    assignments = ["#account_status = :next_status", "updated_at = :now"]
    if target is AccountStatus.ACTIVE:
        assignments.append("activated_at = :now")
    for index, (field, value) in enumerate(sorted((fields or {}).items())):
        if field in {"account_status", "updated_at", "activated_at", "version"}:
            raise ValueError(f"{field} belongs to the transition")
        names[f"#field{index}"] = field
        values[f":field{index}"] = value
        assignments.append(f"#field{index} = :field{index}")
    update = user_repo.profile_update_operation(
        user_id,
        update_expression="SET " + ", ".join(assignments),
        expression_attribute_names=names,
        expression_attribute_values=values,
        expected_version=stored_int(account.get("version")),
        additional_condition_expression="#account_status = :expected_status",
    )
    event = _event(
        actor,
        user_id,
        event_type="account_status_changed",
        reason_code=reason,
        evidence_reference=f"account_status:{origin.value}->{target.value}",
        created_at=instant,
    )
    try:
        db_table.fenced(
            user_id,
            [
                update,
                *survivor,
                security_audit_repo.append_event_operation(user_id, event),
                *also,
            ],
        )
    except (
        account_deletion_repo.AccountDeletionConflict,
        db_table.WriteRefused,
        db_table.TableUnavailable,
    ) as exc:
        raise AccountViolation(AccountErrorCode.ACCOUNT_STATUS_TRANSITION_CONFLICT) from exc
    return event


def _status(value: AccountStatus | str | None, code: AccountErrorCode) -> AccountStatus:
    try:
        return AccountStatus(str(value or ""))
    except ValueError:
        raise AccountViolation(code) from None


def _event(actor: LifecycleActor, user_id: str, **fields: object) -> dict[str, object]:
    return {
        "event_id": f"event_{uuid4().hex}",
        "actor_id": actor.user_id,
        "actor_role": actor.role,
        "target_id": user_id,
        "target_type": "account",
        "action": f"account_status_transition:{actor.trigger.value}",
        **{
            key: (value[:400] if key == "evidence_reference" else value[:200])
            if isinstance(value, str)
            else value
            for key, value in fields.items()
        },
    }


def _refuse(actor: LifecycleActor, user_id: str, code: AccountErrorCode) -> None:
    """A refused move is still a command somebody issued, so it is recorded."""
    security_audit_repo.append_event(
        user_id,
        _event(
            actor,
            user_id,
            event_type="account_status_change_denied",
            reason_code=code.value,
            evidence_reference=f"account_status_denied:{code.value}",
            created_at=datetime.now(UTC).isoformat(),
        ),
    )
    raise AccountViolation(code)
