"""Authentication routes — aligned with frontend API contract."""
from datetime import UTC, datetime, timezone
import hashlib
from typing import Any

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field, field_validator

from stoa.config import Settings, get_settings
from stoa.db.dynamodb import get_table
from stoa.db.repositories import user_repo
from stoa.deps import (
    get_current_user,
    get_deletion_command,
    get_identity_repository,
    get_jwks_key_provider,
    security,
)
from stoa.jobs.account_deletion import continue_deletion_command
from stoa.models.user import PublicRegistrationRole, RegisterRequest
from stoa.services import (
    account_provisioning_service,
    account_verification_service,
    free_trial_service,
    locale_service,
    password_change_code_service,
    public_identity_service,
)
from stoa.security.identity import MUST_CHANGE_PASSWORD_FIELD
from stoa.security.tokens import verify_access_token
from stoa.security.route_inventory import explicit_route_classification
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.public_auth_errors import (
    PublicAuthOperation,
    normalize_cognito_failure,
    public_auth_error_response,
)
from stoa.security.request_correlation import get_request_correlation_id
from stoa.services.account_deletion_service import DeletionReceipt
from stoa.services.teacher_identity_provider import CognitoTeacherIdentityProvider

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models (aligned with frontend types/user.ts)
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    model_config = {"extra": "forbid"}


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: str
    preferredLanguage: str | None = None
    preferredLocale: str
    effectiveLocale: str
    subscriptionStatus: str = "trial"
    plan: str = "free_trial"
    emailVerificationStatus: str | None = None
    emailVerificationRequired: bool = False
    accountActivationStatus: str | None = None
    # True after an administrator reset: the sign-in succeeds and every route but
    # the password change is refused until the account picks its own password.
    mustChangePassword: bool = False


class AuthResponse(BaseModel):
    accessToken: str
    user: UserOut
    onboardingStatus: str | None = None
    verificationStatus: str | None = None
    emailVerificationStatus: str | None = None
    emailVerificationRequired: bool = False
    accountActivationStatus: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str

    model_config = {"extra": "forbid"}


class LogoutRequest(BaseModel):
    access_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    model_config = {"extra": "forbid"}


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    confirmationCode: str = Field(..., min_length=1, max_length=100)
    newPassword: str = Field(..., min_length=1, max_length=256)

    model_config = {"extra": "forbid"}


class EmailVerificationRequest(BaseModel):
    email: EmailStr

    model_config = {"extra": "forbid"}


class EmailVerificationConfirmRequest(EmailVerificationRequest):
    confirmationCode: str = Field(..., min_length=1, max_length=100)


class EmailVerificationResponse(BaseModel):
    status: str
    emailVerificationStatus: str
    emailVerificationRequired: bool
    accountActivationStatus: str
    resendAllowed: bool = False
    delivery: dict | None = None


class LoginCodeRequest(BaseModel):
    email: EmailStr

    model_config = {"extra": "forbid"}


class LoginCodeConfirmRequest(LoginCodeRequest):
    code: str = Field(..., min_length=1, max_length=100)


class LoginCodePolicyResponse(BaseModel):
    status: str = "deferred"
    policy: str = account_verification_service.LOGIN_CODE_POLICY
    reason: str


class PasswordResetResponse(BaseModel):
    status: str


class PasswordChangeRequest(BaseModel):
    currentPassword: str = Field(..., min_length=1, max_length=256)

    model_config = {"extra": "forbid"}


def enforce_password_complexity(value: str) -> str:
    """The one definition of what this service accepts as a password.

    Every entry point that takes a password of the user's own choosing calls this, so
    the rule cannot drift between them and none of them can be left relying on the
    identity pool to do the rejecting after a single-use credential has been spent.
    """
    if (
        len(value) < 8
        or not any(character.islower() for character in value)
        or not any(character.isupper() for character in value)
        or not any(character.isdigit() for character in value)
    ):
        raise ValueError(
            "Password must be at least 8 characters and contain an uppercase "
            "letter, a lowercase letter and a digit."
        )
    return value


class PasswordChangeConfirmRequest(PasswordChangeRequest):
    code: str = Field(..., min_length=1, max_length=16)
    newPassword: str = Field(..., min_length=1, max_length=256)

    @field_validator("newPassword")
    @classmethod
    def enforce_password_policy(cls, value: str) -> str:
        """Reject a non-compliant new password before the code is spent."""
        return enforce_password_complexity(value)


class PasswordChangeRequestResponse(BaseModel):
    status: str = "sent"
    maskedRecipient: str
    expiresAt: int


