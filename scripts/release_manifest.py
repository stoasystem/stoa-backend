#!/usr/bin/env python3
"""Build and validate one closed, content-bound STOA release manifest."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any


SCHEMA = "stoa.release.manifest.v1"
IDENTITY_SOURCE = "execution-receipted-git-objects"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

REPOSITORY_CONTRACTS = (
    ("backend", "uv.lock"),
    ("frontend", "package-lock.json"),
    ("infra", "uv.lock"),
)
REQUIRED_GATE_IDS = (
    "candidate-source",
    "backend-python-standard",
    "backend-python-future",
    "backend-ruff",
    "backend-mypy",
    "backend-dependencies",
    "frontend-locked-install",
    "frontend-eslint",
    "frontend-typecheck",
    "frontend-build",
    "frontend-dependencies",
    "frontend-contract",
    "frontend-playwright",
    "release-provenance",
    "artifact-integrity",
)
ARTIFACT_NAMES = ("backend-lambda-zip", "frontend-web-bundle")
CONFIG_NAMES = ("backend-runtime-config", "frontend-runtime-config")
PRODUCTION_KEYS = ("infrastructure", "deploy", "smoke", "rollback")

_INPUT_KEYS = {
    "identity_source",
    "candidate_execution_identity",
    "repositories",
    "runtime",
    "gates",
    "artifacts",
    "configs",
    "production",
}
_MANIFEST_KEYS = _INPUT_KEYS | {"schema", "release_id", "manifest_sha256"}
_REPOSITORY_KEYS = {"name", "commit", "tree", "lock_path", "lock_sha256", "clean"}
_RUNTIME_KEYS = {
    "backend_python",
    "lambda_runtime",
    "lambda_platform",
    "lambda_architecture",
    "web_node",
    "web_npm",
    "web_platform",
}
_GATE_KEYS = {"gate_id", "receipt_sha256", "run_id", "status"}
_BYTE_IDENTITY_KEYS = {"name", "bytes", "sha256"}


class ManifestPolicyError(ValueError):
    """Raised when release identity is mutable, incomplete, or tampered."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _require_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ManifestPolicyError(f"{label} fields are not closed")


def _require_sha(value: Any, label: str, *, git: bool = False) -> str:
    pattern = GIT_SHA_RE if git else SHA256_RE
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ManifestPolicyError(f"{label} is malformed")
    return value


def _require_sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise ManifestPolicyError(f"{label} must be an ordered array")
    return value


def _validate_repositories(value: Any) -> list[Mapping[str, Any]]:
    repositories = _require_sequence(value, "repositories")
    if len(repositories) != len(REPOSITORY_CONTRACTS):
        raise ManifestPolicyError("repository inventory is incomplete")
    validated: list[Mapping[str, Any]] = []
    for repository, (expected_name, expected_lock) in zip(
        repositories, REPOSITORY_CONTRACTS, strict=True
    ):
        if not isinstance(repository, dict):
            raise ManifestPolicyError("repository identity is malformed")
        _require_keys(repository, _REPOSITORY_KEYS, f"{expected_name} repository")
        if (
            repository.get("name") != expected_name
            or repository.get("lock_path") != expected_lock
            or repository.get("clean") is not True
        ):
            raise ManifestPolicyError(f"{expected_name} repository identity is invalid")
        _require_sha(repository.get("commit"), f"{expected_name} commit", git=True)
        _require_sha(repository.get("tree"), f"{expected_name} tree", git=True)
        _require_sha(repository.get("lock_sha256"), f"{expected_name} lock")
        validated.append(repository)
    return validated


