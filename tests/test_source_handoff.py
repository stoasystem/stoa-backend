"""Closed contracts for the owner-approved Phase 474 source handoff."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
HANDOFF_MODULE_PATH = ROOT / "scripts" / "source_handoff.py"
GATE_MODULE_PATH = ROOT / "scripts" / "release_gate.py"


def _load_module(name: str, path: Path) -> Any:
    assert path.is_file(), f"missing contract implementation: {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *argv: str) -> str:
    completed = subprocess.run(
        ["git", *argv],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.rstrip("\n")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _init_repository(root: Path, name: str, lock_path: str) -> str:
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "source-handoff@example.invalid")
    _git(root, "config", "user.name", "Source Handoff Test")
    if name == "frontend":
        _write(root / "package.json", json.dumps({"name": "stoa-frontend"}) + "\n")
    else:
        _write(root / "pyproject.toml", f'[project]\nname = "stoa-{name}"\n')
    _write(root / lock_path, f"{name}-locked\n")
    if name == "backend":
        _write(root / ".planning/ROADMAP.md", "roadmap base\n")
        _write(root / ".planning/STATE.md", "state base\n")
        _write(root / "scripts/release_gate.py", "# gate\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", f"seed {name}")
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture()
def source_fixture(tmp_path: Path) -> dict[str, Any]:
    handoff = _load_module("source_handoff_contract", HANDOFF_MODULE_PATH)
    gate = _load_module("source_handoff_gate", GATE_MODULE_PATH)
    roots = {
        "backend": tmp_path / "backend",
        "frontend": tmp_path / "frontend",
        "infra": tmp_path / "infra",
    }
    commits = {
        "backend": _init_repository(roots["backend"], "backend", "uv.lock"),
        "frontend": _init_repository(
            roots["frontend"], "frontend", "package-lock.json"
        ),
        "infra": _init_repository(roots["infra"], "infra", "uv.lock"),
    }
    workspace = gate.WorkspaceRoots.from_mapping(roots)
    operations = gate.system_operations()
    payload = handoff.issue_handoff(workspace, operations)
    return {
        "handoff": handoff,
        "gate": gate,
        "roots": roots,
        "commits": commits,
        "workspace": workspace,
        "operations": operations,
        "payload": payload,
    }


def _publish(
    fixture: dict[str, Any],
    *,
    payload_bytes: bytes | None = None,
    extra_path: bool = False,
    executable_summary: bool = False,
) -> str:
    handoff = fixture["handoff"]
    backend = fixture["roots"]["backend"]
    raw = payload_bytes or handoff.canonical_json_bytes(fixture["payload"])
    target = backend / handoff.HANDOFF_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    summary = backend / handoff.SUMMARY_PATH
    _write(summary, "Plan 93 source handoff summary.\n")
    if executable_summary:
        summary.chmod(0o755)
    _write(backend / ".planning/ROADMAP.md", "roadmap published\n")
    _write(backend / ".planning/STATE.md", "state published\n")
    if extra_path:
        _write(backend / "unexpected.txt", "source drift\n")
    _git(backend, "add", ".")
    _git(backend, "commit", "-qm", "publish source handoff")
    return _git(backend, "rev-parse", "HEAD")


def _utc(second: int) -> str:
    base = datetime(2026, 7, 20, tzinfo=timezone.utc) + timedelta(seconds=second)
    return base.isoformat().replace("+00:00", "Z")


def _formal_receipt(
    candidate: dict[str, Any],
    *,
    start: int,
    digest: str,
    platform: str = "linux-aarch64",
) -> dict[str, Any]:
    children: list[dict[str, Any]] = []
    for index, gate_id in enumerate(
        ("backend-python-hermetic", "frontend-web-fresh"), start=1
    ):
        child_start = start + index
        evidence: dict[str, Any]
        if gate_id == "backend-python-hermetic":
            evidence = {
                "schema": "stable-python-matrix",
                "collection_sha256": "1" * 64,
                "counts": {"total": 7, "passed": 7, "failed": 0},
            }
        else:
            evidence = {
                "schema": "stoa.web.gate-run.v1",
                "artifact": {"treeSha256": "2" * 64, "bytes": 3, "files": 1},
                "steps": [
                    {
                        "id": f"step-{step}",
                        "stdoutSha256": f"{step + 3:x}" * 64,
                        "stderrSha256": f"{step + 8:x}" * 64,
                        "counts": {"total": 1, "passed": 1},
                    }
                    for step in range(5)
                ],
                "receiptSha256": "e" * 64,
            }
        children.append(
            {
                "schema": "stoa.release.gate-receipt.v1",
                "gate_id": gate_id,
                "source": {
                    "candidate_identity": candidate["execution_identity"],
                    "repositories": deepcopy(candidate["repositories"]),
                },
                "command": {"name": "verify", "gate": gate_id},
                "runtime": {
                    "python": "3.12.13",
                    "platform": platform,
                    "clock": _utc(child_start),
                },
                "inputs": {"stable": gate_id},
                "result": {
                    "status": "PASS",
                    "classification": "COMPLETE_PASS",
                    "exit_code": 0,
                    "reason_code": None,
                    "outcomes": {"total": 1, "passed": 1},
                    "stdout_sha256": "a" * 64,
                    "stderr_sha256": "b" * 64,
                },
                "gate_evidence": evidence,
                "privacy": {"passed": True},
                "started_at": _utc(child_start),
                "ended_at": _utc(child_start + 1),
                "receipt_sha256": f"{index + 5:x}" * 64,
            }
        )
    return {
        "schema": "stoa.release.formal-gate-run.v1",
        "source": {
            "candidate_identity": candidate["execution_identity"],
            "repositories": deepcopy(candidate["repositories"]),
        },
        "command": {"name": "formal", "gate_ids": [child["gate_id"] for child in children]},
        "runtime": {
            "python": "3.12.13",
            "platform": platform,
            "clock": _utc(start),
        },
        "inputs": {"stable": True},
        "children": children,
        "result": {
            "status": "PASS",
            "classification": "COMPLETE_PASS",
            "exit_code": 0,
            "reason_code": None,
            "obligations": {
                "total": 2,
                "passed": 2,
                "policy_rejected": 0,
                "execution_failed": 0,
                "not_run": 0,
            },
        },
        "production": {
            "infrastructure": "NOT RUN",
            "deploy": "NOT RUN",
            "smoke": "NOT RUN",
            "rollback": "NOT RUN",
        },
        "privacy": {"passed": True},
        "started_at": _utc(start),
        "ended_at": _utc(start + 4),
        "receipt_sha256": digest,
    }


def test_handoff_is_canonical_ordered_and_never_serializes_publication(
    source_fixture: dict[str, Any],
) -> None:
    handoff = source_fixture["handoff"]
    payload = source_fixture["payload"]
    handoff.validate_handoff(payload, source_fixture["workspace"])
    raw = handoff.canonical_json_bytes(payload)
    assert json.loads(raw) == payload
    assert raw == handoff.canonical_json_bytes(json.loads(raw))
    assert [row["name"] for row in payload["repositories"]] == [
        "backend",
        "frontend",
        "infra",
    ]
    assert source_fixture["commits"]["backend"] in raw.decode()
    assert all(key not in raw for key in (b'"publication"', b'"branch"', b'"timestamp"'))


def test_publication_accepts_only_the_exact_direct_metadata_child(
    source_fixture: dict[str, Any],
) -> None:
    handoff = source_fixture["handoff"]
    publication = _publish(source_fixture)
    approved = handoff.verify_publication(publication, source_fixture["workspace"])
    assert approved["publication"] == publication
    assert approved["implementation"] == source_fixture["commits"]["backend"]
    assert approved["handoff"] == source_fixture["payload"]


@pytest.mark.parametrize("attack", ["extra", "mode", "pretty", "duplicate"])
def test_publication_rejects_extra_mode_and_noncanonical_json(
    source_fixture: dict[str, Any], attack: str
) -> None:
    handoff = source_fixture["handoff"]
    payload = source_fixture["payload"]
    raw: bytes | None = None
    if attack == "pretty":
        raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    elif attack == "duplicate":
        canonical = handoff.canonical_json_bytes(payload)
        raw = canonical.replace(b'{"identity_source":', b'{"schema":"duplicate","identity_source":', 1)
    publication = _publish(
        source_fixture,
        payload_bytes=raw,
        extra_path=attack == "extra",
        executable_summary=attack == "mode",
    )
    with pytest.raises(handoff.HandoffPolicyError):
        handoff.verify_publication(publication, source_fixture["workspace"])


def test_handoff_rejects_tree_lock_marker_order_and_tracked_ds_store(
    source_fixture: dict[str, Any],
) -> None:
    handoff = source_fixture["handoff"]
    payload = source_fixture["payload"]
    mutations = []
    wrong_order = deepcopy(payload)
    wrong_order["repositories"].reverse()
    mutations.append(wrong_order)
    for field in ("tree", "lock_sha256"):
        changed = deepcopy(payload)
        changed["repositories"][1][field] = "f" * (40 if field == "tree" else 64)
        mutations.append(changed)
    for changed in mutations:
        with pytest.raises(handoff.HandoffPolicyError):
            handoff.validate_handoff(changed, source_fixture["workspace"])

    infra = source_fixture["roots"]["infra"]
    _write(infra / ".DS_Store", "tracked\n")
    _git(infra, "add", ".DS_Store")
    _git(infra, "commit", "-qm", "track forbidden metadata")
    changed = handoff.issue_handoff(source_fixture["workspace"], source_fixture["operations"])
    with pytest.raises(handoff.HandoffPolicyError):
        handoff.validate_handoff(changed, source_fixture["workspace"])


def test_stable_projection_replaces_only_the_fixed_run_local_fields(
    source_fixture: dict[str, Any],
) -> None:
    handoff = source_fixture["handoff"]
    publication = _publish(source_fixture)
    candidate = source_fixture["gate"].issue_live_candidate(
        workspace=source_fixture["workspace"], operations=source_fixture["operations"]
    )
    left = _formal_receipt(candidate, start=0, digest="a" * 64)
    right = _formal_receipt(candidate, start=10, digest="b" * 64)
    for child in right["children"]:
        child["result"]["stdout_sha256"] = "c" * 64
        child["result"]["stderr_sha256"] = "d" * 64
    web = right["children"][1]["gate_evidence"]
    web["receiptSha256"] = "f" * 64
    for step in web["steps"]:
        step["stdoutSha256"] = "0" * 64
        step["stderrSha256"] = "1" * 64
    assert handoff.stable_formal_projection(left) == handoff.stable_formal_projection(right)

    right["children"][1]["gate_evidence"]["artifact"]["treeSha256"] = "9" * 64
    assert handoff.stable_formal_projection(left) != handoff.stable_formal_projection(right)
    assert publication == _git(source_fixture["roots"]["backend"], "rev-parse", "HEAD")


def test_admission_requires_exact_pfi_two_distinct_sequential_linux_passes(
    source_fixture: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = source_fixture["handoff"]
    gate = source_fixture["gate"]
    publication = _publish(source_fixture)
    candidate = gate.issue_live_candidate(
        workspace=source_fixture["workspace"], operations=source_fixture["operations"]
    )
    receipts = (
        _formal_receipt(candidate, start=0, digest="a" * 64),
        _formal_receipt(candidate, start=10, digest="b" * 64),
    )
    validated: list[str] = []

    def validate(receipt: dict[str, Any], **_: Any) -> None:
        validated.append(receipt["receipt_sha256"])

    monkeypatch.setattr(handoff.gate, "validate_formal_receipt", validate)
    admission = handoff.admit_formal_runs(
        publication,
        candidate,
        receipts,
        source_fixture["workspace"],
        source_fixture["operations"],
    )
    assert validated == ["a" * 64, "b" * 64]
    assert admission["status"] == "PASS"
    assert admission["publication"]["commit"] == publication
    assert admission["candidate_source"]["repositories"][0]["head"] == publication
    assert admission["production"] == receipts[0]["production"]


@pytest.mark.parametrize("attack", ["candidate-b", "duplicate", "overlap", "darwin", "not-pass", "drift"])
def test_admission_rejects_wrong_candidate_weak_run_and_retained_drift(
    source_fixture: dict[str, Any], monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    handoff = source_fixture["handoff"]
    gate = source_fixture["gate"]
    publication = _publish(source_fixture)
    candidate = gate.issue_live_candidate(
        workspace=source_fixture["workspace"], operations=source_fixture["operations"]
    )
    receipts = [
        _formal_receipt(candidate, start=0, digest="a" * 64),
        _formal_receipt(candidate, start=10, digest="b" * 64),
    ]
    monkeypatch.setattr(handoff.gate, "validate_formal_receipt", lambda *args, **kwargs: None)
    if attack == "candidate-b":
        candidate["repositories"][0]["head"] = source_fixture["commits"]["backend"]
        candidate["execution_identity"] = gate.candidate_execution_identity(candidate["repositories"])
        monkeypatch.setattr(handoff.gate, "validate_live_candidate", lambda *args, **kwargs: None)
    elif attack == "duplicate":
        receipts[1]["receipt_sha256"] = receipts[0]["receipt_sha256"]
    elif attack == "overlap":
        receipts[1]["started_at"] = receipts[0]["ended_at"] = _utc(3)
        receipts[1]["runtime"]["clock"] = _utc(3)
    elif attack == "darwin":
        for receipt in receipts:
            receipt["runtime"]["platform"] = "darwin-arm64"
    elif attack == "not-pass":
        receipts[1]["result"]["status"] = "NOT RUN"
    else:
        receipts[1]["inputs"]["stable"] = False
    with pytest.raises(handoff.HandoffPolicyError):
        handoff.admit_formal_runs(
            publication,
            candidate,
            tuple(receipts),
            source_fixture["workspace"],
            source_fixture["operations"],
        )


def test_source_handoff_schemas_are_closed_and_match_runtime_constants() -> None:
    handoff = _load_module("source_handoff_schema_contract", HANDOFF_MODULE_PATH)
    for path, schema_name in (
        (ROOT / "schemas/release/source-handoff-v1.schema.json", handoff.HANDOFF_SCHEMA),
        (
            ROOT / "schemas/release/source-handoff-admission-v1.schema.json",
            handoff.ADMISSION_SCHEMA,
        ),
    ):
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["additionalProperties"] is False
        assert schema["properties"]["schema"]["const"] == schema_name
    assert sha256(b"").hexdigest() == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
