"""Which teacher a help request is offered to, and the operators' view of it.

`plan_dispatch` ranks the teachers who could take a request now; the request
itself - its offers, deadlines and lapses - is `help_requests`' (#189).
"""

from __future__ import annotations

import logging

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol, cast

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo, practice_repo, user_repo
from stoa.services import (
    teacher_reply_service,
)


logger = logging.getLogger(__name__)

# Logged for each request nobody could be offered that has waited past the
# alert limit (#88). stoa-infra's metric filter matches this exact string, and
# its test reads it from here.
TEACHER_HELP_WAITING_EVENT = "teacher_help_waiting_no_candidate"


DISPATCH_ACCEPT_TIMEOUT_SECONDS = 10 * 60
DISPATCH_SLA_RISK_SECONDS = teacher_reply_service.TAKEOVER_TARGET_SECONDS
ELIGIBLE_ROLES = {"teacher", "admin"}
AVAILABLE_STATES = {"available", "active", "online", "ready"}
PAUSED_STATES = {"paused", "offline", "busy", "disabled", "inactive"}


class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


def list_teacher_profiles(limit: int = 200) -> list[dict[str, Any]]:
    """Return teacher/admin profiles usable by the dispatch planner."""
    table = cast(_ScanTable, get_table())

    def eligible_profile(profile: dict[str, Any]) -> dict[str, Any] | None:
        teacher_id = str(profile.get("user_id") or "")
        if (
            not teacher_id
            or str(profile.get("role") or "").lower() not in ELIGIBLE_ROLES
            or profile.get("account_status") != "active"
            or _int(profile.get("version"), 0) <= 0
        ):
            return None
        try:
            fence = account_deletion_repo.require_active_account_fence(
                teacher_id, table=table
            )
            generation = int(fence["generation"])
        except (KeyError, TypeError, ValueError, account_deletion_repo.AccountDeletionConflict):
            return None
        return {**profile, "account_fence_generation": generation}

    return _scan_filtered_items(
        table,
        filter_expression="SK = :profile",
        expression_attribute_values={":profile": "PROFILE"},
        accept_item=eligible_profile,
        limit=limit,
    )


