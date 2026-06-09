"""Adaptive learning memory and reviewed assignment workflows."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
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
from stoa.services import curriculum_service, learning_profile_service


ASSIGNMENT_STATUSES = {"draft", "recommended", "assigned", "started", "completed", "skipped", "archived"}
CREATABLE_STATUSES = {"draft", "recommended", "assigned"}
STUDENT_ACTIONS = {"start", "complete", "skip"}
STALE_AFTER_DAYS = 14


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
    recommendations = _next_practice_recommendations(student_id, profile, snapshots, normalized_subject)
    return _memory_response(
        student_id=student_id,
        user=user,
        profile=profile,
        generated_snapshots=snapshots,
        stored_snapshots=stored,
        recommendations=recommendations,
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
    source = _assignment_source(source_type, source_id, student_id)
    created_at = now_iso()
    item = {
        "assignment_id": f"assignment-{uuid4().hex}",
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
    adaptive_learning_repo.put_assignment(item)
    return assignment_response(item, user=user)


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
    return {"items": visible, "count": len(visible)}


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

    previous_status = str(item.get("status") or "")
    now = now_iso()
    updates: dict[str, Any] = {"updated_at": now}

    if action == "start":
        if previous_status in {"assigned", "recommended"}:
            updates.update({"status": "started", "started_at": item.get("started_at") or now})
        elif previous_status not in {"started", "completed"}:
            raise HTTPException(status_code=409, detail="Assignment cannot be started from its current state")
    elif action == "complete":
        if previous_status not in {"assigned", "recommended", "started", "completed"}:
            raise HTTPException(status_code=409, detail="Assignment cannot be completed from its current state")
        updates.update(
            {
                "status": "completed",
                "started_at": item.get("started_at") or now,
                "completed_at": item.get("completed_at") or now,
                "student_answer": student_answer,
                "completion_result": {"correct": correct} if correct is not None else None,
            }
        )
        if previous_status != "completed":
            _record_assignment_progress(item, correct=correct, student_answer=student_answer)
    elif action == "skip":
        if previous_status in {"completed", "archived"}:
            raise HTTPException(status_code=409, detail="Completed or archived assignments cannot be skipped")
        updates.update({"status": "skipped", "skipped_at": item.get("skipped_at") or now, "skip_note": _clean_note(note)})
    elif action == "archive":
        updates.update({"status": "archived", "archived_at": item.get("archived_at") or now, "archive_note": _clean_note(note)})

    updated = adaptive_learning_repo.update_assignment(assignment_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Assignment not found")
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
        "assignedPracticeCount": len(active),
        "completedPracticeCount": len(completed),
        "freshness": memory["freshness"],
        "assignments": active[:5],
        "completedAssignments": completed[:5],
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
        "studentAnswer": item.get("student_answer"),
        "completionResult": item.get("completion_result"),
    }
    if _can_manage_assignments(user):
        response["answerKey"] = item.get("answer_key") or []
    return response


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
        "subjects": profile.get("subjects", []),
        "subjectActivity": profile.get("subjectActivity", []),
        "weakTopics": weak_topics,
        "strengthTopics": profile.get("strengthTopics", []),
        "memorySnapshots": visible_snapshots,
        "recommendations": recommendations,
        "freshness": _overall_freshness(visible_snapshots),
        "updatedAt": now_iso(),
    }


def _assignment_source(source_type: str, source_id: str, student_id: str) -> dict[str, Any]:
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
    )


def _next_practice_recommendations(
    student_id: str,
    profile: dict[str, Any],
    snapshots: list[dict[str, Any]],
    subject: str | None,
) -> list[dict[str, Any]]:
    assignments = adaptive_learning_repo.list_assignments(student_id=student_id)
    assigned_topic_ids = {
        topic_id
        for assignment in assignments
        if assignment.get("status") in {"recommended", "assigned", "started"}
        for topic_id in assignment.get("topic_ids", [])
    }
    recommendations = []
    for topic in profile.get("weakTopics", [])[:5]:
        topic_subject = _safe_subject(topic.get("subject"))
        if subject and topic_subject != subject:
            continue
        topic_id = topic.get("topicId") or topic.get("topic_id")
        if not topic_id or topic_id in assigned_topic_ids:
            continue
        recommendations.append(
            {
                "type": "next_practice",
                "subject": topic_subject,
                "topicId": topic_id,
                "label": topic.get("label") or topic_id,
                "rationale": "Recent evidence suggests this is a useful next practice area.",
                "reviewRequired": True,
                "autonomousDecision": False,
            }
        )
    if not recommendations and snapshots:
        snapshot = snapshots[0]
        recommendations.append(
            {
                "type": "maintenance",
                "subject": snapshot["subject"],
                "topicId": snapshot["topic_id"],
                "label": snapshot["topic_id"],
                "rationale": "Continue with one short reviewed practice item to keep memory fresh.",
                "reviewRequired": True,
                "autonomousDecision": False,
            }
        )
    return recommendations


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
