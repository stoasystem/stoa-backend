"""An account's usage period: until which day a paying account may use STOA (#239).

Payment is taken offline. An administrator sets, for each paying account - a
student, or a parent paying for their children - the last day it may be used,
and every time they set or extend it a record is kept: who, when, by how much,
paid or gifted, and which offline payment.

Storage (the「#239 形状定完」shape, decisions 1 and 2):

- The end date lives on the paying account's own PROFILE as
  `usage_period_ends_at`, a Zurich calendar date (`YYYY-MM-DD`). The period
  ends at 23:59:59 that day, Zurich time.
- Each set or extension appends one record row to the account's partition,
  `USER#{account}` / `USAGE_PERIOD#{recorded_at}#{record_id}`, never changed
  afterwards. The profile change and the record are one transaction, held to
  the PROFILE `version` that was read and made behind the account's fence.
- A student's effective period is the latest of their own and that of every
  parent `current_relationship.parents_of` says is current. Nothing is copied
  onto the child, so a parent's extension reaches the child at once and a
  revoked relationship stops lending its period at once.

This step stores and administers periods only. Nothing here refuses a student
anything: reading the period into the entitlement and refusing a question at
expiry are #343 and #344.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any, Final
from uuid import uuid4
from zoneinfo import ZoneInfo

from boto3.dynamodb.conditions import Key

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, user_repo
from stoa.services import current_relationship
from stoa.services.account_errors import AccountErrorCode, AccountViolation

ZURICH: Final = ZoneInfo("Europe/Zurich")

PROFILE_FIELD: Final = "usage_period_ends_at"
RECORD_SK_PREFIX: Final = "USAGE_PERIOD#"
RECORD_ENTITY_TYPE: Final = "usage_period_record"
RECORD_SCHEMA_VERSION: Final = 1

# Only the accounts that pay hold a period: a student paying for themself, or a
# parent paying for their children. A teacher or an administrator never does.
PERIOD_ROLES: Final = frozenset({"student", "parent"})

# The ending-soon list also shows accounts that ran out this many days ago, so an
# administrator can still reach the families who did not renew.
RECENTLY_ENDED_DAYS: Final = 30

PAYMENT_REFERENCE_MAX_LENGTH: Final = 200


class PeriodState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    NONE = "none"


class PeriodUnit(StrEnum):
    MONTHS = "months"
    DAYS = "days"


class PeriodSource(StrEnum):
    PAID = "paid"
    GIFTED = "gifted"


class RecordKind(StrEnum):
    EXTEND = "extend"
    SET = "set"


class PaidBy(StrEnum):
    SELF = "self"
    PARENT = "parent"


# -- dates --------------------------------------------------------------------------


def zurich_today(now: datetime | None = None) -> date:
    """The calendar day it is in Zurich at `now` (default: this moment)."""
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        raise ValueError("a moment without a time zone cannot be placed in Zurich")
    return moment.astimezone(ZURICH).date()


def state_on(ends_on: date | None, today: date) -> PeriodState:
    """`none` without an end date; `active` through the end date itself; `expired` after."""
    if ends_on is None:
        return PeriodState.NONE
    return PeriodState.ACTIVE if today <= ends_on else PeriodState.EXPIRED


def add_months(start: date, months: int) -> date:
    """`months` calendar months after `start`, landing on the month's last day when shorter."""
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def extended_end(
    current: date | None, today: date, unit: PeriodUnit, amount: int
) -> date:
    """Where an extension ends: counted from today or the current end, whichever is later."""
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
        raise ValueError("an extension is at least one month or one day")
    start = max(today, current) if current is not None else today
    if unit is PeriodUnit.MONTHS:
        return add_months(start, amount)
    return start + timedelta(days=amount)


def stored_end(profile: Mapping[str, Any] | None) -> date | None:
    """The end date a profile stores, or `None`. A value that is not a date is a defect."""
    raw = (profile or {}).get(PROFILE_FIELD)
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise ValueError("malformed usage period end date")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("malformed usage period end date") from exc


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


# -- one account ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccountPeriod:
    """What an account's own profile says about its period."""

    user_id: str
    role: str
    ends_on: date | None
    state: PeriodState
    version: int
    subscription_tier: str | None


def profile_version(profile: Mapping[str, Any]) -> int:
    """The profile's `version` as the API shows it: 0 for a profile never versioned."""
    raw = profile.get("version")
    if raw is None:
        return 0
    if isinstance(raw, bool):
        raise ValueError("malformed profile version")
    return int(raw)


