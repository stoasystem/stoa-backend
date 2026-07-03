"""Authentication routes — aligned with frontend API contract."""
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from stoa.config import Settings, get_settings
from stoa.db.repositories import user_repo
from stoa.deps import get_current_user
from stoa.services import account_verification_service, locale_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models (aligned with frontend types/user.ts)
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # role is optional — backend infers from DynamoDB profile if omitted
    role: str | None = None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: str                       # frontend: student | parent | tutor | admin
    name: str | None = None
    preferredLanguage: str = "de"   # camelCase matches frontend payload
    # Accept (and silently ignore) any extra frontend onboarding fields
    model_config = {"extra": "allow"}


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
    role: str | None = None


class LogoutRequest(BaseModel):
    access_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    role: str | None = None


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    confirmationCode: str = Field(..., min_length=1, max_length=100)
    newPassword: str = Field(..., min_length=1, max_length=256)
    role: str | None = None


class EmailVerificationRequest(BaseModel):
    email: EmailStr
    role: str | None = None


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
    role: str | None = None


class LoginCodeConfirmRequest(LoginCodeRequest):
    code: str = Field(..., min_length=1, max_length=100)


class LoginCodePolicyResponse(BaseModel):
    status: str = "deferred"
    policy: str = account_verification_service.LOGIN_CODE_POLICY
    reason: str


class PasswordResetResponse(BaseModel):
    status: str
    delivery: dict | None = None


class LocalePreferenceUpdate(BaseModel):
    preferredLocale: str = Field(..., min_length=1, max_length=32)


class LocalePreferenceResponse(BaseModel):
    preferredLocale: str
    effectiveLocale: str
    supportedLocales: list[str]
    updatedAt: str | None = None


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

# Frontend uses "tutor" for what the backend calls "teacher"
_ROLE_ALIAS = {"tutor": "teacher"}
_ROLE_DISPLAY = {"teacher": "tutor"}   # reverse for response


def _normalise_role(role: str) -> str:
    """Map frontend role names to backend role names."""
    return _ROLE_ALIAS.get(role, role)


def _display_role(role: str) -> str:
    """Map backend role names back to frontend role names."""
    return _ROLE_DISPLAY.get(role, role)


def _client_id_for_role(role: str, settings: Settings) -> str:
    mapping = {
        "student": settings.cognito_student_client_id,
        "parent": settings.cognito_parent_client_id,
        "teacher": settings.cognito_teacher_client_id,
        "admin": settings.cognito_admin_client_id,
    }
    cid = mapping.get(role)
    if not cid:
        raise HTTPException(status_code=400, detail=f"No Cognito client for role '{role}'")
    return cid


def _get_cognito(settings: Settings):
    return boto3.client("cognito-idp", region_name=settings.aws_region)


def _build_user_out(profile: dict) -> UserOut:
    role = _display_role(profile.get("role", "student"))
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


def _role_for_password_flow(email: str, role: str | None) -> str | None:
    if role:
        return _normalise_role(role)
    profile = user_repo.get_user_by_email(email)
    if not profile:
        return None
    return profile.get("role", "student")


def _email_verification_status(profile: dict) -> str:
    return account_verification_service.verification_status(profile)


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


