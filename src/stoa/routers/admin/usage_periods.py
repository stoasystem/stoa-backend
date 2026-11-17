"""Admin usage periods: read, extend and set one account's period, list those ending."""

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from stoa.db import table as db_table
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor
from stoa.services import usage_period
from stoa.routers.admin.users import _record_account_admin_event


router = APIRouter()


# ---------------------------------------------------------------------------
# Usage periods (#239): set, extend and read an account's paid-up period
# ---------------------------------------------------------------------------


class UsagePeriodExtensionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit: usage_period.PeriodUnit
    amount: int = Field(ge=1, le=366)
    source: usage_period.PeriodSource
    paymentReference: str | None = Field(
        default=None, max_length=usage_period.PAYMENT_REFERENCE_MAX_LENGTH
    )
    note: str | None = Field(default=None, max_length=1000)
    expectedVersion: int = Field(ge=0)

    @model_validator(mode="after")
    def _paid_names_its_payment(self) -> "UsagePeriodExtensionRequest":
        # Paid periods are sold by the month; a gift may be days or months.
        if self.source is usage_period.PeriodSource.PAID:
            if self.unit is not usage_period.PeriodUnit.MONTHS:
                raise ValueError("a paid extension is counted in months")
            if not (self.paymentReference or "").strip():
                raise ValueError("a paid extension names its offline payment")
        return self


class UsagePeriodSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endsOn: date
    reason: str = Field(min_length=1, max_length=1000)
    expectedVersion: int = Field(ge=0)

    @model_validator(mode="after")
    def _reason_is_not_blank(self) -> "UsagePeriodSetRequest":
        if not self.reason.strip():
            raise ValueError("a changed end date states its reason")
        return self


def _usage_period_record(record: usage_period.PeriodRecord) -> dict[str, object]:
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


def _usage_period_account(period: usage_period.AccountPeriod) -> dict[str, object]:
    return {
        "userId": period.user_id,
        "role": period.role,
        "endsOn": period.ends_on.isoformat() if period.ends_on else None,
        "state": period.state.value,
        "version": period.version,
    }


def _usage_period_effective(
    effective: usage_period.EffectivePeriod,
) -> dict[str, object]:
    return {
        "endsOn": effective.ends_on.isoformat() if effective.ends_on else None,
        "state": effective.state.value,
        "paidBy": effective.paid_by.value if effective.paid_by else None,
        "parentId": effective.parent_id,
    }


def _usage_period_change(
    actor: Actor,
    change: usage_period.PeriodChange,
    *,
    event_type: str,
    action: str,
    reason_code: str,
) -> dict[str, object]:
    record = change.record
    _record_account_admin_event(
        actor=actor,
        target_id=record.user_id,
        event_type=event_type,
        action=action,
        reason_code=reason_code,
        evidence_reference=(
            f"usage-period:{record.previous_ends_on or 'none'}->{record.new_ends_on};"
            f"record:{record.record_id}"
        ),
    )
    return {**_usage_period_account(change.period), "record": _usage_period_record(record)}


@router.get("/users/{user_id}/usage-period")
def read_usage_period(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    pageToken: Optional[str] = Query(default=None, max_length=2048),
    actor: Actor = Depends(admin_operation),
) -> dict[str, Any]:
    """The account's own end date, a student's effective period, and the records.

    Records are newest first, one page at a time; `nextPageToken` continues this
    account's records and no other listing.
    """
    del actor
    table = db_table.table()
    period = usage_period.read_account(user_id, table=table)
    effective = (
        _usage_period_effective(usage_period.effective_for_student(user_id, table=table))
        if period.role == "student"
        else None
    )
    records, next_token = usage_period.list_records(
        user_id, limit=limit, token=pageToken, table=table
    )
    return {
        **_usage_period_account(period),
        "effective": effective,
        "records": [_usage_period_record(record) for record in records],
        "nextPageToken": next_token,
    }


@router.post("/users/{user_id}/usage-period/extensions")
def extend_usage_period(
    user_id: str,
    body: UsagePeriodExtensionRequest,
    actor: Actor = Depends(admin_operation),
) -> dict[str, Any]:
    """Extend by months or days, counted from today or the current end, whichever is later.

    The write carries the version the console read: two administrators extending
    the same account at once cannot both add their months (`usage_period_version_conflict`).
    """
    change = usage_period.extend(
        user_id,
        actor_id=actor.user_id,
        unit=body.unit,
        amount=body.amount,
        source=body.source,
        payment_reference=body.paymentReference,
        note=body.note,
        expected_version=body.expectedVersion,
        table=db_table.table(),
    )
    return _usage_period_change(
        actor,
        change,
        event_type="usage_period_extended",
        action="extend_usage_period",
        reason_code=f"{body.source.value}:{body.amount}:{body.unit.value}",
    )


@router.put("/users/{user_id}/usage-period")
def set_usage_period(
    user_id: str,
    body: UsagePeriodSetRequest,
    actor: Actor = Depends(admin_operation),
) -> dict[str, Any]:
    """Put the end date on a given day: to correct a mistake or end a period early."""
    change = usage_period.set_end(
        user_id,
        actor_id=actor.user_id,
        ends_on=body.endsOn,
        reason=body.reason,
        expected_version=body.expectedVersion,
        table=db_table.table(),
    )
    return _usage_period_change(
        actor,
        change,
        event_type="usage_period_set",
        action="set_usage_period",
        reason_code=body.reason,
    )


@router.get("/usage-periods")
def list_ending_usage_periods(
    endingWithinDays: int = Query(default=14, ge=0, le=366),
    actor: Actor = Depends(admin_operation),
) -> dict[str, Any]:
    """Students and parents whose period ends within the window or ended in the last 30 days.

    A parent's row names the children it currently covers, so the administrator
    knows whom a lapse reaches.
    """
    del actor
    rows = usage_period.ending_soon(within_days=endingWithinDays, table=db_table.table())
    items = [
        {
            "userId": row.user_id,
            "accountNumber": row.account_number,
            "name": row.name,
            "role": row.role,
            "endsOn": row.ends_on.isoformat(),
            "state": row.state.value,
            "children": list(row.children),
        }
        for row in rows
    ]
    return {"items": items, "count": len(items), "endingWithinDays": endingWithinDays}
