"""Teacher assistance summary seed generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from stoa.db.repositories import notification_repo
from stoa.security.authorization import AuthorizedResource
from stoa.security.identity import Actor
from stoa.services import locale_service, message_catalog


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_summary_seed(
    authorized: AuthorizedResource, actor: Actor
) -> dict[str, Any]:
    """Build a bounded seed from the exact question authorized by the route."""
    question = dict(authorized.value)
    question_id = authorized.ref.resource_id

    created_at = now_iso()
    # The seed is rebuilt on every request, by the teacher who is about to read
    # it, so the reader is known here and the sentences can be written in their
    # language straight away (#124). What is stored stays a record of what that
    # teacher was shown; nothing re-renders it afterwards.
    locale = locale_service.reader_locale(actor.user_id)
    topic_labels = _topic_labels(question)
    raw_ai_response = question.get("ai_response")
    ai_response: dict[str, Any] = raw_ai_response if isinstance(raw_ai_response, dict) else {}
    seed = {
        "entity_type": notification_repo.SUMMARY_SEED_ENTITY,
        "summary_id": f"assist-{uuid4().hex}",
        "question_id": question_id,
        "student_id": question.get("student_id"),
        "subject": question.get("subject") or "general",
        "student_context_summary": _student_context_summary(question, topic_labels, locale),
        "question_summary": _preview(question.get("content"), limit=360),
        "ai_answer_summary": _preview(ai_response.get("answer"), limit=360),
        "weak_topics": topic_labels,
        "suggested_focus": _suggested_focus(question, topic_labels, locale),
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


def _student_context_summary(question: dict[str, Any], topics: list[str], locale: str) -> str:
    # The subject id and the topic labels are the values the rows carry, not
    # copy: they go in as they are, the way `{status}` does elsewhere.
    subject = question.get("subject") or "general"
    if topics:
        return message_catalog.text(
            "assistance.context.with_topics",
            locale,
            subject=subject,
            topics=", ".join(topics[:3]),
        )
    return message_catalog.text(
        "assistance.context.without_topics", locale, subject=subject
    )


def _suggested_focus(question: dict[str, Any], topics: list[str], locale: str) -> str:
    if question.get("teacher_response"):
        return message_catalog.text("assistance.focus.after_reply", locale)
    if topics:
        return message_catalog.text("assistance.focus.with_topics", locale, topic=topics[0])
    return message_catalog.text("assistance.focus.default", locale)


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
