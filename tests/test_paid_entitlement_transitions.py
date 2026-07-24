from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from stoa.config import FREE_STORAGE_BYTES, PAID_STORAGE_BYTES
from stoa.models.billing import BillingPlanId
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services import attachment_service, paid_entitlement_service


_DIGEST = "a" * 64
_PERIOD_END = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)


def _grant(
    *,
    parent_id: str = "parent-1",
    student_id: str = "student-1",
    plan: BillingPlanId = BillingPlanId.FAMILY,
    grant_version: int = 7,
    plan_version: int = 7,
) -> dict[str, object]:
    return {
        "PK": f"PAID_GRANT#{parent_id}",
        "SK": f"BENEFICIARY#{student_id}",
        "entity_type": "beneficiary_grant",
        "schema_version": "paid_beneficiary_grant.v1",
        "parent_id": parent_id,
        "beneficiary_id": student_id,
        "grant_status": "active",
        "command_id": "cmd-paid-1",
        "subscription_id_digest": _DIGEST,
        "grant_version": grant_version,
        "plan_id": plan.value,
        "plan_version": plan_version,
        "allowance_version": plan_version,
        "activation_version": grant_version,
        "activated_at": "2026-07-01T00:00:00+00:00",
    }


class _AtomicTable:
    def __init__(self, items: dict[tuple[str, str], dict[str, object]]) -> None:
        self.items = deepcopy(items)
        self.transactions: list[list[dict[str, Any]]] = []

    def get_item(self, **kwargs: object) -> dict[str, object]:
        key = kwargs["Key"]
        assert isinstance(key, dict)
        item = self.items.get((str(key["PK"]), str(key["SK"])))
        return {"Item": deepcopy(item)} if item is not None else {}

    def apply(self, operations: list[dict[str, Any]]) -> None:
        self.transactions.append(deepcopy(operations))
        for operation in operations:
            if "Put" not in operation:
                continue
            item = deepcopy(operation["Put"]["Item"])
            self.items[(str(item["PK"]), str(item["SK"]))] = item


def _install_atomic_transact(
    monkeypatch: pytest.MonkeyPatch,
    table: _AtomicTable,
) -> None:
    def transact(operations: object, *, table: object) -> None:
        assert table is table_ref
        assert isinstance(operations, list)
        table_ref.apply(operations)

    table_ref = table
    monkeypatch.setattr(
        paid_entitlement_service.account_deletion_repo,
        "transact",
        transact,
    )


def test_cancel_or_downgrade_applies_only_at_period_end_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grant = _grant()
    table = _AtomicTable({(str(grant["PK"]), str(grant["SK"])): grant})
    _install_atomic_transact(monkeypatch, table)

    scheduled = paid_entitlement_service.schedule_period_end_transition(
        parent_id="parent-1",
        beneficiary_ids=("student-1",),
        subscription_id_digest=_DIGEST,
        current_plan=BillingPlanId.FAMILY,
        target_plan=BillingPlanId.STUDENT,
        plan_version=8,
        period_end=_PERIOD_END,
        table=table,
    )
    assert scheduled.disposition is paid_entitlement_service.PaidTransitionDisposition.SCHEDULED
    assert table.items[("PAID_GRANT#parent-1", "BENEFICIARY#student-1")] == grant

    before = paid_entitlement_service.apply_due_paid_transition(
        parent_id="parent-1",
        subscription_id_digest=_DIGEST,
        transition_kind="period_end",
        transition_identity=scheduled.transition["transition_identity"],
        now=_PERIOD_END - timedelta(seconds=1),
        table=table,
    )
    assert before.disposition is paid_entitlement_service.PaidTransitionDisposition.NOT_DUE
    assert table.items[("PAID_GRANT#parent-1", "BENEFICIARY#student-1")] == grant

    at_boundary = paid_entitlement_service.apply_due_paid_transition(
        parent_id="parent-1",
        subscription_id_digest=_DIGEST,
        transition_kind="period_end",
        transition_identity=scheduled.transition["transition_identity"],
        now=_PERIOD_END,
        table=table,
    )
    assert at_boundary.disposition is paid_entitlement_service.PaidTransitionDisposition.APPLIED
    current = table.items[("PAID_GRANT#parent-1", "BENEFICIARY#student-1")]
    assert current["plan_id"] == BillingPlanId.STUDENT.value
    assert current["grant_status"] == "active"
    assert current["grant_version"] == 8
    assert at_boundary.transition["attachment_storage_limit"] == PAID_STORAGE_BYTES

    after = paid_entitlement_service.apply_due_paid_transition(
        parent_id="parent-1",
        subscription_id_digest=_DIGEST,
        transition_kind="period_end",
        transition_identity=scheduled.transition["transition_identity"],
        now=_PERIOD_END + timedelta(seconds=1),
        table=table,
    )
    assert after.disposition is paid_entitlement_service.PaidTransitionDisposition.ALREADY_APPLIED
    assert after.transition["transition_version"] == 2
    assert len(
        [
            item
            for item in table.items.values()
            if item.get("entity_type") == "paid_grant_history"
        ]
    ) == 1


