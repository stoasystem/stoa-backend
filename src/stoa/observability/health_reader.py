"""What the admin system-health pages read: metrics, alarms, logs, probes, deploys (card 134).

Every AWS source is read with a short timeout and degrades to empty or null
rather than failing the page; `partial` says one of them did not answer.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from itertools import islice
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.config import Config

from stoa import aws, config
from stoa.aws import Kind
from stoa.db import table as db_table
from stoa.observability import analytics_store, features, request_metrics, usage_stats

logger = logging.getLogger(__name__)

# window -> (seconds, spark period, series period); 12 spark points each.
WINDOWS: Mapping[str, tuple[int, int, int]] = {
    "1h": (3600, 300, 60),
    "24h": (86400, 7200, 900),
    "7d": (604800, 50400, 3600),
}
ALARM_PREFIX = "stoa-"
FEATURE_ALARM_PREFIX = "stoa-feature-"
API_FUNCTION_NAME = "stoa-api"
API_LOG_GROUP = "/aws/lambda/stoa-api"
LOGS_WAIT_SECONDS = 12.0
LOGS_POLL_SECONDS = 1.0
HEALTH_CACHE_SECONDS = 30.0
DETAIL_CACHE_SECONDS = 60.0
DEPLOY_CACHE_SECONDS = 300.0
DEPLOYS_SHOWN = 10
VERSION_PAGE_BUDGET = 20
PROBE_PAGE_BUDGET = 5
FRONTEND_PAGE_BUDGET = 20
ERROR_RATE_WARN = 0.01

_READ_CONFIG = Config(connect_timeout=2, read_timeout=5, retries={"mode": "standard", "total_max_attempts": 2})

_installed: dict[str, Any] = {}


def install(*, cloudwatch: Any = None, logs: Any = None) -> None:
    """Put doubles where the CloudWatch and Logs clients would be; no arguments clears."""
    _installed.clear()
    if cloudwatch is not None:
        _installed["cloudwatch"] = cloudwatch
    if logs is not None:
        _installed["logs"] = logs


@lru_cache
def _real_client(service: str, region: str) -> Any:
    return aws.session().client(service, region_name=region, config=_READ_CONFIG)


def _client(service: str) -> Any:
    if service in _installed:
        return _installed[service]
    return _real_client(service, config.settings().aws_region)


def _lambda() -> Any:
    return aws.client(Kind.LAMBDA)


# -- caching ---------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache: dict[Any, tuple[float, Any]] = {}


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _cached(key: Any, seconds: float, build: Callable[[], Any]) -> Any:
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < seconds:
            return hit[1]
    value = build()
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)
    return value


# -- helpers ---------------------------------------------------------------------


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace(" ", "T", 1)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if len(text) > 5 and text[-5] in "+-" and text[-3] != ":":
        text = text[:-2] + ":" + text[-2:]
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso_or_none(value: Any) -> str | None:
    parsed = _parse_time(value)
    return iso(parsed) if parsed else None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def feature_status(
    *,
    open_alarms: int,
    probe_failed_twice: bool,
    requests: float | None,
    error_rate: float | None,
    p95_ms: float | None,
    p95_limit_ms: int,
    probe_in_window: bool,
) -> str:
    """bad / warn / unknown / ok, by the card 134 rule."""
    if open_alarms > 0 or probe_failed_twice:
        return "bad"
    if (p95_ms is not None and p95_ms > p95_limit_ms) or (
        error_rate is not None and error_rate > ERROR_RATE_WARN
    ):
        return "warn"
    if not requests and not probe_in_window:
        return "unknown"
    return "ok"


def alarm_feature(name: str) -> str | None:
    if not name.startswith(FEATURE_ALARM_PREFIX):
        return None
    rest = name[len(FEATURE_ALARM_PREFIX) :]
    for key in sorted(features.FEATURE_KEYS, key=len, reverse=True):
        if rest.startswith(key + "-"):
            return key
    return None


# -- CloudWatch metrics ----------------------------------------------------------


def _metric_query(qid: str, namespace: str, metric: str, feature: str, stat: str, period: int) -> dict:
    return {
        "Id": qid,
        "MetricStat": {
            "Metric": {
                "Namespace": namespace,
                "MetricName": metric,
                "Dimensions": [{"Name": "Feature", "Value": feature}],
            },
            "Period": period,
            "Stat": stat,
        },
        "ReturnData": True,
    }


def metric_data(
    queries: list[dict[str, Any]], start: datetime, end: datetime
) -> dict[str, list[tuple[datetime, float]]]:
    """Each query's points, oldest first."""
    client = _client("cloudwatch")
    found: dict[str, list[tuple[datetime, float]]] = {query["Id"]: [] for query in queries}
    for offset in range(0, len(queries), 500):
        request: dict[str, Any] = {
            "MetricDataQueries": queries[offset : offset + 500],
            "StartTime": start,
            "EndTime": end,
            "ScanBy": "TimestampAscending",
        }
        for _page in range(20):
            response = client.get_metric_data(**request)
            for result in response.get("MetricDataResults", []):
                points = found.setdefault(result["Id"], [])
                for stamp, value in zip(result.get("Timestamps", []), result.get("Values", [])):
                    moment = _parse_time(stamp)
                    if moment is not None:
                        points.append((moment, float(value)))
            token = response.get("NextToken")
            if not token:
                break
            request["NextToken"] = token
    for points in found.values():
        points.sort(key=lambda point: point[0])
    return found


