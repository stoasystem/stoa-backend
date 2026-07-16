"""Deterministic authorization inventory derived from registered FastAPI routes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from types import UnionType
from typing import Annotated, Any, Callable, Iterable, Literal, Union, get_args, get_origin

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from pydantic import BaseModel

from stoa.security.admin_authorization import AdminRoutePolicy, AdminTargetProvider
from stoa.security.authorization import AuthorizationSpec, ResourceType


RouteAccess = Literal["public", "authenticated-global"]
IdentifierScope = Literal["command-local", "self-only"]


@dataclass(frozen=True, slots=True)
class ExplicitRouteClassification:
    access: RouteAccess
    reason: str
    allowed_identifiers: tuple[str, ...] = ()
    identifier_scope: IdentifierScope | None = None


@dataclass(frozen=True, slots=True)
class InventorySpec:
    resource_type: str
    action: str
    purpose: str
    capability: str | None = None


@dataclass(frozen=True, slots=True)
class RouteInventoryItem:
    method: str
    path: str
    family: str
    classification: str
    identifiers: tuple[str, ...]
    authorization_specs: tuple[InventorySpec, ...]
    sensitive: bool
    admin_target: dict[str, Any] | None = None

    @property
    def authorization_spec(self) -> InventorySpec | None:
        return self.authorization_specs[0] if self.authorization_specs else None

    def projection(self) -> dict[str, Any]:
        projection = {
            "method": self.method,
            "path": self.path,
            "family": self.family,
            "classification": self.classification,
            "identifiers": list(self.identifiers),
            "authorization": [asdict(spec) for spec in self.authorization_specs],
            "sensitive": self.sensitive,
        }
        if self.admin_target is not None:
            projection["adminTarget"] = self.admin_target
        return projection


@dataclass(frozen=True, slots=True)
class InventoryFailure:
    method: str
    path: str
    reason: str


def explicit_route_classification(
    access: RouteAccess,
    reason: str,
    *,
    allowed_identifiers: Iterable[str] = (),
    identifier_scope: IdentifierScope | None = None,
):
    """Mark an endpoint as deliberately public or authenticated global state."""

    if not reason.strip():
        raise ValueError("route classification reason is required")

    def decorate(endpoint: Callable[..., Any]) -> Callable[..., Any]:
        endpoint.stoa_route_classification = ExplicitRouteClassification(  # type: ignore[attr-defined]
            access,
            reason.strip(),
            tuple(allowed_identifiers),
            identifier_scope,
        )
        return endpoint

    return decorate


def _walk_dependants(root: Dependant) -> Iterable[Dependant]:
    seen: set[int] = set()
    stack = [root]
    while stack:
        dependant = stack.pop()
        if id(dependant) in seen:
            continue
        seen.add(id(dependant))
        yield dependant
        stack.extend(reversed(dependant.dependencies))


def _field_aliases(
    annotation: Any,
    *,
    prefix: str = "",
    model_path: frozenset[type[BaseModel]] = frozenset(),
) -> set[str]:
    """Return dotted schema aliases from every supported annotation shape.

    ``model_path`` is path-local rather than global: it prevents recursive model
    cycles while still allowing the same model to be declared in two branches.
    """

    aliases: set[str] = set()
    origin = get_origin(annotation)
    if origin is Annotated:
        return _field_aliases(get_args(annotation)[0], prefix=prefix, model_path=model_path)
    if origin in {Union, UnionType}:
        for argument in get_args(annotation):
            aliases.update(_field_aliases(argument, prefix=prefix, model_path=model_path))
        return aliases
    if origin is not None:
        for argument in get_args(annotation):
            aliases.update(_field_aliases(argument, prefix=prefix, model_path=model_path))
        return aliases
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in model_path:
            return aliases
        next_path = model_path | {annotation}
        for name, field in annotation.model_fields.items():
            alias = str(field.alias or name)
            path = f"{prefix}.{alias}" if prefix else alias
            aliases.add(path)
            aliases.update(_field_aliases(field.annotation, prefix=path, model_path=next_path))
    return aliases


_EXACT_IDENTIFIERS = {
    "studentid",
    "childid",
    "userid",
    "parentid",
    "teacherid",
    "questionid",
    "conversationid",
    "sessionid",
    "assignmentid",
    "requestid",
    "reportid",
    "deliveryid",
    "jobid",
    "draftid",
    "notificationid",
    "eventid",
    "tokenreference",
    "providertokenreference",
    "pushtoken",
    "deviceid",
    "applicationid",
    "uploadid",
    "attachmentid",
    "attemptid",
    "challengeid",
}


def _canonical_identifier(value: str) -> str | None:
    leaf = value.rsplit(".", 1)[-1]
    normalized = "".join(character.lower() for character in leaf if character.isalnum())
    if normalized in _EXACT_IDENTIFIERS:
        return leaf
    if normalized.endswith("tokenreference") or normalized in {"pushtoken", "deviceid"}:
        return leaf
    return None


def _route_identifiers(route: APIRoute) -> tuple[str, ...]:
    names: set[str] = set()
    for dependant in _walk_dependants(route.dependant):
        for field in (
            *dependant.path_params,
            *dependant.query_params,
            *dependant.body_params,
        ):
            alias = str(field.alias or field.name)
            names.add(alias)
            names.update(_field_aliases(field.field_info.annotation))
    return tuple(sorted(set(filter(None, (_canonical_identifier(name) for name in names)))))


def _route_body_aliases(route: APIRoute) -> tuple[str, ...]:
    aliases: set[str] = set()
    for dependant in _walk_dependants(route.dependant):
        for field in dependant.body_params:
            aliases.update(_field_aliases(field.field_info.annotation))
    return tuple(sorted(aliases))


def _target_projection(provider: AdminTargetProvider | None) -> dict[str, Any] | None:
    if provider is None:
        return None
    return {
        "cardinality": provider.cardinality,
        "bodyParameter": provider.body_parameter,
        "targetPaths": list(provider.target_paths),
        "tupleFields": list(provider.tuple_fields),
        "collectionPath": provider.collection_path,
        "maximum": provider.maximum,
        "required": provider.required,
        "referenceOnly": list(provider.reference_only),
        "resolver": provider.resolver,
    }


def _inventory_spec(
    spec: AuthorizationSpec,
    capability: str | None = None,
) -> InventorySpec:
    return InventorySpec(
        spec.resource_type.value,
        spec.action.value,
        spec.purpose.value,
        capability,
    )


def _admin_inventory_spec(policy: AdminRoutePolicy) -> InventorySpec:
    return InventorySpec(
        policy.resource_type.value,
        policy.action.value,
        policy.purpose.value,
        "|".join(policy.capabilities),
    )


def _family(path: str) -> str:
    parts = path.strip("/").split("/")
    if len(parts) > 1 and parts[0] == "admin" and parts[1] == "reports":
        return "reports"
    return parts[0] or "root"


def _classify_route(route: APIRoute, method: str) -> tuple[str, tuple[InventorySpec, ...]]:
    specs: list[InventorySpec] = []
    admin_policies: list[AdminRoutePolicy] = []
    safe_public = False
    for dependant in _walk_dependants(route.dependant):
        call = dependant.call
        safe_public = safe_public or bool(getattr(call, "safe_public", False))
        capability = getattr(call, "required_capability", None)
        specs.extend(
            _inventory_spec(spec, capability) for spec in getattr(call, "authorization_specs", ())
        )
        classifier = getattr(call, "admin_policy_classifier", None)
        if classifier is not None:
            admin_policies.append(classifier(method, route.path))
    marker = getattr(route.endpoint, "stoa_route_classification", None)
    if marker is not None and not isinstance(marker, ExplicitRouteClassification):
        raise ValueError("invalid explicit route classification")
    if marker is not None and (admin_policies or specs):
        raise ValueError(
            "explicit public/global declaration cannot accompany executable resource authorization"
        )
    if admin_policies:
        if len(admin_policies) != 1:
            raise ValueError("duplicate admin policy classifiers")
        specs.append(_admin_inventory_spec(admin_policies[0]))
        classification = "admin-capability"
    elif specs:
        classification = "safe-public" if safe_public else "authorized"
    else:
        if not isinstance(marker, ExplicitRouteClassification):
            raise ValueError(
                "route has no executable authorization or explicit public/global classification"
            )
        classification = marker.access
    unique = {
        (item.resource_type, item.action, item.purpose, item.capability): item for item in specs
    }
    return classification, tuple(
        sorted(
            unique.values(),
            key=lambda item: (item.resource_type, item.action, item.purpose, item.capability or ""),
        )
    )


_NOTIFICATION_IDS = {
    "notificationid",
    "eventid",
    "tokenreference",
    "providertokenreference",
    "pushtoken",
    "deviceid",
}

_IDENTIFIER_RESOURCE_TYPES: dict[str, frozenset[str]] = {
    "studentid": frozenset(
        {
            ResourceType.STUDENT.value,
            ResourceType.QUESTION.value,
            ResourceType.CONVERSATION.value,
            ResourceType.PRACTICE.value,
            ResourceType.ADAPTIVE_PROFILE.value,
            ResourceType.REPORT.value,
            ResourceType.TEACHER_ASSIGNMENT.value,
            ResourceType.PARENT_BINDING.value,
            ResourceType.TEACHER_HELP_REQUEST.value,
            ResourceType.AI_TEACHER_DRAFT.value,
        }
    ),
    "childid": frozenset({ResourceType.STUDENT.value, ResourceType.PARENT_BINDING.value}),
    "parentid": frozenset({ResourceType.PARENT_BINDING.value}),
    "questionid": frozenset(
        {
            ResourceType.QUESTION.value,
            ResourceType.CONVERSATION.value,
            ResourceType.TEACHER_HELP_REQUEST.value,
            ResourceType.AI_TEACHER_DRAFT.value,
        }
    ),
    "conversationid": frozenset(
        {ResourceType.CONVERSATION.value, ResourceType.TEACHER_HELP_REQUEST.value}
    ),
    "sessionid": frozenset(
        {
            ResourceType.QUESTION.value,
            ResourceType.CONVERSATION.value,
            ResourceType.PRACTICE.value,
            ResourceType.ADAPTIVE_PROFILE.value,
        }
    ),
    "assignmentid": frozenset(
        {ResourceType.TEACHER_ASSIGNMENT.value, ResourceType.ADAPTIVE_PROFILE.value}
    ),
    "requestid": frozenset({ResourceType.TEACHER_HELP_REQUEST.value}),
    "reportid": frozenset({ResourceType.REPORT.value}),
    "draftid": frozenset({ResourceType.AI_TEACHER_DRAFT.value}),
    "notificationid": frozenset({ResourceType.NOTIFICATION_EVENT.value}),
    "eventid": frozenset({ResourceType.NOTIFICATION_EVENT.value}),
    "tokenreference": frozenset({ResourceType.NOTIFICATION_PUSH_TOKEN.value}),
    "providertokenreference": frozenset({ResourceType.NOTIFICATION_PUSH_TOKEN.value}),
    "pushtoken": frozenset({ResourceType.NOTIFICATION_PUSH_TOKEN.value}),
    "deviceid": frozenset({ResourceType.NOTIFICATION_PUSH_TOKEN.value}),
    "applicationid": frozenset({ResourceType.OPERATOR_RESOURCE.value}),
    "uploadid": frozenset({ResourceType.UPLOAD.value}),
    "attachmentid": frozenset({ResourceType.ATTACHMENT.value}),
    "attemptid": frozenset({ResourceType.PRACTICE.value}),
    "challengeid": frozenset(
        {ResourceType.PRACTICE.value, ResourceType.CURRICULUM_ANSWER.value}
    ),
}

_SELF_ONLY_IDENTIFIERS = frozenset({"userid", "uploadid", "attachmentid"})


def _normalized_identifier(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def _narrow_identifier_reason(reason: str) -> bool:
    normalized = " ".join(reason.lower().split())
    generic = {
        "command local identifier",
        "identifier declaration",
        "public command identifier",
        "public identifier",
        "public route",
        "self only identifier",
        "synthetic mutation",
    }
    return len(normalized.split()) >= 4 and normalized not in generic


def _validate_explicit_declaration(
    item: RouteInventoryItem,
    marker: ExplicitRouteClassification,
) -> str | None:
    declared = marker.allowed_identifiers
    canonical_declared = tuple(_canonical_identifier(value) for value in declared)
    if any(value is None for value in canonical_declared):
        return "explicit identifier declaration contains a wildcard or unknown identifier"
    if len(set(declared)) != len(declared):
        return "explicit identifier declaration contains duplicates"
    if set(declared) != set(item.identifiers):
        return "explicit identifier declaration must exactly match observed identifiers"
    if not item.identifiers:
        if marker.identifier_scope is not None:
            return "identifier scope requires at least one observed identifier"
        return None
    if not _narrow_identifier_reason(marker.reason):
        return "identifier-bearing explicit route requires a narrow non-generic reason"
    if marker.access == "public":
        if marker.identifier_scope != "command-local":
            return "explicit-public identifiers require command-local scope"
        return None
    if marker.identifier_scope != "self-only":
        return "authenticated-global identifiers require self-only scope"
    if any(
        _normalized_identifier(value) not in _SELF_ONLY_IDENTIFIERS for value in item.identifiers
    ):
        return "authenticated-global identifiers must be Actor-self command fields"
    return None


def _validate_spec_compatibility(item: RouteInventoryItem) -> str | None:
    if any(spec.capability for spec in item.authorization_specs):
        return None
    resource_types = {spec.resource_type for spec in item.authorization_specs}
    for identifier in item.identifiers:
        allowed = _IDENTIFIER_RESOURCE_TYPES.get(_normalized_identifier(identifier))
        if item.classification == "safe-public" and _normalized_identifier(identifier) in {
            "studentid",
            "childid",
            "userid",
        }:
            allowed = frozenset({ResourceType.STUDENT.value})
        if allowed is not None and not resource_types & allowed:
            return f"identifier {identifier} lacks a compatible executable authorization spec"
    return None


def _validate_identifier_policy(
    item: RouteInventoryItem,
    marker: ExplicitRouteClassification | None,
) -> str | None:
    normalized = {_normalized_identifier(value) for value in item.identifiers}
    if marker is not None:
        reason = _validate_explicit_declaration(item, marker)
        if reason:
            return reason
    if not item.identifiers:
        return None
    if item.classification in {"public", "authenticated-global"}:
        return None
    if not item.authorization_specs:
        return "sensitive identifiers have no executable authorization spec"
    if normalized & _NOTIFICATION_IDS:
        valid = any(
            spec.resource_type
            in {
                ResourceType.NOTIFICATION_EVENT.value,
                ResourceType.NOTIFICATION_PUSH_TOKEN.value,
                ResourceType.NOTIFICATION_COLLECTION.value,
            }
            and (
                spec.purpose == "notification_self_service"
                or (item.classification == "admin-capability" and spec.capability)
            )
            for spec in item.authorization_specs
        )
        if not valid:
            return "notification/event/token identifier lacks Actor-owner or exact admin-capability policy"
    compatibility = _validate_spec_compatibility(item)
    if compatibility:
        return compatibility
    return None


def inventory_application(app: FastAPI) -> tuple[RouteInventoryItem, ...]:
    failures = validate_application_inventory(app)
    if failures:
        detail = "; ".join(
            f"{failure.method} {failure.path}: {failure.reason}" for failure in failures
        )
        raise ValueError(detail)
    items: list[RouteInventoryItem] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        identifiers = _route_identifiers(route)
        target_projection = _target_projection(
            getattr(route.endpoint, "admin_target_provider", None)
        )
        for method in sorted(route.methods):
            classification, specs = _classify_route(route, method)
            items.append(
                RouteInventoryItem(
                    method,
                    route.path,
                    _family(route.path),
                    classification,
                    identifiers,
                    specs,
                    classification not in {"public", "safe-public"}
                    and bool(identifiers or specs or classification == "admin-capability"),
                    target_projection,
                )
            )
    return tuple(sorted(items, key=lambda item: (item.method, item.path)))


def validate_application_inventory(app: FastAPI) -> tuple[InventoryFailure, ...]:
    failures: list[InventoryFailure] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        endpoint_metadata = getattr(route.endpoint, "authorization_specs", ())
        graph_calls = {dependant.call for dependant in _walk_dependants(route.dependant)}
        if endpoint_metadata and route.endpoint not in graph_calls - {route.dependant.call}:
            failures.append(
                InventoryFailure("*", route.path, "metadata is not attached to a dependency")
            )
        identifiers = _route_identifiers(route)
        body_aliases = _route_body_aliases(route)
        provider = getattr(route.endpoint, "admin_target_provider", None)
        for method in sorted(route.methods):
            try:
                classification, specs = _classify_route(route, method)
                item = RouteInventoryItem(
                    method,
                    route.path,
                    _family(route.path),
                    classification,
                    identifiers,
                    specs,
                    classification not in {"public", "safe-public"}
                    and bool(identifiers or specs or classification == "admin-capability"),
                    _target_projection(provider),
                )
                if classification == "admin-capability":
                    policy = next(
                        getattr(dependant.call, "admin_policy_classifier")(method, route.path)
                        for dependant in _walk_dependants(route.dependant)
                        if getattr(dependant.call, "admin_policy_classifier", None) is not None
                    )
                    target_names = {_normalized_identifier(value) for value in policy.target_keys}
                    observed = {
                        alias
                        for alias in body_aliases
                        if _normalized_identifier(alias.rsplit(".", 1)[-1]) in target_names
                    }
                    if observed and provider is None:
                        raise ValueError("body target lacks an executable typed provider")
                    if provider is not None:
                        declared = set(provider.target_paths)
                        if observed != declared:
                            raise ValueError(
                                "typed provider target paths do not exactly match policy/body targets"
                            )
                        if (
                            provider.cardinality in {"collection", "resolver_collection"}
                            and provider.maximum is None
                        ):
                            raise ValueError("typed collection provider lacks a declared maximum")
                        if declared & set(provider.reference_only):
                            raise ValueError(
                                "evidence-only field is promoted as an authorization target"
                            )
                marker = getattr(route.endpoint, "stoa_route_classification", None)
                reason = _validate_identifier_policy(item, marker)
                if reason:
                    failures.append(InventoryFailure(method, route.path, reason))
            except (KeyError, TypeError, ValueError) as error:
                failures.append(InventoryFailure(method, route.path, str(error)))
    return tuple(
        sorted(failures, key=lambda failure: (failure.method, failure.path, failure.reason))
    )


def inventory_projection(app: FastAPI) -> list[dict[str, Any]]:
    return [item.projection() for item in inventory_application(app)]


def install_authorization_openapi(app: FastAPI) -> None:
    """Install one OpenAPI projection backed by the same validated inventory."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title, version=app.version, description=app.description, routes=app.routes
        )
        for item in inventory_application(app):
            operation = schema["paths"][item.path][item.method.lower()]
            extension = {
                "classification": item.classification,
                "identifiers": list(item.identifiers),
                "authorization": [asdict(spec) for spec in item.authorization_specs],
            }
            if item.admin_target is not None:
                extension["adminTarget"] = item.admin_target
            operation["x-stoa-authorization"] = extension
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
