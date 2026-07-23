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
        verifier.REVIEW_FINDING_CONTRACTS,
        verifier.REVIEW_WARNING_CONTRACTS,
    )
    return {
        selector
        for registry in contracts
        for selectors in registry.values()
        for selector in selectors
    }


def test_coverage_registry_requires_all_truthful_gap_nodes() -> None:
    verifier = _load_verifier()
    expected_modules = (
        "tests/test_phase475_question_admission.py",
        "tests/test_phase475_question_replay.py",
        "tests/test_phase475_question_reconciliation.py",
        "tests/test_phase475_question_state_cas.py",
        "tests/test_phase475_question_effect_recovery.py",
        "tests/test_phase475_teacher_takeover.py",
        "tests/test_phase475_teacher_takeover_effect.py",
        "tests/test_phase475_parent_binding_transaction.py",
        "tests/test_phase475_parent_binding_reconciliation.py",
        "tests/test_phase475_profile_version_cas.py",
        "tests/test_phase475_rate_limit.py",
        "tests/test_phase475_mistake_answer.py",
        "tests/test_phase475_delivery_begin.py",
        "tests/test_phase475_completed_deletion_replay.py",
        "tests/test_phase475_deletion_discovery.py",
        "tests/test_phase475_deletion_relationship_scrub.py",
        "tests/test_phase475_deletion_teacher_identity_scrub.py",
        "tests/test_phase475_deletion_notification_identity_scrub.py",
    )
    assert verifier.PHASE475_MODULES == expected_modules

    observed = _all_coverage_nodes(verifier)
    coverage = verifier.derive_coverage(observed)
    verifier.verify_coverage(coverage, observed)
    assert set(coverage) == {
        "requirements",
        "decisions",
        "review_findings",
        "review_warnings",
    }
    assert {row["id"] for row in coverage["requirements"]} == {
        f"V9DATA-{index:02d}" for index in range(1, 9)
    }
    assert {row["id"] for row in coverage["decisions"]} == {
        f"D-{index:02d}" for index in range(1, 17)
    }
    assert {row["id"] for row in coverage["review_findings"]} == {
        f"CR-{index:02d}" for index in range(1, 11)
    }
    assert {row["id"] for row in coverage["review_warnings"]} == {
        f"WR-{index:02d}" for index in range(1, 5)
    }

    cr10 = verifier.REVIEW_FINDING_CONTRACTS["CR-10"]
    assert cr10 == (
        "tests/test_phase475_deletion_discovery.py::test_cross_account_identity_registry_and_two_clean_epochs",
        "tests/test_phase475_deletion_relationship_scrub.py::test_relationship_identity_scrub_retries_cas_then_requires_two_clean_epochs",
        "tests/test_phase475_deletion_teacher_identity_scrub.py::test_teacher_identity_scrub_preserves_student_question_and_requires_two_clean_epochs",
        "tests/test_phase475_deletion_notification_identity_scrub.py::test_notification_identity_scrub_retries_cas_then_requires_two_clean_epochs",
    )
    assert set(cr10).isdisjoint(
        selector
        for selectors in verifier.DECISION_CONTRACTS.values()
        for selector in selectors
    )
    assert verifier.DECISION_CONTRACTS["D-08"] == (
        "tests/test_phase475_teacher_takeover.py::test_two_barrier_claimants_produce_one_owner_session_and_private_loser",
    )
    assert verifier.REVIEW_FINDING_CONTRACTS["CR-04"] == (
        "tests/test_phase475_teacher_takeover.py::test_stale_authorized_teacher_lifecycle_race_rolls_back_every_artifact",
    )
    assert verifier.DECISION_CONTRACTS["D-13"] == (
        "tests/test_phase475_rate_limit.py::test_replay_returns_original_receipt_after_intervening_accepted_and_rejected_traffic",
    )
    assert verifier.REVIEW_FINDING_CONTRACTS["CR-09"] == verifier.DECISION_CONTRACTS[
        "D-13"
    ]
    assert cr10[1] in verifier.REQUIREMENT_CONTRACTS["V9DATA-03"]
    assert cr10[2] in verifier.REQUIREMENT_CONTRACTS["V9DATA-02"]
    assert cr10[3] in verifier.REQUIREMENT_CONTRACTS["V9DATA-07"]
    assert set(cr10).isdisjoint(verifier.REQUIREMENT_CONTRACTS["V9DATA-05"])
    assert verifier.REVIEW_WARNING_CONTRACTS["WR-04"] == (
        "tests/test_phase475_question_effect_recovery.py::test_effect_proof_executes_repository_boundaries_instead_of_monkeypatching_them",
    )


