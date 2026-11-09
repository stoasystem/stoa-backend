"""Declarative route authorization: one entry, one loader per resource (#316, #348).

A route declares, once, what it acts on::

    Depends(authorized(ResourceType.STUDENT, AuthorizationAction.READ,
                       path("child_id"), {CanonicalRole.PARENT: PARENT_OVERSIGHT}))

and this module does the rest: it takes the id by the declared name from the
request (never by matching a function parameter's name, which is how #104
authorized the wrong object), loads the resource through the loader registered
for its type, reads the current facts, asks the policy and records the
decision. The dependency carries the declaration, which is what the route
inventory reads (`route_inventory._classify_route`).

Where the id comes from is one of four sources:

- ``path(name)``: a parameter of the route path. The route inventory gate
  refuses a route whose path does not have it.
- ``query(name, student_defaults_to_self=...)``: a query parameter. Only when
  the caller is a student and the parameter is absent may it stand for the
  student's own id, and only when the declaration says so.
- ``SELF``: the Actor's own account. It is loaded through the type's loader
  when one is registered (so a store outage refuses before the handler runs),
  otherwise the Actor's own record is authorized as is; either way the handler
  receives the `Actor`.
- ``operator(capability=...)``: an exact operator grant; the handler receives
  the `Actor`.

A route that loads first and decides after (a list, a batch, an id in a body)
calls `authorize_loaded` instead and declares itself with `loaded_declaration`.
A route whose check lives in a service declares `service_enforced("<entry>")`,
so the inventory says where the check is instead of claiming one here.

An id that cannot be taken where the declaration says is a program error: it
is logged, recorded and answered with a 500, and never falls back to the
Actor's own id.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from fastapi import Depends, Path, Query, Request

from stoa.db.repositories import adaptive_learning_repo, practice_repo, user_repo
from stoa.db.repositories.security_audit_repo import AuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationFactRepository,
    AuthorizationPolicy,
    AuthorizationPurpose,
    AuthorizationSpec,
    AuthorizedResource,
    PolicyDecision,
    ResourceRef,
    ResourceType,
    authorize_and_resolve,
    operator_capability_decision,
    record_authorization_decision,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor, CanonicalRole
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.route_authorization import (
    valid_loaded_curriculum_answer,
    get_authorization_fact_repository,
    get_authorization_policy,
)

logger = logging.getLogger(__name__)

PurposeMap = Mapping[CanonicalRole, AuthorizationPurpose]
ResourceLoader = Callable[[str, Actor], Awaitable[AuthorizedResource | None]]
Dependency = TypeVar("Dependency", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PathSource:
    name: str


@dataclass(frozen=True, slots=True)
class QuerySource:
    name: str
    student_defaults_to_self: bool = False


@dataclass(frozen=True, slots=True)
class SelfSource:
    pass


@dataclass(frozen=True, slots=True)
class OperatorSource:
    capability: str


IdSource = PathSource | QuerySource | SelfSource | OperatorSource


def path(name: str) -> PathSource:
    """The id is the route path parameter called ``name``."""
    if not name.isidentifier():
        raise ValueError(f"path identifier {name!r} is not a parameter name")
    return PathSource(name)


def query(name: str, *, student_defaults_to_self: bool = False) -> QuerySource:
    """The id is the query parameter called ``name``.

    With ``student_defaults_to_self`` a student who leaves it out means their
    own id; anyone else who leaves it out is refused. Without it the parameter
    is required.
    """
    if not name.isidentifier():
        raise ValueError(f"query identifier {name!r} is not a parameter name")
    return QuerySource(name, student_defaults_to_self)


#: The id is the Actor's own; the handler receives the Actor.
SELF = SelfSource()


def operator(*, capability: str) -> OperatorSource:
    """An exact operator grant on the global operator resource; hands over the Actor."""
    if not capability.strip():
        raise ValueError("operator capability is required")
    return OperatorSource(capability)


# ---------------------------------------------------------------------------
# Declarations (what the route inventory reads)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuthorizationDeclaration:
    """What a route acts on, as the dependency that enforces it carries it."""

    resource_type: ResourceType
    action: AuthorizationAction
    purposes: tuple[tuple[CanonicalRole, AuthorizationPurpose], ...]
    source: IdSource | None
    service_entry: str | None = None

    @property
    def capability(self) -> str | None:
        return self.source.capability if isinstance(self.source, OperatorSource) else None

    def purpose_for(self, role: CanonicalRole) -> AuthorizationPurpose | None:
        return dict(self.purposes).get(role)


def _declaration(
    resource_type: ResourceType,
    action: AuthorizationAction,
    source: IdSource | None,
    purposes: PurposeMap,
    service_entry: str | None = None,
) -> AuthorizationDeclaration:
    if not purposes:
        raise ValueError("an authorization declaration names at least one role's purpose")
    return AuthorizationDeclaration(
        ResourceType(resource_type),
        AuthorizationAction(action),
        tuple((CanonicalRole(role), AuthorizationPurpose(p)) for role, p in purposes.items()),
        source,
        service_entry,
    )


def declaration_of(call: object) -> AuthorizationDeclaration | None:
    declaration = getattr(call, "authorization_declaration", None)
    return declaration if isinstance(declaration, AuthorizationDeclaration) else None


# ---------------------------------------------------------------------------
# Resource loaders, registered once per resource type
# ---------------------------------------------------------------------------

_LOADERS: dict[tuple[ResourceType, str | None], ResourceLoader] = {}


def register_resource_loader(
    resource_type: ResourceType, loader: ResourceLoader, *, kind: str | None = None
) -> None:
    """Register how one resource type is loaded by id.

    ``kind`` separates the ids one resource type is addressed by: a practice
    item is a lesson, a challenge or an attempt, and an adaptive profile is
    reached by its student or by one of its assignments.
    """
    key = (ResourceType(resource_type), kind)
    if key in _LOADERS:
        raise ValueError(f"a loader for {key} is already registered")
    _LOADERS[key] = loader


def unregister_resource_loader(resource_type: ResourceType, *, kind: str | None = None) -> None:
    _LOADERS.pop((ResourceType(resource_type), kind), None)


def resource_loader(resource_type: ResourceType, kind: str | None = None) -> ResourceLoader:
    try:
        return _LOADERS[(ResourceType(resource_type), kind)]
    except KeyError:
        raise LookupError(
            f"no resource loader is registered for {resource_type.value} (kind {kind!r})"
        ) from None


def _student_account_loader(resource_type: ResourceType) -> ResourceLoader:
    async def load(student_id: str, _actor: Actor) -> AuthorizedResource | None:
        profile = user_repo.get_user(student_id)
        if not profile or profile.get("role") not in {None, "student"}:
            return None
        return AuthorizedResource(ResourceRef(resource_type, student_id, student_id), profile)

    return load


async def _load_assignment(assignment_id: str, _actor: Actor) -> AuthorizedResource | None:
    item = adaptive_learning_repo.get_assignment(assignment_id)
    if not item:
        return None
    return AuthorizedResource(
        ResourceRef(
            ResourceType.ADAPTIVE_PROFILE, assignment_id, str(item.get("student_id") or "")
        ),
        item,
    )


def _practice_item_loader(read: Callable[[str, Actor], Mapping[str, object] | None]):
    async def load(item_id: str, actor: Actor) -> AuthorizedResource | None:
        item = read(item_id, actor)
        if not item:
            return None
        # A practice item is shared catalogue (or, for an attempt, read from
        # the Actor's own partition): what is authorized is the Actor's own
        # practice with it.
        return AuthorizedResource(ResourceRef(ResourceType.PRACTICE, item_id, actor.user_id), item)

    return load


async def _load_curriculum_answer(challenge_id: str, _actor: Actor) -> AuthorizedResource | None:
    item = practice_repo.get_challenge(challenge_id)
    if not valid_loaded_curriculum_answer(item, challenge_id):
        return None
    assert item is not None
    return AuthorizedResource(
        ResourceRef(
            ResourceType.CURRICULUM_ANSWER,
            challenge_id,
            challenge_id,
            course_id=item["course_id"],
            class_id=item["class_id"],
            lesson_id=item.get("lesson_id"),
            subject_id=item.get("subject_id"),
            grade_level=item.get("grade_level"),
        ),
        item,
    )


#: The student fact family: one student's account, typed as the facts read.
#: Practice is not in it: a student's own practice (``SELF``) has never loaded
#: the account, and no route reads another student's practice by student id.
STUDENT_FACT_FAMILY = (
    ResourceType.STUDENT,
    ResourceType.ADAPTIVE_PROFILE,
    ResourceType.REPORT,
)
ASSIGNMENT = "assignment"
LESSON = "lesson"
CHALLENGE = "challenge"
ATTEMPT = "attempt"

for _family_type in STUDENT_FACT_FAMILY:
    register_resource_loader(_family_type, _student_account_loader(_family_type))
register_resource_loader(ResourceType.ADAPTIVE_PROFILE, _load_assignment, kind=ASSIGNMENT)
register_resource_loader(
    ResourceType.PRACTICE,
    _practice_item_loader(lambda item_id, _actor: practice_repo.get_lesson(item_id)),
    kind=LESSON,
)
register_resource_loader(
    ResourceType.PRACTICE,
    _practice_item_loader(lambda item_id, _actor: practice_repo.get_challenge(item_id)),
    kind=CHALLENGE,
)
register_resource_loader(
    ResourceType.PRACTICE,
    _practice_item_loader(lambda item_id, actor: practice_repo.get_attempt(actor.user_id, item_id)),
    kind=ATTEMPT,
)
register_resource_loader(ResourceType.CURRICULUM_ANSWER, _load_curriculum_answer)


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    """The four request-scoped collaborators every decision uses."""

    facts: AuthorizationFactRepository
    policy: AuthorizationPolicy
    correlation_id: str
    audit_sink: AuthorizationAuditSink


async def get_authorization_context(
    facts: AuthorizationFactRepository = Depends(get_authorization_fact_repository),
    policy: AuthorizationPolicy = Depends(get_authorization_policy),
    correlation_id: str = Depends(get_request_correlation_id),
    audit_sink: AuthorizationAuditSink = Depends(get_authorization_audit_sink),
) -> AuthorizationContext:
    return AuthorizationContext(facts, policy, correlation_id, audit_sink)


class AuthorizationDeclarationError(RuntimeError):
    """A route's declaration does not fit its request: a program error (500)."""


