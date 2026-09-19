"""Single-use email verification codes for self-service password changes.

Nothing in this module may log or return the code itself: it is only ever
readable at issue time, on its way to the account's own mailbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import secrets

import boto3
from botocore.exceptions import ClientError

from stoa.config import settings
from stoa.db.dynamodb import get_table
from stoa.services import locale_service


CODE_DIGITS = 6
CODE_TTL_SECONDS = 600
SEND_WINDOW_SECONDS = 3600
MAX_SENDS_PER_WINDOW = 5
MAX_VERIFY_ATTEMPTS = 5

_DIGEST_ITERATIONS = 100_000
_QUOTA_WRITE_ATTEMPTS = 3
_CODE_ENTITY = "password_change_code"
_QUOTA_ENTITY = "password_change_send_quota"


class PasswordChangeCodeRateLimited(RuntimeError):
    """Too many codes were requested for one account inside the send window."""


class PasswordChangeCodeDeliveryFailed(RuntimeError):
    """The code could not be handed to the mail provider.

    Raised only when nothing was charged and nothing was replaced: the send
    quota is given back and any code still outstanding stays usable.
    """


class PasswordChangeCodeRejected(RuntimeError):
    """The presented code is not usable.

    Every rejection reason — wrong, expired, already used, never issued,
    out of attempts — raises this one error with no distinguishing detail.
    Callers must answer all of them with the same response.
    """


@dataclass(frozen=True, slots=True)
class IssuedCode:
    expires_at: int
    masked_recipient: str


def _now_epoch(now: datetime | None = None) -> int:
    return int((now or datetime.now(UTC)).timestamp())


def _table(table=None):
    return table if table is not None else get_table()


def _int(value: object, default: int = 0) -> int:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, Decimal)):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return default


def _conditional_check_failed(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def _code_key(user_id: str) -> dict[str, str]:
    return {"PK": f"PASSWORD_CHANGE_CODE#{user_id}", "SK": "CURRENT"}


def _quota_key(user_id: str) -> dict[str, str]:
    return {"PK": f"PASSWORD_CHANGE_QUOTA#{user_id}", "SK": "WINDOW"}


def _required_user_id(user_id: str) -> str:
    value = str(user_id or "").strip()
    if not value:
        raise ValueError("user_id is required")
    return value


def generate_code() -> str:
    """Draw one uniformly random six-digit code from the system CSPRNG."""

    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def _digest(code: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        str(code).encode("utf-8"),
        bytes.fromhex(salt),
        _DIGEST_ITERATIONS,
    ).hex()


def mask_recipient(email: str) -> str:
    """Show only enough of the address to pick the right inbox."""

    address = str(email or "").strip()
    local, separator, domain = address.partition("@")
    if not separator or not local:
        return "***"
    head = local[0]
    return f"{head}{'*' * max(len(local) - 1, 1)}@{domain}"


def admit_send(user_id: str, *, now: datetime | None = None, table=None) -> None:
    """Admit one send inside a rolling window, or refuse the account's request.

    The window is the last `SEND_WINDOW_SECONDS`, not a calendar hour, so the
    limit cannot be doubled by waiting for a boundary. Write contention is
    refused rather than admitted.
    """

    owner = _required_user_id(user_id)
    moment = _now_epoch(now)
    client = _table(table)
    key = _quota_key(owner)
    for _ in range(_QUOTA_WRITE_ATTEMPTS):
        stored = (client.get_item(Key=key, ConsistentRead=True) or {}).get("Item") or {}
        version = _int(stored.get("version"))
        recent = [
            value
            for value in (_int(entry) for entry in (stored.get("sends") or []))
            if value > 0 and moment - value < SEND_WINDOW_SECONDS
        ]
        if len(recent) >= MAX_SENDS_PER_WINDOW:
            raise PasswordChangeCodeRateLimited("password change code send limit reached")
        recent.append(moment)
        expires_at = moment + SEND_WINDOW_SECONDS
        try:
            if version == 0:
                client.put_item(
                    Item={
                        **key,
                        "entity_type": _QUOTA_ENTITY,
                        "sends": recent,
                        "version": 1,
                        "expires_at": expires_at,
                    },
                    ConditionExpression="attribute_not_exists(PK)",
                )
            else:
                client.update_item(
                    Key=key,
                    UpdateExpression=(
                        "SET #sends = :sends, #version = :next_version, #expires_at = :expires_at"
                    ),
                    ConditionExpression="#version = :version",
                    ExpressionAttributeNames={
                        "#sends": "sends",
                        "#version": "version",
                        "#expires_at": "expires_at",
                    },
                    ExpressionAttributeValues={
                        ":sends": recent,
                        ":version": version,
                        ":next_version": version + 1,
                        ":expires_at": expires_at,
                    },
                )
            return
        except ClientError as exc:
            if not _conditional_check_failed(exc):
                raise
    raise PasswordChangeCodeRateLimited("password change code send limit reached")


def release_send(user_id: str, sent_at: int, *, table=None) -> None:
    """Give back one admitted send that never left the building.

    Best effort on purpose: the caller is already on a failure path, and a lost
    refund only costs the account one slot of its hourly quota, while a raised
    error here would hide why the send actually failed.
    """

    owner = _required_user_id(user_id)
    client = _table(table)
    key = _quota_key(owner)
    for _ in range(_QUOTA_WRITE_ATTEMPTS):
        stored = (client.get_item(Key=key, ConsistentRead=True) or {}).get("Item") or {}
        version = _int(stored.get("version"))
        sends = [_int(entry) for entry in (stored.get("sends") or [])]
        if version == 0 or sent_at not in sends:
            return
        sends.remove(sent_at)
        try:
            client.update_item(
                Key=key,
                UpdateExpression="SET #sends = :sends, #version = :next_version",
                ConditionExpression="#version = :version",
                ExpressionAttributeNames={"#sends": "sends", "#version": "version"},
                ExpressionAttributeValues={
                    ":sends": sends,
                    ":version": version,
                    ":next_version": version + 1,
                },
            )
            return
        except ClientError as exc:
            if not _conditional_check_failed(exc):
                return


def store_code(user_id: str, code: str, *, now: datetime | None = None, table=None) -> int:
    """Persist only the derived digest, replacing any code already outstanding."""

    owner = _required_user_id(user_id)
    moment = _now_epoch(now)
    expires_at = moment + CODE_TTL_SECONDS
    salt = secrets.token_hex(16)
    _table(table).put_item(
        Item={
            **_code_key(owner),
            "entity_type": _CODE_ENTITY,
            "code_digest": _digest(code, salt),
            "salt": salt,
            "issued_at": moment,
            "expires_at": expires_at,
            "attempts": 0,
        }
    )
    return expires_at


def verify_and_consume(
    user_id: str,
    code: str,
    *,
    now: datetime | None = None,
    table=None,
) -> None:
    """Accept one presented code exactly once, or raise the single rejection.

    Consumption is a conditional write, so two concurrent uses of the same code
    cannot both succeed.
    """

    owner = _required_user_id(user_id)
    moment = _now_epoch(now)
    client = _table(table)
    key = _code_key(owner)
    stored = (client.get_item(Key=key, ConsistentRead=True) or {}).get("Item") or {}
    if not stored or stored.get("consumed_at"):
        raise PasswordChangeCodeRejected()
    if _int(stored.get("attempts")) >= MAX_VERIFY_ATTEMPTS:
        raise PasswordChangeCodeRejected()
    salt = str(stored.get("salt") or "")
    expected = str(stored.get("code_digest") or "")
    presented = str(code or "")
    if not salt or not expected or not presented.isdigit() or len(presented) != CODE_DIGITS:
        _record_failed_attempt(client, key)
        raise PasswordChangeCodeRejected()
    if not secrets.compare_digest(_digest(presented, salt), expected):
        _record_failed_attempt(client, key)
        raise PasswordChangeCodeRejected()
    if moment >= _int(stored.get("expires_at")):
        raise PasswordChangeCodeRejected()
    try:
        client.update_item(
            Key=key,
            UpdateExpression="SET #consumed_at = :consumed_at",
            ConditionExpression="attribute_not_exists(#consumed_at)",
            ExpressionAttributeNames={"#consumed_at": "consumed_at"},
            ExpressionAttributeValues={":consumed_at": moment},
        )
    except ClientError as exc:
        if _conditional_check_failed(exc):
            raise PasswordChangeCodeRejected() from exc
        raise


def _record_failed_attempt(client, key: dict[str, str]) -> None:
    client.update_item(
        Key=key,
        UpdateExpression="ADD #attempts :one",
        ExpressionAttributeNames={"#attempts": "attempts"},
        ExpressionAttributeValues={":one": 1},
    )


_EMAIL_TEMPLATES: dict[str, tuple[str, str]] = {
    "de": (
        "STOA - Bestätigungscode für Ihr neues Passwort",
        "<p>Hallo,</p>"
        "<p>für die Änderung Ihres STOA-Passworts lautet Ihr "
        "Bestätigungscode:</p><p><strong>{code}</strong></p>"
        "<p>Der Code ist {minutes} Minuten lang und nur einmal gültig.</p>"
        "<p>Wenn Sie das nicht angefordert haben, ändern Sie Ihr "
        "Passwort nicht und melden Sie sich bei uns.</p>",
    ),
    "en": (
        "STOA - Verification code for your new password",
        "<p>Hello,</p>"
        "<p>here is your verification code for changing your STOA "
        "password:</p><p><strong>{code}</strong></p>"
        "<p>The code is valid for {minutes} minutes and can be used once.</p>"
        "<p>If you did not request this, do not change your password and "
        "get in touch with us.</p>",
    ),
    "fr": (
        "STOA - Code de vérification pour votre nouveau mot de passe",
        "<p>Bonjour,</p>"
        "<p>voici votre code de vérification pour modifier votre mot de passe "
        "STOA :</p><p><strong>{code}</strong></p>"
        "<p>Le code est valable {minutes} minutes et ne peut servir qu'une fois.</p>"
        "<p>Si vous n'êtes pas à l'origine de cette demande, ne modifiez pas "
        "votre mot de passe et contactez-nous.</p>",
    ),
    "it": (
        "STOA - Codice di verifica per la tua nuova password",
        "<p>Ciao,</p>"
        "<p>ecco il tuo codice di verifica per modificare la password "
        "STOA:</p><p><strong>{code}</strong></p>"
        "<p>Il codice è valido per {minutes} minuti e può essere usato una sola volta.</p>"
        "<p>Se non hai richiesto tu questa modifica, non cambiare la password "
        "e contattaci.</p>",
    ),
}


def _template(locale: str | None) -> tuple[str, str]:
    """Pick the account's language, falling back to the product default.

    The fallback is `locale_service.DEFAULT_LOCALE`, the same one the API
    answers in when a profile carries no preference, so a mail never lands in
    a language the rest of the product would not have used either.
    """

    try:
        resolved = locale_service.normalize_locale(locale)
    except ValueError:
        resolved = locale_service.DEFAULT_LOCALE
    return _EMAIL_TEMPLATES.get(resolved, _EMAIL_TEMPLATES[locale_service.DEFAULT_LOCALE])


def send_code_email(recipient: str, code: str, *, locale: str | None = None, ses_client=None) -> None:
    """Deliver the code to the account's own mailbox and nowhere else."""

    ses = ses_client or boto3.client("ses", region_name=settings.aws_region)
    minutes = CODE_TTL_SECONDS // 60
    subject, body = _template(locale)
    ses.send_email(
        Source=settings.notification_email_sender,
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Html": {"Data": body.format(code=code, minutes=minutes)}},
        },
    )


