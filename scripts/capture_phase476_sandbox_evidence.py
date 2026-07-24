#!/usr/bin/env python3
"""Validate and publish redacted Phase 476 Stripe sandbox evidence.

This command never calls Stripe and never turns local fixtures into provider
proof. It accepts only an observation produced by the separately gated real
browser/provider run, verifies its source and preflight bindings, rejects false
passing states, and publishes an immutable redacted receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Never


MAX_INPUT_BYTES = 1_000_000
SCHEMA = "phase476.stripe_sandbox.v1"
OBSERVATION_SCHEMA = "phase476.stripe_sandbox.observation.v1"
PREFLIGHT_SCHEMA = "stoa.stripe-sandbox-preflight.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
SECRET_RE = re.compile(r"(?i)(sk_(?:test|live)_|whsec_|bearer\s+|xox[baprs]-)")

ROOT_KEYS = frozenset(
    {"schema", "runId", "observedAt", "source", "browser", "provider", "operation", "safety"}
)
SOURCE_KEYS = frozenset(
    {
        "backendSha",
        "frontendSha",
        "acceptanceSourceSha256",
        "collectorSourceSha256",
        "preflightReceiptSha256",
    }
)
BROWSER_KEYS = frozenset(
    {
        "project",
        "hostedCheckoutOrigin",
        "mockCheckout",
        "routeInterception",
        "returnStates",
        "createAttempts",
        "recheckAttempts",
        "parentProjectionSha256",
        "adminProjectionSha256",
        "projectionsAgree",
        "adminProjectionRedacted",
    }
)
PROVIDER_KEYS = frozenset(
    {
        "environment",
        "keyMode",
        "livemode",
        "priceModes",
        "checkoutSessionId",
        "invoiceId",
        "subscriptionId",
        "eventIds",
        "signedEventDestination",
        "webhookSignaturesVerified",
        "eventDestinationVersion",
        "redeliverySource",
        "redeliveryObserved",
        "outOfOrderObserved",
        "duplicateDeliveryObserved",
    }
)
OPERATION_KEYS = frozenset(
    {
        "checkoutRef",
        "idempotencyKeyDigest",
        "checkoutCommandCount",
        "checkoutSessionCount",
        "activationCount",
        "activationVersion",
        "grantVersions",
        "allowanceVersions",
        "supportStateVersions",
        "factLifecycle",
    }
)
SAFETY_KEYS = frozenset(
    {
        "liveChargeCount",
        "productionMutationCount",
        "testChargeCount",
        "containsSecrets",
        "containsPii",
    }
)
FACT_KEYS = frozenset(
    {
        "kind",
        "factVersion",
        "providerEventIdDigest",
        "providerObjectIdDigest",
        "signatureVerified",
        "providerLivemode",
    }
)
PRICE_MODES = frozenset({"student", "teacher_supported", "family"})


class EvidenceError(RuntimeError):
    """Closed failure with a safe stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def fail(code: str) -> Never:
    raise EvidenceError(code)


def mapping(value: object, code: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        fail(code)
    return {str(key): member for key, member in value.items()}


def exact_keys(value: Mapping[str, object], expected: frozenset[str], code: str) -> None:
    if set(value) != expected:
        fail(code)


def required_text(value: object, code: str, *, maximum: int = 512) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not 1 <= len(value) <= maximum
        or "\x00" in value
        or "\n" in value
        or "\r" in value
    ):
        fail(code)
    return value


def required_bool(value: object, code: str) -> bool:
    if type(value) is not bool:
        fail(code)
    return value


def exact_count(value: object, code: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if type(value) is not int or not minimum <= value <= (1 << 63) - 1:
        fail(code)
    return value


def digest(value: object, code: str) -> str:
    candidate = required_text(value, code, maximum=64)
    if SHA256_RE.fullmatch(candidate) is None:
        fail(code)
    return candidate


def sequence(value: object, code: str) -> list[object]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) == 0
    ):
        fail(code)
    return list(value)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def safe_input_file(path: Path) -> bytes:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or not 1 <= info.st_size <= MAX_INPUT_BYTES
        ):
            fail("INPUT_BOUNDARY_INVALID")
        return path.read_bytes()
    except EvidenceError:
        raise
    except OSError:
        fail("INPUT_BOUNDARY_INVALID")


