"""Authentication routes — aligned with frontend API contract."""
import uuid
from datetime import datetime

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from stoa.config import Settings, get_settings
from stoa.db.repositories import user_repo
from stoa.deps import get_current_user

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
    subscriptionStatus: str = "trial"
    plan: str = "free_trial"


class AuthResponse(BaseModel):
    accessToken: str
    user: UserOut
    onboardingStatus: str | None = None
    verificationStatus: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str
    role: str | None = None


class LogoutRequest(BaseModel):
    access_token: str


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
    return UserOut(
        id=profile.get("user_id", ""),
        name=profile.get("name") or profile.get("email", "").split("@")[0],
        email=profile.get("email", ""),
        role=role,
        preferredLanguage=profile.get("language") or profile.get("preferredLanguage"),
        subscriptionStatus="trial",
        plan="free_trial",
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
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "UsernameExistsException":
            raise HTTPException(status_code=409, detail="Email already registered")
        raise HTTPException(status_code=500, detail=f"Cognito error: {code}")

    profile = {
        "user_id": user_id,
        "email": body.email,
        "name": body.name or body.email.split("@")[0],
        "role": role,
        "language": body.preferredLanguage,
        "subjects": [],
        "subscription_tier": "free",
        "created_at": datetime.utcnow().isoformat(),
    }
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
            raise HTTPException(status_code=401, detail="Invalid email or password")
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
    )


@router.get("/me", response_model=UserOut)
async def me(
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Return the authenticated user's profile."""
    # JWT `username` is Cognito internal UUID — resolve email via admin API
    cognito_username = current_user.get("username", "")
    email = ""
    role_from_cognito = None

    if cognito_username:
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

    profile = user_repo.get_user_by_email(email) if email else None
    if not profile:
        profile = {
            "user_id": current_user.get("sub", ""),
            "email": email,
            "name": email.split("@")[0] if email else "",
            "role": role_from_cognito or current_user.get("role") or "student",
        }
    return _build_user_out(profile)


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
        user=UserOut(id="", name="", email="", role=role),
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
