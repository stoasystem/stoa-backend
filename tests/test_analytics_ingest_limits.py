"""Card 002 gap #10: the open analytics write path is charged and bounded.

`/analytics/events` is reachable without a token by design. What was missing is a
price: any caller could put unbounded rows of unbounded size into the single table,
and the only thing that separated one caller from another was a `sessionId` the
caller minted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dynamodb_expression_assertions import assert_expression_placeholders_closed

from stoa.config import settings
from stoa.routers import analytics


NOW = datetime(2026, 9, 20, 12, 0, 30, tzinfo=UTC)


class _AnalyticsTable:
    """Counter-honest table double: ADD accumulates, and the expression is checked."""

    def __init__(self, *, update_fails: bool = False) -> None:
        self.counters: dict[tuple[str, str], int] = {}
        self.puts: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.update_fails = update_fails

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self.update_calls.append(kwargs)
        assert_expression_placeholders_closed({"Update": kwargs})
        if self.update_fails:
            raise RuntimeError("counter unavailable")
        key = (kwargs["Key"]["PK"], kwargs["Key"]["SK"])
        increment = int(kwargs["ExpressionAttributeValues"][":one"])
        self.counters[key] = self.counters.get(key, 0) + increment
        return {"Attributes": {"count": Decimal(self.counters[key])}}

    def put_item(self, *, Item: dict[str, Any]) -> dict[str, Any]:
        self.puts.append(Item)
        return {}


class _StubRequest:
    """The two attributes the source derivation is allowed to look at."""

    def __init__(self, peer: str, headers: dict[str, str] | None = None) -> None:
        self.client = type("_Peer", (), {"host": peer})()
        self.headers = headers or {}


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> _AnalyticsTable:
    fake = _AnalyticsTable()
    monkeypatch.setattr(analytics, "get_table", lambda: fake)
    return fake


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
    return TestClient(app)


def _event(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "user_login",
        "payload": {"durationMs": 412, "ok": True},
        "path": "/login",
        "sessionId": "5f1d1c1e-0b2a-4a1f-8f6e-2b0c9d7e4a31",
        "createdAt": "2026-09-20T12:00:30.000Z",
    }
    body.update(overrides)
    return body


def _counter_keys(table: _AnalyticsTable) -> set[str]:
    return {key[0] for key in table.counters}


def _tuned(**overrides: Any) -> Any:
    return settings.model_copy(update=overrides)


# ---------------------------------------------------------------------------
# The route still answers what it always answered
# ---------------------------------------------------------------------------


def test_未认证的调用仍然被接受并写一行(table: _AnalyticsTable) -> None:
    response = _client().post("/analytics/events", json=_event())

    assert response.status_code == 202, response.text
    assert response.json() == {"status": "accepted"}
    assert len(table.puts) == 1
    assert table.puts[0]["name"] == "user_login"
    assert table.puts[0]["session_id"] == "5f1d1c1e-0b2a-4a1f-8f6e-2b0c9d7e4a31"


# ---------------------------------------------------------------------------
# Negative control: the shipped default must not stand in normal usage's way
# ---------------------------------------------------------------------------


def test_出厂额度放行一整个窗口的正常用量(table: _AnalyticsTable) -> None:
    """One source may spend its whole configured window allowance without a refusal.

    A limit that refuses ordinary traffic is not a limit, it is an outage; the 39
    `trackEvent` call sites in the web client share one source address behind a
    school's NAT, so the allowance has to hold the aggregate, not one browser.
    """
    request = _StubRequest("198.51.100.7")

    for _ in range(settings.analytics_ingest_max_events_per_window):
        analytics.admit_analytics_event(request, now=NOW, table=table)

    assert sum(table.counters.values()) == settings.analytics_ingest_max_events_per_window

    with pytest.raises(Exception) as refusal:
        analytics.admit_analytics_event(request, now=NOW, table=table)
    assert getattr(refusal.value, "status_code", None) == 429


# ---------------------------------------------------------------------------
# The bucket is the observed source, not anything the caller chose
# ---------------------------------------------------------------------------


def test_分桶按网关观测到的地址_换sessionId换不来新额度(
    table: _AnalyticsTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(analytics, "settings", _tuned(analytics_ingest_max_events_per_window=2))
    client = _client()

    statuses = [
        client.post("/analytics/events", json=_event(sessionId=f"session-{index}")).status_code
        for index in range(3)
    ]

    assert statuses == [202, 202, 429]
    assert len(_counter_keys(table)) == 1
    assert len(table.puts) == 2


def test_不同来源地址各自计数(table: _AnalyticsTable) -> None:
    analytics.admit_analytics_event(_StubRequest("198.51.100.7"), now=NOW, table=table)
    analytics.admit_analytics_event(_StubRequest("203.0.113.9"), now=NOW, table=table)

    assert len(_counter_keys(table)) == 2
    assert set(table.counters.values()) == {1}


def test_窗口滚过之后重新放行(
    table: _AnalyticsTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(analytics, "settings", _tuned(analytics_ingest_max_events_per_window=1))
    request = _StubRequest("198.51.100.7")
    later = datetime.fromtimestamp(
        NOW.timestamp() + settings.analytics_ingest_window_seconds, tz=UTC
    )

    analytics.admit_analytics_event(request, now=NOW, table=table)
    with pytest.raises(Exception):
        analytics.admit_analytics_event(request, now=NOW, table=table)
    analytics.admit_analytics_event(request, now=later, table=table)

    assert len(table.counters) == 2


# ---------------------------------------------------------------------------
# Refusal costs the caller the same, and is charged before the row is written
# ---------------------------------------------------------------------------


def test_超额时拒绝且不写事件行(
    table: _AnalyticsTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(analytics, "settings", _tuned(analytics_ingest_max_events_per_window=1))
    client = _client()

    assert client.post("/analytics/events", json=_event()).status_code == 202
    refused = client.post("/analytics/events", json=_event())

    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "analytics_ingest_rate_limited"
    assert refused.headers["retry-after"] == str(settings.analytics_ingest_window_seconds)
    assert len(table.puts) == 1


def test_计数器写不进去时拒绝而不是放行(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = _AnalyticsTable(update_fails=True)
    monkeypatch.setattr(analytics, "get_table", lambda: broken)

    response = _client().post("/analytics/events", json=_event())

    assert response.status_code == 429
    assert broken.puts == []


# ---------------------------------------------------------------------------
# One request cannot become one very large row
# ---------------------------------------------------------------------------


def test_前端形状的载荷原样存下且不标记截断(table: _AnalyticsTable) -> None:
    payload = {"durationMs": 412, "ok": True, "plan": "free", "attempts": None}

    _client().post("/analytics/events", json=_event(payload=payload))

    stored = table.puts[0]
    assert stored["payload"] == payload
    assert stored["payload_truncated"] is False


def test_嵌套结构与超长字符串与超量字段都被挡在行外(table: _AnalyticsTable) -> None:
    payload: dict[str, Any] = {
        "nested": {"a": 1},
        "listed": [1, 2, 3],
        "long": "x" * (settings.analytics_payload_max_value_length + 50),
    }
    payload.update(
        {f"key{index}": index for index in range(settings.analytics_payload_max_entries + 10)}
    )

    _client().post("/analytics/events", json=_event(payload=payload))

    stored = table.puts[0]
    assert "nested" not in stored["payload"]
    assert "listed" not in stored["payload"]
    assert len(stored["payload"]["long"]) == settings.analytics_payload_max_value_length
    assert len(stored["payload"]) <= settings.analytics_payload_max_entries
    assert stored["payload_truncated"] is True


def test_浮点数仍然转成Decimal且不算截断(table: _AnalyticsTable) -> None:
    _client().post("/analytics/events", json=_event(payload={"score": 0.1}))

    assert table.puts[0]["payload"]["score"] == Decimal("0.1")
    assert table.puts[0]["payload_truncated"] is False


# ---------------------------------------------------------------------------
# The counter write itself
# ---------------------------------------------------------------------------


def test_计数写的是带TTL的固定窗口行(table: _AnalyticsTable) -> None:
    analytics.admit_analytics_event(_StubRequest("198.51.100.7"), now=NOW, table=table)

    call = table.update_calls[0]
    window = int(NOW.timestamp()) - int(NOW.timestamp()) % settings.analytics_ingest_window_seconds
    assert call["Key"]["PK"].startswith("SOURCEWINDOW#ANALYTICS-EVENTS#")
    assert call["Key"]["SK"] == f"WINDOW#{window}"
    assert call["ExpressionAttributeValues"][":expires"] == (
        window + 2 * settings.analytics_ingest_window_seconds
    )
    assert call["ReturnValues"] == "UPDATED_NEW"
