"""Central fail-closed student-resource authorization policy.

The policy deliberately has one decision path.  Resolvers load a resource once,
fact loaders attach current relationship/assignment evidence, and handlers receive
that same :class:`AuthorizedResource` after an allow decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from inspect import isawaitable
from typing import Awaitable, Callable, Mapping, Protocol

from stoa.db.repositories.security_audit_repo import AuthorizationAuditSink
from stoa.security.errors import (
    SecurityDecisionError,
    SecurityErrorCode,
    SecurityHttpResponse,
    normalize_correlation_id,
    safe_error_response,
)
from stoa.security.events import SecurityEvent, project_security_event
from stoa.security.identity import Actor, CanonicalRole


POLICY_VERSION = "472.v1"


class ResourceType(StrEnum):
    STUDENT = "student"
    QUESTION = "question"
    CONVERSATION = "conversation"
    PRACTICE = "practice"
    ADAPTIVE_PROFILE = "adaptive_profile"
    REPORT = "report"
    TEACHER_ASSIGNMENT = "teacher_assignment"
    PARENT_BINDING = "parent_binding"
    TEACHER_PORTAL = "teacher_portal"
    TEACHER_HELP_REQUEST = "teacher_help_request"
    AI_TEACHER_DRAFT = "ai_teacher_draft"
    NOTIFICATION_COLLECTION = "notification_collection"
    NOTIFICATION_EVENT = "notification_event"
    NOTIFICATION_PREFERENCE = "notification_preference"
    NOTIFICATION_DIGEST = "notification_digest"
    NOTIFICATION_PUSH_TOKEN = "notification_push_token"
    OPERATOR_RESOURCE = "operator_resource"
    UPLOAD = "upload"
    ATTACHMENT = "attachment"


class AuthorizationAction(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RESPOND = "respond"
    ASSIGN = "assign"
    CLAIM = "claim"
    RESOLVE = "resolve"
    LOOKUP = "lookup"
    EXPORT = "export"
    EXTERNAL_SEND = "external_send"
    MANAGE_PRIVILEGE = "manage_privilege"
    CURRICULUM_MUTATION = "curriculum_mutation"


class AuthorizationPurpose(StrEnum):
    SELF_SERVICE = "self_service"
    PARENT_OVERSIGHT = "parent_oversight"
    TEACHER_HELP = "teacher_help"
    TEACHER_DISPATCH = "teacher_dispatch"
    AI_TEACHER_TOOLS = "ai_teacher_tools"
    LEARNING_ASSIGNMENT = "learning_assignment"
    ASSIGNMENT_AUTOMATION_PREVIEW = "assignment_automation_preview"
    ASSIGNMENT_AUTOMATION_EXECUTE = "assignment_automation_execute"
    SUPPORT = "support"
    SAFETY_REVIEW = "safety_review"
    INCIDENT_BREAK_GLASS = "incident_break_glass"
    NOTIFICATION_SELF_SERVICE = "notification_self_service"
    NOTIFICATION_EVENT_INSPECTION = "notification_event_inspection"
    NOTIFICATION_DELIVERY_HEALTH = "notification_delivery_health"
    IDENTITY_MANAGEMENT = "identity_management"
    MODERATION_OPERATIONS = "moderation_operations"
    CURRICULUM_OPERATIONS = "curriculum_operations"
    ACCOUNT_OPERATIONS = "account_operations"
    BILLING_OPERATIONS = "billing_operations"
    USAGE_OPERATIONS = "usage_operations"
    GLOBAL_OPERATIONS = "global_operations"
    REPORT_OPERATIONS = "report_operations"
    REPORT_RECOVERY = "report_recovery"
    SUPPORT_HANDOFF = "support_handoff"
    AUDIT_GOVERNANCE = "audit_governance"


@dataclass(frozen=True, slots=True)
class ResourceRef:
    """Canonical identity and ownership coordinates for one loaded resource."""

    resource_type: ResourceType
    resource_id: str
    student_id: str
    owner_id: str | None = None
    question_id: str | None = None
    session_id: str | None = None
    relationship_known: bool = False
    safe_support_metadata: bool = False

    def __post_init__(self) -> None:
        if not self.resource_id.strip() or not self.student_id.strip():
            raise ValueError("resource_id and student_id are required")
        if not isinstance(self.resource_type, ResourceType):
            object.__setattr__(self, "resource_type", ResourceType(self.resource_type))


@dataclass(frozen=True, slots=True)
class ParentAuthorizationFacts:
    forward: Mapping[str, object] | None = None
    reverse: Mapping[str, object] | None = None
    parent_account: Mapping[str, object] | None = None
    student_account: Mapping[str, object] | None = None

    def matches(self, parent_id: str, student_id: str) -> bool:
        rows = (self.forward, self.reverse)
        if any(not row or row.get("status") != "active" for row in rows):
            return False
        forward, reverse = rows
        assert forward is not None and reverse is not None
        coordinates = ("parent_id", "student_id", "relationship", "version")
        if any(forward.get(key) != reverse.get(key) for key in coordinates):
            return False
        if forward.get("parent_id") != parent_id or forward.get("student_id") != student_id:
            return False
        return _active_account(
            self.parent_account, parent_id, CanonicalRole.PARENT
        ) and _active_account(self.student_account, student_id, CanonicalRole.STUDENT)


@dataclass(frozen=True, slots=True)
class TeacherAuthorizationFacts:
    question: Mapping[str, object] | None = None
    session: Mapping[str, object] | None = None
    assignment: Mapping[str, object] | None = None
    teacher_account: Mapping[str, object] | None = None
    student_account: Mapping[str, object] | None = None

    def permits(
        self,
        actor_id: str,
        resource: ResourceRef,
        action: AuthorizationAction,
        purpose: AuthorizationPurpose,
        now: datetime,
    ) -> bool:
        if not _active_account(self.teacher_account, actor_id, CanonicalRole.TEACHER):
            return False
        if not _active_account(self.student_account, resource.student_id, CanonicalRole.STUDENT):
            return False
        if self._current_task_permits(actor_id, resource, action, purpose, now):
            return True
        assignment = self.assignment
        if not assignment or assignment.get("status") != "active":
            return False
        if (
            assignment.get("teacher_id") != actor_id
            or assignment.get("student_id") != resource.student_id
        ):
            return False
        if _expired(assignment.get("expires_at"), now):
            return False
        exact_scope = _scope_matches(
            str(assignment.get("scope") or ""), resource, action, purpose, allow_global=False
        )
        declared_scope = (
            resource.resource_type.value in _string_set(assignment.get("resource_types"))
            and action.value in _string_set(assignment.get("actions"))
            and purpose.value in _string_set(assignment.get("purposes"))
        )
        return exact_scope or declared_scope

    def _current_task_permits(
        self,
        actor_id: str,
        resource: ResourceRef,
        action: AuthorizationAction,
        purpose: AuthorizationPurpose,
        now: datetime,
    ) -> bool:
        if purpose is not AuthorizationPurpose.TEACHER_HELP:
            return False
        question = self.question
        if not question or question.get("student_id") != resource.student_id:
            return False
        linked_ids = {
            str(question.get("question_id") or ""),
            str(question.get("conversation_id") or ""),
            str(question.get("session_id") or ""),
        }
        if resource.resource_type not in {
            ResourceType.QUESTION,
            ResourceType.CONVERSATION,
            ResourceType.TEACHER_HELP_REQUEST,
            ResourceType.AI_TEACHER_DRAFT,
        }:
            return False
        task_link_id = (
            str(resource.question_id or "")
            if resource.resource_type is ResourceType.AI_TEACHER_DRAFT
            else resource.resource_id
        )
        if task_link_id not in linked_ids:
            return False
        if action not in {
            AuthorizationAction.READ,
            AuthorizationAction.CREATE,
            AuthorizationAction.UPDATE,
            AuthorizationAction.RESPOND,
            AuthorizationAction.RESOLVE,
            AuthorizationAction.CLAIM,
        }:
            return False
        dispatch_status = str(question.get("dispatch_status") or "unassigned")
        if action is AuthorizationAction.CLAIM:
            if resource.resource_type is not ResourceType.QUESTION:
                return False
            if question.get("status") != "escalated":
                return False
            if actor_id in _string_set(question.get("previous_dispatch_teacher_ids")):
                return False
            if dispatch_status == "dispatched":
                return question.get("dispatched_teacher_id") == actor_id and not _expired(
                    question.get("dispatch_deadline_at"), now
                )
            return dispatch_status in {"", "unassigned", "pending"}

        if dispatch_status in {"timed_out", "reassigned", "revoked"}:
            return False
        if action in {
            AuthorizationAction.RESPOND,
            AuthorizationAction.RESOLVE,
            AuthorizationAction.UPDATE,
        }:
            if question.get("teacher_id") != actor_id:
                return False
            if question.get("status") not in {"teacher_active", "resolved"}:
                return False
        else:
            current_teacher = question.get("teacher_id") or question.get("dispatched_teacher_id")
            if current_teacher != actor_id:
                return False
            if question.get("status") not in {"escalated", "teacher_active", "resolved"}:
                return False
            if dispatch_status == "dispatched" and _expired(
                question.get("dispatch_deadline_at"), now
            ):
                return False
        if self.session:
            session = self.session
            if (
                session.get("teacher_id") != actor_id
                or session.get("student_id") != resource.student_id
            ):
                return False
            if session.get("resolved_at") and action is not AuthorizationAction.READ:
                return False
        return True


@dataclass(frozen=True, slots=True)
class BreakGlassEvidence:
    incident_id: str
    reason: str
    notification_reference: str
    review_reference: str
    issued_at: datetime
    expires_at: datetime

    def valid(self, now: datetime) -> bool:
        bounded = self.issued_at <= now < self.expires_at
        short_lived = self.expires_at - self.issued_at <= timedelta(minutes=15)
        return (
            bounded
            and short_lived
            and all(
                value.strip()
                for value in (
                    self.incident_id,
                    self.reason,
                    self.notification_reference,
                    self.review_reference,
                )
            )
            and self.expires_at > now
        )


@dataclass(frozen=True, slots=True)
class AuthorizationFacts:
    parent: ParentAuthorizationFacts | None = None
    teacher: TeacherAuthorizationFacts | None = None
    break_glass: BreakGlassEvidence | None = None


@dataclass(frozen=True, slots=True)
class AuthorizedResource:
    """One resolver result, enriched with current facts and passed to the handler."""

    ref: ResourceRef
    value: Mapping[str, object]
    facts: AuthorizationFacts = field(default_factory=AuthorizationFacts)


ResourceResolver = Callable[[str], Awaitable[Mapping[str, object] | AuthorizedResource | None]]


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
    policy_version: str = POLICY_VERSION
    evidence_reference: str | None = None
    correlation_id: str | None = None
    event: Mapping[str, object] | None = None


def requires_durable_evidence(
    actor: Actor,
    resource: ResourceRef,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
) -> bool:
    """Classify allows whose effects must wait for durable evidence."""
    owner_self = (
        purpose
        in {
            AuthorizationPurpose.SELF_SERVICE,
            AuthorizationPurpose.NOTIFICATION_SELF_SERVICE,
        }
        and actor.user_id in {resource.student_id, resource.owner_id}
        and actor.role in {CanonicalRole.STUDENT, CanonicalRole.TEACHER}
    )
    if owner_self and action not in {
        AuthorizationAction.EXPORT,
        AuthorizationAction.EXTERNAL_SEND,
        AuthorizationAction.MANAGE_PRIVILEGE,
    }:
        return False
    return True


async def record_authorization_decision(
    *,
    actor: Actor,
    resource: ResourceRef,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
    decision: PolicyDecision,
    correlation_id: str,
    audit_sink: AuthorizationAuditSink,
    decision_kind: str = "policy",
) -> PolicyDecision:
    """Persist required evidence before the decision can reach a handler."""
    canonical_id = normalize_correlation_id(correlation_id)
    if decision.allowed and not requires_durable_evidence(actor, resource, action, purpose):
        return decision
    try:
        result = audit_sink.persist_authorization_decision(
            correlation_id=canonical_id,
            actor_id=actor.user_id,
            actor_role=actor.role.value,
            policy_version=decision.policy_version,
            resource_type=resource.resource_type.value,
            resource_id=resource.resource_id,
            student_id=resource.student_id,
            owner_id=resource.owner_id,
            scope_discriminator="|".join(
                value for value in (resource.question_id, resource.session_id) if value
            ),
            action=action.value,
            purpose=purpose.value,
            result="allowed" if decision.allowed else decision.result_code.value,
            decision_kind=decision_kind,
            evidence_reference=decision.evidence_reference,
        )
        if isawaitable(result):
            result = await result
        if not decision.allowed:
            aggregate = audit_sink.aggregate_authorization_probe(
                record=result,
                actor_id=actor.user_id,
                resource_type=resource.resource_type.value,
                action=action.value,
                purpose=purpose.value,
                result=decision.result_code.value,
                policy_version=decision.policy_version,
            )
            if isawaitable(aggregate):
                await aggregate
    except Exception as exc:
        if decision.allowed:
            raise SecurityDecisionError(
                SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
                canonical_id,
                internal_detail=type(exc).__name__,
            ) from exc
        # Evidence degradation must never turn a denial into an allow or oracle.
    return PolicyDecision(
        decision.allowed,
        decision.result_code,
        decision.policy_version,
        decision.evidence_reference,
        canonical_id,
        decision.event,
    )


class AuthorizationFactRepository(Protocol):
    async def facts_for(
        self,
        actor: Actor,
        resource: ResourceRef,
        action: AuthorizationAction,
        purpose: AuthorizationPurpose,
        resource_value: Mapping[str, object],
    ) -> AuthorizationFacts: ...


class CurrentAuthorizationFactRepository:
    """Fresh local fact loader; it intentionally keeps no cross-request cache."""

    async def facts_for(
        self,
        actor: Actor,
        resource: ResourceRef,
        action: AuthorizationAction,
        purpose: AuthorizationPurpose,
        resource_value: Mapping[str, object],
    ) -> AuthorizationFacts:
        if actor.role is CanonicalRole.PARENT:
            from stoa.db.repositories import user_repo

            return AuthorizationFacts(
                parent=ParentAuthorizationFacts(
                    forward=user_repo.get_parent_student_binding(
                        actor.user_id, resource.student_id
                    ),
                    reverse=user_repo.get_student_parent_binding(
                        resource.student_id, actor.user_id
                    ),
                    parent_account=user_repo.get_user(actor.user_id),
                    student_account=user_repo.get_user(resource.student_id),
                )
            )
        if actor.role is CanonicalRole.TEACHER:
            from stoa.db.repositories import question_repo, user_repo

            question = resource_value if resource.resource_type is ResourceType.QUESTION else None
            if resource.resource_type is ResourceType.CONVERSATION and resource.question_id:
                question = question_repo.get_question(resource.question_id)
            if resource.resource_type in {
                ResourceType.TEACHER_HELP_REQUEST,
                ResourceType.AI_TEACHER_DRAFT,
            }:
                question = (
                    question_repo.get_question(resource.question_id)
                    if resource.question_id
                    else resource_value
                )
            session_id = str(resource.session_id or (question or {}).get("session_id") or "")
            return AuthorizationFacts(
                teacher=TeacherAuthorizationFacts(
                    question=question,
                    session=question_repo.get_teacher_session(session_id),
                    assignment=question_repo.get_teacher_assignment(
                        actor.user_id, resource.student_id
                    ),
                    teacher_account=user_repo.get_user(actor.user_id),
                    student_account=user_repo.get_user(resource.student_id),
                )
            )
        return AuthorizationFacts()


class AuthorizationPolicy:
    """Deterministic Actor + ResourceRef + Action + Purpose decision pipeline."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    def evaluate(
        self,
        actor: Actor,
        authorized_resource: AuthorizedResource,
        action: AuthorizationAction,
        purpose: AuthorizationPurpose,
        *,
        correlation_id: str | None = None,
    ) -> PolicyDecision:
        action = AuthorizationAction(action)
        purpose = AuthorizationPurpose(purpose)
        resource = authorized_resource.ref
        now = self._clock()
        allowed = False
        evidence: str | None = None

        if actor.can_authorize:
            if (
                purpose is AuthorizationPurpose.NOTIFICATION_SELF_SERVICE
                and resource.resource_type
                in {
                    ResourceType.NOTIFICATION_COLLECTION,
                    ResourceType.NOTIFICATION_EVENT,
                    ResourceType.NOTIFICATION_PREFERENCE,
                    ResourceType.NOTIFICATION_DIGEST,
                    ResourceType.NOTIFICATION_PUSH_TOKEN,
                }
                and resource.owner_id == actor.user_id
            ):
                allowed = True
            elif (
                purpose is AuthorizationPurpose.SELF_SERVICE
                and resource.resource_type is ResourceType.TEACHER_PORTAL
                and resource.owner_id == actor.user_id
                and actor.role in {CanonicalRole.TEACHER, CanonicalRole.ADMIN}
            ):
                allowed = True
            elif purpose in {
                AuthorizationPurpose.TEACHER_DISPATCH,
                AuthorizationPurpose.AI_TEACHER_TOOLS,
            }:
                capability = {
                    AuthorizationPurpose.TEACHER_DISPATCH: "teacher_dispatch_operator",
                    AuthorizationPurpose.AI_TEACHER_TOOLS: "ai_teacher_tools_operator",
                }[purpose]
                allowed = bool(
                    _matching_grant(
                        actor,
                        capability,
                        resource,
                        action,
                        purpose,
                        allow_global=True,
                    )
                )
            elif actor.role is CanonicalRole.STUDENT:
                allowed = (
                    actor.user_id == resource.student_id
                    and purpose is AuthorizationPurpose.SELF_SERVICE
                )
            elif actor.role is CanonicalRole.PARENT and authorized_resource.facts.parent:
                allowed = (
                    purpose is AuthorizationPurpose.PARENT_OVERSIGHT
                    and authorized_resource.facts.parent.matches(actor.user_id, resource.student_id)
                )
            elif actor.role is CanonicalRole.TEACHER and authorized_resource.facts.teacher:
                allowed = authorized_resource.facts.teacher.permits(
                    actor.user_id, resource, action, purpose, now
                )
            elif actor.role is CanonicalRole.ADMIN:
                allowed, evidence = self._admin_permits(
                    actor, authorized_resource, action, purpose, now
                )

        result = SecurityErrorCode.ACTION_NOT_ALLOWED
        if not allowed and not _relationship_known_to_actor(actor, authorized_resource):
            result = SecurityErrorCode.RESOURCE_NOT_FOUND
        if allowed:
            result = SecurityErrorCode.ACTION_NOT_ALLOWED
        event = project_security_event(
            SecurityEvent(
                actor_id=actor.user_id,
                canonical_role=actor.role.value,
                resource_type=resource.resource_type.value,
                action=action.value,
                purpose=purpose.value,
                policy_version=POLICY_VERSION,
                result_code="allowed" if allowed else result.value,
                correlation_id=correlation_id or "authorization",
                evidence_reference=evidence,
            )
        )
        return PolicyDecision(allowed, result, POLICY_VERSION, evidence, correlation_id, event)

    def _admin_permits(
        self,
        actor: Actor,
        resource: AuthorizedResource,
        action: AuthorizationAction,
        purpose: AuthorizationPurpose,
        now: datetime,
    ) -> tuple[bool, str | None]:
        ref = resource.ref
        if purpose is AuthorizationPurpose.INCIDENT_BREAK_GLASS:
            evidence = resource.facts.break_glass
            forbidden = {
                AuthorizationAction.CREATE,
                AuthorizationAction.UPDATE,
                AuthorizationAction.DELETE,
                AuthorizationAction.RESPOND,
                AuthorizationAction.ASSIGN,
                AuthorizationAction.CLAIM,
                AuthorizationAction.RESOLVE,
                AuthorizationAction.EXPORT,
                AuthorizationAction.EXTERNAL_SEND,
                AuthorizationAction.MANAGE_PRIVILEGE,
                AuthorizationAction.CURRICULUM_MUTATION,
            }
            grant = _matching_grant(actor, "student_data_break_glass", ref, action, purpose)
            return bool(action not in forbidden and evidence and evidence.valid(now) and grant), (
                evidence.incident_id if evidence and evidence.valid(now) else None
            )
        capability = {
            AuthorizationPurpose.SUPPORT: "student_support_lookup"
            if ref.safe_support_metadata
            else "student_content_review",
            AuthorizationPurpose.SAFETY_REVIEW: "student_safety_review",
            AuthorizationPurpose.LEARNING_ASSIGNMENT: "learning_assignment_manager",
            AuthorizationPurpose.ASSIGNMENT_AUTOMATION_PREVIEW: "assignment_automation_preview",
            AuthorizationPurpose.ASSIGNMENT_AUTOMATION_EXECUTE: "assignment_automation_execute",
        }.get(purpose)
        if not capability:
            return False, None
        if capability == "student_support_lookup" and action not in {
            AuthorizationAction.READ,
            AuthorizationAction.LOOKUP,
        }:
            return False, None
        grant = _matching_grant(actor, capability, ref, action, purpose)
        return bool(grant), f"grant:{grant.version}" if grant else None


