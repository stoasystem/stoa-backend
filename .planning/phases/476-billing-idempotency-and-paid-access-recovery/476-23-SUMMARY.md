---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 23
subsystem: payments
tags: [react, typescript, tanstack-query, playwright, checkout, idempotency]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Durable backend checkout create/status/recheck/supersede APIs and canonical Web billing contracts from Plans 09, 21, and 22
provides:
  - Session-retained Web checkout identity containing only an idempotency key and opaque checkout reference
  - Exact paid-plan and explicit active-beneficiary checkout request contract
  - TanStack Query command status/recheck state and confirmation-gated supersession
  - Browser proof for repeat, refresh, timeout/retry, cardinality, supersession, and no-demo failure behavior
affects: [476-24, 476-25, 476-28, web-billing, checkout-recovery]

tech-stack:
  added: []
  patterns:
    - Browser checkout operation identity is retained separately from server command state
    - Successor checkout keys are deterministic cryptographic derivations of the retained logical key and confirmed intent
    - Strict runtime browser tests proxy local assets through a validated HTTPS staging descriptor/config fixture

key-files:
  created:
    - /Users/zhdeng/stoa-frontend/tests/e2e/billing-command-ui.spec.ts
  modified:
    - /Users/zhdeng/stoa-frontend/src/services/billing/billingApi.ts
    - /Users/zhdeng/stoa-frontend/src/hooks/billing/useCreateCheckoutSessionMutation.ts
    - /Users/zhdeng/stoa-frontend/src/pages/billing/BillingPage.tsx
    - /Users/zhdeng/stoa-frontend/src/components/parent/ParentSubscriptionOperationsCard.tsx

key-decisions:
  - "Persist exactly idempotencyKey and optional checkoutRef under stoa.billing.checkout.v1; plan, beneficiaries, provider URLs, and secrets remain server/query state."
  - "Derive a stable successor key from the retained random key and confirmed normalized intent so supersession timeouts can replay without storing extra intent."
  - "Keep legacy manual subscription requests available but route all payable checkout entry through the canonical Billing page."

patterns-established:
  - "Durable Web command: create retries reuse one retained key, refresh resumes by opaque reference, and terminal backend state clears the operation."
  - "Confirmed supersession: changed plan or beneficiary intent first presents cancel/confirm UI; only confirm calls the successor endpoint."

requirements-completed: [V9BILL-01, V9BILL-02, V9BILL-04]

duration: 21min
completed: 2026-07-24
---

# Phase 476 Plan 23: Durable Web Checkout Command Summary

**Parent checkout now carries one retained logical operation through repeat clicks, refreshes, timeouts, explicit beneficiary selection, and confirmed plan changes without browser callback URLs or demo success.**

## Performance

- **Duration:** 21 min
- **Started:** 2026-07-24T15:53:54Z
- **Completed:** 2026-07-24T16:14:44Z
- **Tasks:** 1
- **Files modified:** 5 frontend files plus plan metadata and this summary

## Accomplishments

- Replaced legacy tier translation, mock plan loading, browser callback URLs, UTM checkout fields, and preview/demo success with the exact `{plan, beneficiaryIds}` backend command and `Idempotency-Key`.
- Added `CheckoutOperationStore`, `getOrCreateCheckoutOperation()`, `clearTerminalCheckoutOperation()`, `getCheckoutCommand()`, `recheckCheckoutCommand()`, and `supersedeCheckoutCommand()` with session storage restricted to the logical key and opaque reference.
- Added TanStack Query status/recheck state, exact beneficiary cardinality, open-command blocking, and explicit cancel/confirm supersession UI.
- Removed the legacy parent dashboard checkout mutation and provider URL link; payable actions now enter the canonical Billing flow.
- Added five focused browser tests covering repeat click, refresh, timeout/retry, storage/request shape, free-trial/cardinality denial, supersession consent, and backend-failure no-demo behavior.

## Task Commits

TDD execution produced the required RED and GREEN commits in `/Users/zhdeng/stoa-frontend`:

