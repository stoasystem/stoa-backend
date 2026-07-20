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
        "gate_evidence": None,
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


def _python_matrix(gate: Any, *, status: str = "PASS") -> dict[str, Any]:
    source: dict[str, dict[str, Any]] = {}
    for relative_path in ("pyproject.toml", "uv.lock", "requirements.txt"):
        content = (ROOT / relative_path).read_bytes()
        source[relative_path] = {
            "bytes": len(content),
            "sha256": gate.sha256(content).hexdigest(),
        }
    collection_sha256 = "c" * 64
    runs = [
        {
            "run": index,
            "environment": f"fresh-{index}",
            "clock": clock,
            "seed": gate.PYTHON_MATRIX_SEED,
            "runtime": "3.12.13",
            "lock_sha256": source["uv.lock"]["sha256"],
            "collection_sha256": collection_sha256,
            "counts": {
                "total": 2124,
                "passed": 2124,
                "failed": 0,
                "error": 0,
                "skipped": 0,
                "xfail": 0,
                "xpass": 0,
            },
        }
        for index, clock in enumerate(gate.PYTHON_MATRIX_CLOCKS, start=1)
    ]
    matrix: dict[str, Any] = {
        "schema": gate.PYTHON_MATRIX_SCHEMA,
        "seed": gate.PYTHON_MATRIX_SEED,
        "clocks": list(gate.PYTHON_MATRIX_CLOCKS),
        "source": source,
        "suite_argv": list(gate.PYTHON_SUITE_ARGV),
        "status": status,
        "reason_code": None,
        "runs": runs,
    }
    if status == "NOT RUN":
        matrix["reason_code"] = "OS_NETWORK_BOUNDARY_UNAVAILABLE"
        matrix["runs"] = []
    elif status == "REJECTED":
        matrix["reason_code"] = "COLLECTION_IDENTITY_DRIFT"
        matrix["runs"][1]["collection_sha256"] = "d" * 64
        matrix["diagnostic"] = {
            "field": "collection_sha256",
            "run_1": collection_sha256,
            "run_2": "d" * 64,
        }
    return matrix


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


def _operations(gate: Any, *, returncode: int = 0, raises: bool = False) -> Any:
    moments = iter(["2026-07-19T00:00:00Z", "2026-07-19T00:00:01Z"])

    def run_process(argv: tuple[str, ...], timeout_seconds: int) -> Any:
        assert argv
        assert timeout_seconds == 120
        if raises:
            raise OSError("provider diagnostic TOP_SECRET=must-not-serialize")
        return gate.ProcessResult(
            returncode=returncode,
            stdout=b"TOP_SECRET=must-not-serialize\n",
            stderr=b"bounded diagnostic\n",
        )

    return gate.GateOperations(
        run_process=run_process,
        git=lambda root, argv: "",
        now_utc=lambda: next(moments),
        python_version=lambda: "3.12.11",
        platform_identity=lambda: "linux-aarch64",
    )


def _hermetic_operations(gate: Any, *, stdout: bytes, returncode: int) -> Any:
    moments = iter(["2026-07-19T00:00:00Z", "2026-07-19T00:00:01Z"])

    def run_process(argv: tuple[str, ...], timeout_seconds: int) -> Any:
        assert argv == gate.default_registry().require("backend-python-hermetic").argv
        assert timeout_seconds == 7200
        return gate.ProcessResult(returncode=returncode, stdout=stdout, stderr=b"")

    return gate.GateOperations(
        run_process=run_process,
        git=lambda root, argv: "",
        now_utc=lambda: next(moments),
        python_version=lambda: "3.12.13",
        platform_identity=lambda: "linux-aarch64",
    )


def test_canonical_receipt_digest_is_order_independent_and_tamper_evident() -> None:
    gate = _load_gate()
    receipt = _receipt()
    receipt["receipt_sha256"] = gate.canonical_receipt_sha256(receipt)
    reordered = dict(reversed(list(receipt.items())))
    assert gate.canonical_receipt_sha256(reordered) == receipt["receipt_sha256"]

    receipt["runtime"]["clock"] = "2035-01-15T12:00:00Z"
    assert gate.canonical_receipt_sha256(receipt) != receipt["receipt_sha256"]


