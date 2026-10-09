"""Signing out ends one sign-in, not every sign-in the account has.

`POST /auth/logout` used to write one cut-off instant per *account* and then call
Cognito's `GlobalSignOut`. Both are scoped to the person, not to the login: the
cut-off refuses every token issued before that instant, and tokens issued before
that instant are exactly the ones belonging to whatever other device signed in
earlier. Signing out of a phone signed the laptop out too, and because the
browser gives up on the request after eight seconds while the server carries on,
a sign-out still in flight could void the session the same person had just
opened by signing back in.

The scope now comes from the token: Cognito's `origin_jti` names the sign-in, and
every access token minted from one refresh token - every renewal, every tab
sharing it - carries the same value. The four tests below are the four promises
in issue #63, one each.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from jose import jwt
import pytest

from fakes.dynamodb import FakeTable
from security.conftest import FakeAsyncJwksTransport
from stoa.config import Settings, get_settings
from stoa.db.repositories import identity_repo
from stoa import deps
from stoa.deps import get_actor, get_identity_repository, get_jwks_key_provider
from stoa.routers import auth
from stoa.security.jwks import JwksKeyProvider
from stoa.security.tokens import VerifiedAccessToken


ISSUER_SUBJECT = "subject-1"
USER_ID = "student-1"
PROFILE: dict[str, Any] = {
    "user_id": USER_ID,
    "email": "student@example.com",
    "name": "Student",
    "role": "student",
    "account_status": "active",
    "registration_command": "admin_assignment",
    "registration_role": "student",
    "preferred_locale": "en-CH",
}


class _Provider:
    """Records every provider call and answers with scripted token material."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sign_in_result: dict[str, Any] = {}
        self.refresh_result: dict[str, Any] = {}
        # How many of the next `revoke_token` calls refuse before one succeeds.
        self.revoke_failures = 0

    def initiate_auth(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("initiate_auth", kwargs))
        if kwargs.get("AuthFlow") == "REFRESH_TOKEN_AUTH":
            return {"AuthenticationResult": dict(self.refresh_result)}
        return {"AuthenticationResult": dict(self.sign_in_result)}

    def revoke_token(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("revoke_token", kwargs))
        if self.revoke_failures:
            self.revoke_failures -= 1
            raise ClientError(
                {"Error": {"Code": "TooManyRequestsException", "Message": "slow down"}},
                "RevokeToken",
            )
        return {}

    def global_sign_out(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("global_sign_out", kwargs))
        return {}

    def operations(self) -> list[str]:
        return [operation for operation, _ in self.calls]


