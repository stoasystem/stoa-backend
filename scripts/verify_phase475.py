#!/usr/bin/env python3
"""Capture and independently verify source-bound Phase 475 evidence."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "docs/security/phase-475-evidence-results.json"
EVIDENCE_PATH = ROOT / "docs/security/phase-475-evidence.md"
DENYLIST_PATH = ROOT / "tests/fixtures/phase473_evidence_denylist.txt"
PHASE_BASE_SHA = "901cb26626cb0f06b7f51a72b95e04aa4f7f4ebf"
RESULT_SCHEMA = "stoa.phase475.evidence-results.v1"
CAPTURE_SCHEMA = "stoa.phase475.evidence-capture.v1"
NODE_SCHEMA = "stoa.phase475.pytest-nodes.v1"
UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NON_PASS = ("failed", "error", "skipped", "xfail", "xpass")
PUBLICATION_PATHS = {
    "docs/security/phase-475-evidence-results.json",
    "docs/security/phase-475-evidence.md",
}
PHASE475_MODULES = (
    "tests/test_phase475_question_admission.py",
    "tests/test_phase475_question_replay.py",
    "tests/test_phase475_question_reconciliation.py",
    "tests/test_phase475_teacher_takeover.py",
    "tests/test_phase475_teacher_takeover_effect.py",
    "tests/test_phase475_parent_binding_transaction.py",
    "tests/test_phase475_parent_binding_reconciliation.py",
    "tests/test_phase475_profile_version_cas.py",
    "tests/test_phase475_rate_limit.py",
    "tests/test_phase475_mistake_answer.py",
    "tests/test_phase475_delivery_begin.py",
    "tests/test_phase475_completed_deletion_replay.py",
)
INHERITED_MODULES = (
    "tests/test_student_authorization_matrix.py",
    "tests/test_admin_authorization.py",
    "tests/test_practice_privacy.py",
    "tests/test_phase473_account_deletion.py",
    "tests/test_phase473_account_deletion_claim_fencing.py",
    "tests/test_phase473_account_deletion_seal.py",
    "tests/test_phase473_delivery_intent_recovery.py",
    "tests/test_phase473_notification_deletion.py",
    "tests/test_notifications.py",
)
EXTERNAL_OBLIGATIONS = (
    ("LIVE-AWS-DYNAMODB", "NOT RUN", "479"),
    ("LIVE-PROVIDER-EFFECTS", "NOT RUN", "480"),
    ("DEPLOYMENT-AND-PRODUCTION-SMOKE", "NOT RUN", "480"),
)
PHASE475_PRIVATE_VALUES = (
    "private-provider-canary",
    "CORRECT-ANSWER-CANARY",
    "raw-secret",
    "student-deleted-1",
    "student-delivery-begin",
    "https://identity.example/pool",
    "teacher-1",
    "teacher-2",
    "parent-1",
    "student-1",
)


@dataclass(frozen=True)
class GateSpec:
    gate_id: str
    kind: str
    modules: tuple[str, ...] = ()


class EvidenceError(ValueError):
    """Evidence is incomplete, ambiguous, stale, or privacy-unsafe."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"JSON object required: {path}")
    return value


def _run(
    argv: Sequence[str],
    *,
    root: Path = ROOT,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(argv),
        cwd=root,
        env=None if env is None else dict(env),
        capture_output=True,
        check=False,
    )


def _git(root: Path, *args: str) -> str:
    completed = _run(("git", *args), root=root)
    if completed.returncode:
        raise EvidenceError("git command failed")
    return completed.stdout.decode("utf-8").strip()


def _head(root: Path = ROOT) -> str:
    return _git(root, "rev-parse", "HEAD")


def _status_paths(root: Path = ROOT) -> set[str]:
    return {
        line[3:]
        for line in _git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
        if len(line) >= 4
    }


def _clean(root: Path = ROOT) -> bool:
    return not _status_paths(root)


def _capture_state(candidate: str) -> dict[str, object]:
    return {"head": _head(), "clean": _clean(), "candidate_match": _head() == candidate}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        raise EvidenceError("malformed UTC evidence")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _file_meta(path: Path, logical_path: str) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "logical_path": logical_path,
        "bytes": len(data),
        "sha256": sha256(data).hexdigest(),
    }


def _verify_file_meta(path: Path, meta: Mapping[str, object], logical_path: str) -> None:
    expected = _file_meta(path, logical_path)
    if dict(meta) != expected or expected["bytes"] == 0:
        raise EvidenceError(f"artifact metadata drift: {logical_path}")


