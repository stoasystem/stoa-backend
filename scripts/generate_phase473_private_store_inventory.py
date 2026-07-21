#!/usr/bin/env python3
"""Generate the source-sealed Phase 473 private-store and evidence inventories."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Iterable


SCHEMA_VERSION = "phase-473-private-store-inventory.v1"
EVIDENCE_SCHEMA_VERSION = "phase-473-retained-evidence-policy.v1"
BRANCH_IDS = (
    "account_profile",
    "identity_cross_account",
    "capability_scope",
    "question_ocr_session",
    "attachments",
    "moderation",
    "report_records",
    "report_artifacts",
    "support_recovery_feed",
    "conversation_messages",
    "practice_progress",
    "adaptive_assignment",
    "learning_memory",
    "ai_teacher_draft",
    "curriculum_signal",
    "notification_device_realtime",
    "external_delivery_debt",
)

SINK_METHODS = frozenset(
    {
        "put_item", "update_item", "delete_item", "batch_write_item",
        "transact_write_items", "transact", "_transact", "put_object", "copy_object", "delete_object",
        "create_multipart_upload", "upload_part", "complete_multipart_upload",
        "abort_multipart_upload", "send_email", "send_raw_email", "send_message",
        "delete_message", "admin_update_user_attributes", "admin_add_user_to_group",
        "admin_remove_user_from_group", "admin_user_global_sign_out",
        "admin_delete_user", "post_to_connection", "invoke_model", "converse",
    }
)
WRAPPER_NAMES = frozenset({"transact", "_transact", "urlopen"})

# Updating a checked JSON digest cannot update this source review boundary.  A
# changed or newly mutating file requires an explicit code review and a change
# to this table, which is why isolated source mutations fail on generation too.
REVIEWED_MUTATING_FILES = {
    "src/stoa/db/repositories/account_deletion_repo.py": "fa7b0e3cb93a59af276dac81a3154ccee0170bfc9e91b63a73b154f48bbcf7cd",
    "src/stoa/db/repositories/adaptive_learning_repo.py": "a7524e930c78946fa5e44af96f5bc32c0123ebb8a0843fe42dd22c749a14b497",
    "src/stoa/db/repositories/ai_teacher_tools_repo.py": "8c5a14ea3446954b25594f661e5ce1d3025bc1bb22ac53f0f4b1f3ec74e99d60",
    "src/stoa/db/repositories/attachment_repo.py": "1b411f62169aae75f7ee182118e2970733cd6e160de8dda912d18d5f89de6c49",
    "src/stoa/db/repositories/capability_repo.py": "25d4e117ac2ffb41e479bd74c70645023034e26f2c393b3789d108a3538555d7",
    "src/stoa/db/repositories/curriculum_analytics_repo.py": "90c1c9996546c8c635c30b32667ce66ec373914338ec887b7f58880a53aa1ced",
    "src/stoa/db/repositories/curriculum_ops_repo.py": "23f5bb6799ca1fd03a5343b415f0c2917442b8f217fa5600a2e93b3588179196",
    "src/stoa/db/repositories/identity_repo.py": "da94ed8c9926f591af0ff24cac34b2a045369ce0aed132c84c7667b715dd77cf",
    "src/stoa/db/repositories/moderation_repo.py": "a84aa5c5e76dff449999520c26406869733471c4598cdf04ac90bc0dbf27db40",
    "src/stoa/db/repositories/notification_repo.py": "10e02e2df0b97b5226d2c160c46c4e6412c00b4fc560accc0875b8b7644363a3",
    "src/stoa/db/repositories/practice_repo.py": "824447145dfb7b4922fb92fd86900db459216581b473f525734d1cbc95a820a9",
    "src/stoa/db/repositories/privileged_identity_repo.py": "a59e0f3cc7619a92b1484e227dbcf6521b951ecd3952c15844d8f32fea18c925",
    "src/stoa/db/repositories/public_identity_repo.py": "454c9f20e08009c0b276478f2fe1c30adad5272feaa6e77da5203dd9f9755b4b",
    "src/stoa/db/repositories/question_repo.py": "8e6956837e8f34442e36c57c709670a9f5b7a3c5226a02a9cd5d8accf2647ef3",
    "src/stoa/db/repositories/report_repo.py": "6ac440dfba3b25ba017ab4e2a6897264dccaa0112f18feaa9d2d49ac89a3bbfb",
    "src/stoa/db/repositories/security_audit_repo.py": "346ce4c47f02efb6913b3a92eb5a0eaa2fef71139c0e8f073054f3122e760204",
    "src/stoa/db/repositories/teacher_application_repo.py": "74abd7b83c0415cb3f994ea2c0c47489c74a58cc4ecc24eb8256affc3dfc6986",
    "src/stoa/db/repositories/usage_ledger_repo.py": "abec9525f79e7f2d02a4ffe07896112084f7abfe9353b344357fd2a597f539b3",
    "src/stoa/db/repositories/user_repo.py": "9aa6f91fe32803c9aa1aca573d6be83833b087b9bb1aa93fc699e7555b5bcbef",
    "src/stoa/db/repositories/websocket_repo.py": "1c9ef73d6767b5de701676425e7af783d9da4a970d87b80a1c0c9fa4fbf7a67f",
    "src/stoa/routers/admin.py": "56028813f940b2ffa78b91185d152a30920f3b5ad8c0297e8ed05e19f616b49c",
    "src/stoa/routers/auth.py": "a647a2bad20c013504101211eeed483b48740a1e817c9ef3f933dfea5a123f06",
    "src/stoa/routers/conversations.py": "04c2fdef6178a03531f215ca29c71ca88204099c09264c9400abc98f216c0ecd",
    "src/stoa/routers/teachers.py": "3419083f653a219eea22ca7c8833095f466d0a81ca07a50ac5aaf396c19ec823",
    "src/stoa/services/account_deletion_service.py": "aaa841a1a2b7726fca268b66eda3b685dfa1ecdfa5187db83de7d58659e658af",
    "src/stoa/services/ai_service.py": "0f918d706c2c14768fa90ae571a11ba41e6d912460f7d80c56cc3719f80dacc8",
    "src/stoa/services/attachment_service.py": "1f4784374d16d84f3c04d047af9a3195d65598cac0f91413a01bb7e3c76a0cc9",
    "src/stoa/services/notification_service.py": "df01a49f7df86ccb780678df18fab6e766db1d71666041b7fb02e7a688832f2d",
    "src/stoa/services/notify_service.py": "cde3ec6b7cb87e07c8fec1a65d1333562b3ce2334bd8aaa3d0e0ccf87df275d3",
    "src/stoa/services/privileged_identity_service.py": "86f1f8052aafef008b4976008f49935c0b4eda6def35ee6396a8955b249b4381",
    "src/stoa/services/public_identity_service.py": "7825a3a80ae09b43b15c3da19457a0e9f31e3b7ccedf11fab90188e9b6e2c38c",
    "src/stoa/services/rate_limit.py": "55d1ff00fee60813d6e1a5376079610bc51989c66983a4ce7add8a9eb733e5f6",
    "src/stoa/services/report_artifact_service.py": "2d6f747f7ed89bd1d50b50a179c6c082a1826421123a0dc12da716d12ddb820f",
    "src/stoa/services/report_audit_retention_service.py": "53b4561c7c584bd5adf6f0793833b400a02d6d1ca31ee18d4f9fcf657ad6ddc3",
    "src/stoa/services/report_service.py": "4f632a8077e89d06920107cd442ed62f50341ed5b8428e0d1fac622fdc9f6b59",
    "src/stoa/services/subscription_service.py": "8cfd9183ef9c0894220478ed8fc6de141d9450e2e6d1c7a4b22dd9b2f8e89cd6",
    "src/stoa/services/teacher_application_service.py": "ec90df94082878d91386800fa0bebc4150e8a01aba2a3e602ba0a02386676216",
    "src/stoa/services/websocket_service.py": "00061ca91d389d9d1990fdfd2fad5255ddcfeaeabb36c91ce6d0ab371694de4a",
}


FINDING_REGISTRY = (
    {
        "finding_id": "CR-01",
        "source_symbols": [
            "account_deletion_repo.claim_deletion_command",
            "account_deletion_repo.renew_deletion_command_claim",
            "account_deletion_repo.persist_branch_result",
            "account_deletion_repo.finalize_account_deletion",
        ],
        "required_semantics": [
            "current-epoch lease comparison",
            "opaque owner/version/digest CAS",
            "strong durable exact-set finalization",
        ],
        "lower_fake_target": "src/stoa/db/repositories/account_deletion_repo.py:table.update_item",
        "runtime_selector": "tests/test_phase473_account_deletion_claim_fencing.py::test_branch_result_cas_requires_owner_version_digest_and_returns_next_claim",
    },
    {
        "finding_id": "CR-02",
        "source_symbols": [
            "notification_service.load_authoritative_delivery_events",
            "notification_service.run_authoritative_delivery",
            "websocket_service.fanout_notification_event",
        ],
        "required_semantics": [
            "strong canonical owner resolution",
            "no direct private provider fallback",
            "one durable intent before every provider effect",
        ],
        "lower_fake_target": "src/stoa/services/notification_service.py:provider_call",
        "runtime_selector": "tests/test_phase473_private_delivery_fencing.py::test_private_push_rejects_missing_malformed_or_stale_persisted_generation",
    },
    {
        "finding_id": "WR-01",
        "source_symbols": [
            "account_deletion_repo._valid_lifecycle_timestamp",
            "account_deletion_service.AccountDeletionService.__init__",
        ],
        "required_semantics": ["nonblank timezone-aware UTC lifecycle validation"],
        "lower_fake_target": "src/stoa/db/repositories/account_deletion_repo.py:_valid_lifecycle_timestamp",
        "runtime_selector": "tests/test_phase473_account_deletion_claim_fencing.py::test_repository_rejects_invalid_lifecycle_timestamps",
    },
    {
        "finding_id": "WR-02",
        "source_symbols": ["account_deletion_repo.scrub_parent_profile_child"],
        "required_semantics": ["narrow legacy normalization", "parent row-version CAS"],
        "lower_fake_target": "src/stoa/db/repositories/account_deletion_repo.py:table.transact",
        "runtime_selector": "tests/test_phase473_account_deletion_claim_fencing.py::test_parent_scrub_is_version_cas_and_never_replaces_concurrent_preferences",
    },
    {
        "finding_id": "WR-03",
        "source_symbols": [
            "notification_repo.claim_delivery_intent",
            "notification_repo.begin_delivery_effect",
            "notification_repo.recover_delivery_intent",
        ],
        "required_semantics": [
            "expired pre-effect takeover only",
            "inflight ambiguity is terminal",
            "intent version and payload/scope digest CAS",
        ],
        "lower_fake_target": "src/stoa/db/repositories/notification_repo.py:table.update_item",
        "runtime_selector": "tests/test_phase473_delivery_intent_recovery.py::test_repository_claim_uses_explicit_current_time_not_proposed_expiry",
    },
)

for _finding in FINDING_REGISTRY:
    _finding["privacy_surface"] = "bounded_noncontent_lifecycle_facts"


SEMANTIC_REQUIREMENTS: dict[str, dict[str, tuple[str, ...]]] = {
    "src/stoa/db/repositories/account_deletion_repo.py": {
        "claim_deletion_command": ("lease_expires_at<:now_epoch", ":now_epoch", ":expiry"),
        "renew_deletion_command_claim": (
            "lease_owner=:owner",
            "command_version=:command_version",
            "branch_results_digest=:branch_results_digest",
            "lease_expires_at>=:now_epoch",
        ),
        "persist_branch_result": (
            "lease_owner=:owner",
            "command_version=:command_version",
            "branch_results_digest=:branch_results_digest",
            "lease_expires_at>=:now_epoch",
            "result_version",
        ),
        "finalize_account_deletion": (
            "get_deletion_command",
            "branch_results_digest(durable_results)",
            "claim.branch_results_digest",
            "lease_owner",
            "command_version",
        ),
        "scrub_parent_profile_child": (
            "attribute_not_exists(#version)",
            "user_id=:parent AND #version=:expected_version",
        ),
    },
    "src/stoa/db/repositories/notification_repo.py": {
        "claim_delivery_intent": (
            "(#effect=:registered OR (#effect=:pre_effect AND ",
            "lease_expires_at < :now_epoch",
            "intent_version=:version",
            "scope_digest=:scope",
            "payload_digest=:payload",
        ),
        "begin_delivery_effect": (
            "#effect=:pre_effect",
            "lease_owner=:lease",
            "intent_version=:version",
            "scope_digest=:scope",
            "payload_digest=:payload",
            "active_fence_condition",
            "classification_digest=:classification_seal",
        ),
        "recover_delivery_intent": (
            "state != \"effect_inflight\"",
            "provider_acceptance_unknown",
            "intent_version=:version",
        ),
    },
    "src/stoa/services/notification_service.py": {
        "resolve_delivery_ownership": (
            "classification = event.get(\"owner_classification\")",
            "return resolve_legacy_delivery_owner(event, table=table)",
        ),
        "run_delivery_intent": (
            "delivery_intent_sendable",
            "begin_delivery_effect",
            "provider_call()",
        ),
        "attempt_push_delivery": ("load_authoritative_delivery_events", "run_authoritative_delivery"),
        "send_digest": ("load_authoritative_delivery_events", "run_authoritative_delivery"),
    },
    "src/stoa/services/websocket_service.py": {
        "fanout_notification_event": (
            "batch = notification_service.load_authoritative_delivery_events([event_id])",
            "notification_service.run_authoritative_delivery",
        ),
    },
}


BRANCH_CONTRACTS: dict[str, dict[str, Any]] = {
    "account_profile": {"roots": ["USER#/PROFILE", "USER#/ACCOUNT_FENCE"], "subfamilies": ["profile", "parent_binding"]},
    "identity_cross_account": {"roots": ["IDENTITY#", "PUBLIC_IDENTITY#", "PROVIDER_REVOKE#"], "subfamilies": ["identity", "public_command", "provider_identity"]},
    "capability_scope": {"roots": ["CAPABILITY#", "GRANT#"], "subfamilies": ["current", "history"]},
    "question_ocr_session": {"roots": ["QUESTION#", "SESSION#"], "subfamilies": ["question", "ocr", "teacher_session"]},
    "attachments": {"roots": ["UPLOAD#", "ATTACHMENT#", "OBJECT_STORE_ATTACHMENT_VERSION"], "subfamilies": ["intent", "association", "immutable_object"]},
    "moderation": {"roots": ["MODERATION#"], "subfamilies": ["summary", "event"]},
    "report_records": {"roots": ["REPORT#", "REPORT_RECOVERY_JOB#"], "subfamilies": ["summary", "audit", "recovery"]},
    "report_artifacts": {"roots": ["REPORT_OBJECT#", "OBJECT_STORE_REPORT_VERSION"], "subfamilies": ["object_intent", "version", "retention"]},
    "support_recovery_feed": {"roots": ["SUPPORT_HANDOFF#", "SUPPORT_CRM_MESSAGE_FEED"], "subfamilies": ["handoff", "delivery", "feed"]},
    "conversation_messages": {"roots": ["CONVERSATION#", "MESSAGE_COMMAND#", "CHAT_OPERATION#"], "subfamilies": ["conversation", "message", "command", "association"]},
    "practice_progress": {"roots": ["PRACTICE_ATTEMPT#", "PRACTICE_PROGRESS#", "USAGE#"], "subfamilies": ["attempt", "receipt", "progress"]},
    "adaptive_assignment": {"roots": ["ASSIGNMENT#"], "subfamilies": ["assignment", "outcome"]},
    "learning_memory": {"roots": ["LEARNING_MEMORY#"], "subfamilies": ["memory", "profile"]},
    "ai_teacher_draft": {"roots": ["AI_TEACHER_DRAFT#"], "subfamilies": ["draft", "accepted_copy"]},
    "curriculum_signal": {"roots": ["CURRICULUM_SIGNAL#", "SIGNAL_OWNER#"], "subfamilies": ["signal", "owner_manifest", "metric_contribution"]},
    "notification_device_realtime": {"roots": ["NOTIFICATION#", "ASSISTANCE_SUMMARY#", "NOTIFICATION_PUSH_TOKEN#", "WS_CONN#"], "subfamilies": ["event", "assistance", "preference", "token", "connection"]},
    "external_delivery_debt": {"roots": ["DELIVERY_INTENT#", "REPORT_EMAIL#", "TEACHER_ESCALATION#"], "subfamilies": ["ses", "sqs", "cognito", "push", "websocket", "provider"]},
}

SELECTORS = {
    "account_profile": ("tests/test_phase473_account_deletion.py::test_tombstone_replacement_retains_only_declared_noncontent_keys", "tests/test_phase473_account_deletion.py::test_every_primary_writer_uses_the_same_active_fence_and_exact_generation"),
    "identity_cross_account": ("tests/test_phase473_account_deletion.py::test_primary_branch_persists_cursor_and_requires_two_clean_epochs", "tests/test_phase473_account_deletion.py::test_resolve_actor_checks_permanent_fence_before_profile_or_grants"),
    "capability_scope": ("tests/test_phase473_account_deletion.py::test_primary_branch_persists_cursor_and_requires_two_clean_epochs", "tests/test_phase473_account_deletion.py::test_every_primary_writer_uses_the_same_active_fence_and_exact_generation"),
    "question_ocr_session": ("tests/test_phase473_account_deletion.py::test_question_and_session_scrub_allowlists_exclude_all_private_learning_fields", "tests/test_phase473_account_deletion.py::test_every_primary_writer_uses_the_same_active_fence_and_exact_generation"),
    "attachments": ("tests/test_phase473_account_deletion.py::test_base_table_discovery_finds_owner_only_intents_and_late_pages", "tests/test_phase473_account_deletion.py::test_upload_intent_is_fenced_before_any_provider_creation"),
    "moderation": ("tests/test_phase473_derived_content_purge.py::test_moderation_scrub_removes_all_content_and_private_linkage", "tests/test_phase473_derived_content_purge.py::test_moderation_repository_case_and_event_writes_share_exact_fence"),
    "report_records": ("tests/test_phase473_report_deletion.py::test_report_discovery_is_strong_paginated_and_scrub_is_allowlisted", "tests/test_phase473_report_deletion.py::test_object_intent_is_owner_partitioned_and_fenced_before_provider"),
    "report_artifacts": ("tests/test_phase473_report_deletion.py::test_exact_object_purge_never_removes_coordinates_before_absence", "tests/test_phase473_report_deletion.py::test_object_intent_is_owner_partitioned_and_fenced_before_provider"),
    "support_recovery_feed": ("tests/test_phase473_report_deletion.py::test_report_branches_restart_and_require_two_later_clean_epochs", "tests/test_phase473_report_deletion.py::test_email_intent_claim_rechecks_fence_and_provider_unknown_is_terminal"),
    "conversation_messages": ("tests/test_phase473_conversation_deletion.py::test_conversation_branch_releases_associations_before_scrub_and_requires_later_zero_scan", "tests/test_phase473_conversation_deletion.py::test_every_conversation_write_transaction_starts_with_exact_account_fence"),
    "practice_progress": ("tests/test_phase473_practice_learning_deletion.py::test_private_scans_are_strong_paginated_and_scrubs_are_strict_allowlists", "tests/test_phase473_practice_learning_deletion.py::test_every_learning_write_builder_starts_with_exact_account_fence"),
    "adaptive_assignment": ("tests/test_phase473_practice_learning_deletion.py::test_five_restartable_branches_are_registered_and_require_later_zero_scan", "tests/test_phase473_practice_learning_deletion.py::test_existing_assignment_and_draft_updates_require_owner_and_row"),
    "learning_memory": ("tests/test_phase473_practice_learning_deletion.py::test_five_restartable_branches_are_registered_and_require_later_zero_scan", "tests/test_phase473_practice_learning_deletion.py::test_every_learning_write_builder_starts_with_exact_account_fence"),
    "ai_teacher_draft": ("tests/test_phase473_practice_learning_deletion.py::test_five_restartable_branches_are_registered_and_require_later_zero_scan", "tests/test_phase473_practice_learning_deletion.py::test_existing_assignment_and_draft_updates_require_owner_and_row"),
    "curriculum_signal": ("tests/test_phase473_practice_learning_deletion.py::test_curriculum_reconciliation_is_exact_once_across_retry", "tests/test_phase473_practice_learning_deletion.py::test_curriculum_signal_is_random_owner_manifested_and_fenced_without_student_hash"),
    "notification_device_realtime": ("tests/test_phase473_notification_deletion.py::test_strong_paginated_scans_and_scrubs_leave_only_strict_tombstones", "tests/test_phase473_notification_deletion.py::test_private_event_and_connection_write_builders_start_with_exact_fence"),
    "external_delivery_debt": ("tests/test_phase473_notification_deletion.py::test_notification_branch_is_registered_and_requires_two_later_clean_scans", "tests/test_phase473_notification_deletion.py::test_delivery_claim_rechecks_fence_immediately_before_provider_effect"),
}

EXCLUSION_RULES = {
    "teacher_application": ("teacher_application_repo.py", "teacher_application_service.py"),
    "privileged_identity_admin": ("privileged_identity_repo.py", "privileged_identity_service.py"),
    "authored_public_curriculum": ("curriculum_ops_repo.py",),
    "subscription_billing_accounting": ("subscription_service.py",),
}


@dataclass(frozen=True, slots=True)
class MutationSink:
    file: str
    symbol: str
    span: tuple[int, int]
    method: str
    normalized_ast_sha256: str


class _SinkVisitor(ast.NodeVisitor):
    def __init__(self, relative_file: str) -> None:
        self.relative_file = relative_file
        self.symbols: list[str] = []
        self.sinks: list[MutationSink] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.symbols.append(node.name)
        self.generic_visit(node)
        self.symbols.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        method = ""
        if isinstance(node.func, ast.Attribute) and node.func.attr in SINK_METHODS:
            method = node.func.attr
        elif isinstance(node.func, ast.Name) and node.func.id in WRAPPER_NAMES:
            method = node.func.id
        if method:
            normalized = _stable_ast_dump(node)
            self.sinks.append(
                MutationSink(
                    self.relative_file,
                    ".".join(self.symbols) or "<module>",
                    (node.lineno, getattr(node, "end_lineno", node.lineno)),
                    method,
                    sha256(normalized.encode()).hexdigest(),
                )
            )
        self.generic_visit(node)


def _stable_ast_dump(value: Any) -> str:
    """Serialize ASTs identically across Python 3.12 and 3.13+.

    Python 3.13 added ``show_empty=False`` to :func:`ast.dump` and changed its
    default output by omitting empty optional fields.  Phase 473 evidence was
    sealed with that representation, while Phase 474's formal runtime is
    Python 3.12.  Keep the already-reviewed bytes without making interpreter
    version part of a mutation identity.
    """
    if isinstance(value, ast.AST):
        fields: list[str] = []
        for name in value._fields:
            field = getattr(value, name, None)
            literal_none = isinstance(value, (ast.Constant, ast.MatchSingleton)) and name == "value"
            if (field is None and not literal_none) or (isinstance(field, list) and not field):
                continue
            fields.append(f"{name}={_stable_ast_dump(field)}")
        return f"{type(value).__name__}({', '.join(fields)})"
    if isinstance(value, list):
        return "[" + ", ".join(_stable_ast_dump(item) for item in value) + "]"
    return repr(value)


def _function_sources(path: Path) -> dict[str, str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=path.as_posix())
    return {
        node.name: ast.get_source_segment(source, node) or ""
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _assigned_call(source: str, *, target: str, function: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        called = value.func
        name = called.attr if isinstance(called, ast.Attribute) else (
            called.id if isinstance(called, ast.Name) else ""
        )
        if name == function and any(
            isinstance(item, ast.Name) and item.id == target for item in targets
        ):
            return True
    return False


def _typed_delivery_begin_precedes_provider(source: str) -> bool:
    """Require the typed begin result to own the claim used by the provider."""
    if any(
        token not in source
        for token in (
            "DeliveryBeginDisposition.PROVEN_ACCOUNT_DELETED",
            "DeliveryBeginDisposition.CLAIM_LOST",
            "DeliveryBeginDisposition.DEPENDENCY_RETRY",
            "inflight_claim = begin_result.claim",
        )
    ):
        return False
    tree = ast.parse(source)
    begin_line: int | None = None
    claim_line: int | None = None
    provider_line: int | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            target_names = {
                item.id for item in targets if isinstance(item, ast.Name)
            }
            value = node.value
            if (
                "begin_result" in target_names
                and isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr == "begin_delivery_effect"
            ):
                begin_line = node.lineno
            if (
                "inflight_claim" in target_names
                and isinstance(value, ast.Attribute)
                and value.attr == "claim"
                and isinstance(value.value, ast.Name)
                and value.value.id == "begin_result"
            ):
                claim_line = node.lineno
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "provider_call"
        ):
            provider_line = (
                node.lineno
                if provider_line is None
                else min(provider_line, node.lineno)
            )
    return bool(
        begin_line is not None
        and claim_line is not None
        and provider_line is not None
        and begin_line < claim_line < provider_line
    )


def validate_private_store_semantics(root: Path | str) -> None:
    """Reject reviewed race/privacy weakening independently of source digests."""
    root_path = Path(root).resolve()
    for relative, symbol_requirements in SEMANTIC_REQUIREMENTS.items():
        path = root_path / relative
        if not path.is_file():
            continue
        functions = _function_sources(path)
        if relative.endswith("account_deletion_repo.py") and path.read_text(
            encoding="utf-8"
        ).count("_valid_lifecycle_timestamp(now_iso)") < 9:
            raise ValueError(
                "reviewed private-store semantic missing: lifecycle timestamp validation"
            )
        for symbol, required in symbol_requirements.items():
            body = functions.get(symbol)
            if body is None or any(token not in body for token in required):
                raise ValueError(
                    f"reviewed private-store semantic missing: {relative}:{symbol}"
                )
        if relative.endswith("notification_service.py") and not (
            _assigned_call(
                functions["run_delivery_intent"],
                target="inflight_claim",
                function="begin_delivery_effect",
            )
            or _typed_delivery_begin_precedes_provider(
                functions["run_delivery_intent"]
            )
        ):
            raise ValueError(
                "reviewed private-store semantic missing: durable delivery begin"
            )
        if relative.endswith("websocket_service.py") and not _assigned_call(
            functions["fanout_notification_event"],
            target="batch",
            function="load_authoritative_delivery_events",
        ):
            raise ValueError(
                "reviewed private-store semantic missing: authoritative websocket load"
            )


def discover_mutation_sinks(root: Path | str) -> list[MutationSink]:
    root_path = Path(root).resolve()
    source_root = root_path / "src" / "stoa"
    if not source_root.is_dir():
        raise ValueError("root must contain src/stoa")
    sinks: list[MutationSink] = []
    mutating_files: set[str] = set()
    for path in sorted(source_root.rglob("*.py")):
        relative = path.relative_to(root_path).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError) as exc:
            raise ValueError(f"cannot parse mutating source {relative}") from exc
        visitor = _SinkVisitor(relative)
        visitor.visit(tree)
        if visitor.sinks:
            mutating_files.add(relative)
            sinks.extend(visitor.sinks)
    unknown = sorted(mutating_files - REVIEWED_MUTATING_FILES.keys())
    changed = sorted(
        relative
        for relative in mutating_files & REVIEWED_MUTATING_FILES.keys()
        if sha256((root_path / relative).read_bytes()).hexdigest()
        != REVIEWED_MUTATING_FILES[relative]
    )
    if unknown or changed:
        details = ", ".join([*unknown, *changed])
        raise ValueError(f"unreviewed mutating source: {details}")
    return sorted(sinks, key=lambda item: (item.file, item.span, item.method, item.symbol))


def _classification(sink: MutationSink) -> tuple[str, str | None, str | None]:
    name = Path(sink.file).name
    for exclusion, files in EXCLUSION_RULES.items():
        if name in files:
            return "reviewed_exclusion", None, exclusion
    if name == "security_audit_repo.py":
        return "retained_evidence", None, "security_audit"
    symbol = sink.symbol.lower()
    path = sink.file.lower()
    if "capability_repo.py" in path:
        branch = "capability_scope"
    elif any(part in path for part in ("identity_repo.py", "public_identity_repo.py", "public_identity_service.py", "routers/auth.py")):
        branch = "identity_cross_account"
    elif "moderation_repo.py" in path:
        branch = "moderation"
    elif "curriculum_analytics_repo.py" in path:
        branch = "curriculum_signal"
    elif "ai_teacher_tools_repo.py" in path:
        branch = "ai_teacher_draft"
    elif "adaptive_learning_repo.py" in path:
        branch = "learning_memory" if "memory" in symbol else "adaptive_assignment"
    elif any(part in path for part in ("practice_repo.py", "usage_ledger_repo.py", "rate_limit.py")):
        branch = "practice_progress"
    elif any(part in path for part in ("notification_repo.py", "websocket_repo.py")):
        branch = "notification_device_realtime"
    elif any(part in path for part in ("notification_service.py", "websocket_service.py", "notify_service.py")) and sink.method in {"send_email", "send_message", "post_to_connection", "urlopen"}:
        branch = "external_delivery_debt"
    elif any(part in path for part in ("notification_service.py", "websocket_service.py")):
        branch = "notification_device_realtime"
    elif "report" in path:
        if sink.method in {"send_email", "send_message"}:
            branch = "external_delivery_debt"
        elif any(word in symbol for word in ("support", "handoff", "crm", "feed")):
            branch = "support_recovery_feed"
        elif sink.method in {"put_object", "copy_object", "delete_object"} or any(word in symbol for word in ("object", "artifact", "manifest", "version")):
            branch = "report_artifacts"
        else:
            branch = "report_records"
    elif any(part in path for part in ("attachment_repo.py", "attachment_service.py")):
        branch = "conversation_messages" if any(word in symbol for word in ("conversation", "message", "chat", "command")) else "attachments"
    elif any(part in path for part in ("routers/conversations.py", "services/ai_service.py")):
        branch = "conversation_messages"
    elif "question_repo.py" in path or "routers/teachers.py" in path:
        branch = "conversation_messages" if any(word in symbol for word in ("help_request", "note")) else "question_ocr_session"
    elif "account_deletion_service.py" in path and sink.method.startswith("admin_"):
        branch = "external_delivery_debt"
    elif any(part in path for part in ("account_deletion_repo.py", "user_repo.py", "routers/admin.py")):
        branch = "account_profile"
    else:
        raise ValueError(f"unexplained mutating source file: {sink.file}:{sink.symbol}")
    return "private_store", branch, None


def _sink_kind(method: str) -> str:
    if method in {"put_item", "update_item", "delete_item", "batch_write_item", "transact_write_items", "transact", "_transact"}:
        return "dynamodb_mutation"
    if method in {"put_object", "copy_object", "delete_object", "create_multipart_upload", "upload_part", "complete_multipart_upload", "abort_multipart_upload"}:
        return "s3_mutation"
    if method in {"send_email", "send_raw_email"}:
        return "ses_send"
    if method in {"send_message", "delete_message"}:
        return "sqs_mutation"
    if method.startswith("admin_"):
        return "cognito_mutation"
    if method == "post_to_connection":
        return "websocket_send"
    if method == "urlopen":
        return "push_http_send"
    return "private_provider_completion"


def build_inventory(root: Path | str) -> dict[str, Any]:
    root_path = Path(root).resolve()
    validate_private_store_semantics(root_path)
    sinks = discover_mutation_sinks(root_path)
    rows: list[dict[str, Any]] = []
    exclusions: dict[str, set[str]] = {name: set() for name in EXCLUSION_RULES}
    represented: set[str] = set()
    for index, sink in enumerate(sinks, start=1):
        classification, branch_id, policy_class = _classification(sink)
        if classification == "reviewed_exclusion":
            assert policy_class is not None
            exclusions[policy_class].add(sink.file)
        if branch_id:
            represented.add(branch_id)
            contract = BRANCH_CONTRACTS[branch_id]
            purge_selector, no_resurrection_selector = SELECTORS[branch_id]
            subfamily = contract["subfamilies"][0]
            roots = contract["roots"]
        else:
            purge_selector = "tests/test_authorization_audit.py::test_denial_persists_redacted_distinct_resource_events_and_idempotent_replay"
            no_resurrection_selector = "tests/test_authorization_audit.py::test_denial_persists_redacted_distinct_resource_events_and_idempotent_replay"
            subfamily = policy_class or "reviewed"
            roots = [policy_class or "reviewed-nonstudent"]
        row_id = sha256(f"{sink.file}:{sink.symbol}:{sink.span}:{sink.method}:{sink.normalized_ast_sha256}".encode()).hexdigest()[:24]
        rows.append(
            {
                "row_id": row_id,
                "source": {"file": sink.file, "symbol": sink.symbol, "span": list(sink.span), "normalized_ast_sha256": sink.normalized_ast_sha256},
                "sink_kind": _sink_kind(sink.method),
                "client_method": sink.method,
                "store": {"roots": roots, "pk_schema": "source-declared owner partition", "sk_or_object_prefix": subfamily},
                "private_value_provenance": ["student", "question", "conversation", "model", "teacher", "report"],
                "owner_resolver": "authoritative strong source row or immutable owner manifest",
                "fence_checkpoint": "USER#{owner_id}/ACCOUNT_FENCE:active:generation",
                "classification": classification,
                "policy_class": policy_class,
                "branch_id": branch_id,
                "subfamily": subfamily,
                "field_scrub_allowlist": ["opaque_id", "status", "created_at", "deleted_at", "privacy_generation"],
                "tombstone_allowlist": ["PK", "SK", "entity_type", "schema_version", "status", "privacy_generation", "created_at", "deleted_at"],
                "cursor_schema": {"type": "strong_base_table", "fields": ["PK", "SK"], "complete_scan_required": True},
                "debt_schema": {"item": "opaque row/operation identity", "ordinary_zero_required": True, "policy_debt_separate": True},
                "quiescence": {"authoritative_zero_epochs": 2, "current_generation_only": True},
                "purge_selector": purge_selector,
                "no_resurrection_selector": no_resurrection_selector,
                "lower_fake_target": f"{sink.file}:{sink.symbol}:{sink.method}",
                "mutation_contract": {
                    "owner_scope": "authoritative persisted owner or immutable sealed global classification",
                    "cas_facts": [
                        "account_fence_generation",
                        "lease_owner",
                        "command_or_intent_version",
                        "scope_or_result_digest",
                    ],
                    "lifecycle_facts": [
                        "status",
                        "lease_expires_at",
                        "updated_at",
                        "effect_state",
                    ],
                    "payload_policy": "digests/counts/status only; no event payload, identifier, endpoint, token, provider response, or exception",
                    "finding_ids": [
                        finding["finding_id"]
                        for finding in FINDING_REGISTRY
                        if any(
                            symbol.rsplit(".", 1)[-1] in sink.symbol
                            for symbol in finding["source_symbols"]
                        )
                    ],
                },
                "requirement_ids": ["V9PRIV-01", "V9PRIV-02", "V9PRIV-03"],
                "decision_ids": ["D-10", "T-473-35-01", "T-473-35-03"],
            }
        )
    missing = set(BRANCH_IDS) - represented
    if missing:
        raise ValueError(f"branches have no source-backed mutation: {sorted(missing)}")
    source_files = [
        {"file": relative, "sha256": sha256((root_path / relative).read_bytes()).hexdigest()}
        for relative in sorted({sink.file for sink in sinks})
    ]
    registry = [
        {
            "branch_id": branch_id,
            "handler_version": "473-35.v1",
            "required_roots": BRANCH_CONTRACTS[branch_id]["roots"],
            "subfamilies": BRANCH_CONTRACTS[branch_id]["subfamilies"],
            "purge_selector": SELECTORS[branch_id][0],
            "no_resurrection_selector": SELECTORS[branch_id][1],
        }
        for branch_id in BRANCH_IDS
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "branch_ids": list(BRANCH_IDS),
        "branch_registry": registry,
        "source_files": source_files,
        "finding_registry": [dict(finding) for finding in FINDING_REGISTRY],
        "rows": rows,
        "exclusions": [
            {"exclusion_class": name, "source_files": sorted(files), "review": "non-student principal/content source semantics"}
            for name, files in sorted(exclusions.items())
        ],
    }


def build_evidence_policy() -> dict[str, Any]:
    common = {"legal_basis": "legitimate_security_and_accounting_operations", "ttl_seconds": 31_536_000, "access_policy": "admin_capability_and_audited_service_only", "mutable": False, "unbounded_retention": False}
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "classes": [
            {**common, "class_id": "usage_accounting", "roots": ["USAGE#", "USAGE_LEDGER#"], "allowed_fields": ["PK", "SK", "entity_type", "schema_version", "operation_id", "action", "period", "count", "status", "created_at", "expires_at", "ttl", "legal_basis"]},
            {**common, "class_id": "security_audit", "roots": ["SECURITY_AUDIT#"], "allowed_fields": ["PK", "SK", "entity_type", "schema_version", "keyed_actor_fingerprint", "keyed_resource_fingerprint", "action", "decision", "category", "correlation_id", "created_at", "expires_at", "ttl", "legal_basis"]},
            {**common, "class_id": "category_only_logs", "roots": ["application_log"], "allowed_fields": ["category", "class", "size_bucket", "count", "correlation_id", "created_at", "expires_at", "ttl", "legal_basis"]},
        ],
        "forbidden_field_markers": ["answer", "name", "email", "subject", "note", "content", "hash", "bucket", "key", "etag", "version", "upload_id", "token", "endpoint", "address", "body"],
        "external_receipt_statuses": ["accepted", "delivered", "provider_acceptance_unknown"],
        "external_receipt_claim": "outside_backend_purge_authority",
    }


def validate_evidence_policy(policy: dict[str, Any]) -> None:
    if policy.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise ValueError("invalid evidence policy schema")
    forbidden = {str(value).lower() for value in policy.get("forbidden_field_markers", [])}
    classes = policy.get("classes")
    if not isinstance(classes, list) or not classes:
        raise ValueError("evidence classes are required")
    seen: set[str] = set()
    exact_forbidden = forbidden | {"s3_key", "version_id", "content_hash"}
    for evidence_class in classes:
        class_id = evidence_class.get("class_id")
        if not isinstance(class_id, str) or not class_id or class_id in seen:
            raise ValueError("invalid evidence class")
        seen.add(class_id)
        if not isinstance(evidence_class.get("legal_basis"), str) or not evidence_class["legal_basis"]:
            raise ValueError("evidence legal basis is required")
        ttl = evidence_class.get("ttl_seconds")
        if type(ttl) is not int or ttl <= 0 or ttl > 31_536_000:
            raise ValueError("evidence TTL must be bounded")
        if not isinstance(evidence_class.get("access_policy"), str) or not evidence_class["access_policy"]:
            raise ValueError("evidence access policy is required")
        if evidence_class.get("mutable") is not False or evidence_class.get("unbounded_retention") is not False:
            raise ValueError("evidence retention must be immutable and bounded")
        fields = evidence_class.get("allowed_fields")
        if not isinstance(fields, list) or any(not isinstance(field, str) or not field for field in fields):
            raise ValueError("evidence field allowlist is required")
        lowered = {field.lower() for field in fields}
        if lowered & exact_forbidden:
            raise ValueError("private field is forbidden in retained evidence")
    if policy.get("external_receipt_claim") != "outside_backend_purge_authority":
        raise ValueError("external receipt authority must remain explicit")


def _render(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _paths(root: Path, output: str | None, evidence_output: str | None) -> tuple[Path, Path]:
    return (
        Path(output) if output else root / "docs/security/phase-473-private-store-inventory.json",
        Path(evidence_output) if evidence_output else root / "docs/security/phase-473-retained-evidence-policy.json",
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(_default_root()))
    parser.add_argument("--output")
    parser.add_argument("--evidence-output")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root).resolve()
    output, evidence_output = _paths(root, args.output, args.evidence_output)
    try:
        inventory = build_inventory(root)
        policy = build_evidence_policy()
        validate_evidence_policy(policy)
        rendered_inventory, rendered_policy = _render(inventory), _render(policy)
        if args.check:
            if output.read_bytes() != rendered_inventory:
                raise ValueError(f"checked inventory is stale: {output}")
            if evidence_output.read_bytes() != rendered_policy:
                raise ValueError(f"checked evidence policy is stale: {evidence_output}")
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            evidence_output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(rendered_inventory)
            evidence_output.write_bytes(rendered_policy)
    except (OSError, ValueError) as exc:
        print(f"phase473-private-store-inventory: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
