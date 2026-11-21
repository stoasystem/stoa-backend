"""Every kind of row the code writes is deleted by a branch, or kept on purpose (#534).

Account deletion first *finds* an account's rows - its derived partitions and
the ones registered under it, which `test_owner_registry_unfenced_writers`
keeps honest - and then runs each branch in
`account_deletion_service.BRANCH_HANDLERS` over them. Each branch picks the
rows it acts on by its own test: an `entity_type`, a key prefix, an owner
field. A row no branch picks outlives the account, and nothing failed. Voice
consent (#476) and the daily transcription counter (#477) were added to a
branch by hand; this test is there for the next kind of row.

It works by `entity_type`, the name every kind of row is written with:

1. `written_entity_types` reads `src/stoa` and collects every `entity_type` a
   row can be written with: the value under an `"entity_type"` key of a dict
   literal, an `entity_type=` keyword argument, and the value an update sets
   with `SET entity_type = :x`. A name or `module.NAME` is resolved to the
   string it stands for, and `a if c else b` to both. A writer whose value it
   cannot resolve (an f-string, a parameter) must be in `UNRESOLVED_WRITERS`,
   saying what it writes.
2. Each type is listed once: in `deleted_by_branch()`, with the branch that
   picks it and one row of that type belonging to the account, keyed the way
   its writer keys it; or in `KEPT`, with why no branch picks it. A type in
   neither fails; a listed type the code no longer writes fails as stale,
   unless it is in `NO_LONGER_WRITTEN`: rows the code stopped writing but that
   may still be stored, so their branch still has to delete them. Such a type
   stays in `deleted_by_branch()` with a row keyed as its old writer keyed it,
   and fails if anything writes it again.
3. The `deleted_by_branch()` rows are stored and every branch is run over the
   account the way a registry-path deletion runs it, with the branches' row
   operations replaced by a recorder. Each row must reach the branch it is
   listed under, so a listing cannot name a branch that does not pick the row.
   A branch that acts on rows through an operation the recorder does not
   replace (`picks_by_branch`) records nothing: add the operation there.

A new kind of row therefore fails here until someone decides: make a branch
pick it and list it with a row of its shape, or say in `KEPT` why it stays.
Rows written with no `entity_type` at all are outside this test.

Reasons in `KEPT`:
- deletion_flow: rows the deletion machinery writes about its own work
  (commands, fences, debts, tombstones, the owner registry, release progress).
- removed_with: no branch picks the row itself; the branch that settles
  another row removes it too (the comment says which).
- not_deletion_data: a class the deletion inventory excludes (billing,
  authored curriculum, teacher applications, privileged identity, security
  audit), or a row that names no account.
- expires: a short-lived row that goes by its own `expires_at` TTL, soon
  enough that deletion leaves it to that (the comment gives how long).
- no_caller: nothing in `src/stoa` calls its writers. If one gets a caller,
  decide again.
- gap: the account's, no branch picks it, and no TTL settles it. Listed so the
  question is visible rather than silent; see #534.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]

type Function = ast.FunctionDef | ast.AsyncFunctionDef

# `SET entity_type = :entity` (or `#entity_type`, or `if_not_exists(...)`) in an
# update expression; a condition (`... AND entity_type = :entity`) only reads it.
_SET_ENTITY = re.compile(
    r"(?:\bSET\b|,)\s*#?entity_type\s*=\s*"
    r"(?:if_not_exists\(\s*#?entity_type\s*,\s*)?(:\w+)"
)


def _module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root / "src").with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


class _Modules:
    """The modules under `src/stoa`: their trees, string constants and imports."""

    def __init__(self, root: Path) -> None:
        self.trees: dict[str, tuple[str, ast.Module]] = {}
        self.constants: dict[str, dict[str, str]] = {}
        self.imports: dict[str, dict[str, tuple[str, str | None]]] = {}
        for path in sorted((root / "src" / "stoa").rglob("*.py")):
            name = _module_name(root, path)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            self.trees[name] = (path.relative_to(root).as_posix(), tree)
            self.constants[name] = constants = {}
            self.imports[name] = imports = {}
            package = name.split(".") if path.name == "__init__.py" else name.split(".")[:-1]
            for node in tree.body:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    value = node.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        for target in targets:
                            if isinstance(target, ast.Name):
                                constants[target.id] = value.value
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    if node.level:
                        stem = package[: len(package) - node.level + 1]
                        base = ".".join([*stem, *([node.module] if node.module else [])])
                    for alias in node.names:
                        imports[alias.asname or alias.name] = (base, alias.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports[alias.asname or alias.name] = (alias.name, None)

    def resolve_all(self, module: str, node: ast.expr) -> set[str] | None:
        """The strings `node` can stand for (both arms of `a if c else b`), or None."""
        if isinstance(node, ast.IfExp):
            body = self.resolve_all(module, node.body)
            orelse = self.resolve_all(module, node.orelse)
            return None if body is None or orelse is None else body | orelse
        value = self._resolve(module, node)
        return None if value is None else {value}

    def _resolve(self, module: str, node: ast.expr) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in self.constants[module]:
                return self.constants[module][node.id]
            source = self.imports[module].get(node.id)
            if source and source[1] and source[0] in self.constants:
                return self.constants[source[0]].get(source[1])
            return None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            source = self.imports[module].get(node.value.id)
            if source:
                target = source[0] if source[1] is None else f"{source[0]}.{source[1]}"
                if target in self.constants:
                    return self.constants[target].get(node.attr)
        return None


def _written_values(scope: ast.AST) -> Iterator[ast.expr]:
    """Every expression `scope` writes as an `entity_type`."""
    placeholders: set[str] = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "entity_type":
                    yield value
        elif isinstance(node, ast.keyword) and node.arg == "entity_type":
            yield node.value
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            placeholders.update(_SET_ENTITY.findall(node.value))
    if placeholders:
        for node in ast.walk(scope):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value in placeholders:
                        yield value


def written_entity_types(root: Path) -> tuple[dict[str, set[str]], set[str]]:
    """`entity_type` -> its writers (`file::function`); and the unresolved writers."""
    modules = _Modules(root)
    found: dict[str, set[str]] = {}
    unresolved: set[str] = set()
    for module, (relative, tree) in modules.trees.items():
        functions: list[Function] = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        # A function nested in another is read as part of the outer one.
        nested = {
            id(inner)
            for function in functions
            for inner in ast.walk(function)
            if inner is not function and isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        # Module level too (a counter kind declared as a constant).
        top = ast.Module(
            body=[
                node
                for node in tree.body
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            ],
            type_ignores=[],
        )
        scopes: list[tuple[str, ast.AST]] = [("<module>", top)]
        scopes.extend((f.name, f) for f in functions if id(f) not in nested)
        for name, scope in scopes:
            writer = f"{relative}::{name}"
            for value in _written_values(scope):
                resolved = modules.resolve_all(module, value)
                if resolved is None:
                    unresolved.add(writer)
                for entity_type in resolved or ():
                    found.setdefault(entity_type, set()).add(writer)
    return found, unresolved


# Writers whose `entity_type` the scan cannot resolve, and what they write.
UNRESOLVED_WRITERS: dict[str, str] = {
    # `{entity}_deletion_tombstone`, `{entity_type}_deletion_tombstone`: the
    # tombstones the deletion leaves in place of what it removed.
    "src/stoa/db/repositories/account_deletion_repo.py::replace_with_deletion_tombstone": (
        "deletion_flow"
    ),
    "src/stoa/db/repositories/adaptive_learning_repo.py::scrub_adaptive_private_row": (
        "deletion_flow"
    ),
    "src/stoa/db/repositories/notification_repo.py::_replace_notification_owner_tombstone": (
        "deletion_flow"
    ),
    # A parameter: its callers pass `entity_type="billing_projection"` and the
    # like, which the scan reads at the call.
    "src/stoa/db/repositories/billing_fact_repo.py::_activation_item": "keyword_at_callers",
    # `kind.entity_type`: the `CounterKind(entity_type=...)` constants in the
    # same module, which the scan reads.
    "src/stoa/db/repositories/weekly_counter.py::write": "keyword_at_callers",
}


KEPT: dict[str, str] = {
    # -- deletion_flow ------------------------------------------------------------
    "account_deletion_command": "deletion_flow",
    "account_deletion_pending": "deletion_flow",
    "account_deletion_scan_cursor": "deletion_flow",
    "account_fence": "deletion_flow",
    "provider_identity_revoke_debt": "deletion_flow",
    "identity_deletion_evidence": "deletion_flow",
    "teacher_session_deletion_tombstone": "deletion_flow",
    "ai_teacher_draft_deletion_tombstone": "deletion_flow",
    "practice_deletion_tombstone": "deletion_flow",
    "practice_accounting_tombstone": "deletion_flow",
    # Removed by `account_deletion_repo.delete_owner_registry` once the deletion
    # is final; until then it is how the deletion finds the account's rows.
    "owner_registry": "deletion_flow",
    "owner_registry_sweep_run": "deletion_flow",
    # The record that a resource's attachments were released (owner, resource
    # id, cursor, status): written by the release, which account deletion runs
    # too. It holds no content and stays as the release's receipt.
    "attachment_retention_fence": "deletion_flow",
    # Written by `reconcile_curriculum_signal` while the curriculum branch runs.
    "curriculum_signal_reconciliation": "deletion_flow",
    # -- removed_with -------------------------------------------------------------
    # Released by the profile's deletion tombstone, in the same transaction
    # (`account_deletion_repo._email_claim_release`).
    "account_email_claim": "removed_with",
    # Reconciled through the owner's `curriculum_signal_owner_manifest` row,
    # which the curriculum_signal branch picks.
    "curriculum_analytics_signal": "removed_with",
    # -- not_deletion_data --------------------------------------------------------
    # Billing, excluded from deletion as `subscription_billing_accounting`.
    "allowance_plan": "not_deletion_data",
    "beneficiary_grant": "not_deletion_data",
    "billing_activation_receipt": "not_deletion_data",
    "billing_event_inbox": "not_deletion_data",
    "billing_object_fact": "not_deletion_data",
    "billing_projection": "not_deletion_data",
    "billing_reconciliation_lease": "not_deletion_data",
    "billing_semantic_dedupe": "not_deletion_data",
    "checkout_command": "not_deletion_data",
    "checkout_open_guard": "not_deletion_data",
    "checkout_public_lookup": "not_deletion_data",
    "paid_grant_history": "not_deletion_data",
    "paid_transition": "not_deletion_data",
    "subscription_billing": "not_deletion_data",
    "subscription_billing_event": "not_deletion_data",
    "subscription_billing_event_dedupe": "not_deletion_data",
    "subscription_billing_provider_lookup": "not_deletion_data",
    "subscription_billing_refund_idempotency": "not_deletion_data",
    "subscription_payment_rollout": "not_deletion_data",
    "subscription_request": "not_deletion_data",
    "subscription_request_event": "not_deletion_data",
    "subscription_request_open_guard": "not_deletion_data",
    # Authored curriculum, excluded as `authored_public_curriculum`.
    "curriculum_audit_event": "not_deletion_data",
    "curriculum_migration_evidence": "not_deletion_data",
    "curriculum_pointer": "not_deletion_data",
    "curriculum_publish_manifest": "not_deletion_data",
    "curriculum_version": "not_deletion_data",
    "practice_challenge_pointer": "not_deletion_data",
    # Teacher applications, excluded as `teacher_application`.
    "teacher_activation_command": "not_deletion_data",
    "teacher_activation_invitation": "not_deletion_data",
    "teacher_application_review": "not_deletion_data",
    "teacher_application_version": "not_deletion_data",
    # Excluded as `privileged_identity_admin`.
    "privileged_identity_command": "not_deletion_data",
    # The security audit trail.
    "security_audit_event": "not_deletion_data",
    "authorization_probe_aggregate": "not_deletion_data",
    # Names no account: a count per curriculum item; the next free number per
    # role and year; a count per subject and knowledge point, personal-looking
    # names refused (`knowledge_gap_repo.looks_personal`), 180 days; an
    # anonymous visitor's event by client session id, 90 days; a hashed request
    # source's attempts; a weekly count under a digest of the support scope.
    "curriculum_analytics_metric": "not_deletion_data",
    "account_number_sequence": "not_deletion_data",
    "knowledge_gap": "not_deletion_data",
    "analytics_event": "not_deletion_data",
    "invitation_claim_throttle": "not_deletion_data",
    "source_rate_window": "not_deletion_data",
    "teacher_support_counter": "not_deletion_data",
    # An invitation id and token digest only; once the invitation row is gone
    # (identity_cross_account) it leads nowhere, which reads as no invitation.
    "account_invitation_pointer": "not_deletion_data",
    # A number is claimed for good so it is never handed to another account;
    # the row holds the number, role, year and the (now unused) account id.
    "account_number": "not_deletion_data",
    # -- expires ------------------------------------------------------------------
    "password_change_code": "expires",  # 10 minutes
    "password_change_send_quota": "expires",  # 1 hour
    "parent_link_request_quota": "expires",  # 2 days
    "teacher_seen": "expires",  # 1 day
    # Keyed by the provider identity; expires when the sign-in would have.
    "auth_sign_in_revocation": "expires",
    # -- no_caller (see test_owner_registry_unfenced_writers) ---------------------
    "AUDIT_RETENTION_EVENT": "no_caller",
    "AUDIT_RETENTION_IMMUTABLE_MANIFEST": "no_caller",
    "LEGAL_HOLD_AUDIT_EVENT": "no_caller",
    "LEGAL_HOLD_METADATA": "no_caller",
    "LEGAL_HOLD_REVIEW_METADATA": "no_caller",
    "REPORT_ARTIFACT_EDIT_DRAFT": "no_caller",
    "REPORT_ARTIFACT_ROLLBACK_PREVIEW": "no_caller",
    "REPORT_EDIT_DRAFT": "no_caller",
    "RETENTION_APPROVAL_AUDIT_EVENT": "no_caller",
    "RETENTION_APPROVAL_METADATA": "no_caller",
    "SUPPORT_CRM_MESSAGE_EVENT": "no_caller",
    "SUPPORT_CRM_MESSAGE_FEED": "no_caller",
    "SUPPORT_HANDOFF_AUDIT_EVENT": "no_caller",
    "SUPPORT_HANDOFF_DELIVERY": "no_caller",
    "SUPPORT_HANDOFF_DELIVERY_AUDIT_EVENT": "no_caller",
    "SUPPORT_HANDOFF_DELIVERY_FEED": "no_caller",
}

_REASONS = {"deletion_flow", "removed_with", "not_deletion_data", "expires", "no_caller", "gap"}


# Types nothing writes any more whose stored rows may still be in the table:
# their branch keeps deleting them with the account. Each says what retired it.
NO_LONGER_WRITTEN: dict[str, str] = {
    # #518 retired the teacher assistance summary
    # (`GET /teachers/questions/{id}/assistance-summary`), its only writer.
    "teacher_assistance_summary_seed": "#518",
    # #518 retired the routes that made and reviewed AI exercise drafts. Drafts
    # already stored can still be set as an assignment (`sourceType: ai_draft`),
    # which only updates them (`ai_teacher_tools_service.mark_delivered`).
    "ai_teacher_draft": "#518",
}


# -- rows the branches pick -----------------------------------------------------------

ACCOUNT = "account-534"
OTHER = "someone-else-534"


def _row(key: Mapping[str, str], entity_type: str, **fields: Any) -> dict[str, Any]:
    return {**key, "entity_type": entity_type, **fields}


def deleted_by_branch() -> dict[str, tuple[str, dict[str, Any]]]:
    """`entity_type` -> (the branch that picks it, one such row of `ACCOUNT`'s).

    Each row is keyed and owned the way its writer keys and owns it - with the
    writer's own key function where there is one - since that is what the
    branches test.
    """
    from stoa.db.repositories import (
        account_invitation_repo,
        ai_teacher_tools_repo,
        allowance_repo,
        asked_knowledge_repo,
        attachment_repo,
        capability_repo,
        identity_repo,
        notification_repo,
        parent_link_repo,
        practice_repo,
        review_repo,
        upload_code_repo,
        voice_question_consent_repo,
        voice_transcription_usage_repo,
        websocket_repo,
        weekly_counter,
    )
    from stoa.services import help_requests, teacher_support_allowance_service, usage_period
    from stoa.services.ask_question import _store as ask_store
    from stoa.services.learning_session import _store as conversation_store

    owner = {"owner_id": ACCOUNT, "student_id": ACCOUNT}
    conversation = conversation_store.conv_pk("conv-534")
    quiz = practice_repo.quiz_partition(ACCOUNT)
    activity = practice_repo.activity_partition(ACCOUNT)
    capability = ("teacher_identity_reviewer", "global")
    rows: dict[str, tuple[str, dict[str, Any]]] = {}

    def add(branch: str, row: dict[str, Any]) -> None:
        rows[row["entity_type"]] = (branch, row)

    # account_profile
    add("account_profile", _row(
        parent_link_repo.student_side_key(ACCOUNT, OTHER), "parent_student_link",
        student_id=ACCOUNT, parent_id=OTHER))
    add("account_profile", _row(
        {"PK": f"USER#{ACCOUNT}", "SK": f"{usage_period.RECORD_SK_PREFIX}2026-11-01#r1"},
        "usage_period_record", user_id=ACCOUNT))
    add("account_profile", _row(
        voice_question_consent_repo.state_key(ACCOUNT), "voice_question_consent",
        student_id=ACCOUNT, changed_by=OTHER))
    add("account_profile", _row(
        voice_question_consent_repo.change_key(ACCOUNT, "2026-11-01T00:00:00+00:00", "c1"),
        "voice_question_consent_change", student_id=ACCOUNT, changed_by=OTHER))
    add("account_profile", _row(
        voice_transcription_usage_repo.day_key(ACCOUNT, "2026-11-01"),
        "voice_transcription_day", student_id=ACCOUNT))
    add("account_profile", _row(
        allowance_repo._effect_key(ACCOUNT, "b" * 64), "allowance_effect",
        beneficiary_id=ACCOUNT, plan_id="plan-1"))
    add("account_profile", _row(
        allowance_repo._evidence_key(ACCOUNT, "c" * 64), "provider_usage_evidence",
        beneficiary_id=ACCOUNT, effect_id="b" * 64))
    add("account_profile", _row(
        {"PK": f"{weekly_counter.TOKENS.namespace}#{ACCOUNT}", "SK": "WEEK#2026-W45"},
        weekly_counter.TOKENS.entity_type, beneficiary_id=ACCOUNT))
    add("account_profile", _row(
        {"PK": "TEACHER_SUPPORT_CASE#case-digest", "SK": "ADMISSION"},
        "teacher_support_admission", beneficiary_id=ACCOUNT, parent_id=OTHER))
    add("account_profile", _row(
        {"PK": f"USER#{ACCOUNT}", "SK": teacher_support_allowance_service.ASSIGNED_ALLOWANCE_SK},
        "teacher_support_assigned_allowance", student_id=ACCOUNT, weekly_cases=3))
    # identity_cross_account
    add("identity_cross_account", _row(
        {"PK": "IDENTITY#issuer#subject", "SK": "BINDING"}, "identity_binding",
        user_id=ACCOUNT))
    add("identity_cross_account", _row(
        {"PK": f"USER#{ACCOUNT}", "SK": "IDENTITY#issuer#subject"}, "user_identity_inventory",
        user_id=ACCOUNT, binding_pk="IDENTITY#issuer#subject"))
    add("identity_cross_account", _row(
        {"PK": "PUBLIC_IDENTITY#digest", "SK": "COMMAND"}, "public_identity_command",
        user_id=ACCOUNT))
    add("identity_cross_account", _row(
        account_invitation_repo.invitation_key("token-digest"), "account_invitation",
        account_id=ACCOUNT))
    add("identity_cross_account", _row(
        identity_repo._sign_in_session_key(ACCOUNT, "jti-1"), "auth_sign_in_session"))
    # capability_scope
    add("capability_scope", _row(
        capability_repo._pointer_key(ACCOUNT, *capability), "capability_grant_current",
        user_id=ACCOUNT))
    add("capability_scope", _row(
        capability_repo._version_key(ACCOUNT, *capability, 1, "g1", 1),
        "capability_grant_revision", user_id=ACCOUNT))
    # attachments
    add("attachments", _row(attachment_repo.attachment_key("att-1"), "attachment", **owner))
    add("attachments", _row(
        attachment_repo.association_key("att-1", "conversation", "conv-534", "m1"),
        "attachment_association", **owner))
    add("attachments", _row({"PK": "UPLOAD#up-1", "SK": "META"}, "upload_intent", **owner))
    add("attachments", _row(
        upload_code_repo.code_key("code-1"), "upload_code", owner_id=ACCOUNT))
    # moderation: an image case is owned by its uploader (#139); its events by the case.
    add("moderation", _row(
        {"PK": "MODERATION#case-1", "SK": "SUMMARY"}, "moderation_case",
        case_id="case-1", surface="image_upload", student_id=ACCOUNT, privacy_generation=1))
    add("moderation", _row(
        {"PK": "MODERATION#case-1", "SK": "EVENT#e1"}, "moderation_event",
        case_id="case-1", student_id=ACCOUNT))
    # report_records / report_artifacts
    add("report_records", _row(
        {"PK": f"USER#{ACCOUNT}", "SK": "REPORT_EMAIL#op-1"}, "report_email_intent",
        owner_id=ACCOUNT))
    add("report_records", _row(
        {"PK": "REPORT#rep-1", "SK": "AUDIT#2026-11-01T00:00:00+00:00#e1"},
        "REPORT_AUDIT_EVENT", student_id=ACCOUNT))
    add("report_records", _row(
        {"PK": "REPORT_RECOVERY_JOB#job-1", "SK": "SUMMARY"}, "REPORT_RECOVERY_JOB",
        job_id="job-1", filters={"student_id": ACCOUNT}))
    add("report_records", _row(
        {"PK": "REPORT_RECOVERY_JOB#job-1", "SK": "TARGET#00000#t1"},
        "REPORT_RECOVERY_JOB_TARGET", job_id="job-1", student_id=ACCOUNT))
    add("report_records", _row(
        {"PK": "REPORT_RECOVERY_JOB#job-1", "SK": "AUDIT#2026-11-01T00:00:00+00:00#e1"},
        "REPORT_RECOVERY_JOB_AUDIT_EVENT", job_id="job-1", metadata={"student_id": ACCOUNT}))
    add("report_artifacts", _row(
        {"PK": f"USER#{ACCOUNT}", "SK": "REPORT_OBJECT#op-1#pdf"}, "report_object_intent",
        owner_id=ACCOUNT, version_id="v1"))
    # conversation_messages
    add("conversation_messages", _row(
        {"PK": conversation, "SK": "CONV"}, "conversation", **owner))
    add("conversation_messages", _row(
        {"PK": conversation, "SK": conversation_store.msg_sk("m1")}, "conversation_message",
        **owner))
    add("conversation_messages", _row(
        ask_store.message_command_key("conv-534", "idem-1"), "message_command", **owner))
    add("conversation_messages", _row(
        {"PK": conversation, "SK": "NOTE#n1"}, "conversation_teacher_note",
        teacher_id=OTHER, **owner))
    add("conversation_messages", _row(
        help_requests.key("conv-534"), "help_request", **owner))
    add("conversation_messages", _row(
        asked_knowledge_repo.record_key("conv-534", "m1"), "asked_knowledge_points", **owner))
    add("conversation_messages", _row(
        ask_store.chat_quota_operation_key(ACCOUNT, "cmd-1"), "chat_quota_operation",
        owner_id=ACCOUNT))
    add("conversation_messages", _row(
        {"PK": f"USAGE_LEDGER#{ACCOUNT}", "SK": "EVENT#ask#2026-11#k1"}, "usage_ledger_event",
        student_id=ACCOUNT))
    # practice_progress
    add("practice_progress", _row(
        {"PK": f"USAGE#{ACCOUNT}", "SK": "VOICE_QUOTA_OP#op-1"}, "rate_admission_operation",
        owner_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": f"USAGE#{ACCOUNT}", "SK": "VOICE#2026-11"}, "rate_counter"))
    add("practice_progress", _row(
        {"PK": f"PROGRESS#{ACCOUNT}", "SK": "LESSON#l1"}, "practice_progress",
        student_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": practice_repo.study_day_partition(ACCOUNT), "SK": "STUDY_DAY#2026-11-01"},
        "study_day", student_id=ACCOUNT, user_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": activity, "SK": "LIT_UNIT#u1"}, "lit_unit", student_id=ACCOUNT, user_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": activity, "SK": "LIT_LEDGER"}, "lit_ledger", student_id=ACCOUNT, user_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": quiz, "SK": "QUIZ_PAPER#q1"}, "practice_quiz_paper", student_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": quiz, "SK": "QUIZ_CREDENTIAL#c1"}, "practice_quiz_credential", student_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": quiz, "SK": "STAR_QUIZ_COOLDOWN#u1#q1"}, "practice_star_quiz_cooldown",
        student_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": quiz, "SK": "STAR_QUIZ_PASS#u1"}, "practice_star_quiz_pass", student_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": review_repo.card_partition(ACCOUNT), "SK": "CARD#ch1"}, "review_card",
        student_id=ACCOUNT, user_id=ACCOUNT))
    # adaptive_assignment / learning_memory / ai_teacher_draft / curriculum_signal
    add("adaptive_assignment", _row(
        {"PK": "ASSIGNMENT#a1", "SK": "META"}, "learning_assignment", student_id=ACCOUNT))
    add("learning_memory", _row(
        {"PK": f"LEARNING_MEMORY#{ACCOUNT}", "SK": "SUBJECT#math#TOPIC#t1"},
        "learning_memory_snapshot", student_id=ACCOUNT))
    add("ai_teacher_draft", _row(
        {"PK": ai_teacher_tools_repo.draft_pk("d1"), "SK": "META"}, "ai_teacher_draft",
        student_id=ACCOUNT))
    add("curriculum_signal", _row(
        {"PK": f"CURRICULUM_SIGNAL_OWNER#{ACCOUNT}", "SK": "SIGNAL#s1"},
        "curriculum_signal_owner_manifest", signal_id="s1"))
    # notification_device_realtime
    add("notification_device_realtime", _row(
        {"PK": notification_repo.notification_pk("e1"), "SK": "META"}, "notification_event",
        owner_id=ACCOUNT))
    add("notification_device_realtime", _row(
        {"PK": notification_repo.preference_pk(ACCOUNT), "SK": "CURRENT"},
        "notification_preference", user_id=ACCOUNT, owner_id=ACCOUNT))
    add("notification_device_realtime", _row(
        {"PK": notification_repo.push_token_pk(ACCOUNT, "ref-1"), "SK": "TOKEN"},
        "notification_push_token", user_id=ACCOUNT, owner_id=ACCOUNT))
    add("notification_device_realtime", _row(
        {"PK": notification_repo.delivery_intent_pk(ACCOUNT),
         "SK": notification_repo.delivery_intent_sk("op-1")},
        "notification_delivery_intent", owner_id=ACCOUNT))
    add("notification_device_realtime", _row(
        # Keyed as `put_summary_seed` keyed it before #518.
        {"PK": "ASSISTANCE_SUMMARY#s1", "SK": "META"},
        "teacher_assistance_summary_seed", **owner))
    add("notification_device_realtime", _row(
        {"PK": notification_repo.payment_expiry_reminder_pk(ACCOUNT),
         "SK": notification_repo.payment_expiry_reminder_sk("a" * 64)},
        "payment_expiry_reminder", owner_id=ACCOUNT, parent_id=ACCOUNT))
    add("notification_device_realtime", _row(
        {"PK": websocket_repo.connection_pk("ws-1"), "SK": "META"}, "websocket_connection",
        user_id=ACCOUNT, owner_id=ACCOUNT))
    return rows


class _PurgeDone(dict[str, int]):
    status = "complete"


class _AnyClient:
    """Any external client call answers an empty success."""

    class exceptions:  # noqa: N801 - the boto3 client's attribute name
        class UserNotFoundException(Exception):  # noqa: N818 - Cognito's name
            pass

    def __getattr__(self, _name: str) -> Any:
        return lambda *_args, **_kwargs: {}


def picks_by_branch(
    monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]
) -> dict[str, set[tuple[str, str]]]:
    """Run every branch over `ACCOUNT` with `rows` stored: the keys each one picked.

    The operations a branch hands its rows to are replaced by a recorder, so
    each branch reads what it would and changes nothing. The read is the
    registry path's: `ACCOUNT`'s derived partitions, and a registry row for
    every other partition a row is in, as `fenced` writes them.
    """
    from fakes.dynamodb import FakeTable
    from stoa import aws
    from stoa.aws import Kind
    from stoa.db import owner_registry, table as db_table
    from stoa.db.repositories import (
        account_deletion_repo,
        adaptive_learning_repo,
        ai_teacher_tools_repo,
        attachment_repo,
        curriculum_analytics_repo,
        moderation_repo,
        notification_repo,
        practice_repo,
        report_repo,
        websocket_repo,
    )
    from stoa.services import (
        account_deletion_service as service,
        ask_question,
        attachment_service,
        moderation_service,
    )

    table = FakeTable()
    table.seed(*rows)
    table.seed_active_account(ACCOUNT)
    for partition in sorted({str(row["PK"]) for row in rows}):
        if not owner_registry.is_derived_for(partition, ACCOUNT):
            table.seed(owner_registry.registry_item(ACCOUNT, partition))
    db_table.install(table)
    aws.install({Kind.S3: _AnyClient(), Kind.COGNITO: _AnyClient()})

    picked: dict[str, set[tuple[str, str]]] = {branch: set() for branch in service.BRANCH_HANDLERS}
    running = [""]

    def record(item: Mapping[str, Any], *_args: Any, **_kwargs: Any) -> dict[str, str]:
        picked[running[0]].add((str(item.get("PK")), str(item.get("SK"))))
        return {"status": "purged"}

    # The base branches hand their rows to a `mutate` of their own.
    run_base = service._run_base_branch
    monkeypatch.setattr(
        service, "_run_base_branch", lambda **kwargs: run_base(**{**kwargs, "mutate": record})
    )
    # The attachment branch purges the whole owner once it meets one of these.
    is_debt = service._is_attachment_debt

    def attachment_debt(item: Mapping[str, Any], owner_id: str) -> bool:
        if is_debt(item, owner_id):
            record(item)
            return True
        return False

    monkeypatch.setattr(service, "_is_attachment_debt", attachment_debt)
    for module, name in (
        (moderation_repo, "scrub_moderation_row"),
        (report_repo, "scrub_report_private_row"),
        (report_repo, "purge_report_object_intent"),
        (attachment_repo, "scrub_conversation_private_row"),
        (practice_repo, "scrub_practice_private_row"),
        (adaptive_learning_repo, "scrub_adaptive_private_row"),
        (ai_teacher_tools_repo, "scrub_ai_draft_private_row"),
        (curriculum_analytics_repo, "reconcile_curriculum_signal"),
        (notification_repo, "scrub_notification_private_row"),
        (websocket_repo, "revoke_account_connection"),
    ):
        monkeypatch.setattr(module, name, record)
    # What the branches do besides acting on a row: nothing, here.
    for module, name, answer in (
        (account_deletion_repo, "create_provider_revoke_debt", None),
        (account_deletion_repo, "close_unused_provider_revoke_debt", None),
        (attachment_service, "purge_student_attachments", _PurgeDone()),
        (attachment_service, "release_conversation_attachments", None),
        (ask_question, "cancel_for_account_deletion", None),
        (moderation_service, "delete_case_image", None),
    ):
        monkeypatch.setattr(module, name, lambda *_a, _answer=answer, **_k: _answer)

    command = {"user_id": ACCOUNT, "generation": 1, "command_id": "cmd-534", "branch_results": {}}
    with account_deletion_repo.registry_scope(ACCOUNT, table=table):
        for branch_id, handler in service.BRANCH_HANDLERS.items():
            running[0] = branch_id
            previous: dict[str, Any] = {}
            for _page in range(100):
                result = handler(command=command, previous=previous)
                if result.cursor is None:
                    break
                previous = {
                    "cursor": result.cursor,
                    "debt_counts": result.debt_counts,
                    "epoch": result.epoch,
                }
            else:
                raise AssertionError(f"{branch_id} kept paging")
    return picked


# -- tests --------------------------------------------------------------------------


def test_every_written_entity_type_is_deleted_by_a_branch_or_kept():
    found, _ = written_entity_types(ROOT)
    listed = deleted_by_branch().keys() | KEPT.keys()
    new = {entity_type: sorted(found[entity_type]) for entity_type in sorted(found.keys() - listed)}
    assert not new, (
        "rows written with an entity_type no deletion branch is listed for: make a branch "
        "pick it and add a row of it to deleted_by_branch(), or list it in KEPT with "
        f"its reason: {new}"
    )


def test_the_lists_name_only_entity_types_the_code_writes():
    found, _ = written_entity_types(ROOT)
    listed = deleted_by_branch().keys() | KEPT.keys()
    stale = sorted(listed - found.keys() - NO_LONGER_WRITTEN.keys())
    assert not stale, (
        "no longer written anywhere in src/stoa: remove from the lists, or, if rows of it "
        f"may still be stored, keep its branch and list it in NO_LONGER_WRITTEN: {stale}"
    )


def test_a_type_no_longer_written_is_not_written_and_is_still_deleted():
    found, _ = written_entity_types(ROOT)
    written_again = {
        entity_type: sorted(found[entity_type])
        for entity_type in sorted(NO_LONGER_WRITTEN.keys() & found.keys())
    }
    assert not written_again, (
        f"written again: take it out of NO_LONGER_WRITTEN: {written_again}"
    )
    assert sorted(NO_LONGER_WRITTEN.keys() - deleted_by_branch().keys()) == [], (
        "rows that may still be stored need a branch that deletes them"
    )


def test_no_entity_type_is_both_deleted_and_kept_and_every_reason_is_known():
    assert not deleted_by_branch().keys() & KEPT.keys()
    assert {reason for reason in KEPT.values()} <= _REASONS


def test_every_unresolved_writer_is_reviewed():
    _, unresolved = written_entity_types(ROOT)
    assert sorted(unresolved - UNRESOLVED_WRITERS.keys()) == [], (
        "a writer whose entity_type the scan cannot read: say in UNRESOLVED_WRITERS what "
        "it writes, and list those types"
    )
    assert sorted(UNRESOLVED_WRITERS.keys() - unresolved) == [], "stale UNRESOLVED_WRITERS"


def test_each_deleted_entity_type_reaches_the_branch_it_is_listed_under(monkeypatch):
    listed = deleted_by_branch()
    picked = picks_by_branch(monkeypatch, [row for _, row in listed.values()])
    missed = {
        entity_type: {
            "listed": branch,
            "picked_by": sorted(b for b, keys in picked.items() if (row["PK"], row["SK"]) in keys),
        }
        for entity_type, (branch, row) in sorted(listed.items())
        if (row["PK"], row["SK"]) not in picked[branch]
    }
    assert not missed, missed


def test_the_branch_run_picks_nothing_of_another_account(monkeypatch):
    """The recorder records picks, not reads: the same rows of another account reach none.

    Every row of `deleted_by_branch()` with `ACCOUNT` swapped for a third
    account, wherever it appears; the partitions stay registered under
    `ACCOUNT`, so the branches still read them.
    """
    third = "third-account-534"
    others = [
        json.loads(json.dumps(row).replace(ACCOUNT, third))
        for _, row in deleted_by_branch().values()
    ]
    picked = picks_by_branch(monkeypatch, others)
    reached = {(row["PK"], row["SK"]) for row in others} & set().union(*picked.values())
    assert not reached, sorted(reached)


def test_the_scan_sees_a_new_entity_type(tmp_path):
    source = tmp_path / "src" / "stoa"
    (source / "db").mkdir(parents=True)
    (source / "db" / "kinds.py").write_text('SHARED = "shared_row"\n', encoding="utf-8")
    (source / "new_repo.py").write_text(
        "\n".join(
            [
                "from stoa.db import kinds",
                'LOCAL = "constant_row"',
                "",
                "def put_one(table, owner):",
                '    table.put_item(Item={"PK": owner, "SK": "A", "entity_type": "literal_row"})',
                '    table.put_item(Item={"PK": owner, "SK": "B", "entity_type": LOCAL})',
                '    table.put_item(Item={"PK": owner, "SK": "C", "entity_type": kinds.SHARED})',
                "",
                "def count(table, owner):",
                "    table.update_item(",
                '        Key={"PK": owner, "SK": "D"},',
                '        UpdateExpression="SET entity_type = :entity ADD hits :one",',
                '        ExpressionAttributeValues={":entity": "updated_row", ":one": 1},',
                "    )",
                "",
                "def only_reads(table, owner):",
                "    table.update_item(",
                '        Key={"PK": owner, "SK": "E"},',
                '        UpdateExpression="SET hits = :one",',
                '        ConditionExpression="entity_type = :entity",',
                '        ExpressionAttributeValues={":entity": "read_row", ":one": 1},',
                "    )",
                "",
                "def tombstone(table, item):",
                '    table.put_item(Item={**item, "entity_type": f"{item[\'kind\']}_gone"})',
                "",
            ]
        ),
        encoding="utf-8",
    )
    found, unresolved = written_entity_types(tmp_path)
    assert set(found) == {"literal_row", "constant_row", "shared_row", "updated_row"}
    assert unresolved == {"src/stoa/new_repo.py::tombstone"}
