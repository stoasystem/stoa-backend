"""Wave 0 authentication-security cases; implementation turns focused cases green later."""

import pytest

from security.conftest import (
    FailingSecurityRepository,
    FakeAsyncJwksTransport,
    InMemorySecurityRepository,
    RepositoryUnavailable,
)

pytest_plugins = ("security.conftest",)


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