def account_period(
    profile: Mapping[str, Any], *, today: date
) -> AccountPeriod:
    ends_on = stored_end(profile)
    tier = profile.get("subscription_tier")
    return AccountPeriod(
        user_id=str(profile.get("user_id") or ""),
        role=str(profile.get("role") or ""),
        ends_on=ends_on,
        state=state_on(ends_on, today),
        version=profile_version(profile),
        subscription_tier=str(tier) if tier else None,
    )


def _period_profile(user_id: str, *, table: object | None) -> dict[str, Any]:
    """The account's profile, refused unless it is an account that can hold a period."""
    profile = user_repo.get_user(user_id, table=table)
    if not profile:
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND)
    if str(profile.get("role") or "") not in PERIOD_ROLES:
        raise AccountViolation(AccountErrorCode.USAGE_PERIOD_ROLE_INVALID)
    return dict(profile)


def read_account(
    user_id: str, *, now: datetime | None = None, table: object | None = None
) -> AccountPeriod:
    """One student's or parent's own period. Other roles are refused."""
    return account_period(_period_profile(user_id, table=table), today=zurich_today(now))


# -- a student's effective period ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EffectivePeriod:
    """The period a student may use: the latest of their own and their current parents'.

    `paid_by` and `parent_id` say where it comes from; both are `None` when no
    one holds a period for the student.
    """

    ends_on: date | None
    state: PeriodState
    paid_by: PaidBy | None
    parent_id: str | None = None


def latest_period(
    own: date | None,
    parents: Iterable[tuple[str, date | None]],
    *,
    today: date,
) -> EffectivePeriod:
    """The rule on its own: the latest end date wins; the student's own wins a tie.

    Parents are taken in the order given, so of two parents with the same end
    date the first named is the one reported.
    """
    best: date | None = own
    paid_by: PaidBy | None = PaidBy.SELF if own is not None else None
    parent_id: str | None = None
    for candidate_id, ends_on in parents:
        if ends_on is not None and (best is None or ends_on > best):
            best, paid_by, parent_id = ends_on, PaidBy.PARENT, candidate_id
    return EffectivePeriod(best, state_on(best, today), paid_by, parent_id)


def effective_for_student(
    student_id: str,
    *,
    profile: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    table: object | None = None,
) -> EffectivePeriod:
    """The student's effective period, judged now.

    Only a parent the relationship judge calls current lends a period; a pending,
    rejected or revoked link lends nothing. `profile` is the student's profile
    when the caller has already read it.
    """
    own_profile = profile if profile is not None else user_repo.get_user(student_id, table=table)
    parents = [
        (
            verdict.parent_id,
            stored_end(user_repo.get_user(verdict.parent_id, table=table)),
        )
        for verdict in current_relationship.parents_of(student_id, table=table)
    ]
    return latest_period(stored_end(own_profile), parents, today=zurich_today(now))


# -- setting and extending -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PeriodRecord:
    """One stored set or extension, as it was written."""

    record_id: str
    user_id: str
    recorded_at: str
    actor_id: str
    kind: RecordKind
    previous_ends_on: str | None
    new_ends_on: str
    unit: str | None = None
    amount: int | None = None
    source: str | None = None
    payment_reference: str | None = None
    note: str | None = None
    reason: str | None = None
    subscription_tier: str | None = None


@dataclass(frozen=True, slots=True)
class PeriodChange:
    """The account after a write, and the record the write kept."""

    period: AccountPeriod
    record: PeriodRecord


