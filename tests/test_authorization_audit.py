"""Durable, redacted authorization-decision and probe evidence."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Response
from fastapi.testclient import TestClient
import pytest

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.config import DEVELOPMENT_AUDIT_KEY, Settings
from stoa.db.repositories import security_audit_repo
from stoa.db.repositories.security_audit_repo import DynamoAuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import notifications
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationFacts,
    AuthorizationPolicy,
    AuthorizationPurpose,
    AuthorizedResource,
    BreakGlassEvidence,
    ParentAuthorizationFacts,
    PolicyDecision,
    ResourceRef,
    ResourceType,
    record_authorization_decision,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import AccountStatus, Actor, CanonicalRole, CapabilityGrant
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.route_authorization import (
    STUDENT_CONTENT_READ,
    authorized_student_dependency,
    get_authorization_fact_repository,
)
from stoa.services import notification_service


def _actor(role: CanonicalRole, user_id: str, *capabilities: str) -> Actor:
    return Actor(
        user_id,
        "https://identity.test",
        f"{user_id}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
        tuple(CapabilityGrant(value, "global", 1) for value in capabilities),
    )


def _decision(allowed: bool, correlation_id: str = "request-1") -> PolicyDecision:
    return PolicyDecision(
        allowed,
        SecurityErrorCode.ACTION_NOT_ALLOWED,
        correlation_id=correlation_id,
    )


@pytest.mark.parametrize("inbound", ["caller-reused", "authorization"])
def test_correlation_is_server_generated_cached_and_returned(inbound):
    app = FastAPI()

    @app.get("/correlation")
    def endpoint(
        request: Request,
        response: Response,
        first: str = Depends(get_request_correlation_id),
        second: str = Depends(get_request_correlation_id),
    ):
        return {"first": first, "second": second, "state": request.state.stoa_correlation_id}

    first = TestClient(app).get("/correlation", headers={"X-Correlation-ID": inbound})
    second = TestClient(app).get("/correlation", headers={"X-Correlation-ID": inbound})
    assert first.status_code == 200
    assert first.json()["first"] == first.json()["second"] == first.json()["state"]
    assert first.headers["X-Correlation-ID"] == first.json()["first"]
    assert first.json()["first"] not in {inbound, "authorization"}
    assert second.json()["first"] != first.json()["first"]


@pytest.mark.asyncio
async def test_denial_persists_redacted_distinct_resource_events_and_idempotent_replay():
    sink = MemoryAuthorizationAuditSink()
    actor = _actor(CanonicalRole.PARENT, "parent-canary@example.test")
    common = dict(
        actor=actor,
        action=AuthorizationAction.READ,
        purpose=AuthorizationPurpose.PARENT_OVERSIGHT,
        decision=_decision(False),
        correlation_id="request-1",
        audit_sink=sink,
    )
    first = ResourceRef(ResourceType.STUDENT, "student-secret-1", "student-secret-1")
    second = ResourceRef(ResourceType.STUDENT, "student-secret-2", "student-secret-2")
    await record_authorization_decision(resource=first, **common)
    await record_authorization_decision(resource=first, **common)
    await record_authorization_decision(resource=second, **common)
    assert len(sink.events) == 2
    assert next(iter(sink.aggregates.values()))["count"] == 2
    fingerprints = {row["resource_fingerprint"] for row in sink.events.values()}
    assert len(fingerprints) == 2
    rendered = repr((sink.events, sink.aggregates))
    for canary in ("student-secret-1", "student-secret-2", "@example.test"):
        assert canary not in rendered


@pytest.mark.asyncio
async def test_separate_requests_for_same_resource_aggregate_but_have_distinct_events():
    sink = MemoryAuthorizationAuditSink()
    actor = _actor(CanonicalRole.PARENT, "parent-1")
    resource = ResourceRef(ResourceType.STUDENT, "student-1", "student-1")
    for correlation_id in ("request-a", "request-b"):
        await record_authorization_decision(
            actor=actor,
            resource=resource,
            action=AuthorizationAction.READ,
            purpose=AuthorizationPurpose.PARENT_OVERSIGHT,
            decision=_decision(False, correlation_id),
            correlation_id=correlation_id,
            audit_sink=sink,
        )
    assert len(sink.events) == 2
    assert len(sink.aggregates) == 1
    assert next(iter(sink.aggregates.values()))["count"] == 2


@pytest.mark.asyncio
async def test_audit_outage_preserves_denial_but_blocks_mandatory_allow():
    sink = MemoryAuthorizationAuditSink(fail=True)
    parent = _actor(CanonicalRole.PARENT, "parent-1")
    resource = ResourceRef(ResourceType.STUDENT, "student-1", "student-1")
    denied = await record_authorization_decision(
        actor=parent,
        resource=resource,
        action=AuthorizationAction.READ,
        purpose=AuthorizationPurpose.PARENT_OVERSIGHT,
        decision=_decision(False, "request-denied"),
        correlation_id="request-denied",
        audit_sink=sink,
    )
    assert not denied.allowed
    with pytest.raises(SecurityDecisionError) as unavailable:
        await record_authorization_decision(
            actor=parent,
            resource=resource,
            action=AuthorizationAction.READ,
            purpose=AuthorizationPurpose.PARENT_OVERSIGHT,
            decision=_decision(True, "request-allow"),
            correlation_id="request-allow",
            audit_sink=sink,
        )
    assert unavailable.value.code is SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE
    assert unavailable.value.correlation_id == "request-allow"
    assert "audit-outage-canary" not in repr(unavailable.value.public_body())


@pytest.mark.asyncio
async def test_owner_self_allow_is_optional_evidence_during_outage():
    actor = _actor(CanonicalRole.STUDENT, "student-1")
    decision = await record_authorization_decision(
        actor=actor,
        resource=ResourceRef(ResourceType.PRACTICE, "lesson-1", "student-1"),
        action=AuthorizationAction.READ,
        purpose=AuthorizationPurpose.SELF_SERVICE,
        decision=_decision(True),
        correlation_id="owner-request",
        audit_sink=MemoryAuthorizationAuditSink(fail=True),
    )
    assert decision.allowed


class _MemoryTable:
    def __init__(self):
        self.rows = {}

    def get_item(self, *, Key, **_kwargs):
        return {"Item": self.rows.get((Key["PK"], Key["SK"]))}

    def put_item(self, *, Item, ConditionExpression=None, **_kwargs):
        key = (Item["PK"], Item["SK"])
        existing = self.rows.get(key)
        expected = (_kwargs.get("ExpressionAttributeValues") or {}).get(":expected_version")
        conflict = bool(
            ConditionExpression
            and (
                ("attribute_not_exists" in ConditionExpression and existing is not None)
                or ("probe_version" in ConditionExpression and (existing or {}).get("probe_version") != expected)
            )
        )
        if conflict:
            error = {"Error": {"Code": "ConditionalCheckFailedException"}}
            from botocore.exceptions import ClientError

            raise ClientError(error, "PutItem")
        self.rows[key] = dict(Item)
        return {}


def test_dynamo_sink_rotation_recognizes_old_key_replay_and_redacts(monkeypatch):
    table = _MemoryTable()
    monkeypatch.setattr(security_audit_repo, "get_table", lambda: table)
    values = dict(
        correlation_id="request-rotation",
        actor_id="parent-1",
        actor_role="parent",
        policy_version="472.v1",
        resource_type="student",
        resource_id="student-rotation-canary",
        student_id="student-rotation-canary",
        owner_id=None,
        scope_discriminator="",
        action="read",
        purpose="parent_oversight",
        result="action_not_allowed",
        decision_kind="policy",
        evidence_reference=None,
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    old = DynamoAuthorizationAuditSink(active_key_id="old-v1", active_secret="old-secret")
    old_record = old.persist_authorization_decision(**values)
    rotated = DynamoAuthorizationAuditSink(
        active_key_id="new-v2",
        active_secret="new-secret",
        previous_keys={"old-v1": "old-secret"},
    )
    replay = rotated.persist_authorization_decision(**values)
    assert replay.replayed and replay.event_id == old_record.event_id
    assert len(table.rows) == 1
    assert "student-rotation-canary" not in repr(table.rows)
    assert "old-secret" not in repr(table.rows)


def test_dynamo_probe_aggregate_is_one_bounded_redacted_window(monkeypatch):
    table = _MemoryTable()
    monkeypatch.setattr(security_audit_repo, "get_table", lambda: table)
    sink = DynamoAuthorizationAuditSink(
        active_key_id="test-v1",
        active_secret="test-secret",
        probe_count_cap=2,
        probe_id_cap=3,
    )
    for index in range(4):
        record = sink.persist_authorization_decision(
            correlation_id=f"request-{index}",
            actor_id="parent-probe@example.test",
            actor_role="parent",
            policy_version="472.v1",
            resource_type="student",
            resource_id=f"guessed-student-{index}",
            student_id=f"guessed-student-{index}",
            owner_id=None,
            scope_discriminator="",
            action="read",
            purpose="parent_oversight",
            result="resource_not_found",
            decision_kind="policy",
            evidence_reference=None,
        )
        sink.aggregate_authorization_probe(
            record=record,
            actor_id="parent-probe@example.test",
            resource_type="student",
            action="read",
            purpose="parent_oversight",
            result="resource_not_found",
            policy_version="472.v1",
        )
    aggregate_rows = [
        row for row in table.rows.values()
        if row.get("entity_type") == "authorization_probe_aggregate"
    ]
    assert len(aggregate_rows) == 1
    assert aggregate_rows[0]["probe_count"] == 2
    assert len(aggregate_rows[0]["decision_event_ids"]) == 2
    rendered = repr(aggregate_rows)
    assert "guessed-student" not in rendered
    assert "@example.test" not in rendered


def test_production_requires_non_placeholder_audit_key():
    with pytest.raises(ValueError, match="authorization audit key"):
        Settings(
            environment="production",
            cognito_allowed_issuers=["https://identity.test"],
            cognito_access_client_ids=["client-1"],
            authorization_audit_active_key=DEVELOPMENT_AUDIT_KEY,
        )


def test_all_production_authorization_call_sites_use_recording_gateway():
    roots = [Path("src/stoa/security/route_authorization.py"), *Path("src/stoa/routers").glob("*.py")]
    missing = []
    for path in roots:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                calls = [child for child in ast.walk(node) if isinstance(child, ast.Call)]
                for call in calls:
                    if isinstance(call.func, ast.Name) and call.func.id == "authorize_and_resolve":
                        keywords = {item.arg for item in call.keywords}
                        if not {"correlation_id", "audit_sink"} <= keywords:
                            missing.append(f"{path}:{call.lineno}:authorize_and_resolve")
                    if (
                        isinstance(call.func, ast.Name)
                        and call.func.id == "authorize_teacher_loaded_resource"
                    ):
                        keywords = {item.arg for item in call.keywords}
                        if not {"correlation_id", "audit_sink"} <= keywords:
                            missing.append(
                                f"{path}:{call.lineno}:authorize_teacher_loaded_resource"
                            )
                has_evaluate = any(
                    isinstance(call.func, ast.Attribute) and call.func.attr == "evaluate"
                    for call in calls
                )
                has_gateway = any(
                    isinstance(call.func, ast.Name)
                    and call.func.id in {"record_authorization_decision", "_record_or_raise"}
                    for call in calls
                )
                if has_evaluate and not has_gateway and path.name != "authorization.py":
                    missing.append(f"{path}:{node.lineno}:direct-evaluate")
    admin_source = Path("src/stoa/security/admin_authorization.py").read_text()
    assert "_record_admin_decision" in admin_source and "operator_capability_decision" in admin_source
    assert not missing


def test_real_admin_dependency_uses_one_correlation_for_response_and_evidence(monkeypatch):
    sink = MemoryAuthorizationAuditSink()
    monkeypatch.setattr(notification_service, "list_admin_events", lambda **_kwargs: [])
    app = FastAPI()
    app.include_router(notifications.admin_router, prefix="/admin")
    app.dependency_overrides[get_actor] = lambda: _actor(
        CanonicalRole.ADMIN, "admin-1", "notification_event_inspector"
    )
    app.dependency_overrides[get_authorization_audit_sink] = lambda: sink
    response = TestClient(app).get("/admin/notifications")
    assert response.status_code == 200
    correlation_id = response.headers["X-Correlation-ID"]
    assert {row["correlation_id"] for row in sink.events.values()} == {correlation_id}


def test_real_admin_mandatory_allow_outage_returns_safe_correlated_503(monkeypatch):
    effects = []
    monkeypatch.setattr(notification_service, "list_admin_events", lambda **_kwargs: effects.append(True))
    app = FastAPI()
    app.include_router(notifications.admin_router, prefix="/admin")
    app.dependency_overrides[get_actor] = lambda: _actor(
        CanonicalRole.ADMIN, "admin-1", "notification_event_inspector"
    )
    app.dependency_overrides[get_authorization_audit_sink] = lambda: MemoryAuthorizationAuditSink(fail=True)
    response = TestClient(app).get("/admin/notifications")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "authorization_temporarily_unavailable"
    assert response.headers["X-Correlation-ID"] == response.json()["detail"]["correlationId"]
    assert "audit-outage-canary" not in response.text
    assert effects == []


def _generated_student_app(monkeypatch, *, sink, facts):
    from stoa.db.repositories import user_repo

    monkeypatch.setattr(
        user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "role": "student", "account_status": "active"},
    )
    effects = []
    app = FastAPI()
    dependency = authorized_student_dependency(
        action=AuthorizationAction.READ,
        purposes=STUDENT_CONTENT_READ,
    )

    @app.get("/students/{student_id}")
    def handler(_resource=Depends(dependency)):
        effects.append(True)
        return {"ok": True}

    app.dependency_overrides[get_actor] = lambda: _actor(CanonicalRole.PARENT, "parent-1")
    app.dependency_overrides[get_authorization_fact_repository] = lambda: facts
    app.dependency_overrides[get_authorization_audit_sink] = lambda: sink
    return app, effects


def test_generated_denial_outage_preserves_hidden_error_and_zero_handler_effect(monkeypatch):
    class NoRelationship:
        async def facts_for(self, *_args):
            return AuthorizationFacts()

    app, effects = _generated_student_app(
        monkeypatch,
        sink=MemoryAuthorizationAuditSink(fail=True),
        facts=NoRelationship(),
    )
    response = TestClient(app).get("/students/student-hidden-canary")
    assert response.status_code == 404
    assert response.headers["X-Correlation-ID"] == response.json()["detail"]["correlationId"]
    assert "canary" not in response.text
    assert effects == []


def test_generated_parent_allow_outage_returns_503_before_handler(monkeypatch):
    row = {
        "parent_id": "parent-1",
        "student_id": "student-1",
        "relationship": "child",
        "version": 1,
        "status": "active",
    }

    class ActiveRelationship:
        async def facts_for(self, *_args):
            return AuthorizationFacts(
                parent=ParentAuthorizationFacts(
                    row,
                    dict(row),
                    {"user_id": "parent-1", "role": "parent", "account_status": "active"},
                    {"user_id": "student-1", "role": "student", "account_status": "active"},
                )
            )

    app, effects = _generated_student_app(
        monkeypatch,
        sink=MemoryAuthorizationAuditSink(fail=True),
        facts=ActiveRelationship(),
    )
    response = TestClient(app).get("/students/student-1")
    assert response.status_code == 503
    assert response.headers["X-Correlation-ID"] == response.json()["detail"]["correlationId"]
    assert effects == []


@pytest.mark.asyncio
async def test_break_glass_positive_requires_working_sink():
    now = datetime(2026, 7, 15, tzinfo=UTC)
    actor = Actor(
        "admin-1",
        "https://identity.test",
        "admin-subject",
        CanonicalRole.ADMIN,
        AccountStatus.ACTIVE,
        "admin",
        (CapabilityGrant("student_data_break_glass", "student:student-1", 1),),
    )
    resource = AuthorizedResource(
        ResourceRef(ResourceType.STUDENT, "student-1", "student-1"),
        {"student_id": "student-1"},
        AuthorizationFacts(
            break_glass=BreakGlassEvidence(
                "incident-1",
                "urgent safety review",
                "notification-1",
                "review-1",
                now,
                now.replace(minute=now.minute + 10),
            )
        ),
    )
    decision = AuthorizationPolicy(clock=lambda: now).evaluate(
        actor,
        resource,
        AuthorizationAction.READ,
        AuthorizationPurpose.INCIDENT_BREAK_GLASS,
        correlation_id="break-glass-request",
    )
    sink = MemoryAuthorizationAuditSink()
    recorded = await record_authorization_decision(
        actor=actor,
        resource=resource.ref,
        action=AuthorizationAction.READ,
        purpose=AuthorizationPurpose.INCIDENT_BREAK_GLASS,
        decision=decision,
        correlation_id="break-glass-request",
        audit_sink=sink,
    )
    assert recorded.allowed
    assert len(sink.events) == 1


def test_missing_audit_key_creates_fail_closed_sink():
    sink = get_authorization_audit_sink(
        Settings(
            authorization_audit_active_key_id="",
            authorization_audit_active_key="",
        )
    )
    with pytest.raises(Exception, match="authorization_audit_key_unavailable"):
        sink.persist_authorization_decision()