class PasswordChangeConfirmResponse(BaseModel):
    status: str = "changed"


class LocalePreferenceUpdate(BaseModel):
    preferredLocale: str = Field(..., min_length=1, max_length=32)


class LocalePreferenceResponse(BaseModel):
    preferredLocale: str
    effectiveLocale: str
    supportedLocales: list[str]
    updatedAt: str | None = None


class AccountDeletionReceiptResponse(BaseModel):
    commandId: str
    status: str
    acceptedAt: str
    completedAt: str | None = None


# ---------------------------------------------------------------------------
# Public authentication helpers
# ---------------------------------------------------------------------------

# STOA is invite/assignment only. Both switches must stay in step with
# `stoa-infra/stacks/auth_stack.py`: the user pool is `AllowAdminCreateUserOnly`
# and its account recovery is `NONE`.
PUBLIC_SELF_REGISTRATION_ENABLED = False
SELF_SERVICE_PASSWORD_RECOVERY_ENABLED = False

_PUBLIC_REGISTRATION_COMMAND = "public_self_service"
_PUBLIC_GROUPS = {
    PublicRegistrationRole.STUDENT.value: "students",
    PublicRegistrationRole.PARENT.value: "parents",
}


def _public_client_id(settings: Settings) -> str:
    """Use one non-privileged app client for every public auth operation."""

    cid = settings.cognito_student_client_id
    if not cid:
        raise HTTPException(status_code=503, detail="Public authentication is unavailable")
    return cid


def _get_cognito(settings: Settings):
    return boto3.client("cognito-idp", region_name=settings.aws_region)


def _build_user_out(profile: dict) -> UserOut:
    role = profile.get("role", "student")
    effective_locale = locale_service.effective_locale(profile)
    verification = account_verification_service.public_state(profile)
    return UserOut(
        id=profile.get("user_id", ""),
        name=profile.get("name") or profile.get("email", "").split("@")[0],
        email=profile.get("email", ""),
        role=role,
        preferredLanguage=effective_locale,
        preferredLocale=effective_locale,
        effectiveLocale=effective_locale,
        subscriptionStatus="trial",
        plan="free_trial",
        emailVerificationStatus=verification["emailVerificationStatus"],
        emailVerificationRequired=verification["emailVerificationRequired"],
        accountActivationStatus=verification["accountActivationStatus"],
        mustChangePassword=bool(profile.get(MUST_CHANGE_PASSWORD_FIELD)),
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _approved_public_registration_role(profile: dict) -> str:
    role = profile.get("registration_role")
    if (
        profile.get("registration_command") != _PUBLIC_REGISTRATION_COMMAND
        or role not in _PUBLIC_GROUPS
        or profile.get("role") != role
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "identity_conflict",
                "message": "This account cannot use public account activation.",
            },
        )
    return role


def _email_verification_status(profile: dict) -> str:
    return account_verification_service.verification_status(profile)


def _is_already_confirmed_provider_error(code: str, message: str) -> bool:
    return code in {"InvalidParameterException", "NotAuthorizedException"} and "CONFIRMED" in message.upper()


def _decommissioned(code: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": code,
            "message": "This is no longer available. Ask your STOA administrator.",
        },
    )


def _public_identity_conflict() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "identity_conflict",
            "message": "Your account needs recovery before you can continue.",
        },
    )


def _public_identity_dependency_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "identity_provider_unavailable",
            "message": "Sign-in is temporarily unavailable. Try again later.",
        },
    )


def _auth_response_for_profile(
    *,
    access_token: str,
    profile: dict,
    onboarding_status: str | None = None,
    verification_status: str | None = None,
) -> AuthResponse:
    verification = account_verification_service.public_state(profile)
    return AuthResponse(
        accessToken=access_token,
        user=_build_user_out(profile),
        onboardingStatus=onboarding_status,
        verificationStatus=verification_status,
        emailVerificationStatus=verification["emailVerificationStatus"],
        emailVerificationRequired=verification["emailVerificationRequired"],
        accountActivationStatus=verification["accountActivationStatus"],
    )


