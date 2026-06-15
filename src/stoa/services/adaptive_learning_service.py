"""Adaptive learning memory and reviewed assignment workflows."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from stoa.db.repositories import (
    adaptive_learning_repo,
    ai_teacher_tools_repo,
    practice_repo,
    question_repo,
    user_repo,
)
from stoa.services import (
    ai_teacher_tools_service,
    curriculum_analytics_service,
    curriculum_service,
    learning_profile_service,
    locale_service,
)


ASSIGNMENT_STATUSES = {"draft", "recommended", "assigned", "started", "completed", "skipped", "archived"}
CREATABLE_STATUSES = {"draft", "recommended", "assigned"}
STUDENT_ACTIONS = {"start", "complete", "skip"}
STALE_AFTER_DAYS = 14
AUTOMATION_LEVELS = {"off", "suggest_only", "tutor_approved_batch", "auto_create_reviewed", "future_auto_deliver"}
AUTOMATION_DELIVERY_MODES = {"draft", "recommended", "assigned"}
AUTOMATION_SOURCE_TYPES = {"ai_draft", "curriculum_exercise", "memory_snapshot", "curriculum_topic"}
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_memory_summary(
    *,
    student_id: str,
    user: dict[str, Any],
    subject: str | None = None,
    persist: bool = False,
) -> dict[str, Any]:
    _require_student_visible(student_id, user)
    normalized_subject = _safe_subject(subject) if subject else None
    questions = question_repo.list_by_student(student_id, limit=500).get("Items", [])
    mistakes = practice_repo.get_mistakes(student_id)
    profile = learning_profile_service.build_learning_profile(
        student_id=student_id,
        questions=questions,
        mistakes=mistakes,
    )
    snapshots = _build_memory_snapshots(
        student_id=student_id,
        questions=questions,
        mistakes=mistakes,
        subject=normalized_subject,
    )
    stored = adaptive_learning_repo.list_memory_snapshots(student_id, normalized_subject)
    if persist:
        for snapshot in snapshots:
            adaptive_learning_repo.put_memory_snapshot(snapshot)
        stored = snapshots
    recommendations = _next_practice_recommendations(student_id, profile, snapshots, normalized_subject, user)
    assignments = adaptive_learning_repo.list_assignments(
        student_id=student_id,
        include_archived=_can_manage_assignments(user),
        limit=None,
    )
    return _memory_response(
        student_id=student_id,
        user=user,
        profile=profile,
        generated_snapshots=snapshots,
        stored_snapshots=stored,
        recommendations=recommendations,
        assignments=assignments,
    )


def create_assignment(
    *,
    student_id: str,
    source_type: str,
    source_id: str,
    user: dict[str, Any],
    title: str | None = None,
    status: str = "assigned",
    due_at: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    _require_teacher_or_admin(user)
    if status not in CREATABLE_STATUSES:
        raise HTTPException(status_code=400, detail="Assignment must start as draft, recommended, or assigned")
    item = _create_assignment_item(
        student_id=student_id,
        source_type=source_type,
        source_id=source_id,
        user=user,
        title=title,
        status=status,
        due_at=due_at,
        note=note,
    )
    adaptive_learning_repo.put_assignment(item)
    return assignment_response(item, user=user)


def execute_assignment_automation_batch(
    *,
    student_id: str,
    batch_id: str,
    approved: bool,
    policy: dict[str, Any],
    candidates: list[dict[str, Any]],
    user: dict[str, Any],
) -> dict[str, Any]:
    _require_teacher_or_admin(user)
    _require_student_visible(student_id, user)
    if not approved:
        raise HTTPException(status_code=400, detail="Approved batch execution requires approval")
    if not candidates:
        raise HTTPException(status_code=400, detail="At least one approved candidate is required")
    replay_policy = _automation_policy(policy, student_id=student_id, user=user)
    existing_assignments = adaptive_learning_repo.list_assignments(
        student_id=student_id,
        include_archived=True,
        limit=None,
    )
    preview = preview_assignment_automation_batch(
        student_id=student_id,
        policy=policy,
        user=user,
    )
    if batch_id != preview["batchId"]:
        replay = _automation_duplicate_replay(
            student_id=student_id,
            batch_id=batch_id,
            policy=replay_policy,
            candidates=candidates,
            existing_assignments=existing_assignments,
            user=user,
        )
        if replay:
            return replay
        raise HTTPException(status_code=409, detail="Automation batch preview is stale")
    normalized_policy = preview["policy"]
    selected_by_id = {str(candidate.get("candidateId") or ""): candidate for candidate in preview["selected"]}
    assignment_state = _assignment_signal_state(existing_assignments)
    results: list[dict[str, Any]] = []

    for candidate in candidates:
        requested_candidate = _automation_execution_candidate(candidate, normalized_policy)
        preview_candidate = selected_by_id.get(requested_candidate["candidateId"])
        if not preview_candidate:
            raise HTTPException(status_code=409, detail="Candidate is not selected in current preview")
        normalized_candidate = _automation_execution_candidate(preview_candidate, normalized_policy)
        _require_candidate_matches_preview(requested_candidate, normalized_candidate)
        normalized_candidate["approved"] = requested_candidate["approved"]
        result = _execute_assignment_automation_candidate(
            student_id=student_id,
            batch_id=batch_id,
            policy=normalized_policy,
            candidate=normalized_candidate,
            assignment_state=assignment_state,
            existing_assignments=existing_assignments,
            user=user,
        )
        results.append(result)
        if result.get("assignmentItem"):
            assignment_item = result.pop("assignmentItem")
            existing_assignments.append(assignment_item)
            assignment_state = _assignment_signal_state(existing_assignments)

    return {
        "batchId": batch_id,
        "policyId": normalized_policy["policyId"],
        "studentId": student_id,
        "status": "completed",
        "approved": True,
        "createdBy": _actor_id(user),
        "createdAt": now_iso(),
        "results": results,
        "summary": _automation_execution_summary(results),
        "reviewRequired": True,
        "autonomousDecision": False,
        "locale": locale_contract(user),
    }


def _create_assignment_item(
    *,
    student_id: str,
    source_type: str,
    source_id: str,
    user: dict[str, Any],
    title: str | None = None,
    status: str = "assigned",
    due_at: str | None = None,
    note: str | None = None,
    automation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = _assignment_source(source_type, source_id, student_id, user=user)
    created_at = now_iso()
    item = {
        "assignment_id": automation.get("assignmentId") if automation else f"assignment-{uuid4().hex}",
        "student_id": student_id,
        "status": status,
        "source_type": source["sourceType"],
        "source_id": source_id,
        "title": title or source["title"],
        "subject": source.get("subject"),
        "topic_ids": source.get("topicIds", []),
        "lesson_id": source.get("lessonId"),
        "exercise_id": source.get("exerciseId"),
        "items": source.get("items", []),
        "answer_key": source.get("answerKey", []),
        "rationale": source.get("rationale", ""),
        "created_by": _actor_id(user),
        "created_by_role": str(user.get("role") or ""),
        "reviewed": True,
        "created_at": created_at,
        "updated_at": created_at,
        "assigned_at": created_at if status == "assigned" else None,
        "started_at": None,
        "completed_at": None,
        "skipped_at": None,
        "archived_at": None,
        "due_at": due_at,
        "note": _clean_note(note),
        "student_answer": None,
        "completion_result": None,
    }
    if automation:
        item["automation"] = automation
        item["automation_key"] = automation["automationKey"]
        item["automation_policy_id"] = automation["policyId"]
        item["automation_batch_id"] = automation["batchId"]
        item["automation_candidate_id"] = automation["candidateId"]
        item["delivery_state"] = automation["deliveryState"]
    return item


def preview_assignment_automation_batch(
    *,
    student_id: str,
    policy: dict[str, Any],
    user: dict[str, Any],
    subject: str | None = None,
) -> dict[str, Any]:
    _require_teacher_or_admin(user)
    _require_student_visible(student_id, user)
    normalized_policy = _automation_policy(policy, student_id=student_id, user=user)
    summary = get_memory_summary(student_id=student_id, user=user, subject=subject)
    assignments = adaptive_learning_repo.list_assignments(student_id=student_id, include_archived=True, limit=None)
    assignment_state = _assignment_signal_state(assignments)
    selected: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []

    for recommendation in summary.get("recommendations", []):
        refusal = _automation_refusal(recommendation, normalized_policy, assignment_state)
        candidate = _automation_candidate(recommendation, normalized_policy)
        if refusal:
            refused.append({**candidate, **refusal})
            continue
        if len(selected) >= normalized_policy["maxAssignmentsPerStudent"]:
            refused.append(
                {
                    **candidate,
                    "refusalCode": "max_assignments_reached",
                    "refusalReason": "Policy maximum selected assignments for this student was reached.",
                }
            )
            continue
        selected.append(candidate)
        _mark_automation_candidate_selected(assignment_state, candidate)

    batch = {
        "batchId": _automation_batch_id(student_id, normalized_policy, selected, refused),
        "policyId": normalized_policy["policyId"],
        "policy": normalized_policy,
        "studentId": student_id,
        "createdBy": _actor_id(user),
        "createdAt": now_iso(),
        "status": "preview",
        "selected": selected,
        "refused": refused,
        "summary": _automation_batch_summary(selected, refused),
        "reviewRequired": True,
        "autonomousDecision": False,
        "locale": locale_contract(user),
    }
    return batch


def list_assignments(
    *,
    student_id: str,
    user: dict[str, Any],
    status: str | None = None,
    include_archived: bool = False,
) -> dict[str, Any]:
    _require_student_visible(student_id, user)
    if status and status not in ASSIGNMENT_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported assignment status")
    items = adaptive_learning_repo.list_assignments(
        student_id=student_id,
        status=status,
        include_archived=include_archived and _can_manage_assignments(user),
    )
    visible = [assignment_response(item, user=user) for item in items if _assignment_visible(item, user)]
    return {"items": visible, "count": len(visible), "locale": locale_contract(user)}


def get_assignment(assignment_id: str, user: dict[str, Any]) -> dict[str, Any]:
    item = _existing_assignment(assignment_id)
    if not _assignment_visible(item, user):
        raise HTTPException(status_code=403, detail="Assignment is not visible")
    return assignment_response(item, user=user)


def transition_assignment(
    *,
    assignment_id: str,
    action: str,
    user: dict[str, Any],
    student_answer: str | None = None,
    correct: bool | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    item = _existing_assignment(assignment_id)
    if action in STUDENT_ACTIONS:
        _require_student_assignment_owner(item, user)
    elif action == "archive":
        _require_teacher_or_admin(user)
    else:
        raise HTTPException(status_code=400, detail="Unsupported assignment action")
    if item.get("pending_sequencing_effect"):
        _apply_pending_assignment_effect(item)
        item = _existing_assignment(assignment_id)

    previous_status = str(item.get("status") or "")
    now = now_iso()
    transition_token = f"transition-{uuid4().hex}"
    updates: dict[str, Any] = {"updated_at": now, "transition_token": transition_token}
    side_effect: str | None = None

    if action == "start":
        if previous_status in {"assigned", "recommended"}:
            updates.update(
                {
                    "status": "started",
                    "started_at": item.get("started_at") or now,
                    "sequencing_feedback": _assignment_sequencing_feedback(item, event="started", recorded_at=now),
                }
            )
            side_effect = "started"
        elif previous_status not in {"started", "completed"}:
            raise HTTPException(status_code=409, detail="Assignment cannot be started from its current state")
    elif action == "complete":
        if previous_status not in {"assigned", "recommended", "started", "completed"}:
            raise HTTPException(status_code=409, detail="Assignment cannot be completed from its current state")
        already_completed = previous_status == "completed"
        attempt_count = _assignment_attempt_count(item) if already_completed else _assignment_attempt_count(item) + 1
        completion_result = item.get("completion_result") if already_completed else (
            {"correct": correct, "attemptCount": attempt_count} if correct is not None else None
        )
        sequencing_feedback = item.get("sequencing_feedback") if already_completed else _assignment_sequencing_feedback(
            item,
            event="completed",
            recorded_at=now,
            correct=correct,
            attempt_count=attempt_count,
        )
        updates.update(
            {
                "status": "completed",
                "started_at": item.get("started_at") or now,
                "completed_at": item.get("completed_at") or now,
                "student_answer": item.get("student_answer") if already_completed else student_answer,
                "completion_result": completion_result,
                "sequencing_feedback": sequencing_feedback,
            }
        )
        if previous_status != "completed":
            side_effect = "completed"
    elif action == "skip":
        if previous_status in {"completed", "archived"}:
            raise HTTPException(status_code=409, detail="Completed or archived assignments cannot be skipped")
        updates.update(
            {
                "status": "skipped",
                "skipped_at": item.get("skipped_at") or now,
                "skip_note": _clean_note(note),
                "sequencing_feedback": _assignment_sequencing_feedback(item, event="skipped", recorded_at=now),
            }
        )
        if previous_status != "skipped":
            side_effect = "skipped"
    elif action == "archive":
        updates.update(
            {
                "status": "archived",
                "archived_at": item.get("archived_at") or now,
                "archive_note": _clean_note(note),
                "sequencing_feedback": _assignment_sequencing_feedback(item, event="archived", recorded_at=now),
            }
        )
        if previous_status != "archived":
            side_effect = "archived"

    if side_effect == "completed":
        updates["pending_sequencing_effect"] = _pending_assignment_effect(
            event=side_effect,
            correct=correct,
            transition_token=transition_token,
        )
    updated = adaptive_learning_repo.update_assignment(assignment_id, updates, expected_status=previous_status)
    if not updated:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if updated.get("transition_token") == transition_token and side_effect:
        if side_effect == "completed":
            _apply_pending_assignment_effect(updated)
            curriculum_analytics_service.record_assignment_outcome(updated, correct=correct)
        elif side_effect == "started":
            curriculum_analytics_service.record_assignment_started(updated)
        elif side_effect == "skipped":
            curriculum_analytics_service.record_assignment_skipped(updated)
        elif side_effect == "archived":
            curriculum_analytics_service.record_assignment_archived(updated)
    return assignment_response(updated, user=user)


def parent_progress_signal(student_id: str, user: dict[str, Any]) -> dict[str, Any]:
    if user.get("role") != "parent":
        raise HTTPException(status_code=403, detail="Parent progress signals require parent access")
    _require_student_visible(student_id, user)
    memory = get_memory_summary(student_id=student_id, user=user)
    assignments = list_assignments(student_id=student_id, user=user)
    completed = [item for item in assignments["items"] if item["status"] == "completed"]
    active = [item for item in assignments["items"] if item["status"] in {"assigned", "started", "recommended"}]
    return {
        "studentId": student_id,
        "weakAreas": memory["weakTopics"],
        "recommendations": memory["recommendations"],
        "sequencingSummary": _sequencing_summary(memory["recommendations"], assignments["items"]),
        "assignedPracticeCount": len(active),
        "completedPracticeCount": len(completed),
        "freshness": memory["freshness"],
        "assignments": active[:5],
        "completedAssignments": completed[:5],
        "locale": locale_contract(user),
    }


def locale_contract(user: dict[str, Any]) -> dict[str, Any]:
    effective_locale = locale_service.effective_locale(user)
    return {
        "effectiveLocale": effective_locale,
        "contentLanguage": effective_locale,
        "supportedLocales": sorted(locale_service.SUPPORTED_LOCALES),
        "canonicalValuesStable": True,
    }


def assignment_response(item: dict[str, Any], *, user: dict[str, Any]) -> dict[str, Any]:
    response = {
        "assignmentId": item.get("assignment_id"),
        "studentId": item.get("student_id"),
        "status": item.get("status"),
        "sourceType": item.get("source_type"),
        "sourceId": item.get("source_id"),
        "title": item.get("title"),
        "subject": item.get("subject"),
        "topicIds": item.get("topic_ids") or [],
        "lessonId": item.get("lesson_id"),
        "exerciseId": item.get("exercise_id"),
        "items": item.get("items") or [],
        "rationale": item.get("rationale", ""),
        "createdBy": item.get("created_by"),
        "createdByRole": item.get("created_by_role"),
        "reviewed": bool(item.get("reviewed")),
        "createdAt": item.get("created_at"),
        "updatedAt": item.get("updated_at"),
        "assignedAt": item.get("assigned_at"),
        "startedAt": item.get("started_at"),
        "completedAt": item.get("completed_at"),
        "skippedAt": item.get("skipped_at"),
        "archivedAt": item.get("archived_at"),
        "dueAt": item.get("due_at"),
        "note": item.get("note"),
        "completionResult": item.get("completion_result"),
        "sequencingFeedback": item.get("sequencing_feedback"),
        "locale": locale_contract(user),
    }
    automation = _assignment_automation_response(item, user)
    if automation:
        response["automation"] = automation
    if user.get("role") != "parent":
        response["studentAnswer"] = item.get("student_answer")
    if _can_manage_assignments(user):
        response["answerKey"] = item.get("answer_key") or []
    return response


def _automation_policy(policy: dict[str, Any], *, student_id: str, user: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    policy_id = str(_policy_value(policy, "policyId", "policy_id", default=f"policy-{student_id}"))
    autonomy_level = _choice(str(_policy_value(policy, "autonomyLevel", "autonomy_level", default="suggest_only")), AUTOMATION_LEVELS)
    status = _choice(str(_policy_value(policy, "status", default="active")), {"active", "paused", "off"})
    if autonomy_level == "off":
        status = "off"
    source_types_provided = "sourceTypes" in policy or "source_types" in policy
    requested_source_types = _string_list(_policy_value(policy, "sourceTypes", "source_types", default=[]), allow_blank=False)
    unsupported_source_types = sorted(set(requested_source_types) - AUTOMATION_SOURCE_TYPES)
    if unsupported_source_types:
        raise HTTPException(status_code=400, detail=f"Unsupported automation source type: {unsupported_source_types[0]}")
    if source_types_provided and not requested_source_types:
        raise HTTPException(status_code=400, detail="At least one automation source type is required")
    source_types = requested_source_types if source_types_provided else ["ai_draft", "curriculum_exercise"]
    if not source_types:
        source_types = ["ai_draft", "curriculum_exercise"]
    confidence = str(_policy_value(policy, "confidenceThreshold", "confidence_threshold", default="medium"))
    confidence = _choice(confidence, set(CONFIDENCE_RANK))
    return {
        "policyId": policy_id,
        "targetStudentId": student_id,
        "name": str(_policy_value(policy, "name", default="Controlled assignment automation")),
        "status": status,
        "autonomyLevel": autonomy_level,
        "studentIds": _string_list(_policy_value(policy, "studentIds", "student_ids", default=[])) or [student_id],
        "subjectIds": _string_list(_policy_value(policy, "subjectIds", "subject_ids", default=[])),
        "topicIds": _string_list(_policy_value(policy, "topicIds", "topic_ids", default=[])),
        "sourceTypes": sorted(set(source_types)),
        "maxAssignmentsPerStudent": _positive_int(_policy_value(policy, "maxAssignmentsPerStudent", "max_assignments_per_student", default=3), 3),
        "confidenceThreshold": confidence,
        "freshnessDays": _positive_int(_policy_value(policy, "freshnessDays", "freshness_days", default=STALE_AFTER_DAYS), STALE_AFTER_DAYS),
        "dueInDays": _positive_int(_policy_value(policy, "dueInDays", "due_in_days", default=7), 7),
        "deliveryMode": _choice(str(_policy_value(policy, "deliveryMode", "delivery_mode", default="recommended")), AUTOMATION_DELIVERY_MODES),
        "createdBy": str(_policy_value(policy, "createdBy", "created_by", default=_actor_id(user))),
        "createdAt": str(_policy_value(policy, "createdAt", "created_at", default=now)),
        "updatedAt": now,
        "pausedReason": _clean_note(_policy_value(policy, "pausedReason", "paused_reason", default=None)),
    }


def _automation_refusal(
    recommendation: dict[str, Any],
    policy: dict[str, Any],
    assignment_state: dict[str, Any],
) -> dict[str, str] | None:
    if policy["status"] == "off":
        return {"refusalCode": "automation_off", "refusalReason": "Automation is disabled for this policy."}
    if policy["status"] == "paused":
        return {"refusalCode": "policy_paused", "refusalReason": policy.get("pausedReason") or "Policy is paused."}
    if str(policy["targetStudentId"]) not in set(policy["studentIds"]):
        return {"refusalCode": "student_out_of_scope", "refusalReason": "Candidate student is outside policy scope."}
    if str(recommendation.get("sourceType") or "") not in set(policy["sourceTypes"]):
        return {"refusalCode": "source_type_not_allowed", "refusalReason": "Candidate source type is outside policy scope."}
    if policy["subjectIds"] and str(recommendation.get("subject") or "") not in set(policy["subjectIds"]):
        return {"refusalCode": "subject_out_of_scope", "refusalReason": "Candidate subject is outside policy scope."}
    if policy["topicIds"] and str(recommendation.get("topicId") or "") not in set(policy["topicIds"]):
        return {"refusalCode": "topic_out_of_scope", "refusalReason": "Candidate topic is outside policy scope."}
    confidence = str(recommendation.get("confidence") or "low")
    if CONFIDENCE_RANK.get(confidence, 0) < CONFIDENCE_RANK[policy["confidenceThreshold"]]:
        return {"refusalCode": "low_confidence", "refusalReason": "Candidate confidence is below policy threshold."}
    if _automation_candidate_stale(recommendation, policy["freshnessDays"]):
        return {"refusalCode": "stale_candidate", "refusalReason": "Candidate evidence is outside the policy freshness window."}
    source_key = (str(recommendation.get("sourceType") or ""), str(recommendation.get("sourceId") or ""))
    if source_key in assignment_state["suppressed_sources"] or str(recommendation.get("topicId") or "") in assignment_state["active_topics"]:
        return {"refusalCode": "duplicate_or_active", "refusalReason": "Candidate duplicates active, completed, or archived assignment work."}
    if recommendation.get("reviewRequired") is not True or recommendation.get("autonomousDecision") is not False:
        return {"refusalCode": "review_boundary_missing", "refusalReason": "Candidate does not preserve review-required automation boundaries."}
    return None


def _automation_candidate_stale(recommendation: dict[str, Any], freshness_days: int) -> bool:
    freshness = recommendation.get("freshness") if isinstance(recommendation.get("freshness"), dict) else {}
    if freshness.get("status") == "stale":
        return True
    last_evidence_at = freshness.get("lastEvidenceAt")
    parsed = _parse_time(str(last_evidence_at)) if last_evidence_at else None
    if not parsed:
        return False
    return (datetime.now(timezone.utc) - parsed).days > freshness_days


def _automation_candidate(recommendation: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    topic_id = str(recommendation.get("topicId") or "")
    due_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=policy["dueInDays"])
    return {
        "candidateId": recommendation.get("candidateId"),
        "type": recommendation.get("type"),
        "sourceType": recommendation.get("sourceType"),
        "sourceId": recommendation.get("sourceId"),
        "title": recommendation.get("label"),
        "subject": recommendation.get("subject"),
        "topicId": topic_id,
        "topicIds": [topic_id] if topic_id else [],
        "confidence": recommendation.get("confidence"),
        "freshness": recommendation.get("freshness") or {},
        "rationale": recommendation.get("rationale"),
        "expectedImpact": _automation_expected_impact(recommendation),
        "reviewStatus": "reviewed_source" if recommendation.get("sourceType") in {"ai_draft", "curriculum_exercise"} else "recommendation_review_required",
        "proposedStatus": policy["deliveryMode"],
        "dueAt": due_at.isoformat(),
        "sourceSignals": recommendation.get("sourceSignals") or {},
        "reviewRequired": True,
        "autonomousDecision": False,
    }


def _mark_automation_candidate_selected(assignment_state: dict[str, Any], candidate: dict[str, Any]) -> None:
    source_key = (str(candidate.get("sourceType") or ""), str(candidate.get("sourceId") or ""))
    topic_ids = [str(topic_id) for topic_id in candidate.get("topicIds", []) if topic_id]
    if candidate.get("topicId"):
        topic_ids.append(str(candidate["topicId"]))
    assignment_state["suppressed_sources"].add(source_key)
    assignment_state["active_topics"].update(topic_ids)
    for topic_id in topic_ids:
        assignment_state["topic_statuses"].setdefault(topic_id, set()).add(str(candidate.get("proposedStatus") or "selected"))


def _automation_expected_impact(recommendation: dict[str, Any]) -> str:
    candidate_type = str(recommendation.get("type") or "")
    if candidate_type == "reviewed_ai_draft":
        return "Turn a tutor-reviewed AI practice draft into a controlled assignment candidate."
    if candidate_type == "curriculum_exercise":
        return "Use a published curriculum exercise to reinforce the recommended topic."
    if candidate_type == "remediation_topic":
        return "Flag a weak topic for tutor-reviewed remediation assignment planning."
    return "Keep learning momentum with a reviewed next-work candidate."


def _automation_batch_summary(selected: list[dict[str, Any]], refused: list[dict[str, Any]]) -> dict[str, Any]:
    refused_counts = Counter(str(item.get("refusalCode") or "unknown") for item in refused)
    topics = Counter(str(item.get("topicId") or "") for item in selected if item.get("topicId"))
    return {
        "selectedCount": len(selected),
        "refusedCount": len(refused),
        "topTopics": [topic for topic, _count in topics.most_common(5)],
        "duplicateCount": refused_counts.get("duplicate_or_active", 0),
        "lowConfidenceCount": refused_counts.get("low_confidence", 0),
        "staleCount": refused_counts.get("stale_candidate", 0),
        "reviewRequiredCount": sum(1 for item in selected if item.get("reviewRequired")),
        "refusalCounts": dict(sorted(refused_counts.items())),
    }


def _automation_batch_id(
    student_id: str,
    policy: dict[str, Any],
    selected: list[dict[str, Any]],
    refused: list[dict[str, Any]],
) -> str:
    payload = {
        "studentId": student_id,
        "policyId": policy["policyId"],
        "selected": [item.get("candidateId") for item in selected],
        "refused": [[item.get("candidateId"), item.get("refusalCode")] for item in refused],
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"batch-{digest}"


def _automation_execution_candidate(candidate: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    topic_ids = _string_list(candidate.get("topicIds") or candidate.get("topic_ids"))
    topic_id = str(candidate.get("topicId") or candidate.get("topic_id") or (topic_ids[0] if topic_ids else ""))
    if topic_id and topic_id not in topic_ids:
        topic_ids = [topic_id, *topic_ids]
    source_type = str(candidate.get("sourceType") or candidate.get("source_type") or "")
    proposed_status = str(candidate.get("proposedStatus") or candidate.get("proposed_status") or policy["deliveryMode"])
    proposed_status = _choice(proposed_status, CREATABLE_STATUSES)
    if proposed_status != policy["deliveryMode"]:
        raise HTTPException(status_code=400, detail="Candidate proposed status must match policy delivery mode")
    return {
        "candidateId": str(candidate.get("candidateId") or candidate.get("candidate_id") or ""),
        "type": candidate.get("type"),
        "sourceType": source_type,
        "sourceId": str(candidate.get("sourceId") or candidate.get("source_id") or ""),
        "title": candidate.get("title"),
        "subject": _safe_subject(candidate.get("subject")),
        "topicId": topic_id,
        "topicIds": topic_ids,
        "confidence": str(candidate.get("confidence") or "low"),
        "freshness": candidate.get("freshness") if isinstance(candidate.get("freshness"), dict) else {},
        "rationale": candidate.get("rationale"),
        "expectedImpact": candidate.get("expectedImpact") or candidate.get("expected_impact"),
        "reviewStatus": candidate.get("reviewStatus") or candidate.get("review_status"),
        "proposedStatus": proposed_status,
        "dueAt": candidate.get("dueAt") or candidate.get("due_at"),
        "sourceSignals": candidate.get("sourceSignals") or candidate.get("source_signals") or {},
        "reviewRequired": candidate.get("reviewRequired", candidate.get("review_required", True)),
        "autonomousDecision": candidate.get("autonomousDecision", candidate.get("autonomous_decision", False)),
        "approved": candidate.get("approved", True),
    }


def _require_candidate_matches_preview(requested: dict[str, Any], preview: dict[str, Any]) -> None:
    compared_fields = ("candidateId", "sourceType", "sourceId", "proposedStatus")
    for field in compared_fields:
        if str(requested.get(field) or "") != str(preview.get(field) or ""):
            raise HTTPException(status_code=409, detail="Candidate does not match current preview")


def _execute_assignment_automation_candidate(
    *,
    student_id: str,
    batch_id: str,
    policy: dict[str, Any],
    candidate: dict[str, Any],
    assignment_state: dict[str, Any],
    existing_assignments: list[dict[str, Any]],
    user: dict[str, Any],
) -> dict[str, Any]:
    automation_key = _automation_key(student_id, batch_id, policy, candidate)
    base = _automation_result_base(candidate, automation_key)
    if candidate["approved"] is not True:
        return {**base, "status": "skipped", "reason": "Candidate was not approved for execution."}
    existing_by_key = _find_assignment_by_automation_key(existing_assignments, automation_key)
    if existing_by_key:
        return {
            **base,
            "status": "duplicate",
            "reason": "Automation key already created an assignment.",
            "assignmentId": existing_by_key.get("assignment_id"),
            "assignment": assignment_response(existing_by_key, user=user),
        }
    if candidate["sourceType"] not in {"ai_draft", "curriculum_exercise"}:
        return {
            **base,
            "status": "refused",
            "reason": "Candidate source cannot create a reviewed assignment.",
            "refusalCode": "unsupported_assignment_source",
        }
    existing_by_source = _find_assignment_by_source(existing_assignments, candidate["sourceType"], candidate["sourceId"])
    if existing_by_source:
        return {
            **base,
            "status": "duplicate",
            "reason": "Source already has assignment history for this student.",
            "assignmentId": existing_by_source.get("assignment_id"),
            "assignment": assignment_response(existing_by_source, user=user),
        }
    refusal = _automation_refusal(candidate, policy, assignment_state)
    if refusal:
        return {
            **base,
            "status": "refused",
            "reason": refusal["refusalReason"],
            "refusalCode": refusal["refusalCode"],
        }

    try:
        automation = _automation_assignment_metadata(
            student_id=student_id,
            batch_id=batch_id,
            policy=policy,
            candidate=candidate,
            automation_key=automation_key,
            user=user,
        )
        item = _create_assignment_item(
            student_id=student_id,
            source_type=candidate["sourceType"],
            source_id=candidate["sourceId"],
            user=user,
            title=candidate.get("title"),
            status=candidate["proposedStatus"],
            due_at=candidate.get("dueAt"),
            note=str(candidate.get("rationale") or ""),
            automation=automation,
        )
        stored, created = _put_assignment_if_absent(item)
    except HTTPException as exc:
        return {
            **base,
            "status": "failed" if exc.status_code >= 500 else "refused",
            "reason": str(exc.detail),
            "refusalCode": "source_not_assignable",
        }
    if not created:
        return {
            **base,
            "status": "duplicate",
            "reason": "Source already has assignment history for this student.",
            "assignmentId": stored.get("assignment_id"),
            "assignment": assignment_response(stored, user=user),
        }

    result_status = _automation_delivery_state(candidate["proposedStatus"])
    return {
        **base,
        "status": result_status,
        "reason": "Reviewed assignment created from approved automation batch.",
        "assignmentId": stored.get("assignment_id"),
        "assignment": assignment_response(stored, user=user),
        "assignmentItem": stored,
        "evidence": {
            "policyId": policy["policyId"],
            "batchId": batch_id,
            "candidateId": candidate["candidateId"],
            "sourceType": candidate["sourceType"],
            "sourceId": candidate["sourceId"],
            "deliveryState": result_status,
            "reviewRequired": True,
            "autonomousDecision": False,
        },
    }


def _automation_duplicate_replay(
    *,
    student_id: str,
    batch_id: str,
    policy: dict[str, Any],
    candidates: list[dict[str, Any]],
    existing_assignments: list[dict[str, Any]],
    user: dict[str, Any],
) -> dict[str, Any] | None:
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        normalized_candidate = _automation_execution_candidate(candidate, policy)
        automation_key = _automation_key(student_id, batch_id, policy, normalized_candidate)
        base = _automation_result_base(normalized_candidate, automation_key)
        existing = _find_assignment_by_automation_key(existing_assignments, automation_key)
        if existing:
            results.append(
                {
                    **base,
                    "status": "duplicate",
                    "reason": "Automation key already created an assignment.",
                    "assignmentId": existing.get("assignment_id"),
                    "assignment": assignment_response(existing, user=user),
                }
            )
            continue
        if normalized_candidate["approved"] is not True:
            results.append({**base, "status": "skipped", "reason": "Candidate was not approved for execution."})
            continue
        if normalized_candidate["sourceType"] not in {"ai_draft", "curriculum_exercise"}:
            results.append(
                {
                    **base,
                    "status": "refused",
                    "reason": "Candidate source cannot create a reviewed assignment.",
                    "refusalCode": "unsupported_assignment_source",
                }
            )
            continue
        source_duplicate = _find_assignment_by_source(
            existing_assignments,
            normalized_candidate["sourceType"],
            normalized_candidate["sourceId"],
        )
        if not source_duplicate:
            return None
        results.append(
            {
                **base,
                "status": "duplicate",
                "reason": "Source already has assignment history for this student.",
                "assignmentId": source_duplicate.get("assignment_id"),
                "assignment": assignment_response(source_duplicate, user=user),
            }
        )
    return {
        "batchId": batch_id,
        "policyId": policy["policyId"],
        "studentId": student_id,
        "status": "completed",
        "approved": True,
        "createdBy": _actor_id(user),
        "createdAt": now_iso(),
        "results": results,
        "summary": _automation_execution_summary(results),
        "reviewRequired": True,
        "autonomousDecision": False,
        "locale": locale_contract(user),
    }


def _automation_assignment_metadata(
    *,
    student_id: str,
    batch_id: str,
    policy: dict[str, Any],
    candidate: dict[str, Any],
    automation_key: str,
    user: dict[str, Any],
) -> dict[str, Any]:
    delivery_state = _automation_delivery_state(candidate["proposedStatus"])
    return {
        "assignmentId": _automation_source_assignment_id(student_id, candidate),
        "automationKey": automation_key,
        "policyId": policy["policyId"],
        "batchId": batch_id,
        "candidateId": candidate["candidateId"],
        "studentId": student_id,
        "autonomyLevel": policy["autonomyLevel"],
        "deliveryMode": policy["deliveryMode"],
        "deliveryState": delivery_state,
        "createdBy": _actor_id(user),
        "createdByRole": str(user.get("role") or ""),
        "createdAt": now_iso(),
        "sourceType": candidate["sourceType"],
        "sourceId": candidate["sourceId"],
        "sourceSignals": candidate.get("sourceSignals") or {},
        "expectedImpact": candidate.get("expectedImpact"),
        "reviewStatus": candidate.get("reviewStatus"),
        "reviewRequired": True,
        "autonomousDecision": False,
        "explanation": _automation_assignment_explanation(candidate, policy),
        "resultEvidence": {
            "policyStatus": policy["status"],
            "confidence": candidate.get("confidence"),
            "subject": candidate.get("subject"),
            "topicIds": candidate.get("topicIds") or [],
            "proposedStatus": candidate["proposedStatus"],
        },
    }


def _automation_result_base(candidate: dict[str, Any], automation_key: str) -> dict[str, Any]:
    return {
        "candidateId": candidate["candidateId"],
        "sourceType": candidate["sourceType"],
        "sourceId": candidate["sourceId"],
        "automationKey": automation_key,
    }


def _automation_key(
    student_id: str,
    batch_id: str,
    policy: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    payload = {
        "studentId": student_id,
        "batchId": batch_id,
        "policyId": policy["policyId"],
        "candidateId": candidate["candidateId"],
        "sourceType": candidate["sourceType"],
        "sourceId": candidate["sourceId"],
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    return f"automation-{digest}"


def _automation_source_assignment_id(student_id: str, candidate: dict[str, Any]) -> str:
    payload = {
        "studentId": student_id,
        "sourceType": candidate["sourceType"],
        "sourceId": candidate["sourceId"],
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    return f"assignment-source-{digest}"


def _automation_delivery_state(status: str) -> str:
    if status == "draft":
        return "created"
    if status == "recommended":
        return "delivered"
    if status == "assigned":
        return "assigned"
    return "created"


def _automation_execution_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(item.get("status") or "unknown") for item in results)
    return {
        "totalCount": len(results),
        "createdCount": counts.get("created", 0),
        "assignedCount": counts.get("assigned", 0),
        "deliveredCount": counts.get("delivered", 0),
        "skippedCount": counts.get("skipped", 0),
        "refusedCount": counts.get("refused", 0),
        "duplicateCount": counts.get("duplicate", 0),
        "failedCount": counts.get("failed", 0),
        "resultCounts": dict(sorted(counts.items())),
    }


def _find_assignment_by_automation_key(assignments: list[dict[str, Any]], automation_key: str) -> dict[str, Any] | None:
    for assignment in assignments:
        if assignment.get("automation_key") == automation_key:
            return assignment
        automation = assignment.get("automation") if isinstance(assignment.get("automation"), dict) else {}
        if automation.get("automationKey") == automation_key:
            return assignment
    return None


def _find_assignment_by_source(
    assignments: list[dict[str, Any]],
    source_type: str,
    source_id: str,
) -> dict[str, Any] | None:
    for assignment in assignments:
        if assignment.get("source_type") == source_type and assignment.get("source_id") == source_id:
            return assignment
    return None


def _put_assignment_if_absent(item: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    put_if_absent = getattr(adaptive_learning_repo, "put_assignment_if_absent", None)
    if callable(put_if_absent):
        return put_if_absent(item)
    existing = adaptive_learning_repo.get_assignment(str(item["assignment_id"]))
    if existing:
        return existing, False
    adaptive_learning_repo.put_assignment(item)
    return item, True


def _assignment_automation_response(item: dict[str, Any], user: dict[str, Any]) -> dict[str, Any] | None:
    automation = item.get("automation")
    if not isinstance(automation, dict):
        return None
    response = {
        "policyId": automation.get("policyId"),
        "batchId": automation.get("batchId"),
        "candidateId": automation.get("candidateId"),
        "autonomyLevel": automation.get("autonomyLevel"),
        "deliveryState": automation.get("deliveryState") or item.get("delivery_state"),
        "reviewRequired": automation.get("reviewRequired", True),
        "autonomousDecision": automation.get("autonomousDecision", False),
        "explanation": automation.get("explanation"),
        "createdBy": automation.get("createdBy"),
        "createdAt": automation.get("createdAt"),
    }
    if _can_manage_assignments(user):
        response.update(
            {
                "automationKey": automation.get("automationKey"),
                "deliveryMode": automation.get("deliveryMode"),
                "sourceSignals": automation.get("sourceSignals") or {},
                "resultEvidence": automation.get("resultEvidence") or {},
            }
        )
    return response


def _automation_assignment_explanation(candidate: dict[str, Any], policy: dict[str, Any]) -> str:
    topic = candidate.get("topicId") or "the current learning target"
    if policy["autonomyLevel"] == "tutor_approved_batch":
        return f"Tutor-approved practice was assigned for {topic} based on recent learning signals."
    return f"Reviewed practice was prepared for {topic} based on recent learning signals."


def _choice(value: str, allowed: set[str]) -> str:
    if value not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported value: {value}")
    return value


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)


def _policy_value(policy: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in policy:
            return policy[key]
    return default


def _string_list(value: Any, *, allow_blank: bool = True) -> list[str]:
    if isinstance(value, str):
        if not value.strip() and not allow_blank:
            raise HTTPException(status_code=400, detail="Blank policy values are not supported")
        return [value] if value else []
    if not value:
        return []
    if isinstance(value, list):
        if not allow_blank and any(not str(item).strip() for item in value):
            raise HTTPException(status_code=400, detail="Blank policy values are not supported")
        return [str(item) for item in value if item]
    return []


def _assignment_attempt_count(item: dict[str, Any]) -> int:
    result = item.get("completion_result") if isinstance(item.get("completion_result"), dict) else {}
    try:
        return int(result.get("attemptCount") or 0)
    except (TypeError, ValueError):
        return 0


def _pending_assignment_effect(
    *,
    event: str,
    correct: bool | None,
    transition_token: str,
) -> dict[str, Any]:
    return {
        "state": "pending",
        "event": event,
        "correct": correct,
        "transitionToken": transition_token,
    }


def _apply_pending_assignment_effect(item: dict[str, Any]) -> None:
    effect = item.get("pending_sequencing_effect")
    if not isinstance(effect, dict) or not effect.get("event") or effect.get("state") not in {"pending", "processing"}:
        return
    claimed = _claim_pending_assignment_effect(item, effect)
    if not claimed:
        return
    claimed_effect = claimed.get("pending_sequencing_effect") or {}
    event = str(claimed_effect.get("event"))
    correct = claimed_effect.get("correct") if isinstance(claimed_effect.get("correct"), bool) else None
    if event == "completed":
        _record_assignment_progress(claimed, correct=correct, student_answer=None)
    adaptive_learning_repo.update_assignment(
        str(claimed.get("assignment_id") or ""),
        {"pending_sequencing_effect": {}, "sequencing_effect_applied_at": now_iso()},
        expected_status=str(claimed.get("status") or ""),
        expected_pending_token=str(claimed_effect.get("transitionToken") or ""),
        expected_pending_state="processing",
    )


def _claim_pending_assignment_effect(item: dict[str, Any], effect: dict[str, Any]) -> dict[str, Any] | None:
    token = str(effect.get("transitionToken") or "")
    if not token:
        return None
    claim_token = f"effect-claim-{uuid4().hex}"
    claimed_effect = {**effect, "state": "processing", "claimToken": claim_token}
    claimed = adaptive_learning_repo.update_assignment(
        str(item.get("assignment_id") or ""),
        {"pending_sequencing_effect": claimed_effect},
        expected_status=str(item.get("status") or ""),
        expected_pending_token=token,
        expected_pending_state=str(effect.get("state") or "pending"),
    )
    if not claimed:
        return None
    current_effect = claimed.get("pending_sequencing_effect") or {}
    if current_effect.get("claimToken") != claim_token or current_effect.get("state") != "processing":
        return None
    return claimed


def _assignment_sequencing_feedback(
    item: dict[str, Any],
    *,
    event: str,
    recorded_at: str,
    correct: bool | None = None,
    attempt_count: int | None = None,
) -> dict[str, Any]:
    topic_ids = [str(topic_id) for topic_id in item.get("topic_ids", []) if topic_id]
    feedback: dict[str, Any] = {
        "event": event,
        "recordedAt": recorded_at,
        "sourceType": item.get("source_type"),
        "sourceId": item.get("source_id"),
        "subject": item.get("subject"),
        "topicIds": topic_ids,
        "remediationTopicIds": topic_ids if event in {"completed", "skipped"} and correct is False else [],
        "rankingEffect": _ranking_effect(event, correct),
    }
    if correct is not None:
        feedback["correct"] = correct
    if attempt_count is not None:
        feedback["attemptCount"] = attempt_count
    return feedback


def _ranking_effect(event: str, correct: bool | None) -> str:
    if event == "started":
        return "active_assignment_suppresses_duplicates"
    if event == "completed" and correct is False:
        return "completion_adds_remediation_pressure"
    if event == "completed":
        return "completion_reduces_exact_source_priority"
    if event == "skipped":
        return "skip_temporarily_reduces_priority"
    if event == "archived":
        return "archive_suppresses_exact_source"
    return "none"


def _sequencing_summary(
    recommendations: list[dict[str, Any]],
    assignments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    assignment_items = assignments or []
    status_counts = Counter(str(item.get("status") or "") for item in assignment_items)
    top = recommendations[0] if recommendations else {}
    return {
        "recommendedCount": len(recommendations),
        "topCandidateType": top.get("type"),
        "topTopicId": top.get("topicId"),
        "topConfidence": top.get("confidence"),
        "activeAssignments": sum(status_counts.get(status, 0) for status in ("recommended", "assigned", "started")),
        "completedAssignments": status_counts.get("completed", 0),
        "skippedAssignments": status_counts.get("skipped", 0),
        "archivedAssignments": status_counts.get("archived", 0),
        "explanation": _sequencing_summary_explanation(recommendations, status_counts),
    }


def _sequencing_summary_explanation(recommendations: list[dict[str, Any]], status_counts: Counter[str]) -> str:
    if not recommendations:
        if any(status_counts.get(status, 0) for status in ("recommended", "assigned", "started")):
            return "Active reviewed assignments already cover the current sequencing priorities."
        return "No reviewed next-work recommendation is available from current signals."
    if status_counts.get("skipped", 0):
        return "Skipped work lowers priority temporarily while remediation remains available if evidence stays weak."
    if status_counts.get("completed", 0):
        return "Completed assignments reduce exact-source repeats while nearby remediation can still be recommended."
    return str(recommendations[0].get("rationale") or "Recommendations are based on recent learning and assignment signals.")


def _build_memory_snapshots(
    *,
    student_id: str,
    questions: list[dict[str, Any]],
    mistakes: list[dict[str, Any]],
    subject: str | None,
) -> list[dict[str, Any]]:
    now = now_iso()
    topic_counts: Counter[tuple[str, str]] = Counter()
    evidence: dict[tuple[str, str], list[str]] = {}
    latest: dict[tuple[str, str], str] = {}
    feedback_by_topic: dict[tuple[str, str], list[int]] = {}

    for question in questions:
        question_subject = _safe_subject(question.get("subject"))
        if subject and question_subject != subject:
            continue
        question_id = str(question.get("question_id") or question.get("id") or "")
        timestamp = str(question.get("created_at") or question.get("createdAt") or now)
        labels = list(question.get("knowledge_points") or [])
        labels.extend(_topic_labels(question.get("topic_seeds")))
        if not labels:
            labels = [question_subject]
        for label in labels:
            topic_id = learning_profile_service.normalize_topic_id(str(label))
            key = (question_subject, topic_id)
            topic_counts[key] += 1
            evidence.setdefault(key, [])
            if question_id and question_id not in evidence[key]:
                evidence[key].append(question_id)
            if timestamp > latest.get(key, ""):
                latest[key] = timestamp
            feedback = question.get("student_feedback")
            if isinstance(feedback, int):
                feedback_by_topic.setdefault(key, []).append(feedback)

    for mistake in mistakes:
        mistake_subject = _safe_subject(mistake.get("subject_id") or mistake.get("subject"))
        if subject and mistake_subject != subject:
            continue
        topic_id = learning_profile_service.normalize_topic_id(str(mistake.get("topic_id") or "general"))
        key = (mistake_subject, topic_id)
        topic_counts[key] += 1
        timestamp = str(mistake.get("created_at") or now)
        if timestamp > latest.get(key, ""):
            latest[key] = timestamp

    snapshots = []
    for (subject_id, topic_id), count in topic_counts.most_common(20):
        feedback_values = feedback_by_topic.get((subject_id, topic_id), [])
        mastered = bool(feedback_values and sum(feedback_values) / len(feedback_values) >= 4 and count <= 2)
        snapshots.append(
            {
                "student_id": student_id,
                "subject": subject_id,
                "topic_id": topic_id,
                "strengths": ["Positive feedback on recent answers"] if mastered else [],
                "weak_topics": [topic_id] if not mastered else [],
                "mastered_concepts": [topic_id] if mastered else [],
                "struggling_concepts": [topic_id] if not mastered else [],
                "preferred_explanation_style": "step_by_step",
                "recent_questions": evidence.get((subject_id, topic_id), [])[:5],
                "recent_curriculum_progress": _progress_for_topic(student_id, subject_id, topic_id),
                "recent_exercise_attempts": _mistake_attempts_for_topic(mistakes, subject_id, topic_id),
                "teacher_notes": [],
                "recommended_next_steps": _recommended_steps(subject_id, topic_id, mastered),
                "freshness": _freshness(latest.get((subject_id, topic_id))),
                "last_updated_at": now,
            }
        )
    return snapshots


def _memory_response(
    *,
    student_id: str,
    user: dict[str, Any],
    profile: dict[str, Any],
    generated_snapshots: list[dict[str, Any]],
    stored_snapshots: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> dict[str, Any]:
    role = str(user.get("role") or "")
    visible_snapshots = stored_snapshots or generated_snapshots
    weak_topics = profile.get("weakTopics", [])
    if role == "parent":
        visible_snapshots = [_parent_snapshot(snapshot) for snapshot in visible_snapshots]
        weak_topics = [_parent_weak_topic(topic) for topic in weak_topics]
    return {
        "studentId": student_id,
        "roleView": "tutor" if role in {"teacher", "tutor", "admin"} else role,
        "locale": locale_contract(user),
        "subjects": profile.get("subjects", []),
        "subjectActivity": profile.get("subjectActivity", []),
        "weakTopics": weak_topics,
        "strengthTopics": profile.get("strengthTopics", []),
        "memorySnapshots": visible_snapshots,
        "recommendations": recommendations,
        "sequencingSummary": _sequencing_summary(recommendations, assignments),
        "freshness": _overall_freshness(visible_snapshots),
        "updatedAt": now_iso(),
    }


def _assignment_source(source_type: str, source_id: str, student_id: str, *, user: dict[str, Any]) -> dict[str, Any]:
    if source_type == "curriculum_exercise":
        exercise = practice_repo.get_challenge(source_id)
        if not exercise:
            raise HTTPException(status_code=404, detail="Curriculum exercise not found")
        return {
            "sourceType": "curriculum_exercise",
            "title": exercise.get("title") or exercise.get("prompt") or source_id,
            "subject": _safe_subject(exercise.get("subject_id")),
            "topicIds": [exercise.get("topic_id")] if exercise.get("topic_id") else [],
            "lessonId": exercise.get("lesson_id"),
            "exerciseId": exercise.get("challenge_id"),
            "items": [curriculum_service._build_exercise(exercise, include_answer_key=False)],  # noqa: SLF001
            "answerKey": [{"exerciseId": source_id, "answer": exercise.get("answer_key") or exercise.get("correct_answer")}],
            "rationale": "Assigned from reviewed curriculum exercise.",
        }
    if source_type == "ai_draft":
        draft = ai_teacher_tools_repo.get_draft(source_id)
        if not draft:
            raise HTTPException(status_code=404, detail="AI teacher draft not found")
        ai_teacher_tools_service._require_can_view_draft(draft, user)  # noqa: SLF001
        if draft.get("draft_type") != "practice_exercise" or draft.get("status") != "accepted":
            raise HTTPException(status_code=409, detail="Only accepted practice exercise drafts can be assigned")
        if str(draft.get("student_id") or "") != student_id:
            raise HTTPException(status_code=400, detail="Draft does not belong to the requested student")
        return {
            "sourceType": "ai_draft",
            "title": "Reviewed practice exercise",
            "subject": draft.get("subject"),
            "topicIds": draft.get("topic_ids") or [],
            "lessonId": None,
            "exerciseId": None,
            "items": draft.get("items") or [],
            "answerKey": draft.get("answer_key") or [],
            "rationale": "Assigned from tutor-reviewed AI exercise draft.",
        }
    raise HTTPException(status_code=400, detail="Unsupported assignment source type")


def _record_assignment_progress(item: dict[str, Any], *, correct: bool | None, student_answer: str | None) -> None:
    exercise_id = item.get("exercise_id")
    lesson_id = item.get("lesson_id")
    if not exercise_id:
        return
    if correct is True and lesson_id:
        lesson = practice_repo.get_lesson(str(lesson_id))
        if lesson:
            practice_repo.mark_lesson_completed(str(item["student_id"]), lesson)
        return
    if correct is not False:
        return
    practice_repo.record_attempt(
        str(item["student_id"]),
        str(exercise_id),
        False,
        subject_id=str(item.get("subject") or ""),
        lesson_id=str(lesson_id or ""),
        topic_id=str((item.get("topic_ids") or [""])[0]),
        attempt_id=f"assignment-{item.get('assignment_id')}",
    )


def _next_practice_recommendations(
    student_id: str,
    profile: dict[str, Any],
    snapshots: list[dict[str, Any]],
    subject: str | None,
    user: dict[str, Any],
) -> list[dict[str, Any]]:
    assignments = adaptive_learning_repo.list_assignments(student_id=student_id, include_archived=True, limit=None)
    assignment_state = _assignment_signal_state(assignments)
    signal_index = _sequencing_signal_index(profile, snapshots, subject)
    drafts = _safe_reviewed_ai_drafts(student_id, user) if _can_manage_assignments(user) else []
    candidates: list[dict[str, Any]] = []

    for signal in signal_index.values():
        if _topic_has_active_assignment(signal, assignment_state):
            continue
        candidates.append(_remediation_candidate(signal, assignment_state))
        candidates.extend(_curriculum_exercise_candidates(signal, assignment_state))
        candidates.extend(_reviewed_draft_candidates(signal, drafts, assignment_state))

    if not candidates:
        candidates.extend(_continuation_candidates(snapshots, subject, assignment_state))

    ranked = sorted(
        _dedupe_candidates(candidate for candidate in candidates if not _candidate_suppressed(candidate, assignment_state)),
        key=lambda candidate: (-candidate["score"], candidate["candidateId"]),
    )
    return [_recommendation_response(candidate) for candidate in ranked[:5]]


def _sequencing_signal_index(
    profile: dict[str, Any],
    snapshots: list[dict[str, Any]],
    subject: str | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    signals: dict[tuple[str, str], dict[str, Any]] = {}
    for position, topic in enumerate(profile.get("weakTopics", [])[:10]):
        topic_subject = _safe_subject(topic.get("subject"))
        if subject and topic_subject != subject:
            continue
        topic_id = str(topic.get("topicId") or topic.get("topic_id") or "")
        if not topic_id:
            continue
        signal = signals.setdefault(
            (topic_subject, topic_id),
            _empty_signal(topic_subject, topic_id, topic.get("label") or topic_id),
        )
        signal["weakTopicCount"] = max(signal["weakTopicCount"], int(topic.get("count") or 1))
        signal["profileRank"] = min(signal["profileRank"], position + 1)
        signal["latestEvidenceAt"] = topic.get("latestEvidenceAt") or signal.get("latestEvidenceAt")

    for snapshot in snapshots:
        topic_subject = _safe_subject(snapshot.get("subject"))
        if subject and topic_subject != subject:
            continue
        topic_id = str(snapshot.get("topic_id") or "")
        if not topic_id:
            continue
        signal = signals.setdefault((topic_subject, topic_id), _empty_signal(topic_subject, topic_id, topic_id))
        signal["snapshotWeak"] = bool(snapshot.get("weak_topics") or snapshot.get("struggling_concepts"))
        signal["mistakeAttempts"] = max(signal["mistakeAttempts"], len(snapshot.get("recent_exercise_attempts") or []))
        signal["progressCount"] = max(signal["progressCount"], len(snapshot.get("recent_curriculum_progress") or []))
        freshness = snapshot.get("freshness") or {}
        signal["freshness"] = freshness or signal.get("freshness")
        signal["latestEvidenceAt"] = (
            freshness.get("lastEvidenceAt")
            or snapshot.get("last_updated_at")
            or signal.get("latestEvidenceAt")
        )
    return signals


def _empty_signal(subject: str, topic_id: str, label: str) -> dict[str, Any]:
    return {
        "subject": subject,
        "topicId": topic_id,
        "label": label,
        "weakTopicCount": 0,
        "profileRank": 999,
        "snapshotWeak": False,
        "mistakeAttempts": 0,
        "progressCount": 0,
        "freshness": {"status": "unknown", "lastEvidenceAt": None},
        "latestEvidenceAt": None,
    }


def _assignment_signal_state(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "active_topics": set(),
        "skipped_topics": set(),
        "suppressed_sources": set(),
        "topic_statuses": {},
    }
    for assignment in assignments:
        status = str(assignment.get("status") or "")
        source_key = (str(assignment.get("source_type") or ""), str(assignment.get("source_id") or ""))
        topic_ids = [str(topic_id) for topic_id in assignment.get("topic_ids", []) if topic_id]
        if status in {"recommended", "assigned", "started"}:
            state["active_topics"].update(topic_ids)
            state["suppressed_sources"].add(source_key)
        if status in {"completed", "archived"}:
            state["suppressed_sources"].add(source_key)
        if status == "skipped":
            state["skipped_topics"].update(topic_ids)
        for topic_id in topic_ids:
            state["topic_statuses"].setdefault(topic_id, set()).add(status)
    return state


def _topic_has_active_assignment(signal: dict[str, Any], assignment_state: dict[str, Any]) -> bool:
    return signal["topicId"] in assignment_state["active_topics"]


def _remediation_candidate(signal: dict[str, Any], assignment_state: dict[str, Any]) -> dict[str, Any]:
    score = 50 + (signal["weakTopicCount"] * 6) + (signal["mistakeAttempts"] * 4)
    if signal["snapshotWeak"]:
        score += 8
    if signal["topicId"] in assignment_state["skipped_topics"]:
        score -= 12
    return _candidate(
        candidate_type="remediation_topic",
        source_type="memory_snapshot",
        source_id=f"{signal['subject']}:{signal['topicId']}",
        signal=signal,
        label=signal["label"],
        rationale="Recent learning evidence points to this topic as the next reviewed remediation area.",
        score=score,
        review_flags=["tutor_review_required"],
        source_signals=_source_signals(signal, assignment_state, reviewed_draft=False, curriculum_available=False),
    )


def _curriculum_exercise_candidates(signal: dict[str, Any], assignment_state: dict[str, Any]) -> list[dict[str, Any]]:
    exercises = _safe_curriculum_exercises(signal["subject"], signal["topicId"])
    candidates = []
    for exercise in exercises[:2]:
        exercise_id = str(exercise.get("id") or "")
        if not exercise_id:
            continue
        score = 64 + (signal["weakTopicCount"] * 6) + (signal["mistakeAttempts"] * 4)
        if signal["topicId"] in assignment_state["skipped_topics"]:
            score -= 10
        candidates.append(
            _candidate(
                candidate_type="curriculum_exercise",
                source_type="curriculum_exercise",
                source_id=exercise_id,
                signal=signal,
                label=str(exercise.get("prompt") or exercise.get("title") or signal["label"]),
                rationale="A reviewed curriculum exercise is available for this weak topic.",
                score=score,
                review_flags=["tutor_review_required", "published_curriculum_only"],
                source_signals=_source_signals(signal, assignment_state, reviewed_draft=False, curriculum_available=True),
            )
        )
    return candidates


def _reviewed_draft_candidates(
    signal: dict[str, Any],
    drafts: list[dict[str, Any]],
    assignment_state: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = []
    for draft in drafts:
        topic_ids = {str(topic_id) for topic_id in draft.get("topic_ids", [])}
        draft_subject = _safe_subject(draft.get("subject"))
        if signal["topicId"] not in topic_ids or draft_subject != signal["subject"]:
            continue
        draft_id = str(draft.get("draft_id") or "")
        if not draft_id:
            continue
        score = 70 + (signal["weakTopicCount"] * 5) + (signal["mistakeAttempts"] * 3)
        candidates.append(
            _candidate(
                candidate_type="reviewed_ai_draft",
                source_type="ai_draft",
                source_id=draft_id,
                signal=signal,
                label=str(draft.get("title") or "Reviewed practice exercise"),
                rationale="A tutor-reviewed AI practice draft matches this learning need.",
                score=score,
                review_flags=["accepted_draft_only", "tutor_review_required"],
                source_signals=_source_signals(signal, assignment_state, reviewed_draft=True, curriculum_available=False),
            )
        )
    return candidates


def _continuation_candidates(
    snapshots: list[dict[str, Any]],
    subject: str | None,
    assignment_state: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = []
    for snapshot in snapshots:
        topic_subject = _safe_subject(snapshot.get("subject"))
        topic_id = str(snapshot.get("topic_id") or "")
        if not topic_id or (subject and topic_subject != subject) or topic_id in assignment_state["active_topics"]:
            continue
        signal = _empty_signal(topic_subject, topic_id, topic_id)
        signal["freshness"] = snapshot.get("freshness") or signal["freshness"]
        signal["latestEvidenceAt"] = signal["freshness"].get("lastEvidenceAt") or snapshot.get("last_updated_at")
        candidates.append(
            _candidate(
                candidate_type="continuation_lesson",
                source_type="curriculum_topic",
                source_id=f"{topic_subject}:{topic_id}",
                signal=signal,
                label=topic_id,
                rationale="Continue with one short reviewed practice item to keep learning memory fresh.",
                score=30,
                review_flags=["tutor_review_required"],
                source_signals=_source_signals(signal, assignment_state, reviewed_draft=False, curriculum_available=False),
            )
        )
        if candidates:
            break
    return candidates


def _safe_curriculum_exercises(subject: str, topic_id: str) -> list[dict[str, Any]]:
    try:
        return curriculum_service.list_exercises(subject_id=subject, topic_id=topic_id, include_preview=False).get("items", [])
    except Exception:  # pragma: no cover - defensive around optional data sources in partial test doubles
        return []


def _safe_reviewed_ai_drafts(student_id: str, user: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        drafts = ai_teacher_tools_repo.list_drafts(
            student_id=student_id,
            status="accepted",
            draft_type="practice_exercise",
            limit=None,
        )
        return [draft for draft in drafts if ai_teacher_tools_service._can_view_draft(draft, user)]  # noqa: SLF001
    except Exception:  # pragma: no cover - defensive around optional data sources in partial test doubles
        return []


def _candidate(
    *,
    candidate_type: str,
    source_type: str,
    source_id: str,
    signal: dict[str, Any],
    label: str,
    rationale: str,
    score: int,
    review_flags: list[str],
    source_signals: dict[str, Any],
) -> dict[str, Any]:
    freshness = signal.get("freshness") or {"status": "unknown", "lastEvidenceAt": signal.get("latestEvidenceAt")}
    return {
        "candidateId": f"{candidate_type}:{source_id}",
        "type": candidate_type,
        "sourceType": source_type,
        "sourceId": source_id,
        "subject": signal["subject"],
        "topicId": signal["topicId"],
        "label": label,
        "rationale": rationale,
        "confidence": _confidence_bucket(score),
        "freshness": {
            "status": freshness.get("status", "unknown"),
            "lastEvidenceAt": freshness.get("lastEvidenceAt") or signal.get("latestEvidenceAt"),
            "source": "adaptive_sequencing",
        },
        "sourceSignals": source_signals,
        "reviewRequired": True,
        "autonomousDecision": False,
        "reviewFlags": sorted(set(review_flags)),
        "score": score,
    }


def _source_signals(
    signal: dict[str, Any],
    assignment_state: dict[str, Any],
    *,
    reviewed_draft: bool,
    curriculum_available: bool,
) -> dict[str, Any]:
    return {
        "weakTopicCount": signal["weakTopicCount"],
        "mistakeAttempts": signal["mistakeAttempts"],
        "curriculumProgressCount": signal["progressCount"],
        "reviewedDraftAvailable": reviewed_draft,
        "curriculumExerciseAvailable": curriculum_available,
        "assignmentStatuses": sorted(assignment_state["topic_statuses"].get(signal["topicId"], set())),
    }


def _candidate_suppressed(candidate: dict[str, Any], assignment_state: dict[str, Any]) -> bool:
    source_key = (candidate["sourceType"], candidate["sourceId"])
    if source_key in assignment_state["suppressed_sources"]:
        return True
    return candidate["topicId"] in assignment_state["active_topics"]


def _dedupe_candidates(candidates: Any) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        existing = best.get(candidate["candidateId"])
        if not existing or candidate["score"] > existing["score"]:
            best[candidate["candidateId"]] = candidate
    return list(best.values())


def _recommendation_response(candidate: dict[str, Any]) -> dict[str, Any]:
    response = dict(candidate)
    response.pop("score", None)
    return response


def _confidence_bucket(score: int) -> str:
    if score >= 85:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def _require_student_visible(student_id: str, user: dict[str, Any]) -> None:
    role = str(user.get("role") or "")
    if role == "student" and user.get("sub") == student_id:
        return
    if role in {"teacher", "tutor", "admin"}:
        return
    if role == "parent" and _parent_can_view(student_id, user):
        return
    raise HTTPException(status_code=403, detail="Student is not visible to this user")


def _parent_can_view(student_id: str, user: dict[str, Any]) -> bool:
    parent_id = str(user.get("sub") or "")
    profile = user_repo.get_user(student_id)
    if profile and profile.get("parent_id") == parent_id:
        return True
    return any(
        binding.get("student_id") == student_id and binding.get("status", "active") == "active"
        for binding in user_repo.list_parent_student_bindings(parent_id)
    )


def _assignment_visible(item: dict[str, Any], user: dict[str, Any]) -> bool:
    try:
        _require_student_visible(str(item.get("student_id") or ""), user)
    except HTTPException:
        return False
    if item.get("status") == "draft" and not _can_manage_assignments(user):
        return False
    if item.get("status") == "archived" and not _can_manage_assignments(user):
        return False
    return True


def _require_student_assignment_owner(item: dict[str, Any], user: dict[str, Any]) -> None:
    if user.get("role") != "student" or user.get("sub") != item.get("student_id"):
        raise HTTPException(status_code=403, detail="Only the assigned student can update assignment progress")


def _require_teacher_or_admin(user: dict[str, Any]) -> None:
    if user.get("role") not in {"teacher", "tutor", "admin"}:
        raise HTTPException(status_code=403, detail="Tutor or admin access required")


def _can_manage_assignments(user: dict[str, Any]) -> bool:
    return user.get("role") in {"teacher", "tutor", "admin"}


def _existing_assignment(assignment_id: str) -> dict[str, Any]:
    item = adaptive_learning_repo.get_assignment(assignment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return item


def _progress_for_topic(student_id: str, subject: str, topic_id: str) -> list[dict[str, Any]]:
    return [
        {
            "lessonId": item.get("lesson_id"),
            "status": item.get("status"),
            "completedAt": item.get("completed_at"),
        }
        for item in practice_repo.get_progress(student_id, subject)
        if item.get("topic_id") == topic_id
    ][:5]


def _mistake_attempts_for_topic(mistakes: list[dict[str, Any]], subject: str, topic_id: str) -> list[dict[str, Any]]:
    return [
        {
            "challengeId": item.get("challenge_id"),
            "lessonId": item.get("lesson_id"),
            "createdAt": item.get("created_at"),
        }
        for item in mistakes
        if _safe_subject(item.get("subject_id") or item.get("subject")) == subject
        and learning_profile_service.normalize_topic_id(str(item.get("topic_id") or "")) == topic_id
    ][:5]


def _recommended_steps(subject: str, topic_id: str, mastered: bool) -> list[str]:
    if mastered:
        return [f"Keep {topic_id} fresh with one mixed {subject} practice item."]
    return [f"Review {topic_id} with a tutor-approved practice item."]


def _freshness(last_seen_at: str | None) -> dict[str, Any]:
    if not last_seen_at:
        return {"status": "stale", "lastEvidenceAt": None, "staleAfterDays": STALE_AFTER_DAYS}
    parsed = _parse_time(last_seen_at)
    age_days = None
    status = "fresh"
    if parsed:
        age_days = (datetime.now(timezone.utc) - parsed).days
        status = "stale" if age_days > STALE_AFTER_DAYS else "fresh"
    return {
        "status": status,
        "lastEvidenceAt": last_seen_at,
        "ageDays": age_days,
        "staleAfterDays": STALE_AFTER_DAYS,
    }


def _overall_freshness(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [snapshot.get("freshness", {}).get("status") for snapshot in snapshots]
    if not statuses:
        return {"status": "empty", "staleCount": 0}
    stale_count = sum(1 for status in statuses if status == "stale")
    return {"status": "stale" if stale_count else "fresh", "staleCount": stale_count}


def _parent_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "student_id": snapshot.get("student_id"),
        "subject": snapshot.get("subject"),
        "topic_id": snapshot.get("topic_id"),
        "strengths": snapshot.get("strengths", []),
        "weak_topics": snapshot.get("weak_topics", []),
        "recommended_next_steps": snapshot.get("recommended_next_steps", []),
        "freshness": snapshot.get("freshness", {}),
        "last_updated_at": snapshot.get("last_updated_at"),
    }


def _parent_weak_topic(topic: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject": topic.get("subject"),
        "topicId": topic.get("topicId"),
        "label": topic.get("label"),
        "count": topic.get("count", 0),
        "latestEvidenceAt": topic.get("latestEvidenceAt"),
    }


def _topic_labels(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    labels = []
    for item in raw:
        if isinstance(item, str):
            labels.append(item)
        elif isinstance(item, dict):
            label = item.get("label") or item.get("topic") or item.get("topic_id")
            if label:
                labels.append(str(label))
    return labels


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_subject(subject: Any) -> str:
    try:
        return learning_profile_service.normalize_subject(str(subject or "math"))
    except ValueError:
        return "math"


def _actor_id(user: dict[str, Any]) -> str:
    return str(user.get("sub") or user.get("username") or "")


def _clean_note(note: str | None) -> str | None:
    if note is None:
        return None
    return note.strip()[:500] or None