class _IdentityRepository:
    """Local authority from memory; sign-in rows through the real repository.

    The binding, fence, profile and grants are fixtures - this card changes none
    of them. The four session methods deliberately are *not* fixtures: they call
    the production functions against the shared table double, so the keys those
    functions build, the TTL attribute they write and the delete that follows a
    read are all under test rather than restated here.
    """

    def __init__(self, issuer: str, table: FakeTable) -> None:
        self.table = table
        self.binding: dict[str, Any] = {
            "status": "active",
            "user_id": USER_ID,
            "issuer": issuer,
            "subject": ISSUER_SUBJECT,
        }
        self.account_cutoffs: list[tuple[str, str, int]] = []

    async def get_binding(self, issuer: str, subject: str) -> dict[str, Any] | None:
        if (issuer, subject) != (self.binding["issuer"], self.binding["subject"]):
            return None
        return dict(self.binding)

    async def get_account_fence(self, user_id: str) -> dict[str, Any]:
        return {"status": "active", "generation": Decimal(1)}

    async def get_account(self, user_id: str) -> dict[str, Any] | None:
        return dict(PROFILE) if user_id == USER_ID else None

    async def get_current_grants(self, user_id: str) -> list[dict[str, Any]]:
        return []

    async def record_session_revocation(
        self, issuer: str, subject: str, revoked_before: int
    ) -> int:
        self.account_cutoffs.append((issuer, subject, int(revoked_before)))
        current = self.binding.get("revoked_before")
        if current is None or int(current) < int(revoked_before):
            self.binding["revoked_before"] = Decimal(int(revoked_before))
        return int(self.binding["revoked_before"])

    async def get_session_revocation(
        self, issuer: str, subject: str, origin_jti: str | None
    ) -> dict[str, Any] | None:
        return identity_repo.get_sign_in_revocation(issuer, subject, origin_jti)

    async def record_sign_in_revocation(
        self, issuer: str, subject: str, origin_jti: str, expires_at: int
    ) -> None:
        identity_repo.record_sign_in_revocation(issuer, subject, origin_jti, expires_at)

    async def put_sign_in_refresh_token(
        self, user_id: str, origin_jti: str, refresh_token: str, expires_at: int
    ) -> None:
        identity_repo.put_sign_in_refresh_token(
            user_id=user_id,
            origin_jti=origin_jti,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

    async def get_sign_in_refresh_token(
        self, user_id: str, origin_jti: str
    ) -> str | None:
        return identity_repo.get_sign_in_refresh_token(user_id, origin_jti)

    async def discard_sign_in_refresh_token(self, user_id: str, origin_jti: str) -> None:
        identity_repo.discard_sign_in_refresh_token(user_id, origin_jti)


def _settings(keyset) -> Settings:
    return Settings(
        aws_region="eu-central-2",
        cognito_user_pool_id="offline-pool",
        cognito_student_client_id="student-client",
        cognito_allowed_issuers=[keyset.issuer],
        cognito_access_client_ids=["student-client"],
    )


def _token(keyset, *, issued_at: int, origin_jti: str | None, jti: str) -> str:
    claims: dict[str, Any] = {
        "iss": keyset.issuer,
        "sub": ISSUER_SUBJECT,
        "client_id": "student-client",
        "token_use": "access",
        "cognito:groups": ["students"],
        "jti": jti,
        "iat": issued_at,
        "exp": issued_at + 3600,
    }
    if origin_jti is not None:
        claims["origin_jti"] = origin_jti
    return jwt.encode(
        claims, keyset.private_key, algorithm="RS256", headers={"kid": keyset.kid}
    )


@pytest.fixture
def session_app(rsa_jwks_keysets, monkeypatch):
    """One application, one table, one provider, wired the way production wires them."""
    keyset, _ = rsa_jwks_keysets
    table = FakeTable()
    monkeypatch.setattr(identity_repo, "get_table", lambda: table)
    provider = _Provider()
    monkeypatch.setattr(auth, "_get_cognito", lambda _settings: provider)
    repository = _IdentityRepository(keyset.issuer, table)

    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")

    @app.get("/protected")
    async def protected(actor=Depends(get_actor)):
        return {"userId": actor.user_id}

    app.dependency_overrides[get_settings] = lambda: _settings(keyset)
    app.dependency_overrides[get_jwks_key_provider] = lambda: JwksKeyProvider(
        FakeAsyncJwksTransport({keyset.issuer: keyset.jwks}),
        ttl_seconds=3600,
        max_stale_seconds=7200,
    )
    app.dependency_overrides[get_identity_repository] = lambda: repository
    client = TestClient(app)
    return client, keyset, provider, repository, table


def _reach(client: TestClient, token: str) -> int:
    return client.get("/protected", headers={"Authorization": f"Bearer {token}"}).status_code


def _sign_in(client, provider, keyset, *, origin_jti: str, issued_at: int) -> tuple[str, str]:
    """Drive the real sign-in route so the refresh token is stored the real way."""
    access = _token(keyset, issued_at=issued_at, origin_jti=origin_jti, jti=f"{origin_jti}-1")
    refresh = f"refresh-for-{origin_jti}"
    provider.sign_in_result = {"AccessToken": access, "RefreshToken": refresh}
    response = client.post(
        "/auth/login", json={"email": PROFILE["email"], "password": "ValidPass123!"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["refreshToken"] == refresh, (
        "the account switcher reads this field; dropping it breaks holding a second account"
    )
    return access, refresh


# ---------------------------------------------------------------------------
# Promise 1: a sign-out processed after the same person signed back in leaves
# the new sign-in alone.
# ---------------------------------------------------------------------------


def test_a_late_sign_out_does_not_reach_the_sign_in_that_replaced_it(session_app):
    client, keyset, _provider, repository, _table = session_app
    now = int(datetime.now(UTC).timestamp())

    first, _ = _sign_in(client, _provider, keyset, origin_jti="sign-in-first", issued_at=now - 300)
    second, _ = _sign_in(client, _provider, keyset, origin_jti="sign-in-second", issued_at=now - 10)

    # The browser gave up on the first sign-out long ago; the server gets to it
    # only now, after the same person has signed back in.
    assert client.post("/auth/logout", json={"access_token": first}).status_code == 204

    assert _reach(client, first) == 401
    assert _reach(client, second) == 200
    assert repository.account_cutoffs == [], (
        "an account-wide cut-off is what used to void the newer sign-in"
    )
    assert "revoked_before" not in repository.binding


# ---------------------------------------------------------------------------
# Promise 2: the signed-out sign-in's access token is refused, and its refresh
# token cannot buy another one.
# ---------------------------------------------------------------------------


def test_the_signed_out_sign_in_can_neither_be_replayed_nor_renewed(session_app):
    client, keyset, provider, _repository, _table = session_app
    now = int(datetime.now(UTC).timestamp())

    access, refresh = _sign_in(
        client, provider, keyset, origin_jti="sign-in-only", issued_at=now - 60
    )
    assert _reach(client, access) == 200

    assert client.post("/auth/logout", json={"access_token": access}).status_code == 204

    assert _reach(client, access) == 401

    # Cognito was asked to revoke this sign-in's refresh token and nothing else.
    assert ("revoke_token", {"Token": refresh, "ClientId": "student-client"}) in provider.calls
    assert "global_sign_out" not in provider.operations(), (
        "global_sign_out is the account-wide call this card exists to stop making"
    )

    # And even where the provider still honoured it, the renewed token carries
    # the same origin_jti, so the backend refuses it on its own authority.
    provider.refresh_result = {
        "AccessToken": _token(
            keyset, issued_at=now + 10, origin_jti="sign-in-only", jti="renewed"
        )
    }
    renewed = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert renewed.status_code == 401, renewed.text
    assert renewed.json()["detail"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# Promise 3: an *older* sign-in of the same account survives. This is the one
# the old cut-off could never keep, because "issued before now" is precisely
# what an older sign-in's tokens are.
# ---------------------------------------------------------------------------


def test_an_older_sign_in_of_the_same_account_survives(session_app):
    client, keyset, provider, repository, _table = session_app
    now = int(datetime.now(UTC).timestamp())

    older, _ = _sign_in(client, provider, keyset, origin_jti="sign-in-older", issued_at=now - 900)
    # Two tabs of the older sign-in, the second holding a renewed token.
    older_tabs = [
        older,
        _token(keyset, issued_at=now - 120, origin_jti="sign-in-older", jti="older-renewed"),
    ]
    newer, _ = _sign_in(client, provider, keyset, origin_jti="sign-in-newer", issued_at=now - 30)

    assert client.post("/auth/logout", json={"access_token": newer}).status_code == 204

    assert _reach(client, newer) == 401
    # Every token of the older sign-in, not merely the first one looked at.
    assert [_reach(client, token) for token in older_tabs] == [200] * len(older_tabs)
    assert repository.account_cutoffs == []


# ---------------------------------------------------------------------------
# Promise 4: tabs sharing one sign-in go together.
# ---------------------------------------------------------------------------


def test_every_tab_of_the_signed_out_sign_in_falls_together(session_app):
    client, keyset, provider, _repository, _table = session_app
    now = int(datetime.now(UTC).timestamp())

    first_tab, _ = _sign_in(
        client, provider, keyset, origin_jti="sign-in-shared", issued_at=now - 600
    )
    # What the other tabs hold: same sign-in, different token, different age -
    # one older than the token signing out and one younger, so neither direction
    # of an "issued before" comparison can pass for this.
    shared_tabs = [
        first_tab,
        _token(keyset, issued_at=now - 900, origin_jti="sign-in-shared", jti="tab-older"),
        _token(keyset, issued_at=now - 5, origin_jti="sign-in-shared", jti="tab-newer"),
    ]
    assert [_reach(client, token) for token in shared_tabs] == [200] * len(shared_tabs)

    assert client.post("/auth/logout", json={"access_token": first_tab}).status_code == 204

    assert [_reach(client, token) for token in shared_tabs] == [401] * len(shared_tabs)


# ---------------------------------------------------------------------------
# Transition: a token from before the pool emitted origin_jti keeps the
# behaviour it was issued under, and the row carries the TTL that lets it go.
# ---------------------------------------------------------------------------


def test_a_token_without_a_sign_in_claim_keeps_the_account_cut_off(session_app):
    client, keyset, provider, repository, _table = session_app
    now = int(datetime.now(UTC).timestamp())

    legacy = _token(keyset, issued_at=now - 60, origin_jti=None, jti="legacy")
    assert _reach(client, legacy) == 200

    assert client.post("/auth/logout", json={"access_token": legacy}).status_code == 204

    assert _reach(client, legacy) == 401
    assert [call[:2] for call in repository.account_cutoffs] == [
        (keyset.issuer, ISSUER_SUBJECT)
    ]
    assert provider.operations() == ["global_sign_out"]


def test_the_revocation_row_expires_on_its_own(session_app):
    client, keyset, provider, _repository, table = session_app
    now = int(datetime.now(UTC).timestamp())

    access, _ = _sign_in(client, provider, keyset, origin_jti="sign-in-ttl", issued_at=now - 60)
    assert client.post("/auth/logout", json={"access_token": access}).status_code == 204

    rows = [
        row
        for row in table.rows.values()
        if row.get("entity_type") == "auth_sign_in_revocation"
    ]
    assert len(rows) == 1
    # `expires_at` is the table's TTL attribute; a row without it never leaves.
    assert int(rows[0]["expires_at"]) >= now + identity_repo.SIGN_IN_REVOCATION_TTL_SECONDS
    assert identity_repo.SIGN_IN_REVOCATION_TTL_SECONDS >= 30 * 24 * 60 * 60, (
        "the row has to outlive the refresh token, not the access token: a revoked "
        "refresh token the provider never actually revoked would otherwise mint a "
        "fresh token the moment this row expired"
    )


def test_the_stored_refresh_token_is_spent_rather_than_left_lying_about(session_app):
    client, keyset, provider, _repository, table = session_app
    now = int(datetime.now(UTC).timestamp())

    access, refresh = _sign_in(
        client, provider, keyset, origin_jti="sign-in-custody", issued_at=now - 60
    )
    held = [
        row for row in table.rows.values() if row.get("entity_type") == "auth_sign_in_session"
    ]
    assert [row.get("refresh_token") for row in held] == [refresh]

    assert client.post("/auth/logout", json={"access_token": access}).status_code == 204

    assert [
        row for row in table.rows.values() if row.get("entity_type") == "auth_sign_in_session"
    ] == []


def test_the_dynamo_repository_answers_every_method_the_resolver_calls():
    """The resolver calls these on whatever is injected; the real one must have them."""
    repository = identity_repo.DynamoIdentityRepository()
    for name in (
        "get_binding",
        "get_account_fence",
        "get_account",
        "get_current_grants",
        "record_session_revocation",
        "get_session_revocation",
        "record_sign_in_revocation",
        "put_sign_in_refresh_token",
        "get_sign_in_refresh_token",
        "discard_sign_in_refresh_token",
    ):
        assert callable(getattr(repository, name, None)), name


# ---------------------------------------------------------------------------
# A provider that refused must still be retriable. Reading the held token and
# dropping its row used to be one step, so a refused revoke left nothing for the
# next sign-out to retry with, and the provider's copy of the refresh token
# outlived the sign-out by thirty days.
# ---------------------------------------------------------------------------


def test_a_refused_provider_revoke_is_retried_by_the_next_sign_out(session_app):
    client, keyset, provider, _repository, table = session_app
    now = int(datetime.now(UTC).timestamp())

    access, refresh = _sign_in(
        client, provider, keyset, origin_jti="sign-in-retry", issued_at=now - 60
    )
    provider.revoke_failures = 1

    first = client.post("/auth/logout", json={"access_token": access})
    assert first.status_code != 204, "a refused provider call is still reported"
    # The sign-in is over here regardless, which is what makes the retry safe.
    assert _reach(client, access) == 401
    assert [
        row for row in table.rows.values() if row.get("entity_type") == "auth_sign_in_session"
    ] != [], "the held row is what the retry needs; a refusal may not consume it"

    second = client.post("/auth/logout", json={"access_token": access})
    assert second.status_code == 204, second.text
    assert provider.operations().count("revoke_token") == 2, (
        "the second sign-out has to reach the provider again, not answer 204 "
        "having found nothing left to revoke"
    )
    assert [kwargs["Token"] for operation, kwargs in provider.calls if operation == "revoke_token"] == [
        refresh,
        refresh,
    ]
    # Only the accepted call spends the row.
    assert [
        row for row in table.rows.values() if row.get("entity_type") == "auth_sign_in_session"
    ] == []


# ---------------------------------------------------------------------------
# `DELETE /auth/me` resolves no Actor, so it carries its own copy of the
# revocation check. Nothing pinned that copy: the whole suite stayed green with
# the revocation argument replaced by None.
# ---------------------------------------------------------------------------


class _DeletionRepository:
    """Binding and sign-in state only; the deletion command itself is stubbed."""

    def __init__(self, issuer: str, *, revoked: bool) -> None:
        self.issuer = issuer
        self.revoked = revoked

    async def get_binding(self, issuer: str, subject: str) -> dict[str, Any]:
        return {"status": "active", "user_id": USER_ID, "issuer": issuer, "subject": subject}

    async def get_session_revocation(
        self, issuer: str, subject: str, origin_jti: str | None
    ) -> dict[str, Any] | None:
        if not self.revoked or not origin_jti:
            return None
        return {"origin_jti": origin_jti, "expires_at": Decimal(2_000_000_000)}


def _deletion_token(issuer: str) -> VerifiedAccessToken:
    return VerifiedAccessToken(
        issuer=issuer,
        subject=ISSUER_SUBJECT,
        client_id="student-client",
        groups=("students",),
        issued_at=10_000,
        origin_jti="sign-in-closing",
    )


@pytest.mark.asyncio
async def test_closing_the_account_is_refused_once_that_sign_in_was_signed_out(
    rsa_jwks_keysets, monkeypatch
):
    keyset, _ = rsa_jwks_keysets
    built: list[str] = []
    monkeypatch.setattr(
        deps, "begin_or_replay_deletion", lambda **kwargs: built.append(kwargs["user_id"])
    )

    with pytest.raises(HTTPException) as refused:
        await deps.get_deletion_command(
            verified=_deletion_token(keyset.issuer),
            repository=_DeletionRepository(keyset.issuer, revoked=True),
        )

    assert refused.value.status_code == 401
    assert refused.value.detail["code"] == "invalid_token"
    assert built == [], "the command must not be built for a signed-out sign-in"


@pytest.mark.asyncio
async def test_closing_the_account_still_works_for_a_sign_in_that_was_not_signed_out(
    rsa_jwks_keysets, monkeypatch
):
    """Negative control: the refusal above has to come from the revocation, not
    from the fixture refusing everything."""
    keyset, _ = rsa_jwks_keysets
    built: list[str] = []
    monkeypatch.setattr(
        deps, "begin_or_replay_deletion", lambda **kwargs: built.append(kwargs["user_id"])
    )

    await deps.get_deletion_command(
        verified=_deletion_token(keyset.issuer),
        repository=_DeletionRepository(keyset.issuer, revoked=False),
    )

    assert built == [USER_ID]
