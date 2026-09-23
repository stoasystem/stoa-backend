"""Closed contracts for the self-service password change verification code."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import re

from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from actor_helpers import install_actor_overrides
# The shared double already evaluates conditions and stores numbers the way the
# table returns them, which is everything the local one here was written for.
from fakes.dynamodb import FakeTable, as_stored as _as_stored
from stoa.config import Settings, get_settings
from stoa.routers import auth
from stoa.services import locale_service, password_change_code_service as codes


SERVICE_SOURCE = Path(codes.__file__).read_text(encoding="utf-8")
BASE_TIME = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


class RecordingSes:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_email(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "ses-message-1"}


class RejectingSes:
    """A mail provider that refuses every send, the way an unverified sender does."""

    def __init__(self) -> None:
        self.attempts: list[dict] = []

    def send_email(self, **kwargs):
        self.attempts.append(kwargs)
        raise ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "Email address not verified"}},
            "SendEmail",
        )


def _sent_code(ses: RecordingSes) -> str:
    html = ses.sent[-1]["Message"]["Body"]["Html"]["Data"]
    match = re.search(r"<strong>(\d{6})</strong>", html)
    assert match, "the delivered email must carry the code"
    return match.group(1)


# ---------------------------------------------------------------------------
# Service-level contracts
# ---------------------------------------------------------------------------

def test_code_is_six_digits_and_never_stored_in_the_clear():
    table = FakeTable()
    ses = RecordingSes()

    codes.issue("user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses)

    code = _sent_code(ses)
    assert len(code) == 6 and code.isdigit()
    stored = table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")]
    assert code not in str(stored)
    assert stored["code_digest"] != code
    assert stored["expires_at"] - stored["issued_at"] == 600


def test_code_is_single_use():
    table = FakeTable()
    ses = RecordingSes()
    codes.issue("user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses)
    code = _sent_code(ses)

    codes.verify_and_consume("user-1", code, now=BASE_TIME, table=table)

    with pytest.raises(codes.PasswordChangeCodeRejected):
        codes.verify_and_consume("user-1", code, now=BASE_TIME, table=table)


def test_code_expires_after_ten_minutes():
    table = FakeTable()
    ses = RecordingSes()
    codes.issue("user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses)
    code = _sent_code(ses)

    codes.verify_and_consume(
        "user-1", code, now=BASE_TIME + timedelta(seconds=599), table=table
    )

    table.rows.clear()
    ses.sent.clear()
    codes.issue("user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses)
    code = _sent_code(ses)
    with pytest.raises(codes.PasswordChangeCodeRejected):
        codes.verify_and_consume(
            "user-1", code, now=BASE_TIME + timedelta(seconds=600), table=table
        )


def test_a_wrong_code_is_rejected_and_bounded_by_attempts():
    table = FakeTable()
    ses = RecordingSes()
    codes.issue("user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses)
    code = _sent_code(ses)
    wrong = f"{(int(code) + 1) % 1000000:06d}"

    for _ in range(codes.MAX_VERIFY_ATTEMPTS):
        with pytest.raises(codes.PasswordChangeCodeRejected):
            codes.verify_and_consume("user-1", wrong, now=BASE_TIME, table=table)

    with pytest.raises(codes.PasswordChangeCodeRejected):
        codes.verify_and_consume("user-1", code, now=BASE_TIME, table=table)


class ReplacingTable(FakeTable):
    """Issue a fresh code the instant verification has read the live one.

    The interleaving the service has to survive: the snapshot a request
    validated is no longer the challenge sitting at `CURRENT` by the time that
    request writes.
    """

    def __init__(self, *, owner: str, replacement: str, at: datetime) -> None:
        super().__init__()
        self.owner = owner
        self.replacement = replacement
        self.at = at
        self.replacements = 0

    def get_item(self, *, Key, ConsistentRead=False):
        response = super().get_item(Key=Key, ConsistentRead=ConsistentRead)
        if Key["SK"] == "CURRENT" and "Item" in response and not self.replacements:
            self.replacements += 1
            codes.store_code(self.owner, self.replacement, now=self.at, table=self)
        return response


class BudgetSpendingTable(FakeTable):
    """Spend the whole attempt budget after verification has read its snapshot."""

    def __init__(self, *, spend_to: int) -> None:
        super().__init__()
        self.spend_to = spend_to
        self.spent = 0

    def get_item(self, *, Key, ConsistentRead=False):
        response = super().get_item(Key=Key, ConsistentRead=ConsistentRead)
        if Key["SK"] == "CURRENT" and "Item" in response and not self.spent:
            self.spent += 1
            self.rows[(Key["PK"], Key["SK"])]["attempts"] = _as_stored(self.spend_to)
        return response


def test_consumption_is_bound_to_the_challenge_that_was_verified():
    ses = RecordingSes()
    table = ReplacingTable(
        owner="user-1", replacement="654321", at=BASE_TIME + timedelta(seconds=1)
    )
    codes.issue("user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses)
    first = _sent_code(ses)

    with pytest.raises(codes.PasswordChangeCodeRejected):
        codes.verify_and_consume("user-1", first, now=BASE_TIME, table=table)

    row = table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")]
    assert "consumed_at" not in row, "the replacement was consumed without being presented"
    assert row["attempts"] == 0
    # The replacement is untouched, so the code its owner actually holds still works.
    codes.verify_and_consume(
        "user-1", "654321", now=BASE_TIME + timedelta(seconds=2), table=table
    )


def test_a_failed_attempt_is_not_charged_to_a_replacement_challenge():
    ses = RecordingSes()
    table = ReplacingTable(
        owner="user-1", replacement="654321", at=BASE_TIME + timedelta(seconds=1)
    )
    codes.issue("user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses)
    first = _sent_code(ses)
    wrong = f"{(int(first) + 1) % 1000000:06d}"

    with pytest.raises(codes.PasswordChangeCodeRejected):
        codes.verify_and_consume("user-1", wrong, now=BASE_TIME, table=table)

    row = table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")]
    assert row["attempts"] == 0, "a wrong guess at the old code spent the new code's budget"


def test_consumption_rechecks_attempt_budget_at_commit():
    ses = RecordingSes()
    table = BudgetSpendingTable(spend_to=codes.MAX_VERIFY_ATTEMPTS)
    codes.issue("user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses)
    code = _sent_code(ses)

    with pytest.raises(codes.PasswordChangeCodeRejected):
        codes.verify_and_consume("user-1", code, now=BASE_TIME, table=table)

    assert "consumed_at" not in table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")]


def test_a_concurrent_failed_attempt_still_leaves_the_right_code_usable():
    """Negative control: only an exhausted budget may refuse the commit."""
    ses = RecordingSes()
    table = BudgetSpendingTable(spend_to=codes.MAX_VERIFY_ATTEMPTS - 1)
    codes.issue("user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses)
    code = _sent_code(ses)

    codes.verify_and_consume("user-1", code, now=BASE_TIME, table=table)

    assert table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")]["consumed_at"] == int(
        BASE_TIME.timestamp()
    )


def test_a_wrong_guess_does_not_stop_the_right_code_that_follows():
    """Negative control: the ordinary retry an account makes after a typo."""
    table = FakeTable()
    ses = RecordingSes()
    codes.issue("user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses)
    code = _sent_code(ses)
    wrong = f"{(int(code) + 1) % 1000000:06d}"

    with pytest.raises(codes.PasswordChangeCodeRejected):
        codes.verify_and_consume("user-1", wrong, now=BASE_TIME, table=table)
    codes.verify_and_consume("user-1", code, now=BASE_TIME + timedelta(seconds=5), table=table)


def test_sends_are_limited_to_five_per_rolling_hour():
    table = FakeTable()
    ses = RecordingSes()

    for minute in range(codes.MAX_SENDS_PER_WINDOW):
        codes.issue(
            "user-1",
            "learner@example.com",
            now=BASE_TIME + timedelta(minutes=minute),
            table=table,
            ses_client=ses,
        )

    with pytest.raises(codes.PasswordChangeCodeRateLimited):
        codes.issue(
            "user-1",
            "learner@example.com",
            now=BASE_TIME + timedelta(minutes=59),
            table=table,
            ses_client=ses,
        )
    assert len(ses.sent) == codes.MAX_SENDS_PER_WINDOW

    codes.issue(
        "user-1",
        "learner@example.com",
        now=BASE_TIME + timedelta(minutes=61),
        table=table,
        ses_client=ses,
    )
    assert len(ses.sent) == codes.MAX_SENDS_PER_WINDOW + 1


def test_a_refused_send_never_reaches_ses_or_replaces_the_live_code():
    table = FakeTable()
    ses = RecordingSes()
    for minute in range(codes.MAX_SENDS_PER_WINDOW):
        codes.issue(
            "user-1",
            "learner@example.com",
            now=BASE_TIME + timedelta(minutes=minute),
            table=table,
            ses_client=ses,
        )
    live = dict(table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")])

    with pytest.raises(codes.PasswordChangeCodeRateLimited):
        codes.issue(
            "user-1",
            "learner@example.com",
            now=BASE_TIME + timedelta(minutes=10),
            table=table,
            ses_client=ses,
        )

    assert len(ses.sent) == codes.MAX_SENDS_PER_WINDOW
    assert table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")] == live


def test_a_failed_send_charges_nothing_and_leaves_the_live_code_alone():
    """The provider refusing is not the account's fault and must not cost it anything.

    Two separate things were being lost when SES refused: the quota slot, and
    the code the account might still be holding in its mailbox.
    """
    table = FakeTable()
    ses = RecordingSes()
    codes.issue("user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses)
    live_code = _sent_code(ses)
    live_row = dict(table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")])
    quota_row = dict(table.rows[("PASSWORD_CHANGE_QUOTA#user-1", "WINDOW")])

    for minute in range(1, 4):
        with pytest.raises(codes.PasswordChangeCodeDeliveryFailed):
            codes.issue(
                "user-1",
                "learner@example.com",
                now=BASE_TIME + timedelta(minutes=minute),
                table=table,
                ses_client=RejectingSes(),
            )

    assert table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")] == live_row
    assert (
        table.rows[("PASSWORD_CHANGE_QUOTA#user-1", "WINDOW")]["sends"]
        == quota_row["sends"]
    )
    # The code that was already delivered is still the one that works.
    codes.verify_and_consume(
        "user-1", live_code, now=BASE_TIME + timedelta(minutes=5), table=table
    )


def test_a_failed_send_never_carries_the_code_or_the_address_outward():
    table = FakeTable()
    rejecting = RejectingSes()

    with pytest.raises(codes.PasswordChangeCodeDeliveryFailed) as raised:
        codes.issue(
            "user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=rejecting
        )

    attempted = rejecting.attempts[-1]["Message"]["Body"]["Html"]["Data"]
    code = re.search(r"<strong>(\d{6})</strong>", attempted).group(1)
    chain = f"{raised.value!r}{raised.value.__cause__!r}{raised.value.__context__!r}"
    assert code not in chain
    assert "learner@example.com" not in chain


def test_the_quota_refund_only_gives_back_the_send_that_failed():
    """A refund must not reopen slots that earlier successful sends used up."""
    table = FakeTable()
    ses = RecordingSes()
    for minute in range(codes.MAX_SENDS_PER_WINDOW - 1):
        codes.issue(
            "user-1",
            "learner@example.com",
            now=BASE_TIME + timedelta(minutes=minute),
            table=table,
            ses_client=ses,
        )

    with pytest.raises(codes.PasswordChangeCodeDeliveryFailed):
        codes.issue(
            "user-1",
            "learner@example.com",
            now=BASE_TIME + timedelta(minutes=10),
            table=table,
            ses_client=RejectingSes(),
        )

    assert (
        len(table.rows[("PASSWORD_CHANGE_QUOTA#user-1", "WINDOW")]["sends"])
        == codes.MAX_SENDS_PER_WINDOW - 1
    )
    codes.issue(
        "user-1", "learner@example.com",
        now=BASE_TIME + timedelta(minutes=11), table=table, ses_client=ses,
    )
    with pytest.raises(codes.PasswordChangeCodeRateLimited):
        codes.issue(
            "user-1", "learner@example.com",
            now=BASE_TIME + timedelta(minutes=12), table=table, ses_client=ses,
        )


@pytest.mark.parametrize(
    ("locale", "subject_marker", "body_marker"),
    [
        ("de", "Bestätigungscode", "Passwort"),
        ("en", "Verification code", "verification code"),
        ("fr", "Code de vérification", "mot de passe"),
        ("it", "Codice di verifica", "password"),
    ],
)
def test_the_code_email_is_written_in_the_account_language(locale, subject_marker, body_marker):
    table = FakeTable()
    ses = RecordingSes()

    codes.issue(
        "user-1", "learner@example.com",
        locale=locale, now=BASE_TIME, table=table, ses_client=ses,
    )

    sent = ses.sent[-1]["Message"]
    assert subject_marker in sent["Subject"]["Data"]
    assert body_marker in sent["Body"]["Html"]["Data"]
    assert len(_sent_code(ses)) == 6


def test_every_supported_language_has_its_own_code_email():
    """Four languages, four distinct mails — no locale may quietly share another's."""
    subjects = {locale: codes._template(locale)[0] for locale in sorted(codes._EMAIL_TEMPLATES)}
    assert set(subjects) == {"de", "en", "fr", "it"}
    assert len(set(subjects.values())) == 4
    assert len({codes._template(locale)[1] for locale in subjects}) == 4


