"""Lower-boundary proof for capped idempotent logical-operation admission."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import threading

from fastapi import HTTPException

from stoa.db.repositories import account_deletion_repo
from stoa.services import rate_limit


PERIOD = "2026-07-21"
NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class _RateTable:
    """Atomic high-level table fake that enforces the two transaction conditions."""

    def __init__(
        self,
        *,
        count: int = 0,
        kind: str = "hint",
        period: str = PERIOD,
        initial_counter_barrier: threading.Barrier | None = None,
    ) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {
            ("USER#student-1", "ACCOUNT_FENCE"): {
                "PK": "USER#student-1",
                "SK": "ACCOUNT_FENCE",
                "status": "active",
                "generation": 1,
            }
        }
        if count:
            self.items[("USAGE#student-1", f"{kind.upper()}#{period}")] = {
                "PK": "USAGE#student-1",
                "SK": f"{kind.upper()}#{period}",
                "count": count,
                "expires_at": int(NOW.timestamp()) + 172800,
            }
        self.transactions: list[list[dict[str, object]]] = []
        self._lock = threading.Lock()
        self._initial_counter_barrier = initial_counter_barrier
        self._initial_counter_reads = 0

    def get_item(self, *, Key, ConsistentRead=True):  # noqa: N803
        assert ConsistentRead is True
        key = (Key["PK"], Key["SK"])
        should_wait = False
        with self._lock:
            item = dict(self.items[key]) if key in self.items else None
            if (
                self._initial_counter_barrier is not None
                and Key["SK"] == f"HINT#{PERIOD}"
                and self._initial_counter_reads < 2
            ):
                self._initial_counter_reads += 1
                should_wait = True
        if should_wait:
            self._initial_counter_barrier.wait(timeout=2)
        return {"Item": item} if item is not None else {}

    def transact_account_deletion(self, operations):
        copied = [dict(operation) for operation in operations]
        with self._lock:
            self.transactions.append(copied)
            put = next(operation["Put"] for operation in operations if "Put" in operation)
            update = next(
                operation["Update"] for operation in operations if "Update" in operation
            )
            operation_item = dict(put["Item"])
            operation_key = (operation_item["PK"], operation_item["SK"])
            counter_key = (update["Key"]["PK"], update["Key"]["SK"])
            current = dict(self.items.get(counter_key, {}))
            limit = int(update["ExpressionAttributeValues"][":limit"])
            if operation_key in self.items or int(current.get("count", 0)) >= limit:
                raise account_deletion_repo.AccountDeletionConflict(
                    "conditional rate admission conflict"
                )
            self.items[operation_key] = operation_item
            self.items[counter_key] = {
                **current,
                **update["Key"],
                "entity_type": "rate_counter",
                "owner_id": update["ExpressionAttributeValues"][":owner"],
                "quota_period": update["ExpressionAttributeValues"][":period"],
                "account_fence_generation": update["ExpressionAttributeValues"][
                    ":generation"
                ],
                "count": int(current.get("count", 0)) + 1,
                "expires_at": int(
                    current.get("expires_at")
                    or update["ExpressionAttributeValues"][":expires"]
                ),
            }

    def count(self, kind: str = "hint", period: str = PERIOD) -> int:
        return int(
            self.items.get(("USAGE#student-1", f"{kind.upper()}#{period}"), {}).get(
                "count", 0
            )
        )

    def operation_rows(self) -> list[dict[str, object]]:
        return [
            dict(item)
            for item in self.items.values()
            if item.get("entity_type") == "rate_admission_operation"
        ]


def _admit(
    table: _RateTable,
    *,
    caller_id: str,
    payload: str = "challenge-1",
    period: str = PERIOD,
    limit: int = 2,
) -> rate_limit.RateAdmissionResult:
    return rate_limit.check_and_record_operation(
        owner_id="student-1",
        kind="hint",
        operation_id=rate_limit.build_rate_operation_id(
            "hint", "student-1", caller_id, period
        ),
        payload_digest=_digest(payload),
        quota_period=period,
        limit=limit,
        table=table,
        now=NOW,
    )


def test_transaction_puts_payload_bound_operation_and_capped_counter_update() -> None:
    table = _RateTable()

    result = _admit(table, caller_id="hint-request-1")

    assert result.disposition is rate_limit.RateAdmissionDisposition.ADMITTED
    assert table.count() == 1
    operations = table.transactions[0]
    put = next(operation["Put"] for operation in operations if "Put" in operation)
    update = next(operation["Update"] for operation in operations if "Update" in operation)
    assert put["Item"]["owner_id"] == "student-1"
    assert put["Item"]["kind"] == "hint"
    assert put["Item"]["quota_period"] == PERIOD
    assert put["Item"]["payload_digest"] == _digest("challenge-1")
    assert put["Item"]["status"] == "admitted"
    assert update["ConditionExpression"] == (
        "attribute_not_exists(#count) OR #count < :limit"
    )
    assert update["ExpressionAttributeValues"][":limit"] == 2


def test_repeating_429_requests_leave_counter_exactly_at_limit(monkeypatch) -> None:
    table = _RateTable(count=2)
    monkeypatch.setattr(rate_limit, "get_table", lambda: table)
    monkeypatch.setattr(rate_limit, "_today_utc", lambda: PERIOD)

    for operation_id in ("rejected-1", "rejected-2"):
        try:
            rate_limit.check_and_record_hint(
                "student-1", "challenge-1", operation_id, limit=2
            )
        except HTTPException as error:
            assert error.status_code == 429
        else:  # pragma: no cover - failure branch
            raise AssertionError("a full counter must reject the operation")

    assert table.count() == 2
    assert table.transactions == []
    assert table.operation_rows() == []


def test_two_concurrent_distinct_requests_compete_for_one_final_slot() -> None:
    table = _RateTable(count=1, initial_counter_barrier=threading.Barrier(2))
    results: list[rate_limit.RateAdmissionResult] = []
    failures: list[Exception] = []

    def run(caller_id: str) -> None:
        try:
            results.append(_admit(table, caller_id=caller_id, limit=2))
        except Exception as error:  # pragma: no cover - assertion reports details
            failures.append(error)

    threads = [threading.Thread(target=run, args=(f"final-{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert failures == []
    assert not any(thread.is_alive() for thread in threads)
    assert sorted(result.disposition.value for result in results) == [
        "admitted",
        "limit_exceeded",
    ]
    assert table.count() == 2
    assert len(table.operation_rows()) == 1


def test_provider_failure_retry_replays_one_count_and_distinct_operation_is_evaluated() -> None:
    table = _RateTable()

    first = _admit(table, caller_id="provider-failure", limit=1)
    # Downstream provider failure does not compensate an already admitted operation.
    replay = _admit(table, caller_id="provider-failure", limit=1)
    distinct = _admit(table, caller_id="new-request", limit=1)

    assert first.disposition is rate_limit.RateAdmissionDisposition.ADMITTED
    assert replay.disposition is rate_limit.RateAdmissionDisposition.REPLAYED
    assert distinct.disposition is rate_limit.RateAdmissionDisposition.LIMIT_EXCEEDED
    assert table.count() == 1
    assert len(table.operation_rows()) == 1


def test_same_operation_changed_digest_conflicts_without_mutation() -> None:
    table = _RateTable()

    admitted = _admit(table, caller_id="same-key", payload="challenge-1")
    conflict = _admit(table, caller_id="same-key", payload="challenge-2")

    assert admitted.disposition is rate_limit.RateAdmissionDisposition.ADMITTED
    assert conflict.disposition is rate_limit.RateAdmissionDisposition.IDEMPOTENCY_CONFLICT
    assert table.count() == 1
    assert len(table.transactions) == 1


def test_hint_adapter_projects_changed_payload_as_structured_conflict(monkeypatch) -> None:
    table = _RateTable()
    monkeypatch.setattr(rate_limit, "get_table", lambda: table)
    monkeypatch.setattr(rate_limit, "_today_utc", lambda: PERIOD)

    rate_limit.check_and_record_hint(
        "student-1", "challenge-1", "same-public-key", limit=2
    )
    try:
        rate_limit.check_and_record_hint(
            "student-1", "challenge-2", "same-public-key", limit=2
        )
    except HTTPException as error:
        assert error.status_code == 409
        assert error.detail == {
            "code": "rate_operation_conflict",
            "message": "This idempotency key was already used for another request.",
        }
    else:  # pragma: no cover - failure branch
        raise AssertionError("changed payload must conflict")

    assert table.count() == 1
    assert len(table.transactions) == 1


def test_utc_day_change_uses_new_counter_and_operation_namespace() -> None:
    table = _RateTable()

    first = _admit(table, caller_id="daily-key", period="2026-07-21")
    prior_row = dict(table.operation_rows()[0])
    second = _admit(table, caller_id="daily-key", period="2026-07-22")

    assert first.disposition is second.disposition is rate_limit.RateAdmissionDisposition.ADMITTED
    assert table.count(period="2026-07-21") == 1
    assert table.count(period="2026-07-22") == 1
    assert len(table.operation_rows()) == 2
    assert table.operation_rows()[0] == prior_row
    assert {row["quota_period"] for row in table.operation_rows()} == {
        "2026-07-21",
        "2026-07-22",
    }
