"""#87: a chat help request no teacher took within the waiting limit ends.

The sweep used to re-offer a waiting request every five minutes, for ever; a
student with no teacher available waited on nothing, with the week's case
spent. Past the limit (24 hours unless configured) the sweep now ends both
rows as `expired`, gives the case back and tells the student, once. A teacher
who accepts first wins.

The rows, the sweep and the routes are the real ones over the shared table
double, as in test_chat_help_waiting_and_withdraw.py, with the clock and the
limit set by each test.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fakes.dynamodb import FakeTable
import pytest

from stoa.config import settings
from stoa.services import notification_service, teacher_dispatch_service

import test_chat_help_request_lifecycle as lifecycle
from test_chat_help_request_lifecycle import CONV, CREATED, TEACHER, _conv, _dispatch_to
from test_chat_help_waiting_and_withdraw import (
    _admit_case,
    _before_the_write,
    _nobody_available,
    _spent,
    _status,
    _student,
    _withdraw,
)

DAY = 24 * 60 * 60


def _after(seconds: int) -> str:
    return (datetime.fromisoformat(CREATED) + timedelta(seconds=seconds)).isoformat()


@pytest.fixture
def table(monkeypatch) -> FakeTable:
    built = lifecycle.build_table(monkeypatch)
    monkeypatch.setattr(settings, "teacher_help_expiry_seconds", DAY)
    return built


@pytest.fixture
def notices(monkeypatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(
        notification_service, "create_event_safe", lambda **kwargs: sent.append(kwargs)
    )
    return sent


def _sweep(at: str) -> dict:
    return teacher_dispatch_service.reconcile_dispatches(now=at)


def _question(table: FakeTable) -> dict:
    return lifecycle._question(table)


def test_a_request_inside_the_limit_is_offered_again_not_ended(table, notices) -> None:
    _nobody_available(table)
    outcome = _sweep(_after(DAY - 60))
    assert outcome["conversationsExpired"] == []
    assert _conv(table)["escalation_status"] == "pending"
    assert notices == []


def test_a_request_past_the_limit_ends_and_its_case_comes_back(table, notices) -> None:
    _admit_case(table)
    _nobody_available(table)
    outcome = _sweep(_after(DAY + 60))
    assert outcome["conversationsExpired"] == [CONV]
    conversation, question = _conv(table), _question(table)
    assert conversation["escalation_status"] == "expired"
    assert conversation["dispatch_status"] == "expired"
    assert conversation["escalation_expired_at"] == _after(DAY + 60)
    assert question["status"] == "expired"
    assert question["dispatch_status"] == "expired"
    assert _spent(table) == 0


def test_the_student_is_told_once(table, notices) -> None:
    _nobody_available(table)
    _sweep(_after(DAY + 60))
    _sweep(_after(DAY + 360))
    [notice] = notices
    assert notice["event_type"] == "teacher_help_expired"
    assert notice["recipient_id"] == lifecycle.STUDENT
    assert notice["recipient_role"] == "student"
    assert notice["event_id"] == f"teacher-help-expired-{lifecycle.REQUEST}"


def test_a_second_notice_for_the_same_request_is_refused_by_the_store(
    table, monkeypatch
) -> None:
    # The notice's id is the request's, so even a repeat call stores one event.
    monkeypatch.setenv("STOA_ENABLE_BEST_EFFORT_NOTIFICATIONS", "true")
    _nobody_available(table)
    _sweep(_after(DAY + 60))
    first = [
        row for row in table.rows.values() if row.get("event_type") == "teacher_help_expired"
    ]
    assert len(first) == 1
    notification_service.create_event_safe(
        recipient_id=lifecycle.STUDENT,
        recipient_role="student",
        event_type="teacher_help_expired",
        target_type="conversation",
        target_id=CONV,
        title="again",
        summary="again",
        owner_id=lifecycle.STUDENT,
        account_fence_generation=1,
        event_id=f"teacher-help-expired-{lifecycle.REQUEST}",
    )
    again = [
        row for row in table.rows.values() if row.get("event_type") == "teacher_help_expired"
    ]
    assert len(again) == 1


def test_an_outstanding_offer_does_not_keep_a_request_alive(table, notices) -> None:
    _dispatch_to(table, TEACHER)
    _sweep(_after(DAY + 60))
    assert _conv(table)["escalation_status"] == "expired"
    for row in (_conv(table), _question(table)):
        for field in ("dispatched_teacher_id", "dispatch_id", "dispatch_deadline_at"):
            assert field not in row, field
    taking = lifecycle._set_status(lifecycle._client(TEACHER), "in_progress")
    assert taking.status_code in {403, 404, 409}


def test_a_request_a_teacher_has_taken_does_not_expire(table, notices) -> None:
    _admit_case(table)
    _dispatch_to(table, TEACHER)
    assert lifecycle._set_status(lifecycle._client(TEACHER), "in_progress").status_code == 200
    outcome = _sweep(_after(DAY + 60))
    assert outcome["conversationsExpired"] == []
    assert _conv(table)["escalation_status"] == "in_progress"
    assert _spent(table) == 1
    assert notices == []


def test_a_teacher_accepting_at_the_same_moment_wins(table, notices, monkeypatch) -> None:
    _admit_case(table)
    _dispatch_to(table, TEACHER)
    _before_the_write(
        monkeypatch,
        lambda: lifecycle._set_status(lifecycle._client(TEACHER), "in_progress"),
    )
    outcome = _sweep(_after(DAY + 60))
    assert outcome["conversationsExpired"] == []
    assert _conv(table)["escalation_status"] == "in_progress"
    assert _question(table)["status"] == "teacher_active"
    assert _spent(table) == 1
    assert notices == []


def test_an_expired_request_is_not_offered_again(table, notices) -> None:
    _nobody_available(table)
    _sweep(_after(DAY + 60))
    later = _sweep(_after(DAY + 600))
    assert later["conversationsWaiting"] == 0
    assert later["conversationsExpired"] == []
    board = teacher_dispatch_service.list_teacher_dispatch_questions()
    assert all(item.get("question_id") != lifecycle.REQUEST for item in board)


def test_the_student_reads_expired(table, notices) -> None:
    _nobody_available(table)
    _sweep(_after(DAY + 60))
    assert _status(_student())["status"] == "expired"


def test_an_expired_request_cannot_then_be_withdrawn(table, notices) -> None:
    _admit_case(table)
    _nobody_available(table)
    _sweep(_after(DAY + 60))
    response = _withdraw(_student())
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "teacher_help_request_closed"
    assert _spent(table) == 0


def test_the_limit_is_configurable(table, notices, monkeypatch) -> None:
    monkeypatch.setattr(settings, "teacher_help_expiry_seconds", 3600)
    _nobody_available(table)
    assert _sweep(_after(3500))["conversationsExpired"] == []
    assert _sweep(_after(3700))["conversationsExpired"] == [CONV]


def test_a_failed_expiry_does_not_stop_the_sweep(table, notices, monkeypatch) -> None:
    def unavailable(*_args, **_kwargs):
        raise teacher_dispatch_service.HelpRequestEndingUnavailable(CONV)

    monkeypatch.setattr(teacher_dispatch_service, "expire_help_request", unavailable)
    outcome = _sweep(_after(DAY + 60))
    assert outcome["conversationSweep"] == "completed"
    assert outcome["conversationsExpired"] == []
    assert _conv(table)["escalation_status"] == "pending"


# --- From the review of #87 ---


def test_a_sweep_working_from_a_stale_read_neither_counts_nor_tells_again(
    table, notices, monkeypatch
) -> None:
    # Two sweeps overlapping: the second still holds the pending row it listed.
    _nobody_available(table)
    stale = dict(_conv(table))
    assert _sweep(_after(DAY + 60))["conversationsExpired"] == [CONV]
    monkeypatch.setattr(
        teacher_dispatch_service, "list_escalated_conversations", lambda limit=200: [stale]
    )
    assert _sweep(_after(DAY + 120))["conversationsExpired"] == []
    assert len(notices) == 1


def test_a_conversation_without_its_own_stamp_expires_by_the_queue_rows(table, notices) -> None:
    del _conv(table)["escalated_at"]
    _nobody_available(table)
    assert _sweep(_after(DAY + 60))["conversationsExpired"] == [CONV]


def test_a_request_with_no_readable_stamp_anywhere_is_left_and_said(
    table, notices, caplog
) -> None:
    _conv(table)["escalated_at"] = "garbage"
    del _question(table)["teacher_requested_at"]
    _nobody_available(table)
    with caplog.at_level("WARNING"):
        assert _sweep(_after(DAY + 60))["conversationsExpired"] == []
    assert _conv(table)["escalation_status"] == "pending"
    assert any("Cannot tell when" in record.message for record in caplog.records)
    assert notices == []


def test_a_conversation_escalated_before_the_status_was_written_expires(table, notices) -> None:
    del _conv(table)["escalation_status"]
    _nobody_available(table)
    assert _sweep(_after(DAY + 60))["conversationsExpired"] == [CONV]
    assert _conv(table)["escalation_status"] == "expired"


def test_a_withdrawn_request_does_not_expire_or_notify(table, notices) -> None:
    _admit_case(table)
    assert _withdraw(_student()).status_code == 200
    assert _sweep(_after(DAY + 60))["conversationsExpired"] == []
    assert _conv(table)["escalation_status"] == "withdrawn"
    assert _spent(table) == 0
    assert notices == []


def test_an_expiry_landing_during_a_withdrawal_gives_back_one_case(
    table, notices, monkeypatch
) -> None:
    _admit_case(table)
    _nobody_available(table)
    _before_the_write(monkeypatch, lambda: _sweep(_after(DAY + 60)))
    response = _withdraw(_student())
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "teacher_help_request_closed"
    assert _conv(table)["escalation_status"] == "expired"
    assert _spent(table) == 0
    assert len(notices) == 1


def test_a_request_whose_case_was_never_spent_does_not_claim_one_back(table, notices) -> None:
    _nobody_available(table)
    _sweep(_after(DAY + 60))
    [notice] = notices
    assert "given back" not in notice["summary"]


def test_a_case_spent_this_week_is_said_to_come_back(table, notices) -> None:
    _admit_case(table)
    _nobody_available(table)
    _sweep(_after(DAY + 60))
    [notice] = notices
    assert "given back" in notice["summary"]


def test_a_case_from_a_week_that_has_ended_goes_back_there_and_is_not_promised(
    table, notices
) -> None:
    # Decision on #87: the case returns to the week it was asked in.
    _admit_case(table)
    _nobody_available(table)
    _sweep(_after(8 * DAY))
    assert _spent(table) == 0
    [notice] = notices
    assert "given back" not in notice["summary"]


def test_a_request_whose_rows_disagree_is_left_said_and_not_announced(
    table, notices, caplog
) -> None:
    _question(table)["status"] = "teacher_active"
    _nobody_available(table)
    with caplog.at_level("WARNING"):
        assert _sweep(_after(DAY + 60))["conversationsExpired"] == []
    assert _conv(table)["escalation_status"] == "pending"
    assert any("refused: teacher_help_request_not_withdrawable" in r.message for r in caplog.records)
    assert notices == []


def test_one_bad_row_does_not_stop_the_rest_of_the_sweep(table, notices, monkeypatch) -> None:
    real = teacher_dispatch_service.expire_help_request
    bad = {
        "conversation_id": "conv-bad",
        "escalation_status": "pending",
        "escalated_at": CREATED,
    }

    def expire(conversation_id, **kwargs):
        if conversation_id == "conv-bad":
            raise ValueError("a row the transaction builder cannot use")
        return real(conversation_id, **kwargs)

    monkeypatch.setattr(teacher_dispatch_service, "expire_help_request", expire)
    monkeypatch.setattr(
        teacher_dispatch_service,
        "list_escalated_conversations",
        lambda limit=200: [bad, dict(_conv(table))],
    )
    _nobody_available(table)
    outcome = _sweep(_after(DAY + 60))
    assert outcome["conversationSweep"] == "completed"
    assert outcome["conversationsExpired"] == [CONV]
