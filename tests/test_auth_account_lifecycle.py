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
    monkeypatch.setattr(
        auth.public_identity_service, "resolve_account_access_token", resolve_token
    )


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


def test_admin_can_inspect_and_repair_parent_binding(monkeypatch):
    profiles = {
        "parent-1": {
            "PK": "USER#parent-1",
            "SK": "PROFILE",
            "user_id": "parent-1",
            "role": "parent",
            "account_status": "active",
            "version": 2,
        },
        "student-1": {
            "PK": "USER#student-1",
            "SK": "PROFILE",
            "user_id": "student-1",
            "role": "student",
            "account_status": "active",
            "version": 5,
            "parent_id": "parent-1",
            "relationship": "child",
            "parent_binding_status": "active",
        },
    }
    forward = {
        "PK": "USER#parent-1",
        "SK": "CHILD#student-1",
        "entity_type": "parent_student_binding",
        "parent_id": "parent-1",
        "student_id": "student-1",
        "relationship": "child",
        "status": "active",
        "source": "legacy",
        "actor": "system",
        "version": 4,
        "created_at": "2026-07-01T00:00:00+00:00",
        "updated_at": "2026-07-01T00:00:00+00:00",
    }
    reverse = None
    writes = []
    monkeypatch.setattr(
        admin.user_repo,
        "get_user",
        lambda user_id: profiles.get(user_id),
    )
    monkeypatch.setattr(
        admin.user_repo,
        "get_parent_student_binding",
        lambda parent_id, student_id: forward,
    )
    monkeypatch.setattr(
        admin.user_repo,
        "get_student_parent_binding",
        lambda student_id, parent_id: reverse,
    )
    monkeypatch.setattr(
        admin.user_repo,
        "list_student_parent_bindings",
        lambda student_id: [reverse] if reverse is not None else [],
    )
    monkeypatch.setattr(
        admin.user_repo,
        "list_parent_student_bindings",
        lambda parent_id: [forward],
    )

    def put_binding(**kwargs):
        nonlocal reverse
        writes.append(dict(kwargs))
        forward.update(
            source=kwargs["source"],
            actor=kwargs["actor"],
            updated_at=kwargs["created_at"],
        )
        reverse = {
            **forward,
            "PK": "USER#student-1",
            "SK": "PARENT#parent-1",
        }
        return admin.user_repo.ParentBindingResult(
            admin.user_repo.ParentBindingDisposition.CREATED,
            binding=forward,
            profile=profiles["student-1"],
        )

    monkeypatch.setattr(
        admin.user_repo, "put_parent_student_relationship", put_binding
    )
    client = _admin_client()
    payload = {
        "parent_id": "parent-1",
        "student_id": "student-1",
        "relationship": "child",
        "reason": "repair signup link",
    }

    missing_evidence = client.post("/admin/parent-bindings/repair", json=payload)
    assert missing_evidence.status_code == 422
    assert writes == []
    assert reverse is None

    preview = client.post("/admin/parent-bindings/repair/preview", json=payload)
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["classification"] == "repairable_missing_reverse"
    assert len(preview_body["pair_id"]) == len(preview_body["preview_id"]) == 64
    assert {item["coordinate"] for item in preview_body["observations"]} >= {
        "parent_profile",
        "student_profile",
        "forward",
        "reverse_target",
    }
    observed_versions = {
        item["coordinate"]: item["version"] for item in preview_body["observations"]
    }
    assert observed_versions == {
        "parent_profile": 2,
        "student_profile": 5,
        "forward": 4,
        "reverse_target": None,
    }
    assert "parent-1" not in preview_body["pair_id"]
    assert "student-1" not in preview_body["preview_id"]
    assert writes == []
    assert reverse is None

    repair = client.post(
        "/admin/parent-bindings/repair",
        json={**payload, "preview_id": preview_body["preview_id"]},
    )

    assert repair.status_code == 200
    repair_body = repair.json()
    assert len(repair_body["preview_id"]) == 64
    assert repair_body["preview_id"] != preview_body["preview_id"]
    assert repair_body == {
        "disposition": "repaired",
        "pair_id": preview_body["pair_id"],
        "preview_id": repair_body["preview_id"],
        "classification": "consistent",
        "mutated": True,
    }
    assert len(writes) == 1
    assert writes[0]["source"] == "admin_reconciliation"

    listed = client.get("/admin/parent-bindings", params={"parent_id": "parent-1"})
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["items"][0]["source"] == "admin_reconciliation"
