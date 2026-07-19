"""Closed release-manifest and tamper-matrix tests for Phase 474."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable

import pytest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "scripts" / "release_manifest.py"
SCHEMA_PATH = ROOT / "schemas" / "release" / "release-manifest-v1.schema.json"
GATE_RECEIPT_SCHEMA_PATH = ROOT / "schemas" / "release" / "gate-receipt-v1.schema.json"
SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64
GIT_A = "1" * 40
GIT_B = "2" * 40
GIT_C = "3" * 40


def _load_manifest_module():
    spec = importlib.util.spec_from_file_location("release_manifest", MANIFEST_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inputs() -> dict[str, Any]:
    return {
        "identity_source": "execution-receipted-git-objects",
        "candidate_execution_identity": SHA256_A,
        "repositories": [
            {
                "name": "backend",
                "commit": GIT_A,
                "tree": GIT_B,
                "lock_path": "uv.lock",
                "lock_sha256": SHA256_A,
                "clean": True,
            },
            {
                "name": "frontend",
                "commit": GIT_B,
                "tree": GIT_C,
                "lock_path": "package-lock.json",
                "lock_sha256": SHA256_B,
                "clean": True,
            },
            {
                "name": "infra",
                "commit": GIT_C,
                "tree": GIT_A,
                "lock_path": "uv.lock",
                "lock_sha256": SHA256_C,
                "clean": True,
            },
        ],
        "runtime": {
            "backend_python": "3.12.13",
            "lambda_runtime": "python3.12",
            "lambda_platform": "manylinux_2_28_aarch64",
            "lambda_architecture": "arm64",
            "web_node": "20.19.4",
            "web_npm": "10.8.2",
            "web_platform": "linux-x64",
        },
        "gates": [
            {
                "gate_id": gate_id,
                "receipt_sha256": f"{index + 4:064x}",
                "run_id": f"run-474-{index + 1:02d}",
                "status": "PASS",
            }
            for index, gate_id in enumerate(
                (
                    "candidate-source",
                    "backend-python-hermetic",
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
            )
        ],
        "artifacts": [
            {
                "name": "backend-lambda-zip",
                "bytes": 100,
                "sha256": SHA256_A,
            },
            {
                "name": "frontend-web-bundle",
                "bytes": 200,
                "sha256": SHA256_B,
            },
        ],
        "configs": [
            {
                "name": "backend-runtime-config",
                "bytes": 10,
                "sha256": SHA256_B,
            },
            {
                "name": "frontend-runtime-config",
                "bytes": 20,
                "sha256": SHA256_C,
            },
        ],
        "production": {
            "infrastructure": "NOT RUN",
            "deploy": "NOT RUN",
            "smoke": "NOT RUN",
            "rollback": "NOT RUN",
        },
    }


def _manifest() -> tuple[Any, dict[str, Any]]:
    module = _load_manifest_module()
    return module, module.build_manifest(_inputs())


def test_schema_is_closed_versioned_and_requires_every_identity() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    receipt_schema = json.loads(GATE_RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    for definition in schema["$defs"].values():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False

    expected_gate_ids = [gate["gate_id"] for gate in _inputs()["gates"]]
    gates = schema["properties"]["gates"]
    assert gates["minItems"] == len(expected_gate_ids) == gates["maxItems"]
    assert [
        schema["$defs"][item["$ref"].removeprefix("#/$defs/")]["properties"][
            "gate_id"
        ]["const"]
        for item in gates["prefixItems"]
    ] == expected_gate_ids
    assert schema["$defs"]["gate"]["properties"]["gate_id"]["enum"] == expected_gate_ids
    assert set(expected_gate_ids) <= set(receipt_schema["properties"]["gate_id"]["enum"])
    assert "gate_backend_standard" not in schema["$defs"]
    assert "gate_backend_future" not in schema["$defs"]
    assert schema["$defs"]["gate_backend_hermetic"]["properties"]["gate_id"] == {
        "const": "backend-python-hermetic"
    }


def test_stable_inputs_produce_one_release_id_and_manifest_digest() -> None:
    module = _load_manifest_module()

    first = module.build_manifest(_inputs())
    second = module.build_manifest(deepcopy(_inputs()))

    assert first == second
    assert len(first["release_id"]) == 64
    assert len(first["manifest_sha256"]) == 64
    module.validate_manifest(first)


def test_release_id_is_non_circular_but_final_digest_binds_bytes() -> None:
    module, manifest = _manifest()
    changed = deepcopy(manifest)
    changed["artifacts"][0]["sha256"] = "f" * 64
    changed["manifest_sha256"] = module.canonical_manifest_sha256(changed)

    assert changed["release_id"] == manifest["release_id"]
    assert changed["manifest_sha256"] != manifest["manifest_sha256"]
    module.validate_manifest(changed)


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("dirty repository", lambda value: value["repositories"][0].__setitem__("clean", False)),
        ("branch identity", lambda value: value["repositories"][0].__setitem__("commit", "main")),
        ("tag identity", lambda value: value["repositories"][1].__setitem__("commit", "v9.0")),
        ("research identity", lambda value: value.__setitem__("identity_source", "research-time-shas")),
        ("mutable artifact", lambda value: value["artifacts"][0].__setitem__("name", "latest")),
        ("unknown gate", lambda value: value["gates"][0].__setitem__("gate_id", "local-green")),
        ("failed gate", lambda value: value["gates"][0].__setitem__("status", "FAIL")),
        ("production pass", lambda value: value["production"].__setitem__("deploy", "PASS")),
        ("unknown field", lambda value: value.__setitem__("branch", "main")),
    ],
)
def test_build_rejects_mutable_dirty_or_unclosed_identity(
    label: str, mutate: Callable[[dict[str, Any]], None]
) -> None:
    module = _load_manifest_module()
    value = _inputs()
    mutate(value)

    with pytest.raises(module.ManifestPolicyError):
        module.build_manifest(value)


def test_build_rejects_duplicate_or_missing_receipts() -> None:
    module = _load_manifest_module()
    duplicate = _inputs()
    duplicate["gates"][1]["gate_id"] = duplicate["gates"][0]["gate_id"]
    with pytest.raises(module.ManifestPolicyError, match="gate inventory"):
        module.build_manifest(duplicate)

    missing = _inputs()
    missing["gates"].pop()
    with pytest.raises(module.ManifestPolicyError, match="gate inventory"):
        module.build_manifest(missing)


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        (
            "legacy standard and future receipts",
            lambda gates: gates.__setitem__(
                slice(1, 2),
                [
                    {
                        "gate_id": "backend-python-standard",
                        "receipt_sha256": "d" * 64,
                        "run_id": "run-474-legacy-standard",
                        "status": "PASS",
                    },
                    {
                        "gate_id": "backend-python-future",
                        "receipt_sha256": "e" * 64,
                        "run_id": "run-474-legacy-future",
                        "status": "PASS",
                    },
                ],
            ),
        ),
        ("missing hermetic receipt", lambda gates: gates.pop(1)),
        ("duplicate hermetic receipt", lambda gates: gates.insert(2, deepcopy(gates[1]))),
        ("reordered hermetic receipt", lambda gates: gates.insert(2, gates.pop(1))),
        (
            "extra gate receipt",
            lambda gates: gates.append(
                {
                    "gate_id": "backend-python-standard",
                    "receipt_sha256": "f" * 64,
                    "run_id": "run-474-extra-standard",
                    "status": "PASS",
                }
            ),
        ),
    ],
)
def test_build_requires_exactly_one_canonical_hermetic_python_receipt(
    label: str, mutate: Callable[[list[dict[str, Any]]], None]
) -> None:
    module = _load_manifest_module()
    value = _inputs()
    mutate(value["gates"])

    with pytest.raises(module.ManifestPolicyError, match="gate inventory"):
        module.build_manifest(value)


@pytest.mark.parametrize(
    "platform",
    (
        "manylinux2014_aarch64",
        "manylinux_2_29_aarch64",
        "manylinux_2_28_x86_64",
    ),
)
def test_build_rejects_lambda_platform_identity_drift(platform: str) -> None:
    module = _load_manifest_module()
    value = _inputs()
    value["runtime"]["lambda_platform"] = platform

    with pytest.raises(module.ManifestPolicyError, match="runtime target or platform"):
        module.build_manifest(value)


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("source", lambda value: value["repositories"][0].__setitem__("tree", GIT_C)),
        ("lock", lambda value: value["repositories"][1].__setitem__("lock_sha256", SHA256_C)),
        ("runtime", lambda value: value["runtime"].__setitem__("backend_python", "3.12.12")),
        ("receipt", lambda value: value["gates"][2].__setitem__("receipt_sha256", SHA256_A)),
        ("artifact", lambda value: value["artifacts"][0].__setitem__("sha256", SHA256_C)),
        ("config", lambda value: value["configs"][1].__setitem__("sha256", SHA256_A)),
    ],
)
def test_any_bound_identity_tamper_invalidates_manifest(
    label: str, mutate: Callable[[dict[str, Any]], None]
) -> None:
    module, manifest = _manifest()
    mutate(manifest)

    with pytest.raises(module.ManifestPolicyError):
        module.validate_manifest(manifest)
