"""Card 002-D: the admin account console, invitation activation and link answers."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from test_account_provisioning import FakeAccountTable, RecordingProvider

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
from stoa.routers import admin, auth, parents, students
from stoa.services import notify_service
from stoa.security.route_inventory import explicit_route_classification, inventory_application
from stoa.services import (
    account_numbering_service,
    account_provisioning_service,
    parent_link_service,
)


INVENTORY_PATH = Path(__file__).resolve().parents[1] / "docs/security/route-authorization-inventory.json"

# Written out by hand so a wrong route wiring cannot agree with the assertion.
NEW_ROUTES = {
    ("POST", "/admin/users"): "admin-capability",
    ("POST", "/admin/users/invitations"): "admin-capability",
    ("POST", "/admin/users/invitations/{invitation_id}/reissue"): "admin-capability",
    ("DELETE", "/admin/users/invitations/{invitation_id}"): "admin-capability",
    ("POST", "/admin/users/{user_id}/password-reset"): "admin-capability",
    ("POST", "/admin/users/{user_id}/status"): "admin-capability",
    ("POST", "/admin/users/parent-links"): "admin-capability",
    ("POST", "/parents/me/children/requests"): "authorized",
    ("POST", "/students/me/parent-requests"): "authorized",
    ("POST", "/auth/invitations/claim"): "public",
    ("GET", "/parents/me/children/requests"): "authorized",
    ("POST", "/parents/me/children/requests/{student_id}/confirm"): "authorized",
    ("POST", "/parents/me/children/requests/{student_id}/reject"): "authorized",
    ("GET", "/students/me/parent-requests"): "authorized",
    ("POST", "/students/me/parent-requests/{parent_id}/confirm"): "authorized",
    ("POST", "/students/me/parent-requests/{parent_id}/reject"): "authorized",
}

# Every administrator command this card added, with a body good enough to reach the
# authorization dependency. None of them may answer anything but 403 to a non-admin.
ADMIN_COMMANDS = (
    ("GET", "/admin/users", None),
    ("POST", "/admin/users", {"role": "student", "email": "x@stoa.test"}),
    ("POST", "/admin/users/invitations", {"role": "student", "email": "x@stoa.test"}),
    ("POST", "/admin/users/invitations/inv-1/reissue", {}),
    ("DELETE", "/admin/users/invitations/inv-1", None),
    ("POST", "/admin/users/user-1/password-reset", {"reason": "support call"}),
    ("POST", "/admin/users/user-1/status", {"status": "suspended", "reason": "abuse"}),
    ("PATCH", "/admin/users/user-1", {"name": "New Name"}),
    (
        "POST",
        "/admin/users/parent-links",
        {"parent_id": "parent-a", "student_id": "student-b"},
    ),
)


def build_app_without_analytics() -> FastAPI:
    """Main's router graph minus the one router that is not part of this change.

    `analytics.py` is an uncommitted third-party route whose own declaration does not
    validate, so the registered app cannot be projected at all. Rebuilding the rest in
    main's exact include order keeps this card's drift check executable.
    """
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


class AccountAdminTable(FakeAccountTable):
    """The provisioning fake plus the scan, prefix query and counter this card needs."""

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        """Page the way the real table does: a cursor in and a cursor back out.

        Without `Limit`, `ExclusiveStartKey` and `LastEvaluatedKey` the pagination
        this endpoint advertises could not be falsified by any test - the fake
        returned the whole table and no cursor whatever was asked for.

        `Limit` counts matched rows here. Real DynamoDB counts rows *read*, before
        the filter, so a production page returns at most as many rows as this one;
        that gap is its own finding and is deliberately not modelled here.
        """
        values = kwargs.get("ExpressionAttributeValues") or {}
        role = values.get(":role")
        limit = kwargs.get("Limit")
        start = kwargs.get("ExclusiveStartKey")
        ordered = sorted(key for key in self.rows if key[1] == "PROFILE")
        if start:
            after = (str(start["PK"]), str(start["SK"]))
            ordered = [key for key in ordered if key > after]
        items: list[dict[str, Any]] = []
        response: dict[str, Any] = {}
        for position, key in enumerate(ordered):
            item = self.rows[key]
            if role is not None and item.get("role") != role:
                continue
            items.append(deepcopy(item))
            if limit is not None and len(items) >= int(limit) and position + 1 < len(ordered):
                response["LastEvaluatedKey"] = {"PK": key[0], "SK": key[1]}
                break
        response["Items"] = items
        return response

    def query(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("IndexName") == "GSI-Email":
            condition = kwargs.get("FilterExpression")
            if condition is None:
                return super().query(**kwargs)
            # The real index projects every row carrying the address, not only the
            # profile, which is how an invitation is found from the account it
            # opened. Limit is not passed on this path, so none is honoured.
            expected = kwargs["KeyConditionExpression"].get_expression()["values"][1]
            return {
                "Items": [
                    deepcopy(self.rows[key])
                    for key in sorted(self.rows)
                    if self.rows[key].get("email") == expected
                    and _filter_holds(condition, self.rows[key])
                ]
            }
        terms = _key_terms(kwargs["KeyConditionExpression"])
        partition = terms[("PK", "=")]
        prefix = terms.get(("SK", "begins_with"), "")
        return {
            "Items": [
                deepcopy(item)
                for (pk, sk), item in self.rows.items()
                if pk == partition and sk.startswith(prefix)
            ]
        }

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        expression = str(kwargs.get("UpdateExpression") or "")
        if " ADD " not in f" {expression.strip()} ":
            return super().update_item(**kwargs)
        # Mirror the real grammar: SET clauses first, then the atomic counter.
        assert expression.strip().upper().startswith("SET "), expression
        key = (kwargs["Key"]["PK"], kwargs["Key"]["SK"])
        values = kwargs.get("ExpressionAttributeValues") or {}
        with self.lock:
            row = self.rows.setdefault(key, dict(kwargs["Key"]))
            row["attempts"] = int(row.get("attempts") or 0) + int(values[":one"])
            row["entity_type"] = values[":entity"]
            row["expires_at"] = values[":expires_at"]
            return {"Attributes": {"attempts": row["attempts"]}}

    def audit_events(self) -> list[dict[str, Any]]:
        return [
            deepcopy(row)
            for key, row in self.rows.items()
            if key[0].startswith("SECURITY_AUDIT#")
        ]


def _filter_holds(condition: Any, item: dict[str, Any]) -> bool:
    """Evaluate the boto3 condition tree the route sends, rather than assuming it."""
    built = condition.get_expression()
    operator = built["operator"]
    if operator == "AND":
        return all(_filter_holds(value, item) for value in built["values"])
    if operator == "OR":
        return any(_filter_holds(value, item) for value in built["values"])
    assert operator == "=", f"unsupported filter operator: {operator}"
    return item.get(built["values"][0].name) == built["values"][1]


def _key_terms(expression: Any) -> dict[tuple[str, str], str]:
    terms: dict[tuple[str, str], str] = {}
    pending = [expression]
    while pending:
        built = pending.pop().get_expression()
        if built["operator"] == "AND":
            pending.extend(built["values"])
            continue
        terms[(built["values"][0].name, built["operator"])] = built["values"][1]
    return terms


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> AccountAdminTable:
    fake = AccountAdminTable()
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
    return Settings(cognito_user_pool_id="eu-central-2_test", aws_region="eu-central-2")


class RecordingPasswordAdministrator:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failure = failure

    def admin_set_user_password(self, **kwargs: Any) -> dict[str, Any]:
        if self.failure is not None:
            raise self.failure
        self.calls.append(kwargs)
        return {}


def _admin_user() -> dict[str, Any]:
    return {"sub": "admin-1", "role": "admin", "accountStatus": "active"}


def _app(
    user: dict[str, Any],
    *,
    provider: Any | None = None,
    password_provider: Any | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.include_router(auth.router, prefix="/auth")
    app.include_router(parents.router, prefix="/parents")
    app.include_router(students.router, prefix="/students")
    install_actor_overrides(app, user)
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[admin.get_account_identity_provider] = lambda: (
        provider or RecordingProvider()
    )
    app.dependency_overrides[auth.get_account_identity_provider] = lambda: (
        provider or RecordingProvider()
    )
    app.dependency_overrides[admin.get_account_password_administrator] = lambda: (
        password_provider or RecordingPasswordAdministrator()
    )
    return app


def _seed_profile(
    table: AccountAdminTable,
    user_id: str,
    role: str,
    *,
    status: str = "active",
    account_number: str = "",
    email: str | None = None,
) -> None:
    table.rows[(f"USER#{user_id}", "PROFILE")] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": role,
        "account_status": status,
        "email": email or f"{user_id}@stoa.test",
        "name": user_id,
        "account_number": account_number,
        "created_at": "2026-03-01T09:00:00+00:00",
        "version": 1,
    }
    table.rows[(f"USER#{user_id}", "ACCOUNT_FENCE")] = {
        "PK": f"USER#{user_id}",
        "SK": "ACCOUNT_FENCE",
        "generation": 1,
        "status": "active",
    }


# ---------------------------------------------------------------------------
# Authorization: only an administrator reaches these commands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["student", "parent", "teacher"])
@pytest.mark.parametrize("method,path,body", ADMIN_COMMANDS)
def test_非管理员调用每一个账号管理端点都是403(
    table: AccountAdminTable, role: str, method: str, path: str, body: dict[str, Any] | None
) -> None:
    client = TestClient(_app({"sub": f"{role}-1", "role": role}))
    response = client.request(method, path, json=body)
    assert response.status_code == 403, (method, path, role, response.text)


@pytest.mark.parametrize("method,path,body", ADMIN_COMMANDS)
def test_管理员本人不会被这道判据挡住(
    table: AccountAdminTable, method: str, path: str, body: dict[str, Any] | None
) -> None:
    _seed_profile(table, "user-1", "student")
    client = TestClient(_app(_admin_user()))
    response = client.request(method, path, json=body)
    assert response.status_code != 403, (method, path, response.text)


# ---------------------------------------------------------------------------
# Route inventory
# ---------------------------------------------------------------------------


def test_新端点全部进清单且分类正确() -> None:
    checked = {
        (row["method"], row["path"]): row for row in json.loads(INVENTORY_PATH.read_text())
    }
    for key, classification in NEW_ROUTES.items():
        assert key in checked, key
        assert checked[key]["classification"] == classification, key


def test_清单与去掉analytics的运行时投影逐条一致() -> None:
    """This card's own drift check, independent of the uncommitted analytics router.

    The registered app is covered by the repository-wide projection test. This one
    keeps answering even while `analytics.py` is being edited outside this card.
    """
    runtime = [item.projection() for item in inventory_application(build_app_without_analytics())]
    checked = [
        row
        for row in json.loads(INVENTORY_PATH.read_text())
        if row["family"] != "analytics"
    ]
    assert checked == runtime


# ---------------------------------------------------------------------------
# Invitation claim: rate limit and the enumeration guard it protects
# ---------------------------------------------------------------------------


def _issue(table: AccountAdminTable, email: str = "invitee@stoa.test") -> dict[str, Any]:
    return account_provisioning_service.invite_account(
        actor={
            "user_id": "admin-1",
            "role": "admin",
            "account_status": "active",
            "current_grants": [
                {
                    "capability": "admin_identity_manager",
                    "scope": "global",
                    "status": "active",
                    "version": 1,
                }
            ],
        },
        role="student",
        email=email,
        full_name="Alex Muster",
        now=lambda: datetime.now(UTC),
    )


def test_认领端点未认证即可调用并激活账号(table: AccountAdminTable) -> None:
    issued = _issue(table)
    client = TestClient(_app({"sub": "nobody", "role": "student"}))

    response = client.post(
        "/auth/invitations/claim",
        json={"token": issued["activationToken"], "password": "Startpass1"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
    assert response.json()["accountNumber"] == issued["accountNumber"]


def test_认领端点挂了限流_按调用方地址计数(table: AccountAdminTable) -> None:
    client = TestClient(_app({"sub": "nobody", "role": "student"}))
    body = {"token": "x" * 40, "password": "Startpass1"}

    statuses = [
        client.post("/auth/invitations/claim", json=body).status_code
        for _ in range(auth.INVITATION_CLAIM_MAX_ATTEMPTS + 1)
    ]

    assert statuses[:-1] == [409] * auth.INVITATION_CLAIM_MAX_ATTEMPTS
    assert statuses[-1] == 429
    counters = [
        row
        for key, row in table.rows.items()
        if key[0].startswith("INVITATION_CLAIM_THROTTLE#")
    ]
    assert len(counters) == 1
    assert counters[0]["attempts"] == auth.INVITATION_CLAIM_MAX_ATTEMPTS + 1


def test_限流先于令牌校验计数_成功的认领也付同样的代价(table: AccountAdminTable) -> None:
    issued = _issue(table)
    client = TestClient(_app({"sub": "nobody", "role": "student"}))

    client.post(
        "/auth/invitations/claim",
        json={"token": issued["activationToken"], "password": "Startpass1"},
    )

    counters = [
        row
        for key, row in table.rows.items()
        if key[0].startswith("INVITATION_CLAIM_THROTTLE#")
    ]
    assert counters and counters[0]["attempts"] == 1


def test_限流计数器写不进去时拒绝而不是放行(
    table: AccountAdminTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("counter unavailable")

    monkeypatch.setattr(table, "update_item", refuse)
    client = TestClient(_app({"sub": "nobody", "role": "student"}))

    response = client.post(
        "/auth/invitations/claim", json={"token": "y" * 40, "password": "Startpass1"}
    )

    assert response.status_code == 429


def test_不存在的令牌与已用过的令牌在路由层逐字节相同(table: AccountAdminTable) -> None:
    """The service answers both with identical bytes; the route may not narrow that."""
    issued = _issue(table)
    client = TestClient(_app({"sub": "nobody", "role": "student"}))
    client.post(
        "/auth/invitations/claim",
        json={"token": issued["activationToken"], "password": "Startpass1"},
    )

    spent = client.post(
        "/auth/invitations/claim",
        json={"token": issued["activationToken"], "password": "Startpass1"},
    )
    never_issued = client.post(
        "/auth/invitations/claim",
        json={"token": "z" * len(issued["activationToken"]), "password": "Startpass1"},
    )

    assert spent.status_code == never_issued.status_code == 409
    assert spent.content == never_issued.content
    assert json.loads(spent.content) == {"detail": {"code": "invitation_invalid"}}


def test_路由层没有自己的令牌拒绝分支(table: AccountAdminTable) -> None:
    """Building a second rejection body in the route is how the guard gets hollowed out.

    The service answers every unusable digest with one payload. A route that looks the
    token up itself, or raises its own error, reintroduces the oracle no matter what
    the service does.
    """
    source = Path(auth.__file__).read_text()
    claim_source = source[source.index("def claim_invitation("):]

    assert "HTTPException" not in claim_source
    assert "account_invitation_repo" not in source
    assert "invitation_invalid" not in source
    assert "not_found" not in claim_source


def test_过期令牌与未知令牌仍然是两条服务层自己的答案(table: AccountAdminTable) -> None:
    """Expiry is the one distinction the service itself makes; the route adds none."""
    issued = account_provisioning_service.invite_account(
        actor={
            "user_id": "admin-1",
            "role": "admin",
            "account_status": "active",
            "current_grants": [
                {
                    "capability": "admin_identity_manager",
                    "scope": "global",
                    "status": "active",
                    "version": 1,
                }
            ],
        },
        role="student",
        email="expired@stoa.test",
        invitation_expiry_seconds=60,
        now=lambda: datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
    )
    client = TestClient(_app({"sub": "nobody", "role": "student"}))

    response = client.post(
        "/auth/invitations/claim",
        json={"token": issued["activationToken"], "password": "Startpass1"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "invitation_expired"}}


# ---------------------------------------------------------------------------
# Administrator password reset: the audit row is the whole point
# ---------------------------------------------------------------------------


def test_重置密码恰好多一条审计且内容正确(table: AccountAdminTable) -> None:
    _seed_profile(table, "student-9", "student", account_number="S26-0007")
    provider = RecordingPasswordAdministrator()
    client = TestClient(_app(_admin_user(), password_provider=provider))
    before = len(table.audit_events())

    response = client.post(
        "/admin/users/student-9/password-reset", json={"reason": "support call 4711"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["mustChangePasswordAtNextSignIn"] is True
    after = table.audit_events()
    assert len(after) == before + 1
    event = [row for row in after if row["event_type"] == "account_password_reset"]
    assert len(event) == 1
    assert event[0]["actor_id"] == "admin-1"
    assert event[0]["target_id"] == "student-9"
    assert event[0]["action"] == "reset_account_password"
    assert event[0]["reason_code"] == "support call 4711"
    assert event[0]["evidence_reference"] == "account-number:S26-0007"
    assert provider.calls == [
        {
            "UserPoolId": "eu-central-2_test",
            "Username": "student-9@stoa.test",
            "Password": response.json()["temporaryPassword"],
            "Permanent": True,
        }
    ]


def test_重置密码的明文不会进审计(table: AccountAdminTable) -> None:
    _seed_profile(table, "student-9", "student")
    client = TestClient(_app(_admin_user()))

    response = client.post("/admin/users/student-9/password-reset", json={"reason": "support"})

    password = response.json()["temporaryPassword"]
    assert password not in table.dump()


def test_身份提供方失败时不写审计也不谎报成功(table: AccountAdminTable) -> None:
    _seed_profile(table, "student-9", "student")
    provider = RecordingPasswordAdministrator(failure=RuntimeError("cognito down"))
    client = TestClient(_app(_admin_user(), password_provider=provider))
    before = len(table.audit_events())

    response = client.post("/admin/users/student-9/password-reset", json={"reason": "support"})

    assert response.status_code == 503
    assert len(table.audit_events()) == before


def test_重置不存在的账号是404(table: AccountAdminTable) -> None:
    client = TestClient(_app(_admin_user()))
    response = client.post("/admin/users/ghost/password-reset", json={"reason": "support"})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Card 006: an administrator may not take a peer administrator's credential
# ---------------------------------------------------------------------------


def test_管理员重置自己的密码是允许的(table: AccountAdminTable) -> None:
    """The negative control that stops this becoming a rule that refuses everything.

    An administrator resetting its own password is the only in-product recovery
    there is, so it has to keep working even though the target is an admin.
    """
    _seed_profile(table, "admin-1", "admin", account_number="A26-0001")
    provider = RecordingPasswordAdministrator()
    client = TestClient(_app(_admin_user(), password_provider=provider))

    response = client.post(
        "/admin/users/admin-1/password-reset", json={"reason": "lost my own password"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["mustChangePasswordAtNextSignIn"] is True
    assert len(provider.calls) == 1
    assert response.json()["temporaryPassword"] not in table.dump()
    assert [row["event_type"] for row in table.audit_events()] == ["account_password_reset"]


def test_管理员不能重置另一个管理员的密码(table: AccountAdminTable) -> None:
    _seed_profile(table, "admin-1", "admin")
    _seed_profile(table, "admin-2", "admin")
    provider = RecordingPasswordAdministrator()
    client = TestClient(_app(_admin_user(), password_provider=provider))

    response = client.post(
        "/admin/users/admin-2/password-reset", json={"reason": "i want their session"}
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "account_peer_admin_password_reset_forbidden"
    # No credential was minted and none was handed back.
    assert provider.calls == []
    assert "temporaryPassword" not in response.text
    # The target account is untouched: no forced-change obligation was raised on it.
    assert "must_change_password" not in table.rows[("USER#admin-2", "PROFILE")]


def test_多一个active管理员也挡得住(table: AccountAdminTable) -> None:
    """The judgement is about whose credential this is, not about console survival.

    `_guard_admin_console_survives` would let this through - two other administrators
    stay active - so a rule copied from the status endpoint would not refuse here.
    """
    _seed_profile(table, "admin-1", "admin")
    _seed_profile(table, "admin-2", "admin")
    _seed_profile(table, "admin-3", "admin")
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/admin-2/password-reset", json={"reason": "support"}
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "account_peer_admin_password_reset_forbidden"


def test_被挡下的重置留痕恰好一条且内容正确(table: AccountAdminTable) -> None:
    _seed_profile(table, "admin-1", "admin")
    _seed_profile(table, "admin-2", "admin")
    client = TestClient(_app(_admin_user()))

    client.post("/admin/users/admin-2/password-reset", json={"reason": "support"})

    denied = [
        row
        for row in table.audit_events()
        if row["event_type"] == "account_password_reset_denied"
    ]
    assert len(denied) == 1
    assert denied[0]["actor_id"] == "admin-1"
    assert denied[0]["target_id"] == "admin-2"
    assert denied[0]["action"] == "reset_account_password"
    assert denied[0]["reason_code"] == "account_peer_admin_password_reset_forbidden"
    assert denied[0]["evidence_reference"] == (
        "account_password_reset_denied:account_peer_admin_password_reset_forbidden"
    )
    assert not [
        row for row in table.audit_events() if row["event_type"] == "account_password_reset"
    ]


def test_重置非管理员账号不受这条判据影响(table: AccountAdminTable) -> None:
    """Second negative control: the refusal is keyed on the target's role."""
    _seed_profile(table, "admin-1", "admin")
    for user_id, role in (("student-9", "student"), ("teacher-3", "teacher"), ("parent-2", "parent")):
        _seed_profile(table, user_id, role)
    client = TestClient(_app(_admin_user()))

    for user_id in ("student-9", "teacher-3", "parent-2"):
        response = client.post(
            f"/admin/users/{user_id}/password-reset", json={"reason": "support"}
        )
        assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Status machine
