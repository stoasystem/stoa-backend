"""Teacher assistance summary seed generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from boto3.dynamodb.conditions import Key

from stoa.db.dynamodb import get_table
from stoa.db.repositories import notification_repo
from stoa.security.authorization import AuthorizedResource
from stoa.security.identity import Actor
from stoa.services import learning_profile_service, locale_service, message_catalog


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
    question_text, ai_answer = _question_and_answer(question)
    seed = {
        "entity_type": notification_repo.SUMMARY_SEED_ENTITY,
        "summary_id": f"assist-{uuid4().hex}",
        "question_id": question_id,
        "student_id": question.get("student_id"),
        "subject": str(question.get("subject") or "general"),
        "student_context_summary": _student_context_summary(question, topic_labels, locale),
        "question_summary": _preview(question_text, limit=360),
        "ai_answer_summary": _preview(ai_answer, limit=360),
        "weak_topics": topic_labels,
        "suggested_focus": _suggested_focus(question, topic_labels, locale),
        "source_count": _source_count(question, has_answer=bool(ai_answer)),
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


def _question_and_answer(question: dict[str, Any]) -> tuple[str, str]:
    """What the student asked and what the assistant answered, as written.

    A request raised from an Ask conversation has a row that holds neither:
    `content` is only the note the student added, often nothing, and no answer
    is written on it (#178). Those come from the conversation - its last
    question and its last answer, the note after the question.
    """
    if question.get("source") != "conversation_escalation":
        raw_ai_response = question.get("ai_response")
        ai_response = raw_ai_response if isinstance(raw_ai_response, dict) else {}
        return str(question.get("content") or ""), str(ai_response.get("answer") or "")
    messages = _conversation_messages(str(question.get("conversation_id") or ""))
    asked = _last_said(messages, "student")
    note = str(question.get("content") or "").strip()
    return " — ".join(part for part in (asked, note) if part), _last_said(messages, "assistant")


# A ceiling on the pages one read follows; a conversation is far from it.
_MESSAGE_PAGE_LIMIT = 25


def _conversation_messages(conversation_id: str) -> list[dict[str, Any]]:
    if not conversation_id:
        return []
    table: Any = get_table()
    request: dict[str, Any] = {
        "KeyConditionExpression": (
            Key("PK").eq(f"CONV#{conversation_id}") & Key("SK").begins_with("MSG#")
        ),
    }
    messages: list[dict[str, Any]] = []
    for _page in range(_MESSAGE_PAGE_LIMIT):
        response = table.query(**request)
        messages.extend(row for row in response.get("Items", []) if isinstance(row, dict))
        cursor = response.get("LastEvaluatedKey")
        if not cursor:
            break
        request["ExclusiveStartKey"] = cursor
    return messages


def _last_said(messages: list[dict[str, Any]], role: str) -> str:
    # Message ids are random, so the keys do not run in the order of sending.
    said = [
        message
        for message in messages
        if message.get("role") == role and str(message.get("content") or "").strip()
    ]
    if not said:
        return ""
    return str(max(said, key=lambda message: str(message.get("created_at") or ""))["content"])


def _student_context_summary(question: dict[str, Any], topics: list[str], locale: str) -> str:
    # The subject is named in the reader's language: the stored id is a key,
    # and «in mathematics» inside a German sentence was what teachers read
    # (#105). The topic labels are content the assistant wrote, and go in as
    # they are.
    subject = learning_profile_service.subject_name(question.get("subject"), locale)
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


def _source_count(question: dict[str, Any], *, has_answer: bool) -> int:
    count = 1
    if has_answer:
        count += 1
    if question.get("teacher_response"):
        count += 1
    if question.get("topic_seeds") or question.get("knowledge_points"):
        count += 1
    return count


def _preview(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:limit]
