"""T-472-05 reconciliation contracts: automation tightens privilege only."""

import pytest
from botocore.exceptions import ClientError

from stoa.security.reconciliation import (
    GrantSnapshot,
    IdentitySnapshot,
    MemoryCheckpointStore,
    ReconciliationAction,
    reconcile_inventory,
)


class CapabilityTable:
    """Atomic in-memory table for the capability repository contract."""

    def __init__(self, items=()):
        self.items = {(item["PK"], item["SK"]): dict(item) for item in items}
        self.transactions = 0

    def get_item(self, *, Key, **_kwargs):
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": dict(item)} if item else {}

    def query(self, **_kwargs):
        return {"Items": [dict(item) for item in self.items.values()]}

    def apply_capability_transaction(self, operations):
        pending = dict(self.items)
        for operation in operations:
            item = operation["item"]
            key = (item["PK"], item["SK"])
            current = pending.get(key)
            if operation["condition"] == "absent" and current is not None:
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException"}}, "TransactWriteItems"
                )
            if operation["condition"] != "absent" and (
                current is None
                or any(current.get(name) != value for name, value in operation["expected"].items())
            ):
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException"}}, "TransactWriteItems"
                )
            pending[key] = dict(item)
        self.items = pending
        self.transactions += 1


def _legacy_grant(*, grant_id="legacy-1", status="active", version=1):
    from stoa.db.repositories import capability_repo

    return {
        **capability_repo._grant_key(
            "admin-1", capability_repo.ADMIN_IDENTITY_MANAGER, "global", grant_id
        ),
        "entity_type": "capability_grant",
        "user_id": "admin-1",
        "grant_id": grant_id,
        "capability": capability_repo.ADMIN_IDENTITY_MANAGER,
        "scope": "global",
        "status": status,
        "version": version,
        "effective_at": "2026-07-15T10:00:00Z",
    }


@pytest.mark.parametrize(
    "case,permitted_automatic_action",
    [
        ("excess-group", "remove_group"),
        ("multiple-role-groups", "suspend_pending_review"),
        ("historical-tutor-role", "suspend_pending_review"),
        ("unknown-privileged-identity", "suspend_pending_review"),
        ("active-grant-revoked", "remove_grant"),
    ],
    ids=lambda value: f"T-472-05-reconciliation-{value}" if isinstance(value, str) else None,
)
def test_t472_05_reconciliation_auto_tightens_only(case, permitted_automatic_action):
    from stoa.security.reconciliation import reconcile_case

    result = reconcile_case(case, dry_run=True)
    assert permitted_automatic_action in result.actions
    assert result.added_roles == ()
    assert result.added_grants == ()


def test_t472_05_reconciliation_dry_run_is_redacted_and_apply_is_idempotent():
    from stoa.security.reconciliation import reconcile_case

    dry_run = reconcile_case("provider-canary", dry_run=True)
    first = reconcile_case("provider-canary", dry_run=False, checkpoint="batch-1")
    replay = reconcile_case("provider-canary", dry_run=False, checkpoint="batch-1")
    assert "provider-payload-canary" not in repr(dry_run)
    assert first == replay


def _snapshot(**overrides):
    values = {
        "provider_subject": "provider-secret-subject",
        "issuer": "https://issuer.example/private",
        "groups": ("admins",),
        "user_id": "user-secret-id",
        "profile_role": "admin",
        "profile_status": "active",
        "binding_count": 1,
        "approved": True,
        "grants": (),
    }
    values.update(overrides)
    return IdentitySnapshot(**values)


@pytest.mark.parametrize(
    "overrides,classification",
    [
        ({}, "exact_approved_active_match"),
        ({"user_id": None, "profile_role": None}, "unknown"),
        ({"approved": False}, "missing_approval"),
        ({"profile_status": "disabled"}, "inactive"),
        ({"binding_count": 0}, "missing_binding"),
        ({"binding_count": 2}, "duplicate_binding"),
        ({"profile_role": "teacher"}, "local_group_mismatch"),
        ({"groups": ("admins", "teachers")}, "multiple_roles"),
        ({"groups": ("tutors",), "profile_role": "tutor"}, "historical_tutor"),
        ({"grants": (GrantSnapshot("g", "cap", "global", version=0),)}, "invalid_capability_version"),
    ],
)
def test_inventory_classifies_every_privileged_authority_conflict(overrides, classification):
    report = reconcile_inventory([_snapshot(**overrides)], run_id="run-1")
    assert report.items[0].classification == classification
    if classification == "exact_approved_active_match":
        assert report.items[0].actions == ()
        assert not report.items[0].manual_approval_required
    else:
        assert all(not action.privilege_increase for action in report.items[0].actions)
        assert report.items[0].manual_approval_required


