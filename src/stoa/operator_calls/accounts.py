"""The account operations an agent may run that only read (#383).

Each answers with the console's own account projection
(`services.account_listing`), so an agent sees what an administrator sees and
nothing a stored row holds besides: no activation token, password or session
ever leaves through here.
"""

from __future__ import annotations

from collections.abc import Mapping

from stoa.db import table as db_table
from stoa.db.repositories import account_number_repo, user_repo
from stoa.operator_calls.catalog import FindAccountsArguments, GetAccountArguments
from stoa.operator_calls.outcome import Outcome
from stoa.services import account_listing, usage_period
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


def _profile(arguments: GetAccountArguments, *, table: object) -> Mapping[str, object]:
    if arguments.userId:
        profile = user_repo.get_user(arguments.userId.strip(), table=table)
    elif arguments.accountNumber:
        claim = account_number_repo.get_account_number_claim(
            arguments.accountNumber.strip().upper(), table=table
        )
        account_id = str((claim or {}).get("account_id") or "")
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
    if not profile:
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND)
    return profile


def _usage_period(profile: Mapping[str, object], *, table: object) -> dict[str, object] | None:
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


def get_account(arguments: GetAccountArguments) -> Outcome:
    table = db_table.table()
    profile = _profile(arguments, table=table)
    items, _ = account_listing.listed_accounts([profile], table=table)
    account = items[0]
    account["usagePeriod"] = _usage_period(profile, table=table)
    return Outcome(account, "account", str(account.get("userId") or ""))
