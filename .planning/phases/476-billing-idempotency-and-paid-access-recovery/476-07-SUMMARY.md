---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 07
subsystem: payments
tags: [stripe, checkout, supersession, dynamodb, idempotency, concurrency]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Durable checkout command, one-open parent guard, and command-first Stripe Session creation from Plans 05 and 06
provides:
  - Version-conditioned Session expiration intent and provider-authoritative nonpayability proof
  - Atomic old-command supersession, one-open guard transfer, and successor command registration
  - Complete/unknown Session reconciliation refusal with prior paid access left unchanged
  - Commit-timeout and concurrent retry convergence on one successor command
affects: [476-08, checkout-reconciliation, plan-change-api, billing-support]

tech-stack:
  added: []
  patterns:
    - Retrieve-expire-retrieve proof before durable guard transfer
    - One DynamoDB transaction updates the old command and guard while creating the successor command and lookup
    - Provider ambiguity remains support-needed behind the original guard

key-files:
  created:
    - tests/test_billing_checkout_supersession.py
  modified:
    - src/stoa/services/subscription_service.py
    - src/stoa/db/repositories/checkout_command_repo.py

key-decisions:
  - "Persist an expiration intent before Stripe expiration, then require a fresh exact Session retrieval with status expired before transferring the parent guard."
  - "Treat complete and unknown provider outcomes as reconciliation/support states that retain the original guard and never create a replacement."
  - "Transfer the guard with an update in the same transaction as old-command supersession and successor creation so DynamoDB never receives two operations for one item."

patterns-established:
  - "Checkout supersession: owner lookup, durable expiration claim, provider expire, provider re-read, nonpayability record, atomic guard transfer, then normal command-first creation."
  - "Ambiguous financial effects retain authority: provider or local uncertainty cannot release or replace the guarded operation."

requirements-completed: [V9BILL-01, V9BILL-02]

duration: 11min
completed: 2026-07-24
---

# Phase 476 Plan 07: Safe Checkout Plan Supersession Summary

**Confirmed plan changes now expire and re-read the old Stripe test Session before atomically transferring the parent guard to one durable successor command.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-24T10:52:56Z
- **Completed:** 2026-07-24T11:04:25Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Added `claim_session_expiration()`, `record_session_expiration()`, and `supersede_checkout_command()` with exact command version, owner, account-fence, Session-attachment, and guard conditions.
- Added `confirm_checkout_plan_change()` with retrieve-open, durable claim, expire, retrieve-expired proof ordering before successor creation.
- Preserved the original guard and returned support-needed for complete, malformed, live, mismatched, unavailable, or otherwise unknown provider outcomes.
- Made supersession response-loss replayable from strong reads and proved two concurrent confirmations converge on one successor command and one transferred guard.
- Kept prior billing and entitlement projections outside every failed, canceled, expired, or ambiguous replacement transition.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-07-01 RED: Add failing checkout supersession contract** - `43eea66` (test)
2. **Task 476-07-01 GREEN: Implement safe checkout supersession** - `ac9fcfe` (feat)

## Files Created/Modified

- `tests/test_billing_checkout_supersession.py` - Open/expired/complete/unknown, owner, provider-call, transaction ambiguity, prior-access, and concurrency proof.
- `src/stoa/db/repositories/checkout_command_repo.py` - Versioned expiration effects, provider outcome recording, and atomic old-to-new guard transfer.
- `src/stoa/services/subscription_service.py` - Confirmed plan-change orchestration plus exact Stripe Session retrieve and expire adapters.

## Decisions Made

- The Stripe expire response is not itself sufficient proof; a fresh retrieval must return the exact bound test Session with `status=expired` and `livemode=false`.
- Already-expired Sessions skip the provider mutation and can persist nonpayability directly from the authoritative retrieval.
- Complete Sessions transition the original command to reconciliation, while unavailable or malformed evidence transitions it to operator attention; neither path creates a successor.
- The successor is registered in the same transaction that marks the old command superseded and changes the one-open guard, then reuses the normal command-first provider creation flow.

## Deviations from Plan

None - plan executed exactly as written.

## Security Verification

- The required `subscription_service.py` → `checkout_command_repo.py` key link now calls `supersede_checkout_command()` after durable nonpayability proof.
- Owner-authorized opaque lookup occurs before provider access; cross-owner references remain concealed as not found.
- The expiration mutation is claimed once under the exact old command version and active account fence.
- Guard transfer requires the current old command version, `nonpayable_proven`, terminal-without-payment state, exact parent guard owner/version, and absent prior supersession.
- One transaction targets five distinct rows/actions: active account-fence check, old command update, guard transfer, successor command create, and successor opaque lookup create.
- Complete and unknown outcomes make zero replacement Session-create calls and retain the original guard.
- Concurrent confirmations make one provider expiration call and converge through one atomic successor identity; committed-response loss replays from strong reads.
- The new Stripe adapters pass only the durable exact test Session ID and configured test key; no real provider call, charge, credential, deployment, or production operation was performed.
- All T-476-07-H mitigations have observed focused selectors. No unresolved ASVS L1 High threat remains in this plan's source boundary.
- The aggregate `scripts/verify_phase476_security_gate.py` is not yet present and remains owned by a later Phase 476 plan; this summary makes no aggregate phase-gate claim.

## Known Stubs

None introduced. Empty collections and optional values in the touched files are bounded accumulators, closed result fields, or test-double state rather than unwired application data.

## Issues Encountered

- Context7 was unavailable locally, so the current Stripe retrieve, status, and expiration behavior was checked against Stripe's official Checkout Session API documentation.
- The first combined implementation patch matched an outdated source boundary and applied no changes; the repository and service edits were then applied in smaller verified patches.
- The aggregate Phase 476 security gate script is not present yet; focused and adjacent source-bound suites were used without overclaiming the later phase gate.

## Verification

- Plan command: `21 passed` across `tests/test_billing_checkout_supersession.py` and `tests/test_billing_checkout_commands.py`.
- Repository plus plan boundary: `41 passed` across checkout repository, supersession, and checkout command suites.
- Extended billing regression: `220 passed` across callback, command, supersession, contract, billing-fact, repository, and subscription-operation suites.
- Ruff passes on all planned implementation/test files.
- `git diff --check` passes.
- Source-link scan finds all planned claim, record, retrieve, expire, and supersede calls.

## User Setup Required

None for this plan. Existing Stripe sandbox/test configuration remains required before any approved external test, but no external provider call or setup change was performed here.

## Next Phase Readiness

- Plan 476-08 can reconcile complete or ambiguous original commands without ever starting a replacement.
- A later route/UI plan can expose explicit confirmation and call `confirm_checkout_plan_change()`; selecting a different card or plan alone does not invoke it.
- The later aggregate Phase 476 gate must include these focused supersession selectors before phase completion.

## Self-Check: PASSED

- FOUND: `src/stoa/services/subscription_service.py`
- FOUND: `src/stoa/db/repositories/checkout_command_repo.py`
- FOUND: `tests/test_billing_checkout_supersession.py`
- FOUND: `43eea66`
- FOUND: `ac9fcfe`
- PASS: plan verification (`21 passed`)
- PASS: extended billing regression (`220 passed`)
- PASS: Ruff and `git diff --check`
- PASS: `subscription_service` → `supersede_checkout_command` key link

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
