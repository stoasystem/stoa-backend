"""The usage period operations an agent may run: read, extend, set (#385).

Each mirrors an admin console route (#239) - `GET /admin/users/{id}/usage-period`,
`POST .../usage-period/extensions` and `PUT .../usage-period` - by calling the same
service, `services.usage_period`, with the same rules: only a student or a parent
holds a period, a paid extension is counted in months and names its payment, a
set states its reason, and a write is held to the version that was read. The one
difference is who: the period record and the console's account event name
`operator:agent_mcp`, and the operator call's own audit row - which carries the
fingerprint of the caller's SSO session - names the record it caused, so the two
join.

A change takes `dryRun`. A dry run only reads: it computes the end date the real
run would write with the service's own rule and judges every student it reaches
with the service's own effective-period rule, then answers with both, before and
after. It writes no business row; the one row it leaves is the audit row of every
operator call. A real run needs the `expectedVersion` the dry run showed, so a
period that moved in between is refused rather than changed twice.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, security_audit_repo, user_repo
from stoa.operator_calls import accounts, catalog
from stoa.operator_calls.catalog import (
    ExtendUsagePeriodArguments,
    GetUsagePeriodArguments,
    SetUsagePeriodArguments,
)
from stoa.operator_calls.outcome import OperatorCallRefused, Outcome
from stoa.services import current_relationship, usage_period
from stoa.services.account_errors import AccountErrorCode, AccountViolation


EXPECTED_VERSION_REQUIRED = "expected_version_required"


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _effective(period: usage_period.EffectivePeriod) -> dict[str, object]:
    return {
        "endsOn": _iso(period.ends_on),
        "state": period.state.value,
        "paidBy": period.paid_by.value if period.paid_by else None,
        "parentId": period.parent_id,
    }


def _record(record: usage_period.PeriodRecord) -> dict[str, object]:
    """A record as the console shows it."""
    return {
        "recordId": record.record_id,
        "recordedAt": record.recorded_at,
        "actorId": record.actor_id,
        "kind": record.kind.value,
        "unit": record.unit,
        "amount": record.amount,
        "previousEndsOn": record.previous_ends_on,
        "newEndsOn": record.new_ends_on,
        "source": record.source,
        "paymentReference": record.payment_reference,
        "note": record.note,
        "reason": record.reason,
        "subscriptionTier": record.subscription_tier,
    }


def _account(number: str, *, table: object) -> tuple[str, dict[str, Any]]:
    """The account id and profile behind a number, refused unless it holds a period."""
    account_id = accounts.account_id_by_number(number, table=table)
    profile = user_repo.get_user(account_id, table=table) if account_id else None
    if not profile or account_deletion_repo.is_deletion_tombstone(profile):
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND)
    if str(profile.get("role") or "") not in usage_period.PERIOD_ROLES:
        raise AccountViolation(AccountErrorCode.USAGE_PERIOD_ROLE_INVALID)
    return account_id, dict(profile)


def _with_end(profile: Mapping[str, Any], ends_on: date | None) -> dict[str, Any]:
    changed = dict(profile)
    if ends_on is None:
        changed.pop(usage_period.PROFILE_FIELD, None)
    else:
        changed[usage_period.PROFILE_FIELD] = ends_on.isoformat()
    return changed


def _reached(
    account_id: str, profile: Mapping[str, Any], *, table: object
) -> list[tuple[str, Mapping[str, Any]]]:
    """The students this account's period reaches: itself, or a parent's current children."""
    if profile.get("role") == "student":
        return [(account_id, profile)]
    reached: list[tuple[str, Mapping[str, Any]]] = []
    for verdict in current_relationship.children_of(account_id, table=table):
        child = user_repo.get_user(verdict.student_id, table=table)
        if child is not None and not account_deletion_repo.is_deletion_tombstone(child):
            reached.append((verdict.student_id, child))
    return reached


def _students(
    account_id: str,
    profile: Mapping[str, Any],
    *,
    new_end: date | None = None,
    changing: bool = False,
    table: object,
) -> list[dict[str, object]]:
    """Each student reached, with its effective period now and, for a change, after it.

    The after side is the service's own rule run on the account's profile as it
    would stand with the new end, so a dry run and the real run judge alike.
    """
    after_profile = _with_end(profile, new_end) if changing else None
    students: list[dict[str, object]] = []
    for student_id, student in _reached(account_id, profile, table=table):
        own = student if student_id != account_id else profile
        entry: dict[str, object] = {
            "userId": student_id,
            "accountNumber": str(student.get("account_number") or "") or None,
            "effective": _effective(
                usage_period.effective_for_student(
                    student_id,
                    profile=own,
                    parent_profiles={account_id: profile} if student_id != account_id else None,
                    table=table,
                )
            ),
        }
        if after_profile is not None:
            after = _effective(
                usage_period.effective_for_student(
                    student_id,
                    profile=after_profile if student_id == account_id else student,
                    parent_profiles=(
                        {account_id: after_profile} if student_id != account_id else None
                    ),
                    table=table,
                )
            )
            entry = {
                "userId": entry["userId"],
                "accountNumber": entry["accountNumber"],
                "before": entry["effective"],
                "after": after,
                "changes": after != entry["effective"],
            }
        students.append(entry)
    return students


# -- get --------------------------------------------------------------------------------


def get_usage_period(arguments: GetUsagePeriodArguments) -> Outcome:
    table = db_table.table()
    number = arguments.accountNumber.strip().upper()
    account_id, profile = _account(number, table=table)
    period = usage_period.account_period(profile, today=usage_period.zurich_today(None))
    records, next_token = usage_period.list_records(
        account_id, limit=arguments.recordLimit, token=arguments.cursor, table=table
    )
    return Outcome(
        {
            "accountNumber": number,
            "userId": account_id,
            "role": period.role,
            "endsOn": _iso(period.ends_on),
            "state": period.state.value,
            "version": period.version,
            "students": _students(account_id, profile, table=table),
            "records": [_record(record) for record in records],
            "nextCursor": next_token,
        },
        "account",
        account_id,
        f"returned_records:{len(records)}",
    )


# -- extend and set ---------------------------------------------------------------------


def _account_event(
    *, target_id: str, event_type: str, action: str, reason_code: str, evidence: str
) -> None:
    """The console's one row per write against an account, named for the operator."""
    security_audit_repo.append_event(
        target_id,
        {
            "event_id": f"event_{uuid4().hex}",
            "event_type": event_type,
            "actor_id": catalog.OPERATOR_ACTOR_ID,
            "actor_role": "operator",
            "target_id": target_id,
            "target_type": "account",
            "action": action,
            "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "reason_code": reason_code[:200],
            "evidence_reference": evidence[:400],
        },
    )


