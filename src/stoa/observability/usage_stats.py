"""Daily rollups of the statistics table and the usage overview read from them (card 134).

A rollup folds one UTC day of raw events into `PK=ROLLUP#<day>` rows:

- `SK=<event>#<role>`: `count`, `unique` (distinct pid or sid), `pids`, and for
  timed events `values` (the timing prop), for `page_viewed` `by_feature`.
- `SK=_active#<role>`: the pseudonyms active that day.
- `SK=_first#<role>`: the pseudonyms first seen that day.
- `SK=_meta`: written last; a day without it has no complete rollup.

Rewriting a day replaces its rows, so the job can be run again for any day.
"""

from __future__ import annotations

import logging
import statistics
import threading
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import islice
from typing import Any

from boto3.dynamodb.conditions import Key

from stoa.db import table as db_table
from stoa.observability import analytics_store, cost_reader, features

logger = logging.getLogger(__name__)

ROLLUP_TTL = timedelta(days=400)
META = "_meta"
ACTIVE = "_active"
FIRST = "_first"
MAX_PIDS = 5000
MAX_VALUES = 5000
DAY_PAGE_BUDGET = 200
# The timing prop kept per event, for medians across days.
VALUE_PROPS = {"ai_answered": "latency_ms", "teacher_replied": "response_ms"}
ROLES = ("student", "parent", "teacher", "admin", analytics_store.ANONYMOUS)
FILTER_ROLES = ("all", "student", "parent", "teacher")
OVERVIEW_DAYS = (7, 30, 90)
NOT_RANKED = frozenset({"frontend_error", "web_vitals"})

# Account profiles in GSI-Listing; the listing is written by card 133-B1.
ACCOUNT_PROFILE_LISTING = "account_profile"
LISTING_INDEX = "GSI-Listing"
_LISTING_KEY = ("PK", "SK", "listing", "listed_at")
PROFILE_PAGE_BUDGET = 50

# The feature an event counts under on the feature detail page.
EVENT_FEATURES: Mapping[str, str] = {
    "user_login": "auth",
    "user_register": "auth",
    "login_submitted": "auth",
    "login_authenticated": "auth",
    "login_first_screen_ready": "auth",
    "chat_conversation_created": "ask_ai",
    "chat_message_sent": "ask_ai",
    "chat_response_started": "ask_ai",
    "chat_response_completed": "ask_ai",
    "chat_response_stopped": "ask_ai",
    "file_uploaded": "ask_ai",
    "question_asked": "ask_ai",
    "ai_answered": "ask_ai",
    "teacher_help_requested": "teacher_help",
    "teacher_help_request_failed": "teacher_help",
    "teacher_help_assigned": "teacher_help",
    "teacher_help_resolved": "teacher_help",
    "help_escalated": "teacher_help",
    "teacher_replied": "teacher_help",
    "teacher_availability_viewed": "teacher_help",
    "teacher_availability_updated": "teacher_help",
    "teacher_request_opened": "teacher_help",
    "teacher_request_status_updated": "teacher_help",
    "exercise_answered": "practice",
    "curriculum_graph_viewed": "practice",
    "curriculum_topic_selected": "practice",
    "weak_point_diagnosis_viewed": "practice",
    "learning_profile_viewed": "practice",
    "parent_child_summary_viewed": "parent_reports",
    "parent_report_viewed": "parent_reports",
    "parent_monthly_report_viewed": "parent_reports",
    "admin_analytics_viewed": "admin",
}


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    return None


def _int(value: Any) -> int:
    number = _num(value)
    return int(number) if number is not None else 0


def _partition(target: Any, pk: str, *, budget: int = DAY_PAGE_BUDGET) -> tuple[list[dict], bool]:
    rows: list[dict[str, Any]] = []
    for page in islice(
        db_table.pages("query", table=target, KeyConditionExpression=Key("PK").eq(pk)), budget
    ):
        rows.extend(page.items)
        if page.last_key is None:
            return rows, True
    return rows, False


def _iso_day(day: date | str) -> str:
    return day if isinstance(day, str) else day.isoformat()


# -- fold ------------------------------------------------------------------------


