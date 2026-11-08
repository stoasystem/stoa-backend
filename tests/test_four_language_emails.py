"""The three emails that used to speak one language each (#278).

Assertions name catalog keys, never sentences: the wording can change without
these tests, the language a recipient is written to cannot.
"""

from __future__ import annotations

from html import escape
import re

import pytest

from stoa.services import locale_service, message_catalog, notify_service
from stoa.services.message_catalog import emails as email_catalog

LOCALES = sorted(locale_service.SUPPORTED_LOCALES)
EMAIL_KEYS = sorted(email_catalog.TEXT)
_PARAM = re.compile(r"{(\w+)}")


@pytest.mark.parametrize("key", EMAIL_KEYS)
def test_every_email_line_has_all_four_languages_with_the_same_params(key):
    variants = email_catalog.TEXT[key]
    assert set(variants) == locale_service.SUPPORTED_LOCALES
    params = {locale: set(_PARAM.findall(text)) for locale, text in variants.items()}
    assert len({frozenset(value) for value in params.values()}) == 1, params


@pytest.mark.parametrize("key", EMAIL_KEYS)
def test_swiss_german_writes_ss(key):
    assert "ß" not in email_catalog.TEXT[key]["de"]


def test_the_email_lines_are_part_of_the_one_catalog():
    assert set(EMAIL_KEYS) <= set(message_catalog.TEXT)


def _activation(key: str, locale: str, **values) -> str:
    return escape(message_catalog.text(f"email.teacher_activation.{key}", locale, **values))


class _FakeSES:
    def __init__(self):
        self.emails: list[dict] = []

    def send_email(self, **kwargs):
        self.emails.append(kwargs)


@pytest.mark.parametrize("locale", LOCALES)
def test_the_teacher_activation_email_is_in_the_candidates_language(locale):
    ses = _FakeSES()
    notify_service.send_teacher_invitation_email(
        "candidate@example.test",
        activation_token="token/with+chars",
        expires_at="2026-07-21T12:00:00+00:00",
        full_name="Candidate Teacher",
        locale=locale,
        ses_client=ses,
    )

    message = ses.emails[0]["Message"]
    body = message["Body"]["Html"]["Data"]
    assert message["Subject"]["Data"] == message_catalog.text(
        "email.teacher_activation.subject", locale
    )
    assert _activation("greeting", locale, name="Candidate Teacher") in body
    assert _activation("intro", locale) in body
    assert _activation("action", locale) in body
    assert _activation("expiry", locale, expires="2026-07-21T12:00:00+00:00") in body
    assert "/teacher-activate?token=token%2Fwith%2Bchars" in body


@pytest.mark.parametrize("locale", LOCALES)
def test_a_nameless_candidate_is_greeted_without_a_name(locale):
    _, body = notify_service.teacher_invitation_message(
        activation_token="t", expires_at="2026-07-21", full_name="  ", locale=locale
    )
    assert body.startswith(f"<p>{_activation('greeting_anonymous', locale)}</p>")


@pytest.mark.parametrize("locale", [None, "", "xx"])
def test_a_candidate_without_a_usable_language_gets_the_default_one(locale):
    subject, body = notify_service.teacher_invitation_message(
        activation_token="t", expires_at="2026-07-21", locale=locale
    )
    assert subject == message_catalog.text(
        "email.teacher_activation.subject", locale_service.DEFAULT_LOCALE
    )
    assert _activation("intro", locale_service.DEFAULT_LOCALE) in body


def test_a_name_cannot_inject_markup_into_the_activation_email():
    _, body = notify_service.teacher_invitation_message(
        activation_token="t", expires_at="2026-07-21", full_name="<b>x</b>", locale="fr"
    )
    assert "<b>" not in body
    assert "&lt;b&gt;x&lt;/b&gt;" in body


@pytest.mark.parametrize("locale", LOCALES)
def test_the_weekly_report_subject_is_in_the_parents_language(locale):
    assert notify_service.weekly_report_subject("Mia", locale) == message_catalog.text(
        "email.weekly_report.subject", locale, student="Mia"
    )
    assert notify_service.weekly_report_subject("", locale) == message_catalog.text(
        "email.weekly_report.subject",
        locale,
        student=message_catalog.text("email.weekly_report.student_fallback", locale),
    )
