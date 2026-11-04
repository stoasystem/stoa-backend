"""每周计数: one row of counts per scope and Zurich week, written under a version.

The weekly AI token allowance (`allowance_repo`) and the weekly count of
teacher-help cases (`teacher_support_allowance_service`) each keep such a row.
What a row is — its key, its shape, how it is read back and how it is written
so that two writers cannot both win — is this module's; what the counts mean,
and every other row a caller writes beside the counter, stay the caller's.

- `zurich_week(observed_at)` is the week an instant falls in: Monday 00:00 to
  Monday 00:00 in Europe/Zurich, named by its ISO week (`ZurichWeek.identity`).
- A `CounterKind` names one kind of counter: its partition prefix, entity type,
  schema version, the field that holds the scope id, and its count fields.
- `read` and `validate` give a `Counter` back, or say the row is damaged.
- `write` returns the transaction operation that writes the next version; the
  caller commits it with whatever else must commit with it.
- `retry` runs one attempt again while it says it lost a race (`CounterConflict`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, TypeVar

from stoa.models.allowance import MAX_EXACT_COUNT, ZURICH, ZurichWeek

T = TypeVar("T")

DEFAULT_ATTEMPTS = 4


class CounterUnavailable(RuntimeError):
    """The counter could not be read, or the row read back is damaged."""


class CounterConflict(Exception):
    """An attempt lost a race for the counter; read it again and try again."""


@dataclass(frozen=True, slots=True)
class CounterKind:
    """One kind of weekly counter, as its rows are stored."""

    namespace: str
    """The partition prefix: rows live at `{namespace}#{scope id}` / `WEEK#{week}`."""
    entity_type: str
    schema_version: str
    scope_field: str
    """The attribute that repeats the scope id on the row."""
    count_fields: tuple[str, ...]


TOKENS = CounterKind(
    namespace="ALLOWANCE",
    entity_type="allowance_counter",
    schema_version="allowance_counter.v1",
    scope_field="beneficiary_id",
    count_fields=(
        "finalized_input_tokens",
        "finalized_output_tokens",
        "reserved_input_tokens",
        "reserved_output_tokens",
        "provider_cost_input_tokens",
        "provider_cost_output_tokens",
    ),
)
"""The weekly AI token allowance, one row per student."""

CASES = CounterKind(
    namespace="TEACHER_SUPPORT",
    entity_type="teacher_support_counter",
    schema_version="teacher_support_counter.v1",
    scope_field="support_scope_id",
    count_fields=("admitted_cases",),
)
"""The weekly count of teacher-help cases, one row per support scope."""


@dataclass(frozen=True, slots=True)
class Counter:
    """A counter row as read back: its counts and version are whole numbers."""

    item: dict[str, object]
    state_version: int

    def count(self, field: str) -> int:
        value = self.item[field]
        assert isinstance(value, int)
        return value


# ── The week ──────────────────────────────────────────────────────────────────


def zurich_week(observed_at: datetime | None = None) -> ZurichWeek:
    """The Zurich calendar week `observed_at` falls in, from local Monday dates."""
    observed = observed_at or datetime.now(timezone.utc)
    if not isinstance(observed, datetime) or observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    local = observed.astimezone(ZURICH)
    monday = local.date() - timedelta(days=local.weekday())
    next_monday = monday + timedelta(days=7)
    local_start = datetime.combine(monday, time.min, tzinfo=ZURICH)
    local_end = datetime.combine(next_monday, time.min, tzinfo=ZURICH)
    iso = monday.isocalendar()
    return ZurichWeek(
        isoYear=iso.year,
        isoWeek=iso.week,
        windowStart=local_start.astimezone(timezone.utc),
        windowEnd=local_end.astimezone(timezone.utc),
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


# ── Reading ───────────────────────────────────────────────────────────────────


def key(kind: CounterKind, scope_id: str, week: ZurichWeek) -> dict[str, str]:
    """Where `scope_id`'s counter for `week` is kept."""
    return {"PK": f"{kind.namespace}#{scope_id}", "SK": f"WEEK#{week.identity}"}


def read(
    kind: CounterKind, scope_id: str, week: ZurichWeek, *, table: object
) -> Counter | None:
    """The counter for `scope_id` and `week`, read strongly; None when there is none.

    Raises `CounterUnavailable` when the table cannot be read or the row is damaged.
    """
    getter = getattr(table, "get_item", None)
    if not callable(getter):
        raise CounterUnavailable("counter persistence is unavailable")
    try:
        response = getter(Key=key(kind, scope_id, week), ConsistentRead=True)
    except Exception:
        raise CounterUnavailable("counter persistence is unavailable") from None
    if not isinstance(response, Mapping):
        raise CounterUnavailable("counter persistence returned malformed data")
    item = response.get("Item")
    if item is None:
        return None
    return validate(kind, item, scope_id=scope_id, week=week)


