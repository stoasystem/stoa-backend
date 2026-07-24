"""Weekly token allowance admission, evidence, and projection contract."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import inspect
import threading
from typing import Any

import pytest

from stoa.db.repositories import account_deletion_repo, allowance_repo
from stoa.models.allowance import TeacherSupportScope
from stoa.models.billing import BillingPlanId
from stoa.services import allowance_service
from tests.dynamodb_expression_assertions import assert_expression_placeholders_closed


UTC = timezone.utc
NOW = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)


class AtomicAllowanceTable:
    """DynamoDB fake that enforces the repository's conditional Put transactions."""

    def __init__(self, *, counter_barrier: threading.Barrier | None = None) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {
            ("USER#student-1", "ACCOUNT_FENCE"): {
                "PK": "USER#student-1",
                "SK": "ACCOUNT_FENCE",
                "status": "active",
                "generation": 1,
            }
        }
        self.transactions: list[list[dict[str, Any]]] = []
        self._lock = threading.Lock()
        self._counter_barrier = counter_barrier
        self._initial_counter_reads = 0

    def get_item(self, *, Key: dict[str, str], ConsistentRead: bool) -> dict[str, object]:
        assert ConsistentRead is True
        key = (Key["PK"], Key["SK"])
        wait = False
        with self._lock:
            item = deepcopy(self.items.get(key))
            if (
                self._counter_barrier is not None
                and Key["SK"].startswith("WEEK#")
                and self._initial_counter_reads < self._counter_barrier.parties
            ):
                self._initial_counter_reads += 1
                wait = True
        if wait:
            self._counter_barrier.wait(timeout=3)
        return {"Item": item} if item is not None else {}

    def query(self, **kwargs: object) -> dict[str, object]:
        assert kwargs["ConsistentRead"] is True
        pk = str(kwargs["ExpressionAttributeValues"][":pk"])  # type: ignore[index]
        prefix = str(kwargs["ExpressionAttributeValues"][":prefix"])  # type: ignore[index]
        with self._lock:
            return {
                "Items": [
                    deepcopy(item)
                    for (row_pk, row_sk), item in sorted(self.items.items())
                    if row_pk == pk and row_sk.startswith(prefix)
                ]
            }

    def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
        for operation in operations:
            assert_expression_placeholders_closed(operation)
        with self._lock:
            snapshot = deepcopy(self.items)
            for operation in operations:
                if "ConditionCheck" in operation:
                    check = operation["ConditionCheck"]
                    current = snapshot.get((check["Key"]["PK"], check["Key"]["SK"]))
                    values = check["ExpressionAttributeValues"]
                    if (
                        current is None
                        or current.get("status") != values[":active"]
                        or current.get("generation") != values[":generation"]
                    ):
                        raise account_deletion_repo.AccountDeletionConflict(
                            "conditional allowance fence conflict"
                        )
                    continue

                put = operation["Put"]
                item = deepcopy(put["Item"])
                key = (str(item["PK"]), str(item["SK"]))
                current = snapshot.get(key)
                condition = put["ConditionExpression"]
                values = put.get("ExpressionAttributeValues", {})
                names = put.get("ExpressionAttributeNames", {})
                if "attribute_not_exists(PK)" in condition and current is not None:
                    raise account_deletion_repo.AccountDeletionConflict(
                        "conditional allowance create conflict"
                    )
                if ":expected_state_version" in values and (
                    current is None
                    or current.get("state_version") != values[":expected_state_version"]
                ):
                    raise account_deletion_repo.AccountDeletionConflict(
                        "conditional allowance version conflict"
                    )
                if ":expected_state" in values:
                    state_name = names.get("#state", "state")
                    if current is None or current.get(state_name) != values[":expected_state"]:
                        raise account_deletion_repo.AccountDeletionConflict(
                            "conditional allowance state conflict"
                        )
                snapshot[key] = item
            self.items = snapshot
            self.transactions.append(deepcopy(operations))

    def counter(self) -> dict[str, object]:
        rows = [
            item
            for item in self.items.values()
            if item.get("entity_type") == "allowance_counter"
        ]
        assert len(rows) == 1
        return deepcopy(rows[0])

    def evidence(self) -> list[dict[str, object]]:
        return [
            deepcopy(item)
            for item in self.items.values()
            if item.get("entity_type") == "provider_usage_evidence"
        ]


def _reserve(
    table: AtomicAllowanceTable,
    *,
    effect_id: str,
    input_tokens: int = 100,
    output_tokens: int = 50,
    plan_id: BillingPlanId = BillingPlanId.FREE_TRIAL,
):
    return allowance_service.reserve_token_allowance(
        beneficiary_id="student-1",
        effect_id=effect_id,
        plan_id=plan_id,
        allowance_version=7,
        input_tokens=input_tokens,
        max_output_tokens=output_tokens,
        observed_at=NOW,
        account_fence_generation=1,
        table=table,
    )