async def _refuse(
    actor: Actor,
    ref: ResourceRef,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
    code: SecurityErrorCode,
    decision_kind: str,
    context: AuthorizationContext,
) -> None:
    await record_authorization_decision(
        actor=actor,
        resource=ref,
        action=action,
        purpose=purpose,
        decision=PolicyDecision(False, code, correlation_id=context.correlation_id),
        correlation_id=context.correlation_id,
        audit_sink=context.audit_sink,
        decision_kind=decision_kind,
    )


async def _purpose_or_refuse(
    actor: Actor,
    declaration: AuthorizationDeclaration,
    ref: ResourceRef,
    context: AuthorizationContext,
) -> AuthorizationPurpose:
    """The purpose the Actor's role acts under; a role the route does not name is refused.

    Used where nothing is hidden by refusing outright: the Actor's own account,
    an operator grant, an object the caller already loaded.
    """
    purpose = declaration.purpose_for(actor.role)
    if purpose is not None:
        return purpose
    await _refuse(
        actor,
        ref,
        declaration.action,
        declaration.purposes[0][1],
        SecurityErrorCode.ACTION_NOT_ALLOWED,
        "role_not_declared",
        context,
    )
    raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED, context.correlation_id)


def _hiding_purpose(
    actor: Actor, declaration: AuthorizationDeclaration
) -> AuthorizationPurpose:
    """The purpose for a resource-keyed decision, for every role.

    A role the route does not name still goes to the policy, under the first
    declared purpose, and is refused there: whether such a resource exists is
    hidden from it exactly as from a role the route does name.
    """
    return declaration.purpose_for(actor.role) or declaration.purposes[0][1]