def test_registry_rejects_duplicate_and_unknown_gate_ids() -> None:
    gate = _load_gate()
    spec = gate.GateSpec(
        gate_id="gate-self-test",
        argv=(sys.executable, "-c", "raise SystemExit(0)"),
        artifact_paths=("evidence/phase-474/candidate-identity.json",),
        config_paths=("schemas/release/gate-receipt-v1.schema.json",),
    )
    with pytest.raises(gate.GatePolicyError, match="duplicate gate id"):
        gate.GateRegistry((spec, spec))
    with pytest.raises(gate.GatePolicyError, match="unknown gate id"):
        gate.GateRegistry((spec,)).require("frontend-build")


def test_registered_gate_emits_a_source_bound_privacy_safe_receipt() -> None:
    gate = _load_gate()
    candidate = gate.load_candidate(CANDIDATE_PATH)
    receipt = gate.run_registered_gate(
        gate_id="gate-self-test",
        command_name="verify",
        candidate=candidate,
        registry=gate.default_registry(),
        operations=_operations(gate),
    )

    gate.validate_receipt(receipt, candidate=candidate, registry=gate.default_registry())
    encoded = json.dumps(receipt, sort_keys=True)
    assert receipt["result"]["classification"] == "COMPLETE_PASS"
    assert receipt["result"]["outcomes"] == _counts()
    assert "TOP_SECRET" not in encoded
    assert "must-not-serialize" not in encoded
    assert receipt["source"]["candidate_identity"] == candidate["execution_identity"]


@pytest.mark.parametrize(
    "stdout",
    [
        b"not-json\n",
        b"{}\n",
        b'{"schema":"stoa.phase474.python-matrix.v1","runs":[]}\n',
    ],
)
def test_hermetic_zero_exit_never_passes_without_a_valid_complete_matrix(stdout: bytes) -> None:
    gate = _load_gate()
    candidate = gate.load_candidate(CANDIDATE_PATH)
    receipt = gate.run_registered_gate(
        gate_id="backend-python-hermetic",
        command_name="verify",
        candidate=candidate,
        registry=gate.default_registry(),
        operations=_hermetic_operations(gate, stdout=stdout, returncode=0),
    )

    assert receipt["result"]["classification"] != "COMPLETE_PASS"
    assert receipt["gate_evidence"] is None
    gate.validate_receipt(receipt, candidate=candidate, registry=gate.default_registry())


def test_hermetic_valid_two_run_matrix_is_preserved_and_source_bound() -> None:
    gate = _load_gate()
    candidate = gate.load_candidate(CANDIDATE_PATH)
    matrix = _python_matrix(gate)
    receipt = gate.run_registered_gate(
        gate_id="backend-python-hermetic",
        command_name="verify",
        candidate=candidate,
        registry=gate.default_registry(),
        operations=_hermetic_operations(
            gate,
            stdout=json.dumps(matrix).encode("utf-8"),
            returncode=0,
        ),
    )

    assert receipt["result"]["classification"] == "COMPLETE_PASS"
    assert receipt["result"]["outcomes"] == _counts(total=2124, passed=2124)
    assert receipt["gate_evidence"] == matrix
    gate.validate_receipt(receipt, candidate=candidate, registry=gate.default_registry())
    schema = _load_schema()
    assert _matches(receipt, schema, schema)

    original_sha = receipt["receipt_sha256"]
    receipt["gate_evidence"]["runs"][0]["environment"] = "fresh-tampered"
    assert gate.canonical_receipt_sha256(receipt) != original_sha
    with pytest.raises(gate.GatePolicyError, match="matrix|digest"):
        gate.validate_receipt(receipt, candidate=candidate, registry=gate.default_registry())


