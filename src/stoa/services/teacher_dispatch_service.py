"""Automatic teacher dispatch planning and queue health helpers."""

from __future__ import annotations

import logging

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, cast

from stoa.db.dynamodb import get_table
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import account_deletion_repo, practice_repo, question_repo, user_repo
from stoa.models.question import QuestionStatus
from stoa.services import teacher_reply_service


logger = logging.getLogger(__name__)

DISPATCH_ACCEPT_TIMEOUT_SECONDS = 10 * 60
DISPATCH_SLA_RISK_SECONDS = teacher_reply_service.TAKEOVER_TARGET_SECONDS
ELIGIBLE_ROLES = {"teacher", "admin"}
AVAILABLE_STATES = {"available", "active", "online", "ready"}
PAUSED_STATES = {"paused", "offline", "busy", "disabled", "inactive"}
_DISPATCH_SOURCE_STATES = frozenset({QuestionStatus.ESCALATED.value})


class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


def _versioned_dispatch_question(
    question: dict[str, Any],
) -> dict[str, Any] | None:
    version = stored_int(question.get("version"))
    if version is not None and version > 0:
        return question
    result = question_repo.initialize_legacy_question_version(
        question,
        allowed_source_statuses=_DISPATCH_SOURCE_STATES,
    )
    if (
        result.disposition is question_repo.QuestionMutationDisposition.APPLIED
        and result.question is not None
    ):
        return dict(result.question)
    return None


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


def list_teacher_dispatch_questions(limit: int = 200) -> list[dict[str, Any]]:
    """Return questions that participate in dispatch and SLA dashboards."""
    table = cast(_ScanTable, get_table())
    items = _scan_filtered_items(
        table,
        filter_expression="SK = :meta",
        expression_attribute_values={":meta": "META"},
        accept_item=lambda item: item
        if (
            item.get("teacher_requested_at")
            or item.get("queue_visible_at")
            or item.get("dispatch_status")
            or item.get("status")
            in {
                QuestionStatus.ESCALATED.value,
                QuestionStatus.TEACHER_ACTIVE.value,
            }
        )
        else None,
        limit=limit,
    )
    return items


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
    question = _versioned_dispatch_question(question)
    if question is None:
        return {"questionId": question_id, "status": "claim_conflict", "reason": "question_changed"}
    if _has_current_dispatch(question, timestamp):
        return {
            "questionId": question_id,
            "status": "already_dispatched",
            "teacherId": question.get("dispatched_teacher_id"),
            "dispatchId": question.get("dispatch_id"),
        }

    plan = plan_dispatch(question, now=timestamp)
    if not plan["selected"]:
        mutation = question_repo.mutate_question(
            question,
            status=QuestionStatus.ESCALATED.value,
            allowed_source_statuses=_DISPATCH_SOURCE_STATES,
            extra_attrs={
                "dispatch_status": "unassigned",
                "dispatch_no_candidate_reason": (
                    plan["summary"]["noCandidateReason"] or "no_eligible_teacher"
                ),
                "dispatch_updated_at": timestamp,
            },
        )
        if mutation.disposition is not question_repo.QuestionMutationDisposition.APPLIED:
            return {
                "questionId": question_id,
                "status": "claim_conflict",
                "reason": "question_changed",
                "plan": plan,
            }
        return {"questionId": question_id, "status": "no_candidate", "plan": plan}

    candidate = plan["selected"][0]
    previous = _previous_assignees(question)
    if question.get("dispatch_status") in {"timed_out", "reassigned"} and question.get("dispatched_teacher_id"):
        previous.append(str(question["dispatched_teacher_id"]))

    dispatch_id = str(uuid.uuid4())
    deadline = _deadline(timestamp)
    attempt_count = int(question.get("dispatch_attempt_count") or 0) + 1
    mutation = question_repo.mutate_question(
        question,
        status=QuestionStatus.ESCALATED.value,
        allowed_source_statuses=_DISPATCH_SOURCE_STATES,
        additional_conditions=_teacher_assignment_conditions(candidate),
        extra_attrs={
            "dispatch_id": dispatch_id,
            "dispatch_status": "dispatched",
            "dispatched_teacher_id": candidate["teacherId"],
            "dispatch_reason": candidate["reason"],
            "dispatch_deadline_at": deadline,
            "dispatch_updated_at": timestamp,
            "dispatch_attempt_count": attempt_count,
            "previous_dispatch_teacher_ids": previous,
            "dispatch_no_candidate_reason": None,
        },
    )
    if mutation.disposition is not question_repo.QuestionMutationDisposition.APPLIED:
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
    results: list[dict[str, Any]] = []
    for item in stale:
        question_id = str(item.get("question_id") or "")
        previous = _previous_assignees(item)
        current_teacher = str(item.get("dispatched_teacher_id") or "")
        if current_teacher and current_teacher not in previous:
            previous.append(current_teacher)
        versioned = _versioned_dispatch_question(item)
        if versioned is None:
            results.append(
                {
                    "questionId": question_id,
                    "previousTeacherId": current_teacher,
                    "status": "claim_conflict",
                }
            )
            continue
        timeout_mutation = question_repo.mutate_question(
            versioned,
            status=QuestionStatus.ESCALATED.value,
            allowed_source_statuses=_DISPATCH_SOURCE_STATES,
            extra_attrs={
                "dispatch_status": "timed_out",
                "dispatch_updated_at": timestamp,
                "previous_dispatch_teacher_ids": previous,
            },
        )
        if (
            timeout_mutation.disposition
            is not question_repo.QuestionMutationDisposition.APPLIED
            or timeout_mutation.question is None
        ):
            results.append(
                {
                    "questionId": question_id,
                    "previousTeacherId": current_teacher,
                    "status": "claim_conflict",
                }
            )
            continue
        refreshed = dict(timeout_mutation.question)
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


