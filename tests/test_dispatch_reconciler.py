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


@pytest.fixture
def dispatched(monkeypatch):
    """Record which questions were handed to a teacher."""
    calls: list[str] = []

    def fake_dispatch(question_id, *, question=None, now=None):
        calls.append(question_id)
        return {"questionId": question_id, "status": "dispatched", "teacherId": "teacher-1"}

    monkeypatch.setattr(dispatch, "dispatch_question", fake_dispatch)
    return calls


def test_a_question_nobody_was_offered_is_offered_now(dispatched):
    """The request tried, found nobody free, and never tried again."""
    waiting = question(dispatch_status="unassigned")

    result = dispatch.reconcile_dispatches([waiting], now=stamp())

    assert dispatched == ["q-1"]
    assert result["waiting"] == 1


def test_a_question_whose_dispatch_failed_outright_is_offered_now(dispatched):
    # The request swallowed the failure, so the question carries no dispatch.
    waiting = question()

    dispatch.reconcile_dispatches([waiting], now=stamp())

    assert dispatched == ["q-1"]


def test_a_teacher_still_within_the_deadline_is_left_alone(dispatched):
    live = question(
        dispatch_status="dispatched",
        dispatched_teacher_id="teacher-7",
        dispatch_deadline_at=stamp(9),
    )

    result = dispatch.reconcile_dispatches([live], now=stamp())

    assert dispatched == []
    assert result["waiting"] == 0


def test_a_teacher_who_let_the_deadline_pass_loses_the_question(monkeypatch):
    moved: list[dict[str, Any]] = []

    def fake_reassign(items, *, now=None):
        moved.append({"items": items, "now": now})
        return {"processed": 1, "results": [{"questionId": "q-1", "status": "dispatched"}]}

    monkeypatch.setattr(dispatch, "reassign_timed_out_dispatches", fake_reassign)
    monkeypatch.setattr(
        dispatch, "dispatch_question",
        lambda question_id, *, question=None, now=None: {"questionId": question_id, "status": "dispatched"},
    )
    stale = question(
        dispatch_status="dispatched",
        dispatched_teacher_id="teacher-7",
        dispatch_deadline_at=stamp(-1),
    )

    result = dispatch.reconcile_dispatches([stale], now=stamp())

    assert result["reassigned"] == 1
    assert moved and moved[0]["now"] == stamp()


def test_a_question_already_answered_is_not_touched(dispatched):
    done = question(status="teacher_active", dispatched_teacher_id="teacher-7")

    result = dispatch.reconcile_dispatches([done], now=stamp())

    assert dispatched == []
    assert result["waiting"] == 0


def test_running_it_twice_changes_nothing_the_second_time(monkeypatch):
    """The sweep runs on a schedule, so it must be safe to repeat."""
    state = {"dispatched": False}

    def fake_dispatch(question_id, *, question=None, now=None):
        if state["dispatched"]:
            return {"questionId": question_id, "status": "already_dispatched"}
        state["dispatched"] = True
        return {"questionId": question_id, "status": "dispatched"}

    monkeypatch.setattr(dispatch, "dispatch_question", fake_dispatch)
    waiting = question(dispatch_status="unassigned")

    first = dispatch.reconcile_dispatches([waiting], now=stamp())
    second = dispatch.reconcile_dispatches([waiting], now=stamp(1))

    assert first["dispatched"] == [{"questionId": "q-1", "status": "dispatched"}]
    assert second["dispatched"] == []


def test_no_free_teacher_is_reported_rather_than_silently_dropped(monkeypatch):
    monkeypatch.setattr(
        dispatch, "dispatch_question",
        lambda question_id, *, question=None, now=None: {
            "questionId": question_id, "status": "no_candidate",
        },
    )

    result = dispatch.reconcile_dispatches([question(dispatch_status="unassigned")], now=stamp())

    assert result["dispatched"] == [{"questionId": "q-1", "status": "no_candidate"}]


def test_a_question_without_an_identifier_cannot_derail_the_sweep(dispatched):
    result = dispatch.reconcile_dispatches(
        [question(question_id=""), question(question_id="q-2", dispatch_status="unassigned")],
        now=stamp(),
    )

    assert dispatched == ["q-2"]
    assert result["waiting"] == 2


def test_the_scheduled_job_reports_what_it_did(monkeypatch):
    from stoa.jobs import dispatch_reconciler

    monkeypatch.setattr(
        dispatch_reconciler.teacher_dispatch_service, "reconcile_dispatches",
        lambda: {"reassigned": 2, "waiting": 3, "dispatched": [{"questionId": "q-1"}],
                 "reassignments": [], "conversationsWaiting": 1,
                 "conversationsDispatched": [{"conversationId": "c-1"}],
                 "generatedAt": stamp()},
    )

    result = dispatch_reconciler.handler({"job": "dispatch_reconcile"}, None)

    assert result == {
        "status": "completed", "reassigned": 2, "waiting": 3, "dispatched": 1,
        "conversationsWaiting": 1, "conversationsDispatched": 1,
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
    monkeypatch.setattr(
        dispatch, "dispatch_question",
        lambda question_id, *, question=None, now=None: {"status": "dispatched"},
    )

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
    monkeypatch.setattr(
        dispatch, "dispatch_question",
        lambda question_id, *, question=None, now=None: {"status": "dispatched"},
    )

    result = dispatch.reconcile_dispatches([], now=stamp())

    assert result["conversationsWaiting"] == 0


def test_a_failing_chat_sweep_does_not_lose_the_question_sweep(monkeypatch, dispatched):
    def explode(limit=200):
        raise RuntimeError("scan is having a day")

    monkeypatch.setattr(dispatch, "list_escalated_conversations", explode)

    result = dispatch.reconcile_dispatches([question(dispatch_status="unassigned")], now=stamp())

    assert dispatched == ["q-1"]
    assert result["conversationsWaiting"] == 0
