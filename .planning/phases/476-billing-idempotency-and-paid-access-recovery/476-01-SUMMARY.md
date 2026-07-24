---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 01
subsystem: payments
tags: [pydantic, billing, stripe, entitlements, allowances, europe-zurich]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    provides: Durable command, idempotency, version, and relationship-convergence conventions
provides:
  - Closed four-plan billing vocabulary with a separate paid-checkout plan type
  - Distinct checkout command, signed billing fact, entitlement, and public outcome contracts
  - Strict Zurich-week token, provider-cost, reservation, finalization, and support-case evidence
affects: [476-02, 476-03, 476-04, 476-05, billing, entitlements, allowance-accounting]

tech-stack:
  added: []
  patterns:
    - Closed Pydantic v2 boundary models with forbidden extras and explicit camelCase aliases
    - Authoritative paid-access coordinates separated from browser/provider navigation hints
    - Strict bounded 64-bit counters and local-calendar Zurich week validation

key-files:
  created:
    - src/stoa/models/billing.py
    - src/stoa/models/allowance.py
    - tests/test_billing_contracts.py
  modified: []

key-decisions:
  - "Use BillingPlanId for all four product identities and a separate PurchasablePlanId that cannot represent free_trial."
  - "Require paid-invoice fact, active-subscription fact, effective-plan, plan-version, and allowance-version coordinates before a public checkout projection can be active."
  - "Represent allowance counts as strict nonnegative signed-64-bit integers and derive week validity from Europe/Zurich Monday calendar boundaries."

patterns-established:
  - "Payment proof separation: browser navigation and checkout completion never satisfy active entitlement coordinates."
  - "Evidence minimization: provider usage contains only digests, exact counts, cost retention, and observation time."
  - "Plan-version binding: checkout intents, beneficiary grants, transitions, and allowance budgets carry explicit versions."

requirements-completed: [V9BILL-01, V9BILL-02, V9BILL-03, V9BILL-04]

duration: 7min
completed: 2026-07-24
---

# Phase 476 Plan 01: Canonical Billing and Allowance Contracts Summary

**Closed Pydantic contracts now bind the four product plans, authoritative paid-access proof, explicit beneficiaries, and exact Zurich-week allowance evidence without legacy tier translation or sensitive content.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-24T07:25:14Z
- **Completed:** 2026-07-24T07:32:23Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Defined exactly `free_trial`, `student`, `teacher_supported`, and `family`, while making only the three paid plans valid checkout intent values.
- Separated durable checkout command state, signed sandbox billing facts, billing lifecycle, entitlement lifecycle, and the four public outcomes.
- Required paid-invoice, active-subscription, effective-plan, plan-version, and allowance-version coordinates before a projection can declare paid access active.
- Added explicit beneficiary grants and monotonic scheduled transitions with closed plan/version coordinates.
- Added Europe/Zurich weekly budgets, strict token reservations/evidence/finalization, provider-cost retention, and one-case teacher-support admissions.
- Proved closed enums, aliases, forbidden legacy/browser/payment/content fields, DST boundaries, and strict nonnegative 64-bit counts with 78 focused tests.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-01-01 RED: Define failing canonical contract behavior** - `b16ea9d` (test)
2. **Task 476-01-01 GREEN: Implement billing and allowance contracts** - `d4e77d7` (feat)

## Files Created/Modified

- `src/stoa/models/billing.py` - Canonical plan enums and closed checkout, fact, grant, transition, payment-method, and support projection models.
- `src/stoa/models/allowance.py` - Zurich week, locked plan budgets, reservation, provider evidence, finalization, and support admission models.
- `tests/test_billing_contracts.py` - Executable enum, alias, payment-proof, beneficiary, privacy, DST, and exact-count contract coverage.

## Decisions Made

- `BillingPlanId` represents the complete four-plan product vocabulary; `PurchasablePlanId` structurally excludes `free_trial` rather than relying on a service-layer conditional.
- Public `active` state is structurally gated by separate authoritative paid-invoice, active-subscription, effective-plan, plan-version, and allowance-version coordinates.
- Provider identifiers are represented only as SHA-256 digests in evidence and masked payment contracts; generic metadata and sensitive content fields are impossible under forbidden extras.
- Exact counters reject booleans, fractions, negatives, and values above `2^63 - 1`.
- Zurich weeks validate local Monday-midnight boundaries and ISO coordinates, including a DST transition where UTC duration is not seven fixed 24-hour periods.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Prevented boolean coercion as one admitted support case**
- **Found during:** Task 476-01-01 GREEN verification
- **Issue:** Pydantic's `Literal[1]` accepted `True`, violating the exact-integer allowance contract.
- **Fix:** Replaced the literal with a strict integer constrained to the inclusive range 1..1.
- **Files modified:** `src/stoa/models/allowance.py`
- **Verification:** The boolean, fraction, zero, negative, and multi-case rejection selector passes.
- **Committed in:** `d4e77d7`

---

**Total deviations:** 1 auto-fixed bug.
**Impact on plan:** The fix strengthens the planned exact-count boundary with no scope expansion.

## Security Verification

- Closed enums and `extra="forbid"` reject legacy aliases, callback/navigation hints, generic metadata, learning content, full-card fields, CVC, provider credentials, and secrets.
- `signatureVerified` is fixed to true and `providerLivemode` to false for canonical billing facts, preserving the sandbox-only boundary.
- Checkout completion is a distinct fact and cannot satisfy the paid-invoice plus active-subscription predicate.
- All High-threat mitigations in T-476-01-H have passing source-bound selectors; no unresolved High threat remains in this plan's files.

## Issues Encountered

- The initial strict one-case representation allowed Python's `bool`/`int` equivalence. Focused GREEN verification exposed it, and the field was tightened before the feature commit.

## User Setup Required

None - no dependencies, credentials, external services, provider calls, charges, or production mutations were introduced.

## Next Phase Readiness

- Downstream Phase 476 plans can import one canonical plan and state vocabulary without translating historical tiers.
- Checkout persistence, Stripe sandbox orchestration, entitlement convergence, and allowance repositories can bind directly to the versioned contracts.
- No production billing activation or real-charge authority is implied by these models.

## Self-Check: PASSED

- FOUND: `src/stoa/models/billing.py`
- FOUND: `src/stoa/models/allowance.py`
- FOUND: `tests/test_billing_contracts.py`
- FOUND: `b16ea9d`
- FOUND: `d4e77d7`
- PASS: `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_contracts.py` (`78 passed`)
- PASS: `.venv/bin/ruff check src/stoa/models/billing.py src/stoa/models/allowance.py tests/test_billing_contracts.py`

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
