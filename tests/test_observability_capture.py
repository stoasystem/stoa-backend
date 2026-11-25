"""Card 134-B1: what the system-health and usage pages are counted from.

- Every route the API answers belongs to a feature, unless it is listed as
  `other` on purpose.
- Each request ends with one EMF line: the route's template, no ids.
- Usage events go to the statistics table only, checked against the catalog,
  and name a person only by pseudonym.
- Frontend error reports are cut, hashed and counted.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from stoa import config
from stoa.db import table as db_table
from stoa.observability import (
    analytics_store,
    event_catalog,
    features,
    request_metrics,
    telemetry,
)
from stoa.routers import analytics, monitoring
from stoa.security.identity import AccountStatus, Actor, CanonicalRole

REAL_USER_ID = "user-real-7f3a9c"
PSEUDONYM_KEY = "test-pseudonym-key"


class MainTable:
    """The main table: rate-limit counters only; any put is a leak."""

    def __init__(self) -> None:
        self.counters: dict[tuple[str, str], int] = {}
        self.puts: list[dict[str, Any]] = []

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        key = (kwargs["Key"]["PK"], kwargs["Key"]["SK"])
        self.counters[key] = self.counters.get(key, 0) + 1
        return {"Attributes": {"count": Decimal(self.counters[key])}}

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        self.puts.append(kwargs["Item"])
        return {}


class _ConditionalCheckFailed(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class StatsTable:
    """Keeps rows by key; honours the conditional put and UPDATED_OLD."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls = 0

    def put_item(self, *, Item: dict[str, Any], ConditionExpression: str | None = None) -> dict:
        self.calls += 1
        key = (Item["PK"], Item["SK"])
        if ConditionExpression == "attribute_not_exists(PK)" and key in self.rows:
            raise _ConditionalCheckFailed()
        self.rows[key] = dict(Item)
        return {}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        key = (kwargs["Key"]["PK"], kwargs["Key"]["SK"])
        old = dict(self.rows.get(key, {}))
        values = kwargs["ExpressionAttributeValues"]
        row = self.rows.setdefault(key, {"PK": key[0], "SK": key[1]})
        row.setdefault("first_event_at", values[":now"])
        row.update(
            last_event_at=values[":now"], role=values[":role"], pid=values[":pid"], ttl=values[":ttl"]
        )
        return {"Attributes": old} if old else {}

    def with_prefix(self, prefix: str) -> list[dict[str, Any]]:
        return [row for (pk, _), row in self.rows.items() if pk.startswith(prefix)]


@pytest.fixture
def main_table() -> MainTable:
    table = MainTable()
    db_table.install(table)
    return table


@pytest.fixture
def stats() -> Any:
    table = StatsTable()
    analytics_store.install(table)
    yield table
    analytics_store.install(None)


@pytest.fixture(autouse=True)
def _no_stats_table_left_behind():
    yield
    analytics_store.install(None)
    analytics_store._real_table.cache_clear()


def _settings(**overrides: Any) -> None:
    config.install(config.settings().model_copy(update=overrides))


def _student() -> Actor:
    return Actor(
        user_id=REAL_USER_ID,
        issuer="https://issuer.example",
        subject="subject-1",
        role=CanonicalRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        cognito_group="student",
    )


def _app() -> TestClient:
    app = FastAPI()
    app.include_router(analytics.router, prefix="/analytics")
    app.include_router(monitoring.router, prefix="/monitoring")
    return TestClient(app)


def _event(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "user_login",
        "payload": {"role": "student"},
        "path": "/login",
        "sessionId": "5f1d1c1e-0b2a-4a1f-8f6e-2b0c9d7e4a31",
        "createdAt": "2026-11-25T12:00:00.000Z",
    }
    body.update(overrides)
    return body


def _emf_lines(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.startswith('{"_aws"')]


# -- features ------------------------------------------------------------------------


def test_every_registered_route_maps_to_a_feature_unless_listed_as_other():
    from stoa.main import app

    unmapped = sorted(
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if features.feature_for_route(method, route.path) == features.OTHER
        and (method, route.path) not in features.OTHER_ROUTES
    )
    assert unmapped == []
    registered = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    assert features.OTHER_ROUTES <= registered


