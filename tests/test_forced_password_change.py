"""Card 002-D / A2: an administrator password reset the account can recover from.

The reset used to hand the account a temporary password and park it in the
provider's own FORCE_CHANGE_PASSWORD challenge, which this build answers on no
route at all; with self-service recovery closed as well, the account signed in
nowhere. The obligation is carried locally now, and these tests hold the three
things that has to mean: the sign-in still succeeds, every route but the
password change is refused while the flag is up, and completing the change puts
the account back. The negative half matters as much — a change that failed must
leave the flag exactly where it was.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException, params
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from audit_helpers import MemoryAuthorizationAuditSink
from test_account_provisioning import FakeAccountTable

from stoa.config import Settings, get_settings
from stoa.db.repositories import (
    account_deletion_repo,
    account_invitation_repo,
    account_number_repo,
    identity_repo,
    parent_link_repo,
    security_audit_repo,
    user_repo,
)
from stoa.deps import (
    FORCED_PASSWORD_CHANGE_EXEMPT_ROUTES,
    _forced_password_change_exempt,
    get_actor,
    get_authorization_audit_sink,
    get_deletion_command,
    get_identity_repository,
    get_verified_token,
)
from stoa.routers import admin, auth, parents, students
from stoa.security.identity import MUST_CHANGE_PASSWORD_FIELD, Actor
from stoa.services.account_deletion_service import DeletionReceipt
from stoa.security.route_inventory import (
    _walk_dependants,
    explicit_route_classification,
    inventory_application,
)
from stoa.security.tokens import VerifiedAccessToken
from stoa.services import parent_link_service, account_numbering_service


# DELETE /auth/me never resolves an Actor: it is served from its own
# verified-subject deletion command, so this gate is not on its path. It is
# named here rather than left to be discovered, and it is the only one.
UNGATED_AUTHENTICATED_ROUTES = {("DELETE", "/auth/me")}

TEST_USER = "student-9"
TEST_EMAIL = "student-9@example.com"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeAccountTable:
    fake = FakeAccountTable()
    for module in (
        account_invitation_repo,
        account_number_repo,
        account_deletion_repo,
        identity_repo,
        parent_link_repo,
        security_audit_repo,
        user_repo,
        admin,
        auth,
        parents,
    ):
        monkeypatch.setattr(module, "get_table", lambda fake=fake: fake)
    parent_link_service.set_account_number_resolver(account_numbering_service.resolve_account_id)
    return fake


def _settings() -> Settings:
    return Settings(
        aws_region="eu-central-2",
        cognito_user_pool_id="eu-central-2_test",
        cognito_student_client_id="student-client",
    )


def _seed_profile(
    table: FakeAccountTable,
    user_id: str = TEST_USER,
    role: str = "student",
    *,
    must_change_password: bool | None = None,
) -> None:
    profile: dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": role,
        "account_status": "active",
        "email": f"{user_id}@stoa.test",
        "name": user_id,
        "account_number": "S26-0007",
        "preferred_locale": "de",
        "created_at": "2026-03-01T09:00:00+00:00",
        "version": 1,
    }
    if must_change_password is not None:
        profile[MUST_CHANGE_PASSWORD_FIELD] = must_change_password
    table.rows[(f"USER#{user_id}", "PROFILE")] = profile
    table.rows[(f"USER#{user_id}", "ACCOUNT_FENCE")] = {
        "PK": f"USER#{user_id}",
        "SK": "ACCOUNT_FENCE",
        "generation": 1,
        "status": "active",
    }


def _stored_flag(table: FakeAccountTable, user_id: str = TEST_USER) -> Any:
    return table.rows[(f"USER#{user_id}", "PROFILE")].get(MUST_CHANGE_PASSWORD_FIELD)


class ProfileBackedIdentityRepository:
    """Resolve the actor from the same profile row the gate and the clear share."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    async def get_binding(self, issuer: str, subject: str) -> dict[str, Any]:
        return {"status": "active", "user_id": self.user_id}

    async def get_account_fence(self, user_id: str) -> dict[str, Any]:
        return {"status": "active", "generation": 1}

    async def get_account(self, user_id: str) -> Any:
        return user_repo.get_user(user_id)

    async def get_current_grants(self, user_id: str) -> list[dict[str, Any]]:
        return []