def test_duplicate_delayed_failure_cannot_extend_fixed_grace_and_recovery_clears_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grant = _grant(plan=BillingPlanId.STUDENT)
    counter = {
        "PK": "ALLOWANCE#student-1",
        "SK": "WEEK#2026-W31",
        "finalized_input_tokens": 123,
        "reserved_input_tokens": 45,
    }
    table = _AtomicTable(
        {
            (str(grant["PK"]), str(grant["SK"])): grant,
            (str(counter["PK"]), str(counter["SK"])): counter,
        }
    )
    _install_atomic_transact(monkeypatch, table)

    first = paid_entitlement_service.start_renewal_grace(
        parent_id="parent-1",
        beneficiary_ids=("student-1",),
        subscription_id_digest=_DIGEST,
        plan_id=BillingPlanId.STUDENT,
        plan_version=8,
        failure_identity="invoice-failure-1",
        failed_at=_PERIOD_END,
        table=table,
    )
    duplicate = paid_entitlement_service.start_renewal_grace(
        parent_id="parent-1",
        beneficiary_ids=("student-1",),
        subscription_id_digest=_DIGEST,
        plan_id=BillingPlanId.STUDENT,
        plan_version=8,
        failure_identity="delayed-duplicate-event",
        failed_at=_PERIOD_END + timedelta(days=1),
        table=table,
    )
    assert first.disposition is paid_entitlement_service.PaidTransitionDisposition.GRACE_STARTED
    assert duplicate.disposition is paid_entitlement_service.PaidTransitionDisposition.ALREADY_APPLIED
    assert duplicate.transition["grace_expires_at"] == first.transition["grace_expires_at"]
    assert first.transition["grace_expires_at"] == (
        _PERIOD_END + timedelta(hours=72)
    ).isoformat()

    recovered = paid_entitlement_service.clear_renewal_grace(
        parent_id="parent-1",
        subscription_id_digest=_DIGEST,
        transition_identity=first.transition["transition_identity"],
        recovered_at=_PERIOD_END + timedelta(hours=48),
        table=table,
    )
    assert recovered.disposition is paid_entitlement_service.PaidTransitionDisposition.GRACE_CLEARED
    replay = paid_entitlement_service.apply_due_paid_transition(
        parent_id="parent-1",
        subscription_id_digest=_DIGEST,
        transition_kind="renewal_grace",
        transition_identity=first.transition["transition_identity"],
        now=_PERIOD_END + timedelta(hours=73),
        table=table,
    )
    assert replay.disposition is paid_entitlement_service.PaidTransitionDisposition.ALREADY_APPLIED
    assert table.items[("PAID_GRANT#parent-1", "BENEFICIARY#student-1")] == grant
    assert table.items[("ALLOWANCE#student-1", "WEEK#2026-W31")] == counter