def _denylist() -> tuple[str, ...]:
    inherited = tuple(
        line.strip()
        for line in DENYLIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    return inherited + PHASE475_PRIVATE_VALUES


def _privacy_matches(payloads: Iterable[bytes]) -> int:
    needles = tuple(value.casefold() for value in _denylist())
    return sum(
        data.decode("utf-8", errors="replace").casefold().count(needle)
        for data in payloads
        for needle in needles
    )


def _privacy_contract(payloads: Iterable[bytes]) -> dict[str, object]:
    values = _denylist()
    return {
        "denylist_sha256": sha256("\n".join(values).encode("utf-8")).hexdigest(),
        "entry_count": len(values),
        "match_count": _privacy_matches(payloads),
    }


def _safe_param_identity(value: object) -> str:
    if callable(value):
        code = getattr(value, "__code__", None)
        raw = (
            f"callable:{getattr(value, '__module__', '')}:"
            f"{getattr(value, '__qualname__', type(value).__qualname__)}:"
            f"{getattr(code, 'co_firstlineno', 0)}"
        )
    else:
        try:
            raw = json.dumps(
                value,
                sort_keys=True,
                ensure_ascii=True,
                default=lambda item: type(item).__qualname__,
            )
        except (TypeError, ValueError):
            raw = type(value).__qualname__
    return "case-" + sha256(raw.encode("utf-8")).hexdigest()[:16]


def pytest_make_parametrize_id(config: Any, val: object, argname: str) -> str | None:
    """Keep evidence node IDs exact but opaque for private parametrized values."""
    if os.environ.get("STOA_PHASE475_NODE_MANIFEST"):
        raw = f"{argname}:{_safe_param_identity(val)}"
        return "case-" + sha256(raw.encode("utf-8")).hexdigest()[:16]
    return None


class _StrictNodePlugin:
    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.node_ids: list[str] = []
        self.reports: dict[str, list[dict[str, object]]] = {}

    def pytest_collection_modifyitems(self, items: Sequence[Any]) -> None:
        self.node_ids = sorted(item.nodeid for item in items)

    def pytest_runtest_logreport(self, report: Any) -> None:
        self.reports.setdefault(report.nodeid, []).append(
            {
                "when": report.when,
                "outcome": report.outcome,
                "wasxfail": getattr(report, "wasxfail", None) is not None,
                "xpass_strict": bool(report.failed and "XPASS(strict)" in str(report.longrepr)),
            }
        )

    def pytest_sessionfinish(self, session: Any) -> None:
        nodes: list[dict[str, object]] = []
        order = {"setup": 0, "call": 1, "teardown": 2}
        for node_id in self.node_ids:
            phases = sorted(self.reports.get(node_id, []), key=lambda row: order[str(row["when"])])
            if any(row["xpass_strict"] for row in phases):
                outcome = "xpass"
            elif any(row["wasxfail"] and row["outcome"] == "passed" for row in phases):
                outcome = "xpass"
            elif any(row["wasxfail"] and row["outcome"] == "skipped" for row in phases):
                outcome = "xfail"
            elif any(row["when"] in {"setup", "teardown"} and row["outcome"] == "failed" for row in phases):
                outcome = "error"
            elif any(row["when"] == "call" and row["outcome"] == "failed" for row in phases):
                outcome = "failed"
            elif any(row["outcome"] == "skipped" for row in phases):
                outcome = "skipped"
            elif phases and all(row["outcome"] == "passed" for row in phases):
                outcome = "passed"
            else:
                outcome = "error"
            nodes.append({"node_id": node_id, "outcome": outcome})
        counts = {"total": len(nodes), "passed": 0, **{name: 0 for name in NON_PASS}}
        for node in nodes:
            counts[str(node["outcome"])] += 1
        payload = {
            "schema_version": NODE_SCHEMA,
            "nodes": nodes,
            "counts": counts,
            "collection_sha256": sha256(
                "".join(f"{row['node_id']}\n" for row in nodes).encode("utf-8")
            ).hexdigest(),
        }
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        self.destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if any(counts[name] for name in NON_PASS):
            session.exitstatus = 1


def pytest_configure(config: Any) -> None:
    destination = os.environ.get("STOA_PHASE475_NODE_MANIFEST")
    if destination:
        config.pluginmanager.register(
            _StrictNodePlugin(Path(destination)), "stoa-phase475-strict-node-accounting"
        )


def _pytest_argv(spec: GateSpec, capture_root: Path) -> list[str]:
    argv = [
        str(ROOT / ".venv/bin/python"),
        "-m",
        "pytest",
        "-q",
        "-p",
        "scripts.verify_phase475",
        "-o",
        "xfail_strict=true",
        "--junitxml",
        str(capture_root / "junit" / f"{spec.gate_id}.xml"),
    ]
    if spec.gate_id == "P475-PHASE474-FORMAL-EXTENSION":
        # release_gate.PYTHON_SUITE_ARGV is fixed to this exact prefix.
        argv[0:0] = []
        argv = [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:socket",
            "-p",
            "scripts.verify_phase475",
            "-o",
            "xfail_strict=true",
            "--junitxml",
            str(capture_root / "junit" / f"{spec.gate_id}.xml"),
        ]
    return [*argv, *spec.modules]


def gate_registry(candidate: str, capture_root: Path) -> list[dict[str, object]]:
    specs = (
        GateSpec("P475-QUESTION", "pytest", PHASE475_MODULES[:3]),
        GateSpec("P475-TAKEOVER", "pytest", PHASE475_MODULES[3:5]),
        GateSpec("P475-RELATIONSHIP", "pytest", PHASE475_MODULES[5:8]),
        GateSpec("P475-RATE", "pytest", (PHASE475_MODULES[8],)),
        GateSpec("P475-MISTAKE", "pytest", (PHASE475_MODULES[9],)),
        GateSpec(
            "P475-DELIVERY",
            "pytest",
            (PHASE475_MODULES[10], "tests/test_phase473_delivery_intent_recovery.py", "tests/test_phase473_notification_deletion.py"),
        ),
        GateSpec(
            "P475-DELETION",
            "pytest",
            (PHASE475_MODULES[11], "tests/test_phase473_account_deletion.py", "tests/test_phase473_account_deletion_seal.py"),
        ),
        GateSpec("P475-INHERITED-AUTH-PRIVACY", "pytest", INHERITED_MODULES),
        GateSpec("P475-PHASE474-FORMAL-EXTENSION", "pytest", ()),
        GateSpec("RUFF-PHASE475", "ruff"),
        GateSpec("MYPY-PHASE475-CHANGED-LINES", "mypy"),
    )
    runtime_files = _phase_runtime_files(candidate)
    registry: list[dict[str, object]] = []
    for spec in specs:
        if spec.kind == "pytest":
            argv = _pytest_argv(spec, capture_root)
        elif spec.kind == "ruff":
            argv = [
                str(ROOT / ".venv/bin/ruff"),
                "check",
                *runtime_files,
                "scripts/verify_phase475.py",
                "tests/test_phase475_evidence_verifier.py",
            ]
        else:
            argv = [
                str(ROOT / ".venv/bin/python"),
                "scripts/verify_phase475.py",
                "_targeted-mypy",
                "--base",
                PHASE_BASE_SHA,
                "--candidate",
                candidate,
                *runtime_files,
            ]
        registry.append({"id": spec.gate_id, "kind": spec.kind, "argv": argv})
    return registry


def _phase_runtime_files(candidate: str) -> list[str]:
    changed = _git(
        ROOT, "diff", "--name-only", PHASE_BASE_SHA, candidate, "--", "src/stoa"
    ).splitlines()
    files = sorted(path for path in changed if path.endswith(".py"))
    if not files:
        raise EvidenceError("Phase 475 runtime file inventory is empty")
    return files


def _changed_lines(base: str, candidate: str, path: str) -> set[int]:
    diff = _git(ROOT, "diff", "--unified=0", base, candidate, "--", path)
    lines: set[int] = set()
    for match in re.finditer(r"^@@ -[^ ]+ \+(\d+)(?:,(\d+))? @@", diff, re.MULTILINE):
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        lines.update(range(start, start + count))
    return lines


def targeted_mypy(base: str, candidate: str, files: Sequence[str]) -> dict[str, object]:
    expected_files = _phase_runtime_files(candidate)
    if sorted(files) != expected_files:
        raise EvidenceError("targeted mypy file registry drift")
    argv = [str(ROOT / ".venv/bin/mypy"), *files]
    completed = _run(argv)
    text = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
    diagnostics: list[tuple[str, int]] = []
    for line in text.splitlines():
        match = re.match(r"([^:]+):(\d+): error:", line)
        if match:
            diagnostics.append((match.group(1), int(match.group(2))))
    changed = {path: _changed_lines(base, candidate, path) for path in files}
    new_diagnostics = [
        (path, line) for path, line in diagnostics if line in changed.get(path, set())
    ]
    result: dict[str, object] = {
        "status": "PASS" if not new_diagnostics else "FAIL",
        "base_sha": base,
        "candidate_sha": candidate,
        "checked_files": list(files),
        "tool_exit_code": completed.returncode,
        "diagnostic_count": len(diagnostics),
        "pre_existing_diagnostic_count": len(diagnostics) - len(new_diagnostics),
        "changed_line_diagnostic_count": len(new_diagnostics),
        "mypy_argv_sha256": sha256(_canonical_bytes(argv)).hexdigest(),
    }
    if new_diagnostics:
        result["changed_line_locations"] = [f"{path}:{line}" for path, line in new_diagnostics]
    return result


def _junit_counts(path: Path) -> dict[str, int]:
    try:
        root = ET.fromstring(path.read_bytes())
    except (OSError, ET.ParseError) as exc:
        raise EvidenceError("invalid JUnit artifact") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        "total": sum(int(row.attrib.get("tests", "0")) for row in suites),
        "failed": sum(int(row.attrib.get("failures", "0")) for row in suites),
        "error": sum(int(row.attrib.get("errors", "0")) for row in suites),
        "skipped": sum(int(row.attrib.get("skipped", "0")) for row in suites),
    }


