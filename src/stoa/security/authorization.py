"""Typed policy inputs and repository protocols; evaluation arrives later."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable, Mapping, Protocol

from stoa.security.errors import SecurityErrorCode


class ResourceType(StrEnum):
    STUDENT = "student"
    QUESTION = "question"
    CONVERSATION = "conversation"
    PRACTICE = "practice"
    ADAPTIVE_PROFILE = "adaptive_profile"
    REPORT = "report"
    TEACHER_ASSIGNMENT = "teacher_assignment"
    PARENT_BINDING = "parent_binding"


class AuthorizationAction(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RESPOND = "respond"
    ASSIGN = "assign"


class AuthorizationPurpose(StrEnum):
    SELF_SERVICE = "self_service"
    PARENT_OVERSIGHT = "parent_oversight"
    TEACHER_HELP = "teacher_help"
    LEARNING_ASSIGNMENT = "learning_assignment"
    SUPPORT = "support"
    SAFETY_REVIEW = "safety_review"
    INCIDENT_BREAK_GLASS = "incident_break_glass"


ResourceResolver = Callable[[str], Awaitable[Mapping[str, object] | None]]


@dataclass(frozen=True, slots=True)
class AuthorizationSpec:
    resource_type: ResourceType
    action: AuthorizationAction
    purpose: AuthorizationPurpose
    resolver: ResourceResolver

    def __post_init__(self) -> None:
        if not callable(self.resolver):
            raise ValueError("authorization resource resolver is required")


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    result_code: SecurityErrorCode
    policy_version: str
    evidence_reference: str | None = None


class AuthorizationFactRepository(Protocol):
    async def facts_for(self, resource_type: ResourceType, resource_id: str) -> Mapping[str, object] | None: ...
