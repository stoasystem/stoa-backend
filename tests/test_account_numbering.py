"""Account numbering contract: format, role fidelity, permanence, concurrency."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import threading
from typing import Any

import pytest
from botocore.exceptions import ClientError

from stoa.db.repositories import account_number_repo
from stoa.services import account_numbering_service


CONCURRENCY = 50

# Written out by hand on purpose: an independent copy of the mapping, so a wrong
# prefix in the service cannot agree with the assertion.
EXPECTED_PREFIXES = {"student": "S", "teacher": "T", "parent": "P", "admin": "A"}


def _conditional_error(operation: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}},
        operation,
    )


class SynchronizedNumberTable:
    """Fake honouring DynamoDB's atomic compare-and-set on a single item."""

    def __init__(self, *, hint_gate: threading.Barrier | None = None) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.hint_gate = hint_gate
        self.gated_threads: set[int] = set()
        self.claim_writes = 0

    def _await_gate(self, key: tuple[str, str]) -> None:
        """Hold every caller until all of them have read the cursor.

        Without this the threads serialise by luck and the allocator never sees
        two callers holding the same cursor value, which is exactly the race the
        conditional claim exists to survive.
        """
        if self.hint_gate is None or key[1] != account_number_repo.ALLOCATION_HINT_SK:
            return
        with self.lock:
            if threading.get_ident() in self.gated_threads:
                return
            self.gated_threads.add(threading.get_ident())
        self.hint_gate.wait()

    def get_item(self, *, Key: dict[str, str], ConsistentRead: bool = False) -> dict[str, Any]:
        key = (Key["PK"], Key["SK"])
        with self.lock:
            item = self.rows.get(key)
            response = {"Item": dict(item)} if item is not None else {}
        self._await_gate(key)
        return response

    def put_item(
        self,
        *,
        Item: dict[str, Any],
        ConditionExpression: str | None = None,
        ExpressionAttributeValues: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = (str(Item["PK"]), str(Item["SK"]))
        with self.lock:
            current = self.rows.get(key)
            if ConditionExpression == account_number_repo.CLAIM_CONDITION:
                if current is not None:
                    raise _conditional_error("PutItem")
            elif ConditionExpression == account_number_repo.HINT_CONDITION:
                sequence = int((ExpressionAttributeValues or {})[":sequence"])
                if current is not None and int(current["last_sequence"]) >= sequence:
                    raise _conditional_error("PutItem")
            elif ConditionExpression is not None:
                raise AssertionError(f"unexpected condition: {ConditionExpression}")
            if key[1] == account_number_repo.CLAIM_SK:
                self.claim_writes += 1
            self.rows[key] = dict(Item)
            return {}

    def claims(self) -> list[dict[str, Any]]:
        with self.lock:
            return [
                dict(item)
                for key, item in self.rows.items()
                if key[1] == account_number_repo.CLAIM_SK
            ]


def _moment(year: int) -> datetime:
    return datetime(year, 3, 1, 9, 0, tzinfo=UTC)


def test_每种角色的编号前缀与角色一致() -> None:
    table = SynchronizedNumberTable()
    for role, expected_prefix in EXPECTED_PREFIXES.items():
        number = account_numbering_service.allocate_account_number(
            role=role,
            account_id=f"sub-{role}",
            created_at=_moment(2026),
            table=table,
        )
        assert number == f"{expected_prefix}26-0001"
        assert number.startswith(expected_prefix)
        assert account_numbering_service.role_for_account_number(number) == role
        claim = account_number_repo.get_account_number_claim(number, table=table)
        assert claim is not None
        assert claim["role"] == role
        assert str(claim["account_number"])[0] == expected_prefix
        assert claim["account_id"] == f"sub-{role}"


def test_序号在同一角色同一年份内递增() -> None:
    table = SynchronizedNumberTable()
    numbers = [
        account_numbering_service.allocate_account_number(
            role="student", account_id=f"sub-{index}", created_at=_moment(2026), table=table
        )
        for index in range(3)
    ]
    assert numbers == ["S26-0001", "S26-0002", "S26-0003"]


def test_跨年从0001重新开始() -> None:
    table = SynchronizedNumberTable()
    for index in range(2):
        account_numbering_service.allocate_account_number(
            role="student", account_id=f"sub-26-{index}", created_at=_moment(2026), table=table
        )
    first_of_2027 = account_numbering_service.allocate_account_number(
        role="student", account_id="sub-27", created_at=_moment(2027), table=table
    )
    assert first_of_2027 == "S27-0001"
    assert account_number_repo.get_account_number_claim("S26-0002", table=table) is not None
    back_in_2026 = account_numbering_service.allocate_account_number(
        role="student", account_id="sub-26-late", created_at=_moment(2026), table=table
    )
    assert back_in_2026 == "S26-0003"


def test_同一编号重复写入被拒() -> None:
    table = SynchronizedNumberTable()
    common = {
        "account_number": "T26-0007",
        "role": "teacher",
        "year": 2026,
        "sequence": 7,
        "created_at": "2026-03-01T09:00:00+00:00",
    }
    assert account_number_repo.claim_account_number(
        account_id="sub-first", table=table, **common
    )
    assert not account_number_repo.claim_account_number(
        account_id="sub-second", table=table, **common
    )
    claim = account_number_repo.get_account_number_claim("T26-0007", table=table)
    assert claim is not None
    assert claim["account_id"] == "sub-first"


def test_编号不是主键而是带唯一性的业务标识() -> None:
    table = SynchronizedNumberTable()
    number = account_numbering_service.allocate_account_number(
        role="parent", account_id="cognito-sub-123", created_at=_moment(2026), table=table
    )
    claim = account_number_repo.get_account_number_claim(number, table=table)
    assert claim is not None
    assert claim["PK"] == f"ACCOUNT_NUMBER#{number}"
    assert claim["SK"] == "ACCOUNT_NUMBER"
    assert claim["account_id"] == "cognito-sub-123"


def test_游标丢失也不会重号() -> None:
    table = SynchronizedNumberTable()
    for index in range(3):
        account_numbering_service.allocate_account_number(
            role="admin", account_id=f"sub-{index}", created_at=_moment(2026), table=table
        )
    with table.lock:
        table.rows.pop(("ACCOUNT_NUMBER_SEQUENCE#admin#2026", "ACCOUNT_NUMBER_SEQUENCE"))
    recovered = account_numbering_service.allocate_account_number(
        role="admin", account_id="sub-after-loss", created_at=_moment(2026), table=table
    )
    assert recovered == "A26-0004"


def test_序号用尽时报错而不是复用() -> None:
    table = SynchronizedNumberTable()
    account_number_repo.advance_allocation_hint(
        role="student", year=2026, sequence=account_numbering_service.MAX_SEQUENCE, table=table
    )
    account_number_repo.claim_account_number(
        account_number="S26-9999",
        role="student",
        year=2026,
        sequence=9999,
        account_id="sub-last",
        created_at="2026-03-01T09:00:00+00:00",
        table=table,
    )
    with pytest.raises(account_numbering_service.AccountNumberExhausted):
        account_numbering_service.allocate_account_number(
            role="student", account_id="sub-overflow", created_at=_moment(2026), table=table
        )


def test_未知角色不发号() -> None:
    table = SynchronizedNumberTable()
    with pytest.raises(account_numbering_service.UnknownAccountRole):
        account_numbering_service.allocate_account_number(
            role="principal", account_id="sub-x", created_at=_moment(2026), table=table
        )
    assert table.claims() == []


def test_五十路并发建号编号全不重复() -> None:
    gate = threading.Barrier(CONCURRENCY, timeout=30)
    table = SynchronizedNumberTable(hint_gate=gate)

    def allocate(index: int) -> str:
        return account_numbering_service.allocate_account_number(
            role="student",
            account_id=f"sub-{index}",
            created_at=_moment(2026),
            table=table,
        )

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        numbers = list(pool.map(allocate, range(CONCURRENCY)))

    duplicates = [number for number, count in Counter(numbers).items() if count > 1]
    assert duplicates == []
    assert len(set(numbers)) == CONCURRENCY
    assert set(numbers) == {f"S26-{index:04d}" for index in range(1, CONCURRENCY + 1)}
    assert len(table.claims()) == CONCURRENCY
    assert table.claim_writes == CONCURRENCY
    assert all(number.startswith("S") for number in numbers)


def test_并发建号跨角色不串号() -> None:
    gate = threading.Barrier(CONCURRENCY, timeout=30)
    table = SynchronizedNumberTable(hint_gate=gate)
    roles = ["student", "teacher", "parent", "admin"]

    def allocate(index: int) -> tuple[str, str]:
        role = roles[index % len(roles)]
        number = account_numbering_service.allocate_account_number(
            role=role,
            account_id=f"sub-{index}",
            created_at=_moment(2026),
            table=table,
        )
        return role, number

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        results = list(pool.map(allocate, range(CONCURRENCY)))

    assert len({number for _role, number in results}) == CONCURRENCY
    for role, number in results:
        assert number[0] == EXPECTED_PREFIXES[role]
        claim = account_number_repo.get_account_number_claim(number, table=table)
        assert claim is not None
        assert claim["role"] == role


def test_一个号能反查回持有它的账号():
    """反查是家长按学号关联孩子的入口，查不到必须是 None 而不是猜。"""
    table = SynchronizedNumberTable()
    number = account_numbering_service.allocate_account_number(
        role="student", account_id="sub-abc", created_at=_moment(2026), table=table
    )

    assert account_numbering_service.resolve_account_id(number, table=table) == "sub-abc"


def test_没发过的号反查为空():
    table = SynchronizedNumberTable()

    assert account_numbering_service.resolve_account_id("S26-9999", table=table) is None
