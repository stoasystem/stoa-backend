"""Reporting what was said in a help request (#185, #186).

A help request is not a question row (#189): its AI answers and teacher
replies are messages in its conversation, so a report of one takes the words
from there and puts them where the admin queue shows that surface's text
(#185). Only the teacher who took the request, or the one it is offered to
now, may report from it; a teacher the policy admits through an assignment to
the student is refused as a teacher who cannot see it (#186).

Everything enters through `POST /questions/{id}/reports`. Rows, dispatch, the
help request record, the authorization facts and the teacher policy are real,
over the shared table double (see test_chat_help_request_lifecycle.py).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from actor_helpers import install_actor_overrides
from fakes.learning_session import seed_message
from stoa.routers import questions
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services import moderation_service
from test_chat_help_request_lifecycle import (
    CONV,
    OTHER_TEACHER,
    REQUEST,
    STUDENT,
    TEACHER,
    _client as _teacher_client,
    _dispatch_to,
    _help,
    _reply,
    _set_status,
)
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture

NOTE = "Step 2 makes no sense to me."
FIRST_ANSWER = "Multiply both sides by 3 to clear the fraction."
LATEST_ANSWER = "So x = 12, because 3 * 4 = 12."
STUDENT_WORDS = "Why is x not 4?"
TEACHER_REPLY = "Look at the denominators first."


def _message(table, message_id: str, role: str, content: str, created_at: str) -> None:
    seed_message(
        table,
        conversation_id=CONV,
        role=role,
        message_id=message_id,
        student_id=STUDENT,
        content=content,
        created_at=created_at,
    )


@pytest.fixture
def said(table):
    """The conversation before help was asked: two AI answers and a question between."""
    # The ids run against the order of sending, as random ids may.
    _message(table, "msg-z-first-answer", "assistant", FIRST_ANSWER, "2026-09-28T11:57:00+00:00")
    _message(table, "msg-m-student", "student", STUDENT_WORDS, "2026-09-28T11:58:00+00:00")
    _message(table, "msg-a-latest-answer", "assistant", LATEST_ANSWER, "2026-09-28T11:59:00+00:00")
    return table


def _client(user_id: str, role: str) -> TestClient:
    app = FastAPI()
    app.include_router(questions.router, prefix="/questions")
    install_actor_overrides(app, {"sub": user_id, "role": role})
    # The helper's fact stand-in grants a teacher whatever they ask for; who may
    # report is the point here, so the facts are loaded from the table.
    del app.dependency_overrides[get_authorization_fact_repository]
    return TestClient(app)


def _report(client: TestClient, surface: str, **extra: Any):
    return client.post(
        f"/questions/{REQUEST}/reports",
        json={"surface": surface, "reason": "incorrect_answer", "severity": "medium", **extra},
    )


def _cases(table) -> list[dict[str, Any]]:
    return [row for row in table.rows.values() if str(row.get("PK", "")).startswith("MODERATION#")]


def _queued_context(case_id: str) -> dict[str, Any]:
    """What the admin moderation queue reads for the case."""
    return moderation_service.get_case(case_id, include_events=False)["question_context"]


def _assign(table, teacher_id: str) -> None:
    """A standing assignment to the student: the policy lets this teacher read the request."""
    table.seed(
        {
            "PK": f"TEACHER_ASSIGNMENT#{teacher_id}",
            "SK": f"STUDENT#{STUDENT}",
            "teacher_id": teacher_id,
            "student_id": STUDENT,
            "status": "active",
            "scope": f"student:{STUDENT}",
        }
    )


# --- #185: the words reported come from the conversation ---


def test_a_student_reports_the_latest_ai_answer_of_their_help_request(said) -> None:
    response = _report(_client(STUDENT, "student"), "ai_answer")

    assert response.status_code == 201, response.text
    context = response.json()["question_context"]
    assert context["ai_answer_preview"] == LATEST_ANSWER
    assert context["reported_message_id"] == "msg-a-latest-answer"
    assert context["content_preview"] == NOTE
    case_id = response.json()["case_id"]
    assert _queued_context(case_id)["ai_answer_preview"] == LATEST_ANSWER


def test_a_report_names_the_ai_answer_it_is_about(said) -> None:
    response = _report(_client(STUDENT, "student"), "ai_answer", message_id="msg-z-first-answer")

    assert response.status_code == 201, response.text
    context = response.json()["question_context"]
    assert context["ai_answer_preview"] == FIRST_ANSWER
    assert context["reported_message_id"] == "msg-z-first-answer"


def test_a_student_reports_the_teacher_reply_in_their_help_request(said) -> None:
    _dispatch_to(said, TEACHER)
    assert _reply(_teacher_client(TEACHER), TEACHER_REPLY).status_code in {200, 201}

    response = _report(_client(STUDENT, "student"), "teacher_reply")

    assert response.status_code == 201, response.text
    context = response.json()["question_context"]
    assert context["teacher_response_preview"] == TEACHER_REPLY
    assert _queued_context(response.json()["case_id"])["teacher_response_preview"] == TEACHER_REPLY


def test_the_teacher_reports_the_students_message_it_names(said) -> None:
    _dispatch_to(said, TEACHER)

    response = _report(_client(TEACHER, "teacher"), "question", message_id="msg-m-student")

    assert response.status_code == 201, response.text
    assert response.json()["question_context"]["content_preview"] == STUDENT_WORDS


def test_a_named_message_must_be_what_the_surface_reports(said) -> None:
    response = _report(_client(STUDENT, "student"), "ai_answer", message_id="msg-m-student")

    assert response.status_code == 404
    assert _cases(said) == []


def test_a_help_request_without_a_teacher_reply_has_none_to_report(said) -> None:
    response = _report(_client(STUDENT, "student"), "teacher_reply")

    assert response.status_code == 400
    assert _cases(said) == []


# --- #186: only the teacher the request is with reports from it ---


def test_the_teacher_it_is_offered_to_reports_from_it(said) -> None:
    _dispatch_to(said, TEACHER)

    response = _report(_client(TEACHER, "teacher"), "ai_answer")

    assert response.status_code == 201, response.text
    assert response.json()["reporter_id"] == TEACHER


def test_the_teacher_who_took_it_reports_from_it_after_resolving(said) -> None:
    _dispatch_to(said, TEACHER)
    teacher = _teacher_client(TEACHER)
    assert _set_status(teacher, "in_progress").status_code == 200
    assert _set_status(teacher, "resolved", resolutionNote="Done.").status_code == 200

    response = _report(_client(TEACHER, "teacher"), "ai_answer")

    assert response.status_code == 201, response.text


@pytest.mark.parametrize("held_by", [TEACHER, None], ids=["taken", "offered"])
def test_an_assigned_teacher_who_does_not_hold_it_is_refused_without_its_content(
    said, held_by: str | None
) -> None:
    _dispatch_to(said, TEACHER)
    if held_by:
        assert _set_status(_teacher_client(TEACHER), "in_progress").status_code == 200
    _assign(said, OTHER_TEACHER)

    response = _report(_client(OTHER_TEACHER, "teacher"), "ai_answer")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "resource_not_found"
    for words in (NOTE, FIRST_ANSWER, LATEST_ANSWER, STUDENT_WORDS):
        assert words not in response.text
    assert _cases(said) == []


def test_a_teacher_whose_offer_lapsed_is_refused(said) -> None:
    _dispatch_to(said, TEACHER)
    _help(said)["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"
    _assign(said, TEACHER)

    response = _report(_client(TEACHER, "teacher"), "ai_answer")

    assert response.status_code == 404
    assert LATEST_ANSWER not in response.text
    assert _cases(said) == []


def test_an_unrelated_teacher_is_refused_like_any_unseen_request(said) -> None:
    _dispatch_to(said, TEACHER)

    response = _report(_client(OTHER_TEACHER, "teacher"), "ai_answer")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "resource_not_found"
    assert _cases(said) == []
