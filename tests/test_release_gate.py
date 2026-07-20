"""Closed contract tests for the Phase 474 release gate."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
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
            "repository": "backend",
            "cwd": ".",
            "argv": ["{python}", "scripts/release_gate.py", "self-test"],
        },
        "runtime": {
            "python": "3.12.11",
            "platform": "linux-aarch64",
            "clock": "2026-07-01T12:00:00Z",
        },
        "inputs": {
            "artifacts": [
                {
                    "repository": "backend",
                    "path": "evidence/phase-474/candidate-identity.json",
                    "bytes": 1,
                    "sha256": SHA256,
                }
            ],
            "configs": [
                {
                    "repository": "backend",
                    "path": "schemas/release/gate-receipt-v1.schema.json",
                    "bytes": 1,
                    "sha256": SHA256,
                }
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

    def run_process(argv: tuple[str, ...], cwd: Path, timeout_seconds: int) -> Any:
        assert argv
        assert cwd == ROOT
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

    def run_process(argv: tuple[str, ...], cwd: Path, timeout_seconds: int) -> Any:
        assert argv == gate.default_registry().require("backend-python-hermetic").argv
        assert cwd == ROOT
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
        argv=("{python}", "-c", "raise SystemExit(0)"),
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
    receipt = gate._run_registered_gate_on_snapshot(
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
    receipt = gate._run_registered_gate_on_snapshot(
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
    receipt = gate._run_registered_gate_on_snapshot(
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
    receipt = gate._run_registered_gate_on_snapshot(
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
    receipt = gate._run_registered_gate_on_snapshot(
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
    receipt = gate._run_registered_gate_on_snapshot(
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
    receipt = gate._run_registered_gate_on_snapshot(
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


def test_candidate_validation_preserves_logical_identity_and_not_run_fields() -> None:
    gate = _load_gate()
    candidate = gate.load_candidate(CANDIDATE_PATH)
    assert candidate["execution_identity"] == "b513818ec3aa39c774e9ac8d6c2934189fc75a39ff5faff6dc170a1ce702acfc"
    assert all("root" not in repository for repository in candidate["repositories"])
    for field in (
        "repository_mutation",
        "production_infrastructure",
        "production_deploy",
        "production_smoke",
        "production_rollback",
    ):
        assert candidate[field] == "NOT RUN"

    tampered = deepcopy(candidate)
    tampered["repositories"][2]["name"] = "mobile"
    with pytest.raises(gate.GatePolicyError, match="infra repository identity"):
        gate.validate_candidate(tampered)


def _live_candidate_fixture(gate: Any, tmp_path: Path) -> tuple[Any, Any, dict[str, dict[str, Any]]]:
    roots: dict[str, Path] = {}
    states: dict[str, dict[str, Any]] = {}
    contracts = {
        "backend": ("uv.lock", "pyproject.toml", '[project]\nname = "stoa-backend"\n'),
        "frontend": ("package-lock.json", "package.json", '{"name":"stoa-frontend"}\n'),
        "infra": ("uv.lock", "pyproject.toml", '[project]\nname = "stoa-infra"\n'),
    }
    for index, (name, (lock_path, marker_path, marker)) in enumerate(contracts.items(), start=1):
        root = tmp_path / f"checkout-{index}"
        root.mkdir()
        lock_bytes = f"{name}-lock\n".encode()
        (root / lock_path).write_bytes(lock_bytes)
        (root / marker_path).write_text(marker, encoding="utf-8")
        roots[name] = root
        states[name] = {
            "head": str(index) * 40,
            "tree": str(index + 3) * 40,
            "porcelain": "",
            "blob": lock_bytes,
        }

    root_names = {root: name for name, root in roots.items()}

    def git(root: Path, argv: tuple[str, ...]) -> str:
        state = states[root_names[root]]
        if argv == ("rev-parse", "HEAD"):
            return state["head"]
        if argv[0] == "rev-parse" and argv[1].endswith("^{tree}"):
            return state["tree"]
        if argv[0:3] == ("ls-tree", "-r", "-z"):
            return state.get("head_entries", "")
        if argv == ("ls-files", "-v", "--"):
            return state.get("index_flags", "H tracked")
        if argv == ("ls-files", "--stage", "-z", "--"):
            return state.get("index_entries", "")
        if argv == ("ls-files", "--", ".DS_Store"):
            return state.get("tracked_ds_store", "")
        if argv[0:2] == ("ls-tree", "--name-only") and argv[-2:] == (
            "--",
            ".DS_Store",
        ):
            assert argv[2] == state["head"]
            return state.get("head_ds_store", "")
        if argv[0:3] == ("ls-files", "--others", "--exclude-standard"):
            return state["porcelain"]
        if argv[0:2] == ("cat-file", "-e"):
            return ""
        raise AssertionError(argv)

    def git_blob(root: Path, revision_path: str) -> bytes:
        name = root_names[root]
        lock_path = "package-lock.json" if name == "frontend" else "uv.lock"
        revision, actual_lock_path = revision_path.split(":", 1)
        assert len(revision) == 40
        assert actual_lock_path == lock_path
        return states[root_names[root]]["blob"]

    operations = gate.GateOperations(
        run_process=lambda argv, cwd, timeout: (_ for _ in ()).throw(
            AssertionError("gate command must not execute during candidate validation")
        ),
        git=git,
        git_blob=git_blob,
        now_utc=lambda: "2026-07-20T00:00:00Z",
        python_version=lambda: "3.12.13",
        platform_identity=lambda: "linux-x86_64",
    )
    return gate.WorkspaceRoots.from_mapping(roots), operations, states


def test_live_candidate_is_host_path_free_and_revalidates_exact_roots(tmp_path: Path) -> None:
    gate = _load_gate()
    workspace, operations, _ = _live_candidate_fixture(gate, tmp_path)
    candidate = gate.issue_live_candidate(workspace=workspace, operations=operations)

    gate.validate_live_candidate(candidate, workspace=workspace, operations=operations)
    encoded = json.dumps(candidate, sort_keys=True)
    assert str(tmp_path) not in encoded
    assert candidate["candidate_issued"] is True
    assert all(repository["porcelain_sha256"] == gate.sha256(b"").hexdigest() for repository in candidate["repositories"])


@pytest.mark.parametrize(
    "drift",
    [
        "head",
        "tree",
        "index-projection",
        "porcelain",
        "index-flag",
        "tracked-infra-exception",
        "head-tracked-infra-exception",
        "committed-lock",
        "worktree-lock",
    ],
)
def test_live_candidate_rejects_every_source_drift(tmp_path: Path, drift: str) -> None:
    gate = _load_gate()
    workspace, operations, states = _live_candidate_fixture(gate, tmp_path)
    candidate = gate.issue_live_candidate(workspace=workspace, operations=operations)

    if drift == "head":
        states["backend"]["head"] = "9" * 40
    elif drift == "tree":
        states["frontend"]["tree"] = "9" * 40
    elif drift == "index-projection":
        lock_bytes = (workspace.require("frontend") / "package-lock.json").read_bytes()
        states["frontend"]["index_entries"] = (
            f"100644 {gate._raw_git_blob_oid(lock_bytes)} 0\tpackage-lock.json\0"
        )
    elif drift == "porcelain":
        states["infra"]["porcelain"] = "?? unexpected.txt"
    elif drift == "index-flag":
        states["backend"]["index_flags"] = "h source.py"
    elif drift == "tracked-infra-exception":
        states["infra"]["tracked_ds_store"] = ".DS_Store"
    elif drift == "head-tracked-infra-exception":
        states["infra"]["head_ds_store"] = ".DS_Store"
    elif drift == "committed-lock":
        states["backend"]["blob"] = b"different-committed-lock\n"
    else:
        (workspace.require("frontend") / "package-lock.json").write_bytes(b"different-worktree-lock\n")

    with pytest.raises(gate.GatePolicyError, match="candidate|lock|clean|index|DS_Store"):
        gate.validate_live_candidate(candidate, workspace=workspace, operations=operations)


def test_candidate_untracked_scan_has_only_exact_infra_root_exception(tmp_path: Path) -> None:
    gate = _load_gate()
    workspace, operations, _ = _live_candidate_fixture(gate, tmp_path)
    calls: list[tuple[Path, tuple[str, ...]]] = []
    original_git = operations.git

    def observe_git(root: Path, argv: tuple[str, ...]) -> str:
        calls.append((root, argv))
        return original_git(root, argv)

    observed = gate.GateOperations(
        run_process=operations.run_process,
        git=observe_git,
        git_blob=operations.git_blob,
        now_utc=operations.now_utc,
        python_version=operations.python_version,
        platform_identity=operations.platform_identity,
    )

    gate.issue_live_candidate(workspace=workspace, operations=observed)
    untracked_calls = {
        root: argv
        for root, argv in calls
        if argv[0:3] == ("ls-files", "--others", "--exclude-standard")
    }
    assert ":(top,exclude,literal).DS_Store" not in untracked_calls[
        workspace.require("backend")
    ]
    assert ":(top,exclude,literal).DS_Store" not in untracked_calls[
        workspace.require("frontend")
    ]
    assert (
        untracked_calls[workspace.require("infra")][-1]
        == ":(top,exclude,literal).DS_Store"
    )
    assert not any(argv and argv[0] == "status" for _, argv in calls)
    assert not any(argv and argv[0] == "write-tree" for _, argv in calls)


def test_candidate_capture_rejects_a_torn_head_snapshot(tmp_path: Path) -> None:
    gate = _load_gate()
    workspace, operations, states = _live_candidate_fixture(gate, tmp_path)
    original_git = operations.git
    head_reads = 0

    def racy_git(root: Path, argv: tuple[str, ...]) -> str:
        nonlocal head_reads
        result = original_git(root, argv)
        if root == workspace.require("backend") and argv == ("rev-parse", "HEAD"):
            head_reads += 1
            if head_reads == 1:
                states["backend"]["head"] = "9" * 40
        return result

    racy = gate.GateOperations(
        run_process=operations.run_process,
        git=racy_git,
        git_blob=operations.git_blob,
        now_utc=operations.now_utc,
        python_version=operations.python_version,
        platform_identity=operations.platform_identity,
    )
    with pytest.raises(gate.GatePolicyError, match="changed during candidate capture"):
        gate.issue_live_candidate(workspace=workspace, operations=racy)


def test_candidate_capture_rejects_index_change_during_second_scan(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    workspace, operations, states = _live_candidate_fixture(gate, tmp_path)
    original_git = operations.git
    index_reads = 0

    def racy_git(root: Path, argv: tuple[str, ...]) -> str:
        nonlocal index_reads
        result = original_git(root, argv)
        if root == workspace.require("backend") and argv == (
            "ls-files",
            "--stage",
            "-z",
            "--",
        ):
            index_reads += 1
            if index_reads == 2:
                states["backend"]["index_entries"] = (
                    f"100644 {'9' * 40} 0\tnewly-staged.txt\0"
                )
                states["backend"]["index_flags"] = "H newly-staged.txt"
        return result

    racy = gate.GateOperations(
        run_process=operations.run_process,
        git=racy_git,
        git_blob=operations.git_blob,
        now_utc=operations.now_utc,
        python_version=operations.python_version,
        platform_identity=operations.platform_identity,
    )

    with pytest.raises(gate.GatePolicyError, match="changed during candidate capture"):
        gate.issue_live_candidate(workspace=workspace, operations=racy)


def test_self_test_requires_an_explicit_candidate() -> None:
    gate = _load_gate()
    parser = gate.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["self-test"])


def test_real_cli_issues_and_rechecks_candidate_from_nondefault_roots(tmp_path: Path) -> None:
    roots: dict[str, Path] = {}
    contracts = {
        "backend": ("uv.lock", "pyproject.toml", '[project]\nname = "stoa-backend"\n'),
        "frontend": ("package-lock.json", "package.json", '{"name":"stoa-frontend"}\n'),
        "infra": ("uv.lock", "pyproject.toml", '[project]\nname = "stoa-infra"\n'),
    }
    for index, (name, (lock_path, marker_path, marker)) in enumerate(contracts.items(), start=1):
        root = tmp_path / f"arbitrary-root-{index}"
        root.mkdir()
        (root / lock_path).write_text(f"{name}-lock\n", encoding="utf-8")
        (root / marker_path).write_text(marker, encoding="utf-8")
        if name == "frontend":
            (root / ".gitattributes").write_text(
                "exported-test.txt export-ignore\n", encoding="utf-8"
            )
            (root / "exported-test.txt").write_text("must remain\n", encoding="utf-8")
        if name == "backend":
            (root / "schemas" / "release").mkdir(parents=True)
            (root / "schemas" / "release" / "gate-receipt-v1.schema.json").write_text(
                "{}\n", encoding="utf-8"
            )
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "gate@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
        roots[name] = root

    candidate_path = tmp_path / "candidate.json"
    receipt_path = tmp_path / "receipt.json"
    root_args = [
        "--backend-root",
        str(roots["backend"]),
        "--frontend-root",
        str(roots["frontend"]),
        "--infra-root",
        str(roots["infra"]),
    ]
    forbidden_output = roots["backend"] / "candidate.json"
    rejected_output = subprocess.run(
        [
            sys.executable,
            str(GATE_PATH),
            "candidate",
            *root_args,
            "--output",
            str(forbidden_output),
        ],
        check=False,
    )
    assert rejected_output.returncode == 2
    assert not forbidden_output.exists()
    rejected_relative = subprocess.run(
        [sys.executable, str(GATE_PATH), "candidate", *root_args, "--output", "candidate.json"],
        check=False,
        cwd=tmp_path,
    )
    assert rejected_relative.returncode == 2
    assert not (tmp_path / "candidate.json").exists()

    issued = subprocess.run(
        [sys.executable, str(GATE_PATH), "candidate", *root_args, "--output", str(candidate_path)],
        check=False,
    )
    assert issued.returncode == 0
    checked = subprocess.run(
        [
            sys.executable,
            str(GATE_PATH),
            "self-test",
            "--candidate",
            str(candidate_path),
            *root_args,
            "--output",
            str(receipt_path),
        ],
        check=False,
    )
    assert checked.returncode == 0
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert str(tmp_path) not in json.dumps(receipt)
    assert receipt["inputs"]["artifacts"][0]["path"] == "pyproject.toml"
    assert "candidate-identity.json" not in json.dumps(receipt)

    ignored_name = "ignored-runtime.py"
    (roots["frontend"] / ".git" / "info" / "exclude").write_text(
        f"{ignored_name}\n", encoding="utf-8"
    )
    (roots["frontend"] / ignored_name).write_text(
        "raise RuntimeError('must not execute')\n", encoding="utf-8"
    )
    gate = _load_gate()
    workspace = gate.WorkspaceRoots.from_mapping(roots)
    operations = gate.system_operations()
    candidate = gate.load_candidate(candidate_path)
    gate.validate_live_candidate(candidate, workspace=workspace, operations=operations)
    with gate.materialize_candidate_workspace(
        candidate,
        source_workspace=workspace,
        operations=operations,
    ) as snapshot:
        assert not (snapshot.require("frontend") / ignored_name).exists()
        assert (snapshot.require("frontend") / "exported-test.txt").read_text(
            encoding="utf-8"
        ) == "must remain\n"
        snapshot_head = subprocess.run(
            ["git", "-C", str(snapshot.require("backend")), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert snapshot_head == candidate["repositories"][0]["head"]
    (roots["frontend"] / ignored_name).unlink()

    infra_ds_store = roots["infra"] / ".DS_Store"
    infra_ds_store.write_text("tracked in HEAD\n", encoding="utf-8")
    subprocess.run(["git", "add", ".DS_Store"], cwd=roots["infra"], check=True)
    subprocess.run(
        ["git", "commit", "-qm", "track exact infra exception"],
        cwd=roots["infra"],
        check=True,
    )
    subprocess.run(
        ["git", "rm", "--cached", "-q", ".DS_Store"],
        cwd=roots["infra"],
        check=True,
    )
    staged_deletion_output = tmp_path / "staged-deletion-candidate.json"
    staged_deletion = subprocess.run(
        [
            sys.executable,
            str(GATE_PATH),
            "candidate",
            *root_args,
            "--output",
            str(staged_deletion_output),
        ],
        check=False,
    )
    assert staged_deletion.returncode == 2
    assert not staged_deletion_output.exists()

    (roots["frontend"] / "untracked.txt").write_text("drift\n", encoding="utf-8")
    receipt_path.write_text('{"status":"PASS","stale":true}\n', encoding="utf-8")
    stale = subprocess.run(
        [
            sys.executable,
            str(GATE_PATH),
            "self-test",
            "--candidate",
            str(candidate_path),
            *root_args,
            "--output",
            str(receipt_path),
        ],
        check=False,
    )
    assert stale.returncode == 2
    assert not receipt_path.exists()


def test_public_gate_entry_rejects_stale_candidate_before_command(tmp_path: Path) -> None:
    gate = _load_gate()
    workspace, operations, states = _live_candidate_fixture(gate, tmp_path)
    candidate = gate.issue_live_candidate(workspace=workspace, operations=operations)
    states["backend"]["head"] = "9" * 40

    with pytest.raises(gate.GatePolicyError, match="candidate"):
        gate.run_registered_gate(
            gate_id="gate-self-test",
            command_name="self-test",
            candidate=candidate,
            registry=gate.default_registry(),
            operations=operations,
            workspace=workspace,
        )


def test_public_gate_rechecks_live_state_after_materialization_before_command(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    workspace, operations, states = _live_candidate_fixture(gate, tmp_path)
    candidate = gate.issue_live_candidate(workspace=workspace, operations=operations)
    materialized = 0

    def materialize(source: Path, commit: str, destination: Path) -> None:
        nonlocal materialized
        assert len(commit) == 40
        for source_file in source.iterdir():
            if source_file.is_file():
                (destination / source_file.name).write_bytes(source_file.read_bytes())
        materialized += 1
        if materialized == 1:
            states["backend"]["head"] = "9" * 40

    checked_operations = gate.GateOperations(
        run_process=operations.run_process,
        git=operations.git,
        git_blob=operations.git_blob,
        materialize_checkout=materialize,
        now_utc=operations.now_utc,
        python_version=operations.python_version,
        platform_identity=operations.platform_identity,
    )
    with pytest.raises(gate.GatePolicyError, match="candidate"):
        gate.run_registered_gate(
            gate_id="gate-self-test",
            command_name="self-test",
            candidate=candidate,
            registry=gate.default_registry(),
            operations=checked_operations,
            workspace=workspace,
        )
    assert materialized == 3


def test_exact_checkout_rejects_gitlinks(tmp_path: Path) -> None:
    gate = _load_gate()
    root = tmp_path / "source"
    destination = tmp_path / "snapshot"
    root.mkdir()
    destination.mkdir()
    (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "gate@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", f"160000,{base},vendor/submodule"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "gitlink"], cwd=root, check=True)
    candidate_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with pytest.raises(gate.GatePolicyError, match="gitlink"):
        gate._system_materialize_checkout(root, candidate_commit, destination)


def test_exact_checkout_and_gate_command_ignore_ambient_git_routing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = _load_gate()
    root = tmp_path / "source"
    destination = tmp_path / "snapshot"
    root.mkdir()
    destination.mkdir()
    (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "gate@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    candidate_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    hostile = {
        "GIT_DIR": str(tmp_path / "external-git-dir"),
        "GIT_INDEX_FILE": str(tmp_path / "external-index"),
        "GIT_WORK_TREE": str(tmp_path / "external-worktree"),
        "GIT_OBJECT_DIRECTORY": str(tmp_path / "external-objects"),
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(tmp_path / "alternate-objects"),
    }
    with monkeypatch.context() as polluted:
        for name, value in hostile.items():
            polluted.setenv(name, value)
        gate._system_materialize_checkout(root, candidate_commit, destination)
        command = gate._system_run(
            (
                sys.executable,
                "-c",
                "import os,sys;sys.exit(any(k in os.environ for k in "
                f"{tuple(hostile)!r}))",
            ),
            destination,
            30,
        )

    assert command.returncode == 0
    assert (destination / ".git" / "index").is_file()
    assert all(not Path(value).exists() for value in hostile.values())
    status = subprocess.run(
        ["git", "-C", str(destination), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status == ""
    assert "--no-lazy-fetch" in gate._git_command("status")
    assert gate._scrubbed_git_environment()["GIT_NO_LAZY_FETCH"] == "1"


def test_git_queries_bind_to_requested_root_despite_local_core_worktree(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    root = tmp_path / "source"
    routed = tmp_path / "configured-worktree"
    root.mkdir()
    routed.mkdir()
    (root / "tracked.txt").write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "gate@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    (routed / "tracked.txt").write_text("committed\n", encoding="utf-8")
    subprocess.run(
        ["git", "config", "core.worktree", str(routed)],
        cwd=root,
        check=True,
    )
    (root / "tracked.txt").write_text("dirty source\n", encoding="utf-8")

    porcelain = gate._system_git(
        root,
        ("status", "--porcelain=v1", "--untracked-files=all", "--", "."),
    )

    assert porcelain == " M tracked.txt"


def test_untracked_scan_ignores_repo_and_user_excludes_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = _load_gate()
    root = tmp_path / "source"
    root.mkdir()
    (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "gate@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    repository_excludes = tmp_path / "repository-excludes"
    repository_excludes.write_text("hidden-by-repo.txt\n", encoding="utf-8")
    subprocess.run(
        ["git", "config", "core.excludesFile", str(repository_excludes)],
        cwd=root,
        check=True,
    )
    xdg_root = tmp_path / "xdg"
    (xdg_root / "git").mkdir(parents=True)
    (xdg_root / "git" / "ignore").write_text(
        "hidden-by-user.txt\n",
        encoding="utf-8",
    )
    (root / "hidden-by-repo.txt").write_text("untracked\n", encoding="utf-8")
    (root / "hidden-by-user.txt").write_text("untracked\n", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_root))

    untracked = gate._system_git(root, gate._untracked_argv("backend"))

    assert set(untracked.rstrip("\0").split("\0")) == {
        "hidden-by-repo.txt",
        "hidden-by-user.txt",
    }
    command = gate._git_command("status")
    assert "core.ignoreCase=false" in command
    assert "core.precomposeUnicode=false" in command


def test_raw_tracked_projection_rejects_core_symlinks_type_emulation(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    root = tmp_path / "source"
    root.mkdir()
    (root / "target.txt").write_text("target\n", encoding="utf-8")
    (root / "tracked-link").symlink_to("target.txt")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "gate@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    subprocess.run(["git", "config", "core.symlinks", "false"], cwd=root, check=True)
    (root / "tracked-link").unlink()
    (root / "tracked-link").write_text("target.txt", encoding="utf-8")
    ordinary_status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert ordinary_status == ""
    raw_index = gate._system_git(root, ("ls-files", "--stage", "-z", "--"))

    with pytest.raises(gate.GatePolicyError, match="tracked worktree type"):
        gate._raw_tracked_worktree_identity(root, raw_index)


def test_raw_tracked_projection_rejects_a_symlinked_parent_directory(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    root = tmp_path / "source"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (nested / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "gate@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    shadow = root / ".shadow"
    nested.rename(shadow)
    nested.symlink_to(".shadow", target_is_directory=True)
    (root / ".git" / "info" / "exclude").write_text(
        ".shadow/\n",
        encoding="utf-8",
    )
    raw_index = gate._system_git(root, ("ls-files", "--stage", "-z", "--"))

    with pytest.raises(gate.GatePolicyError, match="parent type"):
        gate._raw_tracked_worktree_identity(root, raw_index)


def test_raw_tracked_projection_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    gate = _load_gate()
    root = tmp_path / "source"
    root.mkdir()
    tracked = root / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "gate@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    raw_index = gate._system_git(root, ("ls-files", "--stage", "-z", "--"))
    tracked.unlink()
    os.mkfifo(tracked)

    with pytest.raises(gate.GatePolicyError, match="tracked worktree type"):
        gate._raw_tracked_worktree_identity(root, raw_index)


def test_raw_tracked_projection_rejects_clean_filter_normalization(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    root = tmp_path / "source"
    root.mkdir()
    tracked = root / "tracked.txt"
    tracked.write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "gate@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    (root / ".git" / "info" / "attributes").write_text(
        "tracked.txt filter=normalize\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "config", "filter.normalize.clean", "sed s/dirty/committed/"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "filter.normalize.required", "true"],
        cwd=root,
        check=True,
    )
    tracked.write_text("dirty\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
    ordinary_status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert ordinary_status == ""
    raw_index = gate._system_git(root, ("ls-files", "--stage", "-z", "--"))

    with pytest.raises(gate.GatePolicyError, match="tracked worktree bytes"):
        gate._raw_tracked_worktree_identity(root, raw_index)


def test_python_matrix_output_is_external_and_invalidated_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = _load_gate()
    stale_output = tmp_path / "matrix.json"
    stale_output.write_text('{"status":"PASS","stale":true}\n', encoding="utf-8")
    args = gate.build_parser().parse_args(
        ["python-hermetic", "--output", str(stale_output)]
    )

    def fail_before_result(**_: Any) -> dict[str, Any]:
        raise RuntimeError("matrix did not start")

    monkeypatch.setattr(gate, "run_python_matrix", fail_before_result)
    with pytest.raises(RuntimeError, match="did not start"):
        gate._execute_python_matrix(args)

    assert not stale_output.exists()


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

    for cwd in (
        "/tmp",
        "../frontend",
        "nested/../../escape",
        "nested\\windows",
        "nested//double",
        "./nested",
        "x" * 241,
    ):
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
    with pytest.raises(gate.GatePolicyError, match="input path"):
        gate.GateSpec(
            gate_id="portable-test",
            repository="frontend",
            cwd=".",
            argv=("node", "--version"),
            artifact_paths=("../package-lock.json",),
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
        if name == "frontend":
            (root / "package.json").write_text(
                json.dumps({"name": "stoa-frontend"}) + "\n",
                encoding="utf-8",
            )
        else:
            (root / "pyproject.toml").write_text(
                f'[project]\nname = "stoa-{name}"\n',
                encoding="utf-8",
            )
        roots[name] = root

    workspace = gate.WorkspaceRoots.from_mapping(roots)
    assert workspace.require("frontend") == roots["frontend"]
    link = tmp_path / "frontend-link"
    link.symlink_to(roots["frontend"], target_is_directory=True)
    with pytest.raises(gate.GatePolicyError, match="symlink"):
        gate.WorkspaceRoots.from_mapping({**roots, "frontend": link})

    with pytest.raises(gate.GatePolicyError, match="distinct"):
        gate.WorkspaceRoots.from_mapping({**roots, "infra": roots["backend"]})

    mobile = tmp_path / "mobile"
    mobile.mkdir()
    (mobile / "package-lock.json").write_text("lock\n", encoding="utf-8")
    (mobile / "package.json").write_text(
        json.dumps({"name": "@stoa/mobile"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(gate.GatePolicyError, match="identity"):
        gate.WorkspaceRoots.from_mapping({**roots, "frontend": mobile})

    spec = gate.GateSpec(
        gate_id="portable-test",
        repository="frontend",
        cwd=".",
        argv=("node", "--version"),
        artifact_paths=("package-lock.json",),
        config_paths=("package.json",),
    )
    moments = iter(["2026-07-19T00:00:00Z", "2026-07-19T00:00:01Z"])

    def run_process(argv: tuple[str, ...], cwd: Path, timeout: int) -> Any:
        assert argv == ("node", "--version")
        assert cwd == roots["frontend"]
        assert timeout == 120
        return gate.ProcessResult(returncode=0, stdout=b"v20.20.2\n", stderr=b"")

    operations = gate.GateOperations(
        run_process=run_process,
        git=lambda root, argv: "",
        now_utc=lambda: next(moments),
        python_version=lambda: "3.12.13",
        platform_identity=lambda: "linux-aarch64",
    )
    candidate = gate.load_candidate(CANDIDATE_PATH)
    registry = gate.GateRegistry((spec,))
    receipt = gate._run_registered_gate_on_snapshot(
        gate_id="portable-test",
        command_name="verify",
        candidate=candidate,
        registry=registry,
        operations=operations,
        workspace=workspace,
    )
    gate.validate_receipt(
        receipt,
        candidate=candidate,
        registry=registry,
        workspace=workspace,
    )
    assert receipt["command"]["repository"] == "frontend"
    assert receipt["command"]["cwd"] == "."
    assert receipt["inputs"]["artifacts"][0]["repository"] == "frontend"
    encoded = json.dumps(receipt, sort_keys=True)
    assert str(tmp_path) not in encoded

    symlink_input = roots["frontend"] / "linked-package.json"
    symlink_input.symlink_to(roots["frontend"] / "package.json")
    symlink_spec = gate.GateSpec(
        gate_id="symlink-test",
        repository="frontend",
        cwd=".",
        argv=("node", "--version"),
        artifact_paths=("package-lock.json",),
        config_paths=("linked-package.json",),
    )
    with pytest.raises(gate.GatePolicyError, match="regular file"):
        gate._run_registered_gate_on_snapshot(
            gate_id="symlink-test",
            command_name="verify",
            candidate=candidate,
            registry=gate.GateRegistry((symlink_spec,)),
            operations=operations,
            workspace=workspace,
        )
