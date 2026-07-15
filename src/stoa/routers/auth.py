"""Authentication routes — aligned with frontend API contract."""
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from stoa.config import Settings, get_settings
from stoa.db.repositories import user_repo
from stoa.deps import get_current_user, get_identity_repository, get_jwks_key_provider
from stoa.models.user import PublicRegistrationRole, RegisterRequest
from stoa.services import account_verification_service, locale_service, public_identity_service
from stoa.security.route_inventory import explicit_route_classification
from stoa.security.errors import SecurityDecisionError
from stoa.security.public_auth_errors import (
    PublicAuthOperation,
    normalize_cognito_failure,
    public_auth_error_response,
)
from stoa.security.request_correlation import get_request_correlation_id

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


class LocalePreferenceUpdate(BaseModel):
    preferredLocale: str = Field(..., min_length=1, max_length=32)


class LocalePreferenceResponse(BaseModel):
    preferredLocale: str
    effectiveLocale: str
    supportedLocales: list[str]
    updatedAt: str | None = None


# ---------------------------------------------------------------------------
# Public authentication helpers
# ---------------------------------------------------------------------------

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


def _profile_child_email(profile: dict) -> str:
    return _norm_email(
        profile.get("child_email")
        or profile.get("childEmail")
        or profile.get("student_email")
        or profile.get("studentEmail")
    )


def _profile_from_current_user(current_user: dict) -> dict | None:
    """Load only the authoritative business identity projected by get_current_user."""

    user_id = current_user.get("user_id") or current_user.get("sub", "")
    return user_repo.get_user(user_id) if user_id else None


def _bind_parent_student_if_possible(parent_email: str | None, student_profile: dict) -> dict | None:
    if not parent_email:
        return None
    parent = user_repo.get_user_by_email(parent_email)
    if not parent or parent.get("role") != "parent":
        student_profile["parent_binding_status"] = "pending_parent_profile"
        student_profile["parent_email"] = parent_email
        return None
    if _profile_child_email(parent) != _norm_email(student_profile.get("email")):
        student_profile["parent_binding_status"] = "pending_parent_confirmation"
        student_profile["parent_email"] = parent_email
        return None
    parent_id = parent.get("user_id")
    student_id = student_profile.get("user_id")
    if not parent_id or not student_id:
        return None
    binding_status = account_verification_service.binding_status_for_profiles(
        student_profile,
        parent,
    )
    student_profile["parent_id"] = parent_id
    student_profile["parent_binding_status"] = binding_status
    return user_repo.put_parent_student_binding(
        parent_id=parent_id,
        student_id=student_id,
        relationship="child",
        status=binding_status,
        source="student_registration",
        actor="system",
        created_at=_utc_now_iso(),
    )


