"""Practice module routes — subjects, topics, lessons, challenges, progress.

API contract matches stoa-frontend/src/services/practice/practiceApi.ts.
All content is pre-seeded in DynamoDB (PK=PRACTICE, SK=SUBJECT#…/TOPIC#…/LESSON#…/CHALLENGE#…).
Student progress is stored under PK=PROGRESS#{user_id}.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from stoa.db.repositories import practice_repo
from stoa.deps import get_current_user, require_role

router = APIRouter()
logger = logging.getLogger(__name__)


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


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/subjects")
async def list_subjects(user: dict = Depends(get_current_user)):
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
async def get_overview(user: dict = Depends(require_role("student"))):
    """Return a recommended next lesson for the student."""
    user_id = user["sub"]
    progress = practice_repo.get_progress(user_id)
    completed_ids = {p["lesson_id"] for p in progress if p.get("status") == "completed"}

    # Find the first lesson not yet completed
    all_lessons = practice_repo.get_lessons()
    recommended_raw = None
    for l in sorted(all_lessons, key=lambda x: (x.get("topic_id", ""), x.get("order", 0))):
        if l["lesson_id"] not in completed_ids:
            recommended_raw = l
            break

    if not recommended_raw:
        recommended_raw = all_lessons[0] if all_lessons else None

    if not recommended_raw:
        raise HTTPException(status_code=404, detail="No lessons available")

    challenges = [_build_challenge(c)
                  for c in practice_repo.get_challenges(recommended_raw["lesson_id"])]
    recommended = _build_lesson(recommended_raw, challenges, "available")

    return {
        "subjectId": recommended_raw.get("subject_id", "mathematics"),
        "topicId": recommended_raw.get("topic_id", ""),
        "recommendedLesson": recommended,
    }


@router.get("/{subject_id}/{topic_id}/roadmap")
async def get_roadmap(
    subject_id: str,
    topic_id: str,
    user: dict = Depends(get_current_user),
):
    """Return the lesson roadmap for a topic."""
    topic = practice_repo.get_topic(topic_id)
    if not topic or topic.get("subject_id") != subject_id:
        raise HTTPException(status_code=404, detail="Topic not found")

    user_id = user.get("sub", "")
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
        (l["lesson_id"] for l in all_lessons if l["lesson_id"] not in completed_ids),
        all_lessons[-1]["lesson_id"] if all_lessons else None,
    )
    progress_pct = int(len(completed_ids) / len(all_lessons) * 100) if all_lessons else 0

    roadmap_units = []
    for unit_raw in units_raw:
        unit_lessons_raw = [l for l in all_lessons if l.get("unit_id") == unit_raw["unit_id"]]
        roadmap_lessons = []
        for l in unit_lessons_raw:
            st = _lesson_status(l["lesson_id"], completed_ids, current_lesson_id)
            roadmap_lessons.append({
                "id": l["lesson_id"],
                "title": l["title"],
                "description": l.get("description", ""),
                "order": l.get("order", 1),
                "status": st,
                "estimatedMinutes": l.get("estimated_minutes", 10),
                "subjectId": subject_id,
                "gradeLevel": l.get("grade_level", ""),
                "topicId": topic_id,
                "unitId": l.get("unit_id", ""),
                "challengeCount": l.get("challenge_count", 3),
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
    user: dict = Depends(get_current_user),
):
    """Return the practice path (units + lessons) for a subject/topic."""
    if topic_id:
        topics = [practice_repo.get_topic(topic_id)]
        topics = [t for t in topics if t]
    else:
        topics = practice_repo.get_topics(subject_id)

    if not topics:
        raise HTTPException(status_code=404, detail="No topics found")

    user_id = user.get("sub", "")
    progress = practice_repo.get_progress(user_id, subject_id)
    completed_ids = {p["lesson_id"] for p in progress if p.get("status") == "completed"}

    all_lessons = sorted(
        practice_repo.get_lessons(topic_id=topics[0]["topic_id"] if topic_id else None),
        key=lambda x: (x.get("topic_id", ""), x.get("unit_id", ""), x.get("order", 0)),
    )
    current_lesson_id = next(
        (l["lesson_id"] for l in all_lessons if l["lesson_id"] not in completed_ids),
        all_lessons[-1]["lesson_id"] if all_lessons else None,
    )

    units_raw = sorted(
        practice_repo.get_units(topics[0]["topic_id"]) if topic_id
        else [], key=lambda x: x.get("order", 0)
    )

    path_units = []
    for unit_raw in units_raw:
        unit_lessons_raw = [l for l in all_lessons if l.get("unit_id") == unit_raw["unit_id"]]
        unit_lessons = []
        for l in unit_lessons_raw:
            challenges = [_build_challenge(c)
                          for c in practice_repo.get_challenges(l["lesson_id"])]
            st = _lesson_status(l["lesson_id"], completed_ids, current_lesson_id)
            unit_lessons.append(_build_lesson(l, challenges, st))
        path_units.append(_build_unit(unit_raw, unit_lessons))

    return {
        "subjectId": subject_id,
        "gradeLevel": topics[0].get("grade_level", "") if topics else "",
        "topicId": topics[0]["topic_id"] if topics else "",
        "topicTitle": topics[0]["title"] if topics else "",
        "units": path_units,
    }


@router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: str, user: dict = Depends(get_current_user)):
    lesson = practice_repo.get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    user_id = user.get("sub", "")
    progress = practice_repo.get_progress(user_id)
    completed_ids = {p["lesson_id"] for p in progress if p.get("status") == "completed"}
    all_lessons = sorted(
        practice_repo.get_lessons(topic_id=lesson.get("topic_id")),
        key=lambda x: x.get("order", 0),
    )
    current_id = next(
        (l["lesson_id"] for l in all_lessons if l["lesson_id"] not in completed_ids),
        None,
    )
    st = _lesson_status(lesson_id, completed_ids, current_id)
    challenges = [_build_challenge(c) for c in practice_repo.get_challenges(lesson_id)]
    return _build_lesson(lesson, challenges, st)


@router.post("/lessons/{lesson_id}/complete")
async def complete_lesson(
    lesson_id: str,
    user: dict = Depends(require_role("student")),
):
    lesson = practice_repo.get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    practice_repo.mark_lesson_completed(user["sub"], lesson)
    all_lessons = sorted(
        practice_repo.get_lessons(topic_id=lesson.get("topic_id")),
        key=lambda x: x.get("order", 0),
    )
    completed_ids = {p["lesson_id"] for p in practice_repo.get_progress(user["sub"])
                     if p.get("status") == "completed"}
    next_lesson = next(
        (l for l in all_lessons if l["lesson_id"] not in completed_ids), None
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
    user: dict = Depends(require_role("student")),
):
    challenge = practice_repo.get_challenge(challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    student_answer = body.get("answer", "")
    correct_answer = challenge.get("correct_answer", "")

    # Normalise for comparison
    def _norm(v: Any) -> str:
        if isinstance(v, list):
            return "|".join(str(x).strip().lower() for x in v)
        return str(v).strip().lower()

    correct = _norm(student_answer) == _norm(correct_answer)

    # Find challenges in the same lesson for next_challenge_id
    lesson_id = challenge.get("lesson_id", "")
    all_challenges = practice_repo.get_challenges(lesson_id)
    challenge_ids = [c["challenge_id"] for c in all_challenges]
    try:
        idx = challenge_ids.index(challenge_id)
        next_challenge_id = challenge_ids[idx + 1] if idx + 1 < len(challenge_ids) else None
    except ValueError:
        next_challenge_id = None

    user_id = user["sub"]
    practice_repo.record_attempt(
        user_id, challenge_id, correct,
        subject_id=challenge.get("subject_id", ""),
        lesson_id=lesson_id,
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
async def get_mistakes(user: dict = Depends(require_role("student"))):
    user_id = user["sub"]
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
async def get_hint(body: dict, user: dict = Depends(require_role("student"))):
    challenge_id = body.get("challengeId", "")
    challenge = practice_repo.get_challenge(challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    hint = challenge.get("hint", "")
    if not hint:
        # Generate hint with Bedrock
        try:
            from stoa.services.ai_service import get_ai_answer
            hint = get_ai_answer(
                question=f"Gib einen kurzen Hinweis (1-2 Sätze) für diese Mathe-Aufgabe: {challenge['prompt']}",
                grade="6. Klasse",
                subject="Mathematik",
                context=[],
            )
        except Exception:
            hint = "Schau dir die Grundregeln für dieses Thema noch einmal an."

    return {
        "title": "Hinweis",
        "hint": hint,
        "nextStep": "Versuche die Aufgabe mit dem Hinweis nochmals zu lösen.",
    }


@router.post("/teacher-help")
async def request_teacher_help(body: dict, user: dict = Depends(require_role("student"))):
    import uuid
    return {
        "requestId": str(uuid.uuid4()),
        "status": "ready",
        "message": "Ein Lehrer wird sich deine Aufgabe ansehen.",
    }
