"""Adversarial contract for the source-bound Phase 475 evidence verifier."""

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
VERIFIER_PATH = ROOT / "scripts" / "verify_phase475.py"
CANDIDATE = "a" * 40


def _load_verifier() -> Any:
    spec = importlib.util.spec_from_file_location("phase475_evidence_verifier", VERIFIER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return completed.stdout.strip()


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _meta(path: Path, logical: str) -> dict[str, object]:
    data = path.read_bytes()
    return {"logical_path": logical, "bytes": len(data), "sha256": sha256(data).hexdigest()}


def _receipt_fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    verifier = _load_verifier()
    capture = tmp_path / "capture"
    raw = capture / "raw/SYNTHETIC.log"
    junit = capture / "junit/SYNTHETIC.xml"
    nodes = capture / "nodes/SYNTHETIC.json"
    raw.parent.mkdir(parents=True)
    junit.parent.mkdir(parents=True)
    nodes.parent.mkdir(parents=True)
    raw.write_text("one safe passing node\n", encoding="utf-8")
    junit.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">'
        '<testcase classname="tests.test_safe" name="test_ok"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    node_payload = {
        "schema_version": verifier.NODE_SCHEMA,
        "nodes": [{"node_id": "tests/test_safe.py::test_ok", "outcome": "passed"}],
        "counts": {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "error": 0,
            "skipped": 0,
            "xfail": 0,
            "xpass": 0,
        },
        "collection_sha256": sha256(b"tests/test_safe.py::test_ok\n").hexdigest(),
    }
    _json(nodes, node_payload)
    gate = {
        "id": "SYNTHETIC",
        "kind": "pytest",
        "argv": [sys.executable, "-m", "pytest", "-q", "tests/test_safe.py"],
    }
    payloads = (raw.read_bytes(), junit.read_bytes(), nodes.read_bytes())
    receipt = {
        "gate_id": "SYNTHETIC",
        "kind": "pytest",
        "argv": list(gate["argv"]),
        "started_at": "2026-07-22T01:00:00Z",
        "ended_at": "2026-07-22T01:00:01Z",
        "exit_code": 0,
        "candidate_sha": CANDIDATE,
        "before": {"head": CANDIDATE, "clean": True},
        "after": {"head": CANDIDATE, "clean": True},
        "artifacts": {
            "log": _meta(raw, "raw/SYNTHETIC.log"),
            "junit": _meta(junit, "junit/SYNTHETIC.xml"),
            "node_manifest": _meta(nodes, "nodes/SYNTHETIC.json"),
        },
        "counts": deepcopy(node_payload["counts"]),
        "nodes": deepcopy(node_payload["nodes"]),
        "privacy": verifier._privacy_contract(payloads),
    }
    return receipt, gate


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("argv", lambda row: row["argv"].append("--maxfail=1")),
        ("exit", lambda row: row.__setitem__("exit_code", 1)),
        ("candidate", lambda row: row.__setitem__("candidate_sha", "b" * 40)),
        ("dirty", lambda row: row["after"].__setitem__("clean", False)),
        ("time", lambda row: row.__setitem__("ended_at", "2026-07-21T01:00:00Z")),
        ("hash", lambda row: row["artifacts"]["log"].__setitem__("sha256", "0" * 64)),
        ("count", lambda row: row["counts"].__setitem__("passed", 2)),
        ("skip", lambda row: row["counts"].__setitem__("skipped", 1)),
        ("privacy", lambda row: row["privacy"].__setitem__("match_count", 1)),
    ],
)
def test_receipt_rejects_every_source_outcome_and_privacy_drift(
    tmp_path: Path, label: str, mutate: Any
) -> None:
    verifier = _load_verifier()
    receipt, gate = _receipt_fixture(tmp_path)
    mutate(receipt)
    with pytest.raises(verifier.EvidenceError, match=".+"):
        verifier.verify_receipt(receipt, gate, CANDIDATE, tmp_path / "capture")


def test_receipt_accepts_exact_strict_artifacts(tmp_path: Path) -> None:
    verifier = _load_verifier()
    receipt, gate = _receipt_fixture(tmp_path)
    assert verifier.verify_receipt(
        receipt, gate, CANDIDATE, tmp_path / "capture"
    ) == {"tests/test_safe.py::test_ok"}