def _norm_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def _profile_from_current_user(current_user: dict) -> dict | None:
    """Load only the authoritative business identity projected by get_current_user."""

    user_id = current_user.get("user_id") or current_user.get("sub", "")
    return user_repo.get_user(user_id) if user_id else None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@explicit_route_classification(
    "public",
    "decommissioned public registration command surface",
    allowed_identifiers=("parent_id",),
    identifier_scope="command-local",
)
async def register(body: RegisterRequest):
    """Refuse public account creation; accounts are issued by an administrator.

    The user pool itself is `AllowAdminCreateUserOnly`, so a SignUp would be
    refused by the provider as well. This gate answers first so the refusal does
    not depend on reaching Cognito.
    """
    if PUBLIC_SELF_REGISTRATION_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "code": "public_registration_not_implemented",
                "message": "Public self-registration is switched on but this build cannot serve it.",
            },
        )
    raise _decommissioned("public_registration_closed")


@router.post("/login", response_model=AuthResponse)
@explicit_route_classification("public", "credential authentication entry point")
async def login(
    body: LoginRequest,
    settings: Settings = Depends(get_settings),
    key_provider=Depends(get_jwks_key_provider),
    identity_repository=Depends(get_identity_repository),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Authenticate through the single public client without caller-selected privilege."""
    cognito = _get_cognito(settings)
    client_id = _public_client_id(settings)

    try:
        resp = cognito.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": body.email, "PASSWORD": body.password},
            ClientId=client_id,
        )
    except ClientError as e:
        return public_auth_error_response(
            normalize_cognito_failure(PublicAuthOperation.LOGIN, e, correlation_id)
        )

    access_token = resp["AuthenticationResult"]["AccessToken"]

    try:
        _, profile = await public_identity_service.resolve_account_access_token(
            access_token,
            allowed_issuers=settings.allowed_cognito_issuers,
            allowed_client_ids=settings.allowed_cognito_access_clients,
            key_provider=key_provider,
            identity_repository=identity_repository,
        )
    except SecurityDecisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_body()) from exc

    return _auth_response_for_profile(
        access_token=access_token,
        profile=profile,
        onboarding_status="completed",
    )


@router.post("/email-verification/resend", response_model=EmailVerificationResponse)
@explicit_route_classification("public", "bounded verification recovery")
async def resend_email_verification(
    body: EmailVerificationRequest,
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Resend Cognito's sign-up confirmation code without exposing provider internals."""
    try:
        command = public_identity_service.require_public_identity_command(body.email)
    except public_identity_service.PublicIdentityCommandConflict:
        return EmailVerificationResponse(
            status="accepted",
            emailVerificationStatus=account_verification_service.STATUS_PENDING,
            emailVerificationRequired=True,
            accountActivationStatus=account_verification_service.PENDING_EMAIL,
            resendAllowed=False,
        )
    except Exception as exc:
        raise _public_identity_dependency_error() from exc
    try:
        if command.activation_complete:
            profile = public_identity_service.get_completed_public_profile(command)
        else:
            profile = public_identity_service.get_public_profile_for_command(command)
    except public_identity_service.PublicIdentityCommandConflict as exc:
        raise _public_identity_conflict() from exc
    except Exception as exc:
        raise _public_identity_dependency_error() from exc
    public_state = account_verification_service.public_state(profile)
    if command.activation_complete:
        return EmailVerificationResponse(
            status="already_verified",
            emailVerificationStatus=public_state["emailVerificationStatus"],
            emailVerificationRequired=public_state["emailVerificationRequired"],
            accountActivationStatus=public_state["accountActivationStatus"],
            resendAllowed=False,
        )
    if not account_verification_service.resend_allowed(profile):
        return EmailVerificationResponse(
            status="already_requested",
            emailVerificationStatus=public_state["emailVerificationStatus"],
            emailVerificationRequired=public_state["emailVerificationRequired"],
            accountActivationStatus=public_state["accountActivationStatus"],
            resendAllowed=False,
        )

    _approved_public_registration_role(profile)
    cognito = _get_cognito(settings)
    client_id = _public_client_id(settings)
    try:
        resp = cognito.resend_confirmation_code(ClientId=client_id, Username=body.email)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        message = str(e.response["Error"].get("Message") or "")
        if _is_already_confirmed_provider_error(code, message):
            try:
                provider = public_identity_service.provider_identity(
                    cognito,
                    user_pool_id=settings.cognito_user_pool_id,
                    email=body.email,
                )
                issuer = public_identity_service.canonical_public_issuer(
                    settings.allowed_cognito_issuers
                )
                reconciled_command, profile = (
                    public_identity_service.confirm_and_reconcile_public_identity(
                        email=body.email,
                        issuer=issuer,
                        provider_subject=provider["subject"],
                        provider_status=provider["status"],
                        provider_email=provider["email"],
                        provider_email_verified=provider["email_verified"],
                        provider_enabled=provider["enabled"],
                        provider=cognito,
                        user_pool_id=settings.cognito_user_pool_id,
                    )
                )
            except public_identity_service.PublicIdentityCommandConflict as exc:
                raise _public_identity_conflict() from exc
            except Exception as exc:
                raise _public_identity_dependency_error() from exc
            if not reconciled_command.activation_complete:
                raise _public_identity_conflict()
            state = account_verification_service.public_state(profile)
            return EmailVerificationResponse(
                status="already_verified",
                emailVerificationStatus=state["emailVerificationStatus"],
                emailVerificationRequired=state["emailVerificationRequired"],
                accountActivationStatus=state["accountActivationStatus"],
                resendAllowed=False,
            )
        if code in ("LimitExceededException", "TooManyRequestsException"):
            updated = user_repo.update_email_verification_state(
                profile["user_id"],
                account_verification_service.resend_limited_fields(_utc_now_iso()),
            )
            state = account_verification_service.public_state(updated or profile)
            return public_auth_error_response(
                normalize_cognito_failure(
                    PublicAuthOperation.VERIFICATION_RESEND, e, correlation_id
                )
            )
        if code in ("InvalidParameterException", "NotAuthorizedException", "UserNotFoundException"):
            return EmailVerificationResponse(
                status="accepted",
                emailVerificationStatus=public_state["emailVerificationStatus"],
                emailVerificationRequired=public_state["emailVerificationRequired"],
                accountActivationStatus=public_state["accountActivationStatus"],
                resendAllowed=False,
            )
        return public_auth_error_response(
            normalize_cognito_failure(PublicAuthOperation.VERIFICATION_RESEND, e, correlation_id)
        )

    updated = user_repo.update_email_verification_state(
        command.user_id,
        account_verification_service.resend_record_fields(profile, _utc_now_iso()),
    )
    state = account_verification_service.public_state(updated or profile)
    return EmailVerificationResponse(
        status="sent",
        emailVerificationStatus=state["emailVerificationStatus"],
        emailVerificationRequired=state["emailVerificationRequired"],
        accountActivationStatus=state["accountActivationStatus"],
        resendAllowed=state["resendAllowed"],
        delivery=resp.get("CodeDeliveryDetails"),
    )


@router.post("/email-verification/confirm", response_model=EmailVerificationResponse)
@explicit_route_classification("public", "verification confirmation command")
async def confirm_email_verification(
    body: EmailVerificationConfirmRequest,
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Confirm Cognito's sign-up code and activate the local account profile."""
    try:
        command = public_identity_service.require_public_identity_command(body.email)
    except public_identity_service.PublicIdentityCommandConflict as exc:
        raise _public_identity_conflict() from exc
    except Exception as exc:
        raise _public_identity_dependency_error() from exc
    if command.activation_complete:
        try:
            profile = public_identity_service.get_completed_public_profile(command)
            if profile.get("role") == PublicRegistrationRole.STUDENT.value:
                free_trial_service.activate_student_free_trial(
                    command.user_id,
                    student_profile=profile,
                )
        except public_identity_service.PublicIdentityCommandConflict as exc:
            raise _public_identity_conflict() from exc
        except Exception as exc:
            raise _public_identity_dependency_error() from exc
        state = account_verification_service.public_state(profile)
        return EmailVerificationResponse(
            status="already_verified",
            emailVerificationStatus=state["emailVerificationStatus"],
            emailVerificationRequired=state["emailVerificationRequired"],
            accountActivationStatus=state["accountActivationStatus"],
            resendAllowed=False,
        )
    cognito = _get_cognito(settings)
    client_id = _public_client_id(settings)
    already_confirmed = False
    try:
        cognito.confirm_sign_up(
            ClientId=client_id,
            Username=body.email,
            ConfirmationCode=body.confirmationCode,
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        message = str(e.response["Error"].get("Message") or "")
        if _is_already_confirmed_provider_error(code, message):
            already_confirmed = True
        elif code == "ExpiredCodeException":
            user_repo.update_email_verification_state(
                command.user_id,
                account_verification_service.expired_fields(_utc_now_iso()),
            )
            return public_auth_error_response(
                normalize_cognito_failure(
                    PublicAuthOperation.VERIFICATION_CONFIRM, e, correlation_id
                )
            )
        elif code in (
            "CodeMismatchException",
            "InvalidParameterException",
            "NotAuthorizedException",
            "UserNotFoundException",
        ):
            return public_auth_error_response(
                normalize_cognito_failure(
                    PublicAuthOperation.VERIFICATION_CONFIRM, e, correlation_id
                )
            )
        elif not already_confirmed:
            return public_auth_error_response(
                normalize_cognito_failure(
                    PublicAuthOperation.VERIFICATION_CONFIRM, e, correlation_id
                )
            )

    try:
        provider = public_identity_service.provider_identity(
            cognito,
            user_pool_id=settings.cognito_user_pool_id,
            email=body.email,
        )
        issuer = public_identity_service.canonical_public_issuer(settings.allowed_cognito_issuers)
        _, profile = public_identity_service.confirm_and_reconcile_public_identity(
            email=body.email,
            issuer=issuer,
            provider_subject=provider["subject"],
            provider_status=provider["status"],
            provider_email=provider["email"],
            provider_email_verified=provider["email_verified"],
            provider_enabled=provider["enabled"],
            provider=cognito,
            user_pool_id=settings.cognito_user_pool_id,
        )
        if profile.get("role") == PublicRegistrationRole.STUDENT.value:
            free_trial_service.activate_student_free_trial(
                command.user_id,
                student_profile=profile,
            )
    except public_identity_service.PublicIdentityCommandConflict as exc:
        raise _public_identity_conflict() from exc
    except Exception as exc:
        raise _public_identity_dependency_error() from exc
    state = account_verification_service.public_state(profile)
    return EmailVerificationResponse(
        status="already_verified" if already_confirmed else "confirmed",
        emailVerificationStatus=state["emailVerificationStatus"],
        emailVerificationRequired=state["emailVerificationRequired"],
        accountActivationStatus=state["accountActivationStatus"],
        resendAllowed=False,
    )


@router.post("/login-code/request", response_model=LoginCodePolicyResponse)
@explicit_route_classification("public", "disabled login-code policy surface")
async def request_login_code(body: LoginCodeRequest):
    """Explicitly gate passwordless login until a Cognito-compatible flow exists."""
    return LoginCodePolicyResponse(
        reason="Passwordless login codes are deferred until Cognito custom auth triggers are configured.",
    )


@router.post("/login-code/confirm", response_model=LoginCodePolicyResponse)
@explicit_route_classification("public", "disabled login-code policy surface")
async def confirm_login_code(body: LoginCodeConfirmRequest):
    """Explicitly reject placeholder login codes; no production token is minted here."""
    return LoginCodePolicyResponse(
        reason="Login code confirmation is deferred and cannot produce Cognito tokens in this backend.",
    )


@router.post("/forgot-password", response_model=PasswordResetResponse)
@explicit_route_classification("public", "decommissioned password recovery surface")
async def forgot_password(body: ForgotPasswordRequest):
    """Refuse password recovery; a forgotten password is reset by an administrator.

    Kept as a declared 410 rather than removed from the router so an old client
    is told the command is gone instead of reading a 404 as a deployment fault,
    and so the route stays in the authorization inventory.
    """
    if SELF_SERVICE_PASSWORD_RECOVERY_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "code": "password_recovery_not_implemented",
                "message": "Password recovery is switched on but this build cannot serve it.",
            },
        )
    raise _decommissioned("password_recovery_closed")


@router.post("/reset-password", response_model=PasswordResetResponse)
@explicit_route_classification("public", "decommissioned password recovery surface")
async def reset_password(body: ResetPasswordRequest):
    """Refuse recovery-code password resets; see `forgot_password`."""
    if SELF_SERVICE_PASSWORD_RECOVERY_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "code": "password_recovery_not_implemented",
                "message": "Password recovery is switched on but this build cannot serve it.",
            },
        )
    raise _decommissioned("password_recovery_closed")


