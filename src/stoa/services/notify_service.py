"""SQS + SES — teacher queue and email notifications."""
from datetime import UTC, datetime
from functools import partial
from typing import Callable
from urllib.parse import quote
from uuid import uuid4
from stoa import aws
from stoa.aws import Kind
from stoa import config
from stoa.db.repositories import account_deletion_repo, report_repo
from stoa.services import email_layout, email_unsubscribe, locale_service, message_catalog
from stoa.services.email_unsubscribe import EmailKind


def teacher_invitation_message(
    *, activation_token: str, expires_at: str, full_name: str = "", locale: str | None = None
) -> email_layout.Rendered:
    """The teacher activation email in one language (#374).

    `locale` is the language the candidate applied in; a candidate who named none is
    written to in the default one.
    """
    base = config.settings().app_base_url.rstrip("/")
    link = f"{base}/teacher-activate?token={quote(activation_token, safe='')}"
    lang = _lang(locale)

    def copy(key: str, **values: object) -> str:
        return message_catalog.text(f"email.teacher_activation.{key}", lang, **values)

    return email_layout.render(
        subject=copy("subject"),
        title=copy("title"),
        greeting=email_layout.greeting(full_name, lang),
        blocks=[
            email_layout.Paragraph(copy("intro")),
            email_layout.Paragraph(copy("next_step")),
            email_layout.Action(copy("action"), link),
            email_layout.Paragraph(
                message_catalog.text(
                    "email.account_invitation.expiry",
                    lang,
                    expires=email_layout.format_datetime(expires_at, lang),
                ),
                small=True,
            ),
        ],
        locale=lang,
        footer_reason=copy("footer"),
    )


def _lang(locale: str | None) -> str:
    try:
        return locale_service.normalize_locale(locale)
    except ValueError:
        return locale_service.DEFAULT_LOCALE


def send_one_off_email(recipient: str, email: email_layout.Rendered) -> dict:
    """Send one email that is not a notification: activation links and codes.

    These carry no unsubscribe line, so they stay on SES v1 `SendEmail`. Both parts
    go out, HTML and plain text, with Reply-To naming a mailbox somebody reads.
    """
    settings = config.settings()
    return aws.client(Kind.SES).send_email(
        Source=settings.notification_email_sender,
        Destination={"ToAddresses": [recipient]},
        ReplyToAddresses=[settings.notification_email_reply_to],
        Message={
            "Subject": {"Data": email.subject, "Charset": "UTF-8"},
            "Body": {
                "Html": {"Data": email.html, "Charset": "UTF-8"},
                "Text": {"Data": email.text, "Charset": "UTF-8"},
            },
        },
    )


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
    return ses.send_email(
        FromEmailAddress=sender,
        Destination={"ToAddresses": [recipient]},
        ReplyToAddresses=[config.settings().notification_email_reply_to],
        Content={
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html, "Charset": "UTF-8"},
                    "Text": {"Data": email_layout.to_text(html), "Charset": "UTF-8"},
                },
                "Headers": email_unsubscribe.headers(recipient_user_id, kind),
            }
        },
    )


