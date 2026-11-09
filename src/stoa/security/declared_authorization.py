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
- ``operator(capability=..., target=...)``: an exact operator grant on the
  global operator resource, or on the object a ``path(...)`` target names (a
  grant may be scoped to that one object); the handler receives the `Actor`.

A role's purpose may be chosen by a grant the Actor holds (`by_grant`): the
AI teacher tools are read under their own purpose only by a teacher who
holds that grant.

A route that loads first and decides after (a list, a batch, an id in a body)
calls `authorize_loaded` instead (or `authorize_id`, for an id in a body) and
declares itself with `loaded_declaration`.
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

from stoa.db.repositories import (
    adaptive_learning_repo,
    attachment_repo,
    notification_repo,
    practice_repo,
    user_repo,
)
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


@dataclass(frozen=True, slots=True)
class GrantedPurpose:
    """A purpose chosen by a grant: ``granted`` for an Actor holding ``capability``."""

    capability: str
    granted: AuthorizationPurpose
    otherwise: AuthorizationPurpose

    def choose(self, actor: Actor) -> AuthorizationPurpose:
        held = any(grant.capability == self.capability for grant in actor.current_grants)
        return self.granted if held else self.otherwise


def by_grant(
    capability: str,
    granted: AuthorizationPurpose,
    *,
    otherwise: AuthorizationPurpose,
) -> GrantedPurpose:
    """The purpose ``granted`` when the Actor holds ``capability``, else ``otherwise``.

    Which one the policy is asked under is the Actor's; the route inventory
    lists both, since either may be asked.
    """
    if not capability.strip():
        raise ValueError("by_grant names the capability that chooses the purpose")
    return GrantedPurpose(
        capability.strip(), AuthorizationPurpose(granted), AuthorizationPurpose(otherwise)
    )


DeclaredPurpose = AuthorizationPurpose | GrantedPurpose
PurposeMap = Mapping[CanonicalRole, DeclaredPurpose]
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
    target: PathSource | None = None


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


def operator(*, capability: str, target: PathSource | None = None) -> OperatorSource:
    """An exact operator grant; hands over the Actor.

    Without ``target`` the grant is checked on the global operator resource
    (a queue, a list). With ``target=path(name)`` it is checked on the object
    that path parameter names, so a grant scoped to that one object opens it.
    """
    if not capability.strip():
        raise ValueError("operator capability is required")
    return OperatorSource(capability, target)


# ---------------------------------------------------------------------------
# Declarations (what the route inventory reads)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuthorizationDeclaration:
    """What a route acts on, as the dependency that enforces it carries it."""

    resource_type: ResourceType
    action: AuthorizationAction
    purposes: tuple[tuple[CanonicalRole, DeclaredPurpose], ...]
    source: IdSource | None
    service_entry: str | None = None

    @property
    def capability(self) -> str | None:
        return self.source.capability if isinstance(self.source, OperatorSource) else None

    def purpose_for(self, actor: Actor) -> AuthorizationPurpose | None:
        declared = dict(self.purposes).get(actor.role)
        return _chosen(declared, actor) if declared is not None else None

    def first_purpose(self, actor: Actor) -> AuthorizationPurpose:
        return _chosen(self.purposes[0][1], actor)

    def listed_purposes(self) -> tuple[AuthorizationPurpose, ...]:
        """Every purpose a request may be asked under, for the route inventory."""
        listed: list[AuthorizationPurpose] = []
        for _role, declared in self.purposes:
            if isinstance(declared, GrantedPurpose):
                listed.extend((declared.granted, declared.otherwise))
            else:
                listed.append(declared)
        return tuple(dict.fromkeys(listed))


def _chosen(declared: DeclaredPurpose, actor: Actor) -> AuthorizationPurpose:
    return declared.choose(actor) if isinstance(declared, GrantedPurpose) else declared


def _declared_purpose(value: DeclaredPurpose) -> DeclaredPurpose:
    return value if isinstance(value, GrantedPurpose) else AuthorizationPurpose(value)


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
        tuple((CanonicalRole(role), _declared_purpose(p)) for role, p in purposes.items()),
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
#: Types whose kind-free loader loads by a user id: ``SELF`` loads the Actor's own.
_SELF_LOADED: set[ResourceType] = set()


def register_resource_loader(
    resource_type: ResourceType,
    loader: ResourceLoader,
    *,
    kind: str | None = None,
    loads_self: bool = False,
) -> None:
    """Register how one resource type is loaded by id.

    ``kind`` separates the ids one resource type is addressed by: a practice
    item is a lesson, a challenge or an attempt, and an adaptive profile is
    reached by its student or by one of its assignments.

    ``loads_self`` says the loader's id is a user id, so ``SELF`` loads the
    Actor's own record through it. A conversation, a help request or a
    notification event is loaded by its own id, never by the Actor's.
    """
    key = (ResourceType(resource_type), kind)
    if key in _LOADERS:
        raise ValueError(f"a loader for {key} is already registered")
    if loads_self and kind is not None:
        raise ValueError("only a type's kind-free loader loads the Actor's own record")
    _LOADERS[key] = loader
    if loads_self:
        _SELF_LOADED.add(key[0])


