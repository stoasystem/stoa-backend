from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pytest

from stoa.config import Settings
from stoa.db.repositories import billing_fact_repo
from stoa.models.billing import BillingPlanId
from stoa.services import entitlement_service, paid_entitlement_service


_DIGEST = "a" * 64
_NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


class _ReadTable:
    def __init__(self, items: dict[tuple[str, str], dict[str, object]] | None = None) -> None:
        self.items = deepcopy(items or {})

    def get_item(self, **kwargs: object) -> dict[str, object]:
        key = kwargs["Key"]
        assert isinstance(key, dict)
        item = self.items.get((str(key["PK"]), str(key["SK"])))
        return {"Item": deepcopy(item)} if item is not None else {}


def _activation_request(
    *,
    plan: BillingPlanId = BillingPlanId.FAMILY,
    plan_version: int = 2,
    allowance_version: int = 2,
    activation_version: int = 7,
) -> billing_fact_repo.PaidActivationRequest:
    return billing_fact_repo.PaidActivationRequest(
        command_id="cmd-paid-1",
        parent_id="parent-1",
        expected_command_version=4,
        provider_customer_id_digest="b" * 64,
        provider_subscription_id_digest=_DIGEST,
        price_id="price_test_family",
        environment="test",
        plan_id=plan,
        plan_version=plan_version,
        allowance_version=allowance_version,
        activation_version=activation_version,
        paid_invoice_fact_id="fact-invoice",
        active_subscription_fact_id="fact-subscription",
        activated_at=_NOW.isoformat(),
    )


def _command(beneficiary_ids: tuple[str, ...]) -> dict[str, object]:
    return {
        "command_id": "cmd-paid-1",
        "parent_id": "parent-1",
        "beneficiary_ids": list(beneficiary_ids),
        "provider_subscription_id_digest": _DIGEST,
        "plan_id": BillingPlanId.FAMILY.value,
        "plan_version": 2,
    }


def _install_active_relationships(
    monkeypatch: pytest.MonkeyPatch,
    beneficiary_ids: tuple[str, ...],
    *,
    inactive: frozenset[str] = frozenset(),
    foreign_parent: frozenset[str] = frozenset(),
) -> None:
    profiles: dict[str, dict[str, object]] = {
        "parent-1": {
            "user_id": "parent-1",
            "role": "parent",
            "account_status": "active",
            "version": 11,
        }
    }
    for index, student_id in enumerate(beneficiary_ids, start=1):
        profiles[student_id] = {
            "user_id": student_id,
            "role": "student",
            "account_status": "inactive" if student_id in inactive else "active",
            "version": 20 + index,
            "parent_id": "other-parent" if student_id in foreign_parent else "parent-1",
            "parent_binding_status": "active",
        }

    monkeypatch.setattr(
        paid_entitlement_service.user_repo,
        "get_user",
        lambda user_id: deepcopy(profiles.get(user_id)),
    )

    def forward(parent_id: str, student_id: str) -> dict[str, object] | None:
        if student_id not in profiles:
            return None
        return {
            "parent_id": "other-parent" if student_id in foreign_parent else parent_id,
            "student_id": student_id,
            "relationship": "child",
            "status": "active",
            "version": 30 + beneficiary_ids.index(student_id),
        }

    def reverse(student_id: str, parent_id: str) -> dict[str, object] | None:
        if student_id not in profiles:
            return None
        return {
            "parent_id": "other-parent" if student_id in foreign_parent else parent_id,
            "student_id": student_id,
            "relationship": "child",
            "status": "active",
            "version": 40 + beneficiary_ids.index(student_id),
        }

    monkeypatch.setattr(
        paid_entitlement_service.user_repo,
        "get_parent_student_binding",
        forward,
    )
    monkeypatch.setattr(
        paid_entitlement_service.user_repo,
        "get_student_parent_binding",
        reverse,
    )
    monkeypatch.setattr(
        paid_entitlement_service.account_deletion_repo,
        "require_active_account_fence",
        lambda user_id, *, table: {
            "generation": 100 if user_id == "parent-1" else 201 + beneficiary_ids.index(user_id)
        },
    )


