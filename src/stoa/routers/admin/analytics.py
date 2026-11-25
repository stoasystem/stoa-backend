"""Admin usage analytics, read from the statistics table's daily rollups (card 134)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from stoa.observability import usage_stats
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor

router = APIRouter()


class Kpis(BaseModel):
    dau: int
    wau: int
    mau: int
    dauChange: float | None
    questionsPerDay: float
    escalationRate: float | None
    aiP50Ms: int | None
    teacherResponseP50Ms: int | None


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
    days: Literal[7, 30, 90] = Query(default=30),
    role: Literal["all", "student", "parent", "teacher"] = Query(default="all"),
    actor: Actor = Depends(admin_operation),
):
    """Actives, feature use, funnel and retention over the last `days` complete days."""
    return usage_stats.overview(days, role)
