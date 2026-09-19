"""Closed contracts for cards 002-A and 002-E: no self sign-up, no self recovery."""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from stoa.config import Settings, get_settings
from stoa.routers import auth


BACKEND_ROOT = Path(__file__).resolve().parents[1]

_DECOMMISSIONED_BODY = {
    "detail": {
        "code": "",
        "message": "This is no longer available. Ask your STOA administrator.",
    }
}


def _settings() -> Settings:
    return Settings(
        aws_region="eu-central-2",
        cognito_user_pool_id="pool-id",
        cognito_student_client_id="student-client",
        cognito_parent_client_id="parent-client",
        cognito_teacher_client_id="teacher-client",
        cognito_admin_client_id="admin-client",
    )


class _RecordingCognito:
    """Any provider call at all is a failure for a decommissioned route."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, operation: str):
        def record(**_kwargs):
            self.calls.append(operation)
            return {}

        return record


def _auth_client(monkeypatch) -> tuple[TestClient, _RecordingCognito]:
    provider = _RecordingCognito()
    monkeypatch.setattr(auth, "_get_cognito", lambda _settings: provider)
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_settings] = _settings
    return TestClient(app), provider


def _user_pool_keywords() -> dict[str, ast.expr]:
    """Read the declared Cognito user pool arguments out of the CDK source."""

    infra_root = BACKEND_ROOT.parent / "stoa-infra"
    source = infra_root / "stacks" / "auth_stack.py"
    if not source.is_file():
        pytest.skip("stoa-infra is not checked out next to stoa-backend")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Attribute) and target.attr == "UserPool":
            return {
                keyword.arg: keyword.value
                for keyword in node.keywords
                if keyword.arg is not None
            }
    raise AssertionError("no cognito.UserPool construct found in auth_stack.py")


def _attribute_path(node: ast.expr) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def test_cognito_user_pool_is_admin_create_only():
    keywords = _user_pool_keywords()
    declared = keywords.get("self_sign_up_enabled")
    assert declared is not None, "self_sign_up_enabled must stay declared, not defaulted"
    assert isinstance(declared, ast.Constant) and declared.value is False


def test_cognito_account_recovery_is_none():
    keywords = _user_pool_keywords()
    declared = keywords.get("account_recovery")
    assert declared is not None, "account_recovery must stay declared, not defaulted"
    assert _attribute_path(declared) == "cognito.AccountRecovery.NONE"


def test_backend_gates_agree_with_the_declared_user_pool():
    """Drift between the API gate and the provider gate is itself the fault."""
    keywords = _user_pool_keywords()
    assert auth.PUBLIC_SELF_REGISTRATION_ENABLED is keywords["self_sign_up_enabled"].value
    assert auth.SELF_SERVICE_PASSWORD_RECOVERY_ENABLED is (
        _attribute_path(keywords["account_recovery"]) != "cognito.AccountRecovery.NONE"
    )


def test_public_registration_is_refused_without_touching_the_provider(monkeypatch):
    client, provider = _auth_client(monkeypatch)

    response = client.post(
        "/auth/register",
        json={
            "email": "learner@example.com",
            "password": "ValidPass123",
            "role": "student",
        },
    )

    assert response.status_code == 410
    assert response.json() == {
        **_DECOMMISSIONED_BODY,
        "detail": {
            **_DECOMMISSIONED_BODY["detail"],
            "code": "public_registration_closed",
        },
    }
    assert provider.calls == []


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/auth/forgot-password", {"email": "learner@example.com"}),
        (
            "/auth/reset-password",
            {
                "email": "learner@example.com",
                "confirmationCode": "123456",
                "newPassword": "ValidPass123",
            },
        ),
    ],
)
def test_password_recovery_is_refused_without_touching_the_provider(
    monkeypatch, path, payload
):
    client, provider = _auth_client(monkeypatch)

    response = client.post(path, json=payload)

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "password_recovery_closed"
    assert provider.calls == []


def test_registration_payload_validation_still_runs_before_the_gate(monkeypatch):
    """A rejected payload must not reach the provider either."""
    client, provider = _auth_client(monkeypatch)

    response = client.post(
        "/auth/register",
        json={"email": "learner@example.com", "password": "ValidPass123", "role": "admin"},
    )

    assert response.status_code == 422
    assert provider.calls == []
