"""The teacher a chat help request is offered to hears about it (#141).

Dispatch offered a request to a teacher and told nobody: a teacher who was not
looking at the queue let every 10-minute offer lapse. Each offer - the first
one and every re-offer - now leaves the offered teacher a bell notification,
which they cannot switch off, and a reminder email, which they can. The email
names the subject and links into STOA; nothing the student wrote, sent or is
called leaves STOA with it. A failed send is logged and the offer stands.

Seam ③ of #133: the student's request route and the scheduled sweep go in, the
notification store (read back through the teacher's own bell) and the SES
client come out. The request record (#189), dispatch and routes are the real
ones over the shared table double, as in test_chat_help_request_lifecycle.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fakes.dynamodb import FakeTable
import pytest

from actor_helpers import install_actor_overrides
from stoa.jobs import dispatch_reconciler
from stoa.services import notify_service

import test_chat_help_request_lifecycle as lifecycle
from test_chat_help_request_lifecycle import (
    CONV,
    HELP_KEY,
    OTHER_TEACHER,
    STUDENT,
    TEACHER,
)

QUESTION_TEXT = "Step 2 makes no sense to me."
CONVERSATION_TITLE = "Fractions"
STUDENT_NAME = "Mia Muster"
TEACHER_EMAIL = "teacher-66@stoa.test"
OTHER_TEACHER_EMAIL = "teacher-66-other@stoa.test"


class RecordingSes:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.failure: Exception | None = None
        self.built_with: list[dict[str, Any]] = []

    def send_email(self, **kwargs: Any) -> dict[str, Any]:
        if self.failure is not None:
            raise self.failure
        self.sent.append(kwargs)
        return {"MessageId": f"ses-{len(self.sent)}"}

    def to(self, address: str) -> list[dict[str, Any]]:
        return [mail for mail in self.sent if mail["Destination"]["ToAddresses"] == [address]]


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    built = lifecycle.build_table(monkeypatch)
    lifecycle.keep_waiting(monkeypatch)
    monkeypatch.setenv("STOA_ENABLE_BEST_EFFORT_NOTIFICATIONS", "true")
    built.rows[(f"USER#{TEACHER}", "PROFILE")]["email"] = TEACHER_EMAIL
    built.rows[(f"USER#{OTHER_TEACHER}", "PROFILE")]["email"] = OTHER_TEACHER_EMAIL
    built.rows[(f"USER#{STUDENT}", "PROFILE")]["full_name"] = STUDENT_NAME
    # Not yet asked for: the student's request below is what asks.
    del built.rows[HELP_KEY]
    return built


@pytest.fixture
def ses(monkeypatch: pytest.MonkeyPatch) -> RecordingSes:
    client = RecordingSes()

    def build(*_args: Any, **kwargs: Any) -> RecordingSes:
        client.built_with.append(kwargs)
        return client

    monkeypatch.setattr(notify_service.boto3, "client", build)
    return client


@pytest.fixture(autouse=True)
def admission(monkeypatch: pytest.MonkeyPatch) -> None:
    """What the request route needs besides the table: no paid grant, no usage meter."""
    from stoa.routers import conversations
    from stoa.services import teacher_support_allowance_service as allowance

    monkeypatch.setattr(
        allowance.paid_entitlement_service,
        "get_active_beneficiary_grant",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        conversations.usage_ledger_service,
        "record_usage_event",
        lambda **_kwargs: {"idempotency_status": "created"},
    )


def _on_duty(table: FakeTable, *teachers: str) -> None:
    for teacher in (TEACHER, OTHER_TEACHER):
        table.rows[(f"USER#{teacher}", "PROFILE")]["dispatch_availability"] = (
            "available" if teacher in teachers else "paused"
        )


def _speaks(table: FakeTable, teacher: str, locale: str) -> None:
    table.rows[(f"USER#{teacher}", "PROFILE")]["preferred_locale"] = locale


def _student() -> TestClient:
    from stoa.routers import conversations
    from stoa.security.route_authorization import get_authorization_fact_repository

    app = FastAPI()
    app.include_router(conversations.teacher_help_router, prefix="/teacher-help")
    install_actor_overrides(app, {"sub": STUDENT, "role": "student"})
    app.dependency_overrides.pop(get_authorization_fact_repository, None)
    return TestClient(app)


def _teacher(teacher_id: str = TEACHER) -> TestClient:
    from stoa.routers import notifications

    app = FastAPI()
    app.include_router(notifications.router, prefix="/notifications")
    install_actor_overrides(app, {"sub": teacher_id, "role": "teacher"})
    return TestClient(app)


def _ask_for_a_teacher() -> dict[str, Any]:
    response = _student().post(
        "/teacher-help/request", json={"conversationId": CONV, "message": QUESTION_TEXT}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _offers(teacher_id: str) -> list[dict[str, Any]]:
    response = _teacher(teacher_id).get("/notifications")
    assert response.status_code == 200, response.text
    return [
        item for item in response.json()["items"] if item["eventType"] == "teacher_help_dispatched"
    ]


def _lapse_the_offer(table: FakeTable) -> None:
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0).isoformat()
    table.rows[HELP_KEY]["dispatch_deadline_at"] = past


def _sweep() -> dict[str, Any]:
    return dispatch_reconciler.handler({}, None)


def _body(mail: dict[str, Any]) -> str:
    return mail["Message"]["Body"]["Html"]["Data"]


def _subject_line(mail: dict[str, Any]) -> str:
    return mail["Message"]["Subject"]["Data"]


# --- Each offer reaches the offered teacher ---


def test_the_first_offer_leaves_the_teacher_one_notification_and_one_email(table, ses) -> None:
    _on_duty(table, TEACHER)

    help_request = _ask_for_a_teacher()

    assert help_request["status"] == "assigned"
    offers = _offers(TEACHER)
    assert len(offers) == 1
    assert offers[0]["targetType"] == "question"
    assert offers[0]["targetId"] == help_request["requestId"]
    assert offers[0]["status"] == "created"
    assert offers[0]["metadata"]["deadline_at"] == table.rows[HELP_KEY]["dispatch_deadline_at"]
    assert len(ses.sent) == 1
    assert ses.to(TEACHER_EMAIL) == ses.sent
    assert _offers(OTHER_TEACHER) == []


def test_a_re_offer_leaves_the_next_teacher_one_notification_and_one_email(table, ses) -> None:
    _on_duty(table, TEACHER)
    _ask_for_a_teacher()
    _on_duty(table, TEACHER, OTHER_TEACHER)
    _lapse_the_offer(table)

    outcome = _sweep()

    assert outcome["conversationsDispatched"] == 1
    assert table.rows[HELP_KEY]["dispatched_teacher_id"] == OTHER_TEACHER
    assert len(_offers(OTHER_TEACHER)) == 1
    assert len(ses.to(OTHER_TEACHER_EMAIL)) == 1
    # The teacher who let it lapse heard once, for their own offer.
    assert len(_offers(TEACHER)) == 1
    assert len(ses.to(TEACHER_EMAIL)) == 1


def test_a_sweep_that_finds_the_offer_still_live_tells_nobody_again(table, ses) -> None:
    _on_duty(table, TEACHER, OTHER_TEACHER)
    _ask_for_a_teacher()

    _sweep()

    assert len(_offers(TEACHER)) + len(_offers(OTHER_TEACHER)) == 1
    assert len(ses.sent) == 1


# --- What leaves STOA ---


def test_the_email_carries_the_subject_and_a_link_but_nothing_of_the_student(table, ses) -> None:
    _on_duty(table, TEACHER)

    help_request = _ask_for_a_teacher()

    [mail] = ses.sent
    text = _subject_line(mail) + _body(mail)
    assert "Mathematik" in text
    link = f"/teacher/requests/{help_request['requestId']}"
    assert link in _body(mail)
    # A request's id is its conversation's (#189), so the link is the one
    # place that id appears; nothing else of the conversation leaves.
    assert help_request["requestId"] == CONV
    text = text.replace(link, "")
    for private in (QUESTION_TEXT, CONVERSATION_TITLE, STUDENT_NAME, STUDENT, CONV):
        assert private not in text


# --- The teacher's switch ---


def test_the_dispatch_email_is_on_until_the_teacher_switches_it_off(table, ses) -> None:
    teacher = _teacher()

    assert teacher.get("/notifications/preferences").json()["dispatchEmail"] is True
    switched = teacher.patch("/notifications/preferences", json={"dispatchEmail": False})

    assert switched.status_code == 200, switched.text
    assert switched.json()["dispatchEmail"] is False
    assert teacher.get("/notifications/preferences").json()["dispatchEmail"] is False


def test_changing_other_preferences_keeps_the_dispatch_email_switch(table, ses) -> None:
    teacher = _teacher()
    assert teacher.patch("/notifications/preferences", json={"dispatchEmail": False}).status_code == 200

    changed = teacher.patch(
        "/notifications/preferences",
        json={"preferences": {"teacher_responses": {"realtime": False}}},
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["dispatchEmail"] is False
    assert changed.json()["preferences"]["teacher_responses"]["realtime"] is False


def test_with_the_email_switched_off_only_the_notification_remains(table, ses) -> None:
    _on_duty(table, TEACHER)
    assert _teacher().patch("/notifications/preferences", json={"dispatchEmail": False}).status_code == 200

    _ask_for_a_teacher()

    assert len(_offers(TEACHER)) == 1
    assert ses.sent == []


def test_the_notification_cannot_be_switched_off(table, ses) -> None:
    _on_duty(table, TEACHER)
    switched = _teacher().patch(
        "/notifications/preferences",
        json={
            "preferences": {
                category: {"in_app": False}
                for category in _teacher().get("/notifications/preferences").json()[
                    "supportedCategories"
                ]
            }
        },
    )
    assert switched.status_code == 200, switched.text

    _ask_for_a_teacher()

    [offer] = _offers(TEACHER)
    assert offer["status"] == "created"


# --- A failed send ---


def test_a_failed_send_is_logged_and_the_offer_stands(table, ses, caplog) -> None:
    _on_duty(table, TEACHER)
    ses.failure = RuntimeError("SES is down")

    with caplog.at_level(logging.WARNING):
        help_request = _ask_for_a_teacher()

    assert help_request["status"] == "assigned"
    assert table.rows[HELP_KEY]["dispatched_teacher_id"] == TEACHER
    assert table.rows[HELP_KEY]["dispatch_status"] == "dispatched"
    assert len(_offers(TEACHER)) == 1
    assert any("dispatch_reminder_email_failed" in record.getMessage() for record in caplog.records)


def test_a_failed_send_on_a_re_offer_still_re_offers(table, ses) -> None:
    _on_duty(table, TEACHER)
    _ask_for_a_teacher()
    _on_duty(table, TEACHER, OTHER_TEACHER)
    _lapse_the_offer(table)
    ses.failure = RuntimeError("SES is down")

    outcome = _sweep()

    assert outcome["conversationsDispatched"] == 1
    assert table.rows[HELP_KEY]["dispatched_teacher_id"] == OTHER_TEACHER
    assert len(_offers(OTHER_TEACHER)) == 1


def test_the_email_gives_up_well_inside_the_students_request(table, ses) -> None:
    # The first offer is sent from the student's own request, which API
    # Gateway cuts off at 29 seconds; boto3's defaults wait 60 s per read and retry.
    _on_duty(table, TEACHER)

    _ask_for_a_teacher()

    [built] = ses.built_with
    config = built["config"]
    assert config.connect_timeout <= 2
    assert config.read_timeout <= 3
    assert config.retries["max_attempts"] == 1


def test_a_subject_the_catalog_cannot_name_still_dispatches(table, ses, monkeypatch, caplog) -> None:
    # A subject added to the taxonomy before its catalog line: naming it raises.
    from stoa.services import message_catalog

    monkeypatch.delitem(message_catalog.TEXT, "subject.math")
    _on_duty(table, TEACHER)

    with caplog.at_level(logging.WARNING):
        help_request = _ask_for_a_teacher()

    assert help_request["status"] == "assigned"
    assert table.rows[HELP_KEY]["dispatched_teacher_id"] == TEACHER
    assert any("dispatch_teacher_alert_failed" in record.getMessage() for record in caplog.records)

    _on_duty(table, TEACHER, OTHER_TEACHER)
    _lapse_the_offer(table)
    outcome = _sweep()

    assert outcome["conversationSweep"] == "completed"
    assert outcome["conversationsDispatched"] == 1
    assert table.rows[HELP_KEY]["dispatched_teacher_id"] == OTHER_TEACHER


# --- In the teacher's language ---


@pytest.mark.parametrize(
    ("locale", "subject_line", "subject_name"),
    [
        ("de", "STOA – Neue Hilfeanfrage: bitte innerhalb von 10 Minuten annehmen", "Mathematik"),
        ("en", "STOA – New help request: please accept within 10 minutes", "Mathematics"),
        ("fr", "STOA – Nouvelle demande d'aide : à accepter dans les 10 minutes", "Mathématiques"),
        ("it", "STOA – Nuova richiesta di aiuto: da accettare entro 10 minuti", "Matematica"),
    ],
)
def test_the_email_and_notification_are_in_the_teachers_language(
    table, ses, locale: str, subject_line: str, subject_name: str
) -> None:
    _on_duty(table, TEACHER)
    _speaks(table, TEACHER, locale)

    _ask_for_a_teacher()

    [mail] = ses.sent
    assert _subject_line(mail) == subject_line
    assert subject_name in _body(mail)
    [offer] = _offers(TEACHER)
    assert subject_name in offer["summary"]


def test_a_teacher_without_a_language_is_written_to_in_the_default_one(table, ses) -> None:
    _on_duty(table, TEACHER)

    _ask_for_a_teacher()

    [mail] = ses.sent
    assert _subject_line(mail).startswith("STOA – Neue Hilfeanfrage")
