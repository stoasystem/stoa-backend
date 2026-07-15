from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from types import SimpleNamespace

from stoa.config import Settings, get_settings
from stoa.routers import admin, auth
from actor_helpers import install_actor_overrides


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
    install_actor_overrides(app, {"sub": "admin-1", "role": "admin"})
    return TestClient(app)


def _client_error(code: str, message: str | None = None) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message or code}}, "Cognito")


def _public_profile(**values):
    profile = {
        "registration_command": "public_self_service",
        "registration_role": values.get("role", "student"),
    }
    profile.update(values)
    return profile


class FakeCognito:
    def __init__(self):
        self.calls = []

    def sign_up(self, **kwargs):
        self.calls.append(("sign_up", kwargs))
        return {"UserSub": "cognito-user-sub"}

    def admin_create_user(self, **kwargs):
        self.calls.append(("admin_create_user", kwargs))
        return {}

    def admin_set_user_password(self, **kwargs):
        self.calls.append(("admin_set_user_password", kwargs))
        return {}

    def admin_update_user_attributes(self, **kwargs):
        self.calls.append(("admin_update_user_attributes", kwargs))
        return {}

    def admin_add_user_to_group(self, **kwargs):
        self.calls.append(("admin_add_user_to_group", kwargs))
        return {}

    def admin_get_user(self, **kwargs):
        self.calls.append(("admin_get_user", kwargs))
        email = kwargs["Username"]
        return {
            "Username": "cognito-user-sub",
            "UserStatus": "CONFIRMED",
            "Enabled": True,
            "UserAttributes": [
                {"Name": "sub", "Value": "cognito-user-sub"},
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
        }

    def initiate_auth(self, **kwargs):
        self.calls.append(("initiate_auth", kwargs))
        return {"AuthenticationResult": {"AccessToken": "access-token"}}

    def forgot_password(self, **kwargs):
        self.calls.append(("forgot_password", kwargs))
        return {"CodeDeliveryDetails": {"Destination": "s***@example.com", "DeliveryMedium": "EMAIL"}}

    def confirm_forgot_password(self, **kwargs):
        self.calls.append(("confirm_forgot_password", kwargs))
        return {}

    def resend_confirmation_code(self, **kwargs):
        self.calls.append(("resend_confirmation_code", kwargs))
        return {"CodeDeliveryDetails": {"Destination": "s***@example.com", "DeliveryMedium": "EMAIL"}}

    def confirm_sign_up(self, **kwargs):
        self.calls.append(("confirm_sign_up", kwargs))
        return {}


@pytest.fixture(autouse=True)
def _legacy_public_identity_service_adapter(monkeypatch):
    """Keep legacy route edge-case tests isolated from DynamoDB; lifecycle tests cover the real service."""

    def command_for(email):
        profile = auth.user_repo.get_user_by_email(email)
        if not profile:
            raise auth.public_identity_service.PublicIdentityCommandConflict("missing")
        role = auth._approved_public_registration_role(profile)
        return SimpleNamespace(
            user_id=profile["user_id"],
            email=email,
            role=role,
            activation_complete=auth.account_verification_service.is_email_verified(profile),
        )

    def start(**kwargs):
        auth.user_repo.put_user(kwargs["profile"])
        return SimpleNamespace(), kwargs["profile"]

    def confirm(**kwargs):
        profile = auth.user_repo.get_user_by_email(kwargs["email"])
        role = auth._approved_public_registration_role(profile)
        del role
        if auth.account_verification_service.is_email_verified(profile):
            return SimpleNamespace(activation_complete=True), profile
        updated = auth.user_repo.update_email_verification_state(
            profile["user_id"],
            {
                **auth.account_verification_service.verified_fields(auth._utc_now_iso()),
                "account_status": "active",
            },
        )
        return SimpleNamespace(activation_complete=True), updated or profile

    async def resolve_token(*_args, **_kwargs):
        profile = auth.user_repo.get_user_by_email("student@example.com")
        if not profile or not auth.account_verification_service.can_return_tokens(profile):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "email_verification_required",
                    "message": "Email verification is required before login.",
                },
            )
        return SimpleNamespace(user_id=profile["user_id"]), profile

    monkeypatch.setattr(
        auth.public_identity_service, "require_public_identity_command", command_for
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "get_completed_public_profile",
        lambda command: auth.user_repo.get_user_by_email(command.email),
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "get_public_profile_for_command",
        lambda command: auth.user_repo.get_user_by_email(command.email),
    )
    monkeypatch.setattr(
        auth.public_identity_service, "start_or_resume_public_registration", start
    )
    monkeypatch.setattr(
        auth.public_identity_service, "resume_public_registration", start
    )
    monkeypatch.setattr(
        auth.public_identity_service, "confirm_and_reconcile_public_identity", confirm
    )
    monkeypatch.setattr(
        auth.public_identity_service, "resolve_public_access_token", resolve_token
    )


