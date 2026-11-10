"""Notification emails carry an unsubscribe link and RFC 8058 headers (#363).

Three kinds of email recur or notify and can be stopped from the email itself:
the parent's weekly report, the teacher's dispatch reminder and the notification
digest. Each carries a link in the reader's language and the `List-Unsubscribe`
headers. The link holds a signed token bound to one recipient and one kind of
email; following it switches off the existing preference for that kind, without
signing in. A tampered token, one for another kind, or one signed with a key we
do not hold are all refused with the same answer. The three one-off emails
(activation, teacher activation, password code) carry neither.

Seams: the public routes go in over the notification store double; the SES client
comes out. The weekly report goes in at `store_and_send_weekly_report`.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa import aws, config
from stoa.aws import Kind
from stoa.routers import notifications
from stoa.services import email_unsubscribe, notification_service, notify_service
from stoa.services.email_unsubscribe import EmailKind

import test_notifications

PARENT = "parent-363"
TEACHER = "teacher-363"
STUDENT = "student-363"


class RecordingSes:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send_email(self, **kwargs: Any) -> dict[str, Any]:
        self.sent.append(kwargs)
        return {"MessageId": f"ses-{len(self.sent)}"}


def _html(mail: dict[str, Any]) -> str:
    if "Content" in mail:
        return mail["Content"]["Simple"]["Body"]["Html"]["Data"]
    return mail["Message"]["Body"]["Html"]["Data"]


def _headers(mail: dict[str, Any]) -> dict[str, str]:
    simple = mail.get("Content", {}).get("Simple", {})
    return {header["Name"]: header["Value"] for header in simple.get("Headers", [])}


def _footer_token(html: str) -> str:
    [href] = re.findall(r'href="([^"]*/unsubscribe\?token=[^"]*)"', html)
    return unquote(parse_qs(urlparse(href.replace("&amp;", "&")).query)["token"][0])


def _header_token(mail: dict[str, Any]) -> str:
    value = _headers(mail)["List-Unsubscribe"]
    assert value.startswith("<https://") and value.endswith(">")
    return unquote(parse_qs(urlparse(value[1:-1]).query)["token"][0])


def _public_client() -> TestClient:
    app = FastAPI()
    app.include_router(notifications.router, prefix="/notifications")
    return TestClient(app)


@pytest.fixture
def preferences(monkeypatch) -> dict[str, dict]:
    _, stored = test_notifications._install_notification_repo(monkeypatch)
    return stored


# --- The token ---


def test_a_token_names_its_recipient_and_kind_and_not_their_address() -> None:
    token = email_unsubscribe.issue_token(PARENT, EmailKind.WEEKLY_REPORT)

    target = email_unsubscribe.read_token(token)

    assert (target.user_id, target.kind) == (PARENT, EmailKind.WEEKLY_REPORT)
    assert "@" not in token
    assert email_unsubscribe.issue_token(PARENT, EmailKind.WEEKLY_REPORT) == token


def _payload(token: str) -> dict[str, Any]:
    body = token.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def _repack(token: str, **changes: Any) -> str:
    body, signature = token.split(".")
    payload = {**_payload(token), **changes}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode() + "." + signature


def _refused(token: str) -> tuple[int, dict]:
    response = _public_client().post(
        "/notifications/email-unsubscribe", params={"token": token}
    )
    return response.status_code, response.json()


def test_a_tampered_token_another_kind_and_a_foreign_key_are_refused_alike(
    preferences, monkeypatch
) -> None:
    good = email_unsubscribe.issue_token(TEACHER, EmailKind.DISPATCH_REMINDER)
    another_person = _repack(good, u=PARENT)
    another_kind = _repack(good, c=EmailKind.WEEKLY_REPORT.value)
    unknown_kind = _repack(good, c="marketing")
    broken_signature = good[:-2] + ("AA" if not good.endswith("AA") else "BB")

    with monkeypatch.context() as scoped:
        scoped.setattr(
            email_unsubscribe, "_keyring", lambda: (("other-key", bytes(range(32))),)
        )
        foreign = email_unsubscribe.issue_token(TEACHER, EmailKind.DISPATCH_REMINDER)

    answers = [
        _refused(token)
        for token in (another_person, another_kind, unknown_kind, broken_signature, foreign, "x", "")
    ]

    assert {status for status, _ in answers} == {400}
    details = [
        {key: value for key, value in body["detail"].items() if key != "correlationId"}
        for _, body in answers
    ]
    assert len({json.dumps(detail, sort_keys=True) for detail in details}) == 1
    assert details[0]["code"] == "email_unsubscribe_link_invalid"
    assert preferences == {}


# --- Following the link switches the existing preference off ---


def test_unsubscribing_from_dispatch_reminders_switches_dispatch_email_off(preferences) -> None:
    token = email_unsubscribe.issue_token(TEACHER, EmailKind.DISPATCH_REMINDER)

    response = _public_client().post("/notifications/email-unsubscribe", params={"token": token})

    assert response.status_code == 200, response.text
    assert response.json() == {"kind": "dispatch_reminder", "subscribed": False}
    assert notification_service.dispatch_email_enabled(TEACHER) is False


def test_the_one_click_post_of_rfc_8058_unsubscribes(preferences) -> None:
    token = email_unsubscribe.issue_token(TEACHER, EmailKind.DISPATCH_REMINDER)

    response = _public_client().post(
        f"/notifications/email-unsubscribe?token={token}",
        content="List-Unsubscribe=One-Click",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200, response.text
    assert notification_service.dispatch_email_enabled(TEACHER) is False


def test_unsubscribing_from_the_digest_turns_the_email_digest_channel_off(preferences) -> None:
    prefs = notification_service.default_preferences()
    prefs["teacher_responses"]["email_digest"] = True
    prefs["assignments"]["email_digest"] = True
    preferences[STUDENT] = {"user_id": STUDENT, "preferences": prefs}
    token = email_unsubscribe.issue_token(STUDENT, EmailKind.NOTIFICATION_DIGEST)

    client = _public_client()
    assert client.post("/notifications/email-unsubscribe", params={"token": token}).status_code == 200

    stored = notification_service.get_preferences_for_user(STUDENT)
    assert not any(channels["email_digest"] for channels in stored.values())
    assert stored["teacher_responses"]["in_app"] is True

    # Undo puts back exactly the categories that were on, and no others.
    undone = client.post("/notifications/email-resubscribe", params={"token": token})
    assert undone.json() == {"kind": "notification_digest", "subscribed": True}
    restored = notification_service.get_preferences_for_user(STUDENT)
    assert {c for c, channels in restored.items() if channels["email_digest"]} == {
        "teacher_responses",
        "assignments",
    }


def test_the_weekly_report_switch_is_on_by_default_and_the_link_turns_it_off(preferences) -> None:
    assert notification_service.weekly_report_email_enabled(PARENT) is True
    assert notification_service.preferences_response(PARENT)["weeklyReportEmail"] is True
    token = email_unsubscribe.issue_token(PARENT, EmailKind.WEEKLY_REPORT)

    client = _public_client()
    assert client.post("/notifications/email-unsubscribe", params={"token": token}).status_code == 200
    assert notification_service.weekly_report_email_enabled(PARENT) is False

    assert client.post("/notifications/email-resubscribe", params={"token": token}).json() == {
        "kind": "weekly_report",
        "subscribed": True,
    }
    assert notification_service.weekly_report_email_enabled(PARENT) is True


def test_a_parent_can_switch_the_weekly_report_email_in_settings(preferences) -> None:
    from actor_helpers import install_actor_overrides

    app = FastAPI()
    app.include_router(notifications.router, prefix="/notifications")
    install_actor_overrides(app, {"sub": PARENT, "role": "parent"})
    client = TestClient(app)

    switched = client.patch("/notifications/preferences", json={"weeklyReportEmail": False})

    assert switched.status_code == 200, switched.text
    assert switched.json()["weeklyReportEmail"] is False
    # A client that only knows the matrix keeps the switch where it is.
    kept = client.patch(
        "/notifications/preferences",
        json={"preferences": {"teacher_responses": {"realtime": False}}},
    )
    assert kept.json()["weeklyReportEmail"] is False
    assert kept.json()["dispatchEmail"] is True


# --- The emails ---

FOOTER_WORDS = {
    "de": "abbestellen",
    "fr": "désabonner",
    "it": "Non ricevere più",
    "en": "Unsubscribe",
}


@pytest.mark.parametrize("locale", sorted(FOOTER_WORDS))
def test_the_dispatch_reminder_carries_the_link_and_headers_in_the_teachers_language(
    locale,
) -> None:
    ses = RecordingSes()
    aws.install({Kind.SES_DISPATCH_REMINDER: ses})

    notify_service.send_dispatch_reminder_email(
        "teacher@stoa.test",
        recipient_user_id=TEACHER,
        subject_name="Mathematik",
        request_id="req-1",
        minutes=10,
        locale=locale,
    )

    [mail] = ses.sent
    assert FOOTER_WORDS[locale] in _html(mail)
    assert email_unsubscribe.read_token(_footer_token(_html(mail))) == email_unsubscribe.UnsubscribeTarget(
        TEACHER, EmailKind.DISPATCH_REMINDER
    )
    assert _headers(mail)["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert email_unsubscribe.read_token(_header_token(mail)).kind is EmailKind.DISPATCH_REMINDER
    assert "teacher@stoa.test" not in _headers(mail)["List-Unsubscribe"]


def test_the_digest_carries_the_link_and_headers(preferences, monkeypatch) -> None:
    config.install(test_notifications._notification_provider_settings())
    prefs = notification_service.default_preferences()
    prefs["teacher_responses"]["email_digest"] = True
    preferences[STUDENT] = {"user_id": STUDENT, "preferences": prefs}
    notification_service.create_event(
        recipient_id=STUDENT,
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )
    ses = RecordingSes()
    aws.install({Kind.SES_NOTIFICATION: ses})

    result = notification_service.send_digest(
        {"sub": STUDENT, "role": "student", "email": "student@example.com"},
        category="teacher_responses",
    )

    assert result["status"] == "sent"
    [mail] = ses.sent
    target = email_unsubscribe.read_token(_footer_token(_html(mail)))
    assert (target.user_id, target.kind) == (STUDENT, EmailKind.NOTIFICATION_DIGEST)
    assert _headers(mail)["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert email_unsubscribe.read_token(_header_token(mail)) == target


def test_after_unsubscribing_the_next_digest_is_not_sent(preferences, monkeypatch) -> None:
    config.install(test_notifications._notification_provider_settings())
    prefs = notification_service.default_preferences()
    prefs["teacher_responses"]["email_digest"] = True
    preferences[STUDENT] = {"user_id": STUDENT, "preferences": prefs}
    notification_service.create_event(
        recipient_id=STUDENT,
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id="question-1",
        title="Teacher replied",
        summary="Your teacher added a reply.",
    )
    token = email_unsubscribe.issue_token(STUDENT, EmailKind.NOTIFICATION_DIGEST)
    assert _public_client().post("/notifications/email-unsubscribe", params={"token": token}).status_code == 200
    ses = RecordingSes()
    aws.install({Kind.SES_NOTIFICATION: ses})

    result = notification_service.send_digest(
        {"sub": STUDENT, "role": "student", "email": "student@example.com"},
        category="teacher_responses",
    )

    assert result["status"] == "refused_no_digest_items"
    assert ses.sent == []


def test_the_weekly_report_carries_the_link_and_headers_in_the_parents_language(monkeypatch) -> None:
    from stoa.db.repositories import account_deletion_repo, report_repo

    monkeypatch.setattr(report_repo, "register_report_email_intent", lambda **kw: kw)
    monkeypatch.setattr(report_repo, "claim_report_email_intent", lambda *_a, **_k: None)
    monkeypatch.setattr(account_deletion_repo, "require_active_account_fence", lambda *_a, **_k: {})
    ses = RecordingSes()
    aws.install({Kind.SES_NOTIFICATION: ses})

    outcome = notify_service.send_fenced_weekly_report_email(
        "parent@stoa.test",
        "<html><body><h1>Report</h1></body></html>",
        recipient_user_id=PARENT,
        locale="fr",
        owner_id=STUDENT,
        generation=1,
        report_id="report-1",
    )

    assert outcome == "accepted"
    [mail] = ses.sent
    html = _html(mail)
    assert FOOTER_WORDS["fr"] in html
    assert html.index("unsubscribe?token=") < html.index("</body>")
    target = email_unsubscribe.read_token(_footer_token(html))
    assert (target.user_id, target.kind) == (PARENT, EmailKind.WEEKLY_REPORT)
    assert _headers(mail)["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert email_unsubscribe.read_token(_header_token(mail)) == target


def test_a_parent_who_unsubscribed_gets_no_weekly_report_email_but_the_report_stands(
    preferences, monkeypatch
) -> None:
    from test_report_service import (
        FakeS3Client,
        FakeSESClient,
        generated_report_content,
        sample_report_payload,
    )
    from stoa.services import report_service

    monkeypatch.setattr(
        report_service.account_deletion_repo,
        "require_active_account_fence",
        lambda _owner: {"status": "active", "generation": 7},
    )
    monkeypatch.setattr(
        report_service.report_artifact_service,
        "write_fenced_report_artifacts",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(report_service.locale_service, "stored_locale", lambda _uid: "de")
    monkeypatch.setattr(
        report_service.current_relationship,
        "current_parent_recipient",
        lambda *_a: report_service.current_relationship.ParentRecipient(email="parent@example.com"),
    )
    stored, updates = [], []
    monkeypatch.setattr(report_service.report_repo, "put_report", stored.append)
    monkeypatch.setattr(
        report_service.report_repo,
        "update_report_status",
        lambda report_id, status, **fields: updates.append((status, fields)),
    )
    payload = sample_report_payload()
    parent_id = payload["parent"]["id"]
    token = email_unsubscribe.issue_token(parent_id, EmailKind.WEEKLY_REPORT)
    assert _public_client().post("/notifications/email-unsubscribe", params={"token": token}).status_code == 200
    events: list = []
    aws.install(
        {
            Kind.S3: FakeS3Client(events),
            Kind.SES: FakeSESClient(events),
            Kind.SES_NOTIFICATION: FakeSESClient(events),
        }
    )

    result = report_service.store_and_send_weekly_report(payload, generated_report_content())

    assert [event[0] for event in events if event[0] == "ses"] == []
    assert stored and stored[0]["status"] == "generated"
    assert result["status"] == "generated"
    assert result["email_status"] == "skipped_preference"
    [(status, fields)] = updates
    assert status == "generated"
    assert fields["email_status"] == "skipped_preference"
    assert "email_sent_at" not in fields


def test_one_off_emails_carry_no_unsubscribe() -> None:
    from stoa.services import password_change_code_service

    ses = RecordingSes()
    aws.install({Kind.SES: ses})
    notify_service.send_account_invitation_email(
        "a@stoa.test", activation_token="t", expires_at="2026-12-01"
    )
    notify_service.send_teacher_invitation_email(
        "b@stoa.test", activation_token="t", expires_at="2026-12-01"
    )
    password_change_code_service.send_code_email("c@stoa.test", "123456")

    assert len(ses.sent) == 3
    for mail in ses.sent:
        assert "unsubscribe" not in _html(mail).lower()
        assert "List-Unsubscribe" not in _headers(mail)


def test_an_operator_resend_respects_the_parents_unsubscribe(preferences, monkeypatch) -> None:
    from stoa.services import report_recovery_service
    from stoa.services.report_recovery_errors import ReportRecoveryError

    monkeypatch.setattr(
        report_recovery_service.current_relationship,
        "current_parent_recipient",
        lambda *_a: report_recovery_service.current_relationship.ParentRecipient(
            email="parent@stoa.test"
        ),
    )
    audits: list = []
    monkeypatch.setattr(
        report_recovery_service.report_repo, "put_report_audit_event", lambda *a, **k: audits.append(a)
    )
    sent: list = []
    monkeypatch.setattr(
        report_recovery_service.notify_service,
        "send_fenced_weekly_report_email",
        lambda *a, **k: sent.append(a) or "accepted",
    )
    token = email_unsubscribe.issue_token(PARENT, EmailKind.WEEKLY_REPORT)
    assert _public_client().post("/notifications/email-unsubscribe", params={"token": token}).status_code == 200
    report = {
        "report_id": "report-1",
        "parent_id": PARENT,
        "student_id": STUDENT,
        "week_start": "2026-06-01",
        "status": "email_failed",
        "email_status": "failed",
        "html_s3_key": "weekly-reports/private/report.html",
    }

    with pytest.raises(ReportRecoveryError) as refused:
        report_recovery_service.resend_report_email(report, operator="admin-1")

    assert refused.value.code == "report_recipient_unsubscribed"
    assert sent == []


def test_a_link_for_an_account_deleted_since_is_refused_like_any_other(
    preferences, monkeypatch
) -> None:
    from stoa.db.repositories import account_deletion_repo

    def fenced_off(_item):
        raise account_deletion_repo.AccountDeletionConflict("account fence is not active")

    monkeypatch.setattr(notification_service.notification_repo, "put_preferences", fenced_off)
    token = email_unsubscribe.issue_token(PARENT, EmailKind.WEEKLY_REPORT)

    status, body = _refused(token)

    assert status == 400
    assert body["detail"]["code"] == "email_unsubscribe_link_invalid"
