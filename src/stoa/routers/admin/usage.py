"""Admin usage ledger views."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from stoa.config import Settings
from stoa import config
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor
from stoa.services import usage_ledger_service


router = APIRouter()


class UsageSummaryResponse(BaseModel):
    studentId: str
    parentId: str | None = None
    quotaPeriod: str
    action: str
    consumed: int
    limit: int
    remaining: int
    effectivePlan: str | None = None
    entitlementSource: str | None = None
    billingState: str | None = None
    reconciliation: dict[str, Any] = Field(default_factory=dict)
    supportAction: str | None = None
    # A client translates `explanationCode` (+ `explanationParams`); `explanation`
    # is its English sentence (#114).
    explanationCode: str | None = None
    explanationParams: dict[str, Any] = Field(default_factory=dict)
    explanation: str | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    groups: list[dict[str, Any]] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)
    partial: bool = False
    stale: bool = False
    unreconciled: bool = False


class UsageEventListResponse(BaseModel):
    items: list[dict[str, Any]]
    count: int


class UsageReconciliationResponse(BaseModel):
    studentId: str
    action: str
    quotaPeriod: str
    counterKey: str | None = None
    counterCount: int
    ledgerCount: int
    eventCount: int
    status: str
    drift: int = 0
    stale: bool = False
    supportAction: str | None = None
    # A client translates `explanationCode` (+ `explanationParams`); `explanation`
    # is its English sentence (#114).
    explanationCode: str | None = None
    explanationParams: dict[str, Any] = Field(default_factory=dict)
    explanation: str | None = None
    repairMode: str
    repaired: bool
    partial: bool


@router.get("/usage/students/{student_id}", response_model=UsageSummaryResponse)
async def get_student_usage_summary(
    student_id: str,
    day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    settings: Settings = Depends(config.settings),
    actor: Actor = Depends(admin_operation),
):
    """Return a privacy-safe student quota usage summary for support."""
    return usage_ledger_service.build_student_usage_summary(
        student_id=student_id,
        settings=settings,
        day=day,
    )


@router.get("/usage/students/{student_id}/events", response_model=UsageEventListResponse)
async def list_student_usage_events(
    student_id: str,
    day: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    actor: Actor = Depends(admin_operation),
):
    """List redacted usage ledger events for support investigation."""
    items = usage_ledger_service.list_usage_events(
        student_id=student_id,
        day=day,
        action=action,
        limit=limit,
    )
    return UsageEventListResponse(items=items, count=len(items))


@router.get("/usage/reconciliation", response_model=UsageReconciliationResponse)
async def preview_usage_reconciliation(
    student_id: str = Query(..., min_length=1),
    day: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    action: str = Query(default=usage_ledger_service.QUESTION_SUBMISSION_ACTION),
    repair: bool = Query(default=False),
    actor: Actor = Depends(admin_operation),
):
    """Preview or explicitly repair daily counter versus ledger reconciliation."""
    return usage_ledger_service.reconcile_usage_action(
        student_id=student_id,
        day=day,
        action=action,
        repair=repair,
    )