class RecordingAdapter:
    def __init__(self, *, fail_action=None):
        self.calls = []
        self.fail_action = fail_action

    def _call(self, action, action_id):
        if self.fail_action == action:
            self.fail_action = None
            raise RuntimeError("partial failure")
        self.calls.append((action, action_id))

    def suspend_local(self, user_id, *, action_id): self._call("suspend", action_id)
    def remove_group(self, provider_subject, group, *, action_id): self._call("remove_group", action_id)
    def global_sign_out(self, provider_subject, *, action_id): self._call("sign_out", action_id)
    def revoke_grant(self, user_id, grant, *, action_id): self._call("revoke_grant", action_id)
    def append_audit(self, item_id, action, *, action_id): self.calls.append(("audit", action_id))


def test_apply_requires_separate_nonproduction_authorization_and_injected_adapter():
    snapshot = _snapshot(groups=("admins", "teachers"))
    with pytest.raises(PermissionError):
        reconcile_inventory([snapshot], run_id="approved", apply=True)
    with pytest.raises(PermissionError):
        reconcile_inventory(
            [snapshot], run_id="approved", apply=True, environment="production",
            confirmation="APPLY_TIGHTENING", approved_run_id="approved", adapter=RecordingAdapter(),
        )
    with pytest.raises(PermissionError):
        reconcile_inventory(
            [snapshot], run_id="approved", apply=True, environment="sandbox",
            confirmation="APPLY_TIGHTENING", approved_run_id="different", adapter=RecordingAdapter(),
        )


def test_partial_apply_resumes_from_checkpoint_without_duplicate_mutation_or_audit():
    snapshot = _snapshot(groups=("admins", "teachers"))
    checkpoints = MemoryCheckpointStore()
    first = RecordingAdapter(fail_action="remove_group")
    with pytest.raises(RuntimeError, match="partial failure"):
        reconcile_inventory(
            [snapshot], run_id="approved", apply=True, environment="sandbox",
            confirmation="APPLY_TIGHTENING", approved_run_id="approved", adapter=first,
            checkpoints=checkpoints,
        )
    assert [action for action, _ in first.calls].count("suspend") == 1
    second = RecordingAdapter()
    reconcile_inventory(
        [snapshot], run_id="approved", apply=True, environment="sandbox",
        confirmation="APPLY_TIGHTENING", approved_run_id="approved", adapter=second,
        checkpoints=checkpoints,
    )
    assert "suspend" not in [action for action, _ in second.calls]
    third = RecordingAdapter()
    reconcile_inventory(
        [snapshot], run_id="approved", apply=True, environment="sandbox",
        confirmation="APPLY_TIGHTENING", approved_run_id="approved", adapter=third,
        checkpoints=checkpoints,
    )
    assert third.calls == []


def test_dry_run_safe_projection_contains_no_raw_identity_provider_or_group_values():
    report = reconcile_inventory(
        [_snapshot(groups=("admins", "teachers"))], run_id="dry-run"
    )
    rendered = repr(report.safe_projection())
    for secret in ("provider-secret-subject", "issuer.example", "user-secret-id", "admins", "teachers"):
        assert secret not in rendered
    assert report.added_roles == ()
    assert report.added_grants == ()


def test_privilege_increase_actions_are_never_automatic():
    for action in ("add_group", "restore_account", "grant_capability", "activate_account"):
        assert ReconciliationAction(action, "requires approval").privilege_increase


@pytest.mark.parametrize(
    "overrides",
    [
        {"approved": False},
        {"binding_count": 0},
        {"binding_count": 2},
        {"groups": ("admins", "teachers")},
        {"profile_role": "teacher"},
        {"profile_status": "disabled"},
    ],
)
def test_all_grants_are_removed_and_grant_count_is_zero_for_every_non_exact_identity(overrides):
    grants = (
        GrantSnapshot("valid-1", "admin_identity_manager", "global"),
        GrantSnapshot("invalid-1", "student_support_lookup", "global", status="revoked", version=2),
    )
    item = reconcile_inventory([_snapshot(grants=grants, **overrides)], run_id="quarantine").items[0]
    assert [action.target for action in item.actions if action.action == "remove_grant"] == [
        "valid-1", "invalid-1"
    ]
    assert item.after["grantCount"] == 0


