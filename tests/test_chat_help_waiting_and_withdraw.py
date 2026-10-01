"""#86: what a waiting student is told, and taking a chat help request back.

Dispatch used to find nobody and write nothing, so the student read `pending`
whether a teacher had the offer or no teacher existed; and a lapsed offer kept
its teacher on the conversation, so the student read `assigned`, with that
teacher's name, long after the offer was gone. A request nobody has taken can
now be withdrawn, giving the week's case back.

The rows, the dispatch and the routes are the real ones, over the shared table
double, as in test_chat_help_request_lifecycle.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fakes.dynamodb import FakeTable
import pytest

from actor_helpers import install_actor_overrides
from stoa.services import teacher_dispatch_service

import test_chat_help_request_lifecycle as lifecycle
from test_chat_help_request_lifecycle import (
    CONV,
    CONV_KEY,
    CREATED,
    OTHER_TEACHER,
    STUDENT,
    TEACHER,
    _conv,
    _dispatch_to,
)

@pytest.fixture
def table(monkeypatch) -> FakeTable:
    # The lifecycle tests' production-shaped rows, left waiting by the sweep.
    built = lifecycle.build_table(monkeypatch)
    lifecycle.keep_waiting(monkeypatch)
    return built


def _at(minutes: int) -> str:
    return (datetime.fromisoformat(CREATED) + timedelta(minutes=minutes)).isoformat()


def _nobody_available(table: FakeTable) -> None:
    for teacher in (TEACHER, OTHER_TEACHER):
        table.rows[(f"USER#{teacher}", "PROFILE")]["dispatch_availability"] = "paused"


def _sweep(table: FakeTable, minutes: int) -> dict:
    return teacher_dispatch_service.dispatch_conversation(
        CONV, conversation=dict(table.rows[CONV_KEY]), now=_at(minutes), table=table
    )


def _conversation_writes(table: FakeTable) -> int:
    return sum(
        1
        for operation, request in table.requests
        if operation == "update_item" and request["Key"]["PK"] == f"CONV#{CONV}"
    )


def _student() -> TestClient:
    from stoa.routers import conversations
    from stoa.security.route_authorization import get_authorization_fact_repository

    app = FastAPI()
    app.include_router(conversations.router, prefix="/conversations")
    app.include_router(conversations.teacher_help_router, prefix="/teacher-help")
    install_actor_overrides(app, {"sub": STUDENT, "role": "student"})
    app.dependency_overrides.pop(get_authorization_fact_repository, None)
    return TestClient(app, raise_server_exceptions=False)


def _status(client: TestClient) -> dict:
    response = client.get(f"/teacher-help/conversations/{CONV}/request")
    assert response.status_code == 200, response.text
    return response.json()


# --- Recording that nobody could be offered the request ---


def test_finding_nobody_is_recorded_on_the_conversation(table) -> None:
    _nobody_available(table)
    assert _sweep(table, 5)["status"] == "no_candidate"
    conversation = _conv(table)
    assert conversation["dispatch_status"] == "no_candidate"
    assert conversation["dispatch_no_candidate_reason"]
    assert conversation["dispatch_no_candidate_since"] == _at(5)


def test_finding_nobody_again_writes_nothing(table) -> None:
    _nobody_available(table)
    _sweep(table, 5)
    writes = _conversation_writes(table)
    _sweep(table, 10)
    _sweep(table, 15)
    assert _conversation_writes(table) == writes
    assert _conv(table)["dispatch_no_candidate_since"] == _at(5)


def test_a_new_reason_is_recorded_but_the_wait_keeps_its_start(table) -> None:
    _nobody_available(table)
    _sweep(table, 5)
    _conv(table)["dispatch_no_candidate_reason"] = "something_else"
    _sweep(table, 10)
    assert _conv(table)["dispatch_no_candidate_reason"] != "something_else"
    assert _conv(table)["dispatch_no_candidate_since"] == _at(5)


def test_an_offer_clears_the_record_of_finding_nobody(table) -> None:
    _nobody_available(table)
    _sweep(table, 5)
    _dispatch_to(table, TEACHER)
    conversation = _conv(table)
    assert conversation["dispatch_status"] == "dispatched"
    assert "dispatch_no_candidate_reason" not in conversation
    assert "dispatch_no_candidate_since" not in conversation


def test_a_lapsed_offer_is_taken_off_the_conversation_when_nobody_replaces_it(table) -> None:
    _dispatch_to(table, TEACHER)
    deadline = _conv(table)["dispatch_deadline_at"]
    _nobody_available(table)
    later = (datetime.fromisoformat(deadline) + timedelta(minutes=1)).isoformat()
    teacher_dispatch_service.dispatch_conversation(
        CONV, conversation=dict(_conv(table)), now=later, table=table
    )
    conversation = _conv(table)
    assert conversation["dispatch_status"] == "no_candidate"
    for field in ("dispatched_teacher_id", "dispatch_id", "dispatch_deadline_at"):
        assert field not in conversation


def test_a_new_offer_made_meanwhile_is_not_overwritten(table) -> None:
    # The sweep decided on a read taken before another sweep made an offer.
    stale = dict(_conv(table))
    _dispatch_to(table, TEACHER)
    _nobody_available(table)
    teacher_dispatch_service.dispatch_conversation(
        CONV, conversation=stale, now=_at(1), table=table
    )
    assert _conv(table)["dispatch_status"] == "dispatched"
    assert _conv(table)["dispatched_teacher_id"] == TEACHER


# --- What the student reads ---


def test_the_student_is_told_no_teacher_is_available(table) -> None:
    _nobody_available(table)
    _sweep(table, 5)
    body = _status(_student())
    assert body["status"] == "waiting_no_teacher"
    assert body["teacherName"] is None


def test_the_student_sees_the_teacher_holding_a_live_offer(table) -> None:
    table.rows[(f"USER#{TEACHER}", "PROFILE")]["name"] = "Frau Keller"
    _dispatch_to(table, TEACHER)
    body = _status(_student())
    assert body["status"] == "assigned"
    assert body["teacherName"] == "Frau Keller"


def test_a_lapsed_offer_no_longer_shows_its_teacher(table) -> None:
    table.rows[(f"USER#{TEACHER}", "PROFILE")]["name"] = "Frau Keller"
    _dispatch_to(table, TEACHER)
    _conv(table)["dispatch_deadline_at"] = _at(-1)
    body = _status(_student())
    assert body["status"] == "pending"
    assert body["teacherName"] is None


def test_a_request_never_offered_reads_as_pending(table) -> None:
    assert _status(_student())["status"] == "pending"


# --- Withdrawing a request nobody has taken ---


def _admit_case(table: FakeTable) -> None:
    """Spend the week's case for this conversation the way the request route does."""
    from datetime import timezone

    from stoa.db.repositories import account_deletion_repo
    from stoa.services import teacher_support_allowance_service as allowance

    def persist(operations):
        account_deletion_repo.transact(
            [account_deletion_repo.active_fence_condition(STUDENT, 1), *operations],
            table=table,
        )
        return True

    result = allowance.admit_teacher_support_case(
        support_case_id=CONV,
        case_kind="conversation",
        beneficiary_id=STUDENT,
        observed_at=datetime.fromisoformat(CREATED).astimezone(timezone.utc),
        persist_case=persist,
        table=table,
    )
    assert result.disposition is allowance.TeacherSupportAdmissionDisposition.ADMITTED


