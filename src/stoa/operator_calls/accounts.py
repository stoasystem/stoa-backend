"""The account operations an agent may run that only read (#383).

Each answers with the console's own account projection
(`services.account_listing`), so an agent sees what an administrator sees and
nothing a stored row holds besides: no activation token, password or session
ever leaves through here.

`get_account` also says where the account stands in the deletion pipeline
(#396), read from its fence and deletion command: an account whose deletion was
accepted can still show `active` on its profile until the pipeline reaches it,
and once it does the profile is a tombstone with nothing left to project.
"""

from __future__ import annotations

from collections.abc import Mapping

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, account_number_repo, user_repo
from stoa.operator_calls.catalog import FindAccountsArguments, GetAccountArguments
from stoa.operator_calls.outcome import Outcome
from stoa.services import account_deletion_service, account_listing, usage_period
from stoa.services.account_errors import AccountErrorCode, AccountViolation


class AmbiguousAccount(ValueError):
    """An address held by several accounts; the message names their numbers only."""


def find_accounts(arguments: FindAccountsArguments) -> Outcome:
    page = account_listing.account_page(
        limit=arguments.limit,
        role=arguments.role,
        status=arguments.status,
        keyword=arguments.query,
        cursor=arguments.cursor,
    )
    return Outcome(page, "account_list", "search", f"returned:{page['count']}")


def account_id_by_number(number: str, *, table: object) -> str:
    claim = account_number_repo.get_account_number_claim(number.strip().upper(), table=table)
    return str((claim or {}).get("account_id") or "")


def _profile(
    arguments: GetAccountArguments, *, table: object
) -> tuple[str, Mapping[str, object]]:
    """The account id asked for and its stored profile row, which may be a tombstone."""
    if arguments.userId:
        account_id = arguments.userId.strip()
        profile = user_repo.get_user(account_id, table=table)
    elif arguments.accountNumber:
        account_id = account_id_by_number(arguments.accountNumber, table=table)
        profile = user_repo.get_user(account_id, table=table) if account_id else None
    else:
        profiles = user_repo.get_users_by_email(str(arguments.email).strip().casefold())
        if len(profiles) > 1:
            numbers = sorted(str(item.get("account_number") or "?") for item in profiles)
            raise AmbiguousAccount(
                "This address holds several accounts ("
                + ", ".join(numbers)
                + "); ask again by accountNumber."
            )
        profile = profiles[0] if profiles else None
        account_id = str((profile or {}).get("user_id") or "")
    if not profile or not account_id:
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND)
    return account_id, profile


def usage_period_of(
    profile: Mapping[str, object], *, table: object
) -> dict[str, object] | None:
    role = str(profile.get("role") or "")
    if role not in usage_period.PERIOD_ROLES:
        return None
    period = usage_period.account_period(profile, today=usage_period.zurich_today(None))
    projected: dict[str, object] = {
        "endsOn": period.ends_on.isoformat() if period.ends_on else None,
        "state": period.state.value,
        "version": period.version,
    }
    if role == "student":
        effective = usage_period.effective_for_student(
            period.user_id, profile=profile, table=table
        )
        projected["effective"] = {
            "endsOn": effective.ends_on.isoformat() if effective.ends_on else None,
            "state": effective.state.value,
            "paidBy": effective.paid_by.value if effective.paid_by else None,
            "parentId": effective.parent_id,
        }
    return projected


def deletion_of(account_id: str, *, table: object) -> dict[str, object]:
    """The deletion state an agent sees: none, in_progress or completed, and when."""
    status = account_deletion_service.deletion_status(account_id, table=table)
    if status.state == "none":
        return {"state": "none"}
    projected: dict[str, object] = {
        "state": status.state,
        "commandId": status.command_id,
        "acceptedAt": status.accepted_at,
        "initiatedBy": status.initiated_by,
    }
    if status.state == "completed":
        projected["completedAt"] = status.completed_at
    return projected


def get_account(arguments: GetAccountArguments) -> Outcome:
    table = db_table.table()
    account_id, profile = _profile(arguments, table=table)
    deletion = deletion_of(account_id, table=table)
    if account_deletion_repo.is_deletion_tombstone(profile):
        # The pipeline has replaced the profile: no name, address or role is left.
        number = arguments.accountNumber.strip().upper() if arguments.accountNumber else None
        return Outcome(
            {
                "userId": account_id,
                "accountNumber": number,
                "role": None,
                "accountStatus": None,
                "deletion": deletion,
                "summary": (
                    "This account's profile has been erased by its deletion; only the "
                    "deletion state is left to show."
                ),
            },
            "account",
            account_id,
        )
    items, _ = account_listing.listed_accounts([profile], table=table)
    account = items[0]
    account["usagePeriod"] = usage_period_of(profile, table=table)
    account["deletion"] = deletion
    return Outcome(account, "account", str(account.get("userId") or account_id))