@pytest.mark.parametrize("status", ["NOT RUN", "REJECTED"])
def test_hermetic_exit_two_requires_and_preserves_strict_matrix_evidence(status: str) -> None:
    gate = _load_gate()
    candidate = gate.load_candidate(CANDIDATE_PATH)
    matrix = _python_matrix(gate, status=status)
    receipt = gate.run_registered_gate(
        gate_id="backend-python-hermetic",
        command_name="verify",
        candidate=candidate,
        registry=gate.default_registry(),
        operations=_hermetic_operations(
            gate,
            stdout=json.dumps(matrix).encode("utf-8"),
            returncode=2,
        ),
    )

    expected_classification = (
        "NOT_RUN_OBLIGATION" if status == "NOT RUN" else "POLICY_REJECTION"
    )
    assert receipt["result"]["classification"] == expected_classification
    assert receipt["gate_evidence"] == matrix
    gate.validate_receipt(receipt, candidate=candidate, registry=gate.default_registry())


@pytest.mark.parametrize("stdout", [b"garbage", b"{}", b'{"status":"REJECTED"}'])
def test_hermetic_exit_two_does_not_accept_garbage_as_not_run_or_rejected(
    stdout: bytes,
) -> None:
    gate = _load_gate()
    candidate = gate.load_candidate(CANDIDATE_PATH)
    receipt = gate.run_registered_gate(
        gate_id="backend-python-hermetic",
        command_name="verify",
        candidate=candidate,
        registry=gate.default_registry(),
        operations=_hermetic_operations(gate, stdout=stdout, returncode=2),
    )

    assert receipt["result"]["status"] == "FAIL"
    assert receipt["result"]["reason_code"] == "GATE_EVIDENCE_INVALID"
    assert receipt["gate_evidence"] is None
    gate.validate_receipt(receipt, candidate=candidate, registry=gate.default_registry())


@pytest.mark.parametrize(
    ("returncode", "raises", "classification", "exit_code"),
    [
        (7, False, "POLICY_REJECTION", 2),
        (0, True, "EXECUTION_FAILURE", 3),
    ],
)
def test_policy_rejection_and_unexpected_execution_failure_stay_distinct(
    returncode: int,
    raises: bool,
    classification: str,
    exit_code: int,
) -> None:
    gate = _load_gate()
    candidate = gate.load_candidate(CANDIDATE_PATH)
    receipt = gate.run_registered_gate(
        gate_id="gate-self-test",
        command_name="self-test",
        candidate=candidate,
        registry=gate.default_registry(),
        operations=_operations(gate, returncode=returncode, raises=raises),
    )
    assert receipt["result"]["classification"] == classification
    assert receipt["result"]["exit_code"] == exit_code
    assert "provider diagnostic" not in json.dumps(receipt)
    gate.validate_receipt(receipt, candidate=candidate, registry=gate.default_registry())


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("source", lambda value: value["source"].__setitem__("candidate_identity", "b" * 64)),
        ("argv", lambda value: value["command"]["argv"].append("--ci-only")),
        ("counts", lambda value: value["result"]["outcomes"].__setitem__("skipped", 1)),
        ("artifact digest", lambda value: value["inputs"]["artifacts"][0].__setitem__("sha256", "b" * 64)),
        ("receipt digest", lambda value: value.__setitem__("receipt_sha256", "b" * 64)),
    ],
)
def test_runtime_validation_rejects_single_field_tampering(label: str, mutate: Any) -> None:
    gate = _load_gate()
    candidate = gate.load_candidate(CANDIDATE_PATH)
    receipt = gate.run_registered_gate(
        gate_id="gate-self-test",
        command_name="verify",
        candidate=candidate,
        registry=gate.default_registry(),
        operations=_operations(gate),
    )
    mutate(receipt)
    with pytest.raises(gate.GatePolicyError, match=".+"):
        gate.validate_receipt(receipt, candidate=candidate, registry=gate.default_registry())


def test_cli_exposes_only_registered_gate_selection_not_caller_argv() -> None:
    gate = _load_gate()
    parser = gate.build_parser()
    args = parser.parse_args(
        ["verify", "--candidate", str(CANDIDATE_PATH), "--gate", "gate-self-test"]
    )
    assert args.gate == "gate-self-test"
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "verify",
                "--candidate",
                str(CANDIDATE_PATH),
                "--gate",
                "gate-self-test",
                "--argv",
                "pytest -q",
            ]
        )


