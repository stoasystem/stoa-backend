"""Every write outside `fenced` is reviewed for the owner registry (#397).

A registry-path deletion reads only the account's derived partitions and the
partitions registered under it. `db_table.fenced` registers what it writes;
a write that does not go through it - and does not call
`account_deletion_repo.registry_operations_for` or `owner_registry` itself -
is invisible to that deletion unless one of the reasons below holds. This
scans `src/stoa` for such writers (direct `put_item` / `update_item` /
`transact_write_items`, `db_table.put/update/transact`, and callers of the
private helpers that make them) and requires each to be listed with its
reason. A new one fails here until someone decides: register it, or say why
not. A listed one that no longer writes, or now registers, fails as stale.

Reasons:
- deletion_flow: the deletion's own writes (tombstones, scrubs, bookkeeping).
- derived_partition: only writes partitions the user id determines
  (`owner_registry.DERIVED_PREFIXES`), which deletion queries directly.
- existing_partition: only changes rows, or adds rows, in a partition a
  registered write created (a conversation, a report, an upload, a recovery
  job), so the partition is already registered.
- not_deletion_data: no deletion branch acts on what it writes (an excluded
  class in the inventory: billing, teacher applications, privileged identity,
  curriculum content, security audit; or rows naming no account).
- no_caller: nothing in `src/stoa` calls it. If it gets a caller, review it.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WRITE_ATTRS = {"put_item", "update_item", "transact_write_items", "batch_writer"}
GATEWAY_WRITES = {"put", "update", "transact"}
REGISTERS = ("fenced(", "registry_operations_for(", "owner_registry.")

type Function = ast.FunctionDef | ast.AsyncFunctionDef


def _writes_directly(function: Function) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        if isinstance(called, ast.Attribute):
            receiver = ast.unparse(called.value)
            if receiver.endswith("db_table") and called.attr in GATEWAY_WRITES:
                return True
            if called.attr in WRITE_ATTRS:
                return True
        elif isinstance(called, ast.Name) and called.id in WRITE_ATTRS:
            return True
    return False


def _calls(function: Function, names: set[str]) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        if isinstance(called, ast.Name) and called.id in names:
            return True
        if isinstance(called, ast.Attribute) and called.attr in names:
            return True
    return False


def _registers(function: Function) -> bool:
    body = ast.unparse(function)
    return any(token in body for token in REGISTERS)


def scan(root: Path) -> set[str]:
    """`file::function` for every writer that neither fences nor registers."""
    modules: dict[str, list[Function]] = {}
    for path in sorted((Path(root) / "src" / "stoa").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules[path.relative_to(root).as_posix()] = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
    # A private helper that writes (`_put_item`, `_apply`, ...) is judged at
    # its callers; one that registers itself covers them.
    helpers: set[str] = set()
    registering_helpers: set[str] = set()
    for functions in modules.values():
        for function in functions:
            if function.name.startswith("_") and _writes_directly(function):
                (registering_helpers if _registers(function) else helpers).add(function.name)
    found: set[str] = set()
    for relative, functions in modules.items():
        for function in functions:
            if function.name in helpers:
                continue
            direct = _writes_directly(function)
            if not (direct or _calls(function, helpers)):
                continue
            if _registers(function):
                continue
            if not direct and _calls(function, registering_helpers) and not _calls(function, helpers):
                continue
            found.add(f"{relative}::{function.name}")
    return found


REVIEWED: dict[str, str] = {
    "src/stoa/db/repositories/account_deletion_repo.py::advance_deletion_scan_cursor": "deletion_flow",
    # The owner registry sweep's own result row (JOB#owner_registry_sweep): counts only.
    "src/stoa/services/owner_registry_sweep.py::record_run": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::begin_account_deletion": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::claim_deletion_command": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::close_unused_provider_revoke_debt": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::complete_provider_revoke_debt": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::create_provider_revoke_debt": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::delete_owned_row": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::ensure_active_account_fence": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::finalize_account_deletion": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::persist_branch_result": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::register_pending_deletion": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::release_deletion_command_claim": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::renew_deletion_command_claim": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::replace_teacher_session_with_tombstone": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::replace_with_deletion_tombstone": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::scrub_parent_profile_child": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::scrub_teacher_question_reference": "deletion_flow",
    "src/stoa/db/repositories/account_deletion_repo.py::terminalize_identity_row": "deletion_flow",
    "src/stoa/db/repositories/adaptive_learning_repo.py::scrub_adaptive_private_row": "deletion_flow",
    "src/stoa/db/repositories/ai_teacher_tools_repo.py::scrub_ai_draft_private_row": "deletion_flow",
    "src/stoa/db/repositories/attachment_repo.py::activate_retention_fence": "deletion_flow",
    "src/stoa/db/repositories/attachment_repo.py::advance_retention_fence_cursor": "deletion_flow",
    "src/stoa/db/repositories/attachment_repo.py::complete_retention_fence": "deletion_flow",
    "src/stoa/db/repositories/attachment_repo.py::scrub_conversation_private_row": "deletion_flow",
    "src/stoa/db/repositories/curriculum_analytics_repo.py::reconcile_curriculum_signal": "deletion_flow",
    "src/stoa/db/repositories/moderation_repo.py::scrub_moderation_row": "deletion_flow",
    "src/stoa/db/repositories/notification_repo.py::scrub_notification_identity_references": "deletion_flow",
    "src/stoa/db/repositories/notification_repo.py::scrub_notification_private_row": "deletion_flow",
    "src/stoa/db/repositories/practice_repo.py::scrub_practice_private_row": "deletion_flow",
    "src/stoa/db/repositories/report_repo.py::scrub_report_private_row": "deletion_flow",
    "src/stoa/db/repositories/websocket_repo.py::revoke_account_connection": "deletion_flow",
    "src/stoa/db/repositories/identity_repo.py::_create_or_repair_identity_inventory": "derived_partition",
    "src/stoa/db/repositories/identity_repo.py::put_sign_in_refresh_token": "derived_partition",
    "src/stoa/db/repositories/notification_repo.py::_finish_delivery_intent": "derived_partition",
    "src/stoa/db/repositories/notification_repo.py::claim_delivery_intent": "derived_partition",
    "src/stoa/db/repositories/notification_repo.py::recover_delivery_intent": "derived_partition",
    "src/stoa/db/repositories/report_repo.py::claim_report_email_intent": "derived_partition",
    "src/stoa/db/repositories/usage_ledger_repo.py::set_daily_question_counter": "derived_partition",
    "src/stoa/db/repositories/user_repo.py::put_user": "derived_partition",
    "src/stoa/db/repositories/user_repo.py::put_user_with_email_claim": "derived_partition",
    "src/stoa/routers/parents.py::admit_parent_link_request": "derived_partition",
    "src/stoa/services/password_change_code_service.py::admit_send": "derived_partition",
    "src/stoa/services/password_change_code_service.py::release_send": "derived_partition",
    "src/stoa/services/password_change_code_service.py::store_code": "derived_partition",
    "src/stoa/services/password_change_code_service.py::verify_and_consume": "derived_partition",
    "src/stoa/services/teacher_support_allowance_service.py::set_assigned_weekly_cases": "derived_partition",
    "src/stoa/db/repositories/attachment_repo.py::mark_deletion_absence_proven": "existing_partition",
    "src/stoa/db/repositories/attachment_repo.py::mark_saved_attachment_deletion_pending": "existing_partition",
    "src/stoa/db/repositories/identity_repo.py::record_session_revocation": "existing_partition",
    "src/stoa/db/repositories/public_identity_repo.py::advance_public_identity_command": "existing_partition",
    "src/stoa/db/repositories/report_repo.py::put_recovery_job_audit_event": "existing_partition",
    "src/stoa/db/repositories/report_repo.py::put_report_audit_event": "existing_partition",
    "src/stoa/db/repositories/report_repo.py::request_recovery_job_cancellation": "existing_partition",
    "src/stoa/db/repositories/report_repo.py::try_claim_recovery_job": "existing_partition",
    "src/stoa/db/repositories/report_repo.py::try_claim_recovery_job_target": "existing_partition",
    "src/stoa/db/repositories/report_repo.py::try_claim_report_resend": "existing_partition",
    "src/stoa/db/repositories/report_repo.py::try_start_generation_retry": "existing_partition",
    "src/stoa/db/repositories/report_repo.py::update_recovery_job_status": "existing_partition",
    "src/stoa/db/repositories/report_repo.py::update_recovery_job_target": "existing_partition",
    "src/stoa/db/repositories/report_repo.py::update_report_status": "existing_partition",
    "src/stoa/db/repositories/upload_code_repo.py::claim_code": "existing_partition",
    "src/stoa/services/ask_question/_store.py::_leased_command_update": "existing_partition",
    "src/stoa/services/ask_question/_store.py::_unsettled_end_update": "existing_partition",
    "src/stoa/services/ask_question/_store.py::close_stale_lease": "existing_partition",
    "src/stoa/services/ask_question/_store.py::fail_message_command": "existing_partition",
    "src/stoa/services/ask_question/_store.py::mark_message_command_terminal": "existing_partition",
    "src/stoa/services/ask_question/_store.py::record_message_generation_context": "existing_partition",
    "src/stoa/services/ask_question/_store.py::reopen_failed_message_command": "existing_partition",
    "src/stoa/services/learning_session/_store.py::retitle_conversation": "existing_partition",
    "src/stoa/services/uploads/_store.py::_apply": "existing_partition",
    "src/stoa/services/uploads/_store.py::_cleanup_update": "existing_partition",
    "src/stoa/services/uploads/_store.py::claim_stale_upload_operation": "existing_partition",
    "src/stoa/services/uploads/_store.py::complete_upload_part": "existing_partition",
    "src/stoa/services/uploads/_store.py::pin_upload_part": "existing_partition",
    "src/stoa/db/repositories/account_invitation_repo.py::_conditional_put": "not_deletion_data",
    "src/stoa/db/repositories/account_invitation_repo.py::_transition": "not_deletion_data",
    "src/stoa/db/repositories/account_invitation_repo.py::restore_invitation": "not_deletion_data",
    "src/stoa/db/repositories/account_invitation_repo.py::restore_revoked_invitation": "not_deletion_data",
    "src/stoa/db/repositories/account_number_repo.py::advance_allocation_hint": "not_deletion_data",
    "src/stoa/db/repositories/account_number_repo.py::claim_account_number": "not_deletion_data",
    "src/stoa/db/repositories/billing_fact_repo.py::claim_fact_reconciliation": "not_deletion_data",
    "src/stoa/db/repositories/billing_fact_repo.py::record_provider_fact": "not_deletion_data",
    "src/stoa/db/repositories/billing_fact_repo.py::register_provider_event": "not_deletion_data",
    "src/stoa/db/repositories/checkout_command_repo.py::release_open_guard_for_terminal_command": "not_deletion_data",
    "src/stoa/db/repositories/curriculum_analytics_repo.py::increment_metric": "not_deletion_data",
    "src/stoa/db/repositories/curriculum_analytics_repo.py::put_signal": "not_deletion_data",
    "src/stoa/db/repositories/curriculum_ops_repo.py::append_audit_event": "not_deletion_data",
    "src/stoa/db/repositories/curriculum_ops_repo.py::put_manifest": "not_deletion_data",
    "src/stoa/db/repositories/curriculum_ops_repo.py::put_migration_evidence": "not_deletion_data",
    "src/stoa/db/repositories/curriculum_ops_repo.py::put_pointer": "not_deletion_data",
    "src/stoa/db/repositories/curriculum_ops_repo.py::put_published_projection": "not_deletion_data",
    "src/stoa/db/repositories/curriculum_ops_repo.py::put_version": "not_deletion_data",
    "src/stoa/db/repositories/curriculum_ops_repo.py::set_practice_attributes": "not_deletion_data",
    "src/stoa/db/repositories/curriculum_ops_repo.py::set_published_pointer": "not_deletion_data",
    "src/stoa/db/repositories/identity_repo.py::record_sign_in_revocation": "not_deletion_data",
    "src/stoa/db/repositories/notification_repo.py::put_event": "not_deletion_data",
    "src/stoa/db/repositories/privileged_identity_repo.py::create_command": "not_deletion_data",
    "src/stoa/db/repositories/privileged_identity_repo.py::update_command": "not_deletion_data",
    "src/stoa/db/repositories/security_audit_repo.py::aggregate_authorization_probe": "not_deletion_data",
    "src/stoa/db/repositories/security_audit_repo.py::append_event": "not_deletion_data",
    "src/stoa/db/repositories/teacher_application_repo.py::_conditional_put": "not_deletion_data",
    "src/stoa/db/repositories/teacher_application_repo.py::claim_invitation": "not_deletion_data",
    "src/stoa/db/repositories/teacher_application_repo.py::set_application_review_state": "not_deletion_data",
    "src/stoa/db/repositories/teacher_application_repo.py::update_activation_command": "not_deletion_data",
    "src/stoa/jobs/migrate_billing_plan_identity.py::conditional_apply": "not_deletion_data",
    "src/stoa/routers/analytics.py::ingest_event": "not_deletion_data",
    "src/stoa/routers/auth.py::admit_invitation_claim": "not_deletion_data",
    "src/stoa/services/billing_reconciliation_service.py::bind_webhook_provider_identity": "not_deletion_data",
    "src/stoa/services/paid_entitlement_service.py::apply_due_paid_transition": "not_deletion_data",
    "src/stoa/services/paid_entitlement_service.py::clear_renewal_grace": "not_deletion_data",
    "src/stoa/services/paid_entitlement_service.py::schedule_period_end_transition": "not_deletion_data",
    "src/stoa/services/paid_entitlement_service.py::start_renewal_grace": "not_deletion_data",
    "src/stoa/services/subscription_service.py::_apply_billing_transition": "not_deletion_data",
    "src/stoa/services/subscription_service.py::_apply_direct_refund_result": "not_deletion_data",
    "src/stoa/services/subscription_service.py::_apply_request_item": "not_deletion_data",
    "src/stoa/services/subscription_service.py::_put_billing_event": "not_deletion_data",
    "src/stoa/services/subscription_service.py::_put_provider_lookup_rows": "not_deletion_data",
    "src/stoa/services/subscription_service.py::_record_manual_override": "not_deletion_data",
    "src/stoa/services/subscription_service.py::_record_refund_idempotency_failure": "not_deletion_data",
    "src/stoa/services/subscription_service.py::_record_refund_idempotency_success": "not_deletion_data",
    "src/stoa/services/subscription_service.py::_reserve_refund_idempotency": "not_deletion_data",
    "src/stoa/services/subscription_service.py::_update_request_item": "not_deletion_data",
    "src/stoa/services/subscription_service.py::create_parent_request": "not_deletion_data",
    "src/stoa/services/subscription_service.py::update_payment_rollout_controls": "not_deletion_data",
    "src/stoa/db/repositories/report_repo.py::_put_support_handoff_delivery_feed_item": "no_caller",
    "src/stoa/db/repositories/report_repo.py::mark_report_artifact_edit_draft_applied": "no_caller",
    "src/stoa/db/repositories/report_repo.py::mark_report_artifact_rollback_preview_applied": "no_caller",
    "src/stoa/db/repositories/report_repo.py::mark_report_edit_draft_applied": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_audit_retention_audit_event": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_audit_retention_manifest": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_legal_hold_audit_event": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_legal_hold_metadata": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_legal_hold_review_metadata": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_report_artifact_edit_draft": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_report_artifact_rollback_preview": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_report_edit_draft": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_retention_approval_audit_event": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_retention_approval_metadata": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_support_crm_message_event": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_support_handoff_audit_event": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_support_handoff_delivery_audit_event": "no_caller",
    "src/stoa/db/repositories/report_repo.py::put_support_handoff_delivery_record": "no_caller",
    "src/stoa/db/repositories/report_repo.py::try_apply_report_artifact_edit": "no_caller",
    "src/stoa/db/repositories/report_repo.py::try_apply_report_edit": "no_caller",
    "src/stoa/db/repositories/report_repo.py::update_audit_retention_manifest_status": "no_caller",
    "src/stoa/db/repositories/report_repo.py::update_support_handoff_delivery_status": "no_caller",
}


def test_every_unfenced_writer_is_reviewed_for_the_owner_registry():
    found = scan(ROOT)
    new = sorted(found - REVIEWED.keys())
    assert not new, (
        "writes outside db_table.fenced that register nothing: register the "
        "partition (account_deletion_repo.registry_operations_for) or list the "
        f"writer in REVIEWED with its reason: {new}"
    )


def test_the_review_list_names_only_current_unfenced_writers():
    stale = sorted(REVIEWED.keys() - scan(ROOT))
    assert not stale, f"no longer an unregistered writer; remove from REVIEWED: {stale}"


def test_the_scan_sees_a_new_unfenced_writer(tmp_path):
    source = tmp_path / "src" / "stoa"
    source.mkdir(parents=True)
    new = ["def put_private(table, item):", "    table.put_item(Item=item)", ""]
    registered = [
        "def put_private(table, item):",
        "    db_table.fenced(item['owner_id'], [{'Put': {'Item': item}}], table=table)",
        "",
    ]
    (source / "new_repo.py").write_text("\n".join(new), encoding="utf-8")
    (source / "registered_repo.py").write_text("\n".join(registered), encoding="utf-8")
    assert scan(tmp_path) == {"src/stoa/new_repo.py::put_private"}