# ---------------------------------------------------------------------------


def test_停用与启用往返且每次都留痕(table: AccountAdminTable) -> None:
    _seed_profile(table, "student-9", "student")
    client = TestClient(_app(_admin_user()))

    suspended = client.post(
        "/admin/users/student-9/status", json={"status": "suspended", "reason": "abuse report"}
    )
    assert suspended.status_code == 200, suspended.text
    assert table.rows[("USER#student-9", "PROFILE")]["account_status"] == "suspended"
    assert table.rows[("USER#student-9", "PROFILE")]["is_active"] is False

    restored = client.post(
        "/admin/users/student-9/status", json={"status": "active", "reason": "cleared"}
    )
    assert restored.status_code == 200, restored.text
    assert table.rows[("USER#student-9", "PROFILE")]["account_status"] == "active"

    events = [
        row for row in table.audit_events() if row["event_type"] == "account_status_changed"
    ]
    assert len(events) == 2
    assert {row["evidence_reference"] for row in events} == {
        "account_status:active->suspended",
        "account_status:suspended->active",
    }


def test_归档是终态且没有物理删除的路径(table: AccountAdminTable) -> None:
    _seed_profile(table, "student-9", "student")
    client = TestClient(_app(_admin_user()))
    client.post("/admin/users/student-9/status", json={"status": "archived", "reason": "left"})

    revive = client.post(
        "/admin/users/student-9/status", json={"status": "active", "reason": "back"}
    )

    assert revive.status_code == 409
    assert revive.json()["detail"]["code"] == "account_status_transition_invalid"
    assert ("USER#student-9", "PROFILE") in table.rows
    assert not any(
        route.methods == {"DELETE"} and "/admin/users/{user_id}" == route.path
        for route in admin.router.routes
        if hasattr(route, "methods")
    )


