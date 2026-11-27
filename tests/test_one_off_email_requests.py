"""The one-off emails reach SES exactly as they did before they had a module of their own (#685).

The password-change code, the account invitation and the teacher invitation are
recorded request by request - every SES argument, in every language and with no
language named - in `fixtures/one_off_email_requests_685.json`. The snapshot was
taken from the code before the move; any change to what SES receives fails here.

A wording change that is meant shows up here too. Regenerate the snapshot then,
and read its diff before committing it:

    STOA_WRITE_ONE_OFF_EMAIL_SNAPSHOT=1 pytest tests/test_one_off_email_requests.py
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from stoa import aws, config
from stoa.aws import Kind
from stoa.services import one_off_email, password_change_code_service

SNAPSHOT = Path(__file__).parent / "fixtures" / "one_off_email_requests_685.json"
SERVICES = Path(__file__).resolve().parents[1] / "src" / "stoa" / "services"
EXPIRES_AT = "2026-07-21T12:00:00+00:00"
# Every language STOA speaks, none named, and one it does not speak.
LOCALES = ("de", "fr", "it", "en", None, "xx")
ROLES = ("student", "parent", "teacher", "admin", None)


class _RecordingSes:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_email(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "m-1"}


def _send_code(locale):
    password_change_code_service.send_code_email("code@example.test", "042137", locale=locale)


def _send_account_invitation(locale, role):
    # The console and the agent both mail an invitation through this (#384).
    deliver = one_off_email.account_invitation_delivery(locale)
    deliver(
        "invitee@example.test",
        activation_token="token/with+chars",
        expires_at=EXPIRES_AT,
        full_name="Anna Muster",
        role=role,
    )


def _send_teacher_invitation(locale):
    one_off_email.send_teacher_invitation_email(
        "candidate@example.test",
        activation_token="token/with+chars",
        expires_at=EXPIRES_AT,
        full_name="Candidate Teacher",
        locale=locale,
    )


CASES = {
    **{f"password_code.{locale}": (_send_code, (locale,)) for locale in LOCALES},
    **{
        f"account_invitation.{locale}.{role}": (_send_account_invitation, (locale, role))
        for locale in LOCALES
        for role in ROLES
    },
    **{f"teacher_invitation.{locale}": (_send_teacher_invitation, (locale,)) for locale in LOCALES},
}


def _request(case: str) -> dict:
    config.install(
        config.settings().model_copy(
            update={
                "app_base_url": "https://app.example.test/",
                "email_logo_url": "https://cdn.example.test/logo.png",
                "notification_email_sender": "noreply@example.test",
                "notification_email_reply_to": "help@example.test",
            }
        )
    )
    ses = _RecordingSes()
    aws.install({Kind.SES: ses})
    send, args = CASES[case]
    send(*args)
    [request] = ses.sent
    return request


def _snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_write_the_snapshot_when_asked():
    if os.environ.get("STOA_WRITE_ONE_OFF_EMAIL_SNAPSHOT") != "1":
        pytest.skip("set STOA_WRITE_ONE_OFF_EMAIL_SNAPSHOT=1 to rewrite the snapshot")
    requests = {case: _request(case) for case in CASES}
    with SNAPSHOT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(requests, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")


def test_the_snapshot_covers_every_case():
    assert sorted(_snapshot()) == sorted(CASES)


@pytest.mark.parametrize("case", sorted(CASES))
def test_ses_receives_the_same_request_as_before(case):
    assert _request(case) == _snapshot()[case]


def _stoa_imports(module: str) -> set[str]:
    tree = ast.parse((SERVICES / f"{module}.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("stoa"):
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names if alias.name.startswith("stoa")}
    return found


def test_one_off_emails_reach_nothing_of_notifications():
    """No preferences, no unsubscribe, no "only once": only the SES send and the layout."""
    assert _stoa_imports("one_off_email") == {
        "stoa.config",
        "stoa.services.email_layout",
        "stoa.services.locale_service",
        "stoa.services.message_catalog",
        "stoa.services.ses_email",
    }


def test_the_shared_ses_send_knows_nothing_of_either_side():
    assert _stoa_imports("ses_email") == {
        "stoa.aws",
        "stoa.config",
        "stoa.aws.Kind",
        "stoa.services.email_layout",
    }
