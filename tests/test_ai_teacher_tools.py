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


def _request(**overrides):
    """A help request record, as stored: a question id names one (#189, #234)."""
    request_id = overrides.pop("question_id", "question-1")
    return {
        "PK": f"CONV#{request_id}",
        "SK": "HELP",
        "entity_type": "help_request",
        "conversation_id": request_id,
        "escalation_request_id": request_id,
        "student_id": "student-1",
        "escalation_status": "in_progress",
        "teacher_id": "teacher-1",
        "dispatch_status": "accepted",
        "subject": "math",
        "escalation_message": "Why does moving 4 change the equation?",
        **overrides,
    }


def _serve_requests(monkeypatch, **overrides):
    monkeypatch.setattr(
        teachers.help_requests,
        "get",
        lambda question_id, **_kwargs: _request(question_id=question_id, **overrides),
    )


def test_teacher_can_create_summary_draft_for_visible_question(monkeypatch):
    drafts = _install_draft_repo(monkeypatch)
    _serve_requests(monkeypatch)

    response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/teachers/questions/question-1/ai-tools/summary-draft"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["draftType"] == "teacher_summary"
    assert body["status"] == "draft"
    assert body["studentDeliveryStatus"] == "not_delivered"
    # A request names no topic: the draft says so, and quotes the student's note.
    assert body["topicIds"] == []
    assert body["misconceptionSummary"] == (
        "No specific misconception identified yet; start with a diagnostic check."
    )
    assert body["sessionSummary"] == "Student asked: Why does moving 4 change the equation?."
    assert body["sourceContext"]["evidenceQuestionIds"] == ["question-1"]
    assert drafts[body["draftId"]]["prompt_version"] == "stoa_ai_teacher_tools_v1"


def test_summary_draft_requires_visible_question(monkeypatch):
    _install_draft_repo(monkeypatch)
    _serve_requests(monkeypatch, escalation_status="withdrawn", dispatch_status="withdrawn")

    response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/teachers/questions/question-1/ai-tools/summary-draft"
    )

    assert response.status_code == 403


def test_teacher_can_create_bounded_exercise_draft_from_visible_student_context(monkeypatch):
    _install_draft_repo(monkeypatch)
    _serve_requests(monkeypatch, student_id="student-1")

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
    _serve_requests(monkeypatch)

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
    _serve_requests(monkeypatch, teacher_id="teacher-1", escalation_status="in_progress")
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


# ── what a help request's summary and drafts store (#234) ────────────────────
#
# Pinned from what the services stored when they were handed this record told
# as a question, before #234 handed them the record itself: the stored rows
# must not change by a byte.

_PINNED_RECORD = {
    "PK": "CONV#conv-1",
    "SK": "HELP",
    "entity_type": "help_request",
    "conversation_id": "conv-1",
    "escalation_request_id": "conv-1",
    "student_id": "student-1",
    "subject": "math",
    "grade": "7",
    "account_fence_generation": 3,
    "escalated": True,
    "escalated_at": "2026-11-01T10:00:00+00:00",
    "escalation_status": "in_progress",
    "escalation_message": "  I tried   twice  ",
    "teacher_id": "teacher-1",
    "dispatch_status": "accepted",
}
_PINNED_AT = "2026-11-03T00:00:00+00:00"


def _pinned_world(monkeypatch):
    from types import SimpleNamespace

    from stoa.services import teacher_assistance_service

    stored: dict[str, list] = {"seeds": [], "drafts": []}
    hexes = iter(f"{n:032x}" for n in range(1, 100))
    for module in (teacher_assistance_service, ai_teacher_tools_service):
        monkeypatch.setattr(module, "now_iso", lambda: _PINNED_AT)
        monkeypatch.setattr(module, "uuid4", lambda: SimpleNamespace(hex=next(hexes)))
    monkeypatch.setattr(teacher_assistance_service.locale_service, "reader_locale", lambda _user: "de")
    monkeypatch.setattr(
        teacher_assistance_service.learning_session,
        "history",
        lambda _conversation_id: [
            SimpleNamespace(role="student", content="What is 3/4 + 1/8?", created_at="2026-11-01T09:00:00+00:00"),
            SimpleNamespace(role="assistant", content="Find a common denominator: 8.", created_at="2026-11-01T09:00:05+00:00"),
        ],
    )
    monkeypatch.setattr(
        teacher_assistance_service.notification_repo,
        "put_summary_seed",
        lambda item: stored["seeds"].append(dict(item)),
    )
    monkeypatch.setattr(
        ai_teacher_tools_service.ai_teacher_tools_repo,
        "put_draft",
        lambda item: stored["drafts"].append(dict(item)),
    )
    return teacher_assistance_service, stored


