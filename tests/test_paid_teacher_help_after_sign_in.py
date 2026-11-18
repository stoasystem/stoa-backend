"""Paid teacher help keeps working after the student or the parent signs in (#510).

A paid beneficiary grant records the profile versions it was written against.
Every password sign-in stamps `last_login_at` through the versioned profile
writer, so it moves `version`. Admission used to hold both profiles to the
versions on the grant, so the first sign-in after the grant left the paid scope
resolved but every admission refused, and the student got a 503 instead of a
teacher.

These drive the real sign-in route, `POST /auth/login`, against the same table
the grant and the admission use, with the shared test accounts as the grant
tool seeds them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from security.conftest import FakeAsyncJwksTransport, build_key_set
from test_grant_test_account_paid_access import (
    PARENT,
    STUDENT,
    _admit,
    _run,
    seed_accounts,
)

from stoa import aws, config
from stoa.aws import Kind
from stoa.config import Settings
from stoa.db.repositories import identity_repo, user_repo
from stoa.deps import get_identity_repository, get_jwks_key_provider
from stoa.models.billing import BillingPlanId
from stoa.routers import auth
from stoa.security.jwks import JwksKeyProvider
from stoa.services import teacher_support_allowance_service as support

CLIENT_ID = "public-client"
ACCOUNTS = {
    "student@test.stoaedu.ch": (STUDENT, "sub-login-student", "students"),
    "parent@test.stoaedu.ch": (PARENT, "sub-login-parent", "parents"),
}


class _Cognito:
    """The provider's answer to a correct password: a token for that account."""

    def __init__(self, tokens: dict[str, str]) -> None:
        self.tokens = tokens

    def initiate_auth(self, **kwargs: Any) -> dict[str, Any]:
        email = kwargs["AuthParameters"]["USERNAME"]
        return {"AuthenticationResult": {"AccessToken": self.tokens[email]}}


def _token(keyset, subject: str, group: str) -> str:
    now = int(datetime.now(UTC).timestamp())
    return jwt.encode(
        {
            "iss": keyset.issuer,
            "sub": subject,
            "client_id": CLIENT_ID,
            "token_use": "access",
            "cognito:groups": [group],
            "jti": f"access-{subject}",
            "origin_jti": f"sign-in-{subject}",
            "iat": now,
            "exp": now + 3600,
        },
        keyset.private_key,
        algorithm="RS256",
        headers={"kid": keyset.kid},
    )


@pytest.fixture
def client(fake_table) -> TestClient:
    seed_accounts(fake_table)
    keyset = build_key_set("sign-in")
    for user_id, subject, _group in ACCOUNTS.values():
        # Opened by an administrator, as the shared test accounts were; sign-in
        # checks the provenance against the role.
        profile = fake_table.rows[(f"USER#{user_id}", "PROFILE")]
        profile.update(
            registration_command="admin_assignment", registration_role=profile["role"]
        )
        fake_table.seed(
            {
                "PK": f"IDENTITY#{identity_repo.issuer_hash(keyset.issuer)}#{subject}",
                "SK": "BINDING",
                "entity_type": "identity_binding",
                "issuer": keyset.issuer,
                "subject": subject,
                "user_id": user_id,
                "status": "active",
                "version": 1,
            }
        )
    aws.install(
        {
            Kind.COGNITO: _Cognito(
                {
                    email: _token(keyset, subject, group)
                    for email, (_user, subject, group) in ACCOUNTS.items()
                }
            )
        }
    )
    config.install(
        Settings(
            aws_region="eu-central-2",
            cognito_user_pool_id="eu-central-2_test",
            cognito_student_client_id=CLIENT_ID,
            cognito_allowed_issuers=[keyset.issuer],
            cognito_access_client_ids=[CLIENT_ID],
        )
    )
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_jwks_key_provider] = lambda: JwksKeyProvider(
        FakeAsyncJwksTransport({keyset.issuer: keyset.jwks}),
        ttl_seconds=3600,
        max_stale_seconds=7200,
    )
    app.dependency_overrides[get_identity_repository] = identity_repo.DynamoIdentityRepository
    return TestClient(app)


def _sign_in(client: TestClient, email: str) -> None:
    user_id = ACCOUNTS[email][0]
    before = user_repo.get_user(user_id)["version"]

    response = client.post("/auth/login", json={"email": email, "password": "ValidPass123!"})

    assert response.status_code == 200, response.text
    after = user_repo.get_user(user_id)
    # The sign-in really went through the profile writer: this is what moved the
    # version the grant used to be held to.
    assert after["last_login_at"]
    assert after["version"] == before + 1


def _assert_admitted_paid(case_id: str) -> None:
    admitted = _admit(case_id)
    assert admitted.disposition is support.TeacherSupportAdmissionDisposition.ADMITTED
    assert admitted.admission is not None
    assert admitted.admission.plan_id is BillingPlanId.TEACHER_SUPPORTED


def test_the_student_can_ask_a_teacher_after_signing_in_again(client) -> None:
    _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")

    _sign_in(client, "student@test.stoaedu.ch")

    _assert_admitted_paid("case-after-student-sign-in")


def test_the_student_can_ask_a_teacher_after_the_parent_signs_in_again(client) -> None:
    _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")

    _sign_in(client, "parent@test.stoaedu.ch")

    _assert_admitted_paid("case-after-parent-sign-in")


def test_both_signing_in_again_and_again_does_not_wear_the_grant_out(client) -> None:
    _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")

    for round_ in range(2):
        _sign_in(client, "student@test.stoaedu.ch")
        _sign_in(client, "parent@test.stoaedu.ch")
        _assert_admitted_paid(f"case-round-{round_}")
