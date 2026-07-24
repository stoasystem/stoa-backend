---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 06
subsystem: payments
tags: [stripe, checkout, idempotency, fastapi, dynamodb, beneficiaries, sandbox]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Exact server callback builder, safe Stripe configuration, and durable checkout command repository from Plans 02, 03, and 05
provides:
  - Header-bound typed parent checkout command API with explicit paid plan and beneficiaries
  - Command-first Stripe test Session creation using one durable provider idempotency key
  - Same-Session replay across duplicate clicks, response loss, concurrency, and provider ambiguity
  - Fresh active bidirectional beneficiary and paid-plan cardinality enforcement
affects: [476-08, 476-11, 476-23, parent-checkout, billing-reconciliation]

tech-stack:
  added: []
  patterns:
    - Persist command and provider-create lease before the first external mutation
    - Retry one ambiguous Stripe create with byte-identical parameters and idempotency key
    - Poll only the original owner-authorized command when another request owns the active lease

key-files:
  created:
    - tests/test_billing_checkout_commands.py
  modified:
    - src/stoa/services/subscription_service.py
    - src/stoa/routers/parents.py

key-decisions:
  - "Accept one bounded Idempotency-Key header plus plan and explicit beneficiaryIds; browser callback URLs and free_trial are structurally rejected."
  - "Use the durable command's opaque checkout reference as the sole Stripe client/metadata reference and its digest-only provider key as Stripe's idempotency_key."
  - "Require an active parent, active student profiles, and exact active forward and reverse relationship rows before registration or provider access."
  - "Keep only a payable test Session URL on the durable open command; malformed, live, or repeatedly ambiguous provider outcomes are never attached."

patterns-established:
  - "Checkout orchestration order: validate scope, register command, claim provider intent, call Stripe test mode, conditionally attach Session."
  - "Concurrent replay: a lease loser reads only the original opaque command until the owner attaches or returns a bounded confirming response."

requirements-completed: [V9BILL-01, V9BILL-03]

duration: 9min
completed: 2026-07-24
---

# Phase 476 Plan 06: Durable Parent Checkout Orchestration Summary

**Parent checkout now commits one exact beneficiary-scoped command before calling Stripe test mode and reuses its opaque reference, provider key, Session, and owner-visible URL across retries and concurrent requests.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-24T09:50:23Z
- **Completed:** 2026-07-24T09:59:01Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Replaced provider-first parent checkout with `create_or_resume_checkout_command()`, which registers and claims the durable command before Stripe can be invoked.
- Replaced `requestedTier` with the closed `{plan, beneficiaryIds}` body and required a bounded printable `Idempotency-Key` header.
- Revalidated the authenticated parent, every active student profile, and both exact active relationship rows before any command or provider effect.
- Enforced one beneficiary for `student` and `teacher_supported`, one to three for `family`, and structural exclusion of `free_trial`.
- Sent only the opaque checkout reference through Stripe client/metadata fields and passed the repository's stable digest through the SDK `idempotency_key`.
- Replayed an attached payable Session directly, retried an ambiguous provider response with identical arguments, and bounded concurrent lease-loser polling to the original command.
- Refused live keys, live-labeled Prices, live provider objects, malformed provider responses, changed payloads under one key, and another open-key attempt.

## Task Commits

TDD execution produced RED and GREEN commits, followed by one adjacent security-regression fix:

1. **Task 476-06-01 RED: Add failing durable checkout command contract** - `6c663c4` (test)
2. **Task 476-06-01 GREEN: Route checkout through durable sandbox command** - `6eb8cfc` (feat)
3. **Task 476-06-01 Fix: Preserve callback boundary inspection aliases** - `4ba44cf` (fix)

## Files Created/Modified

- `tests/test_billing_checkout_commands.py` - Ordered provider-call, timeout, replay, concurrency, route, beneficiary, sandbox, live-object, redaction, and Stripe call-shape proof.
- `src/stoa/services/subscription_service.py` - Command-first validation, registration, lease claim, fixed callbacks, stable provider retry, conditional attachment, and safe response projection.
- `src/stoa/routers/parents.py` - Typed checkout command request/response and required `Idempotency-Key` header.

## Decisions Made

