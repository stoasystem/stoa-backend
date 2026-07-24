"""Fact-oriented billing persistence and exact-once activation contract."""

from __future__ import annotations

import inspect
from copy import deepcopy
from datetime import datetime
from typing import Any

import pytest

from stoa.db.repositories import billing_fact_repo
from stoa.models.billing import BillingFact, BillingFactKind, BillingPlanId


NOW = "2026-07-24T09:00:00+00:00"


class AtomicBillingTable:
    """Small DynamoDB fake that applies the repository's transaction shapes atomically."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, object]] = {}
        self.transactions: list[list[dict[str, Any]]] = []
        self.fail_next_transaction = False

    def get_item(self, *, Key: dict[str, str], ConsistentRead: bool) -> dict[str, object]:
        assert ConsistentRead is True
        item = self.rows.get((Key["PK"], Key["SK"]))
        return {"Item": deepcopy(item)} if item is not None else {}

    def query(
        self,
        *,
        KeyConditionExpression: str,
        ExpressionAttributeValues: dict[str, object],
        ConsistentRead: bool,
    ) -> dict[str, object]:
        assert KeyConditionExpression == "PK=:pk"
        assert ConsistentRead is True
        pk = str(ExpressionAttributeValues[":pk"])
        return {
            "Items": [
                deepcopy(item)
                for (row_pk, _), item in sorted(self.rows.items())
                if row_pk == pk
            ]
        }

    def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
        if self.fail_next_transaction:
            self.fail_next_transaction = False
            raise RuntimeError("injected transaction failure")
        snapshot = deepcopy(self.rows)
        for operation in operations:
            if "Put" in operation:
                put = operation["Put"]
                item = deepcopy(put["Item"])
                key = (str(item["PK"]), str(item["SK"]))
                if "attribute_not_exists" in put.get("ConditionExpression", "") and key in snapshot:
                    raise RuntimeError("conditional conflict")
                snapshot[key] = item
                continue

            if "Update" in operation:
                update = operation["Update"]
                key = (update["Key"]["PK"], update["Key"]["SK"])
                current = snapshot.get(key)
                values = update["ExpressionAttributeValues"]
                if current is None:
                    raise RuntimeError("conditional conflict")
                if ":expected_object_version" in values:
                    if current.get("object_version") != values[":expected_object_version"]:
                        raise RuntimeError("conditional conflict")
                    current = deepcopy(values[":next_item"])
                elif ":now_epoch" in values:
                    if int(current.get("lease_expires_at", 0)) > values[":now_epoch"]:
                        raise RuntimeError("conditional conflict")
                    current.update(
                        lease_owner=values[":lease_owner"],
                        lease_generation=values[":next_generation"],
                        lease_expires_at=values[":lease_expires_at"],
                        updated_at=values[":updated_at"],
                    )
                elif ":expected_command_version" in values:
                    required = {
                        "command_version": values[":expected_command_version"],
                        "parent_id": values[":parent_id"],
                        "provider_customer_id_digest": values[
                            ":provider_customer_id_digest"
                        ],
                        "price_id": values[":price_id"],
                        "environment": values[":environment"],
                        "plan_id": values[":plan_id"],
                        "plan_version": values[":plan_version"],
                    }
                    if any(current.get(field) != expected for field, expected in required.items()):
                        raise RuntimeError("conditional conflict")
                    current.update(
                        command_state=values[":activation_recorded"],
                        command_version=values[":next_command_version"],
                        activation_version=values[":activation_version"],
                        paid_invoice_fact_id=values[":paid_invoice_fact_id"],
                        active_subscription_fact_id=values[
                            ":active_subscription_fact_id"
                        ],
                        allowance_version=values[":allowance_version"],
                        updated_at=values[":activated_at"],
                    )
                else:
                    raise AssertionError(f"unexpected update: {operation}")
                snapshot[key] = current
                continue

            raise AssertionError(f"unexpected operation: {operation}")

        self.rows = snapshot
        self.transactions.append(deepcopy(operations))

    def put_command(
        self,
        *,
        command_id: str = "checkout-command-1",
        customer_digest: str = "a" * 64,
        price_id: str = "price_test_family_v7",
        environment: str = "test",
    ) -> None:
        self.rows[(f"CHECKOUT_COMMAND#{command_id}", "COMMAND")] = {
            "PK": f"CHECKOUT_COMMAND#{command_id}",
            "SK": "COMMAND",
            "entity_type": "checkout_command",
            "command_id": command_id,
            "parent_id": "parent-1",
            "command_version": 7,
            "command_state": "reconciling",
            "provider_customer_id_digest": customer_digest,
            "price_id": price_id,
            "environment": environment,
            "plan_id": "family",
            "plan_version": 11,
        }


def _fact(
    kind: BillingFactKind,
    *,
    fact_id: str,
    object_digest: str,
    version: int,
    observed_at: str = NOW,
) -> BillingFact:
    return BillingFact(
        factId=fact_id,
        checkoutCommandId="checkout-command-1",
        kind=kind,
        providerEventIdDigest="e" * 64,
        providerObjectIdDigest=object_digest,
        signatureVerified=True,
        providerLivemode=False,
        factVersion=version,
        observedAt=datetime.fromisoformat(observed_at),
    )


def _record_activation_facts(table: AtomicBillingTable) -> tuple[BillingFact, BillingFact]:
    invoice = _fact(
        BillingFactKind.INVOICE_PAID,
        fact_id="invoice-fact-1",
        object_digest="1" * 64,
        version=3,
    )
    subscription = _fact(
        BillingFactKind.SUBSCRIPTION_ACTIVE,
        fact_id="subscription-fact-1",
        object_digest="2" * 64,
        version=5,
    )
    assert billing_fact_repo.record_provider_fact(invoice, table=table).accepted
    assert billing_fact_repo.record_provider_fact(subscription, table=table).accepted
    return invoice, subscription


def _activation_request(
    invoice: BillingFact,
    subscription: BillingFact,
    **changes: object,
) -> billing_fact_repo.PaidActivationRequest:
    values: dict[str, object] = {
        "command_id": "checkout-command-1",
        "parent_id": "parent-1",
        "expected_command_version": 7,
        "provider_customer_id_digest": "a" * 64,
        "price_id": "price_test_family_v7",
        "environment": "test",
        "plan_id": BillingPlanId.FAMILY,
        "plan_version": 11,
        "allowance_version": 13,
        "activation_version": 17,
        "paid_invoice_fact_id": invoice.fact_id,
        "active_subscription_fact_id": subscription.fact_id,
        "activated_at": NOW,
    }
    values.update(changes)
    return billing_fact_repo.PaidActivationRequest(**values)


def _activation_items() -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    projection = {
        "PK": "BILLING#parent-1",
        "SK": "PROJECTION",
        "entity_type": "billing_projection",
        "parent_id": "parent-1",
        "plan_id": "family",
        "plan_version": 11,
        "allowance_version": 13,
        "activation_version": 17,
    }
    grants = [
        {
            "PK": "PLAN_GRANT#parent-1",
            "SK": "STUDENT#student-1",
            "entity_type": "beneficiary_grant",
            "parent_id": "parent-1",
            "beneficiary_id": "student-1",
            "plan_id": "family",
            "plan_version": 11,
            "allowance_version": 13,
            "activation_version": 17,
        },
        {
            "PK": "PLAN_GRANT#parent-1",
            "SK": "STUDENT#student-2",
            "entity_type": "beneficiary_grant",
            "parent_id": "parent-1",
            "beneficiary_id": "student-2",
            "plan_id": "family",
            "plan_version": 11,
            "allowance_version": 13,
            "activation_version": 17,
        },
    ]
    allowance = {
        "PK": "ALLOWANCE#parent-1",
        "SK": "PLAN",
        "entity_type": "allowance_plan",
        "parent_id": "parent-1",
        "plan_id": "family",
        "plan_version": 11,
        "allowance_version": 13,
        "activation_version": 17,
    }
    return projection, grants, allowance


def test_repository_links_billing_fact_contract_and_avoids_global_event_ordering() -> None:
    source = inspect.getsource(billing_fact_repo)
    assert "BillingFact" in source
    assert "BillingFactKind" in source
    assert "last_provider_event_at" not in source
    assert "event.created" not in source


def test_event_id_and_semantic_duplicates_preserve_redacted_audit_receipts() -> None:
    table = AtomicBillingTable()
    first = billing_fact_repo.register_provider_event(
        provider_event_id="evt_private_canary_1",
        event_type="invoice.paid",
        provider_object_id="in_private_canary_1",
        object_version=3,
        fact_observed_at=NOW,
        table=table,
    )
    event_duplicate = billing_fact_repo.register_provider_event(
        provider_event_id="evt_private_canary_1",
        event_type="invoice.paid",
        provider_object_id="in_private_canary_1",
        object_version=3,
        fact_observed_at=NOW,
        table=table,
    )
    semantic_duplicate = billing_fact_repo.register_provider_event(
        provider_event_id="evt_private_canary_2",
        event_type="invoice.paid",
        provider_object_id="in_private_canary_1",
        object_version=3,
        fact_observed_at=NOW,
        table=table,
    )

    assert first.disposition is billing_fact_repo.BillingEventDisposition.REGISTERED
    assert event_duplicate.disposition is billing_fact_repo.BillingEventDisposition.EVENT_DUPLICATE
    assert (
        semantic_duplicate.disposition
        is billing_fact_repo.BillingEventDisposition.SEMANTIC_DUPLICATE
    )
    inbox = [
        item
        for item in table.rows.values()
        if item.get("schema_version") == "billing_event_inbox.v1"
    ]
    semantic = [
        item
        for item in table.rows.values()
        if item.get("schema_version") == "billing_semantic_dedupe.v1"
    ]
    assert len(inbox) == 2
    assert len(semantic) == 1
    persisted = repr((inbox, semantic))
    assert "evt_private_canary" not in persisted
    assert "in_private_canary" not in persisted
    assert "payload" not in persisted.lower()
    assert "signature" not in persisted.lower()
    assert "card" not in persisted.lower()
    assert "checkout_url" not in persisted.lower()


@pytest.mark.parametrize("order", ["invoice_first", "subscription_first"])
def test_invoice_and_subscription_order_converge_to_same_fact_set(order: str) -> None:
    table = AtomicBillingTable()
    invoice = _fact(
        BillingFactKind.INVOICE_PAID,
        fact_id="invoice-fact-1",
        object_digest="1" * 64,
        version=3,
    )
    subscription = _fact(
        BillingFactKind.SUBSCRIPTION_ACTIVE,
        fact_id="subscription-fact-1",
        object_digest="2" * 64,
        version=5,
    )
    facts = [invoice, subscription]
    if order == "subscription_first":
        facts.reverse()
    for fact in facts:
        assert billing_fact_repo.record_provider_fact(fact, table=table).accepted

    loaded = billing_fact_repo.load_activation_facts("checkout-command-1", table=table)
    assert {
        (fact.kind, fact.fact_id, fact.fact_version)
        for fact in loaded
    } == {
        (BillingFactKind.INVOICE_PAID, "invoice-fact-1", 3),
        (BillingFactKind.SUBSCRIPTION_ACTIVE, "subscription-fact-1", 5),
    }


def test_equal_timestamps_remain_independent_and_delayed_snapshot_cannot_regress() -> None:
    table = AtomicBillingTable()
    invoice = _fact(
        BillingFactKind.INVOICE_PAID,
        fact_id="invoice-fact-new",
        object_digest="1" * 64,
        version=9,
    )
    subscription = _fact(
        BillingFactKind.SUBSCRIPTION_ACTIVE,
        fact_id="subscription-fact-equal-time",
        object_digest="2" * 64,
        version=7,
    )
    old_invoice = _fact(
        BillingFactKind.INVOICE_PAID,
        fact_id="invoice-fact-old",
        object_digest="1" * 64,
        version=8,
        observed_at="2026-07-23T09:00:00+00:00",
    )
    assert billing_fact_repo.record_provider_fact(invoice, table=table).accepted
    assert billing_fact_repo.record_provider_fact(subscription, table=table).accepted
    stale = billing_fact_repo.record_provider_fact(old_invoice, table=table)
    assert stale.disposition is billing_fact_repo.FactRecordDisposition.STALE
    loaded = billing_fact_repo.load_activation_facts("checkout-command-1", table=table)
    assert {(fact.fact_id, fact.fact_version) for fact in loaded} == {
        ("invoice-fact-new", 9),
        ("subscription-fact-equal-time", 7),
    }


def test_reconciliation_lease_is_bounded_and_fenced_by_generation() -> None:
    table = AtomicBillingTable()
    first = billing_fact_repo.claim_fact_reconciliation(
        "checkout-command-1",
        lease_owner="worker-1",
        now_epoch=100,
        lease_seconds=30,
        now_iso=NOW,
        table=table,
    )
    busy = billing_fact_repo.claim_fact_reconciliation(
        "checkout-command-1",
        lease_owner="worker-2",
        now_epoch=110,
        lease_seconds=30,
        now_iso=NOW,
        table=table,
    )
    takeover = billing_fact_repo.claim_fact_reconciliation(
        "checkout-command-1",
        lease_owner="worker-2",
        now_epoch=130,
        lease_seconds=30,
        now_iso=NOW,
        table=table,
    )
    assert first.disposition is billing_fact_repo.ReconciliationDisposition.CLAIMED
    assert busy.disposition is billing_fact_repo.ReconciliationDisposition.LEASE_BUSY
    assert takeover.disposition is billing_fact_repo.ReconciliationDisposition.CLAIMED
    assert first.claim is not None and takeover.claim is not None
    assert first.claim.lease_generation == 1
    assert takeover.claim.lease_generation == 2
    with pytest.raises(ValueError, match="lease_seconds"):
        billing_fact_repo.claim_fact_reconciliation(
            "checkout-command-1",
            lease_owner="worker-3",
            now_epoch=200,
            lease_seconds=301,
            now_iso=NOW,
            table=table,
        )


def test_activation_transaction_has_unique_targets_binding_conditions_and_absent_receipt() -> None:
    table = AtomicBillingTable()
    table.put_command()
    invoice, subscription = _record_activation_facts(table)
    projection, grants, allowance = _activation_items()

    result = billing_fact_repo.commit_paid_activation(
        _activation_request(invoice, subscription),
        billing_projection=projection,
        grant_items=grants,
        allowance_item=allowance,
        table=table,
    )

    assert result.disposition is billing_fact_repo.ActivationDisposition.COMMITTED
    operations = list(result.operations)
    targets = []
    for operation in operations:
        body = operation.get("Put") or operation.get("Update")
        targets.append((body.get("Item") or body.get("Key"))["PK"])
        targets[-1] = (targets[-1], (body.get("Item") or body.get("Key"))["SK"])
    assert len(targets) == len(set(targets))
    command_update = operations[0]["Update"]
    condition = command_update["ConditionExpression"]
    for token in (
        "command_version",
        "provider_customer_id_digest",
        "price_id",
        "environment",
        "plan_id",
        "plan_version",
    ):
        assert token in condition
    receipt = operations[-1]["Put"]
    assert receipt["Item"]["schema_version"] == "billing_activation_receipt.v1"
    assert "attribute_not_exists(PK)" in receipt["ConditionExpression"]
    assert table.rows[
        ("CHECKOUT_COMMAND#checkout-command-1", "COMMAND")
    ]["command_state"] == "activation_recorded"


def test_activation_rejects_mismatch_live_mode_and_duplicate_item_targets() -> None:
    table = AtomicBillingTable()
    table.put_command()
    invoice, subscription = _record_activation_facts(table)
    projection, grants, allowance = _activation_items()

    with pytest.raises(ValueError, match="test-mode"):
        billing_fact_repo.commit_paid_activation(
            _activation_request(invoice, subscription, environment="production"),
            billing_projection=projection,
            grant_items=grants,
            allowance_item=allowance,
            table=table,
        )
    duplicate = dict(grants[0])
    duplicate["beneficiary_id"] = "student-other"
    with pytest.raises(ValueError, match="unique"):
        billing_fact_repo.commit_paid_activation(
            _activation_request(invoice, subscription),
            billing_projection=projection,
            grant_items=[grants[0], duplicate],
            allowance_item=allowance,
            table=table,
        )
    wrong_customer = billing_fact_repo.commit_paid_activation(
        _activation_request(invoice, subscription, provider_customer_id_digest="b" * 64),
        billing_projection=projection,
        grant_items=grants,
        allowance_item=allowance,
        table=table,
    )
    assert wrong_customer.disposition is billing_fact_repo.ActivationDisposition.CONFLICT


def test_injected_activation_failure_leaves_every_target_unchanged() -> None:
    table = AtomicBillingTable()
    table.put_command()
    invoice, subscription = _record_activation_facts(table)
    projection, grants, allowance = _activation_items()
    before = deepcopy(table.rows)
    table.fail_next_transaction = True

    result = billing_fact_repo.commit_paid_activation(
        _activation_request(invoice, subscription),
        billing_projection=projection,
        grant_items=grants,
        allowance_item=allowance,
        table=table,
    )

    assert result.disposition is billing_fact_repo.ActivationDisposition.RETRYABLE
    assert table.rows == before
    assert not any(
        row.get("schema_version") == "billing_activation_receipt.v1"
        for row in table.rows.values()
    )


def test_fact_rows_round_trip_through_closed_billing_fact_model_without_sensitive_fields() -> None:
    table = AtomicBillingTable()
    fact = _fact(
        BillingFactKind.INVOICE_PAID,
        fact_id="invoice-fact-safe",
        object_digest="3" * 64,
        version=4,
    )
    result = billing_fact_repo.record_provider_fact(fact, table=table)
    assert result.accepted
    row = next(
        item
        for item in table.rows.values()
        if item.get("schema_version") == "billing_object_fact.v1"
    )
    assert billing_fact_repo.billing_fact_from_item(row) == fact
    assert set(row) <= {
        "PK",
        "SK",
        "entity_type",
        "schema_version",
        "fact_id",
        "checkout_command_id",
        "kind",
        "provider_event_id_digest",
        "provider_object_id_digest",
        "object_version",
        "fact_observed_at",
        "processing_result",
    }
    canaries = ("payload", "signature", "card", "cvc", "secret", "checkout_url")
    assert not any(canary in repr(row).lower() for canary in canaries)
