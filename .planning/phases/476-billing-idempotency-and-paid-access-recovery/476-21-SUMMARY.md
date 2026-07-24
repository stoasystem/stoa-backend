---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 21
subsystem: payments
tags: [billing, allowance, fastapi, stripe-redaction, authorization, reminders]

requires:
  - phase: 476-09
    provides: Owner-safe checkout lifecycle and capability-gated support recheck
  - phase: 476-13
    provides: Current relationship-fenced beneficiary grants and paid transitions
  - phase: 476-15
    provides: Zurich-week token allowance and redacted provider-usage evidence
  - phase: 476-20
    provides: Persistent masked payment-method expiry reminders
provides:
  - Closed parent billing overview with per-beneficiary weekly token percentages and remaining allowance
  - Closed parent child allowance projection replacing daily request-count usage
  - Capability-authorized admin operation detail with fact/grant/allowance versions and digest-only provider evidence
  - Active-only checkout effective-plan projection and persistent masked reminder state
affects: [476-23, web-billing, parent-allowance, admin-billing-support, phase-476-security-gate]

tech-stack:
  added: []
  patterns:
    - Current strict beneficiary grants are the only paid-plan projection authority
    - One Zurich-week source projection feeds both parent overview and child allowance DTOs
    - Admin exact evidence exposes counts, versions, status, and digests while provider/content coordinates stay closed

key-files:
  created:
    - tests/test_billing_allowance_projections.py
  modified:
    - src/stoa/routers/parents.py
    - src/stoa/routers/admin.py
    - src/stoa/services/subscription_service.py
    - tests/test_usage_ledger.py

key-decisions:
  - "Parent effective plan and beneficiary output derive only from current relationship-fenced paid grants; checkout target data becomes effective only after activation_recorded plus authoritative active lifecycle."
  - "Family input/output allowance remains per selected beneficiary while one shared-family teacher-case projection is deduplicated into a single exact remaining value."
  - "The existing capability-authorized checkout support GET preserves its compact default response and exposes the joined exact admin evidence only when detail=true."
  - "Legacy provider billing contributes only allowlisted status, amounts, dunning, and refund state to the parent overview; provider IDs, URLs, manual override evidence, and payment secrets are never returned."

patterns-established:
  - "Closed role projection: every new parent/admin DTO uses extra=forbid and only masked method fields or SHA-256 evidence coordinates."
  - "Projection consistency: beneficiary cardinality, plan/version, subscription, window, and teacher-support scope must agree before any response is emitted."

requirements-completed: [V9BILL-02, V9BILL-04]

duration: 15min
completed: 2026-07-24
---

# Phase 476 Plan 21: Role-Safe Billing and Allowance Projections Summary

**Parents now receive exact Zurich-week allowance and masked reminder state for only their selected beneficiaries, while authorized support admins can inspect versioned lifecycle and digest-only provider evidence without payment-success authority.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-24T15:31:49Z
- **Completed:** 2026-07-24T15:46:49Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments

- Replaced the parent billing response with a closed `ParentBillingOverviewResponse` that exposes effective plan, selected beneficiaries, Zurich UTC/local week boundaries, exact per-beneficiary input/output remaining and percentages, teacher-case state, safe lifecycle amounts, support actions, and masked reminder state.
- Replaced `/parents/me/children/{child_id}/usage` daily request-count output with the closed `ParentAllowanceProjection` backed directly by the current grant and `allowance_service.get_allowance_projection`.
- Added active-only checkout projection so confirming, not-completed, and support-needed operations cannot infer an effective paid plan or activated beneficiaries.
- Added `AdminBillingOperationDetail` on the existing `billing_operations_reader` checkout route through `detail=true`, joining command lifecycle, signed facts, current grant/allowance versions, exact token evidence, reminder state, reconciliation state, and suffix-only provider identity.
- Added arithmetic, shared-family, active-proof, ownership, authorization-before-read, redaction-canary, OpenAPI, and no-manual-success selectors.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-21-01 RED: Add failing billing projection contract** - `927c025d` (test)
2. **Task 476-21-01 GREEN: Expose role-safe billing projections** - `1bcb5a19` (feat)

## Files Created/Modified

- `tests/test_billing_allowance_projections.py` - Exact 0/partial/limit/restored arithmetic, family scope, lifecycle, redaction, authorization, DTO, and source-link proof.
- `src/stoa/routers/parents.py` - Closed parent overview/allowance/reminder models, current-grant weekly projections, and active-only checkout handling.
- `src/stoa/routers/admin.py` - Closed admin lifecycle/provider-evidence models and capability-authorized detailed support projection.
- `src/stoa/services/subscription_service.py` - Current grant/reminder loaders, strict role projection validators, legacy-safe lifecycle allowlist, and admin evidence join.
- `tests/test_usage_ledger.py` - Migrated the directly affected parent child usage regression from daily request counts to Zurich-week token/case output.

## Decisions Made