class QueueRowUnavailable(Exception):
    """The queue row of a chat escalation could not be read."""


def _escalated_question_row(table: Any, request_id: str) -> dict[str, Any] | None:
    """The queue row of a chat escalation, or `None` when it does not exist.

    A failed read is raised, never reported as absent: callers write only the
    conversation when there is no queue row, so reading a throttled or failed
    lookup as "no row" split the two rows.
    """
    try:
        response = table.get_item(
            Key={"PK": f"QUESTION#{request_id}", "SK": "META"}, ConsistentRead=True
        )
    except Exception as exc:  # noqa: BLE001 - any failure means "unknown", not "absent"
        raise QueueRowUnavailable(request_id) from exc
    if not isinstance(response, dict):
        raise QueueRowUnavailable(request_id)
    item = response.get("Item")
    return dict(item) if isinstance(item, dict) else None


def dispatch_conversation(
    conversation_id: str,
    *,
    conversation: dict[str, Any],
    now: str | None = None,
    table: Any | None = None,
) -> dict[str, Any]:
    """Claim an escalated conversation for the best available teacher.

    A chat escalation is two rows: the conversation the student reads and the
    question row the teacher queue reads. Both carry the dispatch, in one
    transaction. Updating only the conversation left the queue row saying
    `unassigned` forever, which let a second teacher be dispatched to the same
    case and left the SLA dashboard counting it as never dispatched.
    """
    timestamp = now or _now()
    target = table or get_table()

    if str(conversation.get("escalation_status") or "") not in {"", "pending"}:
        return {"conversationId": conversation_id, "status": "not_dispatchable"}
    current_teacher = str(conversation.get("dispatched_teacher_id") or "")
    if (
        current_teacher
        and conversation.get("dispatch_status") == "dispatched"
        and not _deadline_expired(conversation.get("dispatch_deadline_at"), timestamp)
    ):
        return {
            "conversationId": conversation_id,
            "status": "already_dispatched",
            "teacherId": current_teacher,
        }

    # Both rows are written together, so the queue row is read first. A read
    # that failed is retried on the next sweep rather than read as "no row".
    request_id = str(conversation.get("escalation_request_id") or "")
    try:
        question = _escalated_question_row(target, request_id) if request_id else None
    except QueueRowUnavailable:
        return {"conversationId": conversation_id, "status": "claim_conflict"}
    if question is None:
        # An escalation from before queue rows: it cannot be taken (#72), so
        # offering it would only re-offer it forever to teachers who get 409.
        return {
            "conversationId": conversation_id,
            "status": "not_dispatchable",
            "reason": "no_queue_row",
        }

    # Who already timed out on this case is recorded on the queue row; the
    # conversation does not carry it, so without this the same teacher was
    # offered the case again.
    planned = dict(conversation)
    if question is not None:
        planned["previous_dispatch_teacher_ids"] = sorted(
            set(_previous_assignees(conversation)) | set(_previous_assignees(question))
        )
    plan = plan_dispatch(planned, now=timestamp)
    if not plan["selected"]:
        return {
            "conversationId": conversation_id,
            "status": "no_candidate",
            "reason": plan["summary"]["noCandidateReason"] or "no_eligible_teacher",
        }

    candidate = plan["selected"][0]
    dispatch_id = str(uuid.uuid4())
    deadline = _deadline(timestamp)
    attempt_count = int(_int(conversation.get("dispatch_attempt_count"), 0)) + 1
    question_operations = question_repo.build_question_update_transaction(
        question,
        # The state does not move: a dispatched case is still escalated. What
        # is written is who it went to, through the same version CAS every
        # other question write goes through.
        status=str(question.get("status") or "escalated"),
        expected_generation=int(_int(question.get("account_fence_generation"), 1)),
        extra_attrs={
            "dispatched_teacher_id": str(candidate["teacherId"]),
            "dispatch_status": "dispatched",
            "dispatch_id": dispatch_id,
            "dispatch_deadline_at": deadline,
            "dispatch_updated_at": timestamp,
        },
    )

    try:
        account_deletion_repo.transact(
            [
                *_teacher_assignment_conditions(candidate),
                *question_operations,
                {
                    "Update": {
                        "Key": {"PK": f"CONV#{conversation_id}", "SK": "CONV"},
                        "UpdateExpression": (
                            "SET dispatched_teacher_id=:teacher, dispatch_status=:dispatched, "
                            "dispatch_id=:dispatch_id, dispatch_deadline_at=:deadline, "
                            "dispatch_attempt_count=:attempts, dispatch_updated_at=:now"
                        ),
                        "ConditionExpression": (
                            "attribute_exists(PK) AND escalation_status=:pending"
                        ),
                        "ExpressionAttributeValues": {
                            ":teacher": str(candidate["teacherId"]),
                            ":dispatched": "dispatched",
                            ":dispatch_id": dispatch_id,
                            ":deadline": deadline,
                            ":attempts": attempt_count,
                            ":now": timestamp,
                            ":pending": "pending",
                        },
                    }
                },
            ],
            table=target,
        )
    except Exception:
        return {"conversationId": conversation_id, "status": "claim_conflict"}

    return {
        "conversationId": conversation_id,
        "status": "dispatched",
        "teacherId": str(candidate["teacherId"]),
        "dispatchId": dispatch_id,
        "deadlineAt": deadline,
    }


