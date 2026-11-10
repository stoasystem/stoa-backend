"""How the administration surfaces show an account: one projection, two callers.

The console's `GET /admin/users` and the operator calls an agent makes (#383)
list the same accounts with the same fields. Both build each row here, from
fields named on purpose, so neither can publish a stored field the other does
not.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone

from stoa.db import table as db_table
from stoa.db.repositories import account_invitation_repo, parent_link_repo, user_repo
from stoa.models import user as user_model
from stoa.security.identity import AccountStatus
from stoa.services import current_relationship, usage_period
from stoa.services.account_errors import AccountErrorCode, AccountViolation


def _account_number_of(user_id: str) -> str:
    profile = user_repo.get_user(user_id)
    return str((profile or {}).get("account_number") or "")


def _linked_counterparts(profile: Mapping[str, object]) -> list[dict[str, str]]:
    """Current relationships only, as the judge sees them; a pending request is not one."""
    role = str(profile.get("role") or "")
    user_id = str(profile.get("user_id") or "")
    if not user_id:
        return []
    if role == "parent":
        counterparts = [
            verdict.student_id for verdict in current_relationship.children_of(user_id)
        ]
    elif role == "student":
        counterparts = [
            verdict.parent_id for verdict in current_relationship.parents_of(user_id)
        ]
    else:
        return []
    return [
        {
            "userId": counterpart_id,
            "accountNumber": _account_number_of(counterpart_id),
            "status": parent_link_repo.STATUS_ACTIVE,
        }
        for counterpart_id in counterparts
        if counterpart_id
    ]


# Card 002-D / B2: this list answers `student_support_lookup`, the support desk
# capability, one rung below the identity manager. The listed account is therefore
# built from the fields named here rather than from the stored row minus whatever
# looked secret, so a field a later card adds to the PROFILE row stays unpublished
# until somebody puts it on this list on purpose.
ACCOUNT_LIST_FIELDS: tuple[tuple[str, str], ...] = (
    ("userId", "user_id"),
    ("accountNumber", "account_number"),
    ("name", "name"),
    ("email", "email"),
    ("role", "role"),
    ("createdAt", "created_at"),
    ("lastLoginAt", "last_login_at"),
)


def _project_account_row(
    profile: Mapping[str, object], *, account_status: str, at: datetime | None = None
) -> dict[str, object]:
    """Construct one listed account from named scalars, never by redacting a row."""
    projected: dict[str, object] = {}
    for exposed, stored in ACCOUNT_LIST_FIELDS:
        value = profile.get(stored)
        if value is None:
            projected[exposed] = ""
            continue
        if not isinstance(value, (str, int, bool)):
            raise RuntimeError("admin data dependency unavailable")
        projected[exposed] = value if isinstance(value, str) else str(value)
    projected["accountStatus"] = account_status
    # Card 008: the console needs to know which accounts must be linked by an
    # administrator. It gets the answer, never the date - a birthday is personal
    # data, and `ACCOUNT_LIST_FIELDS` above stays the only door a stored field
    # leaves by.
    # The moment is a parameter so a test can pin one: read from the clock here,
    # the only assertion on this value would be true until the fixture's child
    # grew up, and then fail on a date nobody chose.
    projected["isMinor"] = user_model.account_is_minor(
        profile, at=at or datetime.now(timezone.utc)
    )
    # `isMinor` is fail-closed: an account with no stored birthday answers "minor"
    # so that every protection decision errs the safe way. Shown on its own that
    # reads as a fact about the person, and the console was labelling every
    # account - administrators included - a minor. This says whether anybody ever
    # told us, so the console can say "unknown" instead of guessing. Still no date.
    projected["minorKnown"] = bool(
        str(profile.get(user_model.DATE_OF_BIRTH_FIELD) or "").strip()
    )
    return projected


def _listed_usage_period_end(profile: Mapping[str, object]) -> str | None:
    try:
        ends_on = usage_period.stored_end(profile)
    except ValueError as exc:
        raise RuntimeError("admin data dependency unavailable") from exc
    return ends_on.isoformat() if ends_on else None


def listed_accounts(
    profiles: Iterable[Mapping[str, object]], *, table: object
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Each profile as the console lists it, and how many of each role."""
    profiles = list(profiles)
    invitation_ids = account_invitation_repo.issued_invitation_ids(
        (
            profile
            for profile in profiles
            if str(profile.get("account_status") or "") == AccountStatus.INVITED
        ),
        table=table,
    )

    items: list[dict[str, object]] = []
    groups: dict[str, int] = {}
    for profile in profiles:
        row_role = str(profile.get("role") or "unknown")
        groups[row_role] = groups.get(row_role, 0) + 1
        item = _project_account_row(
            profile, account_status=str(profile.get("account_status") or "")
        )
        item["role"] = row_role
        item["linkedAccounts"] = _linked_counterparts(profile)
        # #239: the console lists each account's own end date. Named here on
        # purpose, as `ACCOUNT_LIST_FIELDS` names the rest; null without one.
        item["usagePeriodEndsAt"] = _listed_usage_period_end(profile)
        invitation_id = invitation_ids.get(str(profile.get("user_id") or ""))
        if invitation_id:
            item["invitationId"] = invitation_id
        items.append(item)
    return items, groups


def account_page(
    *,
    limit: int,
    role: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    cursor: str | None = None,
) -> dict[str, object]:
    """One page of accounts, grouped by role, with their confirmed parent links.

    What `GET /admin/users` answers; its docstring says what a page costs and
    which test pins that.
    """
    table = db_table.table()
    try:
        page = user_repo.list_accounts(
            limit=limit,
            role=role,
            status=status,
            keyword=keyword,
            created_from=created_from,
            created_to=created_to,
            cursor=cursor,
            table=table,
        )
    except user_repo.InvalidAccountCursor as exc:
        raise AccountViolation(AccountErrorCode.CURSOR_INVALID) from exc
    items, groups = listed_accounts(page.profiles, table=table)
    return {
        "items": items,
        "count": len(items),
        "groups": groups,
        "nextCursor": page.next_cursor,
    }
