"""Role-safe Phase 476 billing, allowance, and reminder projections."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import get_settings
from stoa.deps import get_actor
from stoa.models.billing import BillingFact, BillingFactKind
from stoa.routers import admin, parents
from stoa.security.identity import Actor, CanonicalRole
from stoa.services import subscription_service


NOW = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
SECRET_CANARIES = (
    "sk_test_private_canary",
    "https://checkout.stripe.com/private",
    "4242424242424242",
    "999",
    "cs_test_full_provider_identifier",
    "pm_full_provider_identifier",
    "private prompt canary",
    "private answer canary",
    "student-unselected",
)


def _grant(
    beneficiary_id: str,
    *,
    plan: str = "family",
    grant_version: int = 7,
    allowance_version: int = 4,
) -> dict[str, object]:
    return {
        "parent_id": "parent-1",
        "beneficiary_id": beneficiary_id,
        "plan_id": plan,
        "grant_version": grant_version,
        "plan_version": 3,
        "allowance_version": allowance_version,
        "subscription_id_digest": DIGEST_A,
        "grant_status": "active",
    }


def _allowance(
    beneficiary_id: str,
    *,
    input_remaining: int,
    output_remaining: int,
    input_percent: float,
    output_percent: float,
    admin: bool = False,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schemaVersion": "allowance_projection.v1",
        "beneficiaryId": beneficiary_id,
        "planId": "family",
        "allowanceVersion": 4,
        "weekIdentity": "2026-W30",
        "window": {
            "start": "2026-07-19T22:00:00+00:00",
            "end": "2026-07-26T22:00:00+00:00",
        },
        "input": {
            "budgetTokens": 1_000_000,
            "remainingTokens": input_remaining,
            "usedPercent": input_percent,
        },
        "output": {
            "budgetTokens": 200_000,
            "remainingTokens": output_remaining,
            "usedPercent": output_percent,
        },
    }
    if admin:
        value.update(
            {
                "exactUsage": {
                    "finalizedInputTokens": 125_000,
                    "finalizedOutputTokens": 20_000,
                    "reservedInputTokens": 25_000,
                    "reservedOutputTokens": 5_000,
                },
                "providerCost": {
                    "inputTokens": 150_000,
                    "outputTokens": 25_000,
                },
                "providerEvidence": [
                    {
                        "evidenceId": DIGEST_C,
                        "effectId": DIGEST_B,
                        "providerRequestIdDigest": DIGEST_A,
                        "modelIdDigest": DIGEST_B,
                        "inputTokens": 150_000,
                        "outputTokens": 25_000,
                        "providerCostRetained": True,
                        "observedAt": NOW.isoformat(),
                    }
                ],
            }
        )
    return value


def _reminder() -> dict[str, object]:
    return {
        "brand": "visa",
        "last4": "4242",
        "exp_month": 8,
        "exp_year": 2026,
        "reminder_at": "2026-08-24T22:00:00+00:00",
        "status": "notified",
        "observation_version": 8,
        "payment_method_digest": DIGEST_A,
        "source_subscription_digest": DIGEST_B,
        "provider_id": SECRET_CANARIES[5],
    }


@pytest.mark.parametrize(
    ("remaining", "percent"),
    (
        (1_000_000, 0.0),
        (500_000, 50.0),
        (0, 100.0),
        (1_000_000, 0.0),
    ),
)
def test_parent_projection_keeps_exact_allowance_boundaries(
    remaining: int,
    percent: float,
) -> None:
    result = subscription_service.project_parent_billing_overview(
        parent_id="parent-1",
        grants=[_grant("student-selected")],
        allowance_projections=[
            _allowance(
                "student-selected",
                input_remaining=remaining,
                output_remaining=200_000,
                input_percent=percent,
                output_percent=0.0,
            )
        ],
        teacher_support_projections=[
            {
                "supportScope": "shared_family",
                "remainingCases": 6,
                "limit": 10,
                "weekIdentity": "2026-W30",
            }
        ],
        reminder=_reminder(),
    )

    assert result["inputRemaining"] == {"student-selected": remaining}
    assert result["inputPercentUsed"] == {"student-selected": percent}
    assert result["allowanceWindow"]["localStart"] == "2026-07-20T00:00:00+02:00"
    assert result["allowanceWindow"]["localEnd"] == "2026-07-27T00:00:00+02:00"


def test_family_projection_is_per_selected_beneficiary_and_support_is_shared() -> None:
    result = subscription_service.project_parent_billing_overview(
        parent_id="parent-1",
        grants=[_grant("student-a"), _grant("student-b")],
        allowance_projections=[
            _allowance(
                "student-a",
                input_remaining=900_000,
                output_remaining=190_000,
                input_percent=10.0,
                output_percent=5.0,
            ),
            _allowance(
                "student-b",
                input_remaining=400_000,
                output_remaining=100_000,
                input_percent=60.0,
                output_percent=50.0,
            ),
        ],
        teacher_support_projections=[
            {
                "supportScope": "shared_family",
                "remainingCases": 3,
                "limit": 10,
                "weekIdentity": "2026-W30",
            },
            {
                "supportScope": "shared_family",
                "remainingCases": 3,
                "limit": 10,
                "weekIdentity": "2026-W30",
            },
        ],
        reminder=_reminder(),
    )

    assert result["beneficiaries"] == [
        {"studentId": "student-a", "effectivePlan": "family"},
        {"studentId": "student-b", "effectivePlan": "family"},
    ]
    assert result["inputRemaining"] == {
        "student-a": 900_000,
        "student-b": 400_000,
    }
    assert result["teacherCasesRemaining"] == {
        "scope": "shared_family",
        "remaining": 3,
        "limit": 10,
        "byBeneficiary": {},
    }


def test_parent_projection_is_closed_masked_and_omits_unselected_child() -> None:
    result = subscription_service.project_parent_billing_overview(
        parent_id="parent-1",
        grants=[_grant("student-selected")],
        allowance_projections=[
            _allowance(
                "student-selected",
                input_remaining=1,
                output_remaining=2,
                input_percent=99.9999,
                output_percent=99.999,
            )
        ],
        teacher_support_projections=[
            {
                "supportScope": "shared_family",
                "remainingCases": 1,
                "limit": 10,
                "weekIdentity": "2026-W30",
            }
        ],
        reminder=_reminder(),
    )
    encoded = json.dumps(result, sort_keys=True)

    assert result["paymentReminder"] == {
        "brand": "visa",
        "last4": "4242",
        "expiryMonth": 8,
        "expiryYear": 2026,
        "reminderAt": "2026-08-24T22:00:00+00:00",
        "status": "notified",
    }
    assert not any(canary in encoded for canary in SECRET_CANARIES)


def test_non_active_checkout_cannot_infer_an_effective_plan() -> None:
    projection = subscription_service.project_parent_checkout_lifecycle(
        {
            "plan_id": "family",
            "beneficiary_ids": ["student-selected"],
            "command_state": "provider_session_open",
        },
        lifecycle_state="confirming",
    )
    active = subscription_service.project_parent_checkout_lifecycle(
        {
            "plan_id": "family",
            "beneficiary_ids": ["student-selected"],
            "command_state": "activation_recorded",
        },
        lifecycle_state="active",
    )

    assert projection["effectivePlan"] is None
    assert projection["beneficiaries"] == []
    assert active["effectivePlan"] == "family"
    assert active["beneficiaries"] == ["student-selected"]


def test_admin_detail_exposes_exact_redacted_evidence_and_versions() -> None:
    fact = BillingFact(
        factId="fact-safe",
        checkoutCommandId="command-private",
        kind=BillingFactKind.INVOICE_PAID,
        providerEventIdDigest=DIGEST_A,
        providerObjectIdDigest=DIGEST_B,
        signatureVerified=True,
        providerLivemode=False,
        factVersion=5,
        observedAt=NOW,
    )
    result = subscription_service.project_admin_billing_operation_detail(
        checkout_ref="checkout-safe",
        command={
            "parent_id": "parent-1",
            "plan_id": "family",
            "beneficiary_ids": ["student-selected"],
            "command_state": "activation_recorded",
            "provider_effect_status": "attached",
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
            "provider_session_id": SECRET_CANARIES[4],
            "checkout_url": SECRET_CANARIES[1],
        },
        reconciliation={
            "lifecycleState": "active",
            "lastRecheckedAt": NOW.isoformat(),
            "safeAction": "view_billing",
            "failureClass": "none",
            "providerSessionSuffix": "safe42",
            "reconciliationLeaseGeneration": 9,
        },
        facts=[fact],
        grants=[_grant("student-selected")],
        allowance_projections=[
            _allowance(
                "student-selected",
                input_remaining=850_000,
                output_remaining=175_000,
                input_percent=15.0,
                output_percent=12.5,
                admin=True,
            )
        ],
        reminder=_reminder(),
    )
    encoded = json.dumps(result, sort_keys=True)

    assert result["commandLifecycle"]["state"] == "activation_recorded"
    assert result["factLifecycle"][0]["providerEventIdDigest"] == DIGEST_A
    assert result["grantVersion"] == {"student-selected": 7}
    assert result["allowanceVersion"] == {"student-selected": 4}
    assert result["providerUsageEvidence"][0] == {
        "beneficiaryId": "student-selected",
        "correlationDigest": DIGEST_B,
        "providerRequestIdDigest": DIGEST_A,
        "modelIdDigest": DIGEST_B,
        "inputTokens": 150_000,
        "outputTokens": 25_000,
        "providerCostRetained": True,
        "observedAt": NOW.isoformat(),
    }
    assert not any(canary in encoded for canary in SECRET_CANARIES)


def test_admin_capability_denial_happens_before_billing_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace()
    reads: list[str] = []
    monkeypatch.setattr(
        admin,
        "_load_admin_checkout_command",
        lambda *_args, **_kwargs: reads.append("command"),
    )

    response = TestClient(app).get(
        "/admin/billing/checkouts/checkout-safe",
        params={"parentId": "parent-1"},
    )

    assert response.status_code in {401, 403}
    assert reads == []


def test_parent_route_uses_current_grants_and_week_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.dependency_overrides[get_actor] = lambda: Actor(
        user_id="parent-1",
        claims_sub="claims-parent-1",
        role=CanonicalRole.PARENT,
        email="parent@example.test",
    )
    monkeypatch.setattr(
        subscription_service,
        "get_parent_active_billing_grants",
        lambda *_args, **_kwargs: [_grant("student-selected")],
    )
    monkeypatch.setattr(
        subscription_service,
        "get_current_payment_reminder",
        lambda *_args, **_kwargs: _reminder(),
    )
    monkeypatch.setattr(
        parents.allowance_service,
        "get_allowance_projection",
        lambda **_kwargs: _allowance(
            "student-selected",
            input_remaining=875_000,
            output_remaining=180_000,
            input_percent=12.5,
            output_percent=10.0,
        ),
    )
    monkeypatch.setattr(
        parents.teacher_support_allowance_service,
        "get_teacher_support_projection",
        lambda **_kwargs: {
            "supportScope": "shared_family",
            "remainingCases": 8,
            "limit": 10,
            "weekIdentity": "2026-W30",
        },
    )

    response = TestClient(app).get("/parents/me/subscription/billing")

    assert response.status_code == 200
    assert response.json()["inputRemaining"] == {"student-selected": 875_000}


def test_openapi_has_closed_projection_models_and_no_manual_payment_success() -> None:
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.include_router(admin.router, prefix="/admin")
    document = app.openapi()
    schemas = document["components"]["schemas"]
    paths = "\n".join(document["paths"]).lower()

    assert schemas["ParentBillingOverviewResponse"]["additionalProperties"] is False
    assert schemas["AdminBillingOperationDetail"]["additionalProperties"] is False
    assert "manual-success" not in paths
    assert "mark-payment-success" not in paths


def test_source_binds_parent_projection_and_contains_no_manual_success_action() -> None:
    parent_source = Path("src/stoa/routers/parents.py").read_text()
    admin_source = Path("src/stoa/routers/admin.py").read_text()

    assert "allowance_service.get_allowance_projection" in parent_source
    assert "manual_payment_success" not in admin_source
    assert "mark_payment_success" not in admin_source
