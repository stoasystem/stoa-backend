"""The student hears when a teacher takes or answers their chat help request (#65).

A teacher's reply is written into the student's conversation; until now the
student was never told. Each reply, and each take-over, now leaves one bell
notification for the conversation's own student, pointing at the conversation.
A reply that takes the request in the same write is one event, not two.
"""

from __future__ import annotations

from typing import Any

import pytest

from stoa.services import notification_service
from test_chat_help_request_lifecycle import (
    CONV,
    STUDENT,
    TEACHER,
    _client,
    _dispatch_to,
    _reply,
    _set_status,
)
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        notification_service, "create_event_safe", lambda **kwargs: events.append(kwargs) or kwargs
    )
    return events


def _for_the_student(event: dict[str, Any]) -> None:
    assert event["recipient_id"] == STUDENT
    assert event["recipient_role"] == "student"
    assert event["owner_id"] == STUDENT
    assert event["target_type"] == "conversation"
    assert event["target_id"] == CONV


def test_a_teacher_taking_the_request_tells_the_student_once(table, sent) -> None:
    _dispatch_to(table, TEACHER)

    response = _set_status(_client(), "in_progress")

    assert response.status_code == 200, response.text
    assert [event["event_type"] for event in sent] == ["teacher_takeover"]
    _for_the_student(sent[0])


def test_each_reply_tells_the_student_once(table, sent) -> None:
    _dispatch_to(table, TEACHER)
    assert _set_status(_client(), "in_progress").status_code == 200
    sent.clear()

    first = _reply(_client(), "Look at the denominators first.")
    second = _reply(_client(), "Now add the numerators.")

    assert first.status_code in {200, 201} and second.status_code in {200, 201}
    assert [event["event_type"] for event in sent] == ["teacher_reply", "teacher_reply"]
    for event in sent:
        _for_the_student(event)
    assert sent[0]["event_id"] != sent[1]["event_id"]


def test_a_reply_that_takes_the_offer_is_one_notification(table, sent) -> None:
    _dispatch_to(table, TEACHER)

    response = _reply(_client())

    assert response.status_code in {200, 201}, response.text
    assert [event["event_type"] for event in sent] == ["teacher_reply"]
    _for_the_student(sent[0])


def test_a_refused_reply_tells_nobody(table, sent) -> None:
    # No offer to this teacher: the write is refused (the request is hidden
    # from them) and nothing is announced.
    response = _reply(_client())

    assert 400 <= response.status_code < 500, response.text
    assert sent == []


def test_the_notifications_reach_the_store_once_each(table, monkeypatch) -> None:
    # Through the real store: a target the store refused would be swallowed by
    # create_event_safe and the student would hear nothing, unseen.
    monkeypatch.setenv("STOA_ENABLE_BEST_EFFORT_NOTIFICATIONS", "true")
    _dispatch_to(table, TEACHER)
    assert _set_status(_client(), "in_progress").status_code == 200
    assert _reply(_client()).status_code in {200, 201}
    stored = [
        row for row in table.rows.values() if row.get("event_type") in {"teacher_takeover", "teacher_reply"}
    ]
    assert sorted(row["event_type"] for row in stored) == ["teacher_reply", "teacher_takeover"]
    for row in stored:
        assert row["recipient_id"] == STUDENT
        assert row["target_type"] == "conversation"
        assert row["target_id"] == CONV

    takeover = next(row for row in stored if row["event_type"] == "teacher_takeover")
    conversation = {
        "student_id": STUDENT,
        "conversation_id": CONV,
        "escalation_request_id": takeover["metadata"]["request_id"],
        "account_fence_generation": takeover.get("account_fence_generation"),
    }
    notification_service.emit_teacher_help_takeover(conversation=conversation, teacher_id=TEACHER)
    again = [row for row in table.rows.values() if row.get("event_type") == "teacher_takeover"]
    assert len(again) == 1
