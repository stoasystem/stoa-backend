"""One CloudWatch Embedded Metric Format line per HTTP request (card 134).

Lambda hands every stdout line that is a JSON object with an `_aws` key to
CloudWatch as metrics, with no agent and no API call. The line names the
feature (`features.feature_for_route`) as its only dimension, and carries the
route's template, the method, the status and the release as plain properties:
no user, no path parameter, no query string.

Off with `REQUEST_METRICS=false`. A failure to write the line never touches the
response.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Mapping
from typing import Any

from stoa import config
from stoa.observability import features

logger = logging.getLogger(__name__)

FEATURE_NAMESPACE = "Stoa/Features"
FRONTEND_NAMESPACE = "Stoa/Frontend"
_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


def emf_line(
    namespace: str,
    metrics: Mapping[str, tuple[float, str]],
    *,
    feature: str,
    properties: Mapping[str, Any],
    now_ms: int | None = None,
) -> str:
    """The EMF JSON for one set of metrics under the `Feature` dimension."""
    document: dict[str, Any] = {
        "_aws": {
            "Timestamp": now_ms if now_ms is not None else int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [["Feature"]],
                    "Metrics": [
                        {"Name": name, "Unit": unit} for name, (_value, unit) in metrics.items()
                    ],
                }
            ],
        },
        "Feature": feature,
    }
    for name, (value, _unit) in metrics.items():
        document[name] = value
    for key, value in properties.items():
        document.setdefault(key, value)
    return json.dumps(document, separators=(",", ":"), ensure_ascii=True)


def write_line(line: str) -> None:
    """Write one line straight to stdout, apart from the logging format."""
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def release() -> str:
    return config.settings().stoa_release_id.strip()


def route_template(scope: Mapping[str, Any]) -> str:
    path = getattr(scope.get("route"), "path", None)
    return path if isinstance(path, str) and path else "unmatched"


def _method(scope: Mapping[str, Any]) -> str:
    method = str(scope.get("method") or "").upper()
    return method if method in _METHODS else "other"


def request_line(
    *, method: str, route: str, status: int, latency_ms: float, now_ms: int | None = None
) -> str:
    feature = features.OTHER if route == "unmatched" else features.feature_for_route(method, route)
    return emf_line(
        FEATURE_NAMESPACE,
        {
            "Requests": (1, "Count"),
            "Errors5xx": (1 if status >= 500 else 0, "Count"),
            "Latency": (round(latency_ms, 1), "Milliseconds"),
        },
        feature=feature,
        properties={"route": route, "method": method, "status": status, "release": release()},
        now_ms=now_ms,
    )


class RequestMetricsMiddleware:
    """Time each HTTP request and write its EMF line once it has been answered.

    Plain ASGI like the application's other middleware; the router has put the
    matched route in the scope by the time the endpoint returns.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not config.settings().request_metrics:
            await self.app(scope, receive, send)
            return
        status = 500
        started = time.perf_counter()

        async def send_noting_status(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_noting_status)
        finally:
            try:
                write_line(
                    request_line(
                        method=_method(scope),
                        route=route_template(scope),
                        status=status,
                        latency_ms=(time.perf_counter() - started) * 1000,
                    )
                )
            except Exception:
                logger.warning("request_metrics_line_failed", exc_info=True)