@pytest.mark.parametrize(
    ("plan_id", "input_tokens", "output_tokens", "cases", "scope"),
    [
        (BillingPlanId.FREE_TRIAL, 50_000, 10_000, 0, TeacherSupportScope.NONE),
        (BillingPlanId.STUDENT, 500_000, 100_000, 0, TeacherSupportScope.NONE),
        (
            BillingPlanId.TEACHER_SUPPORTED,
            1_000_000,
            200_000,
            2,
            TeacherSupportScope.PER_BENEFICIARY,
        ),
        (
            BillingPlanId.FAMILY,
            1_000_000,
            200_000,
            10,
            TeacherSupportScope.SHARED_FAMILY,
        ),
    ],
)
def test_plan_budgets_are_the_exact_locked_values(
    plan_id: BillingPlanId,
    input_tokens: int,
    output_tokens: int,
    cases: int,
    scope: TeacherSupportScope,
) -> None:
    budget = allowance_service.plan_allowance_budget(plan_id, allowance_version=7)

    assert (
        budget.input_tokens,
        budget.output_tokens,
        budget.teacher_support_cases,
        budget.teacher_support_scope,
    ) == (input_tokens, output_tokens, cases, scope)


@pytest.mark.parametrize(
    ("instant", "start", "end", "hours"),
    [
        (
            datetime(2026, 3, 25, 12, tzinfo=UTC),
            "2026-03-22T23:00:00+00:00",
            "2026-03-29T22:00:00+00:00",
            167,
        ),
        (
            datetime(2026, 10, 21, 12, tzinfo=UTC),
            "2026-10-18T22:00:00+00:00",
            "2026-10-25T23:00:00+00:00",
            169,
        ),
    ],
)
def test_zurich_week_uses_local_monday_dates_across_dst(
    instant: datetime,
    start: str,
    end: str,
    hours: int,
) -> None:
    week = allowance_service.zurich_week(instant)

    assert week.window_start.astimezone(UTC).isoformat() == start
    assert week.window_end.astimezone(UTC).isoformat() == end
    assert (week.window_end.astimezone(UTC) - week.window_start.astimezone(UTC)).total_seconds() == (
        hours * 3600
    )


def test_concurrent_reservations_cannot_overspend_either_dimension() -> None:
    table = AtomicAllowanceTable(counter_barrier=threading.Barrier(2))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda effect: _reserve(
                    table,
                    effect_id=effect,
                    input_tokens=30_000,
                    output_tokens=6_000,
                ),
                ("effect-a", "effect-b"),
            )
        )

    assert sorted(result.disposition.value for result in results) == [
        "admitted",
        "limit_exceeded",
    ]
    counter = table.counter()
    assert counter["finalized_input_tokens"] + counter["reserved_input_tokens"] <= 50_000
    assert counter["finalized_output_tokens"] + counter["reserved_output_tokens"] <= 10_000


def test_replay_is_byte_stable_after_unrelated_traffic_and_changed_payload_conflicts() -> None:
    table = AtomicAllowanceTable()
    first = _reserve(table, effect_id="stable-effect")
    original = first.reservation.model_dump(mode="json", by_alias=True)
    _reserve(table, effect_id="unrelated-effect")

    replay = _reserve(table, effect_id="stable-effect")
    conflict = _reserve(table, effect_id="stable-effect", input_tokens=101)

    assert replay.disposition is allowance_repo.ReservationDisposition.REPLAYED
    assert replay.reservation.model_dump(mode="json", by_alias=True) == original
    assert conflict.disposition is allowance_repo.ReservationDisposition.IDEMPOTENCY_CONFLICT
    assert len(table.transactions) == 2


def test_provider_usage_finalizes_exact_actual_counts_and_redacts_provider_values() -> None:
    table = AtomicAllowanceTable()
    _reserve(table, effect_id="delivered-effect")

    observed = allowance_service.record_provider_usage(
        beneficiary_id="student-1",
        effect_id="delivered-effect",
        provider_request_id="provider-private-request-canary",
        model_id="provider-private-model-canary",
        input_tokens=80,
        output_tokens=30,
        observed_at=NOW,
        table=table,
    )
    finalized = allowance_service.finalize_token_allowance(
        beneficiary_id="student-1",
        effect_id="delivered-effect",
        technical_validation_passed=True,
        safety_check_passed=True,
        durable_result_stored=True,
        stable_replay_readable=True,
        finalized_at=NOW,
        table=table,
    )

    assert observed.disposition is allowance_repo.ProviderUsageDisposition.RECORDED
    assert finalized.disposition is allowance_repo.FinalizationDisposition.FINALIZED
    assert finalized.finalization.finalized_input_tokens == 80
    assert finalized.finalization.finalized_output_tokens == 30
    counter = table.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["finalized_input_tokens"] == 80
    assert counter["finalized_output_tokens"] == 30
    assert counter["provider_cost_input_tokens"] == 80
    assert counter["provider_cost_output_tokens"] == 30
    serialized = repr(table.evidence())
    assert "provider-private-request-canary" not in serialized
    assert "provider-private-model-canary" not in serialized
    assert "prompt" not in serialized
    assert "answer" not in serialized


