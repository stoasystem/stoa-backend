"""The one declarative route authorization entry (#348, shape in #316).

A route says which resource it acts on, which action, where the resource id
comes from and which purpose each role reads it under; the entry takes the id
by that declared name, loads the resource through the loader registered for
its type, asks the policy and records the decision. These tests drive the
entry through a small application of its own, with the same four override
points the production routes use.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

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
    AuthorizationDeclarationError,
    authorize_loaded,
    authorized,
    operator,
    path,
    query,
    service_enforced,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import AccountStatus, Actor, CanonicalRole, CapabilityGrant
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.security.route_inventory import inventory_application, validate_application_inventory


STUDENT_READ = {
    CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE,
    CanonicalRole.PARENT: AuthorizationPurpose.PARENT_OVERSIGHT,
}
TEST_KIND = "declared-authorization-test"


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


class _Facts:
    """Parents see student-1 only; everyone else gets no relationship facts."""

    async def facts_for(self, actor, resource, action, purpose, value):
        from stoa.security.authorization import ParentAuthorizationFacts
        from stoa.services.current_relationship import Standing, Verdict

        if actor.role is CanonicalRole.PARENT:
            standing = (
                Standing.CURRENT if resource.student_id == "student-1" else Standing.UNKNOWN
            )
            return AuthorizationFacts(
                parent=ParentAuthorizationFacts(
                    verdict=Verdict(standing, actor.user_id, resource.student_id),
                    parent_account={
                        "user_id": actor.user_id,
                        "role": "parent",
                        "account_status": "active",
                    },
                    student_account={
                        "user_id": resource.student_id,
                        "role": "student",
                        "account_status": "active",
                    },
                )
            )
        return AuthorizationFacts()


@pytest.fixture
def loads():
    """A loader for the test kind: student-1 and student-2 exist, `boom` fails."""
    calls: list[tuple[str, str]] = []

    async def load(resource_id: str, actor: Actor):
        calls.append((resource_id, actor.user_id))
        if resource_id == "boom":
            raise TimeoutError("loader-canary")
        if resource_id not in {"student-1", "student-2"}:
            return None
        return AuthorizedResource(
            ResourceRef(ResourceType.STUDENT, resource_id, resource_id),
            {"user_id": resource_id, "role": "student"},
        )

    declared.register_resource_loader(ResourceType.STUDENT, load, kind=TEST_KIND)
    yield calls
    declared.unregister_resource_loader(ResourceType.STUDENT, kind=TEST_KIND)


def _app(actor: Actor, sink: MemoryAuthorizationAuditSink) -> FastAPI:
    app = FastAPI()
    read = AuthorizationAction.READ

    @app.get("/students/{student_id}/thing")
    async def by_path(
        resource: AuthorizedResource = Depends(
            authorized(ResourceType.STUDENT, read, path("student_id"), STUDENT_READ, kind=TEST_KIND)
        ),
    ):
        return {"id": resource.ref.resource_id, "value": dict(resource.value)}

    @app.get("/thing")
    async def by_query(
        resource: AuthorizedResource = Depends(
            authorized(
                ResourceType.STUDENT,
                read,
                query("studentId", student_defaults_to_self=True),
                STUDENT_READ,
                kind=TEST_KIND,
            )
        ),
    ):
        return {"id": resource.ref.resource_id}

    @app.get("/strict-thing")
    async def by_strict_query(
        resource: AuthorizedResource = Depends(
            authorized(
                ResourceType.STUDENT, read, query("studentId"), STUDENT_READ, kind=TEST_KIND
            )
        ),
    ):
        return {"id": resource.ref.resource_id}

    @app.get("/me/thing")
    async def by_self(
        me: Actor = Depends(
            authorized(
                ResourceType.PRACTICE,
                read,
                SELF,
                {CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE},
            )
        ),
    ):
        return {"actor": me.user_id}

    @app.get("/me/account")
    async def by_loaded_self(
        me: Actor = Depends(
            authorized(
                ResourceType.STUDENT,
                read,
                SELF,
                {CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE},
                kind=TEST_KIND,
            )
        ),
    ):
        return {"actor": me.user_id}

    @app.get("/operate")
    async def by_operator(
        me: Actor = Depends(
            authorized(
                ResourceType.OPERATOR_RESOURCE,
                read,
                operator(capability="teacher_identity_reviewer"),
                {CanonicalRole.ADMIN: AuthorizationPurpose.IDENTITY_MANAGEMENT},
            )
        ),
    ):
        return {"actor": me.user_id}

    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_audit_sink] = lambda: sink
    app.dependency_overrides[get_authorization_fact_repository] = _Facts
    return app


def _results(sink: MemoryAuthorizationAuditSink) -> list[tuple[str, str, str]]:
    return sorted(
        (str(event["resource_type"]), str(event["result_code"]), str(event["decision_kind"]))
        for event in sink.events.values()
    )


STUDENT = _actor(CanonicalRole.STUDENT, "student-1")
PARENT = _actor(CanonicalRole.PARENT, "parent-1")
TEACHER = _actor(CanonicalRole.TEACHER, "teacher-1")
REVIEWER = _actor(
    CanonicalRole.ADMIN,
    "admin-1",
    CapabilityGrant("teacher_identity_reviewer", "global", 1),
)
PLAIN_ADMIN = _actor(CanonicalRole.ADMIN, "admin-2")


# (case, actor, url, status, resource id the handler saw, audit rows)
CASES = [
    # path(...)
    ("path-own", STUDENT, "/students/student-1/thing", 200, "student-1", []),
    (
        "path-parent-related",
        PARENT,
        "/students/student-1/thing",
        200,
        "student-1",
        [("student", "allowed", "policy")],
    ),
    (
        "path-policy-denies",
        PARENT,
        "/students/student-2/thing",
        404,
        None,
        [("student", "resource_not_found", "policy")],
    ),
    (
        "path-loader-none",
        STUDENT,
        "/students/student-9/thing",
        404,
        None,
        [("student", "resource_not_found", "resolver")],
    ),
    (
        "path-loader-raises",
        STUDENT,
        "/students/boom/thing",
        503,
        None,
        [("student", "authorization_temporarily_unavailable", "unavailable")],
    ),
    (
        "path-role-not-declared-is-hidden",
        TEACHER,
        "/students/student-1/thing",
        404,
        None,
        [("student", "resource_not_found", "policy")],
    ),
    # query(...)
    ("query-given", STUDENT, "/thing?studentId=student-1", 200, "student-1", []),
    ("query-student-default", STUDENT, "/thing", 200, "student-1", []),
    (
        "query-parent-missing",
        PARENT,
        "/thing",
        404,
        None,
        [("student", "resource_not_found", "missing_identifier")],
    ),
    (
        "query-parent-given",
        PARENT,
        "/thing?studentId=student-1",
        200,
        "student-1",
        [("student", "allowed", "policy")],
    ),
    ("strict-query-student-missing", STUDENT, "/strict-thing", 422, None, []),
    # SELF
    ("self-student", STUDENT, "/me/thing", 200, None, []),
    ("self-loaded", STUDENT, "/me/account", 200, None, []),
    (
        "self-loader-none",
        _actor(CanonicalRole.STUDENT, "student-9"),
        "/me/account",
        404,
        None,
        [("student", "resource_not_found", "resolver")],
    ),
    (
        "self-other-role",
        PARENT,
        "/me/thing",
        403,
        None,
        [("practice", "action_not_allowed", "role_not_declared")],
    ),
    # operator(...)
    (
        "operator-granted",
        REVIEWER,
        "/operate",
        200,
        None,
        [("operator_resource", "allowed", "operator_capability")],
    ),
    (
        "operator-without-grant",
        PLAIN_ADMIN,
        "/operate",
        403,
        None,
        [("operator_resource", "action_not_allowed", "operator_capability")],
    ),
]


@pytest.mark.parametrize(
    "case,actor,url,status,seen_id,audit", CASES, ids=[row[0] for row in CASES]
)
def test_entry_outcomes(loads, case, actor, url, status, seen_id, audit):
    sink = MemoryAuthorizationAuditSink()
    response = TestClient(_app(actor, sink), raise_server_exceptions=False).get(url)

    assert response.status_code == status, response.text
    if seen_id is not None:
        assert response.json()["id"] == seen_id
    assert _results(sink) == sorted(audit)


def test_path_and_query_ids_are_read_by_the_declared_name_and_loaded_once(loads):
    sink = MemoryAuthorizationAuditSink()
    client = TestClient(_app(STUDENT, sink))

    assert client.get("/students/student-1/thing").json()["value"] == {
        "user_id": "student-1",
        "role": "student",
    }
    client.get("/thing?studentId=student-1")
    assert loads == [("student-1", "student-1"), ("student-1", "student-1")]


def test_self_and_operator_hand_the_handler_the_actor(loads):
    sink = MemoryAuthorizationAuditSink()
    assert TestClient(_app(STUDENT, sink)).get("/me/thing").json() == {"actor": "student-1"}
    assert TestClient(_app(REVIEWER, sink)).get("/operate").json() == {"actor": "admin-1"}
    assert loads == []


@pytest.mark.asyncio
async def test_an_absent_path_value_is_a_program_error_never_the_actor(loads, caplog):
    dependency = authorized(
        ResourceType.STUDENT,
        AuthorizationAction.READ,
        path("student_id"),
        STUDENT_READ,
        kind=TEST_KIND,
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/students/student-1/thing",
            "path_params": {},
            "query_string": b"",
            "headers": [],
        }
    )
    sink = MemoryAuthorizationAuditSink()
    context = declared.AuthorizationContext(
        facts=_Facts(),
        policy=declared.AuthorizationPolicy(),
        correlation_id="absent-path-value",
        audit_sink=sink,
    )

    with caplog.at_level(logging.ERROR), pytest.raises(AuthorizationDeclarationError):
        await dependency(request=request, actor=STUDENT, context=context, student_id="student-1")

    assert loads == []
    assert "student_id" in caplog.text
    assert _results(sink) == [("student", "action_not_allowed", "declaration_error")]


def test_a_path_name_missing_from_the_route_never_reaches_the_handler(loads):
    """FastAPI refuses the request; the inventory gate refuses the route."""
    sink = MemoryAuthorizationAuditSink()
    app = FastAPI()

    @app.get("/children/{kid_id}/thing")
    async def misnamed(
        resource: AuthorizedResource = Depends(
            authorized(
                ResourceType.STUDENT,
                AuthorizationAction.READ,
                path("child_id"),
                STUDENT_READ,
                kind=TEST_KIND,
            )
        ),
    ):
        return {"id": resource.ref.resource_id}

    app.dependency_overrides[get_actor] = lambda: STUDENT
    app.dependency_overrides[get_authorization_audit_sink] = lambda: sink

    assert TestClient(app).get("/children/student-1/thing").status_code == 422
    assert loads == []
    failures = validate_application_inventory(app)
    assert [failure.reason for failure in failures] == [
        "declared path identifier child_id is not a parameter of the route path"
    ]


def test_a_query_name_that_is_a_path_parameter_cannot_be_registered(loads):
    app = FastAPI()
    dependency = authorized(
        ResourceType.STUDENT,
        AuthorizationAction.READ,
        query("studentId"),
        STUDENT_READ,
        kind=TEST_KIND,
    )

    with pytest.raises(AssertionError, match="Cannot use `Query` for path param"):

        @app.get("/students/{studentId}/thing")
        async def misdeclared(resource: AuthorizedResource = Depends(dependency)):
            return {}


def test_the_inventory_reads_the_declaration(loads):
    app = _app(STUDENT, MemoryAuthorizationAuditSink())
    items = {(item.method, item.path): item for item in inventory_application(app)}

    by_path = items[("GET", "/students/{student_id}/thing")]
    assert by_path.classification == "authorized"
    assert by_path.identifiers == ("student_id",)
    assert [(s.resource_type, s.action, s.purpose) for s in by_path.authorization_specs] == [
        ("student", "read", "parent_oversight"),
        ("student", "read", "self_service"),
    ]
    assert items[("GET", "/thing")].identifiers == ("studentId",)
    operator_item = items[("GET", "/operate")]
    assert [(s.purpose, s.capability) for s in operator_item.authorization_specs] == [
        ("identity_management", "teacher_identity_reviewer")
    ]


def test_service_enforced_routes_name_where_the_check_is():
    app = FastAPI()

    @app.post("/uploads")
    async def start_upload(
        actor: Actor = Depends(
            service_enforced(
                "uploads.start",
                ResourceType.UPLOAD,
                AuthorizationAction.CREATE,
                {CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE},
            )
        ),
    ):
        return {"actor": actor.user_id}

    app.dependency_overrides[get_actor] = lambda: STUDENT
    assert TestClient(app).post("/uploads").json() == {"actor": "student-1"}
    [item] = inventory_application(app)
    assert item.classification == "service-enforced"
    assert item.projection()["serviceEnforced"] == "uploads.start"
    assert [(s.resource_type, s.action, s.purpose) for s in item.authorization_specs] == [
        ("upload", "create", "self_service")
    ]


def test_a_type_without_a_registered_loader_cannot_be_declared():
    with pytest.raises(LookupError):
        authorized(
            ResourceType.NOTIFICATION_EVENT,
            AuthorizationAction.READ,
            path("event_id"),
            {CanonicalRole.STUDENT: AuthorizationPurpose.NOTIFICATION_SELF_SERVICE},
        )


def test_a_loader_is_registered_once():
    async def load(_resource_id, _actor):
        return None

    with pytest.raises(ValueError):
        declared.register_resource_loader(ResourceType.STUDENT, load)


@pytest.mark.asyncio
async def test_authorize_loaded_decides_on_the_object_the_caller_already_has():
    sink = MemoryAuthorizationAuditSink()
    context = declared.AuthorizationContext(
        facts=_Facts(),
        policy=declared.AuthorizationPolicy(),
        correlation_id="loaded-1",
        audit_sink=sink,
    )
    item = {"student_id": "student-1", "title": "fractions"}
    ref = ResourceRef(ResourceType.ADAPTIVE_PROFILE, "assignment-1", "student-1")

    resolved = await authorize_loaded(
        PARENT, ref, item, AuthorizationAction.READ, STUDENT_READ, context
    )
    assert resolved.value is item and resolved.ref == ref

    with pytest.raises(SecurityDecisionError) as missing:
        await authorize_loaded(
            STUDENT, ref, None, AuthorizationAction.READ, STUDENT_READ, context
        )
    assert missing.value.code is SecurityErrorCode.RESOURCE_NOT_FOUND

    with pytest.raises(SecurityDecisionError) as undeclared:
        await authorize_loaded(
            TEACHER, ref, item, AuthorizationAction.READ, STUDENT_READ, context
        )
    assert undeclared.value.code is SecurityErrorCode.ACTION_NOT_ALLOWED
    assert _results(sink) == sorted(
        [
            ("adaptive_profile", "allowed", "policy"),
            ("adaptive_profile", "resource_not_found", "resolver"),
            ("adaptive_profile", "action_not_allowed", "role_not_declared"),
        ]
    )


@pytest.mark.parametrize(
    "actor,owner,allowed",
    [
        (PARENT, "parent-1", True),
        (PARENT, "parent-2", False),
        (STUDENT, "student-1", True),
        (TEACHER, "teacher-1", False),
    ],
)
def test_a_parent_acts_on_their_own_parent_binding_account(actor, owner, allowed):
    """`_parent_account_dependency` only checked the role before #348."""
    decision = declared.AuthorizationPolicy().evaluate(
        actor,
        AuthorizedResource(
            ResourceRef(ResourceType.PARENT_BINDING, owner, owner, owner_id=owner), {}
        ),
        AuthorizationAction.READ,
        AuthorizationPurpose.SELF_SERVICE,
    )
    assert decision.allowed is allowed


@pytest.mark.parametrize(
    "actor,status,audit",
    [
        (PARENT, 200, [("parent_binding", "allowed", "direct_policy")]),
        (STUDENT, 403, [("parent_binding", "action_not_allowed", "role_not_declared")]),
        (TEACHER, 403, [("parent_binding", "action_not_allowed", "role_not_declared")]),
    ],
)
def test_the_parent_account_routes_ask_the_policy_and_record_it(actor, status, audit):
    """Before #348 `_parent_account_dependency` only compared the role."""
    from stoa.routers import parents

    sink = MemoryAuthorizationAuditSink()
    app = FastAPI()

    @app.get("/parents/me/thing")
    async def own(me: Actor = Depends(parents._parent_account_read)):
        return {"actor": me.user_id}

    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_audit_sink] = lambda: sink

    assert TestClient(app).get("/parents/me/thing").status_code == status
    assert _results(sink) == audit
