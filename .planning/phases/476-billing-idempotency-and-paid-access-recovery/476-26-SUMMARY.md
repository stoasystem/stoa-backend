---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 26
subsystem: payments
tags: [react, typescript, tanstack-query, playwright, admin, billing-recovery]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Capability-protected admin checkout read/recheck routes and redacted command/fact/grant/allowance projections from Plans 09 and 21
provides:
  - Typed read-only admin billing-operation detail and immutable same-reference recheck adapters
  - TanStack Query detail key and recheck invalidation bound to one parent and checkout reference
  - Retained admin account-operations integration for lifecycle, evidence, versions, usage, reminder, and reconciliation status
  - Browser proof for capability denial, expired sessions, redaction, provider errors, contention, and absent payment authority
affects: [476-28, 476-29, admin-billing-support, web-billing-recovery]

tech-stack:
  added: []
  patterns:
    - Admin billing support adapters expose read and empty-body same-reference recheck only
    - Strict browser tests run behind a validated served-release and runtime-config fixture

key-files:
  created:
    - /Users/zhdeng/stoa-frontend/src/hooks/admin/useAdminBillingOperation.ts
    - /Users/zhdeng/stoa-frontend/tests/e2e/admin-billing-recovery.spec.ts
  modified:
    - /Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts
    - /Users/zhdeng/stoa-frontend/src/pages/admin/AdminAccountOperationsPage.tsx
    - .planning/phases/476-billing-idempotency-and-paid-access-recovery/476-26-PLAN.md

key-decisions:
  - "Bind both detail and recheck closures to the same parentId and checkoutRef; recheck sends exactly an empty object and refreshes only that detail key."
  - "Render only backend-approved digests, exact token counts, masked reminder coordinates, and a provider-session suffix; no raw provider object or payment mutation type enters the Web contract."
  - "Treat active effective plan as converged only when the active reconciliation state has current grant versions; otherwise show pending convergence rather than infer entitlement."

patterns-established:
  - "Read-only recovery view: support may inspect redacted evidence and invoke one idempotent recheck without status, plan, beneficiary, callback, or entitlement authority."
  - "Explicit support errors: capability denial, dependency outage, contention, missing checkout, expired session, and support-needed lifecycle remain distinguishable."

requirements-completed: [V9BILL-02, V9BILL-04]

duration: 13min
completed: 2026-07-24
---

# Phase 476 Plan 26: Admin Billing Recovery Web Integration Summary

**Authorized support can inspect one checkout’s redacted command, billing facts, entitlement versions, token evidence, reminder, and reconciliation state, then recheck only that immutable operation without payment authority.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-24T16:19:23Z
- **Completed:** 2026-07-24T16:32:02Z
- **Tasks:** 1
- **Files modified:** 4 frontend files plus plan metadata and this summary

## Accomplishments

- Added exact TypeScript DTOs and API adapters for `GET /admin/billing/checkouts/{checkoutRef}?parentId=…&detail=true` and empty-body `POST /admin/billing/checkouts/{checkoutRef}/recheck?parentId=…`.
- Added one TanStack Query detail identity per parent/reference and invalidated only that identity after recheck.
- Integrated billing recovery into the retained account-operations page with target/effective plan, beneficiaries, command/fact lifecycle, grant/allowance versions, exact provider token counts and digests, masked payment reminder, failure state, and redacted session suffix.
- Added six browser scenarios proving authorized evidence, support-needed recovery, same-ref empty-body recheck, wrong-capability denial, expired-session redirect, provider dependency failure, contention, redaction, and absent manual-success authority.

## Task Commits

TDD execution produced the required RED and GREEN commits in `/Users/zhdeng/stoa-frontend`:

