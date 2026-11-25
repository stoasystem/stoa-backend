"""Card 134-B2: the daily rollup, the usage overview read from it, and the synthetic probe."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from stoa import config
from stoa.config import Settings
from stoa.db import table as db_table
from stoa.jobs import analytics_rollup, synthetic_probe
from stoa.observability import analytics_store, cost_reader, usage_stats

TODAY = datetime.now(UTC).date()
Y = TODAY - timedelta(days=1)


class StatsTable(FakeTable):
    """`FakeTable` plus the `UPDATED_OLD` the active marker asks for."""

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("ReturnValues") != "UPDATED_OLD":
            return super().update_item(**kwargs)
        key = (str(kwargs["Key"]["PK"]), str(kwargs["Key"]["SK"]))
        before = dict(self.rows.get(key) or {})
        super().update_item(**{**kwargs, "ReturnValues": "NONE"})
        old = {name: value for name, value in before.items() if name not in ("PK", "SK")}
        return {"Attributes": old} if old else {}


class FakeCostExplorer:
    """Pages of `get_cost_and_usage` answers; an exception instance is raised instead."""

    def __init__(self, *pages: Any) -> None:
        self.pages = list(pages) or [{"ResultsByTime": []}]
        self.requests: list[dict[str, Any]] = []

    def get_cost_and_usage(self, **request: Any) -> dict[str, Any]:
        self.requests.append(request)
        page = self.pages[min(len(self.requests) - 1, len(self.pages) - 1)]
        if isinstance(page, Exception):
            raise page
        return page


def _cost_page(amounts: dict[str, str], token: str | None = None) -> dict[str, Any]:
    page: dict[str, Any] = {
        "ResultsByTime": [
            {"Groups": [
                {"Keys": [service], "Metrics": {"UnblendedCost": {"Amount": amount, "Unit": "USD"}}}
                for service, amount in amounts.items()
            ]}
        ]
    }
    if token:
        page["NextPageToken"] = token
    return page


@pytest.fixture
def stats_table():
    table = StatsTable()
    analytics_store.install(table)
    cost_reader.install(FakeCostExplorer())
    usage_stats.clear_cache()
    yield table
    analytics_store.install(None)
    cost_reader.install()
    usage_stats.clear_cache()


def _at(day: date, hour: int = 10) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=UTC)


def _event(name: str, day: date, *, role: str, pid: str | None, sid: str | None = None, **props: Any) -> None:
    assert analytics_store.write_event(
        name, role=role, pid=pid, sid=sid, route=str(props.get("route", "")),
        props=props, release="r1", now=_at(day),
    )


def _seed_usage() -> None:
    _event("question_asked", Y - timedelta(days=10), role="student", pid="A")
    _event("ai_answered", Y - timedelta(days=10), role="student", pid="A", latency_ms=1000)
    _event("exercise_answered", Y - timedelta(days=3), role="student", pid="A")
    _event("question_asked", Y, role="student", pid="A")
    _event("ai_answered", Y, role="student", pid="A", latency_ms=3000)
    _event("question_asked", Y, role="student", pid="B")
    _event("help_escalated", Y, role="student", pid="B")
    _event("parent_report_viewed", Y - timedelta(days=7), role="parent", pid="C")
    _event("teacher_replied", Y, role="teacher", pid="T1", response_ms=60000)
    _event("page_viewed", Y, role="anonymous", pid=None, sid="s1", route="/map")


def _seed_profiles(main: FakeTable) -> None:
    main.seed(
        {"PK": "USER#u1", "SK": "PROFILE", "role": "student", "account_status": "invited",
         "listing": "account_profile", "listed_at": f"{Y - timedelta(days=2)}T08:00:00Z"},
        {"PK": "USER#u2", "SK": "PROFILE", "role": "student", "account_status": "active",
         "activated_at": f"{Y}T09:00:00Z", "listing": "account_profile", "listed_at": f"{Y - timedelta(days=1)}T08:00:00Z"},
        {"PK": "USER#u3", "SK": "PROFILE", "role": "parent", "account_status": "active",
         "listing": "account_profile", "listed_at": f"{Y - timedelta(days=40)}T08:00:00Z"},
    )


# ── rollup ───────────────────────────────────────────────────────────────────


def test_rollup_folds_a_day_into_counts_uniques_and_actives(stats_table) -> None:
    _seed_usage()
    result = analytics_rollup.run({"day": Y.isoformat()})
    assert result["status"] == "completed"

    rows = {row["SK"]: row for row in stats_table.rows.values() if row["PK"] == f"ROLLUP#{Y}"}
    assert rows["question_asked#student"]["count"] == 2
    assert rows["question_asked#student"]["unique"] == 2
    assert rows["question_asked#student"]["pids"] == ["A", "B"]
    assert rows["ai_answered#student"]["values"] == [3000]
    assert rows["page_viewed#anonymous"]["unique"] == 1
    assert rows["page_viewed#anonymous"]["by_feature"] == {"practice": 1}
    assert rows["_active#student"]["count"] == 2
    assert rows["_active#teacher"]["pids"] == ["T1"]
    assert rows["_first#student"]["pids"] == ["B"]
    assert rows["_meta"]["complete"] is True
    assert all("ttl" in row for row in rows.values())


def test_rollup_runs_again_to_the_same_rows(stats_table) -> None:
    _seed_usage()
    analytics_rollup.run({"day": Y.isoformat()})

    def rolled() -> dict:
        return {
            key: {k: v for k, v in row.items() if k not in ("computed_at", "ttl")}
            for key, row in stats_table.rows.items()
            if key[0] == f"ROLLUP#{Y}"
        }

    first = rolled()
    stats_table.seed({"PK": f"ROLLUP#{Y}", "SK": "stale_event#student", "count": 99})
    analytics_rollup.run({"day": Y.isoformat()})
    assert rolled() == first


def test_rollup_defaults_to_yesterday_and_backfills_days() -> None:
    now = datetime(2026, 11, 25, 1, 0, tzinfo=UTC)
    assert analytics_rollup.target_days({}, now=now) == ["2026-11-24"]
    assert analytics_rollup.target_days({"days": 3}, now=now) == ["2026-11-22", "2026-11-23", "2026-11-24"]
    assert analytics_rollup.target_days({"day": "2026-10-01"}, now=now) == ["2026-10-01"]
    with pytest.raises(ValueError):
        analytics_rollup.target_days({"days": 91}, now=now)


def test_rollup_skips_without_a_table() -> None:
    analytics_store.install(None)
    assert analytics_rollup.run({})["status"] == "skipped"


# ── overview ─────────────────────────────────────────────────────────────────


def test_overview_from_rollups(stats_table, fake_table) -> None:
    _seed_usage()
    _seed_profiles(fake_table)
    analytics_rollup.run({"days": 30})

    body = usage_stats.overview(7, "all")

    assert body["complete"] is True
    assert body["days"] == 7 and body["role"] == "all"
    kpis = dict(body["kpis"])
    cost = kpis.pop("costPerActiveUser")
    assert kpis == {
        "dau": 3, "wau": 3, "mau": 4, "dauChange": 2.0,
        "questionsPerDay": 0.29, "escalationRate": 0.5,
        "aiP50Ms": 3000, "teacherResponseP50Ms": 60000,
        "wauChange": 0.5, "mauChange": None, "questionsPerDayChange": 1.0,
    }
    assert cost is not None and cost["totalUsd"] == 0.0
    assert len(body["activeSeries"]) == 7
    assert body["activeSeries"][-1] == {"day": Y.isoformat(), "active": 3}
    ranking = {item["event"]: item for item in body["featureRanking"]}
    assert ranking["question_asked"] == {"event": "question_asked", "count": 2, "uniqueUsers": 2}
    assert ranking["page_viewed"]["uniqueUsers"] == 1
    assert body["featureRanking"][0]["event"] == "question_asked"
    assert body["funnel"] == [
        {"step": "invited", "count": 2},
        {"step": "activated", "count": 1},
        {"step": "first_question", "count": 1},
        {"step": "first_exercise", "count": 0},
        {"step": "week2_active", "count": 0},
    ]
    assert len(body["retention"]) == 1
    cohort = body["retention"][0]
    assert cohort["size"] == 2
    assert cohort["weeks"][0] == 1.0 and cohort["weeks"][1:] == [None, None, None, None]


def test_overview_for_one_role(stats_table, fake_table) -> None:
    _seed_usage()
    _seed_profiles(fake_table)
    analytics_rollup.run({"days": 30})

    body = usage_stats.overview(30, "student")

    assert body["kpis"]["dau"] == 2 and body["kpis"]["mau"] == 2
    assert body["kpis"]["teacherResponseP50Ms"] is None
    assert body["kpis"]["aiP50Ms"] == 2000
    funnel = {step["step"]: step["count"] for step in body["funnel"]}
    assert funnel["invited"] == 2
    assert funnel["first_exercise"] == 1
    assert funnel["week2_active"] == 1


def test_a_day_without_rollup_is_computed_and_flagged(stats_table, fake_table) -> None:
    _seed_usage()
    analytics_rollup.run({"days": 30})
    rolled = usage_stats.overview(7, "all")
    usage_stats.clear_cache()
    del stats_table.rows[(f"ROLLUP#{Y - timedelta(days=3)}", "_meta")]

    raw = usage_stats.overview(7, "all")

    assert rolled["complete"] is True and raw["complete"] is False
    assert {k: v for k, v in raw.items() if k not in ("complete", "generatedAt")} == {
        k: v for k, v in rolled.items() if k not in ("complete", "generatedAt")
    }


def test_overview_without_any_data_answers_zeros_and_nulls(stats_table) -> None:
    body = usage_stats.overview(30, "all")
    assert body["kpis"]["dau"] == 0 and body["kpis"]["dauChange"] is None
    assert body["kpis"]["wauChange"] is None and body["kpis"]["mauChange"] is None
    assert body["kpis"]["questionsPerDayChange"] is None
    assert body["kpis"]["escalationRate"] is None and body["kpis"]["aiP50Ms"] is None
    assert body["complete"] is False
    assert body["retention"] == []


def test_overview_reads_profiles_through_the_listing_only(stats_table, fake_table) -> None:
    _seed_profiles(fake_table)
    usage_stats.overview(7, "all")
    assert fake_table.calls["scan"] == 0
    queries = [request for op, request in fake_table.requests if op == "query"]
    assert queries and all(request["IndexName"] == "GSI-Listing" for request in queries)
    assert usage_stats.ACCOUNT_PROFILE_LISTING == "account_profile"


# ── synthetic probe ──────────────────────────────────────────────────────────


class FakeTransport:
    def __init__(self, *, login_status: int = 200, failing: set[str] = frozenset()):
        self.login_status = login_status
        self.failing = failing
        self.requests: list[tuple[str, str, dict, bytes | None]] = []

    def __call__(self, method, url, headers, body, timeout):
        self.requests.append((method, url, headers, body))
        if url.endswith("/auth/login"):
            if self.login_status != 200:
                return self.login_status, b'{"detail":"no"}'
            return 200, json.dumps({"accessToken": "tok-1"}).encode()
        assert headers["Authorization"] == "Bearer tok-1"
        path = url.split("api.stoaedu.ch", 1)[1]
        return (503 if path in self.failing else 200), b"{}"


def _probe_settings(**overrides: Any) -> None:
    config.install(
        Settings(stoa_probe_email="probe@test.stoaedu.ch", stoa_probe_password="pw", **overrides)
    )


def test_probe_without_credentials_does_nothing(stats_table) -> None:
    transport = FakeTransport()
    assert synthetic_probe.run(transport=transport)["status"] == "skipped"
    assert transport.requests == []


def test_probe_walks_only_the_read_only_paths(stats_table) -> None:
    _probe_settings()
    transport = FakeTransport(failing={"/notifications"})
    lines: list[str] = []
    now = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)

    result = synthetic_probe.run(transport=transport, now=now, write_line=lines.append)

    assert [(method, url.split("api.stoaedu.ch", 1)[1]) for method, url, *_ in transport.requests] == [
        ("POST", "/auth/login"),
        ("GET", "/auth/me"),
        ("GET", "/practice/knowledge-map/stars"),
        ("GET", "/practice/curriculum/catalog"),
        ("GET", "/notifications"),
        ("GET", "/conversations"),
        ("GET", "/teacher-help/availability"),
    ]
    assert all(body is None for method, _url, _h, body in transport.requests if method == "GET")
    assert result["failed"] == ["list"]
    rows = sorted(row["SK"] for row in stats_table.rows.values() if row["PK"] == "PROBE#2026-11-25")
    assert rows[0] == "2026-11-25T12:00:00Z#ask_ai#conversations"
    assert len(rows) == 7
    row = stats_table.rows[("PROBE#2026-11-25", "2026-11-25T12:00:00Z#notifications#list")]
    assert row["ok"] is False and row["status"] == 503 and "ttl" in row
    metrics = [json.loads(line) for line in lines]
    assert len(metrics) == 7
    assert metrics[0]["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "Stoa/Probes"
    assert {m["Feature"] for m in metrics} == {"auth", "practice", "notifications", "ask_ai", "teacher_help"}
    assert all("ProbeSuccess" in m and "ProbeLatency" in m for m in metrics)
    assert all("pw" not in line and "tok-1" not in line for line in lines)


def test_every_probe_request_is_whitelisted_and_none_asks_the_model() -> None:
    allowed = synthetic_probe.ALLOWED_REQUESTS
    assert allowed == {
        ("POST", "/auth/login"),
        ("GET", "/auth/me"),
        ("GET", "/practice/knowledge-map/stars"),
        ("GET", "/practice/curriculum/catalog"),
        ("GET", "/notifications"),
        ("GET", "/conversations"),
        ("GET", "/teacher-help/availability"),
    }
    assert all(method == "GET" for method, path in allowed if path != "/auth/login")


def test_a_request_off_the_whitelist_is_refused_before_it_is_sent() -> None:
    sent: list = []
    send = synthetic_probe._guarded(lambda *args: sent.append(args) or (200, b""), "https://api.stoaedu.ch")
    for method, path in [("POST", "/conversations"), ("POST", "/questions"), ("GET", "/admin/stats")]:
        with pytest.raises(synthetic_probe.RequestNotAllowed):
            send(method, "https://api.stoaedu.ch" + path, {}, None, 1.0)
    assert sent == []


def test_a_failed_login_records_only_the_login(stats_table) -> None:
    _probe_settings()
    transport = FakeTransport(login_status=401)
    result = synthetic_probe.run(transport=transport, now=datetime(2026, 11, 25, 12, 0, tzinfo=UTC), write_line=lambda _l: None)
    assert len(transport.requests) == 1
    assert result["failed"] == ["login"]
    assert [row["SK"] for row in stats_table.rows.values()] == ["2026-11-25T12:00:00Z#auth#login"]


def test_probe_does_not_touch_the_main_table(stats_table) -> None:
    main = FakeTable()
    db_table.install(main)
    _probe_settings()
    synthetic_probe.run(transport=FakeTransport(), write_line=lambda _l: None)
    assert main.calls["put_item"] == 0


@pytest.mark.parametrize("job", ["analytics_rollup", "synthetic_probe"])
def test_the_ops_function_hands_each_card_134_job_to_its_own_module(
    job: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The jobs run on the account-deletion function's schedules; a name that missed
    its branch would fall through to running deletions."""
    import importlib

    from stoa.jobs import account_deletion as ops

    module = importlib.import_module(f"stoa.jobs.{job}")
    monkeypatch.setattr(module, "handler", lambda event, context: {"ran": job})
    monkeypatch.setattr(
        ops, "run_pending_deletions", lambda **_: (_ for _ in ()).throw(AssertionError("deletions ran"))
    )
    assert ops.handler({"job": job}, None) == {"ran": job}


