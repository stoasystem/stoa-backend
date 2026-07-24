---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 24
subsystem: payments
tags: [react, typescript, tanstack-query, playwright, checkout-recovery]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Durable parent checkout status/recheck APIs and retained opaque checkout references from Plans 09 and 23
provides:
  - Fixed checkout result route driven only by authoritative original-command status
  - Finite confirming-only polling with same-reference manual recovery
  - Four fail-closed public checkout outcomes with effective plan and beneficiary rendering
  - Browser proof that path, flow, plan, status, and foreign references cannot spoof paid access
affects: [476-25, 476-28, web-billing, checkout-recovery]

tech-stack:
  added: []
  patterns:
    - TanStack Query polling stops on terminal outcomes and after a finite backoff window
    - Checkout result URLs contribute only the opaque reference; every rendered outcome comes from backend state

key-files:
  created:
    - /Users/zhdeng/stoa-frontend/src/hooks/billing/useCheckoutCommandQuery.ts
    - /Users/zhdeng/stoa-frontend/tests/e2e/billing-result-states.spec.ts
  modified:
    - /Users/zhdeng/stoa-frontend/src/pages/billing/CheckoutResultPage.tsx
    - /Users/zhdeng/stoa-frontend/src/app/router/AppRouter.tsx

key-decisions:
  - "Read only checkoutRef from the fixed result URL; flow, plan, status, and success-looking paths never contribute payment truth."
  - "Stop automatic confirming polls after four increasing delays and expose only same-reference recheck plus support recovery."
  - "Fail API errors, unknown outcomes, and malformed active payloads into support_needed instead of displaying paid access."

patterns-established:
  - "Authoritative result convergence: loading starts friendly-confirming, backend state selects one of four branches, and terminal branches stop polling."
  - "Recovery-only mutation: the result hook imports status and recheck capabilities but has no checkout-create capability."

requirements-completed: [V9BILL-02, V9BILL-04]

duration: 12min
completed: 2026-07-24
---

# Phase 476 Plan 24: Authoritative Checkout Convergence Summary

**The Stripe return journey now converges one opaque checkout reference through finite polling and same-operation recheck while rendering paid access only from authoritative active backend state.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-24T16:38:54Z
- **Completed:** 2026-07-24T16:50:49Z
- **Tasks:** 1
- **Files modified:** 4 frontend files plus plan metadata and this summary

## Accomplishments

- Replaced virtual and static success/cancel routes with the single protected `/billing/checkout/result` route.
- Added a dedicated TanStack Query hook that retrieves only `/parents/me/subscription/checkout/{checkoutRef}`, polls only while confirming, stops after four increasing delays or any terminal outcome, and rechecks only the same reference.
- Added accessible confirming, active, not-completed, and support-needed branches; active requires and displays the server effective plan and beneficiaries.
- Added six source-bound Chromium scenarios covering load, all four outcomes, terminal polling, bounded recovery, same-reference empty-body recheck, API failure, unknown outcome, foreign/missing references, and success-looking URL/query negatives.

## Task Commits

TDD execution produced the required RED and GREEN commits in `/Users/zhdeng/stoa-frontend`:

1. **Task 476-24-01 RED: Add failing checkout convergence coverage** - `e1f1412` (test)
2. **Task 476-24-01 GREEN: Converge checkout result on authoritative status** - `7fa5e92` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-frontend/src/hooks/billing/useCheckoutCommandQuery.ts` - Finite confirming-only status polling and same-reference recheck mutation.
- `/Users/zhdeng/stoa-frontend/src/pages/billing/CheckoutResultPage.tsx` - Four authoritative, fail-closed, accessible checkout-result branches.
- `/Users/zhdeng/stoa-frontend/src/app/router/AppRouter.tsx` - One fixed result route with legacy virtual/static routes removed.
- `/Users/zhdeng/stoa-frontend/tests/e2e/billing-result-states.spec.ts` - Six browser scenarios for truth, recovery, polling, negative URLs, and accessibility.
- `.planning/phases/476-billing-idempotency-and-paid-access-recovery/476-24-PLAN.md` - Repository-relative key-link source path for executable verification.

## Decisions Made

- The result page reads `checkoutRef` and deliberately ignores the server-generated non-authoritative `flow` hint and every caller-supplied plan/status value.
- Automatic checks use a finite 500 ms, 1 s, 1.5 s, and 2 s cadence. A still-confirming operation then becomes a static recovery state with a same-reference recheck and support link rather than an endless spinner.
- An `active` outcome is rendered only when the response also contains an effective paid plan and at least one beneficiary; incomplete or unknown data fails closed into support-needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Verification] Made the cross-repository key link verifier-resolvable**
- **Found during:** Task 476-24-01 acceptance gate
- **Issue:** The verifier resolved the absolute frontend `key_links.from` value inside the backend planning repository and reported `Source file not found`.
- **Fix:** Changed only that key-link source to `../stoa-frontend/src/pages/billing/CheckoutResultPage.tsx`, preserving the same artifact and pattern.
- **Files modified:** `.planning/phases/476-billing-idempotency-and-paid-access-recovery/476-24-PLAN.md`
- **Verification:** `gsd-tools verify key-links .../476-24-PLAN.md` reports `all_verified: true`, `verified: 1`, `total: 1`.
- **Committed in:** Plan metadata commit

---

**Total deviations:** 1 auto-fixed (1 blocking verification issue).
**Impact on plan:** The change only makes the planned cross-repository source link executable; implementation scope and behavior are unchanged.

## Security Verification

- **Success-looking URL spoofing:** fixed result route ignores `flow`, `plan`, and `status`; removed success/cancel paths cannot render active.
- **Foreign or missing reference disclosure:** 404, missing reference, API failure, and unknown outcome all render the same generic support-needed branch without backend detail.
- **Create-capable recheck:** result hooks depend only on GET status and POST same-ref recheck; browser interception proves the create endpoint is never called.
- **Polling denial of service:** polling occurs only for confirming and stops on terminal state or after the finite four-delay window.
- **Source binding:** key-link verifier passes 1/1 from `CheckoutResultPage.tsx` through `useCheckoutCommandQuery`.
- **Automated results:** `npm run typecheck` passed; focused ESLint passed; Playwright Chromium passed 6/6.

## Known Stubs

None.

## Issues Encountered

- The plan references a phase-wide `scripts/verify_phase476_security_gate.py`, but that aggregate script is not present in the backend workspace yet. This plan does not claim that future phase-wide gate was run; its exact frontend verification and all four listed High-threat selectors passed locally.
- The first Playwright invocation could not write `test-results` under the managed sandbox. The identical focused command was rerun with approved local filesystem access and completed without external network, provider, production, or deployment operations.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 476-25 can consume the authoritative checkout-result state without relying on redirect, path, or query truth.
- Phase-wide security publication still requires the later aggregate gate artifact; no production or real payment-provider operation was performed.

## Self-Check: PASSED

- Created frontend hook and browser test exist.
- Modified result page and router exist.
- Frontend commits `e1f1412` and `7fa5e92` exist.
- Typecheck, focused lint, Chromium 6/6, and key-link 1/1 all pass.

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
