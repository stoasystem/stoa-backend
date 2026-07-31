"""Fail-closed contract for the protected staging environment controller."""

from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "release_environment.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("release_environment", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inventory() -> dict[str, object]:
    return {
        "schema": "stoa.release.environment-inventory.v1",
        "environment": "staging",
        "actor": "github-actions:stoa-backend:staging",
        "repository": "stoasystem/stoa-backend",
        "account_id": "123456789012",
        "region": "eu-central-2",
        "stack": "StoaReleaseStaging",
        "resources": [
            {"logical_id": "ReleaseAlias", "kind": "AWS::Lambda::Alias", "physical_id": "alias-1"},
            {"logical_id": "ReleaseBucket", "kind": "AWS::S3::Bucket", "physical_id": "bucket-1"},
        ],
    }


def _plan() -> dict[str, object]:
    return {
        "schema": "stoa.release.environment-plan.v1",
        "environment": "staging",
        "actor": "github-actions:stoa-backend:staging",
        "repository": "stoasystem/stoa-backend",
        "account_id": "123456789012",
        "region": "eu-central-2",
        "stack": "StoaReleaseStaging",
        "inventory_sha256": _digest(_inventory()),
        "changes": [
            {"logical_id": "ReleaseAlias", "action": "Modify", "replacement": False},
        ],
    }


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_plan_accepts_only_allowlisted_staging_modify_and_binds_inventory() -> None:
    module = _load_module()

    receipt = module.plan_staging(_inventory(), _plan())

    assert receipt["status"] == "PASS"
    assert receipt["environment"] == "staging"
    assert receipt["inventory_sha256"] == _digest(_inventory())
    assert receipt["confirmation_sha256"] != receipt["inventory_sha256"]
    assert receipt["production_mutation"] == "NOT RUN"


@pytest.mark.parametrize(
    ("target", "mutation", "message"),
    [
        ("plan", ("environment", "production"), "production"),
        ("plan", ("account_id", "999999999999"), "account"),
        ("inventory", ("resources", []), "resource inventory"),
        ("plan", ("changes", [{"logical_id": "Unknown", "action": "Modify", "replacement": False}]), "unknown"),
        ("plan", ("changes", [{"logical_id": "ReleaseAlias", "action": "Remove", "replacement": False}]), "destructive"),
        ("plan", ("changes", [{"logical_id": "ReleaseAlias", "action": "Modify", "replacement": True}]), "replacement"),
    ],
)
def test_plan_rejects_unreviewed_or_destructive_state(
    target: str, mutation: tuple[str, object], message: str
) -> None:
    module = _load_module()
    inventory = _inventory()
    plan = _plan()
    if target == "inventory":
        inventory[mutation[0]] = mutation[1]
    else:
        plan[mutation[0]] = mutation[1]

    with pytest.raises(module.EnvironmentPolicyError, match=message):
        module.plan_staging(inventory, plan)


def test_apply_revalidates_readback_and_never_accepts_partial_success() -> None:
    module = _load_module()
    inventory = _inventory()
    plan = _plan()
    receipt = module.plan_staging(inventory, plan)

    result = module.apply_staging(receipt, inventory, plan, readback=_inventory())
    assert result["status"] == "PASS"
    assert result["operation"] == "apply"
    assert result["production_mutation"] == "NOT RUN"

    bad_readback = _inventory()
    resources = bad_readback["resources"]
    assert isinstance(resources, list)
    bad_readback["resources"] = resources[:1]
    with pytest.raises(module.EnvironmentPolicyError, match="drift"):
        module.apply_staging(receipt, inventory, plan, readback=bad_readback)


def test_environment_policy_is_closed_and_allows_one_owner_self_approval() -> None:
    module = _load_module()
    policy = module.default_policy()

    assert policy["github_environments"] == [
        "staging",
        "staging-smoke",
        "staging-rollback",
        "production",
        "production-smoke",
        "production-rollback",
    ]
    assert policy["sole_owner_self_approval"] is True
    assert policy["production_mutation"] == "NOT RUN"
    assert policy["staging_substrate"]["allowed_stack"] == "StoaReleaseStaging"


