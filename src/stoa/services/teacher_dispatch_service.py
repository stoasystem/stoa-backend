"""Automatic teacher dispatch planning and queue health helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from stoa.db.dynamodb import get_table
from stoa.db.repositories import question_repo
from stoa.models.question import QuestionStatus
from stoa.services import teacher_reply_service

DISPATCH_ACCEPT_TIMEOUT_SECONDS = 10 * 60
DISPATCH_SLA_RISK_SECONDS = teacher_reply_service.TAKEOVER_TARGET_SECONDS
ELIGIBLE_ROLES = {"teacher", "admin"}
AVAILABLE_STATES = {"available", "active", "online", "ready"}
PAUSED_STATES = {"paused", "offline", "busy", "disabled", "inactive"}


def list_teacher_profiles(limit: int = 200) -> list[dict[str, Any]]:
    """Return teacher/admin profiles usable by the dispatch planner."""
    table = get_table()
    result = table.scan(
        FilterExpression="SK = :profile",
        ExpressionAttributeValues={":profile": "PROFILE"},
        Limit=limit,
    )
    return [
        item
        for item in result.get("Items", [])
        if str(item.get("role") or "").lower() in ELIGIBLE_ROLES
    ]


def list_teacher_dispatch_questions(limit: int = 200) -> list[dict[str, Any]]:
    """Return questions that participate in dispatch and SLA dashboards."""
    table = get_table()
    result = table.scan(
        FilterExpression="SK = :meta",
        ExpressionAttributeValues={":meta": "META"},
        Limit=limit,
    )
    return [
        item
        for item in result.get("Items", [])
        if item.get("teacher_requested_at")
        or item.get("queue_visible_at")
        or item.get("dispatch_status")
        or item.get("status") in {QuestionStatus.ESCALATED.value, QuestionStatus.TEACHER_ACTIVE.value}
    ]


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


def dispatch_question(
    question_id: str,
    *,
    question: dict[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Conditionally claim an escalated question for the best available teacher."""
    timestamp = now or _now()
    question = question or question_repo.get_question(question_id)
    if not question:
        return {"questionId": question_id, "status": "not_found", "reason": "question_not_found"}
    if question.get("status") != QuestionStatus.ESCALATED.value:
        return {"questionId": question_id, "status": "not_dispatchable", "reason": "not_escalated"}
    if _has_current_dispatch(question, timestamp):
        return {
            "questionId": question_id,
            "status": "already_dispatched",
            "teacherId": question.get("dispatched_teacher_id"),
            "dispatchId": question.get("dispatch_id"),
        }

    plan = plan_dispatch(question, now=timestamp)
    if not plan["selected"]:
        question_repo.update_status(
            question_id,
            QuestionStatus.ESCALATED.value,
            dispatch_status="unassigned",
            dispatch_no_candidate_reason=plan["summary"]["noCandidateReason"] or "no_eligible_teacher",
            dispatch_updated_at=timestamp,
        )
        return {"questionId": question_id, "status": "no_candidate", "plan": plan}

    candidate = plan["selected"][0]
    previous = _previous_assignees(question)
    if question.get("dispatch_status") in {"timed_out", "reassigned"} and question.get("dispatched_teacher_id"):
        previous.append(str(question["dispatched_teacher_id"]))

    dispatch_id = str(uuid.uuid4())
    deadline = _deadline(timestamp)
    attempt_count = int(question.get("dispatch_attempt_count") or 0) + 1
    claimed = question_repo.update_status_conditionally(
        question_id,
        QuestionStatus.ESCALATED.value,
        condition_expression=(
            "#s = :expected_status AND "
            "(attribute_not_exists(dispatch_status) OR dispatch_status <> :current_dispatch OR "
            "dispatch_deadline_at <= :now)"
        ),
        condition_values={
            ":expected_status": QuestionStatus.ESCALATED.value,
            ":current_dispatch": "dispatched",
            ":now": timestamp,
        },
        dispatch_id=dispatch_id,
        dispatch_status="dispatched",
        dispatched_teacher_id=candidate["teacherId"],
        dispatch_reason=candidate["reason"],
        dispatch_deadline_at=deadline,
        dispatch_updated_at=timestamp,
        dispatch_attempt_count=attempt_count,
        previous_dispatch_teacher_ids=previous,
        dispatch_no_candidate_reason=None,
    )
    if not claimed:
        return {"questionId": question_id, "status": "claim_conflict", "plan": plan}

    return {
        "questionId": question_id,
        "status": "dispatched",
        "dispatchId": dispatch_id,
        "teacherId": candidate["teacherId"],
        "deadlineAt": deadline,
        "attemptCount": attempt_count,
        "plan": plan,
    }


