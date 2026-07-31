"""Durable two-pointer release delivery contract tests for Phase 474."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
DELIVERY_PATH = ROOT / "scripts" / "release_delivery.py"
SCHEMA_PATH = ROOT / "schemas" / "release" / "promotion-transaction-v1.schema.json"
SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64
RELEASE_ID = "d" * 64
MANIFEST_SHA = "e" * 64


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("release_delivery", DELIVERY_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _object(key: str, version_id: str, digest: str) -> dict[str, str]:
    return {"key": key, "version_id": version_id, "sha256": digest}


def _pointer(prefix: str, digest: str) -> dict[str, Any]:
    return {
        "lambda": {
            "function": "stoa-api",
            "alias": "staging",
            "version": f"{prefix}-lambda-version",
            "code_sha256": digest,
            "revision_id": f"{prefix}-lambda-revision",
        },
        "descriptor": _object("served-release.json", f"{prefix}-descriptor-version", digest),
        "runtime_config": _object(
            f"releases/{prefix}/runtime-config.json", f"{prefix}-config-version", SHA256_B
        ),
        "web": _object(f"releases/{prefix}/index.html", f"{prefix}-web-version", SHA256_C),
    }


def _transaction() -> dict[str, Any]:
    return {
        "schema": "stoa.release.promotion-transaction.v1",
        "transaction_id": "promotion-474-27-0001",
        "idempotency_key": "promotion-474-27-key-0001",
        "release_id": RELEASE_ID,
        "manifest_sha256": MANIFEST_SHA,
        "environment": "staging",
        "actor_id": "github-actions:stoa-backend:staging",
        "run_id": "run-474-27",
        "request_id": "request-474-27",
        "state": "PREPARED",
        "previous": _pointer("previous", SHA256_A),
        "target": _pointer("target", SHA256_A),
        "actions": [],
        "smoke": None,
        "failure": None,
    }


class _Store:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def create(self, transaction: dict[str, Any]) -> dict[str, Any]:
        key = transaction["idempotency_key"]
        if key not in self.items:
            self.items[key] = deepcopy(transaction)
        return deepcopy(self.items[key])

    def replace(self, transaction: dict[str, Any], expected_state: str) -> dict[str, Any]:
        key = transaction["idempotency_key"]
        current = self.items[key]
        assert current["state"] == expected_state
        self.items[key] = deepcopy(transaction)
        return deepcopy(transaction)


class _Delivery:
    def __init__(self, *, fail: str | None = None, substitute: bool = False) -> None:
        self.pointer = _pointer("previous", SHA256_A)
        self.fail = fail
        self.substitute = substitute
        self.calls: list[str] = []

    def read(self) -> dict[str, Any]:
        return deepcopy(self.pointer)

    def write_lambda(self, target: dict[str, Any], expected: dict[str, Any]) -> None:
        self.calls.append("lambda")
        assert self.pointer["lambda"] == expected["lambda"]
        if self.fail == "lambda":
            raise RuntimeError("lambda write lost")
        self.pointer["lambda"] = deepcopy(target["lambda"])

    def write_descriptor(self, target: dict[str, Any], expected: dict[str, Any]) -> None:
        self.calls.append("descriptor")
        assert self.pointer["descriptor"] == expected["descriptor"]
        if self.fail == "descriptor":
            raise RuntimeError("descriptor write lost")
        self.pointer["descriptor"] = deepcopy(target["descriptor"])
        self.pointer["runtime_config"] = deepcopy(target["runtime_config"])
        self.pointer["web"] = deepcopy(target["web"])
        if self.substitute:
            self.pointer["web"]["version_id"] = "substituted-web-version"


def _passing_smoke(pointer: dict[str, Any]) -> dict[str, str]:
    return {"status": "PASS", "release_id": RELEASE_ID, "descriptor_sha256": pointer["descriptor"]["sha256"]}


def _failing_smoke(pointer: dict[str, Any]) -> dict[str, str]:
    del pointer
    return {"status": "FAIL", "reason_code": "HEALTH_ENDPOINT_FAILED"}


def test_schema_is_closed_and_lists_all_durable_states() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["state"]["enum"] == [
        "PREPARED",
        "APPLYING",
        "SMOKING",
        "COMMITTED",
        "COMPENSATING",
        "ROLLED_BACK",
        "PARTIAL_FAILURE",
    ]
    assert set(schema["$defs"]["pointer"]["required"]) == {
        "lambda",
        "descriptor",
        "runtime_config",
        "web",
    }


def test_staging_promotion_commits_only_after_two_pointers_and_smoke() -> None:
    module = _load_module()
    store = _Store()
    delivery = _Delivery()

    result = module.promote_staging(_transaction(), store=store, delivery=delivery, smoke=_passing_smoke)

    assert result["state"] == "COMMITTED"
    assert delivery.calls == ["lambda", "descriptor"]
    assert delivery.read() == result["target"]
    assert result["smoke"]["status"] == "PASS"
    assert [action["kind"] for action in result["actions"]] == [
        "lambda_alias_update",
        "served_descriptor_update",
    ]


@pytest.mark.parametrize("failure", ("lambda", "descriptor"))
def test_partial_pointer_failure_compensates_both_previous_identities(failure: str) -> None:
    module = _load_module()
    store = _Store()
    delivery = _Delivery(fail=failure)
    original = delivery.read()

    result = module.promote_staging(_transaction(), store=store, delivery=delivery, smoke=_passing_smoke)

    assert result["state"] == "ROLLED_BACK"
    assert result["failure"]["reason_code"] == "POINTER_MUTATION_FAILED"
    assert delivery.read() == original
    assert result["actions"][-2:][0]["kind"] == "served_descriptor_restore"
    assert result["actions"][-1]["kind"] == "lambda_alias_restore"


def test_smoke_failure_retains_failed_coordinates_and_restores_both_pointers() -> None:
    module = _load_module()
    store = _Store()
    delivery = _Delivery()
    original = delivery.read()

    result = module.promote_staging(_transaction(), store=store, delivery=delivery, smoke=_failing_smoke)

    assert result["state"] == "ROLLED_BACK"
    assert result["smoke"] == {"status": "FAIL", "reason_code": "HEALTH_ENDPOINT_FAILED"}
    assert result["failure"]["reason_code"] == "SMOKE_FAILED"
    assert result["target"] == _transaction()["target"]
    assert delivery.read() == original


def test_retry_replays_the_same_committed_transaction_without_mutating_again() -> None:
    module = _load_module()
    store = _Store()
    delivery = _Delivery()

    first = module.promote_staging(_transaction(), store=store, delivery=delivery, smoke=_passing_smoke)
    calls_after_first = list(delivery.calls)
    second = module.promote_staging(_transaction(), store=store, delivery=delivery, smoke=_passing_smoke)

    assert second == first
    assert delivery.calls == calls_after_first


def test_descriptor_selected_config_or_web_substitution_is_retained_partial_failure() -> None:
    module = _load_module()
    store = _Store()
    delivery = _Delivery(substitute=True)

    result = module.promote_staging(_transaction(), store=store, delivery=delivery, smoke=_passing_smoke)

    assert result["state"] == "ROLLED_BACK"
    assert result["failure"]["reason_code"] == "POINTER_READBACK_MISMATCH"
    assert result["failure"]["observed"]["web"]["version_id"] == "substituted-web-version"
    assert delivery.read() == _pointer("previous", SHA256_A)


def test_stale_prepared_pointer_is_rejected_without_mutation() -> None:
    module = _load_module()
    store = _Store()
    delivery = _Delivery()
    delivery.pointer["descriptor"]["version_id"] = "interloper-version"

    result = module.promote_staging(_transaction(), store=store, delivery=delivery, smoke=_passing_smoke)

    assert result["state"] == "PARTIAL_FAILURE"
    assert result["failure"]["reason_code"] == "STALE_PREVIOUS_POINTER"
    assert delivery.calls == []


def test_invalid_or_production_transaction_is_rejected_before_provider_access() -> None:
    module = _load_module()
    store = _Store()
    delivery = _Delivery()
    bad = _transaction()
    bad["environment"] = "production"

    with pytest.raises(module.DeliveryPolicyError, match="production"):
        module.promote_staging(bad, store=store, delivery=delivery, smoke=_passing_smoke)

    assert delivery.calls == []