@router.get("/me", response_model=UserOut)
@explicit_route_classification("authenticated-global", "Actor self account projection")
async def me(
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Return the authenticated user's profile."""
    profile = _profile_from_current_user(current_user)
    if not profile:
        profile = {
            "user_id": current_user.get("sub", ""),
            "email": current_user.get("email", ""),
            "name": "",
            "role": current_user.get("role") or "student",
        }
    return _build_user_out(profile)


@router.delete(
    "/me",
    response_model=AccountDeletionReceiptResponse,
    response_model_exclude_none=True,
    status_code=202,
)
@explicit_route_classification(
    "authenticated-global", "verified-subject account deletion command"
)
async def delete_me(
    background_tasks: BackgroundTasks,
    receipt: DeletionReceipt = Depends(get_deletion_command),
):
    """Fence first, return an opaque receipt, then continue outside the request."""
    if not receipt.is_terminal:
        background_tasks.add_task(continue_deletion_command, receipt.command_id)
    return AccountDeletionReceiptResponse(
        commandId=receipt.command_id,
        status=receipt.status,
        acceptedAt=receipt.accepted_at,
        completedAt=receipt.completed_at,
    )


@router.patch("/me/preferences/locale", response_model=LocalePreferenceResponse)
@explicit_route_classification("authenticated-global", "Actor self locale preference")
async def update_my_locale_preference(
    body: LocalePreferenceUpdate,
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Persist the authenticated user's preferred locale."""
    profile = _profile_from_current_user(current_user)
    if not profile or not profile.get("user_id"):
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        locale = locale_service.normalize_locale(body.preferredLocale)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    updated_at = _utc_now_iso()
    updated = user_repo.update_locale_preference(profile["user_id"], locale, updated_at)
    effective_locale = locale_service.effective_locale(updated or {**profile, "preferred_locale": locale})
    stored_updated_at = updated.get("locale_updated_at")
    return LocalePreferenceResponse(
        preferredLocale=locale,
        effectiveLocale=effective_locale,
        supportedLocales=sorted(locale_service.SUPPORTED_LOCALES),
        updatedAt=(
            stored_updated_at
            if isinstance(stored_updated_at, str) and stored_updated_at
            else updated_at
        ),
    )


def _password_change_provider_error(exc: ClientError) -> HTTPException:
    """Map provider failures onto fixed bodies that carry no provider detail."""
    code = exc.response.get("Error", {}).get("Code")
    if code in {"NotAuthorizedException", "UserNotFoundException", "UserNotConfirmedException"}:
        # 400, not 401: the session is valid, the password in the body is not.
        # A 401 here would read as an expired session and sign the caller out.
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "password_change_credentials_invalid",
                "message": "Check the current password and try again.",
            },
        )
    if code == "InvalidPasswordException":
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "password_requirements_not_met",
                "message": "Choose a password that meets the listed requirements.",
            },
        )
    if code in {"LimitExceededException", "TooManyRequestsException"}:
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "auth_request_rate_limited",
                "message": "Too many attempts. Wait a few minutes before trying again.",
            },
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "identity_provider_unavailable",
            "message": "Try again in a few minutes.",
        },
    )


