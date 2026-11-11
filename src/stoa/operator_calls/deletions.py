"""The account deletion an agent may run (#396).

`delete_account` closes one account through the same pipeline as an account
closing itself: `account_deletion_service.accept_account_deletion` moves the same
fence and writes the same `DELETE_COMMAND` row, and the scheduled deletion job
carries it to the end. Only the initiator differs: the command names
`operator:agent_mcp` and the operator's reason, where a self-deletion names the
account and is bound to its token.

Which accounts an agent may close (#396, decisions 1-3):

- a student or parent in any state but the two terminal ones (archived,
  provisioning_failed);
- any account that is not an administrator's while it is still invited;
- never an administrator, nor an account holding any capability grant (a
  privileged identity), nor a teacher past invited: a teacher's replies live in
  their students' conversations, and what the pipeline does to them is not yet
  checked;
- never an account already being deleted, nor one with paid billing still
  standing (`subscription_service.standing_billing`): billing is settled first.
  A usage period an administrator granted does not hold a deletion up.

A dry run only reads and answers with the account, its links, its usage period
and whether it can be deleted, or why not; the one row it leaves is the audit row
of every operator call. The real run also needs `confirmAccountNumber` equal to
`accountNumber`, checks everything again, revokes an open invitation (its link
must not open an account that is being erased) and then accepts the deletion.

Continuation is left to the scheduled deletion job (`stoa.jobs.account_deletion`,
every five minutes), which finds every pending command by its sweep and runs
the branches until the deletion completes. Nothing here runs a branch: the audit
row is written after the runner returns, and a pass of the pipeline inside this
invocation could run the function out of time with the deletion accepted and
neither the audit row nor the answer written.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from stoa.db import table as db_table
from stoa.db.repositories import (
    account_deletion_repo,
    capability_repo,
    user_repo,
)
from stoa.operator_calls import accounts, catalog
from stoa.operator_calls.catalog import DeleteAccountArguments
from stoa.operator_calls.invitations import operator_actor
from stoa.operator_calls.outcome import OperatorCallRefused, Outcome
from stoa.services import (
    account_deletion_service,
    account_listing,
    account_provisioning_service,
    subscription_service,
)
from stoa.services.account_errors import AccountErrorCode, AccountViolation


# Refusal codes, in the style of the invitation tools' `AccountErrorCode` values.
CONFIRMATION_MISMATCH = "confirmation_mismatch"
ROLE_NOT_DELETABLE = "account_role_not_deletable"
TEACHER_NOT_DELETABLE = "teacher_not_deletable"
STATUS_NOT_DELETABLE = "account_status_not_deletable"
DELETION_IN_PROGRESS = "account_deletion_in_progress"
ALREADY_DELETED = "account_already_deleted"
BILLING_ACTIVE = "billing_active"
DELETION_CONFLICT = "account_deletion_conflict"

OPENABLE_ROLES = frozenset({"student", "parent", "teacher"})
TERMINAL_STATES = frozenset({"archived", "provisioning_failed"})

IRREVERSIBLE = (
    "Irreversible: the account's data is erased, its parent-student links end, and "
    "its email address is released when the deletion completes."
)


def _evidence(prefix: str, reason: str) -> str:
    return f"{prefix};reason:{reason}"


def _refusal(
    *,
    role: str,
    state: str,
    grants: list[Mapping[str, object]],
    billing: list[str],
) -> tuple[str, str] | None:
    """The code and the why of the first rule this account fails, or None."""
    if role == "admin":
        return ROLE_NOT_DELETABLE, "An administrator account is not deleted by an agent."
    if grants:
        return (
            ROLE_NOT_DELETABLE,
            f"The account holds {len(grants)} admin capability grant(s); a privileged "
            "account is not deleted by an agent.",
        )
    if role not in OPENABLE_ROLES:
        return ROLE_NOT_DELETABLE, f"An account of role {role or 'unknown'} is not deleted by an agent."
    if role == "teacher" and state != "invited":
        return (
            TEACHER_NOT_DELETABLE,
            "Only a teacher account that is still invited is deleted by an agent; an "
            "activated teacher's account is not.",
        )
    if state in TERMINAL_STATES:
        return STATUS_NOT_DELETABLE, f"An account that is {state} is not deleted by an agent."
    if billing:
        return (
            BILLING_ACTIVE,
            "Paid billing still stands on this account ("
            + "; ".join(billing)
            + "). Settle billing first, then delete.",
        )
    return None


def _payer(usage: Mapping[str, Any] | None, linked: list[Mapping[str, Any]], role: str) -> str | None:
    if not usage:
        return None
    effective = usage.get("effective")
    if isinstance(effective, Mapping):
        if effective.get("paidBy") == "parent":
            parent_id = effective.get("parentId")
            number = next(
                (
                    str(item.get("accountNumber") or "")
                    for item in linked
                    if item.get("userId") == parent_id
                ),
                "",
            )
            return f"parent {number}" if number else "a parent"
        if effective.get("paidBy") == "self":
            return "the student's own period"
        return None
    return "the parent's own period" if role == "parent" and usage.get("endsOn") else None


def delete_account(arguments: DeleteAccountArguments) -> Outcome:
    dry = arguments.dryRun
    reason = arguments.reason.strip()
    number = arguments.accountNumber.strip().upper()
    table = db_table.table()

    account_id = accounts.account_id_by_number(number, table=table)
    if not account_id:
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND)

    def refuse(code: str, why: str) -> OperatorCallRefused:
        return OperatorCallRefused(
            code,
            f"{'Would be refused' if dry else 'Refused'}: account {number}. {why} "
            f"Nothing {'would be' if dry else 'was'} deleted.",
            target_type="account",
            target_id=account_id,
            evidence=_evidence(f"{'would_refuse' if dry else 'refused'}:{code}", reason),
        )

    if not dry and arguments.confirmAccountNumber != arguments.accountNumber:
        raise refuse(
            CONFIRMATION_MISMATCH,
            "confirmAccountNumber must repeat accountNumber exactly, after the person "
            "confirmed the dry run.",
        )

    deletion = account_deletion_service.deletion_status(account_id, table=table)
    if deletion.state == "completed":
        raise refuse(
            ALREADY_DELETED,
            f"It was deleted at {deletion.completed_at} (command {deletion.command_id}).",
        )
    if deletion.state == "in_progress":
        raise refuse(
            DELETION_IN_PROGRESS,
            f"Its deletion was accepted at {deletion.accepted_at} (command "
            f"{deletion.command_id}) and is in progress.",
        )
    profile = user_repo.get_user(account_id, table=table)
    if not profile or account_deletion_repo.is_deletion_tombstone(profile):
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND)

    role = str(profile.get("role") or "")
    state = str(profile.get("account_status") or "")
    listed = account_listing.listed_accounts([profile], table=table)[0][0]
    linked = [dict(item) for item in listed.get("linkedAccounts") or []]
    usage = accounts.usage_period_of(profile, table=table)
    invitation_id = str(listed.get("invitationId") or "") or None
    grants = capability_repo.get_current_grants(account_id, table_factory=lambda: table)
    billing = subscription_service.standing_billing(
        account_id,
        role,
        parent_ids=[str(item.get("userId") or "") for item in linked if role == "student"],
        table=table,
    )
    refusal = _refusal(role=role, state=state, grants=grants, billing=billing)

    facts: dict[str, Any] = {
        "accountNumber": number,
        "userId": account_id,
        "role": role,
        "accountStatus": state,
        "linkedAccounts": linked,
        "usagePeriod": usage,
        "usagePeriodPaidBy": _payer(usage, linked, role),
        "openInvitationId": invitation_id,
    }

    if dry:
        if refusal:
            code, why = refusal
            summary = f"Would be refused: account {number}. {why} Nothing was changed."
        else:
            links = ", ".join(str(item.get("accountNumber") or "?") for item in linked)
            summary = (
                f"Would delete {role} account {number} ({state}). {IRREVERSIBLE}"
                + (f" Links that end: {links}." if links else "")
                + (f" Its open invitation {invitation_id} is revoked first." if invitation_id else "")
                + " Nothing was changed."
            )
        return Outcome(
            {
                "dryRun": True,
                "summary": summary,
                **facts,
                "canDelete": refusal is None,
                "refusal": {"code": refusal[0], "message": refusal[1]} if refusal else None,
                "irreversible": IRREVERSIBLE,
            },
            "account",
            account_id,
            _evidence(
                f"would_refuse:{refusal[0]}" if refusal else f"would_delete:{number}", reason
            ),
        )

    if refusal:
        raise refuse(*refusal)

    revoked: str | None = None
    if invitation_id:
        # Before the fence moves: the revocation is a write of its own, and an open
        # activation link must not outlive the decision to erase the account.
        account_provisioning_service.revoke_invitation(
            actor=operator_actor(), invitation_id=invitation_id
        )
        revoked = invitation_id

    now_iso = datetime.now(UTC).isoformat()
    try:
        account_deletion_repo.get_account_fence(account_id, table=table) or (
            account_deletion_repo.ensure_active_account_fence(
                account_id, now_iso=now_iso, table=table
            )
        )
        receipt = account_deletion_service.accept_account_deletion(
            user_id=account_id,
            initiator=account_deletion_service.OperatorInitiated(
                initiated_by=catalog.OPERATOR_ACTOR_ID, reason=reason
            ),
            now_iso=now_iso,
            table=table,
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise refuse(
            DELETION_CONFLICT,
            "The deletion could not be accepted: the account changed while it was "
            "checked, or it has no account fence. Run the dry run again."
            + (f" Its invitation {revoked} was already revoked." if revoked else ""),
        ) from exc

    return Outcome(
        {
            "dryRun": False,
            "summary": (
                f"Accepted the deletion of {role} account {number}. {IRREVERSIBLE} "
                "The scheduled deletion job carries it out, usually within minutes; "
                "get_account shows it in progress and then completed."
                + (f" Revoked its open invitation {revoked}." if revoked else "")
            ),
            "accountNumber": number,
            "deletionCommandId": receipt.command_id,
            "acceptedAt": receipt.accepted_at,
            "status": receipt.status,
            "revokedInvitationId": revoked,
        },
        "account",
        account_id,
        _evidence(f"account-deletion:{receipt.command_id}", reason),
    )