def read_json(path: Path) -> tuple[dict[str, object], bytes]:
    raw = safe_input_file(path)
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail("INPUT_JSON_INVALID")
    return mapping(parsed, "INPUT_JSON_INVALID"), raw


def git_sha(root: Path) -> str:
    try:
        value = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        fail("SOURCE_BINDING_MISMATCH")
    if GIT_SHA_RE.fullmatch(value) is None:
        fail("SOURCE_BINDING_MISMATCH")
    return value


def resolve_source_files(
    backend_root: Path,
    frontend_root: Path,
) -> tuple[Path, Path, Path]:
    try:
        backend = backend_root.resolve(strict=True)
        frontend = frontend_root.resolve(strict=True)
    except OSError:
        fail("SOURCE_BINDING_MISMATCH")
    if not backend.is_dir() or not frontend.is_dir():
        fail("SOURCE_BINDING_MISMATCH")
    acceptance = frontend / "tests" / "e2e" / "billing-paid-access.spec.ts"
    preflight = frontend / "scripts" / "stripe-sandbox-preflight.mjs"
    collector = backend / "scripts" / "capture_phase476_sandbox_evidence.py"
    for candidate in (acceptance, preflight, collector):
        safe_input_file(candidate)
    return acceptance, preflight, collector


def validate_preflight(
    preflight: Mapping[str, object],
    *,
    preflight_raw: bytes,
    preflight_source: Path,
    acceptance_source: Path,
) -> None:
    if (
        preflight.get("schema") != PREFLIGHT_SCHEMA
        or preflight.get("status") != "PASS"
        or preflight.get("mockDisabled") is not True
        or preflight.get("routeInterceptionDisabled") is not True
        or preflight.get("keyMode") != "test"
    ):
        fail("PREFLIGHT_NOT_PASSING")
    price_modes = mapping(preflight.get("priceModes"), "PREFLIGHT_NOT_PASSING")
    if set(price_modes) != PRICE_MODES or any(value != "test" for value in price_modes.values()):
        fail("PREFLIGHT_NOT_PASSING")
    if preflight.get("enabledPaymentMethods") != ["card"]:
        fail("PREFLIGHT_NOT_PASSING")
    if preflight.get("acceptanceSourceSha256") != sha256_bytes(safe_input_file(acceptance_source)):
        fail("SOURCE_BINDING_MISMATCH")
    if preflight.get("sourceSha256") != sha256_bytes(safe_input_file(preflight_source)):
        fail("SOURCE_BINDING_MISMATCH")
    if len(preflight_raw) == 0:
        fail("PREFLIGHT_NOT_PASSING")


def validate_source(
    source: Mapping[str, object],
    *,
    backend_root: Path,
    frontend_root: Path,
    acceptance_source: Path,
    collector_source: Path,
    preflight_raw: bytes,
) -> dict[str, str]:
    exact_keys(source, SOURCE_KEYS, "OBSERVATION_SCHEMA_INVALID")
    expected = {
        "backendSha": git_sha(backend_root.resolve()),
        "frontendSha": git_sha(frontend_root.resolve()),
        "acceptanceSourceSha256": sha256_bytes(safe_input_file(acceptance_source)),
        "collectorSourceSha256": sha256_bytes(safe_input_file(collector_source)),
        "preflightReceiptSha256": sha256_bytes(preflight_raw),
    }
    if any(source.get(key) != value for key, value in expected.items()):
        fail("SOURCE_BINDING_MISMATCH")
    return expected


