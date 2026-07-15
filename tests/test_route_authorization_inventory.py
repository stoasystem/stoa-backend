"""Executable registered-route authorization inventory tests."""

from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    ResourceType,
)
from stoa.security.route_inventory import explicit_route_classification


SENSITIVE_ROUTE_FAMILIES = {
    "students",
    "questions",
    "conversations",
    "practice",
    "adaptive",
    "reports",
    "teachers",
    "parents",
    "admin",
    "notifications",
}

REAL_NESTED_IDENTIFIER_ROUTES = {
    ("GET", "/questions/{question_id}"): ("question_id",),
    ("POST", "/questions/{question_id}/request-teacher"): ("question_id",),
    ("POST", "/questions/{question_id}/feedback"): ("question_id",),
    ("POST", "/questions/{question_id}/reports"): ("question_id",),
    ("GET", "/students/me/profile"): ("student_id",),
    ("PATCH", "/students/me/profile"): ("student_id",),
    ("GET", "/students/{student_id}/summary"): ("student_id",),
    ("GET", "/students/{student_id}/learning-profile"): ("student_id",),
    ("GET", "/students/{student_id}/questions"): ("student_id",),
    ("GET", "/adaptive/students/me/memory"): ("student_id",),
    ("GET", "/adaptive/students/me/assignments"): ("student_id",),
}


async def _resolver(resource_id: str):
    return {"student_id": resource_id}


def _policy_dependency(
    resource_type: ResourceType,
    *,
    safe_public: bool = False,
):
    async def dependency(student_id: str):
        return student_id

    dependency.authorization_specs = (
        AuthorizationSpec(
            resource_type,
            AuthorizationAction.READ,
            AuthorizationPurpose.SELF_SERVICE,
            _resolver,
        ),
    )
    dependency.safe_public = safe_public
    return dependency


class NestedIdentifierLeaf(BaseModel):
    student_id: str
    question_id: str = Field(alias="questionId")


class NestedIdentifierEnvelope(BaseModel):
    optional_leaf: Annotated[NestedIdentifierLeaf | None, "optional"] = None
    list_leaf: list[NestedIdentifierLeaf] = []
    tuple_leaf: tuple[NestedIdentifierLeaf, ...] = ()
    set_leaf: set[NestedIdentifierLeaf] = set()
    frozen_leaf: frozenset[NestedIdentifierLeaf] = frozenset()
    mapping_leaf: dict[str, NestedIdentifierLeaf] = {}


class RecursiveIdentifierModel(BaseModel):
    student_id: str | None = None
    child: "RecursiveIdentifierModel | None" = None


RecursiveIdentifierModel.model_rebuild()


def test_t472_08_inventory_has_every_sensitive_route_family_and_policy_metadata():
    from stoa.security.route_inventory import inventory_application

    from stoa.main import app

    inventory = inventory_application(app)
    assert SENSITIVE_ROUTE_FAMILIES <= {item.family for item in inventory}
    assert all(item.authorization_spec is not None for item in inventory if item.sensitive)
    assert len(inventory) == len({(item.method, item.path) for item in inventory})


def test_nested_annotated_container_body_identifiers_are_discovered_cycle_safely():
    from stoa.security.route_inventory import inventory_application

    app = FastAPI()

    @app.post("/public/nested")
    @explicit_route_classification(
        "public",
        "bounded nested registration correlation only",
        allowed_identifiers=("questionId", "student_id"),
        identifier_scope="command-local",
    )
    def nested(body: NestedIdentifierEnvelope):
        return body

    @app.post("/public/recursive")
    @explicit_route_classification(
        "public",
        "bounded recursive registration correlation only",
        allowed_identifiers=("student_id",),
        identifier_scope="command-local",
    )
    def recursive(body: RecursiveIdentifierModel):
        return body

    inventory = {(item.method, item.path): item for item in inventory_application(app)}
    assert inventory[("POST", "/public/nested")].identifiers == (
        "questionId",
        "student_id",
    )
    assert inventory[("POST", "/public/recursive")].identifiers == ("student_id",)


