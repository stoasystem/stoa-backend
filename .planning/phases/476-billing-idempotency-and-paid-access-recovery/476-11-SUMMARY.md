---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 11
subsystem: payments
tags: [stripe, webhooks, idempotency, dynamodb, paid-access]

requires:
  - phase: 476-06
    provides: Command-first Stripe sandbox Checkout with immutable intent metadata
  - phase: 476-08
    provides: Retrieval-only same-command billing reconciliation
  - phase: 476-10
    provides: Durable provider facts and exact-once atomic paid activation
provides:
  - Official raw-body Stripe signature verification before durable fact registration
  - Legacy and 2025-03-31.basil invoice subscription extraction
  - Provider-retrieved joint paid-invoice and active-subscription activation predicate
  - Monotonic unordered fact convergence with redacted processing dispositions
affects: [billing-entitlements, allowance-activation, phase-476-security-gate]

tech-stack:
  added: []
  patterns:
    - Raw signed event to durable fact to current provider retrieval to atomic activation
    - Digest-only provider-object binding on the durable checkout command

key-files:
  created:
    - tests/test_billing_webhook_convergence.py
  modified:
    - src/stoa/routers/billing.py
    - src/stoa/services/subscription_service.py
    - src/stoa/services/billing_reconciliation_service.py
    - tests/test_subscription_operations.py

key-decisions:
  - "The public webhook route verifies the untouched request bytes with Stripe Webhook.construct_event before it exposes the Plan 10 fact-registration capability."
  - "Invoice and subscription events retrieve the current sandbox Session, Invoice, and Subscription and bind their digest-only identities to the immutable checkout command before facts or activation can authorize paid access."
  - "Checkout completion and invoice-only legacy flows remain confirming; only a paid expected first invoice plus the exact active subscription/customer/Price/command/beneficiary predicate invokes atomic activation."

patterns-established:
  - "Version-aware invoice identity: Basil reads parent.subscription_details.subscription while retained legacy events read invoice.subscription, with conflicting shapes rejected."
  - "Fact-oriented replay: event and semantic duplicates continue reconciliation, object facts advance independently, and no global cross-object event clock controls activation."

requirements-completed: [V9BILL-02, V9BILL-04]

duration: 15min
completed: 2026-07-24
---

# Phase 476 Plan 11: Signed Webhook Convergence Summary

**Stripe-signed sandbox events now converge current paid-invoice and active-subscription evidence into one provider-bound, exact-once paid-access activation.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-24T12:27:50Z
- **Completed:** 2026-07-24T12:42:16Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments

- Bound the public webhook route directly from untouched request bytes through official Stripe signature verification to Plan 10 durable event registration.
- Added legacy/Acacia and `2025-03-31.basil` Invoice subscription extraction with conflicting-shape refusal.
- Added current Session/Invoice/Subscription retrieval, exact command/customer/Price/environment/beneficiary checks, digest-only command binding, independent fact recording, and atomic activation invocation.
- Removed the global cross-object stale-event gate from the legacy projection path; the paid path now converges current object facts without delivery-order dependence.
- Proved unsigned, wrong-secret, body-mutation, old-timestamp, live, wrong-customer, wrong-Price, inactive-subscription, unpaid-invoice, checkout-only, reverse-order, equal-time, stale-snapshot, semantic duplicate, and 20-concurrent-replay behavior.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-11-01 RED: Add failing webhook convergence contract** - `b5c26da0` (test)
2. **Task 476-11-01 GREEN: Converge signed Stripe billing facts** - `d4db90c4` (feat)

## Files Created/Modified

- `src/stoa/routers/billing.py` - Reads the raw body, verifies it first, and supplies the durable fact-registration capability to the signed processor.
- `src/stoa/services/subscription_service.py` - Official verification, version-aware extraction, current-provider retrieval, joint predicate, fact convergence, redacted results, and activation material.
- `src/stoa/services/billing_reconciliation_service.py` - Exact public-reference command resolution and conditional digest-only customer/subscription/initial-invoice binding.
- `tests/test_billing_webhook_convergence.py` - Adversarial signature, version, mismatch, order, replay, concurrency, and redaction matrix.
- `tests/test_subscription_operations.py` - Official Stripe Event fixtures and D-13-compatible legacy checkout/invoice expectations.