def validate_browser(value: Mapping[str, object]) -> dict[str, object]:
    exact_keys(value, BROWSER_KEYS, "OBSERVATION_SCHEMA_INVALID")
    if value.get("project") != "stripe-sandbox":
        fail("MOCK_EVIDENCE_FORBIDDEN")
    if required_bool(value.get("mockCheckout"), "OBSERVATION_SCHEMA_INVALID"):
        fail("MOCK_EVIDENCE_FORBIDDEN")
    if required_bool(value.get("routeInterception"), "OBSERVATION_SCHEMA_INVALID"):
        fail("INTERCEPTED_EVIDENCE_FORBIDDEN")
    if value.get("hostedCheckoutOrigin") != "https://checkout.stripe.com":
        fail("CHECKOUT_NOT_HOSTED")
    states = sequence(value.get("returnStates"), "OBSERVATION_SCHEMA_INVALID")
    if states != ["confirming", "active"]:
        fail("JOINT_PROOF_MISSING")
    if exact_count(value.get("createAttempts"), "OBSERVATION_SCHEMA_INVALID", positive=True) < 2:
        fail("EXACT_ONCE_PROOF_FAILED")
    if exact_count(value.get("recheckAttempts"), "OBSERVATION_SCHEMA_INVALID", positive=True) < 2:
        fail("EXACT_ONCE_PROOF_FAILED")
    parent_hash = digest(value.get("parentProjectionSha256"), "OBSERVATION_SCHEMA_INVALID")
    admin_hash = digest(value.get("adminProjectionSha256"), "OBSERVATION_SCHEMA_INVALID")
    if required_bool(value.get("projectionsAgree"), "OBSERVATION_SCHEMA_INVALID") is not True:
        fail("JOINT_PROOF_MISSING")
    if (
        required_bool(value.get("adminProjectionRedacted"), "OBSERVATION_SCHEMA_INVALID")
        is not True
    ):
        fail("REDACTION_PROOF_FAILED")
    return {
        "parentProjectionSha256": parent_hash,
        "adminProjectionSha256": admin_hash,
    }


def provider_id(value: object, prefix: str) -> str:
    candidate = required_text(value, "PROVIDER_EVIDENCE_INVALID")
    if not candidate.startswith(prefix) or PROVIDER_ID_RE.fullmatch(candidate) is None:
        fail("PROVIDER_EVIDENCE_INVALID")
    return candidate


def validate_provider(
    value: Mapping[str, object],
    preflight: Mapping[str, object],
) -> dict[str, object]:
    exact_keys(value, PROVIDER_KEYS, "OBSERVATION_SCHEMA_INVALID")
    if value.get("environment") != preflight.get("environment"):
        fail("PROVIDER_EVIDENCE_INVALID")
    if value.get("keyMode") != "test":
        fail("TEST_MODE_REQUIRED")
    if required_bool(value.get("livemode"), "PROVIDER_EVIDENCE_INVALID"):
        fail("LIVE_PROVIDER_OBJECT_FORBIDDEN")
    price_modes = mapping(value.get("priceModes"), "PROVIDER_EVIDENCE_INVALID")
    if price_modes != preflight.get("priceModes"):
        fail("TEST_MODE_REQUIRED")
    if (
        value.get("signedEventDestination") is not True
        or value.get("webhookSignaturesVerified") is not True
    ):
        fail("SIGNED_DELIVERY_REQUIRED")
    if value.get("eventDestinationVersion") != preflight.get("eventDestinationVersion"):
        fail("PROVIDER_EVIDENCE_INVALID")
    if value.get("redeliverySource") not in {"stripe_workbench", "stripe_api"}:
        fail("REDELIVERY_PROOF_REQUIRED")
    if value.get("redeliveryObserved") is not True:
        fail("REDELIVERY_PROOF_REQUIRED")
    if value.get("outOfOrderObserved") is not True:
        fail("EVENT_ORDER_PROOF_REQUIRED")
    if value.get("duplicateDeliveryObserved") is not True:
        fail("EVENT_DEDUPE_PROOF_REQUIRED")

    event_ids = [
        provider_id(event_id, "evt_")
        for event_id in sequence(value.get("eventIds"), "PROVIDER_EVIDENCE_INVALID")
    ]
    if len(event_ids) < 2 or len(set(event_ids)) != len(event_ids):
        fail("PROVIDER_EVIDENCE_INVALID")
    return {
        "checkoutSessionId": provider_id(value.get("checkoutSessionId"), "cs_test_"),
        "invoiceId": provider_id(value.get("invoiceId"), "in_"),
        "subscriptionId": provider_id(value.get("subscriptionId"), "sub_"),
        "eventIds": event_ids,
        "environment": required_text(value.get("environment"), "PROVIDER_EVIDENCE_INVALID"),
        "eventDestinationVersion": required_text(
            value.get("eventDestinationVersion"), "PROVIDER_EVIDENCE_INVALID"
        ),
        "priceModes": price_modes,
    }