1. **Task 476-23-01 RED: Add failing durable checkout browser contract** - `675a561` (test)
2. **Task 476-23-01 GREEN: Carry durable checkout identity through Web** - `6ab4ffa` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-frontend/tests/e2e/billing-command-ui.spec.ts` - Source-bound HTTPS runtime fixture and five durable-command browser scenarios.
- `/Users/zhdeng/stoa-frontend/src/services/billing/billingApi.ts` - Exact command API, minimal operation store, status/recheck, and deterministic supersession.
- `/Users/zhdeng/stoa-frontend/src/hooks/billing/useCreateCheckoutSessionMutation.ts` - TanStack Query command state plus create/recheck/supersede mutations.
- `/Users/zhdeng/stoa-frontend/src/pages/billing/BillingPage.tsx` - Explicit beneficiary selection, cardinality checks, retained-command blocking, and supersession consent.
- `/Users/zhdeng/stoa-frontend/src/components/parent/ParentSubscriptionOperationsCard.tsx` - Removes callback-bound checkout and provider URL exposure in favor of the canonical Billing route.

## Decisions Made

- Browser persistence is deliberately smaller than checkout intent: only the random logical key and returned opaque reference survive refresh. The authoritative plan and beneficiary intent are re-read from the backend command through TanStack Query.
- Supersession does not overwrite the retained original operation before the backend responds. Its successor key is reproducibly derived from the original random key and normalized confirmed intent, so a lost response retries the same successor.
- Recheck accepts no caller-supplied reference in the hook and always targets the currently retained original checkout reference.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Test Infrastructure] Added a validated HTTPS runtime fixture for focused browser execution**
- **Found during:** Task 476-23-01 RED
- **Issue:** The current strict startup barrier rejects the Playwright server's plain-HTTP origin and requires immutable served-release/runtime-config evidence before importing the app, so the pre-existing billing E2E analog could not start the application.
- **Fix:** The focused spec serves a valid staging descriptor/config, proxies only local Vite assets under the validated HTTPS origin, intercepts every billing API call, and synchronizes route teardown.
- **Files modified:** `tests/e2e/billing-command-ui.spec.ts`
- **Verification:** Exact focused Playwright command passes 5/5 without external network, provider, or production access.
- **Committed in:** `6ab4ffa`

**2. [Rule 2 - Missing Critical Retry Safety] Made confirmed supersession replay-stable after a lost response**
- **Found during:** Task 476-23-01 GREEN security review
- **Issue:** Generating and storing a fresh random successor key before every supersession call would drift after a timeout or overwrite the original reference before authoritative success.
- **Fix:** Derive the successor key cryptographically from the retained random key plus normalized confirmed intent, retain the original operation until success, and then atomically store the returned successor reference.
- **Files modified:** `src/services/billing/billingApi.ts`
- **Verification:** Typecheck, lint, exact request/storage assertions, supersession browser test, and source selectors pass.
- **Committed in:** `6ab4ffa`

---

**Total deviations:** 2 auto-fixed (1 blocking test infrastructure issue, 1 missing critical retry-safety behavior).
**Impact on plan:** Both changes are required to prove and preserve the planned durable-command security contract. No dependency, visual redesign, provider call, real charge, deployment, or production mutation was added.

## Security Verification

- `stoa.billing.checkout.v1` serializes only `idempotencyKey` and optional `checkoutRef`; browser plan, beneficiaries, Stripe URL, Session ID, secrets, callback URLs, and provider evidence are not persisted.
- Create sends exactly `plan` and normalized `beneficiaryIds` with one retained `Idempotency-Key`.
- Repeat click is guarded before a second request; timeout retry reuses the same retained key; refresh resumes the same reference without another create.
- Free Trial and invalid Student/Teacher-supported/Family beneficiary counts cannot invoke create.
- An open command disables identical create. Changed intent presents explicit confirmation; cancel leaves the original operation untouched and confirm invokes supersede exactly once.
- Recheck is bound to the retained reference and cannot accept an alternate caller-supplied checkout reference.
- Backend failure remains on Billing with an actionable error; demo, virtual, and static success routes cannot replace it.
- Active beneficiary choices come only from the authorized parent children API and remain subject to backend relationship revalidation.
- GSD source link verifies `1/1` from the billing mutation hook through the retained `Idempotency-Key` contract.
- No unresolved ASVS L1 High threat remains in this plan's source boundary.

## Verification

- Exact plan gate: `npm run typecheck && npm run test:e2e -- billing-command-ui.spec.ts --project=chromium` passes; Playwright reports `5 passed`.
- `npm run lint -- --quiet` passes.
- `git diff --check` passes.
- Request-shape, storage-shape, callback/UTM/demo absence, beneficiary/cardinality, supersession, and production-config negative selectors pass.
- `gsd-tools verify key-links .../476-23-PLAN.md` reports `all_verified: true`, `1/1`.

## Known Stubs

None. Empty browser test arrays are request-capture fixtures, optional null checkout fields are closed backend response states, and existing Billing unavailability copy is an intentional error state rather than unwired data.

## Issues Encountered

- The Plan 23 key-link verifier initially could not resolve the absolute frontend source path. Matching the approved Plan 22 cross-repository convention, only `must_haves.key_links.from` was changed to `../stoa-frontend/...`; verification then passed `1/1`.
- The browser fixture performs no external Stripe, backend, staging, or production request; every release descriptor, runtime config, application asset, and billing API response is locally controlled.

## User Setup Required

None - no dependency, credential, provider operation, real charge, deployment, or production change is required.

## Next Phase Readiness

- Plan 24/28 result and provider acceptance flows can consume the retained opaque checkout reference and the status/recheck contract.
- Plan 25 can build authoritative allowance/reminder rendering on the same canonical Billing page without inheriting legacy plan mapping or demo checkout branches.
- The frontend worktree is clean at `6ab4ffa`; backend user changes outside Plan 476-23 remain unstaged and untouched.

## TDD Gate Compliance

- RED: `675a561` failed on the absent durable checkout beneficiary/command UI.
- GREEN: `6ab4ffa` passes the exact typecheck and all five focused browser scenarios.

## Self-Check: PASSED

- FOUND: all five frontend implementation/test files and `476-23-SUMMARY.md`.
- FOUND: RED commit `675a561`.
- FOUND: GREEN commit `6ab4ffa`.
- PASS: exact TypeScript and focused five-scenario Playwright gate.
- PASS: lint, source selectors, `git diff --check`, and GSD key link `1/1`.

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
