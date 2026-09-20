"""Invitation and direct-assignment contract: single use, expiry, enumeration, numbering."""

from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
import secrets
from statistics import median
import threading
import time
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
import pytest
from botocore.exceptions import ClientError

from stoa.db.repositories import (
    account_deletion_repo,
    account_email_claim_repo,
    account_invitation_repo,
    account_number_repo,
    identity_repo,
    security_audit_repo,
    user_repo,
)
from stoa.services import (
    account_deletion_service,
    account_numbering_service,
    account_provisioning_service,
)


SERVICE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "stoa"
    / "services"
    / "account_provisioning_service.py"
)

# Written out by hand, independently of the service, so a wrong mapping there cannot
# agree with the assertion.
EXPECTED_PREFIXES = {"student": "S", "teacher": "T", "parent": "P", "admin": "A"}

# The two arms of an unusable-token rejection differ by a few microseconds of ordinary
# scheduling noise, so a threshold has to sit close enough to that noise to notice a
# branch that actually does different work. `test_计时闸本身能识别出一个人造预言机`
# is the calibration: it plants a known oracle and requires this number to catch it.
TIMING_ORACLE_THRESHOLD_SECONDS = 5e-5
PLANTED_ORACLE_DELAY_SECONDS = 1e-4


def _conditional_error(operation: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "refused"}},
        operation,
    )