def _capture_gate(
    gate: Mapping[str, Any], candidate: str, capture_root: Path
) -> dict[str, object]:
    if _head() != candidate or not _clean():
        raise EvidenceError(f"candidate changed before {gate['id']}")
    gate_id = str(gate["id"])
    kind = str(gate["kind"])
    argv = [str(item) for item in gate["argv"]]
    raw_path = capture_root / "raw" / f"{gate_id}.log"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    node_path = capture_root / "nodes" / f"{gate_id}.json"
    phase474_path = capture_root / "phase474" / f"{gate_id}.json"
    if kind == "pytest":
        environment["STOA_PHASE475_NODE_MANIFEST"] = str(node_path)
    if gate_id == "P475-PHASE474-FORMAL-EXTENSION":
        credential_root = capture_root / "no-credentials"
        environment.update(
            {
                "STOA_PHASE474_HERMETIC": "1",
                "STOA_PHASE474_CLOCK": "2026-07-01T12:00:00Z",
                "STOA_PHASE474_SEED": "4740718",
                "STOA_PHASE474_LOCK": str(ROOT / "uv.lock"),
                "STOA_PHASE474_MANIFEST": str(phase474_path),
                "STOA_PHASE474_CREDENTIAL_ROOT": str(credential_root),
                "AWS_EC2_METADATA_DISABLED": "true",
                "AWS_SHARED_CREDENTIALS_FILE": str(credential_root / "credentials"),
                "AWS_CONFIG_FILE": str(credential_root / "config"),
            }
        )
        for name in tuple(environment):
            if name.startswith("AWS_") and name not in {
                "AWS_EC2_METADATA_DISABLED",
                "AWS_SHARED_CREDENTIALS_FILE",
                "AWS_CONFIG_FILE",
            }:
                environment.pop(name)
    started_at = _utc_now()
    completed = _run(argv, env=environment)
    ended_at = _utc_now()
    raw_path.write_bytes(completed.stdout + completed.stderr)
    if completed.returncode:
        raise EvidenceError(f"gate failed: {gate_id}")
    if _head() != candidate or not _clean():
        raise EvidenceError(f"candidate changed after {gate_id}")
    artifacts = {"log": _file_meta(raw_path, f"raw/{gate_id}.log")}
    receipt: dict[str, object] = {
        "gate_id": gate_id,
        "kind": kind,
        "argv": argv,
        "started_at": started_at,
        "ended_at": ended_at,
        "exit_code": completed.returncode,
        "candidate_sha": candidate,
        "before": {"head": candidate, "clean": True},
        "after": {"head": candidate, "clean": True},
        "artifacts": artifacts,
    }
    payloads = [raw_path.read_bytes()]
    if kind == "pytest":
        junit_path = capture_root / "junit" / f"{gate_id}.xml"
        node = _read_json(node_path)
        artifacts["junit"] = _file_meta(junit_path, f"junit/{gate_id}.xml")
        artifacts["node_manifest"] = _file_meta(node_path, f"nodes/{gate_id}.json")
        payloads.extend((junit_path.read_bytes(), node_path.read_bytes()))
        receipt["counts"] = node["counts"]
        receipt["nodes"] = node["nodes"]
        if gate_id == "P475-PHASE474-FORMAL-EXTENSION":
            formal = _read_json(phase474_path)
            artifacts["phase474_manifest"] = _file_meta(
                phase474_path, f"phase474/{gate_id}.json"
            )
            payloads.append(phase474_path.read_bytes())
            if formal.get("counts") != node.get("counts"):
                raise EvidenceError("Phase 474 and Phase 475 strict accounting disagree")
            receipt["phase474_formal_extension"] = {
                "schema_version": formal.get("schema_version"),
                "clock": formal.get("clock"),
                "seed": formal.get("seed"),
                "runtime": formal.get("runtime"),
                "lock_sha256": formal.get("lock_sha256"),
                "collection_sha256": formal.get("collection_sha256"),
            }
    elif kind == "mypy":
        analysis = json.loads(raw_path.read_text(encoding="utf-8"))
        if analysis.get("status") != "PASS":
            raise EvidenceError("targeted mypy found a Phase 475 diagnostic")
        receipt["analysis"] = analysis
    privacy = _privacy_contract(payloads)
    receipt["privacy"] = privacy
    if privacy["match_count"]:
        raise EvidenceError(f"privacy match in {gate_id}")
    verify_receipt(receipt, gate, candidate, capture_root)
    return receipt


