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
from stoa.services import locale_service

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


class AuthResponse(BaseModel):
    accessToken: str
    user: UserOut
    onboardingStatus: str | None = None
    verificationStatus: str | None = None
    emailVerificationStatus: str | None = None


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
    return profile.get("email_verification_status") or "admin_marked_verified"


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
    student_profile["parent_id"] = parent_id
    student_profile["parent_binding_status"] = "active"
    return user_repo.put_parent_student_binding(
        parent_id=parent_id,
        student_id=student_id,
        relationship="child",
        status="active",
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
    user_repo.update_student_parent_link(student_id, parent_id, child.get("relationship", "child"))
    return user_repo.put_parent_student_binding(
        parent_id=parent_id,
        student_id=student_id,
        relationship=child.get("relationship", "child"),
        status="active",
        source="parent_registration",
        actor="system",
        created_at=_utc_now_iso(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, settings: Settings = Depends(get_settings)):
    """Create a Cognito user and DynamoDB profile, return tokens + user."""
    cognito = _get_cognito(settings)
    user_id = str(uuid.uuid4())
    role = _normalise_role(body.role)

    try:
        cognito.admin_create_user(
            UserPoolId=settings.cognito_user_pool_id,
            Username=body.email,
            TemporaryPassword=body.password,
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "email", "Value": body.email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:role", "Value": role},
                {"Name": "custom:subscription_tier", "Value": "free"},
            ],
        )
        cognito.admin_set_user_password(
            UserPoolId=settings.cognito_user_pool_id,
            Username=body.email,
            Password=body.password,
            Permanent=True,
        )
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
        "email_verification_status": "admin_marked_verified",
        "email_verification_policy": "cognito_email_verified_by_backend_admin_create_user",
        "email_verification_required": False,
        "email_verification_decision_at": _utc_now_iso(),
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

    # Log the user in immediately to return tokens
    client_id = _client_id_for_role(role, settings)
    try:
        resp = cognito.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": body.email, "PASSWORD": body.password},
            ClientId=client_id,
        )
        access_token = resp["AuthenticationResult"]["AccessToken"]
    except ClientError:
        # Registration succeeded even if auto-login fails
        access_token = ""

    verification_status = "pending_review" if role == "teacher" else None

    return AuthResponse(
        accessToken=access_token,
        user=_build_user_out(profile),
        onboardingStatus="completed" if role != "teacher" else "pending_review",
        verificationStatus=verification_status,
        emailVerificationStatus=_email_verification_status(profile),
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
        raise HTTPException(status_code=500, detail=f"Cognito error: {code}")

    access_token = resp["AuthenticationResult"]["AccessToken"]

    # Fetch full profile for response
    profile = user_repo.get_user_by_email(body.email)
    if not profile:
        profile = {"user_id": "", "email": body.email, "role": role}

    return AuthResponse(
        accessToken=access_token,
        user=_build_user_out(profile),
        onboardingStatus="completed",
        emailVerificationStatus=_email_verification_status(profile),
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
