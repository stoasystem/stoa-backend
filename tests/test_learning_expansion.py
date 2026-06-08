import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings, get_settings
from stoa.deps import get_current_user
from stoa.routers import parents, questions, students
from stoa.services import ai_service, learning_profile_service


def _settings() -> Settings:
    return Settings(
        free_tier_daily_question_limit=10,
        standard_tier_daily_question_limit=30,
        premium_tier_daily_question_limit=100,
        s3_images_bucket="images-bucket",
    )


def _question_client(user: dict | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(questions.router, prefix="/questions")
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_current_user] = lambda: user or {"sub": "student-1", "role": "student"}
    return TestClient(app)


def _students_client(user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _parents_client(user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_submit_question_accepts_foundation_subject_and_stores_topic_seeds(monkeypatch):
    stored = {}
    update_calls = []

    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "subscription_tier": "free", "grade": "Grade 8", "language": "en"},
    )
    monkeypatch.setattr(questions.question_repo, "record_daily_question_usage", lambda *args: 1)
    monkeypatch.setattr(questions.question_repo, "put_question", lambda item: stored.update(item))
    monkeypatch.setattr(
        questions.question_repo,
        "update_status",
        lambda *args, **kwargs: update_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **kwargs: {
            "answer": "Use force equals mass times acceleration.",
            "steps": ["Identify known values."],
            "hints": [],
            "similar_exercises": [],
            "knowledge_points": ["Newton's second law"],
        },
    )

    response = _question_client().post(
        "/questions",
        json={"content": "A 2 kg object accelerates at 3 m/s^2.", "subject": "physics"},
    )

    assert response.status_code == 201
    body = response.json()
    assert stored["subject"] == "physics"
    assert body["subject"] == "physics"
    assert body["knowledge_points"] == ["Newton's second law"]
    assert body["topic_seeds"][0]["topic_id"] == "newton-s-second-law"
    assert update_calls[0][1]["topic_seeds"][0]["subject"] == "physics"


def test_submit_question_rejects_uncontracted_subject():
    response = _question_client().post(
        "/questions",
        json={"content": "Explain this sentence please.", "subject": "french"},
    )

    assert response.status_code == 422


def test_ai_prompt_context_differs_for_language_subject(monkeypatch):
    captured = {}

    class FakeBody:
        def read(self):
            return json.dumps(
                {
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "steps": ["Review the grammar."],
                                    "answer": "Corrected sentence.",
                                    "hints": [],
                                    "similar_exercises": [],
                                    "knowledge_points": ["word order"],
                                }
                            )
                        }
                    ]
                }
            ).encode()

    class FakeBedrock:
        def invoke_model(self, **kwargs):
            captured.update(kwargs)
            return {"body": FakeBody()}

    monkeypatch.setattr(ai_service.boto3, "client", lambda *args, **kwargs: FakeBedrock())

    answer = ai_service.get_ai_answer(
        content="Correct this sentence",
        subject="german",
        grade="Grade 8",
        language="de",
    )

    payload = json.loads(captured["body"])
    assert "language learning" in payload["system"]
    assert "Subject label: German" in payload["system"]
    assert answer["knowledge_points"] == ["word order"]


def test_learning_profile_aggregates_subject_activity_and_topic_seeds(monkeypatch):
    questions_for_student = [
        {
            "question_id": "q1",
            "student_id": "student-1",
            "subject": "physics",
            "status": "ai_answered",
            "knowledge_points": ["forces"],
            "topic_seeds": [
                {
                    "subject": "physics",
                    "topic_id": "forces",
                    "label": "forces",
                    "evidence_question_ids": ["q1"],
                    "last_seen_at": "2026-06-08T08:00:00+00:00",
                }
            ],
            "student_feedback": 4,
            "created_at": "2026-06-08T08:00:00+00:00",
        },
        {
            "question_id": "q2",
            "student_id": "student-1",
            "subject": "german",
            "status": "escalated",
            "knowledge_points": ["word order"],
            "student_feedback": 2,
            "created_at": "2026-06-08T09:00:00+00:00",
        },
    ]
    monkeypatch.setattr(
        students.question_repo,
        "list_by_student",
        lambda student_id, limit=500: {"Items": questions_for_student},
    )
    monkeypatch.setattr(
        students.practice_repo,
        "get_mistakes",
        lambda student_id: [{"subject_id": "physics", "topic_id": "forces", "created_at": "2026-06-08T10:00:00+00:00"}],
    )

    response = _students_client({"sub": "student-1", "role": "student"}).get(
        "/students/student-1/learning-profile"
    )

    assert response.status_code == 200
    body = response.json()
    physics = next(item for item in body["subjectActivity"] if item["subject"] == "physics")
    german = next(item for item in body["subjectActivity"] if item["subject"] == "german")
    assert physics["questionCount"] == 1
    assert physics["feedbackAverage"] == 4
    assert german["teacherEscalationCount"] == 1
    assert body["weakTopics"][0]["topicId"] == "forces"
    assert body["weakTopics"][0]["count"] == 2


def test_parent_child_learning_profile_requires_owned_child(monkeypatch):
    resolved = parents.ResolvedParent(
        claims_sub="parent-claims",
        email="parent@example.com",
        parent_user_id="parent-1",
        profile={"user_id": "parent-1", "role": "parent"},
    )
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: resolved)
    monkeypatch.setattr(parents, "_get_owned_child_profile", lambda parent, child_id: {"user_id": child_id})
    monkeypatch.setattr(
        parents.question_repo,
        "list_by_student",
        lambda student_id, limit=500: {
            "Items": [
                {
                    "question_id": "q1",
                    "student_id": student_id,
                    "subject": "math",
                    "status": "ai_answered",
                    "knowledge_points": ["fractions"],
                    "created_at": "2026-06-08T08:00:00+00:00",
                }
            ]
        },
    )
    monkeypatch.setattr(parents.practice_repo, "get_mistakes", lambda student_id: [])

    response = _parents_client({"sub": "parent-claims", "role": "parent"}).get(
        "/parents/me/children/child-1/learning-profile"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["studentId"] == "child-1"
    assert body["weakTopics"][0]["topicId"] == "fractions"


def test_learning_subject_contract_is_limited_to_v3_4_subjects():
    assert learning_profile_service.supported_subject_ids() == {"math", "physics", "german", "english"}
