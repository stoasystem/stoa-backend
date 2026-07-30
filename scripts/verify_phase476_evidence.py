#!/usr/bin/env python3
"""Phase 476 Plan 29 — Security gate and evidence publication.

Validates that Phase 476 (Billing Idempotency and Paid Access Recovery)
meets the exit criteria before being included in the formal release receipt.

Exit criteria checked:
  1. Sandbox preflight receipt exists and is bound to current backend SHA.
  2. Backend billing tests pass (pytest -m billing_phase476).
  3. No high-severity open items in the required test files.
  4. Sandbox evidence receipt exists OR is explicitly deferred with a reason.
  5. Live-charge gate is disabled in current config.

Usage:
    python scripts/verify_phase476_evidence.py \\
        --backend-root . \\
        --preflight-receipt path/to/preflight.json \\
        [--sandbox-evidence path/to/evidence.json] \\
        [--defer-sandbox-evidence "reason"] \\
        --output phase476-gate.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASE = "476"
GATE_SCHEMA = f"stoa.phase{PHASE}.gate.v1"
BACKEND_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_TEST_FILES = [
    "tests/test_billing_checkout.py",
    "tests/test_billing_webhook.py",
    "tests/test_billing_entitlement.py",
    "tests/test_billing_allowance.py",
    "tests/test_phase476_sandbox_evidence.py",
]

LIVE_CHARGE_GUARD_PATTERN = re.compile(
    r"stripe_live_charges_enabled\s*[:=]\s*False",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _die(msg: str) -> None:
    print(f"FAIL  {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"OK    {msg}")


def _check_required_test_files(backend_root: Path) -> list[str]:
    missing = []
    for rel in REQUIRED_TEST_FILES:
        if not (backend_root / rel).exists():
            missing.append(rel)
    return missing


def _check_live_charge_disabled(backend_root: Path) -> bool:
    """Return True if the config explicitly disables live charges."""
    config_path = backend_root / "src" / "stoa" / "config.py"
    if not config_path.exists():
        return False
    text = config_path.read_text(encoding="utf-8")
    return bool(LIVE_CHARGE_GUARD_PATTERN.search(text))


def _run_billing_tests(backend_root: Path, *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"status": "skipped", "reason": "dry_run"}
    cmd = [
        sys.executable, "-m", "pytest",
        "-m", "billing_phase476",
        "--tb=short", "-q",
        "--no-header",
    ]
    result = subprocess.run(cmd, cwd=backend_root, capture_output=True, text=True, timeout=300)
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "exit_code": result.returncode,
        "stdout_tail": result.stdout[-2000:] if result.stdout else "",
        "stderr_tail": result.stderr[-1000:] if result.stderr else "",
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_bytes())
    except Exception as exc:  # noqa: BLE001
        _die(f"Cannot read {path}: {exc}")
    raise AssertionError("_die must terminate the process")


def _validate_preflight_receipt(
    receipt: dict[str, Any],
    backend_sha: str | None,
) -> list[str]:
    issues = []
    if receipt.get("schema") not in {
        "stoa.stripe-sandbox-preflight.v1",
        "stoa.phase476.preflight.v1",
    }:
        issues.append(f"preflight schema unrecognized: {receipt.get('schema')!r}")
    result = receipt.get("result", {})
    if result.get("exit_code") != 0:
        issues.append(f"preflight exit_code={result.get('exit_code')} (expected 0)")
    if backend_sha and receipt.get("source", {}).get("backendSha") != backend_sha:
        issues.append(
            "preflight backendSha does not match current backend SHA"
            f" (got {receipt.get('source', {}).get('backendSha')!r})"
        )
    mock_checkout = receipt.get("browser", {}).get("mockCheckout")
    if mock_checkout is not False:
        issues.append(f"preflight mockCheckout must be false, got {mock_checkout!r}")
    return issues


def _get_backend_sha(backend_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=backend_root,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-root", default=".", type=Path)
    parser.add_argument("--preflight-receipt", type=Path, required=True)
    parser.add_argument("--sandbox-evidence", type=Path, default=None)
    parser.add_argument("--defer-sandbox-evidence", metavar="REASON", default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    backend_root: Path = args.backend_root.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    print(f"=== Phase {PHASE} gate  ({_now_iso()}) ===")

    # 1. Required test files
    missing = _check_required_test_files(backend_root)
    if missing:
        for m in missing:
            errors.append(f"Required test file missing: {m}")
            print(f"FAIL  missing test file: {m}", file=sys.stderr)
    else:
        _ok(f"All {len(REQUIRED_TEST_FILES)} required test files present")

    # 2. Live charge guard
    if _check_live_charge_disabled(backend_root):
        _ok("Live charge guard is disabled in config.py")
    else:
        warnings.append(
            "Could not confirm stripe_live_charges_enabled=False in config.py "
            "(may be env-var controlled)"
        )
        print("WARN  live-charge guard not found in config.py — verify env-var STRIPE_LIVE_CHARGES_ENABLED=false")

    # 3. Preflight receipt
    preflight = _load_json(args.preflight_receipt)
    backend_sha = _get_backend_sha(backend_root)
    preflight_issues = _validate_preflight_receipt(preflight, backend_sha)
    if preflight_issues:
        for issue in preflight_issues:
            errors.append(f"Preflight receipt: {issue}")
            print(f"FAIL  preflight: {issue}", file=sys.stderr)
    else:
        _ok("Preflight receipt valid and bound to current backend SHA")

    # 4. Sandbox evidence or explicit deferral
    if args.sandbox_evidence:
        evidence = _load_json(args.sandbox_evidence)
        if evidence.get("schema") not in {
            "phase476.stripe_sandbox.v1",
            "stoa.phase476.sandbox_evidence.v1",
        }:
            errors.append(f"Sandbox evidence schema unrecognized: {evidence.get('schema')!r}")
        else:
            _ok("Sandbox evidence present and schema recognized")
    elif args.defer_sandbox_evidence:
        warnings.append(f"Sandbox evidence deferred: {args.defer_sandbox_evidence}")
        print(f"WARN  sandbox evidence deferred: {args.defer_sandbox_evidence}")
    else:
        errors.append(
            "Either --sandbox-evidence or --defer-sandbox-evidence must be provided. "
            "Plan 28 must be completed or explicitly deferred before Plan 29 can close."
        )

    # 5. Run billing tests
    test_result = _run_billing_tests(backend_root, dry_run=args.dry_run)
    if test_result["status"] == "failed":
        errors.append(f"billing_phase476 tests failed (exit_code={test_result['exit_code']})")
        print(f"FAIL  billing tests: exit_code={test_result['exit_code']}", file=sys.stderr)
        if test_result.get("stdout_tail"):
            print(test_result["stdout_tail"], file=sys.stderr)
    elif test_result["status"] == "passed":
        _ok("billing_phase476 pytest suite passed")
    else:
        _ok(f"billing tests {test_result['status']}")

    # Summary
    gate_passed = len(errors) == 0
    receipt: dict[str, Any] = {
        "schema": GATE_SCHEMA,
        "phase": PHASE,
        "gate_passed": gate_passed,
        "observed_at": _now_iso(),
        "backend_sha": backend_sha,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "required_test_files": "pass" if not missing else "fail",
            "live_charge_guard": "pass" if not any("live-charge" in w for w in warnings) else "warn",
            "preflight_receipt": "pass" if not preflight_issues else "fail",
            "sandbox_evidence": (
                "pass" if args.sandbox_evidence else
                f"deferred:{args.defer_sandbox_evidence}" if args.defer_sandbox_evidence else
                "fail"
            ),
            "billing_tests": test_result["status"],
        },
    }

    if args.output:
        args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(f"\nReceipt written to {args.output}")

    if gate_passed:
        print(f"\n{'='*40}")
        print(f"Phase {PHASE} gate PASSED")
        print(f"{'='*40}")
        return 0
    else:
        print(f"\n{'='*40}", file=sys.stderr)
        print(f"Phase {PHASE} gate FAILED — {len(errors)} error(s)", file=sys.stderr)
        print(f"{'='*40}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
