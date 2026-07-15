"""FastAPI dependency injection — DB client, auth, AWS clients."""
from functools import lru_cache
from typing import Any

import boto3
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from stoa.config import Settings, get_settings
from stoa.db.repositories.identity_repo import DynamoIdentityRepository
from stoa.db.repositories.security_audit_repo import (
    AuthorizationAuditSink,
    DynamoAuthorizationAuditSink,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor, CanonicalRole, IdentityRepository, resolve_actor
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


@lru_cache(maxsize=1)
def _configured_authorization_audit_sink(
    active_key_id: str,
    active_key: str,
    previous_keys: tuple[tuple[str, str], ...],
    probe_window_seconds: int,
    probe_ttl_seconds: int,
    probe_count_cap: int,
    probe_id_cap: int,
) -> AuthorizationAuditSink:
    return DynamoAuthorizationAuditSink(
        active_key_id=active_key_id,
        active_secret=active_key,
        previous_keys=dict(previous_keys),
        probe_window_seconds=probe_window_seconds,
        probe_ttl_seconds=probe_ttl_seconds,
        probe_count_cap=probe_count_cap,
        probe_id_cap=probe_id_cap,
    )


def get_authorization_audit_sink(
    settings: Settings = Depends(get_settings),
) -> AuthorizationAuditSink:
    """Construct the durable audit sink only from validated settings."""
    return _configured_authorization_audit_sink(
        settings.authorization_audit_active_key_id,
        settings.authorization_audit_active_key,
        tuple(sorted(settings.authorization_audit_previous_keys.items())),
        settings.authorization_audit_probe_window_seconds,
        settings.authorization_audit_probe_ttl_seconds,
        settings.authorization_audit_probe_count_cap,
        settings.authorization_audit_probe_id_cap,
    )


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


@lru_cache(maxsize=1)
def get_identity_repository() -> IdentityRepository:
    return DynamoIdentityRepository()


async def get_actor(
    verified: VerifiedAccessToken = Depends(get_verified_token),
    repository: IdentityRepository = Depends(get_identity_repository),
) -> Actor:
    try:
        return await resolve_actor(verified, repository)
    except SecurityDecisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_body()) from exc


async def get_current_user(actor: Actor = Depends(get_actor)) -> dict[str, Any]:
    """Read-only legacy projection for handlers awaiting typed Actor migration."""
    capabilities = {
        grant.capability: "granted"
        for grant in actor.current_grants
    }
    return {
        "sub": actor.user_id,
        "user_id": actor.user_id,
        "cognito_sub": actor.subject,
        "role": actor.role.value,
        "account_status": actor.account_status.value,
        "capabilities": capabilities,
    }


def require_role(*roles: str):
    """Return a dependency that ensures the current user has one of the given roles."""
    canonical_roles = {
        CanonicalRole(role).value
        for role in roles
        if role in {member.value for member in CanonicalRole}
    }

    async def checker(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user.get("role") not in canonical_roles:
            error = SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error.public_body())
        return user
    return checker
