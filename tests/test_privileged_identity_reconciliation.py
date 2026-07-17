"""T-472-05 reconciliation contracts: automation tightens privilege only."""

import pytest
from botocore.exceptions import ClientError
from datetime import UTC, datetime
from types import SimpleNamespace
import importlib.util
from pathlib import Path

from stoa.security.reconciliation import (
    GrantCoordinate,
    GrantSnapshot,
    IdentitySnapshot,
    MemoryCheckpointStore,
    ReconciliationAction,
    RepositoryTighteningAdapter,
    reconcile_inventory,
)


class CapabilityTable:
    """Atomic in-memory table for the capability repository contract."""

    def __init__(self, items=()):
        seeded = list(items)
        for user_id in ("admin-1", "student-2"):
            fence_key = (f"USER#{user_id}", "ACCOUNT_FENCE")
            if not any((item["PK"], item["SK"]) == fence_key for item in seeded):
                seeded.append(
                    {
                        "PK": fence_key[0],
                        "SK": fence_key[1],
                        "entity_type": "account_fence",
                        "user_id": user_id,
                        "status": "active",
                        "generation": 1,
                    }
                )
        self.items = {(item["PK"], item["SK"]): dict(item) for item in seeded}
        self.transactions = 0

    def get_item(self, *, Key, **_kwargs):
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": dict(item)} if item else {}

    def query(self, **_kwargs):
        return {"Items": [dict(item) for item in self.items.values()]}

    def apply_capability_transaction(self, operations):
        pending = dict(self.items)
        for operation in operations:
            if operation.get("kind") == "condition":
                key_data = operation["key"]
                current = pending.get((key_data["PK"], key_data["SK"]))
                if current is None or any(
                    current.get(name) != value
                    for name, value in operation["expected"].items()
                ):
                    raise ClientError(
                        {"Error": {"Code": "ConditionalCheckFailedException"}},
                        "TransactWriteItems",
                    )
                continue
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