def test_unresolved_grace_falls_to_free_once_and_preserves_history_and_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grant = _grant(plan=BillingPlanId.TEACHER_SUPPORTED)
    storage = {
        "PK": "ATTACHMENT_STORAGE#student-1",
        "SK": "USAGE",
        "used_bytes": FREE_STORAGE_BYTES + 1,
        "object_count": 23,
    }
    table = _AtomicTable(
        {
            (str(grant["PK"]), str(grant["SK"])): grant,
            (str(storage["PK"]), str(storage["SK"])): storage,
        }
    )
    _install_atomic_transact(monkeypatch, table)
    grace = paid_entitlement_service.start_renewal_grace(
        parent_id="parent-1",
        beneficiary_ids=("student-1",),
        subscription_id_digest=_DIGEST,
        plan_id=BillingPlanId.TEACHER_SUPPORTED,
        plan_version=8,
        failure_identity="invoice-failure-2",
        failed_at=_PERIOD_END,
        table=table,
    )
    not_due = paid_entitlement_service.apply_due_paid_transition(
        parent_id="parent-1",
        subscription_id_digest=_DIGEST,
        transition_kind="renewal_grace",
        transition_identity=grace.transition["transition_identity"],
        now=_PERIOD_END + timedelta(hours=72, seconds=-1),
        table=table,
    )
    assert not_due.disposition is paid_entitlement_service.PaidTransitionDisposition.NOT_DUE

    applied = paid_entitlement_service.apply_due_paid_transition(
        parent_id="parent-1",
        subscription_id_digest=_DIGEST,
        transition_kind="renewal_grace",
        transition_identity=grace.transition["transition_identity"],
        now=_PERIOD_END + timedelta(hours=72),
        table=table,
    )
    assert applied.disposition is paid_entitlement_service.PaidTransitionDisposition.APPLIED
    assert applied.transition["target_plan"] == BillingPlanId.FREE_TRIAL.value
    assert applied.transition["attachment_storage_limit"] == FREE_STORAGE_BYTES
    assert table.items[("PAID_GRANT#parent-1", "BENEFICIARY#student-1")][
        "grant_status"
    ] == "historical"
    assert table.items[("ATTACHMENT_STORAGE#student-1", "USAGE")] == storage

    replay = paid_entitlement_service.apply_due_paid_transition(
        parent_id="parent-1",
        subscription_id_digest=_DIGEST,
        transition_kind="renewal_grace",
        transition_identity=grace.transition["transition_identity"],
        now=_PERIOD_END + timedelta(days=4),
        table=table,
    )
    assert replay.disposition is paid_entitlement_service.PaidTransitionDisposition.ALREADY_APPLIED
    assert replay.transition["transition_version"] == 2


def test_over_free_limit_blocks_only_new_bytes_and_never_deletes() -> None:
    class Repository:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def get_storage_usage(self, owner_id: str) -> int:
            self.calls.append(("get_storage_usage", owner_id))
            return FREE_STORAGE_BYTES + 1

        def delete_object(self, *_args: object, **_kwargs: object) -> None:
            pytest.fail("storage downgrade admission must never delete")

    repository = Repository()
    prepared = [("upload", {"content_length": 1})]
    with pytest.raises(AttachmentDecisionError) as error:
        attachment_service.ensure_message_attachment_capacity(
            prepared,
            "student-1",
            BillingPlanId.FREE_TRIAL.value,
            repository=repository,
        )
    assert error.value.code is AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED
    assert repository.calls == [("get_storage_usage", "student-1")]
    assert (
        attachment_service.attachment_storage_limit(BillingPlanId.FREE_TRIAL.value)
        == FREE_STORAGE_BYTES
    )


def test_failed_upgrade_leaves_prior_grant_and_aggregates_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grant = _grant(plan=BillingPlanId.FAMILY)
    counter = {"PK": "ALLOWANCE#student-1", "SK": "WEEK#2026-W31", "used": 17}
    storage = {"PK": "ATTACHMENT_STORAGE#student-1", "SK": "USAGE", "used_bytes": 99}
    items = {
        (str(grant["PK"]), str(grant["SK"])): grant,
        (str(counter["PK"]), str(counter["SK"])): counter,
        (str(storage["PK"]), str(storage["SK"])): storage,
    }
    table = _AtomicTable(items)
    before = deepcopy(table.items)
    monkeypatch.setattr(
        paid_entitlement_service.account_deletion_repo,
        "transact",
        lambda *_args, **_kwargs: pytest.fail("invalid upgrade must not transact"),
    )
    result = paid_entitlement_service.apply_paid_upgrade(
        parent_id="parent-1",
        beneficiary_ids=("student-1",),
        subscription_id_digest=_DIGEST,
        command_id="failed-upgrade",
        plan_id=BillingPlanId.STUDENT,
        plan_version=8,
        allowance_version=8,
        activation_version=8,
        activated_at=_PERIOD_END,
        table=table,
    )
    assert result.disposition is paid_entitlement_service.PaidGrantDisposition.CONFLICT
    assert table.items == before


def test_paid_transition_source_link_uses_attachment_admission_limit() -> None:
    source = open(paid_entitlement_service.__file__, encoding="utf-8").read()
    assert "attachment_service.attachment_storage_limit" in source
    assert "delete_object" not in source
