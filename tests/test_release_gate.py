"""Closed contract tests for the Phase 474 release gate."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "release" / "gate-receipt-v1.schema.json"
GATE_PATH = ROOT / "scripts" / "release_gate.py"
CANDIDATE_PATH = ROOT / "evidence" / "phase-474" / "candidate-identity.json"
SHA256 = "a" * 64


def _load_schema() -> dict[str, Any]:
    value = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if reference is None:
        return schema
    assert isinstance(reference, str) and reference.startswith("#/$defs/")
    resolved = root["$defs"][reference.removeprefix("#/$defs/")]
    assert isinstance(resolved, dict)
    return resolved


def _matches(value: Any, schema: dict[str, Any], root: dict[str, Any]) -> bool:
    """Evaluate the deliberately small JSON-Schema vocabulary used by the receipt."""
    schema = _resolve(schema, root)
    if "oneOf" in schema:
        return sum(_matches(value, branch, root) for branch in schema["oneOf"]) == 1
    if "const" in schema and value != schema["const"]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False

    kind = schema.get("type")
    if isinstance(kind, list):
        if value is None and "null" in kind:
            return True
        kind = next((item for item in kind if item != "null"), None)
    if kind == "object":
        if not isinstance(value, dict):
            return False
        required = schema.get("required", [])
        if any(key not in value for key in required):
            return False
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            return False
        return all(
            key not in value or _matches(value[key], child, root)
            for key, child in properties.items()
        )
    if kind == "array":
        if not isinstance(value, list):
            return False
        if len(value) < schema.get("minItems", 0):
            return False
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return False
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            return False
        if "prefixItems" in schema:
            return all(
                _matches(item, child, root)
                for item, child in zip(value, schema["prefixItems"], strict=True)
            )
        item_schema = schema.get("items")
        return item_schema is None or all(_matches(item, item_schema, root) for item in value)
    if kind == "string":
        if not isinstance(value, str):
            return False
        if len(value) < schema.get("minLength", 0):
            return False
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return False
        return "pattern" not in schema or re.search(schema["pattern"], value) is not None
    if kind == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        return value >= schema.get("minimum", value) and value <= schema.get("maximum", value)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    return True


def _candidate_source() -> dict[str, Any]:
    candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    return {
        "candidate_identity": candidate["execution_identity"],
        "repositories": candidate["repositories"],
    }


def _counts(**overrides: int) -> dict[str, int]:
    value = {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfail": 0,
        "xpass": 0,
    }
    value.update(overrides)
    return value


def _receipt() -> dict[str, Any]:
    return {
        "schema": "stoa.release.gate-receipt.v1",
        "gate_id": "gate-self-test",
        "source": _candidate_source(),
        "command": {
            "name": "self-test",
            "argv": [sys.executable, "scripts/release_gate.py", "self-test"],
        },
        "runtime": {
            "python": "3.12.11",
            "platform": "linux-aarch64",
            "clock": "2026-07-01T12:00:00Z",
        },
        "inputs": {
            "artifacts": [
                {"path": "evidence/phase-474/candidate-identity.json", "bytes": 1, "sha256": SHA256}
            ],
            "configs": [
                {"path": "schemas/release/gate-receipt-v1.schema.json", "bytes": 1, "sha256": SHA256}
            ],
        },
        "result": {
            "status": "PASS",
            "classification": "COMPLETE_PASS",
            "exit_code": 0,
            "reason_code": None,
            "outcomes": _counts(),
            "stdout_sha256": SHA256,
            "stderr_sha256": SHA256,
        },
        "privacy": {
            "passed": True,
            "scanned_field_count": 1,
            "match_count": 0,
            "environment_values_serialized": False,
            "secret_values_serialized": False,
        },
        "started_at": "2026-07-19T00:00:00Z",
        "ended_at": "2026-07-19T00:00:01Z",
        "receipt_sha256": SHA256,
    }


def test_schema_accepts_one_complete_closed_receipt() -> None:
    schema = _load_schema()
    assert schema["additionalProperties"] is False
    assert _matches(_receipt(), schema, schema)


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("missing source", lambda value: value.pop("source")),
        ("unknown field", lambda value: value.__setitem__("token", "secret")),
        ("duplicate repository", lambda value: value["source"]["repositories"].__setitem__(2, deepcopy(value["source"]["repositories"][0]))),
        ("alternate command", lambda value: value["command"].__setitem__("name", "ci-verify")),
        ("unknown gate", lambda value: value.__setitem__("gate_id", "ci-only-second-graph")),
        ("dirty source", lambda value: value["source"]["repositories"][0].__setitem__("clean", False)),
        ("pass with skip", lambda value: value["result"]["outcomes"].__setitem__("skipped", 1)),
        ("privacy match", lambda value: value["privacy"].__setitem__("match_count", 1)),
        ("absolute artifact path", lambda value: value["inputs"]["artifacts"][0].__setitem__("path", "/tmp/result.json")),
    ],
)
def test_schema_rejects_missing_unknown_or_tampered_fields(label: str, mutate: Any) -> None:
    schema = _load_schema()
    receipt = _receipt()
    mutate(receipt)
    assert not _matches(receipt, schema, schema), label


def test_not_run_is_a_zero_count_obligation_and_never_pass_shaped() -> None:
    schema = _load_schema()
    receipt = _receipt()
    receipt["result"] = {
        "status": "NOT RUN",
        "classification": "NOT_RUN_OBLIGATION",
        "exit_code": 2,
        "reason_code": "PRODUCTION_OPERATION_NOT_AUTHORIZED",
        "outcomes": _counts(total=0, passed=0),
        "stdout_sha256": SHA256,
        "stderr_sha256": SHA256,
    }
    assert _matches(receipt, schema, schema)

    receipt["result"]["outcomes"]["passed"] = 1
    assert not _matches(receipt, schema, schema)


def test_policy_and_execution_failures_have_separate_exit_classes() -> None:
    schema = _load_schema()
    receipt = _receipt()
    receipt["result"] = {
        "status": "FAIL",
        "classification": "POLICY_REJECTION",
        "exit_code": 2,
        "reason_code": "SOURCE_IDENTITY_MISMATCH",
        "outcomes": _counts(failed=1, passed=0),
        "stdout_sha256": SHA256,
        "stderr_sha256": SHA256,
    }
    assert _matches(receipt, schema, schema)

    receipt["result"]["classification"] = "EXECUTION_FAILURE"
    assert not _matches(receipt, schema, schema)
    receipt["result"]["exit_code"] = 3
    assert _matches(receipt, schema, schema)


def _load_gate() -> Any:
    assert GATE_PATH.is_file(), "release gate implementation is missing"
    spec = importlib.util.spec_from_file_location("release_gate", GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