# ── change and cost per active user ──────────────────────────────────────────


def test_change_against_an_empty_window_is_null() -> None:
    assert usage_stats._change(5, 0) is None
    assert usage_stats._change(0, 0) is None
    assert usage_stats._change(3, 2) == 0.5
    assert usage_stats._change(9, 10) == -0.1


def test_service_names_fall_into_three_buckets() -> None:
    assert cost_reader.service_bucket("Amazon Bedrock") == "ai"
    assert cost_reader.service_bucket("Claude 3 Haiku (Amazon Bedrock Edition)") == "ai"
    assert cost_reader.service_bucket("Amazon DynamoDB") == "database"
    assert cost_reader.service_bucket("Tax") == "other"
    assert cost_reader.service_bucket("AWS Lambda") == "other"


def test_month_to_date_asks_monthly_unblended_by_service_and_follows_pages() -> None:
    ce = FakeCostExplorer(
        _cost_page({"Amazon Bedrock": "10.5", "Amazon DynamoDB": "2.25"}, token="t1"),
        _cost_page({"Claude 3 Haiku (Amazon Bedrock Edition)": "1.5", "Tax": "3", "AWS Lambda": "0.75"}),
    )
    cost_reader.install(ce)
    try:
        totals = cost_reader.month_to_date(date(2026, 11, 26))
    finally:
        cost_reader.install()
    assert totals == {"ai": 12.0, "database": 2.25, "other": 3.75}
    first = ce.requests[0]
    assert first["TimePeriod"] == {"Start": "2026-11-01", "End": "2026-11-27"}
    assert first["Granularity"] == "MONTHLY" and first["Metrics"] == ["UnblendedCost"]
    assert first["GroupBy"] == [{"Type": "DIMENSION", "Key": "SERVICE"}]
    assert ce.requests[1]["NextPageToken"] == "t1"