def _change(
    arguments: ExtendUsagePeriodArguments | SetUsagePeriodArguments,
    *,
    verb: str,
    new_end_of: Callable[[dict[str, Any], date], date],
    write: Callable[[str, int], usage_period.PeriodChange],
    event_type: str,
    reason_code: str,
) -> Outcome:
    """What extend and set share: check, rehearse or write, and answer before and after."""
    dry = arguments.dryRun
    table = db_table.table()
    number = arguments.accountNumber.strip().upper()
    account_id, profile = _account(number, table=table)

    def refuse(code: str, why: str) -> OperatorCallRefused:
        return OperatorCallRefused(
            code,
            f"{'Would be refused' if dry else 'Refused'}: account {number}. {why} "
            f"Nothing {'would be' if dry else 'was'} changed.",
            target_type="account",
            target_id=account_id,
        )

    today = usage_period.zurich_today(None)
    before = usage_period.account_period(profile, today=today)
    if arguments.expectedVersion is None and not dry:
        raise refuse(
            EXPECTED_VERSION_REQUIRED,
            "A real run passes the version the dry run showed as expectedVersion.",
        )
    if arguments.expectedVersion is not None and arguments.expectedVersion != before.version:
        raise refuse(
            AccountErrorCode.USAGE_PERIOD_VERSION_CONFLICT.value,
            f"The period is at version {before.version}, not {arguments.expectedVersion}: "
            "it changed since it was read. Run the dry run again.",
        )
    try:
        account_deletion_repo.require_active_account_fence(account_id, table=table)
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise refuse(
            AccountErrorCode.ACCOUNT_STATE_INVALID.value,
            "The account is being deleted or cannot be written.",
        ) from exc

    new_end = new_end_of(profile, today)
    students = _students(account_id, profile, new_end=new_end, changing=True, table=table)
    reached = [str(item["accountNumber"] or item["userId"]) for item in students if item["changes"]]
    shift = f"{_iso(before.ends_on) or 'none'}->{new_end.isoformat()}"
    before_view = {
        "endsOn": _iso(before.ends_on),
        "state": before.state.value,
        "version": before.version,
    }

    if dry:
        return Outcome(
            {
                "dryRun": True,
                "summary": (
                    f"Would {verb} the usage period of {before.role} account {number} "
                    f"from {_iso(before.ends_on) or 'none'} to {new_end.isoformat()}. "
                    + (
                        f"Students whose effective period changes: {', '.join(reached)}. "
                        if reached
                        else "No student's effective period changes. "
                    )
                    + f"Pass expectedVersion={before.version} to do it. Nothing was changed."
                ),
                "accountNumber": number,
                "userId": account_id,
                "role": before.role,
                "before": before_view,
                "after": {
                    "endsOn": new_end.isoformat(),
                    "state": usage_period.state_on(new_end, today).value,
                },
                "students": students,
            },
            "account",
            account_id,
            f"would_{verb}:usage-period:{shift}",
        )

    change = write(account_id, before.version)
    record = change.record
    evidence = (
        f"usage-period:{record.previous_ends_on or 'none'}->{record.new_ends_on};"
        f"record:{record.record_id}"
    )
    _account_event(
        target_id=account_id,
        event_type=event_type,
        action=f"{verb}_usage_period",
        reason_code=reason_code,
        evidence=evidence,
    )
    return Outcome(
        {
            "dryRun": False,
            "summary": (
                f"Changed the usage period of {before.role} account {number} from "
                f"{record.previous_ends_on or 'none'} to {record.new_ends_on}. "
                + (
                    f"Students whose effective period changed: {', '.join(reached)}."
                    if reached
                    else "No student's effective period changed."
                )
            ),
            "accountNumber": number,
            "userId": account_id,
            "role": before.role,
            "before": before_view,
            "after": {
                "endsOn": _iso(change.period.ends_on),
                "state": change.period.state.value,
                "version": change.period.version,
            },
            "students": students,
            "record": _record(record),
        },
        "account",
        account_id,
        evidence,
    )


