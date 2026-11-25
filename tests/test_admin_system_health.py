"""Card 134-B2: the admin system-health and usage endpoints.

- Only an administrator with the platform operations grant reads them.
- The health status follows the card's rule.
- The feature detail waits at most 12 s for Logs Insights and answers with what
  it has.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from fakes.dynamodb import FakeTable
from stoa import aws
from stoa.aws import Kind
from stoa.db import table as db_table
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.observability import analytics_store, cost_reader, features, health_reader, usage_stats
from stoa.routers import admin
from stoa.security import admin_authorization
from stoa.security.identity import AccountStatus, Actor, CanonicalRole, CapabilityGrant

NEW_PATHS = ("/admin/system/health", "/admin/system/features/{feature}", "/admin/analytics/overview")
GET_URLS = ("/admin/system/health", "/admin/system/features/practice", "/admin/analytics/overview")


def _actor(role: CanonicalRole, *capabilities: str) -> Actor:
    return Actor(
        f"{role.value}-1",
        "https://identity.test",
        f"{role.value}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
        tuple(CapabilityGrant(capability, "global", 1) for capability in capabilities),
    )


ADMIN = _actor(CanonicalRole.ADMIN, "platform_operations_reader")


class FakeCloudWatch:
    def __init__(self, values: dict[str, float] | None = None, alarms: list[dict] | None = None):
        self.values = values or {}
        self.alarm_rows = alarms or []
        self.calls: list[dict[str, Any]] = []

    def get_metric_data(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        results = []
        for query in kwargs["MetricDataQueries"]:
            value = self.values.get(query["Id"])
            stamps = [kwargs["EndTime"] - timedelta(seconds=query["MetricStat"]["Period"])]
            results.append(
                {
                    "Id": query["Id"],
                    "Timestamps": stamps if value is not None else [],
                    "Values": [value] if value is not None else [],
                }
            )
        return {"MetricDataResults": results}

    def describe_alarms(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["AlarmNamePrefix"] == "stoa-"
        return {"MetricAlarms": self.alarm_rows, "CompositeAlarms": []}


class FakeLambda:
    def list_versions_by_function(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["FunctionName"] == "stoa-api"
        return {
            "Versions": [
                {"Version": "$LATEST", "LastModified": "2026-11-25T10:00:00.000+0000"},
                {"Version": "41", "LastModified": "2026-11-24T09:00:00.000+0000", "Description": ""},
                {"Version": "42", "LastModified": "2026-11-25T08:30:00.000+0000", "Description": "abc123"},
            ]
        }


class FakeLogs:
    def __init__(self, *, finish: bool = True):
        self.finish = finish
        self.started: list[dict[str, Any]] = []
        self.stopped: list[str] = []

    def start_query(self, **kwargs: Any) -> dict[str, str]:
        self.started.append(kwargs)
        return {"queryId": f"q{len(self.started)}"}

    def get_query_results(self, *, queryId: str) -> dict[str, Any]:  # noqa: N803
        status = "Complete" if self.finish else "Running"
        if queryId == "q1":
            rows = [
                [
                    {"field": "route", "value": "/practice/knowledge-map/stars"},
                    {"field": "method", "value": "GET"},
                    {"field": "requests", "value": "200"},
                    {"field": "errors", "value": "2"},
                    {"field": "p50", "value": "300.5"},
                    {"field": "p95", "value": "1900"},
                ],
                [
                    {"field": "route", "value": "/practice/curriculum/catalog"},
                    {"field": "method", "value": "GET"},
                    {"field": "requests", "value": "50"},
                    {"field": "errors", "value": "0"},
                    {"field": "p50", "value": "80"},
                    {"field": "p95", "value": "2500"},
                ],
            ]
        else:
            rows = [
                [
                    {"field": "route", "value": "/practice/knowledge-map/stars"},
                    {"field": "method", "value": "GET"},
                    {"field": "status", "value": "500"},
                    {"field": "count", "value": "2"},
                    {"field": "at", "value": "2026-11-25 10:01:02.000"},
                ]
            ]
        return {"status": status, "results": rows}

    def stop_query(self, *, queryId: str) -> dict[str, Any]:  # noqa: N803
        self.stopped.append(queryId)
        return {"success": True}


@pytest.fixture
def stats_table():
    table = FakeTable()
    analytics_store.install(table)
    yield table
    analytics_store.install(None)


@pytest.fixture
def classified(monkeypatch):
    """The three paths classified as `/admin/stats` is, until the inventory lands."""
    original = admin_authorization.classify_admin_route

    def classify(method: str, path: str):
        if path in NEW_PATHS:
            return original("GET", "/admin/stats")
        return original(method, path)

    monkeypatch.setattr(admin_authorization, "classify_admin_route", classify)


@pytest.fixture(autouse=True)
def _fresh_caches():
    health_reader.clear_cache()
    usage_stats.clear_cache()
    health_reader.install()
    cost_reader.install(FailingCostExplorer())
    yield
    health_reader.clear_cache()
    usage_stats.clear_cache()
    health_reader.install()
    cost_reader.install()


class FailingCostExplorer:
    def get_cost_and_usage(self, **_request: Any) -> dict[str, Any]:
        raise RuntimeError("AccessDeniedException")


def _app(actor: Actor | None) -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    if actor is not None:
        app.dependency_overrides[get_actor] = lambda: actor
    return TestClient(app)


def _install(cloudwatch: FakeCloudWatch | None = None, logs: FakeLogs | None = None) -> FakeCloudWatch:
    cloudwatch = cloudwatch or FakeCloudWatch()
    health_reader.install(cloudwatch=cloudwatch, logs=logs or FakeLogs())
    aws.install({Kind.LAMBDA: FakeLambda()})
    return cloudwatch


# ── who may read ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("url", GET_URLS)
def test_anonymous_is_refused(url, classified, stats_table) -> None:
    _install()
    assert _app(None).get(url).status_code == 401


@pytest.mark.parametrize("url", GET_URLS)
@pytest.mark.parametrize(
    "actor",
    [
        _actor(CanonicalRole.STUDENT),
        _actor(CanonicalRole.PARENT),
        _actor(CanonicalRole.TEACHER),
        _actor(CanonicalRole.ADMIN),
    ],
    ids=["student", "parent", "teacher", "admin-without-grant"],
)
def test_non_admin_is_refused(url, actor, classified, stats_table) -> None:
    _install()
    assert _app(actor).get(url).status_code == 403


@pytest.mark.parametrize("url", GET_URLS)
def test_admin_with_the_grant_reads(url, classified, stats_table) -> None:
    _install()
    response = _app(ADMIN).get(url)
    assert response.status_code == 200, response.text


def test_the_new_paths_are_classified_in_admin_authorization() -> None:
    """Red until the main session adds the three paths to `classify_admin_route`."""
    for path in NEW_PATHS:
        policy = admin_authorization.classify_admin_route("GET", path)
        assert policy.capability == "platform_operations_reader"


# ── status rule ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"open_alarms": 1}, "bad"),
        ({"probe_failed_twice": True}, "bad"),
        ({"open_alarms": 1, "p95_ms": 9999}, "bad"),
        ({"p95_ms": 1501}, "warn"),
        ({"p95_ms": 1500}, "ok"),
        ({"error_rate": 0.011}, "warn"),
        ({"error_rate": 0.01}, "ok"),
        ({"requests": 0, "probe_in_window": False}, "unknown"),
        ({"requests": None, "probe_in_window": False}, "unknown"),
        ({"requests": 0, "probe_in_window": True}, "ok"),
        ({}, "ok"),
    ],
)
def test_status_rule(kwargs, expected) -> None:
    base = {
        "open_alarms": 0,
        "probe_failed_twice": False,
        "requests": 100,
        "error_rate": 0.0,
        "p95_ms": 100,
        "p95_limit_ms": 1500,
        "probe_in_window": False,
    }
    assert health_reader.feature_status(**{**base, **kwargs}) == expected


def test_alarm_names_fall_to_their_feature() -> None:
    assert health_reader.alarm_feature("stoa-feature-ask_ai-error-rate") == "ask_ai"
    assert health_reader.alarm_feature("stoa-feature-teacher_help-latency") == "teacher_help"
    assert health_reader.alarm_feature("stoa-api-5xx") is None
    assert health_reader.alarm_feature("stoa-feature-nope-latency") is None


def test_p95_limits_cover_the_watched_features() -> None:
    assert set(features.FEATURE_P95_LIMIT_MS) == set(features.FEATURE_KEYS) - {"other"}
    assert features.HEALTH_FEATURE_KEYS[0] == "auth"
    assert len(features.HEALTH_FEATURE_KEYS) == 8


# ── health ───────────────────────────────────────────────────────────────────


def _probe(table: FakeTable, at: datetime, feature: str, step: str, ok: bool, latency: int) -> None:
    stamp = at.strftime("%Y-%m-%dT%H:%M:%SZ")
    table.seed(
        {
            "PK": f"PROBE#{at.date().isoformat()}",
            "SK": f"{stamp}#{feature}#{step}",
            "at": stamp,
            "feature": feature,
            "step": step,
            "ok": ok,
            "latency_ms": latency,
        }
    )


def test_health_answers_the_agreed_shape_and_statuses(classified, stats_table) -> None:
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    cloudwatch = _install(
        FakeCloudWatch(
            values={
                "req_practice": 3100,
                "err_practice": 6,
                "p95_practice": 1900,
                "sreq_practice": 120,
                "sp95_practice": 1800,
                "req_auth": 500,
                "err_auth": 0,
                "p95_auth": 200,
                "req_notifications": 1000,
                "err_notifications": 20,
                "p95_notifications": 100,
                "fe_practice": 5,
                "fe_other": 2,
            },
            alarms=[
                {
                    "AlarmName": "stoa-feature-voice-error-rate",
                    "StateValue": "ALARM",
                    "StateUpdatedTimestamp": now - timedelta(minutes=5),
                    "StateReason": "threshold crossed",
                },
                {"AlarmName": "stoa-api-5xx", "StateValue": "OK", "StateUpdatedTimestamp": now},
            ],
        )
    )
    for minutes in (5, 10):
        _probe(stats_table, now - timedelta(minutes=minutes), "ask_ai", "conversations", False, 300)
    _probe(stats_table, now - timedelta(minutes=5), "teacher_help", "availability", True, 820)

    response = _app(ADMIN).get("/admin/system/health?window=24h")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"generatedAt", "window", "features", "alarms", "deploys", "frontendErrors", "partial"}
    assert body["window"] == "24h" and body["partial"] is False
    assert [item["key"] for item in body["features"]] == list(features.HEALTH_FEATURE_KEYS)
    by_key = {item["key"]: item for item in body["features"]}
    practice = by_key["practice"]
    assert set(practice) == {
        "key", "status", "requests", "errorRate", "p95Ms", "p95LimitMs", "spark", "probe", "openAlarms"
    }
    assert practice["requests"] == 3100
    assert practice["errorRate"] == round(6 / 3100, 4)
    assert practice["p95Ms"] == 1900 and practice["p95LimitMs"] == 1500
    assert practice["status"] == "warn"
    assert len(practice["spark"]) == 12
    assert set(practice["spark"][0]) == {"t", "requests", "p95Ms"}
    assert practice["spark"][-1] == {
        "t": practice["spark"][-1]["t"], "requests": 120, "p95Ms": 1800
    }
    assert practice["probe"] is None
    assert by_key["auth"]["status"] == "ok"
    assert by_key["notifications"]["status"] == "warn"
    assert by_key["voice"]["status"] == "bad" and by_key["voice"]["openAlarms"] == 1
    assert by_key["ask_ai"]["status"] == "bad"
    assert by_key["ask_ai"]["probe"]["ok"] is False
    assert by_key["teacher_help"]["status"] == "ok"
    assert by_key["teacher_help"]["probe"]["latencyMs"] == 820
    assert by_key["parent_reports"]["status"] == "unknown"
    assert body["alarms"][0] == {
        "name": "stoa-feature-voice-error-rate",
        "feature": "voice",
        "state": "ALARM",
        "since": health_reader.iso(now - timedelta(minutes=5)),
        "reason": "threshold crossed",
    }
    assert body["alarms"][1]["feature"] is None
    assert body["deploys"][0] == {"at": "2026-11-25T08:30:00Z", "release": "abc123"}
    assert body["deploys"][1]["release"] == "v41"
    assert body["frontendErrors"] == {"total": 7}
    assert len(cloudwatch.calls) == 1


def test_health_is_cached_per_window(classified, stats_table) -> None:
    cloudwatch = _install()
    client = _app(ADMIN)
    client.get("/admin/system/health?window=1h")
    client.get("/admin/system/health?window=1h")
    assert len(cloudwatch.calls) == 1
    client.get("/admin/system/health?window=7d")
    assert len(cloudwatch.calls) == 2


def test_health_degrades_when_cloudwatch_fails(classified, stats_table) -> None:
    class Broken(FakeCloudWatch):
        def get_metric_data(self, **kwargs):
            raise RuntimeError("down")

    _install(Broken())
    body = _app(ADMIN).get("/admin/system/health").json()
    assert body["partial"] is True
    assert all(item["requests"] is None for item in body["features"])
    assert all(item["status"] == "unknown" for item in body["features"])


def test_health_refuses_an_unknown_window(classified, stats_table) -> None:
    _install()
    assert _app(ADMIN).get("/admin/system/health?window=2h").status_code == 422


# ── feature detail ───────────────────────────────────────────────────────────


def test_unknown_feature_is_404(classified, stats_table) -> None:
    _install()
    assert _app(ADMIN).get("/admin/system/features/nope").status_code == 404
    assert _app(ADMIN).get("/admin/system/features/other").status_code == 404


def test_feature_detail_shape(classified, stats_table) -> None:
    now = datetime.now(UTC)
    _install(FakeCloudWatch(values={"req": 10, "err": 1, "p50": 120, "p95": 900}))
    today = now.date().isoformat()
    for index, route in enumerate(["/map", "/chapter/abc123", "/ask"]):
        stats_table.seed(
            {
                "PK": f"DAY#{today}",
                "SK": f"{now.isoformat()}#{index}",
                "name": "frontend_error",
                "role": "student",
                "route": route,
                "props": {"route": route, "message_hash": "h1" if index < 2 else "h2", "message": "boom", "release": "r1"},
            }
        )
    _probe(stats_table, now - timedelta(minutes=3), "practice", "stars", True, 410)

    response = _app(ADMIN).get("/admin/system/features/practice?window=1h")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "generatedAt", "window", "feature", "series", "routes", "recentErrors",
        "frontendErrors", "probes", "alarms", "usage", "partial",
    }
    assert body["partial"] is False
    assert body["feature"]["key"] == "practice"
    assert body["series"][-1] == {"t": body["series"][-1]["t"], "requests": 10, "errors": 1, "p50Ms": 120, "p95Ms": 900}
    assert [route["route"] for route in body["routes"]] == [
        "/practice/curriculum/catalog", "/practice/knowledge-map/stars"
    ]
    assert body["routes"][1] == {
        "method": "GET", "route": "/practice/knowledge-map/stars",
        "requests": 200, "errorRate": 0.01, "p50Ms": 300, "p95Ms": 1900,
    }
    assert body["recentErrors"] == [
        {"at": "2026-11-25T10:01:02Z", "method": "GET", "route": "/practice/knowledge-map/stars", "status": 500, "count": 2}
    ]
    assert body["frontendErrors"] == [
        {
            "messageHash": "h1", "message": "boom", "route": body["frontendErrors"][0]["route"],
            "release": "r1", "count": 2, "lastAt": body["frontendErrors"][0]["lastAt"],
        }
    ]
    assert body["probes"][0]["step"] == "stars" and body["probes"][0]["latencyMs"] == 410
    assert body["alarms"] == []
    assert body["usage"] == []


def test_logs_insights_stops_waiting_at_twelve_seconds() -> None:
    logs = FakeLogs(finish=False)
    health_reader.install(logs=logs)
    clock = {"now": 0.0}
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    now = datetime.now(UTC)
    found, finished = health_reader.logs_insights(
        {"routes": "q", "errors": "q"}, now - timedelta(hours=1), now,
        sleep=sleep, clock=lambda: clock["now"],
    )
    assert finished is False
    assert clock["now"] <= 12.0
    assert sorted(logs.stopped) == ["q1", "q2"]
    assert found["routes"], "the rows returned so far are kept"
    assert all(started["logGroupName"] == "/aws/lambda/stoa-api" for started in logs.started)


def test_feature_detail_marks_a_slow_logs_answer_partial(classified, stats_table, monkeypatch) -> None:
    _install(logs=FakeLogs(finish=False))
    monkeypatch.setattr(health_reader, "LOGS_WAIT_SECONDS", 0.0)
    body = _app(ADMIN).get("/admin/system/features/practice").json()
    assert body["partial"] is True
    assert body["routes"]


def test_feature_detail_usage_reads_rollups(classified, stats_table) -> None:
    _install()
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    stats_table.seed(
        {"PK": f"ROLLUP#{yesterday}", "SK": "_meta"},
        {"PK": f"ROLLUP#{yesterday}", "SK": "exercise_answered#student", "event": "exercise_answered", "role": "student", "count": 9, "unique": 2, "pids": []},
        {"PK": f"ROLLUP#{yesterday}", "SK": "question_asked#student", "event": "question_asked", "role": "student", "count": 4, "unique": 1, "pids": []},
        {"PK": f"ROLLUP#{yesterday}", "SK": "page_viewed#student", "event": "page_viewed", "role": "student", "count": 6, "unique": 1, "pids": [], "by_feature": {"practice": 5, "ask_ai": 1}},
    )
    body = _app(ADMIN).get("/admin/system/features/practice").json()
    assert body["usage"] == [{"event": "exercise_answered", "count": 9}, {"event": "page_viewed", "count": 5}]


def test_routes_do_not_touch_the_main_table(classified, stats_table) -> None:
    main = FakeTable()
    db_table.install(main)
    _install()
    _app(ADMIN).get("/admin/system/health")
    _app(ADMIN).get("/admin/system/features/auth")
    assert main.calls["put_item"] == 0 and main.calls["scan"] == 0


@pytest.mark.parametrize("days", ["7", "30", "90"])
def test_the_console_query_string_reaches_the_overview(days, classified, stats_table) -> None:
    """Card 134: `days` arrives as text; as `Literal[7, 30, 90]` every request was a 422."""
    response = _app(ADMIN).get(f"/admin/analytics/overview?days={days}&role=student")
    assert response.status_code == 200, response.text
    assert response.json()["days"] == int(days)


def test_an_unknown_day_span_is_refused(classified, stats_table) -> None:
    assert _app(ADMIN).get("/admin/analytics/overview?days=8").status_code == 422


def test_a_failed_cost_read_still_answers_the_overview(classified, stats_table) -> None:
    response = _app(ADMIN).get("/admin/analytics/overview?days=7")
    assert response.status_code == 200, response.text
    kpis = response.json()["kpis"]
    assert kpis["costPerActiveUser"] is None
    assert {"wauChange", "mauChange", "questionsPerDayChange"} <= kpis.keys()