def test_the_cost_explorer_client_is_built_in_us_east_1(monkeypatch) -> None:
    from stoa import aws

    built: list[tuple[str, str]] = []

    class Session:
        def client(self, service: str, *, region_name: str, config: Any) -> object:
            built.append((service, region_name))
            return object()

    monkeypatch.setattr(aws, "session", lambda: Session())
    cost_reader._real_client.cache_clear()
    try:
        cost_reader._real_client()
    finally:
        cost_reader._real_client.cache_clear()
    assert built == [("ce", "us-east-1")]


NOW = datetime(2026, 11, 26, 9, tzinfo=UTC)


def _active(table: FakeTable, day: str, role: str, pid: str) -> None:
    table.seed({"PK": f"ACTIVE#{day}", "SK": f"{role}#{pid}", "role": role, "pid": pid})


def test_cost_per_active_user_divides_by_the_month_union(stats_table) -> None:
    _active(stats_table, "2026-11-01", "student", "A")
    _active(stats_table, "2026-11-20", "student", "A")
    _active(stats_table, "2026-11-26", "teacher", "T")
    _active(stats_table, "2026-11-10", "parent", "P")
    _active(stats_table, "2026-10-31", "student", "OLD")
    ce = FakeCostExplorer(_cost_page({"Amazon Bedrock": "6", "Amazon DynamoDB": "1.5", "Tax": "1.5"}))
    cost_reader.install(ce)

    cost = usage_stats.cost_per_active_user(NOW)

    assert cost == {
        "amountUsd": 3.0, "totalUsd": 9.0, "activeUsers": 3,
        "periodStart": "2026-11-01", "periodEnd": "2026-11-26",
        "breakdown": [
            {"service": "ai", "amountUsd": 2.0},
            {"service": "database", "amountUsd": 0.5},
            {"service": "other", "amountUsd": 0.5},
        ],
    }
    assert usage_stats.cost_per_active_user(NOW) == cost
    assert len(ce.requests) == 1


def test_no_active_user_leaves_the_amount_null_and_the_total(stats_table) -> None:
    cost_reader.install(FakeCostExplorer(_cost_page({"Amazon Bedrock": "4.567"})))
    cost = usage_stats.cost_per_active_user(NOW)
    assert cost is not None
    assert cost["amountUsd"] is None and cost["totalUsd"] == 4.57 and cost["activeUsers"] == 0
    assert all(item["amountUsd"] is None for item in cost["breakdown"])


def test_a_failed_cost_read_nulls_the_whole_figure(stats_table) -> None:
    _active(stats_table, "2026-11-02", "student", "A")
    cost_reader.install(FakeCostExplorer(RuntimeError("AccessDenied")))
    assert usage_stats.cost_per_active_user(NOW) is None
    body = usage_stats.overview(7, "all", now=NOW)
    assert body["kpis"]["costPerActiveUser"] is None
    assert body["kpis"]["dau"] == 0


def test_without_a_statistics_table_the_cost_is_null(stats_table) -> None:
    analytics_store.install(None)
    cost_reader.install(FakeCostExplorer(_cost_page({"Amazon Bedrock": "1"})))
    assert usage_stats.cost_per_active_user(NOW) is None
