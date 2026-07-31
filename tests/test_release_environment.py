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