- Parent paid state is never inferred from legacy subscription tier, provider redirect, requested plan, or checkout completion. Only a current exact grant projects paid access, and checkout result data projects effective state only after authoritative activation.
- Parent token maps are keyed by the selected beneficiary so Family budgets remain independent; shared Family teacher support is validated across every selected beneficiary and returned once.
- Admin evidence keeps exact counts and immutable fact/grant/allowance versions, but converts provider request/model/correlation coordinates to their persisted digests and keeps Stripe identity suffix-only.
- Parent compatibility fields retain safe lifecycle, invoice amount, dunning, and refund state while forcing provider-hosted URLs to null and omitting every provider/customer/subscription/payment identifier.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Direct Regression] Migrated the inherited child usage regression to the planned weekly contract**
- **Found during:** Task 476-21-01 GREEN adjacent verification
- **Issue:** `tests/test_usage_ledger.py` still patched and asserted the removed daily request-count service after the planned parent usage route moved to token/case allowance projection.
- **Fix:** Updated the route regression to supply one current grant and weekly allowance projection, then assert exact remaining tokens, percentage, teacher cases, and Zurich timezone.
- **Files modified:** `tests/test_usage_ledger.py`
- **Verification:** `tests/test_usage_ledger.py` passes inside the 280-test directly affected aggregate.
- **Committed in:** `1bcb5a19`

**2. [Rule 2 - Missing Critical] Preserved billing recovery state without retaining the legacy secret-bearing parent DTO**
- **Found during:** Task 476-21-01 GREEN lifecycle regression
- **Issue:** Removing the legacy parent provider response also removed safe checkout-pending/payment-failed dunning context needed by recovery views.
- **Fix:** Added a closed allowlist for status, canonical tier, masked method type, nonnegative invoice amounts, dunning, and refund state; provider IDs, invoice URLs, event payloads, support manual-override evidence, and secrets are excluded.
- **Files modified:** `src/stoa/services/subscription_service.py`, `src/stoa/routers/parents.py`
- **Verification:** All 35 subscription lifecycle tests pass, focused redaction canaries pass, and new response schemas are closed.
- **Committed in:** `1bcb5a19`

---

**Total deviations:** 2 auto-fixed (1 direct regression, 1 missing critical safe compatibility projection).
**Impact on plan:** Both changes are required to complete the planned request-count replacement and retain recovery correctness without reopening provider or secret disclosure. No UI, provider mutation, dependency, deployment, or production operation was added.

## Security Verification

- Parent overview enumerates strict active parent-student bindings, then accepts only `get_active_beneficiary_grant()` results for that exact parent and beneficiary.
- Parent child allowance still crosses the existing `_parent_child_read` resource policy before grant or counter reads.
- Paid plan/version, beneficiary cardinality, subscription digest, allowance version, week boundaries, and support scope must agree or the projection fails closed with a stable temporary-unavailable response.
- Checkout effective plan/beneficiaries remain absent unless lifecycle is `active` and command state is `activation_recorded`.
- Admin detail stays behind the existing `billing_operations_reader` dependency; denial occurs before command, provider, fact, grant, allowance, or reminder reads.
- Admin output contains exact fact/grant/allowance versions and token counts but only persisted provider request, model, correlation, and object/event digests plus a six-character Session suffix.
- Parent output retains only brand, last four, expiry month/year, and reminder status/time. Full PAN/CVC, provider IDs, keys, URLs, prompts, answers, and unselected student IDs fail the canary matrix.
- OpenAPI exposes closed `ParentBillingOverviewResponse`, `ParentAllowanceProjection`, and `AdminBillingOperationDetail` schemas and no manual-payment-success action.
- No unresolved ASVS L1 High threat remains in this plan's source boundary. The aggregate Phase 476 security gate script is still absent and remains later-plan ownership.

## Verification

- Exact plan command: `12 passed` in `tests/test_billing_allowance_projections.py`.
- Required Ruff gate passes for all planned source/test files.
- Directly affected aggregate: `280 passed` across billing projections, recheck, token allowance, teacher support, reminders, paid grants, admin authorization, subscription lifecycle, and usage ledger tests.
- `git diff --check` passes.
- Source link passes twice: parent billing overview and child allowance route both call `allowance_service.get_allowance_projection`.

## Known Stubs

None. Optional null lifecycle fields are closed representations of absent provider-safe state, not unwired data sources.

## Issues Encountered

- The phase-wide `scripts/verify_phase476_security_gate.py` named in the plan is not present yet, so this plan records focused and adjacent source-bound evidence without claiming the later aggregate gate.
- The sandbox denied direct `.git/index.lock` creation; both atomic task commits used the managed approval path with normal hooks enabled and no verification bypass.

## User Setup Required

None - no dependency, credential, provider call, customer charge, frontend change, deployment, or production mutation was introduced.

## Next Phase Readiness

- Parent Web billing and child allowance views can consume the authoritative effective-plan, weekly token/case, support-action, and persistent reminder contracts.
- Admin billing support can request `detail=true` on the existing authorized checkout read for exact redacted lifecycle and provider-cost evidence.
- Later Phase 476 plans must include these arithmetic, ownership, active-proof, redaction, and no-manual-success selectors in the aggregate security gate.

## TDD Gate Compliance

- RED: `927c025d` produced 11 expected failures before implementation.
- GREEN: `1bcb5a19` passes the focused gate and 280-test directly affected aggregate.

## Self-Check: PASSED

- FOUND: all five created/modified implementation and test files.
- FOUND: `476-21-SUMMARY.md`.
- FOUND: RED commit `927c025d`.
- FOUND: GREEN commit `1bcb5a19`.
- PASS: exact focused gate (`12 passed`).
- PASS: required Ruff gate and `git diff --check`.
- PASS: parent router to `allowance_service.get_allowance_projection` key link.

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
