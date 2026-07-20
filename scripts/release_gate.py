#!/usr/bin/env python3
"""Run STOA release obligations through one closed local and CI authority."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1, sha256
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/release/gate-receipt-v1.schema.json"
RECEIPT_SCHEMA = "stoa.release.gate-receipt.v1"
FORMAL_RECEIPT_SCHEMA = "stoa.release.formal-gate-run.v1"
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
WEB_GATE_SCHEMA = "stoa.web.gate-run.v1"
NODE_RUNTIME_VERSION = "20.20.2"
NPM_RUNTIME_VERSION = "10.8.2"
NODE_ARCHIVE_MAX_BYTES = 64 * 1024 * 1024
NODE_ARCHIVE_MAX_MEMBERS = 20_000
NODE_ARCHIVE_MAX_MEMBER_BYTES = 128 * 1024 * 1024
NODE_ARCHIVE_MAX_EXTRACTED_BYTES = 192 * 1024 * 1024
WEB_GATE_MAX_RECEIPT_BYTES = 1024 * 1024
WEB_GATE_MAX_TREE_FILE_BYTES = 64 * 1024 * 1024
WEB_GATE_EXCLUDED_SOURCE_ROOTS = frozenset({".git", "dist", "node_modules"})
WEB_CONTAINMENT_UNSHARE = Path("/usr/bin/unshare")
WEB_CONTAINMENT_SHELL = Path("/usr/bin/dash")
WEB_CONTAINMENT_PREFIX = (
    "--user",
    "--map-root-user",
    "--pid",
    "--fork",
    "--mount-proc",
    "--kill-child=SIGKILL",
    "--",
)
WEB_GATE_STEPS = (
    (
        "frontend-locked-install",
        (
            "npm",
            "ci",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--include=dev",
            "--package-lock=true",
        ),
    ),
    ("frontend-eslint", ("npm", "run", "lint")),
    ("frontend-typecheck", ("npm", "run", "typecheck")),
    ("frontend-build", ("npm", "run", "build")),
    ("web-release-contracts", ("npm", "run", "test:release")),
)
_EVIDENCE_KINDS = frozenset({"none", "python-matrix", "web-gate-run"})
_WEB_RECEIPT_KEYS = {
    "schema",
    "status",
    "runtime",
    "source",
    "artifact",
    "steps",
    "counts",
    "production",
    "receiptSha256",
}
_WEB_STEP_KEYS = {
    "id",
    "argv",
    "status",
    "exitCode",
    "counts",
    "stdoutSha256",
    "stderrSha256",
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
FORMAL_CHILD_GATE_IDS = (
    "backend-python-hermetic",
    "frontend-web-fresh",
)
_FORMAL_PLATFORM_WEB_IDENTITIES = {
    "darwin-arm64": ("darwin", "arm64"),
    "darwin-x86_64": ("darwin", "x64"),
    "linux-aarch64": ("linux", "arm64"),
    "linux-x86_64": ("linux", "x64"),
}
_FORMAL_INPUT_CONTRACTS = (
    ("orchestrator", "backend", "scripts/release_gate.py"),
    ("formal_schema", "backend", "schemas/release/formal-gate-run-v1.schema.json"),
    ("child_schema", "backend", "schemas/release/gate-receipt-v1.schema.json"),
)
_FORMAL_COMMAND_ARGV = (
    "{python}",
    "scripts/release_gate.py",
    "formal",
    "--candidate",
    "{candidate}",
    "--backend-root",
    "{backend_root}",
    "--frontend-root",
    "{frontend_root}",
    "--infra-root",
    "{infra_root}",
    "--output",
    "{output}",
)


def _scrubbed_git_environment(
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a deterministic process environment with no ambient Git routing."""
    environment = dict(os.environ if source is None else source)
    for name in tuple(environment):
        if name.startswith("GIT_"):
            environment.pop(name)
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_ATTR_NOSYSTEM"] = "1"
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment


def _git_command(*argv: str) -> list[str]:
    return [
        "git",
        "--no-replace-objects",
        "--no-lazy-fetch",
        "-c",
        "core.fsmonitor=false",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "core.preloadIndex=false",
        "-c",
        "core.fileMode=true",
        "-c",
        "core.ignoreStat=false",
        "-c",
        "core.ignoreCase=false",
        "-c",
        "core.precomposeUnicode=false",
        "-c",
        "core.symlinks=true",
        "-c",
        f"core.attributesFile={os.devnull}",
        "-c",
        f"core.excludesFile={os.devnull}",
        "-c",
        "protocol.allow=never",
        "-c",
        "credential.helper=",
        *argv,
    ]


