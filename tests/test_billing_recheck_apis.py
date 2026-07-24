"""Closed parent/admin checkout status and same-command recheck APIs."""

from __future__ import annotations

import inspect
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from stoa.config import Settings, get_settings
from stoa.db.repositories import checkout_command_repo
from stoa.main import app as main_app
from stoa.models.billing import CheckoutCommandState
from stoa.routers import admin, parents
from stoa.services import billing_reconciliation_service, subscription_service


CHECKOUT_REF = "co_abcdefghijklmnopqrstuvwxyzABCDEFGH"
OTHER_REF = "co_HGFEDCBAzyxwvutsrqponmlkjihgfedc"
PARENT_ID = "parent-private-canary"
OTHER_PARENT_ID = "other-parent-private-canary"
SESSION_ID = "cs_test_parent_recheck_123456789"


def _settings() -> Settings:
    return Settings(
        environment="test",
        stripe_api_key="sk_test_private_canary",
        stripe_student_price_id="price_test_student",
        stripe_teacher_supported_price_id="price_test_teacher",
        stripe_family_price_id="price_test_family",
        stripe_checkout_web_origins=["http://localhost:5173"],
    )


def _command(
    *,
    parent_id: str = PARENT_ID,
    checkout_ref: str = CHECKOUT_REF,
    state: CheckoutCommandState = CheckoutCommandState.PROVIDER_SESSION_OPEN,
) -> dict[str, object]:
    return {
        "entity_type": "checkout_command",
        "schema_version": checkout_command_repo.COMMAND_SCHEMA_VERSION,
        "command_id": "checkout-" + ("a" * 64),
        "parent_id": parent_id,
        "checkout_ref": checkout_ref,
        "command_state": state,
        "command_version": 4,
        "provider_effect_status": "session_attached",
        "provider_key_digest": "b" * 64,
        "provider_session_id": SESSION_ID,
        "provider_session_url": f"https://checkout.stripe.com/c/pay/{SESSION_ID}",
        "lease_generation": 2,
        "lease_expires_at": 1784890000,
        "price_id": "price_test_family",
        "environment": "test",
        "plan_id": "family",
        "beneficiary_ids": ["student-a", "student-b"],
        "created_at": "2026-07-24T10:00:00+00:00",
        "updated_at": "2026-07-24T10:05:00+00:00",
    }


def _result(
    *,
    lifecycle_state: str = "confirming",
    safe_action: str = "recheck_payment",
    failure_code: str | None = None,
) -> billing_reconciliation_service.BillingReconciliationResult:
    disposition = {
        "active": billing_reconciliation_service.BillingReconciliationDisposition.ACTIVE,
        "confirming": billing_reconciliation_service.BillingReconciliationDisposition.CONFIRMING,
        "not_completed": (
            billing_reconciliation_service.BillingReconciliationDisposition.TERMINAL_NOT_COMPLETED
        ),
        "support_needed": (
            billing_reconciliation_service.BillingReconciliationDisposition.SUPPORT_NEEDED
        ),
    }[lifecycle_state]
    return billing_reconciliation_service.BillingReconciliationResult(
        disposition=disposition,
        command_id="checkout-" + ("a" * 64),
        lifecycle_state=lifecycle_state,
        safe_action=safe_action,
        reconciliation_lease_generation=2,
        last_rechecked_at="2026-07-24T10:06:00+00:00",
        reconciliation_reason="closed-test-reason",
        failure_code=failure_code,
        provider_session_id=SESSION_ID,
    )


