from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.deps import get_current_user
from stoa.routers import adaptive
from stoa.services import adaptive_learning_service


def _app(user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(adaptive.router, prefix="/adaptive")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _install_memory_repo(monkeypatch):
    snapshots: list[dict] = []
    assignments: dict[str, dict] = {}

    def put_memory_snapshot(item):
        snapshots.append(dict(item))

    def list_memory_snapshots(student_id, subject=None):
        items = [item for item in snapshots if item["student_id"] == student_id]
        if subject:
            items = [item for item in items if item["subject"] == subject]
        return [dict(item) for item in items]

    def put_assignment(item):
        assignments[item["assignment_id"]] = dict(item)

    def get_assignment(assignment_id):
        item = assignments.get(assignment_id)
        return dict(item) if item else None

    def update_assignment(assignment_id, updates):
        if assignment_id not in assignments:
            return None
        assignments[assignment_id].update(updates)
        return dict(assignments[assignment_id])

    def list_assignments(student_id, status=None, include_archived=False, limit=100):
        items = [item for item in assignments.values() if item["student_id"] == student_id]
        if status:
            items = [item for item in items if item["status"] == status]
        if not include_archived:
            items = [item for item in items if item["status"] != "archived"]
        return [dict(item) for item in items[:limit]]

    repo = adaptive_learning_service.adaptive_learning_repo
    monkeypatch.setattr(repo, "put_memory_snapshot", put_memory_snapshot)
    monkeypatch.setattr(repo, "list_memory_snapshots", list_memory_snapshots)
    monkeypatch.setattr(repo, "put_assignment", put_assignment)
    monkeypatch.setattr(repo, "get_assignment", get_assignment)
    monkeypatch.setattr(repo, "update_assignment", update_assignment)
    monkeypatch.setattr(repo, "list_assignments", list_assignments)
    return snapshots, assignments


def _install_learning_sources(monkeypatch):
    monkeypatch.setattr(
        adaptive_learning_service.question_repo,
        "list_by_student",
        lambda student_id, limit=500: {
            "Items": [
                {
                    "question_id": "question-1",
                    "student_id": student_id,
                    "status": "ai_answered",
                    "subject": "math",
                    "knowledge_points": ["Linear equations"],
                    "student_feedback": 2,
                    "created_at": "2026-06-09T10:00:00+00:00",
                }
            ]
        },
    )
    monkeypatch.setattr(
        adaptive_learning_service.practice_repo,
        "get_mistakes",
        lambda student_id: [
            {
                "challenge_id": "challenge-1",
                "subject_id": "math",
                "topic_id": "linear-equations",
                "lesson_id": "lesson-1",
                "created_at": "2026-06-09T11:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        adaptive_learning_service.practice_repo,
        "get_progress",
        lambda student_id, subject_id=None: [
            {
                "lesson_id": "lesson-1",
                "subject_id": "math",
                "topic_id": "linear-equations",
                "status": "completed",
                "completed_at": "2026-06-09T12:00:00+00:00",
            }
        ],
    )


def test_tutor_refreshes_memory_and_parent_gets_safe_progress(monkeypatch):
    snapshots, assignments = _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    monkeypatch.setattr(
        adaptive_learning_service.user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "role": "student", "parent_id": "parent-1"},
    )
    monkeypatch.setattr(adaptive_learning_service.user_repo, "list_parent_student_bindings", lambda parent_id: [])
    assignments["assignment-1"] = {
        "assignment_id": "assignment-1",
        "student_id": "student-1",
        "status": "assigned",
        "source_type": "ai_draft",
        "source_id": "draft-1",
        "title": "Practice linear equations",
        "subject": "math",
        "topic_ids": ["linear-equations"],
        "items": [{"prompt": "Solve x + 2 = 5"}],
        "answer_key": [{"answer": "3"}],
        "created_at": "2026-06-10T00:00:00+00:00",
        "updated_at": "2026-06-10T00:00:00+00:00",
    }

    tutor_response = _app({"sub": "tutor-1", "role": "tutor"}).post(
        "/adaptive/students/student-1/memory/refresh"
    )

    assert tutor_response.status_code == 200
    assert snapshots[0]["topic_id"] == "linear-equations"
    assert tutor_response.json()["memorySnapshots"][0]["recent_questions"] == ["question-1"]
    assert tutor_response.json()["recommendations"][0]["reviewRequired"] is True
    assert tutor_response.json()["recommendations"][0]["autonomousDecision"] is False
    assert tutor_response.json()["locale"]["effectiveLocale"] == "de"
    assert tutor_response.json()["locale"]["canonicalValuesStable"] is True

    parent_response = _app({"sub": "parent-1", "role": "parent"}).get(
        "/adaptive/parents/me/children/student-1/progress"
    )

    assert parent_response.status_code == 200
    parent_body = parent_response.json()
    assert parent_body["assignedPracticeCount"] == 1
    assert parent_body["freshness"]["status"] == "fresh"
    assert parent_body["locale"]["effectiveLocale"] == "de"
    assert "recent_questions" not in parent_body["weakAreas"][0]
    assert "evidenceQuestionIds" not in parent_body["weakAreas"][0]


def test_reviewed_ai_draft_assignment_lifecycle_is_student_owned_and_idempotent(monkeypatch):
    _install_memory_repo(monkeypatch)
    attempts: list[dict] = []
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "get_draft",
        lambda draft_id: {
            "draft_id": draft_id,
            "draft_type": "practice_exercise",
            "status": "accepted",
            "student_id": "student-1",
            "subject": "math",
            "topic_ids": ["fractions"],
            "items": [{"prompt": "Simplify 2/4"}],
            "answer_key": [{"answer": "1/2"}],
        },
    )
    monkeypatch.setattr(adaptive_learning_service.practice_repo, "record_attempt", lambda *args, **kwargs: attempts.append(kwargs))

    created = _app({"sub": "tutor-1", "role": "tutor"}).post(
        "/adaptive/assignments",
        json={
            "studentId": "student-1",
            "sourceType": "ai_draft",
            "sourceId": "draft-1",
            "status": "assigned",
        },
    )

    assert created.status_code == 200
    assignment_id = created.json()["assignmentId"]
    assert created.json()["answerKey"] == [{"answer": "1/2"}]
    assert created.json()["locale"]["effectiveLocale"] == "de"

    student_client = _app({"sub": "student-1", "role": "student"})
    started = student_client.post(f"/adaptive/assignments/{assignment_id}/start")
    completed = student_client.post(
        f"/adaptive/assignments/{assignment_id}/complete",
        json={"studentAnswer": "2/4", "correct": False},
    )
    repeated = student_client.post(
        f"/adaptive/assignments/{assignment_id}/complete",
        json={"studentAnswer": "2/4", "correct": False},
    )

    assert started.status_code == 200
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert "answerKey" not in completed.json()
    assert repeated.status_code == 200
    assert attempts == []

    forbidden = _app({"sub": "student-2", "role": "student"}).post(
        f"/adaptive/assignments/{assignment_id}/skip"
    )
    assert forbidden.status_code == 403


def test_adaptive_locale_metadata_does_not_change_canonical_values(monkeypatch):
    _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    monkeypatch.setattr(
        adaptive_learning_service.user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "role": "student", "parent_id": "parent-1"},
    )
    monkeypatch.setattr(adaptive_learning_service.user_repo, "list_parent_student_bindings", lambda parent_id: [])

    german = _app({"sub": "student-1", "role": "student", "preferredLocale": "de"}).get(
        "/adaptive/students/me/memory"
    )
    english = _app({"sub": "student-1", "role": "student", "preferredLocale": "en"}).get(
        "/adaptive/students/me/memory"
    )

    assert german.status_code == 200
    assert english.status_code == 200
    german_body = german.json()
    english_body = english.json()
    assert german_body["locale"]["effectiveLocale"] == "de"
    assert english_body["locale"]["effectiveLocale"] == "en"
    assert german_body["studentId"] == english_body["studentId"] == "student-1"
    assert german_body["roleView"] == english_body["roleView"] == "student"
    assert german_body["recommendations"][0]["type"] == english_body["recommendations"][0]["type"]
    assert german_body["recommendations"][0]["topicId"] == english_body["recommendations"][0]["topicId"]
    assert german_body["freshness"]["status"] == english_body["freshness"]["status"]


