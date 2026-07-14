"""Canonical immutable actor and identity repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol

from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.tokens import VerifiedAccessToken


class CanonicalRole(StrEnum):
    STUDENT = "student"
    PARENT = "parent"
    TEACHER = "teacher"
    ADMIN = "admin"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    PENDING_VERIFICATION = "pending_verification"
    PENDING_REVIEW = "pending_review"
    SUSPENDED = "suspended"
    SUSPENDED_PENDING_REVIEW = "suspended_pending_review"
    REVOKED = "revoked"
    DISABLED = "disabled"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    capability: str
    scope: str
    version: int


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: str
    issuer: str
    subject: str
    role: CanonicalRole
    account_status: AccountStatus
    cognito_group: str
    current_grants: tuple[CapabilityGrant, ...] = ()
    auth_context: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for name in ("user_id", "issuer", "subject", "cognito_group"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if not isinstance(self.role, CanonicalRole):
            object.__setattr__(self, "role", CanonicalRole(self.role))
        if not isinstance(self.account_status, AccountStatus):
            object.__setattr__(self, "account_status", AccountStatus(self.account_status))
        if self.cognito_group != self.role.value:
            raise ValueError("coarse identity group must match the canonical role")
        if not isinstance(self.current_grants, tuple):
            object.__setattr__(self, "current_grants", tuple(self.current_grants))
        if isinstance(self.auth_context, Mapping):
            object.__setattr__(
                self,
                "auth_context",
                tuple(sorted((str(key), str(value)) for key, value in self.auth_context.items())),
            )

    @property
    def can_authorize(self) -> bool:
        return self.account_status is AccountStatus.ACTIVE


class IdentityRepository(Protocol):
    async def get_binding(self, issuer: str, subject: str) -> Mapping[str, Any] | None: ...

    async def get_account(self, user_id: str) -> Mapping[str, Any] | None: ...

    async def get_current_grants(self, user_id: str) -> list[Mapping[str, Any]]: ...


_GROUP_ROLES = {
    "students": CanonicalRole.STUDENT,
    "parents": CanonicalRole.PARENT,
    "teachers": CanonicalRole.TEACHER,
    "admins": CanonicalRole.ADMIN,
}


async def resolve_actor(
    token: VerifiedAccessToken,
    repository: IdentityRepository,
) -> Actor:
    """Resolve one verified external identity from fresh authoritative local facts."""
    try:
        binding = await repository.get_binding(token.issuer, token.subject)
        if not binding or binding.get("status") != "active":
            raise SecurityDecisionError(SecurityErrorCode.IDENTITY_CONFLICT)
        user_id = str(binding.get("user_id") or "").strip()
        if not user_id:
            raise SecurityDecisionError(SecurityErrorCode.IDENTITY_CONFLICT)

        account = await repository.get_account(user_id)
        if not account:
            raise SecurityDecisionError(SecurityErrorCode.IDENTITY_CONFLICT)
        recognized = [_GROUP_ROLES[group] for group in token.groups if group in _GROUP_ROLES]
        if len(recognized) != 1:
            raise SecurityDecisionError(SecurityErrorCode.IDENTITY_CONFLICT)
        if "tutor" in token.groups:
            raise SecurityDecisionError(SecurityErrorCode.IDENTITY_CONFLICT)
        try:
            local_role = CanonicalRole(str(account.get("role") or ""))
            account_status = AccountStatus(
                str(account.get("account_status") or account.get("status") or "")
            )
        except ValueError as exc:
            raise SecurityDecisionError(SecurityErrorCode.IDENTITY_CONFLICT) from exc
        if recognized[0] is not local_role or account_status is not AccountStatus.ACTIVE:
            raise SecurityDecisionError(SecurityErrorCode.IDENTITY_CONFLICT)

        raw_grants = await repository.get_current_grants(user_id)
        grants = tuple(
            CapabilityGrant(
                capability=str(grant["capability"]),
                scope=str(grant["scope"]),
                version=int(grant["version"]),
            )
            for grant in raw_grants
            if grant.get("status") == "active"
            and grant.get("capability")
            and grant.get("scope")
            and int(grant.get("version") or 0) > 0
        )
        return Actor(
            user_id=user_id,
            issuer=token.issuer,
            subject=token.subject,
            role=local_role,
            account_status=account_status,
            cognito_group=local_role.value,
            current_grants=grants,
            auth_context={"token_use": "access", "client_id": token.client_id},
        )
    except SecurityDecisionError:
        raise
    except Exception as exc:
        raise SecurityDecisionError(
            SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
            internal_detail=type(exc).__name__,
        ) from exc
