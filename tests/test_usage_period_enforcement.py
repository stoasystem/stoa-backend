"""#344: an ended usage period stops new questions and new requests for a teacher.

Step 3 of #239 (the「#239 形状定完」shape, decisions 4 to 7). A question is
refused `403 usage_period_ended` at admission, judged in its one eligibility
read, before anything is stored or counted; a request for a human teacher is
refused with the same code before a case of the week is spent. No period at all
counts as ended. What is already under way is not refused: a question claimed
before the period ended is still answered.

These run the real eligibility read (`entitlement_service.resolve_student_entitlement`)
and the real period rule over profiles on the table; only the model is faked.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.config import Settings
from fakes.ask_question import (
    CONV,
    STUDENT,
    _client,
    _command_key,
    _commit,
    _deliver,
    _messages,
    _send,
)
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.dynamodb import FakeTable
from fakes.learning_session import seed_conversation
from fakes.links import LinkRows
from stoa.db import table as db_table
from stoa.db.repositories import parent_link_repo, user_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import conversations
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import (
    entitlement_service,
    help_requests,
    learning_session,
    teacher_support_allowance_service,
    usage_period,
)

PARENT = "parent-344"

# Taken at import, before any test's fixture replaces them with stand-ins.
_RESOLVE = entitlement_service.resolve_student_entitlement
_GET_USER = user_repo.get_user


def _day(offset: int) -> str:
    return (usage_period.zurich_today() + timedelta(days=offset)).isoformat()


def _profile(table: FakeTable, user_id: str, role: str, ends_on: str | None) -> None:
    item: dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": role,
        "account_status": "active",
        "email": f"{user_id}@example.ch",
        "subscription_tier": "student" if role == "student" else "free_trial",
        "version": 1,
    }
    if ends_on is not None:
        item[usage_period.PROFILE_FIELD] = ends_on
    table.put_item(Item=item)


@pytest.fixture
def real_eligibility(table, monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    """The question reads the student's real eligibility, period included, off `table`."""
    monkeypatch.setattr(entitlement_service, "resolve_student_entitlement", _RESOLVE)
    monkeypatch.setattr(user_repo, "get_user", _GET_USER)
    return table


def _usage_rows(table: FakeTable) -> list[dict[str, Any]]:
    """Today's message counter and its per-command marks."""
    return [row for (pk, _sk), row in table.rows.items() if pk.startswith("USAGE#")]


def _assert_refused_before_anything_is_stored(
    response, table: FakeTable, model, key: str
) -> None:
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "usage_period_ended"
    assert model.calls == [] and model.counted == 0
    assert _messages(table, "student") == []
    assert tuple(_command_key(CONV, key).values()) not in table.rows
    # Today's message was not counted against the daily limit.
    assert _usage_rows(table) == []


# ── The rule ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("state", "allowed"),
    [
        (usage_period.PeriodState.ACTIVE, True),
        (usage_period.PeriodState.EXPIRED, False),
        (usage_period.PeriodState.NONE, False),
    ],
)
def test_only_an_active_period_lets_a_student_ask(state, allowed) -> None:
    period = usage_period.EffectivePeriod(None, state, None)

    assert usage_period.allows_new_usage(period) is allowed


def test_the_end_day_itself_still_admits(fake_table) -> None:
    _profile(fake_table, STUDENT, "student", _day(0))

    entitlement = _RESOLVE(STUDENT, settings=Settings())

    assert entitlement["usagePeriod"]["state"] == "active"
    assert entitlement["newUsageAllowed"] is True


# ── A question ───────────────────────────────────────────────────────────────


def test_an_expired_student_is_refused_before_anything_is_stored(
    real_eligibility, model
) -> None:
    _profile(real_eligibility, STUDENT, "student", _day(-1))

    refused = _send(_client(), "after-the-end")

    _assert_refused_before_anything_is_stored(refused, real_eligibility, model, "after-the-end")


def test_a_student_with_no_period_is_refused(real_eligibility, model) -> None:
    _profile(real_eligibility, STUDENT, "student", None)

    refused = _send(_client(), "never-set")

    _assert_refused_before_anything_is_stored(refused, real_eligibility, model, "never-set")


def test_a_student_whose_own_period_runs_may_ask(real_eligibility, model) -> None:
    _profile(real_eligibility, STUDENT, "student", _day(30))

    answered = _send(_client(), "within-the-period")

    assert answered.status_code == 200, answered.text
    assert len(model.calls) == 1


def test_a_child_whose_parent_pays_may_ask(real_eligibility, model) -> None:
    _profile(real_eligibility, STUDENT, "student", None)
    _profile(real_eligibility, PARENT, "parent", _day(30))
    LinkRows(real_eligibility).link(PARENT, STUDENT)

    answered = _send(_client(), "parent-pays")

    assert answered.status_code == 200, answered.text
    assert len(model.calls) == 1


def test_revoking_the_relationship_refuses_the_child_at_once(
    real_eligibility, model
) -> None:
    _profile(real_eligibility, STUDENT, "student", _day(-3))
    _profile(real_eligibility, PARENT, "parent", _day(30))
    links = LinkRows(real_eligibility)
    links.link(PARENT, STUDENT)
    client = _client()
    assert _send(client, "while-linked").status_code == 200

    links.set_status(PARENT, STUDENT, parent_link_repo.STATUS_REJECTED)
    refused = _send(client, "after-revocation")

    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["code"] == "usage_period_ended"
    assert len(model.calls) == 1
    assert tuple(_command_key(CONV, "after-revocation").values()) not in real_eligibility.rows