def test_lineage_current_pointer_is_the_only_authority_and_history_cannot_revive():
    from stoa.db.repositories import capability_repo

    table = CapabilityTable()
    active = capability_repo.grant_capability(
        user_id="admin-1", command_id="command-1", grant_id="grant-1",
        capability=capability_repo.ADMIN_IDENTITY_MANAGER, scope="global",
        grantor_id="manager-1", reason="approved", effective_at="2026-07-15T10:00:00Z",
        expected_generation=0, table_factory=lambda: table,
    )
    assert active["generation"] == 1
    assert [row["grant_id"] for row in capability_repo.get_current_grants("admin-1", table_factory=lambda: table)] == ["grant-1"]

    revoked = capability_repo.revoke_capability(
        user_id="admin-1", grant_id="grant-1", capability=capability_repo.ADMIN_IDENTITY_MANAGER,
        scope="global", expected_generation=1, expected_version=1, actor_id="manager-1",
        reason="conflict", changed_at="2026-07-15T10:01:00Z", action_id="action-1",
        table_factory=lambda: table,
    )
    assert revoked["version"] == 2
    assert capability_repo.get_current_grants("admin-1", table_factory=lambda: table) == []
    assert len([row for row in table.items.values() if row.get("entity_type") == "capability_grant_revision"]) == 2

    replacement = capability_repo.grant_capability(
        user_id="admin-1", command_id="command-2", grant_id="grant-2",
        capability=capability_repo.ADMIN_IDENTITY_MANAGER, scope="global",
        grantor_id="manager-1", reason="new approval", effective_at="2026-07-15T10:02:00Z",
        expected_generation=1, table_factory=lambda: table,
    )
    assert (replacement["generation"], replacement["version"]) == (2, 1)
    assert [row["grant_id"] for row in capability_repo.get_current_grants("admin-1", table_factory=lambda: table)] == ["grant-2"]


def test_lineage_stale_revoke_cannot_touch_replacement_and_ids_cannot_be_reused():
    from stoa.db.repositories import capability_repo

    table = CapabilityTable()
    capability_repo.grant_capability(
        user_id="admin-1", command_id="command-1", grant_id="grant-1",
        capability=capability_repo.ADMIN_IDENTITY_MANAGER, scope="global", grantor_id="manager",
        reason="approved", effective_at="2026-07-15T10:00:00Z", expected_generation=0,
        table_factory=lambda: table,
    )
    capability_repo.revoke_capability(
        user_id="admin-1", grant_id="grant-1", capability=capability_repo.ADMIN_IDENTITY_MANAGER,
        scope="global", expected_generation=1, expected_version=1, actor_id="manager", reason="conflict",
        changed_at="2026-07-15T10:01:00Z", action_id="action-1", table_factory=lambda: table,
    )
    for command_id, grant_id in (("command-1", "grant-2"), ("command-2", "grant-1")):
        with pytest.raises(capability_repo.CapabilityVersionConflict):
            capability_repo.grant_capability(
                user_id="admin-1", command_id=command_id, grant_id=grant_id,
                capability=capability_repo.ADMIN_IDENTITY_MANAGER, scope="global", grantor_id="manager",
                reason="invalid reuse", effective_at="2026-07-15T10:02:00Z", expected_generation=1,
                table_factory=lambda: table,
            )


def test_legacy_migration_is_atomic_retry_safe_and_duplicates_fail_closed():
    from stoa.db.repositories import capability_repo

    table = CapabilityTable([_legacy_grant()])
    assert len(capability_repo.get_current_grants("admin-1", table_factory=lambda: table)) == 1
    revoked = capability_repo.revoke_capability(
        user_id="admin-1", grant_id="legacy-1", capability=capability_repo.ADMIN_IDENTITY_MANAGER,
        scope="global", expected_generation=1, expected_version=1, actor_id="manager",
        reason="migration quarantine", changed_at="2026-07-15T10:01:00Z", action_id="legacy-action",
        table_factory=lambda: table,
    )
    assert revoked["status"] == "revoked"
    assert capability_repo.get_current_grants("admin-1", table_factory=lambda: table) == []
    before = dict(table.items)
    capability_repo.revoke_capability(
        user_id="admin-1", grant_id="legacy-1", capability=capability_repo.ADMIN_IDENTITY_MANAGER,
        scope="global", expected_generation=1, expected_version=1, actor_id="manager",
        reason="migration quarantine", changed_at="2026-07-15T10:01:00Z", action_id="legacy-action",
        table_factory=lambda: table,
    )
    assert table.items == before

    duplicates = CapabilityTable([_legacy_grant(), _legacy_grant(grant_id="legacy-2")])
    assert capability_repo.get_current_grants("admin-1", table_factory=lambda: duplicates) == []
    with pytest.raises(capability_repo.CapabilityVersionConflict):
        capability_repo.revoke_capability(
            user_id="admin-1", grant_id="legacy-1", capability=capability_repo.ADMIN_IDENTITY_MANAGER,
            scope="global", expected_generation=1, expected_version=1, actor_id="manager", reason="conflict",
            changed_at="2026-07-15T10:01:00Z", action_id="duplicate-action",
            table_factory=lambda: duplicates,
        )