1. **Task 476-26-01 RED: Add failing admin billing recovery coverage** - `7343be0` (test)
2. **Task 476-26-01 GREEN: Add read-only admin billing recovery view** - `4df774d` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts` - Redacted admin billing detail/recheck DTOs and exact read/empty-body adapters.
- `/Users/zhdeng/stoa-frontend/src/hooks/admin/useAdminBillingOperation.ts` - Same-reference query key, detail query, recheck mutation, and exact-key invalidation.
- `/Users/zhdeng/stoa-frontend/src/pages/admin/AdminAccountOperationsPage.tsx` - Retained admin support page integration with explicit evidence and error states.
- `/Users/zhdeng/stoa-frontend/tests/e2e/admin-billing-recovery.spec.ts` - Six source-bound browser/security scenarios.
- `.planning/phases/476-billing-idempotency-and-paid-access-recovery/476-26-PLAN.md` - Cross-repository key-link path made verifier-resolvable.

## Decisions Made

- The recheck hook closes over the same checkout reference used by the detail query; no mutation caller can supply a different reference or authority-bearing body.
- The Web contract mirrors the backend’s `extra="forbid"` redacted projection and intentionally omits checkout URLs, customer IDs, card numbers, client secrets, provider keys, and raw provider payloads.
- Effective plan is shown only when the operation is active and current grant versions are present. Other states explicitly remain pending convergence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Test Infrastructure] Added the current validated HTTPS runtime fixture**
- **Found during:** Task 476-26-01 RED/GREEN browser execution
- **Issue:** The strict startup barrier requires a valid served-release/runtime-config pair and rejects direct plain-HTTP `loginAs` startup before the feature page loads.
- **Fix:** The focused spec installs a validated local staging descriptor/config, proxies only local Vite assets under the validated HTTPS origin, and provides an authenticated admin shell.
- **Files modified:** `/Users/zhdeng/stoa-frontend/tests/e2e/admin-billing-recovery.spec.ts`
- **Verification:** Exact focused Playwright command passes 6/6 without external backend, provider, deployment, or production access.
- **Committed in:** `4df774d`

**2. [Rule 3 - Blocking Verification] Made the cross-repository key link verifier-resolvable**
- **Found during:** Final key-link verification
- **Issue:** `gsd-tools verify key-links` reported `Source file not found` for the absolute frontend hook path even though the implementation existed.
- **Fix:** Changed only `must_haves.key_links.from` in Plan 476-26 to backend-relative `../stoa-frontend/src/hooks/admin/useAdminBillingOperation.ts`.
- **Files modified:** `.planning/phases/476-billing-idempotency-and-paid-access-recovery/476-26-PLAN.md`
- **Verification:** GSD key-link verification passes `1/1`.
- **Committed in:** Plan metadata commit

---

**Total deviations:** 2 auto-fixed (2 blocking verification/infrastructure issues).
**Impact on plan:** Both changes were required to execute the planned source-bound browser and link gates. No UI redesign, provider operation, real charge, dependency, deployment, or production mutation was added.

## Security Verification

- Wrong capability returns an explicit denial and exposes no recheck action; the backend capability route remains the trust-boundary enforcement.
- Expired session clears authentication and returns to login without a recheck call.
- The only mutation path posts `{}` to the same immutable checkout reference and sends no plan, status, beneficiary, callback, entitlement, or payment-success field.
- DTOs and DOM expose digests, exact token counts, safe lifecycle/version coordinates, masked brand/last-four/expiry, and a short session suffix only.
- Full provider/card/key/checkout canaries are absent from DOM, browser storage, console output, and the focused test artifacts.
- Provider dependency and contention failures render explicit, actionable support states; support-needed remains distinct from active convergence.
- Source assertions find no mark-paid, manual-success, payment-status setter, or entitlement-active setter.
- GSD source link verifies `1/1` from the billing hook to `/admin/billing/checkouts/{checkoutRef}` through read and same-ref recheck.
- Every Plan 476-26 High-threat mitigation has an observed passing focused selector. The aggregate `scripts/verify_phase476_security_gate.py` does not exist yet because Plan 476-29 owns its creation; this plan does not claim that later phase-wide gate ran.

## Verification

- Exact plan command `npm run typecheck && npm run test:e2e -- admin-billing-recovery.spec.ts --project=chromium` passes; Playwright reports `6 passed`.
- `npm run lint -- --quiet` passes.
- `git diff --check` passes.
- Capability, expired-session, provider-error, contention, same-ref request/body, redaction, storage/console, and no-authority selectors pass.
- `gsd-tools verify key-links .../476-26-PLAN.md` reports `all_verified: true`, `1/1`.

## Known Stubs

None. Form input placeholders are labels for operator-entered identifiers, empty evidence states are explicit backend outcomes, and test-only response arrays are request-capture fixtures rather than unwired production data.

## Issues Encountered

- The first browser run reached the strict startup failure boundary because the older account-operations test analog did not install the current served-release/runtime-config contract. The focused fixture now follows the established Plan 23 HTTPS test pattern.
- The aggregate Phase 476 security gate is not runnable yet because its script is a future Plan 476-29 artifact. Focused source-bound Plan 476-26 selectors passed without overclaiming phase-wide closure.

## User Setup Required

None - no dependency, credential, provider operation, real charge, deployment, or production change is required.

## Next Phase Readiness

- Plan 476-28 can consume the admin recovery view as the redacted browser side of the approved Stripe sandbox journey.
- Plan 476-29 can bind these six passing browser selectors and the exact frontend commit into the aggregate threat/evidence registry.
- The frontend worktree is clean at `4df774d`; unrelated backend user changes remain unstaged and untouched.

## TDD Gate Compliance

- RED: `7343be0` failed because the required admin billing hook and recovery surface were absent.
- GREEN: `4df774d` passes typecheck, lint, and all six focused browser/security scenarios.

## Self-Check: PASSED

- FOUND: all four frontend implementation/test files and `476-26-SUMMARY.md`.
- FOUND: RED commit `7343be0`.
- FOUND: GREEN commit `4df774d`.
- PASS: exact TypeScript and six-scenario Playwright gate.
- PASS: lint, source selectors, `git diff --check`, and GSD key link `1/1`.

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
