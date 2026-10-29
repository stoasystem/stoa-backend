"""A teacher's prep on an Ask help request names what the student asked about (#143).

The prep summary of the old 「交一道题」 flow named the question's topics. A help
request raised from Ask has no question row to read them from, so its detail
names the knowledge points the answers in that conversation recorded, newest
first: the topics of this request, not of every conversation the student had.

Rows, dispatch and the authorization facts are real, over the shared table
double (see test_chat_help_request_lifecycle.py). The records are written by the
repository's own builder; that an Ask writes them is
test_ask_knowledge_points_in_profile.py's.
"""

from __future__ import annotations

from typing import Any

from stoa.db.repositories import asked_knowledge_repo
from test_chat_help_request_lifecycle import (
    CONV,
    REQUEST,
    STUDENT,
    TEACHER,
    _client,
    _dispatch_to,
)
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture


def _asked(
    conversation_id: str, message_id: str, asked_at: str, *names: str
) -> dict[str, Any]:
    put = asked_knowledge_repo.record_put(
        conversation_id=conversation_id,
        message_id=message_id,
        student_id=STUDENT,
        subject="math",
        points=[(name, None) for name in names],
        asked_at=asked_at,
    )
    assert put is not None
    return put["Put"]["Item"]


def test_the_help_request_names_what_was_asked_about_in_its_conversation(table) -> None:
    table.seed(
        _asked(CONV, "msg-a1", "2026-09-28T11:50:00+00:00", "Brüche kürzen", "ggT"),
        _asked(CONV, "msg-a2", "2026-09-28T11:55:00+00:00", "Brüche erweitern", "ggT"),
        # The same student, another conversation: not this request's topic.
        _asked("conv-other", "msg-b1", "2026-09-28T11:57:00+00:00", "Kräfte"),
    )
    _dispatch_to(table, TEACHER)

    response = _client().get(f"/teachers/me/help-requests/{REQUEST}")

    assert response.status_code == 200, response.text
    assert response.json()["weakTopics"] == ["Brüche erweitern", "ggT", "Brüche kürzen"]


def test_a_help_request_with_nothing_asked_names_nothing(table) -> None:
    _dispatch_to(table, TEACHER)

    response = _client().get(f"/teachers/me/help-requests/{REQUEST}")

    assert response.status_code == 200, response.text
    assert response.json()["weakTopics"] == []
