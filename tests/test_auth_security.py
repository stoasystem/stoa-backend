"""Authentication security contracts with no AWS credentials or network access."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from security.conftest import (
    FailingSecurityRepository,
    FakeAsyncJwksTransport,
    InMemorySecurityRepository,
    RepositoryUnavailable,
)
from stoa.config import Settings, get_settings
from stoa.deps import (
    get_current_user,
    get_identity_repository,
    get_verified_token,
    require_role,
)
from stoa.routers import auth
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.jwks import JwksKeyProvider
from stoa.security.tokens import VerifiedAccessToken, verify_access_token


def test_public_identity_runtime_uses_only_canonical_teacher_vocabulary():
    legacy_teacher_term = "tu" + "tor"
    runtime_files = (
        Path("src/stoa/routers/auth.py"),
        Path("src/stoa/services/public_identity_service.py"),
        Path("src/stoa/db/repositories/public_identity_repo.py"),
    )
    for path in runtime_files:
        assert legacy_teacher_term not in path.read_text().casefold()


def _access_token(keyset, *, issuer=None, client_id="student-client", token_use="access"):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": issuer or keyset.issuer,
            "sub": "subject-1",
            "client_id": client_id,
            "token_use": token_use,
            "cognito:groups": ["students"],
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        keyset.private_key,
        algorithm="RS256",
        headers={"kid": keyset.kid},
    )

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
async def test_t472_02_provider_isolates_same_kid_between_issuers(rsa_jwks_keysets):
    first, second = rsa_jwks_keysets
    shared_kid = "shared-kid"
    first_jwks = {"keys": [{**first.jwks["keys"][0], "kid": shared_kid}]}
    second_jwks = {"keys": [{**second.jwks["keys"][0], "kid": shared_kid}]}
    transport = FakeAsyncJwksTransport({first.issuer: first_jwks, second.issuer: second_jwks})
    provider = JwksKeyProvider(transport, ttl_seconds=60, max_stale_seconds=120)

    first_key = await provider.get_key(first.issuer, shared_kid)
    second_key = await provider.get_key(second.issuer, shared_kid)

    assert first_key.to_dict()["n"] != second_key.to_dict()["n"]
    assert transport.calls == [first.issuer, second.issuer]


@pytest.mark.asyncio
async def test_t472_02_unknown_kid_refreshes_once_and_supports_rotation(rsa_jwks_keysets):
    first, _ = rsa_jwks_keysets
    rotated = {"keys": [{**first.jwks["keys"][0], "kid": "primary-kid-v2"}]}
    transport = FakeAsyncJwksTransport({first.issuer: [first.jwks, rotated]})
    provider = JwksKeyProvider(transport, ttl_seconds=60, max_stale_seconds=120)

    await provider.get_key(first.issuer, first.kid)
    rotated_key = await provider.get_key(first.issuer, "primary-kid-v2")

    assert rotated_key.to_dict()["n"] == first.jwks["keys"][0]["n"]
    assert transport.calls == [first.issuer, first.issuer]


@pytest.mark.asyncio
async def test_t472_02_known_key_outage_is_bounded_and_unknown_key_fails_closed(
    rsa_jwks_keysets,
):
    first, _ = rsa_jwks_keysets
    current = 0.0
    transport = FakeAsyncJwksTransport(
        {first.issuer: [first.jwks, RuntimeError("offline"), RuntimeError("offline")]}
    )
    provider = JwksKeyProvider(
        transport,
        ttl_seconds=10,
        max_stale_seconds=20,
        monotonic=lambda: current,
    )
    cached = await provider.get_key(first.issuer, first.kid)
    current = 11.0
    assert await provider.get_key(first.issuer, first.kid) is cached
    current = 21.0
    with pytest.raises(SecurityDecisionError) as exc_info:
        await provider.get_key(first.issuer, first.kid)
    assert exc_info.value.code is SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE

    unknown_transport = FakeAsyncJwksTransport(
        {first.issuer: [first.jwks, RuntimeError("offline")]}
    )
    unknown_provider = JwksKeyProvider(
        unknown_transport,
        ttl_seconds=10,
        max_stale_seconds=20,
    )
    await unknown_provider.get_key(first.issuer, first.kid)
    with pytest.raises(SecurityDecisionError) as unknown_error:
        await unknown_provider.get_key(first.issuer, "unknown-kid")
    assert unknown_error.value.code is SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE
    assert len(unknown_transport.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"issuer": "https://identity.test/wrong"}, SecurityErrorCode.INVALID_TOKEN),
        ({"client_id": "wrong-client"}, SecurityErrorCode.INVALID_TOKEN),
        ({"token_use": "id"}, SecurityErrorCode.INVALID_TOKEN),
    ],
)
async def test_t472_02_verifier_rejects_wrong_issuer_client_and_token_use(
    rsa_jwks_keysets, overrides, expected_code
):
    first, _ = rsa_jwks_keysets
    transport = FakeAsyncJwksTransport({first.issuer: first.jwks})
    provider = JwksKeyProvider(transport, ttl_seconds=60, max_stale_seconds=120)
    token = _access_token(first, **overrides)

    with pytest.raises(SecurityDecisionError) as exc_info:
        await verify_access_token(
            token,
            allowed_issuers={first.issuer},
            allowed_client_ids={"student-client"},
            key_provider=provider,
        )
    assert exc_info.value.code is expected_code
    assert exc_info.value.public_body().keys() == {"code", "message", "correlationId"}


@pytest.mark.asyncio
async def test_t472_02_verifier_accepts_only_bound_access_token(rsa_jwks_keysets):
    first, _ = rsa_jwks_keysets
    provider = JwksKeyProvider(
        FakeAsyncJwksTransport({first.issuer: first.jwks}),
        ttl_seconds=60,
        max_stale_seconds=120,
    )

    verified = await verify_access_token(
        _access_token(first),
        allowed_issuers={first.issuer},
        allowed_client_ids={"student-client"},
        key_provider=provider,
    )

    assert (verified.issuer, verified.subject, verified.client_id) == (
        first.issuer,
        "subject-1",
        "student-client",
    )


def test_t472_02_dependency_path_denies_suspension_next_request_without_mutation():
    class MutableRepository:
        def __init__(self):
            self.status = "active"
            self.calls = []

        async def get_binding(self, issuer, subject):
            self.calls.append(("get_binding", issuer, subject))
            return {"status": "active", "user_id": "student-1"}

        async def get_account_fence(self, user_id):
            self.calls.append(("get_account_fence", user_id))
            return {"status": "active", "generation": 1}

        async def get_account(self, user_id):
            self.calls.append(("get_account", user_id))
            return {"role": "student", "account_status": self.status}

        async def get_current_grants(self, user_id):
            self.calls.append(("get_current_grants", user_id))
            return []

    repository = MutableRepository()
    verified = VerifiedAccessToken(
        issuer="https://identity.test/primary",
        subject="subject-1",
        client_id="student-client",
        groups=("students",),
    )
    handler_calls = []
    app = FastAPI()

    @app.get("/protected")
    async def protected(user=Depends(require_role("student"))):
        handler_calls.append(user["sub"])
        return {"userId": user["sub"]}

    app.dependency_overrides[get_verified_token] = lambda: verified
    app.dependency_overrides[get_identity_repository] = lambda: repository
    client = TestClient(app)

    assert client.get("/protected").status_code == 200
    repository.status = "suspended"
    denied = client.get("/protected")
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "identity_conflict"
    assert handler_calls == ["student-1"]
    assert {operation for operation, *_ in repository.calls} <= {
        "get_binding",
        "get_account_fence",
        "get_account",
        "get_current_grants",
    }


@pytest.mark.asyncio
async def test_t472_02_legacy_adapter_projects_only_resolved_actor_authority():
    from stoa.security.identity import AccountStatus, Actor, CanonicalRole, CapabilityGrant

    actor = Actor(
        user_id="admin-1",
        issuer="https://identity.test/primary",
        subject="provider-subject",
        role=CanonicalRole.ADMIN,
        account_status=AccountStatus.ACTIVE,
        cognito_group="admin",
        current_grants=(CapabilityGrant("student_support_lookup", "student:*", 4),),
    )

    legacy = await get_current_user(actor)
    assert legacy == {
        "sub": "admin-1",
        "user_id": "admin-1",
        "cognito_sub": "provider-subject",
        "role": "admin",
        "account_status": "active",
        "capabilities": {"student_support_lookup": "granted"},
    }


@pytest.mark.asyncio
async def test_t472_07_repository_missing_fact_is_distinct_from_outage_and_timeout():
    assert await InMemorySecurityRepository().get("missing") is None
    with pytest.raises(RepositoryUnavailable):
        await FailingSecurityRepository().get("student-1")
    with pytest.raises(TimeoutError):
        await FailingSecurityRepository(timeout=True).get("student-1")


@pytest.mark.parametrize(
    "public_role",
    [
        "admin",
        "teacher",
        "tutor",
        "Admin",
        "TEACHER",
        "Ｔｅａｃｈｅｒ",
        "teachers",
        "teacher ",
        " unknown ",
    ],
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
            "email": "attacker@example.com",
            "password": "ValidPass123!",
            "role": public_role,
        },
    )

    assert response.status_code in {400, 403, 422}
    fake_cognito.assert_zero_mutations()
    assert database_mutations == []


@pytest.mark.parametrize(
    "payload_patch",
    [
        {"roles": ["student", "admin"]},
        {"userRole": "teacher"},
        {"profile": {"role": "admin"}},
        {"profile": {"nested": {"roles": ["teacher"]}}},
    ],
)
def test_t472_01_registration_rejects_extra_or_nested_role_selectors_before_calls(
    payload_patch, monkeypatch, fake_cognito
):
    repository_calls = []
    monkeypatch.setattr(auth, "_get_cognito", lambda _settings: fake_cognito)
    monkeypatch.setattr(auth.user_repo, "put_user", repository_calls.append)
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
    payload = {
        "email": "attacker@example.com",
        "password": "ValidPass123!",
        "role": "student",
        **payload_patch,
    }

    response = TestClient(app).post("/auth/register", json=payload)

    assert response.status_code == 422
    fake_cognito.assert_zero_mutations()
    assert repository_calls == []


@pytest.mark.parametrize("role", ["teacher", "admin", "tutor", "unknown"])
def test_t472_01_confirmation_rejects_non_public_registration_commands_without_mutation(
    role, monkeypatch, fake_cognito
):
    repository_mutations = []
    monkeypatch.setattr(auth, "_get_cognito", lambda _settings: fake_cognito)
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda _email: {
            "user_id": "privileged-1",
            "email": "privileged@example.com",
            "role": role,
            "registration_command": "public_self_service",
            "registration_role": role,
            "email_verification_status": "pending_verification",
            "email_verification_required": True,
        },
    )
    monkeypatch.setattr(
        auth.user_repo,
        "update_email_verification_state",
        lambda *args, **kwargs: repository_mutations.append((args, kwargs)),
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "require_public_identity_command",
        lambda _email: (_ for _ in ()).throw(
            auth.public_identity_service.PublicIdentityCommandConflict("invalid public role")
        ),
    )
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
        "/auth/email-verification/confirm",
        json={"email": "privileged@example.com", "confirmationCode": "123456"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "identity_conflict"
    fake_cognito.assert_zero_mutations()
    assert repository_mutations == []


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