def unregister_resource_loader(resource_type: ResourceType, *, kind: str | None = None) -> None:
    _LOADERS.pop((ResourceType(resource_type), kind), None)
    if kind is None:
        _SELF_LOADED.discard(ResourceType(resource_type))


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
    register_resource_loader(
        _family_type, _student_account_loader(_family_type), loads_self=True
    )
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


def _conversation_resource(
    conversation_id: str, item: Mapping[str, object] | None
) -> AuthorizedResource | None:
    if not item:
        return None
    return AuthorizedResource(
        ResourceRef(
            ResourceType.CONVERSATION,
            conversation_id,
            str(item.get("student_id") or ""),
            question_id=str(item.get("question_id") or "") or None,
        ),
        item,
    )


async def _load_conversation(conversation_id: str, _actor: Actor) -> AuthorizedResource | None:
    from stoa.services import learning_session

    return _conversation_resource(conversation_id, learning_session.read(conversation_id))


async def _load_live_conversation(
    conversation_id: str, _actor: Actor
) -> AuthorizedResource | None:
    """A conversation that is not deleted: what a new upload code may go into."""
    from stoa.services import learning_session

    item = learning_session.read(conversation_id)
    if item is None or item.get("status") == "deleted":
        return None
    return _conversation_resource(conversation_id, item)


async def _load_question(question_id: str, _actor: Actor) -> AuthorizedResource | None:
    """A question id is a help request's id (#189), loaded once, as stored (#234)."""
    from stoa.services import help_requests

    item = help_requests.get(question_id)
    if not item:
        return None
    return AuthorizedResource(
        ResourceRef(
            ResourceType.QUESTION,
            question_id,
            str(item.get("student_id") or ""),
            question_id=question_id,
        ),
        item,
    )


def teacher_task_resource(
    resource_type: ResourceType, loaded: Mapping[str, object]
) -> AuthorizedResource:
    """A help request, question or draft a teacher works on, as the policy reads it.

    A question id is a help request's id since #189, and a request's id is
    its conversation's; a draft names its request as ``question_id``.
    """
    id_field = {
        ResourceType.QUESTION: "conversation_id",
        ResourceType.TEACHER_HELP_REQUEST: "conversation_id",
        ResourceType.AI_TEACHER_DRAFT: "draft_id",
    }.get(resource_type, "resource_id")
    return AuthorizedResource(
        ResourceRef(
            resource_type,
            str(loaded.get(id_field) or ""),
            str(loaded.get("student_id") or ""),
            question_id=str(
                loaded.get("question_id")
                or loaded.get("escalation_request_id")
                or loaded.get("conversation_id")
                or ""
            )
            or None,
        ),
        loaded,
    )


async def _load_help_request(request_id: str, _actor: Actor) -> AuthorizedResource | None:
    from stoa.services import help_requests

    item = help_requests.get(request_id)
    return teacher_task_resource(ResourceType.TEACHER_HELP_REQUEST, item) if item else None


async def _load_ai_teacher_draft(draft_id: str, _actor: Actor) -> AuthorizedResource | None:
    from stoa.services import ai_teacher_tools_service

    item = ai_teacher_tools_service.ai_teacher_tools_repo.get_draft(draft_id)
    return teacher_task_resource(ResourceType.AI_TEACHER_DRAFT, item) if item else None


def _owned(
    resource_type: ResourceType, resource_id: str, item: Mapping[str, object], owner_id: str
) -> AuthorizedResource:
    return AuthorizedResource(
        ResourceRef(resource_type, resource_id, owner_id, owner_id=owner_id), item
    )


async def _load_notification_event(event_id: str, _actor: Actor) -> AuthorizedResource | None:
    """An event, bound to its canonical recipient."""
    item = notification_repo.get_event(event_id)
    if not item or not item.get("recipient_id"):
        return None
    return _owned(ResourceType.NOTIFICATION_EVENT, event_id, item, str(item["recipient_id"]))


async def _load_push_token(token_reference: str, actor: Actor) -> AuthorizedResource | None:
    """A push token is looked up under the Actor's own account, by its reference."""
    item = notification_repo.get_push_token(actor.user_id, token_reference)
    if not item:
        return None
    return _owned(
        ResourceType.NOTIFICATION_PUSH_TOKEN,
        token_reference,
        item,
        str(item.get("user_id") or ""),
    )


def _attachment_loader(*, for_reading: bool) -> ResourceLoader:
    async def load(attachment_id: str, _actor: Actor) -> AuthorizedResource | None:
        from stoa.services.attachment_service import is_live_attachment

        item = attachment_repo.get_attachment(attachment_id)
        if not is_live_attachment(item, for_reading=for_reading):
            return None
        assert item is not None
        return _owned(ResourceType.ATTACHMENT, attachment_id, item, str(item["owner_id"]))

    return load


#: A conversation that is not deleted.
LIVE = "live"
#: A push token, by its reference under the Actor's own account.
TOKEN = "token"
#: An attachment that may be deleted: a row missing the fields its bytes are
#: read by can still go (`attachment_service.is_live_attachment`).
DELETABLE = "deletable"