def verify_receipt(
    receipt: Mapping[str, object],
    gate: Mapping[str, Any],
    candidate: str,
    capture_root: Path,
) -> set[str]:
    if receipt.get("gate_id") != gate.get("id") or receipt.get("kind") != gate.get("kind"):
        raise EvidenceError("gate identity drift")
    if receipt.get("argv") != gate.get("argv") or receipt.get("exit_code") != 0:
        raise EvidenceError("gate argv or exit drift")
    if receipt.get("candidate_sha") != candidate:
        raise EvidenceError("candidate drift")
    for boundary in ("before", "after"):
        if receipt.get(boundary) != {"head": candidate, "clean": True}:
            raise EvidenceError("candidate cleanliness drift")
    if _parse_utc(receipt.get("ended_at")) < _parse_utc(receipt.get("started_at")):
        raise EvidenceError("gate UTC ordering drift")
    gate_id = str(gate["id"])
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict):
        raise EvidenceError("gate artifact registry missing")
    paths = [capture_root / "raw" / f"{gate_id}.log"]
    _verify_file_meta(paths[0], artifacts["log"], f"raw/{gate_id}.log")
    observed: set[str] = set()
    if gate.get("kind") == "pytest":
        junit_path = capture_root / "junit" / f"{gate_id}.xml"
        node_path = capture_root / "nodes" / f"{gate_id}.json"
        _verify_file_meta(junit_path, artifacts["junit"], f"junit/{gate_id}.xml")
        _verify_file_meta(node_path, artifacts["node_manifest"], f"nodes/{gate_id}.json")
        node = _read_json(node_path)
        counts = node.get("counts")
        nodes = node.get("nodes")
        if node.get("schema_version") != NODE_SCHEMA or not isinstance(counts, dict) or not isinstance(nodes, list):
            raise EvidenceError("node manifest is malformed")
        if counts != receipt.get("counts") or nodes != receipt.get("nodes"):
            raise EvidenceError("node manifest receipt drift")
        if counts.get("total") != counts.get("passed") or any(counts.get(name) for name in NON_PASS):
            raise EvidenceError("strict pytest outcome is not complete pass")
        junit = _junit_counts(junit_path)
        if junit != {
            "total": counts["total"],
            "failed": counts["failed"],
            "error": counts["error"],
            "skipped": counts["skipped"],
        }:
            raise EvidenceError("JUnit count drift")
        observed = {str(row.get("node_id")) for row in nodes if row.get("outcome") == "passed"}
        if len(observed) != counts["total"]:
            raise EvidenceError("duplicate or nonpassing node evidence")
        paths.extend((junit_path, node_path))
        if gate_id == "P475-PHASE474-FORMAL-EXTENSION":
            phase474_path = capture_root / "phase474" / f"{gate_id}.json"
            _verify_file_meta(
                phase474_path,
                artifacts["phase474_manifest"],
                f"phase474/{gate_id}.json",
            )
            paths.append(phase474_path)
    privacy = _privacy_contract(path.read_bytes() for path in paths)
    if receipt.get("privacy") != privacy or privacy["match_count"]:
        raise EvidenceError("privacy receipt drift")
    return observed