def _validate_runtime(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ManifestPolicyError("runtime identity is malformed")
    _require_keys(value, _RUNTIME_KEYS, "runtime")
    for key in ("backend_python", "web_node", "web_npm"):
        version = value.get(key)
        if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
            raise ManifestPolicyError(f"runtime {key} is malformed")
    if not str(value["backend_python"]).startswith("3.12."):
        raise ManifestPolicyError("backend Python runtime is not 3.12")
    if not str(value["web_node"]).startswith("20."):
        raise ManifestPolicyError("Web Node runtime is not 20.x")
    expected = {
        "lambda_runtime": "python3.12",
        "lambda_platform": "manylinux_2_28_aarch64",
        "lambda_architecture": "arm64",
        "web_platform": "linux-x64",
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise ManifestPolicyError("runtime target or platform is invalid")
    return value


def _validate_gates(value: Any) -> list[Mapping[str, Any]]:
    gates = _require_sequence(value, "gates")
    if len(gates) != len(REQUIRED_GATE_IDS):
        raise ManifestPolicyError("gate inventory is incomplete")
    receipt_ids: set[str] = set()
    run_ids: set[str] = set()
    for gate, expected_id in zip(gates, REQUIRED_GATE_IDS, strict=True):
        if not isinstance(gate, dict):
            raise ManifestPolicyError("gate inventory is malformed")
        _require_keys(gate, _GATE_KEYS, "gate")
        if gate.get("gate_id") != expected_id or gate.get("status") != "PASS":
            raise ManifestPolicyError("gate inventory is unknown, reordered, or not PASS")
        receipt = _require_sha(gate.get("receipt_sha256"), "gate receipt")
        run_id = gate.get("run_id")
        if (
            not isinstance(run_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}", run_id)
            or receipt in receipt_ids
            or run_id in run_ids
        ):
            raise ManifestPolicyError("gate inventory contains duplicate or malformed receipts")
        receipt_ids.add(receipt)
        run_ids.add(run_id)
    return gates


def _validate_byte_identities(value: Any, names: tuple[str, ...], label: str) -> None:
    identities = _require_sequence(value, label)
    if len(identities) != len(names):
        raise ManifestPolicyError(f"{label} inventory is incomplete")
    seen_digests: set[str] = set()
    for identity, expected_name in zip(identities, names, strict=True):
        if not isinstance(identity, dict):
            raise ManifestPolicyError(f"{label} identity is malformed")
        _require_keys(identity, _BYTE_IDENTITY_KEYS, f"{label} identity")
        size = identity.get("bytes")
        digest = _require_sha(identity.get("sha256"), f"{label} digest")
        if identity.get("name") != expected_name or not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ManifestPolicyError(f"{label} identity is invalid")
        if digest in seen_digests:
            raise ManifestPolicyError(f"{label} digests must identify distinct byte sets")
        seen_digests.add(digest)


def _validate_production(value: Any) -> None:
    if not isinstance(value, dict):
        raise ManifestPolicyError("production obligations are malformed")
    _require_keys(value, set(PRODUCTION_KEYS), "production obligations")
    if any(value[key] != "NOT RUN" for key in PRODUCTION_KEYS):
        raise ManifestPolicyError("production operations must remain exact NOT RUN")


def _validate_payload(value: Mapping[str, Any], *, manifest: bool) -> None:
    _require_keys(value, _MANIFEST_KEYS if manifest else _INPUT_KEYS, "manifest")
    if value.get("identity_source") != IDENTITY_SOURCE:
        raise ManifestPolicyError("manifest source is not execution-receipted")
    _require_sha(value.get("candidate_execution_identity"), "candidate execution identity")
    _validate_repositories(value.get("repositories"))
    _validate_runtime(value.get("runtime"))
    _validate_gates(value.get("gates"))
    _validate_byte_identities(value.get("artifacts"), ARTIFACT_NAMES, "artifact")
    _validate_byte_identities(value.get("configs"), CONFIG_NAMES, "config")
    _validate_production(value.get("production"))


def canonical_release_id(value: Mapping[str, Any]) -> str:
    """Derive a pre-build identity from source, lock, and runtime facts only."""
    stable = {
        "identity_source": value["identity_source"],
        "candidate_execution_identity": value["candidate_execution_identity"],
        "repositories": value["repositories"],
        "runtime": value["runtime"],
    }
    return sha256(_canonical_bytes(stable)).hexdigest()


def canonical_manifest_sha256(value: Mapping[str, Any]) -> str:
    """Bind every final manifest field except the digest itself."""
    stable = {key: item for key, item in value.items() if key != "manifest_sha256"}
    return sha256(_canonical_bytes(stable)).hexdigest()


def build_manifest(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Create and self-validate one deterministic release manifest."""
    _validate_payload(inputs, manifest=False)
    manifest = deepcopy(dict(inputs))
    manifest["schema"] = SCHEMA
    manifest["release_id"] = canonical_release_id(manifest)
    manifest["manifest_sha256"] = canonical_manifest_sha256(manifest)
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Fail closed if any source, receipt, byte, config, or status was changed."""
    _validate_payload(manifest, manifest=True)
    if manifest.get("schema") != SCHEMA:
        raise ManifestPolicyError("manifest schema is invalid")
    _require_sha(manifest.get("release_id"), "release id")
    _require_sha(manifest.get("manifest_sha256"), "manifest digest")
    if manifest["release_id"] != canonical_release_id(manifest):
        raise ManifestPolicyError("release identity mismatch")
    if manifest["manifest_sha256"] != canonical_manifest_sha256(manifest):
        raise ManifestPolicyError("manifest digest mismatch")