def test_candidate_validation_preserves_exact_plan_01_identity_and_not_run_fields() -> None:
    gate = _load_gate()
    candidate = gate.load_candidate(CANDIDATE_PATH)
    assert candidate["execution_identity"] == "0ce6ef7946e87ca41d05cb0c395ee58eea66dd61c41a100ede11ba06e9a3582c"
    assert candidate["repositories"][2]["root"] == "/Users/zhdeng/stoa-infra"
    for field in (
        "repository_mutation",
        "production_infrastructure",
        "production_deploy",
        "production_smoke",
        "production_rollback",
    ):
        assert candidate[field] == "NOT RUN"

    tampered = deepcopy(candidate)
    tampered["repositories"][2]["root"] = "/tmp/stoa-infra"
    with pytest.raises(gate.GatePolicyError, match="infra repository identity"):
        gate.validate_candidate(tampered)


def test_duplicate_json_fields_fail_before_candidate_or_receipt_use(tmp_path: Path) -> None:
    gate = _load_gate()
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"first","schema":"second"}\n', encoding="utf-8")
    with pytest.raises(gate.GatePolicyError, match="duplicate JSON field: schema"):
        gate.load_json(duplicate)


def test_candidate_and_receipt_schema_use_only_logical_repository_identities() -> None:
    candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    assert [repository["name"] for repository in candidate["repositories"]] == [
        "backend",
        "frontend",
        "infra",
    ]
    assert all("root" not in repository for repository in candidate["repositories"])

    schema = _load_schema()
    for definition in ("backend_repository", "frontend_repository", "infra_repository"):
        repository_schema = schema["$defs"][definition]
        assert "root" not in repository_schema["required"]
        assert "root" not in repository_schema["properties"]
    identity = schema["$defs"]["identity"]
    assert identity["required"] == ["repository", "path", "bytes", "sha256"]
    assert identity["properties"]["repository"]["enum"] == [
        "backend",
        "frontend",
        "infra",
    ]


def test_gate_spec_binds_logical_repository_and_safe_relative_cwd() -> None:
    gate = _load_gate()
    spec = gate.GateSpec(
        gate_id="portable-test",
        repository="frontend",
        cwd=".",
        argv=("node", "--version"),
        artifact_paths=("package-lock.json",),
        config_paths=("package.json",),
    )
    assert spec.repository == "frontend"
    assert spec.cwd == "."

    for cwd in ("/tmp", "../frontend", "nested/../../escape"):
        with pytest.raises(gate.GatePolicyError, match="cwd"):
            gate.GateSpec(
                gate_id="portable-test",
                repository="frontend",
                cwd=cwd,
                argv=("node", "--version"),
                artifact_paths=("package-lock.json",),
                config_paths=("package.json",),
            )
    with pytest.raises(gate.GatePolicyError, match="repository"):
        gate.GateSpec(
            gate_id="portable-test",
            repository="mobile",
            cwd=".",
            argv=("node", "--version"),
            artifact_paths=("package-lock.json",),
            config_paths=("package.json",),
        )


def test_workspace_roots_reject_symlinks_and_expose_no_paths_in_receipts(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    roots: dict[str, Path] = {}
    lock_paths = {"backend": "uv.lock", "frontend": "package-lock.json", "infra": "uv.lock"}
    for name, lock_path in lock_paths.items():
        root = tmp_path / name
        root.mkdir()
        (root / lock_path).write_text("lock\n", encoding="utf-8")
        roots[name] = root

    workspace = gate.WorkspaceRoots.from_mapping(roots)
    assert workspace.require("frontend") == roots["frontend"]
    link = tmp_path / "frontend-link"
    link.symlink_to(roots["frontend"], target_is_directory=True)
    with pytest.raises(gate.GatePolicyError, match="symlink"):
        gate.WorkspaceRoots.from_mapping({**roots, "frontend": link})
