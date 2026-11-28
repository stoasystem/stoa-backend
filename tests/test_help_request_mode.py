"""#480: a help request records how the student wants the help.

The student chooses `text` (a written answer) or `classroom` when asking; the
teacher cannot change it. The student's read, the teacher's list and detail
and the take-over notification all carry it. A request asked before #480 has
no `mode` stored and counts as `text`.

Over the lifecycle tests' production-shaped rows and real routes; their shared
request is one asked before #480, so it carries no mode.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from fakes.admission import seed_period_active
from stoa.services import help_requests, message_catalog
from stoa.services.notifications import _bell, _tell
from stoa.services import teacher_support_allowance_service as allowance
from test_chat_help_request_lifecycle import (
    CONV,
    HELP_KEY,
    REQUEST,
    STUDENT,
    TEACHER,
    _client,
    _dispatch_to,
    _help,
    _set_status,
)
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture


def _student() -> TestClient:
    from stoa.routers import conversations
    from stoa.security.declared_authorization import get_authorization_fact_repository

    app = FastAPI()
    app.include_router(conversations.teacher_help_router, prefix="/teacher-help")
    install_actor_overrides(app, {"sub": STUDENT, "role": "student"})
    app.dependency_overrides.pop(get_authorization_fact_repository, None)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def asking(table, monkeypatch):
    """The conversation has not asked yet; the week's case is admitted."""
    from stoa.routers import conversations

    del table.rows[HELP_KEY]
    seed_period_active(monkeypatch)

    def admit(*, persist_case, **_kwargs):
        assert persist_case((), {})
        return allowance.TeacherSupportAdmissionResult(
            allowance.TeacherSupportAdmissionDisposition.ADMITTED
        )

    monkeypatch.setattr(allowance, "admit_teacher_support_case", admit)
    monkeypatch.setattr(
        conversations.usage_ledger_service,
        "record_usage_event",
        lambda **_kwargs: {"idempotency_status": "created"},
    )
    return table


def _ask(body: dict[str, Any]):
    return _student().post("/teacher-help/request", json={"conversationId": CONV, **body})


def _status() -> dict[str, Any]:
    response = _student().get(f"/teacher-help/conversations/{CONV}/request")
    assert response.status_code == 200, response.text
    return response.json()


# --- The student chooses ---


@pytest.mark.parametrize("mode", ["text", "classroom"])
def test_the_student_asks_in_either_mode_and_it_is_stored(asking, mode) -> None:
    response = _ask({"message": "Step 2?", "mode": mode})

    assert response.status_code == 200, response.text
    assert response.json()["mode"] == mode
    assert _help(asking)["mode"] == mode
    assert _status()["mode"] == mode


def test_asking_without_a_mode_asks_for_a_written_answer(asking) -> None:
    # The web client before stoa-frontend#705 sends no mode.
    response = _ask({"message": "Step 2?"})

    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "text"
    assert _help(asking)["mode"] == "text"


def test_an_unknown_mode_is_refused_and_nothing_is_asked(asking) -> None:
    response = _ask({"mode": "video"})

    assert response.status_code == 422, response.text
    assert HELP_KEY not in asking.rows


def test_asking_again_in_another_mode_does_not_change_it(asking) -> None:
    assert _ask({"mode": "classroom"}).status_code == 200

    again = _ask({"mode": "text"})

    assert again.status_code == 200, again.text
    assert again.json()["mode"] == "classroom"
    assert _help(asking)["mode"] == "classroom"


# --- A request asked before #480 ---


def test_a_request_without_a_mode_counts_as_text_everywhere(table) -> None:
    assert "mode" not in _help(table)
    _dispatch_to(table, TEACHER)
    teacher = _client()

    assert _status()["mode"] == "text"
    [listed] = teacher.get("/teachers/me/help-requests").json()["items"]
    assert listed["mode"] == "text"
    assert teacher.get(f"/teachers/me/help-requests/{REQUEST}").json()["mode"] == "text"
    assert help_requests.mode(_help(table)) == "text"


def test_a_stored_mode_outside_the_two_counts_as_text(table) -> None:
    _help(table)["mode"] = "something-else"

    assert help_requests.mode(_help(table)) == "text"
    assert _status()["mode"] == "text"


# --- The teacher reads it and cannot change it ---


def test_the_teacher_reads_a_classroom_request_as_classroom(table) -> None:
    _help(table)["mode"] = "classroom"
    _dispatch_to(table, TEACHER)
    teacher = _client()

    [listed] = teacher.get("/teachers/me/help-requests").json()["items"]
    detail = teacher.get(f"/teachers/me/help-requests/{REQUEST}")

    assert listed["mode"] == "classroom"
    assert detail.status_code == 200, detail.text
    assert detail.json()["mode"] == "classroom"


def test_taking_the_request_does_not_change_its_mode(table) -> None:
    _help(table)["mode"] = "classroom"
    _dispatch_to(table, TEACHER)

    response = _set_status(_client(), "in_progress", mode="text")

    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "classroom"
    assert _help(table)["mode"] == "classroom"


# --- The student is told how the teacher will help ---


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        _bell,
        "create_event_safe",
        lambda **kwargs: (
            events.append(kwargs) if kwargs.get("recipient_role") == "student" else None
        )
        or kwargs,
    )
    return events


@pytest.mark.parametrize("locale", ["de", "en", "fr", "it"])
def test_taking_a_classroom_request_tells_the_student_to_enter_the_classroom(
    table, sent, monkeypatch, locale
) -> None:
    monkeypatch.setattr(_tell, "recipient_locale", lambda _id: locale)
    _help(table)["mode"] = "classroom"
    _dispatch_to(table, TEACHER)

    assert _set_status(_client(), "in_progress").status_code == 200

    [event] = sent
    assert event["event_type"] == "teacher_takeover"
    assert event["metadata"]["mode"] == "classroom"
    classroom = message_catalog.text("teacher_help.takeover.summary_classroom", locale)
    assert event["summary"] == classroom
    assert classroom != message_catalog.text("teacher_help.takeover.summary", locale)


@pytest.mark.parametrize("stored", [None, "text"], ids=["asked_before_480", "text"])
def test_taking_a_text_request_says_a_teacher_is_working_on_it(table, sent, stored) -> None:
    if stored:
        _help(table)["mode"] = stored
    _dispatch_to(table, TEACHER)

    assert _set_status(_client(), "in_progress").status_code == 200

    [event] = sent
    assert event["metadata"]["mode"] == "text"
    assert event["summary"] in {
        message_catalog.text("teacher_help.takeover.summary", locale)
        for locale in ("de", "en", "fr", "it")
    }


def test_the_classroom_line_exists_in_every_language() -> None:
    lines = message_catalog.TEXT["teacher_help.takeover.summary_classroom"]

    assert set(lines) == {"de", "en", "fr", "it"}
    assert all(line.strip() for line in lines.values())
