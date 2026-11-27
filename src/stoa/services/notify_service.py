"""Notification emails: dispatch reminders and weekly reports.

The one-off emails (codes, invitations) live in `one_off_email` (#685).
"""
from datetime import UTC, datetime
from urllib.parse import quote
from uuid import uuid4
from stoa import aws
from stoa.aws import Kind
from stoa import config
from stoa.db.repositories import account_deletion_repo, report_repo
from stoa.services import (
    email_layout,
    email_unsubscribe,
    locale_service,
    message_catalog,
    ses_email,
)
from stoa.services.email_unsubscribe import EmailKind


def _lang(locale: str | None) -> str:
    try:
        return locale_service.normalize_locale(locale)
    except ValueError:
        return locale_service.DEFAULT_LOCALE


def send_notification_email(
    ses,
    *,
    sender: str,
    recipient: str,
    recipient_user_id: str,
    kind: EmailKind,
    subject: str,
    html: str,
) -> dict:
    """Send one notification email with its `List-Unsubscribe` headers (#363).

    SES v1 `SendEmail` cannot set headers, so notification emails go through
    SESv2 `SendEmail` with `Content.Simple.Headers`; `ses` is an SESv2 client.
    The body is sent as given: the caller has already put the footer in it. The
    plain-text part is read off that HTML (#374).
    """
    return ses_email.send_with_headers(
        ses,
        sender=sender,
        recipient=recipient,
        subject=subject,
        html=html,
        headers=email_unsubscribe.headers(recipient_user_id, kind),
    )


def weekly_report_subject(student_name: str | None, locale: str | None) -> str:
    """The subject of one weekly report email, in the parent's language."""
    lang = locale or locale_service.DEFAULT_LOCALE
    student = str(student_name or "").strip() or message_catalog.text(
        "email.weekly_report.student_fallback", lang
    )
    return message_catalog.text("email.weekly_report.subject", lang, student=student)


def send_weekly_report_email(
    parent_email: str,
    report_html: str,
    *,
    subject: str | None = None,
) -> None:
    """Send the weekly report to a parent via SES, without an unsubscribe line."""
    ses_email.send_plain(
        parent_email,
        email_layout.Rendered(
            subject=subject or weekly_report_subject(None, None),
            html=report_html,
            text=email_layout.to_text(report_html),
        ),
    )


def send_fenced_weekly_report_email(
    parent_email: str,
    report_html: str,
    *,
    recipient_user_id: str,
    locale: str | None,
    owner_id: str,
    generation: int,
    report_id: str,
    subject: str | None = None,
    operation_id: str | None = None,
    table=None,
) -> str:
    """Send once only after durable intent, claim, and immediate fence checks.

    `recipient_user_id` is the parent's account: the unsubscribe line and headers
    stop their weekly report email, in their `locale` (#363).
    """
    operation = operation_id or uuid4().hex
    subject_value = subject or weekly_report_subject(None, locale)
    report_html = email_unsubscribe.with_footer(
        report_html,
        email_unsubscribe.footer_html(recipient_user_id, EmailKind.WEEKLY_REPORT, locale),
    )
    now_iso = datetime.now(UTC).isoformat()
    intent = report_repo.register_report_email_intent(
        owner_id=owner_id,
        generation=generation,
        operation_id=operation,
        report_id=report_id,
        recipient=parent_email,
        subject=subject_value,
        body=report_html,
        now_iso=now_iso,
        table=table,
    )
    report_repo.claim_report_email_intent(intent, lease_id=uuid4().hex, table=table)
    account_deletion_repo.require_active_account_fence(owner_id, generation, table=table)
    ses = aws.client(Kind.SES_NOTIFICATION)
    response = None
    error = None
    try:
        response = send_notification_email(
            ses,
            sender=config.settings().notification_email_sender,
            recipient=parent_email,
            recipient_user_id=recipient_user_id,
            kind=EmailKind.WEEKLY_REPORT,
            subject=subject_value,
            html=report_html,
        )
    except Exception as exc:
        error = exc
    return report_repo.classify_report_delivery_outcome(response=response, error=error)


def dispatch_reminder_message(
    *, recipient_user_id: str, subject_name: str, request_id: str, minutes: int, locale: str
) -> tuple[str, str]:
    """Render the subject and HTML body of one dispatch reminder in one language (#141).

    Only the subject's name and a link into STOA: the email leaves STOA, so nothing
    the student wrote, sent or is called goes with it.
    """
    lang = _lang(locale)
    base = config.settings().app_base_url.rstrip("/")
    link = f"{base}/teacher/requests/{quote(request_id, safe='')}"

    def copy(key: str, **values: object) -> str:
        return message_catalog.text(f"teacher_help.dispatched.{key}", lang, **values)

    email = email_layout.render(
        subject=copy("email.subject", minutes=minutes),
        title=copy("title"),
        greeting=email_layout.greeting(None, lang),
        blocks=[
            email_layout.Paragraph(copy("email.intro")),
            email_layout.Paragraph(
                message_catalog.text(
                    "email.dispatch_reminder.subject_line", lang, subject=subject_name
                )
            ),
            email_layout.Paragraph(copy("email.deadline", minutes=minutes)),
            email_layout.Action(copy("email.action"), link),
            email_layout.Paragraph(copy("email.footer"), small=True),
        ],
        locale=lang,
        footer_reason=None,
        questions=False,
    )
    html = email_unsubscribe.with_footer(
        email.html,
        email_unsubscribe.footer_html(recipient_user_id, EmailKind.DISPATCH_REMINDER, lang),
    )
    return email.subject, html


def send_dispatch_reminder_email(
    recipient: str,
    *,
    recipient_user_id: str,
    subject_name: str,
    request_id: str,
    minutes: int,
    locale: str,
) -> None:
    """Remind the teacher an offer went to that it is waiting for them (#141)."""
    subject_line, body = dispatch_reminder_message(
        recipient_user_id=recipient_user_id,
        subject_name=subject_name,
        request_id=request_id,
        minutes=minutes,
        locale=locale,
    )
    # Bounded well inside the request's 29 seconds (`aws.DISPATCH_REMINDER_SES_CONFIG`).
    ses = aws.client(Kind.SES_DISPATCH_REMINDER)
    send_notification_email(
        ses,
        sender=config.settings().notification_email_sender,
        recipient=recipient,
        recipient_user_id=recipient_user_id,
        kind=EmailKind.DISPATCH_REMINDER,
        subject=subject_line,
        html=body,
    )
