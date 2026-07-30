"""Policy tests for the repository-wide static-quality release gate."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "scripts" / "release_gate.py"
QUALITY_SCHEMA_PATH = ROOT / "schemas" / "release" / "quality-repair-report-v1.schema.json"


def _load_gate() -> Any:
    spec = importlib.util.spec_from_file_location("quality_gate_policy", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _passing_report(gate: Any) -> dict[str, object]:
    return {
        "schema": gate.QUALITY_REPORT_SCHEMA,
        "source_scope": list(gate.QUALITY_SOURCE_SCOPE),
        "commands": [list(command) for command in gate.QUALITY_COMMANDS],
        "results": [
            {"tool": "ruff", "exit_code": 0, "diagnostics": []},
            {"tool": "mypy", "exit_code": 0, "diagnostics": []},
        ],
        "status": "PASS",
    }


def test_canonical_gate_registers_the_exact_standalone_quality_scope() -> None:
    gate = _load_gate()

    assert QUALITY_SCHEMA_PATH.is_file()
    assert gate.QUALITY_SOURCE_SCOPE == ("src/stoa", "scripts", "tests")
    assert gate.QUALITY_COMMANDS == (
        ("{python}", "-m", "ruff", "check", "src", "tests", "scripts", "--no-cache"),
        (
            "{python}",
            "-m",
            "mypy",
            "--no-incremental",
            "--explicit-package-bases",
            "src/stoa",
            "scripts",
            "tests",
        ),
    )
    assert gate.default_registry().require(gate.QUALITY_GATE_ID).argv == (
        "{python}",
        "scripts/release_gate.py",
        "quality",
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda report: report["source_scope"].pop(),
        lambda report: report["commands"][1].remove("tests"),
        lambda report: report["commands"][0].append("--ignore=F401"),
        lambda report: report["results"].__setitem__(
            1, {"tool": "mypy", "exit_code": 1, "diagnostics": ["residual"]}
        ),
    ],
)
def test_quality_policy_rejects_scope_or_semantic_weakening(mutate: Any) -> None:
    gate = _load_gate()
    report = deepcopy(_passing_report(gate))
    mutate(report)

    with pytest.raises(gate.GatePolicyError):
        gate.validate_quality_report(report)


def test_quality_report_schema_is_closed_and_matches_the_runtime_contract() -> None:
    gate = _load_gate()
    schema = json.loads(QUALITY_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$id"] == gate.QUALITY_REPORT_SCHEMA
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["schema", "source_scope", "commands", "results", "status"]
    gate.validate_quality_report(_passing_report(gate))