HELP_REQUEST_STATUSES = ("in_progress", "resolved")


class HelpRequestConflict(Exception):
    """The help request is not in the state the change was decided on."""


def advance_help_request(
    conversation: dict[str, Any],
    *,
    teacher_id: str,
    target: str,
    now: str | None = None,
    resolution_note: str | None = None,
    extra_operations: tuple[dict[str, Any], ...] = (),
    table: Any | None = None,
) -> dict[str, Any]:
    """Move a chat help request to `target` for `teacher_id`, both rows at once.

    A chat escalation is the conversation the student reads and the queue row
    the reconciler reads. Dispatch offers it to one teacher; nothing used to let
    that teacher take it, so the conversation never got a `teacher_id` and every
    write the teacher tried was refused. The teacher's first write on an offer
    is now the acceptance: it binds the conversation and the queue row to them,
    in the same transaction as whatever they did (`in_progress`, `resolved`, or
    a reply passed as `extra_operations`).

    Every condition the decision rested on is part of the write: the exact offer
    (`dispatch_id`) and that it is still live (`dispatch_deadline_at`), the
    teacher's active account and profile version, the student's fence, and the
    queue row's version. If any moved, nothing is written and
    `HelpRequestConflict` is raised.
    """
    if target not in HELP_REQUEST_STATUSES:
        raise ValueError(f"unsupported help request status: {target}")
    timestamp = now or _now()
    store = table or get_table()
    conversation_id = str(conversation.get("conversation_id") or "")
    current = str(conversation.get("escalation_status") or "pending")
    holder = str(conversation.get("teacher_id") or "")
    if not conversation_id or current == "resolved" or (holder and holder != teacher_id):
        raise HelpRequestConflict("help request is not open to this teacher")
    accepting = not holder

    operations: list[dict[str, Any]] = list(_teacher_standing_conditions(teacher_id, store))
    assignments = [
        "escalation_status = :target",
        "updated_at = :now",
        "first_teacher_action_at = if_not_exists(first_teacher_action_at, :now)",
    ]
    values: dict[str, Any] = {":target": target, ":now": timestamp, ":teacher": teacher_id}
    if accepting:
        offer = str(conversation.get("dispatch_id") or "")
        if (
            not offer
            or conversation.get("dispatch_status") != "dispatched"
            or str(conversation.get("dispatched_teacher_id") or "") != teacher_id
            or current != "pending"
        ):
            raise HelpRequestConflict("help request holds no offer for this teacher")
        assignments += [
            "teacher_id = :teacher",
            "dispatch_status = :accepted",
            "accepted_at = :now",
        ]
        condition = (
            "attribute_exists(PK) AND attribute_not_exists(teacher_id) "
            "AND escalation_status = :pending AND dispatch_status = :dispatched "
            "AND dispatched_teacher_id = :teacher AND dispatch_id = :offer "
            "AND dispatch_deadline_at > :now"
        )
        values.update(
            {
                ":accepted": "accepted",
                ":pending": "pending",
                ":dispatched": "dispatched",
                ":offer": offer,
            }
        )
    else:
        condition = (
            "attribute_exists(PK) AND teacher_id = :teacher "
            "AND escalation_status IN (:pending, :in_progress)"
        )
        values.update({":pending": "pending", ":in_progress": "in_progress"})
    if target == "resolved":
        assignments.append("escalation_resolved_at = :now")
        if resolution_note:
            assignments.append("resolution_note = :note")
            values[":note"] = resolution_note
    operations.append(
        {
            "Update": {
                "Key": {"PK": f"CONV#{conversation_id}", "SK": "CONV"},
                "UpdateExpression": "SET " + ", ".join(assignments),
                "ConditionExpression": condition,
                "ExpressionAttributeValues": values,
            }
        }
    )

    request_id = str(conversation.get("escalation_request_id") or "")
    try:
        question = _escalated_question_row(store, request_id) if request_id else None
    except QueueRowUnavailable as exc:
        raise HelpRequestConflict("queue row could not be read") from exc
    if question is None:
        # Escalations from before queue rows existed are not taken: account
        # deletion reaches a chat request through its queue row, so a teacher
        # bound to a conversation without one could never be removed from it
        # (stoasystem/stoa-backend#72). None exist in production (2026-09-28).
        raise HelpRequestConflict("chat help request has no queue row")
    # The queue row's CAS carries the student's fence.
    operations.extend(
        _queue_row_transition(
            question,
            teacher_id=teacher_id,
            target=target,
            now=timestamp,
            accepting=accepting,
            offer=str(conversation.get("dispatch_id") or ""),
        )
    )
    operations.extend(extra_operations)

    try:
        account_deletion_repo.transact(operations, table=store)
    except Exception as exc:  # noqa: BLE001 - every refusal means the case moved on
        raise HelpRequestConflict("help request changed before the write") from exc

    updated = {**conversation, "escalation_status": target, "updated_at": timestamp}
    updated["first_teacher_action_at"] = conversation.get("first_teacher_action_at") or timestamp
    if accepting:
        updated.update({"teacher_id": teacher_id, "dispatch_status": "accepted", "accepted_at": timestamp})
    if target == "resolved":
        updated["escalation_resolved_at"] = timestamp
        if resolution_note:
            updated["resolution_note"] = resolution_note
    return updated