class RetrievalOnlyProvider:
    def __init__(self) -> None:
        self.find_calls: list[tuple[str, str]] = []
        self.retrieve_calls: list[str] = []

    def find_checkout_session(
        self,
        *,
        checkout_ref: str,
        provider_key_digest: str,
    ) -> billing_reconciliation_service.ProviderCheckoutSessionEvidence | None:
        self.find_calls.append((checkout_ref, provider_key_digest))
        return None

    def retrieve_checkout_session(
        self,
        *,
        session_id: str,
    ) -> billing_reconciliation_service.ProviderCheckoutSessionEvidence:
        self.retrieve_calls.append(session_id)
        raise AssertionError("route test replaces reconciliation before provider access")

    def create_checkout_session(self, **_kwargs: object) -> object:
        raise AssertionError("status/recheck must never create a provider Session")


def _parent_app(*, user_id: str = PARENT_ID, role: str = "parent") -> tuple[TestClient, RetrievalOnlyProvider]:
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    install_actor_overrides(app, {"sub": user_id, "role": role})
    provider = RetrievalOnlyProvider()
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[parents.get_billing_reconciliation_provider] = lambda: provider
    return TestClient(app), provider


def _admin_app(*, capability: str) -> tuple[TestClient, RetrievalOnlyProvider]:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(
        app,
        {
            "sub": "admin-1",
            "role": "admin",
            "grantCapabilities": [capability],
            "grantScope": "global",
        },
    )
    provider = RetrievalOnlyProvider()
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[admin.get_billing_reconciliation_provider] = lambda: provider
    return TestClient(app), provider


def _install_lookup(monkeypatch, *, command: dict[str, object] | None = None) -> list[tuple[str, str]]:
    stored = dict(command or _command())
    calls: list[tuple[str, str]] = []

    def lookup(
        checkout_ref: str,
        *,
        parent_id: str,
        table: object | None = None,
    ) -> checkout_command_repo.CheckoutCommandResult:
        del table
        calls.append((checkout_ref, parent_id))
        if checkout_ref != stored["checkout_ref"] or parent_id != stored["parent_id"]:
            return checkout_command_repo.CheckoutCommandResult(
                checkout_command_repo.CheckoutCommandDisposition.NOT_FOUND
            )
        return checkout_command_repo.CheckoutCommandResult(
            checkout_command_repo.CheckoutCommandDisposition.REPLAYED,
            command=dict(stored),
        )

    monkeypatch.setattr(
        checkout_command_repo,
        "get_checkout_command_by_public_ref",
        lookup,
    )
    return calls


def _install_reconciliation(monkeypatch, result=None) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def reconcile(checkout_ref: str, **kwargs: object):
        calls.append({"checkout_ref": checkout_ref, **kwargs})
        return result or _result()

    monkeypatch.setattr(
        billing_reconciliation_service,
        "reconcile_checkout_command",
        reconcile,
    )
    return calls


def test_parent_status_and_recheck_use_original_owner_authorized_command(monkeypatch) -> None:
    lookup_calls = _install_lookup(monkeypatch)
    reconcile_calls = _install_reconciliation(monkeypatch)
    client, provider = _parent_app()

    status = client.get(f"/parents/me/subscription/checkout/{CHECKOUT_REF}")
    assert status.status_code == 200
    assert status.json() == {
        "checkoutRef": CHECKOUT_REF,
        "outcome": "confirming",
        "newCheckoutAllowed": False,
        "safeActions": ["recheck_payment", "contact_support"],
        "targetPlan": "family",
        "beneficiaries": ["student-a", "student-b"],
        "effectivePlan": None,
        "lastRecheckedAt": "2026-07-24T10:06:00+00:00",
    }

    recheck = client.post(
        f"/parents/me/subscription/checkout/{CHECKOUT_REF}/recheck",
        json={},
    )
    assert recheck.status_code == 200
    assert recheck.json() == status.json()
    assert lookup_calls == [(CHECKOUT_REF, PARENT_ID), (CHECKOUT_REF, PARENT_ID)]
    assert [call["parent_id"] for call in reconcile_calls] == [PARENT_ID, PARENT_ID]
    assert [call["checkout_ref"] for call in reconcile_calls] == [CHECKOUT_REF, CHECKOUT_REF]
    assert all(call["provider"] is provider for call in reconcile_calls)