def send_teacher_invitation_email(
    recipient: str,
    *,
    activation_token: str,
    expires_at: str,
    full_name: str = "",
    locale: str | None = None,
) -> None:
    """Deliver a single-use teacher activation link to the reviewed candidate.

    The token is only ever readable at issue time, so this is the one path that puts it
    in the candidate's hands. Callers must treat a raised exception as undelivered and
    re-issue rather than assume the candidate can still activate.
    """
    send_one_off_email(
        recipient,
        teacher_invitation_message(
            activation_token=activation_token,
            expires_at=expires_at,
            full_name=full_name,
            locale=locale,
        ),
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
    send_one_off_email(
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


def _account_invitation_blocks(
    lang: str, *, link: str, expires_at: str, role: str | None, button_locale: bool = False
) -> list[email_layout.Block]:
    def copy(key: str, **values: object) -> str:
        return message_catalog.text(f"email.account_invitation.{key}", lang, **values)

    role_key = f"email.account_invitation.role.{str(role or '').strip().lower()}"
    blocks: list[email_layout.Block] = [email_layout.Paragraph(copy("intro"))]
    if role_key in message_catalog.TEXT:
        blocks.append(email_layout.Paragraph(message_catalog.text(role_key, lang)))
    return blocks + [
        email_layout.Paragraph(copy("next_step")),
        email_layout.Action(copy("action"), link, locale=lang if button_locale else None),
        email_layout.Paragraph(
            copy("expiry", expires=email_layout.format_datetime(expires_at, lang)), small=True
        ),
    ]


def account_invitation_message(
    *,
    activation_token: str,
    expires_at: str,
    full_name: str = "",
    locale: str | None = None,
    role: str | None = None,
) -> email_layout.Rendered:
    """The activation email of an invited account (#374, #415).

    `role` adds one line on what the account is for; without one the email names
    no role. With a `locale` the email is written in that language. Without one,
    nobody knows yet which language the invitee reads, so it says everything in
    all four - German, French, Italian, English - one after the other, each with
    its own button to the same single-use link. Never in the language of whoever
    sent the invitation.
    """
    base = config.settings().app_base_url.rstrip("/")
    link = f"{base}/activate?token={quote(activation_token, safe='')}"

    if locale is None or not str(locale).strip():
        def text(key: str, lang: str) -> str:
            return message_catalog.text(f"email.account_invitation.{key}", lang)

        langs = email_layout.ALL_LOCALES
        return email_layout.render_multilingual(
            subject=" · ".join(text("title", lang) for lang in langs),
            title=" · ".join(text("title", lang) for lang in langs),
            sections=[
                email_layout.Section(
                    locale=lang,
                    greeting=email_layout.greeting(full_name, lang),
                    blocks=tuple(
                        _account_invitation_blocks(
                            lang, link=link, expires_at=expires_at, role=role, button_locale=True
                        )
                    ),
                    footer_reason=text("footer", lang),
                )
                for lang in langs
            ],
        )

    lang = _lang(locale)

    def copy(key: str) -> str:
        return message_catalog.text(f"email.account_invitation.{key}", lang)

    return email_layout.render(
        subject=copy("subject"),
        title=copy("title"),
        greeting=email_layout.greeting(full_name, lang),
        blocks=_account_invitation_blocks(lang, link=link, expires_at=expires_at, role=role),
        locale=lang,
        footer_reason=copy("footer"),
    )


def send_account_invitation_email(
    recipient: str,
    *,
    activation_token: str,
    expires_at: str,
    full_name: str = "",
    locale: str | None = None,
    role: str | None = None,
) -> None:
    """Deliver one single-use activation link to an invited account of any role.

    The token is readable only at issue time. A raised exception means undelivered:
    the caller must reissue rather than assume the invitee can still activate.
    """
    send_one_off_email(
        recipient,
        account_invitation_message(
            activation_token=activation_token,
            expires_at=expires_at,
            full_name=full_name,
            locale=locale,
            role=role,
        ),
    )


def account_invitation_locale(locale: str | None) -> str | None:
    """The language an invitee is written to (#374, #415).

    The one named; None when none is named, which means all four languages, since
    nobody knows yet which one the invitee reads. Never the language of whoever
    sends the invitation; that is who sent it, not who reads it. A name that is not
    one of STOA's languages counts as none named.
    """
    if locale is None or not str(locale).strip():
        return None
    try:
        return locale_service.normalize_locale(locale)
    except ValueError:
        return None


def account_invitation_delivery(locale: str | None) -> Callable[..., None]:
    """How an administrator's invitation is mailed, by the console and by an agent (#384)."""
    return partial(send_account_invitation_email, locale=account_invitation_locale(locale))


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
