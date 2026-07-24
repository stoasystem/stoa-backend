from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = ROOT.parent / "stoa-frontend"
SCRIPT = ROOT / "scripts" / "capture_phase476_sandbox_evidence.py"
ACCEPTANCE_SPEC = FRONTEND_ROOT / "tests" / "e2e" / "billing-paid-access.spec.ts"
PREFLIGHT_SCRIPT = FRONTEND_ROOT / "scripts" / "stripe-sandbox-preflight.mjs"
SHA256 = "a" * 64


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )


def _preflight_receipt() -> dict[str, object]:
    return {
        "schema": "stoa.stripe-sandbox-preflight.v1",
        "status": "PASS",
        "environment": "staging",
        "mockDisabled": True,
        "routeInterceptionDisabled": True,
        "keyMode": "test",
        "priceModes": {
            "student": "test",
            "teacher_supported": "test",
            "family": "test",
        },
        "eventDestinationVersion": "2025-06-30.basil",
        "enabledPaymentMethods": ["card"],
        "objectsVerified": {
            "checkout.session": 1,
            "event": 2,
            "invoice": 1,
            "price": 3,
            "subscription": 1,
        },
        "webOriginSha256": "1" * 64,
        "apiOriginSha256": "2" * 64,
        "accountSha256": "3" * 64,
        "eventDestinationSha256": "4" * 64,
        "acceptanceSourceSha256": _sha256(ACCEPTANCE_SPEC),
        "sourceSha256": _sha256(PREFLIGHT_SCRIPT),
    }


def _observation(preflight_path: Path) -> dict[str, object]:
    return {
        "schema": "phase476.stripe_sandbox.observation.v1",
        "runId": "phase476-run-20260724-a1b2c3d4",
        "observedAt": "2026-07-24T18:00:00Z",
        "source": {
            "backendSha": _git_sha(ROOT),
            "frontendSha": _git_sha(FRONTEND_ROOT),
            "acceptanceSourceSha256": _sha256(ACCEPTANCE_SPEC),
            "collectorSourceSha256": _sha256(SCRIPT),
            "preflightReceiptSha256": _sha256(preflight_path),
        },
        "browser": {
            "project": "stripe-sandbox",
            "hostedCheckoutOrigin": "https://checkout.stripe.com",
            "mockCheckout": False,
            "routeInterception": False,
            "returnStates": ["confirming", "active"],
            "createAttempts": 2,
            "recheckAttempts": 2,
            "parentProjectionSha256": "5" * 64,
            "adminProjectionSha256": "6" * 64,
            "projectionsAgree": True,
            "adminProjectionRedacted": True,
        },
        "provider": {
            "environment": "staging",
            "keyMode": "test",
            "livemode": False,
            "priceModes": {
                "student": "test",
                "teacher_supported": "test",
                "family": "test",
            },
            "checkoutSessionId": "cs_test_phase476_sensitive",
            "invoiceId": "in_phase476_sensitive",
            "subscriptionId": "sub_phase476_sensitive",
            "eventIds": [
                "evt_phase476_invoice_sensitive",
                "evt_phase476_subscription_sensitive",
            ],
            "signedEventDestination": True,
            "webhookSignaturesVerified": True,
            "eventDestinationVersion": "2025-06-30.basil",
            "redeliverySource": "stripe_workbench",
            "redeliveryObserved": True,
            "outOfOrderObserved": True,
            "duplicateDeliveryObserved": True,
        },
        "operation": {
            "checkoutRef": "checkout_public_phase476_sensitive",
            "idempotencyKeyDigest": "7" * 64,
            "checkoutCommandCount": 1,
            "checkoutSessionCount": 1,
            "activationCount": 1,
            "activationVersion": 1,
            "grantVersions": {
                "student-phase476-sensitive-1": 1,
                "student-phase476-sensitive-2": 1,
            },
            "allowanceVersions": {
                "student-phase476-sensitive-1": 1,
                "student-phase476-sensitive-2": 1,
            },
            "supportStateVersions": {
                "student-phase476-sensitive-1": 1,
                "student-phase476-sensitive-2": 1,
            },
            "factLifecycle": [
                {
                    "kind": "subscription_active",
                    "factVersion": 1,
                    "providerEventIdDigest": "8" * 64,
                    "providerObjectIdDigest": "9" * 64,
                    "signatureVerified": True,
                    "providerLivemode": False,
                },
                {
                    "kind": "invoice_paid",
                    "factVersion": 1,
                    "providerEventIdDigest": "a" * 64,
                    "providerObjectIdDigest": "b" * 64,
                    "signatureVerified": True,
                    "providerLivemode": False,
                },
            ],
        },
        "safety": {
            "liveChargeCount": 0,
            "productionMutationCount": 0,
            "testChargeCount": 1,
            "containsSecrets": False,
            "containsPii": False,
        },
    }