def test_parent_foreign_and_random_references_are_concealed_before_recheck(monkeypatch) -> None:
    lookup_calls = _install_lookup(monkeypatch, command=_command(parent_id=OTHER_PARENT_ID))
    reconcile_calls = _install_reconciliation(monkeypatch)
    client, provider = _parent_app()

    real = client.get(f"/parents/me/subscription/checkout/{CHECKOUT_REF}")
    random = client.get(f"/parents/me/subscription/checkout/{OTHER_REF}")

    assert real.status_code == random.status_code == 404
    assert real.json() == random.json()
    assert reconcile_calls == []
    assert provider.find_calls == provider.retrieve_calls == []
    assert lookup_calls == [(CHECKOUT_REF, PARENT_ID), (OTHER_REF, PARENT_ID)]


def test_student_and_unknown_recheck_body_fail_before_repository_or_provider(monkeypatch) -> None:
    lookup_calls = _install_lookup(monkeypatch)
    reconcile_calls = _install_reconciliation(monkeypatch)

    student, student_provider = _parent_app(user_id="student-1", role="student")
    denied = student.get(f"/parents/me/subscription/checkout/{CHECKOUT_REF}")
    assert denied.status_code == 403

    parent, parent_provider = _parent_app()
    rejected = parent.post(
        f"/parents/me/subscription/checkout/{CHECKOUT_REF}/recheck",
        json={"plan": "family", "callback": "https://private-canary.invalid"},
    )
    assert rejected.status_code == 422
    assert lookup_calls == []
    assert reconcile_calls == []
    assert student_provider.find_calls == student_provider.retrieve_calls == []
    assert parent_provider.find_calls == parent_provider.retrieve_calls == []


def test_parent_supersede_requires_literal_confirmation_and_closed_body(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        subscription_service,
        "confirm_checkout_plan_change",
        lambda **kwargs: calls.append(kwargs)
        or {
            "checkoutRef": "co_" + ("N" * 32),
            "commandState": "provider_session_open",
            "checkoutSessionId": "cs_test_successor",
            "checkoutUrl": "https://checkout.stripe.com/c/pay/cs_test_successor",
            "safeActions": ["continue_checkout"],
            "targetPlan": "student",
            "beneficiaries": ["student-a"],
        },
    )
    client, _ = _parent_app()
    path = f"/parents/me/subscription/checkout/{CHECKOUT_REF}/supersede"
    payload = {"confirmed": True, "plan": "student", "beneficiaryIds": ["student-a"]}

    assert client.post(path, headers={"Idempotency-Key": "successor-key"}, json={**payload, "callback": "x"}).status_code == 422
    assert client.post(path, headers={"Idempotency-Key": "successor-key"}, json={**payload, "confirmed": False}).status_code == 422
    accepted = client.post(path, headers={"Idempotency-Key": "successor-key"}, json=payload)
    assert accepted.status_code == 200
    assert accepted.json()["checkoutRef"] == "co_" + ("N" * 32)
    assert len(calls) == 1
    assert calls[0]["checkout_ref"] == CHECKOUT_REF
    assert calls[0]["parent_id"] == PARENT_ID


