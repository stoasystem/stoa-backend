"""Cognito access-token verification with stable redacted failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Collection

from jose import ExpiredSignatureError, JWTError, jwt

from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.jwks import JwksKeyProvider


@dataclass(frozen=True, slots=True)
class VerifiedAccessToken:
    issuer: str
    subject: str
    client_id: str
    groups: tuple[str, ...]
    verified_email: str | None = None


async def verify_access_token(
    token: str,
    *,
    allowed_issuers: Collection[str],
    allowed_client_ids: Collection[str],
    key_provider: JwksKeyProvider,
) -> VerifiedAccessToken:
    try:
        headers = jwt.get_unverified_headers(token)
        unverified = jwt.get_unverified_claims(token)
    except JWTError as exc:
        raise SecurityDecisionError(SecurityErrorCode.INVALID_TOKEN) from exc

    issuer = unverified.get("iss")
    kid = headers.get("kid")
    if not isinstance(issuer, str) or issuer not in set(allowed_issuers):
        raise SecurityDecisionError(SecurityErrorCode.INVALID_TOKEN)
    if headers.get("alg") != "RS256" or not isinstance(kid, str) or not kid:
        raise SecurityDecisionError(SecurityErrorCode.INVALID_TOKEN)

    public_key = await key_provider.get_key(issuer, kid)
    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False, "require_exp": True, "require_iat": True},
        )
    except ExpiredSignatureError as exc:
        raise SecurityDecisionError(SecurityErrorCode.TOKEN_EXPIRED) from exc
    except JWTError as exc:
        raise SecurityDecisionError(SecurityErrorCode.INVALID_TOKEN) from exc

    client_id = claims.get("client_id")
    subject = claims.get("sub")
    if (
        claims.get("token_use") != "access"
        or not isinstance(client_id, str)
        or client_id not in set(allowed_client_ids)
        or not isinstance(subject, str)
        or not subject
    ):
        raise SecurityDecisionError(SecurityErrorCode.INVALID_TOKEN)
    groups = claims.get("cognito:groups") or ()
    if not isinstance(groups, (list, tuple)) or not all(isinstance(value, str) for value in groups):
        raise SecurityDecisionError(SecurityErrorCode.INVALID_TOKEN)
    verified_email = None
    if claims.get("email_verified") is True and isinstance(claims.get("email"), str):
        verified_email = claims["email"].strip().casefold() or None
    return VerifiedAccessToken(issuer, subject, client_id, tuple(groups), verified_email)


@dataclass(frozen=True, slots=True)
class TokenCaseDecision:
    allowed: bool
    safe_code: str


def verify_token_case(claim_case: str) -> TokenCaseDecision:
    """Keep Wave 0's named negative-case inventory executable without provider access."""
    code = (
        SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE
        if claim_case == "jwks-outage"
        else SecurityErrorCode.TOKEN_EXPIRED
        if claim_case == "expired"
        else SecurityErrorCode.INVALID_TOKEN
    )
    return TokenCaseDecision(False, code.value)
