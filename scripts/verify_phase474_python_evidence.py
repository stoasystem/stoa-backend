"""Fail-closed verification for Phase 474 Linux Python hermetic evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Literal, NoReturn, overload


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METADATA = ROOT / "evidence/phase-474/python-hermetic-linux.json"
DEFAULT_MATRIX = ROOT / "evidence/phase-474/python-hermetic-matrix.json"

TESTED_COMMIT = "f0fe24f88cffb4e196eb7a5f3089be3a80d5daaa"
TESTED_TREE = "578028f1503182a84be9fbe49fc79c6a1c9503e9"
MATRIX_SHA256 = "6a554f5c6036fc9830b099db8ac1b5e67ecbc68c2a072595ad18d23c92fed4bd"
MATRIX_BYTES = 1739
LOCK_SHA256 = "68efeb83c23ff4683cba1ff735130c365e8f9ec16dfb0eff5959a827536748fa"
COLLECTION_SHA256 = "70e9138e8ba8951716ca4f9dad6331497b7fa5e5e566a30805c330ea03aac3ea"
SEED = 4740718
CLOCKS = ["2026-07-01T12:00:00Z", "2035-01-15T12:00:00Z"]
SUITE_ARGV = ["python", "-m", "pytest", "-q", "-p", "no:socket"]
SOURCE_FILES = ("pyproject.toml", "requirements.txt", "uv.lock")

EXPECTED_METADATA: dict[str, Any] = {
    "schema": "stoa.phase474.python-hermetic-linux.v1",
    "status": "PASS",
    "completed_at": "2026-07-19T22:59:44Z",
    "tested_source": {
        "commit": TESTED_COMMIT,
        "tree": TESTED_TREE,
        "bundle_sha256": "b2b58a5ebf0bc1d53c27e77ecbc6f9fae8e1edadcc1d80a3e9a5b3f3e222b7ef",
    },
    "matrix": {
        "path": "evidence/phase-474/python-hermetic-matrix.json",
        "bytes": MATRIX_BYTES,
        "sha256": MATRIX_SHA256,
    },
    "runner": {
        "operating_system": "Linux",
        "architecture": "aarch64",
        "distribution": "Ubuntu 26.04 LTS",
        "kernel": "7.0.0-27-generic",
        "virtualization": {
            "product": "Lima",
            "version": "2.1.4",
            "driver": "VZ",
            "host_mounts": False,
        },
        "uv": {
            "version": "0.11.16",
            "binary_architecture": "aarch64",
            "binary_sha256": (
                "3d146b4232a025297b7983e1e89282d82c37ec99f4a94c0518ca855ce715c542"
            ),
        },
    },
    "network_boundary": {
        "argv": ["unshare", "--user", "--map-root-user", "--net", "--"],
        "probe": "PASS",
    },
    "command": (
        "python3 scripts/release_gate.py python-hermetic "
        "--output /tmp/phase474-python-matrix-f0fe24f.json"
    ),
    "production_operations": {
        "infrastructure": "NOT RUN",
        "deploy": "NOT RUN",
        "smoke": "NOT RUN",
        "rollback": "NOT RUN",
    },
}


class EvidenceVerificationError(RuntimeError):
    """Raised when persisted evidence is incomplete, altered, or source-unbound."""


def _fail(message: str) -> NoReturn:
    raise EvidenceVerificationError(message)


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _reject_non_finite_json(value: str) -> NoReturn:
    _fail(f"non-finite JSON number is forbidden: {value}")


def _load_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        _fail(f"cannot read {label}: {exc}")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_non_finite_json,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"invalid {label} JSON: {exc}")
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object")
    return raw, value


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        _fail(f"{label} keys differ: expected {sorted(expected)}, got {sorted(actual)}")


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{label} must be an array")
    return value


@overload
def _git(repo_root: Path, *args: str, binary: Literal[False] = False) -> str: ...


@overload
def _git(repo_root: Path, *args: str, binary: Literal[True]) -> bytes: ...


def _git(repo_root: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        _fail(f"git {' '.join(args)} failed: {detail}")
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", errors="strict").strip()


def _verify_metadata(metadata: dict[str, Any]) -> None:
    _require_exact_keys(metadata, set(EXPECTED_METADATA), "metadata")
    for nested in (
        "tested_source",
        "matrix",
        "runner",
        "network_boundary",
        "production_operations",
    ):
        actual = _require_dict(metadata[nested], f"metadata.{nested}")
        expected = _require_dict(EXPECTED_METADATA[nested], f"expected metadata.{nested}")
        _require_exact_keys(actual, set(expected), f"metadata.{nested}")

    runner = _require_dict(metadata["runner"], "metadata.runner")
    expected_runner = _require_dict(EXPECTED_METADATA["runner"], "expected metadata.runner")
    for nested in ("virtualization", "uv"):
        actual = _require_dict(runner[nested], f"metadata.runner.{nested}")
        expected = _require_dict(expected_runner[nested], f"expected metadata.runner.{nested}")
        _require_exact_keys(actual, set(expected), f"metadata.runner.{nested}")

    if metadata != EXPECTED_METADATA:
        _fail("metadata values differ from the closed Phase 474 Linux receipt")


def _verify_source(repo_root: Path, matrix_source: dict[str, Any]) -> None:
    object_type = _git(repo_root, "cat-file", "-t", TESTED_COMMIT)
    if object_type != "commit":
        _fail(f"tested source object is not a commit: {object_type}")
    actual_tree = _git(repo_root, "rev-parse", f"{TESTED_COMMIT}^{{tree}}")
    if actual_tree != TESTED_TREE:
        _fail(f"tested source tree differs: {actual_tree}")

    _require_exact_keys(matrix_source, set(SOURCE_FILES), "matrix.source")
    for name in SOURCE_FILES:
        recorded = _require_dict(matrix_source[name], f"matrix.source.{name}")
        _require_exact_keys(recorded, {"bytes", "sha256"}, f"matrix.source.{name}")
        blob_id = _git(repo_root, "rev-parse", f"{TESTED_COMMIT}:{name}")
        blob_type = _git(repo_root, "cat-file", "-t", str(blob_id))
        if blob_type != "blob":
            _fail(f"tested source {name} is not a Git blob")
        blob = _git(repo_root, "cat-file", "blob", str(blob_id), binary=True)
        assert isinstance(blob, bytes)
        expected = {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
        if recorded != expected:
            _fail(f"matrix source binding differs for {name}")


def _verify_matrix(matrix: dict[str, Any], repo_root: Path) -> None:
    _require_exact_keys(
        matrix,
        {"clocks", "reason_code", "runs", "schema", "seed", "source", "status", "suite_argv"},
        "matrix",
    )
    if matrix["schema"] != "stoa.phase474.python-matrix.v1":
        _fail("matrix schema differs")
    if matrix["status"] != "PASS" or matrix["reason_code"] is not None:
        _fail("matrix is not an unqualified PASS")
    if matrix["clocks"] != CLOCKS or matrix["seed"] != SEED:
        _fail("matrix clocks or seed differ")
    if matrix["suite_argv"] != SUITE_ARGV:
        _fail("matrix suite argv differs")

    source = _require_dict(matrix["source"], "matrix.source")
    _verify_source(repo_root, source)

    runs = _require_list(matrix["runs"], "matrix.runs")
    if len(runs) != 2:
        _fail("matrix must contain exactly two runs")
    expected_count_keys = {"error", "failed", "passed", "skipped", "total", "xfail", "xpass"}
    for index, run_value in enumerate(runs, start=1):
        run = _require_dict(run_value, f"matrix.runs[{index - 1}]")
        _require_exact_keys(
            run,
            {
                "clock",
                "collection_sha256",
                "counts",
                "environment",
                "lock_sha256",
                "run",
                "runtime",
                "seed",
            },
            f"matrix.runs[{index - 1}]",
        )
        expected_run_values = {
            "run": index,
            "clock": CLOCKS[index - 1],
            "environment": f"fresh-{index}",
            "runtime": "3.12.13",
            "seed": SEED,
            "lock_sha256": LOCK_SHA256,
            "collection_sha256": COLLECTION_SHA256,
        }
        for key, expected in expected_run_values.items():
            if run[key] != expected:
                _fail(f"matrix run {index} {key} differs")
        counts = _require_dict(run["counts"], f"matrix.runs[{index - 1}].counts")
        _require_exact_keys(counts, expected_count_keys, f"matrix.runs[{index - 1}].counts")
        if counts != {
            "error": 0,
            "failed": 0,
            "passed": 2139,
            "skipped": 0,
            "total": 2139,
            "xfail": 0,
            "xpass": 0,
        }:
            _fail(f"matrix run {index} counts differ")

    first = _require_dict(runs[0], "matrix.runs[0]")
    second = _require_dict(runs[1], "matrix.runs[1]")
    for field in ("runtime", "lock_sha256", "collection_sha256"):
        if first[field] != second[field]:
            _fail(f"matrix runs disagree on {field}")


def verify_evidence(
    *,
    metadata_path: Path = DEFAULT_METADATA,
    matrix_path: Path = DEFAULT_MATRIX,
    repo_root: Path = ROOT,
) -> None:
    """Verify exact metadata, matrix semantics, bytes, and tested Git source."""
    _, metadata = _load_json(metadata_path, "Linux metadata")
    matrix_raw, matrix = _load_json(matrix_path, "Python matrix")
    _verify_metadata(metadata)
    _verify_matrix(matrix, repo_root)
    if len(matrix_raw) != MATRIX_BYTES:
        _fail(f"matrix byte length differs: {len(matrix_raw)}")
    actual_sha256 = hashlib.sha256(matrix_raw).hexdigest()
    if actual_sha256 != MATRIX_SHA256:
        _fail(f"matrix SHA-256 differs: {actual_sha256}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        verify_evidence(
            metadata_path=args.metadata,
            matrix_path=args.matrix,
            repo_root=args.repo,
        )
    except EvidenceVerificationError as exc:
        print(f"FAIL: {exc}")
        return 2
    print("PASS: Phase 474 Linux Python hermetic evidence is closed and source-bound")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