def operator_capability_decision(
    actor: Actor,
    *,
    capability: str,
    resource: ResourceRef,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
) -> PolicyDecision:
    """Return a structured exact-capability decision for operator routes."""
    operator_role = actor.role is CanonicalRole.ADMIN or (
        actor.role is CanonicalRole.TEACHER
        and (capability.startswith("curriculum_") or capability == "migration_operator")
    )
    if not actor.can_authorize or not operator_role:
        return PolicyDecision(False, SecurityErrorCode.ACTION_NOT_ALLOWED)
    if purpose is AuthorizationPurpose.INCIDENT_BREAK_GLASS:
        return PolicyDecision(False, SecurityErrorCode.ACTION_NOT_ALLOWED)
    allowed = bool(
        _matching_grant(
            actor,
            capability,
            resource,
            action,
            purpose,
            allow_global=True,
        )
    )
    return PolicyDecision(allowed, SecurityErrorCode.ACTION_NOT_ALLOWED)


def operator_capability_permits(
    actor: Actor,
    *,
    capability: str,
    resource: ResourceRef,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
) -> bool:
    """Compatibility projection; production callers record the structured decision."""
    return operator_capability_decision(
        actor,
        capability=capability,
        resource=resource,
        action=action,
        purpose=purpose,
    ).allowed


