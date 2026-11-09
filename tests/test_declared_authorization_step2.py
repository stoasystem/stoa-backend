"""Declarative authorization, step 2 (#349, shape in #316).

The seven remaining router files moved to the one entry. What the entry
needed for them, driven through small applications of their own:

- an operator grant that may be scoped to the object a path names (a
  teacher application), next to the global one a queue uses;
- a purpose chosen by a grant the Actor holds (the AI teacher tools);
- a body-named id authorized like a path-named one (`authorize_id`);
- ``SELF`` that loads only types whose loader loads the Actor's own record;
- service-enforced checks named truthfully, also on a route that authorizes
  something else itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import Body, Depends, FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.security import declared_authorization as declared
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationFacts,
    AuthorizationPurpose,
    AuthorizedResource,
    ResourceRef,
    ResourceType,
)
from stoa.security.declared_authorization import (
    SELF,
    authorize_id,
    authorized,
    by_grant,
    get_authorization_context,
    loaded_declaration,
    operator,
    path,
    service_enforced,
)
from stoa.security.identity import AccountStatus, Actor, CanonicalRole, CapabilityGrant
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.security.route_inventory import inventory_application, validate_application_inventory

ROOT = Path(__file__).resolve().parents[1]
TEST_KIND = "declared-authorization-step2-test"
STUDENT_SELF = {CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE}


def _actor(role: CanonicalRole, user_id: str, *grants: CapabilityGrant) -> Actor:
    return Actor(
        user_id=user_id,
        issuer="https://identity.test",
        subject=f"{user_id}-subject",
        role=role,
        account_status=AccountStatus.ACTIVE,
        cognito_group=role.value,
        current_grants=tuple(grants),
    )


STUDENT = _actor(CanonicalRole.STUDENT, "student-1")
OTHER_STUDENT = _actor(CanonicalRole.STUDENT, "student-2")
TEACHER = _actor(CanonicalRole.TEACHER, "teacher-1")
TOOLS_TEACHER = _actor(
    CanonicalRole.TEACHER,
    "teacher-2",
    CapabilityGrant("ai_teacher_tools_operator", "global", 1),
)
GLOBAL_REVIEWER = _actor(
    CanonicalRole.ADMIN, "admin-1", CapabilityGrant("teacher_identity_reviewer", "global", 1)
)
ONE_APPLICATION_REVIEWER = _actor(
    CanonicalRole.ADMIN,
    "admin-2",
    CapabilityGrant(
        "teacher_identity_reviewer", "resource:operator_resource:application-1", 1
    ),
)


class _NoFacts:
    async def facts_for(self, *_args):
        return AuthorizationFacts()


@pytest.fixture
def owned_things():
    """A loader for the test kind: thing-1 belongs to student-1."""

    async def load(resource_id: str, _actor: Actor):
        if resource_id != "thing-1":
            return None
        return AuthorizedResource(
            ResourceRef(ResourceType.CONVERSATION, resource_id, "student-1"),
            {"student_id": "student-1"},
        )

    declared.register_resource_loader(ResourceType.CONVERSATION, load, kind=TEST_KIND)
    yield
    declared.unregister_resource_loader(ResourceType.CONVERSATION, kind=TEST_KIND)


def _results(sink: MemoryAuthorizationAuditSink) -> list[tuple[str, str, str]]:
    return sorted(
        (str(event["resource_type"]), str(event["result_code"]), str(event["decision_kind"]))
        for event in sink.events.values()
    )


def _client(app: FastAPI, actor: Actor, sink: MemoryAuthorizationAuditSink) -> TestClient:
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_audit_sink] = lambda: sink
    app.dependency_overrides[get_authorization_fact_repository] = _NoFacts
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# operator(..., target=path(...))
# ---------------------------------------------------------------------------


def _reviewer_app() -> FastAPI:
    app = FastAPI()
    purposes = {CanonicalRole.ADMIN: AuthorizationPurpose.IDENTITY_MANAGEMENT}

    @app.get("/applications")
    async def queue(
        me: Actor = Depends(
            authorized(
                ResourceType.OPERATOR_RESOURCE,
                AuthorizationAction.READ,
                operator(capability="teacher_identity_reviewer"),
                purposes,
            )
        ),
    ):
        return {"actor": me.user_id}

    @app.get("/applications/{application_id}")
    async def one(
        me: Actor = Depends(
            authorized(
                ResourceType.OPERATOR_RESOURCE,
                AuthorizationAction.READ,
                operator(capability="teacher_identity_reviewer", target=path("application_id")),
                purposes,
            )
        ),
    ):
        return {"actor": me.user_id}

    return app


@pytest.mark.parametrize(
    "actor,url,status",
    [
        (GLOBAL_REVIEWER, "/applications", 200),
        (GLOBAL_REVIEWER, "/applications/application-2", 200),
        (ONE_APPLICATION_REVIEWER, "/applications/application-1", 200),
        (ONE_APPLICATION_REVIEWER, "/applications/application-2", 403),
        # A grant for one application does not open the queue (#104).
        (ONE_APPLICATION_REVIEWER, "/applications", 403),
    ],
)
def test_an_operator_grant_may_be_scoped_to_the_object_the_path_names(actor, url, status):
    sink = MemoryAuthorizationAuditSink()
    response = _client(_reviewer_app(), actor, sink).get(url)

    assert response.status_code == status, response.text
    [(resource_type, result, kind)] = _results(sink)
    assert (resource_type, kind) == ("operator_resource", "operator_capability")
    assert result == ("allowed" if status == 200 else "action_not_allowed")


def test_the_operator_target_is_in_the_inventory_and_checked_by_the_gate():
    app = _reviewer_app()
    items = {item.path: item for item in inventory_application(app)}
    assert items["/applications/{application_id}"].identifiers == ("application_id",)
    assert items["/applications"].identifiers == ()

    broken = FastAPI()

    @broken.get("/applications/{id}")
    async def misnamed(
        me: Actor = Depends(
            authorized(
                ResourceType.OPERATOR_RESOURCE,
                AuthorizationAction.READ,
                operator(capability="teacher_identity_reviewer", target=path("application_id")),
                {CanonicalRole.ADMIN: AuthorizationPurpose.IDENTITY_MANAGEMENT},
            )
        ),
    ):
        return {}

    reasons = {failure.reason for failure in validate_application_inventory(broken)}
    assert (
        "declared path identifier application_id is not a parameter of the route path"
        in reasons
    )


# ---------------------------------------------------------------------------
# by_grant(...)
# ---------------------------------------------------------------------------

TOOL_PURPOSE = by_grant(
    "ai_teacher_tools_operator",
    AuthorizationPurpose.AI_TEACHER_TOOLS,
    otherwise=AuthorizationPurpose.TEACHER_HELP,
)


def test_a_purpose_chosen_by_a_grant_follows_the_actor_and_lists_both_in_the_inventory(
    owned_things,
):
    app = FastAPI()
    seen: list[str] = []

    class _Policy(declared.AuthorizationPolicy):
        def evaluate(self, actor, resource, action, purpose, *, correlation_id=None):
            seen.append(AuthorizationPurpose(purpose).value)
            return super().evaluate(
                actor, resource, action, purpose, correlation_id=correlation_id
            )

    @app.get("/things/{thing_id}")
    async def thing(
        _resource: AuthorizedResource = Depends(
            authorized(
                ResourceType.CONVERSATION,
                AuthorizationAction.READ,
                path("thing_id"),
                {CanonicalRole.TEACHER: TOOL_PURPOSE},
                kind=TEST_KIND,
            )
        ),
    ):
        return {}

    app.dependency_overrides[declared.get_authorization_policy] = _Policy
    for actor in (TEACHER, TOOLS_TEACHER):
        _client(app, actor, MemoryAuthorizationAuditSink()).get("/things/thing-1")
    assert seen == ["teacher_help", "ai_teacher_tools"]

    [item] = inventory_application(app)
    assert sorted(spec.purpose for spec in item.authorization_specs) == [
        "ai_teacher_tools",
        "teacher_help",
    ]


# ---------------------------------------------------------------------------
# authorize_id: an id from a body, authorized like a path id
# ---------------------------------------------------------------------------


def _body_app() -> FastAPI:
    app = FastAPI()

    @loaded_declaration(ResourceType.CONVERSATION, AuthorizationAction.UPDATE, STUDENT_SELF)
    async def by_body(
        thing_id: str = Body(embed=True),
        actor: Actor = Depends(get_actor),
        context: declared.AuthorizationContext = Depends(get_authorization_context),
    ) -> AuthorizedResource:
        return await authorize_id(
            actor,
            ResourceType.CONVERSATION,
            thing_id,
            AuthorizationAction.UPDATE,
            STUDENT_SELF,
            context,
            kind=TEST_KIND,
        )

    @app.post("/things")
    async def post(resource: AuthorizedResource = Depends(by_body)):
        return {"id": resource.ref.resource_id}

    return app


@pytest.mark.parametrize(
    "actor,thing_id,status,audit",
    [
        (STUDENT, "thing-1", 200, []),
        (OTHER_STUDENT, "thing-1", 404, [("conversation", "resource_not_found", "policy")]),
        (STUDENT, "thing-9", 404, [("conversation", "resource_not_found", "resolver")]),
        # A role the declaration does not name is hidden as on a path id.
        (TEACHER, "thing-1", 404, [("conversation", "resource_not_found", "policy")]),
    ],
)
def test_a_body_id_is_authorized_like_a_path_id(owned_things, actor, thing_id, status, audit):
    sink = MemoryAuthorizationAuditSink()
    response = _client(_body_app(), actor, sink).post("/things", json={"thing_id": thing_id})

    assert response.status_code == status, response.text
    assert _results(sink) == audit


# ---------------------------------------------------------------------------
# SELF and the registered loaders
# ---------------------------------------------------------------------------


def test_self_does_not_load_a_type_whose_loader_is_keyed_by_another_id():
    """A conversation is loaded by its own id: ``SELF`` on it is the Actor's own account."""
    app = FastAPI()

    @app.get("/conversations")
    async def mine(
        me: Actor = Depends(
            authorized(ResourceType.CONVERSATION, AuthorizationAction.READ, SELF, STUDENT_SELF)
        ),
    ):
        return {"actor": me.user_id}

    sink = MemoryAuthorizationAuditSink()
    response = _client(app, STUDENT, sink).get("/conversations")

    assert response.status_code == 200, response.text
    assert response.json() == {"actor": "student-1"}


