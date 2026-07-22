---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 23
subsystem: database
tags: [dynamodb, relationships, lifecycle, authorization, cas]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 22
    provides: dual-account fence and profile-version authorization for relationship transactions
provides:
  - non-revivable create and replay semantics for inactive or revoked relationship history
  - canonical-admin relationship lifecycle endpoint with exact status/version fencing
  - atomic status projection across both formal rows and the student profile
affects: [475-32-user-repository-typing, 475-44-coverage, V9DATA-03]

tech-stack:
  added: []
  patterns: [status-aware relationship equality, explicit lifecycle CAS, redacted correlated conflict]

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/user_repo.py
    - src/stoa/routers/admin.py
    - tests/test_phase475_parent_binding_transaction.py
    - tests/test_phase475_parent_binding_reconciliation.py
    - tests/test_admin_authorization.py
    - docs/security/route-authorization-inventory.json

key-decisions:
  - "Create may initialize a relationship status, but only an exact active tuple is replayable; any persisted non-active history conflicts before mutation."
  - "Relationship status changes update both formal rows and the student profile in one transaction guarded by expected status, relationship version, and profile version."
  - "The lifecycle route accepts only the closed status vocabulary and canonical admin authorization, and returns correlation-only static conflict/dependency errors."

requirements-completed: [V9DATA-03]

duration: 10 min
completed: 2026-07-22
---

# Phase 475 Plan 23: Non-Reviving Relationship Lifecycle Summary

**Revoked and inactive parent relationships can no longer be reactivated by create/reconciliation retries; status changes now require a canonical-admin, version-fenced atomic lifecycle command.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-22T09:13:35Z
- **Completed:** 2026-07-22T09:24:18Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments

- Added status to relationship row equality and conditional-write identity, while changing create updates to initialize status only when absent.
- Made only an exact active tuple eligible for zero-write replay; inactive, revoked, mismatched, or split history returns conflict without changing either row or the profile pointer.
- Added an atomic lifecycle transaction that matches expected status/version on both formal rows, matches the student profile projection/version, and increments all versions with the new status.
- Added a typed `/admin/parent-bindings/status` boundary protected by the existing canonical-admin capability and per-target audit path.
- Added stable, redacted conflict and temporary-unavailability projections that expose no parent/student identifiers, storage coordinates, reason, or repository diagnostics.

## Task Commits

The single TDD task completed through its required gates:

1. **RED: Add failing non-revival and lifecycle authorization tests** - `cd67863` (test)
2. **GREEN: Fence relationship lifecycle transitions** - `a46bf29` (feat)

No separate refactor commit was needed; the minimal implementation remained cohesive after GREEN.

## Files Created/Modified

- `src/stoa/db/repositories/user_repo.py` - Status-aware create/replay classification and explicit dual-row/profile lifecycle CAS.
- `src/stoa/routers/admin.py` - Closed lifecycle request/response models, canonical-admin target boundary, and redacted errors.
- `tests/test_phase475_parent_binding_transaction.py` - Revoked/inactive retry, exact replay, create-expression, and stale lifecycle CAS proof.
- `tests/test_phase475_parent_binding_reconciliation.py` - Non-active reconciliation zero-write and profile-pointer preservation proof.
- `tests/test_admin_authorization.py` - Canonical role/capability denial and redacted conflict contract for the new route.
- `docs/security/route-authorization-inventory.json` - Deterministic checked projection for the new authorized route and target metadata.

## Decisions Made

- Non-active relationship history is never treated as ordinary idempotent replay, even when parent, student, relationship, and version otherwise match.
- Lifecycle status values use the closed set `active|active_pending_verification|inactive|revoked`; same-status commands are rejected before repository mutation.
- A stale expected relationship status/version is a conflict, while an unchanged snapshot after an ambiguous dependency failure remains retryable.
- Business errors carry only a fixed code/message and server-owned correlation ID; target IDs and operator reason never enter the public response.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Regenerated the checked route authorization inventory**
- **Found during:** Task 1 expanded authorization regression
- **Issue:** Adding the planned lifecycle endpoint changed the executable route graph, so the checked deterministic route inventory no longer matched runtime and failed closed.
- **Fix:** Regenerated the inventory with the project generator and verified it byte-matches runtime.
- **Files modified:** `docs/security/route-authorization-inventory.json`
- **Verification:** `scripts/generate_route_authorization_inventory.py --check` and 169 admin/inventory tests passed.
- **Committed in:** `a46bf29`

**2. [Rule 2 - Missing Critical] Extended executable admin authorization regression coverage**
- **Found during:** Task 1 canonical-admin lifecycle boundary implementation
- **Issue:** The new privileged mutation needed direct proof that a non-admin with the same capability is denied before the repository and that conflict responses redact target/reason canaries.
- **Fix:** Added route policy coverage, canonical role denial, one-call mutation proof, and exact correlation-only conflict assertions.
- **Files modified:** `tests/test_admin_authorization.py`
- **Verification:** Full admin authorization and route inventory suite passed 169 tests.
- **Committed in:** `cd67863`, `a46bf29`

---

**Total deviations:** 2 auto-fixed (1 blocking generated-contract sync, 1 missing privileged-boundary regression).
**Impact on plan:** Both additions are direct correctness requirements of the planned admin lifecycle endpoint; no product scope or authorization capability was broadened.

## Issues Encountered

- The sandbox initially denied creation of `.git/index.lock` for the RED commit. Repository permission approval allowed the same individually scoped normal commit; hooks were not bypassed.

## Verification

- RED gate: 5 expected failures and 18 passing related nodes before implementation; Ruff passed all changed tests.
- Acceptance criteria: 7 targeted replay, non-revival, reconciliation, CAS, canonical-admin, and redaction cases passed.
- Exact plan command: 15 passed, 24 deselected; Ruff passed all four planned files.
- Full planned relationship modules: 39 passed.
- Admin authorization and route inventory: 169 passed.
- Account lifecycle, student authorization matrix, and parent children regression: 160 passed.
- Deterministic route inventory `--check`: passed.
- `git diff --check`: passed.
- Normal repository commit hooks: passed for RED and GREEN; no `--no-verify` was used.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None.

## Next Phase Readiness

- CR-06 is closed locally: create/reconciliation retries preserve inactive or revoked relationship history.
- D-09/D-10 lifecycle changes now have one explicit canonical-admin, expected-status/version path with atomic projection consistency.
- No AWS or other live provider mutation was performed; external DynamoDB validation remains owned by later release phases.

## Self-Check: PASSED

- All six modified implementation/test/checked-contract files and this summary exist.
- RED commit `cd67863` and GREEN commit `a46bf29` exist in the required order and contain only 475-23 files.
- Every acceptance criterion, exact plan command, full planned modules, authorization inventory, affected account/parent regressions, Ruff, generator check, and diff check passed.
- Stub scan found no goal-blocking placeholder or unwired lifecycle path.
- The only new security surface is the relationship status endpoint explicitly covered by the plan threat model and executable authorization inventory.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