def fold_day(
    day: date | str, *, target: Any, with_first: bool = True
) -> tuple[list[dict[str, Any]], bool]:
    """The rollup rows of one day, from its raw events; and whether every page was read.

    `with_first=False` skips the per-pseudonym first-seen reads (one get each).
    """
    day = _iso_day(day)
    events, events_complete = _partition(target, f"DAY#{day}")
    actives, actives_complete = _partition(target, f"ACTIVE#{day}")
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in events:
        name = str(row.get("name") or "")
        if not name:
            continue
        role = str(row.get("role") or analytics_store.ANONYMOUS)
        group = groups.setdefault(
            (name, role), {"count": 0, "ids": set(), "pids": set(), "values": [], "by_feature": {}}
        )
        group["count"] += 1
        pid, sid = row.get("pid"), row.get("sid")
        if pid:
            group["pids"].add(str(pid))
            group["ids"].add(f"p:{pid}")
        elif sid:
            group["ids"].add(f"s:{sid}")
        props = row.get("props") if isinstance(row.get("props"), Mapping) else {}
        value_prop = VALUE_PROPS.get(name)
        if value_prop is not None:
            value = _num(props.get(value_prop))
            if value is not None and len(group["values"]) < MAX_VALUES:
                group["values"].append(value)
        if name == "page_viewed":
            feature = features.feature_for_frontend_route(
                str(props.get("route") or row.get("route") or "")
            )
            group["by_feature"][feature] = group["by_feature"].get(feature, 0) + 1

    active_by_role: dict[str, set[str]] = {}
    for row in actives:
        role = str(row.get("role") or str(row.get("SK", "")).split("#", 1)[0])
        pid = row.get("pid") or str(row.get("SK", "")).split("#", 1)[-1]
        if pid:
            active_by_role.setdefault(role, set()).add(str(pid))
    every_pid = sorted(set().union(*active_by_role.values())) if active_by_role and with_first else []
    firsts = db_table.get_many(
        ({"PK": f"FIRST#{pid}", "SK": "FIRST"} for pid in every_pid), table=target
    )
    first_by_role: dict[str, set[str]] = {}
    for (pk, _sk), row in firsts.items():
        if row.get("first_day") == day:
            first_by_role.setdefault(str(row.get("first_role") or "student"), set()).add(
                pk.split("#", 1)[1]
            )

    rows: list[dict[str, Any]] = []
    for (name, role), group in sorted(groups.items()):
        row: dict[str, Any] = {
            "SK": f"{name}#{role}",
            "event": name,
            "role": role,
            "count": group["count"],
            "unique": len(group["ids"]),
            "pids": sorted(group["pids"])[:MAX_PIDS],
        }
        if name in VALUE_PROPS:
            row["values"] = [Decimal(str(round(value, 1))) for value in group["values"]]
        if group["by_feature"]:
            row["by_feature"] = dict(group["by_feature"])
        rows.append(row)
    for marker, by_role in ((ACTIVE, active_by_role), (FIRST, first_by_role)):
        for role, pids in sorted(by_role.items()):
            rows.append(
                {
                    "SK": f"{marker}#{role}",
                    "role": role,
                    "count": len(pids),
                    "pids": sorted(pids)[:MAX_PIDS],
                }
            )
    return rows, events_complete and actives_complete


def write_rollup(
    day: date | str, *, target: Any, now: datetime | None = None
) -> dict[str, Any]:
    """Fold `day` and replace its rollup rows; safe to run again."""
    day = _iso_day(day)
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    rows, complete = fold_day(day, target=target)
    ttl = int(moment.timestamp() + ROLLUP_TTL.total_seconds())
    existing, _ = _partition(target, f"ROLLUP#{day}")
    target.delete_item(Key={"PK": f"ROLLUP#{day}", "SK": META})
    kept = {row["SK"] for row in rows}
    for row in existing:
        if row.get("SK") not in kept and row.get("SK") != META:
            target.delete_item(Key={"PK": row["PK"], "SK": row["SK"]})
    for row in rows:
        target.put_item(Item={"PK": f"ROLLUP#{day}", **row, "ttl": ttl})
    target.put_item(
        Item={
            "PK": f"ROLLUP#{day}",
            "SK": META,
            "computed_at": moment.isoformat(),
            "rows": len(rows),
            "complete": complete,
            "ttl": ttl,
        }
    )
    return {"day": day, "rows": len(rows), "complete": complete}


def rollup_rows(day: date | str, *, target: Any) -> tuple[list[dict[str, Any]], bool]:
    """The stored rollup of a day, or one folded now from raw events (`False`)."""
    day = _iso_day(day)
    stored, _ = _partition(target, f"ROLLUP#{day}")
    if any(row.get("SK") == META for row in stored):
        return [row for row in stored if row.get("SK") != META], True
    rows, _complete = fold_day(day, target=target, with_first=False)
    return rows, False


# -- overview --------------------------------------------------------------------


_cache_lock = threading.Lock()
_cache: dict[Any, tuple[float, Any]] = {}
CACHE_SECONDS = 60.0
COST_CACHE_SECONDS = 6 * 3600.0


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _change(current: float, previous: float) -> float | None:
    return round((current - previous) / previous, 4) if previous else None


