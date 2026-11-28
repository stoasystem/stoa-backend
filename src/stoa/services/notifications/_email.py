"""The email channel: the teacher's dispatch reminder and the parent's weekly report (#687).

Inside the notification package. A happening that goes out by email reaches
`send_once` with what to say; this module does the rest, once for both kinds:

- the reader's switch (`dispatch_email`, `weekly_report_email`) is read by the
  caller in here (`_tell`), never by the service the happening came from;
- the unsubscribe line goes into the body and the RFC 8058 `List-Unsubscribe`
  headers onto the message (#363), in the reader's language;
- the send crosses the same only-once ledger as realtime and push
  (`_ledger.run_delivery_intent`, #638 decision 3), under the happening's fixed
  id with `email-` in front. The ledger row sits behind the account fence of
  the account the happening belongs to (the student), so an account deleted in
  the meantime gets no email, and a retry of the same happening - after a send
  whose record was lost, too - sends nothing a second time.

The one-off emails (codes, invitations) are not notifications: `one_off_email`
(#685). Both share only "send one email with SES" (`ses_email`) and the layout.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import quote

from stoa import aws, config
from stoa.aws import Kind
from stoa.services import email_layout, email_unsubscribe, message_catalog, ses_email
from stoa.services.email_unsubscribe import EmailKind
from stoa.services.notifications import _ledger

CHANNEL = "email"

#: The ledger status of an email that went out, this time or on an earlier try.
ACCEPTED = "accepted"


class EmailOutcome(StrEnum):
    """What became of a happening's email, for a caller that records it (the weekly report)."""

    SENT = "sent"
    UNSUBSCRIBED = "unsubscribed"
    FAILED = "failed"


@dataclass(frozen=True)
class EmailResult:
    """The outcome, and for a failure what failed: the exception, for the caller's own record."""

    outcome: EmailOutcome
    error: Exception | None = None


def operation_id(happening_id: str) -> str:
    """The ledger's id for the email of one happening: its fixed id, as email."""
    return f"{CHANNEL}-{happening_id}"


def with_unsubscribe_footer(
    html: str, *, recipient_user_id: str, kind: EmailKind, locale: str | None
) -> str:
    """The body as the reader gets it: with the line that stops this kind of email."""
    return email_unsubscribe.with_footer(
        html, email_unsubscribe.footer_html(recipient_user_id, kind, locale)
    )


def send_once(
    *,
    kind: EmailKind,
    happening_id: str,
    owner_id: str,
    generation: int,
    recipient_user_id: str,
    recipient: str,
    subject: str,
    html: str,
    locale: str | None,
    ses_kind: Kind,
) -> str:
    """Send one notification email for one happening, at most once; return the ledger status.

    `html` is the body without the unsubscribe line, which is added here. The
    status is `accepted` when the email went out, now or on an earlier try of
    the same happening; anything else means it was not sent this time and will
    not be by a retry of the same happening either (`provider_acceptance_unknown`,
    `canceled_account_deletion`), or that another try holds it right now.
    """
    body = with_unsubscribe_footer(
        html, recipient_user_id=recipient_user_id, kind=kind, locale=locale
    )
    ses = aws.client(ses_kind)

    def provider_call() -> None:
        response = ses_email.send_with_headers(
            ses,
            sender=config.settings().notification_email_sender,
            recipient=recipient,
            subject=subject,
            html=body,
            headers=email_unsubscribe.headers(recipient_user_id, kind),
        )
        message_id = response.get("MessageId") if isinstance(response, Mapping) else None
        if not isinstance(message_id, str) or not message_id.strip():
            raise ValueError("malformed provider acceptance")

    result = _ledger.run_delivery_intent(
        owner_id=owner_id,
        generation=generation,
        operation_id=operation_id(happening_id),
        channel=CHANNEL,
        event_ids=[happening_id],
        # What makes this email the same email: never the body or the address,
        # so a retry whose report was rendered again, or whose reader changed
        # their address, is still the same happening and is not sent again.
        payload={
            "kind": kind.value,
            "happening": happening_id,
            "recipient_user_id": recipient_user_id,
        },
        provider_call=provider_call,
    )
    return str(result.get("status") or "")


def dispatch_reminder_message(
    *, subject_name: str, request_id: str, minutes: int, locale: str
) -> email_layout.Rendered:
    """The subject and body of one dispatch reminder in one language (#141), before its footer.

    Only the subject's name and a link into STOA: the email leaves STOA, so
    nothing the student wrote, sent or is called goes with it.
    """
    base = config.settings().app_base_url.rstrip("/")
    link = f"{base}/teacher/requests/{quote(request_id, safe='')}"

    def copy(key: str, **values: object) -> str:
        return message_catalog.text(f"teacher_help.dispatched.{key}", locale, **values)

    return email_layout.render(
        subject=copy("email.subject", minutes=minutes),
        title=copy("title"),
        greeting=email_layout.greeting(None, locale),
        blocks=[
            email_layout.Paragraph(copy("email.intro")),
            email_layout.Paragraph(
                message_catalog.text(
                    "email.dispatch_reminder.subject_line", locale, subject=subject_name
                )
            ),
            email_layout.Paragraph(copy("email.deadline", minutes=minutes)),
            email_layout.Action(copy("email.action"), link),
            email_layout.Paragraph(copy("email.footer"), small=True),
        ],
        locale=locale,
        footer_reason=None,
        questions=False,
    )