def _spent(table: FakeTable) -> int:
    from datetime import timezone

    from stoa.services import teacher_support_allowance_service as allowance

    projection = allowance.get_teacher_support_projection(
        beneficiary_id=STUDENT,
        observed_at=datetime.fromisoformat(CREATED).astimezone(timezone.utc),
        table=table,
    )
    return int(projection["admittedCases"])


def _withdraw(client: TestClient):
    return client.post(f"/teacher-help/conversations/{CONV}/request/withdraw")


def _question_row(table: FakeTable) -> dict:
    return lifecycle._question(table)


def test_withdrawing_ends_both_rows_and_gives_the_case_back(table) -> None:
    _admit_case(table)
    assert _spent(table) == 1
    _nobody_available(table)
    _sweep(table, 5)

    response = _withdraw(_student())

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "withdrawn"
    conversation, question = _conv(table), _question_row(table)
    assert conversation["escalation_status"] == "withdrawn"
    assert conversation["dispatch_status"] == "withdrawn"
    assert question["status"] == "withdrawn"
    assert question["dispatch_status"] == "withdrawn"
    for field in ("dispatch_no_candidate_reason", "dispatch_no_candidate_since"):
        assert field not in conversation
    assert _spent(table) == 0


def test_a_request_with_a_live_offer_can_be_withdrawn_and_the_offer_goes(table) -> None:
    _dispatch_to(table, TEACHER)
    assert _withdraw(_student()).status_code == 200
    for row in (_conv(table), _question_row(table)):
        for field in ("dispatched_teacher_id", "dispatch_id", "dispatch_deadline_at"):
            assert field not in row, field
    # The teacher it was offered to can no longer take it.
    assert lifecycle._set_status(lifecycle._client(TEACHER), "in_progress").status_code in {
        403,
        404,
        409,
    }