async def authorize_and_resolve(
    *,
    actor: Actor,
    resource_id: str,
    spec: AuthorizationSpec,
    fact_repository: AuthorizationFactRepository,
    audit_sink: AuthorizationAuditSink,
    correlation_id: str,
    policy: AuthorizationPolicy | None = None,
) -> AuthorizedResource:
    """Load once, load current facts once, decide, and return that exact object."""
    try:
        loaded = await spec.resolver(resource_id)
        if loaded is None:
            missing = ResourceRef(spec.resource_type, resource_id, resource_id)
            decision = PolicyDecision(
                False, SecurityErrorCode.RESOURCE_NOT_FOUND, correlation_id=correlation_id
            )
            await record_authorization_decision(
                actor=actor,
                resource=missing,
                action=spec.action,
                purpose=spec.purpose,
                decision=decision,
                correlation_id=correlation_id,
                audit_sink=audit_sink,
                decision_kind="resolver",
            )
            raise SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND, correlation_id)
        if isinstance(loaded, AuthorizedResource):
            resolved = loaded
        else:
            student_id = str(loaded.get("student_id") or loaded.get("user_id") or "")
            resolved = AuthorizedResource(
                ResourceRef(spec.resource_type, resource_id, student_id), loaded
            )
        facts = fact_repository.facts_for(
            actor, resolved.ref, spec.action, spec.purpose, resolved.value
        )
        if isawaitable(facts):
            facts = await facts
        resolved = AuthorizedResource(resolved.ref, resolved.value, facts)
        decision = (policy or AuthorizationPolicy()).evaluate(
            actor, resolved, spec.action, spec.purpose, correlation_id=correlation_id
        )
        decision = await record_authorization_decision(
            actor=actor,
            resource=resolved.ref,
            action=spec.action,
            purpose=spec.purpose,
            decision=decision,
            correlation_id=correlation_id,
            audit_sink=audit_sink,
        )
        if not decision.allowed:
            raise SecurityDecisionError(decision.result_code, correlation_id)
        return resolved
    except SecurityDecisionError:
        raise
    except Exception as exc:
        raise SecurityDecisionError(
            SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
            correlation_id,
            internal_detail=type(exc).__name__,
        ) from exc