def test_feature_keys_are_the_agreed_ones_in_order():
    assert [feature.key for feature in features.FEATURES] == [
        "auth",
        "practice",
        "ask_ai",
        "teacher_help",
        "voice",
        "notifications",
        "parent_reports",
        "admin",
        "other",
    ]


@pytest.mark.parametrize(
    ("method", "route", "feature"),
    [
        ("POST", "/students/me/voice-questions/transcriptions", "voice"),
        ("POST", "/conversations/{conv_id}/messages/stream", "ask_ai"),
        ("POST", "/conversations/{conv_id}/classroom", "teacher_help"),
        ("POST", "/teacher-help/request", "teacher_help"),
        ("POST", "/practice/knowledge-map/stars/{unit_id}/quiz/{quiz_id}/answer", "practice"),
        ("POST", "/teacher-applications", "auth"),
        ("GET", "/teacher-applications", "admin"),
        ("GET", "/parents/me/children/{child_id}/report", "parent_reports"),
        ("GET", "/notifications", "notifications"),
        ("POST", "/auth/login", "auth"),
    ],
)
def test_route_feature_samples(method, route, feature):
    assert features.feature_for_route(method, route) == feature


@pytest.mark.parametrize(
    ("path", "template", "feature"),
    [
        ("/ask/3f2a9c1e-77aa-4b1f-9d0e-12ab34cd56ef?x=1", "/ask/:id", "ask_ai"),
        ("/parent/children/child-123/report", "/parent/children/:id/report", "parent_reports"),
        ("/", "/", "practice"),
        ("/map/math", "/map/math", "practice"),
        ("/admin/system", "/admin/system", "admin"),
        ("/nowhere", "/nowhere", "other"),
    ],
)
def test_frontend_routes_lose_their_ids(path, template, feature):
    assert features.frontend_route_template(path) == template
    assert features.feature_for_frontend_route(path) == feature


# -- EMF request metrics ---------------------------------------------------------------


def _metrics_app() -> TestClient:
    app = FastAPI()
    app.add_middleware(request_metrics.RequestMetricsMiddleware)

    @app.get("/practice/lessons/{lesson_id}")
    def lesson(lesson_id: str):
        return {"ok": True}

    @app.get("/admin/boom")
    def boom():
        raise HTTPException(status_code=503)

    return TestClient(app)


