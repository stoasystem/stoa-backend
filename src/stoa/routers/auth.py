"""Authentication routes — Cognito-backed register / login / refresh / logout."""
import uuid
from datetime import datetime

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from stoa.config import Settings, get_settings
from stoa.db.repositories import user_repo
from stoa.models.user import Grade, RegisterRequest, SubscriptionTier, UserRole

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    role: UserRole


class AuthTokens(BaseModel):
    access_token: str
    id_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
    role: UserRole


class LogoutRequest(BaseModel):
    access_token: str


def _get_cognito(settings: Settings) -> boto3.client:
    return boto3.client("cognito-idp", region_name=settings.aws_region)


def _client_id_for_role(role: UserRole, settings: Settings) -> str:
    """Return the Cognito App Client ID matching the given role."""
    mapping = {
        UserRole.STUDENT: settings.cognito_student_client_id,
        UserRole.PARENT: settings.cognito_parent_client_id,
        UserRole.TEACHER: settings.cognito_teacher_client_id,
        UserRole.ADMIN: settings.cognito_admin_client_id,
    }
    client_id = mapping.get(role)
    if not client_id:
        raise HTTPException(status_code=400, detail=f"No Cognito client configured for role '{role}'")
    return client_id


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, settings: Settings = Depends(get_settings)):
    """Create a new Cognito user and store the profile in DynamoDB."""
    cognito = _get_cognito(settings)
    user_id = str(uuid.uuid4())

    custom_attrs = [
        {"Name": "custom:role", "Value": body.role.value},
        {"Name": "custom:subscription_tier", "Value": SubscriptionTier.FREE.value},
    ]
    if body.grade:
        custom_attrs.append({"Name": "custom:grade", "Value": body.grade.value})

    try:
        cognito.admin_create_user(
            UserPoolId=settings.cognito_user_pool_id,
            Username=body.email,
            TemporaryPassword=body.password,
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "email", "Value": body.email},
                {"Name": "email_verified", "Value": "true"},
                *custom_attrs,
            ],
        )
        # Immediately set a permanent password so the user is CONFIRMED
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
        "role": body.role.value,
        "grade": body.grade.value if body.grade else None,
        "subjects": body.subjects or [],
        "language": body.language,
        "subscription_tier": SubscriptionTier.FREE.value,
        "parent_id": body.parent_id,
        "created_at": datetime.utcnow().isoformat(),
    }
    user_repo.put_user(profile)

    return {"user_id": user_id, "email": body.email, "role": body.role.value}


@router.post("/login", response_model=AuthTokens)
async def login(body: LoginRequest, settings: Settings = Depends(get_settings)):
    """Authenticate with USER_PASSWORD_AUTH flow and return JWT tokens."""
    cognito = _get_cognito(settings)
    client_id = _client_id_for_role(body.role, settings)

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

    result = resp["AuthenticationResult"]
    return AuthTokens(
        access_token=result["AccessToken"],
        id_token=result["IdToken"],
        refresh_token=result["RefreshToken"],
        expires_in=result["ExpiresIn"],
    )


@router.post("/refresh", response_model=AuthTokens)
async def refresh(body: RefreshRequest, settings: Settings = Depends(get_settings)):
    """Exchange a refresh token for a new access/id token pair."""
    cognito = _get_cognito(settings)
    client_id = _client_id_for_role(body.role, settings)

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
    return AuthTokens(
        access_token=result["AccessToken"],
        id_token=result["IdToken"],
        refresh_token=body.refresh_token,
        expires_in=result["ExpiresIn"],
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, settings: Settings = Depends(get_settings)):
    """Revoke the access token (global sign-out alternative)."""
    cognito = _get_cognito(settings)
    try:
        cognito.global_sign_out(AccessToken=body.access_token)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "NotAuthorizedException":
            raise HTTPException(status_code=401, detail="Invalid access token")
        raise HTTPException(status_code=500, detail=f"Cognito error: {code}")