def _month_active_users(start: date, end: date) -> int:
    """Distinct pseudonyms in the raw `ACTIVE#<day>` partitions from `start` through `end`."""
    target = analytics_store.table()
    if target is None:
        raise LookupError("no statistics table")
    pids: set[str] = set()
    day = start
    while day <= end:
        rows, _complete = _partition(target, f"ACTIVE#{day.isoformat()}")
        for row in rows:
            pid = row.get("pid") or str(row.get("SK", "")).split("#", 1)[-1]
            if pid:
                pids.add(str(pid))
        day += timedelta(days=1)
    return len(pids)


def cost_per_active_user(moment: datetime) -> dict[str, Any] | None:
    """Month-to-date cost over month-to-date active users; `None` when either read fails."""
    today = moment.astimezone(UTC).date()
    start = today.replace(day=1)
    key = ("cost", start)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < COST_CACHE_SECONDS:
            return hit[1]
    try:
        totals = cost_reader.month_to_date(today)
        users = _month_active_users(start, today)
    except Exception as error:
        logger.warning("analytics_cost_per_active_user_failed error=%s", type(error).__name__)
        return None

    def per_user(amount: float) -> float | None:
        return round(amount / users, 4) if users else None

    total = sum(totals.values())
    result = {
        "amountUsd": per_user(total),
        "totalUsd": round(total, 2),
        "activeUsers": users,
        "periodStart": start.isoformat(),
        "periodEnd": today.isoformat(),
        "breakdown": [
            {"service": service, "amountUsd": per_user(totals[service])}
            for service in cost_reader.SERVICES
        ],
    }
    with _cache_lock:
        _cache[key] = (time.monotonic(), result)
    return result


def _role_ok(role: str, wanted: str) -> bool:
    return wanted == "all" or role == wanted


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _median(values: list[float]) -> int | None:
    return int(round(statistics.median(values))) if values else None


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _profile_funnel(start: date, end: date, role: str) -> tuple[int | None, int | None, bool]:
    """Invited and activated accounts created in [start, end], from GSI-Listing."""
    try:
        invited = activated = 0
        upper = (end + timedelta(days=1)).isoformat()
        for page in islice(
            db_table.pages(
                "query",
                key=_LISTING_KEY,
                IndexName=LISTING_INDEX,
                KeyConditionExpression=Key("listing").eq(ACCOUNT_PROFILE_LISTING)
                & Key("listed_at").between(start.isoformat(), upper),
            ),
            PROFILE_PAGE_BUDGET,
        ):
            for row in page.items:
                if str(row.get("listed_at", "")) >= upper:
                    continue
                if not _role_ok(str(row.get("role") or ""), role):
                    continue
                invited += 1
                if row.get("activated_at") or row.get("account_status") == "active":
                    activated += 1
            if page.last_key is None:
                return invited, activated, True
        return invited, activated, False
    except Exception as error:
        logger.warning("analytics_funnel_profiles_failed error=%s", type(error).__name__)
        return None, None, False


def overview(days: int, role: str, *, now: datetime | None = None) -> dict[str, Any]:
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    key = ("overview", days, role, moment.date())
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    result = _overview(days, role, moment)
    with _cache_lock:
        _cache[key] = (time.monotonic(), result)
    return result


