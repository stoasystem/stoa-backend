"""#289: one status vocabulary, one way to move between statuses, guards in the commit.

Every pair of statuses is tried with every trigger, against the shared table double,
so the table in `account_lifecycle.TRANSITIONS` is the whole of what can happen and
nothing outside it does.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import product
from typing import Any

import pytest
from fakes.dynamodb import FakeTable

from stoa.db.repositories import account_deletion_repo, security_audit_repo, user_repo
from stoa.rule_violation import RuleViolation
from stoa.security.identity import AccountStatus
from stoa.services import account_lifecycle, privileged_identity_service
from stoa.services.account_errors import AccountErrorCode
from stoa.services.account_lifecycle import LifecycleActor, Trigger

NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
TARGET = "student-1"


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    fake = FakeTable()
    for module in (account_deletion_repo, security_audit_repo, user_repo):
        monkeypatch.setattr(module, "get_table", lambda fake=fake: fake)
    return fake


def _seed(
    table: FakeTable,
    user_id: str,
    status: AccountStatus | str | None,
    *,
    role: str = "student",
    version: int = 3,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": role,
        "email": f"{user_id}@stoa.test",
        "version": version,
    }
    if status is not None:
        row["account_status"] = str(status)
    table.seed(row)
    table.seed_active_account(user_id)
    return profile(table, user_id)


def profile(table: FakeTable, user_id: str) -> dict[str, Any]:
    return dict(table.rows[(f"USER#{user_id}", "PROFILE")])


def audit_rows(table: FakeTable, user_id: str, event_type: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for key, row in table.rows.items()
        if key[0] == f"SECURITY_AUDIT#{user_id}" and row.get("event_type") == event_type
    ]


def _actor(trigger: Trigger) -> LifecycleActor:
    if trigger is Trigger.SYSTEM:
        return LifecycleActor.system()
    return LifecycleActor(trigger, user_id="actor-1", role="admin")


def _refusal(exc_info: pytest.ExceptionInfo[RuleViolation]) -> str:
    return str(exc_info.value.code)


MOVES = [
    (origin, target, trigger)
    for origin, target in product(AccountStatus, AccountStatus)
    if origin is not target
    for trigger in Trigger
]


# ---------------------------------------------------------------------------
# The table: every status x every status x every trigger
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("origin", "target", "trigger"), MOVES)
def test_每个状态对每个触发者_表里有的才能转(
    table: FakeTable, origin: AccountStatus, target: AccountStatus, trigger: Trigger
) -> None:
    before = _seed(table, TARGET, origin)

    if (origin, target) in account_lifecycle.TRANSITIONS and trigger in (
        account_lifecycle.TRANSITIONS[(origin, target)]
    ):
        account_lifecycle.transition(before, origin, target, _actor(trigger), "ticket", now=NOW)
        after = profile(table, TARGET)
        assert after["account_status"] == target.value
        assert after["version"] == before["version"] + 1
        assert ("activated_at" in after) is (target is AccountStatus.ACTIVE)
        [event] = audit_rows(table, TARGET, "account_status_changed")
        assert event["evidence_reference"] == f"account_status:{origin.value}->{target.value}"
        assert event["action"] == f"account_status_transition:{trigger.value}"
        return

    with pytest.raises(RuleViolation) as exc_info:
        account_lifecycle.transition(before, origin, target, _actor(trigger), "ticket", now=NOW)
    assert _refusal(exc_info) == AccountErrorCode.ACCOUNT_STATUS_TRANSITION_INVALID
    assert profile(table, TARGET) == before
    assert audit_rows(table, TARGET, "account_status_changed") == []


def test_表里只有词表里的状态与触发者() -> None:
    for (origin, target), triggers in account_lifecycle.TRANSITIONS.items():
        assert isinstance(origin, AccountStatus) and isinstance(target, AccountStatus)
        assert origin is not target
        assert triggers and all(isinstance(trigger, Trigger) for trigger in triggers)


def test_归档与建号失败是终点() -> None:
    for terminal in (AccountStatus.ARCHIVED, AccountStatus.PROVISIONING_FAILED):
        assert not [pair for pair in account_lifecycle.TRANSITIONS if pair[0] is terminal]


@pytest.mark.parametrize("status", list(AccountStatus))
def test_转到原状态是unchanged(table: FakeTable, status: AccountStatus) -> None:
    before = _seed(table, TARGET, status)

    with pytest.raises(RuleViolation) as exc_info:
        account_lifecycle.transition(before, status, status, _actor(Trigger.ADMIN))

    assert _refusal(exc_info) == AccountErrorCode.ACCOUNT_STATUS_UNCHANGED


# ---------------------------------------------------------------------------
# The strict expectation
# ---------------------------------------------------------------------------


def test_期望状态与行不符时拒绝且不写(table: FakeTable) -> None:
    before = _seed(table, TARGET, AccountStatus.SUSPENDED)

    with pytest.raises(RuleViolation) as exc_info:
        account_lifecycle.transition(
            before, AccountStatus.ACTIVE, AccountStatus.ARCHIVED, _actor(Trigger.ADMIN)
        )

    assert _refusal(exc_info) == AccountErrorCode.ACCOUNT_STATUS_UNEXPECTED
    assert profile(table, TARGET) == before


@pytest.mark.parametrize("stored", [None, "", "disabled", "deleted"])
def test_缺状态或词表外的旧行不被当作任何状态(table: FakeTable, stored: str | None) -> None:
    before = _seed(table, TARGET, stored)

    assert account_lifecycle.status_of(before) is None
    with pytest.raises(RuleViolation) as exc_info:
        account_lifecycle.transition(
            before, AccountStatus.ACTIVE, AccountStatus.SUSPENDED, _actor(Trigger.ADMIN)
        )
    assert _refusal(exc_info) == AccountErrorCode.ACCOUNT_STATUS_UNEXPECTED


def test_读到之后行被别人改过_提交被条件拒绝(table: FakeTable) -> None:
    stale = _seed(table, TARGET, AccountStatus.ACTIVE)
    account_lifecycle.transition(
        stale, AccountStatus.ACTIVE, AccountStatus.SUSPENDED, _actor(Trigger.ADMIN)
    )
    current = profile(table, TARGET)

    # Same status the caller expects, older version: still refused by the commit.
    table.rows[(f"USER#{TARGET}", "PROFILE")]["account_status"] = "active"
    with pytest.raises(RuleViolation) as exc_info:
        account_lifecycle.transition(
            stale, AccountStatus.ACTIVE, AccountStatus.ARCHIVED, _actor(Trigger.ADMIN)
        )

    assert _refusal(exc_info) == AccountErrorCode.ACCOUNT_STATUS_TRANSITION_CONFLICT
    assert profile(table, TARGET)["version"] == current["version"]


def test_状态在提交前被改掉_版本对也拒绝(table: FakeTable) -> None:
    """The status condition is its own guard, not implied by the version."""
    before = _seed(table, TARGET, AccountStatus.ACTIVE)
    table.rows[(f"USER#{TARGET}", "PROFILE")]["account_status"] = "suspended"

    with pytest.raises(RuleViolation) as exc_info:
        account_lifecycle.transition(
            before, AccountStatus.ACTIVE, AccountStatus.ARCHIVED, _actor(Trigger.ADMIN)
        )

    assert _refusal(exc_info) == AccountErrorCode.ACCOUNT_STATUS_TRANSITION_CONFLICT
    assert profile(table, TARGET)["account_status"] == "suspended"


def test_账号围栏不是active时不写(table: FakeTable) -> None:
    before = _seed(table, TARGET, AccountStatus.ACTIVE)
    table.rows[(f"USER#{TARGET}", "ACCOUNT_FENCE")]["status"] = "deletion_pending"

    with pytest.raises(RuleViolation) as exc_info:
        account_lifecycle.transition(
            before, AccountStatus.ACTIVE, AccountStatus.SUSPENDED, _actor(Trigger.ADMIN)
        )

    assert _refusal(exc_info) == AccountErrorCode.ACCOUNT_STATUS_TRANSITION_CONFLICT
    assert profile(table, TARGET) == before
    assert audit_rows(table, TARGET, "account_status_changed") == []


# ---------------------------------------------------------------------------
# activated_at, and the audit row
# ---------------------------------------------------------------------------


def test_activated_at只在转到active时写(table: FakeTable) -> None:
    before = _seed(table, TARGET, AccountStatus.INVITED)
    account_lifecycle.transition(
        before,
        AccountStatus.INVITED,
        AccountStatus.ACTIVE,
        LifecycleActor(Trigger.INVITATION_CLAIM, user_id=TARGET, role="student"),
        now=NOW,
    )
    assert profile(table, TARGET)["activated_at"] == NOW.isoformat()

    later = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
    account_lifecycle.transition(
        profile(table, TARGET),
        AccountStatus.ACTIVE,
        AccountStatus.SUSPENDED,
        _actor(Trigger.ADMIN),
        now=later,
    )
    after = profile(table, TARGET)
    assert after["activated_at"] == NOW.isoformat()
    assert after["updated_at"] == later.isoformat()


def test_每次转移恰好一条审计行_内容正确(table: FakeTable) -> None:
    before = _seed(table, TARGET, AccountStatus.ACTIVE)

    account_lifecycle.transition(
        before,
        AccountStatus.ACTIVE,
        AccountStatus.SUSPENDED,
        LifecycleActor(Trigger.ADMIN, user_id="admin-7", role="admin"),
        "abuse report",
        now=NOW,
    )

    [event] = audit_rows(table, TARGET, "account_status_changed")
    assert event["actor_id"] == "admin-7"
    assert event["actor_role"] == "admin"
    assert event["target_id"] == TARGET
    assert event["target_type"] == "account"
    assert event["reason_code"] == "abuse report"
    assert event["evidence_reference"] == "account_status:active->suspended"
    assert event["created_at"] == NOW.isoformat()


def test_没有操作人时审计记系统操作人(table: FakeTable) -> None:
    before = _seed(table, TARGET, AccountStatus.INVITED)

    account_lifecycle.transition(
        before, AccountStatus.INVITED, AccountStatus.PROVISIONING_FAILED, LifecycleActor.system()
    )

    [event] = audit_rows(table, TARGET, "account_status_changed")
    assert event["actor_id"] == account_lifecycle.SYSTEM_ACTOR_ID
    assert event["actor_role"] == account_lifecycle.SYSTEM_ACTOR_ID
    assert LifecycleActor(Trigger.ADMIN, user_id="  ").user_id == account_lifecycle.SYSTEM_ACTOR_ID


def test_同一次提交里的附加字段与附加操作(table: FakeTable) -> None:
    before = _seed(table, TARGET, AccountStatus.INVITED)
    marker = {"PK": "MARKER#1", "SK": "MARKER"}

    account_lifecycle.transition(
        before,
        AccountStatus.INVITED,
        AccountStatus.PROVISIONING_FAILED,
        LifecycleActor.system(),
        fields={"email": "provisioning_failed:student-1"},
        also=[{"Put": {"Item": marker}}],
    )

    assert profile(table, TARGET)["email"] == "provisioning_failed:student-1"
    assert ("MARKER#1", "MARKER") in table.rows
    other = _seed(table, "student-2", AccountStatus.ACTIVE)
    with pytest.raises(ValueError):
        account_lifecycle.transition(
            other,
            AccountStatus.ACTIVE,
            AccountStatus.SUSPENDED,
            _actor(Trigger.ADMIN),
            fields={"activated_at": "never"},
        )


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target", [AccountStatus.SUSPENDED, AccountStatus.ARCHIVED])
def test_不能停用自己_拒绝也留痕(table: FakeTable, target: AccountStatus) -> None:
    _seed(table, "admin-2", AccountStatus.ACTIVE, role="admin")
    before = _seed(table, "admin-1", AccountStatus.ACTIVE, role="admin")

    with pytest.raises(RuleViolation) as exc_info:
        account_lifecycle.transition(
            before,
            AccountStatus.ACTIVE,
            target,
            LifecycleActor(Trigger.ADMIN, user_id="admin-1", role="admin"),
        )

    assert _refusal(exc_info) == AccountErrorCode.ACCOUNT_SELF_DEACTIVATION_FORBIDDEN
    assert profile(table, "admin-1")["account_status"] == "active"
    [denied] = audit_rows(table, "admin-1", "account_status_change_denied")
    assert denied["reason_code"] == "account_self_deactivation_forbidden"


def test_停不掉最后一个active管理员_拒绝也留痕(table: FakeTable) -> None:
    _seed(table, "admin-1", AccountStatus.SUSPENDED, role="admin")
    before = _seed(table, "admin-2", AccountStatus.ACTIVE, role="admin")

    with pytest.raises(RuleViolation) as exc_info:
        account_lifecycle.transition(
            before,
            AccountStatus.ACTIVE,
            AccountStatus.SUSPENDED,
            LifecycleActor(Trigger.ADMIN, user_id="admin-1", role="admin"),
        )

    assert _refusal(exc_info) == AccountErrorCode.ACCOUNT_LAST_ACTIVE_ADMIN
    assert profile(table, "admin-2")["account_status"] == "active"
    [denied] = audit_rows(table, "admin-2", "account_status_change_denied")
    assert denied["actor_id"] == "admin-1"
    assert denied["target_id"] == "admin-2"
    assert denied["reason_code"] == "account_last_active_admin"
    assert audit_rows(table, "admin-2", "account_status_changed") == []


def test_另有active管理员时可以停用_提交里带着对它的条件(table: FakeTable) -> None:
    _seed(table, "admin-1", AccountStatus.ACTIVE, role="admin")
    before = _seed(table, "admin-2", AccountStatus.ACTIVE, role="admin")

    account_lifecycle.transition(
        before,
        AccountStatus.ACTIVE,
        AccountStatus.SUSPENDED,
        LifecycleActor(Trigger.PRIVILEGED_IDENTITY, user_id="admin-1", role="admin"),
    )

    assert profile(table, "admin-2")["account_status"] == "suspended"
    [(_, request)] = [
        call for call in table.requests if call[0] == "transact_write_items"
    ]
    checks = [
        operation["ConditionCheck"]["Key"]
        for operation in request["operations"]
        if "ConditionCheck" in operation
    ]
    assert {"PK": "USER#admin-1", "SK": "PROFILE"} in checks


def test_两个管理员同时互相停用_必有一笔失败(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both censuses run before either commit, so both see the other one active.

    Without the condition on the survivor's profile, both commits land and nobody is
    left who can undo it.
    """
    first = _seed(table, "admin-1", AccountStatus.ACTIVE, role="admin")
    second = _seed(table, "admin-2", AccountStatus.ACTIVE, role="admin")
    stale_census = {"admin-1": "admin-2", "admin-2": "admin-1"}
    monkeypatch.setattr(user_repo, "find_other_active_admin", stale_census.get)

    outcomes: list[str] = []
    for target, actor in ((second, "admin-1"), (first, "admin-2")):
        try:
            account_lifecycle.transition(
                target,
                AccountStatus.ACTIVE,
                AccountStatus.SUSPENDED,
                LifecycleActor(Trigger.ADMIN, user_id=actor, role="admin"),
            )
            outcomes.append("ok")
        except RuleViolation as exc:
            outcomes.append(str(exc.code))

    assert outcomes == ["ok", AccountErrorCode.ACCOUNT_STATUS_TRANSITION_CONFLICT]
    statuses = {profile(table, user)["account_status"] for user in ("admin-1", "admin-2")}
    assert statuses == {"active", "suspended"}


