---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 12
subsystem: payments
tags: [billing, entitlements, dynamodb, idempotency, relationship-fencing]

requires:
  - phase: 476-10
    provides: Exact-once atomic paid activation transaction and activation receipt
  - phase: 476-11
    provides: Signed Stripe fact convergence and provider-authoritative activation predicate
provides:
  - Explicit one-to-three beneficiary paid grants bound to current bidirectional relationships
  - Atomic profile, relationship, and permanent-account-fence conditions on paid activation
  - Owner-scoped grant entitlement resolution without current/future-child inference
  - Monotonic paid upgrades that preserve weekly usage and attachment storage aggregates
affects: [weekly-allowances, billing-status, parent-account-operations, phase-476-security-gate]

tech-stack:
  added: []
  patterns:
    - Immutable sorted beneficiary selection revalidated immediately before atomic activation
    - Grant snapshots carry plan, allowance, subscription digest, relationship, profile, and fence versions
    - Paid upgrades replace only versioned grant limits and never rewrite consumed-resource aggregates

key-files:
  created:
    - src/stoa/services/paid_entitlement_service.py
    - tests/test_paid_entitlement_grants.py
  modified:
    - src/stoa/db/repositories/billing_fact_repo.py
    - src/stoa/services/entitlement_service.py
    - src/stoa/services/subscription_service.py
    - tests/test_billing_webhook_convergence.py
    - tests/test_entitlements.py
    - tests/test_subscription_operations.py

key-decisions:
  - "Signed paid activation reaches Plan 10 only through explicit grant construction; relationship/profile/account-fence ConditionChecks join the same activation transaction."
  - "An active parent billing projection no longer grants every bound child; the resolver requires one exact owner-scoped active beneficiary grant."
  - "A paid upgrade advances plan, allowance, activation, and grant versions while leaving weekly token/support counters and attachment byte aggregates untouched."

patterns-established:
  - "Grant authority is exact-owner and exact-beneficiary: PAID_GRANT#parent plus BENEFICIARY#student never scans or infers membership."
  - "Relationship races fail the whole activation transaction through versioned forward, reverse, profile, and permanent-fence conditions."

requirements-completed: [V9BILL-02, V9BILL-04]

duration: 11min
completed: 2026-07-24
---

# Phase 476 Plan 12: Explicit Paid Beneficiary Grants Summary

**Paid access now resolves from exact relationship-fenced beneficiary grants, while monotonic upgrades raise limits without resetting consumed tokens, support cases, or stored bytes.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-24T14:14:34Z
- **Completed:** 2026-07-24T14:25:34Z
- **Tasks:** 1
- **Files modified:** 8

## Accomplishments

- Validated exact beneficiary cardinality: one selected student for `student` and `teacher_supported`, and one to three unique selected students for `family`.
- Bound every grant to the immutable command, parent, beneficiary, subscription digest, plan/allowance/activation versions, current profiles, both relationship directions, and permanent account-fence generations.
- Supplied those relationship operations to `billing_fact_repo.commit_paid_activation` in the same Plan 10 transaction as command, billing, allowance, grants, and activation receipt.
- Changed the signed webhook's default persistence adapter and effective entitlement resolver to use the new grant boundary instead of inferred all-child grants.
- Added monotonic upgrades that rewrite only explicit grants; current-week finalized/reserved token/support counters and attachment storage usage remain byte-for-byte unchanged.

## Task Commits

TDD execution produced the mandatory RED and GREEN gates:

1. **Task 476-12-01 RED: Add failing paid entitlement grant contract** - `c0b7f911` (test)
2. **Task 476-12-01 GREEN: Publish explicit paid beneficiary grants** - `187e79b9` (feat)

## Files Created/Modified

- `src/stoa/services/paid_entitlement_service.py` - Selection validation, current relationship proof, explicit grant construction, owner-scoped lookup, atomic activation wrapper, and monotonic upgrade.
- `src/stoa/db/repositories/billing_fact_repo.py` - Accepts validated grant ConditionChecks in the existing exact-once activation transaction.
- `src/stoa/services/entitlement_service.py` - Requires an exact active grant for paid child access.
- `src/stoa/services/subscription_service.py` - Routes signed provider-authoritative activation through the explicit grant service.
- `tests/test_paid_entitlement_grants.py` - Cardinality, duplicate, inactive, cross-parent, race, future-child, resolver, and aggregate-preserving upgrade proof.
- `tests/test_entitlements.py` - Migrated effective entitlement fixtures to explicit grant authority.
- `tests/test_billing_webhook_convergence.py` - Preserves the command beneficiary contract at the signed convergence adapter.
- `tests/test_subscription_operations.py` - Migrated parent account-operation integration to an explicit family grant.

## Decisions Made