def reassign_timed_out_dispatches(
    questions: list[dict[str, Any]] | None = None,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Reassign stale dispatched questions and report per-question results."""
    timestamp = now or _now()
    items = questions if questions is not None else list_teacher_dispatch_questions()
    stale = [
        item
        for item in items
        if item.get("status") == QuestionStatus.ESCALATED.value
        and item.get("dispatch_status") == "dispatched"
        and _deadline_expired(item.get("dispatch_deadline_at"), timestamp)
    ]
    results = []
    for item in stale:
        question_id = str(item.get("question_id") or "")
        previous = _previous_assignees(item)
        current_teacher = str(item.get("dispatched_teacher_id") or "")
        if current_teacher and current_teacher not in previous:
            previous.append(current_teacher)
        question_repo.update_status(
            question_id,
            QuestionStatus.ESCALATED.value,
            dispatch_status="timed_out",
            dispatch_updated_at=timestamp,
            previous_dispatch_teacher_ids=previous,
        )
        refreshed = {**item, "dispatch_status": "timed_out", "previous_dispatch_teacher_ids": previous}
        result = dispatch_question(question_id, question=refreshed, now=timestamp)
        results.append({"questionId": question_id, "previousTeacherId": current_teacher, **result})
        if result["status"] == "not_found":
            plan = plan_dispatch(refreshed, now=timestamp)
            results[-1] = {"questionId": question_id, "previousTeacherId": current_teacher, "status": "no_candidate", "plan": plan}
    return {"processed": len(stale), "results": results, "generatedAt": timestamp}


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
    questions: list[dict[str, Any]] | None = None,
    teacher_profiles: list[dict[str, Any]] | None = None,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Build aggregate operator visibility without exposing question content."""
    timestamp = now or _now()
    items = questions if questions is not None else list_teacher_dispatch_questions()
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


def student_dispatch_status(question: dict[str, Any]) -> str:
    """Return a simple student-safe dispatch status."""
    if question.get("status") == QuestionStatus.RESOLVED.value:
        return "resolved"
    if question.get("teacher_first_replied_at") or question.get("teacher_response"):
        return "replied"
    if question.get("status") == QuestionStatus.TEACHER_ACTIVE.value:
        return "active"
    if question.get("dispatch_status") == "dispatched":
        return "assigned"
    return "waiting"


def _normalize_teacher_profile(profile: dict[str, Any]) -> dict[str, Any]:
    subjects = _list_value(
        profile.get("dispatch_subjects")
        or profile.get("primary_subjects")
        or profile.get("subjects")
        or profile.get("subject_ids")
    )
    availability = str(
        profile.get("dispatch_availability")
        or profile.get("availability_status")
        or profile.get("teacher_status")
        or "available"
    ).lower()
    active_count = _int(profile.get("dispatch_active_count") or profile.get("active_session_count"), 0)
    return {
        "teacherId": str(profile.get("user_id") or profile.get("teacher_id") or profile.get("sub") or ""),
        "role": str(profile.get("role") or "").lower(),
        "subjects": [str(subject).lower() for subject in subjects],
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
    if teacher["availability"] in PAUSED_STATES:
        return {"refusalCode": "not_available", "refusalReason": "Teacher is paused, offline, busy, or inactive."}
    if teacher["availability"] not in AVAILABLE_STATES:
        return {"refusalCode": "not_available", "refusalReason": "Teacher is not marked available for dispatch."}
    if teacher["activeCount"] >= teacher["maxActiveSessions"]:
        return {"refusalCode": "max_active_sessions", "refusalReason": "Teacher is at maximum active session load."}
    if teacher["teacherId"] in previous:
        return {"refusalCode": "previously_timed_out", "refusalReason": "Teacher already timed out or declined this request."}
    subject = str(question.get("subject") or "").lower()
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
    if teacher["availability"] in PAUSED_STATES:
        return False
    if teacher["availability"] not in AVAILABLE_STATES:
        return False
    if teacher["activeCount"] >= teacher["maxActiveSessions"]:
        return False
    return bool(teacher["subjects"])


def _has_current_dispatch(question: dict[str, Any], now: str) -> bool:
    return (
        question.get("dispatch_status") == "dispatched"
        and bool(question.get("dispatched_teacher_id"))
        and not _deadline_expired(question.get("dispatch_deadline_at"), now)
    )


def _deadline_expired(deadline: Any, now: str) -> bool:
    parsed_deadline = _parse_timestamp(deadline)
    parsed_now = _parse_timestamp(now)
    if not parsed_deadline or not parsed_now:
        return False
    return parsed_deadline <= parsed_now


def _deadline(now: str) -> str:
    parsed = _parse_timestamp(now) or datetime.now(timezone.utc)
    return (parsed + timedelta(seconds=DISPATCH_ACCEPT_TIMEOUT_SECONDS)).isoformat()


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


def _previous_assignees(question: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in _list_value(question.get("previous_dispatch_teacher_ids")) if item))


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