class _FactsReached:
    """The context's fact repository, noting whether the facts were read.

    Once they are, the policy decides and `record_authorization_decision`
    records that decision itself; a failure after that point is the audit
    sink's, and must not add a second, contradicting record.
    """

    def __init__(self, facts: AuthorizationFactRepository) -> None:
        self._facts = facts
        self.reached = False

    async def facts_for(self, *args: Any) -> Any:
        facts = await self._facts.facts_for(*args)
        self.reached = True
        return facts


async def _decide(
    actor: Actor,
    resource_id: str,
    resource_type: ResourceType,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
    load: Callable[[str], Awaitable[AuthorizedResource | None]],
    context: AuthorizationContext,
) -> AuthorizedResource:
    facts = _FactsReached(context.facts)
    try:
        return await authorize_and_resolve(
            actor=actor,
            resource_id=resource_id,
            spec=AuthorizationSpec(resource_type, action, purpose, load),
            fact_repository=facts,
            correlation_id=context.correlation_id,
            audit_sink=context.audit_sink,
            policy=context.policy,
        )
    except SecurityDecisionError as error:
        if (
            error.code is SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE
            and not facts.reached
        ):
            # The loader or the fact store failed before any decision: record
            # that the request was refused for it. A refusal that cannot be
            # recorded stays a refusal (`record_authorization_decision`).
            await _refuse(
                actor,
                ResourceRef(resource_type, resource_id, resource_id),
                action,
                purpose,
                error.code,
                "unavailable",
                context,
            )
        raise


