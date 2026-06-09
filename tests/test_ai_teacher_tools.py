from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.deps import get_current_user
from stoa.routers import tutors
from stoa.services import ai_teacher_tools_service


def _app(user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(tutors.router, prefix="/tutors")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _install_draft_repo(monkeypatch):
    drafts: dict[str, dict] = {}

    def put_draft(item):
        drafts[item["draft_id"]] = dict(item)

    def get_draft(draft_id):
        item = drafts.get(draft_id)
        return dict(item) if item else None

    def update_draft(draft_id, updates):
        drafts[draft_id].update(updates)
        return dict(drafts[draft_id])

    def list_drafts(student_id=None, status=None, draft_type=None, limit=100):
        items = list(drafts.values())
        if student_id is not None:
            items = [item for item in items if item.get("student_id") == student_id]
        if status is not None:
            items = [item for item in items if item.get("status") == status]
        if draft_type is not None:
            items = [item for item in items if item.get("draft_type") == draft_type]
        return items[:limit]

    monkeypatch.setattr(ai_teacher_tools_service.ai_teacher_tools_repo, "put_draft", put_draft)
    monkeypatch.setattr(ai_teacher_tools_service.ai_teacher_tools_repo, "get_draft", get_draft)
    monkeypatch.setattr(ai_teacher_tools_service.ai_teacher_tools_repo, "update_draft", update_draft)
    monkeypatch.setattr(ai_teacher_tools_service.ai_teacher_tools_repo, "list_drafts", list_drafts)
    return drafts


def _question(**overrides):
    return {
        "question_id": "question-1",
        "student_id": "student-1",
        "status": "escalated",
        "subject": "math",
        "content": "Why does moving 4 change the equation?",
        "ai_response": {"answer": "Use inverse operations to isolate x."},
        "topic_seeds": [{"label": "Linear equations"}],
        "knowledge_points": ["inverse operations"],
        "teacher_response": None,
        **overrides,
    }


def test_tutor_can_create_summary_draft_for_visible_question(monkeypatch):
    drafts = _install_draft_repo(monkeypatch)
    monkeypatch.setattr(
        ai_teacher_tools_service.question_repo,
        "get_question",
        lambda question_id: _question(question_id=question_id),
    )

    response = _app({"sub": "tutor-1", "role": "tutor"}).post(
        "/tutors/questions/question-1/ai-tools/summary-draft"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["draftType"] == "teacher_summary"
    assert body["status"] == "draft"
    assert body["studentDeliveryStatus"] == "not_delivered"
    assert "Linear equations" in body["misconceptionSummary"]
    assert body["sourceContext"]["evidenceQuestionIds"] == ["question-1"]
    assert drafts[body["draftId"]]["prompt_version"] == "stoa_ai_teacher_tools_v1"


def test_summary_draft_requires_visible_question(monkeypatch):
    _install_draft_repo(monkeypatch)
    monkeypatch.setattr(
        ai_teacher_tools_service.question_repo,
        "get_question",
        lambda question_id: _question(status="ai_answered"),
    )

    response = _app({"sub": "tutor-1", "role": "tutor"}).post(
        "/tutors/questions/question-1/ai-tools/summary-draft"
    )

    assert response.status_code == 403


def test_tutor_can_create_bounded_exercise_draft_from_visible_student_context(monkeypatch):
    _install_draft_repo(monkeypatch)
    monkeypatch.setattr(
        ai_teacher_tools_service.question_repo,
        "list_by_student",
        lambda student_id, limit=50: {
            "Items": [_question(student_id=student_id, question_id="question-2")]
        },
    )

    response = _app({"sub": "tutor-1", "role": "tutor"}).post(
        "/tutors/ai-tools/exercise-drafts",
        json={
            "studentId": "student-1",
            "subject": "math",
            "topicIds": ["Linear equations"],
            "difficulty": "medium",
            "exerciseCount": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["draftType"] == "practice_exercise"
    assert body["topicIds"] == ["linear-equations"]
    assert len(body["items"]) == 3
    assert len(body["answerKey"]) == 3
    assert body["studentDeliveryStatus"] == "not_delivered"
    assert body["sourceContext"]["evidenceQuestionIds"] == ["question-2"]


def test_exercise_draft_rejects_out_of_bounds_count(monkeypatch):
    _install_draft_repo(monkeypatch)

    response = _app({"sub": "admin-1", "role": "admin"}).post(
        "/tutors/ai-tools/exercise-drafts",
        json={
            "studentId": "student-1",
            "subject": "math",
            "topicIds": ["fractions"],
            "difficulty": "easy",
            "exerciseCount": 8,
        },
    )

    assert response.status_code == 400


def test_draft_lifecycle_accept_archive_and_regenerate_preserve_review_boundary(monkeypatch):
    drafts = _install_draft_repo(monkeypatch)
    monkeypatch.setattr(
        ai_teacher_tools_service.question_repo,
        "get_question",
        lambda question_id: _question(question_id=question_id, teacher_id="tutor-1", status="teacher_active"),
    )
    client = _app({"sub": "tutor-1", "role": "tutor"})
    created = client.post("/tutors/questions/question-1/ai-tools/summary-draft").json()

    accepted = client.post(
        f"/tutors/ai-tools/drafts/{created['draftId']}/accept",
        json={"note": "Looks usable"},
    )

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["studentDeliveryStatus"] == "not_delivered"
    assert drafts[created["draftId"]]["review_note"] == "Looks usable"

    regenerated = client.post(f"/tutors/ai-tools/drafts/{created['draftId']}/regenerate")
    assert regenerated.status_code == 200
    regenerated_body = regenerated.json()
    assert regenerated_body["previousDraftId"] == created["draftId"]
    assert regenerated_body["status"] == "draft"

    archived = client.post(f"/tutors/ai-tools/drafts/{regenerated_body['draftId']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