def _bind_existing_child_if_possible(parent_profile: dict, child_email: str | None) -> dict | None:
    if not child_email:
        return None
    child = user_repo.get_user_by_email(child_email)
    if not child or child.get("role") != "student":
        parent_profile["child_binding_status"] = "pending_student_profile"
        parent_profile["child_email"] = child_email
        return None
    if _norm_email(child.get("parent_email")) != _norm_email(parent_profile.get("email")):
        parent_profile["child_binding_status"] = "pending_student_confirmation"
        parent_profile["child_email"] = child_email
        return None
    parent_id = parent_profile.get("user_id")
    student_id = child.get("user_id")
    if not parent_id or not student_id:
        return None
    binding_status = account_verification_service.binding_status_for_profiles(
        parent_profile,
        child,
    )
    if binding_status == "active":
        user_repo.update_student_parent_link(student_id, parent_id, child.get("relationship", "child"))
    parent_profile["child_binding_status"] = binding_status
    return user_repo.put_parent_student_binding(
        parent_id=parent_id,
        student_id=student_id,
        relationship=child.get("relationship", "child"),
        status=binding_status,
        source="parent_registration",
        actor="system",
        created_at=_utc_now_iso(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@explicit_route_classification(
    "public",
    "pending parent-registration correlation only",
    allowed_identifiers=("parent_id",),
    identifier_scope="command-local",
)
async def register(
    body: RegisterRequest,
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Create a Cognito user and DynamoDB profile, then require email verification."""
    role = body.role.value
    client_id = _public_client_id(settings)
    cognito = _get_cognito(settings)

    issuer = public_identity_service.canonical_public_issuer(settings.allowed_cognito_issuers)
    provider_subject = ""
    resume_command = None
    try:
        signup_resp = cognito.sign_up(
            ClientId=client_id,
            Username=body.email,
            Password=body.password,
            UserAttributes=[{"Name": "email", "Value": body.email}],
        )
        provider_subject = str(signup_resp.get("UserSub") or "").strip()
        if not provider_subject:
            raise public_identity_service.PublicIdentityDependencyError(
                "provider signup omitted subject"
            )
        try:
            cognito.admin_update_user_attributes(
                UserPoolId=settings.cognito_user_pool_id,
                Username=body.email,
                UserAttributes=[{"Name": "custom:subscription_tier", "Value": "free"}],
            )
        except ClientError as exc:
            return public_auth_error_response(
                normalize_cognito_failure(PublicAuthOperation.REGISTER, exc, correlation_id)
            )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "UsernameExistsException":
            try:
                resume_command = public_identity_service.require_public_identity_command(
                    body.email
                )
            except public_identity_service.PublicIdentityCommandConflict:
                return public_auth_error_response(
                    normalize_cognito_failure(PublicAuthOperation.REGISTER, e, correlation_id)
                )
            except Exception as exc:
                raise _public_identity_dependency_error() from exc
            if resume_command.role != role:
                return public_auth_error_response(
                    normalize_cognito_failure(PublicAuthOperation.REGISTER, e, correlation_id)
                )
            try:
                provider_subject = public_identity_service.provider_identity(
                    cognito,
                    user_pool_id=settings.cognito_user_pool_id,
                    email=body.email,
                )["subject"]
                if (
                    resume_command.issuer != issuer
                    or resume_command.subject != provider_subject
                    or resume_command.user_id != provider_subject
                ):
                    return public_auth_error_response(
                        normalize_cognito_failure(PublicAuthOperation.REGISTER, e, correlation_id)
                    )
            except public_identity_service.PublicIdentityCommandConflict:
                return public_auth_error_response(
                    normalize_cognito_failure(PublicAuthOperation.REGISTER, e, correlation_id)
                )
            except Exception as exc:
                raise _public_identity_dependency_error() from exc
        if code != "UsernameExistsException":
            return public_auth_error_response(
                normalize_cognito_failure(PublicAuthOperation.REGISTER, e, correlation_id)
            )

    # Extract onboarding profile fields forwarded by the frontend.
    # Frontend sends nested data under "profile"; legacy payload may use "studentProfile"/"parentProfile".
    nested = body.profile or {}
    student_profile = nested if role == "student" else (body.studentProfile or {})
    parent_profile = nested if role == "parent" else (body.parentProfile or {})

    if role == "student":
        grade = student_profile.get("grade", "")
        subjects = student_profile.get("subjectsNeedingHelp", [])
        school_system = student_profile.get("schoolSystem", "")
        school = student_profile.get("school", "")
        parent_name = student_profile.get("parentName", "")
        parent_email = student_profile.get("parentEmail", "")
        age = student_profile.get("age")
    elif role == "parent":
        grade = parent_profile.get("childGrade", "")
        subjects = parent_profile.get("subjectsNeedingHelp", [])
        school_system = ""
        school = parent_profile.get("childSchool", "")
        parent_name = ""
        parent_email = ""
        age = parent_profile.get("childAge")
    else:
        grade = ""
        subjects = body.subjects or []
        school_system = ""
        school = ""
        parent_name = ""
        parent_email = ""
        age = None

    profile = {
        "user_id": provider_subject,
        "email": body.email,
        "name": body.name or body.email.split("@")[0],
        "role": role,
        "registration_command": _PUBLIC_REGISTRATION_COMMAND,
        "registration_role": role,
        "language": body.preferredLanguage,
        "grade": grade,
        "school": school,
        "school_system": school_system,
        "primary_subjects": subjects,
        "subjects": subjects,
        "parent_name": parent_name,
        "parent_email": parent_email,
        **account_verification_service.registration_profile_fields(_utc_now_iso()),
        "subscription_tier": "free",
        "created_at": _utc_now_iso(),
    }
    if age is not None:
        profile["age"] = int(age)
    if role == "student" and resume_command is None:
        _bind_parent_student_if_possible(parent_email, profile)
    if role == "parent" and resume_command is None:
        child_email = (
            parent_profile.get("childEmail")
            or parent_profile.get("studentEmail")
            or parent_profile.get("child_email")
        )
        _bind_existing_child_if_possible(profile, child_email)
    try:
        if resume_command is None:
            _, profile = public_identity_service.start_or_resume_public_registration(
                email=body.email,
                issuer=issuer,
                subject=provider_subject,
                user_id=provider_subject,
                role=role,
                profile=profile,
                provider=cognito,
                user_pool_id=settings.cognito_user_pool_id,
            )
        else:
            _, profile = public_identity_service.resume_public_registration(
                command=resume_command,
                issuer=issuer,
                subject=provider_subject,
                role=role,
                profile=profile,
                provider=cognito,
                user_pool_id=settings.cognito_user_pool_id,
            )
    except public_identity_service.PublicIdentityCommandConflict as exc:
        raise _public_identity_conflict() from exc
    except public_identity_service.PublicIdentityDependencyError as exc:
        raise _public_identity_dependency_error() from exc

    return _auth_response_for_profile(
        access_token="",
        profile=profile,
        onboarding_status="email_verification_required",
    )


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
        _, profile = await public_identity_service.resolve_public_access_token(
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
@explicit_route_classification("public", "password recovery entry point")
async def forgot_password(
    body: ForgotPasswordRequest,
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Start Cognito's forgot-password flow without exposing account existence."""
    cognito = _get_cognito(settings)
    client_id = _public_client_id(settings)
    try:
        cognito.forgot_password(ClientId=client_id, Username=body.email)
    except ClientError as e:
        failure = normalize_cognito_failure(
            PublicAuthOperation.FORGOT_PASSWORD, e, correlation_id
        )
        if failure.publicly_accepted:
            return PasswordResetResponse(status="accepted")
        return public_auth_error_response(failure)
    return PasswordResetResponse(status="accepted")


@router.post("/reset-password", response_model=PasswordResetResponse)
@explicit_route_classification("public", "password recovery confirmation")
async def reset_password(
    body: ResetPasswordRequest,
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Confirm a Cognito forgot-password code and set a new password."""
    cognito = _get_cognito(settings)
    client_id = _public_client_id(settings)
    try:
        cognito.confirm_forgot_password(
            ClientId=client_id,
            Username=body.email,
            ConfirmationCode=body.confirmationCode,
            Password=body.newPassword,
        )
    except ClientError as e:
        return public_auth_error_response(
            normalize_cognito_failure(PublicAuthOperation.RESET_PASSWORD, e, correlation_id)
        )
    return PasswordResetResponse(status="confirmed")


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
    return LocalePreferenceResponse(
        preferredLocale=locale,
        effectiveLocale=effective_locale,
        supportedLocales=sorted(locale_service.SUPPORTED_LOCALES),
        updatedAt=updated.get("locale_updated_at") or updated_at,
    )


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
        _, profile = await public_identity_service.resolve_public_access_token(
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
):
    """Revoke the access token globally."""
    cognito = _get_cognito(settings)
    try:
        cognito.global_sign_out(AccessToken=body.access_token)
    except ClientError as e:
        return public_auth_error_response(
            normalize_cognito_failure(PublicAuthOperation.LOGOUT, e, correlation_id)
        )
