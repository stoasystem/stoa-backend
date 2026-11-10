"""Every email STOA sends wears one frame (#374).

Assertions name catalog keys and settings, not sentences, so the wording can
change without these tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import importlib.util
from pathlib import Path

import pytest

from stoa import aws, config
from stoa.aws import Kind
from stoa.services import (
    email_layout,
    email_unsubscribe,
    locale_service,
    message_catalog,
    notify_service,
)

LOCALES = sorted(locale_service.SUPPORTED_LOCALES)
ROOT = Path(__file__).resolve().parents[1]


def _preview_module():
    spec = importlib.util.spec_from_file_location("preview_emails", ROOT / "scripts" / "preview_emails.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NOTIFICATION_EMAILS = {"dispatch_reminder", "notification_digest", "weekly_report"}


@pytest.mark.parametrize("locale", LOCALES)
def test_all_six_emails_wear_the_frame_in_every_language(locale):
    rendered = _preview_module().emails(locale)

    assert set(rendered) == {
        "account_invitation",
        "teacher_activation",
        "password_code",
        "dispatch_reminder",
        "notification_digest",
        "weekly_report",
    }
    logo = escape(config.settings().email_logo_url, quote=True)
    tagline = escape(message_catalog.text("email.common.tagline", locale))
    signoff_first = escape(message_catalog.text("email.common.signoff", locale).split("\n")[0])
    unsubscribe = escape(message_catalog.text("email.unsubscribe.action", locale))
    for name, (subject, html) in rendered.items():
        assert subject, name
        assert f'<html lang="{locale}">' in html, name
        assert f'src="{logo}"' in html, name
        assert 'alt="STOA"' in html, name
        assert tagline in html, name
        assert "info@stoaedu.ch" in html, name
        assert signoff_first in html, name
        # Only the emails that recur or notify can be stopped from the email (#363).
        assert (unsubscribe in html) is (name in NOTIFICATION_EMAILS), name
        # The unsubscribe line sits inside the footer, not after the card.
        if name in NOTIFICATION_EMAILS:
            assert html.index(unsubscribe) < html.index(email_layout.FOOTER_MARK), name


def test_text_from_a_caller_is_escaped_never_markup():
    email = email_layout.render(
        subject="s",
        title="<script>t</script>",
        greeting=email_layout.greeting("<b>Anna</b>", "de"),
        blocks=[
            email_layout.Paragraph("a < b & c"),
            email_layout.Action("<i>go</i>", 'https://app.stoaedu.ch/x?a=1&b="2"'),
            email_layout.Items((("<u>t</u>", "<s>n</s>"),)),
        ],
        locale="de",
        footer_reason="<em>why</em>",
    )
    for raw in ("<script>", "<b>", "<i>", "<u>", "<s>", "<em>"):
        assert raw not in email.html
    assert "a &lt; b &amp; c" in email.html
    assert 'href="https://app.stoaedu.ch/x?a=1&amp;b=&quot;2&quot;"' in email.html


def test_the_text_part_reads_the_same_email_without_markup():
    email = email_layout.render(
        subject="Betreff",
        title="Titel",
        greeting="Guten Tag Anna",
        blocks=[
            email_layout.Paragraph("Erster Absatz."),
            email_layout.Action("Los", "https://app.stoaedu.ch/go"),
            email_layout.Bullets(("eins", "zwei")),
        ],
        locale="de",
        footer_reason="Darum.",
    )
    text = email.text
    assert "<" not in text
    assert text.startswith("Titel\n\nGuten Tag Anna\n\nErster Absatz.")
    # The button is a line with its address; the "copy this link" fallback is not repeated.
    assert text.count("https://app.stoaedu.ch/go") == 1
    assert "Los: https://app.stoaedu.ch/go" in text
    assert "- eins\n- zwei" in text
    assert "Darum." in text
    assert "Betreff" not in text  # the <title> stays out


@pytest.mark.parametrize(
    ("value", "locale", "expected"),
    [
        ("2026-11-13T13:50:20.578401+00:00", "de", "13. November 2026, 14:50"),
        ("2026-07-21T12:00:00+00:00", "en", "21 July 2026, 14:00"),
        ("2026-03-04T09:00:00Z", "fr", "4 mars 2026, 10:00"),
        ("2026-03-29T01:30:00+00:00", "it", "29 marzo 2026, 03:30"),
        ("2026-03-04T09:00:00", "de", "4. März 2026, 10:00"),
        ("not a date", "de", "not a date"),
    ],
)
def test_a_moment_reads_in_zurich_time_with_the_month_in_words(value, locale, expected):
    assert email_layout.format_datetime(value, locale) == expected


def test_a_moment_given_as_a_datetime_and_an_unknown_language_falls_back():
    moment = datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc)
    assert email_layout.format_datetime(moment, "xx") == "1. Januar 2027, 00:30"


def test_a_day_reads_with_the_month_in_words():
    assert email_layout.format_date("2026-06-01", "de") == "1. Juni 2026"
    assert email_layout.format_date("2026-06-01", "en") == "1 June 2026"
    assert email_layout.format_date("bad", "de") == "bad"


def test_the_unsubscribe_line_goes_into_the_footer_of_a_framed_email():
    email = email_layout.render(
        subject="s", title="t", greeting=None, blocks=[], locale="de", footer_reason=None
    )
    html = email_unsubscribe.with_footer(email.html, "<p>LINE</p>")
    assert html.index("<p>LINE</p>") < html.index(email_layout.FOOTER_MARK) < html.index("</body>")
    # Anything not in the frame still gets the line before </body>.
    assert email_unsubscribe.with_footer("<body>x</body>", "L") == "<body>xL</body>"


class _RecordingSes:
    def __init__(self):
        self.sent: list[dict] = []

    def send_email(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "m-1"}


def test_a_one_off_email_goes_out_as_html_and_text_with_reply_to():
    ses = _RecordingSes()
    aws.install({Kind.SES: ses})

    notify_service.send_account_invitation_email(
        "a@stoa.test", activation_token="t", expires_at="2026-12-01T10:00:00+00:00", role="student"
    )

    [mail] = ses.sent
    settings = config.settings()
    assert mail["Source"] == settings.notification_email_sender
    assert mail["ReplyToAddresses"] == [settings.notification_email_reply_to]
    body = mail["Message"]["Body"]
    assert body["Html"]["Charset"] == body["Text"]["Charset"] == "UTF-8"
    assert "/activate?token=t" in body["Text"]["Data"]


def test_a_notification_email_goes_out_as_html_and_text_with_reply_to_and_headers():
    ses = _RecordingSes()
    aws.install({Kind.SES_DISPATCH_REMINDER: ses})

    notify_service.send_dispatch_reminder_email(
        "teacher@stoa.test",
        recipient_user_id="teacher-1",
        subject_name="Mathematik",
        request_id="req-1",
        minutes=10,
        locale="de",
    )

    [mail] = ses.sent
    assert mail["ReplyToAddresses"] == [config.settings().notification_email_reply_to]
    simple = mail["Content"]["Simple"]
    assert "/teacher/requests/req-1" in simple["Body"]["Text"]["Data"]
    assert email_unsubscribe.PAGE_PATH in simple["Body"]["Text"]["Data"]
    assert {header["Name"] for header in simple["Headers"]} == {
        "List-Unsubscribe",
        "List-Unsubscribe-Post",
    }


def test_the_logo_and_reply_to_come_from_settings():
    config.install(
        config.settings().model_copy(
            update={
                "email_logo_url": "https://cdn.example.test/logo.png",
                "notification_email_reply_to": "help@example.test",
            }
        )
    )
    ses = _RecordingSes()
    aws.install({Kind.SES: ses})

    notify_service.send_account_invitation_email("a@stoa.test", activation_token="t", expires_at="x")

    [mail] = ses.sent
    assert 'src="https://cdn.example.test/logo.png"' in mail["Message"]["Body"]["Html"]["Data"]
    assert mail["ReplyToAddresses"] == ["help@example.test"]


def test_the_preview_script_writes_every_email_in_every_language(tmp_path, monkeypatch):
    module = _preview_module()
    monkeypatch.setattr("sys.argv", ["preview_emails.py", "--out", str(tmp_path)])

    module.main()

    for name in ("account_invitation", "weekly_report"):
        for locale in LOCALES:
            assert (tmp_path / f"{name}.{locale}.html").is_file()
            assert (tmp_path / f"{name}.{locale}.txt").is_file()
    assert (tmp_path / "index.html").is_file()


def test_every_dispatch_reminder_names_its_subject_once():
    _, html = notify_service.dispatch_reminder_message(
        recipient_user_id="t-1", subject_name="Mathematik", request_id="r", minutes=10, locale="de"
    )
    assert escape(
        message_catalog.text("email.dispatch_reminder.subject_line", "de", subject="Mathematik")
    ) in html
    summary = message_catalog.text(
        "teacher_help.dispatched.summary", "de", subject="Mathematik", minutes=10
    )
    assert escape(summary) not in html