def test_a_question_claimed_before_the_end_is_still_answered(
    real_eligibility, model
) -> None:
    """Decision 8: the worker does not admit again, so the answer is finished."""
    _profile(real_eligibility, STUDENT, "student", _day(0))
    _commit("claimed-in-time")

    _profile(real_eligibility, STUDENT, "student", _day(-1))
    _deliver("claimed-in-time")

    assert len(model.calls) == 1
    assert len(_messages(real_eligibility, "assistant")) == 1


def test_a_replay_of_an_answered_question_is_not_refused(real_eligibility, model) -> None:
    _profile(real_eligibility, STUDENT, "student", _day(0))
    client = _client()
    assert _send(client, "asked-in-time").status_code == 200

    _profile(real_eligibility, STUDENT, "student", _day(-1))
    replay = _send(client, "asked-in-time")

    assert replay.status_code == 200, replay.text
    assert len(model.calls) == 1


def test_a_new_conversations_first_question_is_refused_naming_it(
    real_eligibility, model
) -> None:
    _profile(real_eligibility, STUDENT, "student", _day(-1))

    refused = _client().post(
        "/conversations",
        json={"subject": "Mathematik", "grade": "Grade 6", "initialMessage": "Wie rechne ich?"},
    )

    assert refused.status_code == 403, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "usage_period_ended"
    assert detail["conversationId"]
    assert model.calls == []


# ── A request for a human teacher ────────────────────────────────────────────


@pytest.fixture
def help_table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    table = FakeTable()
    table.seed_active_account(STUDENT)
    seed_conversation(table, conversation_id=CONV, student_id=STUDENT)
    db_table.install(table)
    monkeypatch.setattr(
        learning_session,
        "read",
        lambda conv_id: dict(table.rows[(f"CONV#{conv_id}", "CONV")]),
    )
    return table


@pytest.fixture
def admissions(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Each case the weekly allowance was asked to admit; every one is admitted."""
    asked: list[str] = []
    service = teacher_support_allowance_service

    def admit(*, support_case_id, persist_case, **_kwargs):
        asked.append(support_case_id)
        persist_case((), {})
        return service.TeacherSupportAdmissionResult(
            service.TeacherSupportAdmissionDisposition.ADMITTED
        )

    monkeypatch.setattr(service, "admit_teacher_support_case", admit)
    monkeypatch.setattr(help_requests, "dispatch", lambda record, **_kwargs: dict(record))
    return asked


def _help_client() -> TestClient:
    app = FastAPI()
    app.include_router(conversations.teacher_help_router, prefix="/teacher-help")
    app.dependency_overrides[get_actor] = lambda: Actor(
        STUDENT,
        "https://identity.test",
        f"{STUDENT}-subject",
        CanonicalRole.STUDENT,
        AccountStatus.ACTIVE,
        CanonicalRole.STUDENT.value,
        (),
    )
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app, raise_server_exceptions=False)


def _ask_teacher() -> Any:
    return _help_client().post(
        "/teacher-help/request", json={"conversationId": CONV, "message": "Hilfe bitte"}
    )


def test_an_expired_student_cannot_ask_a_teacher_and_spends_no_case(
    help_table, admissions
) -> None:
    _profile(help_table, STUDENT, "student", _day(-1))

    refused = _ask_teacher()

    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["code"] == "usage_period_ended"
    assert admissions == []
    assert help_requests.get(CONV, table=help_table) is None


def test_a_student_with_no_period_cannot_ask_a_teacher(help_table, admissions) -> None:
    _profile(help_table, STUDENT, "student", None)

    refused = _ask_teacher()

    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["code"] == "usage_period_ended"
    assert admissions == []


def test_a_student_whose_parent_pays_reaches_the_weekly_allowance(
    help_table, admissions
) -> None:
    _profile(help_table, STUDENT, "student", None)
    _profile(help_table, PARENT, "parent", _day(10))
    LinkRows(help_table).link(PARENT, STUDENT)

    outcome = help_requests.ask(
        conversation={"conversation_id": CONV, "student_id": STUDENT},
        student_id=STUDENT,
        message=None,
        system_message="Eine Lehrperson wurde gefragt.",
        table=help_table,
    )

    assert admissions == [CONV]
    assert outcome.created is True


def test_a_request_asked_before_the_end_is_still_answered_with(
    help_table, admissions
) -> None:
    """Not a new request: the conversation's existing one comes back."""
    _profile(help_table, STUDENT, "student", _day(0))
    first = help_requests.ask(
        conversation={"conversation_id": CONV, "student_id": STUDENT},
        student_id=STUDENT,
        message=None,
        system_message="Eine Lehrperson wurde gefragt.",
        table=help_table,
    )
    assert first.created is True

    _profile(help_table, STUDENT, "student", _day(-1))
    again = help_requests.ask(
        conversation={"conversation_id": CONV, "student_id": STUDENT},
        student_id=STUDENT,
        message=None,
        system_message="Eine Lehrperson wurde gefragt.",
        table=help_table,
    )

    assert again.record is not None and again.created is False
    assert admissions == [CONV]


def test_the_period_is_read_once_per_request(help_table, admissions, monkeypatch) -> None:
    _profile(help_table, STUDENT, "student", _day(5))
    reads: list[str] = []
    judge = usage_period.effective_for_student

    def counting(student_id, **kwargs):
        reads.append(student_id)
        return judge(student_id, **kwargs)

    monkeypatch.setattr(usage_period, "effective_for_student", counting)

    assert _ask_teacher().status_code == 200
    assert reads == [STUDENT]

