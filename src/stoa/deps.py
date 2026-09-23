"""FastAPI dependency injection — DB client, auth, AWS clients."""
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import boto3
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from stoa.config import (
    Settings,
    ValidatedAuthorizationAuditKey,
    get_settings,
    validate_authorization_audit_keyring,
)
from stoa.db.repositories.identity_repo import DynamoIdentityRepository
from stoa.db.repositories import account_deletion_repo
from stoa.db.repositories.security_audit_repo import (
    AuthorizationAuditSink,
    DynamoAuthorizationAuditSink,
    UnavailableAuthorizationAuditSink,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import (
    Actor,
    CanonicalRole,
    IdentityRepository,
    enforce_session_not_revoked,
    resolve_actor,
)
from stoa.security.jwks import HttpxJwksTransport, JwksKeyProvider
from stoa.security.tokens import VerifiedAccessToken, verify_access_token
from stoa.services.account_deletion_service import DeletionReceipt, begin_or_replay_deletion

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
    active_key: bytes,
    previous_keys: tuple[tuple[str, bytes], ...],
    probe_window_seconds: int,
    probe_ttl_seconds: int,
    probe_count_cap: int,
    probe_id_cap: int,
) -> AuthorizationAuditSink:
    return DynamoAuthorizationAuditSink.from_validated_keyring(
        active=ValidatedAuthorizationAuditKey(active_key_id, active_key),
        previous=tuple(
            ValidatedAuthorizationAuditKey(key_id, secret)
            for key_id, secret in previous_keys
        ),
        probe_window_seconds=probe_window_seconds,
        probe_ttl_seconds=probe_ttl_seconds,
        probe_count_cap=probe_count_cap,
        probe_id_cap=probe_id_cap,
    )


def get_authorization_audit_sink(
    settings: Settings = Depends(get_settings),
) -> AuthorizationAuditSink:
    """Construct the durable audit sink only from validated settings."""
    try:
        active, previous = validate_authorization_audit_keyring(
            settings.authorization_audit_active_key_id,
            settings.authorization_audit_active_key,
            settings.authorization_audit_previous_keys,
            allow_development_default=not settings.is_production,
        )
        return _configured_authorization_audit_sink(
            active.key_id,
            active.secret,
            tuple(sorted((key.key_id, key.secret) for key in previous)),
            settings.authorization_audit_probe_window_seconds,
            settings.authorization_audit_probe_ttl_seconds,
            settings.authorization_audit_probe_count_cap,
            settings.authorization_audit_probe_id_cap,
        )
    except Exception:
        return UnavailableAuthorizationAuditSink()


@lru_cache(maxsize=8)
def _configured_jwks_provider(
    issuers: tuple[str, ...],
    connect_timeout: float,
    read_timeout: float,
    ttl_seconds: int,
    max_stale_seconds: int,
    unknown_kid_cooldown_seconds: int,
) -> JwksKeyProvider:
    del issuers  # issuer allowlisting happens before the provider is consulted
    return JwksKeyProvider(
        HttpxJwksTransport(
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        ),
        ttl_seconds=ttl_seconds,
        max_stale_seconds=max_stale_seconds,
        unknown_kid_cooldown_seconds=unknown_kid_cooldown_seconds,
    )