def test_an_unknown_language_falls_back_to_the_product_default():
    assert codes._template(None) == codes._template(locale_service.DEFAULT_LOCALE)
    assert codes._template("zz") == codes._template(locale_service.DEFAULT_LOCALE)
    assert codes._template("it-CH") == codes._template("it")


def test_send_quota_is_per_account():
    table = FakeTable()
    ses = RecordingSes()
    for minute in range(codes.MAX_SENDS_PER_WINDOW):
        codes.issue(
            "user-1", "one@example.com", now=BASE_TIME + timedelta(minutes=minute),
            table=table, ses_client=ses,
        )

    codes.issue("user-2", "two@example.com", now=BASE_TIME, table=table, ses_client=ses)

    assert len(ses.sent) == codes.MAX_SENDS_PER_WINDOW + 1


def test_comparison_is_constant_time_and_nothing_is_logged():
    assert "secrets.compare_digest(" in SERVICE_SOURCE
    assert "import logging" not in SERVICE_SOURCE
    assert "print(" not in SERVICE_SOURCE


def test_issuing_a_code_writes_it_to_no_log(caplog):
    table = FakeTable()
    ses = RecordingSes()
    with caplog.at_level("DEBUG"):
        codes.issue(
            "user-1", "learner@example.com", now=BASE_TIME, table=table, ses_client=ses
        )
    code = _sent_code(ses)

    assert code not in caplog.text
    assert "learner@example.com" not in caplog.text


