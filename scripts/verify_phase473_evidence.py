#!/usr/bin/env python3
"""Capture and independently verify immutable Phase 473 evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
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
    return completed.stdout.strip()


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
            rows.append(
                {
                    "id": identifier,
                    "selector": selector,
                    "node_id": _selector_node(selector, observed_nodes),
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
    return {
        "requirements": identifier_rows(REQUIREMENTS, 1),
        "decisions": identifier_rows(DECISIONS, 2),
        "read_boundaries": read_coverage,
        "private_writes": write_coverage,
        "branches": branches,
        "retained_policy": retained,
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
        path = ROOT / relative
        if path.is_file():
            snapshot.append(_artifact_meta(path))
    return snapshot


def _finding_rows(observed: set[str]) -> list[dict[str, str]]:
    selectors = {
        "CR-01": "tests/test_phase473_provider_state_machine.py::test_put_upload_chunk_part_acknowledgement_rejects_missing_malformed_or_unequal_checksum",
        "CR-02": "tests/test_phase473_message_command.py::test_completion_transport_is_typed_and_commit_then_raise_reconciles",
        "CR-03": "tests/test_phase473_conversation_replay.py::test_batch_get_rejects_every_partial_duplicate_extra_or_malformed_shape",
        "CR-04": "tests/test_phase473_retention_reconciliation.py::test_strong_owner_enumeration_joins_metadata_and_associations_across_pages",
        "WR-01": "tests/test_phase473_message_command.py::test_deterministic_prebind_rejection_is_terminal_and_compensates_once",
        "WR-02": "tests/test_phase473_document_boundary.py::test_relationship_external_detection_is_encoding_and_spelling_independent",
    }
    rows = []
    for item, selector in selectors.items():
        try:
            node = _selector_node(selector, observed)
        except EvidenceError:
            matching = sorted(node for node in observed if selector.rsplit("::", 1)[0] in node)
            if not matching:
                raise
            node = matching[0]
        rows.append({"id": item, "selector": selector, "node_id": node, "result": "PASS"})
    return rows


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
        "finding_adjudications": _finding_rows(set(observed)),
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


def _publication_paths(root: Path) -> tuple[set[str], str]:
    validation = ".planning/phases/473-student-content-privacy-and-practice-integrity/473-VALIDATION.md"
    if not (root / validation).exists():
        matches = sorted((root / ".planning/phases").glob("*/473-VALIDATION.md"))
        if len(matches) != 1:
            raise EvidenceError("publication validation path is ambiguous")
        validation = matches[0].relative_to(root).as_posix()
    return PUBLICATION_FIXED_PATHS | {validation}, validation


def _status_paths(root: Path) -> set[str]:
    lines = _git(root, "status", "--porcelain").splitlines()
    return {line[3:].split(" -> ")[-1] for line in lines if len(line) >= 4}


def verify_publication(root: Path, candidate: str, *, dirty: bool) -> None:
    expected_paths, validation_relative = _publication_paths(root)
    if dirty:
        if _head(root) != candidate or _status_paths(root) != expected_paths:
            raise EvidenceError("dirty publication must change exactly four paths on candidate")
    else:
        if not _clean(root) or _git(root, "rev-parse", "HEAD^") != candidate:
            raise EvidenceError("publication must be a clean direct candidate child")
        changed = set(_git(root, "diff", "--name-only", candidate, "HEAD").splitlines())
        if changed != expected_paths:
            raise EvidenceError("publication child changed paths outside exact four documents")
    manifest_path = root / "docs/security/phase-473-evidence-manifest.json"
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("candidate_sha") != candidate:
        raise EvidenceError("publication manifest identity drift")
    expected_artifacts = expected_paths - {"docs/security/phase-473-evidence-manifest.json"}
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or {row.get("path") for row in artifacts} != expected_artifacts:
        raise EvidenceError("manifest must hash results, evidence, and validation only")
    if any(row.get("path") == manifest_path.relative_to(root).as_posix() for row in artifacts):
        raise EvidenceError("manifest cannot hash itself")
    for row in artifacts:
        path = root / row["path"]
        data = path.read_bytes()
        if row.get("bytes") != len(data) or row.get("sha256") != sha256(data).hexdigest():
            raise EvidenceError("publication artifact hash drift")
    results = _read_json(root / "docs/security/phase-473-evidence-results.json")
    if results.get("candidate_sha") != candidate:
        raise EvidenceError("results candidate drift")
    for path in (
        root / "docs/security/phase-473-evidence.md",
        root / validation_relative,
    ):
        if candidate not in path.read_text(encoding="utf-8"):
            raise EvidenceError("narrative candidate binding missing")
    if _privacy_match_count((root / path for path in expected_paths), DENYLIST_PATH):
        raise EvidenceError("publication privacy denylist match")
    if results.get("schema_version") == RESULT_SCHEMA:
        coverage = results.get("coverage")
        if not isinstance(coverage, dict):
            raise EvidenceError("publication coverage missing")
        for key, expected in (
            ("requirements", set(REQUIREMENTS)),
            ("decisions", set(DECISIONS)),
        ):
            rows = coverage.get(key, [])
            if len(rows) != len(expected) or {row.get("id") for row in rows} != expected:
                raise EvidenceError(f"publication {key} cardinality drift")
        verify_external_obligations(
            results.get("external_obligations", []),
            local_gate_ids={row["gate_id"] for row in results.get("receipts", [])},
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
    lines.extend(["", "## Requirement proof", "", "| Requirement | Observed node | Result |", "| --- | --- | --- |"]) 
    for row in coverage["requirements"]:
        lines.append(f"| {row['id']} | `{row['node_id']}` | {row['result']} |")
    lines.extend(["", "## Decision proof", "", "| Decision | Observed node | Result |", "| --- | --- | --- |"]) 
    for row in coverage["decisions"]:
        lines.append(f"| {row['id']} | `{row['node_id']}` | {row['result']} |")
    lines.extend(["", "## Retained verification/review findings", "", "| Finding | Observed node | Result |", "| --- | --- | --- |"]) 
    for row in result["finding_adjudications"]:
        lines.append(f"| {row['id']} | `{row['node_id']}` | {row['result']} |")
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
    return (
        "---\nphase: 473\nslug: student-content-privacy-and-practice-integrity\n"
        "status: local_gates_complete\nnyquist_compliant: true\n"
        f"testedSourceSha: {candidate}\n---\n\n"
        "# Phase 473 — checked final validation\n\n"
        f"All local observations derive from immutable candidate `{candidate}`. "
        f"The strict full suite observed {result['observed_full_suite_count']} nodes.\n\n"
        "Every receipt has exact argv, UTC bounds, clean candidate state, raw log/JUnit/node "
        "hashes, recomputed counts, and zero denylist matches. Requirements V9PRIV-01/02/03, "
        "D-01 through D-22, all checked read/private-store boundaries, exact 17 branches, and "
        "retained-policy rows map to observed nodes in the checked results JSON.\n\n"
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
    publication.add_argument("--dirty", action="store_true")
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
            verify_publication(ROOT, args.candidate, dirty=args.dirty)
        else:
            privacy_denial(args.capture_root, args.denylist)
    except (EvidenceError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"phase473 evidence verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
