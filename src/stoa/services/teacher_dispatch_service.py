"""Which teacher a help request is offered to: the ranking policy.

`plan_dispatch` ranks the teachers who could take a request now, and
`teacher_assignment_conditions` binds an offer to the chosen teacher's profile
as it was read; the write holds the teacher's account fence at the generation
read with it (`db_table.fenced`). The two availability readers tell a student
whether anyone is on dispatch and a teacher whether they are. The request
itself - its offers, deadlines and lapses - is `help_requests`' (#189).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol, cast

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, user_repo
from stoa.services import curriculum_service

# Logged for each request nobody could be offered that has waited past the
# alert limit (#88). stoa-infra's metric filter matches this exact string, and
# its test reads it from here.
TEACHER_HELP_WAITING_EVENT = "teacher_help_waiting_no_candidate"


DISPATCH_ACCEPT_TIMEOUT_SECONDS = 10 * 60
ELIGIBLE_ROLES = {"teacher", "admin"}
AVAILABLE_STATES = {"available", "active", "online", "ready"}
PAUSED_STATES = {"paused", "offline", "busy", "disabled", "inactive"}


class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


def list_teacher_profiles(limit: int = 200) -> list[dict[str, Any]]:
    """Return teacher/admin profiles usable by the dispatch planner."""
    table = cast(_ScanTable, db_table.table())

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
    """Rank eligible teachers for a help request without mutating state.

    ``question`` is read for its `subject`, its `question_id` (echoed back) and
    the `previous_dispatch_teacher_ids` it must not be offered to again.
    """
    timestamp = now or _now()
    profiles = teacher_profiles if teacher_profiles is not None else list_teacher_profiles()
    selected: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    previous = set(question.get("previous_dispatch_teacher_ids") or ())

    for profile in profiles:
        normalized = _normalize_teacher_profile(profile)
        refusal = _refusal_reason(question, normalized, previous)
        candidate = _candidate_payload(normalized, timestamp)
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


def teacher_assignment_conditions(
    teacher: dict[str, Any],
) -> tuple[dict[str, Any]]:
    """Bind a planned candidate's exact profile into a write.

    ``teacher`` is a `plan_dispatch` candidate; `help_requests` adds these to
    an offer, and to a teacher's move on a request, sent behind the teacher's
    account fence at the candidate's `accountFenceGeneration`.
    """
    teacher_id = str(teacher["teacherId"])
    role = str(teacher["role"])
    profile_version = int(teacher["profileVersion"])
    return (
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


def teacher_availability_summary(
    teacher_profiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return student-safe availability for currently dispatchable teachers."""
    profiles = teacher_profiles if teacher_profiles is not None else list_teacher_profiles()
    available = [
        normalized
        for normalized in (_normalize_teacher_profile(profile) for profile in profiles)
        if _standing_refusal(normalized) is None and normalized["subjects"]
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


def parse_timestamp(value: Any) -> datetime | None:
    """A stored timestamp as an aware UTC datetime; None when it cannot be read.

    How `help_requests` reads its deadlines, so offer and planner read time alike.
    """
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


def _normalize_teacher_profile(profile: dict[str, Any]) -> dict[str, Any]:
    # Canonical ids, so `math` and the stored `mathematics` are one subject.
    subjects = [
        curriculum_service.subject_key(subject)
        for subject in user_repo.stored_teacher_subjects(profile)
    ]
    availability = str(
        user_repo.stored_teacher_availability(profile) or "unavailable"
    ).lower()
    active_count = _int(profile.get("dispatch_active_count") or profile.get("active_session_count"), 0)
    return {
        "teacherId": str(profile.get("user_id") or ""),
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


def _candidate_payload(teacher: dict[str, Any], now: str) -> dict[str, Any]:
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


def _standing_refusal(teacher: dict[str, Any]) -> dict[str, str] | None:
    """Why this teacher can take no request at all now, if they cannot."""
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
    return None


def _refusal_reason(question: dict[str, Any], teacher: dict[str, Any], previous: set[str]) -> dict[str, str] | None:
    standing = _standing_refusal(teacher)
    if standing:
        return standing
    if teacher["teacherId"] in previous:
        return {"refusalCode": "previously_timed_out", "refusalReason": "Teacher already timed out or declined this request."}
    subject = curriculum_service.subject_key(question.get("subject") or "")
    if teacher["subjects"] and subject not in teacher["subjects"]:
        return {"refusalCode": "subject_mismatch", "refusalReason": "Teacher subject capability does not match the question."}
    if not teacher["subjects"]:
        return {"refusalCode": "missing_subject_capability", "refusalReason": "Teacher profile has no dispatch subject capability."}
    return None


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
    reads = db_table.pages(
        "scan",
        table=table,
        FilterExpression=filter_expression,
        ExpressionAttributeValues=expression_attribute_values,
        Limit=limit,
    )
    try:
        for page in reads:
            for item in page.items:
                accepted = accept_item(item)
                if accepted is not None:
                    items.append(accepted)
                if len(items) >= limit:
                    break
            if (
                len(items) >= limit
                or page.last_key is None
                or page.last_key == last_evaluated_key
            ):
                break
            last_evaluated_key = page.last_key
    except db_table.TableUnavailable as exc:
        # A page the table did not answer in shape ends the walk with what is in hand.
        if not exc.code.startswith("malformed"):
            raise
    return items[:limit]


def _top_refusal_reason(refused: list[dict[str, Any]]) -> str | None:
    counts: dict[str, int] = {}
    for item in refused:
        code = item.get("refusalCode")
        if code:
            counts[str(code)] = counts.get(str(code), 0) + 1
    if not counts:
        return "no_teacher_profiles"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _recency_penalty(value: Any, now: str) -> int:
    dispatched_at = parse_timestamp(value)
    parsed_now = parse_timestamp(now)
    if not dispatched_at or not parsed_now:
        return 0
    age_minutes = max(0, int((parsed_now - dispatched_at).total_seconds() // 60))
    return max(0, 60 - min(age_minutes, 60))


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