def test_withdrawing_twice_writes_nothing_the_second_time(table) -> None:
    _admit_case(table)
    student = _student()
    assert _withdraw(student).status_code == 200
    transactions = table.calls["transact_write_items"]
    again = _withdraw(student)
    assert again.status_code == 200
    assert again.json()["status"] == "withdrawn"
    assert table.calls["transact_write_items"] == transactions
    assert _spent(table) == 0


def test_a_request_a_teacher_has_taken_cannot_be_withdrawn(table) -> None:
    _admit_case(table)
    _dispatch_to(table, TEACHER)
    assert lifecycle._set_status(lifecycle._client(TEACHER), "in_progress").status_code == 200

    response = _withdraw(_student())

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "teacher_help_already_accepted"
    assert _conv(table)["escalation_status"] == "in_progress"
    assert _spent(table) == 1


def test_a_teacher_accepting_at_the_same_moment_wins_and_nothing_is_refunded(
    table, monkeypatch
) -> None:
    _admit_case(table)
    _dispatch_to(table, TEACHER)
    # The teacher accepts after the withdrawal read the rows, before it writes.
    accept_once = {"done": False}

    from stoa.services import teacher_support_allowance_service as allowance

    original = allowance.refund_teacher_support_case

    def accept_first(**kwargs):
        if not accept_once["done"]:
            accept_once["done"] = True
            status = lifecycle._set_status(lifecycle._client(TEACHER), "in_progress")
            assert status.status_code == 200
        return original(**kwargs)

    monkeypatch.setattr(allowance, "refund_teacher_support_case", accept_first)

    response = _withdraw(_student())

    assert response.status_code == 409
    assert _conv(table)["escalation_status"] == "in_progress"
    assert _question_row(table)["status"] == "teacher_active"
    assert _spent(table) == 1


def test_a_withdrawn_request_is_no_longer_swept(table) -> None:
    _nobody_available(table)
    _sweep(table, 5)
    assert _withdraw(_student()).status_code == 200
    lifecycle._nothing_waits()