def _password_change_verification_failed() -> HTTPException:
    """One body for every rejected code.

    A wrong code, an expired code, a spent code and a code that was never issued
    all answer with these exact bytes. Telling them apart would say whether a
    guess was close, which is the whole value of guessing.
    """
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "password_change_verification_failed",
            "message": "This code cannot be used. Request a new code and try again.",
        },
    )


def _clear_forced_password_change(current_user: dict, user_id: str) -> None:
    """Lower the administrator-reset flag, and only after the password really changed.

    This cannot share a transaction with the provider call, so it is ordered
    after it and made repeatable instead: the flag is only ever lowered on a
    password that has already been replaced, and a write that does not land
    answers 503 rather than reporting success. The account then signs in with
    its new password, is sent straight back to this same command, and the write
    is retried — it is never locked behind a flag it cannot lower.

    Whether the flag is up is read from the same authoritative resolution that
    admitted this very request, not from a second read that could disagree with
    it, so an account the gate is holding is always one this clears.
    """
    if not current_user.get("must_change_password"):
        return
    result = user_repo.update_profile_fields_versioned(
        user_id,
        update_expression="SET #must_change_password = :cleared, updated_at = :now",
        expression_attribute_names={"#must_change_password": MUST_CHANGE_PASSWORD_FIELD},
        expression_attribute_values={":cleared": False, ":now": _utc_now_iso()},
    )
    if result.disposition is not user_repo.ProfileWriteDisposition.UPDATED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "password_change_state_not_cleared",
                "message": "Your password was changed. Sign in again to finish.",
            },
        )