def _selector_nodes(selector: str, observed: set[str]) -> list[str]:
    matches = sorted(node for node in observed if node == selector or node.startswith(selector + "["))
    if not matches:
        raise EvidenceError(f"required selector not observed: {selector}")
    return matches


REQUIREMENT_CONTRACTS: dict[str, tuple[str, ...]] = {
    "V9DATA-01": (
        "tests/test_phase475_question_admission.py::test_concurrent_identical_keys_commit_one_complete_admission",
        "tests/test_phase475_question_admission.py::test_commit_then_timeout_reconciles_to_resume",
        "tests/test_phase475_question_reconciliation.py::test_each_terminal_transaction_boundary_fails_without_partial_compensation",
        "tests/test_phase475_question_reconciliation.py::test_terminal_reversal_is_exact_once_and_attachment_storage_are_unchanged",
    ),
    "V9DATA-02": (
        "tests/test_phase475_teacher_takeover.py::test_two_barrier_claimants_produce_one_owner_session_and_private_loser",
        "tests/test_phase475_teacher_takeover_effect.py::test_begin_dependency_failure_then_retry_creates_one_notification",
        "tests/test_phase475_teacher_takeover_effect.py::test_losing_claim_never_reaches_notification_effect",
    ),
    "V9DATA-03": (
        "tests/test_phase475_parent_binding_transaction.py::test_failure_at_every_operation_leaves_all_relationship_projections_unchanged",
        "tests/test_phase475_parent_binding_reconciliation.py::test_changed_after_preview_is_skipped_and_new_data_is_preserved",
        "tests/test_phase475_parent_binding_reconciliation.py::test_one_sided_apply_is_atomic_and_replay_is_zero_write",
    ),
    "V9DATA-04": (
        "tests/test_phase475_rate_limit.py::test_repeating_429_requests_leave_counter_exactly_at_limit",
        "tests/test_phase475_rate_limit.py::test_two_concurrent_distinct_requests_compete_for_one_final_slot",
        "tests/test_phase475_rate_limit.py::test_provider_failure_retry_replays_one_count_and_distinct_operation_is_evaluated",
    ),
    "V9DATA-05": (
        "tests/test_phase475_mistake_answer.py::test_wrong_answer_round_trips_exactly_after_normalization",
        "tests/test_phase475_mistake_answer.py::test_legacy_missing_answer_is_explicit_unknown_and_never_uses_standard_answer",
        "tests/test_phase475_mistake_answer.py::test_route_rejects_unsupported_answer_before_attempt_write_and_redacts_value",
    ),
    "V9DATA-06": (
        "tests/test_phase475_profile_version_cas.py::test_real_locale_writer_races_real_scrub_and_preserves_exact_latest_bytes",
        "tests/test_phase475_profile_version_cas.py::test_same_sensitive_field_race_always_leaves_scrubbed_linkage_absent",
        "tests/test_phase475_profile_version_cas.py::test_profile_writer_registry_is_closed_against_direct_source_mutations",
    ),
    "V9DATA-07": (
        "tests/test_phase475_delivery_begin.py::test_dependency_failure_remains_recoverable_then_healthy_retry_delivers_once",
        "tests/test_phase475_delivery_begin.py::test_ordered_fence_failure_plus_strong_deleted_fence_cancels_without_provider",
        "tests/test_phase475_delivery_begin.py::test_ordered_intent_condition_loss_is_retryable_and_never_mislabeled",
    ),
    "V9DATA-08": (
        "tests/test_phase475_completed_deletion_replay.py::test_real_endpoint_replays_stored_terminal_receipt_with_zero_new_effects",
        "tests/test_phase475_completed_deletion_replay.py::test_terminal_replay_preserves_fingerprint_and_verified_identity_conflicts",
    ),
}