def validate_version_map(value: object, code: str) -> tuple[list[str], list[int]]:
    versions = mapping(value, code)
    if not 1 <= len(versions) <= 3:
        fail(code)
    keys: list[str] = []
    numbers: list[int] = []
    for key, version in versions.items():
        keys.append(required_text(key, code))
        numbers.append(exact_count(version, code, positive=True))
    if len(set(numbers)) != 1:
        fail(code)
    return keys, sorted(set(numbers))


def validate_facts(value: object) -> list[dict[str, object]]:
    facts = sequence(value, "JOINT_PROOF_MISSING")
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in facts:
        fact = mapping(raw, "JOINT_PROOF_MISSING")
        exact_keys(fact, FACT_KEYS, "OBSERVATION_SCHEMA_INVALID")
        kind = required_text(fact.get("kind"), "JOINT_PROOF_MISSING")
        if kind in seen:
            fail("EXACT_ONCE_PROOF_FAILED")
        seen.add(kind)
        if fact.get("signatureVerified") is not True:
            fail("SIGNED_DELIVERY_REQUIRED")
        if fact.get("providerLivemode") is not False:
            fail("LIVE_PROVIDER_OBJECT_FORBIDDEN")
        result.append(
            {
                "kind": kind,
                "factVersion": exact_count(
                    fact.get("factVersion"), "JOINT_PROOF_MISSING", positive=True
                ),
                "providerEventIdDigest": digest(
                    fact.get("providerEventIdDigest"), "JOINT_PROOF_MISSING"
                ),
                "providerObjectIdDigest": digest(
                    fact.get("providerObjectIdDigest"), "JOINT_PROOF_MISSING"
                ),
                "signatureVerified": True,
                "providerLivemode": False,
            }
        )
    if not {"invoice_paid", "subscription_active"}.issubset(seen):
        fail("JOINT_PROOF_MISSING")
    return sorted(result, key=lambda fact: str(fact["kind"]))


def validate_operation(value: Mapping[str, object]) -> dict[str, object]:
    exact_keys(value, OPERATION_KEYS, "OBSERVATION_SCHEMA_INVALID")
    if (
        exact_count(value.get("checkoutCommandCount"), "EXACT_ONCE_PROOF_FAILED") != 1
        or exact_count(value.get("checkoutSessionCount"), "EXACT_ONCE_PROOF_FAILED") != 1
        or exact_count(value.get("activationCount"), "EXACT_ONCE_PROOF_FAILED") != 1
    ):
        fail("EXACT_ONCE_PROOF_FAILED")
    activation_version = exact_count(
        value.get("activationVersion"), "EXACT_ONCE_PROOF_FAILED", positive=True
    )
    grant_keys, grant_versions = validate_version_map(
        value.get("grantVersions"), "EXACT_ONCE_PROOF_FAILED"
    )
    allowance_keys, allowance_versions = validate_version_map(
        value.get("allowanceVersions"), "EXACT_ONCE_PROOF_FAILED"
    )
    support_keys, support_versions = validate_version_map(
        value.get("supportStateVersions"), "EXACT_ONCE_PROOF_FAILED"
    )
    if set(grant_keys) != set(allowance_keys) or set(grant_keys) != set(support_keys):
        fail("EXACT_ONCE_PROOF_FAILED")
    facts = validate_facts(value.get("factLifecycle"))
    return {
        "checkoutRef": required_text(value.get("checkoutRef"), "OPERATION_EVIDENCE_INVALID"),
        "idempotencyKeyDigest": digest(
            value.get("idempotencyKeyDigest"), "OPERATION_EVIDENCE_INVALID"
        ),
        "activationVersion": activation_version,
        "grantVersions": grant_versions,
        "allowanceVersions": allowance_versions,
        "supportStateVersions": support_versions,
        "facts": facts,
        "beneficiaryIds": grant_keys,
    }


