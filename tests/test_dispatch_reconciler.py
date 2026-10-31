"""Nobody should be left waiting on a teacher who is not coming.

Dispatch happens inside the request that asks for a teacher. These cover what
happens afterwards, when that request left the student waiting on nobody.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from stoa.services import teacher_dispatch_service as dispatch

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)


def stamp(offset_minutes: int = 0) -> str:
    return (NOW + timedelta(minutes=offset_minutes)).isoformat()


def question(**overrides: Any) -> dict[str, Any]:
    base = {
        "question_id": "q-1",
        "student_id": "student-1",
        "status": "escalated",
        "subject": "mathematics",
        "SK": "META",
        "version": 1,
    }
    base.update(overrides)
    return base


def test_the_scheduled_job_reports_what_it_did(monkeypatch):
    from stoa.jobs import dispatch_reconciler

    monkeypatch.setattr(
        dispatch_reconciler.teacher_dispatch_service, "reconcile_dispatches",
        lambda: {"reassigned": 2, "reassignments": [], "conversationSweep": "completed",
                 "conversationsWaiting": 1,
                 "conversationsDispatched": [{"conversationId": "c-1"}],
                 "generatedAt": stamp()},
    )

    result = dispatch_reconciler.handler({"job": "dispatch_reconcile"}, None)

    assert result == {
        "status": "completed", "reassigned": 2,
        "conversationSweep": "completed",
        "conversationsWaiting": 1, "conversationsDispatched": 1, "conversationsExpired": 0,
        "generatedAt": stamp(),
    }


def test_a_failed_sweep_is_not_swallowed(monkeypatch):
    """A silent failure here is how the gap it closes went unnoticed."""
    from stoa.jobs import dispatch_reconciler

    def explode():
        raise RuntimeError("dynamo is having a day")

    monkeypatch.setattr(
        dispatch_reconciler.teacher_dispatch_service, "reconcile_dispatches", explode
    )

    with pytest.raises(RuntimeError):
        dispatch_reconciler.handler({}, None)


def test_a_chat_escalation_nobody_took_is_swept_too(monkeypatch):
    """The chat lane is the one a student actually uses."""
    taken: list[str] = []

    monkeypatch.setattr(
        dispatch, "list_escalated_conversations",
        lambda limit=200: [
            {"conversation_id": "c-1", "escalated": True, "escalation_status": "pending"},
            {"conversation_id": "c-2", "escalated": True, "escalation_status": "in_progress"},
        ],
    )
    def fake_dispatch_conversation(conversation_id, *, conversation, now=None):
        taken.append(conversation_id)
        return {"conversationId": conversation_id, "status": "dispatched"}

    monkeypatch.setattr(dispatch, "dispatch_conversation", fake_dispatch_conversation)

    result = dispatch.reconcile_dispatches([], now=stamp())

    # Only the one still waiting; a teacher is already working on the other.
    assert taken == ["c-1"]
    assert result["conversationsWaiting"] == 1


def test_a_chat_escalation_with_a_live_teacher_is_left_alone(monkeypatch):
    monkeypatch.setattr(
        dispatch, "list_escalated_conversations",
        lambda limit=200: [{
            "conversation_id": "c-1", "escalated": True, "escalation_status": "pending",
            "dispatch_status": "dispatched", "dispatched_teacher_id": "teacher-3",
            "dispatch_deadline_at": stamp(9),
        }],
    )
    monkeypatch.setattr(
        dispatch, "dispatch_conversation",
        lambda *a, **k: pytest.fail("a teacher already has this conversation"),
    )

    result = dispatch.reconcile_dispatches([], now=stamp())

    assert result["conversationsWaiting"] == 0


def test_a_failed_chat_sweep_says_so_rather_than_reporting_nobody_waiting(monkeypatch):
    """Reporting zero for a sweep that never ran is how a broken sweep hides."""
    def explode(limit=200):
        raise RuntimeError("scan is having a day")

    monkeypatch.setattr(dispatch, "list_escalated_conversations", explode)

    result = dispatch.reconcile_dispatches([question(dispatch_status="unassigned")], now=stamp())

    assert result["conversationSweep"] == "failed"
    assert result["conversationsWaiting"] == 0


def test_a_healthy_chat_sweep_says_it_completed(monkeypatch):
    monkeypatch.setattr(dispatch, "list_escalated_conversations", lambda limit=200: [])

    result = dispatch.reconcile_dispatches([], now=stamp())

    assert result["conversationSweep"] == "completed"


def test_the_conversation_lister_asks_for_conversations_that_were_escalated(monkeypatch):
    """It was called with the wrong arguments and the failure was swallowed."""
    seen: dict[str, object] = {}

    def fake_scan(table, **kwargs):
        seen.update(kwargs)
        return [{"conversation_id": "c-1"}, {"no_id": True}]

    monkeypatch.setattr(dispatch, "_scan_filtered_items", fake_scan)
    monkeypatch.setattr(dispatch, "get_table", lambda: object())

    rows = dispatch.list_escalated_conversations()

    assert rows == [{"conversation_id": "c-1"}, {"no_id": True}]
    assert seen["expression_attribute_values"] == {
        ":conversation": "conversation",
        ":yes": True,
    }
    assert callable(seen["accept_item"])
    assert seen["accept_item"]({"conversation_id": "c-1"}) == {"conversation_id": "c-1"}
    assert seen["accept_item"]({"no_id": True}) is None


def test_the_conversation_lister_leaves_out_requests_that_have_ended(monkeypatch):
    # The limit counts what is accepted, so an ended request accepted here took
    # the place of a waiting one; enough of them and the sweep never reached it.
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        dispatch, "_scan_filtered_items", lambda table, **kwargs: seen.update(kwargs) or []
    )
    monkeypatch.setattr(dispatch, "get_table", lambda: object())
    dispatch.list_escalated_conversations()
    accept = seen["accept_item"]
    for status in ("expired", "withdrawn", "resolved", "in_progress"):
        assert accept({"conversation_id": "c-1", "escalation_status": status}) is None, status
    for row in (
        {"conversation_id": "c-1", "escalation_status": "pending"},
        {"conversation_id": "c-1"},
    ):
        assert accept(row) == row