def is_chat_question_row(question: dict[str, Any] | None) -> bool:
    """Whether a queue row is the second half of a chat help request."""
    row = question or {}
    return row.get("source") == "conversation_escalation" or bool(row.get("conversation_id"))


def _queue_row_transition(
    question: dict[str, Any],
    *,
    teacher_id: str,
    target: str,
    now: str,
    accepting: bool,
    offer: str = "",
) -> list[dict[str, Any]]:
    """The queue row's half of a help-request move.

    Everything read here is bound by the row's version CAS, so the checks hold
    at write time: when accepting, the row must still be waiting on the very
    offer the conversation carries, and the teacher must not be one who
    already timed out on it.
    """
    status = str(question.get("status") or "")
    if accepting:
        if status != QuestionStatus.ESCALATED.value:
            raise HelpRequestConflict("queue row is no longer waiting")
        if (
            question.get("dispatch_status") != "dispatched"
            or str(question.get("dispatched_teacher_id") or "") != teacher_id
            or not offer
            or str(question.get("dispatch_id") or "") != offer
        ):
            raise HelpRequestConflict("queue row no longer carries this offer")
        if teacher_id in _previous_assignees(question):
            raise HelpRequestConflict("teacher already timed out on this request")
    elif status != QuestionStatus.TEACHER_ACTIVE.value or str(question.get("teacher_id") or "") != teacher_id:
        raise HelpRequestConflict("queue row is not held by this teacher")
    if not accepting and target == "in_progress":
        return []  # already held and active: nothing moves on the queue row
    extra: dict[str, Any] = {}
    if accepting:
        extra.update(
            {
                "teacher_id": teacher_id,
                "dispatch_status": "accepted",
                "teacher_accepted_at": now,
                **teacher_reply_service.compute_takeover_sla_fields(question, now),
            }
        )
    if target == "resolved":
        extra.update(
            {"resolved_at": now, **teacher_reply_service.compute_resolved_sla_fields(question, now)}
        )
    return question_repo.build_question_update_transaction(
        question,
        status=(
            QuestionStatus.RESOLVED.value
            if target == "resolved"
            else QuestionStatus.TEACHER_ACTIVE.value
        ),
        expected_generation=int(_int(question.get("account_fence_generation"), 1)),
        # An offer is taken only while it is live, checked where it is written,
        # as question_repo.claim_teacher_takeover does for the question lane.
        condition_expression="dispatch_deadline_at > :offer_live_at" if accepting else None,
        condition_values={":offer_live_at": now} if accepting else None,
        extra_attrs=extra,
    )