def test_masked_recipient_keeps_the_address_out_of_the_response():
    assert codes.mask_recipient("learner@example.com") == "l******@example.com"


# ---------------------------------------------------------------------------
# Endpoint contracts
# ---------------------------------------------------------------------------

def _settings() -> Settings:
    return Settings(
        aws_region="eu-central-2",
        cognito_user_pool_id="pool-id",
        cognito_student_client_id="student-client",
        cognito_parent_client_id="parent-client",
        cognito_teacher_client_id="teacher-client",
        cognito_admin_client_id="admin-client",
    )


class FakeCognito:
    def __init__(self, *, current_password: str = "OldPass123") -> None:
        self.current_password = current_password
        self.changed: list[dict] = []

    @staticmethod
    def _not_authorized() -> ClientError:
        return ClientError(
            {"Error": {"Code": "NotAuthorizedException", "Message": "bad password"}},
            "Cognito",
        )

    def initiate_auth(self, **kwargs):
        if kwargs["AuthParameters"]["PASSWORD"] != self.current_password:
            raise self._not_authorized()
        return {"AuthenticationResult": {"AccessToken": "access-token"}}

    def change_password(self, **kwargs):
        if kwargs["PreviousPassword"] != self.current_password:
            raise self._not_authorized()
        self.changed.append(kwargs)
        self.current_password = kwargs["ProposedPassword"]
        return {}