def _all_coverage_nodes(verifier: Any) -> set[str]:
    contracts = (
        verifier.REQUIREMENT_CONTRACTS,
        verifier.DECISION_CONTRACTS,
        verifier.FINDING_CONTRACTS,
        verifier.FOLLOW_UP_CONTRACTS,
    )
    return {
        selector
        for registry in contracts
        for selectors in registry.values()
        for selector in selectors
    }


def test_closed_coverage_maps_all_requirements_decisions_findings_and_followups() -> None:
    verifier = _load_verifier()
    observed = _all_coverage_nodes(verifier)
    coverage = verifier.derive_coverage(observed)
    verifier.verify_coverage(coverage, observed)
    assert {row["id"] for row in coverage["requirements"]} == {
        f"V9DATA-{index:02d}" for index in range(1, 9)
    }
    assert {row["id"] for row in coverage["decisions"]} == {
        f"D-{index:02d}" for index in range(1, 17)
    }
    assert {row["id"] for row in coverage["audit_findings"]} == {
        "DATA-001",
        "BUG-002",
        "DATA-003",
        "BUG-006",
        "BUG-004",
    }
    assert {row["id"] for row in coverage["phase473_follow_ups"]} == {
        "profile-version-cas",
        "delivery-begin-dependency-classification",
        "completed-deletion-replay",
    }


@pytest.mark.parametrize(
    "selector",
    [
        "tests/test_phase475_question_admission.py::test_concurrent_identical_keys_commit_one_complete_admission",
        "tests/test_phase475_question_reconciliation.py::test_each_terminal_transaction_boundary_fails_without_partial_compensation",
        "tests/test_phase475_teacher_takeover.py::test_two_barrier_claimants_produce_one_owner_session_and_private_loser",
        "tests/test_phase475_parent_binding_reconciliation.py::test_changed_after_preview_is_skipped_and_new_data_is_preserved",
        "tests/test_phase475_profile_version_cas.py::test_real_locale_writer_races_real_scrub_and_preserves_exact_latest_bytes",
        "tests/test_phase475_rate_limit.py::test_repeating_429_requests_leave_counter_exactly_at_limit",
        "tests/test_phase475_delivery_begin.py::test_dependency_failure_remains_recoverable_then_healthy_retry_delivers_once",
        "tests/test_phase475_completed_deletion_replay.py::test_real_endpoint_replays_stored_terminal_receipt_with_zero_new_effects",
    ],
)
def test_coverage_rejects_missing_lower_failure_concurrency_or_effect_node(
    selector: str,
) -> None:
    verifier = _load_verifier()
    observed = _all_coverage_nodes(verifier)
    observed.remove(selector)
    with pytest.raises(verifier.EvidenceError, match="selector not observed"):
        verifier.derive_coverage(observed)


def test_source_string_substitute_cannot_replace_runtime_lower_node() -> None:
    verifier = _load_verifier()
    observed = _all_coverage_nodes(verifier)
    required = (
        "tests/test_phase475_profile_version_cas.py::"
        "test_real_locale_writer_races_real_scrub_and_preserves_exact_latest_bytes"
    )
    observed.remove(required)
    observed.add("tests/test_source_scan.py::test_source_mentions_profile_race")
    with pytest.raises(verifier.EvidenceError, match="selector not observed"):
        verifier.derive_coverage(observed)


def test_registry_uses_phase474_full_argv_and_all_runtime_static_targets(
    tmp_path: Path,
) -> None:
    verifier = _load_verifier()
    candidate = _git(ROOT, "rev-parse", "HEAD")
    registry = {row["id"]: row for row in verifier.gate_registry(candidate, tmp_path)}
    formal = registry["P475-PHASE474-FORMAL-EXTENSION"]["argv"]
    assert formal[:6] == [
        str(ROOT / ".venv/bin/python"),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:socket",
    ]
    runtime = verifier._phase_runtime_files(candidate)
    assert set(runtime) <= set(registry["RUFF-PHASE475"]["argv"])
    assert set(runtime) <= set(registry["MYPY-PHASE475-CHANGED-LINES"]["argv"])


def test_targeted_mypy_rejects_only_diagnostics_on_candidate_changed_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _load_verifier()
    files = ["src/stoa/example.py"]
    monkeypatch.setattr(verifier, "_phase_runtime_files", lambda candidate: files)
    monkeypatch.setattr(verifier, "_changed_lines", lambda base, candidate, path: {10, 11})

    class _Completed:
        returncode = 1
        stdout = b"src/stoa/example.py:9: error: old\nsrc/stoa/example.py:10: error: new\n"
        stderr = b""

    monkeypatch.setattr(verifier, "_run", lambda argv: _Completed())
    result = verifier.targeted_mypy("b" * 40, "c" * 40, files)
    assert result["status"] == "FAIL"
    assert result["pre_existing_diagnostic_count"] == 1
    assert result["changed_line_diagnostic_count"] == 1


