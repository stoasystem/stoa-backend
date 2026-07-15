from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
import pytest

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.main import app as main_app
from stoa.routers import admin, notifications
from stoa.db.repositories import report_repo
from stoa.security.admin_authorization import admin_operation, classify_admin_route
from stoa.security.authorization import ResourceRef, operator_capability_permits, project_support_lookup
from stoa.security.identity import AccountStatus, Actor, CanonicalRole, CapabilityGrant
from stoa.services import notification_service


def _actor(*capabilities: str, scope: str = "global") -> Actor:
    return Actor(
        "admin-1",
        "https://identity.test",
        "admin-subject",
        CanonicalRole.ADMIN,
        AccountStatus.ACTIVE,
        "admin",
        tuple(CapabilityGrant(capability, scope, 1) for capability in capabilities),
    )


def _actor_with_grants(capability: str, *scopes: str) -> Actor:
    actor = _actor(capability)
    return Actor(
        actor.user_id, actor.issuer, actor.subject, actor.role, actor.account_status,
        actor.cognito_group,
        tuple(CapabilityGrant(capability, scope, index + 1) for index, scope in enumerate(scopes)),
    )


def _registered_admin_routes() -> list[tuple[str, str, APIRoute]]:
    rows = []
    for route in main_app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/admin"):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            rows.append((method, route.path, route))
    return rows


REGISTERED_ADMIN_ROUTES = _registered_admin_routes()


@pytest.mark.parametrize("method,path,route", REGISTERED_ADMIN_ROUTES)
def test_registered_admin_router_has_exact_executable_policy_and_controls(method, path, route):
    policy = classify_admin_route(method, path)
    assert policy.capability
    assert policy.purpose.value
    assert policy.action.value
    assert sum(dep.call is admin_operation for dep in route.dependant.dependencies) == 1

    ref = ResourceRef(policy.resource_type, "global", "admin-1", relationship_known=True)
    assert operator_capability_permits(
        _actor(policy.capability),
        capability=policy.capability,
        resource=ref,
        action=policy.action,
        purpose=policy.purpose,
    )
    assert not operator_capability_permits(
        _actor("wrong_capability"),
        capability=policy.capability,
        resource=ref,
        action=policy.action,
        purpose=policy.purpose,
    )


def test_registered_admin_router_table_is_complete_across_main_registrations():
    keys = [(method, path) for method, path, _route in REGISTERED_ADMIN_ROUTES]
    assert len(keys) == len(set(keys)) == 109
    assert ("GET", "/admin/notifications") in keys
    assert ("GET", "/admin/notifications/delivery-status") in keys
    assert all(classify_admin_route(method, path) for method, path in keys)


def test_identity_user_usage_subscription_binding_and_curriculum_capabilities_are_distinct():
    expected = {
        ("POST", "/admin/privileged-identities/admins"): "admin_identity_manager",
        ("GET", "/admin/users"): "student_support_lookup",
        ("GET", "/admin/usage/students/{student_id}/events"): "usage_event_inspector",
        ("POST", "/admin/subscriptions/billing/{parent_id}/refunds"): "billing_refund_executor",
        ("POST", "/admin/parent-bindings/repair"): "parent_binding_repairer",
        ("POST", "/admin/curriculum/lessons/{public_lesson_id}/publish"): "curriculum_publisher",
    }
    assert {
        key: classify_admin_route(*key).capability
        for key in expected
    } == expected


def test_support_lookup_projection_is_d15_only():
    projection = project_support_lookup(
        account={"account_status": "active", "email": "secret@example.test", "answers": ["secret"]},
        binding={"status": "active", "report": "private"},
        denial_code="none",
        correlation_id="corr-1",
        support_id="support-1",
    )
    assert set(projection) == {"accountState", "bindingState", "denialCode", "correlationId", "supportId"}
    assert "secret" not in repr(projection)