def test_cli_only_validates_local_receipts_and_fails_closed(tmp_path: Path) -> None:
    inventory_path = tmp_path / "inventory.json"
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "receipt.json"
    output_path = tmp_path / "output.json"
    inventory_path.write_text(json.dumps(_inventory()), encoding="utf-8")
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")

    planned = subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            str(MODULE_PATH),
            "plan-staging",
            "--inventory",
            str(inventory_path),
            "--plan",
            str(plan_path),
            "--output",
            str(receipt_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert planned.returncode == 0, planned.stderr
    applied = subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            str(MODULE_PATH),
            "apply-staging",
            "--receipt",
            str(receipt_path),
            "--inventory",
            str(inventory_path),
            "--plan",
            str(plan_path),
            "--readback",
            str(inventory_path),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert applied.returncode == 0, applied.stderr
    assert json.loads(output_path.read_text(encoding="utf-8"))["operation"] == "apply"


def _source_ref(name: str, commit: str) -> dict[str, object]:
    return {
        "schema": "stoa.release.source-ref.v1",
        "name": name,
        "commit": commit,
        "tree": "a" * 40,
        "lock_path": "package-lock.json" if name == "frontend" else "uv.lock",
        "lock_sha256": "b" * 64,
        "approval": {
            "provenance": "project-owner-explicit-codex-instruction",
            "approved_at": "2026-07-31T12:00:00Z",
            "scope": ["local-auditable-source-ref-receipts-only"],
        },
    }


def _live_inventory() -> dict[str, object]:
    return {
        "schema": "stoa.release.environment-observation.v1",
        "status": "PASS",
        "source": {
            "frontend": _source_ref("frontend", "c" * 40),
            "infra": _source_ref("infra", "d" * 40),
        },
        "github": {
            "repository": "stoasystem/stoa-backend",
            "environments": [
                {"name": name, "branch_policy": "main-only", "protection": "required"}
                for name in (
                    "staging",
                    "staging-smoke",
                    "staging-rollback",
                    "production",
                    "production-smoke",
                    "production-rollback",
                )
            ],
            "oidc_subjects": [
                f"repo:stoasystem/stoa-backend:environment:{name}"
                for name in (
                    "staging",
                    "staging-smoke",
                    "staging-rollback",
                    "production",
                    "production-smoke",
                    "production-rollback",
                )
            ],
            "request_sha256": "e" * 64,
        },
        "aws": {
            "account_id": "123456789012",
            "region": "eu-central-2",
            "stack": "StoaReleaseStaging",
            "stack_sha256": "f" * 64,
            "resources": [
                {"logical_id": "ReleaseAlias", "kind": "AWS::Lambda::Alias", "physical_id_sha256": "1" * 64},
                {"logical_id": "ReleaseBucket", "kind": "AWS::S3::Bucket", "physical_id_sha256": "2" * 64},
                {"logical_id": "ReleaseDistribution", "kind": "AWS::CloudFront::Distribution", "physical_id_sha256": "3" * 64},
                {"logical_id": "ReleaseRole", "kind": "AWS::IAM::Role", "physical_id_sha256": "4" * 64},
            ],
            "request_sha256": "5" * 64,
        },
        "cdk": {
            "infra_commit": "d" * 40,
            "infra_tree": "a" * 40,
            "infra_lock_sha256": "b" * 64,
            "diff_sha256": "6" * 64,
            "changes": [
                {"logical_id": "ReleaseAlias", "action": "Modify", "replacement": False},
                {"logical_id": "ReleaseBucket", "action": "Modify", "replacement": False},
            ],
        },
        "production": {
            "infrastructure": "NOT RUN",
            "deploy": "NOT RUN",
            "smoke": "NOT RUN",
            "rollback": "NOT RUN",
        },
    }


def test_live_inventory_is_closed_source_bound_and_rejects_unsafe_diff(tmp_path: Path) -> None:
    module = _load_module()
    receipt = _live_inventory()
    frontend_ref = _source_ref("frontend", "c" * 40)
    infra_ref = _source_ref("infra", "d" * 40)

    module.verify_inventory(receipt, frontend_ref, infra_ref)

    cdk = receipt["cdk"]
    assert isinstance(cdk, dict)
    cdk["changes"] = [{"logical_id": "ReleaseAlias", "action": "Modify", "replacement": True}]
    with pytest.raises(module.EnvironmentPolicyError, match="replacement"):
        module.verify_inventory(receipt, frontend_ref, infra_ref)

    receipt_path = tmp_path / "receipt.json"
    frontend_path = tmp_path / "frontend.json"
    infra_path = tmp_path / "infra.json"
    receipt_path.write_text(json.dumps(_live_inventory()), encoding="utf-8")
    frontend_path.write_text(json.dumps(frontend_ref), encoding="utf-8")
    infra_path.write_text(json.dumps(infra_ref), encoding="utf-8")
    verified = subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            str(MODULE_PATH),
            "verify-inventory",
            "--receipt",
            str(receipt_path),
            "--frontend-ref",
            str(frontend_path),
            "--infra-ref",
            str(infra_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert verified.returncode == 0, verified.stderr


def _protected_environment_receipt() -> dict[str, object]:
    environments = (
        "staging",
        "staging-smoke",
        "staging-rollback",
        "production",
        "production-smoke",
        "production-rollback",
    )
    production = {"production", "production-smoke", "production-rollback"}
    return {
        "schema": "stoa.release.protected-environments-receipt.v1",
        "status": "PASS",
        "observed_at": "2026-07-31T12:00:00Z",
        "repository": "stoasystem/stoa-backend",
        "actor": {
            "login": "DengZhiyuan-math",
            "id": 125728853,
            "repository_permission": "admin",
            "repository_admin": True,
        },
        "readback": {
            "environments": [
                {
                    "name": name,
                    "branch_policies": [{"name": "main", "type": "branch"}],
                    "reviewers": ([{"type": "User", "id": 125728853}] if name in production else []),
                    "prevent_self_review": False,
                }
                for name in environments
            ],
            "main_branch_protection": {
                "branch": "main",
                "protected": True,
                "enforce_admins": True,
                "allow_force_pushes": False,
                "allow_deletions": False,
            },
            "rulesets": [
                {
                    "target": "branch",
                    "enforcement": "active",
                    "ref_name_include": ["refs/heads/main"],
                    "rules": ["deletion", "non_fast_forward"],
                }
            ],
            "oidc_subjects": [f"repo:stoasystem/stoa-backend:environment:{name}" for name in environments],
        },
        "mutation": {
            "github_configuration": "PASS",
            "application": "NOT RUN",
            "infrastructure": "NOT RUN",
            "staging_deploy": "NOT RUN",
            "production_deploy": "NOT RUN",
            "production_smoke": "NOT RUN",
            "production_rollback": "NOT RUN",
        },
        "production_mutation": "NOT RUN",
    }


def test_verify_github_accepts_an_exact_authenticated_protected_environment_readback() -> None:
    module = _load_module()

    module.verify_github(_live_inventory(), _protected_environment_receipt(), module.default_policy())