def _load_cli():
    path = Path(__file__).parents[1] / "scripts" / "reconcile_privileged_identities.py"
    spec = importlib.util.spec_from_file_location("reconcile_privileged_identities_cli", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_grant_actions_carry_full_coordinates_and_are_order_independent_and_redacted():
    from stoa.db.repositories import capability_repo

    grants = (
        GrantSnapshot(
            "shared-id", capability_repo.STUDENT_SUPPORT_LOOKUP,
            "student:student-2", generation=4, version=3,
        ),
        GrantSnapshot(
            "shared-id", capability_repo.ADMIN_IDENTITY_MANAGER,
            "global", generation=2, version=7,
        ),
    )
    forward = reconcile_inventory(
        [_snapshot(approved=False, grants=grants)], run_id="coordinate-run"
    )
    reverse = reconcile_inventory(
        [_snapshot(approved=False, grants=tuple(reversed(grants)))], run_id="coordinate-run"
    )
    coordinates = tuple(
        action.grant_coordinate
        for action in forward.items[0].actions
        if action.action == "remove_grant"
    )
    assert coordinates == tuple(
        action.grant_coordinate
        for action in reverse.items[0].actions
        if action.action == "remove_grant"
    )
    assert coordinates == (
        GrantCoordinate(
            capability_repo.ADMIN_IDENTITY_MANAGER, "global", 2, "shared-id", 7
        ),
        GrantCoordinate(
            capability_repo.STUDENT_SUPPORT_LOOKUP,
            "student:student-2", 4, "shared-id", 3,
        ),
    )
    rendered = repr(forward.safe_projection())
    for secret in ("shared-id", "student:student-2", "admin_identity_manager"):
        assert secret not in rendered

    applied_ids = []
    for ordered_grants in (grants, tuple(reversed(grants))):
        result = reconcile_inventory(
            [_snapshot(approved=False, grants=ordered_grants)],
            run_id="coordinate-run",
            apply=True,
            environment="sandbox",
            confirmation="APPLY_TIGHTENING",
            approved_run_id="coordinate-run",
            adapter=RecordingAdapter(),
        )
        applied_ids.append(
            tuple(
                action_id
                for action_id in result.applied_actions
                if ":remove_grant:" in action_id
            )
        )
    assert applied_ids[0] == applied_ids[1]
    assert len(set(applied_ids[0])) == 2


@pytest.mark.parametrize(
    "coordinate",
    [
        GrantCoordinate("", "global", 1, "grant-1", 1),
        GrantCoordinate("admin_identity_manager", "", 1, "grant-1", 1),
        GrantCoordinate("admin_identity_manager", "global", 0, "grant-1", 1),
        GrantCoordinate("admin_identity_manager", "global", 1, "grant-1", 0),
        GrantCoordinate("admin_identity_manager", " global", 1, "grant-1", 1),
    ],
)
def test_invalid_grant_coordinate_fails_before_any_apply_mutation(coordinate):
    grant = GrantSnapshot(
        coordinate.grant_id,
        coordinate.capability,
        coordinate.scope,
        generation=coordinate.generation,
        version=coordinate.version,
    )
    adapter = RecordingAdapter()
    with pytest.raises(ValueError, match="grant"):
        reconcile_inventory(
            [_snapshot(approved=False, grants=(grant,))],
            run_id="invalid-coordinate",
            apply=True,
            environment="sandbox",
            confirmation="APPLY_TIGHTENING",
            approved_run_id="invalid-coordinate",
            adapter=adapter,
        )
    assert adapter.calls == []


def test_remove_grant_action_rejects_bare_or_mismatched_target_contracts():
    coordinate = GrantCoordinate("admin_identity_manager", "global", 1, "grant-1", 1)
    with pytest.raises(ValueError, match="full grant coordinate"):
        ReconciliationAction("remove_grant", "conflict", target="grant-1")
    with pytest.raises(ValueError, match="full grant coordinate"):
        ReconciliationAction(
            "remove_grant", "conflict", target="other", grant_coordinate=coordinate
        )


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
    assert [
        action.grant_coordinate.grant_id
        for action in item.actions
        if action.action == "remove_grant"
    ] == [
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


class IdempotentCollaborator:
    def __init__(self):
        self.calls = []

    def suspend_local(self, user_id, *, action_id):
        if action_id not in self.calls:
            self.calls.append(action_id)

    def remove_group(self, provider_subject, group, *, action_id):
        if action_id not in self.calls:
            self.calls.append(action_id)

    def global_sign_out(self, provider_subject, *, action_id):
        if action_id not in self.calls:
            self.calls.append(action_id)


class AuditRepository:
    class DuplicateSecurityAuditEvent(RuntimeError):
        pass

    def __init__(self, *, fail_remove_once=False):
        self.events = {}
        self.fail_remove_once = fail_remove_once

    def append_event(self, stream_id, event):
        if self.fail_remove_once and event["action"] == "remove_grant":
            self.fail_remove_once = False
            raise RuntimeError("audit unavailable")
        if event["event_id"] in self.events:
            raise self.DuplicateSecurityAuditEvent()
        self.events[event["event_id"]] = (stream_id, dict(event))


def _repository_adapter(monkeypatch, table, audit):
    from stoa.db.repositories import capability_repo

    monkeypatch.setattr(capability_repo, "get_table", lambda: table)
    local = IdempotentCollaborator()
    provider = IdempotentCollaborator()
    adapter = RepositoryTighteningAdapter(
        local_account=local,
        provider=provider,
        capability_repository=capability_repo,
        audit_repository=audit,
        clock=lambda: datetime(2026, 7, 15, 11, 0, tzinfo=UTC),
    )
    return adapter, local, provider


def test_concrete_adapter_replay_after_audit_failure_revokes_and_audits_exactly_once(monkeypatch):
    from stoa.db.repositories import capability_repo

    table = CapabilityTable()
    capability_repo.grant_capability(
        user_id="admin-1", command_id="command-1", grant_id="grant-1",
        capability=capability_repo.ADMIN_IDENTITY_MANAGER, scope="global", grantor_id="manager",
        reason="approved", effective_at="2026-07-15T10:00:00Z", expected_generation=0,
        table_factory=lambda: table,
    )
    audit = AuditRepository(fail_remove_once=True)
    adapter, _, _ = _repository_adapter(monkeypatch, table, audit)
    checkpoints = MemoryCheckpointStore()
    snapshot = _snapshot(
        user_id="admin-1", approved=False,
        grants=(GrantSnapshot("grant-1", capability_repo.ADMIN_IDENTITY_MANAGER, "global"),),
    )
    kwargs = dict(
        run_id="authorized-run", apply=True, environment="non-production",
        confirmation="APPLY_TIGHTENING", approved_run_id="authorized-run",
        adapter=adapter, checkpoints=checkpoints,
    )
    with pytest.raises(RuntimeError, match="audit unavailable"):
        reconcile_inventory([snapshot], **kwargs)
    assert capability_repo.get_current_grants("admin-1", table_factory=lambda: table) == []
    assert len([row for row in table.items.values() if row.get("entity_type") == "capability_grant_revision"]) == 2

    reconcile_inventory([snapshot], **kwargs)
    reconcile_inventory([snapshot], **kwargs)
    assert len([row for row in table.items.values() if row.get("entity_type") == "capability_grant_revision"]) == 2
    remove_events = [event for _, event in audit.events.values() if event["action"] == "remove_grant"]
    assert len(remove_events) == 1
    rendered = repr(remove_events)
    for secret in ("admin-1", "grant-1", "global", "issuer.example", "provider-secret-subject"):
        assert secret not in rendered


@pytest.mark.parametrize("reverse_inventory", [False, True])
def test_duplicate_grant_id_lineages_revoke_replay_restore_and_regrant_safely(
    monkeypatch, reverse_inventory
):
    from stoa.db.repositories import capability_repo
    from stoa.services import privileged_identity_service

    table = CapabilityTable()
    coordinates = (
        GrantCoordinate(
            capability_repo.ADMIN_IDENTITY_MANAGER, "global", 1, "shared-grant", 1
        ),
        GrantCoordinate(
            capability_repo.STUDENT_SUPPORT_LOOKUP,
            "student:student-2", 1, "shared-grant", 1,
        ),
    )
    for index, coordinate in enumerate(coordinates, start=1):
        capability_repo.grant_capability(
            user_id="admin-1",
            command_id=f"approved-command-{index}",
            grant_id=coordinate.grant_id,
            capability=coordinate.capability,
            scope=coordinate.scope,
            grantor_id="manager",
            reason="approved",
            effective_at="2026-07-15T10:00:00Z",
            expected_generation=0,
            table_factory=lambda: table,
        )
    monkeypatch.setattr(capability_repo, "get_table", lambda: table)
    audit = AuditRepository(fail_remove_once=True)
    adapter, _, _ = _repository_adapter(monkeypatch, table, audit)
    checkpoint = MemoryCheckpointStore()
    inventory = tuple(
        GrantSnapshot(
            coordinate.grant_id,
            coordinate.capability,
            coordinate.scope,
            generation=coordinate.generation,
            version=coordinate.version,
        )
        for coordinate in coordinates
    )
    if reverse_inventory:
        inventory = tuple(reversed(inventory))
    snapshot = _snapshot(user_id="admin-1", approved=False, grants=inventory)
    kwargs = dict(
        run_id="duplicate-coordinate-run",
        apply=True,
        environment="non-production",
        confirmation="APPLY_TIGHTENING",
        approved_run_id="duplicate-coordinate-run",
        adapter=adapter,
        checkpoints=checkpoint,
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        reconcile_inventory([snapshot], **kwargs)
    completed = reconcile_inventory([snapshot], **kwargs)
    replay = reconcile_inventory([snapshot], **kwargs)

    assert capability_repo.get_current_grants(
        "admin-1", table_factory=lambda: table
    ) == []
    remove_ids = {
        action_id
        for action_id in completed.applied_actions + replay.skipped_actions
        if ":remove_grant:" in action_id
    }
    assert len(remove_ids) == 2
    remove_events = [
        event for _, event in audit.events.values() if event["action"] == "remove_grant"
    ]
    assert len(remove_events) == 2
    assert table.transactions == 4  # two grants plus one exact revoke per lineage

    commands = {}
    profiles = {
        "admin-1": {
            "user_id": "admin-1", "role": "admin", "account_status": "suspended"
        }
    }
    monkeypatch.setattr(
        privileged_identity_service.privileged_identity_repo,
        "create_command",
        lambda item: (commands.setdefault(item["command_id"], dict(item)), True),
    )

    def update_command(command_id, **updates):
        command = commands[command_id]
        command.update(
            status=updates["status"],
            version=updates["expected_version"] + 1,
            evidence_reference=updates["evidence_reference"],
        )
        return dict(command)

    monkeypatch.setattr(
        privileged_identity_service.privileged_identity_repo,
        "update_command",
        update_command,
    )
    monkeypatch.setattr(
        privileged_identity_service.user_repo,
        "get_user",
        lambda user_id: dict(profiles[user_id]),
    )
    monkeypatch.setattr(
        privileged_identity_service.user_repo,
        "put_user",
        lambda item: profiles.__setitem__(item["user_id"], dict(item)),
    )
    monkeypatch.setattr(
        privileged_identity_service.security_audit_repo,
        "append_event",
        lambda *_args, **_kwargs: None,
    )

    class RestoreProvider:
        def admin_add_user_to_group(self, **_kwargs):
            return None

    before_restore_transactions = table.transactions
    restored = privileged_identity_service.change_admin_status(
        actor={
            "user_id": "manager",
            "role": "admin",
            "account_status": "active",
            "capabilities": {capability_repo.ADMIN_IDENTITY_MANAGER: True},
        },
        command_id="restore-command",
        target_id="admin-1",
        operation="restore",
        reason="separate approved account restore",
        provider=RestoreProvider(),
        provider_username="admin-1",
    )
    assert restored["status"] == "active"
    assert profiles["admin-1"]["account_status"] == "active"
    assert table.transactions == before_restore_transactions
    assert capability_repo.get_current_grants(
        "admin-1", table_factory=lambda: table
    ) == []

    replacement = capability_repo.grant_capability(
        user_id="admin-1",
        command_id="new-manager-approved-command",
        grant_id="new-grant-identity",
        capability=capability_repo.ADMIN_IDENTITY_MANAGER,
        scope="global",
        grantor_id="manager",
        reason="new approval",
        effective_at="2026-07-15T12:00:00Z",
        expected_generation=1,
        table_factory=lambda: table,
    )
    assert (replacement["generation"], replacement["version"]) == (2, 1)
    assert [
        row["grant_id"]
        for row in capability_repo.get_current_grants(
            "admin-1", table_factory=lambda: table
        )
    ] == ["new-grant-identity"]


def test_stale_reconciliation_action_cannot_revoke_later_regrant(monkeypatch):
    from stoa.db.repositories import capability_repo

    table = CapabilityTable()
    capability_repo.grant_capability(
        user_id="admin-1", command_id="command-1", grant_id="grant-1",
        capability=capability_repo.ADMIN_IDENTITY_MANAGER, scope="global", grantor_id="manager",
        reason="approved", effective_at="2026-07-15T10:00:00Z", expected_generation=0,
        table_factory=lambda: table,
    )
    adapter, _, _ = _repository_adapter(monkeypatch, table, AuditRepository())
    old = GrantCoordinate(
        capability_repo.ADMIN_IDENTITY_MANAGER, "global", 1, "grant-1", 1
    )
    adapter.revoke_grant("admin-1", old, action_id="old-action")
    capability_repo.grant_capability(
        user_id="admin-1", command_id="command-2", grant_id="grant-2",
        capability=capability_repo.ADMIN_IDENTITY_MANAGER, scope="global", grantor_id="manager",
        reason="new approval", effective_at="2026-07-15T11:01:00Z", expected_generation=1,
        table_factory=lambda: table,
    )
    with pytest.raises(capability_repo.CapabilityVersionConflict):
        adapter.revoke_grant("admin-1", old, action_id="old-action")
    assert [row["grant_id"] for row in capability_repo.get_current_grants("admin-1", table_factory=lambda: table)] == ["grant-2"]


def test_restore_is_mutation_free_and_regrant_requires_manager_new_command(monkeypatch):
    from fastapi import HTTPException
    from stoa.db.repositories import capability_repo
    from stoa.services import privileged_identity_service

    actor = {
        "user_id": "manager", "role": "admin", "account_status": "active",
        "capabilities": {capability_repo.ADMIN_IDENTITY_MANAGER: True},
    }
    monkeypatch.setattr(
        capability_repo, "restore_capability",
        SimpleNamespace(side_effect=AssertionError("restore repository mutation must not exist")),
        raising=False,
    )
    with pytest.raises(HTTPException) as exc_info:
        privileged_identity_service.restore_capability(
            actor=actor, target_id="admin-1", reason="restore", grant_id="old",
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "capability_regrant_required"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--apply", "--environment", "production"],
        ["--apply", "--environment", "non-production"],
        ["--apply", "--environment", "non-production", "--confirm", "wrong"],
        [
            "--apply", "--environment", "non-production", "--confirm", "APPLY_TIGHTENING",
            "--run-id", "run-1", "--approved-run-id", "other",
        ],
        [
            "--apply", "--environment", "non-production", "--confirm", "APPLY_TIGHTENING",
            "--run-id", "run-1", "--approved-run-id", "run-1",
        ],
    ],
)
def test_apply_boundary_rejects_before_adapter_construction(monkeypatch, arguments):
    cli = _load_cli()

    constructed = []
    monkeypatch.setattr(cli, "_load_adapter", lambda *_args: constructed.append(True))
    with pytest.raises(SystemExit):
        cli.main(arguments)
    assert constructed == []


def test_apply_boundary_constructs_adapter_only_after_all_nonproduction_gates(monkeypatch, tmp_path, capsys):
    cli = _load_cli()

    config = tmp_path / "adapter.json"
    config.write_text("{}")
    constructed = []
    adapter = RepositoryTighteningAdapter(
        local_account=IdempotentCollaborator(), provider=IdempotentCollaborator(),
        capability_repository=SimpleNamespace(), audit_repository=AuditRepository(),
    )
    monkeypatch.setattr(
        cli, "_load_adapter",
        lambda factory, path: constructed.append((factory, path)) or adapter,
    )
    assert cli.main(
        [
            "--apply", "--environment", "non-production", "--confirm", "APPLY_TIGHTENING",
            "--run-id", "run-1", "--approved-run-id", "run-1",
            "--adapter-factory", "approved.factory:create", "--adapter-config", str(config),
        ]
    ) == 0
    assert constructed == [("approved.factory:create", config)]
    assert '"mode": "apply-tightening"' in capsys.readouterr().out