def test_被邀请的账号不能被管理员直接激活(table: AccountAdminTable) -> None:
    _seed_profile(table, "student-9", "student", status="invited")
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/student-9/status", json={"status": "active", "reason": "shortcut"}
    )

    assert response.status_code == 409
    assert table.rows[("USER#student-9", "PROFILE")]["account_status"] == "invited"


def test_并发状态切换只有一个赢(table: AccountAdminTable) -> None:
    _seed_profile(table, "student-9", "student")
    client = TestClient(_app(_admin_user()))
    body = {"status": "suspended", "reason": "abuse"}

    first = client.post("/admin/users/student-9/status", json=body)
    second = client.post("/admin/users/student-9/status", json=body)

    assert first.status_code == 200
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# Card 002-D / B7: the administrators protect each other
# ---------------------------------------------------------------------------


def test_只剩一个active管理员时停用自己是409(table: AccountAdminTable) -> None:
    _seed_profile(table, "admin-1", "admin")
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/admin-1/status", json={"status": "suspended", "reason": "oops"}
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "account_self_deactivation_forbidden"
    assert table.rows[("USER#admin-1", "PROFILE")]["account_status"] == "active"


def test_自己归档自己同样被挡(table: AccountAdminTable) -> None:
    _seed_profile(table, "admin-1", "admin")
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/admin-1/status", json={"status": "archived", "reason": "leaving"}
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "account_self_deactivation_forbidden"


