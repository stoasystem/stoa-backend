"""#144: whether the student can still ask a teacher this week, and when that resets.

The 「找老师」 button appears under an AI answer that suggests it (#133, D2/Q20).
When the week's teacher-support cases are spent, the button is greyed with the
reason and the moment it comes back, so the student knows the way exists. The
chat indicator's read, `GET /teacher-help/availability`, carries that standing.

Cases are spent through the real `POST /teacher-help/request`, over the shared
table double, so the read is held to the same rule the request is refused by.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fakes.dynamodb import FakeTable
import pytest

from actor_helpers import install_actor_overrides

import test_chat_help_request_lifecycle as lifecycle
from test_chat_help_request_lifecycle import STUDENT

# A Wednesday in Zurich's winter time: the week turns at Monday 2 November
# 00:00 in Zurich, which is 23:00 UTC the evening before.
WEDNESDAY = "2026-10-28T10:00:00+00:00"
NEXT_MONDAY = "2026-11-01T23:00:00+00:00"


@pytest.fixture
def table(monkeypatch) -> FakeTable:
    built = lifecycle.build_table(monkeypatch)
    lifecycle.keep_waiting(monkeypatch)
    _clock(monkeypatch, WEDNESDAY)
    return built


def _clock(monkeypatch, now: str) -> None:
    from stoa.routers import conversations

    monkeypatch.setattr(conversations, "_now", lambda: now)


def _weekly_cases(table: FakeTable, cases: int, *, version: int = 1) -> None:
    """The figure an administrator set for this student."""
    from stoa.services import teacher_support_allowance_service as allowance

    table.seed(
        {
            "PK": f"USER#{STUDENT}",
            "SK": allowance.ASSIGNED_ALLOWANCE_SK,
            "entity_type": "teacher_support_assigned_allowance",
            "schema_version": allowance.ASSIGNED_ALLOWANCE_SCHEMA_VERSION,
            "weekly_cases": Decimal(cases),
            "state_version": Decimal(version),
        }
    )


def _conversation(table: FakeTable, conversation_id: str) -> str:
    table.seed(
        {
            "PK": f"CONV#{conversation_id}",
            "SK": "CONV",
            "account_fence_generation": 1,
            "conversation_id": conversation_id,
            "created_at": WEDNESDAY,
            "entity_type": "conversation",
            "grade": "6",
            "owner_id": STUDENT,
            "student_id": STUDENT,
            "subject": "mathematics",
            "title": "Fractions",
            "updated_at": WEDNESDAY,
        }
    )
    return conversation_id


def _student(student_id: str = STUDENT) -> TestClient:
    from stoa.routers import conversations
    from stoa.security.route_authorization import get_authorization_fact_repository

    app = FastAPI()
    app.include_router(conversations.teacher_help_router, prefix="/teacher-help")
    install_actor_overrides(app, {"sub": student_id, "role": "student"})
    app.dependency_overrides.pop(get_authorization_fact_repository, None)
    return TestClient(app, raise_server_exceptions=False)


def _ask(table: FakeTable, conversation_id: str):
    _conversation(table, conversation_id)
    return _student().post(
        "/teacher-help/request",
        json={"conversationId": conversation_id, "message": "Step 2?"},
    )


def _standing() -> dict:
    response = _student().get("/teacher-help/availability")
    assert response.status_code == 200, response.text
    return response.json()["teacherSupport"]


def test_a_student_with_cases_left_can_ask_and_is_told_how_many(table) -> None:
    assert _standing() == {
        "canRequest": True,
        "blockedReason": None,
        "remainingCases": 7,
        "weeklyCases": 7,
        "resetsAt": NEXT_MONDAY,
    }


def test_a_request_spends_one_of_the_weeks_cases(table) -> None:
    assert _ask(table, "conv-144-a").status_code == 200

    standing = _standing()

    assert standing["canRequest"] is True
    assert standing["remainingCases"] == 6


def test_once_the_week_is_spent_the_student_reads_why_and_until_when(table) -> None:
    _weekly_cases(table, 1)
    assert _ask(table, "conv-144-a").status_code == 200

    assert _standing() == {
        "canRequest": False,
        "blockedReason": "teacher_support_allowance_exhausted",
        "remainingCases": 0,
        "weeklyCases": 1,
        "resetsAt": NEXT_MONDAY,
    }
    # The request is refused for the reason the read gave.
    refused = _ask(table, "conv-144-b")
    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "teacher_support_allowance_exhausted"


def test_a_spent_week_is_whole_again_when_the_week_turns(table, monkeypatch) -> None:
    _weekly_cases(table, 1)
    assert _ask(table, "conv-144-a").status_code == 200

    # One minute before the turn the case is still spent ...
    _clock(monkeypatch, "2026-11-01T22:59:00+00:00")
    assert _standing()["canRequest"] is False
    assert _standing()["resetsAt"] == NEXT_MONDAY

    # ... and at the moment it gives, the week is new and so is its end.
    _clock(monkeypatch, NEXT_MONDAY)
    standing = _standing()
    assert standing["canRequest"] is True
    assert standing["remainingCases"] == 1
    assert standing["resetsAt"] == "2026-11-08T23:00:00+00:00"
    assert _ask(table, "conv-144-b").status_code == 200


def test_the_week_turns_at_zurich_midnight_in_summer_time_too(table, monkeypatch) -> None:
    _clock(monkeypatch, "2026-07-01T10:00:00+00:00")
    assert _standing()["resetsAt"] == "2026-07-05T22:00:00+00:00"


def test_a_withdrawn_request_gives_the_case_back_to_the_read(table) -> None:
    _weekly_cases(table, 1)
    assert _ask(table, "conv-144-a").status_code == 200
    assert _standing()["canRequest"] is False

    withdrawn = _student().post("/teacher-help/conversations/conv-144-a/request/withdraw")

    assert withdrawn.status_code == 200, withdrawn.text
    assert _standing()["canRequest"] is True


def test_a_figure_lowered_below_what_was_spent_reads_as_none_left(table) -> None:
    _weekly_cases(table, 2)
    assert _ask(table, "conv-144-a").status_code == 200
    assert _ask(table, "conv-144-b").status_code == 200
    _weekly_cases(table, 1, version=2)

    standing = _standing()

    assert standing["canRequest"] is False
    assert standing["blockedReason"] == "teacher_support_allowance_exhausted"
    assert standing["remainingCases"] == 0


def test_a_student_without_teacher_support_is_not_told_to_wait_a_week(table) -> None:
    _weekly_cases(table, 0)

    assert _standing() == {
        "canRequest": False,
        "blockedReason": "teacher_support_not_included",
        "remainingCases": 0,
        "weeklyCases": 0,
        "resetsAt": None,
    }
    refused = _ask(table, "conv-144-a")
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "teacher_support_not_included"


def test_an_allowance_that_cannot_be_read_leaves_the_indicator_working(table) -> None:
    from stoa.services import teacher_support_allowance_service as allowance

    table.rows[(f"USER#{STUDENT}", allowance.ASSIGNED_ALLOWANCE_SK)] = {
        "PK": f"USER#{STUDENT}",
        "SK": allowance.ASSIGNED_ALLOWANCE_SK,
        "entity_type": "something_else",
    }

    response = _student().get("/teacher-help/availability")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["teacherSupport"] is None
    assert "online" in body


def test_a_read_failing_in_an_unexpected_way_still_leaves_the_indicator_working(
    table, monkeypatch
) -> None:
    from stoa.services import teacher_support_allowance_service as allowance

    def unreachable(*_args, **_kwargs):
        raise RuntimeError("relationship read failed")

    # Not every read on the way is wrapped: a parent binding's versions, say.
    monkeypatch.setattr(allowance, "_resolve_scope", unreachable)

    response = _student().get("/teacher-help/availability")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["teacherSupport"] is None
    assert "online" in body


def test_each_student_reads_their_own_week(table) -> None:
    _weekly_cases(table, 1)
    assert _ask(table, "conv-144-a").status_code == 200
    other = "student-144-other"
    table.seed(
        {
            "PK": f"USER#{other}",
            "SK": "PROFILE",
            "user_id": other,
            "role": "student",
            "account_status": "active",
            "version": 1,
        },
        {"PK": f"USER#{other}", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 1},
    )

    response = _student(other).get("/teacher-help/availability")

    assert response.status_code == 200, response.text
    assert response.json()["teacherSupport"]["canRequest"] is True
    assert response.json()["teacherSupport"]["remainingCases"] == 7
