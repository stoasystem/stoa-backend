"""What one HTTP request reads from the table, in capacity units (#610).

CloudWatch says what the table was charged per hour, not which endpoint was
reading. With `DYNAMODB_READ_METERING=true` every read a request makes through
the gateway's table and client asks DynamoDB what it cost
(`ReturnConsumedCapacity=TOTAL`), and the request ends with one log line:

    event_category=dynamodb_read_metering route=/practice/knowledge-map/stars
    method=GET status=200 rcu=1840.5 read_calls=14 wall_ms=1612 query_calls=12
    query_rcu=1838.5 scan_calls=0 scan_rcu=0 get_item_calls=2 get_item_rcu=2 ...

Two halves:

- `attach(client)` hooks a boto3 client's own events, so a read is counted
  however it was made: through `db_table.pages`, or by a repository calling
  `table.query(...)` itself. The gateway attaches it when it builds the real
  table and client, and only while the switch is on.
- `ReadMeteringMiddleware` opens a meter for the length of a request and writes
  the line. The hooks do nothing outside a request it opened, so a job or an
  operator call sends exactly what it sent before.

The line names the route's template, never the path that was asked for, and
holds numbers besides: no ids, no keys, nothing a row contains. With the switch
off no hook is registered, no parameter is added and no line is written.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from stoa import config

logger = logging.getLogger(__name__)

# The operations that read, as botocore names them. Writes are left alone.
READ_OPERATIONS = ("Query", "Scan", "GetItem", "BatchGetItem", "TransactGetItems")
_LABELS = {
    "Query": "query",
    "Scan": "scan",
    "GetItem": "get_item",
    "BatchGetItem": "batch_get_item",
    "TransactGetItems": "transact_get_items",
}
_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


class ReadMeter:
    """The reads of one request: calls and capacity units per operation.

    A synchronous route runs on a worker thread with a copy of the request's
    context, so the meter is one shared object and guards its own counts.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls = dict.fromkeys(READ_OPERATIONS, 0)
        self._units = dict.fromkeys(READ_OPERATIONS, 0.0)

    def add(self, operation: str, units: float) -> None:
        if operation not in self._calls:
            return
        with self._lock:
            self._calls[operation] += 1
            self._units[operation] += units

    def calls(self, operation: str) -> int:
        return self._calls[operation]

    def units(self, operation: str) -> float:
        return self._units[operation]

    @property
    def total_calls(self) -> int:
        return sum(self._calls.values())

    @property
    def total_units(self) -> float:
        return sum(self._units.values())


_meter: ContextVar[ReadMeter | None] = ContextVar("stoa_read_meter", default=None)


@contextmanager
def measuring() -> Iterator[ReadMeter]:
    """A meter that every hooked read made inside the block reports to."""
    meter = ReadMeter()
    token = _meter.set(meter)
    try:
        yield meter
    finally:
        _meter.reset(token)


# -- the client's side ------------------------------------------------------------------


def attach(client: Any) -> None:
    """Hook `client` so its reads report what they consumed to the current meter."""
    events = client.meta.events
    for operation in READ_OPERATIONS:
        events.register(f"provide-client-params.dynamodb.{operation}", _ask_for_capacity)
        events.register(f"after-call.dynamodb.{operation}", _record_capacity)


def _ask_for_capacity(params: Any = None, **_event: object) -> None:
    """Add `ReturnConsumedCapacity` to a read, unless the caller chose its own."""
    if _meter.get() is None or not isinstance(params, dict):
        return
    params.setdefault("ReturnConsumedCapacity", "TOTAL")


def _record_capacity(parsed: Any = None, model: Any = None, **_event: object) -> None:
    """Count one answered read. A measurement never fails the read it measures."""
    meter = _meter.get()
    if meter is None:
        return
    try:
        consumed = parsed.get("ConsumedCapacity") if isinstance(parsed, Mapping) else None
        meter.add(str(getattr(model, "name", "")), consumed_units(consumed))
    except Exception:  # noqa: BLE001 - the read itself succeeded
        logger.warning("dynamodb_read_metering_unreadable")


def consumed_units(consumed: object) -> float:
    """The capacity units in a response's `ConsumedCapacity`.

    One mapping for a single read, a list (one per table) for a batch or a
    transaction, absent when the read failed or was not asked.
    """
    if isinstance(consumed, Mapping):
        units = consumed.get("CapacityUnits")
        if isinstance(units, (int, float)) and not isinstance(units, bool):
            return float(units)
        return 0.0
    if isinstance(consumed, (list, tuple)):
        return sum(consumed_units(entry) for entry in consumed)
    return 0.0


# -- the request's side -----------------------------------------------------------------


class ReadMeteringMiddleware:
    """Measure the table reads of each HTTP request, while the switch is on.

    Plain ASGI for the same reasons as the application's other middleware: the
    meter set here has to be the one the endpoint's reads find.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not config.settings().dynamodb_read_metering:
            await self.app(scope, receive, send)
            return
        status = 500
        started = time.perf_counter()

        async def send_noting_status(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        with measuring() as meter:
            try:
                await self.app(scope, receive, send_noting_status)
            finally:
                _log(scope, status, meter, time.perf_counter() - started)


def _log(scope: Mapping[str, Any], status: int, meter: ReadMeter, seconds: float) -> None:
    fields = [
        "event_category=dynamodb_read_metering",
        f"route={_route_template(scope)}",
        f"method={_method(scope)}",
        f"status={status}",
        f"rcu={_number(meter.total_units)}",
        f"read_calls={meter.total_calls}",
        f"wall_ms={max(0, round(seconds * 1000))}",
    ]
    for operation in READ_OPERATIONS:
        label = _LABELS[operation]
        fields.append(f"{label}_calls={meter.calls(operation)}")
        fields.append(f"{label}_rcu={_number(meter.units(operation))}")
    logger.info(" ".join(fields))


def _route_template(scope: Mapping[str, Any]) -> str:
    """The matched route as it was declared (`/students/{student_id}`).

    The router puts the route in the scope once it has matched. A request that
    matched nothing is `unmatched`: its path is whatever the caller typed.
    """
    path = getattr(scope.get("route"), "path", None)
    return path if isinstance(path, str) and path else "unmatched"


def _method(scope: Mapping[str, Any]) -> str:
    method = str(scope.get("method") or "").upper()
    return method if method in _METHODS else "other"


def _number(value: float) -> str:
    """Capacity units without float noise: `12`, `0.5`, `1840.5`."""
    return f"{value:.2f}".rstrip("0").rstrip(".")
