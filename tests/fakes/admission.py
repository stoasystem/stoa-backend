"""A student's eligibility and week, as a question's admission finds them (#241).

A question reads the student's eligibility once, when it is first submitted
(`ask_question._admission.admit`). `seed_plan` is the one place the tests
decide what that read returns, and it counts the reads, so a test can hold
that a replay makes none. The student's usage period is active unless a test
says otherwise (`period_state`; #344 refuses any other). `seed_week_used` spends part of the student's week
on the allowance table the question is charged on, through the real ledger.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import pytest

from stoa.db.repositories import allowance_repo
from stoa.services import allowance_service, entitlement_service, usage_period

# Taken before any test points the allowance at a table of its own.
_RESERVE = allowance_service.reserve_token_allowance


class Eligibility:
    """What the eligibility read returns, and who it was read for."""

    def __init__(self, entitlement: dict[str, Any]) -> None:
        self.entitlement = entitlement
        self.reads: list[str] = []

    def __call__(self, student_id: str, **_kwargs: Any) -> dict[str, Any]:
        self.reads.append(student_id)
        return dict(self.entitlement)


def seed_plan(
    monkeypatch: pytest.MonkeyPatch,
    *,
    plan: str = "free_trial",
    daily_limit: int = 50,
    allowance_version: int = 1,
    period_state: str = "active",
) -> Eligibility:
    """Have every student's eligibility read as `plan` with `daily_limit` messages a day."""
    eligibility = Eligibility(
        {
            "effectivePlan": plan,
            "allowanceVersion": allowance_version,
            "limits": {"dailyChatMessageLimit": daily_limit},
            "usagePeriod": {"state": period_state},
            "newUsageAllowed": period_state == "active",
        }
    )
    monkeypatch.setattr(entitlement_service, "resolve_student_entitlement", eligibility)
    return eligibility


def seed_week_used(
    table: object,
    student_id: str,
    *,
    at: datetime,
    plan: str = "free_trial",
    input_tokens: int | None = None,
    output_tokens: int = 1,
) -> None:
    """Reserve `input_tokens` (the whole week's budget unless given) of the week `at` falls in."""
    budget = allowance_service.plan_allowance_budget(plan, allowance_version=1)
    reserved = _RESERVE(
        beneficiary_id=student_id,
        effect_id=f"seeded-{uuid.uuid4()}",
        plan_id=plan,
        allowance_version=1,
        input_tokens=budget.input_tokens if input_tokens is None else input_tokens,
        max_output_tokens=output_tokens,
        observed_at=at,
        table=table,
    )
    assert reserved.disposition is allowance_repo.ReservationDisposition.ADMITTED


def seed_period_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let every student ask a human teacher, as one whose usage period runs (#344).

    For tests about the request itself, whose students have no profile with a
    period on it. `tests/test_usage_period_enforcement.py` holds the rule with
    real periods on the table.
    """
    monkeypatch.setattr(usage_period, "student_may_ask", lambda *_a, **_k: True)