def _teacher_standing_conditions(teacher_id: str, table: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind the accepting teacher's active fence and exact current profile."""
    try:
        response = table.get_item(
            Key={"PK": f"USER#{teacher_id}", "SK": "PROFILE"}, ConsistentRead=True
        )
        profile = response.get("Item") if isinstance(response, dict) else None
        fence = account_deletion_repo.require_active_account_fence(teacher_id, table=table)
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise HelpRequestConflict("teacher account is not active") from exc
    if not isinstance(profile, dict) or profile.get("account_status") != "active":
        raise HelpRequestConflict("teacher account is not active")
    role = str(profile.get("role") or "").lower()
    if role not in ELIGIBLE_ROLES:
        raise HelpRequestConflict("profile cannot take teacher help requests")
    return _teacher_assignment_conditions(
        {
            "teacherId": teacher_id,
            "role": str(profile.get("role")),
            "accountFenceGeneration": int(fence["generation"]),
            "profileVersion": _int(profile.get("version"), 0),
        }
    )


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


def list_escalated_conversations(limit: int = 200) -> list[dict[str, Any]]:
    """Conversations a student escalated to a teacher."""
    table = cast(_ScanTable, get_table())
    return _scan_filtered_items(
        table,
        filter_expression="entity_type = :conversation AND escalated = :yes",
        expression_attribute_values={":conversation": "conversation", ":yes": True},
        accept_item=lambda item: item if item.get("conversation_id") else None,
        limit=limit,
    )


def reconcile_dispatches(
    questions: list[dict[str, Any]] | None = None,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Give every waiting student a teacher who is still expected to answer.

    Dispatch happens inside the request that asks for a teacher, which leaves
    two ways for a student to end up waiting on nobody: the dispatch failed or
    found no free teacher at that moment, and nothing tried again; or a teacher
    was offered the question and let the deadline pass, and nothing offered it
    to anyone else. Both are invisible to the student, who simply waits.

    This is the sweep that closes them. It is safe to run repeatedly:
    dispatching a question that already has a live offer is a no-op.
    """
    timestamp = now or _now()
    items = questions if questions is not None else list_teacher_dispatch_questions()

    reassigned = reassign_timed_out_dispatches(items, now=timestamp)

    # Re-read, because reassignment has moved some of them on.
    refreshed = questions if questions is not None else list_teacher_dispatch_questions()
    waiting = [
        item
        for item in refreshed
        if item.get("status") == QuestionStatus.ESCALATED.value
        and not _has_current_dispatch(item, timestamp)
    ]

    dispatched: list[dict[str, Any]] = []
    for item in waiting:
        question_id = str(item.get("question_id") or "")
        if not question_id:
            continue
        result = dispatch_question(question_id, question=dict(item), now=timestamp)
        if result.get("status") in {"dispatched", "no_candidate"}:
            dispatched.append({"questionId": question_id, "status": result["status"]})

    # The chat lane is what a student actually uses, and it records its
    # dispatch on the conversation rather than on a question.
    conversations_waiting = 0
    conversations_dispatched: list[dict[str, Any]] = []
    conversation_sweep = "completed"
    try:
        for conversation in list_escalated_conversations():
            if str(conversation.get("escalation_status") or "") not in {"", "pending"}:
                continue
            if (
                conversation.get("dispatch_status") == "dispatched"
                and conversation.get("dispatched_teacher_id")
                and not _deadline_expired(
                    conversation.get("dispatch_deadline_at"), timestamp
                )
            ):
                continue
            conversation_id = str(conversation.get("conversation_id") or "")
            if not conversation_id:
                continue
            conversations_waiting += 1
            result = dispatch_conversation(
                conversation_id, conversation=dict(conversation), now=timestamp
            )
            if result.get("status") in {"dispatched", "no_candidate"}:
                conversations_dispatched.append(
                    {"conversationId": conversation_id, "status": result["status"]}
                )
    except Exception:  # noqa: BLE001
        logger.warning("Conversation sweep failed", exc_info=True)
        conversation_sweep = "failed"

    return {
        "reassigned": reassigned["processed"],
        "reassignments": reassigned["results"],
        "waiting": len(waiting),
        "dispatched": dispatched,
        "conversationSweep": conversation_sweep,
        "conversationsWaiting": conversations_waiting,
        "conversationsDispatched": conversations_dispatched,
        "generatedAt": timestamp,
    }