def test_停用最后一个active管理员是409(table: AccountAdminTable) -> None:
    """Not self: the actor is an administrator whose own account is already down."""
    _seed_profile(table, "admin-1", "admin", status="suspended")
    _seed_profile(table, "admin-2", "admin")
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/admin-2/status", json={"status": "suspended", "reason": "lockout"}
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "account_last_active_admin"
    assert table.rows[("USER#admin-2", "PROFILE")]["account_status"] == "active"


def test_还有两个active管理员时可以停用其中一个(table: AccountAdminTable) -> None:
    """The negative control: a rule that refused everything would also pass above."""
    _seed_profile(table, "admin-1", "admin")
    _seed_profile(table, "admin-2", "admin")
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/admin-2/status", json={"status": "suspended", "reason": "rotation"}
    )

    assert response.status_code == 200, response.text
    assert table.rows[("USER#admin-2", "PROFILE")]["account_status"] == "suspended"


def test_最后一个管理员的判据不牵连普通账号(table: AccountAdminTable) -> None:
    _seed_profile(table, "admin-1", "admin")
    _seed_profile(table, "student-9", "student")
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/student-9/status", json={"status": "suspended", "reason": "abuse"}
    )

    assert response.status_code == 200, response.text


def test_被挡下的停用也留痕(table: AccountAdminTable) -> None:
    _seed_profile(table, "admin-1", "admin", status="suspended")
    _seed_profile(table, "admin-2", "admin")
    client = TestClient(_app(_admin_user()))

    client.post("/admin/users/admin-2/status", json={"status": "suspended", "reason": "lockout"})

    denied = [
        row
        for row in table.audit_events()
        if row["event_type"] == "account_status_change_denied"
    ]
    assert len(denied) == 1
    assert denied[0]["actor_id"] == "admin-1"
    assert denied[0]["target_id"] == "admin-2"
    assert denied[0]["action"] == "change_account_status"
    assert denied[0]["reason_code"] == "account_last_active_admin"
    assert not [
        row for row in table.audit_events() if row["event_type"] == "account_status_changed"
    ]


