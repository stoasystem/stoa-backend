"""A student's question history shows questions, and only what is theirs to see.

`GET /students/{id}/questions` answered with the raw rows of `GSI-StudentId`.
That index holds every row with a `student_id` and a `created_at`, so the
student's chat conversation and message rows came back too, and each row as
stored: the dispatched teacher's id, the teachers who let an offer lapse,
dispatch ids, versions, fence generations and table keys. Found by the audit
of stoasystem/stoa-backend#76; with #75 those dispatch fields are written in
production for the first time.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import test_chat_help_request_lifecycle as lifecycle
from actor_helpers import install_actor_overrides
from stoa.routers import students


@pytest.fixture
def table(monkeypatch):
    table = lifecycle.table.__wrapped__(monkeypatch)
    lifecycle._dispatch_to(table, lifecycle.TEACHER)
    table.rows[lifecycle.QUESTION_KEY]["previous_dispatch_teacher_ids"] = ["teacher-who-timed-out"]
    table.seed(
        {
            "PK": f"CONV#{lifecycle.CONV}",
            "SK": "MSG#m-1",
            "entity_type": "conversation_message",
            "message_id": "m-1",
            "conversation_id": lifecycle.CONV,
            "student_id": lifecycle.STUDENT,
            "role": "student",
            "content": "Step 2 makes no sense to me.",
            "created_at": lifecycle.CREATED,
        },
        # A question-lane question, dispatched and with a teacher who lapsed.
        {
            "PK": "QUESTION#q-lane", "SK": "META", "entity_type": "question", "question_id": "q-lane",
            "student_id": lifecycle.STUDENT, "owner_id": lifecycle.STUDENT, "status": "escalated",
            "subject": "physics", "content": "Why does the ball fall?", "version": 4,
            "account_fence_generation": 1, "dispatch_status": "dispatched", "dispatch_id": "d-1",
            "dispatched_teacher_id": lifecycle.TEACHER, "previous_dispatch_teacher_ids": ["teacher-who-timed-out"],
            "created_at": "2026-09-27T09:00:00+00:00",
        },
        # Rows that carry the question's id without being the question.
        {
            "PK": "TEACHER_ESCALATION#op-1",
            "SK": "INTENT",
            "entity_type": "teacher_escalation_intent",
            "question_id": lifecycle.REQUEST,
            "student_id": lifecycle.STUDENT,
            "created_at": lifecycle.CREATED,
        },
    )
    return table


def _student() -> TestClient:
    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    install_actor_overrides(app, {"sub": lifecycle.STUDENT, "role": "student"})
    return TestClient(app)


def test_the_question_history_lists_question_rows_only(table):
    response = _student().get(f"/students/{lifecycle.STUDENT}/questions")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    # The chat help request's queue row is not a question (#77); it is shown
    # through its conversation.
    assert [item["question_id"] for item in items] == ["q-lane"]


def test_the_question_history_leaks_no_teacher_dispatch_or_storage_field(table):
    response = _student().get(f"/students/{lifecycle.STUDENT}/questions")

    (item,) = response.json()["items"]
    assert item == {
        "question_id": "q-lane",
        "subject": "physics",
        "content": "Why does the ball fall?",
        "status": "escalated",
        "has_image": False,
        "student_feedback": None,
        "created_at": "2026-09-27T09:00:00+00:00",
        "resolved_at": None,
    }
    served = json.dumps(response.json())
    for secret in (lifecycle.TEACHER, "teacher-who-timed-out", "dispatch", "version", "PK", "fence"):
        assert secret not in served, secret


def test_a_parent_sees_the_same_safe_history(table):
    # Parents reach this route through PARENT_OVERSIGHT; the response model is
    # the same for every role.
    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    install_actor_overrides(app, {"sub": "parent-66", "role": "parent"})

    response = TestClient(app).get(f"/students/{lifecycle.STUDENT}/questions")

    assert response.status_code == 200, response.text
    assert [item["question_id"] for item in response.json()["items"]] == ["q-lane"]
    served = json.dumps(response.json())
    for secret in (lifecycle.TEACHER, "teacher-who-timed-out", "dispatch", "PK"):
        assert secret not in served, secret


def test_the_summary_counts_a_resolved_chat_help_request_once_through_its_conversation(table):
    # A chat help request's queue row is not a question (#77), so the summary
    # counts it through its conversation (user decision, 2026-09-29): once in
    # teacher_resolved, never in total_questions.
    assert lifecycle._set_status(lifecycle._client(), "resolved").status_code == 200

    summary = _student().get(f"/students/{lifecycle.STUDENT}/summary").json()

    assert summary["total_questions"] == 1  # the question-lane question only
    assert summary["teacher_resolved"] == 1  # the resolved chat help request