def _active_account(
    account: Mapping[str, object] | None, user_id: str, role: CanonicalRole
) -> bool:
    return bool(
        account
        and account.get("user_id") == user_id
        and account.get("role") == role.value
        and (account.get("account_status") or account.get("status")) == "active"
    )


def _relationship_known_to_actor(actor: Actor, resource: AuthorizedResource) -> bool:
    """Separate existence hiding from a known formal relationship or scoped role."""
    if resource.ref.relationship_known:
        return True
    if actor.role is CanonicalRole.STUDENT:
        return actor.user_id == resource.ref.student_id
    if actor.role is CanonicalRole.ADMIN:
        return True
    if actor.role is CanonicalRole.PARENT and resource.facts.parent:
        rows = (resource.facts.parent.forward, resource.facts.parent.reverse)
        return any(
            row
            and row.get("parent_id") == actor.user_id
            and row.get("student_id") == resource.ref.student_id
            for row in rows
        )
    if actor.role is CanonicalRole.TEACHER and resource.facts.teacher:
        facts = resource.facts.teacher
        question = facts.question or {}
        assignment = facts.assignment or {}
        return bool(
            question.get("teacher_id") == actor.user_id
            or question.get("dispatched_teacher_id") == actor.user_id
            or (
                assignment.get("teacher_id") == actor.user_id
                and assignment.get("student_id") == resource.ref.student_id
            )
        )
    return False