def test_管理员守卫不牵连普通账号也不牵连转到active(table: FakeTable) -> None:
    before = _seed(table, TARGET, AccountStatus.ACTIVE)
    account_lifecycle.transition(
        before, AccountStatus.ACTIVE, AccountStatus.SUSPENDED, _actor(Trigger.ADMIN)
    )
    admin = _seed(table, "admin-9", AccountStatus.SUSPENDED, role="admin")
    account_lifecycle.transition(
        admin, AccountStatus.SUSPENDED, AccountStatus.ACTIVE, _actor(Trigger.ADMIN)
    )
    assert profile(table, "admin-9")["account_status"] == "active"


# ---------------------------------------------------------------------------
# The privileged identity lifecycle runs through it, fence and audit included
# ---------------------------------------------------------------------------


class _Provider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def admin_remove_user_from_group(self, **_kwargs: Any) -> None:
        self.calls.append("remove")

    def admin_user_global_sign_out(self, **_kwargs: Any) -> None:
        self.calls.append("signout")

    def admin_add_user_to_group(self, **_kwargs: Any) -> None:
        self.calls.append("add")


def _manager() -> dict[str, Any]:
    return {
        "user_id": "admin-1",
        "role": "admin",
        "account_status": "active",
        "capabilities": {"admin_identity_manager": "granted"},
    }


