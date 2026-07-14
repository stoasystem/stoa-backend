"""Fail-closed identity and authorization contracts for STOA."""

from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    PolicyDecision,
    ResourceType,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import AccountStatus, Actor, CanonicalRole

__all__ = [
    "AccountStatus",
    "Actor",
    "AuthorizationAction",
    "AuthorizationPurpose",
    "AuthorizationSpec",
    "CanonicalRole",
    "PolicyDecision",
    "ResourceType",
    "SecurityDecisionError",
    "SecurityErrorCode",
]
