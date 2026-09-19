"""SQS + SES — teacher queue and email notifications."""
import json
from datetime import UTC, datetime
from html import escape
from urllib.parse import quote
from uuid import uuid4
import boto3
from stoa.config import settings
from stoa.db.repositories import account_deletion_repo, report_repo


def require_active_account_fence(owner_id: str, generation: int) -> bool:
    try:
        account_deletion_repo.require_active_account_fence(owner_id, generation)
    except account_deletion_repo.AccountDeletionConflict:
        return False
    return True


def enqueue_teacher_request(
    *, question_id: str, operation_id: str, generation: int, owner_id: str | None = None
) -> None:
    """Push only opaque fenced coordinates to the teacher FIFO queue."""
    if type(generation) is not int or generation <= 0:
        raise RuntimeError("teacher escalation generation is required")
    fence_owner = owner_id or operation_id
    if not require_active_account_fence(fence_owner, generation):
        raise RuntimeError("teacher escalation owner is fenced")
    if owner_id:
        account_deletion_repo.create_teacher_escalation_intent(
            owner_id=owner_id,
            question_id=question_id,
            operation_id=operation_id,
            generation=generation,
        )
        if not require_active_account_fence(owner_id, generation):
            raise RuntimeError("teacher escalation owner is fenced")
    sqs = boto3.client("sqs", region_name=settings.aws_region)
    sqs.send_message(
        QueueUrl=settings.teacher_queue_url,
        MessageBody=json.dumps({
            "operation_id": operation_id,
            "question_id": question_id,
            "generation": generation,
        }),
        MessageGroupId=operation_id,
        MessageDeduplicationId=operation_id,
    )


def send_teacher_invitation_email(
    recipient: str,
    *,
    activation_token: str,
    expires_at: str,
    full_name: str = "",
    ses_client=None,
) -> None:
    """Deliver a single-use teacher activation link to the reviewed candidate.

    The token is only ever readable at issue time, so this is the one path that puts it
    in the candidate's hands. Callers must treat a raised exception as undelivered and
    re-issue rather than assume the candidate can still activate.
    """
    ses = ses_client or boto3.client("ses", region_name=settings.aws_region)
    base = settings.app_base_url.rstrip("/")
    link = f"{base}/teacher-activate?token={quote(activation_token, safe='')}"
    greeting = f"Hallo {escape(full_name)}," if full_name.strip() else "Hallo,"
    ses.send_email(
        Source="noreply@stoaedu.ch",
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": "STOA - Ihre Freischaltung als Lehrperson"},
            "Body": {
                "Html": {
                    "Data": (
                        f"<p>{greeting}</p>"
                        "<p>Ihre Bewerbung als Lehrperson bei STOA wurde geprüft und "
                        "freigegeben. Über den folgenden Link können Sie Ihr Konto "
                        "einrichten und freischalten:</p>"
                        f'<p><a href="{escape(link, quote=True)}">Konto freischalten</a></p>'
                        f"<p>Der Link ist einmalig verwendbar und gültig bis "
                        f"{escape(expires_at)}.</p>"
                    )
                }
            },
        },
    )


def send_weekly_report_email(
    parent_email: str,
    report_html: str,
    *,
    subject: str | None = None,
    ses_client=None,
) -> None:
    """Send the weekly report to a parent via SES."""
    ses = ses_client or boto3.client("ses", region_name=settings.aws_region)
    ses.send_email(
        Source="noreply@stoaedu.ch",
        Destination={"ToAddresses": [parent_email]},
        Message={
            "Subject": {"Data": subject or "STOA - Wochenbericht Ihres Kindes"},
            "Body": {"Html": {"Data": report_html}},
        },
    )


def send_fenced_weekly_report_email(
    parent_email: str,
    report_html: str,
    *,
    owner_id: str,
    generation: int,
    report_id: str,
    subject: str | None = None,
    operation_id: str | None = None,
    ses_client=None,
    table=None,
) -> str:
    """Send once only after durable intent, claim, and immediate fence checks."""
    operation = operation_id or uuid4().hex
    subject_value = subject or "STOA - Wochenbericht Ihres Kindes"
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
    ses = ses_client or boto3.client("ses", region_name=settings.aws_region)
    response = None
    error = None
    try:
        response = ses.send_email(
            Source="noreply@stoaedu.ch",
            Destination={"ToAddresses": [parent_email]},
            Message={
                "Subject": {"Data": subject_value},
                "Body": {"Html": {"Data": report_html}},
            },
        )
    except Exception as exc:
        error = exc
    return report_repo.classify_report_delivery_outcome(response=response, error=error)