@pytest.fixture
def commands(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}
    repo = privileged_identity_service.privileged_identity_repo

    def create_command(item: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        if item["command_id"] in store:
            return dict(store[item["command_id"]]), False
        store[item["command_id"]] = dict(item)
        return dict(item), True

    def update_command(command_id: str, **updates: Any) -> dict[str, Any]:
        command = store[command_id]
        command.update(
            status=updates["status"],
            version=updates["expected_version"] + 1,
            evidence_reference=updates["evidence_reference"],
        )
        return dict(command)

    monkeypatch.setattr(repo, "create_command", create_command)
    monkeypatch.setattr(repo, "update_command", update_command)
    return store


@pytest.mark.parametrize("operation,status", [("suspend", "suspended"), ("revoke", "revoked")])
def test_特权身份停用走生命周期_有围栏有审计(
    table: FakeTable, commands: dict[str, Any], operation: str, status: str
) -> None:
    _seed(table, "admin-1", AccountStatus.ACTIVE, role="admin")
    _seed(table, "admin-2", AccountStatus.ACTIVE, role="admin")

    result = privileged_identity_service.change_admin_status(
        actor=_manager(),
        command_id="command-1",
        target_id="admin-2",
        operation=operation,
        reason="approved investigation",
        provider=_Provider(),
        provider_username="admin-2",
    )

    assert result["status"] == status
    assert profile(table, "admin-2")["account_status"] == status
    [event] = audit_rows(table, "admin-2", "account_status_changed")
    assert event["action"] == "account_status_transition:privileged_identity"
    assert event["actor_id"] == "admin-1"


def test_特权身份恢复走生命周期_重放不报同状态(
    table: FakeTable, commands: dict[str, Any]
) -> None:
    _seed(table, "admin-1", AccountStatus.ACTIVE, role="admin")
    _seed(table, "admin-2", AccountStatus.REVOKED, role="admin")
    provider = _Provider()

    restored = privileged_identity_service.change_admin_status(
        actor=_manager(),
        command_id="restore-1",
        target_id="admin-2",
        operation="restore",
        reason="cleared",
        provider=provider,
        provider_username="admin-2",
    )

    assert restored["status"] == "active"
    after = profile(table, "admin-2")
    assert after["account_status"] == "active"
    assert "activated_at" in after
    assert provider.calls == ["add"]


def test_特权身份不能恢复已归档的管理员(table: FakeTable, commands: dict[str, Any]) -> None:
    _seed(table, "admin-1", AccountStatus.ACTIVE, role="admin")
    _seed(table, "admin-2", AccountStatus.ARCHIVED, role="admin")
    provider = _Provider()

    with pytest.raises(RuleViolation) as exc_info:
        privileged_identity_service.change_admin_status(
            actor=_manager(),
            command_id="restore-2",
            target_id="admin-2",
            operation="restore",
            reason="cleared",
            provider=provider,
            provider_username="admin-2",
        )

    assert _refusal(exc_info) == AccountErrorCode.IDENTITY_RESTORE_NOT_ALLOWED
    assert provider.calls == []


def test_特权身份停不掉最后一个管理员(table: FakeTable, commands: dict[str, Any]) -> None:
    _seed(table, "admin-1", AccountStatus.SUSPENDED, role="admin")
    _seed(table, "admin-2", AccountStatus.ACTIVE, role="admin")
    provider = _Provider()

    with pytest.raises(RuleViolation) as exc_info:
        privileged_identity_service.change_admin_status(
            actor=_manager(),
            command_id="command-2",
            target_id="admin-2",
            operation="suspend",
            reason="lockout",
            provider=provider,
            provider_username="admin-2",
        )

    assert _refusal(exc_info) == AccountErrorCode.ACCOUNT_LAST_ACTIVE_ADMIN
    assert provider.calls == []