def test_report_metadata_content_recovery_export_and_send_capabilities_are_distinct():
    expected = {
        ("GET", "/admin/reports/{parent_id}/{student_id}/{week_start}/ops"): "report_metadata_reader",
        ("GET", "/admin/reports/{parent_id}/{student_id}/{week_start}/artifact-edit-previews/{draft_id}"): "report_recovery_reader",
        ("POST", "/admin/reports/{parent_id}/{student_id}/{week_start}/resend"): "report_recovery_operator",
        ("GET", "/admin/reports/recovery-evidence"): "report_evidence_exporter",
        ("POST", "/admin/reports/support-handoff-delivery"): "report_external_handoff_sender",
        ("POST", "/admin/reports/legal-holds"): "report_governance_manager",
    }
    assert {key: classify_admin_route(*key).capability for key in expected} == expected


def test_report_target_scope_denies_before_lookup_or_mutation(monkeypatch):
    calls = []
    monkeypatch.setattr(
        report_repo,
        "get_report_for_child_by_week",
        lambda *args: calls.append(args),
    )
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    app.dependency_overrides[get_actor] = lambda: _actor(
        "report_metadata_reader", scope="student:student-other"
    )
    response = TestClient(app).get(
        "/admin/reports/parent-1/student-1/2026-06-01/ops"
    )
    assert response.status_code == 403
    assert calls == []


def test_parent_binding_body_target_exact_scope_allows_before_mutation(monkeypatch):
    calls = []
    monkeypatch.setattr(user_repo := admin.user_repo, "get_user", lambda value: {
        "user_id": value, "role": "parent" if value.startswith("parent") else "student"
    })
    monkeypatch.setattr(user_repo, "update_student_parent_link", lambda *args: calls.append(("link", args)))
    monkeypatch.setattr(user_repo, "put_parent_student_binding", lambda **values: calls.append(("binding", values)) or values)
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    app.dependency_overrides[get_actor] = lambda: _actor("parent_binding_repairer", scope="student:student-1")
    response = TestClient(app).post("/admin/parent-bindings/repair", json={
        "parent_id": "parent-1", "student_id": "student-1", "relationship": "child", "reason": "repair"
    })
    assert response.status_code == 200
    assert [kind for kind, _ in calls] == ["link", "binding"]


def test_bulk_body_targets_are_all_of_and_duplicate_safe(monkeypatch):
    mutations = []
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda *args: mutations.append(("lookup", args)) or {
        "report_id": "report-1", "parent_id": args[0], "student_id": args[1], "week_start": args[2]
    })
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    app.dependency_overrides[get_actor] = lambda: _actor_with_grants(
        "report_recovery_operator", "student:student-1"
    )
    client = TestClient(app)
    payload = {"reports": [
        {"parent_id": "parent-1", "student_id": "student-1", "week_start": "2026-06-01"},
        {"parent_id": "parent-2", "student_id": "student-2", "week_start": "2026-06-08"},
    ]}
    assert client.post("/admin/reports/bulk-resend", json=payload).status_code == 403
    assert mutations == []
    duplicate = {"reports": [payload["reports"][0], payload["reports"][0]]}
    assert client.post("/admin/reports/bulk-resend", json=duplicate).status_code == 403
    assert mutations == []


def test_bulk_body_targets_persist_every_allow_before_first_effect(monkeypatch):
    sink = MemoryAuthorizationAuditSink()
    effects = []
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda *args: effects.append(args) or None)
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_authorization_audit_sink] = lambda: sink
    app.dependency_overrides[get_actor] = lambda: _actor_with_grants(
        "report_recovery_operator", "student:student-1", "student:student-2"
    )
    reports = [
        {"parent_id": "parent-1", "student_id": "student-1", "week_start": "2026-06-01"},
        {"parent_id": "parent-2", "student_id": "student-2", "week_start": "2026-06-08"},
    ]
    response = TestClient(app).post("/admin/reports/bulk-resend", json={"reports": reports})
    assert response.status_code == 200
    assert len(effects) == len(sink.events) == 2
    assert len({row["resource_fingerprint"] for row in sink.events.values()}) == 2


