import json
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings
from stoa.db.repositories import user_repo
from stoa.deps import get_actor, get_current_user
from stoa.routers import parents, students
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import ai_service, ask_answer, learning_profile_service
from actor_helpers import install_actor_overrides


def _settings() -> Settings:
    return Settings(
        free_tier_daily_question_limit=10,
        standard_tier_daily_question_limit=30,
        premium_tier_daily_question_limit=100,
        s3_images_bucket="images-bucket",
    )


def _students_client(user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    app.dependency_overrides[get_current_user] = lambda: user
    role = CanonicalRole(user["role"])
    app.dependency_overrides[get_actor] = lambda: Actor(
        user["sub"], "https://identity.test", f"{user['sub']}-subject", role,
        AccountStatus.ACTIVE, role.value,
    )
    return TestClient(app)


def _parents_client(user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    install_actor_overrides(app, user)
    return TestClient(app)


def test_ai_prompt_context_differs_for_language_subject(monkeypatch):
    captured = {}

    class FakeBody:
        def read(self):
            return json.dumps(
                {
                    "id": "msg-learning-expansion",
                    "model": "anthropic.claude-sonnet-4-6",
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
                    ],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 31, "output_tokens": 12},
                }
            ).encode()

        def close(self):
            return None

    class FakeBedrock:
        def invoke_model(self, **kwargs):
            captured.update(kwargs)
            return {
                "body": FakeBody(),
                "ResponseMetadata": {
                    "HTTPStatusCode": 200,
                    "RequestId": "request-learning-expansion",
                },
            }

    monkeypatch.setattr(ai_service.boto3, "client", lambda *args, **kwargs: FakeBedrock())

    answer = ask_answer.answer(
        ask_answer.Asked(content="Correct this sentence"),
        ask_answer.Asker(student_id="student-1", subject="german", grade="Grade 8", locale="de"),
        ask_answer.ModelCall(),
        read_star_map=lambda *_a, **_k: None,
    )

    payload = json.loads(captured["body"])
    assert "language learning" in payload["system"]
    assert "Subject label: German" in payload["system"]
    assert [point.name for point in answer.structured.knowledgePoints] == ["word order"]
    assert answer.provider is not None
    assert answer.provider.usage.input_tokens == 31
    assert answer.provider.usage.output_tokens == 12


def test_learning_profile_aggregates_subject_activity_and_topic_seeds(monkeypatch):
    questions_for_student = [
        {
            "PK": "QUESTION#q1",
            "SK": "META",
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
            # The table returns the stored rating as Decimal.
            "student_feedback": Decimal(4),
            "created_at": "2026-06-08T08:00:00+00:00",
        },
        {
            "PK": "QUESTION#q2",
            "SK": "META",
            "question_id": "q2",
            "student_id": "student-1",
            "subject": "german",
            "status": "escalated",
            "knowledge_points": ["word order"],
            "student_feedback": Decimal(2),
            "created_at": "2026-06-08T09:00:00+00:00",
        },
    ]
    monkeypatch.setattr(
        students.question_repo,
        "list_by_student",
        lambda student_id, limit=500, **_kwargs: {"Items": questions_for_student},
    )
    monkeypatch.setattr(
        students.practice_repo,
        "get_mistakes",
        lambda student_id: [{"subject_id": "physics", "topic_id": "forces", "created_at": "2026-06-08T10:00:00+00:00"}],
    )
    monkeypatch.setattr(
        user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
        },
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
    monkeypatch.setattr(
        parents.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
        },
    )
    monkeypatch.setattr(
        parents.question_repo,
        "list_by_student",
        lambda student_id, limit=500, **_kwargs: {
            "Items": [
                {
                    "PK": "QUESTION#q1",
                    "SK": "META",
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