def test_phase475_module_registry_rejects_missing_extra_or_duplicate_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _load_verifier()
    modules = verifier.PHASE475_MODULES
    monkeypatch.setattr(
        verifier, "_phase_runtime_files", lambda candidate: ["src/stoa/example.py"]
    )
    for drifted in (
        modules[:-1],
        (*modules, "tests/test_phase475_unreviewed.py"),
        (*modules, modules[-1]),
    ):
        monkeypatch.setattr(verifier, "PHASE475_MODULES", drifted)
        with pytest.raises(verifier.EvidenceError, match="module registry drift"):
            verifier.gate_registry(CANDIDATE, tmp_path)


def test_coverage_rejects_id_selector_result_and_observed_node_drift() -> None:
    verifier = _load_verifier()
    observed = _all_coverage_nodes(verifier)
    exact = verifier.derive_coverage(observed)

    mutations = []
    missing_id = deepcopy(exact)
    missing_id["review_findings"].pop()
    mutations.append(missing_id)
    extra_id = deepcopy(exact)
    extra_id["review_findings"].append(
        {"id": "CR-11", "result": "PASS", "selectors": []}
    )
    mutations.append(extra_id)
    duplicate_id = deepcopy(exact)
    duplicate_id["review_findings"][-1] = deepcopy(
        duplicate_id["review_findings"][0]
    )
    mutations.append(duplicate_id)
    selector_drift = deepcopy(exact)
    selector_drift["decisions"][0]["selectors"][0]["selector"] += "_drift"
    mutations.append(selector_drift)
    non_pass = deepcopy(exact)
    non_pass["requirements"][0]["result"] = "SKIPPED"
    mutations.append(non_pass)
    node_drift = deepcopy(exact)
    node_drift["review_warnings"][0]["selectors"][0]["observed_nodes"] = [
        "tests/test_unobserved.py::test_false_claim"
    ]
    mutations.append(node_drift)

    for coverage in mutations:
        with pytest.raises(verifier.EvidenceError, match="coverage|non-pass"):
            verifier.verify_coverage(coverage, observed)

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
    assert set(runtime) <= set(registry["MYPY-PHASE475"]["argv"])


def test_mypy_gate_fails_closed_for_every_nonzero_or_ambiguous_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _load_verifier()
    files = ["src/stoa/example.py", "src/stoa/other.py"]
    monkeypatch.setattr(verifier, "_phase_runtime_files", lambda candidate: files)

    class _Completed:
        def __init__(
            self, returncode: int, stdout: bytes = b"", stderr: bytes = b""
        ) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls: list[list[str]] = []

    def run_success(argv: list[str], **kwargs: object) -> _Completed:
        calls.append(list(argv))
        return _Completed(0, b"Success: no issues found in 2 source files\n")

    monkeypatch.setattr(verifier, "_run", run_success)
    result = verifier.targeted_mypy("b" * 40, "c" * 40, files)
    assert result == {
        "status": "PASS",
        "base_sha": "b" * 40,
        "candidate_sha": "c" * 40,
        "checked_files": files,
        "tool_exit_code": 0,
        "diagnostic_count": 0,
        "completion_source_count": 2,
        "raw_output_bytes": 43,
        "raw_output_sha256": sha256(
            b"Success: no issues found in 2 source files\n"
        ).hexdigest(),
        "mypy_argv_sha256": sha256(
            verifier._canonical_bytes([str(ROOT / ".venv/bin/mypy"), *files])
        ).hexdigest(),
    }
    assert calls == [[str(ROOT / ".venv/bin/mypy"), *files]]

    failures = (
        _Completed(1, b"src/stoa/example.py:10: error: ordinary diagnostic\n"),
        _Completed(1),
        _Completed(0),
        _Completed(0, b"Found 0 errors in 2 files\n"),
        _Completed(0, b"Success: no issues found in 1 source file\n"),
        _Completed(0, b"src/stoa/example.py:10: error: contradictory\n"),
        _Completed(0, b"\xffSuccess: no issues found in 2 source files\n"),
        _Completed(
            0,
            b"Success: no issues found in 2 source files\n",
            b"unexpected stderr\n",
        ),
    )
    for completed in failures:
        monkeypatch.setattr(verifier, "_run", lambda argv, **kwargs: completed)
        assert verifier.targeted_mypy("b" * 40, "c" * 40, files)["status"] == "FAIL"

    for error in (
        OSError("not executable"),
        subprocess.TimeoutExpired(["mypy"], timeout=1),
    ):
        def raise_execution_error(argv: list[str], **kwargs: object) -> _Completed:
            raise error

        monkeypatch.setattr(verifier, "_run", raise_execution_error)
        assert verifier.targeted_mypy("b" * 40, "c" * 40, files)["status"] == "FAIL"

    for drifted in (
        files[:-1],
        [*files, "src/stoa/extra.py"],
        [files[0], files[0], files[1]],
        list(reversed(files)),
    ):
        with pytest.raises(verifier.EvidenceError, match="registry drift"):
            verifier.targeted_mypy("b" * 40, "c" * 40, drifted)