# ---------------------------------------------------------------------------
# Profile edit
# ---------------------------------------------------------------------------


def test_编辑资料留下改前改后(table: AccountAdminTable) -> None:
    _seed_profile(table, "student-9", "student")
    client = TestClient(_app(_admin_user()))

    response = client.patch("/admin/users/student-9", json={"name": "Neuer Name", "grade": "8"})

    assert response.status_code == 200, response.text
    event = [
        row for row in table.audit_events() if row["event_type"] == "account_profile_edited"
    ]
    assert len(event) == 1
    assert event[0]["actor_id"] == "admin-1"
    assert event[0]["target_id"] == "student-9"
    assert event[0]["action"] == "update_account_profile"
    assert "name:student-9->Neuer Name" in event[0]["evidence_reference"]
    assert "grade:None->8" in event[0]["evidence_reference"]


# ---------------------------------------------------------------------------
# Account list
# ---------------------------------------------------------------------------


def test_列表按角色分组并显示确认过的绑定(table: AccountAdminTable) -> None:
    _seed_profile(table, "parent-a", "parent", account_number="P26-0001")
    _seed_profile(table, "student-b", "student", account_number="S26-0001")
    _seed_profile(table, "teacher-c", "teacher", account_number="T26-0001")
    parent_link_service.assign_link(
        parent_id="parent-a", student_id="student-b", actor_id="admin-1"
    )
    client = TestClient(_app(_admin_user()))

    payload = client.get("/admin/users").json()

    assert payload["groups"] == {"parent": 1, "student": 1, "teacher": 1}
    rows = {row["userId"]: row for row in payload["items"]}
    assert rows["parent-a"]["linkedAccounts"] == [
        {"userId": "student-b", "accountNumber": "S26-0001", "status": "active"}
    ]
    assert rows["student-b"]["linkedAccounts"] == [
        {"userId": "parent-a", "accountNumber": "P26-0001", "status": "active"}
    ]
    assert rows["teacher-c"]["linkedAccounts"] == []