def get_jwks_key_provider(settings: Settings = Depends(get_settings)) -> JwksKeyProvider:
    return _configured_jwks_provider(
        settings.allowed_cognito_issuers,
        settings.cognito_jwks_connect_timeout_seconds,
        settings.cognito_jwks_read_timeout_seconds,
        settings.cognito_jwks_ttl_seconds,
        settings.cognito_jwks_max_stale_seconds,
        settings.cognito_jwks_unknown_kid_cooldown_seconds,
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


# The only routes an account carrying must_change_password may still reach.  A
# closed allowlist keyed on method and registered path, so a route added
# anywhere else is refused by default rather than let through by omission.
#
# GET /auth/me is in here because the change-password screen is the only screen
# such an account can open and it has to be able to render: the browser keeps
# the token but not the account, so after a reload this read is the only way the
# client learns it owes a password change. It is a self-only projection that
# returns strictly less than the sign-in it follows.
FORCED_PASSWORD_CHANGE_EXEMPT_ROUTES = frozenset(
    {
        ("GET", "/auth/me"),
        ("POST", "/auth/password-change/request"),
        ("POST", "/auth/password-change/confirm"),
    }
)


def _forced_password_change_exempt(request: Request) -> bool:
    """Match the registered route path, not the received URL.

    Behind API Gateway the received URL carries a stage prefix, so comparing
    `request.url.path` would silently stop matching in production and open every
    route. An unresolved route is treated as not exempt.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if not isinstance(path, str):
        return False
    return (request.method.upper(), path) in FORCED_PASSWORD_CHANGE_EXEMPT_ROUTES


async def get_actor(
    request: Request,
    verified: VerifiedAccessToken = Depends(get_verified_token),
    repository: IdentityRepository = Depends(get_identity_repository),
) -> Actor:
    try:
        actor = await resolve_actor(verified, repository)
    except SecurityDecisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_body()) from exc
    if actor.must_change_password and not _forced_password_change_exempt(request):
        error = SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
        raise HTTPException(status_code=error.status_code, detail=error.public_body())
    return actor


async def get_deletion_command(
    verified: VerifiedAccessToken = Depends(get_verified_token),
    repository: IdentityRepository = Depends(get_identity_repository),
) -> DeletionReceipt:
    """Resolve only the immutable DELETE /auth/me command, never an Actor.

    Card 006: this is the one authenticated entry point in the build that does
    not go through the Actor resolver above, which means every gate that resolver
    carries - today the forced password change, tomorrow whatever else is hung
    there - is off this path by construction. Do not read that as a general
    licence. It holds because this resolver takes nothing a caller sends: no path,
    query, header, cookie or body parameter, only the verified token and the
    repository, so the account it acts on is the one the token is bound to and no
    other. It also has to answer after the binding is gone, which is what makes
    replaying a completed deletion idempotent and is why an Actor cannot be
    required here.

    `tests/test_forced_password_change.py` holds both halves: that this is still
    the only route resolving no Actor, and that the signature above is still what
    justifies it. A second such route is a change to the authorization surface and
    fails there - naming it somewhere does not settle it.

    Card 002 #5: what this path is therefore not subject to, measured rather than
    assumed. From `resolve_actor`: an active account fence, a present account row,
    exactly one recognised group, that group agreeing with the stored role, and an
    account status of active. From the resolver above: the forced password change.
    Every one of them is a fact about an account still in service, and the account
    here is on its way out. The password change is settled and pinned: an account
    owing one can still close itself, because refusing would make a password the
    price of leaving. The account status is not settled - a suspension raised to
    hold evidence is the case where erasure arguably should wait, and today it does
    not. A gate that must also bind erasure belongs on this resolver, not on the one
    above; the two tests named for this card go red if that distinction is lost.
    """
    try:
        binding = await repository.get_binding(verified.issuer, verified.subject)
        enforce_session_not_revoked(verified, binding)
        user_id = (
            str(binding.get("user_id") or "").strip()
            if binding and binding.get("status") == "active"
            else ""
        )
        if not user_id:
            replay = account_deletion_repo.find_deletion_command_for_identity(
                account_deletion_repo.normalized_identity_hash(
                    verified.issuer.strip().rstrip("/")
                ),
                account_deletion_repo.normalized_identity_hash(verified.subject.strip()),
            )
            user_id = str((replay or {}).get("user_id") or "").strip()
        if not user_id:
            raise account_deletion_repo.AccountDeletionConflict(
                "deletion identity is unavailable"
            )
        return begin_or_replay_deletion(
            verified=verified,
            user_id=user_id,
            method="DELETE",
            path="/auth/me",
            body=b"",
            now_iso=datetime.now(UTC).isoformat(),
        )
    except SecurityDecisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_body()) from exc
    except account_deletion_repo.AccountDeletionConflict as exc:
        error = SecurityDecisionError(SecurityErrorCode.IDENTITY_CONFLICT)
        raise HTTPException(
            status_code=error.status_code, detail=error.public_body()
        ) from exc
    except Exception as exc:
        error = SecurityDecisionError(
            SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
            internal_detail=type(exc).__name__,
        )
        raise HTTPException(
            status_code=error.status_code, detail=error.public_body()
        ) from exc


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
        "must_change_password": actor.must_change_password,
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
