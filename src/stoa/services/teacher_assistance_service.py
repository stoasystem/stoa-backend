"""Teacher assistance summary seed generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from stoa.db.repositories import notification_repo
from stoa.security.authorization import AuthorizedResource
from stoa.security.identity import Actor
from stoa.services import (
    learning_profile_service,
    learning_session,
    locale_service,
    message_catalog,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_summary_seed(
    authorized: AuthorizedResource, actor: Actor
) -> dict[str, Any]:
    """Build a bounded seed from the exact help request authorized by the route.

    The route is keyed by a question id, which is the request's id (#189);
    the record is handed over as stored (#234).
    """
    request = dict(authorized.value)
    question_id = authorized.ref.resource_id

    created_at = now_iso()
    # The seed is rebuilt on every request, by the teacher who is about to read
    # it, so the reader is known here and the sentences can be written in their
    # language straight away (#124). What is stored stays a record of what that
    # teacher was shown; nothing re-renders it afterwards.
    locale = locale_service.reader_locale(actor.user_id)
    question_text, ai_answer = _question_and_answer(request)
    seed = {
        "entity_type": notification_repo.SUMMARY_SEED_ENTITY,
        "summary_id": f"assist-{uuid4().hex}",
        "question_id": question_id,
        "student_id": request.get("student_id"),
        "subject": str(request.get("subject") or "general"),
        # A request carries no topics: nothing on it names one yet.
        "student_context_summary": _student_context_summary(request, locale),
        "question_summary": _preview(question_text, limit=360),
        "ai_answer_summary": _preview(ai_answer, limit=360),
        "weak_topics": [],
        "suggested_focus": message_catalog.text("assistance.focus.default", locale),
        # The request itself, and the answer when there is one.
        "source_count": 2 if ai_answer else 1,
        "created_at": created_at,
        "created_by": actor.user_id,
        "owner_id": request.get("student_id"),
        "account_fence_generation": request.get("account_fence_generation"),
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


def _question_and_answer(request: dict[str, Any]) -> tuple[str, str]:
    """What the student asked and what the assistant answered, as written.

    A request holds neither: `escalation_message` is only the note the student
    added, often nothing, and no answer is written on it (#178). Those come
    from the conversation - its last question and its last answer, the note
    after the question.
    """
    messages = _conversation_messages(str(request.get("conversation_id") or ""))
    asked = _last_said(messages, "student")
    note = str(request.get("escalation_message") or "").strip()
    return " — ".join(part for part in (asked, note) if part), _last_said(messages, "assistant")


def _conversation_messages(conversation_id: str) -> list[learning_session.Message]:
    if not conversation_id:
        return []
    return learning_session.history(conversation_id)


def _last_said(messages: list[learning_session.Message], role: str) -> str:
    # The latest by when it was sent, as `history` orders them.
    said = [
        message for message in messages if message.role == role and message.content.strip()
    ]
    if not said:
        return ""
    return max(said, key=lambda message: message.created_at).content


def _student_context_summary(request: dict[str, Any], locale: str) -> str:
    # The subject is named in the reader's language: the stored id is a key,
    # and «in mathematics» inside a German sentence was what teachers read
    # (#105).
    subject = learning_profile_service.subject_name(request.get("subject"), locale)
    return message_catalog.text(
        "assistance.context.without_topics", locale, subject=subject
    )


def _preview(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:limit]