def test_one_emf_line_per_request_with_the_template_and_no_ids(capsys):
    _settings(stoa_release_id="rel-42")

    response = _metrics_app().get("/practice/lessons/lesson-secret-9?token=abc")

    assert response.status_code == 200
    out = capsys.readouterr().out
    lines = _emf_lines(out)
    assert len(lines) == 1
    line = lines[0]
    assert line["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "Stoa/Features"
    assert line["_aws"]["CloudWatchMetrics"][0]["Dimensions"] == [["Feature"]]
    assert {m["Name"]: m["Unit"] for m in line["_aws"]["CloudWatchMetrics"][0]["Metrics"]} == {
        "Requests": "Count",
        "Errors5xx": "Count",
        "Latency": "Milliseconds",
    }
    assert line["Feature"] == "practice"
    assert line["route"] == "/practice/lessons/{lesson_id}"
    assert line["method"] == "GET"
    assert line["status"] == 200
    assert line["release"] == "rel-42"
    assert line["Requests"] == 1 and line["Errors5xx"] == 0
    assert "lesson-secret-9" not in out and "token" not in out


def test_a_5xx_counts_as_an_error(capsys):
    _metrics_app().get("/admin/boom")

    line = _emf_lines(capsys.readouterr().out)[0]
    assert line["Feature"] == "admin" and line["status"] == 503 and line["Errors5xx"] == 1


def test_an_unmatched_path_is_other_and_not_echoed(capsys):
    _metrics_app().get("/students/someone-42/secret")

    out = capsys.readouterr().out
    line = _emf_lines(out)[0]
    assert line["route"] == "unmatched" and line["Feature"] == "other"
    assert "someone-42" not in out


def test_switched_off_writes_nothing(capsys):
    _settings(request_metrics=False)

    _metrics_app().get("/practice/lessons/x")

    assert _emf_lines(capsys.readouterr().out) == []


def test_a_failing_metrics_write_leaves_the_response_alone(monkeypatch):
    def broken(_line: str) -> None:
        raise OSError("stdout closed")

    monkeypatch.setattr(request_metrics, "write_line", broken)

    assert _metrics_app().get("/practice/lessons/x").status_code == 200


# -- the statistics table --------------------------------------------------------------


def test_without_a_statistics_table_events_are_dropped_and_never_reach_the_main_table(
    main_table: MainTable, caplog
):
    _settings(analytics_table_name="")
    caplog.set_level(logging.INFO)

    response = _app().post("/analytics/events", json=_event())
    telemetry.record("question_asked", actor_user_id=REAL_USER_ID, role="student", subject="math")

    assert response.status_code == 202
    assert main_table.puts == []
    assert all(key[0].startswith("SOURCEWINDOW#") for key in main_table.counters)
    drops = [r for r in caplog.messages if "analytics_event_dropped" in r]
    assert len(drops) == 2 and all("table_not_configured" in r for r in drops)


def test_an_event_writes_its_day_row_active_mark_and_first_appearance(
    main_table: MainTable, stats: StatsTable, monkeypatch
):
    _settings(analytics_pseudonym_key=PSEUDONYM_KEY, stoa_release_id="rel-1")

    async def signed_in(_request):
        return _student()

    monkeypatch.setattr(analytics, "optional_actor", signed_in)
    client = _app()
    client.post("/analytics/events", json=_event(path="/ask/conv-123"))
    client.post("/analytics/events", json=_event(name="page_viewed", payload={"route": "/ask/:id", "load_ms": 812.5}))

    pid = analytics_store.pseudonym(REAL_USER_ID)
    assert pid is not None and len(pid) == 16
    events = stats.with_prefix("DAY#")
    assert len(events) == 2
    login = next(row for row in events if row["name"] == "user_login")
    assert login["role"] == "student" and login["pid"] == pid
    assert login["sid"] == "5f1d1c1e-0b2a-4a1f-8f6e-2b0c9d7e4a31"
    assert login["route"] == "/ask/:id" and login["release"] == "rel-1"
    assert login["props"] == {"role": "student"}
    assert login["ttl"] > 0
    page = next(row for row in events if row["name"] == "page_viewed")
    assert page["props"] == {"route": "/ask/:id", "load_ms": Decimal("812.5")}
    actives = stats.with_prefix("ACTIVE#")
    assert [row["SK"] for row in actives] == [f"student#{pid}"]
    firsts = stats.with_prefix("FIRST#")
    assert len(firsts) == 1 and firsts[0]["SK"] == "FIRST" and "first_day" in firsts[0]
    assert main_table.puts == []


def test_the_first_appearance_is_written_once():
    _settings(analytics_pseudonym_key=PSEUDONYM_KEY)
    table = StatsTable()
    analytics_store.install(table)

    for _ in range(3):
        telemetry.record("ai_answered", actor_user_id=REAL_USER_ID, role="student", latency_ms=5, refused=False)
    first = table.with_prefix("FIRST#")[0]
    table.rows[(first["PK"], first["SK"])]["first_day"] = "2020-01-01"
    table.rows.pop(next(k for k in table.rows if k[0].startswith("ACTIVE#")))
    telemetry.record("ai_answered", actor_user_id=REAL_USER_ID, role="student", latency_ms=5, refused=False)

    assert table.with_prefix("FIRST#")[0]["first_day"] == "2020-01-01"
    assert len(table.with_prefix("DAY#")) == 4


def test_the_statistics_table_never_holds_the_real_account_id(
    main_table: MainTable, stats: StatsTable, monkeypatch
):
    _settings(analytics_pseudonym_key=PSEUDONYM_KEY)

    async def signed_in(_request):
        return _student()

    monkeypatch.setattr(analytics, "optional_actor", signed_in)
    monkeypatch.setattr(monitoring, "optional_actor", signed_in)
    client = _app()
    client.post(
        "/analytics/events",
        json=_event(
            payload={"role": "student", "userId": REAL_USER_ID, "studentId": REAL_USER_ID},
            path=f"/students/{REAL_USER_ID}/learning-profile",
        ),
    )
    client.post(
        "/analytics/events",
        json=_event(name="learning_profile_viewed", payload={"studentId": REAL_USER_ID}),
    )
    client.post(
        "/monitoring/frontend-errors",
        json={"message": "boom", "name": "Error", "route": f"/parent/children/{REAL_USER_ID}", "source": "manual"},
    )
    for event, props in (
        ("question_asked", {"subject": "math", "voice": False, "has_image": True}),
        ("ai_answered", {"latency_ms": 900, "refused": False}),
        ("help_escalated", {"wait_ms": None}),
        ("teacher_replied", {"response_ms": 60000}),
        ("exercise_answered", {"exercise_id": "ex-1", "correct": True, "duration_ms": None}),
    ):
        telemetry.record(event, actor_user_id=REAL_USER_ID, role="student", **props)

    assert len(stats.with_prefix("DAY#")) == 8
    stored = json.dumps(list(stats.rows.values()), default=str) + json.dumps(
        [list(key) for key in stats.rows]
    )
    assert REAL_USER_ID not in stored


def test_without_a_pseudonym_key_only_the_session_is_kept(
    main_table: MainTable, stats: StatsTable, monkeypatch
):
    _settings(analytics_pseudonym_key="")

    async def signed_in(_request):
        return _student()

    monkeypatch.setattr(analytics, "optional_actor", signed_in)
    _app().post("/analytics/events", json=_event())

    (row,) = stats.with_prefix("DAY#")
    assert "pid" not in row and row["sid"] and row["role"] == "student"
    assert stats.with_prefix("ACTIVE#") == [] and stats.with_prefix("FIRST#") == []


def test_an_anonymous_event_is_recorded_as_anonymous(main_table: MainTable, stats: StatsTable):
    _app().post("/analytics/events", json=_event())

    (row,) = stats.with_prefix("DAY#")
    assert row["role"] == "anonymous" and "pid" not in row


def test_an_unknown_event_is_accepted_and_dropped(main_table: MainTable, stats: StatsTable, caplog):
    caplog.set_level(logging.INFO)

    unknown = _app().post("/analytics/events", json=_event(name="made_up_event"))
    forged = _app().post("/analytics/events", json=_event(name="question_asked"))

    assert unknown.status_code == 202 and forged.status_code == 202
    assert stats.rows == {}
    assert sum("reason=unknown_event" in m for m in caplog.messages) == 2


def test_unknown_props_are_stripped_and_values_bounded():
    props = event_catalog.clean_props(
        "web_vitals",
        {
            "route": "/map/" + "x" * 500,
            "lcp": 1234.5,
            "inp": True,
            "cls": float("nan"),
            "nested": {"a": 1},
            "content": "the student's question",
        },
    )

    assert props == {"route": ("/map/" + "x" * 500)[:128], "lcp": Decimal("1234.5")}
    assert event_catalog.clean_props("nope", {}) is None


def test_a_failing_statistics_write_never_raises(caplog):
    class Broken:
        def put_item(self, **_kwargs):
            raise RuntimeError("down")

    analytics_store.install(Broken())
    caplog.set_level(logging.INFO)

    telemetry.record("teacher_replied", actor_user_id="t-1", role="teacher", response_ms=5)

    assert any("reason=write_failed" in m for m in caplog.messages)


def test_elapsed_ms_reads_iso_and_refuses_junk():
    from datetime import UTC, datetime

    now = datetime(2026, 11, 25, 12, 0, 1, tzinfo=UTC)
    assert telemetry.elapsed_ms("2026-11-25T12:00:00+00:00", now) == 1000
    assert telemetry.elapsed_ms("2026-11-25T12:00:00Z", now) == 1000
    assert telemetry.elapsed_ms("junk", now) is None
    assert telemetry.elapsed_ms(None, now) is None


# -- frontend errors ---------------------------------------------------------------------


def test_a_frontend_error_is_hashed_cut_and_counted(main_table: MainTable, stats: StatsTable, capsys):
    _settings(stoa_release_id="rel-9")
    stack = "\n".join(f"at fn{index} (https://app.stoaedu.ch/a.js?v=123:1:2)" for index in range(12))
    body = {
        "appEnv": "production",
        "errorId": "e-1",
        "message": "x" * 503,
        "name": "TypeError",
        "route": "/ask/3f2a9c1e-77aa-4b1f-9d0e-12ab34cd56ef",
        "source": "app-error-boundary",
        "stack": stack,
        "componentStack": "in Foo",
        "timestamp": "2026-11-25T12:00:00.000Z",
        "somethingNew": 1,
    }

    response = _app().post("/monitoring/frontend-errors", json=body)

    assert response.status_code == 202
    (row,) = stats.with_prefix("DAY#")
    assert row["name"] == "frontend_error" and row["route"] == "/ask/:id"
    props = row["props"]
    assert props["message_hash"] == monitoring.message_hash("x" * 503)
    assert len(props["message_hash"]) == 12
    assert props["message"] == "TypeError"
    assert props["release"] == "rel-9"
    frames = props["stack"].split("\n")
    assert len(frames) == 8 and all("?" not in frame for frame in frames)
    lines = _emf_lines(capsys.readouterr().out)
    assert len(lines) == 1
    assert lines[0]["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "Stoa/Frontend"
    assert lines[0]["Feature"] == "ask_ai" and lines[0]["FrontendErrors"] == 1
    assert main_table.puts == []


def test_frontend_errors_are_charged_to_their_own_source_window(main_table: MainTable, stats: StatsTable):
    _settings(analytics_ingest_max_events_per_window=1)
    client = _app()

    first = client.post("/monitoring/frontend-errors", json={"message": "a"})
    second = client.post("/monitoring/frontend-errors", json={"message": "b"})
    event = client.post("/analytics/events", json=_event())

    assert (first.status_code, second.status_code, event.status_code) == (202, 429, 202)
    assert {key[0].split("#")[1] for key in main_table.counters} == {
        "FRONTEND-ERRORS",
        "ANALYTICS-EVENTS",
    }



def test_a_frontend_error_keeps_no_text_a_person_wrote(main_table: MainTable, stats: StatsTable):
    """Card 134 audit: the message, and a stack's first line, can carry an email or a child's words."""
    secret = 'Unexpected token, "Mein Sohn versteht Brüche nicht" from anna.muster@schule.ch'
    body = {
        "message": secret,
        "name": "SyntaxError",
        "route": "/teacher/requests/abc",
        "source": "app-error-boundary",
        "stack": f"SyntaxError: {secret}\n    at parse (https://app.stoaedu.ch/assets/a.js?x=1:1:2)\nreader@https://app.stoaedu.ch/assets/b.js:3:4",
    }

    assert _app().post("/monitoring/frontend-errors", json=body).status_code == 202

    (row,) = stats.with_prefix("DAY#")
    stored = repr(row)
    assert "anna" not in stored and "Mein Sohn" not in stored and "schule" not in stored
    assert row["props"]["message"] == "SyntaxError"
    assert row["props"]["message_hash"] == monitoring.message_hash(secret)
    assert row["props"]["stack"].split("\n") == [
        "at parse (https://app.stoaedu.ch/assets/a.js)",
        "reader@https://app.stoaedu.ch/assets/b.js:3:4",
    ]


def test_a_name_that_is_not_a_class_name_is_kept_as_error() -> None:
    assert monitoring.error_kind("TypeError") == "TypeError"
    assert monitoring.error_kind("anna.muster@schule.ch") == "Error"
    assert monitoring.error_kind("") == "Error"