def test_未确认的关联不会出现在绑定列里(table: AccountAdminTable) -> None:
    _seed_profile(table, "parent-a", "parent", account_number="P26-0001")
    _seed_profile(table, "student-b", "student", account_number="S26-0001")
    parent_link_repo.create_link(
        parent_id="parent-a",
        student_id="student-b",
        status=parent_link_repo.STATUS_PENDING,
        initiator_role=parent_link_repo.INITIATOR_PARENT,
        created_by="parent-a",
        linked_at="2026-03-01T09:00:00+00:00",
    )
    client = TestClient(_app(_admin_user()))

    rows = {row["userId"]: row for row in client.get("/admin/users").json()["items"]}

    assert rows["parent-a"]["linkedAccounts"] == []
    assert rows["student-b"]["linkedAccounts"] == []


def test_列表可按角色状态与关键字筛选(table: AccountAdminTable) -> None:
    _seed_profile(table, "student-b", "student", account_number="S26-0001")
    _seed_profile(table, "student-c", "student", account_number="S26-0002", status="suspended")
    client = TestClient(_app(_admin_user()))

    by_status = client.get("/admin/users", params={"status": "suspended"}).json()
    by_keyword = client.get("/admin/users", params={"q": "S26-0001"}).json()

    assert [row["userId"] for row in by_status["items"]] == ["student-c"]
    assert [row["userId"] for row in by_keyword["items"]] == ["student-b"]


def test_列表只发名单上的字段_后加的字段不会自动发布给客服档(
    table: AccountAdminTable,
) -> None:
    """The capability behind this route is the support desk, not the identity manager.

    The row is the account's whole record, so publishing it wholesale means every
    field a later card adds publishes itself too. The last field below stands for
    exactly that card: it is not a secret today and still must not be answered.
    """
    _seed_profile(table, "student-b", "student", account_number="S26-0001")
    row = table.rows[("USER#student-b", "PROFILE")]
    row["stripe_customer_id"] = "cus_SECRET"
    row["cognito_sub"] = "sub-SECRET"
    row["password_change_code_hash"] = "HASH-SECRET"
    row["field_a_later_card_added"] = "NOT-REVIEWED-BY-THIS-CARD"
    client = TestClient(_app(_admin_user()))

    response = client.get("/admin/users")

    assert response.status_code == 200, response.text
    assert set(response.json()["items"][0]) == {
        "userId",
        "accountNumber",
        "name",
        "email",
        "role",
        "accountStatus",
        "createdAt",
        "lastLoginAt",
        "linkedAccounts",
    }
    for leaked in (
        "cus_SECRET",
        "sub-SECRET",
        "HASH-SECRET",
        "NOT-REVIEWED-BY-THIS-CARD",
        "field_a_later_card_added",
    ):
        assert leaked not in response.text, leaked


def test_分页按limit切页_下一页不重不漏(table: AccountAdminTable) -> None:
    for index in range(10):
        _seed_profile(
            table, f"student-{index:02d}", "student", account_number=f"S26-{index:04d}"
        )
    client = TestClient(_app(_admin_user()))

    seen: list[str] = []
    pages: list[int] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 3}
        if cursor:
            params["cursor"] = cursor
        payload = client.get("/admin/users", params=params).json()
        assert len(payload["items"]) <= 3, payload
        if not pages:
            assert payload["nextCursor"], payload
        seen.extend(str(row["userId"]) for row in payload["items"])
        pages.append(len(payload["items"]))
        cursor = payload["nextCursor"]
        assert len(pages) <= 10, pages
        if not cursor:
            break

    # Counting alone would pass while a page repeated a row the next one dropped.
    assert seen == sorted(seen)
    assert len(seen) == len(set(seen))
    assert set(seen) == {f"student-{index:02d}" for index in range(10)}
    assert pages == [3, 3, 3, 1]


def test_被邀请的账号带上可重发的invitationId(table: AccountAdminTable) -> None:
    issued = _issue(table)
    client = TestClient(_app(_admin_user()))

    rows = {row["userId"]: row for row in client.get("/admin/users").json()["items"]}

    assert rows[issued["userId"]]["accountStatus"] == "invited"
    assert rows[issued["userId"]]["invitationId"] == issued["invitationId"]


def test_列表给出的invitationId能直接重发_而账号id不能(
    table: AccountAdminTable, ses: RecordingSes
) -> None:
    issued = _issue(table)
    client = TestClient(_app(_admin_user()))
    row = client.get("/admin/users").json()["items"][0]

    accepted = client.post(
        f"/admin/users/invitations/{row['invitationId']}/reissue", json={}
    )
    refused = client.post(f"/admin/users/invitations/{issued['userId']}/reissue", json={})

    assert accepted.status_code == 200, accepted.text
    assert refused.status_code == 404
    assert refused.json()["detail"]["code"] == "invitation_not_found"


def test_重发之后列表给出的是新的invitationId(
    table: AccountAdminTable, ses: RecordingSes
) -> None:
    issued = _issue(table)
    client = TestClient(_app(_admin_user()))

    reissued = client.post(
        f"/admin/users/invitations/{issued['invitationId']}/reissue", json={}
    ).json()
    row = client.get("/admin/users").json()["items"][0]

    assert row["invitationId"] == reissued["invitationId"]
    assert row["invitationId"] != issued["invitationId"]


def test_列表带出的是邀请编号而不是令牌(table: AccountAdminTable) -> None:
    """An invitation id is a handle; the token and its digest are the credential."""
    issued = _issue(table)
    client = TestClient(_app(_admin_user()))

    response = client.get("/admin/users")

    assert issued["activationToken"] not in response.text
    assert "token_digest" not in response.text


# ---------------------------------------------------------------------------
# Link answers from both sides
# ---------------------------------------------------------------------------


