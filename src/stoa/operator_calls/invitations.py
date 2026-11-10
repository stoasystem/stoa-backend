"""The invitation operations an agent may run: invite, reissue, revoke (#384).

Each one mirrors an admin console route - `POST /admin/users/invitations`,
`POST /admin/users/invitations/{id}/reissue` and `DELETE /admin/users/invitations/{id}` -
by calling the same service with the same mail delivery, so an invitation an agent
sends is the one an administrator would have sent.

Each takes `dryRun`. A dry run only reads: it creates no account, sends no mail,
claims no address and writes no business row; the one row it leaves is the audit
row every operator call leaves. It answers with what the real run would do, or
refuses the way the real run would, naming the account involved by its number.
The real run checks the same things first and then lets the service decide on its
own conditional writes, which still hold if the state moved in between.

Answers carry account numbers, ids, roles and states. The activation token the
service hands back is dropped here and never leaves the function; neither does any
stored token digest.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from stoa.db import table as db_table
from stoa.db.repositories import (
    account_invitation_repo,
    account_number_repo,
    capability_repo,
    user_repo,
)
from stoa.operator_calls import catalog
from stoa.operator_calls.catalog import (
    InviteAccountArguments,
    ReissueInvitationArguments,
    RevokeInvitationArguments,
)
from stoa.operator_calls.outcome import OperatorCallRefused, Outcome
from stoa.services import account_provisioning_service, notify_service
from stoa.services.account_errors import AccountErrorCode, AccountViolation


LANGUAGES = {"de": "German", "en": "English", "fr": "French", "it": "Italian"}


def operator_actor() -> dict[str, Any]:
    """The actor the provisioning service sees for an operator call.

    The service asks its caller to be an active account administrator holding
    `admin_identity_manager`. An operator call has already been verified as an AWS
    SSO session of the production account, the trust tier above every administrator
    (`scripts/operator_capability.py`), so it stands as one under its own id: every
    account row, invitation row and service audit row it causes names
    `operator:agent_mcp`, never a web account. No grant is stored for it.
    """
    return {
        "user_id": catalog.OPERATOR_ACTOR_ID,
        "role": "admin",
        "account_status": "active",
        "capabilities": {capability_repo.ADMIN_IDENTITY_MANAGER: True},
    }


def _language(locale: str | None) -> tuple[str, str]:
    code = notify_service.account_invitation_locale(locale)
    return code, LANGUAGES.get(code, code)


def _expiry(seconds: int | None) -> int:
    if seconds is None:
        return account_provisioning_service.DEFAULT_INVITATION_SECONDS
    return seconds


def _number(profile: Mapping[str, object] | None) -> str:
    return str((profile or {}).get("account_number") or "").strip() or "no account number"


# -- invite ----------------------------------------------------------------------------


def invite_account(arguments: InviteAccountArguments) -> Outcome:
    dry = arguments.dryRun
    checked = account_provisioning_service.check_invitation(
        role=arguments.role,
        email=arguments.email,
        date_of_birth=arguments.dateOfBirth,
    )
    role, address = str(checked["role"]), str(checked["email"])
    holder = checked["holder"]
    if holder:
        state = str(holder.get("account_status") or "unknown")
        raise OperatorCallRefused(
            AccountErrorCode.ACCOUNT_EXISTS.value,
            f"{'Would be refused' if dry else 'Refused'}: this address already holds a "
            f"{role} account ({_number(holder)}, {state}). Nothing "
            f"{'would be' if dry else 'was'} created or sent.",
            target_type="account",
            target_id=str(holder.get("user_id") or ""),
        )
    locale, language = _language(arguments.locale)
    expiry = _expiry(arguments.expirySeconds)
    if dry:
        return Outcome(
            {
                "dryRun": True,
                "summary": (
                    f"Would create a {role} account in state invited and send a "
                    f"{language} activation email to {address}. Its account number is "
                    "allocated when it runs. Nothing was created or sent."
                ),
                "role": role,
                "email": address,
                "accountStatus": "invited",
                "emailLanguage": locale,
                "expirySeconds": expiry,
            },
            "account",
            "",
            f"would_invite:{role}",
        )
    issued = account_provisioning_service.invite_account(
        actor=operator_actor(),
        role=role,
        email=address,
        full_name=arguments.fullName,
        date_of_birth=arguments.dateOfBirth,
        invitation_expiry_seconds=expiry,
        deliver=notify_service.account_invitation_delivery(locale),
    )
    user_id = str(issued.get("userId") or "")
    number = str(issued.get("accountNumber") or "")
    invitation_id = str(issued.get("invitationId") or "")
    delivered = issued.get("invitationDelivered") is True
    summary = f"Created {role} account {number} in state invited and " + (
        f"sent a {language} activation email."
        if delivered
        else "could not send the activation email; reissue the invitation once mail works."
    )
    return Outcome(
        {
            "dryRun": False,
            "summary": summary,
            "userId": user_id,
            "accountNumber": number,
            "role": role,
            "accountStatus": str(issued.get("accountStatus") or "invited"),
            "invitationId": invitation_id,
            "invitationStatus": account_invitation_repo.ISSUED_STATUS,
            "invitationDelivered": delivered,
            "emailLanguage": locale,
            "expiresAt": str(issued.get("expiresAt") or ""),
        },
        "account",
        user_id,
        f"account-invitation:{invitation_id}",
    )


# -- the invitation an agent names -----------------------------------------------------


def _resolve(
    arguments: ReissueInvitationArguments | RevokeInvitationArguments,
) -> tuple[Mapping[str, object], Mapping[str, object] | None]:
    """The invitation and the account it was opened for, by invitation id or number."""
    table = db_table.table()
    if arguments.invitationId:
        invitation = account_invitation_repo.get_invitation_by_id(
            arguments.invitationId.strip(), table=table
        )
        if not invitation:
            raise AccountViolation(AccountErrorCode.INVITATION_NOT_FOUND)
        account_id = str(invitation.get("account_id") or "")
        profile = user_repo.get_user(account_id, table=table) if account_id else None
        return invitation, profile
    number = str(arguments.accountNumber).strip().upper()
    claim = account_number_repo.get_account_number_claim(number, table=table)
    account_id = str((claim or {}).get("account_id") or "")
    profile = user_repo.get_user(account_id, table=table) if account_id else None
    if not profile:
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND)
    invitation_id = account_invitation_repo.issued_invitation_ids([profile], table=table).get(
        account_id
    )
    found = (
        account_invitation_repo.get_invitation_by_id(invitation_id, table=table)
        if invitation_id
        else None
    )
    if not found:
        raise OperatorCallRefused(
            AccountErrorCode.INVITATION_NOT_FOUND.value,
            f"Account {number} ({profile.get('account_status') or 'unknown'}) has no open "
            "invitation.",
            target_type="account",
            target_id=account_id,
        )
    return found, profile


def _state(
    invitation: Mapping[str, object], profile: Mapping[str, object] | None
) -> dict[str, Any]:
    """The invitation as an agent may see it: ids, numbers and states, no digest."""
    expires_at = str(invitation.get("expires_at_iso") or "")
    expired: bool | None
    try:
        expired = datetime.fromisoformat(expires_at) <= datetime.now(UTC)
    except (TypeError, ValueError):
        expired = None
    return {
        "invitationId": str(invitation.get("invitation_id") or ""),
        "invitationStatus": str(invitation.get("status") or ""),
        "expiresAt": expires_at or None,
        "expired": expired,
        "userId": str(invitation.get("account_id") or ""),
        "accountNumber": str(invitation.get("account_number") or "")
        or str((profile or {}).get("account_number") or ""),
        "role": str(invitation.get("role") or ""),
        "accountStatus": str((profile or {}).get("account_status") or "") or None,
    }


def _describe(state: Mapping[str, Any]) -> str:
    validity = " and expired" if state["expired"] else ""
    return (
        f"invitation {state['invitationId']} is {state['invitationStatus']}{validity}; "
        f"{state['role']} account {state['accountNumber'] or 'without a number'} is "
        f"{state['accountStatus'] or 'missing'}"
    )


def _refuse(
    code: AccountErrorCode, *, dry: bool, state: Mapping[str, Any], why: str
) -> OperatorCallRefused:
    return OperatorCallRefused(
        code.value,
        f"{'Would be refused' if dry else 'Refused'}: {_describe(state)}. {why}",
        target_type="account",
        target_id=str(state["userId"]),
    )


# -- reissue ---------------------------------------------------------------------------


def reissue_invitation(arguments: ReissueInvitationArguments) -> Outcome:
    dry = arguments.dryRun
    invitation, profile = _resolve(arguments)
    state = _state(invitation, profile)
    status = state["invitationStatus"]
    # Reissuing an administrator's invitation would hand out a new administrator
    # link; opening administrators stays off the agent's list (#380, decision 3).
    if state["role"] == "admin":
        raise _refuse(
            AccountErrorCode.ROLE_NOT_PROVISIONABLE,
            dry=dry,
            state=state,
            why="An administrator invitation is reissued in the admin console, not by an agent.",
        )
    if status == account_invitation_repo.USED_STATUS:
        raise _refuse(
            AccountErrorCode.INVITATION_ALREADY_USED,
            dry=dry,
            state=state,
            why="A used invitation cannot be reissued.",
        )
    if status != account_invitation_repo.ISSUED_STATUS:
        raise _refuse(
            AccountErrorCode.INVITATION_NOT_REISSUABLE,
            dry=dry,
            state=state,
            why="Only an open invitation can be reissued.",
        )
    if state["accountStatus"] != "invited":
        raise _refuse(
            AccountErrorCode.ACCOUNT_NOT_INVITED,
            dry=dry,
            state=state,
            why="Only an account that is still invited can be sent a new invitation.",
        )
    locale, language = _language(arguments.locale)
    expiry = _expiry(arguments.expirySeconds)
    target = str(state["userId"])
    if dry:
        return Outcome(
            {
                "dryRun": True,
                "summary": (
                    f"Now: {_describe(state)}. Would retire this invitation, so its link "
                    f"stops working, and send a new {language} activation email; the "
                    "account and its number stay. Nothing was changed or sent."
                ),
                **state,
                "emailLanguage": locale,
                "expirySeconds": expiry,
            },
            "account",
            target,
            f"would_reissue:account-invitation:{state['invitationId']}",
        )
    issued = account_provisioning_service.reissue_invitation(
        actor=operator_actor(),
        invitation_id=str(state["invitationId"]),
        invitation_expiry_seconds=expiry,
        deliver=notify_service.account_invitation_delivery(locale),
    )
    new_id = str(issued.get("invitationId") or "")
    delivered = issued.get("invitationDelivered") is True
    summary = f"Retired invitation {state['invitationId']} and issued {new_id}; " + (
        f"sent a {language} activation email."
        if delivered
        else "could not send the activation email; reissue again once mail works."
    )
    return Outcome(
        {
            "dryRun": False,
            "summary": summary,
            "userId": str(issued.get("userId") or target),
            "accountNumber": str(issued.get("accountNumber") or state["accountNumber"]),
            "role": str(issued.get("role") or state["role"]),
            "accountStatus": "invited",
            "invitationId": new_id,
            "invitationStatus": account_invitation_repo.ISSUED_STATUS,
            "replacedInvitationId": str(state["invitationId"]),
            "invitationDelivered": delivered,
            "emailLanguage": locale,
            "expiresAt": str(issued.get("expiresAt") or ""),
        },
        "account",
        target,
        f"account-invitation:{new_id};replaced:{state['invitationId']}",
    )


# -- revoke ----------------------------------------------------------------------------


def revoke_invitation(arguments: RevokeInvitationArguments) -> Outcome:
    dry = arguments.dryRun
    invitation, profile = _resolve(arguments)
    state = _state(invitation, profile)
    if state["invitationStatus"] != account_invitation_repo.ISSUED_STATUS:
        raise _refuse(
            AccountErrorCode.INVITATION_NOT_REVOCABLE,
            dry=dry,
            state=state,
            why="Only an open invitation can be revoked.",
        )
    target = str(state["userId"])
    if dry:
        return Outcome(
            {
                "dryRun": True,
                "summary": (
                    f"Now: {_describe(state)}. Would revoke this invitation, so its link "
                    "stops working; the account stays as it is. Nothing was changed."
                ),
                **state,
            },
            "account",
            target,
            f"would_revoke:account-invitation:{state['invitationId']}",
        )
    revoked = account_provisioning_service.revoke_invitation(
        actor=operator_actor(), invitation_id=str(state["invitationId"])
    )
    number = state["accountNumber"] or "without a number"
    return Outcome(
        {
            "dryRun": False,
            "summary": (
                f"Revoked invitation {state['invitationId']}; its link no longer works. "
                f"The {state['role']} account {number} stays "
                f"{state['accountStatus'] or 'as it was'}."
            ),
            **state,
            "invitationStatus": str(
                revoked.get("status") or account_invitation_repo.REVOKED_STATUS
            ),
        },
        "account",
        target,
        f"account-invitation:{state['invitationId']}",
    )