# Role-neutral activation copy. Each locale carries its own subject, greeting and body
# so an invited student, parent, teacher or admin reads the same message in their own
# language. The teacher review flow keeps its own German-only template.
ACCOUNT_INVITATION_COPY = {
    "de": {
        "subject": "STOA – Ihr Konto freischalten",
        "greeting": "Hallo {name},",
        "greeting_anonymous": "Hallo,",
        "intro": "für Sie wurde ein STOA-Konto eröffnet. Über den folgenden Link legen Sie Ihr Passwort fest und schalten das Konto frei:",
        "action": "Konto freischalten",
        "expiry": "Der Link ist einmalig verwendbar und gültig bis {expires}.",
        "ignore": "Wenn Sie dieses Konto nicht erwartet haben, können Sie diese Nachricht ignorieren.",
    },
    "fr": {
        "subject": "STOA – Activez votre compte",
        "greeting": "Bonjour {name},",
        "greeting_anonymous": "Bonjour,",
        "intro": "un compte STOA a été ouvert pour vous. Le lien ci-dessous vous permet de définir votre mot de passe et d'activer le compte :",
        "action": "Activer le compte",
        "expiry": "Ce lien est à usage unique et valable jusqu'au {expires}.",
        "ignore": "Si vous n'attendiez pas ce compte, vous pouvez ignorer ce message.",
    },
    "it": {
        "subject": "STOA – Attiva il tuo account",
        "greeting": "Ciao {name},",
        "greeting_anonymous": "Ciao,",
        "intro": "è stato aperto un account STOA per te. Con il link seguente puoi impostare la password e attivare l'account:",
        "action": "Attiva l'account",
        "expiry": "Il link è utilizzabile una sola volta ed è valido fino al {expires}.",
        "ignore": "Se non ti aspettavi questo account, puoi ignorare questo messaggio.",
    },
    "en": {
        "subject": "STOA – Activate your account",
        "greeting": "Hello {name},",
        "greeting_anonymous": "Hello,",
        "intro": "a STOA account has been opened for you. Use the link below to choose your password and activate the account:",
        "action": "Activate account",
        "expiry": "The link can be used once and is valid until {expires}.",
        "ignore": "If you were not expecting this account, you can ignore this message.",
    },
}

ACCOUNT_INVITATION_DEFAULT_LOCALE = "de"


def account_invitation_message(
    *, activation_token: str, expires_at: str, full_name: str = "", locale: str | None = None
) -> tuple[str, str]:
    """Render the subject and HTML body of one activation email in one language."""
    copy = ACCOUNT_INVITATION_COPY.get(
        str(locale or "").strip().lower(),
        ACCOUNT_INVITATION_COPY[ACCOUNT_INVITATION_DEFAULT_LOCALE],
    )
    base = settings.app_base_url.rstrip("/")
    link = f"{base}/activate?token={quote(activation_token, safe='')}"
    name = full_name.strip()
    greeting = (
        copy["greeting"].format(name=escape(name)) if name else copy["greeting_anonymous"]
    )
    body = (
        f"<p>{greeting}</p>"
        f"<p>{copy['intro']}</p>"
        f'<p><a href="{escape(link, quote=True)}">{copy["action"]}</a></p>'
        f"<p>{copy['expiry'].format(expires=escape(expires_at))}</p>"
        f"<p>{copy['ignore']}</p>"
    )
    return copy["subject"], body


def send_account_invitation_email(
    recipient: str,
    *,
    activation_token: str,
    expires_at: str,
    full_name: str = "",
    locale: str | None = None,
    ses_client=None,
) -> None:
    """Deliver one single-use activation link to an invited account of any role.

    The token is readable only at issue time. A raised exception means undelivered:
    the caller must reissue rather than assume the invitee can still activate.
    """
    subject, body = account_invitation_message(
        activation_token=activation_token,
        expires_at=expires_at,
        full_name=full_name,
        locale=locale,
    )
    ses = ses_client or boto3.client("ses", region_name=settings.aws_region)
    ses.send_email(
        Source=settings.notification_email_sender,
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Html": {"Data": body}},
        },
    )