def _pending(table: AccountAdminTable, initiator: str) -> None:
    _seed_profile(table, "parent-a", "parent", account_number="P26-0001")
    _seed_profile(table, "student-b", "student", account_number="S26-0001")
    parent_link_repo.create_link(
        parent_id="parent-a",
        student_id="student-b",
        status=parent_link_repo.STATUS_PENDING,
        initiator_role=initiator,
        created_by="parent-a" if initiator == parent_link_repo.INITIATOR_PARENT else "student-b",
        # 相对当下播种：请求满 14 天就会过期，写死的日期迟早会自己走出窗口。
        linked_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
    )


def test_学生确认家长发起的请求后关联生效(table: AccountAdminTable) -> None:
    _pending(table, parent_link_repo.INITIATOR_PARENT)
    client = TestClient(_app({"sub": "student-b", "role": "student"}))

    listed = client.get("/students/me/parent-requests")
    confirmed = client.post("/students/me/parent-requests/parent-a/confirm")

    assert [item["parentId"] for item in listed.json()["items"]] == ["parent-a"]
    assert confirmed.status_code == 200, confirmed.text
    assert parent_link_service.active_link("parent-a", "student-b") is not None


def test_发起方不能自己确认自己的请求(table: AccountAdminTable) -> None:
    _pending(table, parent_link_repo.INITIATOR_PARENT)
    client = TestClient(_app({"sub": "parent-a", "role": "parent"}))

    response = client.post("/parents/me/children/requests/student-b/confirm")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "link_confirmation_not_allowed"
    assert parent_link_service.active_link("parent-a", "student-b") is None


def test_家长确认学生发起的请求后关联生效(table: AccountAdminTable) -> None:
    _pending(table, parent_link_repo.INITIATOR_STUDENT)
    client = TestClient(_app({"sub": "parent-a", "role": "parent"}))

    listed = client.get("/parents/me/children/requests")
    confirmed = client.post("/parents/me/children/requests/student-b/confirm")

    assert [item["studentId"] for item in listed.json()["items"]] == ["student-b"]
    assert confirmed.status_code == 200, confirmed.text
    assert parent_link_service.active_link("parent-a", "student-b") is not None


def test_拒绝后关联不生效(table: AccountAdminTable) -> None:
    _pending(table, parent_link_repo.INITIATOR_PARENT)
    client = TestClient(_app({"sub": "student-b", "role": "student"}))

    rejected = client.post("/students/me/parent-requests/parent-a/reject")

    assert rejected.status_code == 200, rejected.text
    assert parent_link_service.active_link("parent-a", "student-b") is None


def test_待确认请求不出现在别人的列表里(table: AccountAdminTable) -> None:
    _pending(table, parent_link_repo.INITIATOR_PARENT)
    _seed_profile(table, "student-c", "student")
    client = TestClient(_app({"sub": "student-c", "role": "student"}))

    assert client.get("/students/me/parent-requests").json()["items"] == []


def test_编号解析器已接线_不退化成拿用户号当编号猜(table: AccountAdminTable) -> None:
    _seed_profile(table, "student-b", "student")
    number = account_numbering_service.allocate_account_number(
        role="student", account_id="student-b", created_at=datetime(2026, 3, 1, tzinfo=UTC)
    )

    assert parent_link_service._resolve_account_number(number) == "student-b"
    assert parent_link_service._resolve_account_number("S26-9999") is None


# ---------------------------------------------------------------------------
# Revoking the legacy binding must also close the link table
# ---------------------------------------------------------------------------


def test_管理员吊销旧绑定时新表的关联一并关闭(
    table: AccountAdminTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_profile(table, "parent-a", "parent")
    _seed_profile(table, "student-b", "student")
    parent_link_service.assign_link(
        parent_id="parent-a", student_id="student-b", actor_id="admin-1"
    )
    monkeypatch.setattr(
        user_repo,
        "transition_parent_student_relationship_status",
        lambda **_kwargs: user_repo.ParentBindingStatusResult(
            user_repo.ParentBindingStatusDisposition.TRANSITIONED, status="revoked", version=2
        ),
    )
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/parent-bindings/status",
        json={
            "parent_id": "parent-a",
            "student_id": "student-b",
            "relationship": "child",
            "expected_status": "active",
            "expected_version": 1,
            "status": "revoked",
            "reason": "guardian withdrew consent",
        },
    )

    assert response.status_code == 200, response.text
    assert parent_link_service.active_link("parent-a", "student-b") is None
    assert any(
        row["event_type"] == "parent_link_revoked" for row in table.audit_events()
    )


# ---------------------------------------------------------------------------
# Creating links: administrator assignment and self-service requests
# ---------------------------------------------------------------------------


def test_管理员分配的关联直接生效且留痕(table: AccountAdminTable) -> None:
    _seed_profile(table, "parent-a", "parent")
    _seed_profile(table, "student-b", "student")
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/parent-links",
        json={"parent_id": "parent-a", "student_id": "student-b"},
    )

    assert response.status_code == 200, response.text
    assert parent_link_service.active_link("parent-a", "student-b") is not None
    event = [row for row in table.audit_events() if row["event_type"] == "parent_link_assigned"]
    assert len(event) == 1
    assert event[0]["actor_id"] == "admin-1"
    assert event[0]["target_id"] == "student-b"
    assert event[0]["action"] == "assign_parent_link"


