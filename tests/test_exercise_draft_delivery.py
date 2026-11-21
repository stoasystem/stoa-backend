"""#519: an accepted exercise draft reaches the student as an assignment.

A teacher sets an accepted draft for the student through the one route #495
opened to a teacher who took the student's help request: `POST
/adaptive/assignments` with `sourceType: ai_draft`. The draft then says it was
delivered, and the student sees the assignment in their list. A draft is one
assignment however often it is sent.

Since #518 no route makes or reviews a draft any more; drafts already stored
are still delivered this way, so each test stores its draft through the
repository as the retired routes stored it.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import actor_from_user
from audit_helpers import MemoryAuthorizationAuditSink
from stoa.db.repositories import ai_teacher_tools_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.services import adaptive_learning_service, ai_teacher_tools_service, help_requests
from test_adaptive_learning import _install_memory_repo

TEACHER = "teacher-1"
STUDENT = "student-1"
DRAFT_ID = "aitool-519"


def _install_draft_repo(monkeypatch) -> dict[str, dict[str, Any]]:
    """The draft rows in a dict, behind the repository's own functions."""
    drafts: dict[str, dict[str, Any]] = {}

    def put_draft(item):
        drafts[item["draft_id"]] = dict(item)

    def get_draft(draft_id):
        item = drafts.get(draft_id)
        return dict(item) if item else None

    def update_draft(draft_id, updates, *, existing=None):
        drafts[draft_id].update(updates)
        return dict(drafts[draft_id])

    monkeypatch.setattr(ai_teacher_tools_repo, "put_draft", put_draft)
    monkeypatch.setattr(ai_teacher_tools_repo, "get_draft", get_draft)
    monkeypatch.setattr(ai_teacher_tools_repo, "update_draft", update_draft)
    return drafts


def _store_draft(status: str = "accepted") -> dict[str, Any]:
    """An exercise draft of two bank exercises, stored as the retired route stored it."""
    item = {
        "entity_type": ai_teacher_tools_repo.DRAFT_ENTITY,
        "draft_id": DRAFT_ID,
        "draft_type": "practice_exercise",
        "status": status,
        "student_id": STUDENT,
        "question_id": "question-1",
        "subject": "math",
        "requested_topic_ids": ["gleichungen"],
        "star_ids": [],
        "difficulty": "standard",
        "requested_count": 2,
        "topic_ids": ["gleichungen"],
        "lesson_id": "lesson-gl-1",
        "title": "Gleichungen",
        "exercise_count": 2,
        "items": [
            {"itemId": exercise_id, "id": exercise_id, "lessonId": "lesson-gl-1",
             "type": "short_answer", "prompt": f"Löse {exercise_id}: 3x + 4 = 10",
             "reviewState": "draft"}
            for exercise_id in ("ex-1", "ex-2")
        ],
        "answer_key": [{"itemId": exercise_id, "answer": "x = 2"} for exercise_id in ("ex-1", "ex-2")],
        "explanations": [],
        "created_by": TEACHER,
        "created_by_role": "teacher",
        "created_at": "2026-11-20T10:00:00+00:00",
        "student_delivery_status": "not_delivered",
    }
    ai_teacher_tools_repo.put_draft(item)
    return item


def _adaptive(user: dict[str, Any]) -> TestClient:
    """The adaptive routes, decided by the real fact loader (#495)."""
    from stoa.routers import adaptive

    app = FastAPI()
    app.include_router(adaptive.router, prefix="/adaptive")
    app.dependency_overrides[get_actor] = lambda: actor_from_user(user)
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


@pytest.fixture
def world(monkeypatch):
    from stoa.db.repositories import question_repo, user_repo

    _snapshots, assignments = _install_memory_repo(monkeypatch)
    drafts = _install_draft_repo(monkeypatch)
    # The teacher holds the student's help request: the #495 relationship.
    monkeypatch.setattr(
        help_requests,
        "for_student",
        lambda student_id, *, table=None: {
            "0": {
                "entity_type": "help_request",
                "conversation_id": "question-1",
                "escalation_request_id": "question-1",
                "student_id": STUDENT,
                "teacher_id": TEACHER,
                "escalation_status": "in_progress",
                "dispatch_status": "accepted",
            }
        }
        if student_id == STUDENT
        else {},
    )
    monkeypatch.setattr(question_repo, "get_teacher_assignment", lambda *_args: None)
    monkeypatch.setattr(
        user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "role": "teacher" if user_id.startswith("teacher") else "student",
            "account_status": "active",
            "preferred_locale": "de",
        },
    )
    monkeypatch.setattr(
        adaptive_learning_service.usage_ledger_service, "record_usage_event", lambda **_kwargs: None
    )
    return drafts, assignments


