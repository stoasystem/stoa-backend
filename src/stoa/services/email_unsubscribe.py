"""Unsubscribe links and headers for notification emails (#363).

Three kinds of email recur or notify, and each can be stopped from the email
itself: the parent's weekly report, the teacher's dispatch reminder and the
notification digest. One-off emails (account and teacher activation, password
code) carry nothing from here.

A link holds a token naming one recipient and one kind of email, signed with
HMAC-SHA256. It reveals the account id, never the address. It does not expire:
an email can be opened months later, and a leaked token can only stop one kind
of email for one person.

The signing key is derived from the authorization audit keyring, which every
deployment already holds, under a label of its own so neither use can stand in
for the other. A token names the key id it was signed with; a token signed with
a key that has since left the keyring (active or previous) stops working, so a
rotation should keep the old key among the previous ones.

Every refusal - a broken token, a signature over another person or kind, an
unknown kind, a key we no longer hold, an account deleted since - is the one
`email_unsubscribe_link_invalid`.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass
from enum import StrEnum
from html import escape
from urllib.parse import quote

from stoa import config
from stoa.config import validate_authorization_audit_keyring
from stoa.services import locale_service, message_catalog
from stoa.services.notification_errors import NotificationErrorCode, NotificationViolation

_KEY_LABEL = b"stoa.email-unsubscribe.v1"
ONE_CLICK_PATH = "/notifications/email-unsubscribe"
PAGE_PATH = "/unsubscribe"


class EmailKind(StrEnum):
    WEEKLY_REPORT = "weekly_report"
    DISPATCH_REMINDER = "dispatch_reminder"
    NOTIFICATION_DIGEST = "notification_digest"


@dataclass(frozen=True, slots=True)
class UnsubscribeTarget:
    user_id: str
    kind: EmailKind


def _keyring() -> tuple[tuple[str, bytes], ...]:
    """(key id, secret) pairs, the active one first."""
    settings = config.settings()
    active, previous = validate_authorization_audit_keyring(
        settings.authorization_audit_active_key_id,
        settings.authorization_audit_active_key,
        settings.authorization_audit_previous_keys,
        allow_development_default=not settings.is_production,
    )
    return tuple((key.key_id, key.secret) for key in (active, *previous))


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signature(secret: bytes, body: str) -> bytes:
    key = hmac.new(secret, _KEY_LABEL, hashlib.sha256).digest()
    return hmac.new(key, body.encode("ascii"), hashlib.sha256).digest()


def issue_token(user_id: str, kind: EmailKind) -> str:
    key_id, secret = _keyring()[0]
    payload = {"c": EmailKind(kind).value, "k": key_id, "u": str(user_id)}
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{body}.{_b64(_signature(secret, body))}"


def invalid_link() -> NotificationViolation:
    return NotificationViolation(NotificationErrorCode.EMAIL_UNSUBSCRIBE_LINK_INVALID)


def read_token(token: str) -> UnsubscribeTarget:
    """The recipient and kind a token was issued for; any doubt is the one refusal."""
    body, dot, signature_text = str(token or "").partition(".")
    if not body or not dot or not signature_text:
        raise invalid_link()
    try:
        payload = json.loads(_unb64(body))
        presented = _unb64(signature_text)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise invalid_link() from exc
    if not isinstance(payload, dict):
        raise invalid_link()
    keys = dict(_keyring())
    secret = keys.get(payload.get("k")) if isinstance(payload.get("k"), str) else None
    if secret is None or not hmac.compare_digest(_signature(secret, body), presented):
        raise invalid_link()
    user_id, kind = payload.get("u"), payload.get("c")
    if not isinstance(user_id, str) or not user_id or not isinstance(kind, str) or kind not in set(EmailKind):
        raise invalid_link()
    return UnsubscribeTarget(user_id, EmailKind(kind))


def page_url(user_id: str, kind: EmailKind) -> str:
    """The frontend page the link in the body opens; it confirms and can undo."""
    token = quote(issue_token(user_id, kind), safe="")
    return f"{config.settings().app_base_url.rstrip('/')}{PAGE_PATH}?token={token}"


def one_click_url(user_id: str, kind: EmailKind) -> str:
    """The API address a mail client POSTs to under RFC 8058."""
    token = quote(issue_token(user_id, kind), safe="")
    return f"{config.settings().api_base_url.rstrip('/')}{ONE_CLICK_PATH}?token={token}"


def headers(user_id: str, kind: EmailKind) -> list[dict[str, str]]:
    """`List-Unsubscribe` with one-click (RFC 8058), as SESv2 takes headers."""
    return [
        {"Name": "List-Unsubscribe", "Value": f"<{one_click_url(user_id, kind)}>"},
        {"Name": "List-Unsubscribe-Post", "Value": "List-Unsubscribe=One-Click"},
    ]


def footer_html(user_id: str, kind: EmailKind, locale: str | None) -> str:
    lang = locale or locale_service.DEFAULT_LOCALE
    reason = escape(message_catalog.text(f"email.unsubscribe.reason.{EmailKind(kind).value}", lang))
    action = escape(message_catalog.text("email.unsubscribe.action", lang))
    link = escape(page_url(user_id, kind), quote=True)
    return (
        '<p style="font-size:12px;color:#6b7280">'
        f'{reason} <a href="{link}">{action}</a></p>'
    )


def with_footer(html: str, footer: str) -> str:
    """The footer at the end of the body: before `</body>` when there is one."""
    index = html.lower().rfind("</body>")
    if index == -1:
        return html + footer
    return html[:index] + footer + html[index:]