def test_register_username_exists_without_command_returns_safe_action_before_lookup(monkeypatch):
    class ExistingCognito(FakeCognito):
        def sign_up(self, **kwargs):
            self.calls.append(("sign_up", kwargs))
            raise _client_error("UsernameExistsException", "provider-state-canary")

    fake = ExistingCognito()
    mutations = []
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.public_identity_service,
        "require_public_identity_command",
        lambda _email: (_ for _ in ()).throw(
            auth.public_identity_service.PublicIdentityCommandConflict("missing")
        ),
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "start_or_resume_public_registration",
        lambda **kwargs: mutations.append(("start", kwargs)),
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "resume_public_registration",
        lambda **kwargs: mutations.append(("resume", kwargs)),
    )

    response = _auth_client().post(
        "/auth/register",
        json={
            "email": "existing@example.com",
            "password": "ValidPass123!",
            "role": "student",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "email_already_registered"
    assert "provider-state-canary" not in response.text
    assert [name for name, _ in fake.calls] == ["sign_up"]
    assert mutations == []


def test_register_username_exists_resumes_only_exact_command(monkeypatch):
    class ExistingCognito(FakeCognito):
        def sign_up(self, **kwargs):
            self.calls.append(("sign_up", kwargs))
            raise _client_error("UsernameExistsException")

    fake = ExistingCognito()
    resumed = []
    command = SimpleNamespace(
        issuer="https://cognito-idp.eu-central-2.amazonaws.com/pool-id",
        subject="cognito-user-sub",
        user_id="cognito-user-sub",
        role="student",
    )
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.public_identity_service,
        "require_public_identity_command",
        lambda _email: command,
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "resume_public_registration",
        lambda **kwargs: resumed.append(kwargs) or (command, kwargs["profile"]),
    )

    response = _auth_client().post(
        "/auth/register",
        json={
            "email": "student@example.com",
            "password": "ValidPass123!",
            "role": "student",
        },
    )

    assert response.status_code == 201
    assert [name for name, _ in fake.calls] == ["sign_up", "admin_get_user"]
    assert resumed[0]["command"] is command
    assert resumed[0]["subject"] == "cognito-user-sub"
    assert resumed[0]["role"] == "student"


@pytest.mark.parametrize(
    ("case", "command_role", "provider_subject"),
    [
        ("provider_only_public", None, "cognito-user-sub"),
        ("provider_only_privileged", None, "privileged-provider-sub"),
        ("altered_role", "parent", "cognito-user-sub"),
        ("altered_subject", "student", "different-provider-sub"),
    ],
)
def test_existing_account_adoption_matrix_is_indistinguishable_and_mutation_free(
    monkeypatch, case, command_role, provider_subject
):
    class ExistingCognito(FakeCognito):
        def sign_up(self, **kwargs):
            self.calls.append(("sign_up", kwargs))
            raise _client_error("UsernameExistsException", f"{case}-provider-canary")

        def admin_get_user(self, **kwargs):
            self.calls.append(("admin_get_user", kwargs))
            return {
                "Username": provider_subject,
                "UserStatus": "CONFIRMED",
                "Enabled": True,
                "UserAttributes": [
                    {"Name": "sub", "Value": provider_subject},
                    {"Name": "email", "Value": kwargs["Username"]},
                    {"Name": "email_verified", "Value": "true"},
                ],
            }

    fake = ExistingCognito()
    mutations = []
    command = (
        SimpleNamespace(
            issuer="https://cognito-idp.eu-central-2.amazonaws.com/pool-id",
            subject="cognito-user-sub",
            user_id="cognito-user-sub",
            role=command_role,
        )
        if command_role
        else None
    )
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.public_identity_service,
        "require_public_identity_command",
        lambda _email: command
        if command
        else (_ for _ in ()).throw(
            auth.public_identity_service.PublicIdentityCommandConflict("missing")
        ),
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "start_or_resume_public_registration",
        lambda **kwargs: mutations.append(("start", kwargs)),
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "resume_public_registration",
        lambda **kwargs: mutations.append(("resume", kwargs)),
    )
    monkeypatch.setattr(
        auth,
        "_bind_parent_student_if_possible",
        lambda *args: mutations.append(("relationship", args)),
    )

    response = _auth_client().post(
        "/auth/register",
        json={
            "email": "shared@example.com",
            "password": "ValidPass123!",
            "role": "student",
        },
    )

    assert response.status_code == 409
    assert set(response.json()) == {"code", "message", "correlationId"}
    assert response.json()["code"] == "email_already_registered"
    assert response.json()["message"] == (
        "This email already has an account. Sign in instead, or reset your password."
    )
    assert "provider-canary" not in response.text
    assert mutations == []
    assert [name for name, _ in fake.calls] in (
        ["sign_up"],
        ["sign_up", "admin_get_user"],
    )
    assert all(
        name not in {"admin_update_user_attributes", "admin_add_user_to_group"}
        for name, _ in fake.calls
    )