def test_a_help_requests_summary_seed_and_drafts_are_stored_as_before(monkeypatch):
    from stoa.security.authorization import AuthorizedResource, ResourceRef, ResourceType
    from stoa.security.identity import AccountStatus, Actor, CanonicalRole

    assistance, stored = _pinned_world(monkeypatch)
    actor = Actor(
        "teacher-1", "https://identity.test", "teacher-subject", CanonicalRole.TEACHER,
        AccountStatus.ACTIVE, "teacher", (),
    )
    authorized = AuthorizedResource(
        ResourceRef(ResourceType.QUESTION, "conv-1", "student-1", question_id="conv-1"),
        dict(_PINNED_RECORD),
    )

    assistance.build_summary_seed(authorized, actor)
    ai_teacher_tools_service.create_summary_draft(authorized, actor)
    for question_id in ("conv-1", None):
        ai_teacher_tools_service.create_exercise_draft(
            student_id="student-1", subject="math", topic_ids=["fractions"],
            difficulty="easy", exercise_count=2, actor=actor,
            authorized_context=authorized, question_id=question_id,
        )

    assert stored["seeds"] == [
        {
            "entity_type": "teacher_assistance_summary_seed",
            "summary_id": "assist-00000000000000000000000000000001",
            "question_id": "conv-1",
            "student_id": "student-1",
            "subject": "math",
            "student_context_summary": (
                "Die Schülerin oder der Schüler hat eine offene Anfrage in Mathematik, "
                "noch ohne ausreichende Hinweise auf ein Thema."
            ),
            "question_summary": "What is 3/4 + 1/8? — I tried twice",
            "ai_answer_summary": "Find a common denominator: 8.",
            "weak_topics": [],
            "suggested_focus": "Stell eine diagnostische Frage und erkläre dann den kleinsten nächsten Schritt.",
            "source_count": 2,
            "created_at": _PINNED_AT,
            "created_by": "teacher-1",
            "owner_id": "student-1",
            "account_fence_generation": 3,
        }
    ]
    reviewed_blank = {
        "created_by": "teacher-1",
        "created_by_role": "teacher",
        "created_at": _PINNED_AT,
        "generated_at": _PINNED_AT,
        "updated_at": _PINNED_AT,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_note": None,
        "previous_draft_id": None,
        "student_delivery_status": "not_delivered",
        "prompt_version": "stoa_ai_teacher_tools_v1",
        "entity_type": "ai_teacher_draft",
        "status": "draft",
        "student_id": "student-1",
        "subject": "math",
    }
    summary, with_request, without_request = stored["drafts"]
    assert summary == {
        **reviewed_blank,
        "draft_id": "aitool-00000000000000000000000000000002",
        "draft_type": "teacher_summary",
        "question_id": "conv-1",
        "topic_ids": [],
        "difficulty": None,
        "exercise_count": 0,
        "session_summary": "Student asked: I tried twice.",
        "misconception_summary": "No specific misconception identified yet; start with a diagnostic check.",
        "suggested_teaching_focus": "Ask the student to explain what they tried, then model the smallest next step.",
        "draft_followup_explanation": (
            "Let's focus on the core concept. First, tell me which step feels unclear. "
            "Then we will solve one math example together before you try the next one."
        ),
        "items": [],
        "answer_key": [],
        "explanations": [],
        "source_context": {
            "studentId": "student-1",
            "evidenceQuestionIds": ["conv-1"],
            "topicLabels": [],
            "sourceCount": 1,
        },
    }
    exercise = {
        **reviewed_blank,
        "draft_type": "practice_exercise",
        "topic_ids": ["fractions"],
        "difficulty": "easy",
        "exercise_count": 2,
        "items": [
            {
                "itemId": f"item-{index}",
                "prompt": f"Math practice {index}: solve a easy problem about fractions.",
                "subject": "math",
                "topicIds": ["fractions"],
                "difficulty": "easy",
                "reviewState": "draft",
            }
            for index in (1, 2)
        ],
        "answer_key": [
            {"itemId": f"item-{index}", "answer": f"Teacher-reviewed answer placeholder {index}"}
            for index in (1, 2)
        ],
        "explanations": [
            {"itemId": f"item-{index}", "explanation": "Explain the reasoning around fractions step by step."}
            for index in (1, 2)
        ],
    }
    assert with_request == {
        **exercise,
        "draft_id": "aitool-00000000000000000000000000000003",
        "question_id": "conv-1",
        "source_context": {
            "studentId": "student-1",
            "evidenceQuestionIds": ["conv-1"],
            "topicLabels": [],
            "sourceCount": 1,
        },
    }
    assert without_request == {
        **exercise,
        "draft_id": "aitool-00000000000000000000000000000004",
        "question_id": None,
        "source_context": {
            "studentId": "student-1",
            "evidenceQuestionIds": [],
            "topicLabels": [],
            "sourceCount": 0,
        },
    }
