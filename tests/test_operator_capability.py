"""#48: the offline operator path for capability grants and the audit baseline.

The product refuses an administrator's grant to itself, so a lone administrator
gets a new capability from here, in the AWS trust domain, and every such grant
is recorded. The baseline records the grants an administrator already holds,
because the ones issued before per-grant audit rows existed have none.
"""

from __future__ import annotations

from argparse import Namespace
from hashlib import sha256
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from stoa.db.repositories import capability_repo


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "operator_capability.py"
    spec = importlib.util.spec_from_file_location("operator_capability", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()

ADMIN = "admin-1"
NOW = "2026-09-30T12:00:00+00:00"
ALLOWANCE = capability_repo.TEACHER_SUPPORT_ALLOWANCE_MANAGER


class FakeTable:
    """Profiles to read and audit rows to append, refusing a second row at one key."""

    def __init__(self, profiles: dict[str, dict[str, Any]] | None = None) -> None:
        self.profiles = (
            profiles
            if profiles is not None
            else {ADMIN: {"user_id": ADMIN, "role": "admin", "account_status": "active"}}
        )
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.puts: list[dict[str, Any]] = []

    def get_item(self, Key: dict[str, str]) -> dict[str, Any]:  # noqa: N803 - boto3 shape
        if Key["SK"] == "PROFILE":
            profile = self.profiles.get(Key["PK"].removeprefix("USER#"))
            return {"Item": dict(profile)} if profile else {}
        row = self.rows.get((Key["PK"], Key["SK"]))
        return {"Item": dict(row)} if row else {}

    def put_item(self, Item: dict[str, Any], ConditionExpression: str) -> None:  # noqa: N803
        assert ConditionExpression == "attribute_not_exists(PK) AND attribute_not_exists(SK)"
        key = (Item["PK"], Item["SK"])
        assert key not in self.rows, "conditional put refused"
        self.rows[key] = dict(Item)
        self.puts.append(dict(Item))


def _grant_row(
    capability: str,
    *,
    scope: str = "global",
    version: int = 1,
    status: str = "active",
    grant_id: str | None = None,
    grantor_id: str = "admin-0",
) -> dict[str, Any]:
    return {
        "capability": capability,
        "scope": scope,
        "status": status,
        "version": version,
        "grant_id": grant_id or f"grant-{capability}",
        "grantor_id": grantor_id,
    }


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"current": [], "grants": [], "generation": 0}
    monkeypatch.setattr(
        script.capability_repo,
        "get_current_grants",
        lambda user_id, table_factory=None: [dict(item) for item in state["current"]],
    )
    monkeypatch.setattr(
        script.capability_repo,
        "current_lineage_generation",
        lambda user_id, capability, scope, table_factory=None: state["generation"],
    )

    def grant_capability(**kwargs: Any) -> dict[str, Any]:
        # Refuses what the store refuses: the bootstrap's first run passed the
        # fence generation, a different number the store rejects.
        if kwargs["expected_generation"] != state["generation"]:
            raise capability_repo.CapabilityVersionConflict("stale expected capability generation")
        state["grants"].append(kwargs)
        return {
            **_grant_row(
                kwargs["capability"],
                scope=kwargs["scope"],
                grant_id=kwargs["grant_id"],
                grantor_id=kwargs["grantor_id"],
            ),
            "command_id": kwargs["command_id"],
            "effective_at": kwargs["effective_at"],
        }

    monkeypatch.setattr(script.capability_repo, "grant_capability", grant_capability)
    return state


def _grant(
    table: FakeTable,
    capability: str = ALLOWANCE,
    *,
    dry_run: bool = False,
    scope: str = "global",
) -> str:
    return script.grant(
        table,
        user_id=ADMIN,
        capability=capability,
        scope=scope,
        incident_reason="card 028 follow-up",
        dry_run=dry_run,
        now=lambda: NOW,
    )


def test_an_offline_grant_issues_the_capability_and_records_it(repo: dict[str, Any]) -> None:
    table = FakeTable()
    repo["generation"] = 3
    assert _grant(table) == "issued"
    [issued] = repo["grants"]
    assert issued["user_id"] == ADMIN
    assert issued["capability"] == ALLOWANCE
    assert issued["scope"] == "global"
    assert issued["grantor_id"] == "operator:operator_capability"
    assert issued["reason"] == "card 028 follow-up"
    assert issued["expected_generation"] == 3
    [event] = table.puts
    assert event["PK"] == f"SECURITY_AUDIT#{ADMIN}"
    assert event["SK"] == f"EVENT#event_operator_grant_{issued['grant_id']}"
    assert event["event_type"] == "capability_granted"
    assert event["actor_id"] == "operator:operator_capability"
    assert event["actor_role"] == "operator"
    assert event["target_id"] == ADMIN
    assert event["target_type"] == "capability_grant"
    assert event["action"] == "grant_capability"
    assert event["reason_code"] == "operator_capability_grant"
    assert event["evidence_reference"] == f"capability-grant:{issued['grant_id']}"
    assert event["command_id"] == issued["command_id"]
    assert event["created_at"] == NOW
    # The free-text reason stays on the grant; the audit row is a safe projection.
    assert "card 028" not in repr(event)


