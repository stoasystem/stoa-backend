#!/usr/bin/env python3
"""Run STOA release obligations through one closed local and CI authority."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "evidence/phase-474/candidate-identity.json"
SCHEMA_PATH = ROOT / "schemas/release/gate-receipt-v1.schema.json"
RECEIPT_SCHEMA = "stoa.release.gate-receipt.v1"
POLICY_EXIT = 2
EXECUTION_EXIT = 3
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$")
PYTHON_MATRIX_SCHEMA = "stoa.phase474.python-matrix.v1"
PYTHON_MATRIX_CLOCKS = (
    "2026-07-01T12:00:00Z",
    "2035-01-15T12:00:00Z",
)
PYTHON_MATRIX_SEED = 4740718
PYTHON_SUITE_ARGV = (
    "python",
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:socket",
)
_PYTHON_MATRIX_SOURCE_FILES = ("pyproject.toml", "uv.lock", "requirements.txt")
_PYTEST_MANIFEST_KEYS = {
    "schema_version",
    "clock",
    "seed",
    "runtime",
    "lock_sha256",
    "collection_sha256",
    "nodes",
    "counts",
}
_PYTEST_COUNT_KEYS = {"total", "passed", "failed", "error", "skipped", "xfail", "xpass"}
_PYTHON_MATRIX_KEYS = {
    "schema",
    "seed",
    "clocks",
    "source",
    "suite_argv",
    "status",
    "reason_code",
    "runs",
}
_PYTHON_MATRIX_RUN_KEYS = {
    "run",
    "environment",
    "clock",
    "seed",
    "runtime",
    "lock_sha256",
    "collection_sha256",
    "counts",
}

_CANDIDATE_KEYS = {
    "schema",
    "status",
    "identity_source",
    "execution_identity",
    "repositories",
    "candidate_issued",
    "mutation_count",
    "repository_mutation",
    "production_infrastructure",
    "production_deploy",
    "production_smoke",
    "production_rollback",
}
_REPOSITORY_KEYS = {
    "name",
    "head",
    "tree",
    "lock_path",
    "lock_sha256",
    "porcelain_sha256",
    "clean",
}
_REPOSITORY_CONTRACTS = (
    ("backend", "uv.lock"),
    ("frontend", "package-lock.json"),
    ("infra", "uv.lock"),
)
_REPOSITORY_NAMES = tuple(name for name, _ in _REPOSITORY_CONTRACTS)
_LOCK_PATHS = dict(_REPOSITORY_CONTRACTS)
_REPOSITORY_MARKERS = {
    "backend": ("pyproject.toml", "stoa-backend"),
    "frontend": ("package.json", "stoa-frontend"),
    "infra": ("pyproject.toml", "stoa-infra"),
}
_RECEIPT_KEYS = {
    "schema",
    "gate_id",
    "source",
    "command",
    "runtime",
    "inputs",
    "result",
    "gate_evidence",
    "privacy",
    "started_at",
    "ended_at",
    "receipt_sha256",
}
_COUNT_KEYS = {"total", "passed", "failed", "errors", "skipped", "xfail", "xpass"}
_IDENTITY_KEYS = {"repository", "path", "bytes", "sha256"}


class GatePolicyError(ValueError):
    """A stable, redacted rejection of untrusted release evidence."""

    def __init__(self, message: str, *, result: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class GateSpec:
    gate_id: str
    argv: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    config_paths: tuple[str, ...]
    repository: str = "backend"
    cwd: str = "."
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if not self.gate_id or not self.argv:
            raise GatePolicyError("gate registration is incomplete")
        if not self.artifact_paths or not self.config_paths:
            raise GatePolicyError("gate registration lacks input identities")
        if self.repository not in _REPOSITORY_NAMES:
            raise GatePolicyError("gate repository is invalid")
        if not _is_safe_relative_path(self.cwd, allow_dot=True):
            raise GatePolicyError("gate cwd must be repository-relative")
        for path in (*self.artifact_paths, *self.config_paths):
            if not _is_safe_relative_path(path):
                raise GatePolicyError("gate input path must be repository-relative")
        if self.timeout_seconds <= 0:
            raise GatePolicyError("gate timeout must be positive")


@dataclass(frozen=True)
class GateOperations:
    run_process: Callable[[tuple[str, ...], Path, int], ProcessResult]
    git: Callable[[Path, tuple[str, ...]], str]
    now_utc: Callable[[], str]
    python_version: Callable[[], str]
    platform_identity: Callable[[], str]


@dataclass(frozen=True)
class PythonMatrixOperations:
    run_process: Callable[[tuple[str, ...], dict[str, str], Path, int], ProcessResult]
    network_boundary: Callable[[], tuple[str, ...] | None]


@dataclass(frozen=True)
class WorkspaceRoots:
    """Execution-only repository roots; canonical receipts contain no host paths."""

    roots: tuple[tuple[str, Path], ...]

    @classmethod
    def from_mapping(cls, roots: Mapping[str, Path]) -> WorkspaceRoots:
        if set(roots) != set(_REPOSITORY_NAMES):
            raise GatePolicyError("workspace repository roots are incomplete")
        resolved_roots: list[tuple[str, Path]] = []
        for name in _REPOSITORY_NAMES:
            supplied = Path(roots[name])
            if supplied.is_symlink():
                raise GatePolicyError("workspace repository root is a symlink")
            try:
                resolved = supplied.resolve(strict=True)
            except OSError as exc:
                raise GatePolicyError("workspace repository root is unavailable") from exc
            if not resolved.is_dir():
                raise GatePolicyError("workspace repository root is not a directory")
            resolved_roots.append((name, resolved))
        if len({root for _, root in resolved_roots}) != len(resolved_roots):
            raise GatePolicyError("workspace repository roots must be distinct")

        validated: list[tuple[str, Path]] = []
        for name, resolved in resolved_roots:
            lock = resolved / _LOCK_PATHS[name]
            if lock.is_symlink() or not lock.is_file():
                raise GatePolicyError("workspace repository lock is unavailable")
            marker_path, expected_project = _REPOSITORY_MARKERS[name]
            marker = resolved / marker_path
            if marker.is_symlink() or not marker.is_file():
                raise GatePolicyError("workspace repository identity is unavailable")
            try:
                if marker_path == "package.json":
                    marker_value = json.loads(marker.read_text(encoding="utf-8")).get("name")
                else:
                    marker_value = tomllib.loads(marker.read_text(encoding="utf-8")).get(
                        "project", {}
                    ).get("name")
            except (OSError, UnicodeError, json.JSONDecodeError, tomllib.TOMLDecodeError, AttributeError):
                raise GatePolicyError("workspace repository identity is invalid") from None
            if marker_value != expected_project:
                raise GatePolicyError("workspace repository identity is invalid")
            validated.append((name, resolved))
        return cls(tuple(validated))

    def require(self, repository: str) -> Path:
        for name, root in self.roots:
            if name == repository:
                return root
        raise GatePolicyError("unknown workspace repository")


def _is_safe_relative_path(value: str, *, allow_dot: bool = False) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 240
        or "\\" in value
        or "\x00" in value
        or "\n" in value
        or "\r" in value
    ):
        return False
    if value == ".":
        return allow_dot
    parts = value.split("/")
    if value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        return False
    return True


def default_workspace_roots() -> WorkspaceRoots:
    parent = ROOT.parent
    return WorkspaceRoots.from_mapping(
        {
            "backend": ROOT,
            "frontend": parent / "stoa-frontend",
            "infra": parent / "stoa-infra",
        }
    )


class GateRegistry:
    """Typed registrations are the only executable command graph."""

    def __init__(self, specs: Iterable[GateSpec]) -> None:
        registered: dict[str, GateSpec] = {}
        for spec in specs:
            if spec.gate_id in registered:
                raise GatePolicyError(f"duplicate gate id: {spec.gate_id}")
            registered[spec.gate_id] = spec
        if not registered:
            raise GatePolicyError("gate registry is empty")
        self._specs = registered

    def require(self, gate_id: str) -> GateSpec:
        try:
            return self._specs[gate_id]
        except KeyError as exc:
            raise GatePolicyError(f"unknown gate id: {gate_id}") from exc


def default_registry() -> GateRegistry:
    """Return the initial closed registry; later plans add reviewed capabilities here."""
    return GateRegistry(
        (
            GateSpec(
                gate_id="gate-self-test",
                argv=("{python}", "-c", "raise SystemExit(0)"),
                artifact_paths=("evidence/phase-474/candidate-identity.json",),
                config_paths=("schemas/release/gate-receipt-v1.schema.json",),
            ),
            GateSpec(
                gate_id="backend-python-hermetic",
                argv=("{python}", "scripts/release_gate.py", "python-hermetic"),
                artifact_paths=_PYTHON_MATRIX_SOURCE_FILES,
                config_paths=("scripts/phase474_pytest_guard.py", "tests/conftest.py"),
                timeout_seconds=7200,
            ),
        )
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    stable = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    return sha256(_canonical_bytes(stable)).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise GatePolicyError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except GatePolicyError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GatePolicyError("JSON input is unavailable or malformed") from exc
    if not isinstance(value, dict):
        raise GatePolicyError("JSON input must be an object")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise GatePolicyError(f"{label} fields are not closed")


def _require_sha(value: Any, label: str, *, git: bool = False) -> str:
    pattern = GIT_SHA_RE if git else SHA256_RE
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise GatePolicyError(f"{label} is malformed")
    return value


def _canonical_candidate_repositories(repositories: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ordered_keys = (
        "name",
        "head",
        "tree",
        "lock_path",
        "lock_sha256",
        "porcelain_sha256",
        "clean",
    )
    return [{key: repository[key] for key in ordered_keys} for repository in repositories]


def validate_candidate(candidate: Mapping[str, Any]) -> None:
    _require_exact_keys(candidate, _CANDIDATE_KEYS, "candidate")
    expected_literals = {
        "schema": "stoa.release.candidate-identity.v1",
        "status": "CLEAN",
        "identity_source": "execution-time-live-repository-state",
        "candidate_issued": True,
        "mutation_count": 0,
        "repository_mutation": "NOT RUN",
        "production_infrastructure": "NOT RUN",
        "production_deploy": "NOT RUN",
        "production_smoke": "NOT RUN",
        "production_rollback": "NOT RUN",
    }
    for key, expected in expected_literals.items():
        if candidate.get(key) != expected:
            raise GatePolicyError(f"candidate {key} is invalid")

    repositories = candidate.get("repositories")
    if not isinstance(repositories, list) or len(repositories) != len(_REPOSITORY_CONTRACTS):
        raise GatePolicyError("candidate repositories are incomplete")
    for repository, (name, lock_path) in zip(
        repositories, _REPOSITORY_CONTRACTS, strict=True
    ):
        if not isinstance(repository, dict):
            raise GatePolicyError(f"{name} repository identity is malformed")
        _require_exact_keys(repository, _REPOSITORY_KEYS, f"{name} repository identity")
        if (
            repository.get("name") != name
            or repository.get("lock_path") != lock_path
            or repository.get("clean") is not True
        ):
            raise GatePolicyError(f"{name} repository identity is invalid")
        _require_sha(repository.get("head"), f"{name} head", git=True)
        _require_sha(repository.get("tree"), f"{name} tree", git=True)
        _require_sha(repository.get("lock_sha256"), f"{name} lock digest")
        _require_sha(repository.get("porcelain_sha256"), f"{name} porcelain digest")

    expected_identity = sha256(
        json.dumps(
            _canonical_candidate_repositories(repositories),
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if candidate.get("execution_identity") != expected_identity:
        raise GatePolicyError("candidate execution identity mismatch")


def load_candidate(path: Path) -> dict[str, Any]:
    candidate = load_json(path)
    validate_candidate(candidate)
    return candidate


def _root_path(root: Path, relative_path: str) -> Path:
    if not _is_safe_relative_path(relative_path):
        raise GatePolicyError("input path must be repository-relative")
    unresolved = root / relative_path
    current = root
    for part in Path(relative_path).parts:
        current /= part
        if current.is_symlink():
            raise GatePolicyError("input path is not a regular file")
    candidate = unresolved.resolve()
    if candidate != root and root not in candidate.parents:
        raise GatePolicyError("input path escapes the repository")
    if not candidate.is_file():
        raise GatePolicyError("input path is not a regular file")
    return candidate


def _file_identity(
    workspace: WorkspaceRoots,
    repository: str,
    relative_path: str,
) -> dict[str, Any]:
    path = _root_path(workspace.require(repository), relative_path)
    content = path.read_bytes()
    return {
        "repository": repository,
        "path": relative_path,
        "bytes": len(content),
        "sha256": sha256(content).hexdigest(),
    }


def _source(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_identity": candidate["execution_identity"],
        "repositories": candidate["repositories"],
    }


def _matrix_source_identity(root: Path) -> dict[str, dict[str, Any]]:
    identities: dict[str, dict[str, Any]] = {}
    for relative_path in _PYTHON_MATRIX_SOURCE_FILES:
        path = root / relative_path
        if path.is_symlink() or not path.is_file():
            raise GatePolicyError("Python matrix source input is unavailable")
        content = path.read_bytes()
        identities[relative_path] = {
            "bytes": len(content),
            "sha256": sha256(content).hexdigest(),
        }
    return identities


def _matrix_hermetic_environment(
    source: Mapping[str, str], *, nonexistent_root: Path
) -> dict[str, str]:
    environment = dict(source)
    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "NO_PROXY",
        "no_proxy",
    ):
        environment.pop(name, None)
    environment["AWS_EC2_METADATA_DISABLED"] = "true"
    environment["AWS_SHARED_CREDENTIALS_FILE"] = str(nonexistent_root / "credentials")
    environment["AWS_CONFIG_FILE"] = str(nonexistent_root / "config")
    return environment


def _validate_pytest_manifest(
    manifest: Mapping[str, Any], *, clock: str, lock_sha256: str
) -> dict[str, Any]:
    _require_exact_keys(manifest, _PYTEST_MANIFEST_KEYS, "pytest manifest")
    if manifest.get("schema_version") != "stoa.phase474.pytest-nodes.v1":
        raise GatePolicyError("pytest manifest schema is invalid")
    if manifest.get("clock") != clock or manifest.get("seed") != PYTHON_MATRIX_SEED:
        raise GatePolicyError("pytest clock or seed identity mismatch")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, str) or re.fullmatch(r"3\.12\.[0-9]+", runtime) is None:
        raise GatePolicyError("pytest runtime is not Python 3.12")
    if manifest.get("lock_sha256") != lock_sha256:
        raise GatePolicyError("pytest lock identity mismatch")
    _require_sha(manifest.get("collection_sha256"), "pytest collection digest")

    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        raise GatePolicyError("pytest outcome counts are malformed")
    _require_exact_keys(counts, _PYTEST_COUNT_KEYS, "pytest outcome counts")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts.values()):
        raise GatePolicyError("pytest outcome count is invalid")
    if counts["total"] != sum(counts[name] for name in _PYTEST_COUNT_KEYS if name != "total"):
        raise GatePolicyError("pytest outcome counts do not total")
    if counts["total"] < 1 or counts["passed"] != counts["total"]:
        raise GatePolicyError("pytest run contains a non-pass outcome")

    nodes = manifest.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != counts["total"]:
        raise GatePolicyError("pytest node evidence is incomplete")
    node_ids: list[str] = []
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"node_id", "outcome", "phases"}:
            raise GatePolicyError("pytest node evidence is malformed")
        node_id = node.get("node_id")
        if not isinstance(node_id, str) or not node_id or node.get("outcome") != "passed":
            raise GatePolicyError("pytest node evidence is not passing")
        if not isinstance(node.get("phases"), list):
            raise GatePolicyError("pytest node phases are malformed")
        node_ids.append(node_id)
    if node_ids != sorted(node_ids) or len(set(node_ids)) != len(node_ids):
        raise GatePolicyError("pytest node ordering is invalid")

    return {
        "clock": clock,
        "seed": PYTHON_MATRIX_SEED,
        "runtime": runtime,
        "lock_sha256": lock_sha256,
        "collection_sha256": manifest["collection_sha256"],
        "counts": dict(counts),
    }


def _load_python_matrix_output(stdout: bytes) -> dict[str, Any]:
    try:
        text = stdout.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except GatePolicyError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GatePolicyError("Python matrix output is malformed") from exc
    if not isinstance(value, dict):
        raise GatePolicyError("Python matrix output must be an object")
    return value


def _validate_registered_python_run(
    value: Any,
    *,
    index: int,
    clock: str,
    lock_sha256: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GatePolicyError("Python matrix run is malformed")
    _require_exact_keys(value, _PYTHON_MATRIX_RUN_KEYS, "Python matrix run")
    if value.get("run") != index or value.get("environment") != f"fresh-{index}":
        raise GatePolicyError("Python matrix fresh environment identity is invalid")
    if value.get("clock") != clock or value.get("seed") != PYTHON_MATRIX_SEED:
        raise GatePolicyError("Python matrix clock or seed identity is invalid")
    runtime = value.get("runtime")
    if not isinstance(runtime, str) or re.fullmatch(r"3\.12\.[0-9]+", runtime) is None:
        raise GatePolicyError("Python matrix runtime is invalid")
    if value.get("lock_sha256") != lock_sha256:
        raise GatePolicyError("Python matrix lock identity is invalid")
    _require_sha(value.get("collection_sha256"), "Python matrix collection digest")

    counts = value.get("counts")
    if not isinstance(counts, dict):
        raise GatePolicyError("Python matrix counts are malformed")
    _require_exact_keys(counts, _PYTEST_COUNT_KEYS, "Python matrix counts")
    if any(
        not isinstance(item, int) or isinstance(item, bool) or item < 0
        for item in counts.values()
    ):
        raise GatePolicyError("Python matrix count is invalid")
    if counts["total"] != sum(
        counts[name] for name in _PYTEST_COUNT_KEYS if name != "total"
    ):
        raise GatePolicyError("Python matrix counts do not total")
    if counts["total"] < 1 or counts["passed"] != counts["total"]:
        raise GatePolicyError("Python matrix run is not complete-pass")
    return value


def _validate_registered_python_matrix(matrix: Mapping[str, Any], *, root: Path = ROOT) -> None:
    status = matrix.get("status")
    expected_keys = set(_PYTHON_MATRIX_KEYS)
    if status == "REJECTED":
        expected_keys.add("diagnostic")
    _require_exact_keys(matrix, expected_keys, "Python matrix")
    if matrix.get("schema") != PYTHON_MATRIX_SCHEMA:
        raise GatePolicyError("Python matrix schema is invalid")
    if matrix.get("seed") != PYTHON_MATRIX_SEED:
        raise GatePolicyError("Python matrix seed is invalid")
    if matrix.get("clocks") != list(PYTHON_MATRIX_CLOCKS):
        raise GatePolicyError("Python matrix clocks are invalid")
    if matrix.get("suite_argv") != list(PYTHON_SUITE_ARGV):
        raise GatePolicyError("Python matrix suite command is invalid")
    if matrix.get("source") != _matrix_source_identity(root):
        raise GatePolicyError("Python matrix source identity is invalid")

    runs = matrix.get("runs")
    if status == "NOT RUN":
        if (
            matrix.get("reason_code") != "OS_NETWORK_BOUNDARY_UNAVAILABLE"
            or runs != []
        ):
            raise GatePolicyError("Python matrix NOT RUN evidence is invalid")
        return
    if status not in {"PASS", "REJECTED"}:
        raise GatePolicyError("Python matrix status is invalid")
    expected_reason = None if status == "PASS" else "COLLECTION_IDENTITY_DRIFT"
    if matrix.get("reason_code") != expected_reason:
        raise GatePolicyError("Python matrix reason is invalid")
    if not isinstance(runs, list) or len(runs) != len(PYTHON_MATRIX_CLOCKS):
        raise GatePolicyError("Python matrix requires exactly two runs")

    lock_sha256 = matrix["source"]["uv.lock"]["sha256"]
    validated_runs = [
        _validate_registered_python_run(
            run,
            index=index,
            clock=clock,
            lock_sha256=lock_sha256,
        )
        for index, (run, clock) in enumerate(
            zip(runs, PYTHON_MATRIX_CLOCKS, strict=True),
            start=1,
        )
    ]
    if validated_runs[0]["runtime"] != validated_runs[1]["runtime"]:
        raise GatePolicyError("Python matrix runtime identity drifted")
    if validated_runs[0]["counts"] != validated_runs[1]["counts"]:
        raise GatePolicyError("Python matrix outcome counts drifted")

    first_collection = validated_runs[0]["collection_sha256"]
    second_collection = validated_runs[1]["collection_sha256"]
    if status == "PASS":
        if first_collection != second_collection:
            raise GatePolicyError("Python matrix collection identity drifted")
        return
    if first_collection == second_collection:
        raise GatePolicyError("Python matrix rejection lacks collection drift")
    expected_diagnostic = {
        "field": "collection_sha256",
        "run_1": first_collection,
        "run_2": second_collection,
    }
    if matrix.get("diagnostic") != expected_diagnostic:
        raise GatePolicyError("Python matrix rejection diagnostic is invalid")


def run_python_matrix(
    *,
    root: Path,
    environment_paths: Sequence[Path],
    operations: PythonMatrixOperations,
    source_environment: Mapping[str, str],
) -> dict[str, Any]:
    """Acquire twice, then run the complete suite twice behind network-none isolation."""
    root = root.resolve()
    if len(environment_paths) != len(PYTHON_MATRIX_CLOCKS):
        raise GatePolicyError("Python matrix requires exactly two fresh environments")
    resolved_environments = tuple(path.resolve() for path in environment_paths)
    if len(set(resolved_environments)) != len(resolved_environments):
        raise GatePolicyError("Python matrix environments must be distinct")
    for environment_path in resolved_environments:
        if environment_path.exists():
            raise GatePolicyError("Python matrix environment is not fresh")
        if environment_path == root or root in environment_path.parents:
            raise GatePolicyError("Python matrix environment must be outside the source tree")

    source_identity = _matrix_source_identity(root)
    boundary = operations.network_boundary()
    base = {
        "schema": PYTHON_MATRIX_SCHEMA,
        "seed": PYTHON_MATRIX_SEED,
        "clocks": list(PYTHON_MATRIX_CLOCKS),
        "source": source_identity,
        "suite_argv": list(PYTHON_SUITE_ARGV),
    }
    if boundary is None:
        return {
            **base,
            "status": "NOT RUN",
            "reason_code": "OS_NETWORK_BOUNDARY_UNAVAILABLE",
            "runs": [],
        }
    if not boundary or boundary[-1] != "--":
        raise GatePolicyError("OS network boundary command is malformed")

    lock_sha256 = source_identity["uv.lock"]["sha256"]
    runs: list[dict[str, Any]] = []
    for index, (environment_path, clock) in enumerate(
        zip(resolved_environments, PYTHON_MATRIX_CLOCKS, strict=True),
        start=1,
    ):
        acquisition_environment = dict(source_environment)
        acquisition_environment["UV_PROJECT_ENVIRONMENT"] = str(environment_path)
        sync = operations.run_process(
            ("uv", "sync", "--frozen", "--python", "3.12", "--extra", "dev"),
            acquisition_environment,
            root,
            1800,
        )
        if sync.returncode != 0:
            raise GatePolicyError("fresh Python environment sync failed")
        if _matrix_source_identity(root) != source_identity:
            raise GatePolicyError("source or lock drifted during Python environment sync")

        environment_python = environment_path / "bin" / "python"
        if not environment_python.is_file():
            raise GatePolicyError("fresh Python environment is incomplete")
        credential_root = environment_path / "phase474-no-credentials"
        manifest_path = environment_path / "phase474-pytest-manifest.json"
        test_environment = _matrix_hermetic_environment(
            source_environment,
            nonexistent_root=credential_root,
        )
        existing_path = test_environment.get("PATH", "")
        test_environment.update(
            {
                "PATH": str(environment_path / "bin")
                + (os.pathsep + existing_path if existing_path else ""),
                "PYTHONHASHSEED": str(PYTHON_MATRIX_SEED),
                "STOA_PHASE474_HERMETIC": "1",
                "STOA_PHASE474_CLOCK": clock,
                "STOA_PHASE474_SEED": str(PYTHON_MATRIX_SEED),
                "STOA_PHASE474_LOCK": str(root / "uv.lock"),
                "STOA_PHASE474_MANIFEST": str(manifest_path),
                "STOA_PHASE474_CREDENTIAL_ROOT": str(credential_root),
            }
        )
        completed = operations.run_process(
            (*boundary, *PYTHON_SUITE_ARGV),
            test_environment,
            root,
            1800,
        )
        if completed.returncode != 0 or not manifest_path.is_file():
            raise GatePolicyError("hermetic complete Python suite failed")
        if _matrix_source_identity(root) != source_identity:
            raise GatePolicyError("source or lock drifted during Python verification")
        manifest = load_json(manifest_path)
        evidence = _validate_pytest_manifest(
            manifest,
            clock=clock,
            lock_sha256=lock_sha256,
        )
        runs.append(
            {
                "run": index,
                "environment": f"fresh-{index}",
                **evidence,
            }
        )

    if runs[0]["collection_sha256"] != runs[1]["collection_sha256"]:
        raise GatePolicyError(
            "Python matrix collection identity drifted",
            result={
                **base,
                "status": "REJECTED",
                "reason_code": "COLLECTION_IDENTITY_DRIFT",
                "runs": runs,
                "diagnostic": {
                    "field": "collection_sha256",
                    "run_1": runs[0]["collection_sha256"],
                    "run_2": runs[1]["collection_sha256"],
                },
            },
        )
    return {
        **base,
        "status": "PASS",
        "reason_code": None,
        "runs": runs,
    }


def python_matrix_exit_code(result: Mapping[str, Any]) -> int:
    if result.get("status") == "PASS" and result.get("reason_code") is None:
        return 0
    if (
        result.get("status") == "NOT RUN"
        and result.get("reason_code") == "OS_NETWORK_BOUNDARY_UNAVAILABLE"
        and result.get("runs") == []
    ):
        return POLICY_EXIT
    if (
        result.get("status") == "REJECTED"
        and result.get("reason_code") == "COLLECTION_IDENTITY_DRIFT"
        and isinstance(result.get("runs"), list)
        and len(result["runs"]) == len(PYTHON_MATRIX_CLOCKS)
    ):
        return POLICY_EXIT
    return EXECUTION_EXIT


def _counts(*, passed: int = 0, failed: int = 0, errors: int = 0) -> dict[str, int]:
    return {
        "total": passed + failed + errors,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": 0,
        "xfail": 0,
        "xpass": 0,
    }


def _system_run(argv: tuple[str, ...], cwd: Path, timeout_seconds: int) -> ProcessResult:
    resolved_argv = (sys.executable, *argv[1:]) if argv[0] == "{python}" else argv
    completed = subprocess.run(
        list(resolved_argv),
        check=False,
        capture_output=True,
        cwd=cwd,
        timeout=timeout_seconds,
    )
    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


def _system_matrix_run(
    argv: tuple[str, ...],
    environment: dict[str, str],
    cwd: Path,
    timeout_seconds: int,
) -> ProcessResult:
    completed = subprocess.run(
        list(argv),
        check=False,
        capture_output=True,
        cwd=cwd,
        env=environment,
        timeout=timeout_seconds,
    )
    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


def _probe_boundary(argv: tuple[str, ...]) -> bool:
    try:
        completed = subprocess.run(
            [*argv, "true"],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def detect_network_boundary() -> tuple[str, ...] | None:
    """Return a proved Linux network-none wrapper or exact local unavailability."""
    if platform.system() != "Linux":
        return None
    if shutil.which("bwrap"):
        bubblewrap = (
            "bwrap",
            "--unshare-net",
            "--die-with-parent",
            "--ro-bind",
            "/",
            "/",
            "--dev-bind",
            "/dev",
            "/dev",
            "--proc",
            "/proc",
            "--",
        )
        if _probe_boundary(bubblewrap):
            return bubblewrap
    if shutil.which("unshare"):
        unshare = ("unshare", "--user", "--map-root-user", "--net", "--")
        if _probe_boundary(unshare):
            return unshare
    return None


def system_python_matrix_operations() -> PythonMatrixOperations:
    return PythonMatrixOperations(
        run_process=_system_matrix_run,
        network_boundary=detect_network_boundary,
    )


def _system_git(root: Path, argv: tuple[str, ...]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *argv],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def system_operations() -> GateOperations:
    return GateOperations(
        run_process=_system_run,
        git=_system_git,
        now_utc=_now_utc,
        python_version=platform.python_version,
        platform_identity=lambda: f"{platform.system().lower()}-{platform.machine().lower()}",
    )


def run_registered_gate(
    *,
    gate_id: str,
    command_name: str,
    candidate: Mapping[str, Any],
    registry: GateRegistry,
    operations: GateOperations,
    workspace: WorkspaceRoots | None = None,
) -> dict[str, Any]:
    validate_candidate(candidate)
    if command_name not in {"verify", "self-test"}:
        raise GatePolicyError("unknown command name")
    spec = registry.require(gate_id)
    resolved_workspace = workspace or default_workspace_roots()
    repository_root = resolved_workspace.require(spec.repository)
    unresolved_cwd = repository_root / spec.cwd
    current_cwd = repository_root
    for part in Path(spec.cwd).parts:
        current_cwd /= part
        if current_cwd.is_symlink():
            raise GatePolicyError("gate cwd is not a directory")
    command_cwd = unresolved_cwd.resolve()
    if (
        command_cwd != repository_root
        and repository_root not in command_cwd.parents
    ) or not command_cwd.is_dir():
        raise GatePolicyError("gate cwd is not a directory")
    inputs = {
        "artifacts": [
            _file_identity(resolved_workspace, spec.repository, path)
            for path in spec.artifact_paths
        ],
        "configs": [
            _file_identity(resolved_workspace, spec.repository, path)
            for path in spec.config_paths
        ],
    }
    started_at = operations.now_utc()
    stdout = b""
    stderr = b""
    gate_evidence: dict[str, Any] | None = None
    try:
        for repository in candidate["repositories"]:
            operations.git(
                resolved_workspace.require(repository["name"]),
                ("cat-file", "-e", f"{repository['head']}^{{commit}}"),
            )
        completed = operations.run_process(spec.argv, command_cwd, spec.timeout_seconds)
        stdout = completed.stdout
        stderr = completed.stderr
        if gate_id == "backend-python-hermetic":
            try:
                matrix = _load_python_matrix_output(stdout)
                _validate_registered_python_matrix(matrix, root=repository_root)
                valid_exit_status = (completed.returncode, matrix["status"]) in {
                    (0, "PASS"),
                    (POLICY_EXIT, "NOT RUN"),
                    (POLICY_EXIT, "REJECTED"),
                }
                if not valid_exit_status:
                    raise GatePolicyError("Python matrix exit and status disagree")
            except GatePolicyError:
                result = {
                    "status": "FAIL",
                    "classification": "POLICY_REJECTION",
                    "exit_code": POLICY_EXIT,
                    "reason_code": "GATE_EVIDENCE_INVALID",
                    "outcomes": _counts(failed=1),
                }
            else:
                gate_evidence = matrix
                if matrix["status"] == "PASS":
                    passed = matrix["runs"][0]["counts"]["passed"]
                    result = {
                        "status": "PASS",
                        "classification": "COMPLETE_PASS",
                        "exit_code": 0,
                        "reason_code": None,
                        "outcomes": _counts(passed=passed),
                    }
                elif matrix["status"] == "NOT RUN":
                    result = {
                        "status": "NOT RUN",
                        "classification": "NOT_RUN_OBLIGATION",
                        "exit_code": POLICY_EXIT,
                        "reason_code": "EXTERNAL_CHECK_UNAVAILABLE",
                        "outcomes": _counts(),
                    }
                else:
                    result = {
                        "status": "FAIL",
                        "classification": "POLICY_REJECTION",
                        "exit_code": POLICY_EXIT,
                        "reason_code": "COLLECTION_IDENTITY_DRIFT",
                        "outcomes": _counts(failed=1),
                    }
        elif completed.returncode == 0:
            result = {
                "status": "PASS",
                "classification": "COMPLETE_PASS",
                "exit_code": 0,
                "reason_code": None,
                "outcomes": _counts(passed=1),
            }
        else:
            result = {
                "status": "FAIL",
                "classification": "POLICY_REJECTION",
                "exit_code": POLICY_EXIT,
                "reason_code": "GATE_COMMAND_FAILED",
                "outcomes": _counts(failed=1),
            }
    except Exception:
        result = {
            "status": "FAIL",
            "classification": "EXECUTION_FAILURE",
            "exit_code": EXECUTION_EXIT,
            "reason_code": "GATE_EXECUTION_ERROR",
            "outcomes": _counts(errors=1),
        }
    result["stdout_sha256"] = sha256(stdout).hexdigest()
    result["stderr_sha256"] = sha256(stderr).hexdigest()
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "gate_id": gate_id,
        "source": _source(candidate),
        "command": {
            "name": command_name,
            "repository": spec.repository,
            "cwd": spec.cwd,
            "argv": list(spec.argv),
        },
        "runtime": {
            "python": operations.python_version(),
            "platform": operations.platform_identity(),
            "clock": started_at,
        },
        "inputs": inputs,
        "result": result,
        "gate_evidence": gate_evidence,
        "privacy": {
            "passed": True,
            "scanned_field_count": len(_RECEIPT_KEYS),
            "match_count": 0,
            "environment_values_serialized": False,
            "secret_values_serialized": False,
        },
        "started_at": started_at,
        "ended_at": operations.now_utc(),
    }
    receipt["receipt_sha256"] = canonical_receipt_sha256(receipt)
    return receipt


def _validate_identity(value: Any, expected: dict[str, Any]) -> None:
    if not isinstance(value, dict):
        raise GatePolicyError("input identity is malformed")
    _require_exact_keys(value, _IDENTITY_KEYS, "input identity")
    if value != expected:
        raise GatePolicyError("input artifact or config identity mismatch")


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        raise GatePolicyError(f"{label} is not canonical UTC")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _validate_result(value: Any) -> None:
    if not isinstance(value, dict):
        raise GatePolicyError("result is malformed")
    expected_keys = {
        "status",
        "classification",
        "exit_code",
        "reason_code",
        "outcomes",
        "stdout_sha256",
        "stderr_sha256",
    }
    _require_exact_keys(value, expected_keys, "result")
    counts = value["outcomes"]
    if not isinstance(counts, dict):
        raise GatePolicyError("outcome counts are malformed")
    _require_exact_keys(counts, _COUNT_KEYS, "outcome counts")
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in counts.values()):
        raise GatePolicyError("outcome count is invalid")
    if counts["total"] != sum(counts[key] for key in _COUNT_KEYS if key != "total"):
        raise GatePolicyError("outcome counts do not total")
    _require_sha(value["stdout_sha256"], "stdout digest")
    _require_sha(value["stderr_sha256"], "stderr digest")

    status = value["status"]
    classification = value["classification"]
    if (status, classification, value["exit_code"], value["reason_code"]) == (
        "PASS",
        "COMPLETE_PASS",
        0,
        None,
    ):
        if counts["total"] < 1 or counts["passed"] != counts["total"]:
            raise GatePolicyError("PASS is incomplete")
        return
    if status == "FAIL" and classification == "POLICY_REJECTION" and value["exit_code"] == POLICY_EXIT:
        if not isinstance(value["reason_code"], str) or counts["failed"] < 1:
            raise GatePolicyError("policy rejection is incomplete")
        return
    if status == "FAIL" and classification == "EXECUTION_FAILURE" and value["exit_code"] == EXECUTION_EXIT:
        if not isinstance(value["reason_code"], str) or counts["errors"] < 1:
            raise GatePolicyError("execution failure is incomplete")
        return
    if (
        status == "NOT RUN"
        and classification == "NOT_RUN_OBLIGATION"
        and value["exit_code"] == POLICY_EXIT
        and value["reason_code"]
        in {"EXTERNAL_CHECK_UNAVAILABLE", "PRODUCTION_OPERATION_NOT_AUTHORIZED"}
        and all(count == 0 for count in counts.values())
    ):
        return
    raise GatePolicyError("result classification is invalid")


def validate_receipt(
    receipt: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    registry: GateRegistry,
    workspace: WorkspaceRoots | None = None,
) -> None:
    validate_candidate(candidate)
    resolved_workspace = workspace or default_workspace_roots()
    _require_exact_keys(receipt, _RECEIPT_KEYS, "receipt")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise GatePolicyError("receipt schema is invalid")
    spec = registry.require(str(receipt.get("gate_id")))
    if receipt.get("source") != _source(candidate):
        raise GatePolicyError("receipt source identity mismatch")
    command = receipt.get("command")
    if not isinstance(command, dict) or set(command) != {
        "name",
        "repository",
        "cwd",
        "argv",
    }:
        raise GatePolicyError("receipt command is malformed")
    if (
        command["name"] not in {"verify", "self-test"}
        or command["repository"] != spec.repository
        or command["cwd"] != spec.cwd
        or command["argv"] != list(spec.argv)
    ):
        raise GatePolicyError("receipt command graph mismatch")

    runtime = receipt.get("runtime")
    if not isinstance(runtime, dict) or set(runtime) != {"python", "platform", "clock"}:
        raise GatePolicyError("receipt runtime is malformed")
    if not isinstance(runtime["python"], str) or re.fullmatch(r"3\.[0-9]+\.[0-9]+", runtime["python"]) is None:
        raise GatePolicyError("receipt Python runtime is invalid")
    if not isinstance(runtime["platform"], str) or not runtime["platform"]:
        raise GatePolicyError("receipt platform is invalid")
    if runtime["clock"] != receipt.get("started_at"):
        raise GatePolicyError("receipt clock identity mismatch")
    started = _parse_utc(receipt.get("started_at"), "receipt start")
    ended = _parse_utc(receipt.get("ended_at"), "receipt end")
    if ended < started:
        raise GatePolicyError("receipt time ordering is invalid")

    inputs = receipt.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != {"artifacts", "configs"}:
        raise GatePolicyError("receipt inputs are malformed")
    for label, paths in (("artifacts", spec.artifact_paths), ("configs", spec.config_paths)):
        values = inputs[label]
        if not isinstance(values, list) or len(values) != len(paths):
            raise GatePolicyError(f"receipt {label} are incomplete")
        for value, path in zip(values, paths, strict=True):
            _validate_identity(
                value,
                _file_identity(resolved_workspace, spec.repository, path),
            )

    _validate_result(receipt.get("result"))
    result = receipt["result"]
    gate_evidence = receipt.get("gate_evidence")
    if spec.gate_id == "backend-python-hermetic":
        if gate_evidence is None:
            if not (
                result["classification"] in {"POLICY_REJECTION", "EXECUTION_FAILURE"}
                and result["reason_code"]
                in {"GATE_EVIDENCE_INVALID", "GATE_EXECUTION_ERROR"}
            ):
                raise GatePolicyError("hermetic receipt lacks matrix evidence")
        else:
            if not isinstance(gate_evidence, dict):
                raise GatePolicyError("hermetic receipt matrix evidence is malformed")
            _validate_registered_python_matrix(
                gate_evidence,
                root=resolved_workspace.require(spec.repository),
            )
            expected_shape = {
                "PASS": ("COMPLETE_PASS", None),
                "NOT RUN": ("NOT_RUN_OBLIGATION", "EXTERNAL_CHECK_UNAVAILABLE"),
                "REJECTED": ("POLICY_REJECTION", "COLLECTION_IDENTITY_DRIFT"),
            }[gate_evidence["status"]]
            if (result["classification"], result["reason_code"]) != expected_shape:
                raise GatePolicyError("hermetic receipt result and matrix disagree")
            if gate_evidence["status"] == "PASS":
                passed = gate_evidence["runs"][0]["counts"]["passed"]
                if result["outcomes"] != _counts(passed=passed):
                    raise GatePolicyError("hermetic receipt outcomes mismatch")
    elif gate_evidence is not None:
        raise GatePolicyError("non-hermetic receipt has unexpected gate evidence")
    expected_privacy = {
        "passed": True,
        "scanned_field_count": len(_RECEIPT_KEYS),
        "match_count": 0,
        "environment_values_serialized": False,
        "secret_values_serialized": False,
    }
    if receipt.get("privacy") != expected_privacy:
        raise GatePolicyError("receipt privacy evidence is invalid")
    _require_sha(receipt.get("receipt_sha256"), "receipt digest")
    if receipt["receipt_sha256"] != canonical_receipt_sha256(receipt):
        raise GatePolicyError("receipt digest mismatch")


def write_json(value: object, path: Path | None) -> None:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(text)
        return
    resolved = path if path.is_absolute() else ROOT / path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(text, encoding="utf-8")


def _execute(args: argparse.Namespace, command_name: str) -> int:
    candidate = load_candidate(Path(args.candidate))
    registry = default_registry()
    workspace = WorkspaceRoots.from_mapping(
        {
            "backend": Path(args.backend_root) if args.backend_root else ROOT,
            "frontend": Path(args.frontend_root)
            if args.frontend_root
            else ROOT.parent / "stoa-frontend",
            "infra": Path(args.infra_root)
            if args.infra_root
            else ROOT.parent / "stoa-infra",
        }
    )
    gate_id = args.gate if command_name == "verify" else "gate-self-test"
    receipt = run_registered_gate(
        gate_id=gate_id,
        command_name=command_name,
        candidate=candidate,
        registry=registry,
        operations=system_operations(),
        workspace=workspace,
    )
    validate_receipt(
        receipt,
        candidate=candidate,
        registry=registry,
        workspace=workspace,
    )
    write_json(receipt, Path(args.output) if args.output else None)
    return int(receipt["result"]["exit_code"])


def _execute_python_matrix(args: argparse.Namespace) -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="stoa-phase474-python-") as temporary_root:
            parent = Path(temporary_root)
            result = run_python_matrix(
                root=ROOT,
                environment_paths=(parent / "standard", parent / "future"),
                operations=system_python_matrix_operations(),
                source_environment=os.environ,
            )
    except GatePolicyError as exc:
        if exc.result is None:
            raise
        result = exc.result
    write_json(result, Path(args.output) if args.output else None)
    return python_matrix_exit_code(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify", help="Run one typed registered release gate")
    verify.add_argument("--candidate", required=True)
    verify.add_argument("--gate", required=True)
    verify.add_argument("--output")
    verify.add_argument("--backend-root")
    verify.add_argument("--frontend-root")
    verify.add_argument("--infra-root")
    verify.set_defaults(func=lambda args: _execute(args, "verify"))

    self_test = subparsers.add_parser("self-test", help="Exercise the authoritative gate path")
    self_test.add_argument("--candidate", default=str(DEFAULT_CANDIDATE))
    self_test.add_argument("--output")
    self_test.add_argument("--backend-root")
    self_test.add_argument("--frontend-root")
    self_test.add_argument("--infra-root")
    self_test.set_defaults(func=lambda args: _execute(args, "self-test"))

    python_hermetic = subparsers.add_parser(
        "python-hermetic",
        help="Run the two-environment Python 3.12 matrix",
    )
    python_hermetic.add_argument("--output")
    python_hermetic.set_defaults(func=_execute_python_matrix)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except GatePolicyError:
        return POLICY_EXIT
    except Exception:
        return EXECUTION_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