def _profile_from_current_user(current_user: dict, settings: Settings) -> dict | None:
    user_id = current_user.get("sub", "")
    if user_id:
        profile = user_repo.get_user(user_id)
        if profile:
            return profile

    email = current_user.get("email", "")
    role_from_cognito = None
    cognito_username = current_user.get("username", "")

    if cognito_username and not email:
        try:
            cognito = _get_cognito(settings)
            user_data = cognito.admin_get_user(
                UserPoolId=settings.cognito_user_pool_id,
                Username=cognito_username,
            )
            attrs = {a["Name"]: a["Value"] for a in user_data.get("UserAttributes", [])}
            email = attrs.get("email", "")
            role_from_cognito = attrs.get("custom:role")
        except ClientError:
            pass

    if email:
        profile = user_repo.get_user_by_email(email)
        if profile:
            return profile
        return {
            "user_id": user_id,
            "email": email,
            "name": email.split("@")[0],
            "role": role_from_cognito or current_user.get("role") or "student",
        }

    return None


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
async def register(body: RegisterRequest, settings: Settings = Depends(get_settings)):
    """Create a Cognito user and DynamoDB profile, then require email verification."""
    cognito = _get_cognito(settings)
    role = _normalise_role(body.role)
    client_id = _client_id_for_role(role, settings)

    try:
        signup_resp = cognito.sign_up(
            ClientId=client_id,
            Username=body.email,
            Password=body.password,
            UserAttributes=[{"Name": "email", "Value": body.email}],
        )
        user_id = signup_resp.get("UserSub") or str(uuid.uuid4())
        try:
            cognito.admin_update_user_attributes(
                UserPoolId=settings.cognito_user_pool_id,
                Username=body.email,
                UserAttributes=[
                    {"Name": "custom:role", "Value": role},
                    {"Name": "custom:subscription_tier", "Value": "free"},
                ],
            )
        except ClientError:
            pass
        # Add user to the role group so the access token carries cognito:groups.
        # Retry once on transient failure; deps.py has a self-healing fallback but
        # it's better to get the group right at registration time.
        _role_to_group = {"student": "students", "parent": "parents",
                          "teacher": "teachers", "admin": "admins"}
        group_name = _role_to_group.get(role)
        if group_name:
            for _attempt in range(2):
                try:
                    cognito.admin_add_user_to_group(
                        UserPoolId=settings.cognito_user_pool_id,
                        Username=body.email,
                        GroupName=group_name,
                    )
                    break
                except ClientError:
                    if _attempt == 1:
                        # Log but don't fail registration; deps.py fallback handles it
                        import logging
                        logging.getLogger(__name__).warning(
                            "Failed to add user %s to group %s after 2 attempts",
                            body.email, group_name,
                        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "UsernameExistsException":
            raise HTTPException(status_code=409, detail="Email already registered")
        if code in ("InvalidPasswordException", "InvalidParameterException"):
            raise HTTPException(status_code=400, detail="Password does not meet requirements")
        raise HTTPException(status_code=500, detail=f"Cognito error: {code}")

    # Extract onboarding profile fields forwarded by the frontend.
    # Frontend sends nested data under "profile"; legacy payload may use "studentProfile"/"parentProfile".
    extra = body.model_extra or {}
    nested = extra.get("profile") or {}
    student_profile = nested if role == "student" else (extra.get("studentProfile") or {})
    parent_profile = nested if role == "parent" else (extra.get("parentProfile") or {})

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
        subjects = extra.get("subjects", [])
        school_system = ""
        school = ""
        parent_name = ""
        parent_email = ""
        age = None

    profile = {
        "user_id": user_id,
        "email": body.email,
        "name": body.name or body.email.split("@")[0],
        "role": role,
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
    if role == "student":
        _bind_parent_student_if_possible(parent_email, profile)
    if role == "parent":
        child_email = (
            parent_profile.get("childEmail")
            or parent_profile.get("studentEmail")
            or parent_profile.get("child_email")
        )
        _bind_existing_child_if_possible(profile, child_email)
    user_repo.put_user(profile)

    verification_status = "pending_review" if role == "teacher" else None

    return _auth_response_for_profile(
        access_token="",
        profile=profile,
        onboarding_status="email_verification_required" if role != "teacher" else "pending_review",
        verification_status=verification_status,
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, settings: Settings = Depends(get_settings)):
    """Authenticate user. Role is inferred from DynamoDB profile if not provided."""
    # Look up role from DynamoDB profile (frontend doesn't send role)
    if body.role:
        role = _normalise_role(body.role)
    else:
        profile = user_repo.get_user_by_email(body.email)
        if not profile:
            raise HTTPException(
                status_code=401,
                detail="No account found for this email. Please register first.",
            )
        role = profile.get("role", "student")

    cognito = _get_cognito(settings)
    client_id = _client_id_for_role(role, settings)

    try:
        resp = cognito.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": body.email, "PASSWORD": body.password},
            ClientId=client_id,
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("NotAuthorizedException", "UserNotFoundException"):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if code == "UserNotConfirmedException":
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "email_verification_required",
                    "message": "Email verification is required before login.",
                },
            )
        raise HTTPException(status_code=500, detail=f"Cognito error: {code}")

    access_token = resp["AuthenticationResult"]["AccessToken"]

    # Fetch full profile for response
    profile = user_repo.get_user_by_email(body.email)
    if not profile:
        profile = {"user_id": "", "email": body.email, "role": role}
    if not account_verification_service.can_return_tokens(profile):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "email_verification_required",
                "message": "Email verification is required before login.",
                "emailVerificationStatus": _email_verification_status(profile),
                "accountActivationStatus": account_verification_service.account_activation_status(profile),
            },
        )

    return _auth_response_for_profile(
        access_token=access_token,
        profile=profile,
        onboarding_status="completed",
    )


