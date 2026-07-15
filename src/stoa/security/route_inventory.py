"""Deterministic authorization inventory derived from registered FastAPI routes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Literal

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from pydantic import BaseModel

from stoa.security.admin_authorization import AdminRoutePolicy
from stoa.security.authorization import AuthorizationSpec, ResourceType


RouteAccess = Literal["public", "authenticated-global"]


@dataclass(frozen=True, slots=True)
class ExplicitRouteClassification:
    access: RouteAccess
    reason: str


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

    @property
    def authorization_spec(self) -> InventorySpec | None:
        return self.authorization_specs[0] if self.authorization_specs else None

    def projection(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "family": self.family,
            "classification": self.classification,
            "identifiers": list(self.identifiers),
            "authorization": [asdict(spec) for spec in self.authorization_specs],
            "sensitive": self.sensitive,
        }


@dataclass(frozen=True, slots=True)
class InventoryFailure:
    method: str
    path: str
    reason: str


def explicit_route_classification(access: RouteAccess, reason: str):
    """Mark an endpoint as deliberately public or authenticated global state."""

    if not reason.strip():
        raise ValueError("route classification reason is required")

    def decorate(endpoint: Callable[..., Any]) -> Callable[..., Any]:
        endpoint.stoa_route_classification = ExplicitRouteClassification(  # type: ignore[attr-defined]
            access, reason.strip()
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


def _field_aliases(annotation: Any, *, prefix: str = "") -> set[str]:
    aliases: set[str] = set()
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        for name, field in annotation.model_fields.items():
            alias = str(field.alias or name)
            aliases.add(f"{prefix}{alias}" if prefix else alias)
            aliases.update(_field_aliases(field.annotation, prefix=f"{alias}."))
    return aliases


_EXACT_IDENTIFIERS = {
    "studentid", "childid", "userid", "parentid", "teacherid", "questionid",
    "conversationid", "sessionid", "assignmentid", "requestid", "reportid",
    "deliveryid", "jobid", "draftid", "notificationid", "eventid",
    "tokenreference", "providertokenreference", "pushtoken", "deviceid",
    "applicationid",
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
    names = {
        str(field.alias or field.name)
        for field in (*route.dependant.path_params, *route.dependant.query_params)
    }
    for field in route.dependant.body_params:
        names.update(_field_aliases(field.field_info.annotation))
    return tuple(sorted(filter(None, (_canonical_identifier(name) for name in names))))


def _inventory_spec(spec: AuthorizationSpec) -> InventorySpec:
    return InventorySpec(spec.resource_type.value, spec.action.value, spec.purpose.value)


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
        specs.extend(_inventory_spec(spec) for spec in getattr(call, "authorization_specs", ()))
        classifier = getattr(call, "admin_policy_classifier", None)
        if classifier is not None:
            admin_policies.append(classifier(method, route.path))
    if admin_policies:
        if len(admin_policies) != 1:
            raise ValueError("duplicate admin policy classifiers")
        specs.append(_admin_inventory_spec(admin_policies[0]))
        classification = "admin-capability"
    elif specs:
        classification = "safe-public" if safe_public else "authorized"
    else:
        marker = getattr(route.endpoint, "stoa_route_classification", None)
        if not isinstance(marker, ExplicitRouteClassification):
            raise ValueError("route has no executable authorization or explicit public/global classification")
        classification = marker.access
    unique = {(item.resource_type, item.action, item.purpose, item.capability): item for item in specs}
    return classification, tuple(sorted(unique.values(), key=lambda item: (
        item.resource_type, item.action, item.purpose, item.capability or ""
    )))


_NOTIFICATION_IDS = {
    "notificationid", "eventid", "tokenreference", "providertokenreference",
    "pushtoken", "deviceid",
}


def _validate_identifier_policy(item: RouteInventoryItem) -> str | None:
    normalized = {"".join(char.lower() for char in value if char.isalnum()) for value in item.identifiers}
    if not item.identifiers:
        return None
    if item.classification in {"public", "safe-public"}:
        return None
    if item.classification == "authenticated-global":
        return "identifier-bearing route is classified public/global without executable owner policy"
    if not item.authorization_specs:
        return "sensitive identifiers have no executable authorization spec"
    if normalized & _NOTIFICATION_IDS:
        valid = any(
            spec.resource_type in {
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
    return None


def inventory_application(app: FastAPI) -> tuple[RouteInventoryItem, ...]:
    failures = validate_application_inventory(app)
    if failures:
        detail = "; ".join(f"{failure.method} {failure.path}: {failure.reason}" for failure in failures)
        raise ValueError(detail)
    items: list[RouteInventoryItem] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        identifiers = _route_identifiers(route)
        for method in sorted(route.methods):
            classification, specs = _classify_route(route, method)
            items.append(RouteInventoryItem(
                method, route.path, _family(route.path), classification, identifiers,
                specs, classification not in {"public", "safe-public"}
                and bool(identifiers or specs or classification == "admin-capability"),
            ))
    return tuple(sorted(items, key=lambda item: (item.method, item.path)))


def validate_application_inventory(app: FastAPI) -> tuple[InventoryFailure, ...]:
    failures: list[InventoryFailure] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        endpoint_metadata = getattr(route.endpoint, "authorization_specs", ())
        graph_calls = {dependant.call for dependant in _walk_dependants(route.dependant)}
        if endpoint_metadata and route.endpoint not in graph_calls - {route.dependant.call}:
            failures.append(InventoryFailure("*", route.path, "metadata is not attached to a dependency"))
        identifiers = _route_identifiers(route)
        for method in sorted(route.methods):
            try:
                classification, specs = _classify_route(route, method)
                item = RouteInventoryItem(
                    method, route.path, _family(route.path), classification, identifiers,
                    specs, classification not in {"public", "safe-public"}
                    and bool(identifiers or specs or classification == "admin-capability"),
                )
                reason = _validate_identifier_policy(item)
                if reason:
                    failures.append(InventoryFailure(method, route.path, reason))
            except (KeyError, TypeError, ValueError) as error:
                failures.append(InventoryFailure(method, route.path, str(error)))
    return tuple(sorted(failures, key=lambda failure: (failure.method, failure.path, failure.reason)))


def inventory_projection(app: FastAPI) -> list[dict[str, Any]]:
    return [item.projection() for item in inventory_application(app)]


def install_authorization_openapi(app: FastAPI) -> None:
    """Install one OpenAPI projection backed by the same validated inventory."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
        for item in inventory_application(app):
            operation = schema["paths"][item.path][item.method.lower()]
            operation["x-stoa-authorization"] = {
                "classification": item.classification,
                "identifiers": list(item.identifiers),
                "authorization": [asdict(spec) for spec in item.authorization_specs],
            }
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
