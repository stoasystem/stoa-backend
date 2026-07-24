"""Durable checkout-command repository security and recovery contract."""

from __future__ import annotations

import inspect
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import pytest

from stoa.db.repositories import checkout_command_repo
from stoa.models.billing import CheckoutCommandState, CheckoutIntent, PurchasablePlanId


NOW = "2026-07-24T08:20:00+00:00"


class AtomicCheckoutTable:
    """Small synchronized fake for the repository's exact transaction shapes."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, object]] = {}
        self.lock = threading.Lock()
        self.transactions: list[list[dict[str, Any]]] = []
        self.successful_creates = 0
        self.commit_then_timeout_updates: set[str] = set()

    def add_active_fence(self, parent_id: str, generation: int = 1) -> None:
        self.rows[(f"USER#{parent_id}", "ACCOUNT_FENCE")] = {
            "PK": f"USER#{parent_id}",
            "SK": "ACCOUNT_FENCE",
            "status": "active",
            "generation": generation,
        }

    def get_item(self, *, Key: dict[str, str], ConsistentRead: bool) -> dict[str, object]:
        assert ConsistentRead is True
        with self.lock:
            item = self.rows.get((Key["PK"], Key["SK"]))
            return {"Item": dict(item)} if item is not None else {}

    def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
        with self.lock:
            snapshot = {key: dict(value) for key, value in self.rows.items()}
            update_kind = ""
            for operation in operations:
                if "ConditionCheck" in operation:
                    check = operation["ConditionCheck"]
                    key = (check["Key"]["PK"], check["Key"]["SK"])
                    current = snapshot.get(key)
                    values = check.get("ExpressionAttributeValues", {})
                    if key[1] == "ACCOUNT_FENCE":
                        if current is None or current.get("status") != "active":
                            raise RuntimeError("conditional conflict")
                        if ":generation" in values and current.get("generation") != values[":generation"]:
                            raise RuntimeError("conditional conflict")
                    else:
                        if current is None:
                            raise RuntimeError("conditional conflict")
                        if ":command_version" in values and (
                            current.get("command_version") != values[":command_version"]
                        ):
                            raise RuntimeError("conditional conflict")
                        terminal_states = values.get(":terminal_states")
                        if terminal_states is not None and current.get("command_state") not in terminal_states:
                            raise RuntimeError("conditional conflict")
                    continue

                if "Put" in operation:
                    put = operation["Put"]
                    item = dict(put["Item"])
                    key = (str(item["PK"]), str(item["SK"]))
                    if key in snapshot:
                        raise RuntimeError("conditional conflict")
                    snapshot[key] = item
                    continue

                if "Update" in operation:
                    update = operation["Update"]
                    key = (update["Key"]["PK"], update["Key"]["SK"])
                    current = snapshot.get(key)
                    if current is None:
                        raise RuntimeError("conditional conflict")
                    values = update["ExpressionAttributeValues"]
                    if current.get("command_version") != values[":expected_version"]:
                        raise RuntimeError("conditional conflict")
                    if ":expected_effect_status" in values and (
                        current.get("provider_effect_status")
                        != values[":expected_effect_status"]
                    ):
                        raise RuntimeError("conditional conflict")
                    if ":expected_lease_owner" in values and (
                        current.get("lease_owner") != values[":expected_lease_owner"]
                        or current.get("lease_generation") != values[":expected_lease_generation"]
                    ):
                        raise RuntimeError("conditional conflict")
                    if ":now_epoch" in values:
                        status = current.get("provider_effect_status")
                        expiry = current.get("lease_expires_at")
                        claimable = status == "not_started" or (
                            status in {"create_claimed", "provider_outcome_unknown"}
                            and isinstance(expiry, int)
                            and expiry <= values[":now_epoch"]
                        )
                        if not claimable:
                            raise RuntimeError("conditional conflict")

                    if ":claimed" in values:
                        update_kind = "claim"
                        current.update(
                            provider_effect_status=values[":claimed"],
                            command_state=values[":pending_state"],
                            lease_owner=values[":lease_owner"],
                            lease_generation=values[":next_lease_generation"],
                            lease_expires_at=values[":lease_expires_at"],
                            command_version=values[":next_version"],
                            updated_at=values[":updated_at"],
                        )
                    elif ":attached" in values:
                        update_kind = "attach"
                        current.update(
                            provider_effect_status=values[":attached"],
                            command_state=values[":open_state"],
                            provider_session_id=values[":provider_session_id"],
                            provider_session_url=values[":provider_session_url"],
                            provider_session_id_digest=values[":provider_session_id_digest"],
                            command_version=values[":next_version"],
                            updated_at=values[":updated_at"],
                        )
                    elif ":unknown" in values:
                        update_kind = "unknown"
                        current.update(
                            provider_effect_status=values[":unknown"],
                            command_state=values[":attention_state"],
                            command_version=values[":next_version"],
                            updated_at=values[":updated_at"],
                        )
                    snapshot[key] = current
                    continue

                if "Delete" in operation:
                    delete = operation["Delete"]
                    key = (delete["Key"]["PK"], delete["Key"]["SK"])
                    current = snapshot.get(key)
                    values = delete["ExpressionAttributeValues"]
                    if (
                        current is None
                        or current.get("command_id") != values[":command_id"]
                        or current.get("command_version") != values[":command_version"]
                    ):
                        raise RuntimeError("conditional conflict")
                    del snapshot[key]
                    update_kind = "release"
                    continue

                raise AssertionError(f"unexpected operation: {operation}")

            self.rows = snapshot
            self.transactions.append(operations)
            if sum("Put" in operation for operation in operations) == 3:
                self.successful_creates += 1
            if update_kind in self.commit_then_timeout_updates:
                self.commit_then_timeout_updates.remove(update_kind)
                raise RuntimeError("response lost after commit")

    def command_rows(self) -> list[dict[str, object]]:
        return [
            dict(item)
            for item in self.rows.values()
            if item.get("entity_type") == "checkout_command"
        ]


def _intent(
    *,
    parent_id: str = "parent-private-canary",
    idempotency_key: str = "browser-private-canary",
    plan: PurchasablePlanId = PurchasablePlanId.FAMILY,
    beneficiaries: tuple[str, ...] = ("student-b", "student-a"),
) -> CheckoutIntent:
    command_id = checkout_command_repo.checkout_command_id(parent_id, idempotency_key)
    return CheckoutIntent(
        commandId=command_id,
        parentId=parent_id,
        idempotencyKey=idempotency_key,
        planId=plan,
        beneficiaryIds=beneficiaries,
        priceCatalogVersion=7,
        planVersion=11,
        createdAt=datetime.fromisoformat(NOW),
    )


def _register(
    table: AtomicCheckoutTable,
    *,
    intent: CheckoutIntent | None = None,
    public_ref: str | None = None,
) -> checkout_command_repo.CheckoutCommandResult:
    value = intent or _intent()
    table.add_active_fence(value.parent_id)
    return checkout_command_repo.register_checkout_command(
        value,
        price_id="price_test_family_v7",
        environment="test",
        public_ref=public_ref,
        now_iso=NOW,
        table=table,
    )


def test_repository_contract_links_checkout_models_and_has_no_provider_dependency() -> None:
    source = inspect.getsource(checkout_command_repo)
    assert "CheckoutIntent" in source
    assert "CheckoutCommandState" in source
    assert "stripe" not in source.lower()
    assert "requests" not in source.lower()
    assert "provider_call" not in inspect.signature(
        checkout_command_repo.register_checkout_command
    ).parameters


def test_fingerprint_is_canonical_and_binds_every_immutable_intent_coordinate() -> None:
    first = _intent()
    reordered = _intent(beneficiaries=("student-a", "student-b"))
    assert checkout_command_repo.checkout_intent_fingerprint(
        first, price_id="price_test_family_v7", environment="test"
    ) == checkout_command_repo.checkout_intent_fingerprint(
        reordered, price_id="price_test_family_v7", environment="test"
    )

    baseline = checkout_command_repo.checkout_intent_fingerprint(
        first, price_id="price_test_family_v7", environment="test"
    )
    variants = [
        (_intent(parent_id="other-parent"), "price_test_family_v7", "test"),
        (
            _intent(plan=PurchasablePlanId.STUDENT, beneficiaries=("student-a",)),
            "price_test_student_v7",
            "test",
        ),
        (_intent(beneficiaries=("student-a", "student-c")), "price_test_family_v7", "test"),
        (_intent(), "price_test_family_v8", "test"),
        (_intent(), "price_test_family_v7", "staging"),
    ]
    for intent, price_id, environment in variants:
        assert (
            checkout_command_repo.checkout_intent_fingerprint(
                intent, price_id=price_id, environment=environment
            )
            != baseline
        )


def test_registration_atomically_creates_three_distinct_rows_behind_parent_fence() -> None:
    table = AtomicCheckoutTable()
    result = _register(table, public_ref="co_public_reference_1234567890")

    assert result.disposition is checkout_command_repo.CheckoutCommandDisposition.CREATED
    assert result.command is not None
    operations = result.operations
    assert len(operations) == 4
    assert operations[0]["ConditionCheck"]["Key"] == {
        "PK": "USER#parent-private-canary",
        "SK": "ACCOUNT_FENCE",
    }
    assert operations[0]["ConditionCheck"]["ExpressionAttributeValues"] == {
        ":active": "active",
        ":generation": 1,
    }
    put_targets = {
        (operation["Put"]["Item"]["PK"], operation["Put"]["Item"]["SK"])
        for operation in operations[1:]
    }
    assert len(put_targets) == 3
    assert {operation["Put"]["Item"]["schema_version"] for operation in operations[1:]} == {
        "checkout_command.v1",
        "checkout_open_guard.v1",
        "checkout_public_lookup.v1",
    }


def test_twenty_synchronized_identical_registrations_create_once_and_replay() -> None:
    table = AtomicCheckoutTable()
    table.add_active_fence("parent-private-canary")
    barrier = threading.Barrier(20)
    results: list[checkout_command_repo.CheckoutCommandResult] = []

    def worker() -> None:
        barrier.wait()
        results.append(
            checkout_command_repo.register_checkout_command(
                _intent(),
                price_id="price_test_family_v7",
                environment="test",
                now_iso=NOW,
                table=table,
            )
        )

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert Counter(result.disposition for result in results) == {
        checkout_command_repo.CheckoutCommandDisposition.CREATED: 1,
        checkout_command_repo.CheckoutCommandDisposition.REPLAYED: 19,
    }
    assert table.successful_creates == 1
    assert len(table.command_rows()) == 1
    assert len({result.command["checkout_ref"] for result in results if result.command}) == 1


def test_same_key_changed_intent_mismatches_without_additional_write() -> None:
    table = AtomicCheckoutTable()
    original = _register(table)
    before = {key: dict(value) for key, value in table.rows.items()}
    changed = _intent(beneficiaries=("student-a", "student-c"))
    result = checkout_command_repo.register_checkout_command(
        changed,
        price_id="price_test_family_v7",
        environment="test",
        now_iso=NOW,
        table=table,
    )
    assert original.command is not None
    assert result.disposition is checkout_command_repo.CheckoutCommandDisposition.IDENTITY_MISMATCH
    assert result.command is None
    assert table.rows == before


def test_different_key_cannot_bypass_one_open_command_guard() -> None:
    table = AtomicCheckoutTable()
    _register(table)
    result = checkout_command_repo.register_checkout_command(
        _intent(idempotency_key="another-browser-key"),
        price_id="price_test_family_v7",
        environment="test",
        now_iso=NOW,
        table=table,
    )
    assert result.disposition is checkout_command_repo.CheckoutCommandDisposition.OPEN_COMMAND_EXISTS
    assert len(table.command_rows()) == 1


def test_public_reference_and_provider_key_are_unrelated_non_pii_stable_tokens() -> None:
    table = AtomicCheckoutTable()
    result = _register(table)
    command = result.command
    assert command is not None
    public_ref = str(command["checkout_ref"])
    provider_key = str(command["provider_key_digest"])
    for canary in ("parent-private-canary", "browser-private-canary", "student-a"):
        assert canary not in public_ref
        assert canary not in provider_key
    assert public_ref != provider_key
    assert len(public_ref) >= 40
    assert len(provider_key) == 64
    assert len(provider_key) < 255
    replay = _register(table)
    assert replay.command is not None
    assert replay.command["provider_key_digest"] == provider_key


def test_public_lookup_is_strong_owner_authorized_and_schema_validated() -> None:
    table = AtomicCheckoutTable()
    created = _register(table)
    assert created.command is not None
    checkout_ref = str(created.command["checkout_ref"])

    found = checkout_command_repo.get_checkout_command_by_public_ref(
        checkout_ref, parent_id="parent-private-canary", table=table
    )
    assert found.disposition is checkout_command_repo.CheckoutCommandDisposition.REPLAYED
    assert found.command == created.command

    denied = checkout_command_repo.get_checkout_command_by_public_ref(
        checkout_ref, parent_id="unrelated-parent", table=table
    )
    assert denied.disposition is checkout_command_repo.CheckoutCommandDisposition.NOT_FOUND
    assert denied.command is None

    lookup_key = (f"CHECKOUT_PUBLIC#{checkout_ref}", "LOOKUP")
    table.rows[lookup_key]["schema_version"] = "legacy-unsafe"
    malformed = checkout_command_repo.get_checkout_command_by_public_ref(
        checkout_ref, parent_id="parent-private-canary", table=table
    )
    assert malformed.disposition is checkout_command_repo.CheckoutCommandDisposition.MALFORMED


def test_provider_claim_persists_call_intent_and_expired_takeover_retains_identity() -> None:
    table = AtomicCheckoutTable()
    created = _register(table)
    assert created.command is not None

    first = checkout_command_repo.claim_provider_create(
        created.command,
        lease_owner="worker-one",
        now_epoch=100,
        lease_expires_at=110,
        now_iso=NOW,
        table=table,
    )
    assert first.disposition is checkout_command_repo.CheckoutCommandDisposition.CLAIMED
    assert first.provider_claim is not None
    assert first.command is not None
    before_identity = (
        first.command["command_id"],
        first.command["intent_fingerprint"],
        first.command["provider_key_digest"],
    )

    busy = checkout_command_repo.claim_provider_create(
        first.command,
        lease_owner="worker-two",
        now_epoch=109,
        lease_expires_at=120,
        now_iso=NOW,
        table=table,
    )
    assert busy.disposition is checkout_command_repo.CheckoutCommandDisposition.LEASE_BUSY

    takeover = checkout_command_repo.claim_provider_create(
        first.command,
        lease_owner="worker-two",
        now_epoch=110,
        lease_expires_at=130,
        now_iso=NOW,
        table=table,
    )
    assert takeover.disposition is checkout_command_repo.CheckoutCommandDisposition.CLAIMED
    assert takeover.provider_claim is not None
    assert takeover.provider_claim.lease_generation == 2
    assert takeover.command is not None
    assert (
        takeover.command["command_id"],
        takeover.command["intent_fingerprint"],
        takeover.command["provider_key_digest"],
    ) == before_identity


def test_stale_lease_owner_cannot_attach_provider_session() -> None:
    table = AtomicCheckoutTable()
    created = _register(table)
    first = checkout_command_repo.claim_provider_create(
        created.command,
        lease_owner="worker-one",
        now_epoch=100,
        lease_expires_at=110,
        now_iso=NOW,
        table=table,
    )
    takeover = checkout_command_repo.claim_provider_create(
        first.command,
        lease_owner="worker-two",
        now_epoch=110,
        lease_expires_at=130,
        now_iso=NOW,
        table=table,
    )
    assert first.provider_claim is not None
    assert takeover.provider_claim is not None
    stale = checkout_command_repo.attach_provider_session(
        first.provider_claim,
        provider_session_id="cs_test_stale",
        provider_session_url="https://checkout.stripe.test/stale",
        now_iso=NOW,
        table=table,
    )
    assert stale.disposition is checkout_command_repo.CheckoutCommandDisposition.STALE_LEASE
    attached = checkout_command_repo.attach_provider_session(
        takeover.provider_claim,
        provider_session_id="cs_test_authoritative",
        provider_session_url="https://checkout.stripe.test/authoritative",
        now_iso=NOW,
        table=table,
    )
    assert attached.disposition is checkout_command_repo.CheckoutCommandDisposition.ATTACHED
    assert attached.command is not None
    assert attached.command["command_state"] == CheckoutCommandState.PROVIDER_SESSION_OPEN


def test_attach_commit_then_timeout_reconciles_from_strong_read() -> None:
    table = AtomicCheckoutTable()
    created = _register(table)
    claimed = checkout_command_repo.claim_provider_create(
        created.command,
        lease_owner="worker-one",
        now_epoch=100,
        lease_expires_at=120,
        now_iso=NOW,
        table=table,
    )
    assert claimed.provider_claim is not None
    table.commit_then_timeout_updates.add("attach")
    result = checkout_command_repo.attach_provider_session(
        claimed.provider_claim,
        provider_session_id="cs_test_committed",
        provider_session_url="https://checkout.stripe.test/committed",
        now_iso=NOW,
        table=table,
    )
    assert result.disposition is checkout_command_repo.CheckoutCommandDisposition.ATTACHED
    assert result.command is not None
    assert result.command["provider_session_id"] == "cs_test_committed"


def test_unknown_provider_outcome_keeps_guard_and_recovers_same_provider_key() -> None:
    table = AtomicCheckoutTable()
    created = _register(table)
    claimed = checkout_command_repo.claim_provider_create(
        created.command,
        lease_owner="worker-one",
        now_epoch=100,
        lease_expires_at=110,
        now_iso=NOW,
        table=table,
    )
    assert claimed.provider_claim is not None
    unknown = checkout_command_repo.mark_provider_outcome_unknown(
        claimed.provider_claim,
        now_iso=NOW,
        table=table,
    )
    assert unknown.disposition is checkout_command_repo.CheckoutCommandDisposition.PROVIDER_OUTCOME_UNKNOWN
    assert unknown.command is not None
    provider_key = unknown.command["provider_key_digest"]
    guard_key = ("CHECKOUT_OPEN#parent-private-canary", "GUARD")
    assert guard_key in table.rows

    recovered = checkout_command_repo.claim_provider_create(
        unknown.command,
        lease_owner="worker-two",
        now_epoch=110,
        lease_expires_at=130,
        now_iso=NOW,
        table=table,
    )
    assert recovered.disposition is checkout_command_repo.CheckoutCommandDisposition.CLAIMED
    assert recovered.command is not None
    assert recovered.command["provider_key_digest"] == provider_key
    assert guard_key in table.rows


@pytest.mark.parametrize(
    "state",
    [
        CheckoutCommandState.INTENT_RECORDED,
        CheckoutCommandState.PROVIDER_CREATE_PENDING,
        CheckoutCommandState.PROVIDER_SESSION_OPEN,
        CheckoutCommandState.RECONCILING,
        CheckoutCommandState.OPERATOR_ATTENTION_REQUIRED,
    ],
)
def test_open_guard_cannot_release_for_nonterminal_state(
    state: CheckoutCommandState,
) -> None:
    table = AtomicCheckoutTable()
    created = _register(table)
    assert created.command is not None
    command_key = (
        str(created.command["PK"]),
        str(created.command["SK"]),
    )
    table.rows[command_key]["command_state"] = state
    result = checkout_command_repo.release_open_guard_for_terminal_command(
        table.rows[command_key], table=table
    )
    assert result.disposition is checkout_command_repo.CheckoutCommandDisposition.NOT_TERMINAL
    assert ("CHECKOUT_OPEN#parent-private-canary", "GUARD") in table.rows


@pytest.mark.parametrize(
    "state",
    [
        CheckoutCommandState.ACTIVATION_RECORDED,
        CheckoutCommandState.TERMINAL_WITHOUT_PAYMENT,
    ],
)
def test_terminal_version_condition_releases_only_matching_open_guard(
    state: CheckoutCommandState,
) -> None:
    table = AtomicCheckoutTable()
    created = _register(table)
    assert created.command is not None
    command_key = (str(created.command["PK"]), str(created.command["SK"]))
    table.rows[command_key]["command_state"] = state
    command = dict(table.rows[command_key])
    result = checkout_command_repo.release_open_guard_for_terminal_command(
        command, table=table
    )
    assert result.disposition is checkout_command_repo.CheckoutCommandDisposition.RELEASED
    assert ("CHECKOUT_OPEN#parent-private-canary", "GUARD") not in table.rows