def test_no_operator_identity_is_recorded_that_a_guess_could_reverse(
    repo: dict[str, Any],
) -> None:
    table = FakeTable()
    _grant(table)
    [event] = table.puts
    assert "actor_fingerprint" not in event


def test_a_capability_already_held_is_left_alone(repo: dict[str, Any]) -> None:
    table = FakeTable()
    repo["current"] = [_grant_row(ALLOWANCE)]
    assert _grant(table) == "present"
    assert repo["grants"] == []
    assert table.puts == []


def test_a_run_cut_short_after_the_grant_writes_the_missing_row_on_rerun(
    repo: dict[str, Any],
) -> None:
    table = FakeTable()
    repo["current"] = [
        {
            **_grant_row(
                ALLOWANCE, grant_id="grant-x", grantor_id="operator:operator_capability"
            ),
            "effective_at": "2026-09-30T09:00:00+00:00",
        }
    ]
    assert _grant(table) == "present_audit_written"
    [event] = table.puts
    assert event["SK"] == "EVENT#event_operator_grant_grant-x"
    assert event["evidence_reference"] == "capability-grant:grant-x"
    assert event["created_at"] == "2026-09-30T09:00:00+00:00"
    assert repo["grants"] == []
    # And the next rerun finds the row and writes nothing more.
    assert _grant(table) == "present"
    assert len(table.puts) == 1


@pytest.mark.parametrize("grantor_id", ["admin-0", "bootstrap:first_admin", ""])
def test_a_grant_this_script_did_not_issue_gets_no_row_from_it(
    repo: dict[str, Any], grantor_id: str
) -> None:
    table = FakeTable()
    repo["current"] = [_grant_row(ALLOWANCE, grant_id="grant-x", grantor_id=grantor_id)]
    assert _grant(table) == "present"
    assert table.puts == []


def test_a_dry_run_rerun_reports_the_missing_row_without_writing_it(
    repo: dict[str, Any],
) -> None:
    table = FakeTable()
    repo["current"] = [
        _grant_row(ALLOWANCE, grant_id="grant-x", grantor_id="operator:operator_capability")
    ]
    assert _grant(table, dry_run=True) == "present_audit_pending"
    assert table.puts == []


def test_a_revoked_grant_does_not_count_as_held(repo: dict[str, Any]) -> None:
    table = FakeTable()
    repo["current"] = [_grant_row(ALLOWANCE, status="revoked")]
    assert _grant(table) == "issued"


def test_the_same_capability_in_another_scope_is_not_held(repo: dict[str, Any]) -> None:
    table = FakeTable()
    repo["current"] = [_grant_row(ALLOWANCE, scope="student:s-1")]
    assert _grant(table) == "issued"


def test_a_dry_run_grant_writes_nothing(repo: dict[str, Any]) -> None:
    table = FakeTable()
    assert _grant(table, dry_run=True) == "pending"
    assert repo["grants"] == []
    assert table.puts == []


def test_an_unregistered_capability_is_refused(repo: dict[str, Any]) -> None:
    with pytest.raises(script.OperatorCapabilityError, match="not a registered capability"):
        _grant(FakeTable(), "root_everything")
    assert repo["grants"] == []


@pytest.mark.parametrize(
    "profile",
    [
        None,
        {"user_id": ADMIN, "role": "teacher", "account_status": "active"},
        {"user_id": ADMIN, "role": "admin", "account_status": "suspended"},
    ],
)
def test_only_an_active_administrator_can_be_granted(
    repo: dict[str, Any], profile: dict[str, Any] | None
) -> None:
    table = FakeTable({} if profile is None else {ADMIN: profile})
    with pytest.raises(script.OperatorCapabilityError, match="active administrator"):
        _grant(table)
    assert repo["grants"] == []
    assert table.puts == []


def test_an_empty_scope_is_refused(repo: dict[str, Any]) -> None:
    with pytest.raises(script.OperatorCapabilityError, match="scope"):
        _grant(FakeTable(), scope="  ")


def _baseline(table: FakeTable, *, dry_run: bool = False) -> tuple[str, int]:
    return script.baseline(
        table,
        user_id=ADMIN,
        dry_run=dry_run,
        now=lambda: NOW,
        snapshot_id="snap-1",
    )


def _listed(table: FakeTable) -> list[str]:
    return sorted(
        row["evidence_reference"]
        for row in table.puts
        if row["event_type"] == "capability_baseline_recorded"
    )