def _send(draft_id: str, teacher: str = TEACHER):
    return _adaptive({"sub": teacher, "role": "teacher"}).post(
        "/adaptive/assignments",
        json={"studentId": STUDENT, "sourceType": "ai_draft", "sourceId": draft_id, "status": "assigned"},
    )


def test_an_accepted_draft_sent_by_the_helping_teacher_reaches_the_student(world) -> None:
    drafts, _assignments = world
    draft = _store_draft()

    sent = _send(draft["draft_id"])

    assert sent.status_code == 200, sent.text
    assignment = sent.json()
    assert assignment["sourceType"] == "ai_draft"
    assert assignment["sourceId"] == draft["draft_id"]
    assert assignment["status"] == "assigned"
    assert assignment["title"] == "Gleichungen"
    assert assignment["lessonId"] == "lesson-gl-1"
    assert assignment["topicIds"] == ["gleichungen"]

    stored = drafts[draft["draft_id"]]
    assert stored["student_delivery_status"] == "delivered"
    assert stored["delivered_assignment_id"] == assignment["assignmentId"]

    mine = _adaptive({"sub": STUDENT, "role": "student"}).get("/adaptive/students/me/assignments")
    assert mine.status_code == 200, mine.text
    [seen] = mine.json()["items"]
    assert seen["assignmentId"] == assignment["assignmentId"]
    assert [item["itemId"] for item in seen["items"]] == ["ex-1", "ex-2"]
    assert "answerKey" not in seen


def test_a_draft_sent_again_is_the_assignment_already_made(world) -> None:
    _drafts, assignments = world
    draft = _store_draft()

    first = _send(draft["draft_id"])
    again = _send(draft["draft_id"])

    assert again.status_code == 200, again.text
    assert again.json()["assignmentId"] == first.json()["assignmentId"]
    assert len(assignments) == 1


def test_a_draft_not_accepted_is_not_sent(world) -> None:
    drafts, assignments = world
    draft = _store_draft(status="draft")

    sent = _send(draft["draft_id"])

    assert sent.status_code == 409, sent.text
    assert sent.json()["detail"]["code"] == "ai_draft_not_assignable"
    assert assignments == {}
    assert drafts[draft["draft_id"]]["student_delivery_status"] == "not_delivered"


def test_a_teacher_who_did_not_help_the_student_cannot_send_it(world) -> None:
    drafts, assignments = world
    draft = _store_draft()

    sent = _send(draft["draft_id"], teacher="teacher-unrelated")

    assert sent.status_code == 404, sent.text
    assert assignments == {}
    assert drafts[draft["draft_id"]]["student_delivery_status"] == "not_delivered"


def test_an_assignment_kept_as_draft_is_not_a_delivery(world) -> None:
    drafts, _assignments = world
    draft = _store_draft()

    sent = _adaptive({"sub": TEACHER, "role": "teacher"}).post(
        "/adaptive/assignments",
        json={"studentId": STUDENT, "sourceType": "ai_draft", "sourceId": draft["draft_id"], "status": "draft"},
    )

    assert sent.status_code == 200, sent.text
    assert drafts[draft["draft_id"]]["student_delivery_status"] == "not_delivered"


def test_an_automation_batch_that_sets_the_draft_marks_it_delivered(world) -> None:
    drafts, _assignments = world
    draft = _store_draft()
    item = adaptive_learning_service._create_assignment_item(  # noqa: SLF001
        student_id=STUDENT,
        source_type="ai_draft",
        source_id=draft["draft_id"],
        user={"sub": TEACHER, "role": "teacher"},
        status="recommended",
    )
    stored, created = adaptive_learning_service._put_assignment_if_absent(item)  # noqa: SLF001
    assert created

    ai_teacher_tools_service.mark_delivered(stored)

    assert drafts[draft["draft_id"]]["student_delivery_status"] == "delivered"
    assert drafts[draft["draft_id"]]["delivered_assignment_id"] == stored["assignment_id"]


def test_marking_a_delivered_draft_again_changes_nothing(world) -> None:
    drafts, _assignments = world
    draft = _store_draft()
    first = _send(draft["draft_id"]).json()
    delivered = dict(drafts[draft["draft_id"]])

    ai_teacher_tools_service.mark_delivered(
        {"source_type": "ai_draft", "source_id": draft["draft_id"], "status": "assigned",
         "assignment_id": "another-assignment"}
    )

    assert drafts[draft["draft_id"]] == delivered
    assert delivered["delivered_assignment_id"] == first["assignmentId"]