@pytest.mark.parametrize("role", ["student", "parent"])
def test_matching_interrupted_public_command_resumes_exact_role(monkeypatch, role):
    class ExistingCognito(FakeCognito):
        def sign_up(self, **kwargs):
            self.calls.append(("sign_up", kwargs))
            raise _client_error("UsernameExistsException")

    fake = ExistingCognito()
    subject = "cognito-user-sub"
    command = SimpleNamespace(
        issuer="https://cognito-idp.eu-central-2.amazonaws.com/pool-id",
        subject=subject,
        user_id=subject,
        role=role,
    )
    resumed = []
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.public_identity_service,
        "require_public_identity_command",
        lambda _email: command,
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "resume_public_registration",
        lambda **kwargs: resumed.append(kwargs) or (command, kwargs["profile"]),
    )

    response = _auth_client().post(
        "/auth/register",
        json={
            "email": f"{role}@example.com",
            "password": "ValidPass123!",
            "role": role,
        },
    )

    assert response.status_code == 201
    assert response.json()["user"]["role"] == role
    assert resumed[0]["command"] is command
    assert resumed[0]["role"] == role
    assert resumed[0]["subject"] == subject


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
    assert body["accessToken"] == ""
    assert body["emailVerificationStatus"] == "pending_verification"
    assert body["emailVerificationRequired"] is True
    assert body["accountActivationStatus"] == "pending_email_verification"
    assert body["user"]["emailVerificationStatus"] == "pending_verification"
    assert fake.calls[0][0] == "sign_up"
    assert fake.calls[0][1]["ClientId"] == "student-client"
    assert fake.calls[0][1]["UserAttributes"] == [{"Name": "email", "Value": "student@example.com"}]
    assert fake.calls[1][0] == "admin_update_user_attributes"
    assert stored["user_id"] == "cognito-user-sub"
    assert stored["email_verification_policy"] == "cognito_sign_up_confirm_sign_up"
    assert stored["email_verification_required"] is True
    assert stored["parent_id"] == "parent-1"
    assert stored["parent_binding_status"] == "active_pending_verification"
    assert bindings[0]["parent_id"] == "parent-1"
    assert bindings[0]["student_id"] == stored["user_id"]
    assert bindings[0]["status"] == "active_pending_verification"
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


