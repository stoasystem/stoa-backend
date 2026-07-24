---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 22
subsystem: payments
tags: [react, typescript, billing, pricing, localization]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Canonical backend BillingPlanId, PurchasablePlanId, checkout outcome, allowance, and masked-payment contracts from Plans 01, 03, and 15
provides:
  - Exact Web SubscriptionPlan vocabulary for free_trial, student, teacher_supported, and family
  - Discriminated CHF pricing catalog that structurally prevents free-trial checkout
  - Checkout command, weekly allowance, beneficiary, masked payment, and reminder TypeScript contracts
  - English and German teacher_supported pricing/localization keys
affects: [476-23, 476-25, web-billing, checkout, allowance-projections]

tech-stack:
  added: []
  patterns:
    - Mapped discriminated unions bind plan identity to locked price and purchasability
    - Compile-time contract tests use exact-union assertions and expected type failures

key-files:
  created:
    - /Users/zhdeng/stoa-frontend/src/types/billing.contract.test-d.ts
  modified:
    - /Users/zhdeng/stoa-frontend/src/types/user.ts
    - /Users/zhdeng/stoa-frontend/src/types/billing.ts
    - /Users/zhdeng/stoa-frontend/src/components/pricing/pricingPlans.ts
    - /Users/zhdeng/stoa-frontend/src/i18n/locales/en/pricing.json
    - /Users/zhdeng/stoa-frontend/src/i18n/locales/de/pricing.json

key-decisions:
  - "Bind each BillingPlan ID to its exact CHF monthly price and purchasability in one discriminated TypeScript union."
  - "Keep the pre-Plan-25 request-count UI shape component-local so the canonical billing type module exposes only weekly input/output/support allowance dimensions."
  - "Expose only brand, last four, and expiry coordinates in the Web MaskedPaymentMethod contract."

patterns-established:
  - "Canonical product catalog: a four-entry tuple covers the entire SubscriptionPlan union and makes free_trial the sole non-purchasable entry."
  - "Safe billing projection: browser-facing payment types omit PAN, CVC, provider credentials, and payment-capable identifiers."

requirements-completed: [V9BILL-01, V9BILL-04]

duration: 10min
completed: 2026-07-24
---

# Phase 476 Plan 22: Web Billing Contract Integration Summary

**The Web now shares the backend’s four exact plan identities, locked CHF catalog, checkout outcomes, weekly allowance vocabulary, and closed masked-payment projection without a hidden tutor tier.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-24T10:18:43Z
- **Completed:** 2026-07-24T10:28:45Z
- **Tasks:** 1
- **Files modified:** 17

## Accomplishments

- Replaced `tutor_supported` and legacy subscription-plan aliases with the exact `free_trial|student|teacher_supported|family` Web union.
- Bound the four product cards to CHF 0/29/89/149 and made `free_trial` structurally and behaviorally non-purchasable.
- Added browser-facing checkout command/outcome, Zurich weekly allowance, beneficiary, masked payment method, and reminder contracts with backend-compatible camelCase fields.
- Updated English/German pricing, billing, and shared plan-label keys so active canonical lookups use `teacher_supported`.
- Added compile-time tests that reject the tutor alias, a purchasable free trial, CVC, full-card values, and provider secrets.

## Task Commits

TDD execution produced the required RED and GREEN commits in `/Users/zhdeng/stoa-frontend`:

