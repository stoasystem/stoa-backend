from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.routers import teachers
from stoa.services import ai_teacher_tools_service
from actor_helpers import install_actor_overrides


def _app(user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(teachers.router, prefix="/teachers")
    install_actor_overrides(app, user)
    return TestClient(app)


def _install_draft_repo(monkeypatch):
    drafts: dict[str, dict] = {}

    def put_draft(item):
        drafts[item["draft_id"]] = dict(item)

    def get_draft(draft_id):
        item = drafts.get(draft_id)
        return dict(item) if item else None

    def update_draft(draft_id, updates, *, existing=None):
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
        "status": "teacher_active",
        "teacher_id": "teacher-1",
        "subject": "math",
        "content": "Why does moving 4 change the equation?",
        "ai_response": {"answer": "Use inverse operations to isolate x."},
        "topic_seeds": [{"label": "Linear equations"}],
        "knowledge_points": ["inverse operations"],
        "teacher_response": None,
        **overrides,
    }


def test_teacher_can_create_summary_draft_for_visible_question(monkeypatch):
    drafts = _install_draft_repo(monkeypatch)
    monkeypatch.setattr(
        teachers.question_repo,
        "get_question",
        lambda question_id: _question(question_id=question_id),
    )

    response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/teachers/questions/question-1/ai-tools/summary-draft"
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
        teachers.question_repo,
        "get_question",
        lambda question_id: _question(status="ai_answered"),
    )

    response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/teachers/questions/question-1/ai-tools/summary-draft"
    )

    assert response.status_code == 403


def test_teacher_can_create_bounded_exercise_draft_from_visible_student_context(monkeypatch):
    _install_draft_repo(monkeypatch)
    monkeypatch.setattr(
        teachers.question_repo,
        "get_question",
        lambda question_id: _question(student_id="student-1", question_id=question_id),
    )

    response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/teachers/ai-tools/exercise-drafts",
        json={
            "studentId": "student-1",
            "subject": "math",
            "topicIds": ["Linear equations"],
            "difficulty": "medium",
            "exerciseCount": 3,
            "questionId": "question-2",
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
    monkeypatch.setattr(
        teachers.question_repo,
        "get_question",
        lambda question_id: _question(question_id=question_id),
    )

    response = _app(
        {
            "sub": "admin-1",
            "role": "admin",
            "grantCapabilities": ["ai_teacher_tools_operator"],
            "grantScope": "global",
        }
    ).post(
        "/teachers/ai-tools/exercise-drafts",
        json={
            "studentId": "student-1",
            "subject": "math",
            "topicIds": ["fractions"],
            "difficulty": "easy",
            "exerciseCount": 8,
            "questionId": "question-1",
        },
    )

    assert response.status_code == 400


def test_draft_lifecycle_accept_archive_and_regenerate_preserve_review_boundary(monkeypatch):
    drafts = _install_draft_repo(monkeypatch)
    monkeypatch.setattr(
        teachers.question_repo,
        "get_question",
        lambda question_id: _question(question_id=question_id, teacher_id="teacher-1", status="teacher_active"),
    )
    client = _app({"sub": "teacher-1", "role": "teacher"})
    created = client.post("/teachers/questions/question-1/ai-tools/summary-draft").json()

    accepted = client.post(
        f"/teachers/ai-tools/drafts/{created['draftId']}/accept",
        json={"note": "Looks usable"},
    )

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["studentDeliveryStatus"] == "not_delivered"
    assert drafts[created["draftId"]]["review_note"] == "Looks usable"

    regenerated = client.post(f"/teachers/ai-tools/drafts/{created['draftId']}/regenerate")
    assert regenerated.status_code == 200
    regenerated_body = regenerated.json()
    assert regenerated_body["previousDraftId"] == created["draftId"]
    assert regenerated_body["status"] == "draft"

    archived = client.post(f"/teachers/ai-tools/drafts/{regenerated_body['draftId']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_cross_teacher_and_stale_draft_ids_are_hidden_without_mutation(monkeypatch):
    drafts = _install_draft_repo(monkeypatch)
    draft = {
        "draft_id": "draft-1",
        "draft_type": "teacher_summary",
        "status": "draft",
        "student_id": "student-1",
        "question_id": "question-1",
        "created_by": "teacher-1",
        "created_by_role": "teacher",
    }
    drafts[draft["draft_id"]] = dict(draft)

    other = _app(
        {
            "sub": "teacher-2",
            "role": "teacher",
            "taskTeacherId": "teacher-1",
        }
    ).post("/teachers/ai-tools/drafts/draft-1/accept")
    stale = _app(
        {
            "sub": "teacher-1",
            "role": "teacher",
            "taskTeacherId": "teacher-2",
            "taskDispatchStatus": "reassigned",
        }
    ).post("/teachers/ai-tools/drafts/draft-1/accept")

    assert other.status_code == 404
    assert stale.status_code == 404
    assert drafts["draft-1"]["status"] == "draft"


def test_draft_list_filters_noncurrent_tasks_and_operator_grant_can_broaden(monkeypatch):
    drafts = _install_draft_repo(monkeypatch)
    for draft_id, question_id, creator in (
        ("draft-current", "question-current", "teacher-1"),
        ("draft-other", "question-other", "teacher-2"),
    ):
        drafts[draft_id] = {
            "draft_id": draft_id,
            "draft_type": "teacher_summary",
            "status": "draft",
            "student_id": "student-1",
            "question_id": question_id,
            "created_by": creator,
            "created_by_role": "teacher",
        }

    teacher = _app(
        {
            "sub": "teacher-1",
            "role": "teacher",
            "taskTeacherByQuestion": {
                "question-current": "teacher-1",
                "question-other": "teacher-2",
            },
        }
    ).get("/teachers/ai-tools/drafts")
    operator = _app(
        {
            "sub": "admin-1",
            "role": "admin",
            "grantCapabilities": ["ai_teacher_tools_operator"],
            "grantScope": "global",
        }
    ).get("/teachers/ai-tools/drafts")

    assert [item["draftId"] for item in teacher.json()["items"]] == ["draft-current"]
    assert {item["draftId"] for item in operator.json()["items"]} == {
        "draft-current",
        "draft-other",
    }


def test_plain_teacher_role_does_not_broaden_draft_or_curriculum_scope(monkeypatch):
    drafts = _install_draft_repo(monkeypatch)
    drafts["draft-other"] = {
        "draft_id": "draft-other",
        "draft_type": "teacher_summary",
        "status": "draft",
        "student_id": "student-1",
        "question_id": "question-other",
        "created_by": "teacher-2",
    }
    response = _app(
        {"sub": "teacher-1", "role": "teacher", "taskTeacherId": "teacher-2"}
    ).get("/teachers/ai-tools/drafts/draft-other")

    assert response.status_code == 404


def test_draft_repository_outage_returns_503_before_tool_invocation(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ai_teacher_tools_service.ai_teacher_tools_repo,
        "get_draft",
        lambda _draft_id: (_ for _ in ()).throw(RuntimeError("repository unavailable")),
    )
    monkeypatch.setattr(
        ai_teacher_tools_service,
        "regenerate_draft",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/teachers/ai-tools/drafts/draft-1/regenerate"
    )

    assert response.status_code == 503
    assert calls == []