def test_nested_dependency_identifier_is_discovered():
    from stoa.security.route_inventory import inventory_application

    app = FastAPI()

    async def nested_dependency(student_id: str, question_id: str):
        return student_id, question_id

    @app.post("/public/dependency")
    @explicit_route_classification(
        "public",
        "bounded dependency registration correlation only",
        allowed_identifiers=("question_id", "student_id"),
        identifier_scope="command-local",
    )
    def endpoint(_: tuple[str, str] = Depends(nested_dependency)):
        return {}

    item = inventory_application(app)[0]
    assert item.identifiers == ("question_id", "student_id")


def test_public_nested_dependency_without_declaration_fails_closed():
    from stoa.security.route_inventory import validate_application_inventory

    app = FastAPI()

    class NestedBody(BaseModel):
        question_id: str

    async def nested_dependency(student_id: str, body: NestedBody):
        return student_id, body

    @app.post("/public/undeclared")
    @explicit_route_classification("public", "bounded public submission without identifiers")
    def endpoint(_: tuple[str, NestedBody] = Depends(nested_dependency)):
        return {}

    failures = validate_application_inventory(app)
    assert len(failures) == 1
    assert "exactly match" in failures[0].reason


def test_nested_non_sensitive_control_stays_non_sensitive_and_identifiers_deduplicate():
    from stoa.security.route_inventory import inventory_application

    class SafeLeaf(BaseModel):
        locale: str
        subject: str

    class DuplicateLeaf(BaseModel):
        student_id: str

    class MixedBody(BaseModel):
        safe: list[SafeLeaf]
        first: DuplicateLeaf
        second: DuplicateLeaf

    app = FastAPI()

    @app.post("/public/safe")
    @explicit_route_classification("public", "bounded non-sensitive catalog command only")
    def safe(body: SafeLeaf):
        return body

    @app.post("/public/deduplicated")
    @explicit_route_classification(
        "public",
        "bounded duplicate registration correlation only",
        allowed_identifiers=("student_id",),
        identifier_scope="command-local",
    )
    def deduplicated(body: MixedBody):
        return body

    inventory = {(item.method, item.path): item for item in inventory_application(app)}
    assert inventory[("POST", "/public/safe")].identifiers == ()
    assert inventory[("POST", "/public/safe")].sensitive is False
    assert inventory[("POST", "/public/deduplicated")].identifiers == ("student_id",)


def test_safe_public_marker_without_executable_spec_cannot_classify_route():
    from stoa.security.route_inventory import validate_application_inventory

    app = FastAPI()

    async def metadata_free_dependency(student_id: str):
        return student_id

    metadata_free_dependency.safe_public = True

    @app.get("/catalog/{student_id}")
    def endpoint(student_id: str, _: str = Depends(metadata_free_dependency)):
        return student_id

    failures = validate_application_inventory(app)
    assert len(failures) == 1
    assert "no executable authorization" in failures[0].reason


@pytest.mark.parametrize(
    ("allowed", "scope", "reason", "with_resource_spec", "expected"),
    [
        (("student_id",), "command-local", "bounded registration correlation identifier only", False, None),
        ((), None, "bounded registration correlation identifier only", False, "exactly match"),
        (("student_id", "question_id"), "command-local", "bounded registration correlation identifier only", False, "exactly match"),
        (("*",), "command-local", "bounded registration correlation identifier only", False, "wildcard"),
        (("student_id",), "command-local", "public route", False, "narrow"),
        (("student_id",), "command-local", "bounded registration correlation identifier only", True, "cannot accompany"),
    ],
)
def test_explicit_public_identifier_declaration_is_exact_and_command_local(
    allowed,
    scope,
    reason,
    with_resource_spec,
    expected,
):
    from stoa.security.route_inventory import validate_application_inventory

    app = FastAPI()
    dependency = _policy_dependency(ResourceType.STUDENT) if with_resource_spec else None

    if dependency is None:
        @app.post("/public/command/{student_id}")
        @explicit_route_classification(
            "public",
            reason,
            allowed_identifiers=allowed,
            identifier_scope=scope,
        )
        def endpoint(student_id: str):
            return student_id
    else:
        @app.post("/public/command/{student_id}")
        @explicit_route_classification(
            "public",
            reason,
            allowed_identifiers=allowed,
            identifier_scope=scope,
        )
        def endpoint(student_id: str, _: str = Depends(dependency)):
            return student_id

    failures = validate_application_inventory(app)
    if expected is None:
        assert failures == ()
    else:
        assert len(failures) == 1
        assert expected in failures[0].reason