def _recorded_at(now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("a record's time carries its time zone")
    return now.astimezone(UTC).isoformat(timespec="microseconds")


def _record_item(record: PeriodRecord, role: str) -> dict[str, Any]:
    item: dict[str, Any] = {
        "PK": f"USER#{record.user_id}",
        "SK": f"{RECORD_SK_PREFIX}{record.recorded_at}#{record.record_id}",
        "entity_type": RECORD_ENTITY_TYPE,
        "schema_version": RECORD_SCHEMA_VERSION,
        "record_id": record.record_id,
        # `user_id` is what the account deletion scan finds a row's owner by.
        "user_id": record.user_id,
        "role": role,
        "recorded_at": record.recorded_at,
        "actor_id": record.actor_id,
        "kind": record.kind.value,
        "previous_ends_on": record.previous_ends_on,
        "new_ends_on": record.new_ends_on,
        "unit": record.unit,
        "amount": record.amount,
        "source": record.source,
        "payment_reference": record.payment_reference,
        "note": record.note,
        "reason": record.reason,
        "subscription_tier": record.subscription_tier,
    }
    # A transaction drops `None` members anyway; leaving them out keeps the row
    # the same whichever way it is written.
    return {name: value for name, value in item.items() if value is not None}


def _write(
    profile: Mapping[str, Any],
    *,
    expected_version: int,
    new_ends_on: date,
    make_record: Any,
    now: datetime,
    table: object | None,
) -> PeriodChange:
    user_id = str(profile["user_id"])
    stored_version = profile_version(profile)
    if expected_version != stored_version:
        raise AccountViolation(AccountErrorCode.USAGE_PERIOD_VERSION_CONFLICT)
    current = account_period(profile, today=zurich_today(now))
    recorded_at = _recorded_at(now)
    record: PeriodRecord = make_record(
        record_id=uuid4().hex,
        user_id=user_id,
        recorded_at=recorded_at,
        previous_ends_on=_iso(current.ends_on),
        new_ends_on=new_ends_on.isoformat(),
        subscription_tier=current.subscription_tier,
    )
    operations = [
        user_repo.profile_update_operation(
            user_id,
            update_expression="SET #ends = :ends, updated_at = :now",
            expression_attribute_names={"#ends": PROFILE_FIELD},
            expression_attribute_values={":ends": new_ends_on.isoformat(), ":now": recorded_at},
            expected_version=stored_version or None,
        ),
        {
            "Put": {
                "Item": _record_item(record, current.role),
                "ConditionExpression": "attribute_not_exists(PK)",
            }
        },
    ]
    try:
        db_table.fenced(user_id, operations, table=table)
    except account_deletion_repo.AccountDeletionConflict as exc:
        # The account is being deleted, or its fence is not active.
        raise AccountViolation(AccountErrorCode.ACCOUNT_STATE_INVALID) from exc
    except db_table.WriteRefused as exc:
        # The profile moved since it was read: somebody else wrote first.
        raise AccountViolation(AccountErrorCode.USAGE_PERIOD_VERSION_CONFLICT) from exc
    after = AccountPeriod(
        user_id=user_id,
        role=current.role,
        ends_on=new_ends_on,
        state=state_on(new_ends_on, zurich_today(now)),
        version=stored_version + 1,
        subscription_tier=current.subscription_tier,
    )
    return PeriodChange(after, record)


def extend(
    user_id: str,
    *,
    actor_id: str,
    unit: PeriodUnit,
    amount: int,
    source: PeriodSource,
    payment_reference: str | None,
    note: str | None,
    expected_version: int,
    now: datetime | None = None,
    table: object | None = None,
) -> PeriodChange:
    """Add `amount` months or days, from today or the current end, whichever is later.

    A paid extension names the offline payment it was for; nothing here checks
    the payment, the reference is written down as the administrator gave it.
    """
    reference = (payment_reference or "").strip() or None
    if source is PeriodSource.PAID and reference is None:
        raise ValueError("a paid extension names its payment")
    if reference is not None and len(reference) > PAYMENT_REFERENCE_MAX_LENGTH:
        raise ValueError("payment reference too long")
    moment = now or datetime.now(UTC)
    profile = _period_profile(user_id, table=table)
    new_ends_on = extended_end(stored_end(profile), zurich_today(moment), unit, amount)

    def make_record(**fields: Any) -> PeriodRecord:
        return PeriodRecord(
            **fields,
            actor_id=actor_id,
            kind=RecordKind.EXTEND,
            unit=unit.value,
            amount=amount,
            source=source.value,
            payment_reference=reference,
            note=(note or "").strip() or None,
        )

    return _write(
        profile,
        expected_version=expected_version,
        new_ends_on=new_ends_on,
        make_record=make_record,
        now=moment,
        table=table,
    )


def set_end(
    user_id: str,
    *,
    actor_id: str,
    ends_on: date,
    reason: str,
    expected_version: int,
    now: datetime | None = None,
    table: object | None = None,
) -> PeriodChange:
    """Put the end on `ends_on` directly - to correct a mistake or end a period early."""
    stated = (reason or "").strip()
    if not stated:
        raise ValueError("a changed end date states its reason")
    moment = now or datetime.now(UTC)
    profile = _period_profile(user_id, table=table)

    def make_record(**fields: Any) -> PeriodRecord:
        return PeriodRecord(**fields, actor_id=actor_id, kind=RecordKind.SET, reason=stated)

    return _write(
        profile,
        expected_version=expected_version,
        new_ends_on=ends_on,
        make_record=make_record,
        now=moment,
        table=table,
    )


# -- reading the records ---------------------------------------------------------------


def _record_from_item(item: Mapping[str, Any]) -> PeriodRecord:
    amount = item.get("amount")
    return PeriodRecord(
        record_id=str(item.get("record_id") or ""),
        user_id=str(item.get("user_id") or ""),
        recorded_at=str(item.get("recorded_at") or ""),
        actor_id=str(item.get("actor_id") or ""),
        kind=RecordKind(str(item.get("kind"))),
        previous_ends_on=item.get("previous_ends_on") or None,
        new_ends_on=str(item.get("new_ends_on") or ""),
        unit=item.get("unit") or None,
        amount=int(amount) if amount is not None else None,
        source=item.get("source") or None,
        payment_reference=item.get("payment_reference") or None,
        note=item.get("note") or None,
        reason=item.get("reason") or None,
        subscription_tier=item.get("subscription_tier") or None,
    )


def records_scope(user_id: str) -> str:
    return f"usage_period_records:{user_id}"


def list_records(
    user_id: str,
    *,
    limit: int,
    token: str | None = None,
    table: object | None = None,
) -> tuple[list[PeriodRecord], str | None]:
    """One page of the account's records, newest first, and the token for the next.

    A token made for another account's records, or not made here at all, is
    `page_token_invalid`.
    """
    partition = f"USER#{user_id}"

    def within(key: Mapping[str, Any]) -> bool:
        sort_key = key.get("SK")
        return (
            key.get("PK") == partition
            and isinstance(sort_key, str)
            and sort_key.startswith(RECORD_SK_PREFIX)
        )

    try:
        walk = db_table.pages(
            "query",
            token=token or None,
            scope=records_scope(user_id),
            within=within,
            table=table,
            KeyConditionExpression=Key("PK").eq(partition)
            & Key("SK").begins_with(RECORD_SK_PREFIX),
            ScanIndexForward=False,
            Limit=limit,
        )
    except db_table.PageTokenInvalid as exc:
        raise AccountViolation(AccountErrorCode.PAGE_TOKEN_INVALID) from exc
    page = next(iter(walk))
    return [_record_from_item(item) for item in page.items], page.next_token


# -- the ending-soon list --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EndingAccount:
    """One account in the ending-soon list. A parent's row names the children it covers."""

    user_id: str
    account_number: str
    name: str
    role: str
    ends_on: date
    state: PeriodState
    children: tuple[dict[str, str], ...] = ()


def _child_entry(student_id: str, *, table: object | None) -> dict[str, str]:
    child = user_repo.get_user(student_id, table=table) or {}
    return {
        "userId": student_id,
        "accountNumber": str(child.get("account_number") or ""),
        "name": str(child.get("name") or ""),
    }


def ending_soon(
    *,
    within_days: int,
    now: datetime | None = None,
    table: object | None = None,
) -> list[EndingAccount]:
    """Students and parents whose period ends within `within_days` or ended in the last 30.

    There are few accounts, so this scans the profiles rather than keep an index
    (shape decision 11). Soonest first; an ended period sorts before a running one.
    """
    if isinstance(within_days, bool) or not isinstance(within_days, int) or within_days < 0:
        raise ValueError("within_days is a number of days")
    today = zurich_today(now)
    earliest = (today - timedelta(days=RECENTLY_ENDED_DAYS)).isoformat()
    latest = (today + timedelta(days=within_days)).isoformat()
    profiles = db_table.rows(
        "scan",
        table=table,
        FilterExpression=(
            "#sk = :profile AND #role IN (:student, :parent) AND #ends BETWEEN :earliest AND :latest"
        ),
        ExpressionAttributeNames={"#sk": "SK", "#role": "role", "#ends": PROFILE_FIELD},
        ExpressionAttributeValues={
            ":profile": "PROFILE",
            ":student": "student",
            ":parent": "parent",
            ":earliest": earliest,
            ":latest": latest,
        },
    )
    found: list[EndingAccount] = []
    for profile in profiles:
        # The filter already said so; a double or a stray row is held to it again.
        ends_on = stored_end(profile)
        role = str(profile.get("role") or "")
        if ends_on is None or role not in PERIOD_ROLES:
            continue
        if not earliest <= ends_on.isoformat() <= latest:
            continue
        user_id = str(profile.get("user_id") or "")
        children: tuple[dict[str, str], ...] = ()
        if role == "parent":
            children = tuple(
                _child_entry(verdict.student_id, table=table)
                for verdict in current_relationship.children_of(user_id, table=table)
            )
        found.append(
            EndingAccount(
                user_id=user_id,
                account_number=str(profile.get("account_number") or ""),
                name=str(profile.get("name") or ""),
                role=role,
                ends_on=ends_on,
                state=state_on(ends_on, today),
                children=children,
            )
        )
    return sorted(found, key=lambda row: (row.ends_on, row.user_id))