def _split_top(expression: str, separator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current = ""
    index = 0
    while index < len(expression):
        char = expression[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if depth == 0 and expression[index : index + len(separator)] == separator:
            parts.append(current)
            current = ""
            index += len(separator)
            continue
        current += char
        index += 1
    parts.append(current)
    return parts


def _fully_wrapped(text: str) -> bool:
    if not text.startswith("(") or not text.endswith(")"):
        return False
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index == len(text) - 1
    return False


class ConditionEvaluator:
    """The subset of DynamoDB condition syntax this codebase actually writes."""

    OPERATORS = ("<>", ">=", "<=", "=", "<", ">")

    def __init__(self, names: dict[str, str] | None, values: dict[str, Any] | None) -> None:
        self.names = names or {}
        self.values = values or {}

    def holds(self, expression: str | None, item: dict[str, Any] | None) -> bool:
        if not expression:
            return True
        return self._clause(expression, item or {})

    def _clause(self, expression: str, item: dict[str, Any]) -> bool:
        text = expression.strip()
        if _fully_wrapped(text):
            return self._clause(text[1:-1], item)
        for separator, combine in ((" OR ", any), (" AND ", all)):
            parts = _split_top(text, separator)
            if len(parts) > 1:
                return combine(self._clause(part, item) for part in parts)
        return self._primary(text, item)

    def _primary(self, expression: str, item: dict[str, Any]) -> bool:
        text = expression.strip()
        if text.startswith("attribute_not_exists("):
            return self._path(text[len("attribute_not_exists(") : -1]) not in item
        if text.startswith("attribute_exists("):
            return self._path(text[len("attribute_exists(") : -1]) in item
        for operator in self.OPERATORS:
            if operator in text:
                left, right = text.split(operator, 1)
                stored = item.get(self._path(left))
                expected = self._value(right)
                return self._compare(operator, stored, expected)
        raise AssertionError(f"unsupported condition: {expression}")

    @staticmethod
    def _compare(operator: str, stored: Any, expected: Any) -> bool:
        if operator == "=":
            return stored == expected
        if operator == "<>":
            return stored != expected
        if stored is None:
            return False
        if operator == "<":
            return stored < expected
        if operator == ">":
            return stored > expected
        if operator == "<=":
            return stored <= expected
        return stored >= expected

    def _path(self, token: str) -> str:
        name = token.strip()
        return self.names.get(name, name)

    def _value(self, token: str) -> Any:
        name = token.strip()
        if name.startswith(":"):
            if name not in self.values:
                raise AssertionError(f"unbound value: {name}")
            return self.values[name]
        return name


def _filter_holds(condition: Any, item: dict[str, Any]) -> bool:
    """Evaluate one boto3 `Attr` filter the way the index would."""
    if condition is None:
        return True
    built = condition.get_expression()
    operator = built["operator"]
    values = built["values"]
    if operator == "AND":
        return all(_filter_holds(value, item) for value in values)
    if operator == "OR":
        return any(_filter_holds(value, item) for value in values)
    name, expected = values
    stored = item.get(name.name)
    if operator == "=":
        return stored == expected
    if operator == "<>":
        return stored != expected
    raise AssertionError(f"unsupported filter: {operator}")


def _as_stored(value: Any) -> Any:
    """Numbers as the table gives them back, which is never `int`.

    The resource interface deserializes every stored number to `Decimal`. A double
    that hands back the `int` it was given makes every guard written against `int`
    pass here and fail in production - which is exactly what happened to the version
    checks on the opening path.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _as_stored(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_stored(item) for item in value]
    return value


class FakeAccountTable:
    """In-memory single table honouring the conditions the production code sends."""

    def __init__(
        self,
        *,
        claim_gate: threading.Barrier | None = None,
        email_gate: threading.Barrier | None = None,
    ) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.access: list[tuple[str, str, str]] = []
        self.lock = threading.Lock()
        self.claim_gate = claim_gate
        self.gated: set[int] = set()
        self.email_gate = email_gate
        self.email_gated: set[int] = set()

    def _record(self, method: str, key: dict[str, str]) -> None:
        self.access.append((method, str(key["PK"]).split("#", 1)[0], str(key["SK"])))

    def _await_gate(self, key: tuple[str, str]) -> None:
        """Hold every reader of the invitation row until all of them have read it.

        Releasing the lock first is not enough: without this the threads serialise by
        luck and no two callers ever hold the same `issued` status at once, which is
        exactly the race the conditional claim exists to survive.
        """
        if self.claim_gate is None or not key[0].startswith("ACCOUNT_INVITATION#"):
            return
        with self.lock:
            if threading.get_ident() in self.gated:
                return
            self.gated.add(threading.get_ident())
        self.claim_gate.wait(timeout=5)

    def get_item(self, *, Key: dict[str, str], ConsistentRead: bool = False) -> dict[str, Any]:  # noqa: N803
        del ConsistentRead
        key = (Key["PK"], Key["SK"])
        with self.lock:
            self._record("get_item", Key)
            item = self.rows.get(key)
            response = {"Item": deepcopy(item)} if item is not None else {}
        self._await_gate(key)
        return response

    def put_item(
        self,
        *,
        Item: dict[str, Any],  # noqa: N803
        ConditionExpression: str | None = None,  # noqa: N803
        ExpressionAttributeNames: dict[str, str] | None = None,  # noqa: N803
        ExpressionAttributeValues: dict[str, Any] | None = None,  # noqa: N803
    ) -> dict[str, Any]:
        key = (str(Item["PK"]), str(Item["SK"]))
        evaluator = ConditionEvaluator(ExpressionAttributeNames, ExpressionAttributeValues)
        with self.lock:
            self._record("put_item", {"PK": key[0], "SK": key[1]})
            if not evaluator.holds(ConditionExpression, self.rows.get(key)):
                raise _conditional_error("PutItem")
            self.rows[key] = _as_stored(deepcopy(Item))
        return {}

    def update_item(
        self,
        *,
        Key: dict[str, str],  # noqa: N803
        UpdateExpression: str,  # noqa: N803
        ConditionExpression: str | None = None,  # noqa: N803
        ExpressionAttributeNames: dict[str, str] | None = None,  # noqa: N803
        ExpressionAttributeValues: dict[str, Any] | None = None,  # noqa: N803
        ReturnValues: str | None = None,  # noqa: N803
    ) -> dict[str, Any]:
        del ReturnValues
        key = (Key["PK"], Key["SK"])
        evaluator = ConditionEvaluator(ExpressionAttributeNames, ExpressionAttributeValues)
        with self.lock:
            self._record("update_item", Key)
            current = self.rows.get(key)
            if not evaluator.holds(ConditionExpression, current):
                raise _conditional_error("UpdateItem")
            updated = deepcopy(current) if current else dict(Key)
            self._apply(updated, UpdateExpression, evaluator)
            self.rows[key] = _as_stored(updated)
        return {"Attributes": deepcopy(updated)}

    @staticmethod
    def _apply(item: dict[str, Any], expression: str, evaluator: ConditionEvaluator) -> None:
        text = expression.strip()
        assert text.upper().startswith("SET "), f"unsupported update: {expression}"
        for assignment in _split_top(text[4:], ","):
            target, source = assignment.split("=", 1)
            item[evaluator._path(target)] = evaluator._value(source)

    def query(
        self,
        *,
        IndexName: str,  # noqa: N803
        KeyConditionExpression: Any,  # noqa: N803
        FilterExpression: Any = None,  # noqa: N803
        Limit: int | None = None,  # noqa: N803
        **_kwargs: Any,
    ) -> dict[str, Any]:
        """Model what the index actually holds: every row carrying the address.

        The profile row has no privileged position in GSI-Email - the invitation row
        repeats the address and sits right beside it - so only the caller's own
        FilterExpression narrows the answer. Limit is applied before the filter,
        exactly as DynamoDB applies it, which is why a caller that sends both gets
        fewer rows than it asked for rather than the wrong ones.
        """
        assert IndexName == "GSI-Email"
        expected = KeyConditionExpression.get_expression()["values"][1]
        with self.lock:
            matches = [
                deepcopy(item)
                for _, item in sorted(self.rows.items())
                if item.get("email") == expected
            ]
        if Limit is not None:
            matches = matches[: int(Limit)]
        response = {"Items": [row for row in matches if _filter_holds(FilterExpression, row)]}
        self._await_email_gate()
        return response

    def _await_email_gate(self) -> None:
        """Hold every reader of the address index until all of them have read it.

        Same reason as `_await_gate`: without it two openings of the same address
        serialise by luck, one of them sees the other's row through the pre-read, and
        the conditional claim underneath is never asked to decide anything.
        """
        if self.email_gate is None:
            return
        with self.lock:
            if threading.get_ident() in self.email_gated:
                return
            self.email_gated.add(threading.get_ident())
        self.email_gate.wait(timeout=5)

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        """Whole-table paging, the shape `scan_owned_private_rows` walks.

        No filter is sent, so this hands back rows as they sort and leaves the
        caller to decide which of them belong to the account being deleted -
        which is where that rule actually lives.
        """
        with self.lock:
            ordered = [deepcopy(row) for _, row in sorted(self.rows.items())]
        start = kwargs.get("ExclusiveStartKey")
        if start:
            after = (str(start["PK"]), str(start["SK"]))
            ordered = [row for row in ordered if (str(row["PK"]), str(row["SK"])) > after]
        limit = int(kwargs.get("Limit") or 0) or len(ordered) or 1
        page, rest = ordered[:limit], ordered[limit:]
        response: dict[str, Any] = {"Items": page}
        if rest and page:
            response["LastEvaluatedKey"] = {
                "PK": str(page[-1]["PK"]),
                "SK": str(page[-1]["SK"]),
            }
        return response

    def put_profile_with_fence(
        self, profile: dict[str, Any], fence: dict[str, Any]
    ) -> None:
        for row in (profile, fence):
            key = (str(row["PK"]), str(row["SK"]))
            if key in self.rows:
                raise account_deletion_repo.AccountDeletionConflict("profile exists")
        for row in (profile, fence):
            self.rows[(str(row["PK"]), str(row["SK"]))] = _as_stored(deepcopy(row))

    def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
        """All conditions, then all effects, under one lock.

        The lock is the transaction: without it two callers can both pass their
        conditions before either writes, and a conditional claim that the real store
        would refuse gets through the double.
        """
        staged: list[tuple[tuple[str, str], dict[str, Any] | None]] = []
        with self.lock:
            for operation in operations:
                for kind, body in operation.items():
                    key = (
                        (str(body["Key"]["PK"]), str(body["Key"]["SK"]))
                        if "Key" in body
                        else (str(body["Item"]["PK"]), str(body["Item"]["SK"]))
                    )
                    evaluator = ConditionEvaluator(
                        body.get("ExpressionAttributeNames"),
                        body.get("ExpressionAttributeValues"),
                    )
                    current = self.rows.get(key)
                    if not evaluator.holds(body.get("ConditionExpression"), current):
                        raise account_deletion_repo.AccountDeletionConflict(
                            f"{kind} refused for {key}"
                        )
                    if kind == "ConditionCheck":
                        continue
                    if kind == "Put":
                        staged.append((key, _as_stored(deepcopy(body["Item"]))))
                        continue
                    if kind == "Delete":
                        staged.append((key, None))
                        continue
                    assert kind == "Update", f"unsupported operation: {kind}"
                    updated = deepcopy(current) if current else dict(body["Key"])
                    self._apply(updated, body["UpdateExpression"], evaluator)
                    staged.append((key, _as_stored(updated)))
            for key, row in staged:
                if row is None:
                    self.rows.pop(key, None)
                else:
                    self.rows[key] = row

    def profiles(self) -> list[dict[str, Any]]:
        return [deepcopy(row) for key, row in self.rows.items() if key[1] == "PROFILE"]

    def claims(self) -> list[dict[str, Any]]:
        return [
            deepcopy(row)
            for key, row in self.rows.items()
            if key[1] == account_email_claim_repo.CLAIM_SK
        ]

    def invitations(self) -> list[dict[str, Any]]:
        return [
            deepcopy(row)
            for key, row in self.rows.items()
            if key[0].startswith("ACCOUNT_INVITATION#")
        ]

    def dump(self) -> str:
        return json.dumps(
            [
                {key: str(value) for key, value in row.items()}
                for row in self.rows.values()
            ],
            sort_keys=True,
        )


class RecordingProvider:
    """Account provider double; records what it was asked to create.

    `created` is the live population, not a call log: `delete_account` takes an entry
    back out, so a compensated failure and a clean run are told apart by what is left
    standing rather than by how many calls were made.
    """

    def __init__(
        self,
        *,
        failure: Exception | None = None,
        group_failures: int = 0,
        deletable: bool = True,
    ) -> None:
        self.created: list[dict[str, str]] = []
        self.groups: list[dict[str, str]] = []
        self.deleted: list[str] = []
        self.create_calls = 0
        self.failure = failure
        self.group_failures = group_failures
        self.deletable = deletable
        if deletable:
            self.delete_account = self._delete_account

    def create_account(self, *, email: str, password: str) -> str:
        self.create_calls += 1
        if self.failure is not None:
            raise self.failure
        self.created.append({"email": email, "password": password})
        return f"sub-{uuid4().hex[:12]}"

    def ensure_account_group(self, *, email: str, user_id: str, group: str) -> None:
        if self.group_failures > 0:
            self.group_failures -= 1
            raise RuntimeError("group membership temporarily unavailable")
        self.groups.append({"email": email, "user_id": user_id, "group": group})

    def _delete_account(self, *, email: str) -> None:
        self.deleted.append(email)
        self.created = [entry for entry in self.created if entry["email"] != email]


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeAccountTable:
    fake = FakeAccountTable()
    for module in (
        account_email_claim_repo,
        account_invitation_repo,
        account_number_repo,
        account_deletion_repo,
        identity_repo,
        security_audit_repo,
        user_repo,
    ):
        monkeypatch.setattr(module, "get_table", lambda fake=fake: fake)
    return fake


def _admin() -> dict[str, Any]:
    return {
        "user_id": "admin-1",
        "role": "admin",
        "account_status": "active",
        "current_grants": [
            {
                "capability": "admin_identity_manager",
                "scope": "global",
                "status": "active",
                "version": 1,
            }
        ],
    }


def _moment(offset_seconds: int = 0) -> datetime:
    return datetime(2026, 3, 1, 9, 0, tzinfo=UTC) + timedelta(seconds=offset_seconds)


def _invite(
    table: FakeAccountTable,
    *,
    role: str = "student",
    email: str = "invitee@example.ch",
    expiry: int = 3600,
    at: datetime | None = None,
) -> dict[str, Any]:
    del table
    return account_provisioning_service.invite_account(
        actor=_admin(),
        role=role,
        email=email,
        full_name="Alex Muster",
        invitation_expiry_seconds=expiry,
        now=lambda: at or _moment(),
    )


def _claim(
    *,
    token: str,
    provider: RecordingProvider | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    return account_provisioning_service.claim_invitation(
        token=token,
        password="Startpass1",
        issuer="https://issuer.example",
        provider=provider or RecordingProvider(),
        now=lambda: at or _moment(60),
    )


def _rejection(exc_info: pytest.ExceptionInfo[HTTPException]) -> bytes:
    error = exc_info.value
    return json.dumps(
        {"status": error.status_code, "detail": error.detail}, sort_keys=True
    ).encode("utf-8")


def test_邀请落库含角色过期时间使用标记邀请人与预分配编号(table: FakeAccountTable) -> None:
    issued = _invite(table, role="teacher")

    stored = table.invitations()
    rows = [row for row in stored if row["SK"] == account_invitation_repo.INVITATION_SK]
    assert len(rows) == 1
    invitation = rows[0]
    assert invitation["role"] == "teacher"
    assert invitation["invited_by"] == "admin-1"
    assert invitation["status"] == account_invitation_repo.ISSUED_STATUS
    assert invitation["account_number"] == issued["accountNumber"]
    assert "used_at" not in invitation
    # The table's time-to-live attribute is `expires_at`, and DynamoDB only expires a
    # numeric epoch, so an ISO string there would never be collected.
    stored_expiry = invitation["expires_at"]
    assert not isinstance(stored_expiry, (str, bool))
    assert int(stored_expiry) == stored_expiry == int(_moment(3600).timestamp())
    assert invitation["expires_at_iso"] == _moment(3600).isoformat()


def test_令牌只在签发那一刻可读_库里只有摘要(table: FakeAccountTable) -> None:
    issued = _invite(table)
    token = issued["activationToken"]

    assert len(token) >= 32
    dump = table.dump()
    assert token not in dump
    digest = sha256(token.encode("utf-8")).hexdigest()
    assert digest in dump
    stored = account_invitation_repo.get_invitation(digest)
    assert stored is not None
    assert stored["token_digest"] == digest
    # Nothing in the stored row reverses to the token.
    assert all(token not in str(value) for value in stored.values())


def test_同一令牌第二次认领被拒(table: FakeAccountTable) -> None:
    issued = _invite(table)
    first = _claim(token=issued["activationToken"])
    assert first["status"] == "active"

    with pytest.raises(HTTPException) as exc_info:
        _claim(token=issued["activationToken"], at=_moment(120))
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "invitation_invalid"}


def test_过期令牌给出明确原因而不是崩溃(table: FakeAccountTable) -> None:
    issued = _invite(table, expiry=60)

    with pytest.raises(HTTPException) as exc_info:
        _claim(token=issued["activationToken"], at=_moment(3600))
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "invitation_expired"}


def test_不存在的令牌与已使用的令牌响应逐字节相同且访问序列相同(
    table: FakeAccountTable,
) -> None:
    issued = _invite(table)
    _claim(token=issued["activationToken"])
    used_token = issued["activationToken"]
    missing_token = secrets.token_urlsafe(32)

    table.access.clear()
    with pytest.raises(HTTPException) as used_error:
        _claim(token=used_token, at=_moment(120))
    used_access = list(table.access)

    table.access.clear()
    with pytest.raises(HTTPException) as missing_error:
        _claim(token=missing_token, at=_moment(120))
    missing_access = list(table.access)

    assert _rejection(used_error) == _rejection(missing_error)
    assert used_access == missing_access


def test_不存在的令牌与已使用的令牌耗时不可区分(table: FakeAccountTable) -> None:
    issued = _invite(table)
    _claim(token=issued["activationToken"])
    used_token = issued["activationToken"]
    missing_token = secrets.token_urlsafe(32)

    def _sample(token: str) -> float:
        start = time.perf_counter()
        try:
            _claim(token=token, at=_moment(120))
        except HTTPException:
            pass
        return time.perf_counter() - start

    # Warm the interpreter so the first-call cost does not land on one arm.
    for _ in range(20):
        _sample(used_token)
        _sample(missing_token)

    used = median(_sample(used_token) for _ in range(200))
    missing = median(_sample(missing_token) for _ in range(200))
    assert abs(used - missing) < TIMING_ORACLE_THRESHOLD_SECONDS


def test_撤销的令牌与不存在的令牌响应相同(table: FakeAccountTable) -> None:
    issued = _invite(table)
    account_provisioning_service.revoke_invitation(
        actor=_admin(), invitation_id=issued["invitationId"], now=lambda: _moment(30)
    )

    with pytest.raises(HTTPException) as revoked_error:
        _claim(token=issued["activationToken"], at=_moment(60))
    with pytest.raises(HTTPException) as missing_error:
        _claim(token=secrets.token_urlsafe(32), at=_moment(60))
    assert _rejection(revoked_error) == _rejection(missing_error)


def test_激活后的角色与邀请预置的角色逐字相同且编号前缀一致(
    table: FakeAccountTable,
) -> None:
    for role, prefix in EXPECTED_PREFIXES.items():
        issued = _invite(table, role=role, email=f"{role}@example.ch")
        assert issued["role"] == role
        assert issued["accountNumber"].startswith(prefix)

        provider = RecordingProvider()
        activated = _claim(token=issued["activationToken"], provider=provider)

        profile = user_repo.get_user(issued["userId"])
        assert profile is not None
        assert profile["role"] == role
        assert activated["role"] == role
        assert profile["account_status"] == "active"
        assert profile["account_number"] == issued["accountNumber"]
        assert account_numbering_service.role_for_account_number(
            str(profile["account_number"])
        ) == role
        assert provider.groups[-1]["group"] == account_provisioning_service.ROLE_GROUPS[role]


def test_重复接线同一账号被拒且不会拿到第二个编号(table: FakeAccountTable) -> None:
    issued = _invite(table)
    account_id = issued["userId"]

    with pytest.raises(HTTPException) as exc_info:
        account_provisioning_service._attach_account_number(
            account_id=account_id, role="student", now=_moment(10)
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "account_number_already_assigned"}

    claims = [
        row
        for row in table.rows.values()
        if row.get("SK") == account_number_repo.CLAIM_SK
        and row.get("account_id") == account_id
    ]
    assert len(claims) == 1


def test_条件写本身拦住第二个编号_即使调用方读到旧快照(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store refuses the second number, not the read above it.

    The profile is handed back without `account_number` while the row already carries
    one and keeps the same version, so the version compare-and-set cannot decide this
    case: only `attribute_not_exists(account_number)` can.
    """
    issued = _invite(table)
    account_id = issued["userId"]
    key = (f"USER#{account_id}", "PROFILE")
    table.rows[key]["version"] = 1
    stale = deepcopy(table.rows[key])
    stale.pop("account_number")
    monkeypatch.setattr(user_repo, "get_user", lambda user_id: deepcopy(stale))

    with pytest.raises(HTTPException) as exc_info:
        account_provisioning_service._attach_account_number(
            account_id=account_id, role="student", now=_moment(10)
        )
    assert exc_info.value.status_code == 409
    assert table.rows[key]["account_number"] == issued["accountNumber"]


def test_编号写入的条件表达式含attribute_not_exists() -> None:
    operation = user_repo.profile_update_operation(
        "student-1",
        update_expression="SET #account_number = :account_number",
        expression_attribute_names={"#account_number": "account_number"},
        expression_attribute_values={":account_number": "S26-0001"},
        expected_version=1,
        additional_condition_expression="attribute_not_exists(#account_number)",
    )
    assert "attribute_not_exists(#account_number)" in operation["Update"]["ConditionExpression"]
    source = SERVICE_PATH.read_text(encoding="utf-8")
    assert 'additional_condition_expression="attribute_not_exists(#account_number)"' in source


def test_直接分配返回一次性初始密码且密码不落库(table: FakeAccountTable) -> None:
    provider = RecordingProvider()
    assigned = account_provisioning_service.assign_account(
        actor=_admin(),
        role="parent",
        email="parent@example.ch",
        provider=provider,
        full_name="Chris Muster",
        issuer="https://issuer.example",
        now=lambda: _moment(),
    )

    password = assigned["initialPassword"]
    # Written out here, not read back from the service: an assertion that quotes the
    # constant it is guarding agrees with whatever that constant is changed to.
    assert len(password) >= 12
    assert any(char.isupper() for char in password)
    assert any(char.islower() for char in password)
    assert any(char.isdigit() for char in password)
    assert provider.created == [{"email": "parent@example.ch", "password": password}]
    assert password not in table.dump()
    assert assigned["accountNumber"].startswith("P")
    profile = user_repo.get_user(assigned["userId"])
    assert profile is not None
    assert profile["role"] == "parent"
    assert profile["account_status"] == "active"
    assert profile["account_number"] == assigned["accountNumber"]


def test_两次分配拿到两个不同账号与不同编号(table: FakeAccountTable) -> None:
    first = account_provisioning_service.assign_account(
        actor=_admin(),
        role="student",
        email="one@example.ch",
        provider=RecordingProvider(),
        issuer="https://issuer.example",
        now=lambda: _moment(),
    )
    second = account_provisioning_service.assign_account(
        actor=_admin(),
        role="student",
        email="two@example.ch",
        provider=RecordingProvider(),
        issuer="https://issuer.example",
        now=lambda: _moment(10),
    )
    assert first["accountNumber"] != second["accountNumber"]
    assert first["initialPassword"] != second["initialPassword"]
    assert {first["accountNumber"], second["accountNumber"]} == {"S26-0001", "S26-0002"}


def test_重发邀请换新令牌但沿用同一账号与编号(table: FakeAccountTable) -> None:
    issued = _invite(table)
    reissued = account_provisioning_service.reissue_invitation(
        actor=_admin(), invitation_id=issued["invitationId"], now=lambda: _moment(30)
    )

    assert reissued["userId"] == issued["userId"]
    assert reissued["accountNumber"] == issued["accountNumber"]
    assert reissued["activationToken"] != issued["activationToken"]

    with pytest.raises(HTTPException) as exc_info:
        _claim(token=issued["activationToken"], at=_moment(60))
    assert exc_info.value.detail == {"code": "invitation_invalid"}
    assert _claim(token=reissued["activationToken"], at=_moment(60))["status"] == "active"


def test_非管理员不能发邀请也不能分配账号(table: FakeAccountTable) -> None:
    del table
    for actor in (
        {"user_id": "student-1", "role": "student", "account_status": "active"},
        {"user_id": "teacher-1", "role": "teacher", "account_status": "active"},
        {"user_id": "parent-1", "role": "parent", "account_status": "active"},
        {"user_id": "admin-2", "role": "admin", "account_status": "active"},
    ):
        with pytest.raises(HTTPException) as invite_error:
            account_provisioning_service.invite_account(
                actor=actor, role="student", email="x@example.ch", now=_moment
            )
        assert invite_error.value.status_code == 403
        with pytest.raises(HTTPException) as assign_error:
            account_provisioning_service.assign_account(
                actor=actor,
                role="student",
                email="x@example.ch",
                provider=RecordingProvider(),
                issuer="https://issuer.example",
                now=_moment,
            )
        assert assign_error.value.status_code == 403


def test_令牌比较真的走了常数时间比较(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A spy on `secrets.compare_digest` that a plain `==` cannot satisfy."""
    issued = _invite(table)
    calls: list[tuple[str, str]] = []
    original = secrets.compare_digest

    def spy(left: Any, right: Any) -> bool:
        calls.append((str(left), str(right)))
        return original(left, right)

    monkeypatch.setattr(account_provisioning_service.secrets, "compare_digest", spy)
    _claim(token=issued["activationToken"])

    digest = sha256(issued["activationToken"].encode("utf-8")).hexdigest()
    assert (digest, digest) in calls


def test_服务源码里没有对令牌或摘要的直接相等比较() -> None:
    source = SERVICE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
            continue
        segment = ast.get_source_segment(source, node) or ""
        if "digest" in segment or "token" in segment:
            offenders.append(segment)
    assert offenders == []
    assert source.count("secrets.compare_digest") >= 1


def test_并发两次认领同一令牌只有一个能建号(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both callers read `issued` before either writes; only the store can break the tie."""
    gate = threading.Barrier(2, timeout=5)
    fake = FakeAccountTable(claim_gate=gate)
    for module in (
        account_email_claim_repo,
        account_invitation_repo,
        account_number_repo,
        account_deletion_repo,
        identity_repo,
        security_audit_repo,
        user_repo,
    ):
        monkeypatch.setattr(module, "get_table", lambda fake=fake: fake)

    issued = _invite(fake)
    fake.gated.clear()
    provider = RecordingProvider()
    outcomes: list[object] = []

    def attempt() -> None:
        try:
            outcomes.append(_claim(token=issued["activationToken"], provider=provider))
        except HTTPException as error:
            outcomes.append(error)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    accepted = [item for item in outcomes if isinstance(item, dict)]
    rejected = [item for item in outcomes if isinstance(item, HTTPException)]
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert rejected[0].detail == {"code": "invitation_invalid"}
    assert len(provider.created) == 1


# ---------------------------------------------------------------------------
# Compensation: a multi-step opening that dies part-way must not keep the address,
# the token or the identity it had reserved.
# ---------------------------------------------------------------------------


def test_分配途中provider失败后同一邮箱仍可重新分配(table: FakeAccountTable) -> None:
    """A provider outage costs a number, never the address."""
    with pytest.raises(HTTPException) as exc_info:
        account_provisioning_service.assign_account(
            actor=_admin(),
            role="student",
            email="x@example.ch",
            provider=RecordingProvider(failure=RuntimeError("provider down")),
            issuer="https://issuer.example",
            now=lambda: _moment(),
        )
    assert exc_info.value.status_code == 503

    retry = account_provisioning_service.assign_account(
        actor=_admin(),
        role="student",
        email="x@example.ch",
        provider=RecordingProvider(),
        issuer="https://issuer.example",
        now=lambda: _moment(10),
    )
    assert retry["accountStatus"] == "active"
    assert retry["email"] == "x@example.ch"
    live = [
        row
        for row in table.profiles()
        if row.get("account_status") not in {
            account_provisioning_service.FAILED_ACCOUNT_STATUS
        }
    ]
    assert [row["user_id"] for row in live] == [retry["userId"]]


def test_认领途中绑组失败后同一令牌仍可再次认领(table: FakeAccountTable) -> None:
    """The invitee's own account must survive one transient failure at the provider."""
    issued = _invite(table)
    provider = RecordingProvider(group_failures=1)

    with pytest.raises(HTTPException) as exc_info:
        _claim(token=issued["activationToken"], provider=provider)
    assert exc_info.value.status_code == 503

    digest = sha256(issued["activationToken"].encode("utf-8")).hexdigest()
    parked = account_invitation_repo.get_invitation(digest)
    assert parked is not None
    assert parked["status"] == account_invitation_repo.ISSUED_STATUS

    retry = _claim(token=issued["activationToken"], provider=provider, at=_moment(120))
    assert retry["status"] == "active"
    # Exactly one identity is left standing: the failed attempt's was withdrawn, and
    # the retry did not skip creating one.
    assert len(provider.created) == 1
    assert provider.create_calls == 2
    assert provider.deleted == ["invitee@example.ch"]
    profile = user_repo.get_user(issued["userId"])
    assert profile is not None and profile["account_status"] == "active"


def _numbering_fails_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the next allocation only. `monkeypatch.undo()` is not an option here: it
    would also revert the table fixture's patches and send the retry at real AWS."""
    original = account_numbering_service.allocate_account_number
    remaining = [1]

    def flaky(**kwargs: Any) -> str:
        if remaining[0] > 0:
            remaining[0] -= 1
            raise account_numbering_service.AccountNumberAllocationFailed("counter down")
        return original(**kwargs)

    monkeypatch.setattr(account_numbering_service, "allocate_account_number", flaky)


def test_邀请途中编号分配失败不留下无法重开的账号(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    _numbering_fails_once(monkeypatch)
    with pytest.raises(HTTPException) as exc_info:
        _invite(table, email="wedge@example.ch")
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {"code": "account_number_unavailable"}
    assert [row["email"] for row in table.profiles()] != ["wedge@example.ch"]

    reopened = _invite(table, email="wedge@example.ch", at=_moment(10))
    assert reopened["accountStatus"] == "invited"
    assert reopened["email"] == "wedge@example.ch"


def test_半途失败的账号无法被继续推进(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parked row is terminal: it cannot be talked back into an active account."""
    _numbering_fails_once(monkeypatch)
    with pytest.raises(HTTPException):
        _invite(table, email="parked@example.ch")

    parked = [
        row
        for row in table.profiles()
        if row.get("account_status")
        == account_provisioning_service.FAILED_ACCOUNT_STATUS
    ]
    assert len(parked) == 1
    # The released address carries no `@`, so it can never collide with a real one.
    assert "@" not in str(parked[0]["email"])
    with pytest.raises(HTTPException) as exc_info:
        account_provisioning_service._transition_account_status(
            account_id=str(parked[0]["user_id"]),
            expected_status="invited",
            next_status="active",
            now=_moment(30),
        )
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Password policy, entropy and source of randomness
# ---------------------------------------------------------------------------


def _password_claim_app(provider: RecordingProvider) -> Any:
    from fastapi import FastAPI

    from stoa.config import Settings, get_settings
    from stoa.routers import auth as auth_router

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/auth")
    app.dependency_overrides[get_settings] = lambda: Settings(
        cognito_user_pool_id="eu-central-2_test", aws_region="eu-central-2"
    )
    app.dependency_overrides[auth_router.get_account_identity_provider] = lambda: provider
    return app


class ThrottleAwareTable(FakeAccountTable):
    """The provisioning fake plus the atomic counter the claim throttle increments."""

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        expression = str(kwargs.get("UpdateExpression") or "")
        if " ADD " not in f" {expression.strip()} ":
            return super().update_item(**kwargs)
        key = (kwargs["Key"]["PK"], kwargs["Key"]["SK"])
        values = kwargs.get("ExpressionAttributeValues") or {}
        with self.lock:
            row = self.rows.setdefault(key, dict(kwargs["Key"]))
            row["attempts"] = int(row.get("attempts") or 0) + int(values[":one"])
            return {"Attributes": {"attempts": row["attempts"]}}


def test_认领端点在令牌被消费前就拒绝弱密码(monkeypatch: pytest.MonkeyPatch) -> None:
    """A password the identity pool would refuse must not cost the invitee their token."""
    from fastapi.testclient import TestClient

    from stoa.routers import auth as auth_router

    fake = ThrottleAwareTable()
    for module in (
        account_invitation_repo,
        account_number_repo,
        account_deletion_repo,
        identity_repo,
        security_audit_repo,
        user_repo,
        auth_router,
    ):
        monkeypatch.setattr(module, "get_table", lambda fake=fake: fake)

    issued = _invite(fake, at=datetime.now(UTC), expiry=3600)
    token = issued["activationToken"]
    digest = sha256(token.encode("utf-8")).hexdigest()
    provider = RecordingProvider()
    client = TestClient(_password_claim_app(provider))

    weak = client.post("/auth/invitations/claim", json={"token": token, "password": "password"})
    assert weak.status_code == 422
    assert provider.create_calls == 0
    stored = account_invitation_repo.get_invitation(digest)
    assert stored is not None
    assert stored["status"] == account_invitation_repo.ISSUED_STATUS

    strong = client.post(
        "/auth/invitations/claim", json={"token": token, "password": "Startpass1"}
    )
    assert strong.status_code == 200
    assert strong.json()["status"] == "active"


def test_改密与认领共用同一处密码复杂度定义() -> None:
    """Two copies of a policy drift; this pins them to one definition."""
    from stoa.routers import auth as auth_router

    source = (
        Path(__file__).resolve().parents[1] / "src" / "stoa" / "routers" / "auth.py"
    ).read_text(encoding="utf-8")
    assert source.count("def enforce_password_complexity") == 1
    assert source.count("enforce_password_complexity(value)") == 2
    for weak in ("password", "PASSWORD1", "Password", "Pass1"):
        with pytest.raises(ValueError):
            auth_router.enforce_password_complexity(weak)
    assert auth_router.enforce_password_complexity("Startpass1") == "Startpass1"


def test_初始密码来自secrets而不是random(monkeypatch: pytest.MonkeyPatch) -> None:
    """`random` is seeded and predictable; a credential minted from it is guessable."""
    calls: list[str] = []
    original = secrets.choice

    def spy(sequence: Any) -> Any:
        calls.append(str(sequence)[:1])
        return original(sequence)

    monkeypatch.setattr(account_provisioning_service.secrets, "choice", spy)
    password = account_provisioning_service.generate_initial_password()

    assert len(calls) >= len(password)
    assert len(calls) >= 12

    source = SERVICE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(str(node.module))
    assert "random" not in imported
    assert "random." not in source


def test_初始密码字符池满足独立写死的下界() -> None:
    # Hand-written bounds. Reading them back off the service would make the assertion
    # agree with any pool the service is trimmed down to.
    upper = account_provisioning_service.PASSWORD_UPPER
    lower = account_provisioning_service.PASSWORD_LOWER
    digits = account_provisioning_service.PASSWORD_DIGITS
    assert len(set(upper)) >= 20
    assert len(set(lower)) >= 20
    assert len(set(digits)) >= 8
    assert len(set(upper + lower + digits)) >= 50


def test_初始密码熵不低于80bit() -> None:
    pool = len(
        set(
            account_provisioning_service.PASSWORD_UPPER
            + account_provisioning_service.PASSWORD_LOWER
            + account_provisioning_service.PASSWORD_DIGITS
        )
    )
    length = account_provisioning_service.INITIAL_PASSWORD_LENGTH
    assert length * math.log2(pool) >= 80


def test_计时闸本身能识别出一个人造预言机(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calibration for the threshold above: plant a known oracle and require a catch.

    Without this the timing assertion is only a number somebody picked; a threshold
    two orders of magnitude above the real noise passes whatever it is pointed at.
    """
    issued = _invite(table)
    _claim(token=issued["activationToken"])
    used_token = issued["activationToken"]
    missing_token = secrets.token_urlsafe(32)
    original = account_invitation_repo.absent_invitation

    def slow_absent(*, token_digest: str) -> dict[str, Any]:
        time.sleep(PLANTED_ORACLE_DELAY_SECONDS)
        return original(token_digest=token_digest)

    monkeypatch.setattr(
        account_provisioning_service.account_invitation_repo,
        "absent_invitation",
        slow_absent,
    )

    def _sample(token: str) -> float:
        start = time.perf_counter()
        try:
            _claim(token=token, at=_moment(120))
        except HTTPException:
            pass
        return time.perf_counter() - start

    for _ in range(20):
        _sample(used_token)
        _sample(missing_token)

    used = median(_sample(used_token) for _ in range(100))
    missing = median(_sample(missing_token) for _ in range(100))
    assert abs(used - missing) >= TIMING_ORACLE_THRESHOLD_SECONDS


# ---------------------------------------------------------------------------
# Reissue: one account, at most one live invitation
# ---------------------------------------------------------------------------


def test_拿已作废的邀请id重发被拒绝(table: FakeAccountTable) -> None:
    issued = _invite(table)
    account_provisioning_service.reissue_invitation(
        actor=_admin(), invitation_id=issued["invitationId"], now=lambda: _moment(30)
    )

    with pytest.raises(HTTPException) as exc_info:
        account_provisioning_service.reissue_invitation(
            actor=_admin(), invitation_id=issued["invitationId"], now=lambda: _moment(60)
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "invitation_not_reissuable"}


def test_任何时刻一个账号最多一个issued邀请(table: FakeAccountTable) -> None:
    issued = _invite(table)
    first = account_provisioning_service.reissue_invitation(
        actor=_admin(), invitation_id=issued["invitationId"], now=lambda: _moment(30)
    )
    second = account_provisioning_service.reissue_invitation(
        actor=_admin(), invitation_id=first["invitationId"], now=lambda: _moment(60)
    )
    with pytest.raises(HTTPException):
        account_provisioning_service.reissue_invitation(
            actor=_admin(), invitation_id=issued["invitationId"], now=lambda: _moment(90)
        )

    live = [
        row
        for row in table.invitations()
        if row.get("status") == account_invitation_repo.ISSUED_STATUS
    ]
    assert len(live) == 1
    assert live[0]["invitation_id"] == second["invitationId"]


def test_邮箱大小写不同视为同一账号(table: FakeAccountTable) -> None:
    _invite(table, email="case@example.ch")

    with pytest.raises(HTTPException) as exc_info:
        _invite(table, email="Case@Example.CH", at=_moment(10))
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "account_exists"}
    assert len(table.profiles()) == 1


def test_归还令牌只认本次烧掉的那一行(table: FakeAccountTable) -> None:
    """Handing a token back must not become a second way to revive a dead one.

    A revoked invitation and an already-returned one both sit outside the burn this
    caller is entitled to undo, so the conditional write refuses them.
    """
    revoked = _invite(table, email="revoked@example.ch")
    account_provisioning_service.revoke_invitation(
        actor=_admin(), invitation_id=revoked["invitationId"], now=lambda: _moment(30)
    )
    revoked_digest = sha256(revoked["activationToken"].encode("utf-8")).hexdigest()
    assert (
        account_invitation_repo.restore_invitation(
            revoked_digest, restored_at=_moment(60).isoformat()
        )
        is False
    )
    stored = account_invitation_repo.get_invitation(revoked_digest)
    assert stored is not None
    assert stored["status"] == account_invitation_repo.REVOKED_STATUS

    burned = _invite(table, email="burned@example.ch", at=_moment(10))
    provider = RecordingProvider(group_failures=1)
    with pytest.raises(HTTPException):
        _claim(token=burned["activationToken"], provider=provider)
    burned_digest = sha256(burned["activationToken"].encode("utf-8")).hexdigest()
    # The claim already returned this one; a replayed restore finds it at version 1.
    assert (
        account_invitation_repo.restore_invitation(
            burned_digest, restored_at=_moment(90).isoformat()
        )
        is False
    )
    live = account_invitation_repo.get_invitation(burned_digest)
    assert live is not None
    assert live["status"] == account_invitation_repo.ISSUED_STATUS
    assert live["version"] == 1


def test_管理员直接开的账号欠一次改密(table: FakeAccountTable) -> None:
    """初始密码是管理员知道的，和被重置的账号欠的是同一件事。"""
    account_provisioning_service.assign_account(
        actor=_admin(),
        role="student",
        email="assigned@example.ch",
        provider=RecordingProvider(),
        issuer="https://issuer.example",
        now=lambda: _moment(),
    )

    profile = next(
        row for row in table.profiles() if row.get("email") == "assigned@example.ch"
    )
    assert profile["must_change_password"] is True


def test_受邀账号自己设密码_不欠这次改密(table: FakeAccountTable) -> None:
    """阴性对照：受邀人自选密码，没人知道它，强制改密只会白挡一道。"""
    account_provisioning_service.invite_account(
        actor=_admin(),
        role="student",
        email="invited@example.ch",
        now=lambda: _moment(),
    )

    profile = next(
        row for row in table.profiles() if row.get("email") == "invited@example.ch"
    )
    assert profile["must_change_password"] is False


# ---------------------------------------------------------------------------
# Uniqueness: the key is the pair `(address, role)`, and it is held by a
# conditional write rather than by a read of an eventually consistent index.
# ---------------------------------------------------------------------------


def test_占位行的条件写是attribute_not_exists() -> None:
    """The claim is taken by the store, and its key is the pair, not the address."""
    operation = account_email_claim_repo.claim_operation(
        email="Pin@Example.CH",
        role="student",
        account_id="student-1",
        created_at=_moment().isoformat(),
    )
    assert operation["Put"]["ConditionExpression"] == (
        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
    )
    item = operation["Put"]["Item"]
    assert item["PK"] == "EMAIL#pin@example.ch#student"
    assert item["SK"] == account_email_claim_repo.CLAIM_SK
    # The claim repeats the address under a name GSI-Email does not index, so it can
    # never be mistaken for the profile that holds it.
    assert "email" not in item
    assert item["claimed_email"] == "pin@example.ch"


def test_并发两次同一邮箱同一角色只有一个能建号(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both administrators read the address free; only the store can break the tie."""
    gate = threading.Barrier(2, timeout=5)
    fake = FakeAccountTable(email_gate=gate)
    for module in (
        account_email_claim_repo,
        account_invitation_repo,
        account_number_repo,
        account_deletion_repo,
        identity_repo,
        security_audit_repo,
        user_repo,
    ):
        monkeypatch.setattr(module, "get_table", lambda fake=fake: fake)

    original = user_repo.get_user_by_email_and_role
    pre_reads: list[object] = []

    def recording(email: str, role: str) -> Any:
        answer = original(email, role)
        pre_reads.append(answer)
        return answer

    monkeypatch.setattr(user_repo, "get_user_by_email_and_role", recording)

    outcomes: list[object] = []

    def attempt() -> None:
        try:
            outcomes.append(_invite(fake, email="twin@example.ch", role="student"))
        except HTTPException as error:
            outcomes.append(error)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    accepted = [item for item in outcomes if isinstance(item, dict)]
    rejected = [item for item in outcomes if isinstance(item, HTTPException)]
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert rejected[0].detail == {"code": "account_exists"}
    # The pre-read refused neither of them: both were told the address was free, which
    # is exactly the state the conditional claim underneath has to survive.
    assert pre_reads == [None, None]
    assert len(fake.profiles()) == 1
    assert [str(row["PK"]) for row in fake.claims()] == ["EMAIL#twin@example.ch#student"]
    # The loser burned no account number. Numbers are never recycled, so a second one
    # taken here would be gone for good.
    burned = [key for key in fake.rows if key[1] == "ACCOUNT_NUMBER"]
    assert len(burned) == 1
    assert accepted[0]["accountNumber"] == "S26-0001"


def test_同一邮箱不同角色各开一个账号(table: FakeAccountTable) -> None:
    """Negative control: a teacher whose own child studies here needs both accounts."""
    teacher = _invite(table, role="teacher", email="both@example.ch")
    parent = _invite(table, role="parent", email="both@example.ch", at=_moment(10))

    assert teacher["userId"] != parent["userId"]
    assert teacher["accountNumber"].startswith(EXPECTED_PREFIXES["teacher"])
    assert parent["accountNumber"].startswith(EXPECTED_PREFIXES["parent"])
    assert sorted(str(row["role"]) for row in table.profiles()) == ["parent", "teacher"]
    assert sorted(str(row["PK"]) for row in table.claims()) == [
        "EMAIL#both@example.ch#parent",
        "EMAIL#both@example.ch#teacher",
    ]
    # Weaker on the pair is not weaker on the duplicate it was always there to refuse.
    with pytest.raises(HTTPException) as exc_info:
        _invite(table, role="teacher", email="both@example.ch", at=_moment(20))
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "account_exists"}


def test_占位行与profile行是同一次提交(table: FakeAccountTable) -> None:
    """A refused claim leaves no account behind: the two rows are one commit."""
    taken = account_email_claim_repo.claim_item(
        email="taken@example.ch",
        role="student",
        account_id="student-somebody-else",
        created_at=_moment().isoformat(),
    )
    table.rows[(str(taken["PK"]), str(taken["SK"]))] = taken
    # The pre-read cannot see it - a claim row is not a profile - so the commit is the
    # only thing left that can refuse this opening.
    assert user_repo.get_user_by_email_and_role("taken@example.ch", "student") is None

    with pytest.raises(HTTPException) as exc_info:
        _invite(table, email="taken@example.ch")
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "account_exists"}
    assert table.profiles() == []
    assert [key for key in table.rows if key[1] == "ACCOUNT_FENCE"] == []
    assert [str(row["PK"]) for row in table.claims()] == [str(taken["PK"])]


def test_建号事务恰好写下profile围栏与占位行(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pinned against the claim quietly dropping out of the creation transaction."""
    committed: list[list[dict[str, Any]]] = []
    original = account_deletion_repo.transact

    def recording(operations: Any, *, table: Any = None) -> None:
        batch = list(operations)
        committed.append(deepcopy(batch))
        original(batch, table=table)

    monkeypatch.setattr(account_deletion_repo, "transact", recording)
    issued = _invite(table, email="atomic@example.ch")

    with_claim = [
        batch
        for batch in committed
        if any(
            str((body.get("Item") or {}).get("SK")) == account_email_claim_repo.CLAIM_SK
            for operation in batch
            for body in operation.values()
        )
    ]
    assert len(with_claim) == 1
    written = {
        (str(body["Item"]["PK"]), str(body["Item"]["SK"]))
        for operation in with_claim[0]
        for body in operation.values()
    }
    assert written == {
        (f"USER#{issued['userId']}", "PROFILE"),
        (f"USER#{issued['userId']}", "ACCOUNT_FENCE"),
        ("EMAIL#atomic@example.ch#student", account_email_claim_repo.CLAIM_SK),
    }


def test_邀请行不会被当成已存在的账号(table: FakeAccountTable) -> None:
    """The invitation repeats the address in GSI-Email; only the profile may answer."""
    issued = _invite(table, email="pending@example.ch")
    assert [
        str(row["email"]) for row in table.invitations() if "email" in row
    ] == ["pending@example.ch"]

    found = user_repo.get_user_by_email("pending@example.ch")
    assert found is not None
    assert found["SK"] == "PROFILE"
    assert found["user_id"] == issued["userId"]

    # Once the profile gives the address back, nothing else may stand in for it - that
    # is what used to cancel the compensation.
    table.rows[(f"USER#{issued['userId']}", "PROFILE")]["email"] = (
        f"{account_provisioning_service.FAILED_ACCOUNT_STATUS}:{issued['userId']}"
    )
    assert user_repo.get_user_by_email("pending@example.ch") is None
    assert user_repo.get_user_by_email_and_role("pending@example.ch", "student") is None


def test_邀请写下之后才失败_同一邮箱同角色仍可重开(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The uncovered square: the failure lands after the invitation row exists."""
    original_append = security_audit_repo.append_event

    def flaky(stream_id: str, event: Any) -> Any:
        if event.get("event_type") == "account_invitation_issued":
            raise RuntimeError("audit stream unavailable")
        return original_append(stream_id, event)

    monkeypatch.setattr(security_audit_repo, "append_event", flaky)

    committed: list[list[dict[str, Any]]] = []
    original_transact = account_deletion_repo.transact

    def recording(operations: Any, *, table: Any = None) -> None:
        batch = list(operations)
        committed.append(deepcopy(batch))
        original_transact(batch, table=table)

    monkeypatch.setattr(account_deletion_repo, "transact", recording)

    with pytest.raises(RuntimeError):
        _invite(table, email="late@example.ch")
    monkeypatch.setattr(security_audit_repo, "append_event", original_append)

    # The invitation row survives with the address on it, and no longer matters.
    assert [
        str(row["email"]) for row in table.invitations() if "email" in row
    ] == ["late@example.ch"]
    assert table.claims() == []
    # Parking the profile and giving the claim back is one commit, so the pair can
    # never be half-released.
    release = committed[-1]
    assert {str(next(iter(operation))) for operation in release} == {
        "ConditionCheck",
        "Update",
        "Delete",
    }

    reopened = _invite(table, email="late@example.ch", at=_moment(10))
    assert reopened["accountStatus"] == "invited"
    assert reopened["email"] == "late@example.ch"
    assert [str(row["PK"]) for row in table.claims()] == [
        "EMAIL#late@example.ch#student"
    ]


def test_认领失败不会把地址还给别人(table: FakeAccountTable) -> None:
    """A failed activation gives the token back, never the address.

    The account is still `invited` and still holds the pair. Releasing the claim here
    would open a second account for a person whose first token is live again - more
    accounts let through, which is the one direction this key may not move.
    """
    issued = _invite(table, email="held@example.ch")
    with pytest.raises(HTTPException):
        _claim(
            token=issued["activationToken"],
            provider=RecordingProvider(group_failures=1),
        )

    assert [str(row["PK"]) for row in table.claims()] == [
        "EMAIL#held@example.ch#student"
    ]
    with pytest.raises(HTTPException) as exc_info:
        _invite(table, email="held@example.ch", at=_moment(30))
    assert exc_info.value.detail == {"code": "account_exists"}


def test_大小写不同的邮箱落在同一个占位行(table: FakeAccountTable) -> None:
    _invite(table, email="Case2@Example.CH")
    assert [str(row["PK"]) for row in table.claims()] == [
        "EMAIL#case2@example.ch#student"
    ]


def _profile_for(table: FakeAccountTable, email: str) -> dict[str, Any]:
    return next(row for row in table.profiles() if row.get("email") == email)


def _delete_account(table: FakeAccountTable, email: str, *, generation: int = 1) -> str:
    """Take one account through the step of its deletion that ends the profile row."""
    profile = _profile_for(table, email)
    user_id = str(profile["user_id"])
    fence = table.rows[(f"USER#{user_id}", "ACCOUNT_FENCE")]
    fence["status"] = "deletion_pending"
    fence["generation"] = generation
    account_deletion_repo.replace_with_deletion_tombstone(
        profile,
        user_id=user_id,
        generation=generation,
        now_iso=_moment(60).isoformat(),
    )
    return user_id


def test_删号把地址还回去_同一对可以重开(table: FakeAccountTable) -> None:
    """A number is never recycled, an address always is.

    The tombstone drops `email`, so if the placeholder outlives the account nothing
    left in the table can name the pair again: the address reads free to the
    administrator and is refused by the store, with no account anywhere to point at.
    """
    _invite(table, email="leaver@example.ch")
    assert [str(row["PK"]) for row in table.claims()] == [
        "EMAIL#leaver@example.ch#student"
    ]

    _delete_account(table, "leaver@example.ch")

    assert table.claims() == []
    assert (
        account_email_claim_repo.get_claim(email="leaver@example.ch", role="student")
        is None
    )
    reopened = _invite(table, email="leaver@example.ch", at=_moment(120))
    assert reopened["accountNumber"]


def test_删号不会带走别人名下的同一对占位行(table: FakeAccountTable) -> None:
    """The pair can stand in another account's name, and deletion is not the arbiter.

    Six functions still write a profile without taking the claim, so a profile
    can carry an address whose placeholder belongs to somebody else. Deleting it must
    leave that placeholder where it is - and must still finish, because a deletion
    that refuses forever is its own defect.
    """
    _invite(table, email="shared@example.ch")
    claim_key = ("EMAIL#shared@example.ch#student", account_email_claim_repo.CLAIM_SK)
    table.rows[claim_key]["account_id"] = "another-account"

    user_id = _delete_account(table, "shared@example.ch")

    assert table.rows[claim_key]["account_id"] == "another-account"
    tombstone = table.rows[(f"USER#{user_id}", "PROFILE")]
    assert tombstone["status"] == "deleted" and "email" not in tombstone


def test_释放占位行的条件不接受别人的账号(table: FakeAccountTable) -> None:
    """The ownership clause is the whole guard; without it any release takes any pair."""
    _invite(table, email="owned@example.ch")
    claim_key = ("EMAIL#owned@example.ch#student", account_email_claim_repo.CLAIM_SK)
    owner = str(table.rows[claim_key]["account_id"])

    stranger = account_email_claim_repo.release_operation(
        email="owned@example.ch", role="student", account_id="not-the-owner"
    )
    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        account_deletion_repo.transact([stranger], table=table)
    assert claim_key in table.rows

    account_deletion_repo.transact(
        [
            account_email_claim_repo.release_operation(
                email="owned@example.ch", role="student", account_id=owner
            )
        ],
        table=table,
    )
    assert claim_key not in table.rows


# Written out by hand from a sweep of the services, so a path that quietly starts
# opening accounts cannot join the list by being added to it.
PROFILE_WRITERS_WITHOUT_A_CLAIM = {
    ("privileged_identity_service.py", "change_admin_status"),
    ("privileged_identity_service.py", "_reconcile_admin"),
    ("privileged_identity_service.py", "_restore_admin"),
    ("public_identity_service.py", "start_or_resume_public_registration"),
    ("public_identity_service.py", "_resume_public_registration"),
}


def test_还有哪些路径在不取占位行的情况下建号() -> None:
    """`put_user` writes under attribute_not_exists, so every caller opens an account.

    Only the provisioning path takes the claim; these five open a profile carrying an
    address without one, and for those addresses uniqueness is still a read of an
    eventually consistent index. Teacher activation was the sixth and is gone from the
    list: card 010 moved its opening onto `open_account`, so it takes the claim like
    every other role. What this must not allow is a new one appearing unnoticed.
    """
    services = SERVICE_PATH.parent
    found: set[tuple[str, str]] = set()
    claimed: set[tuple[str, str]] = set()
    for path in sorted(services.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for call in ast.walk(node):
                if not (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                ):
                    continue
                if call.func.attr == "put_user":
                    found.add((path.name, node.name))
                elif call.func.attr == "put_user_with_email_claim":
                    claimed.add((path.name, node.name))

    assert found == PROFILE_WRITERS_WITHOUT_A_CLAIM
    assert claimed == {("account_provisioning_service.py", "_create_account_row")}


def test_销户分支自己跑到底才算把地址还回去(table: FakeAccountTable) -> None:
    """The other tests here call the repository; production calls the branch.

    That gap is how A-1 got in: card 009 added the claim, and nothing on the
    deletion side was asked about it. Putting a `raise` on the branch's profile
    arm and running the whole suite was green, so this drives the branch itself
    -- and requires it to reach `complete`, because a release that refuses turns
    into a retry that never ends rather than into a failure anyone would see.
    """
    _invite(table, email="branch@example.ch")
    profile = _profile_for(table, "branch@example.ch")
    user_id = str(profile["user_id"])
    fence = table.rows[(f"USER#{user_id}", "ACCOUNT_FENCE")]
    fence["status"] = "deletion_pending"
    fence["generation"] = 1

    command = {"user_id": user_id, "generation": 1}
    previous: dict[str, Any] = {}
    statuses: list[str] = []
    for _ in range(12):
        result = account_deletion_service._account_profile_branch(
            command=command, previous=previous
        )
        statuses.append(result.status)
        previous = result.persisted(_moment(60).isoformat())
        if result.status == "complete":
            break

    assert statuses[-1] == "complete", statuses
    assert table.claims() == []
    assert (
        account_email_claim_repo.get_claim(email="branch@example.ch", role="student")
        is None
    )
    assert _invite(table, email="branch@example.ch", at=_moment(120))["accountNumber"]


def test_占位行读不出来时销户必须失败而不是当成没有(table: FakeAccountTable) -> None:
    """"Cannot reach the claim" and "there is no claim" are not the same answer.

    Treating the first as the second writes the tombstone, drops the address and
    leaves the pair taken forever - the exact shape of the defect this release
    exists to close, reached by a store that was merely unavailable.
    """
    _invite(table, email="unreadable@example.ch")
    profile = _profile_for(table, "unreadable@example.ch")
    user_id = str(profile["user_id"])
    fence = table.rows[(f"USER#{user_id}", "ACCOUNT_FENCE")]
    fence["status"] = "deletion_pending"
    fence["generation"] = 1

    real_get_item = table.get_item

    def refusing_get_item(*, Key: dict[str, str], ConsistentRead: bool = False):  # noqa: N803
        if Key["SK"] == account_email_claim_repo.CLAIM_SK:
            return "not a mapping at all"
        return real_get_item(Key=Key, ConsistentRead=ConsistentRead)

    table.get_item = refusing_get_item  # type: ignore[method-assign]

    with pytest.raises(ValueError):
        account_deletion_repo.replace_with_deletion_tombstone(
            profile,
            user_id=user_id,
            generation=1,
            now_iso=_moment(60).isoformat(),
        )

    table.get_item = real_get_item  # type: ignore[method-assign]
    assert table.rows[(f"USER#{user_id}", "PROFILE")].get("email") == "unreadable@example.ch"
    assert [str(row["PK"]) for row in table.claims()] == [
        "EMAIL#unreadable@example.ch#student"
    ]


def test_占位行易主时半开账号仍然会被停放(table: FakeAccountTable) -> None:
    """Card 009's A-1, in the other place that gives an address back.

    The release travels in the same commit as the parking, so a claim standing in
    another account's name would cancel both -- and the caller swallows that, leaving
    a `provisioning` row still holding the address with nobody raising anything.
    """
    _invite(table, email="stranded@example.ch")
    profile = _profile_for(table, "stranded@example.ch")
    user_id = str(profile["user_id"])
    claim_key = ("EMAIL#stranded@example.ch#student", account_email_claim_repo.CLAIM_SK)
    table.rows[claim_key]["account_id"] = "another-account"

    account_provisioning_service._release_failed_account(
        account_id=user_id, now=_moment(60)
    )

    parked = table.rows[(f"USER#{user_id}", "PROFILE")]
    assert parked["account_status"] == account_provisioning_service.FAILED_ACCOUNT_STATUS
    assert "@" not in str(parked["email"])
    assert table.rows[claim_key]["account_id"] == "another-account"


def test_销户入口认得表里存回来的代次(table: FakeAccountTable) -> None:
    """The fence generation is read back from the table, so it is not an `int`.

    A guard that insists on one refuses every real account: `DELETE /auth/me` is
    self-service, and the refusal reads as "account is not deletable".
    """
    _invite(table, email="deletable@example.ch")
    user_id = str(_profile_for(table, "deletable@example.ch")["user_id"])

    fence, command = account_deletion_repo.begin_account_deletion(
        user_id=user_id,
        command={"command_id": "command-1", "fingerprint": "fingerprint-1"},
        now_iso=_moment(60).isoformat(),
    )

    assert int(fence["generation"]) >= 1
    assert command["command_id"] == "command-1"
    assert int(command["generation"]) == int(fence["generation"])


def test_发号的末号提示能从表里读回来(table: FakeAccountTable) -> None:
    """Losing the hint is not a slow path, it is a cliff.

    The allocator probes forward from the hint under a fixed attempt budget, so a
    hint that always reads as zero turns every opening into a walk over every number
    already issued -- and stops issuing at all once that walk exceeds the budget.
    """
    account_number_repo.advance_allocation_hint(role="student", year=2026, sequence=7)

    assert account_number_repo.read_allocation_hint(role="student", year=2026) == 7


def test_占位行读不出来时仍然要把半开账号停放(
    table: FakeAccountTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parking is the half that must not depend on the claim store being reachable.

    The caller swallows whatever this raises, so a throttled read would take the
    parking with it and leave a `provisioning` row that reads like a live account
    with nobody raising anything - the state the release was added to end.
    """
    _invite(table, email="hiccup@example.ch")
    user_id = str(_profile_for(table, "hiccup@example.ch")["user_id"])

    def unreachable(**_kwargs: Any) -> None:
        raise ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException"}}, "GetItem"
        )

    monkeypatch.setattr(account_email_claim_repo, "get_claim", unreachable)

    account_provisioning_service._release_failed_account(
        account_id=user_id, now=_moment(60)
    )

    parked = table.rows[(f"USER#{user_id}", "PROFILE")]
    assert parked["account_status"] == account_provisioning_service.FAILED_ACCOUNT_STATUS
    assert "@" not in str(parked["email"])