@pytest.mark.parametrize(
    "resource_type,kind",
    [
        (ResourceType.CONVERSATION, None),
        (ResourceType.CONVERSATION, declared.LIVE),
        (ResourceType.QUESTION, None),
        (ResourceType.TEACHER_HELP_REQUEST, None),
        (ResourceType.AI_TEACHER_DRAFT, None),
        (ResourceType.NOTIFICATION_EVENT, None),
        (ResourceType.NOTIFICATION_PUSH_TOKEN, declared.TOKEN),
        (ResourceType.ATTACHMENT, None),
        (ResourceType.ATTACHMENT, declared.DELETABLE),
    ],
)
def test_each_resource_the_seven_files_name_has_one_registered_loader(resource_type, kind):
    assert declared.resource_loader(resource_type, kind) is not None


# ---------------------------------------------------------------------------
# Service-enforced checks, named where they are
# ---------------------------------------------------------------------------


def test_a_route_that_authorizes_and_leaves_a_check_to_a_service_says_both(owned_things):
    app = FastAPI()
    attachments = service_enforced(
        "ask_question.submit", ResourceType.ATTACHMENT, AuthorizationAction.READ, STUDENT_SELF
    )
    practice = service_enforced(
        "practice_context_service.resolve",
        ResourceType.PRACTICE,
        AuthorizationAction.READ,
        STUDENT_SELF,
    )

    @app.post("/things/{thing_id}/messages")
    async def send(
        _resource: AuthorizedResource = Depends(
            authorized(
                ResourceType.CONVERSATION,
                AuthorizationAction.RESPOND,
                path("thing_id"),
                STUDENT_SELF,
                kind=TEST_KIND,
            )
        ),
        _attachments: Actor = Depends(attachments),
        _practice: Actor = Depends(practice),
    ):
        return {}

    [item] = inventory_application(app)
    assert item.classification == "authorized"
    assert item.projection()["serviceEnforced"] == [
        "ask_question.submit",
        "practice_context_service.resolve",
    ]


