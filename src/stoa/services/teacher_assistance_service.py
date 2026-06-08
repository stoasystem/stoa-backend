"""Teacher assistance summary seed generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from stoa.db.repositories import notification_repo, question_repo


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_summary_seed(question_id: str, user: dict[str, Any]) -> dict[str, Any]:
    question = question_repo.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    _require_teacher_visible(question, user)

    created_at = now_iso()
    topic_labels = _topic_labels(question)
    ai_response = question.get("ai_response") if isinstance(question.get("ai_response"), dict) else {}
    seed = {
        "entity_type": notification_repo.SUMMARY_SEED_ENTITY,
        "summary_id": f"assist-{uuid4().hex}",
        "question_id": question_id,
        "student_id": question.get("student_id"),
        "subject": question.get("subject") or "general",
        "student_context_summary": _student_context_summary(question, topic_labels),
        "question_summary": _preview(question.get("content"), limit=360),
        "ai_answer_summary": _preview(ai_response.get("answer"), limit=360),
        "weak_topics": topic_labels,
        "suggested_focus": _suggested_focus(question, topic_labels),
        "source_count": _source_count(question),
        "created_at": created_at,
        "created_by": str(user.get("sub") or ""),
    }
    notification_repo.put_summary_seed(seed)
    return summary_seed_response(seed)


def summary_seed_response(seed: dict[str, Any]) -> dict[str, Any]:
    return {
        "summaryId": seed.get("summary_id"),
        "questionId": seed.get("question_id"),
        "studentId": seed.get("student_id"),
        "subject": seed.get("subject"),
        "studentContextSummary": seed.get("student_context_summary"),
        "questionSummary": seed.get("question_summary"),
        "aiAnswerSummary": seed.get("ai_answer_summary"),
        "weakTopics": seed.get("weak_topics") or [],
        "suggestedFocus": seed.get("suggested_focus"),
        "sourceCount": seed.get("source_count") or 0,
        "createdAt": seed.get("created_at"),
    }


def _require_teacher_visible(question: dict[str, Any], user: dict[str, Any]) -> None:
    role = user.get("role")
    if role == "admin":
        return
    if role not in {"teacher", "tutor"}:
        raise HTTPException(status_code=403, detail="Role cannot view assistance summaries")
    user_id = str(user.get("sub") or "")
    if question.get("teacher_id") == user_id:
        return
    if question.get("status") in {"escalated", "teacher_active", "resolved"}:
        return
    raise HTTPException(status_code=403, detail="Question is not visible to this teacher workflow")


def _student_context_summary(question: dict[str, Any], topics: list[str]) -> str:
    subject = question.get("subject") or "general"
    if topics:
        return f"Student has active {subject} evidence around {', '.join(topics[:3])}."
    return f"Student has an active {subject} help request without enough topic evidence yet."


def _suggested_focus(question: dict[str, Any], topics: list[str]) -> str:
    if question.get("teacher_response"):
        return "Review the previous teacher reply and continue from the student's unresolved step."
    if topics:
        return f"Clarify the core misconception around {topics[0]} before giving final steps."
    return "Ask one diagnostic question, then explain the smallest next step."


def _topic_labels(question: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for seed in question.get("topic_seeds") or []:
        if isinstance(seed, dict) and seed.get("label"):
            labels.append(str(seed["label"]))
    for point in question.get("knowledge_points") or []:
        if point:
            labels.append(str(point))
    return list(dict.fromkeys(labels))[:5]


def _source_count(question: dict[str, Any]) -> int:
    count = 1
    if question.get("ai_response"):
        count += 1
    if question.get("teacher_response"):
        count += 1
    if question.get("topic_seeds") or question.get("knowledge_points"):
        count += 1
    return count


def _preview(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:limit]
