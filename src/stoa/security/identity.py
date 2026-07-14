"""Canonical immutable actor and identity repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Protocol


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
    async def actor_for_binding(self, issuer: str, subject: str) -> Actor | None: ...


class CapabilityGrantRepository(Protocol):
    async def current_grants_for_user(self, user_id: str) -> tuple[CapabilityGrant, ...]: ...