def _publication_repo(tmp_path: Path) -> tuple[Path, str, str]:
    verifier = _load_verifier()
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "phase475@example.invalid")
    _git(repo, "config", "user.name", "Phase 475 Test")
    (repo / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "source.py")
    _git(repo, "commit", "-m", "candidate")
    candidate = _git(repo, "rev-parse", "HEAD")
    evidence = repo / "docs/security/phase-475-evidence.md"
    results = repo / "docs/security/phase-475-evidence-results.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(f"candidate `{candidate}`\n", encoding="utf-8")
    result = {
        "schema_version": verifier.RESULT_SCHEMA,
        "candidate_sha": candidate,
        "evidence_markdown": {
            "path": evidence.relative_to(repo).as_posix(),
            "bytes": len(evidence.read_bytes()),
            "sha256": sha256(evidence.read_bytes()).hexdigest(),
        },
        "external_obligations": [
            {"id": item, "status": status, "owner_phase": owner}
            for item, status, owner in verifier.EXTERNAL_OBLIGATIONS
        ],
        "receipts": [],
        "coverage": {
            "requirements": [],
            "decisions": [],
            "audit_findings": [],
            "phase473_follow_ups": [],
        },
    }
    _json(results, result)
    _git(repo, "add", results.relative_to(repo).as_posix())
    _git(repo, "add", evidence.relative_to(repo).as_posix())
    _git(repo, "commit", "-m", "publication")
    publication = _git(repo, "rev-parse", "HEAD")
    return repo, candidate, publication


def test_publication_is_direct_source_bound_and_immutable_at_later_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _load_verifier()
    repo, _, _ = _publication_repo(tmp_path)
    _git(repo, "commit", "--allow-empty", "-m", "later metadata")
    monkeypatch.setattr(verifier, "REQUIREMENT_CONTRACTS", {})
    monkeypatch.setattr(verifier, "DECISION_CONTRACTS", {})
    monkeypatch.setattr(verifier, "FINDING_CONTRACTS", {})
    monkeypatch.setattr(verifier, "FOLLOW_UP_CONTRACTS", {})
    verifier.verify_publication(repo)


def test_publication_rejects_later_blob_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _load_verifier()
    repo, _, _ = _publication_repo(tmp_path)
    evidence = repo / "docs/security/phase-475-evidence.md"
    evidence.write_text(evidence.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    _git(repo, "add", evidence.relative_to(repo).as_posix())
    _git(repo, "commit", "-m", "mutate evidence")
    monkeypatch.setattr(verifier, "REQUIREMENT_CONTRACTS", {})
    monkeypatch.setattr(verifier, "DECISION_CONTRACTS", {})
    monkeypatch.setattr(verifier, "FINDING_CONTRACTS", {})
    monkeypatch.setattr(verifier, "FOLLOW_UP_CONTRACTS", {})
    with pytest.raises(verifier.EvidenceError, match="blob changed"):
        verifier.verify_publication(repo)


def test_rendered_evidence_is_candidate_bound_redacted_and_not_run_exact() -> None:
    verifier = _load_verifier()
    coverage = verifier.derive_coverage(_all_coverage_nodes(verifier))
    result = {
        "candidate_sha": CANDIDATE,
        "phase_base_sha": "b" * 40,
        "receipts": [
            {
                "gate_id": "MYPY-PHASE475-CHANGED-LINES",
                "kind": "mypy",
                "counts": {},
                "exit_code": 0,
                "privacy": {"match_count": 0},
                "analysis": {
                    "changed_line_diagnostic_count": 0,
                    "pre_existing_diagnostic_count": 179,
                },
            }
        ],
        "coverage": coverage,
        "phase475_runtime_files": ["src/stoa/example.py"],
        "external_obligations": [
            {"id": item, "status": status, "owner_phase": owner}
            for item, status, owner in verifier.EXTERNAL_OBLIGATIONS
        ],
        "privacy": {"raw_match_count": 0, "published_match_count": 0},
    }
    rendered = verifier._render_evidence(result)
    assert CANDIDATE in rendered
    assert rendered.count("**NOT RUN**") == 3
    assert verifier._privacy_matches((rendered.encode("utf-8"),)) == 0