@pytest.mark.parametrize(
    ("plan", "beneficiaries"),
    [
        (BillingPlanId.STUDENT, ("student-1",)),
        (BillingPlanId.TEACHER_SUPPORTED, ("student-1",)),
        (BillingPlanId.FAMILY, ("student-1",)),
        (BillingPlanId.FAMILY, ("student-3", "student-1", "student-2")),
    ],
)
def test_validate_beneficiary_selection_accepts_only_sorted_bounded_unique_ids(
    plan: BillingPlanId,
    beneficiaries: tuple[str, ...],
) -> None:
    assert paid_entitlement_service.validate_beneficiary_selection(
        plan,
        beneficiaries,
    ) == tuple(sorted(beneficiaries))


@pytest.mark.parametrize(
    ("plan", "beneficiaries"),
    [
        (BillingPlanId.FAMILY, ()),
        (BillingPlanId.FAMILY, ("s1", "s2", "s3", "s4")),
        (BillingPlanId.STUDENT, ("s1", "s2")),
        (BillingPlanId.TEACHER_SUPPORTED, ()),
        (BillingPlanId.FAMILY, ("s1", "s1")),
        (BillingPlanId.FAMILY, (" s1",)),
    ],
)
def test_validate_beneficiary_selection_rejects_zero_four_duplicate_and_malformed(
    plan: BillingPlanId,
    beneficiaries: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        paid_entitlement_service.validate_beneficiary_selection(plan, beneficiaries)


def test_build_paid_activation_operations_binds_three_exact_current_relationships(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = ("student-3", "student-1", "student-2")
    _install_active_relationships(monkeypatch, selected)

    built = paid_entitlement_service.build_paid_activation_operations(
        _activation_request(),
        command=_command(selected),
        table=_ReadTable(),
    )

    assert [item["beneficiary_id"] for item in built.grant_items] == [
        "student-1",
        "student-2",
        "student-3",
    ]
    assert all(item["schema_version"] == "paid_beneficiary_grant.v1" for item in built.grant_items)
    assert all(item["subscription_id_digest"] == _DIGEST for item in built.grant_items)
    assert all(item["grant_version"] == 7 for item in built.grant_items)
    assert all(item["plan_version"] == 2 for item in built.grant_items)
    assert all(item["allowance_version"] == 2 for item in built.grant_items)
    assert all(item["parent_account_fence_generation"] == 100 for item in built.grant_items)
    assert {
        item["beneficiary_id"]: item["student_account_fence_generation"]
        for item in built.grant_items
    } == {"student-1": 202, "student-2": 203, "student-3": 201}

    condition_targets = {
        (
            operation["ConditionCheck"]["Key"]["PK"],
            operation["ConditionCheck"]["Key"]["SK"],
        )
        for operation in built.grant_operations
        if "ConditionCheck" in operation
    }
    assert ("USER#parent-1", "PROFILE") in condition_targets
    for student_id in selected:
        assert ("USER#parent-1", f"CHILD#{student_id}") in condition_targets
        assert (f"USER#{student_id}", "PARENT#parent-1") in condition_targets
        assert (f"USER#{student_id}", "PROFILE") in condition_targets


@pytest.mark.parametrize(
    ("inactive", "foreign"),
    [
        (frozenset({"student-1"}), frozenset()),
        (frozenset(), frozenset({"student-1"})),
    ],
)
def test_build_paid_activation_operations_rejects_inactive_unbound_and_cross_parent(
    monkeypatch: pytest.MonkeyPatch,
    inactive: frozenset[str],
    foreign: frozenset[str],
) -> None:
    selected = ("student-1",)
    _install_active_relationships(
        monkeypatch,
        selected,
        inactive=inactive,
        foreign_parent=foreign,
    )
    request = _activation_request(plan=BillingPlanId.STUDENT)
    command = _command(selected)
    command["plan_id"] = BillingPlanId.STUDENT.value

    with pytest.raises(paid_entitlement_service.PaidGrantConflict):
        paid_entitlement_service.build_paid_activation_operations(
            request,
            command=command,
            table=_ReadTable(),
        )


def test_atomic_activation_receives_grant_rows_and_binding_conditions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = ("student-1",)
    _install_active_relationships(monkeypatch, selected)
    request = _activation_request(plan=BillingPlanId.STUDENT)
    command = _command(selected)
    command["plan_id"] = BillingPlanId.STUDENT.value
    captured: dict[str, object] = {}

    def commit(
        activation: billing_fact_repo.PaidActivationRequest,
        **kwargs: object,
    ) -> billing_fact_repo.ActivationResult:
        captured["request"] = activation
        captured.update(kwargs)
        return billing_fact_repo.ActivationResult(
            billing_fact_repo.ActivationDisposition.COMMITTED
        )

    monkeypatch.setattr(
        paid_entitlement_service.billing_fact_repo,
        "commit_paid_activation",
        commit,
    )

    result = paid_entitlement_service.commit_paid_activation(
        request,
        command=command,
        billing_projection={
            "PK": "BILLING#parent-1",
            "SK": "PROJECTION",
            "entity_type": "billing_projection",
            "parent_id": "parent-1",
            "plan_id": BillingPlanId.STUDENT.value,
            "plan_version": 2,
            "allowance_version": 2,
            "activation_version": 7,
        },
        allowance_item={
            "PK": "ALLOWANCE_PLAN#parent-1",
            "SK": "CURRENT",
            "entity_type": "allowance_plan",
            "parent_id": "parent-1",
            "plan_id": BillingPlanId.STUDENT.value,
            "plan_version": 2,
            "allowance_version": 2,
            "activation_version": 7,
        },
        table=_ReadTable(),
    )

    assert result.disposition is billing_fact_repo.ActivationDisposition.COMMITTED
    assert len(captured["grant_items"]) == 1
    assert captured["grant_operations"]
    assert captured["table"].__class__ is _ReadTable


def test_binding_race_cancels_command_billing_grants_and_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = ("student-1",)
    _install_active_relationships(monkeypatch, selected)
    request = _activation_request(plan=BillingPlanId.STUDENT)
    command = _command(selected)
    command["plan_id"] = BillingPlanId.STUDENT.value

    class RaceTable(_ReadTable):
        def transact_write_items(self, **kwargs: object) -> None:
            raise RuntimeError("relationship condition changed")

    table = RaceTable()
    monkeypatch.setattr(
        billing_fact_repo,
        "load_activation_facts",
        lambda *_args, **_kwargs: (
            billing_fact_repo.BillingFact(
                factId="fact-invoice",
                checkoutCommandId="cmd-paid-1",
                kind=billing_fact_repo.BillingFactKind.INVOICE_PAID,
                providerEventIdDigest="c" * 64,
                providerObjectIdDigest="d" * 64,
                signatureVerified=True,
                providerLivemode=False,
                factVersion=7,
                observedAt=_NOW,
            ),
            billing_fact_repo.BillingFact(
                factId="fact-subscription",
                checkoutCommandId="cmd-paid-1",
                kind=billing_fact_repo.BillingFactKind.SUBSCRIPTION_ACTIVE,
                providerEventIdDigest="e" * 64,
                providerObjectIdDigest="f" * 64,
                signatureVerified=True,
                providerLivemode=False,
                factVersion=7,
                observedAt=_NOW,
            ),
        ),
    )
    monkeypatch.setattr(
        billing_fact_repo.account_deletion_repo,
        "transact",
        lambda operations, *, table: table.transact_write_items(TransactItems=operations),
    )

    before = deepcopy(table.items)
    result = paid_entitlement_service.commit_paid_activation(
        request,
        command=command,
        billing_projection={
            "PK": "BILLING#parent-1",
            "SK": "PROJECTION",
            "entity_type": "billing_projection",
            "parent_id": "parent-1",
            "plan_id": BillingPlanId.STUDENT.value,
            "plan_version": 2,
            "allowance_version": 2,
            "activation_version": 7,
        },
        allowance_item={
            "PK": "ALLOWANCE_PLAN#parent-1",
            "SK": "CURRENT",
            "entity_type": "allowance_plan",
            "parent_id": "parent-1",
            "plan_id": BillingPlanId.STUDENT.value,
            "plan_version": 2,
            "allowance_version": 2,
            "activation_version": 7,
        },
        table=table,
    )
    assert result.disposition in {
        billing_fact_repo.ActivationDisposition.CONFLICT,
        billing_fact_repo.ActivationDisposition.RETRYABLE,
    }
    assert table.items == before


def test_active_grant_lookup_is_exact_owner_scoped_and_future_child_is_not_granted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_active_relationships(monkeypatch, ("student-1", "student-new"))
    table = _ReadTable(
        {
            ("PAID_GRANT#parent-1", "BENEFICIARY#student-1"): {
                "PK": "PAID_GRANT#parent-1",
                "SK": "BENEFICIARY#student-1",
                "entity_type": "beneficiary_grant",
                "schema_version": "paid_beneficiary_grant.v1",
                "parent_id": "parent-1",
                "beneficiary_id": "student-1",
                "grant_status": "active",
                "grant_version": 7,
                "plan_id": BillingPlanId.FAMILY.value,
                "plan_version": 2,
                "allowance_version": 2,
                "subscription_id_digest": _DIGEST,
                "activation_version": 7,
                "activated_at": _NOW.isoformat(),
            }
        }
    )

    assert (
        paid_entitlement_service.get_active_beneficiary_grant(
            "parent-1",
            "student-1",
            table=table,
        )
        is not None
    )
    assert (
        paid_entitlement_service.get_active_beneficiary_grant(
            "parent-1",
            "student-new",
            table=table,
        )
        is None
    )
    assert (
        paid_entitlement_service.get_active_beneficiary_grant(
            "other-parent",
            "student-1",
            table=table,
        )
        is None
    )


def test_entitlement_resolver_uses_exact_grant_not_parent_plan_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    parent = {
        "user_id": "parent-1",
        "role": "parent",
        "subscription_tier": BillingPlanId.FAMILY.value,
    }
    student = {
        "user_id": "student-1",
        "role": "student",
        "subscription_tier": BillingPlanId.FREE_TRIAL.value,
        "parent_id": "parent-1",
        "parent_binding_status": "active",
    }
    monkeypatch.setattr(
        entitlement_service.user_repo,
        "get_user",
        lambda user_id: parent if user_id == "parent-1" else student,
    )
    monkeypatch.setattr(
        entitlement_service,
        "_active_parent_binding",
        lambda *_args: {"status": "active"},
    )
    monkeypatch.setattr(
        entitlement_service,
        "_get_billing_item",
        lambda *_args: {
            "billing_status": "active",
            "subscription_tier": BillingPlanId.FAMILY.value,
        },
    )
    monkeypatch.setattr(entitlement_service, "_get_payment_rollout_item", lambda: None)
    monkeypatch.setattr(
        entitlement_service.paid_entitlement_service,
        "get_active_beneficiary_grant",
        lambda *_args, **_kwargs: None,
    )
    assert (
        entitlement_service.resolve_student_entitlement(
            "student-1",
            settings=settings,
            student_profile=student,
        )["effectivePlan"]
        == BillingPlanId.FREE_TRIAL.value
    )

    monkeypatch.setattr(
        entitlement_service.paid_entitlement_service,
        "get_active_beneficiary_grant",
        lambda *_args, **_kwargs: {
            "grant_status": "active",
            "plan_id": BillingPlanId.FAMILY.value,
            "plan_version": 2,
            "allowance_version": 2,
        },
    )
    resolved = entitlement_service.resolve_student_entitlement(
        "student-1",
        settings=settings,
        student_profile=student,
    )
    assert resolved["effectivePlan"] == BillingPlanId.FAMILY.value
    assert resolved["source"] == "paid_beneficiary_grant"


def test_upgrade_publishes_higher_versions_without_counter_or_storage_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = ("student-1",)
    _install_active_relationships(monkeypatch, selected)
    grant = {
        "PK": "PAID_GRANT#parent-1",
        "SK": "BENEFICIARY#student-1",
        "entity_type": "beneficiary_grant",
        "schema_version": "paid_beneficiary_grant.v1",
        "parent_id": "parent-1",
        "beneficiary_id": "student-1",
        "grant_status": "active",
        "command_id": "cmd-paid-1",
        "subscription_id_digest": _DIGEST,
        "grant_version": 7,
        "plan_id": BillingPlanId.STUDENT.value,
        "plan_version": 2,
        "allowance_version": 2,
        "activation_version": 7,
        "activated_at": _NOW.isoformat(),
    }
    counter = {
        "PK": "ALLOWANCE#student-1",
        "SK": "WEEK#2026-W30",
        "finalized_input_tokens": 123,
        "reserved_input_tokens": 45,
        "finalized_output_tokens": 67,
        "reserved_output_tokens": 8,
        "finalized_support_cases": 2,
        "reserved_support_cases": 1,
    }
    storage = {
        "PK": "ATTACHMENT_STORAGE#student-1",
        "SK": "USAGE",
        "used_bytes": 987654,
    }
    table = _ReadTable(
        {
            ("PAID_GRANT#parent-1", "BENEFICIARY#student-1"): grant,
            ("ALLOWANCE#student-1", "WEEK#2026-W30"): counter,
            ("ATTACHMENT_STORAGE#student-1", "USAGE"): storage,
        }
    )
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        paid_entitlement_service.account_deletion_repo,
        "transact",
        lambda operations, *, table: captured.extend(deepcopy(operations)),
    )

    result = paid_entitlement_service.apply_paid_upgrade(
        parent_id="parent-1",
        beneficiary_ids=selected,
        subscription_id_digest=_DIGEST,
        command_id="cmd-upgrade-1",
        plan_id=BillingPlanId.TEACHER_SUPPORTED,
        plan_version=3,
        allowance_version=3,
        activation_version=8,
        activated_at=_NOW,
        table=table,
    )

    assert result.disposition is paid_entitlement_service.PaidGrantDisposition.UPGRADED
    put_items = [
        operation["Put"]["Item"]
        for operation in captured
        if "Put" in operation
    ]
    upgraded_grant = next(item for item in put_items if item["entity_type"] == "beneficiary_grant")
    assert upgraded_grant["plan_id"] == BillingPlanId.TEACHER_SUPPORTED.value
    assert upgraded_grant["plan_version"] == 3
    assert upgraded_grant["allowance_version"] == 3
    assert upgraded_grant["grant_version"] == 8
    assert all(
        not str(item["PK"]).startswith(("ALLOWANCE#student-", "ATTACHMENT_STORAGE#"))
        for item in put_items
    )
    assert table.items[("ALLOWANCE#student-1", "WEEK#2026-W30")] == counter
    assert table.items[("ATTACHMENT_STORAGE#student-1", "USAGE")] == storage


def test_duplicate_upgrade_replays_one_grant_and_one_allowance_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = ("student-1",)
    _install_active_relationships(monkeypatch, selected)
    upgraded = {
        "PK": "PAID_GRANT#parent-1",
        "SK": "BENEFICIARY#student-1",
        "entity_type": "beneficiary_grant",
        "schema_version": "paid_beneficiary_grant.v1",
        "parent_id": "parent-1",
        "beneficiary_id": "student-1",
        "grant_status": "active",
        "command_id": "cmd-upgrade-1",
        "subscription_id_digest": _DIGEST,
        "grant_version": 8,
        "plan_id": BillingPlanId.TEACHER_SUPPORTED.value,
        "plan_version": 3,
        "allowance_version": 3,
        "activation_version": 8,
        "activated_at": _NOW.isoformat(),
    }
    table = _ReadTable(
        {("PAID_GRANT#parent-1", "BENEFICIARY#student-1"): upgraded}
    )
    monkeypatch.setattr(
        paid_entitlement_service.account_deletion_repo,
        "transact",
        lambda *_args, **_kwargs: pytest.fail("duplicate upgrade must not transact"),
    )

    result = paid_entitlement_service.apply_paid_upgrade(
        parent_id="parent-1",
        beneficiary_ids=selected,
        subscription_id_digest=_DIGEST,
        command_id="cmd-upgrade-1",
        plan_id=BillingPlanId.TEACHER_SUPPORTED,
        plan_version=3,
        allowance_version=3,
        activation_version=8,
        activated_at=_NOW,
        table=table,
    )
    assert result.disposition is paid_entitlement_service.PaidGrantDisposition.ALREADY_APPLIED


def test_source_key_link_uses_grant_operations_in_atomic_paid_activation() -> None:
    source = (
        paid_entitlement_service.__file__
        and open(paid_entitlement_service.__file__, encoding="utf-8").read()
    )
    assert "billing_fact_repo.commit_paid_activation" in source
    assert "grant_operations=built.grant_operations" in source