def _overview(days: int, role: str, moment: datetime) -> dict[str, Any]:
    target = analytics_store.table()
    last = moment.date() - timedelta(days=1)
    # Twice the longest window, for the change against the window before it.
    loaded = max(2 * days, 60)
    window = [last - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    span = [last - timedelta(days=offset) for offset in range(loaded - 1, -1, -1)]
    complete = True
    by_day: dict[date, list[dict[str, Any]]] = {}
    if target is not None:
        for day in span:
            rows, stored = rollup_rows(day, target=target)
            by_day[day] = rows
            if not stored and day in window:
                complete = False
    else:
        complete = False

    active: dict[date, set[str]] = {}
    for day in span:
        pids: set[str] = set()
        for row in by_day.get(day, []):
            if str(row.get("SK", "")).startswith(f"{ACTIVE}#") and _role_ok(str(row.get("role")), role):
                pids.update(str(pid) for pid in row.get("pids") or [])
        active[day] = pids

    def union(days_: Iterable[date]) -> set[str]:
        found: set[str] = set()
        for day in days_:
            found |= active.get(day, set())
        return found

    dau = len(active.get(last, set()))
    before = len(active.get(last - timedelta(days=7), set()))
    dau_change = _change(dau, before)
    wau = len(union(last - timedelta(days=offset) for offset in range(7)))
    wau_before = len(union(last - timedelta(days=offset) for offset in range(7, 14)))
    mau = len(union(last - timedelta(days=offset) for offset in range(30)))
    mau_before = len(union(last - timedelta(days=offset) for offset in range(30, 60)))

    counts: dict[str, int] = {}
    uniques: dict[str, set[str]] = {}
    extra: dict[str, int] = {}
    values: dict[str, list[float]] = {}
    cohort: dict[str, date] = {}
    for day in window:
        for row in by_day.get(day, []):
            sk = str(row.get("SK", ""))
            row_role = str(row.get("role") or "")
            if not _role_ok(row_role, role):
                continue
            if sk.startswith(f"{FIRST}#"):
                for pid in row.get("pids") or []:
                    cohort.setdefault(str(pid), day)
                continue
            if sk.startswith("_"):
                continue
            event = str(row.get("event") or sk.split("#", 1)[0])
            pids = [str(pid) for pid in row.get("pids") or []]
            counts[event] = counts.get(event, 0) + _int(row.get("count"))
            uniques.setdefault(event, set()).update(pids)
            extra[event] = extra.get(event, 0) + max(0, _int(row.get("unique")) - len(pids))
            for value in row.get("values") or []:
                number = _num(value)
                if number is not None:
                    values.setdefault(event, []).append(number)

    ranking = sorted(
        (
            {"event": event, "count": count, "uniqueUsers": len(uniques[event]) + extra[event]}
            for event, count in counts.items()
            if event not in NOT_RANKED
        ),
        key=lambda item: (-item["count"], item["event"]),
    )
    questions = counts.get("question_asked", 0)
    questions_before = 0
    for offset in range(days, 2 * days):
        for row in by_day.get(last - timedelta(days=offset), []):
            if row.get("event") == "question_asked" and _role_ok(str(row.get("role") or ""), role):
                questions_before += _int(row.get("count"))
    escalations = counts.get("help_escalated", 0)

    invited, activated, profiles_complete = _profile_funnel(window[0], last, role)
    if not profiles_complete:
        complete = False
    cohort_pids = set(cohort)
    week2 = 0
    for pid, first in cohort.items():
        if any(pid in active.get(first + timedelta(days=offset), set()) for offset in range(7, 14)):
            week2 += 1
    funnel = [
        {"step": "invited", "count": invited},
        {"step": "activated", "count": activated},
        {"step": "first_question", "count": len(cohort_pids & uniques.get("question_asked", set()))},
        {"step": "first_exercise", "count": len(cohort_pids & uniques.get("exercise_answered", set()))},
        {"step": "week2_active", "count": week2},
    ]

    cohorts: dict[date, set[str]] = {}
    for pid, first in cohort.items():
        cohorts.setdefault(_monday(first), set()).add(pid)
    retention = []
    for week_start in sorted(cohorts):
        members = cohorts[week_start]
        weeks: list[float | None] = []
        for k in range(5):
            start = week_start + timedelta(days=7 * k)
            if start > last:
                weeks.append(None)
                continue
            seen = union(start + timedelta(days=offset) for offset in range(7))
            weeks.append(round(len(members & seen) / len(members), 4))
        retention.append({"cohortWeek": week_start.isoformat(), "size": len(members), "weeks": weeks})

    return {
        "generatedAt": _iso(moment),
        "days": days,
        "role": role,
        "complete": complete,
        "kpis": {
            "dau": dau,
            "wau": wau,
            "mau": mau,
            "dauChange": dau_change,
            "questionsPerDay": round(questions / days, 2),
            "escalationRate": round(escalations / questions, 4) if questions else None,
            "aiP50Ms": _median(values.get("ai_answered", [])),
            "teacherResponseP50Ms": _median(values.get("teacher_replied", [])),
            "wauChange": _change(wau, wau_before),
            "mauChange": _change(mau, mau_before),
            "questionsPerDayChange": _change(questions, questions_before),
            "costPerActiveUser": cost_per_active_user(moment),
        },
        "activeSeries": [{"day": day.isoformat(), "active": len(active.get(day, set()))} for day in window],
        "featureRanking": ranking,
        "funnel": funnel,
        "retention": retention,
    }


def feature_usage(feature: str, days: int, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Event counts of one feature over the last `days` complete days."""
    target = analytics_store.table()
    if target is None:
        return []
    last = (now or datetime.now(UTC)).astimezone(UTC).date() - timedelta(days=1)
    counts: dict[str, int] = {}
    for offset in range(days):
        rows, _stored = rollup_rows(last - timedelta(days=offset), target=target)
        for row in rows:
            sk = str(row.get("SK", ""))
            if sk.startswith("_"):
                continue
            event = str(row.get("event") or sk.split("#", 1)[0])
            if event == "page_viewed":
                by_feature = row.get("by_feature") or {}
                count = _int(by_feature.get(feature))
            elif EVENT_FEATURES.get(event) == feature:
                count = _int(row.get("count"))
            else:
                continue
            if count:
                counts[event] = counts.get(event, 0) + count
    return [
        {"event": event, "count": count}
        for event, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
