---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 05
subsystem: payments
tags: [dynamodb, idempotency, checkout, leases, stripe, concurrency]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Canonical CheckoutIntent and CheckoutCommandState contracts from Plan 01
provides:
  - Atomic durable checkout command, one-open parent guard, and opaque public lookup
  - Immutable intent fingerprint and stable non-PII provider idempotency key digest
  - Versioned provider-create lease, ambiguity preservation, conditional Session attachment, and terminal guard release
affects: [476-06, 476-08, checkout-orchestration, billing-reconciliation]

tech-stack:
  added: []
  patterns:
    - Strong-read replay classification after conditional or ambiguous DynamoDB writes
    - Permanent account fence plus three create-only checkout rows in one transaction
    - Lease owner, generation, expiry, and command version jointly fence provider attachment

key-files:
  created:
    - src/stoa/db/repositories/checkout_command_repo.py
    - tests/test_checkout_command_repo.py
  modified: []

key-decisions:
  - "Derive the command ID from the parent and bounded logical key, persist only the caller-key digest, generate the public reference independently, and use a recomputable digest-only provider key."
  - "Keep provider ambiguity and active leases behind the one-open parent guard; only activation-recorded or proven-without-payment terminal command versions may release it."
  - "Classify transaction exceptions only after authoritative strong reads so committed-response loss replays while pre-commit failure remains retryable."

patterns-established:
  - "Checkout command-first boundary: command, guard, and owner lookup are durable before any provider capability exists."
  - "Immutable replay validation: schema, owner, command identity, canonical fingerprint, public lookup, and provider-key derivation must all agree."
  - "Provider lease fencing: stale owners or generations cannot attach a Session after takeover."

requirements-completed: [V9BILL-01, V9BILL-02]

duration: 15min
completed: 2026-07-24
---

# Phase 476 Plan 05: Durable Checkout Command Repository Summary

**One parent checkout now acquires an account-fenced durable command, one-open guard, opaque owner lookup, and stable provider lease identity before any Stripe capability can be invoked.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-24T08:14:17Z
- **Completed:** 2026-07-24T08:28:52Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Added one transaction that conditionally verifies the permanent parent account fence and creates exactly the checkout command, parent open guard, and public lookup.
- Added canonical immutable intent fingerprinting over parent, plan, sorted explicit beneficiaries, Price identity, catalog/plan versions, and environment.
- Added a server-generated unrelated public reference and stable versioned SHA-256 provider key with no raw parent, beneficiary, or caller key.
- Added strong-read replay and owner-authorized lookup validation that distinguishes identical retry, changed intent, another open command, malformed evidence, and retryable dependency ambiguity.
- Added provider-create claim persistence, lease expiry takeover, stale-owner rejection, commit-then-timeout Session attachment reconciliation, and provider-outcome-unknown preservation.
- Added terminal-version-conditioned open-guard release that refuses every nonterminal and support-needed state.
- Proved the boundary with 20 focused tests, including 20 synchronized callers and injected pre-commit/committed-response-loss outcomes.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-05-01 RED: Add failing checkout command repository contract** - `6e9ec91` (test)
2. **Task 476-05-01 GREEN: Implement durable checkout command repository** - `bf74b4a` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/checkout_command_repo.py` - Atomic registration, immutable replay, owner lookup, provider lease, attachment, ambiguity, and terminal guard operations.
- `tests/test_checkout_command_repo.py` - Concurrency, transaction ambiguity, mismatch, ownership, non-PII identity, lease takeover, stale attachment, and terminal-release proof.

## Decisions Made

- The opaque public checkout reference has no caller-controlled parameter; the repository always generates it from a cryptographic random source.
- The provider idempotency key is a 64-character domain-separated digest derived from the command identity, immutable intent fingerprint, and provider-key version.
- The raw browser idempotency key is never persisted; its digest plus the command identity is enough to validate durable replay.
- Strong reads are the only evidence used to classify an exception as a committed command or attached Session.
- Provider ambiguity advances durable state but deliberately retains the parent open guard and the original provider key for expiry-based recovery.

## Deviations from Plan

None - plan executed exactly as written.

## Security Verification

- The repository imports `CheckoutIntent` and `CheckoutCommandState`, closing the planned source-to-contract key link.
- Provider libraries, provider clients, network functions, and provider-call parameters are absent from the repository.
- Registration emits three distinct create-only row targets plus the exact active parent fence condition.
- Twenty synchronized identical registrations create one row set and replay one reference; changed intent emits no write.
- Cross-parent public lookup is concealed as not found, while malformed lookup/schema evidence fails closed.
- Raw parent, caller-key, and beneficiary canaries do not occur in the public reference or provider key; the provider key is stable and below Stripe's length bound.
- Expired lease takeover preserves command ID, fingerprint, and provider key, and the stale owner cannot attach a Session.
- Attach committed-response loss is reconciled from a consistent read; pre-commit registration failure remains retryable.
- Provider ambiguity never clears the one-open guard; all nonterminal command states refuse release.
- All T-476-05-H mitigations have named source-bound passing selectors. No unresolved ASVS L1 High threat remains in this plan's files.
- The aggregate `scripts/verify_phase476_security_gate.py` is not yet present and remains owned by a later Phase 476 plan; this summary makes no aggregate phase-gate claim.

## Known Stubs

None introduced.

## Issues Encountered

- The first deterministic public-reference fixture was shorter than the repository's entropy floor; the fixture was corrected before GREEN without weakening the production boundary.
- Repository writes to git metadata required the managed approval path; normal hooks remained enabled and no verification was bypassed.

## User Setup Required

None - no dependencies, credentials, provider calls, charges, deployment, or production mutation were introduced.

## Next Phase Readiness

- Plan 476-06 can call `register_checkout_command()` then `claim_provider_create()` before Stripe Session creation and conditionally attach the one returned Session.
- Plan 476-08 can resolve only an owner-authorized opaque reference and reconcile the same stored provider identity without any Session-create dependency.
- Later terminal/supersession flows must persist a proven terminal command version before calling the guard-release operation.

## Self-Check: PASSED

- FOUND: `src/stoa/db/repositories/checkout_command_repo.py`
- FOUND: `tests/test_checkout_command_repo.py`
- FOUND: `6e9ec91`
- FOUND: `bf74b4a`
- PASS: `PYTHONPATH=. .venv/bin/pytest -q tests/test_checkout_command_repo.py` (`20 passed`)
- PASS: `.venv/bin/ruff check src/stoa/db/repositories/checkout_command_repo.py tests/test_checkout_command_repo.py`
- PASS: active key link includes `CheckoutIntent|CheckoutCommandState`.
- PASS: provider/network dependency and stub scans are empty.

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
