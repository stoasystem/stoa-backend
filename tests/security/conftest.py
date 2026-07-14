"""Offline-only builders and provider/repository doubles for Phase 472 security tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
from typing import Any

from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

from stoa.security.identity import (
    AccountStatus,
    Actor,
    CanonicalRole,
    CapabilityGrant,
)


@dataclass
class FrozenClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


@dataclass(frozen=True)
class TestKeySet:
    issuer: str
    kid: str
    private_key: rsa.RSAPrivateKey
    jwks: dict[str, list[dict[str, str]]]


def _b64uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def build_key_set(label: str) -> TestKeySet:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()
    kid = f"{label}-kid-v1"
    return TestKeySet(
        issuer=f"https://identity.test/{label}",
        kid=kid,
        private_key=private_key,
        jwks={
            "keys": [
                {
                    "kty": "RSA",
                    "alg": "RS256",
                    "use": "sig",
                    "kid": kid,
                    "n": _b64uint(numbers.n),
                    "e": _b64uint(numbers.e),
                }
            ]
        },
    )


class FakeAsyncJwksTransport:
    def __init__(self, responses: dict[str, dict[str, Any]]):
        self.responses = responses
        self.calls: list[str] = []

    async def fetch(self, issuer: str) -> dict[str, Any]:
        self.calls.append(issuer)
        value = self.responses[issuer]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeCognitoRecorder:
    """Records any provider mutation without importing or constructing boto clients."""

    def __init__(self):
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, operation: str):
        def record(**kwargs: Any) -> dict[str, Any]:
            self.calls.append((operation, kwargs))
            return {}

        return record

    def assert_zero_mutations(self) -> None:
        assert self.calls == []


class InMemorySecurityRepository:
    """Stores explicit facts; absent keys return None and are distinct from outages."""

    def __init__(self, initial: dict[str, Any] | None = None):
        self.items = dict(initial or {})
        self.mutations: list[tuple[str, str, Any]] = []

    async def get(self, key: str) -> Any | None:
        return self.items.get(key)

    async def put(self, key: str, value: Any) -> None:
        self.items[key] = value
        self.mutations.append(("put", key, value))


class RepositoryUnavailable(RuntimeError):
    pass


class FailingSecurityRepository:
    def __init__(self, *, timeout: bool = False):
        self.timeout = timeout

    async def get(self, _key: str) -> Any:
        if self.timeout:
            raise TimeoutError("injected authorization repository timeout")
        raise RepositoryUnavailable("injected authorization repository outage")


def build_actor(
    role: CanonicalRole = CanonicalRole.STUDENT,
    *,
    user_id: str | None = None,
    status: AccountStatus = AccountStatus.ACTIVE,
    grants: tuple[CapabilityGrant, ...] = (),
) -> Actor:
    return Actor(
        user_id=user_id or f"{role.value}-1",
        issuer="https://identity.test/primary",
        subject=f"subject-{user_id or role.value}",
        role=role,
        account_status=status,
        cognito_group=role.value,
        current_grants=grants,
        auth_context={"token_use": "access", "client_id": f"{role.value}-client"},
    )


def build_binding(*, parent_id: str = "parent-1", student_id: str = "student-1", status="active"):
    return {
        "parent_id": parent_id,
        "student_id": student_id,
        "forward_status": status,
        "reverse_status": status,
    }


def build_assignment(*, teacher_id="teacher-1", student_id="student-1", status="active"):
    return {"teacher_id": teacher_id, "student_id": student_id, "status": status, "scope": "learning"}


def build_resource(*, resource_id="resource-1", student_id="student-1", resource_type="question"):
    return {"resource_id": resource_id, "student_id": student_id, "resource_type": resource_type}


def build_grant(*, capability="student_support_lookup", scope="student:student-1", version=1):
    return CapabilityGrant(capability=capability, scope=scope, version=version)


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc))


@pytest.fixture(scope="session")
def rsa_jwks_keysets() -> tuple[TestKeySet, TestKeySet]:
    return build_key_set("primary"), build_key_set("secondary")


@pytest.fixture
def fake_cognito() -> FakeCognitoRecorder:
    return FakeCognitoRecorder()


@pytest.fixture
def security_repository() -> InMemorySecurityRepository:
    return InMemorySecurityRepository()


@pytest.fixture
def security_canaries() -> dict[str, str]:
    return {
        "token": "eyJ.security-token-canary",
        "email": "student-canary@example.invalid",
        "student_content": "private-student-content-canary",
        "object_key": "private/student-1/object-key-canary",
        "provider_text": "provider-signature-debug-canary",
    }
