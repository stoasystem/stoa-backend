"""The admin account list shows when an account last signed in (#107).

`lastLoginAt` was published by `GET /admin/users` but nothing ever wrote the
field it reads, so the console showed "—" for every account, including the
administrator looking at it. A password sign-in now stamps it. A refresh does
not: it renews a sign-in that already happened.

Every test drives the real routes against one table: the sign-in through
`POST /auth/login`, the answer through `GET /admin/users`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from jose import jwt
import pytest

from security.conftest import FakeAsyncJwksTransport
from test_account_admin_endpoints import (
    AccountAdminTable,
    _admin_user,
    _app,
    _seed_profile,
    table as table,  # a fixture: the tests below take it by name
)

from stoa import aws
from stoa.aws import Kind
from stoa.config import Settings, get_settings
from stoa.db.repositories.identity_repo import DynamoIdentityRepository
from stoa.deps import get_identity_repository, get_jwks_key_provider
from stoa.security.jwks import JwksKeyProvider


USER_ID = "student-b"
SUBJECT = "subject-b"


class _Provider:
    def __init__(self, access_token: str) -> None:
        self.access_token = access_token

    def initiate_auth(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "AuthenticationResult": {
                "AccessToken": self.access_token,
                "RefreshToken": "refresh-b",
            }
        }


class _Repository(DynamoIdentityRepository):
    """The production repository over the test table, bound to one subject.

    The binding row is the only fixture: everything the sign-in reads after it
    - fence, profile, grants, revocations - comes from the table.
    """

    async def get_binding(self, issuer: str, subject: str) -> dict[str, Any] | None:
        if subject != SUBJECT:
            return None
        return {"status": "active", "user_id": USER_ID, "issuer": issuer, "subject": subject}


def _token(keyset) -> str:
    now = int(datetime.now(UTC).timestamp())
    return jwt.encode(
        {
            "iss": keyset.issuer,
            "sub": SUBJECT,
            "client_id": "student-client",
            "token_use": "access",
            "cognito:groups": ["students"],
            "jti": "access-1",
            "origin_jti": "sign-in-1",
            "iat": now,
            "exp": now + 3600,
        },
        keyset.private_key,
        algorithm="RS256",
        headers={"kid": keyset.kid},
    )


@pytest.fixture
def signed_in_client(table: AccountAdminTable, rsa_jwks_keysets, monkeypatch):
    keyset, _ = rsa_jwks_keysets
    _seed_profile(table, USER_ID, "student", account_number="S26-0001")
    table.rows[(f"USER#{USER_ID}", "PROFILE")].update(
        registration_command="admin_assignment", registration_role="student"
    )
    aws.install({Kind.COGNITO: _Provider(_token(keyset))})
    app = _app(_admin_user())
    app.dependency_overrides[get_settings] = lambda: Settings(
        aws_region="eu-central-2",
        cognito_user_pool_id="eu-central-2_test",
        cognito_student_client_id="student-client",
        cognito_allowed_issuers=[keyset.issuer],
        cognito_access_client_ids=["student-client"],
    )
    app.dependency_overrides[get_jwks_key_provider] = lambda: JwksKeyProvider(
        FakeAsyncJwksTransport({keyset.issuer: keyset.jwks}),
        ttl_seconds=3600,
        max_stale_seconds=7200,
    )
    app.dependency_overrides[get_identity_repository] = _Repository
    return TestClient(app), app


def _sign_in(client: TestClient):
    return client.post("/auth/login", json={"email": "student-b@example.com", "password": "ValidPass123!"})


def _listed_last_login(client: TestClient) -> str:
    rows = {row["userId"]: row for row in client.get("/admin/users").json()["items"]}
    return rows[USER_ID]["lastLoginAt"]


def test_a_password_sign_in_shows_in_the_admin_list(signed_in_client) -> None:
    client, _app = signed_in_client
    before = datetime.now(UTC)

    response = _sign_in(client)

    assert response.status_code == 200, response.text
    listed = _listed_last_login(client)
    assert listed, "the console still has nothing to show"
    assert before - timedelta(seconds=1) <= datetime.fromisoformat(listed) <= datetime.now(UTC)


def test_a_profile_edit_after_a_sign_in_is_not_refused(signed_in_client) -> None:
    """The stamp moves the profile version; an edit reads the version afresh."""
    client, _app = signed_in_client
    assert _sign_in(client).status_code == 200

    response = client.patch(f"/admin/users/{USER_ID}", json={"name": "Renamed"})

    assert response.status_code == 200, response.text
    rows = {row["userId"]: row for row in client.get("/admin/users").json()["items"]}
    assert rows[USER_ID]["name"] == "Renamed"
    assert rows[USER_ID]["lastLoginAt"]


def test_a_refresh_is_not_a_sign_in(signed_in_client) -> None:
    client, _app = signed_in_client

    response = client.post("/auth/refresh", json={"refresh_token": "refresh-b"})

    assert response.status_code == 200, response.text
    assert _listed_last_login(client) == ""


def test_a_failing_write_does_not_fail_the_sign_in(
    signed_in_client, table: AccountAdminTable, monkeypatch
) -> None:
    client, _app = signed_in_client

    def unavailable(**_kwargs: Any) -> None:
        raise RuntimeError("DynamoDB is unavailable")

    monkeypatch.setattr(table, "transact_write_items", unavailable)

    response = _sign_in(client)

    assert response.status_code == 200, response.text
    assert response.json()["accessToken"]
    assert "last_login_at" not in table.rows[(f"USER#{USER_ID}", "PROFILE")]


def test_an_account_whose_deletion_began_mid_sign_in_is_not_written(
    signed_in_client, table: AccountAdminTable
) -> None:
    """The sign-in passed the fence; deletion began before the stamp was written."""
    client, app = signed_in_client
    fence = table.rows[(f"USER#{USER_ID}", "ACCOUNT_FENCE")]

    class _DeletionStartsNow(_Repository):
        async def get_account(self, user_id: str) -> dict[str, Any] | None:
            profile = await super().get_account(user_id)
            fence["status"] = "deleting"
            return profile

    app.dependency_overrides[get_identity_repository] = _DeletionStartsNow

    response = _sign_in(client)

    assert response.status_code == 200, response.text
    assert "last_login_at" not in table.rows[(f"USER#{USER_ID}", "PROFILE")]


def test_an_account_being_deleted_is_neither_signed_in_nor_written(
    signed_in_client, table: AccountAdminTable
) -> None:
    client, _app = signed_in_client
    table.rows[(f"USER#{USER_ID}", "ACCOUNT_FENCE")]["status"] = "deleting"

    response = _sign_in(client)

    assert response.status_code != 200
    assert "last_login_at" not in table.rows[(f"USER#{USER_ID}", "PROFILE")]
