"""Zurich-week token budgets, conditional admission, and safe projections."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import hashlib
import struct
from typing import Any
from zoneinfo import ZoneInfo

from stoa.db.repositories import allowance_repo
from stoa.models.allowance import (
    MAX_EXACT_COUNT,
    PlanAllowanceBudget,
    TeacherSupportScope,
    ZurichWeek,
)
from stoa.models.billing import BillingPlanId


ZURICH = ZoneInfo("Europe/Zurich")
_LOCKED_TOKEN_BUDGETS: dict[
    BillingPlanId, tuple[int, int, int, TeacherSupportScope]
] = {
    BillingPlanId.FREE_TRIAL: (50_000, 10_000, 0, TeacherSupportScope.NONE),
    BillingPlanId.STUDENT: (500_000, 100_000, 0, TeacherSupportScope.NONE),
    BillingPlanId.TEACHER_SUPPORTED: (
        1_000_000,
        200_000,
        2,
        TeacherSupportScope.PER_BENEFICIARY,
    ),
    BillingPlanId.FAMILY: (
        1_000_000,
        200_000,
        10,
        TeacherSupportScope.SHARED_FAMILY,
    ),
}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _exact_count(value: object, field: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= MAX_EXACT_COUNT
    ):
        raise ValueError(f"{field} is invalid")
    return value


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def _domain_digest(domain: bytes, *values: str) -> str:
    framed = bytearray(domain)
    for value in values:
        framed.extend(_frame(value))
    return hashlib.sha256(bytes(framed)).hexdigest()


def _effect_digest(beneficiary_id: str, effect_id: str) -> str:
    return _domain_digest(
        b"stoa.allowance.effect.v1",
        _required_text(beneficiary_id, "beneficiary_id"),
        _required_text(effect_id, "effect_id"),
    )


def _provider_digest(kind: str, value: str) -> str:
    return _domain_digest(
        b"stoa.allowance.provider-coordinate.v1",
        kind,
        _required_text(value, kind),
    )


def zurich_week(observed_at: datetime | None = None) -> ZurichWeek:
    """Resolve the containing Zurich calendar week from local Monday dates."""
    observed = _aware(
        observed_at or datetime.now(timezone.utc),
        "observed_at",
    )
    local = observed.astimezone(ZURICH)
    monday = local.date() - timedelta(days=local.weekday())
    next_monday = monday + timedelta(days=7)
    local_start = datetime.combine(monday, time.min, tzinfo=ZURICH)
    local_end = datetime.combine(next_monday, time.min, tzinfo=ZURICH)
    iso = monday.isocalendar()
    return ZurichWeek(
        isoYear=iso.year,
        isoWeek=iso.week,
        windowStart=local_start.astimezone(timezone.utc),
        windowEnd=local_end.astimezone(timezone.utc),
    )


def plan_allowance_budget(
    plan_id: BillingPlanId | str,
    *,
    allowance_version: int,
) -> PlanAllowanceBudget:
    """Return the exact locked D-19 budget for one canonical plan."""
    try:
        plan = (
            plan_id
            if isinstance(plan_id, BillingPlanId)
            else BillingPlanId(_required_text(plan_id, "plan_id"))
        )
    except ValueError as exc:
        raise ValueError("plan_id is not a canonical billing plan") from exc
    version = _exact_count(
        allowance_version, "allowance_version", positive=True
    )
    input_tokens, output_tokens, cases, scope = _LOCKED_TOKEN_BUDGETS[plan]
    return PlanAllowanceBudget(
        planId=plan,
        inputTokens=input_tokens,
        outputTokens=output_tokens,
        teacherSupportCases=cases,
        teacherSupportScope=scope,
        allowanceVersion=version,
    )


def reserve_token_allowance(
    *,
    beneficiary_id: str,
    effect_id: str,
    plan_id: BillingPlanId | str,
    allowance_version: int,
    input_tokens: int,
    max_output_tokens: int,
    observed_at: datetime | None = None,
    account_fence_generation: int | None = None,
    table: object | None = None,
) -> allowance_repo.ReservationResult:
    """Resolve the calendar/budget first, then conditionally reserve both dimensions."""
    observed = _aware(
        observed_at or datetime.now(timezone.utc),
        "observed_at",
    )
    week = zurich_week(observed)
    budget = plan_allowance_budget(
        plan_id, allowance_version=allowance_version
    )
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    effect = _effect_digest(beneficiary, effect_id)
    requested_input = _exact_count(input_tokens, "input_tokens")
    requested_output = _exact_count(max_output_tokens, "max_output_tokens")
    return allowance_repo.reserve_allowance(
        beneficiary_id=beneficiary,
        effect_id=effect,
        week=week,
        budget=budget,
        input_tokens=requested_input,
        output_tokens=requested_output,
        observed_at=observed,
        account_fence_generation=account_fence_generation,
        table=table,
    )


def record_provider_usage(
    *,
    beneficiary_id: str,
    effect_id: str,
    provider_request_id: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    observed_at: datetime | None = None,
    table: object | None = None,
) -> allowance_repo.ProviderUsageResult:
    """Record provider-reported counts without retaining raw provider coordinates."""
    observed = _aware(
        observed_at or datetime.now(timezone.utc),
        "observed_at",
    )
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    return allowance_repo.record_provider_usage(
        beneficiary_id=beneficiary,
        effect_id=_effect_digest(beneficiary, effect_id),
        provider_request_id_digest=_provider_digest(
            "provider_request_id", provider_request_id
        ),
        model_id_digest=_provider_digest("model_id", model_id),
        input_tokens=_exact_count(input_tokens, "input_tokens"),
        output_tokens=_exact_count(output_tokens, "output_tokens"),
        observed_at=observed,
        table=table,
    )


def finalize_token_allowance(
    *,
    beneficiary_id: str,
    effect_id: str,
    technical_validation_passed: bool,
    safety_check_passed: bool,
    durable_result_stored: bool,
    stable_replay_readable: bool,
    finalized_at: datetime | None = None,
    table: object | None = None,
) -> allowance_repo.FinalizationResult:
    """Finalize actual provider counts only after all D-22 delivery gates pass."""
    finalized = _aware(
        finalized_at or datetime.now(timezone.utc),
        "finalized_at",
    )
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    return allowance_repo.finalize_allowance(
        beneficiary_id=beneficiary,
        effect_id=_effect_digest(beneficiary, effect_id),
        technical_validation_passed=technical_validation_passed,
        safety_check_passed=safety_check_passed,
        durable_result_stored=durable_result_stored,
        stable_replay_readable=stable_replay_readable,
        finalized_at=finalized,
        table=table,
    )


def restore_user_allowance(
    *,
    beneficiary_id: str,
    effect_id: str,
    technical_validation_passed: bool,
    safety_check_passed: bool,
    durable_result_stored: bool,
    stable_replay_readable: bool,
    restored_at: datetime | None = None,
    table: object | None = None,
) -> allowance_repo.FinalizationResult:
    """Restore an undelivered user reservation without erasing provider cost."""
    restored = _aware(
        restored_at or datetime.now(timezone.utc),
        "restored_at",
    )
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    return allowance_repo.restore_allowance(
        beneficiary_id=beneficiary,
        effect_id=_effect_digest(beneficiary, effect_id),
        technical_validation_passed=technical_validation_passed,
        safety_check_passed=safety_check_passed,
        durable_result_stored=durable_result_stored,
        stable_replay_readable=stable_replay_readable,
        restored_at=restored,
        table=table,
    )


def _used_percent(used: int, budget: int) -> float:
    return round((used / budget) * 100, 4)


def get_allowance_projection(
    *,
    beneficiary_id: str,
    plan_id: BillingPlanId | str,
    allowance_version: int,
    observed_at: datetime | None = None,
    viewer_role: str,
    table: object | None = None,
) -> dict[str, Any]:
    """Project remaining allowance for parents or exact content-free evidence for admins."""
    role = _required_text(viewer_role, "viewer_role")
    if role not in {"parent", "admin"}:
        raise ValueError("allowance projection requires parent or admin viewer")
    observed = _aware(
        observed_at or datetime.now(timezone.utc),
        "observed_at",
    )
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    week = zurich_week(observed)
    budget = plan_allowance_budget(
        plan_id, allowance_version=allowance_version
    )
    try:
        counter = allowance_repo.get_allowance_counter(
            beneficiary_id=beneficiary,
            week=week,
            table=table,
        )
    except Exception:
        raise ValueError("allowance projection is temporarily unavailable") from None

    finalized_input = int((counter or {}).get("finalized_input_tokens", 0))
    finalized_output = int((counter or {}).get("finalized_output_tokens", 0))
    reserved_input = int((counter or {}).get("reserved_input_tokens", 0))
    reserved_output = int((counter or {}).get("reserved_output_tokens", 0))
    input_used = finalized_input + reserved_input
    output_used = finalized_output + reserved_output
    input_remaining = max(0, budget.input_tokens - input_used)
    output_remaining = max(0, budget.output_tokens - output_used)
    identity = f"{week.iso_year:04d}-W{week.iso_week:02d}"
    projection: dict[str, Any] = {
        "schemaVersion": "allowance_projection.v1",
        "beneficiaryId": beneficiary,
        "planId": str(budget.plan_id),
        "allowanceVersion": budget.allowance_version,
        "weekIdentity": identity,
        "window": {
            "start": week.window_start.isoformat(),
            "end": week.window_end.isoformat(),
        },
        "input": {
            "budgetTokens": budget.input_tokens,
            "remainingTokens": input_remaining,
            "usedPercent": _used_percent(input_used, budget.input_tokens),
        },
        "output": {
            "budgetTokens": budget.output_tokens,
            "remainingTokens": output_remaining,
            "usedPercent": _used_percent(output_used, budget.output_tokens),
        },
    }
    if role == "parent":
        return projection

    try:
        evidence = allowance_repo.list_provider_usage_evidence(
            beneficiary_id=beneficiary,
            week_identity=identity,
            table=table,
        )
    except Exception:
        raise ValueError("allowance projection is temporarily unavailable") from None
    projection.update(
        {
            "exactUsage": {
                "finalizedInputTokens": finalized_input,
                "finalizedOutputTokens": finalized_output,
                "reservedInputTokens": reserved_input,
                "reservedOutputTokens": reserved_output,
            },
            "providerCost": {
                "inputTokens": int(
                    (counter or {}).get("provider_cost_input_tokens", 0)
                ),
                "outputTokens": int(
                    (counter or {}).get("provider_cost_output_tokens", 0)
                ),
            },
            "providerEvidence": [
                item.model_dump(mode="json", by_alias=True) for item in evidence
            ],
        }
    )
    return projection


__all__ = [
    "finalize_token_allowance",
    "get_allowance_projection",
    "plan_allowance_budget",
    "record_provider_usage",
    "reserve_token_allowance",
    "restore_user_allowance",
    "zurich_week",
]
