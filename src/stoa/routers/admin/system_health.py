"""Admin system health: every feature's traffic, errors, latency, alarms and probes (card 134)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from stoa.observability import features, health_reader
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor

router = APIRouter()

Window = Literal["1h", "24h", "7d"]


class SparkPoint(BaseModel):
    t: str
    requests: int | None
    p95Ms: int | None


class ProbeSummary(BaseModel):
    ok: bool
    lastRunAt: str | None
    latencyMs: int | None


class FeatureHealth(BaseModel):
    key: str
    status: Literal["ok", "warn", "bad", "unknown"]
    requests: int | None
    errorRate: float | None
    p95Ms: int | None
    p95LimitMs: int
    spark: list[SparkPoint]
    probe: ProbeSummary | None
    openAlarms: int


class Alarm(BaseModel):
    name: str
    feature: str | None
    state: str
    since: str | None
    reason: str | None


class Deploy(BaseModel):
    at: str | None
    release: str


class FrontendErrorTotal(BaseModel):
    total: int | None


class SystemHealthResponse(BaseModel):
    generatedAt: str
    window: Window
    features: list[FeatureHealth]
    alarms: list[Alarm]
    deploys: list[Deploy]
    frontendErrors: FrontendErrorTotal
    partial: bool = False


class SeriesPoint(BaseModel):
    t: str
    requests: int
    errors: int
    p50Ms: int | None
    p95Ms: int | None


class RouteStats(BaseModel):
    method: str
    route: str
    requests: int
    errorRate: float
    p50Ms: int | None
    p95Ms: int | None


class RecentError(BaseModel):
    at: str | None
    method: str
    route: str
    status: int | None
    count: int


class FrontendErrorGroup(BaseModel):
    messageHash: str
    message: str | None
    route: str | None
    release: str | None
    count: int
    lastAt: str | None


class ProbeStep(BaseModel):
    at: str | None
    ok: bool
    latencyMs: int
    step: str | None


class UsageCount(BaseModel):
    event: str
    count: int


class FeatureDetailResponse(BaseModel):
    generatedAt: str
    window: Window
    feature: FeatureHealth
    series: list[SeriesPoint]
    routes: list[RouteStats]
    recentErrors: list[RecentError]
    frontendErrors: list[FrontendErrorGroup]
    probes: list[ProbeStep]
    alarms: list[Alarm]
    usage: list[UsageCount]
    partial: bool = False


@router.get("/system/health", response_model=SystemHealthResponse)
async def get_system_health(
    window: Window = Query(default="24h"),
    actor: Actor = Depends(admin_operation),
):
    """Every watched feature's health over the window."""
    return health_reader.health(window)


@router.get("/system/features/{feature}", response_model=FeatureDetailResponse)
async def get_feature_health(
    feature: str,
    window: Window = Query(default="24h"),
    actor: Actor = Depends(admin_operation),
):
    """One feature's health in detail: series, routes, errors, probes, usage."""
    if feature not in features.HEALTH_FEATURE_KEYS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown feature")
    return health_reader.feature_detail(feature, window)