# ---------------------------------------------------------------------------
# The seven files
# ---------------------------------------------------------------------------

SEVEN = (
    "conversations",
    "teachers",
    "notifications",
    "files",
    "upload_codes",
    "teacher_applications",
    "questions",
)


@pytest.mark.parametrize("name", SEVEN)
def test_the_router_declares_and_never_pastes_or_calls_the_old_gateway(name):
    source = (ROOT / "src" / "stoa" / "routers" / f"{name}.py").read_text(encoding="utf-8")
    assert "authorization_specs =" not in source
    assert '"authorization_specs"' not in source
    imported = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert not imported & {
        "authorize_and_resolve",
        "authorize_conversation_resource",
        "authorize_teacher_loaded_resource",
    }


def _production_inventory() -> dict[tuple[str, str], dict[str, object]]:
    from stoa.main import app

    return {
        (str(item["method"]), str(item["path"])): item
        for item in __import__(
            "stoa.security.route_inventory", fromlist=["inventory_projection"]
        ).inventory_projection(app)
    }


@pytest.mark.parametrize(
    "method,route,classification,entries",
    [
        ("POST", "/files/intents", "service-enforced", ["uploads.start"]),
        ("POST", "/files/{upload_id}/parts/{part_number}", "service-enforced", ["uploads.sign_part"]),
        ("POST", "/files/{upload_id}/complete", "service-enforced", ["uploads.complete"]),
        (
            "GET",
            "/files/{upload_id}/phone-code",
            "service-enforced",
            ["upload_code_service.unbound_code_status"],
        ),
        (
            "GET",
            "/files/{upload_id}/phone-code/content",
            "service-enforced",
            ["upload_code_service.preview_unbound_upload"],
        ),
        (
            "POST",
            "/teachers/me/help-requests/{request_id}/notes",
            "authorized",
            ["attachment_service.prepare_reply_images"],
        ),
        (
            "POST",
            "/conversations/{conv_id}/messages",
            "authorized",
            ["ask_question.submit", "practice_context_service.resolve"],
        ),
        ("POST", "/conversations", "authorized", ["practice_context_service.resolve"]),
    ],
)
def test_service_enforced_checks_are_named_in_the_inventory(
    method, route, classification, entries
):
    item = _production_inventory()[(method, route)]
    assert item["classification"] == classification
    assert item.get("serviceEnforced") == entries


@pytest.mark.parametrize(
    "method,route",
    [
        ("GET", "/teachers/me/help-requests"),
        ("GET", "/teachers/me/stats"),
        ("GET", "/teachers/ai-tools/drafts"),
    ],
)
def test_lists_decided_item_by_item_are_authorized_not_service_enforced(method, route):
    """The teacher's own portal, then `authorize_loaded` on each listed object."""
    item = _production_inventory()[(method, route)]
    assert item["classification"] == "authorized"
    assert "serviceEnforced" not in item
    assert "teacher_portal" in {spec["resource_type"] for spec in item["authorization"]}
