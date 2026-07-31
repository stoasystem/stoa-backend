#!/usr/bin/env python3
"""Fail-closed durable staging coordinator for Lambda and served-Web pointers.

This module intentionally defines no AWS client.  The deployment adapter owns the
provider calls and must make its writes conditional on the exact coordinates passed
here.  Keeping that boundary narrow makes an interrupted two-pointer operation a
durable compensation transaction rather than an atomicity claim.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
import re
from typing import Protocol, TypeAlias


Transaction: TypeAlias = dict[str, object]
Pointer: TypeAlias = dict[str, object]
Smoke = Callable[[Pointer], Mapping[str, object]]

SCHEMA = "stoa.release.promotion-transaction.v1"
STAGING = "staging"
TERMINAL_STATES = frozenset({"COMMITTED", "ROLLED_BACK", "PARTIAL_FAILURE"})
STATES = frozenset({"PREPARED", "APPLYING", "SMOKING", *TERMINAL_STATES, "COMPENSATING"})
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OBJECT_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")


class DeliveryPolicyError(ValueError):
    """Raised before a provider action when release evidence is incomplete."""


class TransactionStore(Protocol):
    """Durable transaction storage with create-if-absent and state CAS."""

    def create(self, transaction: Transaction) -> Transaction: ...

    def replace(self, transaction: Transaction, expected_state: str) -> Transaction: ...


class DeliveryAdapter(Protocol):
    """Preconditioned provider operations; implementations must read exact values."""

    def read(self) -> Pointer: ...

    def write_lambda(self, target: Pointer, expected: Pointer) -> None: ...

    def write_descriptor(self, target: Pointer, expected: Pointer) -> None: ...


def _copy_transaction(value: Mapping[str, object]) -> Transaction:
    return deepcopy(dict(value))


def _require_keys(value: object, keys: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise DeliveryPolicyError(f"{label} fields are not closed")
    return value


def _require_id(value: object, label: str) -> str:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        raise DeliveryPolicyError(f"{label} is malformed")
    return value


def _require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise DeliveryPolicyError(f"{label} is malformed")
    return value


def _validate_object(value: object, label: str) -> None:
    item = _require_keys(value, {"key", "version_id", "sha256"}, label)
    key = item["key"]
    if not isinstance(key, str) or OBJECT_KEY_RE.fullmatch(key) is None:
        raise DeliveryPolicyError(f"{label} key is malformed")
    _require_id(item["version_id"], f"{label} version")
    _require_sha(item["sha256"], f"{label} digest")


def _validate_lambda(value: object) -> None:
    item = _require_keys(
        value,
        {"function", "alias", "version", "code_sha256", "revision_id"},
        "Lambda pointer",
    )
    for field in ("function", "alias", "version", "revision_id"):
        _require_id(item[field], f"Lambda {field}")
    if item["alias"] != STAGING:
        raise DeliveryPolicyError("Lambda alias is not staging")
    _require_sha(item["code_sha256"], "Lambda code digest")


def validate_pointer(value: object) -> Pointer:
    pointer = _require_keys(
        value,
        {"lambda", "descriptor", "runtime_config", "web"},
        "release pointer",
    )
    _validate_lambda(pointer["lambda"])
    _validate_object(pointer["descriptor"], "served descriptor")
    _validate_object(pointer["runtime_config"], "runtime config")
    _validate_object(pointer["web"], "Web object")
    return _copy_transaction(pointer)


def validate_transaction(value: Mapping[str, object]) -> Transaction:
    transaction = _require_keys(
        value,
        {
            "schema", "transaction_id", "idempotency_key", "release_id", "manifest_sha256",
            "environment", "actor_id", "run_id", "request_id", "state", "previous", "target",
            "actions", "smoke", "failure",
        },
        "promotion transaction",
    )
    if transaction["schema"] != SCHEMA or transaction["environment"] != STAGING:
        raise DeliveryPolicyError("production or unknown delivery environment is forbidden")
    for field in ("transaction_id", "idempotency_key", "actor_id", "run_id", "request_id"):
        _require_id(transaction[field], field)
    _require_sha(transaction["release_id"], "release id")
    _require_sha(transaction["manifest_sha256"], "manifest digest")
    if transaction["state"] not in STATES:
        raise DeliveryPolicyError("transaction state is invalid")
    previous = validate_pointer(transaction["previous"])
    target = validate_pointer(transaction["target"])
    if previous == target:
        raise DeliveryPolicyError("previous and target pointers must differ")
    actions = transaction["actions"]
    if not isinstance(actions, list):
        raise DeliveryPolicyError("transaction actions are malformed")
    if transaction["smoke"] is not None and not isinstance(transaction["smoke"], dict):
        raise DeliveryPolicyError("transaction smoke evidence is malformed")
    if transaction["failure"] is not None and not isinstance(transaction["failure"], dict):
        raise DeliveryPolicyError("transaction failure evidence is malformed")
    return _copy_transaction(transaction)


def _same_immutable(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    names = (
        "schema", "transaction_id", "idempotency_key", "release_id", "manifest_sha256",
        "environment", "actor_id", "run_id", "request_id", "previous", "target",
    )
    return all(left.get(name) == right.get(name) for name in names)


def _append_action(transaction: Transaction, kind: str, outcome: str) -> None:
    actions = transaction["actions"]
    if not isinstance(actions, list):
        raise DeliveryPolicyError("transaction actions are malformed")
    actions.append({"kind": kind, "outcome": outcome})


def _replace(store: TransactionStore, transaction: Transaction, state: str) -> Transaction:
    previous_state = transaction["state"]
    if not isinstance(previous_state, str):
        raise DeliveryPolicyError("transaction state is invalid")
    transaction["state"] = state
    return validate_transaction(store.replace(transaction, previous_state))


def _failure(reason_code: str, observed: Pointer | None = None) -> dict[str, object]:
    result: dict[str, object] = {"reason_code": reason_code}
    if observed is not None:
        result["observed"] = deepcopy(observed)
    return result


def _read_pointer(delivery: DeliveryAdapter) -> Pointer:
    return validate_pointer(delivery.read())


def _finalize_without_mutation(
    transaction: Transaction, store: TransactionStore, reason_code: str, observed: Pointer
) -> Transaction:
    transaction["failure"] = _failure(reason_code, observed)
    return _replace(store, transaction, "PARTIAL_FAILURE")


def _compensate(
    transaction: Transaction,
    *,
    store: TransactionStore,
    delivery: DeliveryAdapter,
    reason_code: str,
) -> Transaction:
    transaction = _replace(store, transaction, "COMPENSATING")
    retained_failure = transaction.get("failure")
    try:
        observed = _read_pointer(delivery)
        previous = validate_pointer(transaction["previous"])
        target = validate_pointer(transaction["target"])
        lambda_now = observed["lambda"]
        if lambda_now not in (previous["lambda"], target["lambda"]):
            raise DeliveryPolicyError("Lambda compensation coordinate is unknown")
        if observed["descriptor"] != previous["descriptor"] or observed["runtime_config"] != previous["runtime_config"] or observed["web"] != previous["web"]:
            delivery.write_descriptor(previous, observed)
            _append_action(transaction, "served_descriptor_restore", "RESTORED")
        else:
            _append_action(transaction, "served_descriptor_restore", "ALREADY_PREVIOUS")
        observed = _read_pointer(delivery)
        if observed["lambda"] != previous["lambda"]:
            delivery.write_lambda(previous, observed)
            _append_action(transaction, "lambda_alias_restore", "RESTORED")
        else:
            _append_action(transaction, "lambda_alias_restore", "ALREADY_PREVIOUS")
        restored = _read_pointer(delivery)
        if restored != previous:
            raise DeliveryPolicyError("compensation read-back differs")
    except (DeliveryPolicyError, RuntimeError):
        transaction["failure"] = _failure("COMPENSATION_FAILED")
        return _replace(store, transaction, "PARTIAL_FAILURE")
    if (
        isinstance(retained_failure, dict)
        and retained_failure.get("reason_code") == reason_code
    ):
        transaction["failure"] = deepcopy(retained_failure)
    else:
        transaction["failure"] = _failure(reason_code, observed)
    return _replace(store, transaction, "ROLLED_BACK")


def promote_staging(
    candidate: Mapping[str, object], *, store: TransactionStore, delivery: DeliveryAdapter, smoke: Smoke
) -> Transaction:
    """Apply an exact staging release, or restore the recorded known-good pointers."""
    requested = validate_transaction(candidate)
    stored = validate_transaction(store.create(requested))
    if not _same_immutable(requested, stored):
        raise DeliveryPolicyError("idempotency key is bound to another promotion transaction")
    state = stored["state"]
    if state in TERMINAL_STATES:
        return stored
    if state != "PREPARED":
        raise DeliveryPolicyError("in-progress transaction requires explicit recovery")

    observed = _read_pointer(delivery)
    previous = validate_pointer(stored["previous"])
    if observed != previous:
        return _finalize_without_mutation(stored, store, "STALE_PREVIOUS_POINTER", observed)
    transaction = _replace(store, stored, "APPLYING")
    target = validate_pointer(transaction["target"])
    try:
        delivery.write_lambda(target, previous)
        _append_action(transaction, "lambda_alias_update", "APPLIED")
        observed = _read_pointer(delivery)
        if observed["lambda"] != target["lambda"]:
            transaction["failure"] = _failure("POINTER_READBACK_MISMATCH", observed)
            return _compensate(transaction, store=store, delivery=delivery, reason_code="POINTER_READBACK_MISMATCH")
        delivery.write_descriptor(target, previous)
        _append_action(transaction, "served_descriptor_update", "APPLIED")
        observed = _read_pointer(delivery)
        if observed != target:
            transaction["failure"] = _failure("POINTER_READBACK_MISMATCH", observed)
            return _compensate(transaction, store=store, delivery=delivery, reason_code="POINTER_READBACK_MISMATCH")
    except RuntimeError:
        transaction["failure"] = _failure("POINTER_MUTATION_FAILED")
        return _compensate(transaction, store=store, delivery=delivery, reason_code="POINTER_MUTATION_FAILED")

    transaction = _replace(store, transaction, "SMOKING")
    try:
        smoke_result = dict(smoke(target))
    except Exception:
        smoke_result = {"status": "FAIL", "reason_code": "SMOKE_EXECUTION_FAILED"}
    transaction["smoke"] = smoke_result
    if smoke_result.get("status") != "PASS" or smoke_result.get("release_id") != transaction["release_id"]:
        return _compensate(transaction, store=store, delivery=delivery, reason_code="SMOKE_FAILED")
    return _replace(store, transaction, "COMMITTED")