- The active route exposes no provider readiness object, raw parent coordinate, provider key, secret, or browser callback authority.
- The owner-visible response contains the opaque checkout reference, payable Session ID/URL, command state, safe actions, target plan, and explicitly authorized beneficiaries.
- Stripe Session creation is test-only in this phase. A `sk_test_` key, non-live Price identity, `cs_test_` Session, `livemode=false`, and Stripe-hosted HTTPS URL are all required.
- The first transient provider exception is retried in the same claimed operation with the exact same arguments. A second exception persists provider ambiguity and returns a retryable confirming response without releasing the open guard.
- No compatibility wrapper retains the provider-first implementation; the legacy inspection names alias the new command function/model only so the existing callback security gate remains source-compatible.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Restored callback security-gate inspection names**
- **Found during:** Task 476-06-01 adjacent verification
- **Issue:** Replacing the old checkout function/model names caused `tests/test_billing_callback_urls.py` to fail collection even though the active route correctly used the new contract.
- **Fix:** Added source-compatibility aliases that point only to the new durable command function/model; legacy `requestedTier`, `successUrl`, and `cancelUrl` remain rejected.
- **Files modified:** `src/stoa/services/subscription_service.py`, `src/stoa/routers/parents.py`
- **Verification:** Focused checkout, durable repository, callback URL, and billing contract suites pass together (`165 passed`).
- **Commit:** `4ba44cf`

---

**Total deviations:** 1 auto-fixed bug.
**Impact:** Existing source-bound callback verification remains executable without restoring provider-first creation or browser callback authority.

## Security Verification

- Ordered test evidence proves `register_checkout_command()` and `claim_provider_create()` complete before `stripe.checkout.Session.create()`, and `attach_provider_session()` occurs only after a validated response.
- Timeout and concurrency selectors prove every ambiguous create uses the same complete provider argument set and one 64-character key; two simultaneous API requests produce one Session and one attachment.
- Changed payload under the same key returns `checkout_idempotency_mismatch`; another key behind the open guard returns `checkout_already_in_progress`.
- Inactive, missing, one-directional, and cross-parent relationship evidence plus invalid cardinality all stop before provider access.
- Header absence, unknown body fields, callback fields, and `free_trial` fail at the FastAPI/Pydantic boundary.
- Stripe receives only the opaque checkout reference in client/metadata fields. Parent/student canaries and the Stripe secret are absent from the provider request metadata and response projection.
- Live keys, live-labeled Prices, `livemode=true`, non-test Session IDs, and non-Stripe checkout URLs cannot become attached command evidence.
- All T-476-06-H mitigations have observed focused selectors. No unresolved ASVS L1 High threat remains in this plan's source boundary.
- No real Stripe request, charge, production operation, provider credential, or deployment was used; all provider behavior was exercised through mocks.
- Current Stripe Session/idempotency call semantics were checked against official Stripe API documentation because Context7 was unavailable locally.

## Known Stubs

None introduced. Empty collections in the test harness and existing modules are bounded accumulators or optional projections, not UI/data-source placeholders.

## Issues Encountered

- Git metadata writes required the managed approval path; normal hooks remained enabled and no verification was bypassed.
- The first adjacent aggregate run exposed the renamed callback inspection symbols. The compatibility aliases were added and all 165 focused/adjacent tests then passed.

## User Setup Required

- Configure the three Stripe sandbox Price IDs and a restricted `sk_test_` key outside source control before using this route against Stripe test mode.
- No setup, provider call, charge, deployment, or production mutation was performed during this plan.

## Next Phase Readiness

- Plan 476-08 can resolve and reconcile the same owner-authorized opaque checkout reference without creating another Session.
- Signed webhook and fact convergence work can consume the attached test Session identity while treating browser return as non-authoritative.
- The aggregate Phase 476 security gate remains owned by a later plan; this summary makes no phase-level or real-browser Stripe evidence claim.

## Self-Check: PASSED

- FOUND: `src/stoa/services/subscription_service.py`
- FOUND: `src/stoa/routers/parents.py`
- FOUND: `tests/test_billing_checkout_commands.py`
- FOUND: `6c663c4`
- FOUND: `6eb8cfc`
- FOUND: `4ba44cf`
- PASS: focused plan verification (`11 passed`)
- PASS: focused plus adjacent billing verification (`165 passed`)
- PASS: Ruff on all planned source/test files
- PASS: command-register/claim/provider/attach source key link
- PASS: route callback/free-plan/unknown-field and sandbox/live refusal matrix
- PASS: `git diff --check`

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