def _git_worktree_command(root: Path, *argv: str) -> list[str]:
    resolved = root.resolve()
    return _git_command(
        "-C",
        str(resolved),
        f"--work-tree={resolved}",
        *argv,
    )


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
_FORMAL_RECEIPT_KEYS = {
    "schema",
    "source",
    "command",
    "runtime",
    "inputs",
    "children",
    "result",
    "production",
    "privacy",
    "started_at",
    "ended_at",
    "receipt_sha256",
}
class GatePolicyError(ValueError):
    """A stable, redacted rejection of untrusted release evidence."""

    def __init__(self, message: str, *, result: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.result = result


class GateContainmentUnavailable(GatePolicyError):
    """The mandatory Web PID boundary cannot be proved before candidate code runs."""


class _StoreOnceAction(argparse.Action):
    """Reject duplicate formal options instead of silently taking the last value."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[str] | None,
        option_string: str | None = None,
    ) -> None:
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"argument {option_string or self.dest}: may only be supplied once")
        setattr(namespace, self.dest, values)


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class NodeArchiveSpec:
    archive_root: str
    url: str
    sha256: str


_NODE_ARCHIVES = {
    ("darwin", "arm64"): NodeArchiveSpec(
        archive_root="node-v20.20.2-darwin-arm64",
        url="https://nodejs.org/dist/v20.20.2/node-v20.20.2-darwin-arm64.tar.gz",
        sha256="466e05f3477c20dfb723054dfebffe55bc74660ee77f612166fca121dacb65b6",
    ),
    ("darwin", "x64"): NodeArchiveSpec(
        archive_root="node-v20.20.2-darwin-x64",
        url="https://nodejs.org/dist/v20.20.2/node-v20.20.2-darwin-x64.tar.gz",
        sha256="8be6f5e4bb128c82774f8a0b8d7a1cc1365a7977d9657cece0ca647b3fe04e61",
    ),
    ("linux", "arm64"): NodeArchiveSpec(
        archive_root="node-v20.20.2-linux-arm64",
        url="https://nodejs.org/dist/v20.20.2/node-v20.20.2-linux-arm64.tar.gz",
        sha256="47ef73d543ecf6eb19435f6c03a0ac4809b3bf0dd6b26c7c571efc2a6572a74d",
    ),
    ("linux", "x64"): NodeArchiveSpec(
        archive_root="node-v20.20.2-linux-x64",
        url="https://nodejs.org/dist/v20.20.2/node-v20.20.2-linux-x64.tar.gz",
        sha256="19e56f0825510207dd904f087fe52faa0a4eb6b2aab5f0ea7a33830d04888b8b",
    ),
}


@dataclass(frozen=True)
class GateSpec:
    gate_id: str
    argv: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    config_paths: tuple[str, ...]
    repository: str = "backend"
    cwd: str = "."
    timeout_seconds: int = 120
    evidence_kind: str = "none"

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
        if self.evidence_kind not in _EVIDENCE_KINDS:
            raise GatePolicyError("gate evidence kind is invalid")
        evidence_tokens = sum(value == "{evidence_output}" for value in self.argv)
        node_tokens = sum(value == "{node}" for value in self.argv)
        if self.evidence_kind == "web-gate-run":
            if evidence_tokens != 1 or node_tokens != 1:
                raise GatePolicyError("Web gate evidence tokens are invalid")
        elif evidence_tokens or node_tokens:
            raise GatePolicyError("non-Web gate cannot use Web evidence tokens")


@dataclass(frozen=True)
class GateOperations:
    run_process: Callable[[tuple[str, ...], Path, int], ProcessResult]
    git: Callable[[Path, tuple[str, ...]], str]
    now_utc: Callable[[], str]
    python_version: Callable[[], str]
    platform_identity: Callable[[], str]
    git_blob: Callable[[Path, str], bytes] | None = None
    materialize_checkout: Callable[[Path, str, Path], None] | None = None
    resolve_node20: Callable[[Mapping[str, str], Path], Path] | None = None
    run_web_process: (
        Callable[[tuple[str, ...], dict[str, str], Path, int], ProcessResult] | None
    ) = None
    probe_web_containment: Callable[[], bool] | None = None


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
                artifact_paths=("pyproject.toml",),
                config_paths=("schemas/release/gate-receipt-v1.schema.json",),
            ),
            GateSpec(
                gate_id="backend-python-hermetic",
                argv=("{python}", "scripts/release_gate.py", "python-hermetic"),
                artifact_paths=_PYTHON_MATRIX_SOURCE_FILES,
                config_paths=("scripts/phase474_pytest_guard.py", "tests/conftest.py"),
                timeout_seconds=7200,
                evidence_kind="python-matrix",
            ),
            GateSpec(
                gate_id="frontend-web-fresh",
                repository="frontend",
                argv=(
                    "{node}",
                    "scripts/verify-release.mjs",
                    "verify",
                    "--output",
                    "{evidence_output}",
                ),
                artifact_paths=("package-lock.json",),
                config_paths=(
                    "package.json",
                    "scripts/verify-release.mjs",
                    "schemas/release/web-gate-run-v1.schema.json",
                ),
                timeout_seconds=5400,
                evidence_kind="web-gate-run",
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


def _reject_nonfinite_json(value: str) -> None:
    raise GatePolicyError(f"non-finite JSON value is forbidden: {value}")


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


def candidate_execution_identity(repositories: Sequence[Mapping[str, Any]]) -> str:
    return sha256(
        json.dumps(
            _canonical_candidate_repositories(repositories),
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


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

    expected_identity = candidate_execution_identity(repositories)
    if candidate.get("execution_identity") != expected_identity:
        raise GatePolicyError("candidate execution identity mismatch")


def load_candidate(path: Path) -> dict[str, Any]:
    candidate = load_json(path)
    validate_candidate(candidate)
    return candidate


def _untracked_argv(repository: str) -> tuple[str, ...]:
    argv = ("ls-files", "--others", "--exclude-standard", "-z", "--", ".")
    if repository == "infra":
        return (*argv, ":(top,exclude,literal).DS_Store")
    return argv


def _parse_index_entries(raw: str) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    seen_paths: set[str] = set()
    for record in raw.split("\0"):
        if not record:
            continue
        try:
            metadata, path = record.split("\t", 1)
            mode, oid, stage = metadata.split(" ")
        except ValueError as exc:
            raise GatePolicyError("candidate index entry is malformed") from exc
        if (
            stage != "0"
            or mode not in {"100644", "100755", "120000"}
            or GIT_SHA_RE.fullmatch(oid) is None
            or not _is_safe_relative_path(path)
            or any(part.casefold() == ".git" for part in Path(path).parts)
            or path in seen_paths
        ):
            raise GatePolicyError("candidate index entry is invalid")
        seen_paths.add(path)
        entries.append((mode, oid, path))
    if len(entries) > 100_000:
        raise GatePolicyError("candidate index has too many entries")
    return sorted(entries, key=lambda entry: entry[2])


def _parse_head_tree_entries(raw: str) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    seen_paths: set[str] = set()
    for record in raw.split("\0"):
        if not record:
            continue
        try:
            metadata, path = record.split("\t", 1)
            mode, kind, oid = metadata.split(" ")
        except ValueError as exc:
            raise GatePolicyError("candidate HEAD tree entry is malformed") from exc
        if (
            kind != "blob"
            or mode not in {"100644", "100755", "120000"}
            or GIT_SHA_RE.fullmatch(oid) is None
            or not _is_safe_relative_path(path)
            or any(part.casefold() == ".git" for part in Path(path).parts)
            or path in seen_paths
        ):
            raise GatePolicyError("candidate HEAD tree entry is invalid")
        seen_paths.add(path)
        entries.append((mode, oid, path))
    if len(entries) > 100_000:
        raise GatePolicyError("candidate HEAD tree has too many entries")
    return sorted(entries, key=lambda entry: entry[2])


def _raw_git_blob_oid(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return sha1(header + content, usedforsecurity=False).hexdigest()


def _read_raw_tracked_path(root: Path, relative_path: str, mode: str) -> bytes:
    parts = Path(relative_path).parts
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(root, directory_flags)
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, directory_flags, dir_fd=directory)
            except OSError as exc:
                raise GatePolicyError(
                    "tracked worktree parent type differs from index"
                ) from exc
            os.close(directory)
            directory = child
        name = parts[-1]
        if mode == "120000":
            metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISLNK(metadata.st_mode):
                raise GatePolicyError("tracked worktree type differs from index")
            return os.fsencode(os.readlink(name, dir_fd=directory))
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode):
            raise GatePolicyError("tracked worktree type differs from index")
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=directory,
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise GatePolicyError("tracked worktree type differs from index")
            executable = bool(metadata.st_mode & stat.S_IXUSR)
            if executable != (mode == "100755"):
                raise GatePolicyError("tracked worktree mode differs from index")
            with os.fdopen(descriptor, "rb", closefd=False) as tracked_file:
                return tracked_file.read()
        finally:
            os.close(descriptor)
    except GatePolicyError:
        raise
    except OSError as exc:
        raise GatePolicyError("tracked worktree path is unavailable") from exc
    finally:
        os.close(directory)


def _raw_tracked_worktree_identity(root: Path, raw_index: str) -> str:
    projection: list[dict[str, str]] = []
    for mode, oid, relative_path in _parse_index_entries(raw_index):
        content = _read_raw_tracked_path(root, relative_path, mode)
        if _raw_git_blob_oid(content) != oid:
            raise GatePolicyError("tracked worktree bytes differ from index")
        projection.append({"mode": mode, "oid": oid, "path": relative_path})
    return sha256(
        json.dumps(
            projection,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _live_repository_identities(
    *,
    workspace: WorkspaceRoots,
    operations: GateOperations,
) -> list[dict[str, Any]]:
    if operations.git_blob is None:
        raise GatePolicyError("live candidate Git blob reader is unavailable")
    repositories: list[dict[str, Any]] = []
    for name, lock_path in _REPOSITORY_CONTRACTS:
        root = workspace.require(name)
        try:
            head = operations.git(root, ("rev-parse", "HEAD"))
            tree = operations.git(root, ("rev-parse", f"{head}^{{tree}}"))
            head_entries = operations.git(root, ("ls-tree", "-r", "-z", head))
            index_flags = operations.git(root, ("ls-files", "-v", "--"))
            index_entries = operations.git(root, ("ls-files", "--stage", "-z", "--"))
            tracked_infra_exception = (
                operations.git(root, ("ls-files", "--", ".DS_Store"))
                if name == "infra"
                else ""
            )
            committed_infra_exception = (
                operations.git(
                    root,
                    ("ls-tree", "--name-only", head, "--", ".DS_Store"),
                )
                if name == "infra"
                else ""
            )
            untracked = operations.git(root, _untracked_argv(name))
            committed_lock = operations.git_blob(root, f"{head}:{lock_path}")
            worktree_lock = _root_path(root, lock_path).read_bytes()
            tracked_identity = _raw_tracked_worktree_identity(root, index_entries)
            second_head = operations.git(root, ("rev-parse", "HEAD"))
            second_index_flags = operations.git(root, ("ls-files", "-v", "--"))
            second_index_entries = operations.git(
                root,
                ("ls-files", "--stage", "-z", "--"),
            )
            second_untracked = operations.git(root, _untracked_argv(name))
            second_tracked_identity = _raw_tracked_worktree_identity(
                root,
                index_entries,
            )
            second_worktree_lock = _root_path(root, lock_path).read_bytes()
            final_untracked = operations.git(root, _untracked_argv(name))
            final_index_flags = operations.git(root, ("ls-files", "-v", "--"))
            final_index_entries = operations.git(
                root,
                ("ls-files", "--stage", "-z", "--"),
            )
            final_head = operations.git(root, ("rev-parse", "HEAD"))
            if (
                second_head != head
                or final_head != head
                or second_index_flags != index_flags
                or final_index_flags != index_flags
                or second_index_entries != index_entries
                or final_index_entries != index_entries
                or second_untracked != untracked
                or final_untracked != untracked
                or second_tracked_identity != tracked_identity
                or second_worktree_lock != worktree_lock
            ):
                raise GatePolicyError("live repository changed during candidate capture")
        except GatePolicyError:
            raise
        except Exception as exc:
            raise GatePolicyError("live repository identity is unavailable") from exc
        _require_sha(head, f"{name} live head", git=True)
        _require_sha(tree, f"{name} live tree", git=True)
        head_projection = _parse_head_tree_entries(head_entries)
        index_projection = _parse_index_entries(index_entries)
        if any(not line.startswith("H ") for line in index_flags.splitlines() if line):
            raise GatePolicyError(f"{name} index has nonstandard path flags")
        if tracked_infra_exception or committed_infra_exception:
            raise GatePolicyError("infra .DS_Store exception cannot be tracked")
        if committed_lock != worktree_lock:
            raise GatePolicyError(f"{name} lock differs from committed source")
        clean = head_projection == index_projection and untracked == ""
        repositories.append(
            {
                "name": name,
                "head": head,
                "tree": tree,
                "lock_path": lock_path,
                "lock_sha256": sha256(worktree_lock).hexdigest(),
                "porcelain_sha256": sha256(untracked.encode("utf-8")).hexdigest(),
                "clean": clean,
            }
        )
    return repositories


def issue_live_candidate(
    *,
    workspace: WorkspaceRoots,
    operations: GateOperations,
) -> dict[str, Any]:
    repositories = _live_repository_identities(workspace=workspace, operations=operations)
    if not all(repository["clean"] is True for repository in repositories):
        raise GatePolicyError("live candidate repositories are not clean")
    candidate: dict[str, Any] = {
        "schema": "stoa.release.candidate-identity.v1",
        "status": "CLEAN",
        "identity_source": "execution-time-live-repository-state",
        "execution_identity": candidate_execution_identity(repositories),
        "repositories": repositories,
        "candidate_issued": True,
        "mutation_count": 0,
        "repository_mutation": "NOT RUN",
        "production_infrastructure": "NOT RUN",
        "production_deploy": "NOT RUN",
        "production_smoke": "NOT RUN",
        "production_rollback": "NOT RUN",
    }
    validate_candidate(candidate)
    return candidate


def validate_live_candidate(
    candidate: Mapping[str, Any],
    *,
    workspace: WorkspaceRoots,
    operations: GateOperations,
) -> None:
    validate_candidate(candidate)
    live_candidate = issue_live_candidate(workspace=workspace, operations=operations)
    if candidate != live_candidate:
        raise GatePolicyError("candidate does not match live repository state")


@contextmanager
def materialize_candidate_workspace(
    candidate: Mapping[str, Any],
    *,
    source_workspace: WorkspaceRoots,
    operations: GateOperations,
) -> Iterator[WorkspaceRoots]:
    validate_candidate(candidate)
    if operations.materialize_checkout is None:
        raise GatePolicyError("candidate checkout materializer is unavailable")
    with tempfile.TemporaryDirectory(prefix="stoa-release-candidate-") as temporary_root:
        parent = Path(temporary_root)
        roots: dict[str, Path] = {}
        for repository in candidate["repositories"]:
            name = repository["name"]
            destination = parent / name
            destination.mkdir()
            try:
                operations.materialize_checkout(
                    source_workspace.require(name),
                    repository["head"],
                    destination,
                )
            except Exception as exc:
                raise GatePolicyError("candidate checkout is unavailable") from exc
            roots[name] = destination
        snapshot = WorkspaceRoots.from_mapping(roots)
        for repository in candidate["repositories"]:
            lock = _root_path(snapshot.require(repository["name"]), repository["lock_path"])
            if sha256(lock.read_bytes()).hexdigest() != repository["lock_sha256"]:
                raise GatePolicyError("candidate archive lock identity mismatch")
        yield snapshot


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
    environment = _scrubbed_git_environment(source)
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
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_json,
        )
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


def _same_file_metadata(left: os.stat_result, right: os.stat_result) -> bool:
    return all(
        getattr(left, name) == getattr(right, name)
        for name in (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_uid",
            "st_gid",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
    )


def _read_stable_regular_at(
    directory: int,
    name: str,
    expected: os.stat_result,
    *,
    maximum_bytes: int,
    label: str,
) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=directory,
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not _same_file_metadata(expected, before)
            or before.st_size < 0
            or before.st_size > maximum_bytes
        ):
            raise GatePolicyError(f"{label} is not a stable regular file")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(content) != before.st_size
            or len(content) > maximum_bytes
            or not _same_file_metadata(before, after)
        ):
            raise GatePolicyError(f"{label} changed during inspection")
        return content
    except GatePolicyError:
        raise
    except OSError as exc:
        raise GatePolicyError(f"{label} is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _web_tree_identity(
    root: Path,
    *,
    exclude_generated: bool = False,
) -> dict[str, Any]:
    """Recompute the Plan-87 byte tree without following links or special files."""
    root_descriptor = -1
    try:
        root_metadata = root.lstat()
        if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(root_metadata.st_mode):
            raise GatePolicyError("Web tree root is not a directory")
        root_descriptor = os.open(
            root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        opened_root = os.fstat(root_descriptor)
        if not _same_file_metadata(root_metadata, opened_root):
            raise GatePolicyError("Web tree root changed during inspection")
    except GatePolicyError:
        if root_descriptor >= 0:
            os.close(root_descriptor)
        raise
    except OSError as exc:
        if root_descriptor >= 0:
            os.close(root_descriptor)
        raise GatePolicyError("Web tree root is unavailable") from exc

    digest = sha256()
    files = 0
    byte_count = 0

    def visit(directory: int, prefix: str) -> None:
        nonlocal files, byte_count
        try:
            names = sorted(os.listdir(directory), key=os.fsencode)
        except (OSError, UnicodeError) as exc:
            raise GatePolicyError("Web tree directory is unavailable") from exc
        for name in names:
            if not name or "/" in name or "\\" in name or "\x00" in name:
                raise GatePolicyError("Web tree path is invalid")
            relative = name if not prefix else f"{prefix}/{name}"
            try:
                metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
            except OSError as exc:
                raise GatePolicyError("Web tree entry is unavailable") from exc
            if (
                exclude_generated
                and not prefix
                and name in WEB_GATE_EXCLUDED_SOURCE_ROOTS
            ):
                continue
            if stat.S_ISLNK(metadata.st_mode):
                raise GatePolicyError("Web tree contains a symlink")
            if stat.S_ISDIR(metadata.st_mode):
                digest.update(f"directory\0{relative}\0".encode("utf-8"))
                child = -1
                try:
                    child = os.open(
                        name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory,
                    )
                    opened = os.fstat(child)
                    if not _same_file_metadata(metadata, opened):
                        raise GatePolicyError("Web tree directory changed during inspection")
                    visit(child, relative)
                    if not _same_file_metadata(opened, os.fstat(child)):
                        raise GatePolicyError("Web tree directory changed during inspection")
                except GatePolicyError:
                    raise
                except OSError as exc:
                    raise GatePolicyError("Web tree directory is unavailable") from exc
                finally:
                    if child >= 0:
                        os.close(child)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise GatePolicyError("Web tree contains a special entry")
            content = _read_stable_regular_at(
                directory,
                name,
                metadata,
                maximum_bytes=WEB_GATE_MAX_TREE_FILE_BYTES,
                label="Web tree file",
            )
            executable = "1" if metadata.st_mode & 0o111 else "0"
            digest.update(
                f"file\0{relative}\0{executable}\0{len(content)}\0".encode("utf-8")
            )
            digest.update(content)
            files += 1
            byte_count += len(content)

    try:
        visit(root_descriptor, "")
        if not _same_file_metadata(opened_root, os.fstat(root_descriptor)):
            raise GatePolicyError("Web tree root changed during inspection")
    finally:
        os.close(root_descriptor)
    return {
        "files": files,
        "bytes": byte_count,
        "treeSha256": digest.hexdigest(),
    }


def _web_root_file_identity(
    root: Path,
    name: str,
    *,
    maximum_bytes: int = WEB_GATE_MAX_TREE_FILE_BYTES,
    label: str = "Web source input",
) -> dict[str, Any]:
    directory = -1
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode):
            raise GatePolicyError("Web source input is not a regular file")
        content = _read_stable_regular_at(
            directory,
            name,
            metadata,
            maximum_bytes=maximum_bytes,
            label=label,
        )
    except GatePolicyError:
        raise
    except OSError as exc:
        raise GatePolicyError("Web source input is unavailable") from exc
    finally:
        if directory >= 0:
            os.close(directory)
    return {"bytes": len(content), "sha256": sha256(content).hexdigest()}


def _stable_regular_path_bytes(
    path: Path,
    *,
    maximum_bytes: int,
    label: str,
) -> bytes:
    directory = -1
    try:
        directory = os.open(
            path.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        metadata = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise GatePolicyError(f"{label} is not a single-link regular file")
        return _read_stable_regular_at(
            directory,
            path.name,
            metadata,
            maximum_bytes=maximum_bytes,
            label=label,
        )
    except GatePolicyError:
        raise
    except OSError as exc:
        raise GatePolicyError(f"{label} is unavailable") from exc
    finally:
        if directory >= 0:
            os.close(directory)


def _require_web_identity(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GatePolicyError(f"{label} is malformed")
    _require_exact_keys(value, {"bytes", "sha256"}, label)
    if (
        not isinstance(value.get("bytes"), int)
        or isinstance(value.get("bytes"), bool)
        or value["bytes"] < 1
    ):
        raise GatePolicyError(f"{label} byte count is invalid")
    _require_sha(value.get("sha256"), f"{label} digest")
    return value


def _web_source_identity(frontend_root: Path) -> dict[str, Any]:
    source_tree = _web_tree_identity(frontend_root, exclude_generated=True)
    return {
        "packageJson": _web_root_file_identity(frontend_root, "package.json"),
        "packageLock": _web_root_file_identity(frontend_root, "package-lock.json"),
        "treeSha256": source_tree["treeSha256"],
    }


def _stable_web_source_identity(frontend_root: Path) -> dict[str, Any]:
    first = _web_source_identity(frontend_root)
    second = _web_source_identity(frontend_root)
    if first != second:
        raise GatePolicyError("Web source changed during independent binding")
    return first


def _require_candidate_web_lock(
    source: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> None:
    candidate_frontend = next(
        (
            repository
            for repository in candidate["repositories"]
            if repository.get("name") == "frontend"
        ),
        None,
    )
    package_lock = source.get("packageLock")
    if (
        not isinstance(candidate_frontend, dict)
        or not isinstance(package_lock, dict)
        or candidate_frontend.get("lock_sha256") != package_lock.get("sha256")
    ):
        raise GatePolicyError("Web lock does not match candidate identity")


def _require_fresh_web_generated_state(frontend_root: Path) -> None:
    directory = -1
    try:
        directory = os.open(
            frontend_root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        for name in ("dist", "node_modules"):
            try:
                os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise GatePolicyError("Web candidate contains a generated tree")
    except GatePolicyError:
        raise
    except OSError as exc:
        raise GatePolicyError("Web generated state is unavailable") from exc
    finally:
        if directory >= 0:
            os.close(directory)


def _validate_web_gate_receipt_shape(
    receipt: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    expected_source: Mapping[str, Any],
) -> dict[str, Any]:
    _require_exact_keys(receipt, _WEB_RECEIPT_KEYS, "Web gate receipt")
    if receipt.get("schema") != WEB_GATE_SCHEMA or receipt.get("status") != "PASS":
        raise GatePolicyError("Web gate receipt status is invalid")
    supplied_digest = _require_sha(receipt.get("receiptSha256"), "Web receipt digest")
    body = {key: value for key, value in receipt.items() if key != "receiptSha256"}
    try:
        expected_digest = sha256(_canonical_bytes(body)).hexdigest()
    except (TypeError, ValueError) as exc:
        raise GatePolicyError("Web gate receipt contains an invalid JSON value") from exc
    if supplied_digest != expected_digest:
        raise GatePolicyError("Web gate receipt digest mismatch")

    runtime = receipt.get("runtime")
    if not isinstance(runtime, dict):
        raise GatePolicyError("Web gate runtime is malformed")
    _require_exact_keys(runtime, {"node", "npm", "platform", "arch"}, "Web runtime")
    if runtime.get("node") != NODE_RUNTIME_VERSION:
        raise GatePolicyError("Web gate Node runtime is invalid")
    if runtime.get("npm") != NPM_RUNTIME_VERSION:
        raise GatePolicyError("Web gate npm runtime is invalid")
    for field in ("platform", "arch"):
        value = runtime.get(field)
        if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{2,32}", value) is None:
            raise GatePolicyError("Web gate platform identity is invalid")

    source = receipt.get("source")
    if not isinstance(source, dict):
        raise GatePolicyError("Web gate source is malformed")
    _require_exact_keys(source, {"packageJson", "packageLock", "treeSha256"}, "Web source")
    _require_web_identity(source.get("packageJson"), "Web package")
    _require_web_identity(source.get("packageLock"), "Web lock")
    _require_sha(source.get("treeSha256"), "Web source tree digest")

    steps = receipt.get("steps")
    if not isinstance(steps, list) or len(steps) != len(WEB_GATE_STEPS):
        raise GatePolicyError("Web gate steps are incomplete")
    for value, (expected_id, expected_argv) in zip(steps, WEB_GATE_STEPS, strict=True):
        if not isinstance(value, dict):
            raise GatePolicyError("Web gate step is malformed")
        _require_exact_keys(value, _WEB_STEP_KEYS, "Web gate step")
        if (
            value.get("id") != expected_id
            or value.get("argv") != list(expected_argv)
            or value.get("status") != "PASS"
            or value.get("exitCode") != 0
            or value.get("counts") != {"total": 1, "passed": 1, "failed": 0}
        ):
            raise GatePolicyError("Web gate step is not an exact pass")
        _require_sha(value.get("stdoutSha256"), "Web step stdout digest")
        _require_sha(value.get("stderrSha256"), "Web step stderr digest")

    if receipt.get("counts") != {"total": 5, "passed": 5, "failed": 0, "omitted": 0}:
        raise GatePolicyError("Web gate counts are not complete-pass")
    if receipt.get("production") != {
        "infrastructure": "NOT RUN",
        "deploy": "NOT RUN",
        "smoke": "NOT RUN",
        "rollback": "NOT RUN",
    }:
        raise GatePolicyError("Web gate production evidence is invalid")

    artifact = receipt.get("artifact")
    if not isinstance(artifact, dict):
        raise GatePolicyError("Web gate artifact is malformed")
    _require_exact_keys(artifact, {"path", "files", "bytes", "treeSha256"}, "Web artifact")
    if (
        artifact.get("path") != "dist"
        or not isinstance(artifact.get("files"), int)
        or isinstance(artifact.get("files"), bool)
        or artifact["files"] < 1
        or not isinstance(artifact.get("bytes"), int)
        or isinstance(artifact.get("bytes"), bool)
        or artifact["bytes"] < 1
    ):
        raise GatePolicyError("Web gate artifact identity is invalid")
    _require_sha(artifact.get("treeSha256"), "Web artifact tree digest")

    if source != expected_source:
        raise GatePolicyError("Web source does not match the candidate seal")
    _require_candidate_web_lock(expected_source, candidate)
    return dict(artifact)


def _validate_web_gate_receipt(
    receipt: Mapping[str, Any],
    *,
    frontend_root: Path,
    candidate: Mapping[str, Any],
    expected_source: Mapping[str, Any] | None = None,
) -> None:
    post_run_source = _stable_web_source_identity(frontend_root)
    baseline = dict(post_run_source if expected_source is None else expected_source)
    artifact = _validate_web_gate_receipt_shape(
        receipt,
        candidate=candidate,
        expected_source=baseline,
    )
    if post_run_source != baseline:
        raise GatePolicyError("Web source does not match the pre-run candidate seal")

    first_artifact = _web_tree_identity(frontend_root / "dist")
    second_artifact = _web_tree_identity(frontend_root / "dist")
    if first_artifact != second_artifact:
        raise GatePolicyError("Web artifact changed during independent binding")
    if artifact != {"path": "dist", **first_artifact}:
        raise GatePolicyError("Web artifact does not match candidate execution")


def _load_private_web_receipt(path: Path) -> dict[str, Any]:
    parent_descriptor = -1
    try:
        parent_metadata = path.parent.lstat()
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or stat.S_ISLNK(parent_metadata.st_mode)
            or stat.S_IMODE(parent_metadata.st_mode) != 0o700
            or (hasattr(os, "getuid") and parent_metadata.st_uid != os.getuid())
        ):
            raise GatePolicyError("Web evidence directory is not private")
        parent_descriptor = os.open(
            path.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        opened_parent = os.fstat(parent_descriptor)
        if not _same_file_metadata(parent_metadata, opened_parent):
            raise GatePolicyError("Web evidence directory changed during inspection")
        metadata = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size < 1
            or metadata.st_size > WEB_GATE_MAX_RECEIPT_BYTES
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            raise GatePolicyError("Web evidence output is not a private regular file")
        content = _read_stable_regular_at(
            parent_descriptor,
            path.name,
            metadata,
            maximum_bytes=WEB_GATE_MAX_RECEIPT_BYTES,
            label="Web evidence output",
        )
        if not _same_file_metadata(opened_parent, os.fstat(parent_descriptor)):
            raise GatePolicyError("Web evidence directory changed during inspection")
    except GatePolicyError:
        raise
    except OSError as exc:
        raise GatePolicyError("Web evidence output is unavailable") from exc
    finally:
        if parent_descriptor >= 0:
            os.close(parent_descriptor)

    try:
        text = content.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_json,
        )
    except GatePolicyError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GatePolicyError("Web evidence output is malformed") from exc
    if not isinstance(value, dict):
        raise GatePolicyError("Web evidence output must be an object")
    try:
        canonical = _canonical_bytes(value)
    except (TypeError, ValueError) as exc:
        raise GatePolicyError("Web evidence output contains an invalid JSON value") from exc
    if content != canonical + b"\n":
        raise GatePolicyError("Web evidence output is not canonical JSON")
    return value


@contextmanager
def _private_web_evidence_directory(
    workspace: WorkspaceRoots,
) -> Iterator[tuple[Path, Path, dict[str, str]]]:
    temporary_base = Path(tempfile.gettempdir()).resolve(strict=True)
    for _, source_root in workspace.roots:
        if temporary_base == source_root or source_root in temporary_base.parents:
            raise GatePolicyError("Web evidence base must be source-external")
    directory = Path(tempfile.mkdtemp(prefix="stoa-web-evidence-", dir=temporary_base))
    try:
        directory.chmod(0o700)
        resolved = directory.resolve(strict=True)
        for _, source_root in workspace.roots:
            if resolved == source_root or source_root in resolved.parents:
                raise GatePolicyError("Web evidence directory must be source-external")
        home = resolved / "home"
        temporary = resolved / "tmp"
        home.mkdir(mode=0o700)
        temporary.mkdir(mode=0o700)
        environment = {
            "CI": "true",
            "HOME": str(home),
            "LANG": "C",
            "LC_ALL": "C",
            "TMPDIR": str(temporary),
            "TZ": "UTC",
        }
        yield resolved, resolved / "receipt.json", environment
    finally:
        try:
            shutil.rmtree(directory)
        except OSError as exc:
            raise GatePolicyError("Web evidence directory cleanup failed") from exc


def _run_web_gate_evidence(
    *,
    spec: GateSpec,
    candidate: Mapping[str, Any],
    workspace: WorkspaceRoots,
    command_cwd: Path,
    operations: GateOperations,
) -> tuple[ProcessResult, dict[str, Any]]:
    if operations.probe_web_containment is None:
        raise GateContainmentUnavailable("Web PID containment is unavailable")
    try:
        containment_available = operations.probe_web_containment()
    except Exception as exc:
        raise GateContainmentUnavailable(
            "Web PID containment is unavailable"
        ) from exc
    if containment_available is not True:
        raise GateContainmentUnavailable("Web PID containment is unavailable")
    if operations.resolve_node20 is None or operations.run_web_process is None:
        raise GatePolicyError("Web gate launcher is unavailable")
    _require_fresh_web_generated_state(command_cwd)
    source_baseline = _stable_web_source_identity(command_cwd)
    _require_candidate_web_lock(source_baseline, candidate)
    with _private_web_evidence_directory(workspace) as (
        evidence_directory,
        evidence_path,
        base_environment,
    ):
        toolchain_root = evidence_directory / "toolchain"
        node = operations.resolve_node20(base_environment, toolchain_root)
        if not node.is_absolute():
            raise GatePolicyError("Web gate Node executable is not absolute")
        resolved_node = node.resolve(strict=True)
        if resolved_node != toolchain_root / "bin" / "node":
            raise GatePolicyError("Web gate Node executable is outside its private snapshot")
        for _, source_root in workspace.roots:
            if resolved_node == source_root or source_root in resolved_node.parents:
                raise GatePolicyError("Web gate Node executable is source-local")
        toolchain_baseline = _node_toolchain_identity(resolved_node)
        environment = {
            **base_environment,
            "PATH": str(resolved_node.parent),
        }
        actual_argv = tuple(
            str(resolved_node)
            if value == "{node}"
            else str(evidence_path)
            if value == "{evidence_output}"
            else value
            for value in spec.argv
        )
        completed = operations.run_web_process(
            actual_argv,
            environment,
            command_cwd,
            spec.timeout_seconds,
        )
        if _node_toolchain_identity(resolved_node) != toolchain_baseline:
            raise GatePolicyError("controlled Node toolchain changed during Web gate")
        if completed.returncode != 0:
            return completed, {}
        receipt = _load_private_web_receipt(evidence_path)
        _validate_web_gate_receipt(
            receipt,
            frontend_root=command_cwd,
            candidate=candidate,
            expected_source=source_baseline,
        )
        if evidence_directory != evidence_path.parent:
            raise GatePolicyError("Web evidence output path changed")
        return completed, receipt


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
        env=_scrubbed_git_environment(),
        timeout=timeout_seconds,
    )
    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


def _write_all(descriptor: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise GatePolicyError("controlled Node file write was incomplete")
        remaining = remaining[written:]


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        raise GatePolicyError("controlled Node archive redirect is forbidden")


def _selected_node_archive() -> NodeArchiveSpec:
    system = platform.system().lower()
    raw_machine = platform.machine().lower()
    machine_aliases = {
        "aarch64": "arm64",
        "arm64": "arm64",
        "amd64": "x64",
        "x86_64": "x64",
    }
    machine = machine_aliases.get(raw_machine)
    if machine is None:
        raise GatePolicyError("controlled Node platform is unsupported")
    try:
        return _NODE_ARCHIVES[(system, machine)]
    except KeyError as exc:
        raise GatePolicyError("controlled Node platform is unsupported") from exc


def _download_node_archive(spec: NodeArchiveSpec, destination: Path) -> None:
    if (
        not spec.url.startswith("https://nodejs.org/dist/v20.20.2/")
        or not spec.url.endswith(".tar.gz")
        or SHA256_RE.fullmatch(spec.sha256) is None
    ):
        raise GatePolicyError("controlled Node archive registration is invalid")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirectHandler(),
    )
    request = urllib.request.Request(
        spec.url,
        headers={
            "Accept-Encoding": "identity",
            "User-Agent": "stoa-release-gate/1",
        },
        method="GET",
    )
    descriptor = -1
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with opener.open(request, timeout=120) as response:
            if response.status != 200:
                raise GatePolicyError("controlled Node archive response is invalid")
            if response.geturl() != spec.url:
                raise GatePolicyError("controlled Node archive redirect is forbidden")
            if response.headers.get("Content-Encoding") not in {None, "identity"}:
                raise GatePolicyError("controlled Node archive encoding is invalid")
            raw_length = response.headers.get("Content-Length")
            try:
                expected_length = int(raw_length)
            except (TypeError, ValueError) as exc:
                raise GatePolicyError("controlled Node archive size is invalid") from exc
            if not 1 <= expected_length <= NODE_ARCHIVE_MAX_BYTES:
                raise GatePolicyError("controlled Node archive size is invalid")
            digest = sha256()
            received = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > expected_length or received > NODE_ARCHIVE_MAX_BYTES:
                    raise GatePolicyError("controlled Node archive size is invalid")
                _write_all(descriptor, chunk)
                digest.update(chunk)
            if received != expected_length:
                raise GatePolicyError("controlled Node archive size is invalid")
            if digest.hexdigest() != spec.sha256:
                raise GatePolicyError("controlled Node archive digest mismatch")
        os.fsync(descriptor)
    except GatePolicyError:
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise GatePolicyError("controlled Node archive download failed") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if sys.exc_info()[0] is not None:
            destination.unlink(missing_ok=True)


def _safe_node_archive_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in name
        or "\x00" in name
    ):
        raise GatePolicyError("controlled Node archive member path is unsafe")
    return path


def _extract_controlled_node_archive(
    spec: NodeArchiveSpec,
    archive_bytes: bytes,
    destination: Path,
) -> None:
    if destination.exists() or destination.is_symlink():
        raise GatePolicyError("controlled Node toolchain destination is not empty")
    destination.mkdir(mode=0o700)
    node_member = f"{spec.archive_root}/bin/node"
    npm_prefix = f"{spec.archive_root}/lib/node_modules/npm"
    required_files = {
        node_member,
        f"{npm_prefix}/package.json",
        f"{npm_prefix}/bin/npm-cli.js",
    }
    seen: set[str] = set()
    extracted_files: set[str] = set()
    extracted_bytes = 0
    member_count = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            for member in archive:
                member_count += 1
                if member_count > NODE_ARCHIVE_MAX_MEMBERS:
                    raise GatePolicyError("controlled Node archive has too many members")
                member_path = _safe_node_archive_path(member.name)
                normalized = member_path.as_posix()
                selected = normalized == node_member or normalized == npm_prefix or (
                    normalized.startswith(f"{npm_prefix}/")
                )
                if not selected:
                    continue
                if normalized in seen:
                    raise GatePolicyError("controlled Node archive member is duplicated")
                seen.add(normalized)
                if normalized == node_member:
                    relative = PurePosixPath("bin/node")
                else:
                    relative = PurePosixPath(*member_path.parts[1:])
                target = destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(mode=0o700, parents=True, exist_ok=True)
                    target.chmod(0o700)
                    continue
                if not member.isfile():
                    raise GatePolicyError("controlled Node archive member type is unsafe")
                if not 0 <= member.size <= NODE_ARCHIVE_MAX_MEMBER_BYTES:
                    raise GatePolicyError("controlled Node archive member size is invalid")
                extracted_bytes += member.size
                if extracted_bytes > NODE_ARCHIVE_MAX_EXTRACTED_BYTES:
                    raise GatePolicyError("controlled Node archive extraction is oversized")
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise GatePolicyError("controlled Node archive member is unavailable")
                descriptor = -1
                written = 0
                try:
                    descriptor = os.open(
                        target,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                    )
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > member.size:
                            raise GatePolicyError(
                                "controlled Node archive member size is invalid"
                            )
                        _write_all(descriptor, chunk)
                    if written != member.size:
                        raise GatePolicyError(
                            "controlled Node archive member size is invalid"
                        )
                    os.fsync(descriptor)
                    os.fchmod(descriptor, 0o700 if member.mode & 0o111 else 0o600)
                finally:
                    source.close()
                    if descriptor >= 0:
                        os.close(descriptor)
                extracted_files.add(normalized)
    except GatePolicyError:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    except (OSError, tarfile.TarError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise GatePolicyError("controlled Node archive extraction failed") from exc
    if not required_files <= extracted_files:
        shutil.rmtree(destination, ignore_errors=True)
        raise GatePolicyError("controlled Node archive is incomplete")


def _node_toolchain_identity(node: Path) -> dict[str, Any]:
    resolved = node.resolve(strict=True)
    prefix = resolved.parent.parent
    if resolved != prefix / "bin" / "node":
        raise GatePolicyError("controlled Node executable layout is invalid")
    npm_root = prefix / "lib" / "node_modules" / "npm"
    package_path = npm_root / "package.json"
    npm_cli = npm_root / "bin" / "npm-cli.js"
    package_bytes = _stable_regular_path_bytes(
        package_path,
        maximum_bytes=1024 * 1024,
        label="controlled npm package",
    )
    try:
        package = json.loads(
            package_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_json,
        )
    except GatePolicyError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GatePolicyError("controlled npm package is malformed") from exc
    if (
        not isinstance(package, dict)
        or package.get("name") != "npm"
        or package.get("version") != NPM_RUNTIME_VERSION
    ):
        raise GatePolicyError("controlled npm runtime identity is invalid")
    return {
        "node": _web_root_file_identity(
            resolved.parent,
            resolved.name,
            maximum_bytes=NODE_ARCHIVE_MAX_MEMBER_BYTES,
            label="controlled Node executable",
        ),
        "npm": _web_tree_identity(npm_root),
        "npmPackage": {
            "bytes": len(package_bytes),
            "sha256": sha256(package_bytes).hexdigest(),
        },
        "npmCli": _web_root_file_identity(
            npm_cli.parent,
            npm_cli.name,
            label="controlled npm CLI",
        ),
    }


def _system_resolve_node20(
    base_environment: Mapping[str, str],
    destination: Path,
) -> Path:
    spec = _selected_node_archive()
    archive_path = destination.parent / f".{spec.archive_root}.tar.gz"
    _download_node_archive(spec, archive_path)
    try:
        archive_bytes = _stable_regular_path_bytes(
            archive_path,
            maximum_bytes=NODE_ARCHIVE_MAX_BYTES,
            label="controlled Node archive",
        )
        if sha256(archive_bytes).hexdigest() != spec.sha256:
            raise GatePolicyError("controlled Node archive digest mismatch")
        _extract_controlled_node_archive(spec, archive_bytes, destination)
    finally:
        archive_path.unlink(missing_ok=True)
    node = (destination / "bin" / "node").resolve(strict=True)
    initial_identity = _node_toolchain_identity(node)
    npm_cli = destination / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js"
    environment = {**base_environment, "PATH": str(node.parent)}
    try:
        node_probe = subprocess.run(
            [str(node), "--version"],
            check=False,
            capture_output=True,
            env=environment,
            timeout=10,
        )
        npm_probe = subprocess.run(
            [str(node), str(npm_cli), "--version"],
            check=False,
            capture_output=True,
            env=environment,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GatePolicyError("controlled Node runtime probe failed") from exc
    try:
        node_version = node_probe.stdout.decode("ascii", errors="strict").strip()
        npm_version = npm_probe.stdout.decode("ascii", errors="strict").strip()
    except UnicodeError as exc:
        raise GatePolicyError("controlled Node runtime identity is invalid") from exc
    if (
        node_probe.returncode != 0
        or node_version != f"v{NODE_RUNTIME_VERSION}"
        or npm_probe.returncode != 0
        or npm_version != NPM_RUNTIME_VERSION
    ):
        raise GatePolicyError("controlled Node/npm runtime identity is invalid")
    if _node_toolchain_identity(node) != initial_identity:
        raise GatePolicyError("controlled Node toolchain changed during probe")
    return node


def _is_trusted_root_executable(path: Path) -> bool:
    if not path.is_absolute():
        return False
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == 0
        and metadata.st_mode & 0o022 == 0
        and metadata.st_mode & 0o111 != 0
    )


def _web_containment_environment() -> dict[str, str]:
    return {
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }


def _system_web_containment_available() -> bool:
    if platform.system() != "Linux":
        return False
    if not _is_trusted_root_executable(WEB_CONTAINMENT_UNSHARE):
        return False
    if not _is_trusted_root_executable(WEB_CONTAINMENT_SHELL):
        return False
    probe_argv = (
        str(WEB_CONTAINMENT_UNSHARE),
        *WEB_CONTAINMENT_PREFIX,
        str(WEB_CONTAINMENT_SHELL),
        "-c",
        'test "$$" -eq 1',
    )
    try:
        completed = subprocess.run(
            list(probe_argv),
            check=False,
            capture_output=True,
            env=_web_containment_environment(),
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _run_web_process_group(
    argv: tuple[str, ...],
    environment: dict[str, str],
    cwd: Path,
    timeout_seconds: int,
) -> ProcessResult:
    process = subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        _confirm_web_process_group_stopped(process.pid)
        raise
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    _confirm_web_process_group_stopped(process.pid)
    return ProcessResult(process.returncode, stdout, stderr)


def _system_web_run(
    argv: tuple[str, ...],
    environment: dict[str, str],
    cwd: Path,
    timeout_seconds: int,
) -> ProcessResult:
    if not _system_web_containment_available():
        raise GateContainmentUnavailable("Web PID containment is unavailable")
    contained_argv = (
        str(WEB_CONTAINMENT_UNSHARE),
        *WEB_CONTAINMENT_PREFIX,
        *argv,
    )
    return _run_web_process_group(
        contained_argv,
        environment,
        cwd,
        timeout_seconds,
    )


def _confirm_web_process_group_stopped(process_group: int) -> None:
    deadline = time.monotonic() + 5.0
    while True:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return
        except OSError as exc:
            raise GatePolicyError("Web gate process group state is unavailable") from exc
        if time.monotonic() >= deadline:
            raise GatePolicyError("Web gate process group did not stop")
        time.sleep(0.01)


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
        _git_worktree_command(root, *argv),
        check=True,
        capture_output=True,
        env=_scrubbed_git_environment(),
        text=True,
        timeout=30,
    )
    return completed.stdout.rstrip("\n")


def _system_git_blob(root: Path, revision_path: str) -> bytes:
    completed = subprocess.run(
        _git_worktree_command(root, "show", revision_path),
        check=True,
        capture_output=True,
        env=_scrubbed_git_environment(),
        timeout=30,
    )
    return completed.stdout


def _parse_tree_entries(raw: bytes) -> list[tuple[str, str, str, bytes]]:
    entries: list[tuple[str, str, str, bytes]] = []
    seen_paths: set[bytes] = set()
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path = record.split(b"\t", 1)
            mode_bytes, kind_bytes, oid_bytes = metadata.split(b" ", 2)
            mode = mode_bytes.decode("ascii")
            kind = kind_bytes.decode("ascii")
            oid = oid_bytes.decode("ascii")
        except (ValueError, UnicodeError) as exc:
            raise GatePolicyError("candidate tree entry is malformed") from exc
        if path in seen_paths or not path or b"\0" in path:
            raise GatePolicyError("candidate tree path is invalid")
        seen_paths.add(path)
        entries.append((mode, kind, oid, path))
    if len(entries) > 100_000:
        raise GatePolicyError("candidate tree has too many entries")
    return entries


def _batch_git_blobs(root: Path, entries: Sequence[tuple[str, str, str, bytes]]) -> list[bytes]:
    requested = [oid for mode, kind, oid, _ in entries if kind == "blob"]
    completed = subprocess.run(
        _git_worktree_command(root, "cat-file", "--batch"),
        input=("\n".join(requested) + "\n").encode("ascii"),
        check=True,
        capture_output=True,
        env=_scrubbed_git_environment(),
        timeout=120,
    )
    output = completed.stdout
    cursor = 0
    blobs: list[bytes] = []
    for expected_oid in requested:
        newline = output.find(b"\n", cursor)
        if newline < 0:
            raise GatePolicyError("candidate blob batch is truncated")
        try:
            actual_oid, kind, size_text = output[cursor:newline].decode("ascii").split(" ")
            size = int(size_text)
        except (ValueError, UnicodeError) as exc:
            raise GatePolicyError("candidate blob header is malformed") from exc
        cursor = newline + 1
        end = cursor + size
        if actual_oid != expected_oid or kind != "blob" or size < 0 or end >= len(output):
            raise GatePolicyError("candidate blob identity is invalid")
        blobs.append(output[cursor:end])
        if output[end : end + 1] != b"\n":
            raise GatePolicyError("candidate blob delimiter is invalid")
        cursor = end + 1
    if cursor != len(output):
        raise GatePolicyError("candidate blob batch has trailing data")
    return blobs


def _safe_checkout_path(destination: Path, raw_path: bytes) -> Path:
    relative = Path(os.fsdecode(raw_path))
    if relative.is_absolute() or any(
        part in {"", ".", ".."} or part.casefold() == ".git"
        for part in relative.parts
    ):
        raise GatePolicyError("candidate tree path is unsafe")
    resolved_destination = destination.resolve()
    path = resolved_destination.joinpath(*relative.parts)
    resolved_parent = path.parent.resolve(strict=False)
    if (
        resolved_parent != resolved_destination
        and resolved_destination not in resolved_parent.parents
    ):
        raise GatePolicyError("candidate tree path escapes checkout")
    return path


def _install_git_context(root: Path, commit: str, destination: Path) -> None:
    git_dir = destination / ".git"
    environment = _scrubbed_git_environment()
    subprocess.run(
        _git_command("init", "--bare", "--template=", "-q", str(git_dir)),
        check=True,
        capture_output=True,
        env=environment,
        timeout=30,
    )
    packed = subprocess.run(
        _git_worktree_command(root, "pack-objects", "--revs", "--stdout"),
        input=f"{commit}\n".encode("ascii"),
        check=True,
        capture_output=True,
        env=environment,
        timeout=300,
    )
    subprocess.run(
        _git_command(f"--git-dir={git_dir}", "index-pack", "--stdin", "--fix-thin"),
        input=packed.stdout,
        check=True,
        capture_output=True,
        env=environment,
        timeout=300,
    )
    git_dir_args = _git_command(f"--git-dir={git_dir}")
    subprocess.run(
        [*git_dir_args, "config", "core.bare", "false"],
        check=True,
        capture_output=True,
        env=environment,
        timeout=30,
    )
    subprocess.run(
        [*git_dir_args, "update-ref", "--no-deref", "HEAD", commit],
        check=True,
        capture_output=True,
        env=environment,
        timeout=30,
    )
    subprocess.run(
        [*git_dir_args, "read-tree", commit],
        check=True,
        capture_output=True,
        env=environment,
        timeout=30,
    )


def _system_materialize_checkout(root: Path, commit: str, destination: Path) -> None:
    checkout_root = destination.resolve()
    tree_result = subprocess.run(
        _git_worktree_command(root, "ls-tree", "-r", "-z", commit),
        check=True,
        capture_output=True,
        env=_scrubbed_git_environment(),
        timeout=120,
    )
    entries = _parse_tree_entries(tree_result.stdout)
    if any(kind == "commit" or mode == "160000" for mode, kind, _, _ in entries):
        raise GatePolicyError("candidate tree contains a gitlink")
    if any(
        kind != "blob" or mode not in {"100644", "100755", "120000"}
        for mode, kind, _, _ in entries
    ):
        raise GatePolicyError("candidate tree contains an unsupported entry")
    blobs = iter(_batch_git_blobs(root, entries))
    for mode, _, _, raw_path in entries:
        path = _safe_checkout_path(destination, raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = next(blobs)
        if mode == "120000":
            target_text = os.fsdecode(blob)
            target = Path(target_text)
            resolved_target = (path.parent / target).resolve(strict=False)
            if (
                target.is_absolute()
                or any(part.casefold() == ".git" for part in target.parts)
                or (
                    resolved_target != checkout_root
                    and checkout_root not in resolved_target.parents
                )
            ):
                raise GatePolicyError("candidate symlink escapes checkout")
            path.symlink_to(target_text)
        else:
            path.write_bytes(blob)
            path.chmod(0o755 if mode == "100755" else 0o644)
    try:
        next(blobs)
    except StopIteration:
        pass
    else:
        raise GatePolicyError("candidate blob count is invalid")
    _install_git_context(root, commit, destination)
    snapshot_head = _system_git(destination, ("rev-parse", "HEAD"))
    snapshot_tree = _system_git(destination, ("rev-parse", "HEAD^{tree}"))
    expected_tree = _system_git(root, ("rev-parse", f"{commit}^{{tree}}"))
    snapshot_status = _system_git(
        destination,
        ("status", "--porcelain=v1", "--untracked-files=all", "--", "."),
    )
    if snapshot_head != commit or snapshot_tree != expected_tree or snapshot_status:
        raise GatePolicyError("candidate checkout identity is invalid")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def system_operations() -> GateOperations:
    return GateOperations(
        run_process=_system_run,
        git=_system_git,
        now_utc=_now_utc,
        python_version=platform.python_version,
        platform_identity=lambda: f"{platform.system().lower()}-{platform.machine().lower()}",
        git_blob=_system_git_blob,
        materialize_checkout=_system_materialize_checkout,
        resolve_node20=_system_resolve_node20,
        run_web_process=_system_web_run,
        probe_web_containment=_system_web_containment_available,
    )


def _run_registered_gate_on_snapshot(
    *,
    gate_id: str,
    command_name: str,
    candidate: Mapping[str, Any],
    registry: GateRegistry,
    operations: GateOperations,
    workspace: WorkspaceRoots | None = None,
    source_workspace: WorkspaceRoots | None = None,
) -> dict[str, Any]:
    validate_candidate(candidate)
    if command_name not in {"verify", "self-test"}:
        raise GatePolicyError("unknown command name")
    if command_name == "self-test" and gate_id != "gate-self-test":
        raise GatePolicyError("command name is not registered for gate")
    spec = registry.require(gate_id)
    resolved_workspace = workspace or default_workspace_roots()
    resolved_source_workspace = source_workspace or resolved_workspace
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
                resolved_source_workspace.require(repository["name"]),
                ("cat-file", "-e", f"{repository['head']}^{{commit}}"),
            )
        if spec.evidence_kind == "web-gate-run":
            try:
                completed, web_evidence = _run_web_gate_evidence(
                    spec=spec,
                    candidate=candidate,
                    workspace=resolved_workspace,
                    command_cwd=command_cwd,
                    operations=operations,
                )
            except GateContainmentUnavailable:
                result = {
                    "status": "NOT RUN",
                    "classification": "NOT_RUN_OBLIGATION",
                    "exit_code": POLICY_EXIT,
                    "reason_code": "EXTERNAL_CHECK_UNAVAILABLE",
                    "outcomes": _counts(),
                }
            except GatePolicyError:
                result = {
                    "status": "FAIL",
                    "classification": "POLICY_REJECTION",
                    "exit_code": POLICY_EXIT,
                    "reason_code": "GATE_EVIDENCE_INVALID",
                    "outcomes": _counts(failed=1),
                }
            else:
                stdout = completed.stdout
                stderr = completed.stderr
                if completed.returncode == 0:
                    gate_evidence = web_evidence
                    result = {
                        "status": "PASS",
                        "classification": "COMPLETE_PASS",
                        "exit_code": 0,
                        "reason_code": None,
                        "outcomes": _counts(passed=len(WEB_GATE_STEPS)),
                    }
                else:
                    result = {
                        "status": "FAIL",
                        "classification": "POLICY_REJECTION",
                        "exit_code": POLICY_EXIT,
                        "reason_code": "GATE_COMMAND_FAILED",
                        "outcomes": _counts(failed=1),
                    }
        else:
            completed = operations.run_process(spec.argv, command_cwd, spec.timeout_seconds)
            stdout = completed.stdout
            stderr = completed.stderr
            if spec.evidence_kind == "python-matrix":
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
    allowed_command_names = (
        {"verify", "self-test"} if spec.gate_id == "gate-self-test" else {"verify"}
    )
    if (
        command["name"] not in allowed_command_names
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
    if spec.evidence_kind == "python-matrix":
        if gate_evidence is None:
            expected_outcomes = {
                (
                    "FAIL",
                    "POLICY_REJECTION",
                    POLICY_EXIT,
                    "GATE_EVIDENCE_INVALID",
                ): _counts(failed=1),
                (
                    "FAIL",
                    "EXECUTION_FAILURE",
                    EXECUTION_EXIT,
                    "GATE_EXECUTION_ERROR",
                ): _counts(errors=1),
            }.get(
                (
                    result["status"],
                    result["classification"],
                    result["exit_code"],
                    result["reason_code"],
                )
            )
            if expected_outcomes is None or result["outcomes"] != expected_outcomes:
                raise GatePolicyError("hermetic receipt lacks matrix evidence")
        else:
            if not isinstance(gate_evidence, dict):
                raise GatePolicyError("hermetic receipt matrix evidence is malformed")
            _validate_registered_python_matrix(
                gate_evidence,
                root=resolved_workspace.require(spec.repository),
            )
            expected_shape: tuple[str, str, int, str | None, dict[str, int]]
            if gate_evidence["status"] == "PASS":
                expected_shape = (
                    "PASS",
                    "COMPLETE_PASS",
                    0,
                    None,
                    _counts(passed=gate_evidence["runs"][0]["counts"]["passed"]),
                )
            elif gate_evidence["status"] == "NOT RUN":
                expected_shape = (
                    "NOT RUN",
                    "NOT_RUN_OBLIGATION",
                    POLICY_EXIT,
                    "EXTERNAL_CHECK_UNAVAILABLE",
                    _counts(),
                )
            else:
                expected_shape = (
                    "FAIL",
                    "POLICY_REJECTION",
                    POLICY_EXIT,
                    "COLLECTION_IDENTITY_DRIFT",
                    _counts(failed=1),
                )
            if (
                result["status"],
                result["classification"],
                result["exit_code"],
                result["reason_code"],
                result["outcomes"],
            ) != expected_shape:
                raise GatePolicyError("hermetic receipt result and matrix disagree")
    elif spec.evidence_kind == "web-gate-run":
        if gate_evidence is None:
            expected_outcomes = {
                (
                    "FAIL",
                    "POLICY_REJECTION",
                    POLICY_EXIT,
                    "GATE_COMMAND_FAILED",
                ): _counts(failed=1),
                (
                    "FAIL",
                    "POLICY_REJECTION",
                    POLICY_EXIT,
                    "GATE_EVIDENCE_INVALID",
                ): _counts(failed=1),
                (
                    "FAIL",
                    "EXECUTION_FAILURE",
                    EXECUTION_EXIT,
                    "GATE_EXECUTION_ERROR",
                ): _counts(errors=1),
                (
                    "NOT RUN",
                    "NOT_RUN_OBLIGATION",
                    POLICY_EXIT,
                    "EXTERNAL_CHECK_UNAVAILABLE",
                ): _counts(),
            }.get(
                (
                    result["status"],
                    result["classification"],
                    result["exit_code"],
                    result["reason_code"],
                )
            )
            if expected_outcomes is None or result["outcomes"] != expected_outcomes:
                raise GatePolicyError("Web receipt lacks gate evidence")
        else:
            if not isinstance(gate_evidence, dict):
                raise GatePolicyError("Web receipt gate evidence is malformed")
            _validate_web_gate_receipt(
                gate_evidence,
                frontend_root=resolved_workspace.require(spec.repository),
                candidate=candidate,
            )
            if (
                result["classification"] != "COMPLETE_PASS"
                or result["reason_code"] is not None
                or result["outcomes"] != _counts(passed=len(WEB_GATE_STEPS))
            ):
                raise GatePolicyError("Web receipt result and evidence disagree")
    else:
        if gate_evidence is not None:
            raise GatePolicyError("gate receipt has unexpected evidence")
        expected_outcomes = {
            ("PASS", "COMPLETE_PASS", 0, None): _counts(passed=1),
            (
                "FAIL",
                "POLICY_REJECTION",
                POLICY_EXIT,
                "GATE_COMMAND_FAILED",
            ): _counts(failed=1),
            (
                "FAIL",
                "EXECUTION_FAILURE",
                EXECUTION_EXIT,
                "GATE_EXECUTION_ERROR",
            ): _counts(errors=1),
        }.get(
            (
                result["status"],
                result["classification"],
                result["exit_code"],
                result["reason_code"],
            )
        )
        if expected_outcomes is None or result["outcomes"] != expected_outcomes:
            raise GatePolicyError("gate receipt result is not registered")
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


def _freeze_json_object(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    try:
        serialized = _canonical_bytes(value)
        frozen = json.loads(
            serialized,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_json,
        )
    except GatePolicyError:
        raise
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise GatePolicyError(f"{label} is not canonical JSON") from exc
    if not isinstance(frozen, dict):
        raise GatePolicyError(f"{label} must be an object")
    return frozen


def classify_formal_children(
    children: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Classify exactly two formal obligations without collapsing NOT RUN into PASS."""
    if len(children) != len(FORMAL_CHILD_GATE_IDS):
        raise GatePolicyError("formal aggregate requires exactly two child receipts")
    kinds: list[str] = []
    for child in children:
        result = child.get("result")
        if not isinstance(result, Mapping):
            raise GatePolicyError("formal child result is malformed")
        status = result.get("status")
        classification = result.get("classification")
        exit_code = result.get("exit_code")
        reason_code = result.get("reason_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise GatePolicyError("formal child exit code is invalid")
        if (status, classification, exit_code, reason_code) == (
            "PASS",
            "COMPLETE_PASS",
            0,
            None,
        ):
            kinds.append("pass")
        elif (
            status == "FAIL"
            and classification == "POLICY_REJECTION"
            and exit_code == POLICY_EXIT
            and isinstance(reason_code, str)
            and bool(reason_code)
        ):
            kinds.append("policy")
        elif (
            status == "FAIL"
            and classification == "EXECUTION_FAILURE"
            and exit_code == EXECUTION_EXIT
            and isinstance(reason_code, str)
            and bool(reason_code)
        ):
            kinds.append("execution")
        elif (status, classification, exit_code, reason_code) == (
            "NOT RUN",
            "NOT_RUN_OBLIGATION",
            POLICY_EXIT,
            "EXTERNAL_CHECK_UNAVAILABLE",
        ):
            kinds.append("not_run")
        else:
            raise GatePolicyError("formal child classification is invalid")

    obligations = {
        "total": len(FORMAL_CHILD_GATE_IDS),
        "passed": kinds.count("pass"),
        "policy_rejected": kinds.count("policy"),
        "execution_failed": kinds.count("execution"),
        "not_run": kinds.count("not_run"),
    }
    if obligations["execution_failed"]:
        result_shape: tuple[str, str, int, str | None] = (
            "FAIL",
            "EXECUTION_FAILURE",
            EXECUTION_EXIT,
            "CHILD_EXECUTION_FAILURE",
        )
    elif obligations["policy_rejected"]:
        result_shape = (
            "FAIL",
            "POLICY_REJECTION",
            POLICY_EXIT,
            "CHILD_POLICY_REJECTION",
        )
    elif obligations["not_run"]:
        result_shape = (
            "NOT RUN",
            "NOT_RUN_OBLIGATION",
            POLICY_EXIT,
            "EXTERNAL_CHECK_UNAVAILABLE",
        )
    else:
        result_shape = ("PASS", "COMPLETE_PASS", 0, None)
    status, classification, exit_code, reason_code = result_shape
    return {
        "status": status,
        "classification": classification,
        "exit_code": exit_code,
        "reason_code": reason_code,
        "obligations": obligations,
    }


def _validate_frozen_web_child_receipt(
    receipt: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    registry: GateRegistry,
    workspace: WorkspaceRoots,
) -> None:
    """Recheck a validated Web child without recreating its deleted dist tree."""
    _require_exact_keys(receipt, _RECEIPT_KEYS, "formal Web child receipt")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise GatePolicyError("formal Web child schema is invalid")
    spec = registry.require("frontend-web-fresh")
    if receipt.get("gate_id") != spec.gate_id or receipt.get("source") != _source(candidate):
        raise GatePolicyError("formal Web child source or gate is invalid")
    if receipt.get("command") != {
        "name": "verify",
        "repository": spec.repository,
        "cwd": spec.cwd,
        "argv": list(spec.argv),
    }:
        raise GatePolicyError("formal Web child command graph is invalid")

    runtime = receipt.get("runtime")
    if not isinstance(runtime, dict) or set(runtime) != {"python", "platform", "clock"}:
        raise GatePolicyError("formal Web child runtime is malformed")
    if not isinstance(runtime["python"], str) or re.fullmatch(
        r"3\.[0-9]+\.[0-9]+", runtime["python"]
    ) is None:
        raise GatePolicyError("formal Web child Python runtime is invalid")
    if not isinstance(runtime["platform"], str) or not runtime["platform"]:
        raise GatePolicyError("formal Web child platform is invalid")
    if runtime["clock"] != receipt.get("started_at"):
        raise GatePolicyError("formal Web child clock identity mismatch")
    started = _parse_utc(receipt.get("started_at"), "formal Web child start")
    ended = _parse_utc(receipt.get("ended_at"), "formal Web child end")
    if ended < started:
        raise GatePolicyError("formal Web child time ordering is invalid")

    inputs = receipt.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != {"artifacts", "configs"}:
        raise GatePolicyError("formal Web child inputs are malformed")
    for label, paths in (("artifacts", spec.artifact_paths), ("configs", spec.config_paths)):
        identities = inputs[label]
        if not isinstance(identities, list) or len(identities) != len(paths):
            raise GatePolicyError(f"formal Web child {label} are incomplete")
        for identity, path in zip(identities, paths, strict=True):
            _validate_identity(identity, _file_identity(workspace, spec.repository, path))

    _validate_result(receipt.get("result"))
    result = receipt["result"]
    evidence = receipt.get("gate_evidence")
    if not isinstance(evidence, dict):
        raise GatePolicyError("formal passing Web child lacks evidence")
    expected_source = _stable_web_source_identity(workspace.require("frontend"))
    _validate_web_gate_receipt_shape(
        evidence,
        candidate=candidate,
        expected_source=expected_source,
    )
    if (
        result["status"],
        result["classification"],
        result["exit_code"],
        result["reason_code"],
        result["outcomes"],
    ) != (
        "PASS",
        "COMPLETE_PASS",
        0,
        None,
        _counts(passed=len(WEB_GATE_STEPS)),
    ):
        raise GatePolicyError("formal Web child result and evidence disagree")
    expected_privacy = {
        "passed": True,
        "scanned_field_count": len(_RECEIPT_KEYS),
        "match_count": 0,
        "environment_values_serialized": False,
        "secret_values_serialized": False,
    }
    if receipt.get("privacy") != expected_privacy:
        raise GatePolicyError("formal Web child privacy evidence is invalid")
    _require_sha(receipt.get("receipt_sha256"), "formal Web child digest")
    if receipt["receipt_sha256"] != canonical_receipt_sha256(receipt):
        raise GatePolicyError("formal Web child digest mismatch")


def _validate_frozen_child_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_gate_id: str,
    candidate: Mapping[str, Any],
    registry: GateRegistry,
    workspace: WorkspaceRoots,
) -> None:
    if receipt.get("gate_id") != expected_gate_id:
        raise GatePolicyError("formal child order is invalid")
    runtime = receipt.get("runtime")
    if (
        not isinstance(runtime, Mapping)
        or not isinstance(runtime.get("platform"), str)
        or runtime["platform"] not in _FORMAL_PLATFORM_WEB_IDENTITIES
    ):
        raise GatePolicyError("formal child platform identity is invalid")
    result = receipt.get("result")
    is_passing_web = (
        expected_gate_id == "frontend-web-fresh"
        and isinstance(result, Mapping)
        and result.get("classification") == "COMPLETE_PASS"
    )
    if is_passing_web:
        _validate_frozen_web_child_receipt(
            receipt,
            candidate=candidate,
            registry=registry,
            workspace=workspace,
        )
        return
    validate_receipt(
        receipt,
        candidate=candidate,
        registry=registry,
        workspace=workspace,
    )


def _formal_inputs(workspace: WorkspaceRoots) -> dict[str, dict[str, Any]]:
    return {
        label: _file_identity(workspace, repository, path)
        for label, repository, path in _FORMAL_INPUT_CONTRACTS
    }


def _formal_privacy() -> dict[str, Any]:
    return {
        "passed": True,
        "scanned_field_count": len(_FORMAL_RECEIPT_KEYS),
        "match_count": 0,
        "environment_values_serialized": False,
        "secret_values_serialized": False,
    }


def _validate_formal_string_privacy(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_formal_string_privacy(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _validate_formal_string_privacy(item)
        return
    if isinstance(value, str) and (
        value.startswith(("/", "\\\\"))
        or re.match(r"^[A-Za-z]:[\\/]", value) is not None
    ):
        raise GatePolicyError("formal receipt contains an absolute host path")


def validate_formal_receipt(
    receipt: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    registry: GateRegistry,
    workspace: WorkspaceRoots,
) -> None:
    validate_candidate(candidate)
    _validate_formal_string_privacy(receipt)
    _require_exact_keys(receipt, _FORMAL_RECEIPT_KEYS, "formal receipt")
    if receipt.get("schema") != FORMAL_RECEIPT_SCHEMA:
        raise GatePolicyError("formal receipt schema is invalid")
    if receipt.get("source") != _source(candidate):
        raise GatePolicyError("formal receipt source identity mismatch")
    if receipt.get("command") != {
        "name": "formal",
        "repository": "backend",
        "cwd": ".",
        "argv": list(_FORMAL_COMMAND_ARGV),
        "gate_ids": list(FORMAL_CHILD_GATE_IDS),
    }:
        raise GatePolicyError("formal receipt command graph mismatch")

    runtime = receipt.get("runtime")
    if not isinstance(runtime, dict) or set(runtime) != {"python", "platform", "clock"}:
        raise GatePolicyError("formal receipt runtime is malformed")
    if not isinstance(runtime["python"], str) or re.fullmatch(
        r"3\.[0-9]+\.[0-9]+", runtime["python"]
    ) is None:
        raise GatePolicyError("formal receipt Python runtime is invalid")
    if not isinstance(runtime["platform"], str) or re.fullmatch(
        r"[A-Za-z0-9_.-]{2,96}", runtime["platform"]
    ) is None or runtime["platform"] not in _FORMAL_PLATFORM_WEB_IDENTITIES:
        raise GatePolicyError("formal receipt platform is invalid")
    if runtime["clock"] != receipt.get("started_at"):
        raise GatePolicyError("formal receipt clock identity mismatch")
    started = _parse_utc(receipt.get("started_at"), "formal receipt start")
    ended = _parse_utc(receipt.get("ended_at"), "formal receipt end")
    if ended < started:
        raise GatePolicyError("formal receipt time ordering is invalid")

    inputs = receipt.get("inputs")
    expected_inputs = _formal_inputs(workspace)
    if not isinstance(inputs, dict) or inputs != expected_inputs:
        raise GatePolicyError("formal receipt input identity mismatch")

    children = receipt.get("children")
    if not isinstance(children, list) or len(children) != len(FORMAL_CHILD_GATE_IDS):
        raise GatePolicyError("formal receipt children are incomplete")
    validated_children: list[Mapping[str, Any]] = []
    child_times: list[tuple[datetime, datetime]] = []
    for child, expected_gate_id in zip(children, FORMAL_CHILD_GATE_IDS, strict=True):
        if not isinstance(child, dict):
            raise GatePolicyError("formal child receipt is malformed")
        _validate_frozen_child_receipt(
            child,
            expected_gate_id=expected_gate_id,
            candidate=candidate,
            registry=registry,
            workspace=workspace,
        )
        child_start = _parse_utc(child.get("started_at"), "formal child start")
        child_end = _parse_utc(child.get("ended_at"), "formal child end")
        if child_start < started or child_end > ended:
            raise GatePolicyError("formal child time is outside aggregate bounds")
        child_times.append((child_start, child_end))
        validated_children.append(child)
        if child["runtime"]["python"] != runtime["python"]:
            raise GatePolicyError("formal child Python runtime differs from aggregate")
        if child["runtime"]["platform"] != runtime["platform"]:
            raise GatePolicyError("formal child platform differs from aggregate")
        if expected_gate_id == "frontend-web-fresh" and isinstance(
            child.get("gate_evidence"), Mapping
        ):
            web_runtime = child["gate_evidence"].get("runtime")
            expected_web_runtime = _FORMAL_PLATFORM_WEB_IDENTITIES[runtime["platform"]]
            if not isinstance(web_runtime, Mapping) or (
                web_runtime.get("platform"),
                web_runtime.get("arch"),
            ) != expected_web_runtime:
                raise GatePolicyError("formal Web runtime differs from aggregate")
    if child_times[1][0] < child_times[0][1]:
        raise GatePolicyError("formal child lifetimes overlap")

    expected_result = classify_formal_children(validated_children)
    if receipt.get("result") != expected_result:
        raise GatePolicyError("formal receipt result does not match child obligations")
    if receipt.get("production") != {
        "infrastructure": "NOT RUN",
        "deploy": "NOT RUN",
        "smoke": "NOT RUN",
        "rollback": "NOT RUN",
    }:
        raise GatePolicyError("formal receipt production evidence is invalid")
    if receipt.get("privacy") != _formal_privacy():
        raise GatePolicyError("formal receipt privacy evidence is invalid")
    _require_sha(receipt.get("receipt_sha256"), "formal receipt digest")
    if receipt["receipt_sha256"] != canonical_receipt_sha256(receipt):
        raise GatePolicyError("formal receipt digest mismatch")


def run_formal_gate(
    *,
    candidate: Mapping[str, Any],
    registry: GateRegistry,
    operations: GateOperations,
    workspace: WorkspaceRoots,
) -> dict[str, Any]:
    validate_live_candidate(candidate, workspace=workspace, operations=operations)
    started_at = operations.now_utc()
    inputs = _formal_inputs(workspace)
    children: list[dict[str, Any]] = []
    for gate_id in FORMAL_CHILD_GATE_IDS:
        child = run_registered_gate(
            gate_id=gate_id,
            command_name="verify",
            candidate=candidate,
            registry=registry,
            operations=operations,
            workspace=workspace,
        )
        validate_live_candidate(candidate, workspace=workspace, operations=operations)
        _validate_frozen_child_receipt(
            child,
            expected_gate_id=gate_id,
            candidate=candidate,
            registry=registry,
            workspace=workspace,
        )
        children.append(child)

    ended_at = operations.now_utc()
    receipt: dict[str, Any] = {
        "schema": FORMAL_RECEIPT_SCHEMA,
        "source": _source(candidate),
        "command": {
            "name": "formal",
            "repository": "backend",
            "cwd": ".",
            "argv": list(_FORMAL_COMMAND_ARGV),
            "gate_ids": list(FORMAL_CHILD_GATE_IDS),
        },
        "runtime": {
            "python": operations.python_version(),
            "platform": operations.platform_identity(),
            "clock": started_at,
        },
        "inputs": inputs,
        "children": children,
        "result": classify_formal_children(children),
        "production": {
            "infrastructure": "NOT RUN",
            "deploy": "NOT RUN",
            "smoke": "NOT RUN",
            "rollback": "NOT RUN",
        },
        "privacy": _formal_privacy(),
        "started_at": started_at,
        "ended_at": ended_at,
    }
    receipt["receipt_sha256"] = canonical_receipt_sha256(receipt)
    validate_formal_receipt(
        receipt,
        candidate=candidate,
        registry=registry,
        workspace=workspace,
    )
    validate_live_candidate(candidate, workspace=workspace, operations=operations)
    return receipt


def run_registered_gate(
    *,
    gate_id: str,
    command_name: str,
    candidate: Mapping[str, Any],
    registry: GateRegistry,
    operations: GateOperations,
    workspace: WorkspaceRoots | None = None,
) -> dict[str, Any]:
    source_workspace = workspace or default_workspace_roots()
    validate_live_candidate(
        candidate,
        workspace=source_workspace,
        operations=operations,
    )
    with materialize_candidate_workspace(
        candidate,
        source_workspace=source_workspace,
        operations=operations,
    ) as snapshot:
        validate_live_candidate(
            candidate,
            workspace=source_workspace,
            operations=operations,
        )
        receipt = _run_registered_gate_on_snapshot(
            gate_id=gate_id,
            command_name=command_name,
            candidate=candidate,
            registry=registry,
            operations=operations,
            workspace=snapshot,
            source_workspace=source_workspace,
        )
        validate_receipt(
            receipt,
            candidate=candidate,
            registry=registry,
            workspace=snapshot,
        )
        return _freeze_json_object(receipt, "registered gate receipt")


def write_json(value: object, path: Path | None) -> None:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(text)
        return
    resolved = path if path.is_absolute() else ROOT / path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=resolved.parent,
        prefix=f".{resolved.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, resolved)
    finally:
        temporary.unlink(missing_ok=True)


def _open_formal_parent(output: Path) -> int:
    if not output.is_absolute() or output.name in {"", ".", ".."}:
        raise GatePolicyError("formal output path is invalid")
    descriptor = -1
    try:
        parent_metadata = output.parent.lstat()
        if not stat.S_ISDIR(parent_metadata.st_mode) or stat.S_ISLNK(
            parent_metadata.st_mode
        ):
            raise GatePolicyError("formal output parent is not a directory")
        descriptor = os.open(
            output.parent,
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
        )
        if not _same_file_metadata(parent_metadata, os.fstat(descriptor)):
            raise GatePolicyError("formal output parent changed during inspection")
        return descriptor
    except GatePolicyError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise GatePolicyError("formal output parent is unavailable") from exc


def _authoritative_source_roots() -> set[Path]:
    return {
        ROOT.resolve(strict=True),
        (ROOT.parent / "stoa-frontend").resolve(strict=False),
        (ROOT.parent / "stoa-infra").resolve(strict=False),
    }


def _require_formal_external_target(output: Path, protected_roots: set[Path]) -> None:
    if any(output == root or root in output.parents for root in protected_roots):
        raise GatePolicyError("formal output must be outside source repositories")


def _require_private_formal_parent(output: Path, descriptor: int) -> None:
    try:
        path_metadata = output.parent.lstat()
        opened_metadata = os.fstat(descriptor)
    except OSError as exc:
        raise GatePolicyError("formal output parent is unavailable") from exc
    if (
        not stat.S_ISDIR(path_metadata.st_mode)
        or stat.S_ISLNK(path_metadata.st_mode)
        or not _same_file_metadata(path_metadata, opened_metadata)
        or stat.S_IMODE(opened_metadata.st_mode) != 0o700
        or (hasattr(os, "getuid") and opened_metadata.st_uid != os.getuid())
    ):
        raise GatePolicyError("formal output parent is not private")


def _unlink_formal_target(output: Path, parent_descriptor: int) -> None:
    try:
        metadata = os.stat(
            output.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    except OSError as exc:
        raise GatePolicyError("formal output target is unavailable") from exc
    if stat.S_ISDIR(metadata.st_mode):
        raise GatePolicyError("formal output target is a directory")
    try:
        os.unlink(output.name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
    except OSError as exc:
        raise GatePolicyError("formal stale output invalidation failed") from exc


def _invalidate_formal_output(output: Path) -> None:
    parent_descriptor = _open_formal_parent(output)
    try:
        _unlink_formal_target(output, parent_descriptor)
        _require_private_formal_parent(output, parent_descriptor)
    finally:
        os.close(parent_descriptor)


def publish_formal_receipt(
    receipt: Mapping[str, Any],
    output: Path,
    *,
    before_replace: Callable[[], None],
) -> None:
    """Publish one formal receipt through a private, durable atomic replacement."""
    try:
        output = output.parent.resolve(strict=True) / output.name
    except OSError as exc:
        raise GatePolicyError("formal output parent is unavailable") from exc
    _require_formal_external_target(output, _authoritative_source_roots())
    try:
        content = (
            json.dumps(
                receipt,
                allow_nan=False,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GatePolicyError("formal receipt output is not canonical JSON") from exc
    if not content or len(content) > 16 * 1024 * 1024:
        raise GatePolicyError("formal receipt output size is invalid")
    parent_descriptor = _open_formal_parent(output)
    temporary_descriptor = -1
    temporary_name: str | None = None
    published = False
    try:
        _unlink_formal_target(output, parent_descriptor)
        _require_private_formal_parent(output, parent_descriptor)
        for _ in range(32):
            candidate_name = f".{output.name}.{os.urandom(16).hex()}.tmp"
            try:
                temporary_descriptor = os.open(
                    candidate_name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | os.O_NOFOLLOW
                    | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate_name
            break
        if temporary_descriptor < 0 or temporary_name is None:
            raise GatePolicyError("formal temporary output cannot be created")
        os.fchmod(temporary_descriptor, 0o600)
        remaining = memoryview(content)
        while remaining:
            written = os.write(temporary_descriptor, remaining)
            if written <= 0:
                raise GatePolicyError("formal receipt write was incomplete")
            remaining = remaining[written:]
        os.fsync(temporary_descriptor)
        temporary_metadata = os.fstat(temporary_descriptor)
        if (
            not stat.S_ISREG(temporary_metadata.st_mode)
            or temporary_metadata.st_nlink != 1
            or stat.S_IMODE(temporary_metadata.st_mode) != 0o600
            or (
                hasattr(os, "getuid")
                and temporary_metadata.st_uid != os.getuid()
            )
        ):
            raise GatePolicyError("formal temporary output is not private")

        before_replace()
        _require_private_formal_parent(output, parent_descriptor)
        path_metadata = os.stat(
            temporary_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not _same_file_metadata(temporary_metadata, path_metadata):
            raise GatePolicyError("formal temporary output changed before publication")
        os.replace(
            temporary_name,
            output.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
        _require_private_formal_parent(output, parent_descriptor)
        published_metadata = os.stat(
            output.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(published_metadata.st_mode)
            or published_metadata.st_nlink != 1
            or stat.S_IMODE(published_metadata.st_mode) != 0o600
            or published_metadata.st_size != len(content)
            or (
                hasattr(os, "getuid")
                and published_metadata.st_uid != os.getuid()
            )
            or (
                published_metadata.st_dev,
                published_metadata.st_ino,
                published_metadata.st_size,
                published_metadata.st_mtime_ns,
            )
            != (
                temporary_metadata.st_dev,
                temporary_metadata.st_ino,
                temporary_metadata.st_size,
                temporary_metadata.st_mtime_ns,
            )
        ):
            raise GatePolicyError("formal published output is not exact")
        published = True
    except GatePolicyError:
        raise
    except OSError as exc:
        raise GatePolicyError("formal receipt publication failed") from exc
    finally:
        if temporary_descriptor >= 0:
            os.close(temporary_descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except OSError:
                pass
        if not published:
            try:
                os.unlink(output.name, dir_fd=parent_descriptor)
            except OSError:
                pass
            try:
                os.fsync(parent_descriptor)
            except OSError:
                pass
        os.close(parent_descriptor)


def _requested_root_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        Path(args.backend_root) if getattr(args, "backend_root", None) else ROOT,
        Path(args.frontend_root)
        if getattr(args, "frontend_root", None)
        else ROOT.parent / "stoa-frontend",
        Path(args.infra_root)
        if getattr(args, "infra_root", None)
        else ROOT.parent / "stoa-infra",
    )


def _prepare_external_output(args: argparse.Namespace) -> Path | None:
    if not args.output:
        return None
    requested = Path(args.output)
    if not requested.is_absolute():
        raise GatePolicyError("candidate and gate output must be an absolute external path")
    if requested.is_symlink():
        raise GatePolicyError("candidate and gate output cannot be a symlink")
    resolved = requested.resolve(strict=False)
    protected_roots = {ROOT.resolve(), *(root.resolve(strict=False) for root in _requested_root_paths(args))}
    if any(resolved == root or root in resolved.parents for root in protected_roots):
        raise GatePolicyError("candidate and gate output must be outside source repositories")
    candidate_path = getattr(args, "candidate", None)
    if candidate_path and resolved == Path(candidate_path).resolve(strict=False):
        raise GatePolicyError("gate output cannot replace its candidate input")
    if resolved.is_dir():
        raise GatePolicyError("gate output path is a directory")
    resolved.unlink(missing_ok=True)
    return resolved


def _prepare_formal_output(args: argparse.Namespace) -> Path:
    requested = Path(args.output)
    if not requested.is_absolute():
        raise GatePolicyError("formal output must be an absolute external path")
    try:
        parent = requested.parent.resolve(strict=True)
    except OSError as exc:
        raise GatePolicyError("formal output parent is unavailable") from exc
    resolved = parent / requested.name
    protected_roots = {
        *_authoritative_source_roots(),
        *(root.resolve(strict=False) for root in _requested_root_paths(args)),
    }
    _require_formal_external_target(resolved, protected_roots)
    if resolved == Path(args.candidate).resolve(strict=False):
        raise GatePolicyError("formal output cannot replace its candidate input")
    _invalidate_formal_output(resolved)
    return resolved


def _workspace_from_args(args: argparse.Namespace) -> WorkspaceRoots:
    backend, frontend, infra = _requested_root_paths(args)
    return WorkspaceRoots.from_mapping(
        {"backend": backend, "frontend": frontend, "infra": infra}
    )


def _execute(args: argparse.Namespace, command_name: str) -> int:
    output = _prepare_external_output(args)
    candidate = load_candidate(Path(args.candidate))
    registry = default_registry()
    workspace = _workspace_from_args(args)
    operations = system_operations()
    gate_id = args.gate if command_name == "verify" else "gate-self-test"
    receipt = run_registered_gate(
        gate_id=gate_id,
        command_name=command_name,
        candidate=candidate,
        registry=registry,
        operations=operations,
        workspace=workspace,
    )
    write_json(receipt, output)
    return int(receipt["result"]["exit_code"])


def _execute_candidate(args: argparse.Namespace) -> int:
    output = _prepare_external_output(args)
    candidate = issue_live_candidate(
        workspace=_workspace_from_args(args),
        operations=system_operations(),
    )
    write_json(candidate, output)
    return 0


def _execute_python_matrix(args: argparse.Namespace) -> int:
    output = _prepare_external_output(args)
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
    write_json(result, output)
    return python_matrix_exit_code(result)


def _execute_formal(args: argparse.Namespace) -> int:
    output = _prepare_formal_output(args)
    workspace = _workspace_from_args(args)
    candidate = load_candidate(Path(args.candidate))
    registry = default_registry()
    operations = system_operations()
    receipt = run_formal_gate(
        candidate=candidate,
        registry=registry,
        operations=operations,
        workspace=workspace,
    )

    def revalidate_before_publication() -> None:
        validate_formal_receipt(
            receipt,
            candidate=candidate,
            registry=registry,
            workspace=workspace,
        )
        validate_live_candidate(candidate, workspace=workspace, operations=operations)

    publish_formal_receipt(
        receipt,
        output,
        before_replace=revalidate_before_publication,
    )
    return int(receipt["result"]["exit_code"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    candidate = subparsers.add_parser(
        "candidate",
        help="Issue one candidate from exact current clean repository state",
    )
    candidate.add_argument("--output")
    candidate.add_argument("--backend-root")
    candidate.add_argument("--frontend-root")
    candidate.add_argument("--infra-root")
    candidate.set_defaults(func=_execute_candidate)

    verify = subparsers.add_parser("verify", help="Run one typed registered release gate")
    verify.add_argument("--candidate", required=True)
    verify.add_argument("--gate", required=True)
    verify.add_argument("--output")
    verify.add_argument("--backend-root")
    verify.add_argument("--frontend-root")
    verify.add_argument("--infra-root")
    verify.set_defaults(func=lambda args: _execute(args, "verify"))

    self_test = subparsers.add_parser("self-test", help="Exercise the authoritative gate path")
    self_test.add_argument("--candidate", required=True)
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

    formal = subparsers.add_parser(
        "formal",
        help="Run the fixed Python and Web release obligations",
        allow_abbrev=False,
    )
    for option in (
        "candidate",
        "backend-root",
        "frontend-root",
        "infra-root",
        "output",
    ):
        formal.add_argument(
            f"--{option}",
            required=True,
            action=_StoreOnceAction,
        )
    formal.set_defaults(func=_execute_formal)
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
