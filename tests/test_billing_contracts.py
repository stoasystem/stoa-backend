"""Executable contracts for canonical billing and weekly allowance evidence."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

import pytest
from pydantic import BaseModel, ValidationError

from stoa.models.allowance import (
    MAX_EXACT_COUNT,
    AllowanceFinalization,
    AllowanceReservation,
    PlanAllowanceBudget,
    ProviderUsageEvidence,
    TeacherSupportAdmission,
    ZurichWeek,
)
from stoa.models.billing import (
    BeneficiaryGrant,
    BillingFact,
    BillingFactKind,
    BillingLifecycleState,
    BillingPlanId,
    BillingSupportProjection,
    CheckoutCommandProjection,
    CheckoutCommandState,
    CheckoutIntent,
    CheckoutPublicOutcome,
    MaskedPaymentMethod,
    PurchasablePlanId,
    ScheduledPlanTransition,
)


ZURICH = ZoneInfo("Europe/Zurich")
MONDAY = datetime(2026, 3, 23, tzinfo=ZURICH)
NEXT_MONDAY = datetime(2026, 3, 30, tzinfo=ZURICH)


def _week_payload() -> dict[str, object]:
    return {
        "isoYear": 2026,
        "isoWeek": 13,
        "windowStart": MONDAY.isoformat(),
        "windowEnd": NEXT_MONDAY.isoformat(),
    }


def _checkout_intent_payload(plan: str = "student") -> dict[str, object]:
    beneficiaries = ["student-1", "student-2"] if plan == "family" else ["student-1"]
    return {
        "commandId": "command-1",
        "parentId": "parent-1",
        "idempotencyKey": "browser-operation-1",
        "planId": plan,
        "beneficiaryIds": beneficiaries,
        "priceCatalogVersion": 7,
        "planVersion": 11,
        "createdAt": "2026-07-24T08:00:00Z",
    }


def _projection_payload(outcome: str = "confirming") -> dict[str, object]:
    return {
        "checkoutRef": "checkout-public-ref",
        "commandState": "reconciling",
        "publicOutcome": outcome,
        "billingLifecycleState": "no_paid_fact",
        "entitlementState": "inactive",
        "stateVersion": 3,
        "targetPlanId": "student",
        "beneficiaryIds": ["student-1"],
        "safeActions": ["recheck_payment", "contact_support"],
    }


def _provider_evidence_payload() -> dict[str, object]:
    return {
        "evidenceId": "evidence-1",
        "effectId": "effect-1",
        "providerRequestIdDigest": "a" * 64,
        "modelIdDigest": "b" * 64,
        "inputTokens": 123,
        "outputTokens": 45,
        "providerCostRetained": True,
        "observedAt": "2026-07-24T08:01:00Z",
    }


def test_all_public_contract_symbols_are_models_or_closed_enums() -> None:
    enums = (
        BillingPlanId,
        PurchasablePlanId,
        CheckoutCommandState,
        CheckoutPublicOutcome,
        BillingFactKind,
        BillingLifecycleState,
    )
    models = (
        CheckoutIntent,
        CheckoutCommandProjection,
        BillingFact,
        BeneficiaryGrant,
        ScheduledPlanTransition,
        MaskedPaymentMethod,
        BillingSupportProjection,
        ZurichWeek,
        PlanAllowanceBudget,
        AllowanceReservation,
        ProviderUsageEvidence,
        AllowanceFinalization,
        TeacherSupportAdmission,
    )

    assert all(issubclass(enum, StrEnum) for enum in enums)
    assert all(issubclass(model, BaseModel) for model in models)


def test_billing_plan_ids_are_exactly_the_four_product_values() -> None:
    assert {member.value for member in BillingPlanId} == {
        "free_trial",
        "student",
        "teacher_supported",
        "family",
    }
    assert {member.value for member in PurchasablePlanId} == {
        "student",
        "teacher_supported",
        "family",
    }


@pytest.mark.parametrize("legacy_value", ["free", "standard", "premium", "tutor_supported"])
def test_legacy_plan_values_are_rejected(legacy_value: str) -> None:
    payload = _checkout_intent_payload()
    payload["planId"] = legacy_value

    with pytest.raises(ValidationError):
        CheckoutIntent.model_validate(payload)


def test_free_trial_cannot_construct_a_checkout_intent() -> None:
    with pytest.raises(ValidationError):
        CheckoutIntent.model_validate(_checkout_intent_payload("free_trial"))


@pytest.mark.parametrize(
    ("plan", "beneficiary_ids"),
    [
        ("student", []),
        ("student", ["student-1", "student-2"]),
        ("teacher_supported", []),
        ("teacher_supported", ["student-1", "student-2"]),
        ("family", []),
        ("family", ["student-1", "student-2", "student-3", "student-4"]),
        ("family", ["student-1", "student-1"]),
    ],
)
def test_checkout_intent_enforces_explicit_unique_plan_beneficiaries(
    plan: str,
    beneficiary_ids: list[str],
) -> None:
    payload = _checkout_intent_payload(plan)
    payload["beneficiaryIds"] = beneficiary_ids

    with pytest.raises(ValidationError):
        CheckoutIntent.model_validate(payload)


def test_checkout_intent_uses_explicit_api_aliases_and_snake_case_storage_fields() -> None:
    intent = CheckoutIntent.model_validate(_checkout_intent_payload("family"))

    assert intent.plan_id is PurchasablePlanId.FAMILY
    assert intent.beneficiary_ids == ("student-1", "student-2")
    assert set(intent.model_dump()) == {
        "command_id",
        "parent_id",
        "idempotency_key",
        "plan_id",
        "beneficiary_ids",
        "price_catalog_version",
        "plan_version",
        "created_at",
    }
    assert set(intent.model_dump(by_alias=True)) == {
        "commandId",
        "parentId",
        "idempotencyKey",
        "planId",
        "beneficiaryIds",
        "priceCatalogVersion",
        "planVersion",
        "createdAt",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("successUrl", "https://example.test/billing/success"),
        ("cancelUrl", "https://example.test/billing/cancel"),
        ("redirectPath", "/billing/success"),
        ("plan", "family"),
        ("providerEvent", "checkout.session.completed"),
    ],
)
def test_browser_navigation_and_provider_hints_are_forbidden_from_checkout_intent(
    field: str,
    value: str,
) -> None:
    payload = _checkout_intent_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        CheckoutIntent.model_validate(payload)


def test_public_checkout_outcomes_are_exactly_the_four_user_states() -> None:
    assert {member.value for member in CheckoutPublicOutcome} == {
        "confirming",
        "active",
        "not_completed",
        "support_needed",
    }


def test_checkout_command_states_are_not_public_outcome_values() -> None:
    assert {member.value for member in CheckoutCommandState}.isdisjoint(
        {member.value for member in CheckoutPublicOutcome}
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("redirectPath", "/billing/success"),
        ("planQuery", "student"),
        ("providerEventType", "checkout.session.completed"),
    ],
)
def test_navigation_hints_cannot_deserialize_as_an_active_projection(
    field: str,
    value: str,
) -> None:
    payload = _projection_payload("active")
    payload[field] = value

    with pytest.raises(ValidationError):
        CheckoutCommandProjection.model_validate(payload)


def test_opaque_reference_and_checkout_completion_do_not_prove_active_access() -> None:
    payload = _projection_payload("active")
    payload["commandState"] = "provider_session_open"
    payload["billingLifecycleState"] = "no_paid_fact"

    with pytest.raises(ValidationError):
        CheckoutCommandProjection.model_validate(payload)


def test_active_projection_requires_paid_invoice_subscription_and_grant_coordinates() -> None:
    payload = _projection_payload("active")
    payload.update(
        {
            "commandState": "activation_recorded",
            "billingLifecycleState": "subscription_active",
            "entitlementState": "active",
            "paidInvoiceFactId": "fact-invoice-paid",
            "activeSubscriptionFactId": "fact-subscription-active",
            "effectivePlanId": "student",
            "planVersion": 11,
            "allowanceVersion": 4,
        }
    )

    projection = CheckoutCommandProjection.model_validate(payload)

    assert projection.public_outcome is CheckoutPublicOutcome.ACTIVE
    assert projection.paid_invoice_fact_id == "fact-invoice-paid"
    assert projection.active_subscription_fact_id == "fact-subscription-active"


@pytest.mark.parametrize(
    "missing",
    [
        "paidInvoiceFactId",
        "activeSubscriptionFactId",
        "effectivePlanId",
        "planVersion",
        "allowanceVersion",
    ],
)
def test_each_authoritative_active_coordinate_is_required(missing: str) -> None:
    payload = _projection_payload("active")
    payload.update(
        {
            "commandState": "activation_recorded",
            "billingLifecycleState": "subscription_active",
            "entitlementState": "active",
            "paidInvoiceFactId": "fact-invoice-paid",
            "activeSubscriptionFactId": "fact-subscription-active",
            "effectivePlanId": "student",
            "planVersion": 11,
            "allowanceVersion": 4,
        }
    )
    payload.pop(missing)

    with pytest.raises(ValidationError):
        CheckoutCommandProjection.model_validate(payload)


def test_signed_sandbox_billing_facts_keep_checkout_invoice_and_subscription_distinct() -> None:
    common = {
        "checkoutCommandId": "command-1",
        "providerEventIdDigest": "a" * 64,
        "providerObjectIdDigest": "b" * 64,
        "signatureVerified": True,
        "providerLivemode": False,
        "factVersion": 1,
        "observedAt": "2026-07-24T08:00:00Z",
    }

    checkout_fact = BillingFact.model_validate(
        {"factId": "fact-checkout", "kind": "checkout_session_completed", **common}
    )
    paid_fact = BillingFact.model_validate(
        {"factId": "fact-paid", "kind": "invoice_paid", **common}
    )
    active_fact = BillingFact.model_validate(
        {"factId": "fact-active", "kind": "subscription_active", **common}
    )

    assert checkout_fact.kind is BillingFactKind.CHECKOUT_SESSION_COMPLETED
    assert paid_fact.kind is BillingFactKind.INVOICE_PAID
    assert active_fact.kind is BillingFactKind.SUBSCRIPTION_ACTIVE
    assert len({checkout_fact.kind, paid_fact.kind, active_fact.kind}) == 3


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("signatureVerified", False),
        ("providerLivemode", True),
        ("callbackUrl", "https://example.test/success"),
        ("providerCredential", "sk_test_sensitive"),
    ],
)
def test_billing_fact_rejects_unverified_live_or_extra_provider_inputs(
    field: str,
    value: object,
) -> None:
    payload: dict[str, object] = {
        "factId": "fact-paid",
        "checkoutCommandId": "command-1",
        "kind": "invoice_paid",
        "providerEventIdDigest": "a" * 64,
        "providerObjectIdDigest": "b" * 64,
        "signatureVerified": True,
        "providerLivemode": False,
        "factVersion": 1,
        "observedAt": "2026-07-24T08:00:00Z",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        BillingFact.model_validate(payload)


def test_beneficiary_grant_and_transition_preserve_plan_version_coordinates() -> None:
    grant = BeneficiaryGrant.model_validate(
        {
            "grantId": "grant-1",
            "parentId": "parent-1",
            "beneficiaryId": "student-1",
            "planId": "student",
            "planVersion": 11,
            "allowanceVersion": 4,
            "stateVersion": 2,
            "activeFrom": "2026-07-24T08:00:00Z",
        }
    )
    transition = ScheduledPlanTransition.model_validate(
        {
            "transitionId": "transition-1",
            "subscriptionIdDigest": "c" * 64,
            "fromPlanId": "student",
            "toPlanId": "free_trial",
            "fromPlanVersion": 11,
            "toPlanVersion": 12,
            "stateVersion": 3,
            "effectiveAt": "2026-08-24T08:00:00Z",
        }
    )

    assert grant.beneficiary_id == "student-1"
    assert transition.to_plan_id is BillingPlanId.FREE_TRIAL
    assert transition.to_plan_version > transition.from_plan_version


def test_masked_payment_method_exposes_only_safe_summary() -> None:
    method = MaskedPaymentMethod.model_validate(
        {
            "paymentMethodIdDigest": "d" * 64,
            "brand": "visa",
            "lastFour": "4242",
            "expiryMonth": 8,
            "expiryYear": 2028,
            "sourceSubscriptionIdDigest": "e" * 64,
            "observationVersion": 1,
            "observedAt": "2026-07-24T08:00:00Z",
        }
    )

    assert method.last_four == "4242"
    assert "pan" not in method.model_dump()
    assert "cvc" not in method.model_dump()


@pytest.mark.parametrize("field", ["pan", "cardNumber", "cvc", "providerSecret"])
def test_masked_payment_method_rejects_payment_capable_secrets(field: str) -> None:
    payload: dict[str, object] = {
        "paymentMethodIdDigest": "d" * 64,
        "brand": "visa",
        "lastFour": "4242",
        "expiryMonth": 8,
        "expiryYear": 2028,
        "sourceSubscriptionIdDigest": "e" * 64,
        "observationVersion": 1,
        "observedAt": "2026-07-24T08:00:00Z",
        field: "sensitive",
    }

    with pytest.raises(ValidationError):
        MaskedPaymentMethod.model_validate(payload)


def test_zurich_week_uses_local_monday_boundaries_across_dst() -> None:
    week = ZurichWeek.model_validate(_week_payload())

    assert week.window_start.utcoffset() == timedelta(hours=1)
    assert week.window_end.utcoffset() == timedelta(hours=2)
    assert week.window_start.hour == week.window_end.hour == 0
    assert week.window_start.weekday() == week.window_end.weekday() == 0


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (MONDAY + timedelta(hours=1), NEXT_MONDAY),
        (MONDAY, NEXT_MONDAY + timedelta(days=1)),
        (
            datetime(2026, 3, 23, tzinfo=ZoneInfo("UTC")),
            datetime(2026, 3, 30, tzinfo=ZoneInfo("UTC")),
        ),
    ],
)
def test_invalid_week_boundaries_are_rejected(start: datetime, end: datetime) -> None:
    payload = _week_payload()
    payload["windowStart"] = start.isoformat()
    payload["windowEnd"] = end.isoformat()

    with pytest.raises(ValidationError):
        ZurichWeek.model_validate(payload)


@pytest.mark.parametrize(
    ("plan", "input_tokens", "output_tokens", "support_cases", "scope"),
    [
        ("free_trial", 50_000, 10_000, 0, "none"),
        ("student", 500_000, 100_000, 0, "none"),
        ("teacher_supported", 1_000_000, 200_000, 2, "per_beneficiary"),
        ("family", 1_000_000, 200_000, 10, "shared_family"),
    ],
)
def test_plan_allowance_budgets_match_locked_weekly_values(
    plan: str,
    input_tokens: int,
    output_tokens: int,
    support_cases: int,
    scope: str,
) -> None:
    budget = PlanAllowanceBudget.model_validate(
        {
            "planId": plan,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "teacherSupportCases": support_cases,
            "teacherSupportScope": scope,
            "allowanceVersion": 1,
        }
    )

    assert budget.input_tokens == input_tokens
    assert budget.output_tokens == output_tokens
    assert budget.teacher_support_cases == support_cases


def test_plan_allowance_budget_rejects_values_not_matching_the_plan() -> None:
    with pytest.raises(ValidationError):
        PlanAllowanceBudget.model_validate(
            {
                "planId": "student",
                "inputTokens": 1_000_000,
                "outputTokens": 100_000,
                "teacherSupportCases": 0,
                "teacherSupportScope": "none",
                "allowanceVersion": 1,
            }
        )


@pytest.mark.parametrize("field", ["inputTokens", "outputTokens"])
@pytest.mark.parametrize("invalid", [-1, 1.5, True, MAX_EXACT_COUNT + 1])
def test_provider_usage_counts_are_nonnegative_bounded_exact_integers(
    field: str,
    invalid: object,
) -> None:
    payload = _provider_evidence_payload()
    payload[field] = invalid

    with pytest.raises(ValidationError):
        ProviderUsageEvidence.model_validate(payload)


def test_provider_usage_accepts_zero_and_the_maximum_exact_count() -> None:
    payload = _provider_evidence_payload()
    payload["inputTokens"] = 0
    payload["outputTokens"] = MAX_EXACT_COUNT

    evidence = ProviderUsageEvidence.model_validate(payload)

    assert evidence.input_tokens == 0
    assert evidence.output_tokens == MAX_EXACT_COUNT


@pytest.mark.parametrize(
    "field",
    [
        "prompt",
        "answer",
        "content",
        "metadata",
        "pan",
        "cardNumber",
        "cvc",
        "providerCredential",
        "secret",
    ],
)
def test_provider_usage_evidence_rejects_learning_payment_and_secret_content(field: str) -> None:
    payload = _provider_evidence_payload()
    payload[field] = "private-canary"

    with pytest.raises(ValidationError):
        ProviderUsageEvidence.model_validate(payload)


def test_allowance_reservation_and_finalization_keep_user_debit_and_provider_cost_distinct() -> None:
    reservation = AllowanceReservation.model_validate(
        {
            "reservationId": "reservation-1",
            "effectId": "effect-1",
            "beneficiaryId": "student-1",
            "planId": "student",
            "allowanceVersion": 1,
            "week": _week_payload(),
            "inputTokens": 150,
            "outputTokens": 75,
            "stateVersion": 1,
            "expiresAt": "2026-07-24T08:05:00Z",
        }
    )
    finalization = AllowanceFinalization.model_validate(
        {
            "reservationId": reservation.reservation_id,
            "evidenceId": "evidence-1",
            "finalizedInputTokens": 123,
            "finalizedOutputTokens": 45,
            "restoredInputTokens": 0,
            "restoredOutputTokens": 0,
            "providerCostRetained": True,
            "technicalValidationPassed": True,
            "safetyCheckPassed": True,
            "durableResultStored": True,
            "stableReplayReadable": True,
            "stateVersion": 2,
            "finalizedAt": "2026-07-24T08:02:00Z",
        }
    )

    assert reservation.week.window_start == MONDAY
    assert finalization.finalized_input_tokens == 123
    assert finalization.provider_cost_retained is True


def test_teacher_support_admission_debits_exactly_one_case() -> None:
    admission = TeacherSupportAdmission.model_validate(
        {
            "caseId": "case-1",
            "effectId": "support-case:case-1",
            "beneficiaryId": "student-1",
            "planId": "teacher_supported",
            "grantId": "grant-1",
            "allowanceVersion": 1,
            "week": _week_payload(),
            "admittedCases": 1,
            "stateVersion": 1,
            "admittedAt": "2026-07-24T08:00:00Z",
        }
    )

    assert admission.admitted_cases == 1


@pytest.mark.parametrize("invalid", [0, 2, -1, 1.5, True])
def test_teacher_support_admission_rejects_non_single_case_debits(invalid: object) -> None:
    payload: dict[str, object] = {
        "caseId": "case-1",
        "effectId": "support-case:case-1",
        "beneficiaryId": "student-1",
        "planId": "teacher_supported",
        "grantId": "grant-1",
        "allowanceVersion": 1,
        "week": _week_payload(),
        "admittedCases": invalid,
        "stateVersion": 1,
        "admittedAt": "2026-07-24T08:00:00Z",
    }

    with pytest.raises(ValidationError):
        TeacherSupportAdmission.model_validate(payload)


def test_support_projection_serializes_named_public_fields_by_alias() -> None:
    projection = BillingSupportProjection.model_validate(
        {
            "checkoutRef": "checkout-public-ref",
            "stateVersion": 3,
            "commandState": "operator_attention_required",
            "publicOutcome": "support_needed",
            "targetPlanId": "student",
            "beneficiaryIds": ["student-1"],
            "safeActions": ["recheck_payment", "contact_support"],
            "failureCode": "provider_state_unknown",
            "updatedAt": "2026-07-24T08:00:00Z",
        }
    )

    assert {
        "checkoutRef",
        "stateVersion",
        "safeActions",
        "beneficiaryIds",
    }.issubset(projection.model_dump(by_alias=True))
