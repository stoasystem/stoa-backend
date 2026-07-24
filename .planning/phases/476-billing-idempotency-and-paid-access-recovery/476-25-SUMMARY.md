---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 25
subsystem: payments-ui
tags: [react, typescript, tanstack-query, playwright, allowance, payment-reminders]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Authoritative parent billing projection, persistent family reminder state, and closed Web billing types from Plans 20 through 23
provides:
  - Server-driven parent weekly input/output/support allowance rendering
  - One authenticated-layout masked payment reminder for parent and selected beneficiary students
  - Explicit in-app-only, email-failed, loading, error, resolved, and replacement states
  - Browser proof for recipient scope, arithmetic boundaries, redaction, trace safety, and accessibility
affects: [476-28, web-billing, parent-dashboard, student-dashboard, phase-476-security-gate]

tech-stack:
  added: []
  patterns:
    - Authenticated shared layout consumes one closed masked reminder projection for parent and student
    - Weekly allowance UI formats server percentages and remaining values without client limit arithmetic
    - Payment delivery state is informational and cannot alter authoritative billing state

key-files:
  created:
    - /Users/zhdeng/stoa-frontend/src/components/billing/PaymentMethodReminderBanner.tsx
    - /Users/zhdeng/stoa-frontend/tests/e2e/billing-allowance-reminder.spec.ts
  modified:
    - /Users/zhdeng/stoa-frontend/src/components/billing/PlanUsageCard.tsx
    - /Users/zhdeng/stoa-frontend/src/components/billing/BillingStatusAlert.tsx
    - /Users/zhdeng/stoa-frontend/src/layouts/DashboardLayout.tsx
    - /Users/zhdeng/stoa-frontend/src/services/billing/billingApi.ts
    - /Users/zhdeng/stoa-frontend/src/hooks/billing/useBillingUsageQuery.ts
    - /Users/zhdeng/stoa-frontend/src/hooks/notifications/useNotificationsQuery.ts
    - /Users/zhdeng/stoa-frontend/src/types/billing.ts

key-decisions:
  - "Render parent allowance directly from the authoritative /parents/me/subscription/billing percentage, remaining, support-case, and Zurich-window fields; no client plan-limit table or usage arithmetic remains."
  - "Use the same PaymentMethodReminder copy and closed masked parser for parent and selected student recipients, while exposing the Billing action only to the parent role."
  - "Prefer recipient-scoped notification reminder state and retain the parent billing projection as the persistent fallback; only backend-resolved state clears a reminder."

patterns-established:
  - "Shared reminder: DashboardLayout owns one non-blocking banner whose content is identical across parent and selected student roles."
  - "Safe payment rendering: only CHF price, billing state, brand, last four, expiry, and closed delivery status cross into the component."

requirements-completed: [V9BILL-04]

duration: 18min
completed: 2026-07-24
---

# Phase 476 Plan 25: Weekly Allowance and Shared Billing Reminder Summary

**Parent billing now renders authoritative Zurich-week allowance percentages and selected family members receive one persistent masked payment reminder without email coupling or payment-capable data.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-24T16:56:38Z
- **Completed:** 2026-07-24T17:14:17Z
- **Tasks:** 1
- **Files modified:** 9 frontend files plus plan metadata and this summary

## Accomplishments

- Replaced legacy learning-message, upload, and teacher-request counters with backend-provided weekly input/output percentages, remaining tokens, support cases, and Europe/Zurich boundaries.
- Added one authenticated `DashboardLayout` reminder for parents and exact recipient-projected students with identical short copy, masked method details, persistent resolved/replacement behavior, and a parent-only Billing action.
- Kept in-app delivery visible when email is ineligible or failed and rendered delivery status independently from authoritative billing state.
- Added eight focused browser scenarios for parent/student scope, allowance boundaries, in-app-only and email-failure behavior, replacement clearing, explicit loading/error/empty states, redaction, trace safety, and keyboard-accessible selectors.

## Task Commits

TDD execution produced the required RED and GREEN commits in `/Users/zhdeng/stoa-frontend`:

1. **Task 476-25-01 RED: Add failing allowance and reminder browser contract** - `d6bc13b` (test)
2. **Task 476-25-01 GREEN: Render weekly allowance and shared reminder** - `8d931f8` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-frontend/src/components/billing/PaymentMethodReminderBanner.tsx` - Closed role-scoped reminder selection, masked parsing, shared copy, delivery state, loading/error behavior, and parent-only Billing link.
- `/Users/zhdeng/stoa-frontend/src/components/billing/PlanUsageCard.tsx` - Weekly server percentage/remaining/support rendering and Zurich window formatting.
- `/Users/zhdeng/stoa-frontend/src/components/billing/BillingStatusAlert.tsx` - Server-confirmed billing status with explicit loading and error states instead of environment-mode copy.
- `/Users/zhdeng/stoa-frontend/src/layouts/DashboardLayout.tsx` - Common authenticated placement for the reminder across retained parent and student surfaces.
- `/Users/zhdeng/stoa-frontend/src/services/billing/billingApi.ts` - Replaces legacy subscription/request-count mapping with the authoritative billing projection request.
- `/Users/zhdeng/stoa-frontend/src/hooks/billing/useBillingUsageQuery.ts` - Parent-only authoritative billing query with no retry-driven ambiguity.
- `/Users/zhdeng/stoa-frontend/src/hooks/notifications/useNotificationsQuery.ts` - Optional role gating and explicit error behavior for shared reminder consumption.
- `/Users/zhdeng/stoa-frontend/src/types/billing.ts` - Parent billing overview, Zurich window, and closed reminder delivery-state contracts.
- `/Users/zhdeng/stoa-frontend/tests/e2e/billing-allowance-reminder.spec.ts` - Eight runtime/source scenarios plus masked trace canaries.

## Decisions Made

- Parent allowance output uses the server maps exactly. Formatting adds locale separators and a progress bar but never derives limits, used counts, or percentages.
- Selected-student visibility starts with the authorization-filtered notification response and additionally requires exact recipient ID, role, target type, and closed reminder shape before rendering.
- Parent reminders prefer the same recipient notification projection used by students and fall back to the parent billing overview so a missing or failed email channel cannot remove persistent Web state.
- The action copy remains shared across roles; only the already-authorized parent receives the Billing navigation control.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Integration] Wired the planned components to authoritative billing and recipient-scoped notification data**
- **Found during:** Task 476-25-01 GREEN
- **Issue:** The listed components still consumed a legacy `/parents/me/subscription` request-count mapper, and the shared layout had no closed reminder query path, so UI-only edits would have rendered fabricated limits or unwired state.
- **Fix:** Added the exact billing overview type, switched the usage query to `/parents/me/subscription/billing`, gated it to parents, and made notification querying role-aware for the shared banner.
- **Files modified:** `src/types/billing.ts`, `src/services/billing/billingApi.ts`, `src/hooks/billing/useBillingUsageQuery.ts`, `src/hooks/notifications/useNotificationsQuery.ts`
- **Verification:** Typecheck, lint, all eight browser scenarios, and source selectors pass.
- **Committed in:** `8d931f8`

**2. [Rule 3 - Blocking Verification] Made the cross-repository key link resolvable**
- **Found during:** Post-GREEN GSD key-link verification
- **Issue:** The verifier reported `Source file not found` for the plan's absolute frontend key-link paths despite both sources existing.
- **Fix:** Changed only the Plan 476-25 `must_haves.key_links` `from` and `to` fields to the established backend-relative `../stoa-frontend/...` paths.
- **Files modified:** `.planning/phases/476-billing-idempotency-and-paid-access-recovery/476-25-PLAN.md`
- **Verification:** `gsd-tools verify key-links` reports `all_verified: true`, `1/1`.
- **Committed in:** Plan metadata commit

---

**Total deviations:** 2 auto-fixed (1 missing critical data integration, 1 blocking cross-repository verification issue).
**Impact on plan:** Both changes were necessary to bind UI to existing authoritative projections and prove the requested layout connection. No dependency, endpoint, provider call, notification delivery, visual redesign, deployment, or production operation was added.

## Security Verification

- The allowance card renders only backend-provided percentage, remaining, support-case, beneficiary, and Zurich-window fields. Legacy daily counters, hardcoded limits, and client arithmetic are absent.
- Reminder selection requires the authenticated role to be parent or student; notification rendering additionally requires exact returned recipient ID/role and `billing_payment_method` target type.
- The runtime parser admits only reminder identity, billing state, nonnegative CHF price, brand, four digits, bounded expiry, resolved timestamps, and the closed in-app/email status union.
- Parent and selected student tests observe byte-equivalent reminder copy; an unselected student receives no banner.
- Email-failed and in-app-only scenarios retain the same `Active` billing state and persistent in-app banner.
- Resolved old state is ignored and the newer active masked method is the only rendered banner.
- The banner is a non-blocking `role="status"` region; its only action is a keyboard-native parent link.
- DOM, local storage, session storage, console, source, and eight generated Playwright traces contain none of the full-card, CVC, provider-method, or secret canaries.
- GSD source verification reports the `DashboardLayout.tsx` → `PaymentMethodReminderBanner.tsx` link passing `1/1`.
- No unresolved ASVS L1 High threat remains within this plan's frontend source boundary.

## Verification

- Exact plan gate passes: `npm run typecheck && npm run test:e2e -- billing-allowance-reminder.spec.ts --project=chromium`; Playwright reports `8 passed`.
- `npm run lint -- --quiet` passes.
- Traced focused run passes `8/8`; direct archive scan reports `TRACE_CANARIES_ABSENT`.
- Daily-counter, hardcoded-limit, sensitive-field, server-projection, role, resolved-state, and layout-link source selectors pass.
- `git diff --check` passes in both frontend and backend planning repositories.
- GSD key-link verification passes `1/1`.

## Known Stubs

None. Null reminder/window values and empty authorized notification lists are explicit server absence states, not mock or unwired data sources.

## Issues Encountered

- The Phase 476 aggregate `scripts/verify_phase476_security_gate.py` is still absent, matching prior Plan 20 through 24 summaries. This plan records passing focused source/runtime evidence without claiming the later aggregate phase gate.
- The managed sandbox allowed source edits but blocked Playwright result metadata and frontend git index writes because the execution workspace root is the backend. Focused runs and both normal-hook commits used the approved execution path; no verification bypass was used.
- The initial parent browser fixture used a broader dashboard route with unrelated incomplete data dependencies. The focused proof was corrected to the retained parent Billing surface, while the common layout link separately proves placement across authenticated parent/student surfaces.

## User Setup Required

None - no dependency, credential, provider configuration, real notification delivery, charge, deployment, or production mutation is required.

## Next Phase Readiness

- Plan 28 and the final Phase 476 verification can include the eight role/arithmetic/lifecycle/redaction selectors and the 1/1 common-layout source link.
- Parent and selected-student Web surfaces now consume existing projections only; later work may integrate the already-defined backend reminder worker without changing this UI contract.
- The frontend worktree is clean at `8d931f8`; backend user changes outside Plan 476-25 remain unstaged and untouched.

## TDD Gate Compliance

- RED: `d6bc13b` produced six expected behavior failures for absent allowance/reminder/loading/source-link UI while two negative safety scenarios already passed.
- GREEN: `8d931f8` passes typecheck, lint, the exact eight-scenario Chromium command, and an additional traced eight-scenario run.

## Self-Check: PASSED

- FOUND: all nine frontend implementation/test files and `476-25-SUMMARY.md`.
- FOUND: RED commit `d6bc13b`.
- FOUND: GREEN commit `8d931f8`.
- PASS: exact typecheck and focused eight-scenario Playwright gate.
- PASS: lint, traced canary scan, `git diff --check`, and GSD key link `1/1`.
- PASS: frontend worktree is clean after task commits.

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
