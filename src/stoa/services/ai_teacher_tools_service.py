"""Reviewed AI teacher tool draft generation and lifecycle helpers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from itertools import islice
from typing import Any
from uuid import uuid4

from stoa.db.repositories import ai_teacher_tools_repo, practice_repo, user_repo
from stoa.security.authorization import AuthorizedResource
from stoa.security.identity import Actor
from stoa.services import (
    curriculum_service,
    exercise_localization,
    learning_profile_service,
    locale_service,
    practice_projection_service,
)
from stoa.services.ai_teacher_tools_errors import AiTeacherToolsErrorCode as _A, AiTeacherToolsViolation
from stoa.services.curriculum_translations import translated_title


PROMPT_VERSION = "stoa_ai_teacher_tools_v1"
#: An exercise draft's exercises are picked from the question bank, not written (#519).
EXERCISE_SOURCE_VERSION = "stoa_question_bank_v1"
DRAFT_TYPES = {"teacher_summary", "practice_exercise"}
DRAFT_STATUSES = {"draft", "accepted", "rejected", "archived"}
TERMINAL_REVIEW_STATUSES = {"accepted", "rejected"}
#: What a teacher asks an exercise draft for, easiest first (#519): exercises
#: aimed at the gap, ordinary practice, or a step beyond.
DIFFICULTIES = ("targeted", "standard", "stretch")
#: The bank's own exercise difficulties, in the band a teacher asks for. One
#: the table does not name counts as `standard`.
DIFFICULTY_BANDS: dict[str, frozenset[str]] = {
    "targeted": frozenset({"intro", "basic", "easy", "review"}),
    "standard": frozenset({"practice", "standard", "medium"}),
    "stretch": frozenset({"beyond", "hard", "challenge"}),
}
#: Drafts stored before #519 named the old values; regenerating one keeps its band.
_LEGACY_DIFFICULTIES = {"easy": "targeted", "medium": "standard", "hard": "stretch"}
MAX_EXERCISE_COUNT = 5
#: How many of one topic's or star's exercises a draft looks through.
_BANK_READ_LIMIT = 60


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
    star_ids: list[str] | None = None,
) -> dict[str, Any]:
    """A draft of up to `exercise_count` published exercises from the bank.

    They are the exercises of the named stars, then of the named topics, of
    the subject, closest to the asked difficulty first and in lesson order
    within it. Nothing is written for the student: a star or topic with no
    published exercise is refused (#519).
    """
    subject = _normalize_subject(subject)
    topic_ids = _normalize_topics(topic_ids)
    star_ids = _normalize_stars(star_ids or [])
    if not topic_ids and not star_ids:
        raise AiTeacherToolsViolation(_A.TOPIC_REQUIRED)
    difficulty = _require_choice(difficulty, set(DIFFICULTIES), "difficulty")
    exercise_count = _require_count(exercise_count)

    # `question_id` names a help request (#189); the context is its record.
    request = dict(authorized_context.value) if question_id else None
    evidence = [request] if request else []
    if request and str(request.get("student_id") or "") != student_id:
        raise AiTeacherToolsViolation(_A.QUESTION_OF_ANOTHER_STUDENT)
    source_context = _source_context(evidence, student_id=student_id)
    picked = _picked_exercises(
        subject=subject,
        topic_ids=topic_ids,
        star_ids=star_ids,
        difficulty=difficulty,
        count=exercise_count,
    )
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
        "requested_topic_ids": topic_ids,
        "star_ids": star_ids,
        "difficulty": difficulty,
        "requested_count": exercise_count,
        **_exercise_content(picked, student_id=student_id),
        "source_context": source_context,
        "prompt_version": PROMPT_VERSION,
        "exercise_source": EXERCISE_SOURCE_VERSION,
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
        },
        existing=item,
    )
    if not updated:
        raise AiTeacherToolsViolation(_A.AI_DRAFT_NOT_FOUND)
    return draft_response(updated)


def mark_delivered(assignment: Mapping[str, Any]) -> None:
    """Record on its draft that an accepted exercise draft reached the student.

    Called once its assignment is stored, by whichever path stored it: the
    single assignment a teacher sets (`POST /adaptive/assignments`) or an
    automation batch. Only an assignment the student is shown counts; one
    stored as `draft` does not. Writing it again changes nothing (#519).
    """
    if assignment.get("source_type") != "ai_draft":
        return
    if assignment.get("status") not in {"assigned", "recommended"}:
        return
    draft_id = str(assignment.get("source_id") or "")
    draft = ai_teacher_tools_repo.get_draft(draft_id) if draft_id else None
    if not draft or draft.get("student_delivery_status") == "delivered":
        return
    ai_teacher_tools_repo.update_draft(
        draft_id,
        {
            "student_delivery_status": "delivered",
            "delivered_assignment_id": assignment.get("assignment_id"),
            "delivered_at": assignment.get("created_at") or now_iso(),
        },
        existing=draft,
    )


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
        "starIds": item.get("star_ids") or [],
        "title": item.get("title"),
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
        "deliveredAssignmentId": item.get("delivered_assignment_id"),
        "deliveredAt": item.get("delivered_at"),
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
    """The same request again, its exercises the bank's next ones where it has them.

    The previous draft's exercises come last, so a topic with no other
    exercise gives them again rather than nothing.
    """
    student_id = str(item.get("student_id") or "")
    stored_difficulty = str(item.get("difficulty") or "standard")
    difficulty = _LEGACY_DIFFICULTIES.get(stored_difficulty, stored_difficulty)
    if difficulty not in DIFFICULTIES:
        difficulty = "standard"
    requested_topics = item.get("requested_topic_ids")
    topic_ids = list(item.get("topic_ids") or []) if requested_topics is None else list(requested_topics)
    star_ids = list(item.get("star_ids") or [])
    previous = {str(entry.get("itemId") or "") for entry in item.get("items") or [] if isinstance(entry, Mapping)}
    picked = _picked_exercises(
        subject=str(item.get("subject") or "math"),
        topic_ids=topic_ids,
        star_ids=star_ids,
        difficulty=difficulty,
        count=_require_count(item.get("requested_count") or item.get("exercise_count") or 1),
        avoid=previous,
    )
    created_at = now_iso()
    draft_id = f"aitool-{uuid4().hex}"
    regenerated = {
        **item,
        "PK": None,
        "SK": None,
        "draft_id": draft_id,
        "status": "draft",
        "requested_topic_ids": topic_ids,
        "star_ids": star_ids,
        "difficulty": difficulty,
        **_exercise_content(picked, student_id=student_id),
        "exercise_source": EXERCISE_SOURCE_VERSION,
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
    for key in ("PK", "SK", "delivered_assignment_id", "delivered_at"):
        regenerated.pop(key, None)
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


def difficulty_band(exercise_difficulty: object) -> str:
    """The band (`DIFFICULTIES`) a bank exercise's own difficulty falls in."""
    value = str(exercise_difficulty or "").strip().lower()
    for band, values in DIFFICULTY_BANDS.items():
        if value in values:
            return band
    return "standard"


def _picked_exercises(
    *,
    subject: str,
    topic_ids: list[str],
    star_ids: list[str],
    difficulty: str,
    count: int,
    avoid: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Up to `count` of the bank's published exercises for the request.

    Those in the asked band first, then the nearer band; in bank order within
    each. An exercise in `avoid` comes after every other one.
    """
    bank = _bank_exercises(subject=subject, topic_ids=topic_ids, star_ids=star_ids)
    if not bank:
        raise AiTeacherToolsViolation(_A.NO_BANK_EXERCISES)
    asked = DIFFICULTIES.index(difficulty)
    avoid = avoid or set()
    ranked = sorted(
        bank,
        key=lambda raw: (
            str(raw.get("challenge_id")) in avoid,
            abs(DIFFICULTIES.index(difficulty_band(raw.get("difficulty"))) - asked),
        ),
    )
    return ranked[:count]


def _bank_exercises(
    *, subject: str, topic_ids: list[str], star_ids: list[str]
) -> list[dict[str, Any]]:
    """The published exercises of the stars, then of the topics, once each."""
    rows: list[dict[str, Any]] = []
    if star_ids:
        units = {str(unit.get("unit_id") or ""): unit for unit in practice_repo.get_all_units()}
        for star_id in star_ids:
            rows.extend(_star_exercises(units.get(star_id)))
    for topic_id in topic_ids:
        rows.extend(islice(practice_repo.topic_challenges(topic_id), _BANK_READ_LIMIT))
    seen: set[str] = set()
    published: list[dict[str, Any]] = []
    for raw in rows:
        exercise_id = str(raw.get("challenge_id") or "")
        if (
            not exercise_id
            or exercise_id in seen
            or not practice_repo.same_subject(raw.get("subject_id", ""), subject)
            or not curriculum_service.visible_to_students(raw)
        ):
            continue
        seen.add(exercise_id)
        published.append(raw)
    return published


def _star_exercises(unit: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """A star's exercises: those of its published lessons, in lesson order.

    A star is a unit on the star map (`unit_id`); its lessons sit on its
    topic's shelf.
    """
    if not unit or not curriculum_service.visible_to_students(dict(unit)) or not unit.get("topic_id"):
        return []
    lessons = sorted(
        (
            lesson
            for lesson in practice_repo.get_lessons(
                topic_id=str(unit["topic_id"]), unit_id=str(unit["unit_id"])
            )
            if curriculum_service.visible_to_students(lesson)
        ),
        key=lambda lesson: (_as_order(lesson.get("order")), str(lesson.get("lesson_id") or "")),
    )
    exercises: list[dict[str, Any]] = []
    for lesson in lessons:
        exercises.extend(practice_repo.get_challenges(str(lesson["lesson_id"])))
        if len(exercises) >= _BANK_READ_LIMIT:
            break
    return exercises[:_BANK_READ_LIMIT]


def _exercise_content(picked: list[dict[str, Any]], *, student_id: str) -> dict[str, Any]:
    """What a draft stores of its exercises, in the student's language.

    `items` are the exercises as a student sees them (no answer); the answers
    and explanations are the bank's own, for the teacher only.
    """
    locale = _student_locale(student_id)
    shown = [exercise_localization.localized(raw, locale) for raw in picked]
    first_lesson = str(picked[0].get("lesson_id") or "") if picked else ""
    return {
        "topic_ids": list(dict.fromkeys(str(raw["topic_id"]) for raw in picked if raw.get("topic_id"))),
        "lesson_id": first_lesson or None,
        "title": _lesson_title(first_lesson, locale),
        "exercise_count": len(picked),
        "items": [
            {
                "itemId": raw["challenge_id"],
                **practice_projection_service.build_exercise_preview(raw, locale),
                "reviewState": "draft",
            }
            for raw in picked
        ],
        "answer_key": [
            {"itemId": raw["challenge_id"], "answer": _text(view.get("correct_answer", view.get("answer_key")))}
            for raw, view in zip(picked, shown, strict=True)
        ],
        "explanations": [
            {"itemId": raw["challenge_id"], "explanation": _text(view.get("explanation"))}
            for raw, view in zip(picked, shown, strict=True)
            if _text(view.get("explanation"))
        ],
    }


def _student_locale(student_id: str) -> str:
    try:
        return locale_service.effective_locale(user_repo.get_user(student_id))
    except Exception:  # noqa: BLE001 - the canonical language is always there
        return "de"


def _lesson_title(lesson_id: str, locale: str) -> str | None:
    lesson = practice_repo.get_lesson(lesson_id) if lesson_id else None
    if not lesson:
        return None
    return translated_title(lesson_id, str(lesson.get("title") or lesson_id), locale)


def _as_order(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _source_context(requests: list[dict[str, Any]], *, student_id: str) -> dict[str, Any]:
    present = [request for request in requests if request]
    return {
        "studentId": student_id,
        "evidenceQuestionIds": [_request_id(request) for request in present],
        "topicLabels": [],
        "sourceCount": len(present),
    }


def _normalize_subject(subject: str) -> str:
    canonical = curriculum_service.subject_id(subject or "math")
    if canonical is None:
        raise AiTeacherToolsViolation(_A.SUBJECT_UNSUPPORTED)
    return canonical


def _safe_subject(subject: Any) -> str:
    return curriculum_service.counted_subject(subject)


def _normalize_topics(topic_ids: list[str]) -> list[str]:
    normalized = [
        learning_profile_service.normalize_topic_id(topic_id)
        for topic_id in topic_ids
        if str(topic_id or "").strip()
    ]
    return list(dict.fromkeys(normalized))[:5]


def _normalize_stars(star_ids: list[str]) -> list[str]:
    """Star ids as the star map names them (`unit_id`), once each."""
    return list(dict.fromkeys(str(star_id).strip() for star_id in star_ids if str(star_id or "").strip()))[:5]


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
