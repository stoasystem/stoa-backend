"""Executable contract for source-bound Phase 473 evidence."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = ROOT / "scripts" / "verify_phase473_evidence.py"
GUARD_PATH = ROOT / "scripts" / "phase473_pytest_guard.py"
DENYLIST = ROOT / "tests" / "fixtures" / "phase473_evidence_denylist.txt"
CANDIDATE = "a" * 40
EXTERNAL = {
    "P479-REAL-S3-MULTIPART-VERSIONING": "479",
    "P480-DEPLOYED-CLEANUP-SCHEDULER-IAC": "480",
    "P480-PRODUCTION-LOGS": "480",
}
FINAL_GAP_GATES = {
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
FINAL_GAP_NODE_GROUPS = {
    "claim_fence_nodes": {
        "tests/test_phase473_account_deletion_claim_fencing.py::test_claim_compares_stored_expiry_with_distinct_current_epoch",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_two_workers_cannot_steal_active_lease_and_only_one_wins_after_expiry",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_branch_result_cas_requires_owner_version_digest_and_returns_next_claim",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_service_invokes_no_branch_or_later_write_after_claim_renewal_loss",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_forged_in_memory_complete_map_cannot_terminalize_durable_incomplete_set",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_repository_rejects_invalid_lifecycle_timestamps",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_production_service_clock_is_nonblank_timezone_aware_utc",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_parent_scrub_is_version_cas_and_never_replaces_concurrent_preferences",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_fresh_parent_rescan_removes_only_child_and_advances_row_version",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_account_profile_row_conflict_stays_retryable_debt",
    },
    "delivery_scope_nodes": {
        "tests/test_phase473_private_delivery_fencing.py::test_strong_event_loader_uses_exact_base_key_and_consistent_read",
        "tests/test_phase473_private_delivery_fencing.py::test_private_push_rejects_missing_malformed_or_stale_persisted_generation",
        "tests/test_phase473_private_delivery_fencing.py::test_legacy_question_owner_resolution_uses_closed_strong_target_join",
        "tests/test_phase473_private_delivery_fencing.py::test_legacy_metadata_only_owner_fails_closed_without_target",
        "tests/test_phase473_private_delivery_fencing.py::test_global_nonprivate_requires_exact_persisted_contract_digest",
        "tests/test_phase473_private_delivery_fencing.py::test_mixed_owner_digest_is_refused_before_email_provider",
        "tests/test_phase473_private_delivery_fencing.py::test_websocket_invalid_persisted_scope_lists_no_connections_and_posts_nothing",
    },
    "crash_state_nodes": {
        "tests/test_phase473_delivery_intent_recovery.py::test_repository_claim_uses_explicit_current_time_not_proposed_expiry",
        "tests/test_phase473_delivery_intent_recovery.py::test_unexpired_pre_effect_claim_and_inflight_are_never_takeover_eligible",
        "tests/test_phase473_delivery_intent_recovery.py::test_begin_private_claim_is_one_fence_plus_exact_version_cas",
        "tests/test_phase473_delivery_intent_recovery.py::test_crash_pre_effect_recovers_only_after_actual_time_passes",
        "tests/test_phase473_delivery_intent_recovery.py::test_crash_after_durable_transition_terminalizes_unknown_without_provider_call",
        "tests/test_phase473_delivery_intent_recovery.py::test_provider_acceptance_lost_response_replays_unknown_without_blind_retry",
        "tests/test_phase473_delivery_intent_recovery.py::test_terminal_completion_lost_response_replays_accepted_without_provider_payload",
        "tests/test_phase473_delivery_intent_recovery.py::test_stale_claim_version_cannot_begin_complete_cancel_or_recover",
        "tests/test_phase473_delivery_intent_recovery.py::test_provider_effect_order_is_recover_fence_transition_call_and_complete",
    },
}


def _load_verifier() -> Any:
    assert VERIFIER_PATH.is_file(), "evidence verifier implementation is missing"
    spec = importlib.util.spec_from_file_location("phase473_evidence_verifier", VERIFIER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _meta(path: Path, logical: str) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "logical_path": logical,
        "captured_path": str(path),
        "bytes": len(data),
        "sha256": sha256(data).hexdigest(),
    }


def _receipt(tmp_path: Path) -> dict[str, Any]:
    log = tmp_path / "raw.log"
    junit = tmp_path / "junit.xml"
    nodes = tmp_path / "nodes.json"
    log.write_text("one safe passing node\n", encoding="utf-8")
    junit.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites tests="1" failures="0" errors="0" skipped="0">'
        '<testsuite name="phase473" tests="1" failures="0" errors="0" skipped="0">'
        '<testcase classname="tests.test_safe" name="test_ok"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "phase-473-pytest-nodes.v1",
        "nodes": [
            {
                "node_id": "tests/test_safe.py::test_ok",
                "outcome": "passed",
                "phases": [{"when": "call", "outcome": "passed", "wasxfail": None}],
            }
        ],
        "counts": {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "error": 0,
            "skipped": 0,
            "xfail": 0,
            "xpass": 0,
        },
    }
    _json(nodes, manifest)
    deny = [line for line in DENYLIST.read_text().splitlines() if line]
    return {
        "gate_id": "SYNTHETIC",
        "argv": [sys.executable, "-m", "pytest", "-q", "tests/test_safe.py"],
        "started_at": "2026-07-18T10:00:00Z",
        "ended_at": "2026-07-18T10:00:01Z",
        "exit_code": 0,
        "candidate_sha": CANDIDATE,
        "before": {"head": CANDIDATE, "clean": True},
        "after": {"head": CANDIDATE, "clean": True},
        "artifacts": {
            "log": _meta(log, "raw/SYNTHETIC.log"),
            "junit": _meta(junit, "junit/SYNTHETIC.xml"),
            "node_manifest": _meta(nodes, "nodes/SYNTHETIC.json"),
        },
        "counts": deepcopy(manifest["counts"]),
        "nodes": deepcopy(manifest["nodes"]),
        "privacy": {
            "denylist_sha256": sha256(DENYLIST.read_bytes()).hexdigest(),
            "entry_count": len(deny),
            "match_count": 0,
        },
    }


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("argv drift", lambda r: r["argv"].append("--maxfail=1")),
        ("nonzero exit", lambda r: r.__setitem__("exit_code", 1)),
        ("candidate drift", lambda r: r["after"].__setitem__("head", "b" * 40)),
        ("wrong candidate", lambda r: r.__setitem__("candidate_sha", "b" * 40)),
        ("dirty before", lambda r: r["before"].__setitem__("clean", False)),
        ("invalid UTC order", lambda r: r.__setitem__("ended_at", "2026-07-17T10:00:00Z")),
        ("changed log hash", lambda r: r["artifacts"]["log"].__setitem__("sha256", "0" * 64)),
        ("empty log", lambda r: r["artifacts"]["log"].__setitem__("bytes", 0)),
        ("count mismatch", lambda r: r["counts"].__setitem__("passed", 2)),
        ("duplicate node", lambda r: r["nodes"].append(deepcopy(r["nodes"][0]))),
        ("skip", lambda r: r["counts"].__setitem__("skipped", 1)),
        ("xfail", lambda r: r["counts"].__setitem__("xfail", 1)),
        ("xpass", lambda r: r["counts"].__setitem__("xpass", 1)),
        ("privacy match", lambda r: r["privacy"].__setitem__("match_count", 1)),
    ],
)
def test_receipt_rejects_every_drift(tmp_path: Path, label: str, mutate: Any) -> None:
    verifier = _load_verifier()
    receipt = _receipt(tmp_path)
    mutate(receipt)
    with pytest.raises(verifier.EvidenceError, match=".+"):
        verifier.verify_receipt(
            receipt,
            expected_gate_id="SYNTHETIC",
            expected_argv=[sys.executable, "-m", "pytest", "-q", "tests/test_safe.py"],
            candidate=CANDIDATE,
            denylist_path=DENYLIST,
        )


def test_receipt_accepts_exact_raw_artifacts(tmp_path: Path) -> None:
    verifier = _load_verifier()
    receipt = _receipt(tmp_path)
    checked = verifier.verify_receipt(
        receipt,
        expected_gate_id="SYNTHETIC",
        expected_argv=receipt["argv"],
        candidate=CANDIDATE,
        denylist_path=DENYLIST,
    )
    assert checked == {"tests/test_safe.py::test_ok": "passed"}


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("def test_skip():\n    import pytest; pytest.skip('no')\n", "skipped"),
        ("import pytest\n@pytest.mark.xfail\ndef test_xfail(): assert False\n", "xfail"),
        ("import pytest\n@pytest.mark.xfail\ndef test_xpass(): assert True\n", "xpass"),
    ],
)
def test_pytest_guard_fails_skip_xfail_and_xpass(
    tmp_path: Path, body: str, expected: str
) -> None:
    assert GUARD_PATH.is_file(), "strict pytest guard implementation is missing"
    test_file = tmp_path / "test_forbidden.py"
    manifest = tmp_path / "nodes.json"
    test_file.write_text(body, encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "scripts.phase473_pytest_guard",
            "-o",
            "xfail_strict=true",
            "--phase473-node-manifest",
            str(manifest),
            str(test_file),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode != 0
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["counts"][expected] == 1


def _coverage_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], set[str]]:
    boundary = json.loads((ROOT / "docs/security/phase-473-boundary-inventory.json").read_text())
    private = json.loads((ROOT / "docs/security/phase-473-private-store-inventory.json").read_text())
    policy = json.loads((ROOT / "docs/security/phase-473-retained-evidence-policy.json").read_text())
    observed = {
        row["malformed_selector"] for row in boundary["rows"]
    } | {
        row[key]
        for row in private["rows"]
        for key in ("purge_selector", "no_resurrection_selector")
    } | {
        row[key]
        for row in private["branch_registry"]
        for key in ("purge_selector", "no_resurrection_selector")
    } | set().union(*FINAL_GAP_NODE_GROUPS.values())
    return boundary, private, policy, observed


def test_registry_contains_exact_dedicated_and_combined_final_gap_gates(
    tmp_path: Path,
) -> None:
    verifier = _load_verifier()
    candidate = _git(ROOT, "rev-parse", "HEAD")
    registry = {row["id"]: row for row in verifier.gate_registry(candidate, tmp_path)}

    for gate_id, modules in FINAL_GAP_GATES.items():
        assert gate_id in registry
        argv = registry[gate_id]["argv"]
        assert argv[-len(modules) :] == list(modules)
        assert "-p" in argv and "scripts.phase473_pytest_guard" in argv
        assert "xfail_strict=true" in argv
    assert set(FINAL_GAP_GATES) <= set(registry)


def test_coverage_is_exact_for_requirements_decisions_boundaries_and_private_stores() -> None:
    verifier = _load_verifier()
    boundary, private, policy, observed = _coverage_fixture()
    coverage = verifier.derive_coverage(boundary, private, policy, observed)
    verifier.verify_coverage(coverage, boundary, private, policy, observed)
    assert {row["id"] for row in coverage["requirements"]} == {
        "V9PRIV-01",
        "V9PRIV-02",
        "V9PRIV-03",
    }
    assert {row["id"] for row in coverage["decisions"]} == {
        f"D-{index:02d}" for index in range(1, 23)
    }
    assert len(coverage["branches"]) == 17
    assert {row["id"] for row in coverage["review_findings"]} == {
        "CR-01",
        "CR-02",
        "WR-01",
        "WR-02",
        "WR-03",
    }
    assert {row["id"] for row in coverage["gap_truths"]} == {
        "current_epoch_claim",
        "two_worker_takeover",
        "stale_write_and_finalization",
        "production_utc_timestamp",
        "parent_row_cas",
        "pre_effect_crash_recovery",
        "inflight_ambiguity_terminalization",
        "legacy_malformed_delivery_denial",
        "sealed_global_validation",
        "deletion_race_zero_provider_effects",
    }
    for section, selectors in FINAL_GAP_NODE_GROUPS.items():
        assert {row["selector"] for row in coverage[section]} == selectors
        assert all(row["node_id"].startswith(row["selector"]) for row in coverage[section])
        assert all(row["lower_fake_target"] and row["observed_condition"] for row in coverage[section])


@pytest.mark.parametrize(
    "missing_selector",
    sorted(set().union(*FINAL_GAP_NODE_GROUPS.values())),
)
def test_final_gap_coverage_rejects_every_missing_lower_node(
    missing_selector: str,
) -> None:
    verifier = _load_verifier()
    boundary, private, policy, observed = _coverage_fixture()
    observed.remove(missing_selector)
    with pytest.raises(verifier.EvidenceError, match="selector not observed"):
        verifier.derive_coverage(boundary, private, policy, observed)


def test_final_gap_coverage_rejects_high_level_or_source_string_substitutes() -> None:
    verifier = _load_verifier()
    boundary, private, policy, observed = _coverage_fixture()
    required = next(iter(FINAL_GAP_NODE_GROUPS["delivery_scope_nodes"]))
    observed.remove(required)
    observed.add(
        "tests/test_source_inventory.py::test_source_contains_provider_call_counter_and_owner_join"
    )
    with pytest.raises(verifier.EvidenceError, match="selector not observed"):
        verifier.derive_coverage(boundary, private, policy, observed)


def test_finding_registry_join_rejects_stale_or_disagreeing_inventory() -> None:
    verifier = _load_verifier()
    boundary, private, policy, observed = _coverage_fixture()
    stale = deepcopy(boundary)
    stale["finding_registry"][0]["runtime_selector"] = (
        "tests/test_source_inventory.py::test_source_mentions_current_epoch"
    )
    with pytest.raises(verifier.EvidenceError, match="finding registry"):
        verifier.derive_coverage(stale, private, policy, observed)


def test_final_gap_coverage_rejects_duplicate_node_mapping() -> None:
    verifier = _load_verifier()
    boundary, private, policy, observed = _coverage_fixture()
    coverage = verifier.derive_coverage(boundary, private, policy, observed)
    duplicate = deepcopy(coverage)
    duplicate["gap_truths"][1]["node_id"] = duplicate["gap_truths"][0]["node_id"]
    with pytest.raises(verifier.EvidenceError, match="coverage|duplicate"):
        verifier.verify_coverage(duplicate, boundary, private, policy, observed)


def test_rendered_publication_exposes_raw_receipts_and_all_final_gap_matrices() -> None:
    verifier = _load_verifier()
    boundary, private, policy, observed = _coverage_fixture()
    coverage = verifier.derive_coverage(boundary, private, policy, observed)
    artifacts = {
        name: {"sha256": name[0] * 64, "bytes": index + 1}
        for index, name in enumerate(("log", "junit", "node_manifest"))
    }
    receipts = [
        {
            "gate_id": gate_id,
            "argv": [sys.executable, "-m", "pytest", *modules],
            "started_at": "2026-07-18T10:00:00Z",
            "ended_at": "2026-07-18T10:00:01Z",
            "artifacts": artifacts,
            "counts": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "error": 0,
                "skipped": 0,
                "xfail": 0,
                "xpass": 0,
            },
            "privacy": {"match_count": 0},
        }
        for gate_id, modules in FINAL_GAP_GATES.items()
    ]
    result = {
        "candidate_sha": CANDIDATE,
        "phase_base_sha": "b" * 40,
        "observed_full_suite_count": 1,
        "receipts": receipts,
        "coverage": coverage,
        "finding_adjudications": coverage["review_findings"],
        "inventory_artifacts": {"boundary_checked": {"bytes": 1, "sha256": "c" * 64}},
        "external_obligations": [
            {"id": item, "status": "NOT RUN", "owner_phase": owner}
            for item, owner in EXTERNAL.items()
        ],
    }

    evidence = verifier._render_evidence(result)
    validation = verifier._render_validation(result)
    for expected in (
        "Raw receipt integrity",
        "Deletion lease, timestamp, and parent-CAS matrix",
        "Legacy/malformed/global/deletion-race delivery matrix",
        "Pre-effect/inflight/post-acceptance crash matrix",
        "zero email/push/WebSocket provider counters",
    ):
        assert expected in evidence
    assert "CR-01, CR-02, WR-01, WR-02, and WR-03" in validation


@pytest.mark.parametrize(
    "section",
    [
        "requirements",
        "decisions",
        "read_boundaries",
        "private_writes",
        "branches",
        "retained_policy",
        "review_findings",
        "gap_truths",
        "claim_fence_nodes",
        "delivery_scope_nodes",
        "crash_state_nodes",
    ],
)
def test_coverage_rejects_missing_or_duplicate_rows(section: str) -> None:
    verifier = _load_verifier()
    boundary, private, policy, observed = _coverage_fixture()
    coverage = verifier.derive_coverage(boundary, private, policy, observed)
    missing = deepcopy(coverage)
    missing[section].pop()
    with pytest.raises(verifier.EvidenceError):
        verifier.verify_coverage(missing, boundary, private, policy, observed)
    duplicate = deepcopy(coverage)
    duplicate[section].append(deepcopy(duplicate[section][0]))
    with pytest.raises(verifier.EvidenceError):
        verifier.verify_coverage(duplicate, boundary, private, policy, observed)


def test_coverage_rejects_policy_and_external_erasure_overclaims() -> None:
    verifier = _load_verifier()
    boundary, private, policy, observed = _coverage_fixture()
    coverage = verifier.derive_coverage(boundary, private, policy, observed)
    coverage["retained_policy"][0]["result"] = "purged"
    with pytest.raises(verifier.EvidenceError, match="retained|purged"):
        verifier.verify_coverage(coverage, boundary, private, policy, observed)
    obligations = [
        {"id": item, "status": "NOT RUN", "owner_phase": owner}
        for item, owner in EXTERNAL.items()
    ]
    verifier.verify_external_obligations(obligations, local_gate_ids=set())
    obligations[0]["status"] = "PASS"
    with pytest.raises(verifier.EvidenceError):
        verifier.verify_external_obligations(obligations, local_gate_ids=set())


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return completed.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "docs/security/phase-473-evidence-results.json")
    _git(repo, "add", "docs/security/phase-473-evidence.md")
    _git(repo, "add", "docs/security/phase-473-evidence-manifest.json")
    _git(repo, "add", ".planning/phases/473-test/473-VALIDATION.md")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def test_candidate_snapshot_reads_immutable_git_blobs_not_publication_child(
    tmp_path: Path,
) -> None:
    verifier = _load_verifier()
    repo = tmp_path / "snapshot-repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "phase473@example.invalid")
    _git(repo, "config", "user.name", "Phase 473 Test")
    source = repo / "source.py"
    source.write_text("VALUE = 0\n", encoding="utf-8")
    _git(repo, "add", "source.py")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    candidate_bytes = b"VALUE = 1\n"
    source.write_bytes(candidate_bytes)
    _git(repo, "add", "source.py")
    _git(repo, "commit", "-m", "candidate")
    candidate = _git(repo, "rev-parse", "HEAD")
    source.write_text("VALUE = 2\n", encoding="utf-8")
    _git(repo, "add", "source.py")
    _git(repo, "commit", "-m", "publication child")
    verifier.ROOT = repo
    verifier.BOUNDARY_PATH = source
    verifier.PRIVATE_PATH = source
    verifier.POLICY_PATH = source
    verifier.ROUTE_PATH = source

    snapshot = verifier._candidate_snapshot(base, candidate)

    assert snapshot == [
        {
            "path": "source.py",
            "bytes": len(candidate_bytes),
            "sha256": sha256(candidate_bytes).hexdigest(),
        }
    ]


def _publication_repo(tmp_path: Path, *, commit: bool = True) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "phase473@example.invalid")
    _git(repo, "config", "user.name", "Phase 473 Test")
    (repo / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "source.py")
    _git(repo, "commit", "-m", "candidate")
    results = repo / "docs/security/phase-473-evidence-results.json"
    evidence = repo / "docs/security/phase-473-evidence.md"
    validation = repo / ".planning/phases/473-test/473-VALIDATION.md"
    manifest = repo / "docs/security/phase-473-evidence-manifest.json"
    _json(results, {"schema_version": "stale"})
    evidence.write_text("stale evidence\n", encoding="utf-8")
    validation.parent.mkdir(parents=True, exist_ok=True)
    validation.write_text("stale validation\n", encoding="utf-8")
    _json(manifest, {"schema_version": "stale"})
    _commit(repo, "candidate evidence baseline")
    candidate = _git(repo, "rev-parse", "HEAD")
    _json(results, {"schema_version": "phase-473-test-results.v1", "candidate_sha": candidate})
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(f"candidate `{candidate}`\n", encoding="utf-8")
    validation.parent.mkdir(parents=True, exist_ok=True)
    validation.write_text(f"testedSourceSha: {candidate}\n", encoding="utf-8")
    artifacts = []
    for path in (results, evidence, validation):
        data = path.read_bytes()
        artifacts.append(
            {
                "path": path.relative_to(repo).as_posix(),
                "bytes": len(data),
                "sha256": sha256(data).hexdigest(),
            }
        )
    _json(
        manifest,
        {
            "schema_version": "phase-473-evidence-manifest.v2",
            "candidate_sha": candidate,
            "artifacts": artifacts,
        },
    )
    if commit:
        _commit(repo, "publication")
    return repo, candidate


@pytest.mark.parametrize("mutation", ["hash", "self", "parent", "extra", "dirty"])
def test_publication_rejects_hash_ancestry_path_and_cleanliness_drift(
    tmp_path: Path, mutation: str
) -> None:
    verifier = _load_verifier()
    repo, candidate = _publication_repo(tmp_path)
    manifest_path = repo / "docs/security/phase-473-evidence-manifest.json"
    if mutation == "hash":
        data = json.loads(manifest_path.read_text())
        data["artifacts"][0]["sha256"] = "0" * 64
        _json(manifest_path, data)
    elif mutation == "self":
        data = json.loads(manifest_path.read_text())
        data["artifacts"].append(
            {"path": "docs/security/phase-473-evidence-manifest.json", "bytes": 1, "sha256": "0" * 64}
        )
        _json(manifest_path, data)
    elif mutation == "parent":
        _git(repo, "commit", "--allow-empty", "-m", "wrong parent")
    elif mutation == "extra":
        (repo / "extra.txt").write_text("extra\n", encoding="utf-8")
        _git(repo, "add", "extra.txt")
        _git(repo, "commit", "-m", "extra path")
    elif mutation == "dirty":
        (repo / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(verifier.EvidenceError):
        verifier.verify_publication(repo, candidate, dirty=False)


def test_publication_accepts_exact_direct_four_path_child(tmp_path: Path) -> None:
    verifier = _load_verifier()
    repo, candidate = _publication_repo(tmp_path)
    verifier.verify_publication(repo, candidate, dirty=False)


def test_publication_accepts_exact_dirty_four_path_draft(tmp_path: Path) -> None:
    verifier = _load_verifier()
    repo, candidate = _publication_repo(tmp_path, commit=False)
    verifier.verify_publication(repo, candidate, dirty=True)