def plan_dispatch(
    question: dict[str, Any],
    teacher_profiles: list[dict[str, Any]] | None = None,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Rank eligible teachers for an escalated question without mutating state."""
    timestamp = now or _now()
    profiles = teacher_profiles if teacher_profiles is not None else list_teacher_profiles()
    selected: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    previous = set(_list_value(question.get("previous_dispatch_teacher_ids")))
    current_teacher = str(question.get("dispatched_teacher_id") or "")
    if question.get("dispatch_status") in {"timed_out", "reassigned"} and current_teacher:
        previous.add(current_teacher)

    for profile in profiles:
        normalized = _normalize_teacher_profile(profile)
        refusal = _refusal_reason(question, normalized, previous)
        candidate = _candidate_payload(question, normalized, timestamp)
        if refusal:
            candidate.update(refusal)
            refused.append(candidate)
            continue
        selected.append(candidate)

    selected.sort(key=lambda item: item["rankScore"])
    for index, item in enumerate(selected, start=1):
        item["rank"] = index

    return {
        "questionId": question.get("question_id", ""),
        "subject": question.get("subject", ""),
        "status": "ready" if selected else "no_candidates",
        "selected": selected,
        "refused": refused,
        "summary": {
            "selectedCount": len(selected),
            "refusedCount": len(refused),
            "topCandidateId": selected[0]["teacherId"] if selected else None,
            "noCandidateReason": None if selected else _top_refusal_reason(refused),
        },
        "generatedAt": timestamp,
    }


def decorate_queue_item(question: dict[str, Any], *, viewer_id: str | None = None, now: str | None = None) -> dict[str, Any]:
    """Project bounded queue metadata; never copy student content/profile fields."""
    timestamp = now or _now()
    dispatch_status = str(question.get("dispatch_status") or "unassigned")
    assigned_teacher = question.get("dispatched_teacher_id")
    deadline = question.get("dispatch_deadline_at")
    queue_age_seconds = _duration_from(
        question.get("queue_visible_at") or question.get("teacher_requested_at"),
        timestamp,
    )
    stale = dispatch_status == "dispatched" and _deadline_expired(deadline, timestamp)
    item = {
        "question_id": str(question.get("question_id") or ""),
        "subject": str(question.get("subject") or ""),
        "status": str(question.get("status") or ""),
        "queue_visible_at": question.get("queue_visible_at"),
        "teacher_requested_at": question.get("teacher_requested_at"),
        "dispatch_status": dispatch_status,
        "dispatched_teacher_id": assigned_teacher,
        "dispatch_deadline_at": deadline,
        "dispatch_attempt_count": int(question.get("dispatch_attempt_count") or 0),
        "dispatch_no_candidate_reason": question.get("dispatch_no_candidate_reason"),
    }
    item["dispatch"] = {
        "status": "stale" if stale else dispatch_status,
        "assignedTeacherId": assigned_teacher,
        "assignedToMe": bool(viewer_id and assigned_teacher == viewer_id),
        "deadlineAt": deadline,
        "attemptCount": item["dispatch_attempt_count"],
        "noCandidateReason": item["dispatch_no_candidate_reason"],
    }
    item["sla"] = {
        "queueAgeSeconds": queue_age_seconds,
        "risk": _sla_risk(queue_age_seconds),
    }
    return item


def build_dispatch_dashboard(
    questions: list[dict[str, Any]],
    teacher_profiles: list[dict[str, Any]] | None = None,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Build aggregate operator visibility without exposing question content.

    ``questions`` are the help requests, as `help_requests.question_view` tells them.
    """
    timestamp = now or _now()
    items = questions
    profiles = teacher_profiles if teacher_profiles is not None else list_teacher_profiles()
    load: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        normalized = _normalize_teacher_profile(profile)
        load[normalized["teacherId"]] = {
            "teacherId": normalized["teacherId"],
            "role": normalized["role"],
            "subjects": normalized["subjects"],
            "availability": normalized["availability"],
            "activeCount": normalized["activeCount"],
            "maxActiveSessions": normalized["maxActiveSessions"],
            "assignedDispatches": 0,
        }

    queue_items = [decorate_queue_item(item, now=timestamp) for item in items]
    for item in queue_items:
        assigned = item.get("dispatched_teacher_id")
        if assigned in load and item.get("dispatch_status") == "dispatched":
            load[assigned]["assignedDispatches"] += 1

    timeout_count = sum(1 for item in queue_items if item["dispatch"]["status"] in {"stale", "timed_out"})
    reassignment_count = sum(int(item.get("dispatch_attempt_count") or 0) > 1 for item in queue_items)
    no_candidate_reasons: dict[str, int] = {}
    for item in queue_items:
        reason = item.get("dispatch_no_candidate_reason")
        if reason:
            no_candidate_reasons[str(reason)] = no_candidate_reasons.get(str(reason), 0) + 1

    return {
        "generatedAt": timestamp,
        "queue": {
            "count": len(queue_items),
            "oldestAgeSeconds": max((item["sla"]["queueAgeSeconds"] or 0 for item in queue_items), default=0),
            "slaRiskCount": sum(1 for item in queue_items if item["sla"]["risk"] != "within_target"),
            "timeoutCount": timeout_count,
            "reassignmentCount": reassignment_count,
            "noCandidateReasons": no_candidate_reasons,
        },
        "teacherLoad": sorted(load.values(), key=lambda item: (item["assignedDispatches"], item["activeCount"], item["teacherId"])),
        "dispatchAttempts": [
            {
                "questionId": item.get("question_id"),
                "dispatchStatus": item.get("dispatch_status") or "unassigned",
                "assignedTeacherId": item.get("dispatched_teacher_id"),
                "attemptCount": int(item.get("dispatch_attempt_count") or 0),
                "slaRisk": item["sla"]["risk"],
                "queueAgeSeconds": item["sla"]["queueAgeSeconds"],
                "noCandidateReason": item.get("dispatch_no_candidate_reason"),
            }
            for item in queue_items
        ],
    }


def teacher_availability_summary(
    teacher_profiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return student-safe availability for currently dispatchable teachers."""
    profiles = teacher_profiles if teacher_profiles is not None else list_teacher_profiles()
    available = [
        normalized
        for normalized in (_normalize_teacher_profile(profile) for profile in profiles)
        if _is_profile_available_for_dispatch(normalized)
    ]
    count = len(available)
    return {
        "online": count > 0,
        "availableTeachers": count,
        "responseTime": (
            "Teacher support is available now."
            if count
            else "Teacher support will review requests when a qualified teacher is available."
        ),
    }


def teacher_availability_status(profile: dict[str, Any] | None) -> str | None:
    """Whether a teacher is on dispatch, read the way the planner reads it.

    `available` and `paused` are what a teacher sets; the older stored words map
    onto them. A teacher who has never saved availability has no status, which
    the planner treats as not available.
    """
    availability = _normalize_teacher_profile(dict(profile or {}))["availability"]
    if availability in AVAILABLE_STATES:
        return "available"
    if availability in PAUSED_STATES:
        return "paused"
    return None


def _normalize_teacher_profile(profile: dict[str, Any]) -> dict[str, Any]:
    # Canonical ids, so `math` and the stored `mathematics` are one subject.
    subjects = [
        practice_repo.normal_subject_id(subject)
        for subject in user_repo.stored_teacher_subjects(profile)
    ]
    availability = str(
        user_repo.stored_teacher_availability(profile) or "unavailable"
    ).lower()
    active_count = _int(profile.get("dispatch_active_count") or profile.get("active_session_count"), 0)
    return {
        "teacherId": str(profile.get("user_id") or profile.get("teacher_id") or profile.get("sub") or ""),
        "role": str(profile.get("role") or "").lower(),
        "accountStatus": str(profile.get("account_status") or "").lower(),
        "profileVersion": _int(profile.get("version"), 0),
        "accountFenceGeneration": _int(
            profile.get("account_fence_generation"), 0
        ),
        "subjects": subjects,
        "availability": availability,
        "maxActiveSessions": max(1, _int(profile.get("max_active_sessions") or profile.get("maxActiveSessions"), 3)),
        "activeCount": max(0, active_count),
        "recentSlaBucket": str(profile.get("recent_sla_bucket") or profile.get("teacher_first_reply_sla_bucket") or "unknown"),
        "lastDispatchedAt": profile.get("last_dispatched_at") or profile.get("dispatch_last_dispatched_at"),
    }


def _candidate_payload(question: dict[str, Any], teacher: dict[str, Any], now: str) -> dict[str, Any]:
    load_ratio = teacher["activeCount"] / teacher["maxActiveSessions"]
    sla_penalty = {"within_target": 0, "at_risk": 1, "unknown": 2, "breached": 3}.get(teacher["recentSlaBucket"], 2)
    last_dispatch_penalty = _recency_penalty(teacher.get("lastDispatchedAt"), now)
    rank_score = round((load_ratio * 100) + (sla_penalty * 20) + last_dispatch_penalty, 2)
    return {
        "teacherId": teacher["teacherId"],
        "role": teacher["role"],
        "accountStatus": teacher["accountStatus"],
        "profileVersion": teacher["profileVersion"],
        "accountFenceGeneration": teacher["accountFenceGeneration"],
        "subjects": teacher["subjects"],
        "availability": teacher["availability"],
        "activeCount": teacher["activeCount"],
        "maxActiveSessions": teacher["maxActiveSessions"],
        "recentSlaBucket": teacher["recentSlaBucket"],
        "rankScore": rank_score,
        "reason": "subject_load_sla_fairness_match",
    }


def _refusal_reason(question: dict[str, Any], teacher: dict[str, Any], previous: set[str]) -> dict[str, str] | None:
    if not teacher["teacherId"]:
        return {"refusalCode": "missing_teacher_id", "refusalReason": "Teacher profile has no stable ID."}
    if teacher["role"] not in ELIGIBLE_ROLES:
        return {"refusalCode": "role_not_eligible", "refusalReason": "Profile role cannot receive teacher dispatch."}
    if teacher["accountStatus"] != "active":
        return {
            "refusalCode": "inactive_account",
            "refusalReason": "Teacher account is not active.",
        }
    if teacher["profileVersion"] <= 0 or teacher["accountFenceGeneration"] <= 0:
        return {
            "refusalCode": "lifecycle_observation_missing",
            "refusalReason": "Teacher lifecycle state could not be safely observed.",
        }
    if teacher["availability"] in PAUSED_STATES:
        return {"refusalCode": "not_available", "refusalReason": "Teacher is paused, offline, busy, or inactive."}
    if teacher["availability"] not in AVAILABLE_STATES:
        return {"refusalCode": "not_available", "refusalReason": "Teacher is not marked available for dispatch."}
    if teacher["activeCount"] >= teacher["maxActiveSessions"]:
        return {"refusalCode": "max_active_sessions", "refusalReason": "Teacher is at maximum active session load."}
    if teacher["teacherId"] in previous:
        return {"refusalCode": "previously_timed_out", "refusalReason": "Teacher already timed out or declined this request."}
    subject = practice_repo.normal_subject_id(question.get("subject") or "")
    if teacher["subjects"] and subject not in teacher["subjects"]:
        return {"refusalCode": "subject_mismatch", "refusalReason": "Teacher subject capability does not match the question."}
    if not teacher["subjects"]:
        return {"refusalCode": "missing_subject_capability", "refusalReason": "Teacher profile has no dispatch subject capability."}
    return None


def _is_profile_available_for_dispatch(teacher: dict[str, Any]) -> bool:
    if not teacher["teacherId"]:
        return False
    if teacher["role"] not in ELIGIBLE_ROLES:
        return False
    if teacher["accountStatus"] != "active":
        return False
    if teacher["profileVersion"] <= 0 or teacher["accountFenceGeneration"] <= 0:
        return False
    if teacher["availability"] in PAUSED_STATES:
        return False
    if teacher["availability"] not in AVAILABLE_STATES:
        return False
    if teacher["activeCount"] >= teacher["maxActiveSessions"]:
        return False
    return bool(teacher["subjects"])


def _teacher_assignment_conditions(
    teacher: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind the selected teacher's active fence and exact profile into assignment."""
    teacher_id = str(teacher["teacherId"])
    role = str(teacher["role"])
    generation = int(teacher["accountFenceGeneration"])
    profile_version = int(teacher["profileVersion"])
    return (
        account_deletion_repo.active_fence_condition(teacher_id, generation),
        {
            "ConditionCheck": {
                "Key": {"PK": f"USER#{teacher_id}", "SK": "PROFILE"},
                "ConditionExpression": (
                    "attribute_exists(PK) AND attribute_exists(SK) AND "
                    "#user_id=:teacher_id AND #role=:teacher_role AND "
                    "#account_status=:active AND #version=:teacher_profile_version"
                ),
                "ExpressionAttributeNames": {
                    "#user_id": "user_id",
                    "#role": "role",
                    "#account_status": "account_status",
                    "#version": "version",
                },
                "ExpressionAttributeValues": {
                    ":teacher_id": teacher_id,
                    ":teacher_role": role,
                    ":active": "active",
                    ":teacher_profile_version": profile_version,
                },
            }
        },
    )


def _scan_filtered_items(
    table: _ScanTable,
    *,
    filter_expression: str,
    expression_attribute_values: dict[str, object],
    accept_item: Callable[[dict[str, Any]], dict[str, Any] | None],
    limit: int,
) -> list[dict[str, Any]]:
    """Collect final business-eligible matches across DynamoDB scan pages."""
    if limit <= 0:
        return []
    items: list[dict[str, Any]] = []
    last_evaluated_key: dict[str, object] | None = None
    while len(items) < limit:
        scan_kwargs: dict[str, object] = {
            "FilterExpression": filter_expression,
            "ExpressionAttributeValues": expression_attribute_values,
            "Limit": limit - len(items),
        }
        if last_evaluated_key is not None:
            scan_kwargs["ExclusiveStartKey"] = last_evaluated_key
        result = cast(dict[str, Any], table.scan(**scan_kwargs))
        page = result.get("Items", [])
        if isinstance(page, list):
            for item in page:
                if not isinstance(item, dict):
                    continue
                accepted = accept_item(dict(item))
                if accepted is not None:
                    items.append(accepted)
                if len(items) >= limit:
                    break
        next_key = result.get("LastEvaluatedKey")
        if (
            not isinstance(next_key, dict)
            or not next_key
            or next_key == last_evaluated_key
        ):
            break
        last_evaluated_key = dict(next_key)
    return items[:limit]


def _deadline_expired(deadline: Any, now: str) -> bool:
    parsed_deadline = _parse_timestamp(deadline)
    parsed_now = _parse_timestamp(now)
    if not parsed_deadline or not parsed_now:
        return False
    return parsed_deadline <= parsed_now


def _duration_from(start: Any, now: str) -> int | None:
    parsed_start = _parse_timestamp(start)
    parsed_now = _parse_timestamp(now)
    if not parsed_start or not parsed_now:
        return None
    return max(0, int((parsed_now - parsed_start).total_seconds()))


def _sla_risk(queue_age_seconds: int | None) -> str:
    if queue_age_seconds is None:
        return "unknown"
    if queue_age_seconds >= DISPATCH_SLA_RISK_SECONDS:
        return "breached"
    if queue_age_seconds >= int(DISPATCH_SLA_RISK_SECONDS * 0.75):
        return "at_risk"
    return "within_target"


def _top_refusal_reason(refused: list[dict[str, Any]]) -> str | None:
    counts: dict[str, int] = {}
    for item in refused:
        code = item.get("refusalCode")
        if code:
            counts[str(code)] = counts.get(str(code), 0) + 1
    if not counts:
        return "no_teacher_profiles"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _list_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (set, tuple)):
        return list(value)
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


def _recency_penalty(value: Any, now: str) -> int:
    dispatched_at = _parse_timestamp(value)
    parsed_now = _parse_timestamp(now)
    if not dispatched_at or not parsed_now:
        return 0
    age_minutes = max(0, int((parsed_now - dispatched_at).total_seconds() // 60))
    return max(0, 60 - min(age_minutes, 60))


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# What `help_requests` binds an offer and a teacher's move to, and how it reads time.
teacher_assignment_conditions = _teacher_assignment_conditions
parse_timestamp = _parse_timestamp