def validate_safety(value: Mapping[str, object]) -> dict[str, int]:
    exact_keys(value, SAFETY_KEYS, "OBSERVATION_SCHEMA_INVALID")
    live_charges = exact_count(value.get("liveChargeCount"), "LIVE_CHARGE_FORBIDDEN")
    production_mutations = exact_count(
        value.get("productionMutationCount"), "PRODUCTION_MUTATION_FORBIDDEN"
    )
    test_charges = exact_count(
        value.get("testChargeCount"), "SAFETY_EVIDENCE_INVALID", positive=True
    )
    if live_charges != 0:
        fail("LIVE_CHARGE_FORBIDDEN")
    if production_mutations != 0:
        fail("PRODUCTION_MUTATION_FORBIDDEN")
    if value.get("containsSecrets") is not False or value.get("containsPii") is not False:
        fail("REDACTION_PROOF_FAILED")
    return {
        "liveChargeCount": live_charges,
        "productionMutationCount": production_mutations,
        "testChargeCount": test_charges,
    }


def scan_sensitive(value: object) -> None:
    if isinstance(value, Mapping):
        for member in value.values():
            scan_sensitive(member)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for member in value:
            scan_sensitive(member)
    elif isinstance(value, str) and (
        SECRET_RE.search(value) is not None or EMAIL_RE.search(value) is not None
    ):
        fail("REDACTION_PROOF_FAILED")


def redact_identifiers(
    provider: Mapping[str, object],
    operation: Mapping[str, object],
) -> dict[str, object]:
    return {
        "checkoutSessionSha256": sha256_text(str(provider["checkoutSessionId"])),
        "invoiceSha256": sha256_text(str(provider["invoiceId"])),
        "subscriptionSha256": sha256_text(str(provider["subscriptionId"])),
        "eventSha256": sorted(
            sha256_text(str(event_id))
            for event_id in provider["eventIds"]  # type: ignore[union-attr]
        ),
        "checkoutRefSha256": sha256_text(str(operation["checkoutRef"])),
        "beneficiarySha256": sorted(
            sha256_text(str(beneficiary))
            for beneficiary in operation["beneficiaryIds"]  # type: ignore[union-attr]
        ),
        "idempotencyKeyDigest": operation["idempotencyKeyDigest"],
    }