DECISION_CONTRACTS: dict[str, tuple[str, ...]] = {
    "D-01": ("tests/test_phase475_question_replay.py::test_ai_failure_returns_queryable_durable_pending_question",),
    "D-02": ("tests/test_phase475_question_replay.py::test_lost_response_retry_returns_original_without_repeating_effects",),
    "D-03": ("tests/test_phase475_question_reconciliation.py::test_terminal_reversal_is_exact_once_and_attachment_storage_are_unchanged",),
    "D-04": ("tests/test_phase475_question_replay.py::test_changed_payload_returns_structured_new_submission_action",),
    "D-05": ("tests/test_phase475_teacher_takeover.py::test_two_barrier_claimants_produce_one_owner_session_and_private_loser",),
    "D-06": ("tests/test_phase475_teacher_takeover_effect.py::test_losing_claim_never_reaches_notification_effect",),
    "D-07": ("tests/test_phase475_teacher_takeover_effect.py::test_route_keeps_winner_session_when_effect_fails_then_replays",),
    "D-08": ("tests/test_phase475_teacher_takeover.py::test_two_barrier_claimants_produce_one_owner_session_and_private_loser",),
    "D-09": ("tests/test_phase475_parent_binding_transaction.py::test_conflicting_parent_is_preserved_and_authorization_remains_denied",),
    "D-10": ("tests/test_phase475_parent_binding_reconciliation.py::test_different_parent_conflict_is_report_only_and_remains_unauthorized",),
    "D-11": ("tests/test_phase475_parent_binding_reconciliation.py::test_changed_after_preview_is_skipped_and_new_data_is_preserved",),
    "D-12": ("tests/test_phase475_profile_version_cas.py::test_real_locale_writer_races_real_scrub_and_preserves_exact_latest_bytes",),
    "D-13": ("tests/test_phase475_rate_limit.py::test_provider_failure_retry_replays_one_count_and_distinct_operation_is_evaluated",),
    "D-14": ("tests/test_phase475_mistake_answer.py::test_legacy_missing_answer_is_explicit_unknown_and_never_uses_standard_answer",),
    "D-15": ("tests/test_phase475_delivery_begin.py::test_dependency_failure_remains_recoverable_then_healthy_retry_delivers_once",),
    "D-16": ("tests/test_phase475_completed_deletion_replay.py::test_real_endpoint_replays_stored_terminal_receipt_with_zero_new_effects",),
}

FINDING_CONTRACTS: dict[str, tuple[str, ...]] = {
    "DATA-001": REQUIREMENT_CONTRACTS["V9DATA-01"],
    "BUG-002": REQUIREMENT_CONTRACTS["V9DATA-02"],
    "DATA-003": REQUIREMENT_CONTRACTS["V9DATA-03"],
    "BUG-006": REQUIREMENT_CONTRACTS["V9DATA-04"],
    "BUG-004": REQUIREMENT_CONTRACTS["V9DATA-05"],
}

FOLLOW_UP_CONTRACTS: dict[str, tuple[str, ...]] = {
    "profile-version-cas": REQUIREMENT_CONTRACTS["V9DATA-06"],
    "delivery-begin-dependency-classification": REQUIREMENT_CONTRACTS["V9DATA-07"],
    "completed-deletion-replay": REQUIREMENT_CONTRACTS["V9DATA-08"],
}


def derive_coverage(observed: set[str]) -> dict[str, list[dict[str, object]]]:
    def rows(contracts: Mapping[str, Sequence[str]]) -> list[dict[str, object]]:
        return [
            {
                "id": identifier,
                "result": "PASS",
                "selectors": [
                    {"selector": selector, "observed_nodes": _selector_nodes(selector, observed)}
                    for selector in selectors
                ],
            }
            for identifier, selectors in contracts.items()
        ]

    return {
        "requirements": rows(REQUIREMENT_CONTRACTS),
        "decisions": rows(DECISION_CONTRACTS),
        "audit_findings": rows(FINDING_CONTRACTS),
        "phase473_follow_ups": rows(FOLLOW_UP_CONTRACTS),
    }


def verify_coverage(coverage: Mapping[str, object], observed: set[str]) -> None:
    expected = {
        "requirements": REQUIREMENT_CONTRACTS,
        "decisions": DECISION_CONTRACTS,
        "audit_findings": FINDING_CONTRACTS,
        "phase473_follow_ups": FOLLOW_UP_CONTRACTS,
    }
    if set(coverage) != set(expected):
        raise EvidenceError("coverage sections are not closed")
    for section, contracts in expected.items():
        rows = coverage.get(section)
        if not isinstance(rows, list) or len(rows) != len(contracts):
            raise EvidenceError(f"coverage cardinality drift: {section}")
        if {row.get("id") for row in rows if isinstance(row, dict)} != set(contracts):
            raise EvidenceError(f"coverage IDs drift: {section}")
        for row in rows:
            if row.get("result") != "PASS":
                raise EvidenceError("coverage contains a non-pass result")
            identifier = str(row["id"])
            selector_rows = row.get("selectors")
            if not isinstance(selector_rows, list) or len(selector_rows) != len(contracts[identifier]):
                raise EvidenceError("coverage selector cardinality drift")
            if {item.get("selector") for item in selector_rows} != set(contracts[identifier]):
                raise EvidenceError("coverage selector registry drift")
            for item in selector_rows:
                nodes = item.get("observed_nodes")
                if not isinstance(nodes, list) or nodes != _selector_nodes(str(item["selector"]), observed):
                    raise EvidenceError("coverage observed-node drift")


def _source_snapshot(candidate: str) -> list[dict[str, object]]:
    paths = _git(ROOT, "diff", "--name-only", PHASE_BASE_SHA, candidate).splitlines()
    rows: list[dict[str, object]] = []
    for path in sorted(paths):
        completed = _run(("git", "show", f"{candidate}:{path}"))
        if completed.returncode:
            continue
        rows.append({"path": path, "bytes": len(completed.stdout), "sha256": sha256(completed.stdout).hexdigest()})
    return rows


def _verify_external(rows: object) -> None:
    expected = [
        {"id": identifier, "status": status, "owner_phase": owner}
        for identifier, status, owner in EXTERNAL_OBLIGATIONS
    ]
    if rows != expected:
        raise EvidenceError("external NOT RUN obligations drift")