class RecordingPasswordAdministrator:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failure = failure

    def admin_set_user_password(self, **kwargs: Any) -> dict[str, Any]:
        if self.failure is not None:
            raise self.failure
        self.calls.append(kwargs)
        return {}


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "provider said no"}}, "ChangePassword")


class FakeCognito:
    """Only the three calls this card's paths make, each one recorded."""

    def __init__(self, *, change_password_error: ClientError | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.change_password_error = change_password_error

    def initiate_auth(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("initiate_auth", kwargs))
        return {"AuthenticationResult": {"AccessToken": "access-token", "ExpiresIn": 3600}}

    def change_password(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("change_password", kwargs))
        if self.change_password_error is not None:
            raise self.change_password_error
        return {}


def _full_app() -> FastAPI:
    """Main's router graph minus the one uncommitted router it cannot project."""
    from stoa.routers import (
        adaptive,
        billing,
        conversations,
        files,
        notifications,
        practice,
        questions,
        teacher_applications,
        teachers,
    )

    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.include_router(conversations.router, prefix="/conversations")
    app.include_router(conversations.teacher_help_router, prefix="/teacher-help")
    app.include_router(practice.router, prefix="/practice")
    app.include_router(questions.router, prefix="/questions")
    app.include_router(students.router, prefix="/students")
    app.include_router(teachers.router, prefix="/teachers")
    app.include_router(teacher_applications.router, prefix="/teacher-applications")
    app.include_router(parents.router, prefix="/parents")
    app.include_router(billing.router, prefix="/billing")
    app.include_router(notifications.router, prefix="/notifications")
    app.include_router(notifications.admin_router, prefix="/admin")
    app.include_router(adaptive.router, prefix="/adaptive")
    app.include_router(admin.router, prefix="/admin")
    app.include_router(files.router, prefix="/files")

    @app.get("/health")
    @explicit_route_classification("public", "load-balancer health probe")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    return app


def _signed_in_app(app: FastAPI, *, role: str = "student", user_id: str = TEST_USER) -> FastAPI:
    """Authenticate for real: only the token and the repository are doubled.

    `get_actor` itself is deliberately left alone, because the gate under test
    lives inside it. A test that overrode it would prove nothing.
    """
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_verified_token] = lambda: VerifiedAccessToken(
        issuer="https://identity.test",
        subject="subject-1",
        client_id="student-client",
        groups=(f"{role}s",),
    )
    app.dependency_overrides[get_identity_repository] = (
        lambda: ProfileBackedIdentityRepository(user_id)
    )
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return app


def _admin_app(table: FakeAccountTable, password_provider: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, {"sub": "admin-1", "role": "admin", "accountStatus": "active"})
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[admin.get_account_password_administrator] = (
        lambda: password_provider
    )
    return app


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


# ---------------------------------------------------------------------------
# The reset raises the flag, and the account can still sign in
# ---------------------------------------------------------------------------


