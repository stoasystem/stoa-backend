"""T-472-05 reconciliation contracts: automation tightens privilege only."""

import pytest


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
