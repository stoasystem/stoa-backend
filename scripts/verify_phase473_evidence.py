#!/usr/bin/env python3
"""Capture and independently verify immutable Phase 473 evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Sequence
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / ".planning/phases/473-student-content-privacy-and-practice-integrity"
BOUNDARY_PATH = ROOT / "docs/security/phase-473-boundary-inventory.json"
PRIVATE_PATH = ROOT / "docs/security/phase-473-private-store-inventory.json"
POLICY_PATH = ROOT / "docs/security/phase-473-retained-evidence-policy.json"
ROUTE_PATH = ROOT / "docs/security/route-authorization-inventory.json"
DENYLIST_PATH = ROOT / "tests/fixtures/phase473_evidence_denylist.txt"
RESULTS_PATH = ROOT / "docs/security/phase-473-evidence-results.json"
EVIDENCE_PATH = ROOT / "docs/security/phase-473-evidence.md"
MANIFEST_PATH = ROOT / "docs/security/phase-473-evidence-manifest.json"
VALIDATION_PATH = PHASE_DIR / "473-VALIDATION.md"
RESULT_SCHEMA = "phase-473-evidence-results.v1"
MANIFEST_SCHEMA = "phase-473-evidence-manifest.v2"
REQUIREMENTS = ("V9PRIV-01", "V9PRIV-02", "V9PRIV-03")
DECISIONS = tuple(f"D-{number:02d}" for number in range(1, 23))
EXTERNAL_OBLIGATIONS = {
    "P479-REAL-S3-MULTIPART-VERSIONING": "479",
    "P480-DEPLOYED-CLEANUP-SCHEDULER-IAC": "480",
    "P480-PRODUCTION-LOGS": "480",
}
PUBLICATION_FIXED_PATHS = {
    "docs/security/phase-473-evidence-results.json",
    "docs/security/phase-473-evidence.md",
    "docs/security/phase-473-evidence-manifest.json",
}
INHERITED_PHASE473 = (
    "tests/test_files.py",
    "tests/test_attachment_security.py",
    "tests/test_questions.py",
    "tests/test_conversations.py",
    "tests/test_practice.py",
    "tests/test_practice_privacy.py",
    "tests/test_curriculum_rollout.py",
    "tests/test_route_authorization_inventory.py",
    "tests/test_student_authorization_matrix.py",
)
PHASE472_REGRESSION = (
    "tests/test_auth_security.py",
    "tests/test_identity_authorization.py",
    "tests/test_client_error_actions.py",
    "tests/test_teacher_onboarding.py",
    "tests/test_teacher_terminology_gate.py",
    "tests/test_student_authorization_matrix.py",
    "tests/test_route_authorization_inventory.py",
    "tests/test_authorization_audit.py",
    "tests/test_public_auth_error_boundary.py",
    "tests/test_public_identity_lifecycle.py",
    "tests/test_notifications.py",
    "tests/test_websocket_notifications.py",
    "tests/test_admin_authorization.py",
    "tests/test_privileged_identity_reconciliation.py",
    "tests/test_provision_production_admin.py",
    "tests/test_auth_account_lifecycle.py",
    "tests/test_parent_children.py",
    "tests/test_questions.py",
    "tests/test_teacher_dispatch.py",
    "tests/test_adaptive_learning.py",
    "tests/test_curriculum_ops.py",
)
FINAL_GAP_GATE_MODULES = {
    "P473-DELETION-CLAIM-FENCING": (
        "tests/test_phase473_account_deletion_claim_fencing.py",
    ),
    "P473-DELIVERY-INTENT-RECOVERY": (
        "tests/test_phase473_delivery_intent_recovery.py",
    ),
    "P473-PRIVATE-DELIVERY-FENCING": (
        "tests/test_phase473_private_delivery_fencing.py",
    ),
    "P473-FINAL-GAP-REGRESSION": (
        "tests/test_phase473_account_deletion_claim_fencing.py",
        "tests/test_phase473_account_deletion.py",
        "tests/test_phase473_account_deletion_seal.py",
        "tests/test_phase473_delivery_intent_recovery.py",
        "tests/test_phase473_notification_deletion.py",
        "tests/test_phase473_private_delivery_fencing.py",
        "tests/test_notifications.py",
        "tests/test_websocket_notifications.py",
    ),
}

CLAIM_FENCE_CONTRACTS = (
    (
        "tests/test_phase473_account_deletion_claim_fencing.py::test_claim_compares_stored_expiry_with_distinct_current_epoch",
        "account_deletion_repo.claim_deletion_command:table.update_item",
        "stored expiry is compared with explicit now_epoch, not proposed expiry",
    ),
    (
        "tests/test_phase473_account_deletion_claim_fencing.py::test_two_workers_cannot_steal_active_lease_and_only_one_wins_after_expiry",
        "account_deletion_repo:_LeaseStateTable",
        "unexpired rejection, one expired takeover, and stale mutation denial",
    ),
    (
        "tests/test_phase473_account_deletion_claim_fencing.py::test_branch_result_cas_requires_owner_version_digest_and_returns_next_claim",
        "account_deletion_repo.persist_branch_result:table.update_item",
        "owner, command version, result digest, and current lease all participate in CAS",
    ),
    (
        "tests/test_phase473_account_deletion_claim_fencing.py::test_service_invokes_no_branch_or_later_write_after_claim_renewal_loss",
        "account_deletion_service.continue_command:repository fake",
        "claim loss stops every branch handler, result write, and finalizer",
    ),
    (
        "tests/test_phase473_account_deletion_claim_fencing.py::test_forged_in_memory_complete_map_cannot_terminalize_durable_incomplete_set",
        "account_deletion_repo.finalize_account_deletion:strong durable fake",
        "terminalization requires the strongly loaded exact durable result set and digest",
    ),
    (
        "tests/test_phase473_account_deletion_claim_fencing.py::test_repository_rejects_invalid_lifecycle_timestamps",
        "account_deletion_repo._valid_lifecycle_timestamp",
        "blank, naive, malformed, non-string, and missing timestamps are rejected",
    ),
    (
        "tests/test_phase473_account_deletion_claim_fencing.py::test_production_service_clock_is_nonblank_timezone_aware_utc",
        "account_deletion_service.AccountDeletionService.__init__",
        "the production constructor emits a nonblank timezone-aware UTC timestamp",
    ),
    (
        "tests/test_phase473_account_deletion_claim_fencing.py::test_parent_scrub_is_version_cas_and_never_replaces_concurrent_preferences",
        "account_deletion_repo.scrub_parent_profile_child:table.transact",
        "parent row-version conflict preserves concurrent preferences",
    ),
    (
        "tests/test_phase473_account_deletion_claim_fencing.py::test_fresh_parent_rescan_removes_only_child_and_advances_row_version",
        "account_deletion_repo.scrub_parent_profile_child:current-row fake",
        "fresh narrow scrub removes only the target child and advances row version",
    ),
    (
        "tests/test_phase473_account_deletion_claim_fencing.py::test_account_profile_row_conflict_stays_retryable_debt",
        "account_deletion_service._account_profile_branch:repository fake",
        "parent CAS conflict remains retryable debt and cannot count as a clean epoch",
    ),
)

DELIVERY_SCOPE_CONTRACTS = (
    (
        "tests/test_phase473_private_delivery_fencing.py::test_strong_event_loader_uses_exact_base_key_and_consistent_read",
        "notification_repo.load_delivery_event_strong:table.get_item",
        "canonical event ownership is loaded by exact base key with ConsistentRead",
    ),
    (
        "tests/test_phase473_private_delivery_fencing.py::test_private_push_rejects_missing_malformed_or_stale_persisted_generation",
        "notification_service.attempt_push_delivery:provider counter",
        "missing, malformed, and stale private generation produce zero provider calls",
    ),
    (
        "tests/test_phase473_private_delivery_fencing.py::test_legacy_question_owner_resolution_uses_closed_strong_target_join",
        "notification_service.resolve_delivery_ownership:strong target fake",
        "legacy ownership comes only from a closed strongly consistent target join",
    ),
    (
        "tests/test_phase473_private_delivery_fencing.py::test_legacy_metadata_only_owner_fails_closed_without_target",
        "notification_service.resolve_delivery_ownership:empty target fake",
        "recipient, actor, and metadata owner claims cannot replace authoritative legacy state",
    ),
    (
        "tests/test_phase473_private_delivery_fencing.py::test_global_nonprivate_requires_exact_persisted_contract_digest",
        "notification_repo.seal_global_nonprivate_event",
        "ownerless delivery requires the exact persisted sealed-global contract digest",
    ),
    (
        "tests/test_phase473_private_delivery_fencing.py::test_mixed_owner_digest_is_refused_before_email_provider",
        "notification_service.send_digest:provider counter",
        "mixed authoritative owners are refused with zero email provider calls",
    ),
    (
        "tests/test_phase473_private_delivery_fencing.py::test_websocket_invalid_persisted_scope_lists_no_connections_and_posts_nothing",
        "websocket_service.fanout_notification_event:connection/provider counters",
        "invalid persisted scope lists no connections and performs zero provider posts",
    ),
)

CRASH_STATE_CONTRACTS = (
    (
        "tests/test_phase473_delivery_intent_recovery.py::test_repository_claim_uses_explicit_current_time_not_proposed_expiry",
        "notification_repo.claim_delivery_intent:table.update_item",
        "only an expired pre-effect claim relative to explicit now_epoch is takeable",
    ),
    (
        "tests/test_phase473_delivery_intent_recovery.py::test_unexpired_pre_effect_claim_and_inflight_are_never_takeover_eligible",
        "notification_repo.claim_delivery_intent:conditional fake",
        "unexpired pre-effect and inflight states are never takeover eligible",
    ),
    (
        "tests/test_phase473_delivery_intent_recovery.py::test_begin_private_claim_is_one_fence_plus_exact_version_cas",
        "notification_repo.begin_delivery_effect:transaction fake",
        "begin uses one account fence plus lease, version, scope, and payload digest CAS",
    ),
    (
        "tests/test_phase473_delivery_intent_recovery.py::test_crash_pre_effect_recovers_only_after_actual_time_passes",
        "notification_service.run_delivery_intent:memory intent store",
        "pre-effect crash is reclaimable only after actual lease expiry and calls provider once",
    ),
    (
        "tests/test_phase473_delivery_intent_recovery.py::test_crash_after_durable_transition_terminalizes_unknown_without_provider_call",
        "notification_service.run_delivery_intent:memory intent store",
        "durable inflight ambiguity terminalizes without a blind provider call",
    ),
    (
        "tests/test_phase473_delivery_intent_recovery.py::test_provider_acceptance_lost_response_replays_unknown_without_blind_retry",
        "notification_service.run_delivery_intent:provider counter",
        "provider acceptance with lost response is never blindly retried",
    ),
    (
        "tests/test_phase473_delivery_intent_recovery.py::test_terminal_completion_lost_response_replays_accepted_without_provider_payload",
        "notification_service.run_delivery_intent:memory intent store",
        "post-acceptance terminal replay is accepted and provider-neutral",
    ),
    (
        "tests/test_phase473_delivery_intent_recovery.py::test_stale_claim_version_cannot_begin_complete_cancel_or_recover",
        "notification_repo:stale claim fake",
        "stale intent versions cannot begin, complete, cancel, or recover newer work",
    ),
    (
        "tests/test_phase473_delivery_intent_recovery.py::test_provider_effect_order_is_recover_fence_transition_call_and_complete",
        "notification_service.run_delivery_intent:ordered fake",
        "provider invocation follows durable begin and precedes only the terminal CAS",
    ),
)

FINAL_GAP_NODE_CONTRACTS = {
    "claim_fence_nodes": CLAIM_FENCE_CONTRACTS,
    "delivery_scope_nodes": DELIVERY_SCOPE_CONTRACTS,
    "crash_state_nodes": CRASH_STATE_CONTRACTS,
}

GAP_TRUTH_CONTRACTS = (
    ("current_epoch_claim", CLAIM_FENCE_CONTRACTS[0]),
    ("two_worker_takeover", CLAIM_FENCE_CONTRACTS[1]),
    ("stale_write_and_finalization", CLAIM_FENCE_CONTRACTS[4]),
    ("production_utc_timestamp", CLAIM_FENCE_CONTRACTS[6]),
    ("parent_row_cas", CLAIM_FENCE_CONTRACTS[7]),
    ("pre_effect_crash_recovery", CRASH_STATE_CONTRACTS[3]),
    ("inflight_ambiguity_terminalization", CRASH_STATE_CONTRACTS[4]),
    ("legacy_malformed_delivery_denial", DELIVERY_SCOPE_CONTRACTS[3]),
    ("sealed_global_validation", DELIVERY_SCOPE_CONTRACTS[4]),
    ("deletion_race_zero_provider_effects", DELIVERY_SCOPE_CONTRACTS[6]),
)

FINAL_IDENTIFIER_SELECTORS = {
    "V9PRIV-02": (
        CLAIM_FENCE_CONTRACTS[2][0],
        CRASH_STATE_CONTRACTS[3][0],
        DELIVERY_SCOPE_CONTRACTS[1][0],
    ),
    "D-10": (CLAIM_FENCE_CONTRACTS[1][0], DELIVERY_SCOPE_CONTRACTS[6][0]),
    "D-16": (CRASH_STATE_CONTRACTS[4][0], DELIVERY_SCOPE_CONTRACTS[3][0]),
    "D-17": (DELIVERY_SCOPE_CONTRACTS[1][0], DELIVERY_SCOPE_CONTRACTS[6][0]),
}

FINDING_CONTRACTS = {
    "CR-01": (
        CLAIM_FENCE_CONTRACTS[2][0],
        "src/stoa/db/repositories/account_deletion_repo.py:table.update_item",
        "src/stoa/db/repositories/account_deletion_repo.py:table.update_item",
    ),
    "CR-02": (
        DELIVERY_SCOPE_CONTRACTS[1][0],
        "src/stoa/db/repositories/notification_repo.py:table.get_item.ConsistentRead",
        "src/stoa/services/notification_service.py:provider_call",
    ),
    "WR-01": (
        CLAIM_FENCE_CONTRACTS[5][0],
        "src/stoa/db/repositories/account_deletion_repo.py:_valid_lifecycle_timestamp",
        "src/stoa/db/repositories/account_deletion_repo.py:_valid_lifecycle_timestamp",
    ),
    "WR-02": (
        CLAIM_FENCE_CONTRACTS[7][0],
        "src/stoa/db/repositories/account_deletion_repo.py:table.transact",
        "src/stoa/db/repositories/account_deletion_repo.py:table.transact",
    ),
    "WR-03": (
        CRASH_STATE_CONTRACTS[0][0],
        "src/stoa/db/repositories/notification_repo.py:table.update_item",
        "src/stoa/db/repositories/notification_repo.py:table.update_item",
    ),
}


class EvidenceError(ValueError):
    """A machine-checked evidence invariant failed."""


def _run(argv: Sequence[str], *, root: Path = ROOT, check: bool = True) -> str:
    completed = subprocess.run(
        list(argv), cwd=root, text=True, capture_output=True, check=False
    )
    if check and completed.returncode:
        raise EvidenceError(
            f"command failed ({completed.returncode}): {list(argv)!r}: "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout.rstrip("\n")


def _git(root: Path, *args: str) -> str:
    return _run(("git", *args), root=root)


def _head(root: Path = ROOT) -> str:
    return _git(root, "rev-parse", "HEAD")


def _clean(root: Path = ROOT) -> bool:
    return not _git(root, "status", "--porcelain")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvidenceError("timestamp must be RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError("timestamp must be RFC3339 UTC") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise EvidenceError("timestamp must use UTC")
    return parsed


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _file_meta(path: Path, logical_path: str | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "logical_path": logical_path or path.as_posix(),
        "captured_path": str(path.resolve()),
        "bytes": len(data),
        "sha256": sha256(data).hexdigest(),
    }


def _artifact_meta(path: Path, root: Path = ROOT) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(data),
        "sha256": sha256(data).hexdigest(),
    }


def _denylist(path: Path) -> list[str]:
    entries = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    entries = [entry for entry in entries if entry and not entry.startswith("#")]
    if not entries or len(entries) != len(set(entry.casefold() for entry in entries)):
        raise EvidenceError("denylist must contain unique nonempty entries")
    return entries


def _privacy_match_count(paths: Iterable[Path], denylist_path: Path) -> int:
    needles = [entry.casefold() for entry in _denylist(denylist_path)]
    matches = 0
    for path in paths:
        text = path.read_bytes().decode("utf-8", errors="replace").casefold()
        matches += sum(text.count(needle) for needle in needles)
    return matches


def _junit_counts(path: Path) -> dict[str, int]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise EvidenceError("invalid JUnit XML") from exc
    attrs = root.attrib
    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = list(root.findall("testsuite"))
    else:
        raise EvidenceError("invalid JUnit root")
    def number(name: str) -> int:
        raw = attrs.get(name)
        if raw is not None:
            return int(raw)
        return sum(int(suite.attrib.get(name, "0")) for suite in suites)
    return {
        "total": number("tests"),
        "failed": number("failures"),
        "error": number("errors"),
        "skipped": number("skipped"),
    }


def verify_receipt(
    receipt: dict[str, Any],
    *,
    expected_gate_id: str,
    expected_argv: Sequence[str],
    candidate: str,
    denylist_path: Path = DENYLIST_PATH,
) -> dict[str, str]:
    if receipt.get("gate_id") != expected_gate_id:
        raise EvidenceError("gate ID drift")
    if receipt.get("argv") != list(expected_argv):
        raise EvidenceError("argv drift")
    if receipt.get("exit_code") != 0:
        raise EvidenceError("nonzero gate exit")
    if receipt.get("candidate_sha") != candidate:
        raise EvidenceError("candidate drift")
    for boundary in ("before", "after"):
        state = receipt.get(boundary)
        if state != {"head": candidate, "clean": True}:
            raise EvidenceError(f"candidate or cleanliness drift {boundary}")
    if _parse_utc(receipt.get("started_at")) > _parse_utc(receipt.get("ended_at")):
        raise EvidenceError("invalid UTC order")
    artifact_paths: list[Path] = []
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"log", "junit", "node_manifest"}:
        raise EvidenceError("receipt artifact set mismatch")
    for name, meta in artifacts.items():
        if not isinstance(meta, dict) or not meta.get("logical_path"):
            raise EvidenceError(f"missing logical {name} path")
        path = Path(str(meta.get("captured_path", "")))
        if not path.is_file():
            raise EvidenceError(f"missing captured {name}")
        data = path.read_bytes()
        if not data or meta.get("bytes") != len(data):
            raise EvidenceError(f"empty or changed {name} bytes")
        if meta.get("sha256") != sha256(data).hexdigest():
            raise EvidenceError(f"changed {name} hash")
        artifact_paths.append(path)
    manifest = _read_json(Path(artifacts["node_manifest"]["captured_path"]))
    if manifest.get("schema_version") != "phase-473-pytest-nodes.v1":
        raise EvidenceError("node manifest schema mismatch")
    nodes = manifest.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise EvidenceError("node manifest is empty")
    node_ids = [node.get("node_id") for node in nodes if isinstance(node, dict)]
    if len(node_ids) != len(nodes) or len(node_ids) != len(set(node_ids)):
        raise EvidenceError("duplicate or invalid node")
    counts = manifest.get("counts")
    expected_count_keys = {"total", "passed", "failed", "error", "skipped", "xfail", "xpass"}
    if not isinstance(counts, dict) or set(counts) != expected_count_keys:
        raise EvidenceError("node count schema mismatch")
    recomputed = {key: 0 for key in expected_count_keys}
    recomputed["total"] = len(nodes)
    outcomes: dict[str, str] = {}
    for node in nodes:
        outcome = node.get("outcome")
        if outcome not in expected_count_keys - {"total"}:
            raise EvidenceError("invalid node outcome")
        recomputed[outcome] += 1
        outcomes[str(node["node_id"])] = str(outcome)
    if counts != recomputed or receipt.get("counts") != counts or receipt.get("nodes") != nodes:
        raise EvidenceError("count or node mismatch")
    if any(counts[key] for key in ("failed", "error", "skipped", "xfail", "xpass")):
        raise EvidenceError("forbidden pytest outcome")
    junit = _junit_counts(Path(artifacts["junit"]["captured_path"]))
    for key in ("total", "failed", "error", "skipped"):
        if junit[key] != counts[key]:
            raise EvidenceError("JUnit count mismatch")
    privacy = receipt.get("privacy")
    entries = _denylist(denylist_path)
    expected_privacy = {
        "denylist_sha256": sha256(denylist_path.read_bytes()).hexdigest(),
        "entry_count": len(entries),
        "match_count": _privacy_match_count(artifact_paths, denylist_path),
    }
    if privacy != expected_privacy or expected_privacy["match_count"]:
        raise EvidenceError("privacy denylist match or receipt drift")
    return outcomes


def _selector_node(selector: str, observed_nodes: set[str]) -> str:
    matches = sorted(
        node for node in observed_nodes if node == selector or node.startswith(selector + "[")
    )
    if not matches:
        raise EvidenceError(f"selector not observed: {selector}")
    return matches[0]


def _final_gap_rows(
    contracts: Sequence[tuple[str, str, str]],
    observed_nodes: set[str],
    *,
    source_inventory_row: str,
) -> list[dict[str, Any]]:
    return [
        {
            "selector": selector,
            "node_id": _selector_node(selector, observed_nodes),
            "lower_fake_target": lower_fake_target,
            "observed_condition": observed_condition,
            "source_inventory_row": source_inventory_row,
            "result": "PASS",
        }
        for selector, lower_fake_target, observed_condition in contracts
    ]


def _finding_coverage(
    boundary: dict[str, Any],
    private: dict[str, Any],
    observed_nodes: set[str],
) -> list[dict[str, Any]]:
    boundary_rows = {
        row.get("finding_id"): row
        for row in boundary.get("finding_registry", [])
        if isinstance(row, dict)
    }
    private_rows = {
        row.get("finding_id"): row
        for row in private.get("finding_registry", [])
        if isinstance(row, dict)
    }
    if set(boundary_rows) != set(FINDING_CONTRACTS) or set(private_rows) != set(
        FINDING_CONTRACTS
    ):
        raise EvidenceError("finding registry ID drift")
    rows: list[dict[str, Any]] = []
    for finding_id, (
        selector,
        boundary_lower_fake,
        private_lower_fake,
    ) in FINDING_CONTRACTS.items():
        boundary_row = boundary_rows[finding_id]
        private_row = private_rows[finding_id]
        if (
            boundary_row.get("runtime_selector") != selector
            or private_row.get("runtime_selector") != selector
            or boundary_row.get("lower_fake_target") != boundary_lower_fake
            or private_row.get("lower_fake_target") != private_lower_fake
            or not boundary_row.get("observed_assertion")
            or not private_row.get("required_semantics")
        ):
            raise EvidenceError(f"finding registry drift: {finding_id}")
        rows.append(
            {
                "id": finding_id,
                "selector": selector,
                "node_id": _selector_node(selector, observed_nodes),
                "lower_fake_targets": [boundary_lower_fake, private_lower_fake],
                "observed_condition": boundary_row["observed_assertion"],
                "required_semantics": private_row["required_semantics"],
                "source_inventory_rows": [
                    f"boundary.finding_registry.{finding_id}",
                    f"private.finding_registry.{finding_id}",
                ],
                "result": "PASS",
            }
        )
    return rows


def derive_coverage(
    boundary: dict[str, Any],
    private: dict[str, Any],
    policy: dict[str, Any],
    observed_nodes: set[str],
) -> dict[str, list[dict[str, Any]]]:
    read_rows = boundary.get("rows", [])
    private_rows = private.get("rows", [])
    branch_rows = private.get("branch_registry", [])
    read_coverage = [
        {
            "id": row["boundary_id"],
            "selector": row["malformed_selector"],
            "node_id": _selector_node(row["malformed_selector"], observed_nodes),
            "lower_fake_target": row["lower_fake_target"],
            "result": "PASS",
        }
        for row in read_rows
    ]
    write_coverage = [
        {
            "id": row["row_id"],
            "branch_id": row["branch_id"],
            "purge_selector": row["purge_selector"],
            "purge_node_id": _selector_node(row["purge_selector"], observed_nodes),
            "no_resurrection_selector": row["no_resurrection_selector"],
            "no_resurrection_node_id": _selector_node(
                row["no_resurrection_selector"], observed_nodes
            ),
            "result": "PASS",
        }
        for row in private_rows
    ]
    branches = [
        {
            "id": row["branch_id"],
            "purge_selector": row["purge_selector"],
            "purge_node_id": _selector_node(row["purge_selector"], observed_nodes),
            "no_resurrection_selector": row["no_resurrection_selector"],
            "no_resurrection_node_id": _selector_node(
                row["no_resurrection_selector"], observed_nodes
            ),
            "result": "PASS",
        }
        for row in branch_rows
    ]
    selector_sources = [
        (row["malformed_selector"], row.get("requirement_ids", []), row.get("decision_ids", []))
        for row in read_rows
    ] + [
        (row["purge_selector"], row.get("requirement_ids", []), row.get("decision_ids", []))
        for row in private_rows
    ]
    def identifier_rows(identifiers: Sequence[str], index: int) -> list[dict[str, Any]]:
        rows = []
        for identifier in identifiers:
            selectors = sorted(
                selector for selector, requirements, decisions in selector_sources
                if identifier in (requirements if index == 1 else decisions)
            )
            if not selectors:
                raise EvidenceError(f"no inventory selector for {identifier}")
            selector = selectors[0]
            required_lower_nodes = [
                {
                    "selector": required_selector,
                    "node_id": _selector_node(required_selector, observed_nodes),
                }
                for required_selector in FINAL_IDENTIFIER_SELECTORS.get(identifier, ())
            ]
            rows.append(
                {
                    "id": identifier,
                    "selector": selector,
                    "node_id": _selector_node(selector, observed_nodes),
                    "inventory_selector": selector,
                    "required_lower_nodes": required_lower_nodes,
                    "result": "PASS",
                }
            )
        return rows
    retained = [
        {
            "id": row["class_id"],
            "result": "RETAINED",
            "legal_basis": row["legal_basis"],
            "ttl_seconds": row["ttl_seconds"],
            "unbounded_retention": row["unbounded_retention"],
        }
        for row in policy.get("classes", [])
    ]
    final_gap_groups = {
        section: _final_gap_rows(
            contracts,
            observed_nodes,
            source_inventory_row=(
                "boundary/private finding registries"
                if section != "crash_state_nodes"
                else "private finding registry WR-03"
            ),
        )
        for section, contracts in FINAL_GAP_NODE_CONTRACTS.items()
    }
    gap_truths = [
        {
            "id": identifier,
            **_final_gap_rows(
                (contract,),
                observed_nodes,
                source_inventory_row="Plan 473-40 gap truth",
            )[0],
        }
        for identifier, contract in GAP_TRUTH_CONTRACTS
    ]
    return {
        "requirements": identifier_rows(REQUIREMENTS, 1),
        "decisions": identifier_rows(DECISIONS, 2),
        "read_boundaries": read_coverage,
        "private_writes": write_coverage,
        "branches": branches,
        "retained_policy": retained,
        "review_findings": _finding_coverage(boundary, private, observed_nodes),
        "gap_truths": gap_truths,
        **final_gap_groups,
    }


def verify_coverage(
    coverage: dict[str, Any],
    boundary: dict[str, Any],
    private: dict[str, Any],
    policy: dict[str, Any],
    observed_nodes: set[str],
) -> None:
    if any(
        row.get("result") == "purged"
        for row in coverage.get("retained_policy", [])
        if isinstance(row, dict)
    ):
        raise EvidenceError("retained policy material cannot be labeled purged")
    expected = derive_coverage(boundary, private, policy, observed_nodes)
    if coverage != expected:
        raise EvidenceError("coverage is missing, duplicated, stale, or mislabeled")
    if policy.get("external_receipt_claim") != "outside_backend_purge_authority":
        raise EvidenceError("external receipt policy drift")
    statuses = set(policy.get("external_receipt_statuses", []))
    if statuses != {"accepted", "delivered", "provider_acceptance_unknown"}:
        raise EvidenceError("external receipt statuses drift")


def verify_external_obligations(
    obligations: list[dict[str, Any]], *, local_gate_ids: set[str]
) -> None:
    expected = [
        {"id": item, "status": "NOT RUN", "owner_phase": owner}
        for item, owner in EXTERNAL_OBLIGATIONS.items()
    ]
    if obligations != expected:
        raise EvidenceError("external NOT RUN obligations drift")
    if local_gate_ids & EXTERNAL_OBLIGATIONS.keys():
        raise EvidenceError("external obligation appeared as a local gate")


def _frontmatter_files(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index("files_modified:") + 1
    except ValueError:
        return []
    files: list[str] = []
    for line in lines[start:]:
        if line.startswith("  - "):
            files.append(line[4:].strip())
        elif line and not line.startswith(" "):
            break
    return files


def _deep_suite_modules() -> tuple[str, ...]:
    modules: set[str] = set()
    for number in range(18, 36):
        plan = PHASE_DIR / f"473-{number:02d}-PLAN.md"
        modules.update(
            item for item in _frontmatter_files(plan)
            if item.startswith("tests/test") and item.endswith(".py")
        )
    return tuple(sorted(modules))


def _phase_base_sha() -> str:
    summary = PHASE_DIR.relative_to(ROOT) / "473-17-SUMMARY.md"
    value = _git(ROOT, "log", "-1", "--format=%H", "--", summary.as_posix())
    if not value:
        raise EvidenceError("473-17 summary history is missing")
    return value


def _phase_python_diff(base: str, candidate: str) -> tuple[str, ...]:
    paths = _git(ROOT, "diff", "--name-only", base, candidate).splitlines()
    return tuple(sorted(path for path in paths if path.endswith(".py") and (ROOT / path).is_file()))


def _pytest_argv(gate_id: str, modules: Sequence[str], capture_root: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "scripts.phase473_pytest_guard",
        "-o",
        "xfail_strict=true",
        "--junitxml",
        str(capture_root / "junit" / f"{gate_id}.xml"),
        "--phase473-node-manifest",
        str(capture_root / "nodes" / f"{gate_id}.json"),
        *modules,
    ]


def gate_registry(candidate: str, capture_root: Path) -> list[dict[str, Any]]:
    base = _phase_base_sha()
    generated = capture_root / "generated"
    registry: list[dict[str, Any]] = [
        {
            "id": gate_id,
            "kind": "pytest",
            "argv": _pytest_argv(gate_id, modules, capture_root),
        }
        for gate_id, modules in FINAL_GAP_GATE_MODULES.items()
    ] + [
        {"id": "P473-NEW-CLOSED", "kind": "pytest", "argv": _pytest_argv("P473-NEW-CLOSED", _deep_suite_modules(), capture_root)},
        {"id": "P473-INHERITED-9", "kind": "pytest", "argv": _pytest_argv("P473-INHERITED-9", INHERITED_PHASE473, capture_root)},
        {"id": "P472-REGRESSION-21", "kind": "pytest", "argv": _pytest_argv("P472-REGRESSION-21", PHASE472_REGRESSION, capture_root)},
        {"id": "FULL-PYTEST", "kind": "pytest", "argv": _pytest_argv("FULL-PYTEST", (), capture_root)},
        {"id": "RUFF-PHASE-DIFF", "kind": "command", "argv": [str(ROOT / ".venv/bin/ruff"), "check", *_phase_python_diff(base, candidate)]},
        {"id": "DIFF-CHECK-PHASE", "kind": "command", "argv": ["git", "diff", "--check", base, candidate]},
        {"id": "SHOW-CHECK-CANDIDATE", "kind": "command", "argv": ["git", "show", "--check", "--format=", candidate]},
        {"id": "READ-BOUNDARY-GENERATE-A", "kind": "command", "argv": [sys.executable, "scripts/generate_phase473_boundary_inventory.py", "--output", str(generated / "boundary-a.json")]},
        {"id": "READ-BOUNDARY-GENERATE-B", "kind": "command", "argv": [sys.executable, "scripts/generate_phase473_boundary_inventory.py", "--output", str(generated / "boundary-b.json")]},
        {"id": "READ-BOUNDARY-CHECK", "kind": "command", "argv": [sys.executable, "scripts/generate_phase473_boundary_inventory.py", "--check"]},
        {"id": "PRIVATE-STORE-GENERATE-A", "kind": "command", "argv": [sys.executable, "scripts/generate_phase473_private_store_inventory.py", "--output", str(generated / "private-a.json"), "--evidence-output", str(generated / "policy-a.json")]},
        {"id": "PRIVATE-STORE-GENERATE-B", "kind": "command", "argv": [sys.executable, "scripts/generate_phase473_private_store_inventory.py", "--output", str(generated / "private-b.json"), "--evidence-output", str(generated / "policy-b.json")]},
        {"id": "PRIVATE-STORE-CHECK", "kind": "command", "argv": [sys.executable, "scripts/generate_phase473_private_store_inventory.py", "--check"]},
        {"id": "ROUTE-GENERATE-A", "kind": "command", "argv": [sys.executable, "scripts/generate_route_authorization_inventory.py", "--output", str(generated / "route-a.json")]},
        {"id": "ROUTE-GENERATE-B", "kind": "command", "argv": [sys.executable, "scripts/generate_route_authorization_inventory.py", "--output", str(generated / "route-b.json")]},
        {"id": "ROUTE-CHECK", "kind": "command", "argv": [sys.executable, "scripts/generate_route_authorization_inventory.py", "--check"]},
        {"id": "PRIVACY-DENIAL", "kind": "command", "argv": [sys.executable, str(Path(__file__).resolve()), "privacy-denial", "--capture-root", str(capture_root), "--denylist", str(DENYLIST_PATH)]},
    ]
    return registry


def _synthetic_artifacts(
    gate_id: str, rc: int, log_path: Path, junit_path: Path, node_path: Path
) -> None:
    outcome = "passed" if rc == 0 else "failed"
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    junit_path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuites tests="1" failures="{int(rc != 0)}" errors="0" skipped="0">'
        f'<testsuite name="phase473" tests="1" failures="{int(rc != 0)}" '
        f'errors="0" skipped="0"><testcase classname="gate" name="{gate_id}">'
        + ("<failure/>" if rc else "")
        + "</testcase></testsuite></testsuites>",
        encoding="utf-8",
    )
    counts = {
        "total": 1,
        "passed": int(rc == 0),
        "failed": int(rc != 0),
        "error": 0,
        "skipped": 0,
        "xfail": 0,
        "xpass": 0,
    }
    _write_json(
        node_path,
        {
            "schema_version": "phase-473-pytest-nodes.v1",
            "nodes": [
                {
                    "node_id": f"gate::{gate_id}",
                    "outcome": outcome,
                    "phases": [{"when": "call", "outcome": outcome, "wasxfail": None}],
                }
            ],
            "counts": counts,
        },
    )
    if not log_path.read_bytes():
        log_path.write_text(f"[{gate_id}] exit={rc}\n", encoding="utf-8")


def _capture_gate(gate: dict[str, Any], candidate: str, capture_root: Path) -> dict[str, Any]:
    if _head() != candidate or not _clean():
        raise EvidenceError(f"candidate changed before {gate['id']}")
    gate_id = gate["id"]
    log_path = capture_root / "raw" / f"{gate_id}.log"
    junit_path = capture_root / "junit" / f"{gate_id}.xml"
    node_path = capture_root / "nodes" / f"{gate_id}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = _utc_now()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        gate["argv"], cwd=ROOT, text=False, capture_output=True, env=env, check=False
    )
    log_path.write_bytes(
        f"[{gate_id}] exit={completed.returncode}\n".encode()
        + completed.stdout
        + completed.stderr
    )
    ended = _utc_now()
    if gate["kind"] != "pytest":
        _synthetic_artifacts(gate_id, completed.returncode, log_path, junit_path, node_path)
    if not junit_path.is_file() or not node_path.is_file():
        raise EvidenceError(f"gate did not emit checked artifacts: {gate_id}")
    if _head() != candidate or not _clean():
        raise EvidenceError(f"candidate changed after {gate_id}")
    node_payload = _read_json(node_path)
    artifact_paths = [log_path, junit_path, node_path]
    receipt = {
        "gate_id": gate_id,
        "argv": gate["argv"],
        "started_at": started,
        "ended_at": ended,
        "exit_code": completed.returncode,
        "candidate_sha": candidate,
        "before": {"head": candidate, "clean": True},
        "after": {"head": candidate, "clean": True},
        "artifacts": {
            "log": _file_meta(log_path, f"raw/{gate_id}.log"),
            "junit": _file_meta(junit_path, f"junit/{gate_id}.xml"),
            "node_manifest": _file_meta(node_path, f"nodes/{gate_id}.json"),
        },
        "counts": node_payload.get("counts"),
        "nodes": node_payload.get("nodes"),
        "privacy": {
            "denylist_sha256": sha256(DENYLIST_PATH.read_bytes()).hexdigest(),
            "entry_count": len(_denylist(DENYLIST_PATH)),
            "match_count": _privacy_match_count(artifact_paths, DENYLIST_PATH),
        },
    }
    if completed.returncode:
        raise EvidenceError(f"gate failed: {gate_id}")
    verify_receipt(
        receipt,
        expected_gate_id=gate_id,
        expected_argv=gate["argv"],
        candidate=candidate,
    )
    return receipt


def _generated_inventory_paths(capture_root: Path) -> dict[str, Path]:
    generated = capture_root / "generated"
    return {
        "boundary_checked": BOUNDARY_PATH,
        "boundary_a": generated / "boundary-a.json",
        "boundary_b": generated / "boundary-b.json",
        "private_checked": PRIVATE_PATH,
        "private_a": generated / "private-a.json",
        "private_b": generated / "private-b.json",
        "policy_checked": POLICY_PATH,
        "policy_a": generated / "policy-a.json",
        "policy_b": generated / "policy-b.json",
        "route_checked": ROUTE_PATH,
        "route_a": generated / "route-a.json",
        "route_b": generated / "route-b.json",
    }


def _verify_generated_inventories(capture_root: Path) -> dict[str, dict[str, Any]]:
    paths = _generated_inventory_paths(capture_root)
    groups = (
        ("boundary_checked", "boundary_a", "boundary_b"),
        ("private_checked", "private_a", "private_b"),
        ("policy_checked", "policy_a", "policy_b"),
        ("route_checked", "route_a", "route_b"),
    )
    for group in groups:
        payloads = [paths[name].read_bytes() for name in group]
        if len(set(payloads)) != 1:
            raise EvidenceError(f"generated inventory bytes drift: {group[0]}")
    return {
        name: {
            "path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
            "bytes": len(path.read_bytes()),
            "sha256": sha256(path.read_bytes()).hexdigest(),
        }
        for name, path in paths.items()
    }


def _candidate_snapshot(base: str, candidate: str) -> list[dict[str, Any]]:
    paths = _git(ROOT, "diff", "--name-only", base, candidate).splitlines()
    required = {BOUNDARY_PATH.relative_to(ROOT).as_posix(), PRIVATE_PATH.relative_to(ROOT).as_posix(), POLICY_PATH.relative_to(ROOT).as_posix(), ROUTE_PATH.relative_to(ROOT).as_posix()}
    paths = sorted(set(paths) | required)
    snapshot = []
    for relative in paths:
        completed = subprocess.run(
            ["git", "show", f"{candidate}:{relative}"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            snapshot.append(
                {
                    "path": relative,
                    "bytes": len(completed.stdout),
                    "sha256": sha256(completed.stdout).hexdigest(),
                }
            )
    return snapshot


def verify_capture(candidate: str, capture_root: Path) -> dict[str, Any]:
    capture = _read_json(capture_root / "capture.json")
    if capture.get("candidate_sha") != candidate or capture.get("phase_base_sha") != _phase_base_sha():
        raise EvidenceError("capture source identity drift")
    registry = gate_registry(candidate, capture_root)
    stored_registry = capture.get("registry")
    expected_registry = [{"gate_id": row["id"], "argv": row["argv"]} for row in registry]
    if stored_registry != expected_registry:
        raise EvidenceError("closed gate registry drift")
    receipts = capture.get("receipts")
    if not isinstance(receipts, list) or len(receipts) != len(registry):
        raise EvidenceError("receipt cardinality drift")
    observed: dict[str, str] = {}
    for gate, receipt in zip(registry, receipts, strict=True):
        gate_nodes = verify_receipt(
            receipt,
            expected_gate_id=gate["id"],
            expected_argv=gate["argv"],
            candidate=candidate,
        )
        observed.update(gate_nodes)
    inventory_meta = _verify_generated_inventories(capture_root)
    boundary = _read_json(BOUNDARY_PATH)
    private = _read_json(PRIVATE_PATH)
    policy = _read_json(POLICY_PATH)
    coverage = derive_coverage(boundary, private, policy, set(observed))
    verify_coverage(coverage, boundary, private, policy, set(observed))
    obligations = [
        {"id": item, "status": "NOT RUN", "owner_phase": owner}
        for item, owner in EXTERNAL_OBLIGATIONS.items()
    ]
    verify_external_obligations(obligations, local_gate_ids={row["id"] for row in registry})
    full_receipt = next(row for row in receipts if row["gate_id"] == "FULL-PYTEST")
    base = _phase_base_sha()
    result = {
        "schema_version": RESULT_SCHEMA,
        "candidate_sha": candidate,
        "phase_base_sha": base,
        "gate_registry": expected_registry,
        "receipts": receipts,
        "observed_full_suite_count": full_receipt["counts"]["total"],
        "inventory_artifacts": inventory_meta,
        "coverage": coverage,
        "finding_adjudications": coverage["review_findings"],
        "external_obligations": obligations,
        "candidate_snapshot": _candidate_snapshot(base, candidate),
        "privacy": {
            "denylist_sha256": sha256(DENYLIST_PATH.read_bytes()).hexdigest(),
            "entry_count": len(_denylist(DENYLIST_PATH)),
            "match_count": sum(row["privacy"]["match_count"] for row in receipts),
        },
    }
    checked = capture_root / "checked-result.json"
    if checked.exists() and _read_json(checked) != result:
        raise EvidenceError("checked result drift")
    return result


def capture(candidate: str, capture_root: Path) -> dict[str, Any]:
    if _head() != candidate or not _clean():
        raise EvidenceError("capture requires the clean candidate at HEAD")
    if not _git(ROOT, "merge-base", "--is-ancestor", _phase_base_sha(), candidate) == "":
        raise EvidenceError("phase base is not an ancestor")
    capture_root.mkdir(parents=True, exist_ok=True)
    registry = gate_registry(candidate, capture_root)
    receipts = [_capture_gate(gate, candidate, capture_root) for gate in registry]
    payload = {
        "schema_version": "phase-473-capture.v1",
        "candidate_sha": candidate,
        "phase_base_sha": _phase_base_sha(),
        "registry": [{"gate_id": row["id"], "argv": row["argv"]} for row in registry],
        "receipts": receipts,
    }
    _write_json(capture_root / "capture.json", payload)
    result = verify_capture(candidate, capture_root)
    _write_json(capture_root / "checked-result.json", result)
    if verify_capture(candidate, capture_root) != result:
        raise EvidenceError("repeated capture verification drift")
    return result


def _exact_commit(root: Path, value: str, *, label: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise EvidenceError(f"{label} must be an explicit full lowercase commit SHA")
    try:
        resolved = _git(root, "rev-parse", "--verify", f"{value}^{{commit}}")
    except EvidenceError as exc:
        raise EvidenceError(f"{label} commit is missing") from exc
    if resolved != value:
        raise EvidenceError(f"{label} must resolve to the exact supplied commit SHA")
    return resolved


def _publication_paths(root: Path, publication: str) -> tuple[set[str], str]:
    validation = ".planning/phases/473-student-content-privacy-and-practice-integrity/473-VALIDATION.md"
    tree_paths = set(
        _git(
            root,
            "ls-tree",
            "-r",
            "--name-only",
            publication,
            "--",
            ".planning/phases",
        ).splitlines()
    )
    if validation not in tree_paths:
        matches = sorted(
            path for path in tree_paths if path.endswith("/473-VALIDATION.md")
        )
        if len(matches) != 1:
            raise EvidenceError("publication validation path is ambiguous")
        validation = matches[0]
    return PUBLICATION_FIXED_PATHS | {validation}, validation


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode not in (0, 1):
        raise EvidenceError("unable to verify publication ancestry")
    return completed.returncode == 0


def _git_blob_oid(root: Path, commit: str, path: str) -> str:
    try:
        oid = _git(root, "rev-parse", "--verify", f"{commit}:{path}")
        if _git(root, "cat-file", "-t", oid) != "blob":
            raise EvidenceError(f"publication path is not a blob: {path}")
    except EvidenceError as exc:
        raise EvidenceError(f"missing immutable Git blob: {commit}:{path}") from exc
    return oid


def _git_blob_bytes(root: Path, oid: str, *, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "cat-file", "blob", oid],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise EvidenceError(f"unable to read immutable Git blob: {path}")
    return completed.stdout


def _blob_json(data: bytes, *, path: str) -> dict[str, Any]:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid JSON publication blob: {path}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"publication JSON blob must be an object: {path}")
    return value


def _privacy_match_count_bytes(payloads: Iterable[bytes], denylist_path: Path) -> int:
    needles = [entry.casefold() for entry in _denylist(denylist_path)]
    return sum(
        data.decode("utf-8", errors="replace").casefold().count(needle)
        for data in payloads
        for needle in needles
    )


def verify_publication(root: Path, candidate: str, publication: str) -> None:
    candidate = _exact_commit(root, candidate, label="candidate")
    publication = _exact_commit(root, publication, label="publication")
    if not _clean(root):
        raise EvidenceError("publication reverification requires a clean worktree")

    parents = _git(root, "rev-list", "--parents", "-n", "1", publication).split()
    if len(parents) != 2:
        raise EvidenceError("publication must have exactly one parent; merge publication rejected")
    if parents[1] != candidate:
        raise EvidenceError("publication must be the direct child of the explicit candidate")
    if not _is_ancestor(root, publication, "HEAD"):
        raise EvidenceError("current HEAD must descend from the explicit publication")

    expected_paths, validation_relative = _publication_paths(root, publication)
    changed = set(
        _git(
            root,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            publication,
        ).splitlines()
    )
    if changed != expected_paths:
        raise EvidenceError("publication commit must change exactly the four evidence paths")

    publication_bytes: dict[str, bytes] = {}
    for path in sorted(expected_paths):
        publication_oid = _git_blob_oid(root, publication, path)
        head_oid = _git_blob_oid(root, "HEAD", path)
        if publication_oid != head_oid:
            raise EvidenceError(f"publication blob changed at later HEAD: {path}")
        published = _git_blob_bytes(root, publication_oid, path=path)
        current = _git_blob_bytes(root, head_oid, path=path)
        if published != current:
            raise EvidenceError(f"publication blob bytes changed at later HEAD: {path}")
        publication_bytes[path] = published

    manifest_relative = "docs/security/phase-473-evidence-manifest.json"
    manifest = _blob_json(publication_bytes[manifest_relative], path=manifest_relative)
    if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("candidate_sha") != candidate:
        raise EvidenceError("publication manifest identity drift")
    expected_artifacts = expected_paths - {manifest_relative}
    artifacts = manifest.get("artifacts")
    if (
        not isinstance(artifacts, list)
        or not all(isinstance(row, dict) for row in artifacts)
        or len(artifacts) != len(expected_artifacts)
        or {row.get("path") for row in artifacts} != expected_artifacts
    ):
        raise EvidenceError("manifest must hash results, evidence, and validation only")
    if any(row.get("path") == manifest_relative for row in artifacts):
        raise EvidenceError("manifest cannot hash itself")
    for row in artifacts:
        data = publication_bytes[row["path"]]
        if row.get("bytes") != len(data) or row.get("sha256") != sha256(data).hexdigest():
            raise EvidenceError("publication artifact hash drift")
    results_relative = "docs/security/phase-473-evidence-results.json"
    results = _blob_json(publication_bytes[results_relative], path=results_relative)
    if results.get("candidate_sha") != candidate:
        raise EvidenceError("results candidate drift")
    for path in (
        "docs/security/phase-473-evidence.md",
        validation_relative,
    ):
        try:
            narrative = publication_bytes[path].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EvidenceError(f"publication narrative is not UTF-8: {path}") from exc
        if candidate not in narrative:
            raise EvidenceError("narrative candidate binding missing")
    if _privacy_match_count_bytes(publication_bytes.values(), DENYLIST_PATH):
        raise EvidenceError("publication privacy denylist match")
    if results.get("schema_version") == RESULT_SCHEMA:
        coverage = results.get("coverage")
        if not isinstance(coverage, dict):
            raise EvidenceError("publication coverage missing")
        for key, expected in (
            ("requirements", set(REQUIREMENTS)),
            ("decisions", set(DECISIONS)),
            ("review_findings", set(FINDING_CONTRACTS)),
            ("gap_truths", {identifier for identifier, _ in GAP_TRUTH_CONTRACTS}),
        ):
            rows = coverage.get(key, [])
            if len(rows) != len(expected) or {row.get("id") for row in rows} != expected:
                raise EvidenceError(f"publication {key} cardinality drift")
        for key, contracts in FINAL_GAP_NODE_CONTRACTS.items():
            rows = coverage.get(key, [])
            expected_selectors = {selector for selector, _, _ in contracts}
            if (
                len(rows) != len(expected_selectors)
                or {row.get("selector") for row in rows} != expected_selectors
            ):
                raise EvidenceError(f"publication {key} cardinality drift")
        local_gate_ids = {row["gate_id"] for row in results.get("receipts", [])}
        if not set(FINAL_GAP_GATE_MODULES) <= local_gate_ids:
            raise EvidenceError("publication final-gap gate registry missing")
        verify_external_obligations(
            results.get("external_obligations", []),
            local_gate_ids=local_gate_ids,
        )
        if results.get("privacy", {}).get("match_count") != 0:
            raise EvidenceError("results privacy claim drift")


def _render_evidence(result: dict[str, Any]) -> str:
    candidate = result["candidate_sha"]
    coverage = result["coverage"]
    receipts = result["receipts"]
    lines = [
        "# Phase 473 checked privacy and practice-integrity evidence",
        "",
        f"Immutable candidate: `{candidate}`. Phase base: `{result['phase_base_sha']}`.",
        "All observations are local deterministic tests/fakes; external obligations remain NOT RUN.",
        "",
        "## Checked gate receipts",
        "",
        "| Gate | Nodes | Fail | Error | Skip | XFAIL | XPASS | Privacy | Result |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in receipts:
        counts = row["counts"]
        lines.append(
            f"| `{row['gate_id']}` | {counts['total']} | {counts['failed']} | "
            f"{counts['error']} | {counts['skipped']} | {counts['xfail']} | "
            f"{counts['xpass']} | {row['privacy']['match_count']} | PASS |"
        )
    lines.extend(
        [
            "",
            "## Raw receipt integrity",
            "",
            "Every argv below is an exact JSON array executed without a shell. UTC bounds, "
            "raw log/JUnit/node-manifest byte counts, and SHA-256 values are independently "
            "recomputed by `verify-capture`.",
            "",
            "| Gate | Exact argv | UTC bounds | Log SHA-256/bytes | JUnit SHA-256/bytes | Node SHA-256/bytes |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in receipts:
        artifacts = row["artifacts"]
        lines.append(
            f"| `{row['gate_id']}` | `{json.dumps(row['argv'], separators=(',', ':'))}` | "
            f"`{row['started_at']}` → `{row['ended_at']}` | "
            f"`{artifacts['log']['sha256']}`/{artifacts['log']['bytes']} | "
            f"`{artifacts['junit']['sha256']}`/{artifacts['junit']['bytes']} | "
            f"`{artifacts['node_manifest']['sha256']}`/"
            f"{artifacts['node_manifest']['bytes']} |"
        )
    lines.extend(
        [
            "",
            "## Requirement proof",
            "",
            "| Requirement | Observed node | Result |",
            "| --- | --- | --- |",
        ]
    )
    for row in coverage["requirements"]:
        required_nodes = ", ".join(
            f"`{item['node_id']}`" for item in row["required_lower_nodes"]
        ) or "—"
        lines.append(
            f"| {row['id']} | `{row['node_id']}`<br>Required final-gap: "
            f"{required_nodes} | {row['result']} |"
        )
    lines.extend(
        [
            "",
            "## Decision proof",
            "",
            "| Decision | Observed node | Result |",
            "| --- | --- | --- |",
        ]
    )
    for row in coverage["decisions"]:
        required_nodes = ", ".join(
            f"`{item['node_id']}`" for item in row["required_lower_nodes"]
        ) or "—"
        lines.append(
            f"| {row['id']} | `{row['node_id']}`<br>Required final-gap: "
            f"{required_nodes} | {row['result']} |"
        )
    lines.extend(
        [
            "",
            "## Retained verification/review findings",
            "",
            "| Finding | Observed node | Lower fake(s) | Observed condition | Result |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in result["finding_adjudications"]:
        lower_fakes = "<br>".join(f"`{item}`" for item in row["lower_fake_targets"])
        lines.append(
            f"| {row['id']} | `{row['node_id']}` | {lower_fakes} | "
            f"{row['observed_condition']} | {row['result']} |"
        )
    lines.extend(
        [
            "",
            "## Final-gap observed matrices",
            "",
            "The following rows are runtime lower-fake observations. Source-string or "
            "collection-only assertions cannot satisfy these selectors.",
            "",
            "| Truth | Exact observed node | Lower fake | Observed condition |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in coverage["gap_truths"]:
        lines.append(
            f"| `{row['id']}` | `{row['node_id']}` | "
            f"`{row['lower_fake_target']}` | {row['observed_condition']} |"
        )
    for title, section in (
        ("Deletion lease, timestamp, and parent-CAS matrix", "claim_fence_nodes"),
        ("Legacy/malformed/global/deletion-race delivery matrix", "delivery_scope_nodes"),
        ("Pre-effect/inflight/post-acceptance crash matrix", "crash_state_nodes"),
    ):
        lines.extend(
            [
                "",
                f"### {title}",
                "",
                "| Exact observed node | Lower fake | Observed condition |",
                "| --- | --- | --- |",
            ]
        )
        for row in coverage[section]:
            lines.append(
                f"| `{row['node_id']}` | `{row['lower_fake_target']}` | "
                f"{row['observed_condition']} |"
            )
    lines.extend(
        [
            "",
            "The deletion matrix explicitly covers unexpired refusal, one expired takeover, "
            "stale write/finalization denial, valid production UTC construction, and parent-row "
            "CAS conflict/rescan. The crash matrix separates pre-effect reclaim, durable inflight "
            "ambiguity, provider acceptance, and terminal replay. The delivery matrix covers "
            "strong legacy owner joins, missing/malformed/stale metadata, sealed-global validation, "
            "and zero email/push/WebSocket provider counters for every denied or deletion-raced path.",
            "",
            "## Checked inventory artifacts",
            "",
            "| Artifact | Bytes | SHA-256 |",
            "| --- | ---: | --- |",
        ]
    )
    for name, meta in sorted(result["inventory_artifacts"].items()):
        lines.append(f"| `{name}` | {meta['bytes']} | `{meta['sha256']}` |")
    lines.extend(
        [
            "",
            "## Complete boundary appendices",
            "",
            f"The checked results contain {len(coverage['read_boundaries'])} read dataflows, "
            f"{len(coverage['private_writes'])} private writes, {len(coverage['branches'])} exact "
            f"deletion branches, and {len(coverage['retained_policy'])} retained-policy rows, each "
            "mapped exactly once to observed nodes. Purge/no-resurrection selectors are included.",
            "Legal-retention-blocked material remains retained policy debt. Provider accepted, "
            "delivered, or acceptance-unknown copies remain outside backend purge authority and "
            "are never labeled deleted. Only purgeable exact absence is called purged.",
            "",
            "## External obligations",
            "",
            "| Obligation | Status | Owner |",
            "| --- | --- | --- |",
        ]
    )
    for row in result["external_obligations"]:
        lines.append(f"| `{row['id']}` | **{row['status']}** | Phase {row['owner_phase']} |")
    return "\n".join(lines) + "\n"


def _render_validation(result: dict[str, Any]) -> str:
    candidate = result["candidate_sha"]
    receipt_counts = {
        row["gate_id"]: row["counts"]["total"] for row in result["receipts"]
    }
    return (
        "---\nphase: 473\nslug: student-content-privacy-and-practice-integrity\n"
        "status: local_gates_complete\nnyquist_compliant: true\n"
        f"testedSourceSha: {candidate}\n---\n\n"
        "# Phase 473 — checked final validation\n\n"
        f"All local observations derive from immutable candidate `{candidate}`. "
        f"The strict full suite observed {result['observed_full_suite_count']} nodes.\n\n"
        "Dedicated final-gap receipts observed "
        f"{receipt_counts['P473-DELETION-CLAIM-FENCING']} deletion-claim nodes, "
        f"{receipt_counts['P473-DELIVERY-INTENT-RECOVERY']} delivery-recovery nodes, "
        f"{receipt_counts['P473-PRIVATE-DELIVERY-FENCING']} private-delivery nodes, and "
        f"{receipt_counts['P473-FINAL-GAP-REGRESSION']} combined regression nodes. "
        "CR-01, CR-02, WR-01, WR-02, and WR-03 map to exact runtime lower fakes.\n\n"
        "Every receipt has exact argv, UTC bounds, clean candidate state, raw log/JUnit/node "
        "hashes, recomputed counts, and zero denylist matches. Requirements V9PRIV-01/02/03, "
        "D-01 through D-22, all checked read/private-store boundaries, exact 17 branches, and "
        "retained-policy rows map to observed nodes in the checked results JSON. The checked "
        "matrices include two-worker unexpired/expired takeover, stale write/finalization, valid "
        "production UTC, parent CAS conflict/rescan, pre-effect/inflight/post-acceptance crash "
        "states, strong legacy owner joins, malformed/stale/global delivery classification, and "
        "zero provider calls for denied/deletion-raced effects.\n\n"
        "Real S3 multipart/versioning, deployed cleanup scheduler/IaC, and production logs are "
        "separate NOT RUN obligations owned by Phases 479/480. No external deletion is inferred; "
        "legal holds and accepted/delivered provider copies are not called purged.\n"
    )


def publish(candidate: str, capture_root: Path) -> None:
    result = verify_capture(candidate, capture_root)
    _write_json(RESULTS_PATH, result)
    EVIDENCE_PATH.write_text(_render_evidence(result), encoding="utf-8")
    VALIDATION_PATH.write_text(_render_validation(result), encoding="utf-8")
    _write_json(
        MANIFEST_PATH,
        {
            "schema_version": MANIFEST_SCHEMA,
            "candidate_sha": candidate,
            "artifacts": [
                _artifact_meta(path) for path in (RESULTS_PATH, EVIDENCE_PATH, VALIDATION_PATH)
            ],
        },
    )


def privacy_denial(capture_root: Path, denylist: Path) -> None:
    paths = sorted(
        path for path in capture_root.rglob("*")
        if path.is_file() and path.name not in {"capture.json", "checked-result.json"}
    )
    paths.extend((BOUNDARY_PATH, PRIVATE_PATH, POLICY_PATH, ROUTE_PATH))
    if _privacy_match_count(paths, denylist):
        raise EvidenceError("privacy denylist match")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("capture", "verify-capture", "publish"):
        child = subparsers.add_parser(command)
        child.add_argument("--candidate", required=True)
        child.add_argument("--capture-root", required=True, type=Path)
    publication = subparsers.add_parser("verify-publication")
    publication.add_argument("--candidate", required=True)
    publication.add_argument("--publication", required=True)
    denial = subparsers.add_parser("privacy-denial")
    denial.add_argument("--capture-root", required=True, type=Path)
    denial.add_argument("--denylist", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            capture(args.candidate, args.capture_root)
        elif args.command == "verify-capture":
            verify_capture(args.candidate, args.capture_root)
        elif args.command == "publish":
            publish(args.candidate, args.capture_root)
        elif args.command == "verify-publication":
            verify_publication(ROOT, args.candidate, args.publication)
        else:
            privacy_denial(args.capture_root, args.denylist)
    except (EvidenceError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"phase473 evidence verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