def publish(output: Path, evidence_dir: Path, receipt: Mapping[str, object]) -> None:
    try:
        directory = evidence_dir.resolve(strict=True)
        if not directory.is_dir() or directory.is_symlink():
            fail("OUTPUT_BOUNDARY_INVALID")
        if output.parent.resolve(strict=True) != directory or output.is_symlink():
            fail("OUTPUT_BOUNDARY_INVALID")
        payload = (
            json.dumps(
                receipt,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )
        descriptor = os.open(
            output,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except EvidenceError:
        raise
    except FileExistsError:
        fail("OUTPUT_NOT_EXCLUSIVE")
    except OSError:
        fail("OUTPUT_BOUNDARY_INVALID")


def collect(args: argparse.Namespace) -> dict[str, object]:
    observation, _ = read_json(Path(args.observation))
    preflight, preflight_raw = read_json(Path(args.preflight_receipt))
    exact_keys(observation, ROOT_KEYS, "OBSERVATION_SCHEMA_INVALID")
    if observation.get("schema") != OBSERVATION_SCHEMA:
        fail("OBSERVATION_SCHEMA_INVALID")
    scan_sensitive(observation)

    backend_root = Path(args.backend_root)
    frontend_root = Path(args.frontend_root)
    acceptance_source, preflight_source, collector_source = resolve_source_files(
        backend_root, frontend_root
    )
    validate_preflight(
        preflight,
        preflight_raw=preflight_raw,
        preflight_source=preflight_source,
        acceptance_source=acceptance_source,
    )
    source = validate_source(
        mapping(observation.get("source"), "OBSERVATION_SCHEMA_INVALID"),
        backend_root=backend_root,
        frontend_root=frontend_root,
        acceptance_source=acceptance_source,
        collector_source=collector_source,
        preflight_raw=preflight_raw,
    )
    browser = validate_browser(mapping(observation.get("browser"), "OBSERVATION_SCHEMA_INVALID"))
    provider = validate_provider(
        mapping(observation.get("provider"), "OBSERVATION_SCHEMA_INVALID"),
        preflight,
    )
    operation = validate_operation(
        mapping(observation.get("operation"), "OBSERVATION_SCHEMA_INVALID")
    )
    safety = validate_safety(mapping(observation.get("safety"), "OBSERVATION_SCHEMA_INVALID"))

    run_id = required_text(observation.get("runId"), "OBSERVATION_SCHEMA_INVALID")
    if not run_id.startswith("phase476-run-"):
        fail("OBSERVATION_SCHEMA_INVALID")
    observed_at = required_text(
        observation.get("observedAt"), "OBSERVATION_SCHEMA_INVALID", maximum=64
    )
    exact_once = {
        "activationCount": 1,
        "allowanceVersions": operation["allowanceVersions"],
        "checkoutCommandCount": 1,
        "checkoutSessionCount": 1,
        "grantVersions": operation["grantVersions"],
        "supportStateVersions": operation["supportStateVersions"],
    }
    receipt: dict[str, object] = {
        "schema": SCHEMA,
        "status": "PASS",
        "runId": run_id,
        "observedAt": observed_at,
        "source": source,
        "preflightReceiptSha256": source["preflightReceiptSha256"],
        "mocked": False,
        "livemode": False,
        "environment": provider["environment"],
        "priceModes": provider["priceModes"],
        "eventDestinationVersion": provider["eventDestinationVersion"],
        "identifiers": redact_identifiers(provider, operation),
        "browser": browser,
        "factLifecycle": operation["facts"],
        "activationVersion": operation["activationVersion"],
        "exactOnce": exact_once,
        "liveChargeCount": safety["liveChargeCount"],
        "productionMutationCount": safety["productionMutationCount"],
        "testChargeCount": safety["testChargeCount"],
        "proofSelectors": {
            "adminProjectionRedacted": True,
            "duplicateDeliveryObserved": True,
            "hostedCheckoutObserved": True,
            "jointActivationProofObserved": True,
            "outOfOrderObserved": True,
            "parentAdminProjectionAgreement": True,
            "redactionScanPassed": True,
            "signedProviderDeliveryObserved": True,
            "sourceBindingVerified": True,
        },
    }
    scan_sensitive(receipt)
    return receipt


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(add_help=False)
    result.add_argument("--observation", required=True)
    result.add_argument("--preflight-receipt", required=True)
    result.add_argument("--frontend-root", required=True)
    result.add_argument("--backend-root", required=True)
    result.add_argument("--evidence-dir", required=True)
    result.add_argument("--output", required=True)
    return result


def main() -> int:
    try:
        args = parser().parse_args()
        receipt = collect(args)
        publish(Path(args.output), Path(args.evidence_dir), receipt)
    except EvidenceError as exc:
        print(f"PHASE476_SANDBOX_EVIDENCE_ERROR:{exc.code}", file=sys.stderr)
        return 1
    except (SystemExit, Exception):
        print(
            "PHASE476_SANDBOX_EVIDENCE_ERROR:UNEXPECTED_FAILURE",
            file=sys.stderr,
        )
        return 1
    print("PHASE476_SANDBOX_EVIDENCE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
