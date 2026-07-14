"""Executable FastAPI dependencies for Actor-owned student resources."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from inspect import isawaitable

from fastapi import Depends, HTTPException, Query

from stoa.db.repositories import notification_repo, question_repo, user_repo
from stoa.deps import get_actor
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPolicy,
    AuthorizationPurpose,
    AuthorizationSpec,
    AuthorizedResource,
    CurrentAuthorizationFactRepository,
    ResourceRef,
    ResourceType,
    authorize_and_resolve,
)
from stoa.security.errors import SecurityDecisionError
from stoa.security.identity import Actor, CanonicalRole


PurposeMap = Mapping[CanonicalRole, AuthorizationPurpose]


def safe_public_dependency(resource_type: ResourceType):
    """Declare an authenticated route as non-personalized public/catalog data."""

    async def resolve(resource_id: str):
        return {"student_id": resource_id}

    async def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        return actor

    dependency.safe_public = True  # type: ignore[attr-defined]
    dependency.authorization_specs = (  # type: ignore[attr-defined]
        _metadata_spec(
            resource_type,
            AuthorizationAction.READ,
            AuthorizationPurpose.SELF_SERVICE,
            resolve,
        ),
    )
    return dependency


def get_authorization_fact_repository() -> CurrentAuthorizationFactRepository:
    return CurrentAuthorizationFactRepository()


def _raise_http(error: SecurityDecisionError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.public_body()) from error


def _purpose_for(actor: Actor, purposes: PurposeMap) -> AuthorizationPurpose:
    purpose = purposes.get(actor.role)
    if purpose is None:
        from stoa.security.errors import SecurityErrorCode

        _raise_http(SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED))
    return purpose


def _metadata_spec(
    resource_type: ResourceType,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
    resolver: Callable,
) -> AuthorizationSpec:
    return AuthorizationSpec(resource_type, action, purpose, resolver)


def authorized_student_dependency(
    *,
    action: AuthorizationAction,
    purposes: PurposeMap,
    self_route: bool = False,
    query_alias: str | None = None,
):
    async def resolve(student_id: str):
        profile = user_repo.get_user(student_id)
        if not profile or profile.get("role") not in {None, "student"}:
            return None
        return AuthorizedResource(
            ResourceRef(ResourceType.STUDENT, student_id, student_id),
            profile,
        )

    async def authorize_target(
        student_id: str | None,
        actor: Actor,
        facts: CurrentAuthorizationFactRepository,
    ) -> AuthorizedResource:
        target_id = (
            actor.user_id
            if self_route or (student_id is None and actor.role is CanonicalRole.STUDENT)
            else str(student_id or "")
        )
        spec = AuthorizationSpec(
            ResourceType.STUDENT, action, _purpose_for(actor, purposes), resolve
        )
        try:
            return await authorize_and_resolve(
                actor=actor,
                resource_id=target_id,
                spec=spec,
                fact_repository=facts,
            )
        except SecurityDecisionError as error:
            _raise_http(error)

    async def path_dependency(
        student_id: str | None = None,
        actor: Actor = Depends(get_actor),
        facts: CurrentAuthorizationFactRepository = Depends(
            get_authorization_fact_repository
        ),
    ) -> AuthorizedResource:
        return await authorize_target(student_id, actor, facts)

    async def query_dependency(
        student_id: str | None = Query(default=None, alias=query_alias),
        actor: Actor = Depends(get_actor),
        facts: CurrentAuthorizationFactRepository = Depends(
            get_authorization_fact_repository
        ),
    ) -> AuthorizedResource:
        return await authorize_target(student_id, actor, facts)

    dependency = query_dependency if query_alias else path_dependency

    dependency.authorization_specs = tuple(  # type: ignore[attr-defined]
        _metadata_spec(ResourceType.STUDENT, action, purpose, resolve)
        for purpose in purposes.values()
    )
    return dependency


def authorized_student_resource_dependency(
    *,
    resource_type: ResourceType,
    action: AuthorizationAction,
    purposes: PurposeMap,
    self_route: bool = False,
):
    """Resolve a canonical student account but authorize a typed student fact family."""

    async def resolve(student_id: str):
        profile = user_repo.get_user(student_id)
        if not profile or profile.get("role") not in {None, "student"}:
            return None
        return AuthorizedResource(
            ResourceRef(resource_type, student_id, student_id),
            profile,
        )

    async def dependency(
        student_id: str | None = None,
        actor: Actor = Depends(get_actor),
        facts: CurrentAuthorizationFactRepository = Depends(
            get_authorization_fact_repository
        ),
    ) -> AuthorizedResource:
        target_id = (
            actor.user_id
            if self_route or (student_id is None and actor.role is CanonicalRole.STUDENT)
            else str(student_id or "")
        )
        spec = AuthorizationSpec(
            resource_type, action, _purpose_for(actor, purposes), resolve
        )
        try:
            return await authorize_and_resolve(
                actor=actor,
                resource_id=target_id,
                spec=spec,
                fact_repository=facts,
            )
        except SecurityDecisionError as error:
            _raise_http(error)

    dependency.authorization_specs = tuple(  # type: ignore[attr-defined]
        _metadata_spec(resource_type, action, purpose, resolve)
        for purpose in purposes.values()
    )
    return dependency


def authorized_question_dependency(
    *, action: AuthorizationAction, purposes: PurposeMap
):
    async def resolve(question_id: str):
        item = question_repo.get_question(question_id)
        if not item:
            return None
        student_id = str(item.get("student_id") or "")
        return AuthorizedResource(
            ResourceRef(
                ResourceType.QUESTION,
                question_id,
                student_id,
                question_id=question_id,
                session_id=str(item.get("session_id") or "") or None,
            ),
            item,
        )

    async def dependency(
        question_id: str,
        actor: Actor = Depends(get_actor),
        facts: CurrentAuthorizationFactRepository = Depends(
            get_authorization_fact_repository
        ),
    ) -> AuthorizedResource:
        spec = AuthorizationSpec(
            ResourceType.QUESTION, action, _purpose_for(actor, purposes), resolve
        )
        try:
            return await authorize_and_resolve(
                actor=actor,
                resource_id=question_id,
                spec=spec,
                fact_repository=facts,
            )
        except SecurityDecisionError as error:
            _raise_http(error)

    dependency.authorization_specs = tuple(  # type: ignore[attr-defined]
        _metadata_spec(ResourceType.QUESTION, action, purpose, resolve)
        for purpose in purposes.values()
    )
    return dependency


def student_create_actor_dependency(resource_type: ResourceType):
    return student_actor_dependency(resource_type, AuthorizationAction.CREATE)


def student_actor_dependency(
    resource_type: ResourceType, action: AuthorizationAction
):
    async def resolve(resource_id: str):
        return {"student_id": resource_id}

    async def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        spec = AuthorizationSpec(
            resource_type,
            action,
            AuthorizationPurpose.SELF_SERVICE,
            resolve,
        )
        resource = AuthorizedResource(
            ResourceRef(resource_type, actor.user_id, actor.user_id),
            {"student_id": actor.user_id},
        )
        decision = AuthorizationPolicy().evaluate(
            actor, resource, spec.action, spec.purpose
        )
        if not decision.allowed:
            from stoa.security.errors import SecurityErrorCode

            _raise_http(SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED))
        return actor

    dependency.authorization_specs = (  # type: ignore[attr-defined]
        _metadata_spec(
            resource_type,
            action,
            AuthorizationPurpose.SELF_SERVICE,
            resolve,
        ),
    )
    return dependency


def notification_self_dependency(
    resource_type: ResourceType,
    action: AuthorizationAction,
):
    """Authorize a notification collection/preference/digest/token create to Actor self."""

    async def resolve(resource_id: str):
        return AuthorizedResource(
            ResourceRef(resource_type, resource_id, resource_id, owner_id=resource_id),
            {"owner_id": resource_id},
        )

    async def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        try:
            await authorize_and_resolve(
                actor=actor,
                resource_id=actor.user_id,
                spec=AuthorizationSpec(
                    resource_type,
                    action,
                    AuthorizationPurpose.NOTIFICATION_SELF_SERVICE,
                    resolve,
                ),
                fact_repository=get_authorization_fact_repository(),
            )
            return actor
        except SecurityDecisionError as error:
            _raise_http(error)

    dependency.authorization_specs = (  # type: ignore[attr-defined]
        _metadata_spec(
            resource_type,
            action,
            AuthorizationPurpose.NOTIFICATION_SELF_SERVICE,
            resolve,
        ),
    )
    return dependency


def authorized_notification_event_dependency(action: AuthorizationAction):
    """Load one event, bind it to its canonical recipient, then authorize it."""

    async def resolve(event_id: str):
        item = notification_repo.get_event(event_id)
        if not item or not item.get("recipient_id"):
            return None
        owner_id = str(item["recipient_id"])
        return AuthorizedResource(
            ResourceRef(
                ResourceType.NOTIFICATION_EVENT,
                event_id,
                owner_id,
                owner_id=owner_id,
            ),
            item,
        )

    async def dependency(
        event_id: str,
        actor: Actor = Depends(get_actor),
        facts: CurrentAuthorizationFactRepository = Depends(get_authorization_fact_repository),
    ) -> AuthorizedResource:
        try:
            return await authorize_and_resolve(
                actor=actor,
                resource_id=event_id,
                spec=AuthorizationSpec(
                    ResourceType.NOTIFICATION_EVENT,
                    action,
                    AuthorizationPurpose.NOTIFICATION_SELF_SERVICE,
                    resolve,
                ),
                fact_repository=facts,
            )
        except SecurityDecisionError as error:
            _raise_http(error)

    dependency.authorization_specs = (  # type: ignore[attr-defined]
        _metadata_spec(
            ResourceType.NOTIFICATION_EVENT,
            action,
            AuthorizationPurpose.NOTIFICATION_SELF_SERVICE,
            resolve,
        ),
    )
    return dependency


def authorized_notification_push_token_dependency(action: AuthorizationAction):
    """Resolve a token reference under Actor ownership before token mutation."""

    async def dependency(
        token_reference: str,
        actor: Actor = Depends(get_actor),
        facts: CurrentAuthorizationFactRepository = Depends(get_authorization_fact_repository),
    ) -> AuthorizedResource:
        async def resolve(resource_id: str):
            item = notification_repo.get_push_token(actor.user_id, resource_id)
            if not item:
                return None
            owner_id = str(item.get("user_id") or "")
            return AuthorizedResource(
                ResourceRef(
                    ResourceType.NOTIFICATION_PUSH_TOKEN,
                    resource_id,
                    owner_id,
                    owner_id=owner_id,
                ),
                item,
            )

        try:
            return await authorize_and_resolve(
                actor=actor,
                resource_id=token_reference,
                spec=AuthorizationSpec(
                    ResourceType.NOTIFICATION_PUSH_TOKEN,
                    action,
                    AuthorizationPurpose.NOTIFICATION_SELF_SERVICE,
                    resolve,
                ),
                fact_repository=facts,
            )
        except SecurityDecisionError as error:
            _raise_http(error)

    async def metadata_resolver(resource_id: str):
        return {"resource_id": resource_id}

    dependency.authorization_specs = (  # type: ignore[attr-defined]
        _metadata_spec(
            ResourceType.NOTIFICATION_PUSH_TOKEN,
            action,
            AuthorizationPurpose.NOTIFICATION_SELF_SERVICE,
            metadata_resolver,
        ),
    )
    return dependency


def teacher_portal_self_dependency(
    action: AuthorizationAction = AuthorizationAction.READ,
):
    """Authorize the active teacher/admin Actor against their own portal record."""

    async def resolve(resource_id: str):
        return {"owner_id": resource_id}

    async def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        spec = AuthorizationSpec(
            ResourceType.TEACHER_PORTAL,
            action,
            AuthorizationPurpose.SELF_SERVICE,
            resolve,
        )
        resource = AuthorizedResource(
            ResourceRef(
                ResourceType.TEACHER_PORTAL,
                actor.user_id,
                actor.user_id,
                owner_id=actor.user_id,
                relationship_known=True,
            ),
            {"owner_id": actor.user_id},
        )
        decision = AuthorizationPolicy().evaluate(
            actor, resource, spec.action, spec.purpose
        )
        if not decision.allowed:
            from stoa.security.errors import SecurityErrorCode

            _raise_http(SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED))
        return actor

    dependency.authorization_specs = (  # type: ignore[attr-defined]
        _metadata_spec(
            ResourceType.TEACHER_PORTAL,
            action,
            AuthorizationPurpose.SELF_SERVICE,
            resolve,
        ),
    )
    return dependency


def teacher_capability_dependency(
    *,
    capability_purpose: AuthorizationPurpose,
    action: AuthorizationAction,
):
    """Require the exact current local grant for a broader teacher operation."""

    async def resolve(resource_id: str):
        return {"owner_id": resource_id}

    async def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        resource = AuthorizedResource(
            ResourceRef(
                ResourceType.TEACHER_PORTAL,
                actor.user_id,
                actor.user_id,
                owner_id=actor.user_id,
                relationship_known=True,
            ),
            {"owner_id": actor.user_id},
        )
        decision = AuthorizationPolicy().evaluate(
            actor, resource, action, capability_purpose
        )
        if not decision.allowed:
            from stoa.security.errors import SecurityErrorCode

            _raise_http(SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED))
        return actor

    dependency.required_capability = {  # type: ignore[attr-defined]
        AuthorizationPurpose.TEACHER_DISPATCH: "teacher_dispatch_operator",
        AuthorizationPurpose.AI_TEACHER_TOOLS: "ai_teacher_tools_operator",
    }[capability_purpose]
    dependency.authorization_specs = (  # type: ignore[attr-defined]
        _metadata_spec(
            ResourceType.TEACHER_PORTAL,
            action,
            capability_purpose,
            resolve,
        ),
    )
    return dependency


async def authorize_conversation_resource(
    *,
    conversation_id: str,
    actor: Actor,
    facts: CurrentAuthorizationFactRepository,
    action: AuthorizationAction,
    purposes: PurposeMap,
    resolver: Callable[[str], Mapping[str, object] | None | Awaitable[Mapping[str, object] | None]],
) -> AuthorizedResource:
    async def resolve(resource_id: str):
        item = resolver(resource_id)
        if isawaitable(item):
            item = await item
        if not item:
            return None
        student_id = str(item.get("student_id") or "")
        return AuthorizedResource(
            ResourceRef(
                ResourceType.CONVERSATION,
                resource_id,
                student_id,
                question_id=str(item.get("question_id") or "") or None,
                session_id=str(item.get("session_id") or "") or None,
            ),
            item,
        )

    spec = AuthorizationSpec(
        ResourceType.CONVERSATION, action, _purpose_for(actor, purposes), resolve
    )
    try:
        return await authorize_and_resolve(
            actor=actor,
            resource_id=conversation_id,
            spec=spec,
            fact_repository=facts,
        )
    except SecurityDecisionError as error:
        _raise_http(error)


def authorized_conversation_dependency(
    *,
    action: AuthorizationAction,
    purposes: PurposeMap,
    resolver: Callable[[str], Mapping[str, object] | None],
):
    async def dependency(
        conv_id: str,
        actor: Actor = Depends(get_actor),
        facts: CurrentAuthorizationFactRepository = Depends(
            get_authorization_fact_repository
        ),
    ) -> AuthorizedResource:
        return await authorize_conversation_resource(
            conversation_id=conv_id,
            actor=actor,
            facts=facts,
            action=action,
            purposes=purposes,
            resolver=resolver,
        )

    async def metadata_resolver(resource_id: str):
        return resolver(resource_id)

    dependency.authorization_specs = tuple(  # type: ignore[attr-defined]
        _metadata_spec(ResourceType.CONVERSATION, action, purpose, metadata_resolver)
        for purpose in purposes.values()
    )
    return dependency


async def authorize_teacher_loaded_resource(
    *,
    actor: Actor,
    facts: CurrentAuthorizationFactRepository,
    loaded: Mapping[str, object],
    resource_type: ResourceType,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose = AuthorizationPurpose.TEACHER_HELP,
) -> AuthorizedResource:
    """Authorize one already-resolved teacher task object without reloading it."""
    student_id = str(loaded.get("student_id") or "")
    id_field = {
        ResourceType.QUESTION: "question_id",
        ResourceType.TEACHER_HELP_REQUEST: "conversation_id",
        ResourceType.AI_TEACHER_DRAFT: "draft_id",
    }.get(resource_type, "resource_id")
    canonical_id = str(loaded.get(id_field) or "")
    resolved = AuthorizedResource(
        ResourceRef(
            resource_type,
            canonical_id,
            student_id,
            question_id=str(loaded.get("question_id") or "") or None,
            session_id=str(loaded.get("session_id") or "") or None,
        ),
        loaded,
    )

    async def resolve(_resource_id: str):
        return resolved

    return await authorize_and_resolve(
        actor=actor,
        resource_id=canonical_id,
        spec=AuthorizationSpec(resource_type, action, purpose, resolve),
        fact_repository=facts,
    )


def authorized_teacher_resource_dependency(
    *,
    resource_type: ResourceType,
    action: AuthorizationAction,
    resolver: Callable[[str], Mapping[str, object] | None],
):
    """Resolve an indirect teacher request/draft identifier before authorization."""

    async def dependency(
        request_id: str,
        actor: Actor = Depends(get_actor),
        facts: CurrentAuthorizationFactRepository = Depends(
            get_authorization_fact_repository
        ),
    ) -> AuthorizedResource:
        try:
            loaded = resolver(request_id)
            if not loaded:
                from stoa.security.errors import SecurityErrorCode

                raise SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND)
            return await authorize_teacher_loaded_resource(
                actor=actor,
                facts=facts,
                loaded=loaded,
                resource_type=resource_type,
                action=action,
            )
        except SecurityDecisionError as error:
            _raise_http(error)
        except Exception as exc:
            from stoa.security.errors import SecurityErrorCode

            _raise_http(
                SecurityDecisionError(
                    SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
                    internal_detail=type(exc).__name__,
                )
            )

    async def metadata_resolver(resource_id: str):
        return resolver(resource_id)

    dependency.authorization_specs = (  # type: ignore[attr-defined]
        _metadata_spec(
            resource_type,
            action,
            AuthorizationPurpose.TEACHER_HELP,
            metadata_resolver,
        ),
    )
    return dependency


def teacher_tool_purpose(actor: Actor) -> AuthorizationPurpose:
    """Select broader AI-tool purpose only when the Actor presents that local grant."""
    if any(
        grant.capability == "ai_teacher_tools_operator"
        for grant in actor.current_grants
    ):
        return AuthorizationPurpose.AI_TEACHER_TOOLS
    return AuthorizationPurpose.TEACHER_HELP


def authorized_ai_teacher_draft_dependency(
    *,
    action: AuthorizationAction,
    resolver: Callable[[str], Mapping[str, object] | None],
):
    """Resolve a draft ID to its student/question owner before lifecycle effects."""

    async def dependency(
        draft_id: str,
        actor: Actor = Depends(get_actor),
        facts: CurrentAuthorizationFactRepository = Depends(
            get_authorization_fact_repository
        ),
    ) -> AuthorizedResource:
        try:
            loaded = resolver(draft_id)
            if not loaded:
                from stoa.security.errors import SecurityErrorCode

                raise SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND)
            return await authorize_teacher_loaded_resource(
                actor=actor,
                facts=facts,
                loaded=loaded,
                resource_type=ResourceType.AI_TEACHER_DRAFT,
                action=action,
                purpose=teacher_tool_purpose(actor),
            )
        except SecurityDecisionError as error:
            _raise_http(error)
        except Exception as exc:
            from stoa.security.errors import SecurityErrorCode

            _raise_http(
                SecurityDecisionError(
                    SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
                    internal_detail=type(exc).__name__,
                )
            )

    async def metadata_resolver(resource_id: str):
        return resolver(resource_id)

    dependency.authorization_specs = tuple(  # type: ignore[attr-defined]
        _metadata_spec(ResourceType.AI_TEACHER_DRAFT, action, purpose, metadata_resolver)
        for purpose in (
            AuthorizationPurpose.TEACHER_HELP,
            AuthorizationPurpose.AI_TEACHER_TOOLS,
        )
    )
    return dependency


STUDENT_SELF = {CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE}
STUDENT_CONTENT_READ = {
    CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE,
    CanonicalRole.PARENT: AuthorizationPurpose.PARENT_OVERSIGHT,
    CanonicalRole.TEACHER: AuthorizationPurpose.LEARNING_ASSIGNMENT,
    CanonicalRole.ADMIN: AuthorizationPurpose.SUPPORT,
}
QUESTION_CONTENT_READ = {
    CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE,
    CanonicalRole.PARENT: AuthorizationPurpose.PARENT_OVERSIGHT,
    CanonicalRole.TEACHER: AuthorizationPurpose.TEACHER_HELP,
    CanonicalRole.ADMIN: AuthorizationPurpose.SUPPORT,
}
CONVERSATION_CONTENT_READ = {
    CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE,
    CanonicalRole.PARENT: AuthorizationPurpose.PARENT_OVERSIGHT,
    CanonicalRole.TEACHER: AuthorizationPurpose.TEACHER_HELP,
    CanonicalRole.ADMIN: AuthorizationPurpose.SUPPORT,
}