def test_curriculum_assignment_completion_updates_progress_once(monkeypatch):
    _install_memory_repo(monkeypatch)
    completed_lessons: list[str] = []
    monkeypatch.setattr(
        adaptive_learning_service.practice_repo,
        "get_challenge",
        lambda challenge_id: {
            "challenge_id": challenge_id,
            "lesson_id": "lesson-1",
            "subject_id": "math",
            "topic_id": "algebra",
            "prompt": "Solve x + 1 = 2",
            "correct_answer": "1",
        },
    )
    monkeypatch.setattr(
        adaptive_learning_service.practice_repo,
        "get_lesson",
        lambda lesson_id: {"lesson_id": lesson_id, "subject_id": "math", "topic_id": "algebra"},
    )
    monkeypatch.setattr(
        adaptive_learning_service.practice_repo,
        "mark_lesson_completed",
        lambda student_id, lesson: completed_lessons.append(lesson["lesson_id"]),
    )

    created = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/assignments",
        json={
            "studentId": "student-1",
            "sourceType": "curriculum_exercise",
            "sourceId": "challenge-1",
            "title": "Linear equation check",
        },
    )

    assert created.status_code == 200
    assignment_id = created.json()["assignmentId"]
    assert created.json()["locale"]["effectiveLocale"] == "de"
    student_client = _app({"sub": "student-1", "role": "student"})
    first = student_client.post(
        f"/adaptive/assignments/{assignment_id}/complete",
        json={"studentAnswer": "1", "correct": True},
    )
    second = student_client.post(
        f"/adaptive/assignments/{assignment_id}/complete",
        json={"studentAnswer": "1", "correct": True},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert completed_lessons == ["lesson-1"]
