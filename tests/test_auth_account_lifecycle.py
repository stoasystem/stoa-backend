from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings, get_settings
from stoa.deps import get_current_user
from stoa.routers import admin, auth


def _settings() -> Settings:
    return Settings(
        aws_region="eu-central-2",
        cognito_user_pool_id="pool-id",
        cognito_student_client_id="student-client",
        cognito_parent_client_id="parent-client",
        cognito_teacher_client_id="teacher-client",
        cognito_admin_client_id="admin-client",
    )


def _auth_client() -> TestClient:
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_settings] = _settings
    return TestClient(app)


def _admin_client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "admin-1", "role": "admin"}
    return TestClient(app)


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "Cognito")


class FakeCognito:
    def __init__(self):
        self.calls = []

    def admin_create_user(self, **kwargs):
        self.calls.append(("admin_create_user", kwargs))
        return {}

    def admin_set_user_password(self, **kwargs):
        self.calls.append(("admin_set_user_password", kwargs))
        return {}

    def admin_add_user_to_group(self, **kwargs):
        self.calls.append(("admin_add_user_to_group", kwargs))
        return {}

    def initiate_auth(self, **kwargs):
        self.calls.append(("initiate_auth", kwargs))
        return {"AuthenticationResult": {"AccessToken": "access-token"}}

    def forgot_password(self, **kwargs):
        self.calls.append(("forgot_password", kwargs))
        return {"CodeDeliveryDetails": {"Destination": "s***@example.com", "DeliveryMedium": "EMAIL"}}

    def confirm_forgot_password(self, **kwargs):
        self.calls.append(("confirm_forgot_password", kwargs))
        return {}


def test_register_records_email_verification_policy_and_parent_binding(monkeypatch):
    fake = FakeCognito()
    stored = {}
    bindings = []

    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: {
            "user_id": "parent-1",
            "role": "parent",
            "email": email,
            "child_email": "student@example.com",
        }
        if email == "parent@example.com"
        else None,
    )
    monkeypatch.setattr(auth.user_repo, "put_user", lambda profile: stored.update(profile))
    monkeypatch.setattr(
        auth.user_repo,
        "put_parent_student_binding",
        lambda **kwargs: bindings.append(kwargs) or kwargs,
    )

    response = _auth_client().post(
        "/auth/register",
        json={
            "email": "student@example.com",
            "password": "ValidPass123!",
            "role": "student",
            "profile": {"parentEmail": "parent@example.com"},
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["accessToken"] == "access-token"
    assert body["emailVerificationStatus"] == "admin_marked_verified"
    assert stored["email_verification_policy"] == "cognito_email_verified_by_backend_admin_create_user"
    assert stored["email_verification_required"] is False
    assert stored["parent_id"] == "parent-1"
    assert stored["parent_binding_status"] == "active"
    assert bindings[0]["parent_id"] == "parent-1"
    assert bindings[0]["student_id"] == stored["user_id"]
    assert bindings[0]["source"] == "student_registration"


def test_register_keeps_one_sided_parent_email_pending(monkeypatch):
    fake = FakeCognito()
    stored = {}
    bindings = []

    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: {
            "user_id": "parent-1",
            "role": "parent",
            "email": email,
            "child_email": "someone-else@example.com",
        }
        if email == "parent@example.com"
        else None,
    )
    monkeypatch.setattr(auth.user_repo, "put_user", lambda profile: stored.update(profile))
    monkeypatch.setattr(
        auth.user_repo,
        "put_parent_student_binding",
        lambda **kwargs: bindings.append(kwargs) or kwargs,
    )

    response = _auth_client().post(
        "/auth/register",
        json={
            "email": "student@example.com",
            "password": "ValidPass123!",
            "role": "student",
            "profile": {"parentEmail": "parent@example.com"},
        },
    )

    assert response.status_code == 201
    assert stored["parent_binding_status"] == "pending_parent_confirmation"
    assert "parent_id" not in stored
    assert bindings == []


def test_forgot_password_is_enumeration_safe_for_unknown_email(monkeypatch):
    monkeypatch.setattr(auth.user_repo, "get_user_by_email", lambda email: None)

    def fail_cognito(settings):
        raise AssertionError("unknown account should not call Cognito")

    monkeypatch.setattr(auth, "_get_cognito", fail_cognito)

    response = _auth_client().post("/auth/forgot-password", json={"email": "missing@example.com"})

    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "delivery": None}


def test_forgot_password_uses_role_client_without_returning_tokens(monkeypatch):
    fake = FakeCognito()
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: {"user_id": "parent-1", "role": "parent", "email": email},
    )

    response = _auth_client().post("/auth/forgot-password", json={"email": "parent@example.com"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert "accessToken" not in body
    assert fake.calls[-1][0] == "forgot_password"
    assert fake.calls[-1][1]["ClientId"] == "parent-client"


def test_reset_password_confirms_code_without_returning_tokens(monkeypatch):
    fake = FakeCognito()
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: {"user_id": "student-1", "role": "student", "email": email},
    )

    response = _auth_client().post(
        "/auth/reset-password",
        json={
            "email": "student@example.com",
            "confirmationCode": "123456",
            "newPassword": "NewValidPass123!",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "confirmed", "delivery": None}
    assert fake.calls[-1][0] == "confirm_forgot_password"
    assert fake.calls[-1][1]["ClientId"] == "student-client"


def test_reset_password_normalizes_cognito_errors(monkeypatch):
    class FailingCognito(FakeCognito):
        def confirm_forgot_password(self, **kwargs):
            raise _client_error("CodeMismatchException")

    monkeypatch.setattr(auth, "_get_cognito", lambda settings: FailingCognito())
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: {"user_id": "student-1", "role": "student", "email": email},
    )

    response = _auth_client().post(
        "/auth/reset-password",
        json={
            "email": "student@example.com",
            "confirmationCode": "bad",
            "newPassword": "NewValidPass123!",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid password reset request"


def test_admin_can_inspect_and_repair_parent_binding(monkeypatch):
    bindings = []
    student_updates = []
    monkeypatch.setattr(
        admin.user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "role": "parent" if user_id == "parent-1" else "student"},
    )
    monkeypatch.setattr(admin.user_repo, "list_parent_student_bindings", lambda parent_id: bindings)
    monkeypatch.setattr(
        admin.user_repo,
        "update_student_parent_link",
        lambda student_id, parent_id, relationship: student_updates.append((student_id, parent_id, relationship)),
    )

    def put_binding(**kwargs):
        bindings.append(
            {
                "parent_id": kwargs["parent_id"],
                "student_id": kwargs["student_id"],
                "relationship": kwargs["relationship"],
                "status": kwargs["status"],
                "source": kwargs["source"],
                "updated_at": kwargs["created_at"],
            }
        )
        return bindings[-1]

    monkeypatch.setattr(admin.user_repo, "put_parent_student_binding", put_binding)

    repair = _admin_client().post(
        "/admin/parent-bindings/repair",
        json={
            "parent_id": "parent-1",
            "student_id": "student-1",
            "relationship": "child",
            "reason": "repair signup link",
        },
    )

    assert repair.status_code == 200
    assert repair.json()["source"] == "admin_repair"
    assert student_updates == [("student-1", "parent-1", "child")]

    listed = _admin_client().get("/admin/parent-bindings", params={"parent_id": "parent-1"})
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