def _password_change_actor(current_user: dict) -> tuple[str, str]:
    profile = _profile_from_current_user(current_user) or {}
    user_id = str(profile.get("user_id") or "").strip()
    email = _norm_email(profile.get("email"))
    if not user_id or not email:
        raise HTTPException(status_code=404, detail="Profile not found")
    return user_id, email


@router.post("/password-change/request", response_model=PasswordChangeRequestResponse)
@explicit_route_classification("authenticated-global", "Actor self password change command")
async def request_password_change(
    body: PasswordChangeRequest,
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Prove the current password, then mail a single-use code to the account."""
    user_id, email = _password_change_actor(current_user)
    cognito = _get_cognito(settings)
    try:
        cognito.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": body.currentPassword},
            ClientId=_public_client_id(settings),
        )
    except ClientError as exc:
        raise _password_change_provider_error(exc) from exc

    # The screen the caller is looking at wins, as everywhere else; the stored
    # preference is only read when the request did not say.
    locale = locale_service.request_locale() or locale_service.effective_locale(
        _profile_from_current_user(current_user)
    )
    try:
        issued = password_change_code_service.issue(user_id, email, locale=locale)
    except password_change_code_service.PasswordChangeCodeRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "password_change_code_rate_limited",
                "message": "Too many codes requested. Try again later.",
            },
        ) from exc
    except password_change_code_service.PasswordChangeCodeDeliveryFailed as exc:
        # 503, not 500: nothing was spent and any live code still works, so the
        # honest answer is "the mail did not go out, try again".
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "password_change_code_delivery_failed",
                "message": "The code could not be sent. Try again in a few minutes.",
            },
        ) from exc
    return PasswordChangeRequestResponse(
        maskedRecipient=issued.masked_recipient,
        expiresAt=issued.expires_at,
    )


@router.post("/password-change/confirm", response_model=PasswordChangeConfirmResponse)
@explicit_route_classification("authenticated-global", "Actor self password change command")
async def confirm_password_change(
    body: PasswordChangeConfirmRequest,
    current_user: dict = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
):
    """Spend the code, then let the provider check the old password and set the new one."""
    user_id, _ = _password_change_actor(current_user)
    try:
        password_change_code_service.verify_and_consume(user_id, body.code)
    except password_change_code_service.PasswordChangeCodeRejected as exc:
        raise _password_change_verification_failed() from exc

    cognito = _get_cognito(settings)
    try:
        cognito.change_password(
            AccessToken=credentials.credentials,
            PreviousPassword=body.currentPassword,
            ProposedPassword=body.newPassword,
        )
    except ClientError as exc:
        raise _password_change_provider_error(exc) from exc
    _clear_forced_password_change(current_user, user_id)
    return PasswordChangeConfirmResponse()


@router.post("/refresh", response_model=AuthResponse)
@explicit_route_classification("public", "refresh-token authentication entry point")
async def refresh(
    body: RefreshRequest,
    settings: Settings = Depends(get_settings),
    key_provider=Depends(get_jwks_key_provider),
    identity_repository=Depends(get_identity_repository),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Exchange a refresh token for fresh tokens."""
    cognito = _get_cognito(settings)
    client_id = _public_client_id(settings)

    try:
        resp = cognito.initiate_auth(
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": body.refresh_token},
            ClientId=client_id,
        )
    except ClientError as e:
        return public_auth_error_response(
            normalize_cognito_failure(PublicAuthOperation.REFRESH, e, correlation_id)
        )

    result = resp["AuthenticationResult"]
    access_token = result["AccessToken"]
    try:
        _, profile = await public_identity_service.resolve_account_access_token(
            access_token,
            allowed_issuers=settings.allowed_cognito_issuers,
            allowed_client_ids=settings.allowed_cognito_access_clients,
            key_provider=key_provider,
            identity_repository=identity_repository,
        )
    except SecurityDecisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_body()) from exc
    return _auth_response_for_profile(
        access_token=access_token,
        profile=profile,
        onboarding_status="completed",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@explicit_route_classification("public", "token invalidation entry point")
async def logout(
    body: LogoutRequest,
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
    key_provider=Depends(get_jwks_key_provider),
    identity_repository=Depends(get_identity_repository),
):
    """Revoke the access token globally and locally.

    Cognito's global_sign_out kills the refresh token but leaves an already
    issued access token passing signature and expiry checks, so the backend
    records its own cut-off first. The local write happens before the provider
    call: if the provider fails the session is already dead here, whereas the
    reverse order would leave a live token behind whenever the write failed.

    A token that does not verify gets no cut-off because there is nothing to
    revoke - every protected route refuses it already - and the provider call
    still runs so its failure taxonomy is unchanged.
    """
    verified = None
    try:
        verified = await verify_access_token(
            body.access_token,
            allowed_issuers=settings.allowed_cognito_issuers,
            allowed_client_ids=settings.allowed_cognito_access_clients,
            key_provider=key_provider,
        )
    except SecurityDecisionError:
        verified = None

    if verified is not None:
        try:
            await identity_repository.record_session_revocation(
                verified.issuer,
                verified.subject,
                int(datetime.now(UTC).timestamp()) + 1,
            )
        except Exception as exc:
            error = SecurityDecisionError(
                SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
                internal_detail=type(exc).__name__,
            )
            raise HTTPException(
                status_code=error.status_code, detail=error.public_body()
            ) from exc

    cognito = _get_cognito(settings)
    try:
        cognito.global_sign_out(AccessToken=body.access_token)
    except ClientError as e:
        return public_auth_error_response(
            normalize_cognito_failure(PublicAuthOperation.LOGOUT, e, correlation_id)
        )


# ---------------------------------------------------------------------------
# Invitation activation (unauthenticated)
# ---------------------------------------------------------------------------

INVITATION_CLAIM_WINDOW_SECONDS = 900
INVITATION_CLAIM_MAX_ATTEMPTS = 10
INVITATION_CLAIM_THROTTLE_ENTITY = "invitation_claim_throttle"


class InvitationClaimRequest(BaseModel):
    model_config = {"extra": "forbid"}

    token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=8, max_length=256)
    # Card 008: supplied only when the invitation did not already carry one. The
    # calendar check lives in the service, which refuses by code rather than by
    # repeating the date back.
    dateOfBirth: str | None = Field(default=None, max_length=32)

    @field_validator("password")
    @classmethod
    def enforce_password_policy(cls, value: str) -> str:
        """Reject a weak password before the single-use token is anywhere near burned."""
        return enforce_password_complexity(value)


