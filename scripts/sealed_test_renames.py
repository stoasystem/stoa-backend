"""Where the tests named inside the sealed private-store inventories live now.

`docs/security/phase-473-private-store-inventory.json` (v1) and its `.v2.json`
name their purge, no-resurrection and finding tests by the file names they had
in 2026-07. Every account-deletion command stores the seal's sha256, so the seal
can never be edited to follow a rename (#397). The tests were renamed in #433;
anything that runs or resolves a sealed selector maps it through here first.
"""

from __future__ import annotations

RENAMED_TEST_FILES: dict[str, str] = {
    "tests/test_phase473_account_deletion.py": "tests/test_account_deletion_fence.py",
    "tests/test_phase473_account_deletion_claim_fencing.py": "tests/test_account_deletion_claim_race.py",
    "tests/test_phase473_account_deletion_seal.py": "tests/test_account_deletion_seal.py",
    "tests/test_phase473_boundary_inventory.py": "tests/test_untrusted_read_boundaries.py",
    "tests/test_phase473_private_store_inventory.py": "tests/test_private_store_inventory.py",
    "tests/test_phase473_conversation_deletion.py": "tests/test_conversation_deletion_fence.py",
    "tests/test_phase473_conversation_replay.py": "tests/test_conversation_replay.py",
    "tests/test_phase473_message_command.py": "tests/test_conversation_message_command.py",
    "tests/test_phase473_delivery_intent_recovery.py": "tests/test_notification_delivery_intent_recovery.py",
    "tests/test_phase473_private_delivery_fencing.py": "tests/test_notification_delivery_fencing.py",
    "tests/test_phase473_notification_deletion.py": "tests/test_notification_deletion.py",
    "tests/test_phase473_derived_content_purge.py": "tests/test_moderation_content_purge.py",
    "tests/test_phase473_report_deletion.py": "tests/test_report_deletion.py",
    "tests/test_phase473_practice_learning_deletion.py": "tests/test_learning_store_deletion.py",
    "tests/test_phase473_practice_authorization.py": "tests/test_practice_teacher_authorization.py",
    "tests/test_phase473_practice_snapshot.py": "tests/test_practice_receipt_snapshot.py",
    "tests/test_phase473_document_boundary.py": "tests/test_document_upload_limits.py",
    "tests/test_phase473_provider_cleanup.py": "tests/test_upload_provider_cleanup.py",
    "tests/test_phase473_provider_state_machine.py": "tests/test_upload_provider_state_machine.py",
    "tests/test_phase473_retention_reconciliation.py": "tests/test_attachment_retention_reconciliation.py",
    "tests/test_phase473_saved_attachments.py": "tests/test_saved_attachments.py",
    "tests/test_phase475_completed_deletion_replay.py": "tests/test_account_deletion_completed_replay.py",
    "tests/test_phase475_deletion_discovery.py": "tests/test_account_deletion_discovery.py",
    "tests/test_phase475_deletion_notification_identity_scrub.py": "tests/test_account_deletion_notification_scrub.py",
    "tests/test_phase475_deletion_teacher_identity_scrub.py": "tests/test_account_deletion_teacher_scrub.py",
    "tests/test_phase475_delivery_begin.py": "tests/test_notification_delivery_begin.py",
    "tests/test_phase475_mistake_answer.py": "tests/test_practice_mistake_answer.py",
    "tests/test_phase475_profile_version_cas.py": "tests/test_profile_version_cas.py",
    "tests/test_phase475_question_state_cas.py": "tests/test_question_state_cas.py",
    "tests/test_phase475_rate_limit.py": "tests/test_rate_limit_admission.py",
}


def current_selector(selector: str) -> str:
    """The runnable form of a selector as sealed: same test, today's file name."""
    file_name, separator, node = selector.partition("::")
    return RENAMED_TEST_FILES.get(file_name, file_name) + separator + node