def test_later_body_target_audit_failure_prevents_entire_bulk_effect(monkeypatch):
    class FailSecondSink(MemoryAuthorizationAuditSink):
        def persist_authorization_decision(self, **values):
            if len(self.events) == 1:
                raise RuntimeError("later-audit-outage")
            return super().persist_authorization_decision(**values)

    effects = []
    sink = FailSecondSink()
    monkeypatch.setattr(report_repo, "get_report_for_child_by_week", lambda *args: effects.append(args))
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_authorization_audit_sink] = lambda: sink
    app.dependency_overrides[get_actor] = lambda: _actor("report_recovery_operator")
    reports = [
        {"parent_id": "parent:a", "student_id": "student-1", "week_start": "b"},
        {"parent_id": "parent", "student_id": "student-1", "week_start": "a:b"},
    ]
    response = TestClient(app).post("/admin/reports/bulk-resend", json={"reports": reports})
    assert response.status_code == 503
    assert effects == []


def test_recovery_job_identifier_is_resolved_and_outage_fails_before_cancel(monkeypatch):
    mutations = []
    monkeypatch.setattr(
        admin.report_recovery_job_service,
        "cancel_recovery_job",
        lambda *args, **kwargs: mutations.append((args, kwargs)),
    )
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    app.dependency_overrides[get_actor] = lambda: _actor("report_recovery_operator")

    monkeypatch.setattr(report_repo, "get_recovery_job", lambda job_id: None)
    assert TestClient(app).post("/admin/reports/recovery-jobs/missing/cancel").status_code == 404
    monkeypatch.setattr(
        report_repo,
        "get_recovery_job",
        lambda job_id: (_ for _ in ()).throw(RuntimeError("store unavailable")),
    )
    response = TestClient(app).post("/admin/reports/recovery-jobs/job-1/cancel")
    assert response.status_code == 503
    assert mutations == []


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/admin/reports/bulk-resend"),
        ("GET", "/admin/reports/recovery-evidence"),
        ("POST", "/admin/reports/support-handoff-delivery"),
        ("POST", "/admin/reports/immutable-evidence/persist"),
        ("POST", "/admin/reports/legal-holds"),
    ],
)
def test_report_bulk_export_send_persist_and_hold_reject_break_glass(method, path):
    policy = classify_admin_route(method, path)
    ref = ResourceRef(policy.resource_type, "global", "admin-1", relationship_known=True)
    assert not operator_capability_permits(
        _actor("student_data_break_glass"),
        capability=policy.capability,
        resource=ref,
        action=policy.action,
        purpose=policy.purpose,
    )


def test_admin_role_and_break_glass_cannot_provision_privilege(monkeypatch):
    calls = []
    monkeypatch.setattr(admin.privileged_identity_service, "provision_admin", lambda **kwargs: calls.append(kwargs))
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    app.dependency_overrides[get_actor] = lambda: _actor("student_data_break_glass")
    response = TestClient(app).post(
        "/admin/privileged-identities/admins",
        json={
            "command_id": "command-1",
            "target_email": "target@example.test",
            "issuer": "https://identity.test",
            "subject": "target-subject",
            "reason": "approved command",
        },
    )
    assert response.status_code == 403
    assert calls == []


@pytest.mark.parametrize(
    "path,capability,wrong",
    [
        ("/admin/notifications", "notification_event_inspector", "notification_delivery_health_reader"),
        ("/admin/notifications/delivery-status", "notification_delivery_health_reader", "notification_event_inspector"),
    ],
)
def test_notification_admin_routes_require_distinct_exact_capabilities(monkeypatch, path, capability, wrong):
    monkeypatch.setattr(notification_service, "list_admin_events", lambda **kwargs: [])
    monkeypatch.setattr(
        notification_service,
        "delivery_status",
        lambda **kwargs: {
            "websocketConfigured": False,
            "websocketMode": "disabled",
            "preferenceCategories": [],
            "preferenceChannels": [],
            "recentEventCount": 0,
            "categoryCounts": {},
            "realtimeDecisionCounts": {},
        },
    )
    app = FastAPI()
    app.include_router(notifications.admin_router, prefix="/admin")
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    app.dependency_overrides[get_actor] = lambda: _actor(wrong)
    assert TestClient(app).get(path).status_code == 403
    app.dependency_overrides[get_actor] = lambda: _actor()
    assert TestClient(app).get(path).status_code == 403
    app.dependency_overrides[get_actor] = lambda: _actor("student_data_break_glass")
    assert TestClient(app).get(path).status_code == 403
    app.dependency_overrides[get_actor] = lambda: _actor(capability)
    assert TestClient(app).get(path).status_code == 200