def verify_capture(candidate: str, capture_root: Path) -> dict[str, Any]:
    capture = _read_json(capture_root / "capture.json")
    if capture.get("schema_version") != CAPTURE_SCHEMA or capture.get("candidate_sha") != candidate:
        raise EvidenceError("capture source identity drift")
    registry = gate_registry(candidate, capture_root)
    if capture.get("registry") != registry:
        raise EvidenceError("capture gate registry drift")
    receipts = capture.get("receipts")
    if not isinstance(receipts, list) or len(receipts) != len(registry):
        raise EvidenceError("capture receipt cardinality drift")
    observed: set[str] = set()
    for gate, receipt in zip(registry, receipts, strict=True):
        observed.update(verify_receipt(receipt, gate, candidate, capture_root))
    coverage = derive_coverage(observed)
    verify_coverage(coverage, observed)
    runtime_files = _phase_runtime_files(candidate)
    obligations = [
        {"id": identifier, "status": status, "owner_phase": owner}
        for identifier, status, owner in EXTERNAL_OBLIGATIONS
    ]
    _verify_external(obligations)
    full = next(row for row in receipts if row["gate_id"] == "P475-PHASE474-FORMAL-EXTENSION")
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA,
        "candidate_sha": candidate,
        "phase_base_sha": PHASE_BASE_SHA,
        "environment_classification": "local deterministic fakes plus Phase 474 strict full-backend extension",
        "gate_registry": registry,
        "receipts": receipts,
        "observed_full_suite_count": full["counts"]["total"],
        "coverage": coverage,
        "phase475_runtime_files": runtime_files,
        "source_snapshot": _source_snapshot(candidate),
        "external_obligations": obligations,
        "privacy": {
            "denylist_sha256": _privacy_contract([])["denylist_sha256"],
            "entry_count": len(_denylist()),
            "raw_match_count": sum(row["privacy"]["match_count"] for row in receipts),
            "published_match_count": 0,
        },
    }
    evidence = _render_evidence(result)
    if _privacy_matches((evidence.encode("utf-8"), _canonical_bytes(result))):
        raise EvidenceError("public evidence contains a forbidden value")
    result["evidence_markdown"] = {
        "path": EVIDENCE_PATH.relative_to(ROOT).as_posix(),
        "bytes": len(evidence.encode("utf-8")),
        "sha256": sha256(evidence.encode("utf-8")).hexdigest(),
    }
    return result


