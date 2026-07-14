"""FastAPI dependency injection — DB client, auth, AWS clients."""
from functools import lru_cache
from typing import Any

import boto3
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from stoa.config import Settings, get_settings
from stoa.security.errors import SecurityDecisionError
from stoa.security.jwks import HttpxJwksTransport, JwksKeyProvider
from stoa.security.tokens import VerifiedAccessToken, verify_access_token

security = HTTPBearer()


@lru_cache
def get_dynamodb():
    settings = get_settings()
    return boto3.resource("dynamodb", region_name=settings.aws_region)


@lru_cache
def get_s3_client():
    settings = get_settings()
    return boto3.client("s3", region_name=settings.aws_region)


@lru_cache
def get_bedrock_client():
    settings = get_settings()
    return boto3.client("bedrock-runtime", region_name=settings.aws_region)


@lru_cache
def get_rekognition_client():
    settings = get_settings()
    return boto3.client("rekognition", region_name=settings.aws_region)


@lru_cache
def get_sqs_client():
    settings = get_settings()
    return boto3.client("sqs", region_name=settings.aws_region)


@lru_cache(maxsize=8)
def _configured_jwks_provider(
    issuers: tuple[str, ...],
    connect_timeout: float,
    read_timeout: float,
    ttl_seconds: int,
    max_stale_seconds: int,
) -> JwksKeyProvider:
    del issuers  # issuer allowlisting happens before the provider is consulted
    return JwksKeyProvider(
        HttpxJwksTransport(
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        ),
        ttl_seconds=ttl_seconds,
        max_stale_seconds=max_stale_seconds,
    )


def get_jwks_key_provider(settings: Settings = Depends(get_settings)) -> JwksKeyProvider:
    return _configured_jwks_provider(
        settings.allowed_cognito_issuers,
        settings.cognito_jwks_connect_timeout_seconds,
        settings.cognito_jwks_read_timeout_seconds,
        settings.cognito_jwks_ttl_seconds,
        settings.cognito_jwks_max_stale_seconds,
    )


async def get_verified_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
    key_provider: JwksKeyProvider = Depends(get_jwks_key_provider),
) -> VerifiedAccessToken:
    try:
        return await verify_access_token(
            credentials.credentials,
            allowed_issuers=settings.allowed_cognito_issuers,
            allowed_client_ids=settings.allowed_cognito_access_clients,
            key_provider=key_provider,
        )
    except SecurityDecisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_body()) from exc


async def get_current_user(
    verified: VerifiedAccessToken = Depends(get_verified_token),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Temporary compatibility resolver; Plan 472-02 Task 3 replaces its fallbacks."""
    claims: dict[str, Any] = {
        "iss": verified.issuer,
        "sub": verified.subject,
        "client_id": verified.client_id,
        "token_use": "access",
        "cognito:groups": list(verified.groups),
    }

    # Resolve role from Cognito groups (present in access token via cognito:groups).
    # Group names: students → student, parents → parent, teachers → teacher, admins → admin
    _group_to_role = {
        "students": "student",
        "parents": "parent",
        "teachers": "teacher",
        "admins": "admin",
    }
    groups = claims.get("cognito:groups") or []
    role = next((_group_to_role[g] for g in groups if g in _group_to_role), None)

    # Fallback: custom:role attribute (not typically in access token but kept for safety)
    if not role:
        role = claims.get("custom:role")

    # Fallback: look up role in DynamoDB when the user was registered but
    # not yet added to a Cognito group (e.g. admin_add_user_to_group failed).
    if not role:
        from stoa.db.repositories import user_repo  # lazy import to avoid circular deps
        cognito_username = claims.get("username", "")
        if cognito_username:
            try:
                cognito = boto3.client("cognito-idp", region_name=settings.aws_region)
                user_data = cognito.admin_get_user(
                    UserPoolId=settings.cognito_user_pool_id,
                    Username=cognito_username,
                )
                attrs = {a["Name"]: a["Value"] for a in user_data.get("UserAttributes", [])}
                email = attrs.get("email", "")
                if email:
                    profile = user_repo.get_user_by_email(email)
                    if profile:
                        raw_role = profile.get("role", "")
                        # Backend stores "teacher"; frontend/JWT uses "tutor" mapping
                        _display = {"teacher": "tutor"}
                        role = _display.get(raw_role, raw_role) or None
                        # Also add the user to the correct Cognito group so future
                        # tokens carry the group claim without needing this fallback.
                        _role_to_group = {
                            "student": "students", "parent": "parents",
                            "teacher": "teachers", "tutor": "teachers", "admin": "admins",
                        }
                        group = _role_to_group.get(raw_role)
                        if group:
                            try:
                                cognito.admin_add_user_to_group(
                                    UserPoolId=settings.cognito_user_pool_id,
                                    Username=cognito_username,
                                    GroupName=group,
                                )
                            except Exception:  # noqa: BLE001
                                pass  # best-effort; role is already resolved above
            except Exception:  # noqa: BLE001
                pass  # if lookup fails, role stays None → 403 on protected routes

    claims["role"] = role
    return claims


def require_role(*roles: str):
    """Return a dependency that ensures the current user has one of the given roles."""
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.get('role')}' is not permitted",
            )
        return user
    return checker