def test_管理员重置后标记落库且临时密码是永久密码(table: FakeAccountTable) -> None:
    _seed_profile(table)
    provider = RecordingPasswordAdministrator()
    client = TestClient(_admin_app(table, provider))

    response = client.post(
        "/admin/users/student-9/password-reset", json={"reason": "support call 4711"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["mustChangePasswordAtNextSignIn"] is True
    assert _stored_flag(table) is True
    # Permanent=True is the whole point: a non-permanent password would leave the
    # account in a provider challenge this build answers on no route.
    assert provider.calls[0]["Permanent"] is True


def test_重置后登录成功并且回执带着这条义务(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_profile(table)
    client = TestClient(_admin_app(table, RecordingPasswordAdministrator()))
    client.post("/admin/users/student-9/password-reset", json={"reason": "support"})

    fake = FakeCognito()
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)

    async def resolve_token(*_args: Any, **_kwargs: Any):
        return SimpleNamespace(user_id=TEST_USER), user_repo.get_user(TEST_USER)

    monkeypatch.setattr(
        auth.public_identity_service, "resolve_account_access_token", resolve_token
    )

    login_app = FastAPI()
    login_app.include_router(auth.router, prefix="/auth")
    login_app.dependency_overrides[get_settings] = _settings
    login = TestClient(login_app).post(
        "/auth/login", json={"email": TEST_EMAIL, "password": "TempPass123"}
    )

    assert login.status_code == 200, login.text
    assert login.json()["accessToken"] == "access-token"
    assert login.json()["user"]["mustChangePassword"] is True


def test_没有被重置的账号登录回执里这条是假(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control on the projection itself: it is not always true."""
    _seed_profile(table)
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: FakeCognito())

    async def resolve_token(*_args: Any, **_kwargs: Any):
        return SimpleNamespace(user_id=TEST_USER), user_repo.get_user(TEST_USER)

    monkeypatch.setattr(
        auth.public_identity_service, "resolve_account_access_token", resolve_token
    )

    login_app = FastAPI()
    login_app.include_router(auth.router, prefix="/auth")
    login_app.dependency_overrides[get_settings] = _settings
    login = TestClient(login_app).post(
        "/auth/login", json={"email": TEST_EMAIL, "password": "OwnPass123"}
    )

    assert login.status_code == 200, login.text
    assert login.json()["user"]["mustChangePassword"] is False


# ---------------------------------------------------------------------------
# The gate: everything but the password change is refused
# ---------------------------------------------------------------------------


def _authenticated_routes() -> list[tuple[str, str]]:
    return [
        (item.method, item.path)
        for item in inventory_application(_full_app())
        if item.classification not in {"public", "safe-public"}
    ]


def test_带标记时每一条需要身份的路由都是403(table: FakeAccountTable) -> None:
    _seed_profile(table, must_change_password=True)
    client = TestClient(_signed_in_app(_full_app()))

    refused: list[tuple[str, str]] = []
    admitted: list[tuple[str, str, int]] = []
    for method, path in _authenticated_routes():
        if (method, path) in UNGATED_AUTHENTICATED_ROUTES:
            continue
        url = path.replace("{", "").replace("}", "")
        for segment in ("user_id", "student_id", "parent_id", "invitation_id"):
            url = url.replace(segment, "x")
        response = client.request(method, url, json={}, headers=_auth_headers())
        if response.status_code == 403:
            refused.append((method, path))
        else:
            admitted.append((method, path, response.status_code))

    expected_open = {
        (method, path)
        for method, path in FORCED_PASSWORD_CHANGE_EXEMPT_ROUTES
    }
    assert {(method, path) for method, path, _ in admitted} == expected_open, admitted
    assert len(refused) > 100, len(refused)


def test_没有标记时同一批路由不会被这道闸挡住(table: FakeAccountTable) -> None:
    """Negative control on the gate: it is the flag that refuses, not the harness."""
    _seed_profile(table, must_change_password=False)
    client = TestClient(_signed_in_app(_full_app()))

    response = client.patch(
        "/auth/me/preferences/locale",
        json={"preferredLocale": "fr"},
        headers=_auth_headers(),
    )

    assert response.status_code == 200, response.text


def test_豁免清单恰好是这三条(table: FakeAccountTable) -> None:
    assert FORCED_PASSWORD_CHANGE_EXEMPT_ROUTES == frozenset(
        {
            ("GET", "/auth/me"),
            ("POST", "/auth/password-change/request"),
            ("POST", "/auth/password-change/confirm"),
        }
    )


# ---------------------------------------------------------------------------
# Card 006: the one route that resolves no Actor has to earn that, every run
# ---------------------------------------------------------------------------


def _routes_without_actor_resolution(app: FastAPI) -> dict[tuple[str, str], frozenset[Any]]:
    """Every authenticated route whose dependency graph never reaches `get_actor`.

    Read off the graph FastAPI will actually execute, so a route cannot get on or
    off this answer by being named anywhere.
    """
    authenticated = {
        (item.method, item.path)
        for item in inventory_application(app)
        if item.classification not in {"public", "safe-public"}
    }
    bypass: dict[tuple[str, str], frozenset[Any]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        calls = frozenset(dependant.call for dependant in _walk_dependants(route.dependant))
        for method in route.methods:
            if (method, route.path) in authenticated and get_actor not in calls:
                bypass[(method, route.path)] = calls
    return bypass


def test_不解析Actor的路由只能是那条销户命令本身() -> None:
    """`get_actor` carries every gate there is, so skipping it needs a reason.

    The reason is not membership in a list - a list would be satisfied by adding
    the next bypass to it. The only reason this accepts is that the route *is*
    the deletion command: its dependency graph reaches `get_deletion_command`,
    whose own authority is pinned by the test below. Any other route that stops
    resolving an Actor fails here and cannot be argued out of it.
    """
    app = _full_app()
    bypass = _routes_without_actor_resolution(app)

    # Harness control: a route that does resolve an Actor is not reported here.
    assert ("PATCH", "/auth/me/preferences/locale") not in bypass

    unjustified = {
        route for route, calls in bypass.items() if get_deletion_command not in calls
    }
    assert unjustified == set(), unjustified


def test_销户命令的身份只能来自已验证的令牌() -> None:
    """Why that one route may skip the Actor: nothing a caller sends reaches it.

    `get_deletion_command` takes no path, query, header, cookie or body input at
    all - only the verified token and the identity repository - so it can act on
    exactly one account, the one the token is bound to. Give it a target
    parameter and this goes red, and with it the justification above.
    """
    sources: dict[str, Any] = {}
    for name, parameter in inspect.signature(get_deletion_command).parameters.items():
        assert isinstance(parameter.default, params.Depends), name
        sources[name] = parameter.default.dependency

    assert set(sources.values()) == {get_verified_token, get_identity_repository}


def test_旁路清单与依赖图推出来的一致() -> None:
    """The hand-written naming stays honest: it is exactly what the graph says."""
    assert set(_routes_without_actor_resolution(_full_app())) == UNGATED_AUTHENTICATED_ROUTES


def _terminal_receipt() -> DeletionReceipt:
    """Stand in for the deletion machinery only.

    These two tests are about what gates the route, not about what it erases, so
    the command is already terminal and the handler queues no follow-up work.
    """
    return DeletionReceipt(
        command_id="command-1",
        status="deleted",
        accepted_at="2026-09-21T10:00:00+00:00",
        completed_at="2026-09-21T10:00:01+00:00",
    )


def test_新挂到Actor上的闸不会落到销户路径上(table: FakeAccountTable) -> None:
    """Card 002 #5: the bypass is a decision, and this is where it is held.

    A future gate will be hung where every existing one is - inside `get_actor` -
    so that is what gets hung here, and the deletion command still answers. The
    same run carries its own negative control: the locale route does resolve an
    Actor, so the new gate refuses it. Without that half the test would pass on a
    gate that never fired.

    Deliberate, not incidental: the account being erased may already have lost
    the facts `get_actor` needs, so requiring it would make erasure fail exactly
    where it matters most. A gate that must also bind erasure therefore belongs
    on `get_deletion_command`, not on `get_actor`, and this going red is the
    reminder.
    """
    _seed_profile(table)
    app = _signed_in_app(_full_app())

    async def _refusing_actor() -> Actor:
        raise HTTPException(status_code=403, detail={"code": "gate_added_later"})

    app.dependency_overrides[get_actor] = _refusing_actor
    app.dependency_overrides[get_deletion_command] = _terminal_receipt
    client = TestClient(app)

    control = client.patch(
        "/auth/me/preferences/locale",
        json={"preferredLocale": "fr"},
        headers=_auth_headers(),
    )
    deletion = client.delete("/auth/me", headers=_auth_headers())

    assert control.status_code == 403, control.text
    assert deletion.status_code == 202, deletion.text


def test_欠着一次改密的账号仍然可以销户(table: FakeAccountTable) -> None:
    """The product call on the one gate that exists today, made executable.

    An account that owes a password change can still close itself. Erasure is not
    a feature the debt withholds, and the alternative - forcing a password onto an
    account on its way out - is a worse answer to ask of somebody leaving. The
    control is the same flag refusing the locale route in the same run.
    """
    _seed_profile(table, must_change_password=True)
    app = _signed_in_app(_full_app())
    app.dependency_overrides[get_deletion_command] = _terminal_receipt
    client = TestClient(app)

    control = client.patch(
        "/auth/me/preferences/locale",
        json={"preferredLocale": "fr"},
        headers=_auth_headers(),
    )
    deletion = client.delete("/auth/me", headers=_auth_headers())

    assert control.status_code == 403, control.text
    assert deletion.status_code == 202, deletion.text


def test_路由没解析出来时不豁免() -> None:
    """A request whose route the gate cannot read is refused, not waved through."""

    class _Request:
        method = "POST"
        scope: dict[str, Any] = {}

    assert _forced_password_change_exempt(_Request()) is False


# ---------------------------------------------------------------------------
# Completing the change puts the account back; failing it does not
# ---------------------------------------------------------------------------


def _confirm(
    table: FakeAccountTable,
    monkeypatch: pytest.MonkeyPatch,
    *,
    cognito: FakeCognito,
    code_accepted: bool = True,
) -> TestClient:
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: cognito)

    def verify_and_consume(user_id: str, code: str) -> None:
        if not code_accepted:
            raise auth.password_change_code_service.PasswordChangeCodeRejected("no")

    monkeypatch.setattr(
        auth.password_change_code_service, "verify_and_consume", verify_and_consume
    )
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    return TestClient(_signed_in_app(app))


def test_改密成功后标记被清掉且原先被拒的端点变成可用(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_profile(table, must_change_password=True)
    client = _confirm(table, monkeypatch, cognito=FakeCognito())

    blocked = client.patch(
        "/auth/me/preferences/locale",
        json={"preferredLocale": "fr"},
        headers=_auth_headers(),
    )
    assert blocked.status_code == 403

    response = client.post(
        "/auth/password-change/confirm",
        json={
            "currentPassword": "TempPass123",
            "code": "012345",
            "newPassword": "BrandNew123",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 200, response.text
    assert _stored_flag(table) is False

    reopened = client.patch(
        "/auth/me/preferences/locale",
        json={"preferredLocale": "fr"},
        headers=_auth_headers(),
    )
    assert reopened.status_code == 200, reopened.text


def test_身份提供方拒绝改密时标记仍在(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_profile(table, must_change_password=True)
    cognito = FakeCognito(change_password_error=_client_error("NotAuthorizedException"))
    client = _confirm(table, monkeypatch, cognito=cognito)

    response = client.post(
        "/auth/password-change/confirm",
        json={
            "currentPassword": "WrongPass123",
            "code": "012345",
            "newPassword": "BrandNew123",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 400
    assert _stored_flag(table) is True


def test_验证码被拒时标记仍在且没碰过提供方(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_profile(table, must_change_password=True)
    cognito = FakeCognito()
    client = _confirm(table, monkeypatch, cognito=cognito, code_accepted=False)

    response = client.post(
        "/auth/password-change/confirm",
        json={
            "currentPassword": "TempPass123",
            "code": "999999",
            "newPassword": "BrandNew123",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 400
    assert _stored_flag(table) is True
    assert cognito.calls == []


def test_清除写不下去时不谎报成功而且标记不动(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The password really changed, so the answer says retry rather than 200."""
    _seed_profile(table, must_change_password=True)
    client = _confirm(table, monkeypatch, cognito=FakeCognito())
    monkeypatch.setattr(
        auth.user_repo,
        "update_profile_fields_versioned",
        lambda *args, **kwargs: user_repo.ProfileWriteResult(
            user_repo.ProfileWriteDisposition.RETRYABLE, attempts=3
        ),
    )

    response = client.post(
        "/auth/password-change/confirm",
        json={
            "currentPassword": "TempPass123",
            "code": "012345",
            "newPassword": "BrandNew123",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "password_change_state_not_cleared"
    assert _stored_flag(table) is True
