"""The dispatch reminder and the weekly report are a channel of the notification package (#687).

The caller only says what happened: an offer went to a teacher
(`HelpOffered`), a report is ready for its parent (`WeeklyReportReady`, told
by `report_service.tell_report_ready`). The package reads the reader's switch,
adds the unsubscribe line and headers, and sends once, through the same
only-once ledger as realtime and push, under the happening's fixed id.

Held here, over the shared table double with the real ledger:

- **The same email.** What SES is sent - sender, recipient, Reply-To,
  subject, HTML and text body, unsubscribe line and headers - is byte for
  byte what the code before #687 sent, in all four languages
  (`fixtures/notification_emails_before_687.json`, captured from main
  `7bb4d897` with the same settings and inputs).
- **Once.** A happening told again sends nothing, also when SES accepted the
  email and the ledger never recorded it; an operator's resend is a happening
  of its own and sends again, a retry of that resend does not.
- **The switch.** A teacher who switched the reminder off still gets the
  bell; a parent who unsubscribed gets no email and the report says so.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fakes.dynamodb import FakeTable

from stoa import aws, config
from stoa.aws import Kind
from stoa.config import DEVELOPMENT_AUDIT_KEY, Settings
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, notification_repo
from stoa.services import notifications, report_recovery_service, report_service
from stoa.services.notifications import _email, _ledger
from stoa.services.report_recovery_errors import ReportRecoveryError

BEFORE = json.loads(
    (Path(__file__).parent / "fixtures" / "notification_emails_before_687.json").read_text(
        encoding="utf-8"
    )
)
LOCALES = ["de", "en", "fr", "it"]
TEACHER = "teacher-687"
PARENT = "parent-687"
STUDENT = "student-687"
GENERATION = 3
REPORT_ID = "weekly-report-parent-687-student-687-2026-11-16"
REPORT_HTML = (
    "<html><body><h1>Wochenbericht für Mia</h1>"
    "<p>Brüche &amp; Dezimalzahlen – très bien.</p></body></html>"
)


class RecordingSes:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send_email(self, **kwargs: Any) -> dict[str, Any]:
        self.sent.append(kwargs)
        return {"MessageId": f"ses-{len(self.sent)}"}


def install_world(*, locale: str = "de", table: FakeTable | None = None) -> tuple[FakeTable, RecordingSes]:
    """A teacher, a parent and a student in `locale`, the student's account fence, and SES.

    The settings are the ones the snapshot of the emails before #687 was taken with.
    """
    double = table or FakeTable()
    double.seed(
        *(
            {
                **account_deletion_repo.account_fence_key(user_id),
                "entity_type": "account_fence",
                "status": "active",
                "generation": GENERATION,
            }
            for user_id in (STUDENT, TEACHER, PARENT)
        ),
        {"PK": f"USER#{TEACHER}", "SK": "PROFILE", "user_id": TEACHER, "role": "teacher",
         "preferred_locale": locale, "email": "teacher@stoa.test"},
        {"PK": f"USER#{PARENT}", "SK": "PROFILE", "user_id": PARENT, "role": "parent",
         "preferred_locale": locale, "email": "parent@stoa.test"},
    )
    db_table.install(double)
    ses = RecordingSes()
    aws.install({Kind.SES_DISPATCH_REMINDER: ses, Kind.SES_NOTIFICATION: ses})
    config.install(
        Settings(
            _env_file=None,
            environment="test",
            app_base_url="https://app.stoaedu.ch",
            api_base_url="https://api.stoaedu.ch",
            notification_email_sender="noreply@stoaedu.ch",
            notification_email_reply_to="info@stoaedu.ch",
            authorization_audit_active_key_id="development-v1",
            authorization_audit_active_key=DEVELOPMENT_AUDIT_KEY,
            authorization_audit_previous_keys={},
            stoa_enable_best_effort_notifications=True,
        )
    )
    return double, ses


@pytest.fixture
def world() -> Iterator[tuple[FakeTable, RecordingSes]]:
    try:
        yield install_world()
    finally:
        aws.install(None)


def offer(*, dispatch_id: str = "dispatch-687", standing: bool = False) -> None:
    notifications.happened(
        notifications.HelpOffered(
            conversation={
                "conversation_id": "conversation-687",
                "student_id": STUDENT,
                "escalation_request_id": "req-687",
                "subject": "math",
                "account_fence_generation": GENERATION,
            },
            teacher_id=TEACHER,
            dispatch_id=dispatch_id,
            deadline_at="2026-11-28T10:10:00+00:00",
            accept_minutes=10,
            standing=standing,
        )
    )


def report_ready(*, student_name: str = "Mia", locale: str = "de", resend: int = 0) -> notifications.EmailResult:
    return report_service.tell_report_ready(
        {
            "report_id": REPORT_ID,
            "parent_id": PARENT,
            "student_id": STUDENT,
            "student_name": student_name,
        },
        parent_email="parent@stoa.test",
        generation=GENERATION,
        html=REPORT_HTML,
        locale=locale,
        resend=resend,
    )


def _intents(table: FakeTable) -> list[dict[str, Any]]:
    return [
        row
        for row in table.rows.values()
        if row.get("entity_type") == notification_repo.DELIVERY_INTENT_ENTITY
    ]


def _bell_rows(table: FakeTable) -> list[dict[str, Any]]:
    return [
        row
        for row in table.rows.values()
        if row.get("entity_type") == notification_repo.NOTIFICATION_ENTITY
    ]


# --- The same email as before, in four languages ---


@pytest.mark.parametrize("locale", LOCALES)
def test_the_dispatch_reminder_ses_gets_is_the_one_it_got_before(locale) -> None:
    try:
        _, ses = install_world(locale=locale)

        offer()

        assert ses.sent == [BEFORE["dispatch_reminder"][locale]]
    finally:
        aws.install(None)


@pytest.mark.parametrize("student_name", ["Mia", ""])
@pytest.mark.parametrize("locale", LOCALES)
def test_the_weekly_report_ses_gets_is_the_one_it_got_before(locale, student_name) -> None:
    try:
        _, ses = install_world(locale=locale)

        result = report_ready(student_name=student_name, locale=locale)

        assert result == notifications.EmailResult(notifications.EmailOutcome.SENT)
        assert ses.sent == [BEFORE["weekly_report"][f"{locale}:{student_name or '-'}"]]
    finally:
        aws.install(None)


# --- Once ---


def test_an_offer_told_twice_sends_one_reminder_under_its_fixed_id(world) -> None:
    table, ses = world

    offer()
    offer()

    assert len(ses.sent) == 1
    [intent] = _intents(table)
    assert intent["channel"] == "email"
    assert intent["operation_id"] == "email-teacher-help-dispatched-dispatch-687"
    assert intent["event_ids"] == ["teacher-help-dispatched-dispatch-687"]
    assert intent["status"] == "accepted"
    # The ledger row is the student's, as the bell row is: their deletion takes it.
    assert intent["owner_id"] == STUDENT
    assert "teacher@stoa.test" not in json.dumps(intent, default=str)


def test_a_reminder_sent_but_never_recorded_is_not_sent_again(world, monkeypatch) -> None:
    table, ses = world
    real_complete = notification_repo.complete_delivery_intent
    calls = {"n": 0}

    def lost_after_send(**kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("the table went away after SES accepted")
        return real_complete(**kwargs)

    monkeypatch.setattr(_ledger.notification_repo, "complete_delivery_intent", lost_after_send)

    offer()
    offer()

    assert len(ses.sent) == 1
    [intent] = _intents(table)
    assert intent["status"] == "provider_acceptance_unknown"


def test_another_offer_of_the_same_request_is_another_reminder(world) -> None:
    _, ses = world

    offer(dispatch_id="dispatch-687-a")
    offer(dispatch_id="dispatch-687-b")

    assert len(ses.sent) == 2


def test_a_weekly_report_told_again_sends_nothing_and_still_counts_as_sent(world) -> None:
    table, ses = world

    first = report_ready()
    again = report_ready()

    assert first == again == notifications.EmailResult(notifications.EmailOutcome.SENT)
    assert len(ses.sent) == 1
    [intent] = _intents(table)
    assert intent["channel"] == "email"
    assert intent["owner_id"] == STUDENT
    # The report id names both accounts; the ledger keeps only its digest.
    assert PARENT not in json.dumps(intent, default=str)
    assert intent["operation_id"].startswith("email-weekly-report-")


def test_a_weekly_report_sent_but_never_recorded_is_not_sent_again(world, monkeypatch) -> None:
    _, ses = world
    real_complete = notification_repo.complete_delivery_intent
    calls = {"n": 0}

    def lost_after_send(**kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("the table went away after SES accepted")
        return real_complete(**kwargs)

    monkeypatch.setattr(_ledger.notification_repo, "complete_delivery_intent", lost_after_send)

    first = report_ready()
    again = report_ready()

    assert len(ses.sent) == 1
    assert first.outcome is again.outcome is notifications.EmailOutcome.FAILED
    assert str(again.error) == "provider_acceptance_unknown"


def test_each_operator_resend_is_its_own_email_and_a_retry_of_one_is_not(world) -> None:
    table, ses = world

    report_ready()
    report_ready(resend=1)
    report_ready(resend=1)
    report_ready(resend=2)

    assert len(ses.sent) == 3
    operations = sorted(intent["operation_id"] for intent in _intents(table))
    assert [op.rsplit("-resend-", 1)[-1] for op in operations if "-resend-" in op] == ["1", "2"]


def test_a_report_whose_student_account_is_gone_is_not_sent(world) -> None:
    table, ses = world
    table.seed(
        {
            **account_deletion_repo.account_fence_key(STUDENT),
            "entity_type": "account_fence",
            "status": "deleting",
            "generation": GENERATION,
        }
    )

    result = report_ready()

    assert result.outcome is notifications.EmailOutcome.FAILED
    assert ses.sent == []


# --- The operator's resend, through the recovery service ---


@pytest.fixture
def recovery(world, monkeypatch) -> dict[str, list]:
    recorded: dict[str, list] = {"updates": [], "audits": []}
    monkeypatch.setattr(
        report_recovery_service.current_relationship,
        "current_parent_recipient",
        lambda *_a: report_recovery_service.current_relationship.ParentRecipient(
            email="parent@stoa.test"
        ),
    )
    monkeypatch.setattr(
        report_recovery_service.report_artifact_service, "get_report_html", lambda _key: REPORT_HTML
    )
    monkeypatch.setattr(
        report_recovery_service.report_repo,
        "update_report_status",
        lambda report_id, status, **fields: recorded["updates"].append((status, fields)),
    )
    monkeypatch.setattr(
        report_recovery_service.report_repo,
        "put_report_audit_event",
        lambda *a, **_k: recorded["audits"].append(a),
    )
    return recorded


def _failed_report(**fields: Any) -> dict[str, Any]:
    return {
        "report_id": REPORT_ID,
        "parent_id": PARENT,
        "student_id": STUDENT,
        "student_name": "Mia",
        "week_start": "2026-11-16",
        "status": "email_failed",
        "email_status": "failed",
        "html_s3_key": "weekly-reports/private/report.html",
        **fields,
    }


def test_a_resend_whose_outcome_was_never_written_is_the_same_resend(world, recovery) -> None:
    _, ses = world
    report_ready()  # the weekly job's email, whatever became of it

    # The operator resends; the email goes out, but the report never hears of it.
    report_recovery_service.resend_report_email(_failed_report(), operator="admin-1")
    # So it still reads as failed, with no resend recorded, and is resent.
    result = report_recovery_service.resend_report_email(_failed_report(), operator="admin-1")

    assert len(ses.sent) == 2  # the weekly one and resend 1, once
    assert result.email_status == "sent"
    assert [fields["email_resends"] for _status, fields in recovery["updates"]] == [1, 1]


def test_the_next_resend_after_a_recorded_one_sends_again(world, recovery) -> None:
    _, ses = world

    report_recovery_service.resend_report_email(_failed_report(), operator="admin-1")
    report_recovery_service.resend_report_email(
        _failed_report(email_resends=1), operator="admin-1"
    )

    assert len(ses.sent) == 2
    assert [fields["email_resends"] for _status, fields in recovery["updates"]] == [1, 2]


def test_a_resend_to_a_parent_who_unsubscribed_is_refused_and_sends_nothing(world, recovery) -> None:
    _, ses = world
    notifications.update_preferences(PARENT, None, weekly_report_email=False)

    with pytest.raises(ReportRecoveryError) as refused:
        report_recovery_service.resend_report_email(_failed_report(), operator="admin-1")

    assert refused.value.code == "report_recipient_unsubscribed"
    assert ses.sent == []
    assert recovery["updates"] == []


# --- The switch ---


def test_a_teacher_who_switched_the_reminder_off_still_gets_the_bell(world) -> None:
    table, ses = world
    notifications.update_preferences(TEACHER, None, dispatch_email=False)

    offer()

    assert ses.sent == []
    assert [row["event_id"] for row in _bell_rows(table)] == ["teacher-help-dispatched-dispatch-687"]
    assert _intents(table) == []


def test_a_standing_offer_sends_no_second_reminder(world) -> None:
    _, ses = world

    offer(standing=True)

    assert ses.sent == []


def test_a_parent_who_unsubscribed_gets_no_report_email(world) -> None:
    table, ses = world
    notifications.update_preferences(PARENT, None, weekly_report_email=False)

    result = report_ready()

    assert result == notifications.EmailResult(notifications.EmailOutcome.UNSUBSCRIBED)
    assert ses.sent == []
    assert _intents(table) == []


def test_a_weekly_report_has_no_bell_row(world) -> None:
    table, _ = world

    report_ready()

    assert _bell_rows(table) == []


def test_the_email_operation_is_the_happenings_fixed_id_as_email() -> None:
    assert _email.operation_id("teacher-help-dispatched-d-1") == "email-teacher-help-dispatched-d-1"
    first = notifications.WeeklyReportReady(
        report_id=REPORT_ID, parent_id=PARENT, parent_email="p@stoa.test", student_id=STUDENT,
        generation=GENERATION, subject="s", html="<p>h</p>",
    )
    again = notifications.WeeklyReportReady(
        report_id=REPORT_ID, parent_id=PARENT, parent_email="new@stoa.test", student_id=STUDENT,
        generation=GENERATION, subject="other", html="<p>rendered again</p>",
    )
    resent = notifications.WeeklyReportReady(
        report_id=REPORT_ID, parent_id=PARENT, parent_email="p@stoa.test", student_id=STUDENT,
        generation=GENERATION, subject="s", html="<p>h</p>", resend=2,
    )
    assert first.event_id == again.event_id
    assert resent.event_id == f"{first.event_id}-resend-2"
    with pytest.raises(ValueError):
        notifications.WeeklyReportReady(
            report_id=REPORT_ID, parent_id=PARENT, parent_email="p@stoa.test", student_id=STUDENT,
            generation=GENERATION, subject="s", html="<p>h</p>", resend=-1,
        )