register_resource_loader(ResourceType.CONVERSATION, _load_conversation)
register_resource_loader(ResourceType.CONVERSATION, _load_live_conversation, kind=LIVE)
register_resource_loader(ResourceType.QUESTION, _load_question)
register_resource_loader(ResourceType.TEACHER_HELP_REQUEST, _load_help_request)
register_resource_loader(ResourceType.AI_TEACHER_DRAFT, _load_ai_teacher_draft)
register_resource_loader(ResourceType.NOTIFICATION_EVENT, _load_notification_event)
register_resource_loader(ResourceType.NOTIFICATION_PUSH_TOKEN, _load_push_token, kind=TOKEN)
register_resource_loader(ResourceType.ATTACHMENT, _attachment_loader(for_reading=True))
register_resource_loader(
    ResourceType.ATTACHMENT, _attachment_loader(for_reading=False), kind=DELETABLE
)


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
    purpose = declaration.purpose_for(actor)
    if purpose is not None:
        return purpose
    await _refuse(
        actor,
        ref,
        declaration.action,
        declaration.first_purpose(actor),
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
    return declaration.purpose_for(actor) or declaration.first_purpose(actor)


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
    if isinstance(source, OperatorSource):
        return _declared_parameter(source.target) if source.target is not None else None
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


async def _absent_path(
    request: Request,
    actor: Actor,
    declaration: AuthorizationDeclaration,
    source: PathSource,
    purpose: AuthorizationPurpose,
    context: AuthorizationContext,
) -> AuthorizationDeclarationError:
    """A declared path value missing from the request: logged, recorded, a 500."""
    logger.error("declared path identifier %s is absent from %s", source.name, request.url.path)
    absent = _absent(source)
    await _refuse(
        actor,
        ResourceRef(declaration.resource_type, absent, absent),
        declaration.action,
        purpose,
        SecurityErrorCode.ACTION_NOT_ALLOWED,
        "declaration_error",
        context,
    )
    return AuthorizationDeclarationError(
        f"declared path identifier {source.name} is absent from the request"
    )


async def _decide_by_id(
    actor: Actor,
    declaration: AuthorizationDeclaration,
    load_by_id: ResourceLoader,
    resource_id: str,
    context: AuthorizationContext,
) -> AuthorizedResource:
    async def load(requested: str) -> AuthorizedResource | None:
        return await load_by_id(requested, actor)

    return await _decide(
        actor,
        resource_id,
        declaration.resource_type,
        declaration.action,
        _hiding_purpose(actor, declaration),
        load,
        context,
    )


async def authorize_id(
    actor: Actor,
    resource_type: ResourceType,
    resource_id: str,
    action: AuthorizationAction,
    purposes: PurposeMap,
    context: AuthorizationContext,
    *,
    kind: str | None = None,
) -> AuthorizedResource:
    """Authorize an id the request carries elsewhere than its path or query (a body).

    It is loaded through the loader registered for the type and decided
    exactly as a ``path(...)`` id is, a role the purposes do not name
    included. The dependency that calls it declares itself with
    `loaded_declaration`.
    """
    declaration = _declaration(resource_type, action, None, purposes)
    loader = resource_loader(declaration.resource_type, kind)
    return await _decide_by_id(actor, declaration, loader, resource_id, context)


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
    elif isinstance(source, SelfSource) and declaration.resource_type in _SELF_LOADED:
        load_by_id = resource_loader(declaration.resource_type)
    else:
        load_by_id = None

    async def dependency(
        request: Request,
        actor: Actor,
        context: AuthorizationContext,
        **_parsed: object,
    ) -> AuthorizedResource | Actor:
        if isinstance(source, OperatorSource):
            return await _authorize_operator(request, actor, declaration, source, context)
        if isinstance(source, SelfSource):
            return await _authorize_self(actor, declaration, load_by_id, context)
        assert load_by_id is not None
        resource_id = _requested_id(request, source)
        if resource_id is None and isinstance(source, PathSource):
            raise await _absent_path(
                request, actor, declaration, source, _hiding_purpose(actor, declaration), context
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
        return await _decide_by_id(actor, declaration, load_by_id, resource_id, context)

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
    """Authorize the Actor on their own account of this resource type.

    The Actor's own record is known to them, so a refusal is a 403, never a
    404 that pretends their own account might not exist.
    """
    ref = ResourceRef(
        declaration.resource_type,
        actor.user_id,
        actor.user_id,
        owner_id=actor.user_id,
        relationship_known=True,
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
    request: Request,
    actor: Actor,
    declaration: AuthorizationDeclaration,
    source: OperatorSource,
    context: AuthorizationContext,
) -> Actor:
    """Require the exact operator grant, on the global resource or the named target."""
    resource_id = "global"
    if source.target is not None:
        requested = _requested_id(request, source.target)
        if requested is None:
            raise await _absent_path(
                request,
                actor,
                declaration,
                source.target,
                _hiding_purpose(actor, declaration),
                context,
            )
        resource_id = requested
    ref = ResourceRef(
        declaration.resource_type, resource_id, actor.user_id, relationship_known=True
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
