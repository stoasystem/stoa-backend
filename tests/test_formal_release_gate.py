"""Closed contracts for the non-selectable Phase 474 formal aggregate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "scripts" / "release_gate.py"
SCHEMA_PATH = ROOT / "schemas" / "release" / "formal-gate-run-v1.schema.json"


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