def test_restoration_releases_user_allowance_but_retains_provider_cost_and_replays() -> None:
    table = AtomicAllowanceTable()
    _reserve(table, effect_id="undelivered-effect")
    allowance_service.record_provider_usage(
        beneficiary_id="student-1",
        effect_id="undelivered-effect",
        provider_request_id="request-1",
        model_id="model-1",
        input_tokens=80,
        output_tokens=30,
        observed_at=NOW,
        table=table,
    )

    restored = allowance_service.restore_user_allowance(
        beneficiary_id="student-1",
        effect_id="undelivered-effect",
        technical_validation_passed=True,
        safety_check_passed=True,
        durable_result_stored=False,
        stable_replay_readable=False,
        restored_at=NOW,
        table=table,
    )
    replay = allowance_service.restore_user_allowance(
        beneficiary_id="student-1",
        effect_id="undelivered-effect",
        technical_validation_passed=True,
        safety_check_passed=True,
        durable_result_stored=False,
        stable_replay_readable=False,
        restored_at=NOW,
        table=table,
    )

    assert restored.disposition is allowance_repo.FinalizationDisposition.RESTORED
    assert replay.disposition is allowance_repo.FinalizationDisposition.REPLAYED
    assert replay.finalization.model_dump(mode="json", by_alias=True) == (
        restored.finalization.model_dump(mode="json", by_alias=True)
    )
    counter = table.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["finalized_input_tokens"] == 0
    assert counter["finalized_output_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == 80
    assert counter["provider_cost_output_tokens"] == 30


@pytest.mark.parametrize("malformed", [True, Decimal("1.5"), -1, "1"])
def test_malformed_persisted_counts_fail_closed_without_another_effect(
    malformed: object,
) -> None:
    table = AtomicAllowanceTable()
    _reserve(table, effect_id="initial-effect")
    counter_key = next(
        key
        for key, item in table.items.items()
        if item.get("entity_type") == "allowance_counter"
    )
    table.items[counter_key]["reserved_input_tokens"] = malformed
    transaction_count = len(table.transactions)

    result = _reserve(table, effect_id="must-fail-closed")

    assert result.disposition is allowance_repo.ReservationDisposition.RETRYABLE
    assert len(table.transactions) == transaction_count


def test_parent_projection_is_budget_safe_and_admin_projection_has_exact_redacted_evidence() -> None:
    table = AtomicAllowanceTable()
    _reserve(table, effect_id="projection-effect")
    allowance_service.record_provider_usage(
        beneficiary_id="student-1",
        effect_id="projection-effect",
        provider_request_id="request-private-canary",
        model_id="model-private-canary",
        input_tokens=80,
        output_tokens=30,
        observed_at=NOW,
        table=table,
    )
    allowance_service.finalize_token_allowance(
        beneficiary_id="student-1",
        effect_id="projection-effect",
        technical_validation_passed=True,
        safety_check_passed=True,
        durable_result_stored=True,
        stable_replay_readable=True,
        finalized_at=NOW,
        table=table,
    )

    parent = allowance_service.get_allowance_projection(
        beneficiary_id="student-1",
        plan_id=BillingPlanId.FREE_TRIAL,
        allowance_version=7,
        observed_at=NOW,
        viewer_role="parent",
        table=table,
    )
    admin = allowance_service.get_allowance_projection(
        beneficiary_id="student-1",
        plan_id=BillingPlanId.FREE_TRIAL,
        allowance_version=7,
        observed_at=NOW,
        viewer_role="admin",
        table=table,
    )

    assert parent["input"] == {
        "budgetTokens": 50_000,
        "remainingTokens": 49_920,
        "usedPercent": 0.16,
    }
    assert parent["output"] == {
        "budgetTokens": 10_000,
        "remainingTokens": 9_970,
        "usedPercent": 0.3,
    }
    assert "providerCost" not in parent
    assert "providerEvidence" not in parent
    assert admin["providerCost"] == {"inputTokens": 80, "outputTokens": 30}
    assert admin["providerEvidence"][0]["inputTokens"] == 80
    assert admin["providerEvidence"][0]["outputTokens"] == 30
    assert "request-private-canary" not in repr(admin)
    assert "model-private-canary" not in repr(admin)


def test_service_resolves_window_and_budget_before_repository_reservation() -> None:
    source = inspect.getsource(allowance_service.reserve_token_allowance)
    assert source.index("zurich_week") < source.index("allowance_repo.reserve_allowance")
    assert source.index("plan_allowance_budget") < source.index(
        "allowance_repo.reserve_allowance"
    )
    assert "allowance_counter.v1" in inspect.getsource(allowance_repo)
    assert "allowance_effect.v1" in inspect.getsource(allowance_repo)
    assert "provider_usage_evidence.v1" in inspect.getsource(allowance_repo)
