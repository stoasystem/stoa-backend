"""Reviewed AI teacher tool draft generation and lifecycle helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from stoa.db.repositories import ai_teacher_tools_repo
from stoa.security.authorization import AuthorizedResource
from stoa.security.identity import Actor
from stoa.services import learning_profile_service
from stoa.services.ai_teacher_tools_errors import AiTeacherToolsErrorCode as _A, AiTeacherToolsViolation


PROMPT_VERSION = "stoa_ai_teacher_tools_v1"
DRAFT_TYPES = {"teacher_summary", "practice_exercise"}
DRAFT_STATUSES = {"draft", "accepted", "rejected", "archived"}
TERMINAL_REVIEW_STATUSES = {"accepted", "rejected"}
DIFFICULTIES = {"easy", "medium", "hard"}
MAX_EXERCISE_COUNT = 5


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_summary_draft(
    authorized: AuthorizedResource, actor: Actor
) -> dict[str, Any]:
    return draft_response(
        _store_summary_draft(request=dict(authorized.value), actor=actor)
    )


def create_exercise_draft(
    *,
    student_id: str,
    subject: str,
    topic_ids: list[str],
    difficulty: str,
    exercise_count: int,
    actor: Actor,
    authorized_context: AuthorizedResource,
    question_id: str | None = None,
) -> dict[str, Any]:
    subject = _normalize_subject(subject)
    topic_ids = _normalize_topics(topic_ids)
    difficulty = _require_choice(difficulty, DIFFICULTIES, "difficulty")
    exercise_count = _require_count(exercise_count)

    # `question_id` names a help request (#189); the context is its record.
    request = dict(authorized_context.value) if question_id else None
    evidence = [request] if request else []
    if request and str(request.get("student_id") or "") != student_id:
        raise AiTeacherToolsViolation(_A.QUESTION_OF_ANOTHER_STUDENT)
    source_context = _source_context(evidence, student_id=student_id)
    created_at = now_iso()
    draft_id = f"aitool-{uuid4().hex}"
    item: ai_teacher_tools_repo.AIDraftItem = {
        "entity_type": ai_teacher_tools_repo.DRAFT_ENTITY,
        "draft_id": draft_id,
        "draft_type": "practice_exercise",
        "status": "draft",
        "student_id": student_id,
        "question_id": question_id,
        "subject": subject,
        "topic_ids": topic_ids,
        "difficulty": difficulty,
        "exercise_count": exercise_count,
        "items": _exercise_items(subject, topic_ids, difficulty, exercise_count),
        "answer_key": _answer_key(exercise_count),
        "explanations": _exercise_explanations(topic_ids, exercise_count),
        "source_context": source_context,
        "prompt_version": PROMPT_VERSION,
        "created_by": actor.user_id,
        "created_by_role": actor.role.value,
        "created_at": created_at,
        "generated_at": created_at,
        "updated_at": created_at,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_note": None,
        "previous_draft_id": None,
        "student_delivery_status": "not_delivered",
    }
    ai_teacher_tools_repo.put_draft(item)
    return draft_response(item)


def list_drafts(
    *,
    student_id: str | None = None,
    status: str | None = None,
    draft_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if status is not None:
        _require_choice(status, DRAFT_STATUSES, "status")
    if draft_type is not None:
        _require_choice(draft_type, DRAFT_TYPES, "draft_type")
    items = ai_teacher_tools_repo.list_drafts(
        student_id=student_id,
        status=status,
        draft_type=draft_type,
        limit=limit,
    )
    return items


def get_draft(authorized: AuthorizedResource) -> dict[str, Any]:
    return draft_response(dict(authorized.value))


def review_draft(
    *,
    authorized: AuthorizedResource,
    action: str,
    actor: Actor,
    note: str | None = None,
) -> dict[str, Any]:
    item = dict(authorized.value)
    draft_id = authorized.ref.resource_id
    action = _require_choice(action, {"accept", "reject", "archive"}, "action")
    if item.get("status") == "archived":
        raise AiTeacherToolsViolation(_A.DRAFT_ALREADY_ARCHIVED)
    if action in {"accept", "reject"} and item.get("status") in TERMINAL_REVIEW_STATUSES:
        raise AiTeacherToolsViolation(_A.DRAFT_ALREADY_REVIEWED)
    status = {"accept": "accepted", "reject": "rejected", "archive": "archived"}[action]
    now = now_iso()
    updated = ai_teacher_tools_repo.update_draft(
        draft_id,
        {
            "status": status,
            "updated_at": now,
            "reviewed_by": actor.user_id,
            "reviewed_at": now,
            "review_note": _clean_note(note),
            "student_delivery_status": "not_delivered",
        },
        existing=item,
    )
    if not updated:
        raise AiTeacherToolsViolation(_A.AI_DRAFT_NOT_FOUND)
    return draft_response(updated)


def regenerate_draft(
    authorized: AuthorizedResource, actor: Actor
) -> dict[str, Any]:
    item = dict(authorized.value)
    draft_id = authorized.ref.resource_id
    if item.get("draft_type") == "teacher_summary":
        request = authorized.facts.teacher.request if authorized.facts.teacher else None
        if not request:
            raise AiTeacherToolsViolation(_A.DRAFT_QUESTION_UNAVAILABLE)
        regenerated = _store_summary_draft(
            request=dict(request), actor=actor, previous_draft_id=draft_id
        )
    elif item.get("draft_type") == "practice_exercise":
        regenerated = _regenerate_exercise_draft(item, actor)
    else:
        raise AiTeacherToolsViolation(_A.DRAFT_TYPE_UNSUPPORTED)
    return draft_response(regenerated)


def draft_response(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "draftId": item.get("draft_id"),
        "draftType": item.get("draft_type"),
        "status": item.get("status"),
        "studentId": item.get("student_id"),
        "questionId": item.get("question_id"),
        "subject": item.get("subject"),
        "topicIds": item.get("topic_ids") or [],
        "difficulty": item.get("difficulty"),
        "exerciseCount": item.get("exercise_count") or 0,
        "sessionSummary": item.get("session_summary"),
        "misconceptionSummary": item.get("misconception_summary"),
        "suggestedTeachingFocus": item.get("suggested_teaching_focus"),
        "draftFollowupExplanation": item.get("draft_followup_explanation"),
        "items": item.get("items") or [],
        "answerKey": item.get("answer_key") or [],
        "explanations": item.get("explanations") or [],
        "sourceContext": item.get("source_context") or {},
        "promptVersion": item.get("prompt_version"),
        "createdBy": item.get("created_by"),
        "createdByRole": item.get("created_by_role"),
        "createdAt": item.get("created_at"),
        "generatedAt": item.get("generated_at"),
        "updatedAt": item.get("updated_at"),
        "reviewedBy": item.get("reviewed_by"),
        "reviewedAt": item.get("reviewed_at"),
        "reviewNote": item.get("review_note"),
        "previousDraftId": item.get("previous_draft_id"),
        "studentDeliveryStatus": item.get("student_delivery_status") or "not_delivered",
    }


def _store_summary_draft(
    *,
    request: dict[str, Any],
    actor: Actor,
    previous_draft_id: str | None = None,
) -> dict[str, Any]:
    """A summary draft of one help request, as stored.

    A request names no topic and holds no answer, so the draft takes the
    no-topic sentences throughout.
    """
    created_at = now_iso()
    draft_id = f"aitool-{uuid4().hex}"
    item: dict[str, Any] = {
        "entity_type": ai_teacher_tools_repo.DRAFT_ENTITY,
        "draft_id": draft_id,
        "draft_type": "teacher_summary",
        "status": "draft",
        "student_id": request.get("student_id"),
        "question_id": _request_id(request),
        "subject": _safe_subject(request.get("subject")),
        "topic_ids": [],
        "difficulty": None,
        "exercise_count": 0,
        "session_summary": f"Student asked: {_preview(request.get('escalation_message'), limit=180)}.",
        "misconception_summary": "No specific misconception identified yet; start with a diagnostic check.",
        "suggested_teaching_focus": (
            "Ask the student to explain what they tried, then model the smallest next step."
        ),
        "draft_followup_explanation": _draft_followup(request),
        "items": [],
        "answer_key": [],
        "explanations": [],
        "source_context": _source_context([request], student_id=str(request.get("student_id") or "")),
        "prompt_version": PROMPT_VERSION,
        "created_by": actor.user_id,
        "created_by_role": actor.role.value,
        "created_at": created_at,
        "generated_at": created_at,
        "updated_at": created_at,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_note": None,
        "previous_draft_id": previous_draft_id,
        "student_delivery_status": "not_delivered",
    }
    ai_teacher_tools_repo.put_draft(item)
    return item


def _regenerate_exercise_draft(item: dict[str, Any], actor: Actor) -> dict[str, Any]:
    student_id = str(item.get("student_id") or "")
    created_at = now_iso()
    draft_id = f"aitool-{uuid4().hex}"
    regenerated = {
        **item,
        "PK": None,
        "SK": None,
        "draft_id": draft_id,
        "status": "draft",
        "items": _exercise_items(
            str(item.get("subject") or "math"),
            list(item.get("topic_ids") or ["general"]),
            str(item.get("difficulty") or "medium"),
            int(item.get("exercise_count") or 1),
        ),
        "answer_key": _answer_key(int(item.get("exercise_count") or 1)),
        "explanations": _exercise_explanations(
            list(item.get("topic_ids") or ["general"]),
            int(item.get("exercise_count") or 1),
        ),
        "source_context": dict(item.get("source_context") or {"studentId": student_id}),
        "created_by": actor.user_id,
        "created_by_role": actor.role.value,
        "created_at": created_at,
        "generated_at": created_at,
        "updated_at": created_at,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_note": None,
        "previous_draft_id": item.get("draft_id"),
        "student_delivery_status": "not_delivered",
    }
    regenerated.pop("PK", None)
    regenerated.pop("SK", None)
    ai_teacher_tools_repo.put_draft(regenerated)
    return regenerated


def _request_id(request: dict[str, Any]) -> str:
    # A request's id is its conversation's (#189); the record names it both ways.
    return str(request.get("escalation_request_id") or request.get("conversation_id"))


def _draft_followup(request: dict[str, Any]) -> str:
    subject = _safe_subject(request.get("subject"))
    return (
        "Let's focus on the core concept. First, tell me which step feels unclear. "
        f"Then we will solve one {subject} example together before you try the next one."
    )


def _exercise_items(subject: str, topic_ids: list[str], difficulty: str, count: int) -> list[dict[str, Any]]:
    topic_label = ", ".join(topic_ids[:2]) if topic_ids else "general"
    return [
        {
            "itemId": f"item-{index}",
            "prompt": f"{subject.title()} practice {index}: solve a {difficulty} problem about {topic_label}.",
            "subject": subject,
            "topicIds": topic_ids,
            "difficulty": difficulty,
            "reviewState": "draft",
        }
        for index in range(1, count + 1)
    ]


def _answer_key(count: int) -> list[dict[str, Any]]:
    return [
        {"itemId": f"item-{index}", "answer": f"Teacher-reviewed answer placeholder {index}"}
        for index in range(1, count + 1)
    ]


def _exercise_explanations(topic_ids: list[str], count: int) -> list[dict[str, Any]]:
    topic = topic_ids[0] if topic_ids else "the selected topic"
    return [
        {"itemId": f"item-{index}", "explanation": f"Explain the reasoning around {topic} step by step."}
        for index in range(1, count + 1)
    ]


def _source_context(requests: list[dict[str, Any]], *, student_id: str) -> dict[str, Any]:
    present = [request for request in requests if request]
    return {
        "studentId": student_id,
        "evidenceQuestionIds": [_request_id(request) for request in present],
        "topicLabels": [],
        "sourceCount": len(present),
    }


def _normalize_subject(subject: str) -> str:
    try:
        return learning_profile_service.normalize_subject(subject)
    except ValueError as exc:
        raise AiTeacherToolsViolation(_A.SUBJECT_UNSUPPORTED) from exc


def _safe_subject(subject: Any) -> str:
    try:
        return learning_profile_service.normalize_subject(str(subject or "math"))
    except ValueError:
        return "math"


def _normalize_topics(topic_ids: list[str]) -> list[str]:
    normalized = [
        learning_profile_service.normalize_topic_id(topic_id)
        for topic_id in topic_ids
        if str(topic_id or "").strip()
    ]
    normalized = list(dict.fromkeys(normalized))
    if not normalized:
        raise AiTeacherToolsViolation(_A.TOPIC_REQUIRED)
    return normalized[:5]


def _require_count(count: int) -> int:
    try:
        value = int(count)
    except (TypeError, ValueError) as exc:
        raise AiTeacherToolsViolation(_A.EXERCISE_COUNT_INVALID, params={"max": MAX_EXERCISE_COUNT}) from exc
    if value < 1 or value > MAX_EXERCISE_COUNT:
        raise AiTeacherToolsViolation(_A.EXERCISE_COUNT_INVALID, params={"max": MAX_EXERCISE_COUNT})
    return value


def _require_choice(value: str, choices: set[str], field: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in choices:
        raise AiTeacherToolsViolation(_A.DRAFT_OPTION_UNSUPPORTED, params={"field": field})
    return normalized


def _clean_note(note: str | None) -> str | None:
    if note is None:
        return None
    return " ".join(note.strip().split())[:500] or None


def _preview(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]
