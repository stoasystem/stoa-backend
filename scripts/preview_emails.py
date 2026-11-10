"""Render every email STOA sends, in every language, to HTML files (#374).

Nothing is sent and nothing is read from AWS: each email is rendered from sample
values, so a person can open the files and look at them. One HTML file and one
plain-text file per email and language, plus an index page linking them all.

    python scripts/preview_emails.py --out <directory>
"""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from stoa.services import (
    email_unsubscribe,
    locale_service,
    message_catalog,
    notification_service,
    notify_service,
    password_change_code_service,
    report_service,
)
from stoa.services.email_layout import to_text
from stoa.services.email_unsubscribe import EmailKind

SAMPLE_USER = "user_preview"
EXPIRES = "2026-11-13T13:50:20+00:00"


def _weekly_report(locale: str) -> str:
    payload = {
        "parent": {"id": SAMPLE_USER, "name": "Anna Muster"},
        "student": {"id": "student_preview", "name": "Lea"},
        "week": {"start": "2026-11-02", "end": "2026-11-08"},
    }
    content = {
        "summary": "Lea hat diese Woche 14 Aufgaben gelöst und zwei neue Sterne erreicht.",
        "recommendations": ["Bruchrechnen wiederholen", "Täglich 10 Minuten Kopfrechnen"],
        "weakTopics": [{"topic": "Brüche kürzen", "note": "3 von 5 Aufgaben richtig"}],
        "teacherNote": "Sehr gute Fortschritte beim Textverständnis.",
    }
    return report_service.render_weekly_report_html(payload, content, locale=locale)


def emails(locale: str) -> dict[str, tuple[str, str]]:
    """Name -> (subject, html) for every email, in one language."""
    invitation = notify_service.account_invitation_message(
        activation_token="preview-token",
        expires_at=EXPIRES,
        full_name="Anna Muster",
        locale=locale,
        role="parent",
    )
    teacher = notify_service.teacher_invitation_message(
        activation_token="preview-token", expires_at=EXPIRES, full_name="Marco Rossi", locale=locale
    )
    code = password_change_code_service.code_email("482913", locale=locale)
    dispatch = notify_service.dispatch_reminder_message(
        recipient_user_id=SAMPLE_USER,
        subject_name="Mathematik",
        request_id="request_preview",
        minutes=10,
        locale=locale,
    )
    digest_html = notification_service._digest_email_html(
        [
            {"title": "Neue Antwort einer Lehrperson", "summary": "Ihre Frage zu Brüchen wurde beantwortet."},
            {"title": "Wochenbericht bereit", "summary": "Der Bericht für Lea ist da."},
        ],
        locale,
        SAMPLE_USER,
    )
    # The unsubscribe line is added at send time, as `send_fenced_weekly_report_email` does.
    weekly_html = email_unsubscribe.with_footer(
        _weekly_report(locale),
        email_unsubscribe.footer_html(SAMPLE_USER, EmailKind.WEEKLY_REPORT, locale),
    )
    return {
        "account_invitation": (invitation.subject, invitation.html),
        "teacher_activation": (teacher.subject, teacher.html),
        "password_code": (code.subject, code.html),
        "dispatch_reminder": dispatch,
        "notification_digest": (
            message_catalog.text("email.notification_digest.subject", locale),
            digest_html,
        ),
        "weekly_report": (notify_service.weekly_report_subject("Lea", locale), weekly_html),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path, help="directory to write the files into")
    args = parser.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for locale in sorted(locale_service.SUPPORTED_LOCALES):
        for name, (subject, html) in emails(locale).items():
            stem = f"{name}.{locale}"
            (out / f"{stem}.html").write_text(html, encoding="utf-8", newline="\n")
            (out / f"{stem}.txt").write_text(to_text(html), encoding="utf-8", newline="\n")
            rows.append(
                f'<tr><td>{escape(name)}</td><td>{locale}</td><td>{escape(subject)}</td>'
                f'<td><a href="{stem}.html">HTML</a> · <a href="{stem}.txt">Text</a></td></tr>'
            )
    (out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>STOA emails</title>"
        "<style>body{font:14px system-ui;margin:24px}td{padding:4px 10px;border-bottom:1px solid #ddd}</style>"
        f"<h1>STOA emails</h1><table>{''.join(rows)}</table>",
        encoding="utf-8",
        newline="\n",
    )
    print(f"{len(rows)} emails written to {out}")


if __name__ == "__main__":
    main()