def test_asking_again_in_the_same_conversation_returns_the_withdrawn_request(
    table, monkeypatch
) -> None:
    from stoa.services import teacher_support_allowance_service as allowance

    _admit_case(table)
    assert _withdraw(_student()).status_code == 200
    admissions = []
    monkeypatch.setattr(
        allowance,
        "admit_teacher_support_case",
        lambda **kwargs: admissions.append(kwargs),
    )

    response = _student().post(
        "/teacher-help/request", json={"conversationId": CONV, "message": "again"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "withdrawn"
    assert admissions == []
    assert _spent(table) == 0


def test_the_status_route_reports_a_withdrawn_request(table) -> None:
    assert _withdraw(_student()).status_code == 200
    assert _status(_student())["status"] == "withdrawn"


def test_another_student_cannot_withdraw_it(table) -> None:
    from stoa.routers import conversations
    from stoa.security.route_authorization import get_authorization_fact_repository

    app = FastAPI()
    app.include_router(conversations.teacher_help_router, prefix="/teacher-help")
    install_actor_overrides(app, {"sub": "student-someone-else", "role": "student"})
    app.dependency_overrides.pop(get_authorization_fact_repository, None)
    response = TestClient(app, raise_server_exceptions=False).post(
        f"/teacher-help/conversations/{CONV}/request/withdraw"
    )
    assert response.status_code in {403, 404}
    assert _conv(table)["escalation_status"] == "pending"


def test_a_withdrawn_request_drops_off_the_dispatch_board(table) -> None:
    assert _withdraw(_student()).status_code == 200
    board = teacher_dispatch_service.list_teacher_dispatch_questions()
    assert all(item.get("question_id") != lifecycle.REQUEST for item in board)


def _before_the_write(monkeypatch, change) -> None:
    """Run ``change`` once, after the withdrawal read the rows and before it writes."""
    from stoa.services import teacher_support_allowance_service as allowance

    original = allowance.refund_teacher_support_case
    fired = {"done": False}

    def refund_after(**kwargs):
        if not fired["done"]:
            fired["done"] = True
            change()
        return original(**kwargs)

    monkeypatch.setattr(allowance, "refund_teacher_support_case", refund_after)


def test_the_conversations_own_teacher_guard_refuses_a_late_teacher(table, monkeypatch) -> None:
    # Only the conversation learns of the teacher; the queue row's version does
    # not move, so nothing but the conversation's guard can refuse the write.
    _admit_case(table)
    _before_the_write(monkeypatch, lambda: _conv(table).update(teacher_id=TEACHER))

    response = _withdraw(_student())

    assert response.status_code == 409
    assert _conv(table)["escalation_status"] == "pending"
    assert _question_row(table)["status"] == "escalated"
    assert _spent(table) == 1


def test_the_queue_rows_own_teacher_guard_refuses_a_late_teacher(table, monkeypatch) -> None:
    # Only the queue row learns of the teacher, without its version moving.
    _admit_case(table)
    _before_the_write(monkeypatch, lambda: _question_row(table).update(teacher_id=TEACHER))

    response = _withdraw(_student())

    assert response.status_code == 409
    assert _conv(table)["escalation_status"] == "pending"
    assert _spent(table) == 1


def test_an_offer_made_by_a_sweep_meanwhile_is_withdrawn_with_the_request(
    table, monkeypatch
) -> None:
    _admit_case(table)
    _before_the_write(monkeypatch, lambda: _dispatch_to(table, TEACHER))

    response = _withdraw(_student())

    assert response.status_code == 200, response.text
    for row in (_conv(table), _question_row(table)):
        assert row.get("dispatch_status") == "withdrawn"
        for field in ("dispatched_teacher_id", "dispatch_id", "dispatch_deadline_at"):
            assert field not in row, field
    assert _spent(table) == 0


def test_a_conversation_escalated_before_the_status_was_written_can_be_withdrawn(
    table,
) -> None:
    _admit_case(table)
    del _conv(table)["escalation_status"]
    response = _withdraw(_student())
    assert response.status_code == 200, response.text
    assert _conv(table)["escalation_status"] == "withdrawn"
    assert _spent(table) == 0


def test_a_parent_cannot_withdraw_their_childs_request(table) -> None:
    from stoa.routers import conversations
    from stoa.security.route_authorization import get_authorization_fact_repository
    from stoa.services import parent_link_service

    parent = "parent-of-student-66"
    table.seed(
        {
            "PK": f"USER#{parent}",
            "SK": "PROFILE",
            "user_id": parent,
            "role": "parent",
            "account_status": "active",
            "version": 1,
        },
        {"PK": f"USER#{parent}", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 1},
    )
    # A real, active link: the refusal is about the route, not a missing relationship.
    parent_link_service.assign_link(parent_id=parent, student_id=STUDENT, actor_id="admin-1")
    assert parent_link_service.active_link(parent, STUDENT) is not None

    app = FastAPI()
    app.include_router(conversations.teacher_help_router, prefix="/teacher-help")
    install_actor_overrides(app, {"sub": parent, "role": "parent"})
    app.dependency_overrides.pop(get_authorization_fact_repository, None)
    response = TestClient(app, raise_server_exceptions=False).post(
        f"/teacher-help/conversations/{CONV}/request/withdraw"
    )
    assert response.status_code in {403, 404}
    assert _conv(table)["escalation_status"] == "pending"


def test_a_withdrawn_request_still_counts_as_help_the_student_asked_for(table) -> None:
    # Decision on #86: parent and weekly-report figures keep counting it. They
    # read these two fields, which withdrawing leaves as they were.
    assert _withdraw(_student()).status_code == 200
    assert _conv(table)["escalated"] is True
    assert _question_row(table)["teacher_help_requested"] is True