def _render_evidence(result: Mapping[str, Any]) -> str:
    lines = [
        "# Phase 475 checked transactional consistency evidence",
        "",
        f"Immutable source candidate: `{result['candidate_sha']}`. Phase base: `{result['phase_base_sha']}`.",
        "All passing behavioral observations are local deterministic tests/fakes. Live AWS, provider effects, deployment, and production smoke remain exact NOT RUN obligations.",
        "",
        "## Gate receipts",
        "",
        "| Gate | Kind | Nodes | Exit | Privacy | Result |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for receipt in result["receipts"]:
        nodes = receipt.get("counts", {}).get("total", "—")
        lines.append(
            f"| `{receipt['gate_id']}` | {receipt['kind']} | {nodes} | {receipt['exit_code']} | "
            f"{receipt['privacy']['match_count']} | PASS |"
        )
    lines.extend(
        [
            "",
            "The final backend aggregate uses the fixed Phase 474 full-suite argv prefix, strict Python 3.12 node accounting, fixed clock/seed, denied ambient AWS credentials, and socket denial. It extends the authoritative backend gate to this candidate; it does not relabel this local run as the historical two-environment Linux/cross-repository release receipt.",
            "",
            "## Closed coverage",
            "",
        ]
    )
    for title, section in (
        ("Requirements", "requirements"),
        ("Decisions", "decisions"),
        ("Audit findings", "audit_findings"),
        ("Phase 473 follow-ups", "phase473_follow_ups"),
    ):
        lines.extend((f"### {title}", "", "| ID | Exact observed nodes | Result |", "| --- | --- | --- |"))
        for row in result["coverage"][section]:
            nodes = "<br>".join(
                f"`{node}`" for selector in row["selectors"] for node in selector["observed_nodes"]
            )
            lines.append(f"| `{row['id']}` | {nodes} | PASS |")
        lines.append("")
    mypy = next(row for row in result["receipts"] if row["gate_id"] == "MYPY-PHASE475-CHANGED-LINES")["analysis"]
    lines.extend(
        [
            "## Static analysis truth",
            "",
            f"Ruff passed all {len(result['phase475_runtime_files'])} Phase 475 runtime files plus the verifier and its test. Mypy analyzed the same runtime inventory: {mypy['changed_line_diagnostic_count']} diagnostics touch Phase 475 changed lines; {mypy['pre_existing_diagnostic_count']} diagnostics remain on pre-candidate lines and are disclosed rather than suppressed or called zero.",
            "",
            "## External obligations",
            "",
            "| Obligation | Status | Owner phase |",
            "| --- | --- | --- |",
        ]
    )
    for row in result["external_obligations"]:
        lines.append(f"| `{row['id']}` | **{row['status']}** | {row['owner_phase']} |")
    lines.extend(
        [
            "",
            "## Privacy and source binding",
            "",
            f"Raw receipt match count: {result['privacy']['raw_match_count']}; published match count: {result['privacy']['published_match_count']}. Exact argv, UTC bounds, exit codes, safe opaque node manifests, artifact hashes, runtime-file inventory, and immutable Git-blob source snapshot are recorded in the checked JSON. No raw answer, teacher identity, storage coordinate, provider diagnostic, or identity hash is published.",
            "",
        ]
    )
    return "\n".join(lines)


def capture(candidate: str, capture_root: Path) -> dict[str, Any]:
    if GIT_SHA_RE.fullmatch(candidate) is None or _head() != candidate or not _clean():
        raise EvidenceError("capture requires the explicit clean candidate at HEAD")
    if _run(("git", "merge-base", "--is-ancestor", PHASE_BASE_SHA, candidate)).returncode:
        raise EvidenceError("Phase 475 base is not an ancestor")
    capture_root.mkdir(parents=True, exist_ok=True)
    registry = gate_registry(candidate, capture_root)
    receipts = [_capture_gate(gate, candidate, capture_root) for gate in registry]
    payload = {
        "schema_version": CAPTURE_SCHEMA,
        "candidate_sha": candidate,
        "phase_base_sha": PHASE_BASE_SHA,
        "registry": registry,
        "receipts": receipts,
    }
    _write_json(capture_root / "capture.json", payload)
    result = verify_capture(candidate, capture_root)
    evidence = _render_evidence(result)
    if result["evidence_markdown"] != {
        "path": EVIDENCE_PATH.relative_to(ROOT).as_posix(),
        "bytes": len(evidence.encode("utf-8")),
        "sha256": sha256(evidence.encode("utf-8")).hexdigest(),
    }:
        raise EvidenceError("rendered evidence hash drift")
    _write_json(RESULTS_PATH, result)
    EVIDENCE_PATH.write_text(evidence, encoding="utf-8")
    return result


def _exact_commit(root: Path, value: str, label: str) -> str:
    if GIT_SHA_RE.fullmatch(value) is None:
        raise EvidenceError(f"{label} is not an explicit full commit SHA")
    resolved = _git(root, "rev-parse", "--verify", f"{value}^{{commit}}")
    if resolved != value:
        raise EvidenceError(f"{label} commit drift")
    return resolved


def verify_publication(root: Path = ROOT) -> None:
    if not _clean(root):
        raise EvidenceError("publication verification requires a clean worktree")
    results = _read_json(root / RESULTS_PATH.relative_to(ROOT))
    candidate = _exact_commit(root, str(results.get("candidate_sha")), "candidate")
    paths = sorted(PUBLICATION_PATHS)
    commits = {
        _git(root, "log", "-1", "--format=%H", "--", path)
        for path in paths
    }
    if len(commits) != 1:
        raise EvidenceError("publication paths do not share one immutable commit; blob changed")
    publication = _exact_commit(root, commits.pop(), "publication")
    parents = _git(root, "rev-list", "--parents", "-n", "1", publication).split()
    if len(parents) != 2 or parents[1] != candidate:
        raise EvidenceError("publication must be the direct child of the candidate")
    if _run(("git", "merge-base", "--is-ancestor", publication, "HEAD"), root=root).returncode:
        raise EvidenceError("current HEAD does not descend from publication")
    changed = set(
        _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", publication).splitlines()
    )
    if changed != PUBLICATION_PATHS:
        raise EvidenceError("publication commit must change exactly two evidence paths")
    payloads: dict[str, bytes] = {}
    for path in paths:
        publication_oid = _git(root, "rev-parse", f"{publication}:{path}")
        head_oid = _git(root, "rev-parse", f"HEAD:{path}")
        if publication_oid != head_oid:
            raise EvidenceError("published evidence blob changed at later HEAD")
        payloads[path] = _run(("git", "cat-file", "blob", publication_oid), root=root).stdout
    results_path = next(path for path in paths if path.endswith(".json"))
    published_results = json.loads(payloads[results_path])
    if published_results != results or published_results.get("schema_version") != RESULT_SCHEMA:
        raise EvidenceError("published results drift")
    evidence_path = next(path for path in paths if path.endswith(".md"))
    meta = results.get("evidence_markdown")
    if not isinstance(meta, dict) or meta != {
        "path": evidence_path,
        "bytes": len(payloads[evidence_path]),
        "sha256": sha256(payloads[evidence_path]).hexdigest(),
    }:
        raise EvidenceError("published Markdown hash drift")
    narrative = payloads[evidence_path].decode("utf-8")
    if candidate not in narrative or _privacy_matches(payloads.values()):
        raise EvidenceError("publication source binding or privacy drift")
    _verify_external(results.get("external_obligations"))
    observed = {
        str(node["node_id"])
        for receipt in results.get("receipts", [])
        for node in receipt.get("nodes", [])
        if node.get("outcome") == "passed"
    }
    verify_coverage(results.get("coverage", {}), observed)


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("capture", "verify-capture"):
        child = subparsers.add_parser(command)
        child.add_argument("--candidate", required=True)
        child.add_argument("--capture-root", required=True, type=Path)
    subparsers.add_parser("verify-publication")
    mypy = subparsers.add_parser("_targeted-mypy")
    mypy.add_argument("--base", required=True)
    mypy.add_argument("--candidate", required=True)
    mypy.add_argument("files", nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            capture(args.candidate, args.capture_root)
        elif args.command == "verify-capture":
            verify_capture(args.candidate, args.capture_root)
        elif args.command == "verify-publication":
            verify_publication()
        else:
            result = targeted_mypy(args.base, args.candidate, args.files)
            sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
            return 0 if result["status"] == "PASS" else 1
    except (EvidenceError, OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"phase475 evidence verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