def test_confirm_email_verification_activates_profile(monkeypatch):
    fake = FakeCognito()
    updates = []
    profile = _public_profile(**{
        "user_id": "student-1",
        "role": "student",
        "email": "student@example.com",
        "email_verification_status": "pending_verification",
        "email_verification_required": True,
    })
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(auth.user_repo, "get_user_by_email", lambda email: profile)
    monkeypatch.setattr(
        auth.user_repo,
        "update_email_verification_state",
        lambda user_id, fields: updates.append((user_id, fields)) or {**profile, **fields},
    )

    response = _auth_client().post(
        "/auth/email-verification/confirm",
        json={"email": "student@example.com", "confirmationCode": "123456"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["emailVerificationStatus"] == "verified"
    assert body["emailVerificationRequired"] is False
    assert fake.calls[0][0] == "confirm_sign_up"
    assert updates[0][0] == "student-1"
    assert updates[0][1]["email_verification_status"] == "verified"


def test_login_blocks_unconfirmed_cognito_user(monkeypatch):
    class UnconfirmedCognito(FakeCognito):
        def initiate_auth(self, **kwargs):
            raise _client_error("UserNotConfirmedException")

    monkeypatch.setattr(auth, "_get_cognito", lambda settings: UnconfirmedCognito())
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: {
            "user_id": "student-1",
            "role": "student",
            "email": email,
            "email_verification_status": "pending_verification",
            "email_verification_required": True,
        },
    )

    response = _auth_client().post(
        "/auth/login",
        json={"email": "student@example.com", "password": "ValidPass123!"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "email_verification_required"
    assert set(response.json()) == {"code", "message", "correlationId"}


def test_login_does_not_repair_local_pending_state_after_cognito_auth_succeeds(monkeypatch):
    fake = FakeCognito()
    updates = []
    profile = _public_profile(**{
        "user_id": "student-1",
        "role": "student",
        "email": "student@example.com",
        "email_verification_status": "pending_verification",
        "email_verification_required": True,
    })
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(auth.user_repo, "get_user_by_email", lambda email: profile)
    monkeypatch.setattr(
        auth.user_repo,
        "update_email_verification_state",
        lambda user_id, fields: updates.append((user_id, fields)) or {**profile, **fields},
    )

    response = _auth_client().post(
        "/auth/login",
        json={"email": "student@example.com", "password": "ValidPass123!"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "email_verification_required"
    assert updates == []


def test_login_allows_verified_profile(monkeypatch):
    fake = FakeCognito()
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: _public_profile(**{
            "user_id": "student-1",
            "role": "student",
            "email": email,
            "email_verification_status": "verified",
            "email_verification_required": False,
        }),
    )

    response = _auth_client().post(
        "/auth/login",
        json={"email": "student@example.com", "password": "ValidPass123!"},
    )

    assert response.status_code == 200
    assert response.json()["accessToken"] == "access-token"
    assert response.json()["emailVerificationStatus"] == "verified"


def test_resend_email_verification_is_idempotent_during_cooldown(monkeypatch):
    fake = FakeCognito()
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: _public_profile(**{
            "user_id": "student-1",
            "role": "student",
            "email": email,
            "email_verification_status": "pending_verification",
            "email_verification_required": True,
            "email_verification_last_resend_at": auth._utc_now_iso(),
        }),
    )

    response = _auth_client().post(
        "/auth/email-verification/resend",
        json={"email": "student@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "already_requested"
    assert fake.calls == []


def test_resend_email_verification_records_provider_delivery(monkeypatch):
    fake = FakeCognito()
    updates = []
    profile = _public_profile(**{
        "user_id": "student-1",
        "role": "student",
        "email": "student@example.com",
        "email_verification_status": "pending_verification",
        "email_verification_required": True,
    })
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(auth.user_repo, "get_user_by_email", lambda email: profile)
    monkeypatch.setattr(
        auth.user_repo,
        "update_email_verification_state",
        lambda user_id, fields: updates.append((user_id, fields)) or {**profile, **fields},
    )

    response = _auth_client().post(
        "/auth/email-verification/resend",
        json={"email": "student@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert fake.calls[-1][0] == "resend_confirmation_code"
    assert updates[0][1]["email_verification_resend_count"] == 1


def test_resend_missing_command_is_bounded_and_mutation_free(monkeypatch):
    fake = FakeCognito()
    profile_reads = []
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.public_identity_service,
        "require_public_identity_command",
        lambda _email: (_ for _ in ()).throw(
            auth.public_identity_service.PublicIdentityCommandConflict("missing")
        ),
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "get_public_profile_for_command",
        lambda command: profile_reads.append(command),
    )

    response = _auth_client().post(
        "/auth/email-verification/resend",
        json={"email": "unknown@example.com"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "emailVerificationStatus": "pending_verification",
        "emailVerificationRequired": True,
        "accountActivationStatus": "pending_email_verification",
        "resendAllowed": False,
        "delivery": None,
    }
    assert profile_reads == []
    assert fake.calls == []


def test_resend_uses_command_user_and_never_email_index(monkeypatch):
    fake = FakeCognito()
    updates = []
    command = SimpleNamespace(
        user_id="command-user",
        email="shared@example.com",
        role="student",
        activation_complete=False,
    )
    profile = _public_profile(**{
        "user_id": "command-user",
        "role": "student",
        "email": "shared@example.com",
        "email_verification_status": "pending_verification",
        "email_verification_required": True,
    })
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.public_identity_service,
        "require_public_identity_command",
        lambda _email: command,
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "get_public_profile_for_command",
        lambda loaded: profile if loaded is command else None,
    )
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda _email: (_ for _ in ()).throw(AssertionError("email index used")),
    )
    monkeypatch.setattr(
        auth.user_repo,
        "update_email_verification_state",
        lambda user_id, fields: updates.append((user_id, fields)) or {**profile, **fields},
    )

    response = _auth_client().post(
        "/auth/email-verification/resend",
        json={"email": "shared@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert updates[0][0] == "command-user"
    assert [name for name, _ in fake.calls] == ["resend_confirmation_code"]


def test_resend_email_verification_repairs_local_state_when_cognito_already_confirmed(monkeypatch):
    class AlreadyConfirmedCognito(FakeCognito):
        def resend_confirmation_code(self, **kwargs):
            raise _client_error("NotAuthorizedException", "User is already confirmed.")

    updates = []
    profile = _public_profile(**{
        "user_id": "student-1",
        "role": "student",
        "email": "student@example.com",
        "email_verification_status": "pending_verification",
        "email_verification_required": True,
    })
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: AlreadyConfirmedCognito())
    monkeypatch.setattr(auth.user_repo, "get_user_by_email", lambda email: profile)
    monkeypatch.setattr(
        auth.user_repo,
        "update_email_verification_state",
        lambda user_id, fields: updates.append((user_id, fields)) or {**profile, **fields},
    )

    response = _auth_client().post(
        "/auth/email-verification/resend",
        json={"email": "student@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "already_verified"
    assert response.json()["emailVerificationStatus"] == "verified"
    assert response.json()["emailVerificationRequired"] is False
    assert updates[0][0] == "student-1"
    assert updates[0][1]["email_verification_status"] == "verified"


def test_already_confirmed_resend_reconciles_exact_command_subject(monkeypatch):
    class AlreadyConfirmedCognito(FakeCognito):
        def resend_confirmation_code(self, **kwargs):
            self.calls.append(("resend_confirmation_code", kwargs))
            raise _client_error("NotAuthorizedException", "User is already confirmed.")

    fake = AlreadyConfirmedCognito()
    command = SimpleNamespace(
        user_id="command-user",
        email="student@example.com",
        role="student",
        activation_complete=False,
    )
    completed = SimpleNamespace(
        user_id=command.user_id,
        email=command.email,
        role=command.role,
        activation_complete=True,
    )
    pending = _public_profile(**{
        "user_id": "command-user",
        "role": "student",
        "email": "student@example.com",
        "account_status": "pending_verification",
        "email_verification_status": "pending_verification",
        "email_verification_required": True,
    })
    active = {
        **pending,
        "account_status": "active",
        "email_verification_status": "verified",
        "email_verification_required": False,
    }
    reconciliations = []
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.public_identity_service,
        "require_public_identity_command",
        lambda _email: command,
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "get_public_profile_for_command",
        lambda loaded: pending if loaded is command else None,
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "confirm_and_reconcile_public_identity",
        lambda **kwargs: reconciliations.append(kwargs) or (completed, active),
    )
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda _email: (_ for _ in ()).throw(AssertionError("email index used")),
    )

    response = _auth_client().post(
        "/auth/email-verification/resend",
        json={"email": "student@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "already_verified"
    assert response.json()["accountActivationStatus"] == "active"
    assert reconciliations[0]["provider_subject"] == "cognito-user-sub"
    assert reconciliations[0]["email"] == "student@example.com"
    assert [name for name, _ in fake.calls] == [
        "resend_confirmation_code",
        "admin_get_user",
    ]


def test_resend_command_dependency_failure_does_not_touch_provider(monkeypatch):
    fake = FakeCognito()
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.public_identity_service,
        "require_public_identity_command",
        lambda _email: (_ for _ in ()).throw(TimeoutError("dependency-canary")),
    )

    response = _auth_client().post(
        "/auth/email-verification/resend",
        json={"email": "student@example.com"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "identity_provider_unavailable"
    assert "dependency-canary" not in response.text
    assert fake.calls == []


def test_confirm_email_verification_marks_expired_code(monkeypatch):
    class ExpiredCognito(FakeCognito):
        def confirm_sign_up(self, **kwargs):
            raise _client_error("ExpiredCodeException")

    updates = []
    profile = _public_profile(**{
        "user_id": "student-1",
        "role": "student",
        "email": "student@example.com",
        "email_verification_status": "pending_verification",
        "email_verification_required": True,
    })
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: ExpiredCognito())
    monkeypatch.setattr(auth.user_repo, "get_user_by_email", lambda email: profile)
    monkeypatch.setattr(
        auth.user_repo,
        "update_email_verification_state",
        lambda user_id, fields: updates.append((user_id, fields)) or {**profile, **fields},
    )

    response = _auth_client().post(
        "/auth/email-verification/confirm",
        json={"email": "student@example.com", "confirmationCode": "expired"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "verification_code_expired"
    assert response.json()["message"] == "Request a new verification code, then try again."
    assert updates[0][1]["email_verification_status"] == "expired_verification"


def test_confirm_email_verification_is_idempotent_for_locally_verified_profile(monkeypatch):
    fake = FakeCognito()
    profile = _public_profile(**{
        "user_id": "student-1",
        "role": "student",
        "email": "student@example.com",
        "email_verification_status": "verified",
        "email_verification_required": False,
    })
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(auth.user_repo, "get_user_by_email", lambda email: profile)

    response = _auth_client().post(
        "/auth/email-verification/confirm",
        json={"email": "student@example.com", "confirmationCode": "123456"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "already_verified"
    assert response.json()["emailVerificationStatus"] == "verified"
    assert fake.calls == []


def test_confirm_email_verification_repairs_local_state_when_cognito_already_confirmed(monkeypatch):
    class AlreadyConfirmedCognito(FakeCognito):
        def confirm_sign_up(self, **kwargs):
            raise _client_error("NotAuthorizedException", "User cannot be confirmed. Current status is CONFIRMED")

    updates = []
    profile = _public_profile(**{
        "user_id": "student-1",
        "role": "student",
        "email": "student@example.com",
        "email_verification_status": "pending_verification",
        "email_verification_required": True,
    })
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: AlreadyConfirmedCognito())
    monkeypatch.setattr(auth.user_repo, "get_user_by_email", lambda email: profile)
    monkeypatch.setattr(
        auth.user_repo,
        "update_email_verification_state",
        lambda user_id, fields: updates.append((user_id, fields)) or {**profile, **fields},
    )

    response = _auth_client().post(
        "/auth/email-verification/confirm",
        json={"email": "student@example.com", "confirmationCode": "123456"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "already_verified"
    assert response.json()["emailVerificationStatus"] == "verified"
    assert updates[0][1]["email_verification_status"] == "verified"


def test_confirm_email_verification_normalizes_wrong_code(monkeypatch):
    class WrongCodeCognito(FakeCognito):
        def confirm_sign_up(self, **kwargs):
            raise _client_error("CodeMismatchException")

    monkeypatch.setattr(auth, "_get_cognito", lambda settings: WrongCodeCognito())
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: _public_profile(**{
            "user_id": "student-1",
            "role": "student",
            "email": email,
            "email_verification_status": "pending_verification",
            "email_verification_required": True,
        }),
    )

    response = _auth_client().post(
        "/auth/email-verification/confirm",
        json={"email": "student@example.com", "confirmationCode": "bad"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "verification_code_invalid"


def test_confirm_email_verification_normalizes_rate_limit(monkeypatch):
    class LimitedCognito(FakeCognito):
        def confirm_sign_up(self, **kwargs):
            raise _client_error("TooManyRequestsException")

    monkeypatch.setattr(auth, "_get_cognito", lambda settings: LimitedCognito())
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: _public_profile(**{
            "user_id": "student-1",
            "role": "student",
            "email": email,
            "email_verification_status": "pending_verification",
            "email_verification_required": True,
        }),
    )

    response = _auth_client().post(
        "/auth/email-verification/confirm",
        json={"email": "student@example.com", "confirmationCode": "123456"},
    )

    assert response.status_code == 429
    assert response.json()["code"] == "auth_request_rate_limited"


def test_login_disabled_account_returns_support_safe_error(monkeypatch):
    class DisabledCognito(FakeCognito):
        def initiate_auth(self, **kwargs):
            raise _client_error("UserDisabledException")

    monkeypatch.setattr(auth, "_get_cognito", lambda settings: DisabledCognito())
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: _public_profile(**{
            "user_id": "student-1",
            "role": "student",
            "email": email,
            "email_verification_status": "verified",
            "email_verification_required": False,
        }),
    )

    response = _auth_client().post(
        "/auth/login",
        json={"email": "student@example.com", "password": "ValidPass123!"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "account_disabled"


def test_resend_disabled_account_returns_support_safe_error(monkeypatch):
    class DisabledCognito(FakeCognito):
        def resend_confirmation_code(self, **kwargs):
            raise _client_error("UserDisabledException")

    monkeypatch.setattr(auth, "_get_cognito", lambda settings: DisabledCognito())
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: _public_profile(**{
            "user_id": "student-1",
            "role": "student",
            "email": email,
            "email_verification_status": "pending_verification",
            "email_verification_required": True,
        }),
    )

    response = _auth_client().post(
        "/auth/email-verification/resend",
        json={"email": "student@example.com"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "account_disabled"


def test_login_code_policy_is_deferred_without_tokens():
    request = _auth_client().post(
        "/auth/login-code/request",
        json={"email": "student@example.com"},
    )
    confirm = _auth_client().post(
        "/auth/login-code/confirm",
        json={"email": "student@example.com", "code": "123456"},
    )

    assert request.status_code == 200
    assert request.json()["status"] == "deferred"
    assert request.json()["policy"] == "deferred_cognito_custom_auth_required"
    assert "custom auth triggers" in request.json()["reason"]
    assert "accessToken" not in request.json()
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "deferred"
    assert confirm.json()["policy"] == "deferred_cognito_custom_auth_required"
    assert "cannot produce Cognito tokens" in confirm.json()["reason"]
    assert "accessToken" not in confirm.json()


def test_admin_can_inspect_account_verification_status(monkeypatch):
    monkeypatch.setattr(
        admin.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "role": "student",
            "email": "student@example.com",
            "email_verification_status": "expired_verification",
            "email_verification_required": True,
            "email_verification_policy": "cognito_sign_up_confirm_sign_up",
            "email_verification_resend_count": 2,
            "parent_binding_status": "active_pending_verification",
        },
    )

    response = _admin_client().get("/admin/account-verification/student-1")

    assert response.status_code == 200
    body = response.json()
    assert body["userId"] == "student-1"
    assert body["emailVerificationStatus"] == "expired_verification"
    assert body["accountActivationStatus"] == "pending_email_verification"
    assert body["emailVerificationPolicy"] == "cognito_sign_up_confirm_sign_up"
    assert body["parentBindingStatus"] == "active_pending_verification"
    assert body["supportRecoveryState"] == "expired_code"
    assert body["supportAction"] == "resend_verification_code"


def test_forgot_password_is_enumeration_safe_for_unknown_email(monkeypatch):
    monkeypatch.setattr(auth.user_repo, "get_user_by_email", lambda email: None)

    def fail_cognito(settings):
        raise AssertionError("unknown account should not call Cognito")

    monkeypatch.setattr(auth, "_get_cognito", fail_cognito)

    response = _auth_client().post("/auth/forgot-password", json={"email": "missing@example.com"})

    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "delivery": None}


def test_forgot_password_uses_public_client_without_returning_tokens(monkeypatch):
    fake = FakeCognito()
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: {
            "user_id": "parent-1",
            "role": "parent",
            "email": email,
            "registration_command": "public_self_service",
            "registration_role": "parent",
        },
    )

    response = _auth_client().post("/auth/forgot-password", json={"email": "parent@example.com"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert "accessToken" not in body
    assert fake.calls[-1][0] == "forgot_password"
    assert fake.calls[-1][1]["ClientId"] == "student-client"


def test_reset_password_confirms_code_without_returning_tokens(monkeypatch):
    fake = FakeCognito()
    monkeypatch.setattr(auth, "_get_cognito", lambda settings: fake)
    monkeypatch.setattr(
        auth.user_repo,
        "get_user_by_email",
        lambda email: {
            "user_id": "student-1",
            "role": "student",
            "email": email,
            "registration_command": "public_self_service",
            "registration_role": "student",
        },
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
        lambda email: {
            "user_id": "student-1",
            "role": "student",
            "email": email,
            "registration_command": "public_self_service",
            "registration_role": "student",
        },
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
    assert response.json()["code"] == "password_reset_request_invalid"
    assert set(response.json()) == {"code", "message", "correlationId"}


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