@pytest.fixture
def password_change_client(monkeypatch):
    table = FakeTable()
    ses = RecordingSes()
    provider = FakeCognito()
    monkeypatch.setattr(auth, "_get_cognito", lambda _settings: provider)
    monkeypatch.setattr(
        auth.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "email": "learner@example.com",
            "role": "student",
        },
    )
    monkeypatch.setattr(codes, "get_table", lambda: table)
    monkeypatch.setattr(codes.boto3, "client", lambda *_args, **_kwargs: ses)

    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_settings] = _settings
    install_actor_overrides(app, {"sub": "user-1", "role": "student"})
    client = TestClient(app)
    client.headers.update({"Authorization": "Bearer access-token"})
    return client, table, ses, provider


def test_self_service_password_change_completes(password_change_client):
    client, _table, ses, provider = password_change_client

    requested = client.post(
        "/auth/password-change/request", json={"currentPassword": "OldPass123"}
    )
    assert requested.status_code == 200
    assert requested.json()["maskedRecipient"] == "l******@example.com"
    assert requested.json()["status"] == "sent"

    confirmed = client.post(
        "/auth/password-change/confirm",
        json={
            "currentPassword": "OldPass123",
            "code": _sent_code(ses),
            "newPassword": "BrandNew123",
        },
    )

    assert confirmed.status_code == 200
    assert confirmed.json() == {"status": "changed"}
    assert provider.changed[0]["ProposedPassword"] == "BrandNew123"


