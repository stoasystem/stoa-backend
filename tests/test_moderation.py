import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.db.repositories import question_repo, user_repo
from stoa.deps import get_actor
from stoa.routers import admin, questions
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import learning_session, moderation_service
from actor_helpers import install_actor_overrides


def _request(**overrides):
    """A help request record: what `/questions/{id}/reports` resolves (#189, #234)."""
    item = {
        "conversation_id": "question-1",
        "escalation_request_id": "question-1",
        "student_id": "student-1",
        "account_fence_generation": 1,
        "subject": "math",
        "escalation_status": "pending",
        "escalation_message": "Solve 2x = 10",
    }
    item.update(overrides)
    return item


def _serve_request(monkeypatch, **overrides):
    from stoa.services import help_requests

    monkeypatch.setattr(help_requests, "get", lambda *_a, **_k: _request(**overrides))


def _report(user, request, **body):
    """A report made through the service alone, of the help request handed to it."""
    from stoa.models.moderation import ModerationReportRequest

    return moderation_service.create_case(
        "question-1", ModerationReportRequest.model_validate(body), user, request=request
    )


def _case(**overrides):
    item = {
        "case_id": "mod-1",
        "status": "open",
        "reason": "unsafe_content",
        "severity": "high",
        "surface": "ai_answer",
        "question_id": "question-1",
        "student_id": "student-1",
        "privacy_generation": 1,
        "reporter_id": "student-1",
        "reporter_role": "student",
        "assigned_admin_id": None,
        "report_note": "This answer looks unsafe",
        "resolution_note": None,
        "created_at": "2026-06-08T10:00:00+00:00",
        "updated_at": "2026-06-08T10:00:00+00:00",
        "closed_at": None,
        "question_context": {
            "question_id": "question-1",
            "student_id": "student-1",
            "subject": "math",
            "status": "ai_answered",
            "content_preview": "Solve 2x = 10",
            "ai_answer_preview": "x = 5",
            "teacher_response_preview": "Divide by 2.",
            "has_image": True,
        },
        "history": [],
    }
    item.update(overrides)
    return item


def _questions_app(user):
    app = FastAPI()
    app.include_router(questions.router, prefix="/questions")
    role = CanonicalRole(user["role"])
    app.dependency_overrides[get_actor] = lambda: Actor(
        user["sub"],
        "https://identity.test",
        f"{user['sub']}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
    )
    return TestClient(app)


def _admin_app(user):
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, user)
    return TestClient(app)


def _stub_teacher_authorization_facts(monkeypatch):
    monkeypatch.setattr(question_repo, "get_teacher_assignment", lambda *_: None)
    monkeypatch.setattr(
        user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "role": "teacher" if user_id.startswith("teacher") else "student",
            "account_status": "active",
        },
    )


def test_student_can_report_own_question_without_private_image_key(monkeypatch):
    stored = {}
    events = []
    monkeypatch.setattr(
        moderation_service.learning_session,
        "history",
        lambda conversation_id: [
            learning_session.Message(
                id="msg-answer",
                conversation_id=conversation_id,
                student_id="student-1",
                role="assistant",
                content="x = 5",
                created_at="2026-06-08T09:59:00+00:00",
            )
        ],
    )
    monkeypatch.setattr(
        moderation_service.moderation_repo,
        "put_case",
        lambda item, event: (stored.update(item), events.append(event)),
    )
    monkeypatch.setattr(moderation_service.moderation_repo, "put_event", lambda case_id, event: events.append(event))

    body = _report(
        {"sub": "student-1", "role": "student"},
        # An image key on the record would not be copied either.
        _request(image_s3_key="private/student-1/question.png"),
        surface="ai_answer",
        reason="unsafe_content",
        severity="high",
        note="This answer looks unsafe",
    )

    assert body["status"] == "open"
    assert body["reason"] == "unsafe_content"
    assert body["question_context"]["ai_answer_preview"] == "x = 5"
    assert body["question_context"]["content_preview"] == "Solve 2x = 10"
    # The case keeps the request's own state word, not a question's.
    assert body["question_context"]["status"] == "pending"
    assert "image_s3_key" not in str(body)
    assert "private/student-1/question.png" not in str(body)
    assert stored["reporter_id"] == "student-1"
    assert stored["history"][0]["event_type"] == "reported"
    assert events[0]["case_id"] == stored["case_id"]