def validate(
    kind: CounterKind, item: object, *, scope_id: str, week: ZurichWeek
) -> Counter:
    """Check the parts of a counter row every kind shares.

    The key, entity type, schema version, scope id, week and its window must be
    exactly this counter's; every count and the version must be whole numbers
    in range. `created_at` is not required: rows written before it was kept on
    every write do not have it. Fields of the caller's own are the caller's to
    check. Raises `CounterUnavailable`.
    """
    if not isinstance(item, Mapping) or any(not isinstance(name, str) for name in item):
        raise CounterUnavailable("malformed counter")
    expected_key = key(kind, scope_id, week)
    if (
        item.get("PK") != expected_key["PK"]
        or item.get("SK") != expected_key["SK"]
        or item.get("entity_type") != kind.entity_type
        or item.get("schema_version") != kind.schema_version
        or item.get(kind.scope_field) != scope_id
        or item.get("week_identity") != week.identity
        or item.get("window_start") != _timestamp(week.window_start)
        or item.get("window_end") != _timestamp(week.window_end)
    ):
        raise CounterUnavailable("malformed counter")
    normalized = {str(name): value for name, value in item.items()}
    for field in kind.count_fields:
        normalized[field] = _whole(item.get(field), field)
    state_version = _whole(item.get("state_version"), "state_version", positive=True)
    normalized["state_version"] = state_version
    return Counter(item=normalized, state_version=state_version)


def _whole(value: object, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool):
        raise CounterUnavailable(f"malformed {field}")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        parsed = int(value)
    else:
        raise CounterUnavailable(f"malformed {field}")
    if not (1 if positive else 0) <= parsed <= MAX_EXACT_COUNT:
        raise CounterUnavailable(f"malformed {field}")
    return parsed


# ── Writing ───────────────────────────────────────────────────────────────────


def write(
    kind: CounterKind,
    scope_id: str,
    week: ZurichWeek,
    previous: Counter | None,
    *,
    counts: Mapping[str, int],
    fields: Mapping[str, object] | None = None,
    at: datetime,
) -> dict[str, Any]:
    """The transaction operation that writes the counter's next version.

    With no `previous` it creates the row (and only if none exists), with every
    count not given at 0 and `created_at` set; otherwise it replaces `previous`
    (and only if its version is still the stored one), keeping its
    `created_at` as it is, or absent. `counts` are the new values, `fields` the
    caller's own attributes. The version goes up by one either way.
    """
    unknown = set(counts) - set(kind.count_fields)
    if unknown:
        raise ValueError(f"not counts of {kind.entity_type}: {sorted(unknown)}")
    for field, value in counts.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_EXACT_COUNT:
            raise ValueError(f"{field} is out of range")
    reserved = {*key(kind, scope_id, week), "entity_type", "schema_version", kind.scope_field,
                "week_identity", "window_start", "window_end", "state_version",
                "created_at", "updated_at", *kind.count_fields}
    clash = set(fields or {}) & reserved
    if clash:
        raise ValueError(f"fields may not set {sorted(clash)}")
    now = _timestamp(at)
    if previous is None:
        item: dict[str, object] = {
            **key(kind, scope_id, week),
            "entity_type": kind.entity_type,
            "schema_version": kind.schema_version,
            kind.scope_field: scope_id,
            "week_identity": week.identity,
            "window_start": _timestamp(week.window_start),
            "window_end": _timestamp(week.window_end),
            **{field: 0 for field in kind.count_fields},
            "created_at": now,
        }
        condition: dict[str, object] = {
            "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
        }
        next_version = 1
    else:
        item = dict(previous.item)
        condition = {
            "ConditionExpression": "state_version=:expected_state_version",
            "ExpressionAttributeValues": {":expected_state_version": previous.state_version},
        }
        next_version = previous.state_version + 1
    item.update(fields or {})
    item.update(counts)
    item["state_version"] = next_version
    item["updated_at"] = now
    return {"Put": {"Item": item, **condition}}


# ── Retrying ──────────────────────────────────────────────────────────────────


def retry(
    attempt: Callable[[], T], *, exhausted: T, attempts: int = DEFAULT_ATTEMPTS
) -> T:
    """Run `attempt` until it returns, at most `attempts` times.

    An attempt that raises `CounterConflict` lost a race: it is run again,
    reading the counter afresh. After the last one, `exhausted` is returned.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    for _ in range(attempts):
        try:
            return attempt()
        except CounterConflict:
            continue
    return exhausted