def test_a_wrong_current_password_sends_no_code(password_change_client):
    client, _table, ses, _provider = password_change_client

    response = client.post(
        "/auth/password-change/request", json={"currentPassword": "WrongPass123"}
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "password_change_credentials_invalid"
    assert ses.sent == []


def test_a_weak_new_password_is_refused_before_the_code_is_spent(password_change_client):
    client, _table, ses, provider = password_change_client
    client.post("/auth/password-change/request", json={"currentPassword": "OldPass123"})
    code = _sent_code(ses)

    rejected = client.post(
        "/auth/password-change/confirm",
        json={"currentPassword": "OldPass123", "code": code, "newPassword": "weakpass"},
    )
    assert rejected.status_code == 422

    accepted = client.post(
        "/auth/password-change/confirm",
        json={"currentPassword": "OldPass123", "code": code, "newPassword": "BrandNew123"},
    )
    assert accepted.status_code == 200
    assert provider.changed


def test_a_code_cannot_be_replayed_through_the_endpoint(password_change_client):
    client, _table, ses, _provider = password_change_client
    client.post("/auth/password-change/request", json={"currentPassword": "OldPass123"})
    code = _sent_code(ses)
    body = {"currentPassword": "OldPass123", "code": code, "newPassword": "BrandNew123"}

    assert client.post("/auth/password-change/confirm", json=body).status_code == 200

    replay = client.post(
        "/auth/password-change/confirm",
        json={"currentPassword": "BrandNew123", "code": code, "newPassword": "ThirdPass123"},
    )
    assert replay.status_code == 400
    assert replay.json()["detail"]["code"] == "password_change_verification_failed"


def test_wrong_and_expired_codes_answer_with_identical_bytes(password_change_client):
    """A caller must not be able to tell a bad guess from a stale code."""
    client, table, ses, _provider = password_change_client

    client.post("/auth/password-change/request", json={"currentPassword": "OldPass123"})
    code = _sent_code(ses)
    wrong_code = f"{(int(code) + 7) % 1000000:06d}"
    wrong = client.post(
        "/auth/password-change/confirm",
        json={
            "currentPassword": "OldPass123",
            "code": wrong_code,
            "newPassword": "BrandNew123",
        },
    )

    row = table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")]
    row["expires_at"] = row["issued_at"]
    row["attempts"] = 0
    expired = client.post(
        "/auth/password-change/confirm",
        json={"currentPassword": "OldPass123", "code": code, "newPassword": "BrandNew123"},
    )

    assert wrong.status_code == expired.status_code == 400
    assert wrong.content == expired.content
    assert wrong.headers.get("content-type") == expired.headers.get("content-type")


def test_the_send_limit_is_enforced_through_the_endpoint(password_change_client):
    client, _table, ses, _provider = password_change_client
    body = {"currentPassword": "OldPass123"}

    for _ in range(codes.MAX_SENDS_PER_WINDOW):
        assert client.post("/auth/password-change/request", json=body).status_code == 200

    limited = client.post("/auth/password-change/request", json=body)

    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "password_change_code_rate_limited"
    assert len(ses.sent) == codes.MAX_SENDS_PER_WINDOW


def test_a_mail_provider_outage_answers_503_and_costs_the_account_nothing(
    password_change_client, monkeypatch
):
    """A refused send used to surface as a 500 with the quota already spent."""
    client, table, ses, _provider = password_change_client
    body = {"currentPassword": "OldPass123"}
    assert client.post("/auth/password-change/request", json=body).status_code == 200
    live_code = _sent_code(ses)
    live_row = dict(table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")])

    monkeypatch.setattr(codes.boto3, "client", lambda *_a, **_k: RejectingSes())
    for _ in range(codes.MAX_SENDS_PER_WINDOW + 2):
        failed = client.post("/auth/password-change/request", json=body)
        assert failed.status_code == 503
        assert failed.json()["detail"]["code"] == "password_change_code_delivery_failed"

    assert table.rows[("PASSWORD_CHANGE_CODE#user-1", "CURRENT")] == live_row
    monkeypatch.setattr(codes.boto3, "client", lambda *_a, **_k: ses)
    assert client.post("/auth/password-change/request", json=body).status_code == 200

    # The code from before the outage is still the one that was mailed out.
    assert (
        client.post(
            "/auth/password-change/confirm",
            json={
                "currentPassword": "OldPass123",
                "code": live_code,
                "newPassword": "BrandNew123",
            },
        ).status_code
        == 400
    )


def test_a_failed_send_leaks_nothing_through_the_response(password_change_client, monkeypatch):
    client, _table, _ses, _provider = password_change_client
    monkeypatch.setattr(codes.boto3, "client", lambda *_a, **_k: RejectingSes())

    failed = client.post(
        "/auth/password-change/request", json={"currentPassword": "OldPass123"}
    )

    assert failed.status_code == 503
    assert "learner@example.com" not in failed.text
    assert "MessageRejected" not in failed.text


def test_the_endpoint_mails_in_the_language_stored_on_the_account(
    password_change_client, monkeypatch
):
    client, _table, ses, _provider = password_change_client
    # Nothing in the request says a language, so the stored preference decides.
    monkeypatch.setattr(auth.locale_service, "request_locale", lambda: None)
    monkeypatch.setattr(
        auth.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "email": "learner@example.com",
            "role": "student",
            "preferred_locale": "it",
        },
    )

    assert (
        client.post(
            "/auth/password-change/request", json={"currentPassword": "OldPass123"}
        ).status_code
        == 200
    )

    assert "Codice di verifica" in ses.sent[-1]["Message"]["Subject"]["Data"]


def test_摘要成本不会被悄悄调低():
    """把轮数从 100_000 改到 1，其余测试全都照绿——只有这条会说话。

    成本是这套摘要的全部安全性所在，而它不体现在任何行为断言里：
    存的仍然不是明文，比对仍然对得上，耗时差没有任何断言在看。
    """
    assert codes._DIGEST_ITERATIONS >= 100_000
