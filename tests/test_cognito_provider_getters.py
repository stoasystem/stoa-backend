"""#356: the two Cognito provider getters resolve for real.

Both were an ``lru_cache`` over their ``Settings`` argument. A ``Settings`` is not
hashable, so every request that reached either getter answered 500 before its
handler ran: teacher activation, provisioning an admin, changing an admin's
status. The deny paths were tested; the allow paths never were. These cases let
FastAPI resolve the getters themselves; only the cognito-idp client is a double,
installed in ``stoa.aws`` (#358), which builds and reuses the real one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from stoa import aws
from stoa.aws import Kind
from stoa import config
from stoa.deps import get_actor, get_authorization_audit_sink, get_verified_token
from stoa.routers import admin, teacher_applications
from stoa.security.identity import AccountStatus, Actor, CanonicalRole, CapabilityGrant
from stoa.security.tokens import VerifiedAccessToken


class _Cognito:
    """A stand-in for a cognito-idp client; the services are replaced too."""


@pytest.fixture
def cognito_clients() -> Callable[[], list[aws.Request]]:
    """What the getters asked `stoa.aws` for; each request gets a `_Cognito`."""
    aws.install({Kind.COGNITO: _Cognito()})
    return aws.requests


def _identity_manager() -> Actor:
    return Actor(
        "admin-1",
        "https://identity.test",
        "admin-subject",
        CanonicalRole.ADMIN,
        AccountStatus.ACTIVE,
        "admin",
        (CapabilityGrant("admin_identity_manager", "global", 1),),
    )


def _admin_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    app.dependency_overrides[get_actor] = _identity_manager
    return app


def test_teacher_activation_resolves_its_identity_provider(monkeypatch, cognito_clients):
    seen: dict[str, Any] = {}
    # The route declares its success body (#392), so the stub answers with one.
    activated = {
        "status": "active",
        "userId": "teacher_1",
        "applicationId": "application_1",
        "applicationVersion": 1,
        "evidenceReference": "teacher-activation:command_1",
        "email": "teacher@stoa.test",
    }

    def activate_from_invitation(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return activated

    monkeypatch.setattr(
        teacher_applications.teacher_application_service,
        "activate_from_invitation",
        activate_from_invitation,
    )
    app = FastAPI()
    app.include_router(teacher_applications.router, prefix="/teacher-applications")
    app.dependency_overrides[get_verified_token] = lambda: VerifiedAccessToken(
        "https://identity.test",
        "teacher-subject",
        "client-1",
        (),
        verified_email="teacher@stoa.test",
        issued_at=1,
    )

    # Twice: a cache over the getter would only be exercised by the second request.
    for _ in range(2):
        response = TestClient(app).post(
            "/teacher-applications/activation/consume",
            json={"invitation_token": "t" * 32},
        )
        assert response.status_code == 200, response.text
        assert response.json() == activated
        assert isinstance(seen["provider"], _Cognito)
    assert seen["verified_email"] == "teacher@stoa.test"
    assert [(r.kind, r.region) for r in cognito_clients()] == [
        (Kind.COGNITO, config.settings().aws_region)
    ] * 2


def test_provisioning_an_admin_resolves_its_identity_provider(monkeypatch, cognito_clients):
    seen: dict[str, Any] = {}

    def provision_admin(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"status": "provisioned"}

    monkeypatch.setattr(admin.privileged_identity_service, "provision_admin", provision_admin)

    response = TestClient(_admin_app()).post(
        "/admin/privileged-identities/admins",
        json={
            "command_id": "command-1",
            "target_email": "target@example.test",
            "issuer": "https://identity.test",
            "subject": "target-subject",
            "reason": "approved command",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "provisioned"}
    assert isinstance(seen["provider"], _Cognito)
    assert [(r.kind, r.region) for r in cognito_clients()] == [
        (Kind.COGNITO, config.settings().aws_region)
    ]


def test_changing_an_admins_status_resolves_its_identity_provider(monkeypatch, cognito_clients):
    seen: dict[str, Any] = {}

    def change_admin_status(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"status": "suspended"}

    monkeypatch.setattr(admin.privileged_identity_service, "change_admin_status", change_admin_status)

    response = TestClient(_admin_app()).post(
        "/admin/privileged-identities/admins/target-1/status",
        json={
            "command_id": "command-2",
            "operation": "suspend",
            "provider_username": "target-subject",
            "reason": "approved command",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "suspended"}
    assert seen["target_id"] == "target-1"
    assert isinstance(seen["provider"], _Cognito)
    assert [(r.kind, r.region) for r in cognito_clients()] == [
        (Kind.COGNITO, config.settings().aws_region)
    ]
