"""Send one email through SES: the one layer one-off emails and notifications share (#685).

It knows the sender, the Reply-To mailbox and the shape of the two SES calls,
nothing about who may be written to or why. Preferences, unsubscribe lines and
"only once" belong to the notification side; the one-off side has none of them.
"""

from stoa import aws, config
from stoa.aws import Kind
from stoa.services import email_layout


def send_plain(recipient: str, email: email_layout.Rendered) -> dict:
    """Send one email with SES v1 `SendEmail`: HTML and plain text, no extra headers.

    Reply-To names a mailbox somebody reads.
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


def send_with_headers(
    ses,
    *,
    sender: str,
    recipient: str,
    subject: str,
    html: str,
    headers: list[dict[str, str]],
) -> dict:
    """Send one email with SESv2 `SendEmail`, which can carry `headers`; `ses` is an SESv2 client.

    SES v1 `SendEmail` cannot set headers. The plain-text part is read off the HTML.
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
                "Headers": headers,
            }
        },
    )