def get_account_identity_provider(settings: Settings = Depends(get_settings)) -> Any:
    return CognitoTeacherIdentityProvider(
        boto3.client("cognito-idp", region_name=settings.aws_region),
        user_pool_id=settings.cognito_user_pool_id,
    )


def _claim_source_digest(request: Request) -> str:
    """Bucket a caller by the address the gateway observed, never by a client header.

    `X-Forwarded-For` is caller-controlled at the edge, so keying on it would let one
    attacker mint a fresh quota per guess. Only the digest is stored.
    """
    source = request.client.host if request.client else ""
    return hashlib.sha256(str(source or "unknown").encode("utf-8")).hexdigest()


def _invitation_claim_rate_limited() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "auth_request_rate_limited",
            "message": "Too many attempts. Wait a few minutes before trying again.",
        },
        headers={"Retry-After": str(INVITATION_CLAIM_WINDOW_SECONDS)},
    )


def admit_invitation_claim(request: Request, *, now: datetime | None = None, table=None) -> None:
    """Charge one attempt per caller per window before the token is ever examined.

    Counting first is what makes the limit a brute-force gate: a wrong token, a spent
    token and a good token all cost the same. A counter that cannot be written refuses
    the attempt rather than admitting it.
    """
    moment = int((now or datetime.now(UTC)).timestamp())
    window_start = moment - (moment % INVITATION_CLAIM_WINDOW_SECONDS)
    digest = _claim_source_digest(request)
    client = table if table is not None else get_table()
    try:
        response = client.update_item(
            Key={
                "PK": f"INVITATION_CLAIM_THROTTLE#{digest}",
                "SK": f"WINDOW#{window_start}",
            },
            # DynamoDB's grammar puts SET before ADD; the reverse order is refused.
            UpdateExpression=(
                "SET entity_type = :entity, expires_at = :expires_at ADD attempts :one"
            ),
            ExpressionAttributeValues={
                ":one": 1,
                ":entity": INVITATION_CLAIM_THROTTLE_ENTITY,
                ":expires_at": window_start + 2 * INVITATION_CLAIM_WINDOW_SECONDS,
            },
            ReturnValues="UPDATED_NEW",
        )
    except Exception as exc:
        raise _invitation_claim_rate_limited() from exc
    attributes = response.get("Attributes") if isinstance(response, dict) else None
    attempts = int((attributes or {}).get("attempts") or 0)
    if attempts > INVITATION_CLAIM_MAX_ATTEMPTS:
        raise _invitation_claim_rate_limited()


@router.post("/invitations/claim")
@explicit_route_classification(
    "public", "invitation-gated account activation for every provisionable role"
)
def claim_invitation(
    body: InvitationClaimRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    provider: Any = Depends(get_account_identity_provider),
) -> dict[str, Any]:
    """Exchange one single-use token for an active account with a chosen password.

    Every rejection the service raises is returned unchanged. The service answers a
    token that never existed and one already burned with identical bytes; any wording
    added here would turn that into an oracle.
    """
    admit_invitation_claim(request)
    issuer = public_identity_service.canonical_public_issuer(settings.allowed_cognito_issuers)
    return account_provisioning_service.claim_invitation(
        token=body.token,
        password=body.password,
        date_of_birth=body.dateOfBirth,
        issuer=issuer,
        provider=provider,
    )