## Decisions Made

- Signature verification uses the installed official Stripe SDK against the exact raw request bytes; the former custom HMAC/unsigned parsing path is not reachable from the public webhook route.
- Current provider retrieval is mandatory when a predicate half is missing. Provider errors after durable event registration return a retryable response rather than granting access or fabricating proof.
- Provider customer, subscription, and expected first-invoice bindings are stored only as domain-separated SHA-256 digests and advance the checkout command version once before fact publication.
- Durable duplicates are safe to replay through reconciliation; an existing activation receipt remains the exact-once authority.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added Stripe SDK v15 object conversion**
- **Found during:** Task 476-11-01 GREEN
- **Issue:** Verified Stripe Event objects expose `to_dict()` in the locked SDK, while the existing converter recognized only the older recursive method and converted valid signed events to an empty mapping.
- **Fix:** Added the current official `to_dict()` conversion path while retaining the older compatible method.
- **Files modified:** `src/stoa/services/subscription_service.py`
- **Verification:** Official signed fixture passes and wrong/mutated/expired signatures fail.
- **Committed in:** `d4db90c4`

**2. [Rule 1 - Bug] Migrated stale legacy webhook fixtures**
- **Found during:** Adjacent billing verification
- **Issue:** Three legacy tests disabled the SDK, omitted Stripe's Event object envelope, or expected invoice-only activation.
- **Fix:** Migrated valid fixtures to official Event envelopes, preserved invalid-signature rejection, and changed checkout/invoice-only assertions to remain confirming/retryable under D-13.
- **Files modified:** `tests/test_subscription_operations.py`
- **Verification:** Focused plus adjacent billing suites pass 59 tests.
- **Committed in:** `d4db90c4`

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes were required for the locked Stripe SDK and the authoritative D-13 security boundary; no compatibility bypass or provider mutation was introduced.

## Security Verification

- Raw request bytes reach `stripe.Webhook.construct_event` before `billing_fact_repo.register_provider_event`; the exact source link is statically observed in the router.
- Checkout completion cannot invoke activation, and provider mismatch/live objects cannot persist a grant or active projection.
- Invoice and subscription facts use independent current-object versions; the removed `_provider_event_is_stale` gate cannot suppress a necessary fact because of an unrelated event clock.
- Public processing responses expose a digest-derived event reference and closed dispositions, not signatures, secrets, payloads, Checkout URLs, PAN/CVC, or full provider identifiers.
- The focused security matrix passes 14 tests, including 20 concurrent duplicate deliveries and both fact arrival orders.
- No unresolved ASVS L1 High threat remains in this plan's source-bound selectors.
- `scripts/verify_phase476_security_gate.py` is not present yet and remains owned by a later Phase 476 plan; no aggregate phase-gate claim is made here.

## Known Stubs

None introduced.

## Issues Encountered

- Context7 was not installed. The implementation contract was checked against current official Stripe webhook and subscription-webhook documentation instead.
- The Starlette test client emits one existing deprecation warning about a future `httpx2` migration; it does not affect the webhook result.
- No real Stripe call, charge, production operation, deployment, or provider mutation was performed; all verification used signed fixtures and retrieval mocks.

## User Setup Required

None - no dependencies or external configuration were added.

## Next Phase Readiness

- Paid activation is now available exclusively through the signed fact-convergence path and the Plan 10 atomic transaction.
- Later Phase 476 work can consume the active billing/grant/allowance projections and add the aggregate source-bound phase security gate.

## Self-Check: PASSED

- FOUND: `src/stoa/routers/billing.py`
- FOUND: `src/stoa/services/subscription_service.py`
- FOUND: `src/stoa/services/billing_reconciliation_service.py`
- FOUND: `tests/test_billing_webhook_convergence.py`
- FOUND: `tests/test_subscription_operations.py`
- FOUND: `b5c26da0`
- FOUND: `d4db90c4`
- PASS: `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_webhook_convergence.py` (`14 passed`)
- PASS: focused plus adjacent billing verification (`59 passed`)
- PASS: planned ruff gate
- PASS: exact router key link and global stale-gate absence selectors

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
