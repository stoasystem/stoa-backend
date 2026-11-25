"""Admin usage analytics, read from the statistics table's daily rollups (card 134)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from stoa.observability import usage_stats
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor

router = APIRouter()

# A query string arrives as text, and pydantic does not coerce "7" into
# `Literal[7, 30, 90]`; the console's every request was a 422 (card 134).
ANALYTICS_DAYS = (7, 30, 90)


class CostShare(BaseModel):
    service: Literal["ai", "database", "other"]
    amountUsd: float | None


class CostPerActiveUser(BaseModel):
    amountUsd: float | None
    totalUsd: float
    activeUsers: int
    periodStart: str
    periodEnd: str
    breakdown: list[CostShare]


class Kpis(BaseModel):
    dau: int
    wau: int
    mau: int
    dauChange: float | None
    questionsPerDay: float
    escalationRate: float | None
    aiP50Ms: int | None
    teacherResponseP50Ms: int | None
    wauChange: float | None
    mauChange: float | None
    questionsPerDayChange: float | None
    costPerActiveUser: CostPerActiveUser | None


class ActivePoint(BaseModel):
    day: str
    active: int


class FeatureRank(BaseModel):
    event: str
    count: int
    uniqueUsers: int


class FunnelStep(BaseModel):
    step: Literal["invited", "activated", "first_question", "first_exercise", "week2_active"]
    count: int | None


class RetentionCohort(BaseModel):
    cohortWeek: str
    size: int
    weeks: list[float | None]


class AnalyticsOverviewResponse(BaseModel):
    generatedAt: str
    days: Literal[7, 30, 90]
    role: Literal["all", "student", "parent", "teacher"]
    complete: bool
    kpis: Kpis
    activeSeries: list[ActivePoint]
    featureRanking: list[FeatureRank]
    funnel: list[FunnelStep]
    retention: list[RetentionCohort]


@router.get("/analytics/overview", response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(
    days: int = Query(default=30),
    role: Literal["all", "student", "parent", "teacher"] = Query(default="all"),
    actor: Actor = Depends(admin_operation),
):
    """Actives, feature use, funnel and retention over the last `days` complete days."""
    if days not in ANALYTICS_DAYS:
        raise HTTPException(status_code=422, detail="days must be 7, 30 or 90")
    return usage_stats.overview(days, role)
