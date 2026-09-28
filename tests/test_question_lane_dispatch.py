"""Question-lane dispatch against the real repository: stoasystem/stoa-backend#75.

Every dispatch test elsewhere mocks `question_repo.mutate_question`, which hid
that a successful dispatch could never be written: it cleared
`dispatch_no_candidate_reason` by passing `None`, the serializer drops `None`
values, and DynamoDB refused an expression naming an undefined value. In
production the question lane's offer therefore always came back
`claim_conflict` (2026-09-28 15:48Z: a teacher was available and the summary
read `1 questions waiting, 0 re-offered`).

These run the real service and repository over the shared table double, which
serializes the way production does.
"""

from __future__ import annotations

import pytest

import test_chat_help_request_lifecycle as lifecycle
from stoa.services import teacher_dispatch_service

NOW = "2026-09-28T12:00:00+00:00"


@pytest.fixture
def table(monkeypatch):
    return lifecycle.table.__wrapped__(monkeypatch)


def _question_lane(table) -> dict:
    """Turn the fixture's queue row into an ordinary question-lane question."""
    row = table.rows[lifecycle.QUESTION_KEY]
    for field in ("conversation_id", "source"):
        row.pop(field, None)
    return row


def _only(table, teacher_id: str) -> None:
    for teacher in (lifecycle.TEACHER, lifecycle.OTHER_TEACHER):
        table.rows[(f"USER#{teacher}", "PROFILE")]["dispatch_availability"] = (
            "available" if teacher == teacher_id else "paused"
        )


def test_a_question_lane_question_is_dispatched_and_the_old_reason_cleared(table):
    row = _question_lane(table)
    assert row["dispatch_no_candidate_reason"] == "not_available"
    _only(table, lifecycle.TEACHER)
    before = int(row["version"])

    result = teacher_dispatch_service.dispatch_question(lifecycle.REQUEST, now=NOW)

    assert result["status"] == "dispatched", result
    row = table.rows[lifecycle.QUESTION_KEY]
    assert row["dispatch_status"] == "dispatched"
    assert row["dispatched_teacher_id"] == lifecycle.TEACHER
    assert row["dispatch_id"] == result["dispatchId"]
    assert "dispatch_no_candidate_reason" not in row
    assert int(row["version"]) == before + 1


def test_a_lapsed_question_lane_offer_goes_to_the_next_teacher(table):
    _question_lane(table)
    _only(table, lifecycle.TEACHER)
    assert teacher_dispatch_service.dispatch_question(lifecycle.REQUEST, now=NOW)["status"] == "dispatched"
    table.rows[lifecycle.QUESTION_KEY]["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"
    _only(table, lifecycle.OTHER_TEACHER)

    outcome = teacher_dispatch_service.reassign_timed_out_dispatches(now=NOW)

    assert outcome["results"][0]["status"] == "dispatched", outcome
    row = table.rows[lifecycle.QUESTION_KEY]
    assert row["dispatched_teacher_id"] == lifecycle.OTHER_TEACHER
    assert lifecycle.TEACHER in row["previous_dispatch_teacher_ids"]


def test_the_question_lane_does_not_offer_a_chat_queue_row_on_its_own(table, monkeypatch):
    # With the question lane's offer working again, it would split a chat
    # request: offer the queue row to one teacher while the conversation waits.
    # The conversation lane offers both rows; the question lane leaves them.
    _only(table, lifecycle.TEACHER)
    monkeypatch.setattr(teacher_dispatch_service, "list_escalated_conversations", lambda limit=200: [])

    teacher_dispatch_service.reconcile_dispatches()

    row = table.rows[lifecycle.QUESTION_KEY]
    assert row["dispatch_status"] == "unassigned"
    assert "dispatched_teacher_id" not in row


def test_a_lapsed_chat_offer_is_recorded_but_not_re_offered_by_the_question_lane(table, monkeypatch):
    # The timeout is still recorded on the queue row, which the conversation
    # lane and accepting rely on; the re-offer is left to the conversation lane.
    lifecycle._dispatch_to(table, lifecycle.TEACHER)
    for key in (lifecycle.CONV_KEY, lifecycle.QUESTION_KEY):
        table.rows[key]["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"
    _only(table, lifecycle.OTHER_TEACHER)
    monkeypatch.setattr(teacher_dispatch_service, "list_escalated_conversations", lambda limit=200: [])

    teacher_dispatch_service.reconcile_dispatches()

    row = table.rows[lifecycle.QUESTION_KEY]
    assert lifecycle.TEACHER in row["previous_dispatch_teacher_ids"]
    assert row["dispatch_status"] == "timed_out"
    assert row.get("dispatched_teacher_id") != lifecycle.OTHER_TEACHER


def test_the_transaction_builder_clears_a_field_given_none(table):
    # The same None-to-REMOVE rule for the builder used by conversation-lane
    # writes; no caller passes None to it today, so it is pinned directly.
    from stoa.db.repositories import account_deletion_repo, question_repo

    row = table.rows[lifecycle.QUESTION_KEY]
    before = int(row["version"])

    account_deletion_repo.transact(
        question_repo.build_question_update_transaction(
            dict(row),
            status=row["status"],
            expected_generation=1,
            extra_attrs={"dispatch_no_candidate_reason": None, "dispatch_status": "unassigned"},
        ),
        table=table,
    )

    row = table.rows[lifecycle.QUESTION_KEY]
    assert "dispatch_no_candidate_reason" not in row
    assert row["dispatch_status"] == "unassigned"
    assert int(row["version"]) == before + 1


def test_dispatch_question_itself_refuses_a_chat_queue_row(table):
    # Every caller of the question lane's dispatch, present and future, is
    # covered here rather than by each caller remembering to skip chat rows.
    # The fixture's queue row is a chat request's.
    _only(table, lifecycle.TEACHER)
    before = dict(table.rows[lifecycle.QUESTION_KEY])

    result = teacher_dispatch_service.dispatch_question(lifecycle.REQUEST, now=NOW)

    assert result["status"] == "not_dispatchable"
    assert result["reason"] == "chat_help_request"
    assert table.rows[lifecycle.QUESTION_KEY] == before