1. **Task 476-22-01 RED: Add failing Web billing contract** - `830cd6b` (test)
2. **Task 476-22-01 GREEN: Establish canonical Web billing contract** - `225fa1b` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-frontend/src/types/billing.contract.test-d.ts` - Exact-union, catalog-coverage, purchasability, and sensitive-field rejection proof.
- `/Users/zhdeng/stoa-frontend/src/types/user.ts` - Closed four-plan `SubscriptionPlan` with no legacy product-plan union.
- `/Users/zhdeng/stoa-frontend/src/types/billing.ts` - Canonical plan, checkout, allowance, beneficiary, masked payment, and reminder contracts.
- `/Users/zhdeng/stoa-frontend/src/components/pricing/pricingPlans.ts` - Exact four-entry CHF catalog with typed paid/free semantics.
- `/Users/zhdeng/stoa-frontend/src/components/billing/PlanCard.tsx` and `src/pages/pricing/PricingPage.tsx` - Non-purchasable trial CTA cannot dispatch a checkout selection.
- `/Users/zhdeng/stoa-frontend/src/i18n/locales/{en,de}/{pricing,billing,common}.json` - Canonical `teacher_supported` keys and teacher-facing copy.
- Direct typed consumers in `src/data/phase11MockData.ts`, `src/services/billing/billingApi.ts`, `src/pages/billing/BillingPage.tsx`, and `src/lib/displayLabels.ts` now compile with `teacher_supported`.

## Decisions Made

- Used a mapped discriminated union rather than an uncorrelated `id`, price, and boolean object so TypeScript rejects both wrong prices and a purchasable free trial.
- Mirrored backend checkout lifecycle/action literals and camelCase aliases directly; no browser plan mapper was added to the canonical type module.
- Kept current request-count rendering isolated as a component-local compatibility shape. Plan 25 still owns the server-driven weekly allowance UI conversion.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Enforced non-checkout behavior in the existing pricing card**
- **Found during:** Task 476-22-01 GREEN implementation
- **Issue:** Adding `purchasable=false` to catalog data alone did not stop the existing card callback from selecting `free_trial`.
- **Fix:** Narrowed pricing selection callbacks to paid plans, disabled the free-trial card action, and guarded callback dispatch on the discriminant.
- **Files modified:** `src/components/billing/PlanCard.tsx`, `src/pages/pricing/PricingPage.tsx`
- **Verification:** Typecheck plus source selector confirms callback dispatch is guarded by `plan.purchasable`.
- **Committed in:** `225fa1b`

**2. [Rule 3 - Blocking] Migrated direct consumers after closing the canonical type module**
- **Found during:** Task 476-22-01 GREEN typecheck
- **Issue:** Removing the tutor plan and request-count export exposed direct catalog, label, route-guard, mock, service, and usage-card compile dependencies outside the plan’s primary file list.
- **Fix:** Canonicalized active teacher-supported consumers and kept the pre-Plan-25 usage shape local to its existing component instead of retaining it in `types/billing.ts`.
- **Files modified:** `src/components/billing/PlanUsageCard.tsx`, `src/data/phase11MockData.ts`, `src/services/billing/billingApi.ts`, `src/pages/billing/BillingPage.tsx`, `src/lib/displayLabels.ts`, and English/German billing/common locale files.
- **Verification:** `npm run typecheck` and `npm run lint -- --quiet` pass.
- **Committed in:** `225fa1b`

---

**Total deviations:** 2 auto-fixed (1 missing critical functionality, 1 blocking integration issue).
**Impact on plan:** Both changes are narrow contract-integration work required for financial correctness and a clean build; no checkout workflow or visual redesign from Plans 23/25 was implemented.

## Security Verification

- Compile-time tests prove the exact four plan IDs and four public checkout outcomes.
- The four-card AST selector observed exactly CHF 0/29/89/149 with only `free_trial` non-purchasable.
- English/German pricing JSON contains the canonical four IDs and no `tutor_supported` key.
- Canonical contract sources contain no request-count fields, PAN, CVC, provider secret, or provider API-key fields.
- Expected TypeScript errors reject `tutor_supported`, a purchasable trial, CVC, full-card number, and provider-secret properties.
- The aggregate `scripts/verify_phase476_security_gate.py` is not present yet; local source-bound selectors cover every Plan 476-22 mitigation without claiming the later aggregate phase gate ran.
- No real charge, provider operation, deployment, or production mutation was performed.

## Known Stubs

- `src/components/billing/PlanUsageCard.tsx` retains the pre-existing request-count rendering through a component-local compatibility shape. It is intentionally excluded from the canonical billing type module; Plan 25 owns replacement with the server-provided weekly allowance projection.

## Issues Encountered

- The first GREEN typecheck correctly exposed direct consumers of the removed canonical exports. They were migrated narrowly under deviation Rule 3, and the complete frontend typecheck/lint gate then passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 23 can consume `PurchasableSubscriptionPlan` and `CheckoutCommand` while implementing retained idempotency identity and explicit beneficiary checkout.
- Plan 25 can replace the isolated legacy usage rendering with `BillingAllowance` and `PaymentReminder`.
- The frontend worktree is clean at `225fa1b`; the separate backend’s pre-existing dirty user files were not staged or modified.

## Self-Check: PASSED

- FOUND: `/Users/zhdeng/stoa-frontend/src/types/user.ts`
- FOUND: `/Users/zhdeng/stoa-frontend/src/types/billing.ts`
- FOUND: `/Users/zhdeng/stoa-frontend/src/types/billing.contract.test-d.ts`
- FOUND: `/Users/zhdeng/stoa-frontend/src/components/pricing/pricingPlans.ts`
- FOUND: English/German pricing locale files
- FOUND: frontend commits `830cd6b` and `225fa1b`
- PASS: `npm run typecheck`
- PASS: `npm run lint -- --quiet`
- PASS: source-bound catalog, locale, free-trial, and sensitive-field selector

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