def test_source_snapshot_is_exhaustive_for_all_git_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _load_verifier()
    base = "b" * 40
    candidate = "c" * 40
    name_status = (
        b"M\0modified.py\0"
        b"A\0added.py\0"
        b"D\0deleted.py\0"
        b"R100\0old-name.py\0renamed.py\0"
        b"C087\0copy-source.py\0copied.py\0"
    )
    blobs = {
        f"{candidate}:added.py": b"added bytes\n",
        f"{candidate}:modified.py": b"modified bytes\n",
        f"{base}:deleted.py": b"deleted bytes\n",
        f"{base}:old-name.py": b"renamed bytes\n",
        f"{candidate}:renamed.py": b"renamed bytes\n",
        f"{base}:copy-source.py": b"copy source bytes\n",
        f"{candidate}:copied.py": b"copy source bytes\n",
    }

    class _Completed:
        def __init__(self, returncode: int, stdout: bytes = b"") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = b""

    calls: list[tuple[str, ...]] = []

    def run(argv: tuple[str, ...], **kwargs: object) -> _Completed:
        call = tuple(argv)
        calls.append(call)
        if call[:3] == ("git", "diff", "--name-status"):
            return _Completed(0, name_status)
        if call[:2] == ("git", "ls-tree"):
            assert call[-1] in {
                ":(literal)deleted.py",
                ":(literal)old-name.py",
            }
            return _Completed(0)
        assert call[:2] == ("git", "show")
        spec = call[2]
        if spec in blobs:
            return _Completed(0, blobs[spec])
        raise AssertionError(f"unexpected Git read: {spec}")

    monkeypatch.setattr(verifier, "PHASE_BASE_SHA", base)
    monkeypatch.setattr(verifier, "_run", run)

    assert verifier._source_snapshot(candidate) == [
        {
            "status": "added",
            "path": "added.py",
            "candidate_blob": {
                "bytes": len(blobs[f"{candidate}:added.py"]),
                "sha256": sha256(blobs[f"{candidate}:added.py"]).hexdigest(),
            },
        },
        {
            "status": "copied",
            "similarity": 87,
            "source_path": "copy-source.py",
            "path": "copied.py",
            "base_blob": {
                "bytes": len(blobs[f"{base}:copy-source.py"]),
                "sha256": sha256(blobs[f"{base}:copy-source.py"]).hexdigest(),
            },
            "candidate_blob": {
                "bytes": len(blobs[f"{candidate}:copied.py"]),
                "sha256": sha256(blobs[f"{candidate}:copied.py"]).hexdigest(),
            },
        },
        {
            "status": "deleted",
            "path": "deleted.py",
            "candidate_absent": True,
            "base_blob": {
                "bytes": len(blobs[f"{base}:deleted.py"]),
                "sha256": sha256(blobs[f"{base}:deleted.py"]).hexdigest(),
            },
        },
        {
            "status": "modified",
            "path": "modified.py",
            "candidate_blob": {
                "bytes": len(blobs[f"{candidate}:modified.py"]),
                "sha256": sha256(blobs[f"{candidate}:modified.py"]).hexdigest(),
            },
        },
        {
            "status": "renamed",
            "similarity": 100,
            "source_path": "old-name.py",
            "path": "renamed.py",
            "source_candidate_absent": True,
            "base_blob": {
                "bytes": len(blobs[f"{base}:old-name.py"]),
                "sha256": sha256(blobs[f"{base}:old-name.py"]).hexdigest(),
            },
            "candidate_blob": {
                "bytes": len(blobs[f"{candidate}:renamed.py"]),
                "sha256": sha256(blobs[f"{candidate}:renamed.py"]).hexdigest(),
            },
        },
    ]
    assert calls[0] == (
        "git",
        "diff",
        "--name-status",
        "-z",
        "--find-renames",
        "--find-copies",
        base,
        candidate,
    )


