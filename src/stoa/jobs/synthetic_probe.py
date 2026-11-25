"""Synthetic probe: sign in as the probe student and walk the read-only paths (card 134).

Every few minutes on a schedule. Only the routes in `ALLOWED_REQUESTS` are
ever requested: nothing that asks the model, nothing that writes, apart from
what signing in itself records. Each step becomes one `PROBE#<day>` row in the
statistics table and one EMF line (`Stoa/Probes`, by `Feature`).
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from stoa import config
from stoa.observability import analytics_store, request_metrics

logger = logging.getLogger(__name__)

PROBE_NAMESPACE = "Stoa/Probes"
PROBE_TTL = timedelta(days=30)
TIMEOUT_SECONDS = 10.0

# (status, body) for (method, url, headers, body, timeout).
Transport = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, bytes]]


class Step(NamedTuple):
    feature: str
    step: str
    method: str
    path: str


LOGIN = Step("auth", "login", "POST", "/auth/login")
STEPS: tuple[Step, ...] = (
    Step("auth", "me", "GET", "/auth/me"),
    Step("practice", "stars", "GET", "/practice/knowledge-map/stars"),
    Step("practice", "catalog", "GET", "/practice/curriculum/catalog"),
    Step("notifications", "list", "GET", "/notifications"),
    Step("ask_ai", "conversations", "GET", "/conversations"),
    Step("teacher_help", "availability", "GET", "/teacher-help/availability"),
)
ALLOWED_REQUESTS = frozenset((step.method, step.path) for step in (LOGIN, *STEPS))


class RequestNotAllowed(RuntimeError):
    pass


def urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read() or b""


def _guarded(transport: Transport, base_url: str) -> Transport:
    def send(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float):
        path = urlsplit(url).path
        if (method, path) not in ALLOWED_REQUESTS or not url.startswith(base_url):
            raise RequestNotAllowed(f"{method} {path}")
        return transport(method, url, headers, body, timeout)

    return send


def _attempt(send: Transport, url: str, step: Step, headers: dict[str, str], body: bytes | None):
    started = time.perf_counter()
    try:
        status, payload = send(step.method, url, headers, body, TIMEOUT_SECONDS)
    except RequestNotAllowed:
        raise
    except Exception as error:
        logger.warning("probe_step_failed step=%s error=%s", step.step, type(error).__name__)
        status, payload = 0, b""
    return status, payload, int(round((time.perf_counter() - started) * 1000))


def run(
    *,
    transport: Transport | None = None,
    now: datetime | None = None,
    write_line: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    settings = config.settings()
    email, password = settings.stoa_probe_email.strip(), settings.stoa_probe_password
    if not email or not password:
        logger.info("synthetic_probe_skipped reason=credentials_not_configured")
        return {"status": "skipped", "reason": "credentials_not_configured"}
    base = settings.stoa_probe_base_url.rstrip("/")
    send = _guarded(transport or urllib_transport, base)
    emit = write_line or request_metrics.write_line
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    results: list[dict[str, Any]] = []

    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "stoa-synthetic-probe"}
    body = json.dumps({"email": email, "password": password}).encode("utf-8")
    status, payload, latency = _attempt(send, base + LOGIN.path, LOGIN, headers, body)
    token = None
    if 200 <= status < 300:
        try:
            token = json.loads(payload.decode("utf-8")).get("accessToken")
        except (ValueError, AttributeError):
            token = None
    results.append({"step": LOGIN, "ok": bool(token), "status": status, "latency_ms": latency})

    if token:
        auth = {"Accept": "application/json", "Authorization": f"Bearer {token}", "User-Agent": "stoa-synthetic-probe"}
        for step in STEPS:
            status, _payload, latency = _attempt(send, base + step.path, step, auth, None)
            results.append({"step": step, "ok": 200 <= status < 300, "status": status, "latency_ms": latency})

    _record(results, moment, emit)
    failed = [result["step"].step for result in results if not result["ok"]]
    logger.info("synthetic_probe_done steps=%s failed=%s", len(results), ",".join(failed) or "-")
    return {"status": "completed", "steps": len(results), "failed": failed}


def _record(results: list[dict[str, Any]], moment: datetime, emit: Callable[[str], None]) -> None:
    at = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    day = moment.date().isoformat()
    ttl = int(moment.timestamp() + PROBE_TTL.total_seconds())
    target = analytics_store.table()
    for result in results:
        step: Step = result["step"]
        try:
            emit(
                request_metrics.emf_line(
                    PROBE_NAMESPACE,
                    {
                        "ProbeSuccess": (1 if result["ok"] else 0, "Count"),
                        "ProbeLatency": (result["latency_ms"], "Milliseconds"),
                    },
                    feature=step.feature,
                    properties={"step": step.step, "status": result["status"]},
                    now_ms=int(moment.timestamp() * 1000),
                )
            )
        except Exception:
            logger.warning("probe_metric_failed", exc_info=True)
        if target is None:
            continue
        try:
            target.put_item(
                Item={
                    "PK": f"PROBE#{day}",
                    "SK": f"{at}#{step.feature}#{step.step}",
                    "at": at,
                    "feature": step.feature,
                    "step": step.step,
                    "ok": result["ok"],
                    "status": result["status"],
                    "latency_ms": result["latency_ms"],
                    "ttl": ttl,
                }
            )
        except Exception as error:
            logger.warning("probe_row_failed error=%s", type(error).__name__)


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Lambda handler for the scheduled synthetic probe."""
    return run()