def _sum(points: Iterable[tuple[datetime, float]]) -> float:
    return sum(value for _, value in points)


def _peak(points: list[tuple[datetime, float]]) -> float | None:
    return max((value for _, value in points), default=None)


def _buckets(end: datetime, seconds: int, period: int) -> list[datetime]:
    start = end - timedelta(seconds=seconds)
    return [start + timedelta(seconds=period * index) for index in range(seconds // period)]


def _bucketed(
    points: list[tuple[datetime, float]],
    buckets: list[datetime],
    period: int,
    combine: Callable[[float, float], float] = lambda a, b: a + b,
) -> list[float | None]:
    values: list[float | None] = [None] * len(buckets)
    if not buckets:
        return values
    first = buckets[0]
    for moment, value in points:
        index = int((moment - first).total_seconds() // period)
        if 0 <= index < len(buckets):
            values[index] = value if values[index] is None else combine(values[index], value)
    return values


# -- alarms, deploys, probes -----------------------------------------------------


def alarms() -> list[dict[str, Any]]:
    client = _client("cloudwatch")
    request: dict[str, Any] = {
        "AlarmNamePrefix": ALARM_PREFIX,
        "AlarmTypes": ["MetricAlarm", "CompositeAlarm"],
        "MaxRecords": 100,
    }
    found: list[dict[str, Any]] = []
    for _page in range(10):
        response = client.describe_alarms(**request)
        for alarm in [*response.get("MetricAlarms", []), *response.get("CompositeAlarms", [])]:
            name = str(alarm.get("AlarmName") or "")
            found.append(
                {
                    "name": name,
                    "feature": alarm_feature(name),
                    "state": str(alarm.get("StateValue") or "INSUFFICIENT_DATA"),
                    "since": _iso_or_none(alarm.get("StateUpdatedTimestamp")),
                    "reason": alarm.get("StateReason"),
                }
            )
        token = response.get("NextToken")
        if not token:
            break
        request["NextToken"] = token
    order = {"ALARM": 0, "INSUFFICIENT_DATA": 1, "OK": 2}
    found.sort(key=lambda alarm: (order.get(alarm["state"], 3), alarm["name"]))
    return found


def deploys() -> list[dict[str, Any]]:
    """The API function's published versions, newest first: one per deploy."""

    def build() -> list[dict[str, Any]]:
        client = _lambda()
        request: dict[str, Any] = {"FunctionName": API_FUNCTION_NAME, "MaxItems": 50}
        versions: list[dict[str, Any]] = []
        for _page in range(VERSION_PAGE_BUDGET):
            response = client.list_versions_by_function(**request)
            versions.extend(
                version for version in response.get("Versions", []) if version.get("Version") != "$LATEST"
            )
            marker = response.get("NextMarker")
            if not marker:
                break
            request["Marker"] = marker
        versions.sort(key=lambda version: int(version.get("Version") or 0), reverse=True)
        return [
            {
                "at": _iso_or_none(version.get("LastModified")),
                "release": str(version.get("Description") or f"v{version.get('Version')}"),
            }
            for version in versions[:DEPLOYS_SHOWN]
        ]

    return _cached(("deploys",), DEPLOY_CACHE_SECONDS, build)


def probe_rows(now: datetime) -> list[dict[str, Any]]:
    """Today's and yesterday's probe steps, newest first."""
    target = analytics_store.table()
    if target is None:
        return []
    rows: list[dict[str, Any]] = []
    for day in (now.date(), now.date() - timedelta(days=1)):
        for page in islice(
            db_table.pages(
                "query",
                table=target,
                KeyConditionExpression=Key("PK").eq(f"PROBE#{day.isoformat()}"),
                ScanIndexForward=False,
            ),
            PROBE_PAGE_BUDGET,
        ):
            rows.extend(page.items)
            if page.last_key is None:
                break
    rows.sort(key=lambda row: str(row.get("SK", "")), reverse=True)
    return rows


def _runs(rows: list[dict[str, Any]], feature: str) -> list[tuple[str, list[dict[str, Any]]]]:
    runs: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("feature") != feature:
            continue
        runs.setdefault(str(row.get("at") or str(row.get("SK", "")).split("#", 1)[0]), []).append(row)
    return sorted(runs.items(), key=lambda run: run[0], reverse=True)


def probe_summary(rows: list[dict[str, Any]], feature: str) -> tuple[dict[str, Any] | None, bool]:
    """The feature's latest probe run, and whether its last two runs both failed."""
    runs = _runs(rows, feature)
    if not runs:
        return None, False
    ok = [all(bool(step.get("ok")) for step in steps) for _, steps in runs[:2]]
    at, steps = runs[0]
    latency = sum(_number(step.get("latency_ms")) or 0 for step in steps)
    summary = {"ok": ok[0], "lastRunAt": _iso_or_none(at), "latencyMs": int(round(latency))}
    return summary, len(ok) == 2 and not any(ok)


# -- health ----------------------------------------------------------------------


def health(window: str, *, now: datetime | None = None) -> dict[str, Any]:
    return _cached(("health", window), HEALTH_CACHE_SECONDS, lambda: _health(window, now))


def _health(window: str, now: datetime | None) -> dict[str, Any]:
    moment = (now or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
    seconds, spark_period, _series = WINDOWS[window]
    start = moment - timedelta(seconds=seconds)
    partial = False

    queries: list[dict[str, Any]] = []
    for key in features.HEALTH_FEATURE_KEYS:
        ns = request_metrics.FEATURE_NAMESPACE
        queries += [
            _metric_query(f"req_{key}", ns, "Requests", key, "Sum", seconds),
            _metric_query(f"err_{key}", ns, "Errors5xx", key, "Sum", seconds),
            _metric_query(f"p95_{key}", ns, "Latency", key, "p95", seconds),
            _metric_query(f"sreq_{key}", ns, "Requests", key, "Sum", spark_period),
            _metric_query(f"sp95_{key}", ns, "Latency", key, "p95", spark_period),
        ]
    for key in sorted(features.FEATURE_KEYS):
        queries.append(
            _metric_query(f"fe_{key}", request_metrics.FRONTEND_NAMESPACE, "FrontendErrors", key, "Sum", seconds)
        )
    try:
        points = metric_data(queries, start, moment)
    except Exception as error:
        logger.warning("system_health_metrics_failed error=%s", type(error).__name__)
        points, partial = None, True
    try:
        alarm_list = alarms()
    except Exception as error:
        logger.warning("system_health_alarms_failed error=%s", type(error).__name__)
        alarm_list, partial = [], True
    try:
        deploy_list = deploys()
    except Exception as error:
        logger.warning("system_health_deploys_failed error=%s", type(error).__name__)
        deploy_list, partial = [], True
    try:
        probes = probe_rows(moment)
    except Exception as error:
        logger.warning("system_health_probes_failed error=%s", type(error).__name__)
        probes, partial = [], True

    buckets = _buckets(moment, seconds, spark_period)
    items = []
    for key in features.HEALTH_FEATURE_KEYS:
        limit = features.FEATURE_P95_LIMIT_MS[key]
        if points is None:
            requests = errors = p95 = None
            spark = [{"t": iso(bucket), "requests": None, "p95Ms": None} for bucket in buckets]
        else:
            requests = _sum(points[f"req_{key}"])
            errors = _sum(points[f"err_{key}"])
            p95 = _peak(points[f"p95_{key}"])
            spark_requests = _bucketed(points[f"sreq_{key}"], buckets, spark_period)
            spark_p95 = _bucketed(points[f"sp95_{key}"], buckets, spark_period, max)
            spark = [
                {
                    "t": iso(bucket),
                    "requests": int(spark_requests[index] or 0),
                    "p95Ms": None if spark_p95[index] is None else int(round(spark_p95[index])),
                }
                for index, bucket in enumerate(buckets)
            ]
        error_rate = round(errors / requests, 4) if requests else None
        probe, failed_twice = probe_summary(probes, key)
        last_run = _parse_time(probe["lastRunAt"]) if probe else None
        open_alarms = sum(1 for alarm in alarm_list if alarm["feature"] == key and alarm["state"] == "ALARM")
        items.append(
            {
                "key": key,
                "status": feature_status(
                    open_alarms=open_alarms,
                    probe_failed_twice=failed_twice,
                    requests=requests,
                    error_rate=error_rate,
                    p95_ms=p95,
                    p95_limit_ms=limit,
                    probe_in_window=bool(last_run and last_run >= start),
                ),
                "requests": None if requests is None else int(requests),
                "errorRate": error_rate,
                "p95Ms": None if p95 is None else int(round(p95)),
                "p95LimitMs": limit,
                "spark": spark,
                "probe": probe,
                "openAlarms": open_alarms,
            }
        )
    frontend_total = (
        None if points is None else int(sum(_sum(points[f"fe_{key}"]) for key in features.FEATURE_KEYS))
    )
    result: dict[str, Any] = {
        "generatedAt": iso(moment),
        "window": window,
        "features": items,
        "alarms": alarm_list,
        "deploys": deploy_list,
        "frontendErrors": {"total": frontend_total},
    }
    if partial:
        result["partial"] = True
    return result


# -- feature detail --------------------------------------------------------------


def _routes_query(feature: str) -> str:
    return (
        f'filter Feature = "{feature}" and ispresent(Requests)'
        " | stats count(*) as requests, sum(Errors5xx) as errors,"
        " pct(Latency, 50) as p50, pct(Latency, 95) as p95 by route, method"
        " | sort p95 desc | limit 50"
    )


def _errors_query(feature: str) -> str:
    return (
        f'filter Feature = "{feature}" and ispresent(Requests) and status >= 500'
        " | stats count(*) as count, max(@timestamp) as at by route, method, status"
        " | sort at desc | limit 20"
    )


def logs_insights(
    queries: Mapping[str, str],
    start: datetime,
    end: datetime,
    *,
    wait_seconds: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[dict[str, list[dict[str, str]]], bool]:
    """Run the queries side by side; what each returned, and whether all finished in time."""
    client = _client("logs")
    deadline = clock() + (LOGS_WAIT_SECONDS if wait_seconds is None else wait_seconds)
    started: dict[str, str] = {}
    for name, text in queries.items():
        response = client.start_query(
            logGroupName=API_LOG_GROUP,
            startTime=int(start.timestamp()),
            endTime=int(end.timestamp()),
            queryString=text,
            limit=100,
        )
        started[name] = response["queryId"]
    results: dict[str, list[dict[str, str]]] = {name: [] for name in queries}
    pending = dict(started)
    while pending:
        for name, query_id in list(pending.items()):
            response = client.get_query_results(queryId=query_id)
            results[name] = [
                {field["field"]: field.get("value", "") for field in row}
                for row in response.get("results", [])
            ]
            if response.get("status") in ("Complete", "Failed", "Cancelled", "Timeout", "Unknown"):
                pending.pop(name)
        if not pending:
            break
        if clock() + LOGS_POLL_SECONDS > deadline:
            for query_id in pending.values():
                try:
                    client.stop_query(queryId=query_id)
                except Exception:
                    logger.info("system_health_stop_query_failed")
            return results, False
        sleep(LOGS_POLL_SECONDS)
    return results, True


def _frontend_errors(feature: str, now: datetime) -> list[dict[str, Any]]:
    target = analytics_store.table()
    if target is None:
        return []
    grouped: dict[str, dict[str, Any]] = {}
    for day in (now.date(), now.date() - timedelta(days=1)):
        for page in islice(
            db_table.pages(
                "query",
                table=target,
                KeyConditionExpression=Key("PK").eq(f"DAY#{day.isoformat()}"),
                FilterExpression="#n = :n",
                ExpressionAttributeNames={"#n": "name"},
                ExpressionAttributeValues={":n": "frontend_error"},
            ),
            FRONTEND_PAGE_BUDGET,
        ):
            for row in page.items:
                props = row.get("props") if isinstance(row.get("props"), Mapping) else {}
                route = str(props.get("route") or row.get("route") or "")
                if features.feature_for_frontend_route(route) != feature:
                    continue
                digest = str(props.get("message_hash") or "")
                at = str(row.get("SK", "")).rsplit("#", 1)[0]
                entry = grouped.setdefault(
                    digest,
                    {"messageHash": digest, "message": None, "route": None, "release": None, "count": 0, "lastAt": None},
                )
                entry["count"] += 1
                if entry["lastAt"] is None or at > entry["lastAt"]:
                    entry.update(
                        lastAt=at,
                        message=props.get("message"),
                        route=route,
                        release=props.get("release") or row.get("release"),
                    )
            if page.last_key is None:
                break
    for entry in grouped.values():
        entry["lastAt"] = _iso_or_none(entry["lastAt"])
    return sorted(grouped.values(), key=lambda entry: (-entry["count"], entry["messageHash"]))[:50]


def feature_detail(
    feature: str,
    window: str,
    *,
    now: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    return _cached(
        ("detail", feature, window),
        DETAIL_CACHE_SECONDS,
        lambda: _feature_detail(feature, window, now, sleep, clock),
    )


def _feature_detail(
    feature: str,
    window: str,
    now: datetime | None,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> dict[str, Any]:
    overview = health(window, now=now)
    moment = (now or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
    seconds, _spark, period = WINDOWS[window]
    start = moment - timedelta(seconds=seconds)
    partial = bool(overview.get("partial"))
    item = next(entry for entry in overview["features"] if entry["key"] == feature)

    ns = request_metrics.FEATURE_NAMESPACE
    buckets = _buckets(moment, seconds, period)
    try:
        points = metric_data(
            [
                _metric_query("req", ns, "Requests", feature, "Sum", period),
                _metric_query("err", ns, "Errors5xx", feature, "Sum", period),
                _metric_query("p50", ns, "Latency", feature, "p50", period),
                _metric_query("p95", ns, "Latency", feature, "p95", period),
            ],
            start,
            moment,
        )
        columns = {
            name: _bucketed(points[name], buckets, period, max if name.startswith("p") else lambda a, b: a + b)
            for name in ("req", "err", "p50", "p95")
        }
        series = [
            {
                "t": iso(bucket),
                "requests": int(columns["req"][index] or 0),
                "errors": int(columns["err"][index] or 0),
                "p50Ms": None if columns["p50"][index] is None else int(round(columns["p50"][index])),
                "p95Ms": None if columns["p95"][index] is None else int(round(columns["p95"][index])),
            }
            for index, bucket in enumerate(buckets)
        ]
    except Exception as error:
        logger.warning("feature_detail_metrics_failed error=%s", type(error).__name__)
        series, partial = [], True

    routes: list[dict[str, Any]] = []
    recent: list[dict[str, Any]] = []
    try:
        found, finished = logs_insights(
            {"routes": _routes_query(feature), "errors": _errors_query(feature)},
            start,
            moment,
            sleep=sleep,
            clock=clock,
        )
        partial = partial or not finished
        for row in found["routes"]:
            requests = _number(row.get("requests")) or 0
            errors = _number(row.get("errors")) or 0
            p50, p95 = _number(row.get("p50")), _number(row.get("p95"))
            routes.append(
                {
                    "method": row.get("method") or "",
                    "route": row.get("route") or "",
                    "requests": int(requests),
                    "errorRate": round(errors / requests, 4) if requests else 0,
                    "p50Ms": None if p50 is None else int(round(p50)),
                    "p95Ms": None if p95 is None else int(round(p95)),
                }
            )
        routes.sort(key=lambda route: -(route["p95Ms"] or 0))
        for row in found["errors"]:
            status = _number(row.get("status"))
            recent.append(
                {
                    "at": _iso_or_none(row.get("at")),
                    "method": row.get("method") or "",
                    "route": row.get("route") or "",
                    "status": None if status is None else int(status),
                    "count": int(_number(row.get("count")) or 0),
                }
            )
    except Exception as error:
        logger.warning("feature_detail_logs_failed error=%s", type(error).__name__)
        partial = True

    try:
        frontend = _frontend_errors(feature, moment)
    except Exception as error:
        logger.warning("feature_detail_frontend_failed error=%s", type(error).__name__)
        frontend, partial = [], True
    try:
        probes = [
            {
                "at": _iso_or_none(row.get("at")),
                "ok": bool(row.get("ok")),
                "latencyMs": int(_number(row.get("latency_ms")) or 0),
                "step": row.get("step"),
            }
            for row in probe_rows(moment)
            if row.get("feature") == feature
            and (_parse_time(row.get("at")) or moment) >= start
        ][:200]
    except Exception as error:
        logger.warning("feature_detail_probes_failed error=%s", type(error).__name__)
        probes, partial = [], True
    try:
        usage = usage_stats.feature_usage(feature, 7 if window == "7d" else 1, now=moment)
    except Exception as error:
        logger.warning("feature_detail_usage_failed error=%s", type(error).__name__)
        usage, partial = [], True

    result: dict[str, Any] = {
        "generatedAt": iso(moment),
        "window": window,
        "feature": item,
        "series": series,
        "routes": routes,
        "recentErrors": recent,
        "frontendErrors": frontend,
        "probes": probes,
        "alarms": [alarm for alarm in overview["alarms"] if alarm["feature"] == feature],
        "usage": usage,
    }
    if partial:
        result["partial"] = True
    return result
