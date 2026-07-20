"""Closed contracts for the non-selectable Phase 474 formal aggregate."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "scripts" / "release_gate.py"
SCHEMA_PATH = ROOT / "schemas" / "release" / "formal-gate-run-v1.schema.json"
CANDIDATE_PATH = ROOT / "evidence" / "phase-474" / "candidate-identity.json"


def _load_gate() -> Any:
    spec = importlib.util.spec_from_file_location("formal_release_gate", GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _child(classification: str) -> dict[str, Any]:
    shapes = {
        "pass": ("PASS", "COMPLETE_PASS", 0, None),
        "policy": ("FAIL", "POLICY_REJECTION", 2, "GATE_COMMAND_FAILED"),
        "execution": ("FAIL", "EXECUTION_FAILURE", 3, "GATE_EXECUTION_ERROR"),
        "not-run": (
            "NOT RUN",
            "NOT_RUN_OBLIGATION",
            2,
            "EXTERNAL_CHECK_UNAVAILABLE",
        ),
    }
    status, result_class, exit_code, reason = shapes[classification]
    return {
        "result": {
            "status": status,
            "classification": result_class,
            "exit_code": exit_code,
            "reason_code": reason,
        }
    }


def _failure_child_receipt(
    gate: Any,
    *,
    gate_id: str,
    candidate: dict[str, Any],
    workspace: Any,
    started_at: str,
    ended_at: str,
) -> dict[str, Any]:
    spec = gate.default_registry().require(gate_id)
    receipt: dict[str, Any] = {
        "schema": gate.RECEIPT_SCHEMA,
        "gate_id": gate_id,
        "source": gate._source(candidate),
        "command": {
            "name": "verify",
            "repository": spec.repository,
            "cwd": spec.cwd,
            "argv": list(spec.argv),
        },
        "runtime": {
            "python": "3.12.13",
            "platform": "linux-aarch64",
            "clock": started_at,
        },
        "inputs": {
            "artifacts": [
                gate._file_identity(workspace, spec.repository, path)
                for path in spec.artifact_paths
            ],
            "configs": [
                gate._file_identity(workspace, spec.repository, path)
                for path in spec.config_paths
            ],
        },
        "result": {
            "status": "FAIL",
            "classification": "EXECUTION_FAILURE",
            "exit_code": gate.EXECUTION_EXIT,
            "reason_code": "GATE_EXECUTION_ERROR",
            "outcomes": gate._counts(errors=1),
            "stdout_sha256": gate.sha256(b"").hexdigest(),
            "stderr_sha256": gate.sha256(b"").hexdigest(),
        },
        "gate_evidence": None,
        "privacy": {
            "passed": True,
            "scanned_field_count": len(gate._RECEIPT_KEYS),
            "match_count": 0,
            "environment_values_serialized": False,
            "secret_values_serialized": False,
        },
        "started_at": started_at,
        "ended_at": ended_at,
    }
    receipt["receipt_sha256"] = gate.canonical_receipt_sha256(receipt)
    return receipt


def _valid_formal_receipt(gate: Any) -> tuple[dict[str, Any], dict[str, Any], Any]:
    candidate = gate.load_candidate(CANDIDATE_PATH)
    workspace = gate.default_workspace_roots()
    children = [
        _failure_child_receipt(
            gate,
            gate_id="backend-python-hermetic",
            candidate=candidate,
            workspace=workspace,
            started_at="2026-07-19T00:00:01Z",
            ended_at="2026-07-19T00:00:02Z",
        ),
        _failure_child_receipt(
            gate,
            gate_id="frontend-web-fresh",
            candidate=candidate,
            workspace=workspace,
            started_at="2026-07-19T00:00:03Z",
            ended_at="2026-07-19T00:00:04Z",
        ),
    ]
    receipt: dict[str, Any] = {
        "schema": gate.FORMAL_RECEIPT_SCHEMA,
        "source": gate._source(candidate),
        "command": {
            "name": "formal",
            "repository": "backend",
            "cwd": ".",
            "argv": list(gate._FORMAL_COMMAND_ARGV),
            "gate_ids": list(gate.FORMAL_CHILD_GATE_IDS),
        },
        "runtime": {
            "python": "3.12.13",
            "platform": "linux-aarch64",
            "clock": "2026-07-19T00:00:00Z",
        },
        "inputs": gate._formal_inputs(workspace),
        "children": children,
        "result": gate.classify_formal_children(children),
        "production": {
            "infrastructure": "NOT RUN",
            "deploy": "NOT RUN",
            "smoke": "NOT RUN",
            "rollback": "NOT RUN",
        },
        "privacy": gate._formal_privacy(),
        "started_at": "2026-07-19T00:00:00Z",
        "ended_at": "2026-07-19T00:00:05Z",
    }
    receipt["receipt_sha256"] = gate.canonical_receipt_sha256(receipt)
    return receipt, candidate, workspace


def test_formal_graph_is_fixed_and_cannot_be_selected_by_the_caller(tmp_path: Path) -> None:
    gate = _load_gate()
    assert gate.FORMAL_CHILD_GATE_IDS == (
        "backend-python-hermetic",
        "frontend-web-fresh",
    )

    parser = gate.build_parser()
    argv = [
        "formal",
        "--candidate",
        str(tmp_path / "candidate.json"),
        "--backend-root",
        str(tmp_path / "backend"),
        "--frontend-root",
        str(tmp_path / "frontend"),
        "--infra-root",
        str(tmp_path / "infra"),
        "--output",
        str(tmp_path / "evidence" / "formal.json"),
    ]
    parsed = parser.parse_args(argv)
    assert parsed.command == "formal"
    for forbidden in ("--gate", "--gates", "--skip", "--only", "--order", "--argv"):
        with pytest.raises(SystemExit):
            parser.parse_args([*argv, forbidden, "frontend-web-fresh"])
    with pytest.raises(SystemExit):
        parser.parse_args([*argv, "--candidate", str(tmp_path / "other.json")])


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (left, right, expected)
        for left in ("pass", "policy", "execution", "not-run")
        for right in ("pass", "policy", "execution", "not-run")
        for expected in (
            "execution"
            if "execution" in {left, right}
            else "policy"
            if "policy" in {left, right}
            else "not-run"
            if "not-run" in {left, right}
            else "pass",
        )
    ],
)
def test_formal_classification_has_one_strict_priority(
    left: str,
    right: str,
    expected: str,
) -> None:
    gate = _load_gate()
    result = gate.classify_formal_children([_child(left), _child(right)])
    expected_shape = {
        "pass": ("PASS", "COMPLETE_PASS", 0, None),
        "policy": ("FAIL", "POLICY_REJECTION", 2, "CHILD_POLICY_REJECTION"),
        "execution": ("FAIL", "EXECUTION_FAILURE", 3, "CHILD_EXECUTION_FAILURE"),
        "not-run": (
            "NOT RUN",
            "NOT_RUN_OBLIGATION",
            2,
            "EXTERNAL_CHECK_UNAVAILABLE",
        ),
    }[expected]
    assert (
        result["status"],
        result["classification"],
        result["exit_code"],
        result["reason_code"],
    ) == expected_shape
    obligations = result["obligations"]
    assert obligations["total"] == 2
    assert sum(value for key, value in obligations.items() if key != "total") == 2


def test_formal_schema_is_closed_and_fixes_two_child_slots() -> None:
    assert SCHEMA_PATH.is_file()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$id"] == (
        "https://stoa.invalid/schemas/release/formal-gate-run-v1.schema.json"
    )
    assert schema["additionalProperties"] is False
    children = schema["properties"]["children"]
    assert children["minItems"] == children["maxItems"] == 2
    assert children["items"] is False
    assert [
        slot["allOf"][1]["properties"]["gate_id"]["const"]
        for slot in children["prefixItems"]
    ] == list(_load_gate().FORMAL_CHILD_GATE_IDS)


def test_formal_schema_and_runtime_constants_are_one_exact_graph() -> None:
    gate = _load_gate()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    command = schema["properties"]["command"]["properties"]
    assert command["argv"]["const"] == list(gate._FORMAL_COMMAND_ARGV)
    assert command["gate_ids"]["const"] == list(gate.FORMAL_CHILD_GATE_IDS)
    assert schema["properties"]["production"]["$ref"] == "#/$defs/production"
    assert set(schema["$defs"]["runtime"]["properties"]["platform"]["enum"]) == set(
        gate._FORMAL_PLATFORM_WEB_IDENTITIES
    )
    assert schema["$defs"]["privacy"]["properties"]["scanned_field_count"] == {
        "const": len(gate._FORMAL_RECEIPT_KEYS)
    }


def test_formal_validator_accepts_one_closed_source_bound_receipt() -> None:
    gate = _load_gate()
    receipt, candidate, workspace = _valid_formal_receipt(gate)

    gate.validate_formal_receipt(
        receipt,
        candidate=candidate,
        registry=gate.default_registry(),
        workspace=workspace,
    )
    encoded = json.dumps(receipt, sort_keys=True)
    assert str(workspace.require("backend")) not in encoded
    assert receipt["result"]["obligations"] == {
        "total": 2,
        "passed": 0,
        "policy_rejected": 0,
        "execution_failed": 2,
        "not_run": 0,
    }


@pytest.mark.parametrize(
    "tamper",
    [
        "missing",
        "extra",
        "child-count",
        "swapped",
        "source",
        "child-source",
        "child-digest",
        "child-extra",
        "result",
        "privacy",
        "production",
        "host-path",
        "platform-secret",
        "overlap",
    ],
)
def test_formal_validator_rejects_every_closed_contract_tamper(tamper: str) -> None:
    gate = _load_gate()
    receipt, candidate, workspace = _valid_formal_receipt(gate)
    if tamper == "missing":
        receipt.pop("inputs")
    elif tamper == "extra":
        receipt["diagnostic"] = "must-not-be-published"
    elif tamper == "child-count":
        receipt["children"].append(deepcopy(receipt["children"][1]))
    elif tamper == "swapped":
        receipt["children"].reverse()
    elif tamper == "source":
        receipt["source"]["candidate_identity"] = "f" * 64
    elif tamper == "child-source":
        receipt["children"][0]["source"]["candidate_identity"] = "f" * 64
        receipt["children"][0]["receipt_sha256"] = gate.canonical_receipt_sha256(
            receipt["children"][0]
        )
    elif tamper == "child-digest":
        receipt["children"][0]["receipt_sha256"] = "f" * 64
    elif tamper == "child-extra":
        receipt["children"][0]["token"] = "must-not-be-published"
        receipt["children"][0]["receipt_sha256"] = gate.canonical_receipt_sha256(
            receipt["children"][0]
        )
    elif tamper == "result":
        receipt["result"]["classification"] = "COMPLETE_PASS"
    elif tamper == "privacy":
        receipt["privacy"]["match_count"] = 1
    elif tamper == "production":
        receipt["production"]["deploy"] = "PASS"
    elif tamper == "host-path":
        receipt["children"][0]["runtime"]["platform"] = "/private/tmp/leak"
        receipt["children"][0]["receipt_sha256"] = gate.canonical_receipt_sha256(
            receipt["children"][0]
        )
    elif tamper == "platform-secret":
        receipt["children"][0]["runtime"]["platform"] = "TOP_SECRET=leak"
        receipt["children"][0]["receipt_sha256"] = gate.canonical_receipt_sha256(
            receipt["children"][0]
        )
    else:
        receipt["children"][1]["started_at"] = "2026-07-19T00:00:01Z"
        receipt["children"][1]["runtime"]["clock"] = "2026-07-19T00:00:01Z"
        receipt["children"][1]["receipt_sha256"] = gate.canonical_receipt_sha256(
            receipt["children"][1]
        )
    receipt["receipt_sha256"] = gate.canonical_receipt_sha256(receipt)

    with pytest.raises(gate.GatePolicyError):
        gate.validate_formal_receipt(
            receipt,
            candidate=candidate,
            registry=gate.default_registry(),
            workspace=workspace,
        )


@pytest.mark.parametrize("first", ["policy", "execution", "not-run"])
def test_formal_runs_the_second_child_after_every_valid_first_non_pass(
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    gate = _load_gate()
    events: list[str] = []
    child_results = {
        "backend-python-hermetic": _child(first),
        "frontend-web-fresh": _child("pass"),
    }

    def run_child(**kwargs: Any) -> dict[str, Any]:
        gate_id = kwargs["gate_id"]
        events.append(f"run:{gate_id}")
        return deepcopy(child_results[gate_id])

    def validate_child(receipt: Any, **kwargs: Any) -> None:
        del receipt
        events.append(f"validate:{kwargs['expected_gate_id']}")

    monkeypatch.setattr(gate, "validate_live_candidate", lambda *args, **kwargs: None)
    monkeypatch.setattr(gate, "_formal_inputs", lambda workspace: {})
    monkeypatch.setattr(gate, "run_registered_gate", run_child)
    monkeypatch.setattr(gate, "_validate_frozen_child_receipt", validate_child)
    monkeypatch.setattr(gate, "validate_formal_receipt", lambda *args, **kwargs: None)
    moments = iter(["2026-07-19T00:00:00Z", "2026-07-19T00:00:05Z"])
    operations = gate.GateOperations(
        run_process=lambda argv, cwd, timeout: gate.ProcessResult(0, b"", b""),
        git=lambda root, argv: "",
        now_utc=lambda: next(moments),
        python_version=lambda: "3.12.13",
        platform_identity=lambda: "linux-aarch64",
    )

    receipt = gate.run_formal_gate(
        candidate={"execution_identity": "a" * 64, "repositories": []},
        registry=gate.default_registry(),
        operations=operations,
        workspace=gate.WorkspaceRoots(()),
    )

    assert events == [
        "run:backend-python-hermetic",
        "validate:backend-python-hermetic",
        "run:frontend-web-fresh",
        "validate:frontend-web-fresh",
    ]
    assert receipt["result"] == gate.classify_formal_children(
        [child_results[gate_id] for gate_id in gate.FORMAL_CHILD_GATE_IDS]
    )


def test_registered_child_is_frozen_before_its_snapshot_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = _load_gate()
    active = False
    original = {"nested": {"value": 1}}

    @contextmanager
    def snapshot(*args: Any, **kwargs: Any) -> Any:
        nonlocal active
        del args, kwargs
        active = True
        try:
            yield gate.WorkspaceRoots(())
        finally:
            active = False

    def freeze(value: Any, label: str) -> dict[str, Any]:
        assert active
        assert label == "registered gate receipt"
        return deepcopy(value)

    monkeypatch.setattr(gate, "validate_live_candidate", lambda *args, **kwargs: None)
    monkeypatch.setattr(gate, "materialize_candidate_workspace", snapshot)
    monkeypatch.setattr(
        gate,
        "_run_registered_gate_on_snapshot",
        lambda **kwargs: original,
    )
    monkeypatch.setattr(gate, "validate_receipt", lambda *args, **kwargs: None)
    monkeypatch.setattr(gate, "_freeze_json_object", freeze)

    frozen = gate.run_registered_gate(
        gate_id="backend-python-hermetic",
        command_name="verify",
        candidate={},
        registry=gate.default_registry(),
        operations=gate.GateOperations(
            run_process=lambda argv, cwd, timeout: gate.ProcessResult(0, b"", b""),
            git=lambda root, argv: "",
            now_utc=lambda: "2026-07-19T00:00:00Z",
            python_version=lambda: "3.12.13",
            platform_identity=lambda: "linux-aarch64",
        ),
        workspace=gate.WorkspaceRoots(()),
    )

    assert not active
    assert frozen == original
    assert frozen is not original
    assert frozen["nested"] is not original["nested"]


def test_formal_stops_before_second_child_when_source_drifts_after_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = _load_gate()
    first_finished = False
    calls: list[str] = []

    def validate_live(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        if first_finished:
            raise gate.GatePolicyError("candidate drift")

    def run_child(**kwargs: Any) -> dict[str, Any]:
        nonlocal first_finished
        calls.append(kwargs["gate_id"])
        first_finished = True
        return _child("pass")

    monkeypatch.setattr(gate, "validate_live_candidate", validate_live)
    monkeypatch.setattr(gate, "_formal_inputs", lambda workspace: {})
    monkeypatch.setattr(gate, "run_registered_gate", run_child)
    operations = gate.GateOperations(
        run_process=lambda argv, cwd, timeout: gate.ProcessResult(0, b"", b""),
        git=lambda root, argv: "",
        now_utc=lambda: "2026-07-19T00:00:00Z",
        python_version=lambda: "3.12.13",
        platform_identity=lambda: "linux-aarch64",
    )

    with pytest.raises(gate.GatePolicyError, match="candidate drift"):
        gate.run_formal_gate(
            candidate={"execution_identity": "a" * 64, "repositories": []},
            registry=gate.default_registry(),
            operations=operations,
            workspace=gate.WorkspaceRoots(()),
        )
    assert calls == ["backend-python-hermetic"]


def test_formal_publication_revalidates_outer_then_candidate_last(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    events: list[str] = []
    output = tmp_path / "formal.json"
    receipt = {"result": {"exit_code": 2}}
    operations = gate.GateOperations(
        run_process=lambda argv, cwd, timeout: gate.ProcessResult(0, b"", b""),
        git=lambda root, argv: "",
        now_utc=lambda: "2026-07-19T00:00:00Z",
        python_version=lambda: "3.12.13",
        platform_identity=lambda: "linux-aarch64",
    )

    monkeypatch.setattr(gate, "_prepare_formal_output", lambda args: output)
    monkeypatch.setattr(gate, "_workspace_from_args", lambda args: gate.WorkspaceRoots(()))
    monkeypatch.setattr(gate, "load_candidate", lambda path: {})
    monkeypatch.setattr(gate, "system_operations", lambda: operations)
    monkeypatch.setattr(
        gate,
        "run_formal_gate",
        lambda **kwargs: events.append("run") or receipt,
    )
    monkeypatch.setattr(
        gate,
        "validate_formal_receipt",
        lambda *args, **kwargs: events.append("outer"),
    )
    monkeypatch.setattr(
        gate,
        "validate_live_candidate",
        lambda *args, **kwargs: events.append("candidate"),
    )

    def publish(value: Any, path: Path, *, before_replace: Any) -> None:
        assert value is receipt
        assert path == output
        before_replace()
        events.append("replace")

    monkeypatch.setattr(gate, "publish_formal_receipt", publish)
    assert gate._execute_formal(SimpleNamespace(candidate="candidate.json")) == 2
    assert events == ["run", "outer", "candidate", "replace"]


def test_formal_publication_requires_private_atomic_output(tmp_path: Path) -> None:
    gate = _load_gate()
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    output = parent / "formal.json"
    receipt = {"schema": "stoa.release.formal-gate-run.v1", "receipt_sha256": "a" * 64}

    gate.publish_formal_receipt(receipt, output, before_replace=lambda: None)
    metadata = output.stat()
    assert metadata.st_mode & 0o777 == 0o600
    assert metadata.st_nlink == 1
    assert output.read_bytes() == (
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    output.write_text('{"status":"PASS","stale":true}\n', encoding="utf-8")
    parent.chmod(0o755)
    with pytest.raises(gate.GatePolicyError):
        gate.publish_formal_receipt(receipt, output, before_replace=lambda: None)
    assert not output.exists()


def test_formal_publication_invalidates_on_callback_or_hostile_target(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    output = parent / "formal.json"
    receipt = {"schema": gate.FORMAL_RECEIPT_SCHEMA, "receipt_sha256": "a" * 64}

    with pytest.raises(gate.GatePolicyError):
        gate.publish_formal_receipt(
            receipt,
            output,
            before_replace=lambda: (_ for _ in ()).throw(
                gate.GatePolicyError("candidate drift")
            ),
        )
    assert not output.exists()
    assert list(parent.iterdir()) == []

    output.mkdir()
    with pytest.raises(gate.GatePolicyError, match="directory"):
        gate.publish_formal_receipt(receipt, output, before_replace=lambda: None)
    assert output.is_dir()


def test_formal_publication_rejects_a_hardlinked_temporary_inode(tmp_path: Path) -> None:
    gate = _load_gate()
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    output = parent / "formal.json"
    linked = parent / "linked.json"
    receipt = {"schema": gate.FORMAL_RECEIPT_SCHEMA, "receipt_sha256": "a" * 64}

    def add_link() -> None:
        temporary = next(parent.glob(".formal.json.*.tmp"))
        os.link(temporary, linked)

    with pytest.raises(gate.GatePolicyError):
        gate.publish_formal_receipt(receipt, output, before_replace=add_link)
    assert not output.exists()
    assert linked.stat().st_nlink == 1


def test_formal_preflight_removes_stale_output_before_root_validation(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    output = parent / "formal.json"
    output.write_text('{"stale":true}\n', encoding="utf-8")
    parser = gate.build_parser()
    args = parser.parse_args(
        [
            "formal",
            "--candidate",
            str(tmp_path / "missing-candidate.json"),
            "--backend-root",
            str(tmp_path / "missing-backend"),
            "--frontend-root",
            str(tmp_path / "missing-frontend"),
            "--infra-root",
            str(tmp_path / "missing-infra"),
            "--output",
            str(output),
        ]
    )

    with pytest.raises(gate.GatePolicyError):
        gate._execute_formal(args)
    assert not output.exists()


def test_formal_preflight_never_deletes_authoritative_source_with_fake_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    authoritative_root = tmp_path / "authoritative-backend"
    authoritative_root.mkdir(mode=0o700)
    source_file = authoritative_root / "must-remain.py"
    source_file.write_text("must remain\n", encoding="utf-8")
    monkeypatch.setattr(gate, "ROOT", authoritative_root)
    args = SimpleNamespace(
        candidate=str(tmp_path / "candidate.json"),
        backend_root=str(tmp_path / "fake-backend"),
        frontend_root=str(tmp_path / "fake-frontend"),
        infra_root=str(tmp_path / "fake-infra"),
        output=str(source_file),
    )

    with pytest.raises(gate.GatePolicyError, match="outside source"):
        gate._prepare_formal_output(args)
    assert source_file.read_text(encoding="utf-8") == "must remain\n"

    with pytest.raises(gate.GatePolicyError, match="outside source"):
        gate.publish_formal_receipt(
            {"schema": gate.FORMAL_RECEIPT_SCHEMA, "receipt_sha256": "a" * 64},
            source_file,
            before_replace=lambda: None,
        )
    assert source_file.read_text(encoding="utf-8") == "must remain\n"
