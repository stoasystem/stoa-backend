"""Teacher assistance summary seed generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from stoa.db.repositories import notification_repo
from stoa.security.authorization import AuthorizedResource
from stoa.security.identity import Actor


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_summary_seed(
    authorized: AuthorizedResource, actor: Actor
) -> dict[str, Any]:
    """Build a bounded seed from the exact question authorized by the route."""
    question = dict(authorized.value)
    question_id = authorized.ref.resource_id

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
        "created_by": actor.user_id,
        "owner_id": question.get("student_id"),
        "account_fence_generation": question.get("account_fence_generation"),
    }
    persisted = notification_repo.put_summary_seed(seed)
    if isinstance(persisted, dict):
        seed = persisted
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
