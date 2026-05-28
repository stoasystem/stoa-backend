"""FastAPI dependency injection — DB client, auth, AWS clients."""
import json
from functools import lru_cache
from typing import Any

import boto3
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from jose.utils import base64url_decode

from stoa.config import Settings, get_settings

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


# ---------------------------------------------------------------------------
# JWKS cache — fetched once per Lambda cold start
# ---------------------------------------------------------------------------

_jwks_cache: dict[str, Any] | None = None


def _fetch_jwks(settings: Settings) -> dict[str, Any]:
    global _jwks_cache
    if _jwks_cache is None:
        resp = httpx.get(settings.cognito_jwks_url, timeout=5.0)
        resp.raise_for_status()
        _jwks_cache = {key["kid"]: key for key in resp.json()["keys"]}
    return _jwks_cache


def _get_public_key(token: str, settings: Settings) -> Any:
    """Return the RSA public key matching the token's kid header."""
    headers = jwt.get_unverified_headers(token)
    kid = headers.get("kid")
    jwks = _fetch_jwks(settings)
    key_data = jwks.get(kid)
    if not key_data:
        raise HTTPException(status_code=401, detail="Unknown signing key")
    from jose.backends import RSAKey
    return RSAKey(key_data, algorithm="RS256")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Validate Cognito JWT (access token) and return the decoded claims."""
    token = credentials.credentials
    try:
        public_key = _get_public_key(token, settings)
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Access tokens have no aud in Cognito
        )
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    # Verify the token was issued by our User Pool
    expected_iss = (
        f"https://cognito-idp.{settings.aws_region}.amazonaws.com"
        f"/{settings.cognito_user_pool_id}"
    )
    if claims.get("iss") != expected_iss:
        raise HTTPException(status_code=401, detail="Token issuer mismatch")

    if claims.get("token_use") != "access":
        raise HTTPException(status_code=401, detail="Expected access token")

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