- Kept the Plan 10 activation receipt as the exact-once authority and added only ConditionChecks to its existing transaction; no second activation transaction or new provider operation was introduced.
- Revalidated both formal relationship rows plus parent/student profiles and permanent account fences immediately before commit. Profile links or one relationship direction alone never authorize a grant.
- Treated grant plan and allowance versions as the fresh admission snapshot. Upgrade transactions do not touch weekly counter or storage aggregate keys, so higher limits apply without recounting or reset.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added relationship conditions to Plan 10's atomic activation**
- **Found during:** Task 476-12-01 GREEN
- **Issue:** The existing repository accepted grant rows but had no narrow way to include profile, relationship, and account-fence ConditionChecks, leaving a revalidation-to-commit race.
- **Fix:** Added validated condition-only `grant_operations` to the existing transaction and routed default signed activation through the explicit grant builder.
- **Files modified:** `src/stoa/db/repositories/billing_fact_repo.py`, `src/stoa/services/subscription_service.py`, `src/stoa/services/paid_entitlement_service.py`
- **Verification:** Exact source link selector passes; relationship-race test leaves command, billing, grants, and versions unchanged.
- **Committed in:** `187e79b9`

**2. [Rule 1 - Test Bug] Corrected the beneficiary fence fixture's zero-based offset**
- **Found during:** Task 476-12-01 GREEN focused verification
- **Issue:** The RED fixture generated student fence generations starting at 200 while its assertions correctly required the declared 201-based sequence.
- **Fix:** Corrected the fixture generator without weakening any assertion.
- **Files modified:** `tests/test_paid_entitlement_grants.py`
- **Verification:** Focused suite passes all 20 selectors.
- **Committed in:** `187e79b9`

**3. [Rule 1 - Test Drift] Migrated inherited all-child entitlement fixtures**
- **Found during:** Adjacent entitlement and subscription verification
- **Issue:** Two inherited integration fixtures still expected active parent billing alone to grant a family plan.
- **Fix:** Added exact bidirectional versioned relationships, active fences, and explicit family grant fixtures; updated the expected authority source.
- **Files modified:** `tests/test_entitlements.py`, `tests/test_subscription_operations.py`
- **Verification:** Focused plus adjacent billing/entitlement suites pass 82 tests.
- **Committed in:** `187e79b9`

---

**Total deviations:** 3 auto-fixed (2 Rule 1 bugs, 1 Rule 2 missing critical security condition)
**Impact on plan:** The fixes close the intended relationship-race boundary and align inherited tests with D-14. No new provider access, charge, production mutation, dependency, or architecture was introduced.

## Security Verification

- Explicit grant rows are owner-scoped and exact-beneficiary keyed; adding a later child creates no grant and cannot inherit family access.
- Parent/student profiles, both relationship directions, and both permanent account fences are version/generation conditioned in the same activation transaction.
- Duplicate activation remains governed by the existing activation receipt; duplicate upgrade recognizes the exact command/version snapshot without a transaction.
- Cross-parent, inactive, malformed, duplicate, zero/four-beneficiary, and relationship-race inputs fail closed.
- The planned source link is exact: `paid_entitlement_service.py` calls `billing_fact_repo.commit_paid_activation` with `grant_operations=built.grant_operations`.
- No unresolved ASVS L1 High threat remains in Plan 476-12's source-bound focused selectors.
- The aggregate `scripts/verify_phase476_security_gate.py` is not present yet; no aggregate phase-gate claim is made.

## Known Stubs

None introduced.

## Issues Encountered

- Targeted mypy exposed seven pre-existing `BillingFact` reconstruction narrowing diagnostics in `billing_fact_repo.py`; the new paid-grant and transaction-operation code adds no targeted diagnostic. The inherited debt is recorded in `deferred-items.md`.
- One existing Starlette test-client deprecation warning remains for the later `httpx2` migration.
- No real Stripe call, charge, production operation, deployment, or provider mutation was performed.

## User Setup Required

None - no dependencies or external configuration were added.

## Next Phase Readiness

- Signed paid activation now has an explicit, transaction-fenced beneficiary authority suitable for weekly allowance and parent/admin projections.
- Later Phase 476 work can include these selectors in the aggregate source-bound security gate.

## Self-Check: PASSED

- FOUND: `src/stoa/services/paid_entitlement_service.py`
- FOUND: `src/stoa/services/entitlement_service.py`
- FOUND: `src/stoa/services/subscription_service.py`
- FOUND: `src/stoa/db/repositories/billing_fact_repo.py`
- FOUND: `tests/test_paid_entitlement_grants.py`
- FOUND: `c0b7f911`
- FOUND: `187e79b9`
- PASS: focused suite (`20 passed`)
- PASS: focused plus adjacent billing/entitlement verification (`82 passed`)
- PASS: planned ruff gate and `git diff --check`
- PASS: exact paid-entitlement-service to billing-fact-repository key link

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