def test_管理员不能给不存在的学生建关联(table: AccountAdminTable) -> None:
    _seed_profile(table, "parent-a", "parent")
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/parent-links",
        json={"parent_id": "parent-a", "student_id": "ghost"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "link_target_not_found"


def test_家长凭学号发起的请求只到pending(table: AccountAdminTable) -> None:
    _seed_profile(table, "parent-a", "parent")
    _seed_profile(table, "student-b", "student")
    number = account_numbering_service.allocate_account_number(
        role="student", account_id="student-b", created_at=datetime(2026, 3, 1, tzinfo=UTC)
    )
    client = TestClient(_app({"sub": "parent-a", "role": "parent"}))

    response = client.post(
        "/parents/me/children/requests", json={"studentNumber": number}
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"
    assert parent_link_service.active_link("parent-a", "student-b") is None


def test_学生凭家长号发起的请求只到pending(table: AccountAdminTable) -> None:
    _seed_profile(table, "parent-a", "parent")
    _seed_profile(table, "student-b", "student")
    number = account_numbering_service.allocate_account_number(
        role="parent", account_id="parent-a", created_at=datetime(2026, 3, 1, tzinfo=UTC)
    )
    client = TestClient(_app({"sub": "student-b", "role": "student"}))

    response = client.post("/students/me/parent-requests", json={"parentNumber": number})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"
    assert parent_link_service.active_link("parent-a", "student-b") is None


def test_未分配的编号发起请求是404(table: AccountAdminTable) -> None:
    _seed_profile(table, "parent-a", "parent")
    client = TestClient(_app({"sub": "parent-a", "role": "parent"}))

    response = client.post(
        "/parents/me/children/requests", json={"studentNumber": "S26-9999"}
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "link_target_not_found"


def test_自助发起关联挂了频次上限(table: AccountAdminTable) -> None:
    """Uncapped requests are a harassment path: one pending row blocks assignment."""
    _seed_profile(table, "parent-a", "parent")
    client = TestClient(_app({"sub": "parent-a", "role": "parent"}))

    statuses = [
        client.post(
            "/parents/me/children/requests", json={"studentNumber": "S26-9999"}
        ).status_code
        for _ in range(parents.PARENT_LINK_REQUEST_MAX_PER_WINDOW + 1)
    ]

    assert statuses[:-1] == [404] * parents.PARENT_LINK_REQUEST_MAX_PER_WINDOW
    assert statuses[-1] == 429
    assert client.post(
        "/parents/me/children/requests", json={"studentNumber": "S26-9999"}
    ).json()["detail"]["code"] == "link_request_rate_limited"


def test_频次上限按发起人分桶_不牵连别人(table: AccountAdminTable) -> None:
    _seed_profile(table, "parent-a", "parent")
    _seed_profile(table, "parent-b", "parent")
    exhausted = TestClient(_app({"sub": "parent-a", "role": "parent"}))
    for _ in range(parents.PARENT_LINK_REQUEST_MAX_PER_WINDOW + 1):
        exhausted.post("/parents/me/children/requests", json={"studentNumber": "S26-9999"})

    other = TestClient(_app({"sub": "parent-b", "role": "parent"}))
    response = other.post(
        "/parents/me/children/requests", json={"studentNumber": "S26-9999"}
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Invitation delivery: one role-neutral template, four languages
# ---------------------------------------------------------------------------


class RecordingSes:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self.failure = failure

    def send_email(self, **kwargs: Any) -> dict[str, Any]:
        if self.failure is not None:
            raise self.failure
        self.sent.append(kwargs)
        return {"MessageId": "ses-1"}


@pytest.fixture
def ses(monkeypatch: pytest.MonkeyPatch) -> RecordingSes:
    client = RecordingSes()
    monkeypatch.setattr(notify_service.boto3, "client", lambda *_a, **_k: client)
    return client


def test_邀请端点真的把信交给了SES并带上激活链接(
    table: AccountAdminTable, ses: RecordingSes
) -> None:
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/invitations",
        json={"role": "parent", "email": "neu@stoa.test", "fullName": "Änne Müller", "locale": "de"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["invitationDelivered"] is True
    assert len(ses.sent) == 1
    message = ses.sent[0]
    assert message["Destination"]["ToAddresses"] == ["neu@stoa.test"]
    body = message["Message"]["Body"]["Html"]["Data"]
    assert "/activate?token=" in body
    assert response.json()["activationToken"] in body


def test_四语邮件各自成文且用对了变音字符() -> None:
    subjects = {}
    for locale in ("de", "fr", "it", "en"):
        subject, body = notify_service.account_invitation_message(
            activation_token="tok", expires_at="2026-03-04T09:00:00+00:00", locale=locale
        )
        subjects[locale] = subject
        assert "/activate?token=tok" in body
    assert len(set(subjects.values())) == 4
    assert subjects["de"] == "STOA – Ihr Konto freischalten"
    assert "eröffnet" in notify_service.account_invitation_message(
        activation_token="tok", expires_at="x", locale="de"
    )[1]
    assert "é" in notify_service.account_invitation_message(
        activation_token="tok", expires_at="x", locale="fr"
    )[1]


def test_邮件模板是角色中立的_不说教师(
) -> None:
    for locale in ("de", "fr", "it", "en"):
        subject, body = notify_service.account_invitation_message(
            activation_token="tok", expires_at="x", locale=locale
        )
        text = f"{subject} {body}".lower()
        for word in ("lehrperson", "teacher", "enseignant", "insegnante"):
            assert word not in text, (locale, word)


def test_发信失败不谎称已送达_账号仍然建成(
    table: AccountAdminTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    failing = RecordingSes(failure=RuntimeError("ses rejected"))
    monkeypatch.setattr(notify_service.boto3, "client", lambda *_a, **_k: failing)
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/invitations", json={"role": "student", "email": "neu@stoa.test"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["invitationDelivered"] is False
    assert response.json()["activationToken"]
    assert any(
        row["event_type"] == "account_invitation_delivery_failed" for row in table.audit_events()
    )


def test_未指定语言时用默认德语_不崩(table: AccountAdminTable, ses: RecordingSes) -> None:
    client = TestClient(_app(_admin_user()))

    response = client.post(
        "/admin/users/invitations", json={"role": "student", "email": "neu@stoa.test"}
    )

    assert response.status_code == 200, response.text
    assert ses.sent[0]["Message"]["Subject"]["Data"] == "STOA – Ihr Konto freischalten"