@pytest.mark.parametrize(
    "name_status",
    [
        b"T\0typed.py\0",
        b"A\0",
        b"R100\0old.py\0",
        b"Rabc\0old.py\0new.py\0",
        b"A\0duplicate.py\0M\0duplicate.py\0",
        b"R100\0same.py\0same.py\0",
        b"M\0bad\xffpath.py\0",
    ],
)
def test_source_snapshot_rejects_malformed_unsupported_or_duplicate_inventory(
    monkeypatch: pytest.MonkeyPatch,
    name_status: bytes,
) -> None:
    verifier = _load_verifier()

    class _Completed:
        returncode = 0
        stdout = name_status
        stderr = b""

    monkeypatch.setattr(verifier, "_run", lambda argv, **kwargs: _Completed())
    with pytest.raises(verifier.EvidenceError, match="source snapshot"):
        verifier._source_snapshot("c" * 40)


@pytest.mark.parametrize(
    ("name_status", "responses"),
    [
        (b"A\0added.py\0", {}),
        (b"M\0modified.py\0", {}),
        (b"D\0deleted.py\0", {"candidate:deleted.py": b"still present"}),
        (b"D\0deleted.py\0", {}),
        (b"R100\0old.py\0new.py\0", {"candidate:old.py": b"still present"}),
        (b"R100\0old.py\0new.py\0", {}),
        (b"C100\0old.py\0new.py\0", {}),
    ],
)
def test_source_snapshot_fails_closed_on_required_blob_or_absence_drift(
    monkeypatch: pytest.MonkeyPatch,
    name_status: bytes,
    responses: dict[str, bytes],
) -> None:
    verifier = _load_verifier()
    base = "b" * 40
    candidate = "c" * 40

    class _Completed:
        def __init__(self, returncode: int, stdout: bytes = b"") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = b""

    def run(argv: tuple[str, ...], **kwargs: object) -> _Completed:
        call = tuple(argv)
        if call[:3] == ("git", "diff", "--name-status"):
            return _Completed(0, name_status)
        if call[:2] == ("git", "ls-tree"):
            path = call[-1].removeprefix(":(literal)")
            spec = f"candidate:{path}"
            value = responses.get(spec)
            return (
                _Completed(0)
                if value is None
                else _Completed(0, path.encode("utf-8") + b"\0")
            )
        spec = call[2].replace(base, "base").replace(candidate, "candidate")
        value = responses.get(spec)
        return _Completed(128) if value is None else _Completed(0, value)

    monkeypatch.setattr(verifier, "PHASE_BASE_SHA", base)
    monkeypatch.setattr(verifier, "_run", run)
    with pytest.raises(verifier.EvidenceError, match="source snapshot"):
        verifier._source_snapshot(candidate)


def test_source_snapshot_fails_when_absence_probe_git_command_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _load_verifier()

    class _Completed:
        def __init__(self, returncode: int, stdout: bytes = b"") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = b""

    def run(argv: tuple[str, ...], **kwargs: object) -> _Completed:
        if tuple(argv)[:3] == ("git", "diff", "--name-status"):
            return _Completed(0, b"D\0deleted.py\0")
        return _Completed(128)

    monkeypatch.setattr(verifier, "_run", run)
    with pytest.raises(verifier.EvidenceError, match="absence check failed"):
        verifier._source_snapshot("c" * 40)


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [
            {"status": "added", "path": "added.py"},
            {"status": "modified", "path": "extra.py"},
        ],
        [
            {"status": "added", "path": "added.py"},
            {"status": "added", "path": "added.py"},
        ],
    ],
)
def test_source_snapshot_rejects_missing_extra_or_duplicate_rows(rows: list[dict[str, object]]) -> None:
    verifier = _load_verifier()
    inventory = [{"status": "A", "path": "added.py"}]
    with pytest.raises(verifier.EvidenceError, match="source snapshot"):
        verifier._validate_source_snapshot(inventory, rows)


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
                    "gate_id": "MYPY-PHASE475",
                    "kind": "mypy",
                    "counts": {},
                    "exit_code": 0,
                    "privacy": {"match_count": 0},
                    "analysis": {
                        "tool_exit_code": 0,
                        "diagnostic_count": 0,
                        "completion_source_count": 1,
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