@pytest.mark.parametrize(
    ("resource_type", "with_declaration", "expected"),
    [
        (ResourceType.STUDENT, False, None),
        (ResourceType.QUESTION, False, "compatible"),
        (ResourceType.QUESTION, True, "cannot accompany"),
    ],
)
def test_safe_public_identifiers_require_compatible_executable_specs(
    resource_type,
    with_declaration,
    expected,
):
    from stoa.security.route_inventory import validate_application_inventory

    app = FastAPI()
    dependency = _policy_dependency(resource_type, safe_public=True)
    decorator = (
        explicit_route_classification(
            "public",
            "bounded catalog correlation identifier only",
            allowed_identifiers=("student_id",),
            identifier_scope="command-local",
        )
        if with_declaration
        else lambda endpoint: endpoint
    )

    @app.get("/catalog/{student_id}")
    @decorator
    def endpoint(student_id: str, _: str = Depends(dependency)):
        return student_id

    failures = validate_application_inventory(app)
    if expected is None:
        assert failures == ()
    else:
        assert len(failures) == 1
        assert expected in failures[0].reason


@pytest.mark.parametrize(
    ("field_name", "allowed", "scope", "expected"),
    [
        ("user_id", ("user_id",), "self-only", None),
        ("user_id", (), None, "exactly match"),
        ("user_id", ("user_id",), "command-local", "self-only"),
        ("student_id", ("student_id",), "self-only", "Actor-self"),
    ],
)
def test_authenticated_global_identifier_requires_exact_self_only_declaration(
    field_name,
    allowed,
    scope,
    expected,
):
    from stoa.security.route_inventory import validate_application_inventory

    app = FastAPI()

    if field_name == "user_id":
        async def identity_dependency(user_id: str):
            return user_id
    else:
        async def identity_dependency(student_id: str):
            return student_id

    @app.post("/me/command")
    @explicit_route_classification(
        "authenticated-global",
        "authenticated Actor self identifier command only",
        allowed_identifiers=allowed,
        identifier_scope=scope,
    )
    def endpoint(_: str = Depends(identity_dependency)):
        return {}

    failures = validate_application_inventory(app)
    if expected is None:
        assert failures == ()
    else:
        assert len(failures) == 1
        assert expected in failures[0].reason