def _run_collector(
    tmp_path: Path,
    *,
    mutate_observation=None,
    mutate_preflight=None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True)
    preflight_path = tmp_path / "preflight.json"
    preflight = _preflight_receipt()
    if mutate_preflight is not None:
        mutate_preflight(preflight)
    _write_json(preflight_path, preflight)

    observation = _observation(preflight_path)
    if mutate_observation is not None:
        mutate_observation(observation)
    observation_path = tmp_path / "observation.json"
    _write_json(observation_path, observation)
    output_path = evidence_dir / "phase476-stripe-sandbox-evidence.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--observation",
            str(observation_path),
            "--preflight-receipt",
            str(preflight_path),
            "--frontend-root",
            str(FRONTEND_ROOT),
            "--backend-root",
            str(ROOT),
            "--evidence-dir",
            str(evidence_dir),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, output_path


def _set_path(value: dict[str, object], path: tuple[str, ...], replacement: object) -> None:
    target: dict[str, object] = value
    for part in path[:-1]:
        member = target[part]
        assert isinstance(member, dict)
        target = member
    target[path[-1]] = replacement


def test_collector_emits_source_bound_redacted_pass_receipt(tmp_path: Path) -> None:
    result, output_path = _run_collector(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "PHASE476_SANDBOX_EVIDENCE_PASS\n"
    assert result.stderr == ""
    receipt = json.loads(output_path.read_text(encoding="utf-8"))
    assert receipt["schema"] == "phase476.stripe_sandbox.v1"
    assert receipt["status"] == "PASS"
    assert receipt["mocked"] is False
    assert receipt["livemode"] is False
    assert receipt["productionMutationCount"] == 0
    assert receipt["liveChargeCount"] == 0
    assert receipt["exactOnce"] == {
        "activationCount": 1,
        "allowanceVersions": [1],
        "checkoutCommandCount": 1,
        "checkoutSessionCount": 1,
        "grantVersions": [1],
        "supportStateVersions": [1],
    }
    assert receipt["proofSelectors"] == {
        "adminProjectionRedacted": True,
        "duplicateDeliveryObserved": True,
        "hostedCheckoutObserved": True,
        "jointActivationProofObserved": True,
        "outOfOrderObserved": True,
        "parentAdminProjectionAgreement": True,
        "redactionScanPassed": True,
        "signedProviderDeliveryObserved": True,
        "sourceBindingVerified": True,
    }
    serialized = json.dumps(receipt, sort_keys=True)
    for forbidden in (
        "cs_test_phase476_sensitive",
        "in_phase476_sensitive",
        "sub_phase476_sensitive",
        "evt_phase476_invoice_sensitive",
        "evt_phase476_subscription_sensitive",
        "checkout_public_phase476_sensitive",
        "student-phase476-sensitive",
    ):
        assert forbidden not in serialized
    assert "sk_test_" not in serialized
    assert "whsec_" not in serialized


@pytest.mark.parametrize(
    ("path", "replacement", "error_code"),
    [
        (("browser", "mockCheckout"), True, "MOCK_EVIDENCE_FORBIDDEN"),
        (("browser", "routeInterception"), True, "INTERCEPTED_EVIDENCE_FORBIDDEN"),
        (("browser", "hostedCheckoutOrigin"), "https://checkout.example", "CHECKOUT_NOT_HOSTED"),
        (("provider", "livemode"), True, "LIVE_PROVIDER_OBJECT_FORBIDDEN"),
        (("provider", "keyMode"), "live", "TEST_MODE_REQUIRED"),
        (("provider", "signedEventDestination"), False, "SIGNED_DELIVERY_REQUIRED"),
        (("provider", "webhookSignaturesVerified"), False, "SIGNED_DELIVERY_REQUIRED"),
        (("provider", "redeliveryObserved"), False, "REDELIVERY_PROOF_REQUIRED"),
        (("provider", "outOfOrderObserved"), False, "EVENT_ORDER_PROOF_REQUIRED"),
        (("provider", "duplicateDeliveryObserved"), False, "EVENT_DEDUPE_PROOF_REQUIRED"),
        (("operation", "checkoutCommandCount"), 2, "EXACT_ONCE_PROOF_FAILED"),
        (("operation", "checkoutSessionCount"), 2, "EXACT_ONCE_PROOF_FAILED"),
        (("operation", "activationCount"), 2, "EXACT_ONCE_PROOF_FAILED"),
        (("safety", "liveChargeCount"), 1, "LIVE_CHARGE_FORBIDDEN"),
        (("safety", "productionMutationCount"), 1, "PRODUCTION_MUTATION_FORBIDDEN"),
        (("safety", "containsSecrets"), True, "REDACTION_PROOF_FAILED"),
        (("safety", "containsPii"), True, "REDACTION_PROOF_FAILED"),
    ],
)
def test_collector_rejects_false_passes(
    tmp_path: Path,
    path: tuple[str, ...],
    replacement: object,
    error_code: str,
) -> None:
    result, output_path = _run_collector(
        tmp_path,
        mutate_observation=lambda value: _set_path(value, path, replacement),
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == f"PHASE476_SANDBOX_EVIDENCE_ERROR:{error_code}\n"
    assert not output_path.exists()


def test_collector_rejects_duplicate_or_divergent_versions(tmp_path: Path) -> None:
    def mutate(value: dict[str, object]) -> None:
        operation = value["operation"]
        assert isinstance(operation, dict)
        operation["grantVersions"] = {"student-1": 1, "student-2": 2}

    result, output_path = _run_collector(tmp_path, mutate_observation=mutate)

    assert result.returncode != 0
    assert result.stderr == "PHASE476_SANDBOX_EVIDENCE_ERROR:EXACT_ONCE_PROOF_FAILED\n"
    assert not output_path.exists()


@pytest.mark.parametrize(
    "source_field",
    [
        "backendSha",
        "frontendSha",
        "acceptanceSourceSha256",
        "collectorSourceSha256",
        "preflightReceiptSha256",
    ],
)
def test_collector_rejects_source_mismatch(
    tmp_path: Path,
    source_field: str,
) -> None:
    def mutate(value: dict[str, object]) -> None:
        source = value["source"]
        assert isinstance(source, dict)
        source[source_field] = SHA256

    result, output_path = _run_collector(tmp_path, mutate_observation=mutate)

    assert result.returncode != 0
    assert result.stderr == "PHASE476_SANDBOX_EVIDENCE_ERROR:SOURCE_BINDING_MISMATCH\n"
    assert not output_path.exists()


def test_collector_rejects_preflight_failure(tmp_path: Path) -> None:
    result, output_path = _run_collector(
        tmp_path,
        mutate_preflight=lambda value: value.update({"status": "NOT_RUN"}),
    )

    assert result.returncode != 0
    assert result.stderr == "PHASE476_SANDBOX_EVIDENCE_ERROR:PREFLIGHT_NOT_PASSING\n"
    assert not output_path.exists()


def test_collector_refuses_overwrite_and_symlink_input(
    tmp_path: Path,
) -> None:
    result, output_path = _run_collector(tmp_path)
    assert result.returncode == 0

    second, _ = _run_collector(tmp_path / "second")
    assert second.returncode == 0

    # Re-running against an existing immutable receipt must fail.
    preflight_path = tmp_path / "preflight-existing.json"
    _write_json(preflight_path, _preflight_receipt())
    observation = _observation(preflight_path)
    observation_path = tmp_path / "observation-existing.json"
    _write_json(observation_path, observation)
    rerun = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--observation",
            str(observation_path),
            "--preflight-receipt",
            str(preflight_path),
            "--frontend-root",
            str(FRONTEND_ROOT),
            "--backend-root",
            str(ROOT),
            "--evidence-dir",
            str(output_path.parent),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rerun.returncode != 0
    assert rerun.stderr == "PHASE476_SANDBOX_EVIDENCE_ERROR:OUTPUT_NOT_EXCLUSIVE\n"

    symlink_path = tmp_path / "observation-link.json"
    symlink_path.symlink_to(observation_path)
    symlink_run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--observation",
            str(symlink_path),
            "--preflight-receipt",
            str(preflight_path),
            "--frontend-root",
            str(FRONTEND_ROOT),
            "--backend-root",
            str(ROOT),
            "--evidence-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "symlink-output.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert symlink_run.returncode != 0
    assert symlink_run.stderr == "PHASE476_SANDBOX_EVIDENCE_ERROR:INPUT_BOUNDARY_INVALID\n"


def test_collector_rejects_unknown_observation_fields(tmp_path: Path) -> None:
    def mutate(value: dict[str, object]) -> None:
        unsafe = deepcopy(value)
        value.clear()
        value.update(unsafe)
        value["unreviewedEvidence"] = "must-not-be-accepted"

    result, output_path = _run_collector(tmp_path, mutate_observation=mutate)

    assert result.returncode != 0
    assert result.stderr == "PHASE476_SANDBOX_EVIDENCE_ERROR:OBSERVATION_SCHEMA_INVALID\n"
    assert not output_path.exists()
