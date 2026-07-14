from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.routers import practice
from stoa.security import route_authorization
from actor_helpers import install_actor_overrides


SUBJECTS = [
    {
        "subject_id": "math",
        "name": "Mathematics",
        "description": "Math rollout",
        "grade_levels": ["lower_secondary"],
        "status": "active",
        "order": 1,
    },
    {
        "subject_id": "physics",
        "name": "Physics",
        "grade_levels": ["lower_secondary"],
        "status": "draft",
        "order": 2,
    },
    {
        "subject_id": "french",
        "name": "French",
        "grade_levels": ["lower_secondary"],
        "status": "active",
        "order": 3,
    },
]

TOPICS = [
    {
        "topic_id": "linear-equations",
        "subject_id": "math",
        "grade_level": "lower_secondary",
        "title": "Linear equations",
        "status": "active",
        "order": 1,
    },
    {
        "topic_id": "forces",
        "subject_id": "physics",
        "grade_level": "lower_secondary",
        "title": "Forces",
        "status": "draft",
        "order": 2,
    },
]

UNITS = [
    {
        "unit_id": "unit-linear",
        "subject_id": "math",
        "topic_id": "linear-equations",
        "grade_level": "lower_secondary",
        "title": "Solving equations",
        "status": "active",
        "order": 1,
    },
    {
        "unit_id": "unit-forces",
        "subject_id": "physics",
        "topic_id": "forces",
        "grade_level": "lower_secondary",
        "title": "Forces",
        "status": "draft",
        "order": 1,
    },
]

LESSONS = [
    {
        "lesson_id": "lesson-linear-1",
        "subject_id": "math",
        "topic_id": "linear-equations",
        "unit_id": "unit-linear",
        "grade_level": "lower_secondary",
        "title": "Solve one-step equations",
        "description": "Use inverse operations.",
        "objective": "Isolate x in one step.",
        "explanation": "Undo the same operation on both sides.",
        "examples": ["x + 4 = 9"],
        "difficulty": "standard",
        "estimated_minutes": 12,
        "status": "active",
        "order": 1,
    },
    {
        "lesson_id": "lesson-forces-1",
        "subject_id": "physics",
        "topic_id": "forces",
        "unit_id": "unit-forces",
        "grade_level": "lower_secondary",
        "title": "Net force",
        "difficulty": "standard",
        "status": "draft",
        "order": 1,
    },
]

CHALLENGES = [
    {
        "challenge_id": "challenge-linear-1",
        "lesson_id": "lesson-linear-1",
        "subject_id": "math",
        "topic_id": "linear-equations",
        "prompt": "Solve x + 4 = 9.",
        "correct_answer": "x = 5",
        "explanation": "Subtract 4 from both sides.",
        "difficulty": "standard",
        "status": "active",
        "order": 1,
    },
    {
        "challenge_id": "challenge-forces-1",
        "lesson_id": "lesson-forces-1",
        "subject_id": "physics",
        "topic_id": "forces",
        "prompt": "Find the net force.",
        "correct_answer": "5 N",
        "difficulty": "standard",
        "status": "draft",
        "order": 1,
    },
]


def _client(user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, user)
    return TestClient(app)


def _install_practice_content(monkeypatch):
    monkeypatch.setattr(practice.practice_repo, "get_subjects", lambda: list(SUBJECTS))
    monkeypatch.setattr(
        practice.practice_repo,
        "get_topics",
        lambda subject_id=None: [item for item in TOPICS if subject_id is None or item["subject_id"] == subject_id],
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "get_units",
        lambda topic_id: [item for item in UNITS if item["topic_id"] == topic_id],
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "get_lessons",
        lambda topic_id=None, unit_id=None: [
            item
            for item in LESSONS
            if (topic_id is None or item["topic_id"] == topic_id)
            and (unit_id is None or item["unit_id"] == unit_id)
        ],
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "get_lesson",
        lambda lesson_id: next((item for item in LESSONS if item["lesson_id"] == lesson_id), None),
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "get_challenges",
        lambda lesson_id: [item for item in CHALLENGES if item["lesson_id"] == lesson_id],
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "get_all_challenges",
        lambda lesson_id=None, subject_id=None, topic_id=None: [
            item
            for item in CHALLENGES
            if (lesson_id is None or item["lesson_id"] == lesson_id)
            and (subject_id is None or item["subject_id"] == subject_id)
            and (topic_id is None or item["topic_id"] == topic_id)
        ],
    )


def test_curriculum_catalog_filters_active_supported_content(monkeypatch):
    _install_practice_content(monkeypatch)

    response = _client({"sub": "student-1", "role": "student"}).get(
        "/practice/curriculum/catalog?gradeLevel=lower_secondary"
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["subjects"]] == ["math"]
    assert [item["id"] for item in body["topics"]] == ["linear-equations"]
    assert [item["id"] for item in body["lessons"]] == ["lesson-linear-1"]
    assert body["lessons"][0]["exerciseCount"] == 1
    assert "french" not in body["rolloutSubjects"]


def test_curriculum_preview_requires_teacher_or_admin(monkeypatch):
    _install_practice_content(monkeypatch)

    blocked = _client({"sub": "student-1", "role": "student"}).get(
        "/practice/curriculum/catalog?includePreview=true"
    )
    allowed = _client({"sub": "teacher-1", "role": "teacher"}).get(
        "/practice/curriculum/catalog?includePreview=true&rolloutState=draft"
    )

    assert blocked.status_code == 403
    assert allowed.status_code == 200
    assert [item["id"] for item in allowed.json()["subjects"]] == ["physics"]
    assert [item["id"] for item in allowed.json()["lessons"]] == ["lesson-forces-1"]


def test_curriculum_lesson_hides_answer_key_from_student(monkeypatch):
    _install_practice_content(monkeypatch)

    student = _client({"sub": "student-1", "role": "student"}).get(
        "/practice/curriculum/lessons/lesson-linear-1?includeAnswers=true"
    )
    teacher = _client({"sub": "teacher-1", "role": "teacher"}).get(
        "/practice/curriculum/lessons/lesson-linear-1?includeAnswers=true"
    )

    assert student.status_code == 200
    assert "answerKey" not in student.json()["exercises"][0]
    assert teacher.status_code == 200
    assert teacher.json()["exercises"][0]["answerKey"] == "x = 5"


def test_curriculum_progress_uses_existing_practice_records(monkeypatch):
    _install_practice_content(monkeypatch)
    monkeypatch.setattr(
        route_authorization.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
        },
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "get_progress",
        lambda student_id, subject_id=None: [
            {
                "lesson_id": "lesson-linear-1",
                "subject_id": "math",
                "topic_id": "linear-equations",
                "status": "completed",
            }
        ],
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "get_mistakes",
        lambda student_id: [
            {"challenge_id": "challenge-linear-1", "subject_id": "math", "topic_id": "linear-equations"}
        ],
    )

    response = _client({"sub": "student-1", "role": "student"}).get(
        "/practice/curriculum/progress?subjectId=math"
    )
    forbidden = _client({"sub": "student-1", "role": "student"}).get(
        "/practice/curriculum/progress?studentId=student-2"
    )
    teacher = _client({"sub": "teacher-1", "role": "teacher"}).get(
        "/practice/curriculum/progress?studentId=student-1&subjectId=math"
    )

    assert response.status_code == 200
    assert response.json()["completedLessonIds"] == ["lesson-linear-1"]
    assert response.json()["weakTopics"] == [{"topicId": "linear-equations", "count": 1}]
    assert forbidden.status_code == 404
    assert teacher.status_code == 200