def test_real_route_nested_identifiers_and_public_declarations_are_exact():
    from stoa.main import app
    from stoa.security.route_inventory import inventory_application

    inventory = {(item.method, item.path): item for item in inventory_application(app)}
    for operation, identifiers in REAL_NESTED_IDENTIFIER_ROUTES.items():
        item = inventory[operation]
        assert item.identifiers == identifiers
        assert item.authorization_specs

    routes = {
        (method, route.path): route
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    register = routes[("POST", "/auth/register")].endpoint.stoa_route_classification
    application = routes[("POST", "/teacher-applications")].endpoint.stoa_route_classification
    assert register.allowed_identifiers == ("parent_id",)
    assert register.identifier_scope == "command-local"
    assert application.allowed_identifiers == ("application_id",)
    assert application.identifier_scope == "command-local"


def test_t472_08_inventory_mutation_rejects_synthetic_unclassified_sensitive_route():
    from stoa.security.route_inventory import validate_application_inventory

    app = FastAPI()
    router = APIRouter()

    @router.get("/students/{student_id}/synthetic-sensitive")
    def synthetic_sensitive(student_id: str):
        return {"studentId": student_id}

    app.include_router(router)
    failures = validate_application_inventory(app)
    assert any("synthetic-sensitive" in failure.path for failure in failures)


def test_inventory_rejects_every_new_unclassified_registered_router():
    from stoa.security.route_inventory import validate_application_inventory

    app = FastAPI()
    router = APIRouter()

    @router.get("/new-global-route")
    def newly_registered():
        return {}

    app.include_router(router)
    assert validate_application_inventory(app) == (
        validate_application_inventory(app)[0],
    )
    assert "no executable authorization" in validate_application_inventory(app)[0].reason


def test_event_id_and_push_token_body_mutations_require_actor_owner_policy():
    from stoa.security.route_inventory import validate_application_inventory

    class PushBody(BaseModel):
        provider_token_reference: str = Field(alias="providerTokenReference")
        device_id: str = Field(alias="deviceId")

    app = FastAPI()

    @app.post("/notifications/{event_id}/unsafe")
    @explicit_route_classification("authenticated-global", "synthetic mutation")
    def event_mutation(event_id: str):
        return {"eventId": event_id}

    @app.post("/notifications/push-token-unsafe")
    @explicit_route_classification("authenticated-global", "synthetic mutation")
    def token_mutation(body: PushBody):
        return body

    failures = validate_application_inventory(app)
    assert {failure.path for failure in failures} == {
        "/notifications/{event_id}/unsafe",
        "/notifications/push-token-unsafe",
    }


def test_notification_identifier_rejects_unrelated_executable_spec():
    from stoa.security.route_inventory import validate_application_inventory

    async def resolver(resource_id: str):
        return {"student_id": resource_id}

    async def wrong_dependency():
        return None

    wrong_dependency.authorization_specs = (
        AuthorizationSpec(
            ResourceType.STUDENT,
            AuthorizationAction.READ,
            AuthorizationPurpose.SELF_SERVICE,
            resolver,
        ),
    )
    app = FastAPI()

    @app.get("/notifications/{event_id}")
    def unsafe_event(event_id: str, _: None = Depends(wrong_dependency)):
        return {"eventId": event_id}

    failures = validate_application_inventory(app)
    assert len(failures) == 1
    assert "Actor-owner" in failures[0].reason


def test_openapi_and_checked_json_are_identical_runtime_projections():
    import json
    from pathlib import Path

    from stoa.main import app
    from stoa.security.route_inventory import inventory_application

    checked = json.loads(Path("docs/security/route-authorization-inventory.json").read_text())
    runtime = [item.projection() for item in inventory_application(app)]
    assert checked == runtime
    schema = app.openapi()
    for item in runtime:
        extension = schema["paths"][item["path"]][item["method"].lower()][
            "x-stoa-authorization"
        ]
        expected = {
            "classification": item["classification"],
            "identifiers": item["identifiers"],
            "authorization": item["authorization"],
        }
        if "adminTarget" in item:
            expected["adminTarget"] = item["adminTarget"]
        assert extension == expected


def test_admin_body_target_provider_is_executable_exact_and_projected(monkeypatch):
    from stoa.main import app
    from stoa.security.admin_authorization import AdminTargetProvider
    from stoa.security.route_inventory import inventory_application, validate_application_inventory

    route = next(
        route for route in app.routes
        if isinstance(route, APIRoute) and route.path == "/admin/parent-bindings/repair"
    )
    provider = route.endpoint.admin_target_provider
    assert provider.cardinality == "scalar"
    assert provider.target_paths == ("parent_id", "student_id")
    item = next(
        item for item in inventory_application(app)
        if item.method == "POST" and item.path == route.path
    )
    assert item.admin_target["tupleFields"] == ["parent_id", "student_id"]

    monkeypatch.setattr(route.endpoint, "admin_target_provider", AdminTargetProvider(
        "scalar", "body", ("student_id",), ("student_id",)
    ))
    failures = validate_application_inventory(app)
    assert any("exactly match" in failure.reason for failure in failures if failure.path == route.path)


def test_metadata_on_endpoint_without_dependency_is_rejected():
    from stoa.security.route_inventory import validate_application_inventory

    async def resolver(resource_id: str):
        return {"student_id": resource_id}

    app = FastAPI()

    @app.get("/students/{student_id}/metadata-only")
    def metadata_only(student_id: str):
        return {"studentId": student_id}

    metadata_only.authorization_specs = (
        AuthorizationSpec(
            ResourceType.STUDENT,
            AuthorizationAction.READ,
            AuthorizationPurpose.SELF_SERVICE,
            resolver,
        ),
    )
    failures = validate_application_inventory(app)
    assert any("not attached to a dependency" in failure.reason for failure in failures)
