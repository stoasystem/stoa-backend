from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
import pytest

from stoa.deps import get_actor
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
    app.dependency_overrides[get_actor] = lambda: _actor(
        "report_metadata_reader", scope="student:student-other"
    )
    response = TestClient(app).get(
        "/admin/reports/parent-1/student-1/2026-06-01/ops"
    )
    assert response.status_code == 403
    assert calls == []


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
    app.dependency_overrides[get_actor] = lambda: _actor(wrong)
    assert TestClient(app).get(path).status_code == 403
    app.dependency_overrides[get_actor] = lambda: _actor()
    assert TestClient(app).get(path).status_code == 403
    app.dependency_overrides[get_actor] = lambda: _actor("student_data_break_glass")
    assert TestClient(app).get(path).status_code == 403
    app.dependency_overrides[get_actor] = lambda: _actor(capability)
    assert TestClient(app).get(path).status_code == 200