def test_the_baseline_records_every_active_grant_once_with_its_scope(
    repo: dict[str, Any],
) -> None:
    table = FakeTable()
    repo["current"] = [
        _grant_row(capability_repo.ADMIN_IDENTITY_MANAGER, version=2),
        _grant_row(capability_repo.STUDENT_SUPPORT_LOOKUP, scope="student:s-1"),
        _grant_row(capability_repo.PARENT_BINDING_REPAIRER, status="revoked"),
    ]
    assert _baseline(table) == ("snap-1", 2)
    assert _listed(table) == sorted(
        [
            "capability-baseline:snap-1:admin_identity_manager:global:v2:"
            "grant-admin_identity_manager",
            "capability-baseline:snap-1:student_support_lookup:student:s-1:v1:"
            "grant-student_support_lookup",
        ]
    )
    for row in table.puts:
        assert row["actor_id"] == "operator:operator_capability"
        assert row["action"] == "record_capability_baseline"
        assert row["target_id"] == ADMIN
        assert row["command_id"] == "snap-1"
        assert row["created_at"] == NOW
    assert repo["grants"] == []


def test_the_baseline_closes_with_a_count_and_a_digest_of_what_it_listed(
    repo: dict[str, Any],
) -> None:
    table = FakeTable()
    repo["current"] = [
        _grant_row(capability_repo.STUDENT_SUPPORT_LOOKUP),
        _grant_row(capability_repo.ADMIN_IDENTITY_MANAGER, version=2),
    ]
    _baseline(table)
    digest = sha256("\n".join(_listed(table)).encode()).hexdigest()
    # Written last, so a snapshot cut short has no summary.
    summary = table.puts[-1]
    assert summary["event_type"] == "capability_baseline_snapshot"
    assert summary["evidence_reference"] == f"capability-baseline:snap-1:count=2:sha256={digest}"
    assert summary["command_id"] == "snap-1"
    # The count lives in the reference; `version` keeps its meaning elsewhere.
    assert "version" not in summary


def test_an_empty_baseline_still_says_so(repo: dict[str, Any]) -> None:
    table = FakeTable()
    assert _baseline(table) == ("snap-1", 0)
    [summary] = table.puts
    assert summary["event_type"] == "capability_baseline_snapshot"
    assert ":count=0:" in summary["evidence_reference"]


def test_a_dry_run_baseline_writes_nothing(repo: dict[str, Any]) -> None:
    table = FakeTable()
    repo["current"] = [_grant_row(capability_repo.STUDENT_SUPPORT_LOOKUP)]
    assert _baseline(table, dry_run=True) == ("snap-1", 1)
    assert table.puts == []


def test_the_baseline_requires_an_active_administrator(repo: dict[str, Any]) -> None:
    with pytest.raises(script.OperatorCapabilityError, match="active administrator"):
        _baseline(FakeTable({}))


def _args(**overrides: Any) -> Namespace:
    values = {
        "command": "grant",
        "user_id": ADMIN,
        "confirm_production": True,
        "incident_reason": "card 028 follow-up",
        "capability": ALLOWANCE,
        "scope": "global",
        "dry_run": False,
        "profile": "stoa",
        "region": "eu-central-2",
        "account_id": "562923011260",
        "table_name": "stoa-main",
    }
    values.update(overrides)
    return Namespace(**values)


def test_inputs_require_the_production_guard() -> None:
    with pytest.raises(script.OperatorCapabilityError, match="--confirm-production"):
        script.validate_inputs(_args(confirm_production=False))


def test_a_grant_requires_an_incident_reason() -> None:
    with pytest.raises(script.OperatorCapabilityError, match="--incident-reason"):
        script.validate_inputs(_args(incident_reason="  "))


def test_a_baseline_needs_no_reason_it_would_not_record() -> None:
    script.validate_inputs(_args(command="baseline", incident_reason="", capability=""))


def _forbid_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no write may happen without an operator session")

    monkeypatch.setattr(script, "grant", forbidden)
    monkeypatch.setattr(script, "baseline", forbidden)


@pytest.mark.parametrize("command", ["grant", "baseline"])
def test_no_sso_operator_session_means_no_write(
    monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    def refuse(**kwargs: Any) -> Any:
        raise script.AwsOperatorIdentityError("not an SSO operator session")

    monkeypatch.setattr(script, "require_sso_operator_session", refuse)
    monkeypatch.setattr(script, "parse_args", lambda: _args(command=command))
    _forbid_writes(monkeypatch)
    assert script.main() == 1


class _Session:
    def resource(self, name: str, region_name: str) -> Any:
        class Resource:
            def Table(self, name: str) -> FakeTable:  # noqa: N802 - boto3 shape
                return FakeTable()

        return Resource()


@pytest.mark.parametrize(
    "refusal",
    [
        ValueError("expires_at is required for break-glass"),
        capability_repo.CapabilityVersionConflict("stale expected capability generation"),
    ],
)
def test_a_store_refusal_ends_the_run_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    refusal: Exception,
) -> None:
    monkeypatch.setattr(script, "require_sso_operator_session", lambda **kwargs: _Session())
    monkeypatch.setattr(script, "parse_args", lambda: _args())

    def grant(*args: Any, **kwargs: Any) -> str:
        raise refusal

    monkeypatch.setattr(script, "grant", grant)
    assert script.main() == 1
    assert "the grant store refused" in capsys.readouterr().err