def test_student_cannot_report_another_students_question(monkeypatch):
    _serve_request(monkeypatch)

    response = _questions_app({"sub": "student-2", "role": "student"}).post(
        "/questions/question-1/reports",
        json={"surface": "question", "reason": "abuse", "severity": "medium"},
    )

    assert response.status_code == 404


def test_teacher_reporting_requires_visible_question(monkeypatch):
    _stub_teacher_authorization_facts(monkeypatch)
    _serve_request(monkeypatch)

    response = _questions_app({"sub": "teacher-1", "role": "teacher"}).post(
        "/questions/question-1/reports",
        json={"surface": "question", "reason": "other", "severity": "low"},
    )

    assert response.status_code == 404


def test_report_teacher_reply_requires_existing_reply(monkeypatch):
    _stub_teacher_authorization_facts(monkeypatch)
    _serve_request(monkeypatch, escalation_status="pending")

    response = _questions_app({"sub": "teacher-1", "role": "teacher"}).post(
        "/questions/question-1/reports",
        json={"surface": "teacher_reply", "reason": "incorrect_answer", "severity": "medium"},
    )

    assert response.status_code == 404


def test_admin_moderation_list_is_admin_only(monkeypatch):
    monkeypatch.setattr(moderation_service.moderation_repo, "list_cases", lambda limit: [_case()])

    response = _admin_app({"sub": "student-1", "role": "student"}).get("/admin/moderation/cases")

    assert response.status_code == 403


def test_admin_lists_filtered_moderation_cases(monkeypatch):
    monkeypatch.setattr(
        moderation_service.moderation_repo,
        "list_cases",
        lambda limit: [
            _case(case_id="mod-1", status="open", severity="high"),
            _case(case_id="mod-2", status="closed", severity="low"),
        ],
    )

    response = _admin_app({"sub": "admin-1", "role": "admin"}).get(
        "/admin/moderation/cases?status=open&severity=high"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["case_id"] == "mod-1"
    assert body["access_pattern"] == "bounded_scan"


def test_admin_can_open_update_and_note_moderation_case(monkeypatch):
    updates = []
    events = []
    case = _case(history=[{"event_id": "event-1", "event_type": "reported"}])
    monkeypatch.setattr(moderation_service.moderation_repo, "get_case", lambda case_id: case)
    monkeypatch.setattr(
        moderation_service.moderation_repo,
        "list_case_events",
        lambda case_id: events or case["history"],
    )
    monkeypatch.setattr(
        moderation_service.moderation_repo,
        "update_case",
        lambda case_id, attrs: updates.append(attrs) or {**case, **attrs},
    )
    monkeypatch.setattr(moderation_service.moderation_repo, "put_event", lambda case_id, event: events.append(event))

    client = _admin_app({"sub": "admin-1", "role": "admin"})
    detail = client.get("/admin/moderation/cases/mod-1")
    patched = client.patch(
        "/admin/moderation/cases/mod-1",
        json={"status": "actioned", "assigned_admin_id": "admin-1", "resolution_note": "Removed bad answer"},
    )
    noted = client.post("/admin/moderation/cases/mod-1/notes", json={"note": "Parent notified"})

    assert detail.status_code == 200
    assert patched.status_code == 200
    assert patched.json()["status"] == "actioned"
    assert patched.json()["closed_at"] is not None
    assert noted.status_code == 200
    assert updates[0]["status"] == "actioned"
    assert updates[0]["assigned_admin_id"] == "admin-1"
    assert updates[0]["resolution_note"] == "Removed bad answer"
    assert events[0]["event_type"] == "updated"
    assert events[1]["event_type"] == "note_added"


def test_nobody_can_report_an_image_case_themselves(monkeypatch):
    """`image_upload` cases are opened by image moderation only (#139)."""
    _serve_request(monkeypatch)
    monkeypatch.setattr(
        moderation_service.moderation_repo,
        "put_case",
        lambda *_args, **_kwargs: pytest.fail("no case may be written"),
    )

    response = _questions_app({"sub": "student-1", "role": "student"}).post(
        "/questions/question-1/reports",
        json={"surface": "image_upload", "reason": "unsafe_content", "severity": "high"},
    )

    assert response.status_code == 400