def test_admin_read_and_recheck_use_billing_support_capability_and_redaction(monkeypatch) -> None:
    lookup_calls = _install_lookup(monkeypatch)
    reconcile_calls = _install_reconciliation(
        monkeypatch,
        _result(
            lifecycle_state="support_needed",
            safe_action="contact_support",
            failure_code="provider_read_unavailable",
        ),
    )
    client, provider = _admin_app(capability="billing_operations_reader")
    suffix = SESSION_ID[-6:]
    expected = {
        "checkoutRef": CHECKOUT_REF,
        "parentId": PARENT_ID,
        "targetPlan": "family",
        "beneficiaryIds": ["student-a", "student-b"],
        "createdAt": "2026-07-24T10:00:00+00:00",
        "updatedAt": "2026-07-24T10:05:00+00:00",
        "commandState": "provider_session_open",
        "providerEffectStatus": "session_attached",
        "lifecycleState": "support_needed",
        "lastRecheckedAt": "2026-07-24T10:06:00+00:00",
        "safeAction": "contact_support",
        "failureCode": "provider_read_unavailable",
        "providerSessionSuffix": suffix,
        "reconciliationLeaseGeneration": 2,
    }
    query = f"?parentId={PARENT_ID}"

    status = client.get(f"/admin/billing/checkouts/{CHECKOUT_REF}{query}")
    recheck = client.post(
        f"/admin/billing/checkouts/{CHECKOUT_REF}/recheck{query}",
        json={},
    )
    assert status.status_code == recheck.status_code == 200
    assert status.json() == recheck.json() == expected
    assert lookup_calls == [(CHECKOUT_REF, PARENT_ID), (CHECKOUT_REF, PARENT_ID)]
    assert len(reconcile_calls) == 2
    assert all(call["provider"] is provider for call in reconcile_calls)
    for response in (status, recheck):
        assert SESSION_ID not in response.text
        assert "sk_test_private_canary" not in response.text
        assert "checkout.stripe.com" not in response.text


def test_wrong_admin_capability_denies_before_checkout_lookup_or_provider(monkeypatch) -> None:
    lookup_calls = _install_lookup(monkeypatch)
    reconcile_calls = _install_reconciliation(monkeypatch)
    client, provider = _admin_app(capability="billing_refund_executor")

    denied = client.post(
        f"/admin/billing/checkouts/{CHECKOUT_REF}/recheck?parentId={PARENT_ID}",
        json={},
    )

    assert denied.status_code == 403
    assert lookup_calls == reconcile_calls == []
    assert provider.find_calls == provider.retrieve_calls == []


def test_openapi_publishes_five_closed_routes_without_payment_authority() -> None:
    schema = main_app.openapi()
    expected = {
        ("get", f"/parents/me/subscription/checkout/{{checkout_ref}}"),
        ("post", f"/parents/me/subscription/checkout/{{checkout_ref}}/recheck"),
        ("post", f"/parents/me/subscription/checkout/{{checkout_ref}}/supersede"),
        ("get", f"/admin/billing/checkouts/{{checkout_ref}}"),
        ("post", f"/admin/billing/checkouts/{{checkout_ref}}/recheck"),
    }
    assert all(method in schema["paths"][path] for method, path in expected)
    serialized = str(
        {
            path: schema["paths"][path]
            for _, path in expected
        }
    ).lower()
    for forbidden in (
        "manualpaid",
        "markpaid",
        "marksuccess",
        "successurl",
        "cancelurl",
        "callbackurl",
        "providerkey",
        "checkoutsessionid",
    ):
        assert forbidden not in serialized

    components = schema["components"]["schemas"]
    for name in (
        "ParentCheckoutRecheckRequest",
        "ParentCheckoutSupersedeRequest",
        "AdminCheckoutRecheckRequest",
    ):
        assert components[name]["additionalProperties"] is False


def test_no_admin_manual_success_route_or_recheck_create_capability() -> None:
    routes = {
        (method, route.path)
        for route in main_app.routes
        for method in getattr(route, "methods", set())
        if route.path.startswith("/admin")
    }
    assert not any(
        marker in path.lower()
        for _, path in routes
        for marker in ("mark-paid", "mark-success", "manual-success", "manual-paid")
    )
    parent_source = inspect.getsource(parents)
    admin_source = inspect.getsource(admin)
    assert "billing_reconciliation_service.reconcile_checkout_command" in parent_source
    assert "create_checkout_session" not in inspect.getsource(
        parents.get_billing_reconciliation_provider
    )
    assert "create_checkout_session" not in inspect.getsource(
        admin.get_billing_reconciliation_provider
    )
    assert "manual_paid" not in (parent_source + admin_source).lower()