def issue(
    user_id: str,
    email: str,
    *,
    locale: str | None = None,
    now: datetime | None = None,
    table=None,
    ses_client=None,
) -> IssuedCode:
    """Admit, mint, deliver and only then store one code for the account.

    The send is attempted before the new digest replaces the old one, and an
    admitted send that the provider refuses is handed back. A failing mail
    provider therefore costs the account nothing: no quota, and no loss of a
    code that was already on its way to the mailbox.
    """

    owner = _required_user_id(user_id)
    recipient = str(email or "").strip()
    if not recipient:
        raise ValueError("recipient email is required")
    # One pinned instant, so the refund removes the exact stamp that was admitted.
    pinned = now or datetime.now(UTC)
    moment = _now_epoch(pinned)
    admit_send(owner, now=pinned, table=table)
    code = generate_code()
    try:
        send_code_email(recipient, code, locale=locale, ses_client=ses_client)
    except Exception:
        release_send(owner, moment, table=table)
        # `from None`: the provider error names the recipient, and nothing that
        # renders an exception chain may pick that up.
        raise PasswordChangeCodeDeliveryFailed("verification code could not be sent") from None
    expires_at = store_code(owner, code, now=pinned, table=table)
    return IssuedCode(expires_at=expires_at, masked_recipient=mask_recipient(recipient))
