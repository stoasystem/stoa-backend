"""Wave 0 authentication-security cases; implementation turns focused cases green later."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from security.conftest import (
    FailingSecurityRepository,
    FakeAsyncJwksTransport,
    InMemorySecurityRepository,
    RepositoryUnavailable,
)
from stoa.config import Settings, get_settings
from stoa.routers import auth

def test_t472_02_jwks_keysets_are_issuer_and_kid_isolated(rsa_jwks_keysets):
    first, second = rsa_jwks_keysets
    assert first.issuer != second.issuer
    assert first.kid != second.kid
    assert first.jwks["keys"][0]["n"] != second.jwks["keys"][0]["n"]


def test_t472_01_rejected_auth_path_can_assert_zero_cognito_mutations(fake_cognito):
    fake_cognito.assert_zero_mutations()


@pytest.mark.asyncio
async def test_t472_02_jwks_transport_records_refresh_rotation_and_isolation(rsa_jwks_keysets):
    first, second = rsa_jwks_keysets
    rotated = {"keys": [{**first.jwks["keys"][0], "kid": "primary-kid-v2"}]}
    transport = FakeAsyncJwksTransport(
        {first.issuer: [first.jwks, rotated], second.issuer: second.jwks}
    )
    assert await transport.fetch(first.issuer) == first.jwks
    assert await transport.fetch(first.issuer) == rotated
    assert await transport.fetch(second.issuer) == second.jwks
    assert transport.calls == [first.issuer, first.issuer, second.issuer]


@pytest.mark.asyncio
async def test_t472_07_repository_missing_fact_is_distinct_from_outage_and_timeout():
    assert await InMemorySecurityRepository().get("missing") is None
    with pytest.raises(RepositoryUnavailable):
        await FailingSecurityRepository().get("student-1")
    with pytest.raises(TimeoutError):
        await FailingSecurityRepository(timeout=True).get("student-1")


@pytest.mark.parametrize(
    "public_role",
    ["admin", "teacher", "tutor", "Admin", "TEACHER", "Ｔｅａｃｈｅｒ", "unknown"],
    ids=lambda value: f"T-472-01-SEC-001-reject-{value.encode('unicode_escape').decode()}",
)
def test_t472_01_sec001_public_registration_rejects_privilege_without_mutation(
    public_role, monkeypatch, fake_cognito
):
    """Red until Plan 03: exercise the reachable API and both mutation boundaries."""
    database_mutations = []
    monkeypatch.setattr(auth, "_get_cognito", lambda _settings: fake_cognito)
    monkeypatch.setattr(auth.user_repo, "get_user_by_email", lambda _email: None)
    monkeypatch.setattr(auth.user_repo, "put_user", database_mutations.append)
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_settings] = lambda: Settings(
        aws_region="eu-central-2",
        cognito_user_pool_id="offline-pool",
        cognito_student_client_id="student-client",
        cognito_parent_client_id="parent-client",
        cognito_teacher_client_id="teacher-client",
        cognito_admin_client_id="admin-client",
    )

    response = TestClient(app).post(
        "/auth/register",
        json={
            "email": "attacker@example.invalid",
            "password": "ValidPass123!",
            "role": public_role,
        },
    )

    assert response.status_code in {400, 403, 422}
    fake_cognito.assert_zero_mutations()
    assert database_mutations == []


@pytest.mark.parametrize(
    "claim_case",
    ["wrong-client", "wrong-issuer", "id-token", "expired", "unknown-kid", "jwks-outage"],
    ids=lambda value: f"T-472-02-SEC-004-{value}",
)
def test_t472_02_sec004_token_validation_cases_are_executable(claim_case):
    """Red until Plan 02 supplies the isolated token verifier."""
    from stoa.security.tokens import verify_token_case

    decision = verify_token_case(claim_case)
    assert decision.allowed is False
    assert decision.safe_code in {
        "invalid_token",
        "token_expired",
        "identity_provider_unavailable",
    }