async def authorize_loaded(
    actor: Actor,
    ref: ResourceRef,
    value: Mapping[str, object] | None,
    action: AuthorizationAction,
    purposes: PurposeMap,
    context: AuthorizationContext,
) -> AuthorizedResource:
    """Decide on an object the caller has already loaded (a list, a batch, a body id).

    ``value`` None means the caller found nothing under ``ref``: refused as
    not found, and recorded, like a loader that finds nothing.
    """
    declaration = _declaration(ref.resource_type, action, None, purposes)
    purpose = await _purpose_or_refuse(actor, declaration, ref, context)

    async def load(_resource_id: str) -> AuthorizedResource | None:
        return None if value is None else AuthorizedResource(ref, value)

    return await _decide(
        actor, ref.resource_id, ref.resource_type, action, purpose, load, context
    )


def loaded_declaration(
    resource_type: ResourceType,
    action: AuthorizationAction,
    purposes: PurposeMap,
) -> Callable[[Dependency], Dependency]:
    """Declare a dependency that decides through `authorize_loaded`.

    The id such a dependency decides on is not one of the four sources (a body
    field, a list's items), so it declares the resource, action and purposes
    for the route inventory here, next to the code that enforces them.
    """
    declaration = _declaration(resource_type, action, None, purposes)

    def decorate(dependency: Dependency) -> Dependency:
        setattr(dependency, "authorization_declaration", declaration)
        return dependency

    return decorate


# ---------------------------------------------------------------------------
# The entry
# ---------------------------------------------------------------------------


def _declared_parameter(source: IdSource) -> inspect.Parameter | None:
    """Expose the declared id to FastAPI, so OpenAPI and the inventory see it.

    The value FastAPI parses is not what is authorized: the entry reads the id
    from the request by the declared name.
    """
    if isinstance(source, PathSource):
        return inspect.Parameter(
            source.name,
            inspect.Parameter.KEYWORD_ONLY,
            default=Path(alias=source.name),
            annotation=str,
        )
    if isinstance(source, QuerySource):
        return inspect.Parameter(
            source.name,
            inspect.Parameter.KEYWORD_ONLY,
            default=Query(
                default=None if source.student_defaults_to_self else ...,
                alias=source.name,
            ),
            annotation=str | None if source.student_defaults_to_self else str,
        )
    return None


def _requested_id(request: Request, source: PathSource | QuerySource) -> str | None:
    params = request.path_params if isinstance(source, PathSource) else request.query_params
    value = params.get(source.name)
    return str(value) if value not in {None, ""} else None


def _absent(source: PathSource | QuerySource) -> str:
    """The id an absent identifier is recorded under (a ref needs one)."""
    return f"absent:{source.name}"


def authorized(
    resource_type: ResourceType,
    action: AuthorizationAction,
    source: IdSource,
    purposes: PurposeMap,
    *,
    kind: str | None = None,
):
    """The FastAPI dependency that authorizes one declared resource.

    It returns the loaded `AuthorizedResource` for ``path``/``query`` sources
    and the `Actor` for ``SELF`` and ``operator``.
    """
    declaration = _declaration(resource_type, action, source, purposes)
    if isinstance(source, PathSource | QuerySource) or kind is not None:
        load_by_id: ResourceLoader | None = resource_loader(declaration.resource_type, kind)
    elif isinstance(source, SelfSource):
        load_by_id = _LOADERS.get((declaration.resource_type, None))
    else:
        load_by_id = None

    async def dependency(
        request: Request,
        actor: Actor,
        context: AuthorizationContext,
        **_parsed: object,
    ) -> AuthorizedResource | Actor:
        if isinstance(source, OperatorSource):
            return await _authorize_operator(actor, declaration, source, context)
        if isinstance(source, SelfSource):
            return await _authorize_self(actor, declaration, load_by_id, context)
        assert load_by_id is not None
        resource_id = _requested_id(request, source)
        if resource_id is None and isinstance(source, PathSource):
            logger.error(
                "declared path identifier %s is absent from %s", source.name, request.url.path
            )
            absent = _absent(source)
            await _refuse(
                actor,
                ResourceRef(declaration.resource_type, absent, absent),
                declaration.action,
                _hiding_purpose(actor, declaration),
                SecurityErrorCode.ACTION_NOT_ALLOWED,
                "declaration_error",
                context,
            )
            raise AuthorizationDeclarationError(
                f"declared path identifier {source.name} is absent from the request"
            )
        if resource_id is None and isinstance(source, QuerySource):
            if source.student_defaults_to_self and actor.role is CanonicalRole.STUDENT:
                resource_id = actor.user_id
            else:
                absent = _absent(source)
                await _refuse(
                    actor,
                    ResourceRef(declaration.resource_type, absent, absent),
                    declaration.action,
                    _hiding_purpose(actor, declaration),
                    SecurityErrorCode.RESOURCE_NOT_FOUND,
                    "missing_identifier",
                    context,
                )
                raise SecurityDecisionError(
                    SecurityErrorCode.RESOURCE_NOT_FOUND, context.correlation_id
                )
        assert resource_id is not None
        purpose = _hiding_purpose(actor, declaration)

        async def load(requested: str) -> AuthorizedResource | None:
            return await load_by_id(requested, actor)

        return await _decide(
            actor,
            resource_id,
            declaration.resource_type,
            declaration.action,
            purpose,
            load,
            context,
        )

    parameters = [
        inspect.Parameter("request", inspect.Parameter.KEYWORD_ONLY, annotation=Request),
        inspect.Parameter(
            "actor", inspect.Parameter.KEYWORD_ONLY, default=Depends(get_actor), annotation=Actor
        ),
        inspect.Parameter(
            "context",
            inspect.Parameter.KEYWORD_ONLY,
            default=Depends(get_authorization_context),
            annotation=AuthorizationContext,
        ),
    ]
    declared_parameter = _declared_parameter(source)
    if declared_parameter is not None:
        parameters.append(declared_parameter)
    return_annotation = (
        Actor if isinstance(source, SelfSource | OperatorSource) else AuthorizedResource
    )
    setattr(
        dependency,
        "__signature__",
        inspect.Signature(parameters, return_annotation=return_annotation),
    )
    setattr(dependency, "authorization_declaration", declaration)
    return dependency


