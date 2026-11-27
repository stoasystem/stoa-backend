"""One-off emails: activation links and codes, sent once each time they are asked for (#685).

These are not notifications. The recipient cannot turn them off, they carry no
unsubscribe line, and nothing checks whether one went out before: every request
sends a fresh one. They share only the SES send (`ses_email`) and the layout
(`email_layout`) with the notification emails, never preferences or unsubscribe.
"""

from functools import partial
from typing import Callable
from urllib.parse import quote

from stoa import config
from stoa.services import email_layout, locale_service, message_catalog, ses_email


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
    return ses_email.send_plain(recipient, email)


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
