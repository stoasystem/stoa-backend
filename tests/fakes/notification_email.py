"""The email channel's send, for tests about the weekly report rather than about the channel (#687).

The weekly report service tells the notification package that a report is
ready, and the package sends it through the only-once ledger
(`stoa.services.notifications._email.send_once`). Report tests that run over
their own table doubles hold no ledger, so they swap that one send for theirs.
The preference check and everything before the send stay real. The channel
itself - footer, headers, ledger - is tested in
`tests/test_notification_email_channel.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from stoa.services import email_layout, ses_email
from stoa.services.notifications import _email


def install_send(monkeypatch: pytest.MonkeyPatch, send: Callable[..., Any]) -> None:
    """Send with `send(recipient, html, subject=...)`: the body as the report service wrote it.

    What `send` returns, when it is a ledger status, is the status; anything
    else is `accepted`. Whatever it raises fails the email.
    """

    def send_once(**kwargs: Any) -> str:
        status = send(kwargs["recipient"], kwargs["html"], subject=kwargs["subject"])
        return status if isinstance(status, str) else _email.ACCEPTED

    monkeypatch.setattr(_email, "send_once", send_once)


def _plain(recipient: str, html: str, *, subject: str) -> None:
    ses_email.send_plain(
        recipient,
        email_layout.Rendered(subject=subject, html=html, text=email_layout.to_text(html)),
    )


def install_plain_send(monkeypatch: pytest.MonkeyPatch) -> None:
    """Send the body as written through SES v1 (`Kind.SES`), with no ledger, footer or headers."""
    install_send(monkeypatch, _plain)
