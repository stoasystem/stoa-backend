"""T-472-05 reconciliation contracts: automation tightens privilege only."""

import pytest

from stoa.security.reconciliation import (
    GrantSnapshot,
    IdentitySnapshot,
    MemoryCheckpointStore,
    ReconciliationAction,
    reconcile_inventory,
)


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