def _invalid(why: str) -> OperatorCallRefused:
    return OperatorCallRefused("invalid_arguments", why)


def extend_usage_period(arguments: ExtendUsagePeriodArguments) -> Outcome:
    unit = usage_period.PeriodUnit(arguments.unit)
    source = usage_period.PeriodSource(arguments.source)
    reference = (arguments.paymentReference or "").strip() or None
    # The console's rule (`UsagePeriodExtensionRequest`): paid periods are sold by
    # the month and name their offline payment; a gift may be days or months.
    if source is usage_period.PeriodSource.PAID:
        if unit is not usage_period.PeriodUnit.MONTHS:
            raise _invalid("unit: a paid extension is counted in months.")
        if reference is None:
            raise _invalid("paymentReference: a paid extension names its offline payment.")

    def write(account_id: str, version: int) -> usage_period.PeriodChange:
        return usage_period.extend(
            account_id,
            actor_id=catalog.OPERATOR_ACTOR_ID,
            unit=unit,
            amount=arguments.amount,
            source=source,
            payment_reference=reference,
            note=arguments.note,
            expected_version=version,
            table=db_table.table(),
        )

    return _change(
        arguments,
        verb="extend",
        new_end_of=lambda profile, today: usage_period.extended_end(
            usage_period.stored_end(profile), today, unit, arguments.amount
        ),
        write=write,
        event_type="usage_period_extended",
        reason_code=f"{source.value}:{arguments.amount}:{unit.value}",
    )


def set_usage_period(arguments: SetUsagePeriodArguments) -> Outcome:
    reason = arguments.reason.strip()
    if not reason:
        raise _invalid("reason: a changed end date states its reason.")

    def write(account_id: str, version: int) -> usage_period.PeriodChange:
        return usage_period.set_end(
            account_id,
            actor_id=catalog.OPERATOR_ACTOR_ID,
            ends_on=arguments.endsOn,
            reason=reason,
            expected_version=version,
            table=db_table.table(),
        )

    return _change(
        arguments,
        verb="set",
        new_end_of=lambda _profile, _today: arguments.endsOn,
        write=write,
        event_type="usage_period_set",
        reason_code=reason,
    )