async def _authorize_self(
    actor: Actor,
    declaration: AuthorizationDeclaration,
    load_by_id: ResourceLoader | None,
    context: AuthorizationContext,
) -> Actor:
    """Authorize the Actor on their own account of this resource type."""
    ref = ResourceRef(
        declaration.resource_type, actor.user_id, actor.user_id, owner_id=actor.user_id
    )
    purpose = await _purpose_or_refuse(actor, declaration, ref, context)
    if load_by_id is not None:

        async def load(requested: str) -> AuthorizedResource | None:
            return await load_by_id(requested, actor)

        await _decide(
            actor,
            actor.user_id,
            declaration.resource_type,
            declaration.action,
            purpose,
            load,
            context,
        )
        return actor
    resource = AuthorizedResource(ref, {"student_id": actor.user_id, "owner_id": actor.user_id})
    decision = context.policy.evaluate(
        actor, resource, declaration.action, purpose, correlation_id=context.correlation_id
    )
    decision = await record_authorization_decision(
        actor=actor,
        resource=ref,
        action=declaration.action,
        purpose=purpose,
        decision=decision,
        correlation_id=context.correlation_id,
        audit_sink=context.audit_sink,
        decision_kind="direct_policy",
    )
    if not decision.allowed:
        raise SecurityDecisionError(decision.result_code, context.correlation_id)
    return actor


async def _authorize_operator(
    actor: Actor,
    declaration: AuthorizationDeclaration,
    source: OperatorSource,
    context: AuthorizationContext,
) -> Actor:
    """Require the exact operator grant, against the global operator resource."""
    ref = ResourceRef(
        declaration.resource_type, "global", actor.user_id, relationship_known=True
    )
    purpose = await _purpose_or_refuse(actor, declaration, ref, context)
    decision = operator_capability_decision(
        actor,
        capability=source.capability,
        resource=ref,
        action=declaration.action,
        purpose=purpose,
    )
    decision = await record_authorization_decision(
        actor=actor,
        resource=ref,
        action=declaration.action,
        purpose=purpose,
        decision=decision,
        correlation_id=context.correlation_id,
        audit_sink=context.audit_sink,
        decision_kind="operator_capability",
    )
    if not decision.allowed:
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED, context.correlation_id)
    return actor


def service_enforced(
    entry: str,
    resource_type: ResourceType,
    action: AuthorizationAction,
    purposes: PurposeMap,
):
    """A route whose check is in a service: hand over the Actor, say where the check is.

    The inventory classifies such a route ``service-enforced`` and names
    ``entry``, the service function that authorizes, instead of claiming the
    dependency does.
    """
    if not entry.strip():
        raise ValueError("service_enforced names the service entry that authorizes")
    declaration = _declaration(resource_type, action, None, purposes, entry.strip())

    async def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        return actor

    setattr(dependency, "authorization_declaration", declaration)
    return dependency
