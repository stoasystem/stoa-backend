"""Practice module routes — subjects, topics, lessons, challenges, progress.

API contract matches stoa-frontend/src/services/practice/practiceApi.ts.
All content is pre-seeded in DynamoDB (PK=PRACTICE, SK=SUBJECT#…/TOPIC#…/LESSON#…/CHALLENGE#…).
Student progress is stored under PK=PROGRESS#{user_id}.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from stoa.config import settings
from stoa.db.repositories import practice_repo
from stoa.deps import get_actor
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    AuthorizedResource,
    CurrentAuthorizationFactRepository,
    ResourceRef,
    ResourceType,
    authorize_and_resolve,
)
from stoa.security.errors import SecurityDecisionError
from stoa.security.identity import Actor
from stoa.security.route_authorization import (
    STUDENT_CONTENT_READ,
    authorized_student_dependency,
    get_authorization_fact_repository,
    safe_public_dependency,
    student_actor_dependency,
)
from stoa.services import curriculum_analytics_service, curriculum_service, entitlement_service, usage_ledger_service

router = APIRouter()
logger = logging.getLogger(__name__)

_catalog_access = safe_public_dependency(ResourceType.PRACTICE)
_practice_read = student_actor_dependency(ResourceType.PRACTICE, AuthorizationAction.READ)
_practice_update = student_actor_dependency(ResourceType.PRACTICE, AuthorizationAction.UPDATE)
_practice_progress = authorized_student_dependency(
    action=AuthorizationAction.READ,
    purposes=STUDENT_CONTENT_READ,
)


async def _authorize_practice_item(
    *,
    actor: Actor,
    facts: CurrentAuthorizationFactRepository,
    item_id: str,
    item: dict | None,
    action: AuthorizationAction,
) -> AuthorizedResource:
    async def resolve(_resource_id: str):
        if not item:
            return None
        return AuthorizedResource(
            ResourceRef(ResourceType.PRACTICE, item_id, actor.user_id),
            item,
        )

    spec = AuthorizationSpec(
        ResourceType.PRACTICE,
        action,
        AuthorizationPurpose.SELF_SERVICE,
        resolve,
    )
    try:
        return await authorize_and_resolve(
            actor=actor,
            resource_id=item_id,
            spec=spec,
            fact_repository=facts,
        )
    except SecurityDecisionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.public_body()) from error


def _practice_item_specs(action: AuthorizationAction, resolver):
    return (
        AuthorizationSpec(
            ResourceType.PRACTICE,
            action,
            AuthorizationPurpose.SELF_SERVICE,
            resolver,
        ),
    )


async def _authorized_lesson_read(
    lesson_id: str,
    actor: Actor = Depends(get_actor),
    facts: CurrentAuthorizationFactRepository = Depends(get_authorization_fact_repository),
) -> AuthorizedResource:
    return await _authorize_practice_item(
        actor=actor,
        facts=facts,
        item_id=lesson_id,
        item=practice_repo.get_lesson(lesson_id),
        action=AuthorizationAction.READ,
    )


async def _authorized_lesson_update(
    lesson_id: str,
    actor: Actor = Depends(get_actor),
    facts: CurrentAuthorizationFactRepository = Depends(get_authorization_fact_repository),
) -> AuthorizedResource:
    return await _authorize_practice_item(
        actor=actor,
        facts=facts,
        item_id=lesson_id,
        item=practice_repo.get_lesson(lesson_id),
        action=AuthorizationAction.UPDATE,
    )


async def _authorized_challenge_update(
    challenge_id: str,
    actor: Actor = Depends(get_actor),
    facts: CurrentAuthorizationFactRepository = Depends(get_authorization_fact_repository),
) -> AuthorizedResource:
    return await _authorize_practice_item(
        actor=actor,
        facts=facts,
        item_id=challenge_id,
        item=practice_repo.get_challenge(challenge_id),
        action=AuthorizationAction.UPDATE,
    )


async def _authorized_body_challenge_update(
    body: dict,
    actor: Actor = Depends(get_actor),
    facts: CurrentAuthorizationFactRepository = Depends(get_authorization_fact_repository),
) -> AuthorizedResource:
    challenge_id = str(body.get("challengeId") or "").strip()
    return await _authorize_practice_item(
        actor=actor,
        facts=facts,
        item_id=challenge_id,
        item=practice_repo.get_challenge(challenge_id) if challenge_id else None,
        action=AuthorizationAction.UPDATE,
    )


async def _lesson_metadata_resolver(resource_id: str):
    return practice_repo.get_lesson(resource_id)


async def _challenge_metadata_resolver(resource_id: str):
    return practice_repo.get_challenge(resource_id)


_authorized_lesson_read.authorization_specs = _practice_item_specs(  # type: ignore[attr-defined]
    AuthorizationAction.READ, _lesson_metadata_resolver
)
_authorized_lesson_update.authorization_specs = _practice_item_specs(  # type: ignore[attr-defined]
    AuthorizationAction.UPDATE, _lesson_metadata_resolver
)
_authorized_challenge_update.authorization_specs = _practice_item_specs(  # type: ignore[attr-defined]
    AuthorizationAction.UPDATE, _challenge_metadata_resolver
)
_authorized_body_challenge_update.authorization_specs = _practice_item_specs(  # type: ignore[attr-defined]
    AuthorizationAction.UPDATE, _challenge_metadata_resolver
)


def _as_int(val: Any, default: int = 0) -> int:
    """Convert DynamoDB Decimal or any numeric to plain int."""
    if val is None:
        return default
    if isinstance(val, Decimal):
        return int(val)
    return int(val)


def _hint_limit_for_student(student_id: str) -> int:
    entitlement = entitlement_service.resolve_student_entitlement(student_id, settings=settings)
    limits = entitlement.get("limits") or {}
    return int(limits.get("dailyHintLimit") or settings.daily_hint_limit)


# ── Response helpers ────────────────────────────────────────────────────────

def _lesson_status(lesson_id: str, completed_ids: set[str],
                   current_id: str | None) -> str:
    if lesson_id in completed_ids:
        return "completed"
    if lesson_id == current_id:
        return "current"
    return "available"


def _build_challenge(raw: dict) -> dict:
    return {
        "id": raw["challenge_id"],
        "lessonId": raw["lesson_id"],
        "unitId": raw.get("unit_id", ""),
        "subjectId": raw["subject_id"],
        "gradeLevel": raw.get("grade_level", ""),
        "topicId": raw["topic_id"],
        "topic": raw.get("topic_title", ""),
        "type": raw.get("type", "text_input"),
        "prompt": raw["prompt"],
        "options": raw.get("options"),
        "correctAnswer": raw["correct_answer"],
        "hint": raw.get("hint"),
        "explanation": raw.get("explanation"),
        "correctFeedback": raw.get("correct_feedback"),
        "incorrectFeedback": raw.get("incorrect_feedback"),
    }


def _build_lesson(raw: dict, challenges: list[dict], status: str = "available") -> dict:
    return {
        "id": raw["lesson_id"],
        "unitId": raw.get("unit_id", ""),
        "subjectId": raw["subject_id"],
        "gradeLevel": raw.get("grade_level", ""),
        "topicId": raw["topic_id"],
        "title": raw["title"],
        "topic": raw.get("topic_title", ""),
        "difficulty": raw.get("difficulty", "practice"),
        "status": status,
        "estimatedMinutes": raw.get("estimated_minutes", 10),
        "challenges": challenges,
    }


def _build_unit(raw: dict, lessons: list[dict]) -> dict:
    return {
        "id": raw["unit_id"],
        "subjectId": raw["subject_id"],
        "gradeLevel": raw.get("grade_level", ""),
        "topicId": raw["topic_id"],
        "title": raw["title"],
        "description": raw.get("description", ""),
        "order": raw.get("order", 1),
        "status": "available",
        "lessons": lessons,
    }


def _actor_projection(actor: Actor) -> dict[str, object]:
    return {
        "sub": actor.user_id,
        "user_id": actor.user_id,
        "role": actor.role.value,
        "capabilities": {
            grant.capability: "granted" for grant in actor.current_grants
        },
    }


def _enforce_curriculum_preview_access(user: Actor, include_preview: bool, rollout_state: str | None) -> None:
    preview_requested = include_preview or (rollout_state is not None and rollout_state.lower() != "active")
    if preview_requested and not curriculum_service.can_preview(_actor_projection(user)):
        raise HTTPException(status_code=403, detail="Curriculum preview content requires teacher or admin access")


def _resolve_curriculum_student_id(user: dict, requested_student_id: str | None) -> str:
    role = str(user.get("role", "")).lower()
    if role == "student":
        if requested_student_id and requested_student_id != user.get("sub"):
            raise HTTPException(status_code=403, detail="Students can only view their own curriculum progress")
        return user["sub"]
    if role in {"admin", "teacher"} and requested_student_id:
        return requested_student_id
    raise HTTPException(status_code=400, detail="studentId is required for teacher/admin curriculum progress")


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/subjects")
async def list_subjects(_actor: Actor = Depends(_catalog_access)):
    subjects = practice_repo.get_subjects()
    items = []
    for s in sorted(subjects, key=lambda x: x.get("order", 0)):
        items.append({
            "id": s["subject_id"],
            "name": s["name"],
            "description": s.get("description", ""),
            "gradeLevels": s.get("grade_levels", []),
            "progress": 0,
            "accent": s.get("accent", "blue"),
        })
    return {"items": items}


@router.get("/overview")
async def get_overview(actor: Actor = Depends(_practice_read)):
    """Return a full practice overview for the student dashboard."""
    user_id = actor.user_id
    progress_records = practice_repo.get_progress(user_id)
    completed_ids = {p["lesson_id"] for p in progress_records if p.get("status") == "completed"}

    today = datetime.now(timezone.utc).date().isoformat()
    completed_today = sum(
        1 for p in progress_records
        if p.get("status") == "completed" and str(p.get("completed_at", ""))[:10] == today
    )
    daily_target = 3

    # -- Subjects --
    subjects_raw = practice_repo.get_subjects()
    all_topics_raw = practice_repo.get_topics()
    all_lessons = practice_repo.get_lessons()

    # Per-topic progress
    topic_progress: dict[str, dict] = {}
    for t in all_topics_raw:
        tid = t["topic_id"]
        t_lessons = [lesson for lesson in all_lessons if lesson.get("topic_id") == tid]
        done = sum(1 for lesson in t_lessons if lesson["lesson_id"] in completed_ids)
        pct = int(done / len(t_lessons) * 100) if t_lessons else 0
        current = next(
            (lesson["lesson_id"] for lesson in sorted(t_lessons, key=lambda x: x.get("order", 0))
             if lesson["lesson_id"] not in completed_ids),
            t_lessons[-1]["lesson_id"] if t_lessons else None,
        )
        topic_progress[tid] = {"pct": pct, "current_lesson_id": current}

    subjects_out = []
    for s in sorted(subjects_raw, key=lambda x: _as_int(x.get("order", 0))):
        subjects_out.append({
            "id": s["subject_id"],
            "name": s["name"],
            "description": s.get("description", ""),
            "gradeLevels": s.get("grade_levels", []),
            "progress": int(
                sum(topic_progress[t["topic_id"]]["pct"]
                    for t in all_topics_raw if t.get("subject_id") == s["subject_id"])
                / max(sum(1 for t in all_topics_raw if t.get("subject_id") == s["subject_id"]), 1)
            ),
            "accent": s.get("accent", "burgundy"),
        })

    topics_out = []
    for t in sorted(all_topics_raw, key=lambda x: _as_int(x.get("order", 0))):
        tp = topic_progress.get(t["topic_id"], {})
        topics_out.append({
            "id": t["topic_id"],
            "subjectId": t["subject_id"],
            "gradeLevel": t.get("grade_level", ""),
            "title": t["title"],
            "description": t.get("description", ""),
            "order": _as_int(t.get("order", 0)),
            "status": "available",
            "progress": tp.get("pct", 0),
            "currentLessonId": tp.get("current_lesson_id"),
        })

    # -- Recommended lesson --
    recommended_raw = None
    for lesson in sorted(all_lessons, key=lambda x: (x.get("topic_id", ""), x.get("order", 0))):
        if lesson["lesson_id"] not in completed_ids:
            recommended_raw = lesson
            break
    if not recommended_raw:
        recommended_raw = all_lessons[0] if all_lessons else None
    if not recommended_raw:
        raise HTTPException(status_code=404, detail="No lessons available")

    challenges = [_build_challenge(c)
                  for c in practice_repo.get_challenges(recommended_raw["lesson_id"])]
    recommended = _build_lesson(recommended_raw, challenges,
                                _lesson_status(recommended_raw["lesson_id"], completed_ids,
                                               topic_progress.get(recommended_raw.get("topic_id", ""), {}).get("current_lesson_id")))

    # -- Mistakes --
    mistakes_raw = practice_repo.get_mistakes(user_id)[:5]
    recent_mistakes = []
    for m in mistakes_raw:
        recent_mistakes.append({
            "id": m.get("mistake_id", m.get("challenge_id", "")),
            "challengeId": m.get("challenge_id", ""),
            "lessonId": m.get("lesson_id", ""),
            "topic": m.get("topic_id", ""),
            "subject": m.get("subject_id", ""),
            "prompt": m.get("prompt", ""),
            "studentAnswer": m.get("student_answer", ""),
            "correctAnswer": m.get("correct_answer", ""),
            "reviewedAt": None,
        })

    # Weak topics: topics with ≥2 mistakes
    topic_mistake_counts: dict[str, int] = {}
    for m in practice_repo.get_mistakes(user_id):
        tid = m.get("topic_id", "")
        topic_mistake_counts[tid] = topic_mistake_counts.get(tid, 0) + 1
    weak_topics = [
        {
            "id": tid,
            "subject": "mathematics",
            "topic": next((t["title"] for t in all_topics_raw if t["topic_id"] == tid), tid),
            "note": f"{count} incorrect answer{'s' if count != 1 else ''}",
        }
        for tid, count in sorted(topic_mistake_counts.items(), key=lambda x: -x[1])
        if count >= 1
    ][:3]

    return {
        "subjects": subjects_out,
        "topics": topics_out,
        "recommendedLesson": recommended,
        "dailyGoal": {
            "completed": completed_today,
            "target": daily_target,
            "label": f"{completed_today}/{daily_target} lessons today",
        },
        "studyStreak": 1 if completed_today > 0 else 0,
        "progressPoints": len(completed_ids) * 10,
        "recentMistakes": recent_mistakes,
        "weakTopics": weak_topics,
    }


@router.get("/curriculum/catalog")
async def get_curriculum_catalog(
    subject_id: str | None = Query(default=None, alias="subjectId"),
    grade_level: str | None = Query(default=None, alias="gradeLevel"),
    rollout_state: str | None = Query(default=None, alias="rolloutState"),
    include_preview: bool = Query(default=False, alias="includePreview"),
    user: Actor = Depends(_catalog_access),
):
    _enforce_curriculum_preview_access(user, include_preview, rollout_state)
    return curriculum_service.list_catalog(
        subject_id=subject_id,
        grade_level=grade_level,
        rollout_state=rollout_state,
        include_preview=include_preview,
    )


@router.get("/curriculum/lessons/{lesson_id}")
async def get_curriculum_lesson(
    lesson_id: str,
    include_preview: bool = Query(default=False, alias="includePreview"),
    include_answers: bool = Query(default=False, alias="includeAnswers"),
    user: Actor = Depends(_catalog_access),
):
    _enforce_curriculum_preview_access(user, include_preview, None)
    include_answer_keys = include_answers and curriculum_service.can_view_answer_keys(
        _actor_projection(user)
    )
    lesson = curriculum_service.get_lesson_detail(
        lesson_id,
        include_preview=include_preview,
        include_answer_keys=include_answer_keys,
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Curriculum lesson not found")
    return lesson


@router.get("/curriculum/exercises")
async def list_curriculum_exercises(
    lesson_id: str | None = Query(default=None, alias="lessonId"),
    subject_id: str | None = Query(default=None, alias="subjectId"),
    topic_id: str | None = Query(default=None, alias="topicId"),
    difficulty: str | None = Query(default=None),
    rollout_state: str | None = Query(default=None, alias="rolloutState"),
    include_preview: bool = Query(default=False, alias="includePreview"),
    include_answers: bool = Query(default=False, alias="includeAnswers"),
    user: Actor = Depends(_catalog_access),
):
    _enforce_curriculum_preview_access(user, include_preview, rollout_state)
    include_answer_keys = include_answers and curriculum_service.can_view_answer_keys(
        _actor_projection(user)
    )
    return curriculum_service.list_exercises(
        lesson_id=lesson_id,
        subject_id=subject_id,
        topic_id=topic_id,
        difficulty=difficulty,
        rollout_state=rollout_state,
        include_preview=include_preview,
        include_answer_keys=include_answer_keys,
    )


@router.get("/curriculum/progress")
async def get_curriculum_progress(
    student_id: str | None = Query(default=None, alias="studentId"),
    subject_id: str | None = Query(default=None, alias="subjectId"),
    authorized_student: AuthorizedResource = Depends(_practice_progress),
):
    resolved_student_id = authorized_student.ref.student_id
    return curriculum_service.get_progress_summary(resolved_student_id, subject_id=subject_id)


@router.get("/{subject_id}/{topic_id}/roadmap")
async def get_roadmap(
    subject_id: str,
    topic_id: str,
    actor: Actor = Depends(_practice_read),
):
    """Return the lesson roadmap for a topic."""
    topic = practice_repo.get_topic(topic_id)
    if not topic or topic.get("subject_id") != subject_id:
        raise HTTPException(status_code=404, detail="Topic not found")

    user_id = actor.user_id
    progress = practice_repo.get_progress(user_id, subject_id)
    completed_ids = {p["lesson_id"] for p in progress if p.get("status") == "completed"}

    units_raw = sorted(
        practice_repo.get_units(topic_id), key=lambda x: x.get("order", 0)
    )
    # Find the current lesson (first non-completed)
    all_lessons = sorted(
        practice_repo.get_lessons(topic_id=topic_id),
        key=lambda x: (x.get("unit_id", ""), x.get("order", 0)),
    )
    current_lesson_id = next(
        (lesson["lesson_id"] for lesson in all_lessons if lesson["lesson_id"] not in completed_ids),
        all_lessons[-1]["lesson_id"] if all_lessons else None,
    )
    progress_pct = int(len(completed_ids) / len(all_lessons) * 100) if all_lessons else 0

    roadmap_units = []
    for unit_raw in units_raw:
        unit_lessons_raw = [lesson for lesson in all_lessons if lesson.get("unit_id") == unit_raw["unit_id"]]
        roadmap_lessons = []
        for lesson in unit_lessons_raw:
            st = _lesson_status(lesson["lesson_id"], completed_ids, current_lesson_id)
            roadmap_lessons.append({
                "id": lesson["lesson_id"],
                "title": lesson["title"],
                "description": lesson.get("description", ""),
                "order": lesson.get("order", 1),
                "status": st,
                "estimatedMinutes": lesson.get("estimated_minutes", 10),
                "subjectId": subject_id,
                "gradeLevel": lesson.get("grade_level", ""),
                "topicId": topic_id,
                "unitId": lesson.get("unit_id", ""),
                "challengeCount": lesson.get("challenge_count", 3),
            })
        roadmap_units.append({
            "id": unit_raw["unit_id"],
            "title": unit_raw["title"],
            "description": unit_raw.get("description", ""),
            "order": unit_raw.get("order", 1),
            "lessons": roadmap_lessons,
        })

    return {
        "subjectId": subject_id,
        "topicId": topic_id,
        "gradeLevel": topic.get("grade_level", ""),
        "topic": {
            "id": topic["topic_id"],
            "subjectId": subject_id,
            "gradeLevel": topic.get("grade_level", ""),
            "title": topic["title"],
            "description": topic.get("description", ""),
            "progress": progress_pct,
            "currentLessonId": current_lesson_id,
        },
        "progress": progress_pct,
        "currentLessonId": current_lesson_id,
        "units": roadmap_units,
    }


@router.get("/{subject_id}/{topic_id}/path")
async def get_path(
    subject_id: str,
    topic_id: str | None = None,
    actor: Actor = Depends(_practice_read),
):
    """Return the practice path (units + lessons) for a subject/topic."""
    if topic_id:
        topics = [practice_repo.get_topic(topic_id)]
        topics = [t for t in topics if t]
    else:
        topics = practice_repo.get_topics(subject_id)

    if not topics:
        raise HTTPException(status_code=404, detail="No topics found")

    user_id = actor.user_id
    progress = practice_repo.get_progress(user_id, subject_id)
    completed_ids = {p["lesson_id"] for p in progress if p.get("status") == "completed"}

    all_lessons = sorted(
        practice_repo.get_lessons(topic_id=topics[0]["topic_id"] if topic_id else None),
        key=lambda x: (x.get("topic_id", ""), x.get("unit_id", ""), x.get("order", 0)),
    )
    current_lesson_id = next(
        (lesson["lesson_id"] for lesson in all_lessons if lesson["lesson_id"] not in completed_ids),
        all_lessons[-1]["lesson_id"] if all_lessons else None,
    )

    units_raw = sorted(
        practice_repo.get_units(topics[0]["topic_id"]) if topic_id
        else [], key=lambda x: x.get("order", 0)
    )

    path_units = []
    for unit_raw in units_raw:
        unit_lessons_raw = [lesson for lesson in all_lessons if lesson.get("unit_id") == unit_raw["unit_id"]]
        unit_lessons = []
        for lesson in unit_lessons_raw:
            challenges = [_build_challenge(c)
                          for c in practice_repo.get_challenges(lesson["lesson_id"])]
            st = _lesson_status(lesson["lesson_id"], completed_ids, current_lesson_id)
            unit_lessons.append(_build_lesson(lesson, challenges, st))
        path_units.append(_build_unit(unit_raw, unit_lessons))

    return {
        "subjectId": subject_id,
        "gradeLevel": topics[0].get("grade_level", "") if topics else "",
        "topicId": topics[0]["topic_id"] if topics else "",
        "topicTitle": topics[0]["title"] if topics else "",
        "units": path_units,
    }


@router.get("/lessons/{lesson_id}")
async def get_lesson(
    lesson_id: str,
    actor: Actor = Depends(_practice_read),
    authorized_lesson: AuthorizedResource = Depends(_authorized_lesson_read),
):
    lesson = dict(authorized_lesson.value)

    user_id = actor.user_id
    progress = practice_repo.get_progress(user_id)
    completed_ids = {p["lesson_id"] for p in progress if p.get("status") == "completed"}
    all_lessons = sorted(
        practice_repo.get_lessons(topic_id=lesson.get("topic_id")),
        key=lambda x: x.get("order", 0),
    )
    current_id = next(
        (lesson["lesson_id"] for lesson in all_lessons if lesson["lesson_id"] not in completed_ids),
        None,
    )
    st = _lesson_status(lesson_id, completed_ids, current_id)
    challenges = [_build_challenge(c) for c in practice_repo.get_challenges(lesson_id)]
    return _build_lesson(lesson, challenges, st)


@router.post("/lessons/{lesson_id}/complete")
async def complete_lesson(
    lesson_id: str,
    actor: Actor = Depends(_practice_update),
    authorized_lesson: AuthorizedResource = Depends(_authorized_lesson_update),
):
    lesson = dict(authorized_lesson.value)

    practice_repo.mark_lesson_completed(actor.user_id, lesson)
    curriculum_analytics_service.record_lesson_completed(student_id=actor.user_id, lesson=lesson)
    _record_practice_usage(
        student_id=actor.user_id,
        action=usage_ledger_service.PRACTICE_LESSON_COMPLETION_ACTION,
        resource_id=lesson_id,
        metadata={
            "lesson_id": lesson_id,
            "subject": lesson.get("subject_id"),
            "topic_id": lesson.get("topic_id"),
            "unit_id": lesson.get("unit_id"),
            "status": "completed",
        },
    )
    all_lessons = sorted(
        practice_repo.get_lessons(topic_id=lesson.get("topic_id")),
        key=lambda x: x.get("order", 0),
    )
    completed_ids = {p["lesson_id"] for p in practice_repo.get_progress(actor.user_id)
                     if p.get("status") == "completed"}
    next_lesson = next(
        (lesson for lesson in all_lessons if lesson["lesson_id"] not in completed_ids), None
    )
    return {
        "lessonId": lesson_id,
        "completed": True,
        "nextLessonId": next_lesson["lesson_id"] if next_lesson else None,
        "progressPoints": len(completed_ids) * 10,
        "studyStreak": 1,
        "dailyGoalCompleted": False,
    }


@router.post("/challenges/{challenge_id}/answer")
async def submit_answer(
    challenge_id: str,
    body: dict,
    actor: Actor = Depends(_practice_update),
    authorized_challenge: AuthorizedResource = Depends(_authorized_challenge_update),
):
    challenge = dict(authorized_challenge.value)

    student_answer = body.get("answer", "")
    correct_answer = challenge.get("correct_answer", "")

    # Normalise for comparison
    def _norm(v: Any) -> str:
        if isinstance(v, list):
            return "|".join(str(x).strip().lower() for x in v)
        return str(v).strip().lower()

    correct = _norm(student_answer) == _norm(correct_answer)
    curriculum_analytics_service.record_practice_attempt(
        student_id=actor.user_id,
        challenge=challenge,
        correct=correct,
    )

    # Find challenges in the same lesson for next_challenge_id
    lesson_id = challenge.get("lesson_id", "")
    all_challenges = practice_repo.get_challenges(lesson_id)
    challenge_ids = [c["challenge_id"] for c in all_challenges]
    try:
        idx = challenge_ids.index(challenge_id)
        next_challenge_id = challenge_ids[idx + 1] if idx + 1 < len(challenge_ids) else None
    except ValueError:
        next_challenge_id = None

    user_id = actor.user_id
    practice_repo.record_attempt(
        user_id, challenge_id, correct,
        subject_id=challenge.get("subject_id", ""),
        topic_id=challenge.get("topic_id", ""),
        lesson_id=lesson_id,
    )
    _record_practice_usage(
        student_id=user_id,
        action=usage_ledger_service.PRACTICE_ANSWER_ACTION,
        resource_id=challenge_id,
        metadata={
            "challenge_id": challenge_id,
            "lesson_id": lesson_id,
            "subject": challenge.get("subject_id"),
            "topic_id": challenge.get("topic_id"),
            "attempt_result": "correct" if correct else "incorrect",
            "status": "submitted",
        },
    )

    feedback = (
        challenge.get("correct_feedback") if correct
        else challenge.get("incorrect_feedback")
    ) or ("Richtig!" if correct else "Leider falsch. Schau dir den Hinweis an.")

    return {
        "challengeId": challenge_id,
        "correct": correct,
        "feedback": feedback,
        "explanation": challenge.get("explanation") if correct else None,
        "hint": challenge.get("hint") if not correct else None,
        "nextChallengeId": next_challenge_id,
        "attemptsRemaining": 2,
        "canAskLearningAssistant": not correct,
        "canAskTeacher": False,
    }


@router.get("/mistakes")
async def get_mistakes(actor: Actor = Depends(_practice_read)):
    user_id = actor.user_id
    attempts = practice_repo.get_mistakes(user_id)
    mistakes = []
    for attempt in attempts[-20:]:  # last 20 wrong answers
        ch = practice_repo.get_challenge(attempt["challenge_id"])
        if not ch:
            continue
        mistakes.append({
            "id": attempt.get("SK", attempt["challenge_id"]),
            "challengeId": attempt["challenge_id"],
            "subjectId": attempt.get("subject_id", ""),
            "topic": ch.get("topic_title", ""),
            "prompt": ch["prompt"],
            "yourAnswer": attempt.get("student_answer", ""),
            "correctAnswer": ch["correct_answer"],
            "createdAt": attempt.get("created_at", ""),
        })
    return {"items": mistakes}


@router.post("/hints")
async def get_hint(
    body: dict,
    actor: Actor = Depends(_practice_update),
    authorized_challenge: AuthorizedResource = Depends(_authorized_body_challenge_update),
):
    from stoa.services.rate_limit import check_and_record_hint
    challenge_id = body.get("challengeId", "")
    challenge = dict(authorized_challenge.value)

    usage_counter = check_and_record_hint(
        actor.user_id,
        challenge_id,
        limit=_hint_limit_for_student(actor.user_id),
    )

    hint = challenge.get("hint", "")
    if not hint:
        # Generate hint with Bedrock using the dedicated hint function
        try:
            from stoa.services.ai_service import get_hint_answer
            hint = get_hint_answer(
                prompt=challenge["prompt"],
                subject=challenge.get("subject_id", "Mathematik"),
                grade=challenge.get("grade_level", "6. Klasse"),
            )
        except Exception:
            pass
        if not hint:
            hint = "Schau dir die Grundregeln für dieses Thema noch einmal an."

    _record_practice_usage(
        student_id=actor.user_id,
        action=usage_ledger_service.HINT_REQUEST_ACTION,
        resource_id=challenge_id,
        usage_counter=usage_counter,
        metadata={
            "challenge_id": challenge_id,
            "lesson_id": challenge.get("lesson_id"),
            "subject": challenge.get("subject_id"),
            "topic_id": challenge.get("topic_id"),
            "status": "returned",
        },
    )

    return {
        "title": "Hinweis",
        "hint": hint,
        "nextStep": "Versuche die Aufgabe mit dem Hinweis nochmals zu lösen.",
    }


@router.post("/teacher-help")
async def request_teacher_help(
    body: dict,
    actor: Actor = Depends(_practice_update),
    authorized_challenge: AuthorizedResource = Depends(_authorized_body_challenge_update),
):
    import uuid
    challenge_id = str(body.get("challengeId") or "").strip()
    challenge = dict(authorized_challenge.value)

    request_id = str(uuid.uuid4())
    _record_practice_usage(
        student_id=actor.user_id,
        action=usage_ledger_service.PRACTICE_TEACHER_HELP_ACTION,
        resource_id=challenge_id,
        metadata={
            "challenge_id": challenge_id,
            "request_id": request_id,
            "lesson_id": body.get("lessonId") or challenge.get("lesson_id"),
            "subject": body.get("subjectId") or challenge.get("subject_id"),
            "topic_id": body.get("topicId") or challenge.get("topic_id"),
            "status": "ready",
        },
    )
    return {
        "requestId": request_id,
        "status": "ready",
        "message": "Ein Lehrer wird sich deine Aufgabe ansehen.",
    }


def _record_practice_usage(
    *,
    student_id: str,
    action: str,
    resource_id: str,
    metadata: dict[str, Any],
    usage_counter: dict | None = None,
) -> None:
    try:
        usage_ledger_service.record_usage_event(
            student_id=student_id,
            action=action,
            quota_period=(usage_counter or {}).get("quotaPeriod") or usage_ledger_service.today_period(),
            idempotency_key=usage_ledger_service.build_usage_idempotency_key(
                action=action,
                resource_id=resource_id,
                qualifier=student_id,
            ),
            counter_key=(usage_counter or {}).get("counterKey"),
            counter_value=(usage_counter or {}).get("counterValue"),
            request_correlation_id=resource_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Practice usage ledger write failed", exc_info=True)
