"""Fail-closed, source-bound controller for protected staging release state.

The module deliberately has no AWS SDK dependency.  Plan 474-33 supplies a
read-only provider inventory and Plan 474-34 supplies the separately approved
staging substrate invocation.  This boundary validates their exact JSON
receipts before a staging-only controller can be asked to continue.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
import sys
from typing import Final


INVENTORY_SCHEMA: Final = "stoa.release.environment-inventory.v1"
PLAN_SCHEMA: Final = "stoa.release.environment-plan.v1"
RECEIPT_SCHEMA: Final = "stoa.release.environment-receipt.v1"
STAGING: Final = "staging"
_IDENTITY_FIELDS: Final = ("environment", "actor", "repository", "account_id", "region", "stack")
_INVENTORY_FIELDS: Final = frozenset({"schema", *_IDENTITY_FIELDS, "resources"})
_PLAN_FIELDS: Final = frozenset({"schema", *_IDENTITY_FIELDS, "inventory_sha256", "changes"})
_RESOURCE_FIELDS: Final = frozenset({"logical_id", "kind", "physical_id"})
_CHANGE_FIELDS: Final = frozenset({"logical_id", "action", "replacement"})
_POLICY: Final[dict[str, object]] = {
    "schema": "stoa.release.environment-policy.v1",
    "github_environments": [
        "staging",
        "staging-smoke",
        "staging-rollback",
        "production",
        "production-smoke",
        "production-rollback",
    ],
    "sole_owner_self_approval": True,
    "production_mutation": "NOT RUN",
    "staging_substrate": {
        "allowed_stack": "StoaReleaseStaging",
        "allowed_region": "eu-central-2",
        "allowed_repository": "stoasystem/stoa-backend",
        "allowed_resources": {
            "ReleaseAlias": "AWS::Lambda::Alias",
            "ReleaseBucket": "AWS::S3::Bucket",
        },
    },
}


class EnvironmentPolicyError(ValueError):
    """Raised when an untrusted provider receipt cannot authorize staging."""


def default_policy() -> dict[str, object]:
    """Return the closed, reviewable policy without exposing mutable globals."""

    return deepcopy(_POLICY)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _as_closed_mapping(value: object, fields: frozenset[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise EnvironmentPolicyError(f"{label} has unknown or missing fields")
    if not all(isinstance(key, str) for key in value):
        raise EnvironmentPolicyError(f"{label} has non-string fields")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EnvironmentPolicyError(f"{label} must be a non-empty string")
    return value


def _require_sha256(value: object, label: str) -> str:
    text = _require_text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise EnvironmentPolicyError(f"{label} must be a lowercase SHA-256")
    return text


def _validate_identity(receipt: Mapping[str, object], policy: Mapping[str, object]) -> None:
    substrate = policy["staging_substrate"]
    if not isinstance(substrate, Mapping):
        raise EnvironmentPolicyError("closed staging substrate policy is malformed")
    if receipt["environment"] != STAGING:
        raise EnvironmentPolicyError("production or unknown environment is forbidden")
    if receipt["stack"] != substrate["allowed_stack"]:
        raise EnvironmentPolicyError("wrong staging stack")
    if receipt["region"] != substrate["allowed_region"]:
        raise EnvironmentPolicyError("wrong staging region")
    if receipt["repository"] != substrate["allowed_repository"]:
        raise EnvironmentPolicyError("wrong source repository")
    for field in _IDENTITY_FIELDS:
        _require_text(receipt[field], field)
    account_id = _require_text(receipt["account_id"], "account id")
    if len(account_id) != 12 or not account_id.isdecimal():
        raise EnvironmentPolicyError("account id must be an exact twelve digit identity")


def _validate_inventory(value: object, policy: Mapping[str, object]) -> Mapping[str, object]:
    inventory = _as_closed_mapping(value, _INVENTORY_FIELDS, "environment inventory")
    if inventory["schema"] != INVENTORY_SCHEMA:
        raise EnvironmentPolicyError("environment inventory schema is not recognized")
    _validate_identity(inventory, policy)
    resources = inventory["resources"]
    if not isinstance(resources, list) or not resources:
        raise EnvironmentPolicyError("resource inventory must be a non-empty list")
    substrate = policy["staging_substrate"]
    if not isinstance(substrate, Mapping) or not isinstance(substrate["allowed_resources"], Mapping):
        raise EnvironmentPolicyError("closed resource policy is malformed")
    allowed = substrate["allowed_resources"]
    observed: set[str] = set()
    for resource in resources:
        row = _as_closed_mapping(resource, _RESOURCE_FIELDS, "resource inventory row")
        logical_id = _require_text(row["logical_id"], "resource logical id")
        kind = _require_text(row["kind"], "resource kind")
        _require_text(row["physical_id"], "resource physical id")
        if logical_id in observed or allowed.get(logical_id) != kind:
            raise EnvironmentPolicyError("resource inventory contains an unknown or duplicate resource")
        observed.add(logical_id)
    if observed != set(allowed):
        raise EnvironmentPolicyError("resource inventory is incomplete")
    return inventory


def _validate_plan(value: object, inventory: Mapping[str, object], policy: Mapping[str, object]) -> Mapping[str, object]:
    plan = _as_closed_mapping(value, _PLAN_FIELDS, "environment plan")
    if plan["schema"] != PLAN_SCHEMA:
        raise EnvironmentPolicyError("environment plan schema is not recognized")
    _validate_identity(plan, policy)
    for field in _IDENTITY_FIELDS:
        if plan[field] != inventory[field]:
            raise EnvironmentPolicyError(f"plan {field} drifts from inventory")
    if _require_sha256(plan["inventory_sha256"], "inventory sha256") != _canonical_sha256(inventory):
        raise EnvironmentPolicyError("plan is not bound to the exact inventory")
    changes = plan["changes"]
    if not isinstance(changes, list) or not changes:
        raise EnvironmentPolicyError("plan changes must be a non-empty list")
    resources = inventory["resources"]
    if not isinstance(resources, list):
        raise EnvironmentPolicyError("resource inventory must be a list")
    known = {
        _require_text(_as_closed_mapping(row, _RESOURCE_FIELDS, "resource inventory row")["logical_id"], "resource logical id")
        for row in resources
    }
    planned: set[str] = set()
    for change in changes:
        row = _as_closed_mapping(change, _CHANGE_FIELDS, "plan change")
        logical_id = _require_text(row["logical_id"], "change logical id")
        action = _require_text(row["action"], "change action")
        if logical_id not in known:
            raise EnvironmentPolicyError("plan contains an unknown resource")
        if logical_id in planned:
            raise EnvironmentPolicyError("plan contains duplicate resources")
        planned.add(logical_id)
        if action != "Modify":
            raise EnvironmentPolicyError("destructive or unknown change action is forbidden")
        if row["replacement"] is not False:
            raise EnvironmentPolicyError("replacement change is forbidden")
    return plan


def _receipt(operation: str, inventory: Mapping[str, object], plan: Mapping[str, object]) -> dict[str, object]:
    inventory_sha256 = _canonical_sha256(inventory)
    return {
        "schema": RECEIPT_SCHEMA,
        "status": "PASS",
        "operation": operation,
        "environment": STAGING,
        "inventory_sha256": inventory_sha256,
        "plan_sha256": _canonical_sha256(plan),
        "confirmation_sha256": _canonical_sha256(
            {"inventory_sha256": inventory_sha256, "plan_sha256": _canonical_sha256(plan), "operation": operation}
        ),
        "production_mutation": "NOT RUN",
    }


def plan_staging(inventory_value: object, plan_value: object) -> dict[str, object]:
    """Validate a read-only inventory and return a source-bound staging plan receipt."""

    policy = default_policy()
    inventory = _validate_inventory(inventory_value, policy)
    plan = _validate_plan(plan_value, inventory, policy)
    return _receipt("plan", inventory, plan)


def apply_staging(
    receipt: object,
    inventory_value: object,
    plan_value: object,
    *,
    readback: object,
) -> dict[str, object]:
    """Revalidate a prior plan plus provider readback; never issue provider commands."""

    policy = default_policy()
    inventory = _validate_inventory(inventory_value, policy)
    plan = _validate_plan(plan_value, inventory, policy)
    previous = _as_closed_mapping(
        receipt,
        frozenset({"schema", "status", "operation", "environment", "inventory_sha256", "plan_sha256", "confirmation_sha256", "production_mutation"}),
        "plan receipt",
    )
    expected = _receipt("plan", inventory, plan)
    if dict(previous) != expected:
        raise EnvironmentPolicyError("plan receipt is not an exact reviewed confirmation")
    try:
        confirmed = _validate_inventory(readback, policy)
    except EnvironmentPolicyError as error:
        raise EnvironmentPolicyError("provider readback drift or partial success is forbidden") from error
    if _canonical_sha256(confirmed) != _canonical_sha256(inventory):
        raise EnvironmentPolicyError("provider readback drift or partial success is forbidden")
    return _receipt("apply", inventory, plan)


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EnvironmentPolicyError("controller JSON input is unavailable or malformed") from error


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    if path.exists() and path.is_symlink():
        raise EnvironmentPolicyError("controller output path may not be a symlink")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan-staging")
    plan.add_argument("--inventory", required=True, type=Path)
    plan.add_argument("--plan", required=True, type=Path)
    plan.add_argument("--output", required=True, type=Path)
    apply = commands.add_parser("apply-staging")
    apply.add_argument("--receipt", required=True, type=Path)
    apply.add_argument("--inventory", required=True, type=Path)
    apply.add_argument("--plan", required=True, type=Path)
    apply.add_argument("--readback", required=True, type=Path)
    apply.add_argument("--output", required=True, type=Path)
    verify = commands.add_parser("verify-staging")
    verify.add_argument("--receipt", required=True, type=Path)
    verify.add_argument("--inventory", required=True, type=Path)
    verify.add_argument("--plan", required=True, type=Path)
    verify.add_argument("--readback", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run only local receipt validation; provider execution stays out of this module."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "plan-staging":
            _write_json(args.output, plan_staging(_load_json(args.inventory), _load_json(args.plan)))
            return 0
        applied = apply_staging(
            _load_json(args.receipt),
            _load_json(args.inventory),
            _load_json(args.plan),
            readback=_load_json(args.readback),
        )
        if args.command == "apply-staging":
            _write_json(args.output, applied)
            return 0
        if applied["production_mutation"] != "NOT RUN":
            raise EnvironmentPolicyError("production mutation must remain not run")
        return 0
    except EnvironmentPolicyError as error:
        print(f"release-environment: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