@router.post("/email-verification/resend", response_model=EmailVerificationResponse)
async def resend_email_verification(
    body: EmailVerificationRequest,
    settings: Settings = Depends(get_settings),
):
    """Resend Cognito's sign-up confirmation code without exposing provider internals."""
    profile = user_repo.get_user_by_email(body.email)
    if not profile:
        return EmailVerificationResponse(
            status="accepted",
            emailVerificationStatus=account_verification_service.STATUS_PENDING,
            emailVerificationRequired=True,
            accountActivationStatus=account_verification_service.PENDING_EMAIL,
            resendAllowed=False,
        )
    public_state = account_verification_service.public_state(profile)
    if account_verification_service.is_email_verified(profile):
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

    role = _role_for_password_flow(body.email, body.role) or profile.get("role", "student")
    cognito = _get_cognito(settings)
    client_id = _client_id_for_role(role, settings)
    try:
        resp = cognito.resend_confirmation_code(ClientId=client_id, Username=body.email)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("LimitExceededException", "TooManyRequestsException"):
            updated = user_repo.update_email_verification_state(
                profile["user_id"],
                account_verification_service.resend_limited_fields(_utc_now_iso()),
            )
            state = account_verification_service.public_state(updated or profile)
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "verification_resend_limited",
                    "emailVerificationStatus": state["emailVerificationStatus"],
                },
            )
        if code in ("InvalidParameterException", "UserNotFoundException"):
            return EmailVerificationResponse(
                status="accepted",
                emailVerificationStatus=public_state["emailVerificationStatus"],
                emailVerificationRequired=public_state["emailVerificationRequired"],
                accountActivationStatus=public_state["accountActivationStatus"],
                resendAllowed=False,
            )
        raise HTTPException(status_code=500, detail=f"Cognito error: {code}")

    updated = user_repo.update_email_verification_state(
        profile["user_id"],
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
async def confirm_email_verification(
    body: EmailVerificationConfirmRequest,
    settings: Settings = Depends(get_settings),
):
    """Confirm Cognito's sign-up code and activate the local account profile."""
    profile = user_repo.get_user_by_email(body.email)
    if not profile:
        raise HTTPException(status_code=400, detail="Invalid verification request")
    role = _role_for_password_flow(body.email, body.role) or profile.get("role", "student")
    cognito = _get_cognito(settings)
    client_id = _client_id_for_role(role, settings)
    try:
        cognito.confirm_sign_up(
            ClientId=client_id,
            Username=body.email,
            ConfirmationCode=body.confirmationCode,
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ExpiredCodeException":
            user_repo.update_email_verification_state(
                profile["user_id"],
                account_verification_service.expired_fields(_utc_now_iso()),
            )
            raise HTTPException(status_code=400, detail="Verification code expired")
        if code in (
            "CodeMismatchException",
            "InvalidParameterException",
            "NotAuthorizedException",
            "UserNotFoundException",
        ):
            raise HTTPException(status_code=400, detail="Invalid verification request")
        if code in ("LimitExceededException", "TooManyRequestsException"):
            raise HTTPException(status_code=429, detail="Verification confirmation rate limit exceeded")
        raise HTTPException(status_code=500, detail=f"Cognito error: {code}")

    group_name = {
        "student": "students",
        "parent": "parents",
        "teacher": "teachers",
        "admin": "admins",
    }.get(role)
    if group_name:
        try:
            cognito.admin_add_user_to_group(
                UserPoolId=settings.cognito_user_pool_id,
                Username=body.email,
                GroupName=group_name,
            )
        except ClientError:
            pass
    updated = user_repo.update_email_verification_state(
        profile["user_id"],
        account_verification_service.verified_fields(_utc_now_iso()),
    )
    state = account_verification_service.public_state(updated or profile)
    return EmailVerificationResponse(
        status="confirmed",
        emailVerificationStatus=state["emailVerificationStatus"],
        emailVerificationRequired=state["emailVerificationRequired"],
        accountActivationStatus=state["accountActivationStatus"],
        resendAllowed=False,
    )


@router.post("/login-code/request", response_model=LoginCodePolicyResponse)
async def request_login_code(body: LoginCodeRequest):
    """Explicitly gate passwordless login until a Cognito-compatible flow exists."""
    return LoginCodePolicyResponse(
        reason="Passwordless login codes are deferred until Cognito custom auth triggers are configured.",
    )


@router.post("/login-code/confirm", response_model=LoginCodePolicyResponse)
async def confirm_login_code(body: LoginCodeConfirmRequest):
    """Explicitly reject placeholder login codes; no production token is minted here."""
    return LoginCodePolicyResponse(
        reason="Login code confirmation is deferred and cannot produce Cognito tokens in this backend.",
    )


@router.post("/forgot-password", response_model=PasswordResetResponse)
async def forgot_password(body: ForgotPasswordRequest, settings: Settings = Depends(get_settings)):
    """Start Cognito's forgot-password flow without exposing account existence."""
    role = _role_for_password_flow(body.email, body.role)
    if role is None:
        return PasswordResetResponse(status="accepted")
    cognito = _get_cognito(settings)
    client_id = _client_id_for_role(role, settings)
    try:
        resp = cognito.forgot_password(ClientId=client_id, Username=body.email)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("UserNotFoundException", "ResourceNotFoundException"):
            return PasswordResetResponse(status="accepted")
        if code in ("LimitExceededException", "TooManyRequestsException"):
            raise HTTPException(status_code=429, detail="Password reset request rate limit exceeded")
        raise HTTPException(status_code=500, detail=f"Cognito error: {code}")
    delivery = resp.get("CodeDeliveryDetails")
    return PasswordResetResponse(status="accepted", delivery=delivery)


@router.post("/reset-password", response_model=PasswordResetResponse)
async def reset_password(body: ResetPasswordRequest, settings: Settings = Depends(get_settings)):
    """Confirm a Cognito forgot-password code and set a new password."""
    role = _role_for_password_flow(body.email, body.role)
    if role is None:
        raise HTTPException(status_code=400, detail="Invalid password reset request")
    cognito = _get_cognito(settings)
    client_id = _client_id_for_role(role, settings)
    try:
        cognito.confirm_forgot_password(
            ClientId=client_id,
            Username=body.email,
            ConfirmationCode=body.confirmationCode,
            Password=body.newPassword,
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in (
            "CodeMismatchException",
            "ExpiredCodeException",
            "InvalidPasswordException",
            "InvalidParameterException",
            "UserNotFoundException",
        ):
            raise HTTPException(status_code=400, detail="Invalid password reset request")
        if code in ("LimitExceededException", "TooManyRequestsException"):
            raise HTTPException(status_code=429, detail="Password reset request rate limit exceeded")
        raise HTTPException(status_code=500, detail=f"Cognito error: {code}")
    return PasswordResetResponse(status="confirmed")


@router.get("/me", response_model=UserOut)
async def me(
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Return the authenticated user's profile."""
    profile = _profile_from_current_user(current_user, settings)
    if not profile:
        profile = {
            "user_id": current_user.get("sub", ""),
            "email": current_user.get("email", ""),
            "name": "",
            "role": current_user.get("role") or "student",
        }
    return _build_user_out(profile)


@router.patch("/me/preferences/locale", response_model=LocalePreferenceResponse)
async def update_my_locale_preference(
    body: LocalePreferenceUpdate,
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Persist the authenticated user's preferred locale."""
    profile = _profile_from_current_user(current_user, settings)
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
async def refresh(body: RefreshRequest, settings: Settings = Depends(get_settings)):
    """Exchange a refresh token for fresh tokens."""
    # Require role for refresh (or default to student)
    role = _normalise_role(body.role) if body.role else "student"
    cognito = _get_cognito(settings)
    client_id = _client_id_for_role(role, settings)

    try:
        resp = cognito.initiate_auth(
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": body.refresh_token},
            ClientId=client_id,
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "NotAuthorizedException":
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        raise HTTPException(status_code=500, detail=f"Cognito error: {code}")

    result = resp["AuthenticationResult"]
    return AuthResponse(
        accessToken=result["AccessToken"],
        user=UserOut(
            id="",
            name="",
            email="",
            role=role,
            preferredLanguage=locale_service.DEFAULT_LOCALE,
            preferredLocale=locale_service.DEFAULT_LOCALE,
            effectiveLocale=locale_service.DEFAULT_LOCALE,
        ),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, settings: Settings = Depends(get_settings)):
    """Revoke the access token globally."""
    cognito = _get_cognito(settings)
    try:
        cognito.global_sign_out(AccessToken=body.access_token)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "NotAuthorizedException":
            raise HTTPException(status_code=401, detail="Invalid access token")
        raise HTTPException(status_code=500, detail=f"Cognito error: {code}")
