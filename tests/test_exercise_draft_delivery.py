"""#519: an accepted exercise draft reaches the student as an assignment.

The teacher reviews a draft of the bank's exercises, accepts it, and sets it
for the student through the one route #495 opened to a teacher who took the
student's help request: `POST /adaptive/assignments` with `sourceType:
ai_draft`. The draft then says it was delivered, and the student sees the
assignment in their list. A draft is one assignment however often it is sent.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import actor_from_user
from audit_helpers import MemoryAuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.services import adaptive_learning_service, ai_teacher_tools_service, help_requests
from test_adaptive_learning import _install_memory_repo
from test_ai_teacher_tools import (
    _EXERCISE_DRAFT,
    _app as _teacher_tools,
    _exercise,
    _install_bank,
    _install_draft_repo,
    _serve_requests,
)

TEACHER = "teacher-1"
STUDENT = "student-1"


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
    _serve_requests(monkeypatch)
    _install_bank(
        monkeypatch,
        [_exercise("ex-1"), _exercise("ex-2")],
        lessons=[{"lesson_id": "lesson-gl-1", "topic_id": "gleichungen", "unit_id": "gl-u1", "title": "Gleichungen"}],
    )
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


def _accepted_draft() -> dict[str, Any]:
    tools = _teacher_tools({"sub": TEACHER, "role": "teacher"})
    created = tools.post(
        "/teachers/ai-tools/exercise-drafts", json={**_EXERCISE_DRAFT, "topicIds": ["gleichungen"]}
    ).json()
    accepted = tools.post(f"/teachers/ai-tools/drafts/{created['draftId']}/accept").json()
    assert accepted["status"] == "accepted"
    # Accepting is the review; it sends nothing.
    assert accepted["studentDeliveryStatus"] == "not_delivered"
    return accepted


def _send(draft_id: str, teacher: str = TEACHER):
    return _adaptive({"sub": teacher, "role": "teacher"}).post(
        "/adaptive/assignments",
        json={"studentId": STUDENT, "sourceType": "ai_draft", "sourceId": draft_id, "status": "assigned"},
    )


def test_an_accepted_draft_sent_by_the_helping_teacher_reaches_the_student(world) -> None:
    drafts, _assignments = world
    draft = _accepted_draft()

    sent = _send(draft["draftId"])

    assert sent.status_code == 200, sent.text
    assignment = sent.json()
    assert assignment["sourceType"] == "ai_draft"
    assert assignment["sourceId"] == draft["draftId"]
    assert assignment["status"] == "assigned"
    assert assignment["title"] == "Gleichungen"
    assert assignment["lessonId"] == "lesson-gl-1"
    assert assignment["topicIds"] == ["gleichungen"]

    stored = drafts[draft["draftId"]]
    assert stored["student_delivery_status"] == "delivered"
    assert stored["delivered_assignment_id"] == assignment["assignmentId"]
    shown = _teacher_tools({"sub": TEACHER, "role": "teacher"}).get(
        f"/teachers/ai-tools/drafts/{draft['draftId']}"
    ).json()
    assert shown["studentDeliveryStatus"] == "delivered"
    assert shown["deliveredAssignmentId"] == assignment["assignmentId"]

    mine = _adaptive({"sub": STUDENT, "role": "student"}).get("/adaptive/students/me/assignments")
    assert mine.status_code == 200, mine.text
    [seen] = mine.json()["items"]
    assert seen["assignmentId"] == assignment["assignmentId"]
    assert [item["itemId"] for item in seen["items"]] == ["ex-1", "ex-2"]
    assert "answerKey" not in seen


def test_a_draft_sent_again_is_the_assignment_already_made(world) -> None:
    _drafts, assignments = world
    draft = _accepted_draft()

    first = _send(draft["draftId"])
    again = _send(draft["draftId"])

    assert again.status_code == 200, again.text
    assert again.json()["assignmentId"] == first.json()["assignmentId"]
    assert len(assignments) == 1


def test_archiving_a_delivered_draft_does_not_take_back_the_delivery(world) -> None:
    drafts, _assignments = world
    draft = _accepted_draft()
    _send(draft["draftId"])

    archived = _teacher_tools({"sub": TEACHER, "role": "teacher"}).post(
        f"/teachers/ai-tools/drafts/{draft['draftId']}/archive"
    )

    assert archived.status_code == 200
    assert archived.json()["studentDeliveryStatus"] == "delivered"
    assert drafts[draft["draftId"]]["student_delivery_status"] == "delivered"


def test_a_draft_not_accepted_is_not_sent(world) -> None:
    drafts, assignments = world
    tools = _teacher_tools({"sub": TEACHER, "role": "teacher"})
    created = tools.post(
        "/teachers/ai-tools/exercise-drafts", json={**_EXERCISE_DRAFT, "topicIds": ["gleichungen"]}
    ).json()

    sent = _send(created["draftId"])

    assert sent.status_code == 409, sent.text
    assert sent.json()["detail"]["code"] == "ai_draft_not_assignable"
    assert assignments == {}
    assert drafts[created["draftId"]]["student_delivery_status"] == "not_delivered"


def test_a_teacher_who_did_not_help_the_student_cannot_send_it(world) -> None:
    drafts, assignments = world
    draft = _accepted_draft()

    sent = _send(draft["draftId"], teacher="teacher-unrelated")

    assert sent.status_code == 404, sent.text
    assert assignments == {}
    assert drafts[draft["draftId"]]["student_delivery_status"] == "not_delivered"


def test_an_assignment_kept_as_draft_is_not_a_delivery(world) -> None:
    drafts, _assignments = world
    draft = _accepted_draft()

    sent = _adaptive({"sub": TEACHER, "role": "teacher"}).post(
        "/adaptive/assignments",
        json={"studentId": STUDENT, "sourceType": "ai_draft", "sourceId": draft["draftId"], "status": "draft"},
    )

    assert sent.status_code == 200, sent.text
    assert drafts[draft["draftId"]]["student_delivery_status"] == "not_delivered"


def test_an_automation_batch_that_sets_the_draft_marks_it_delivered(world) -> None:
    drafts, _assignments = world
    draft = _accepted_draft()
    item = adaptive_learning_service._create_assignment_item(  # noqa: SLF001
        student_id=STUDENT,
        source_type="ai_draft",
        source_id=draft["draftId"],
        user={"sub": TEACHER, "role": "teacher"},
        status="recommended",
    )
    stored, created = adaptive_learning_service._put_assignment_if_absent(item)  # noqa: SLF001
    assert created

    ai_teacher_tools_service.mark_delivered(stored)

    assert drafts[draft["draftId"]]["student_delivery_status"] == "delivered"
    assert drafts[draft["draftId"]]["delivered_assignment_id"] == stored["assignment_id"]