def _expired(value: object, now: datetime) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed <= now
    except (TypeError, ValueError):
        return True


def _scope_matches(
    scope: str,
    resource: ResourceRef,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
    *,
    allow_global: bool,
) -> bool:
    exact = {
        f"resource:{resource.resource_type.value}:{resource.resource_id}",
        f"student:{resource.student_id}",
        (
            f"resource:{resource.resource_type.value}:{resource.resource_id}:"
            f"action:{action.value}:purpose:{purpose.value}"
        ),
    }
    return scope in exact or (allow_global and scope == "global")


def _string_set(value: object) -> set[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return set()
    return {str(item) for item in value}


def _matching_grant(
    actor: Actor,
    capability: str,
    resource: ResourceRef,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
    *,
    allow_global: bool = False,
):
    return next(
        (
            grant
            for grant in actor.current_grants
            if grant.capability == capability
            and _scope_matches(
                grant.scope,
                resource,
                action,
                purpose,
                allow_global=allow_global,
            )
        ),
        None,
    )


def evaluate_matrix_case(
    *, family: str, actor: str, relation: str, action: str, purpose: str
) -> PolicyDecision:
    """Executable reference matrix used by the Wave 0/3 regression contract."""
    role = CanonicalRole(actor)
    actor_id = f"{actor}-1"
    student_id = actor_id if role is CanonicalRole.STUDENT else "student-1"
    resource_type = {
        "students": ResourceType.STUDENT,
        "questions": ResourceType.QUESTION,
        "conversations": ResourceType.CONVERSATION,
        "practice": ResourceType.PRACTICE,
        "adaptive": ResourceType.ADAPTIVE_PROFILE,
        "reports": ResourceType.REPORT,
        "teacher_help": ResourceType.QUESTION,
        "admin_support": ResourceType.STUDENT,
    }[family]
    ref = ResourceRef(
        resource_type,
        "question-1" if resource_type is ResourceType.QUESTION else f"{family}-1",
        student_id,
        relationship_known=relation not in {"unrelated", "one_sided_binding"},
        safe_support_metadata=family == "admin_support",
    )
    parent = _matrix_parent_facts(relation, student_id)
    teacher = _matrix_teacher_facts(relation, student_id, ref.resource_id)
    grants = ()
    if relation == "scoped_grant":
        from stoa.security.identity import CapabilityGrant

        grants = (CapabilityGrant("student_support_lookup", f"student:{student_id}", 1),)
    principal = Actor(
        actor_id,
        "https://identity.test",
        f"{actor}-subject",
        role,
        __import__("stoa.security.identity", fromlist=["AccountStatus"]).AccountStatus.ACTIVE,
        role.value,
        grants,
    )
    return AuthorizationPolicy(clock=lambda: datetime(2026, 7, 15, tzinfo=UTC)).evaluate(
        principal,
        AuthorizedResource(
            ref, {"resource_id": ref.resource_id}, AuthorizationFacts(parent, teacher)
        ),
        AuthorizationAction(action),
        AuthorizationPurpose(purpose),
    )


def _matrix_parent_facts(relation: str, student_id: str) -> ParentAuthorizationFacts | None:
    if relation not in {"active_bidirectional_binding", "revoked_binding", "one_sided_binding"}:
        return None
    status = "revoked" if relation == "revoked_binding" else "active"
    row = {
        "parent_id": "parent-1",
        "student_id": student_id,
        "relationship": "child",
        "version": 1,
        "status": status,
    }
    return ParentAuthorizationFacts(
        row,
        None if relation == "one_sided_binding" else dict(row),
        {"user_id": "parent-1", "role": "parent", "account_status": "active"},
        {"user_id": student_id, "role": "student", "account_status": "active"},
    )


def _matrix_teacher_facts(
    relation: str, student_id: str, resource_id: str
) -> TeacherAuthorizationFacts | None:
    if relation not in {"assigned", "dispatched", "unassigned", "other_dispatch"}:
        return None
    teacher_id = "teacher-1" if relation in {"assigned", "dispatched"} else "teacher-2"
    question = {
        "question_id": resource_id,
        "student_id": student_id,
        "teacher_id": teacher_id,
        "dispatched_teacher_id": teacher_id,
        "dispatch_status": "accepted",
        "status": "teacher_active",
    }
    return TeacherAuthorizationFacts(
        question=question,
        teacher_account={"user_id": "teacher-1", "role": "teacher", "account_status": "active"},
        student_account={"user_id": student_id, "role": "student", "account_status": "active"},
    )


def evaluate_hidden_resource_case(_resource_id: str) -> SecurityHttpResponse:
    """Return the same safe response for existing-but-hidden and absent identifiers."""
    return safe_error_response(SecurityErrorCode.RESOURCE_NOT_FOUND, "hidden-resource")


def project_support_lookup(
    *,
    account: Mapping[str, object] | None,
    binding: Mapping[str, object] | None,
    denial_code: SecurityErrorCode | str | None,
    correlation_id: str,
    support_id: str,
) -> dict[str, object]:
    """Return bounded support metadata without copying student learning data."""
    code = denial_code.value if isinstance(denial_code, SecurityErrorCode) else denial_code
    return {
        "accountState": str(
            (account or {}).get("account_status") or (account or {}).get("status") or "unknown"
        ),
        "bindingState": str((binding or {}).get("status") or "unknown"),
        "denialCode": str(code or "none"),
        "correlationId": correlation_id,
        "supportId": support_id,
    }
