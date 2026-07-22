---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 22
subsystem: database
tags: [dynamodb, transactions, parent-binding, authorization, concurrency]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 06
    provides: atomic forward, reverse, and student-profile relationship projection
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 07
    provides: preview-bound historical relationship reconciliation
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 08
    provides: shared profile version/CAS protocol
provides:
  - exact parent and student account-fence generations bound into every relationship transaction
  - canonical active parent and student profile/version conditions at the commit boundary
  - parent/student lifecycle and profile-version rollback proof for direct and reconciliation writes
affects: [475-23-relationship-lifecycle, 475-32-user-repository-typing, 475-44-coverage, V9DATA-03]

tech-stack:
  added: []
  patterns: [dual-account authorization observations, profile-version transaction fencing, conditional same-item projection]

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/user_repo.py
    - tests/test_phase475_parent_binding_transaction.py
    - tests/test_phase475_parent_binding_reconciliation.py

key-decisions:
  - "Relationship transactions carry separate parent/student fence generations and profile versions; missing or malformed observations have no permissive fallback."
  - "Only exact canonical `parent` and `student` roles with active account status may reach commit."
  - "The student profile authorization condition is merged into its projection Update because DynamoDB forbids two transaction actions against the same item."

patterns-established:
  - "Dual participant fence: both ACCOUNT_FENCE generations and both PROFILE versions are observed before write and rechecked atomically."
  - "Same-item authorization: a PROFILE row being mutated carries role, lifecycle, identity, and version conditions on that Update."

requirements-completed: [V9DATA-03]

duration: 8 min
completed: 2026-07-22
---

# Phase 475 Plan 22: Dual-Account Parent Relationship Fencing Summary

**Parent/student relationship creation and reconciliation now lose atomically to either participant's deletion, suspension, role change, or profile-version advance.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-22T07:30:54Z
- **Completed:** 2026-07-22T07:38:22Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Added explicit parent and student fence-generation plus profile-version inputs to the relationship transaction builder.
- Added a parent PROFILE condition requiring the exact user, canonical `parent` role, active status, and observed version.
- Extended the student PROFILE projection condition to require the exact user, canonical `student` role, active status, and observed version.
- Removed permissive observation fallback: malformed, inactive, legacy-role, unversioned, or unfenced participants cannot create or replay a binding.
- Proved total rollback for eight parent/student lifecycle and version races and four parent-side reconciliation races.

## Task Commits

The single TDD task was committed through its required gates:

1. **RED: Add failing dual-account relationship fence tests** - `4eab0eb` (test)
2. **GREEN: Fence relationship writes with both accounts** - `9c961eb` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/user_repo.py` - Dual fence/profile observations, canonical lifecycle checks, and transaction conditions inherited by reconciliation.
- `tests/test_phase475_parent_binding_transaction.py` - Six-operation interpreter plus parent/student deletion, suspension, role, and version race matrix.
- `tests/test_phase475_parent_binding_reconciliation.py` - Parent lifecycle/version race injection through the real preview/apply entry point.

## Decisions Made

- Both participants are represented by four exact observations: parent fence generation, student fence generation, parent profile version, and student profile version.
- Parent authorization is a PROFILE `ConditionCheck`; student authorization is an equivalent condition on the same atomic PROFILE projection Update so the transaction never targets the student profile twice.
- Exact canonical roles are hard-coded as `parent` and `student`; historical aliases such as `guardian` and `child` fail closed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Merged the student profile condition into its projection Update**
- **Found during:** Task 1 (Fence relationship writes with both active account versions)
- **Issue:** A separate student PROFILE `ConditionCheck` plus the required student PROFILE projection `Update` would target one DynamoDB item twice in a single transaction, which DynamoDB rejects.
- **Fix:** Kept the parent PROFILE as an explicit `ConditionCheck` and placed the student's exact identity, canonical role, active status, and observed version conditions on the same atomic projection Update.
- **Files modified:** `src/stoa/db/repositories/user_repo.py`, `tests/test_phase475_parent_binding_transaction.py`, `tests/test_phase475_parent_binding_reconciliation.py`
- **Verification:** The transaction-shape assertion proves both profile keys/versions are present, and all twelve participant/reconciliation race cases roll back every planned relationship write.
- **Committed in:** `9c961eb`

---

**Total deviations:** 1 auto-fixed (1 blocking correctness constraint).
**Impact on plan:** The implementation preserves the full dual-profile authorization guarantee while producing a valid DynamoDB transaction; no product or authorization scope was broadened.

## Issues Encountered

- The initial RED commit could not acquire `.git/index.lock` inside the restricted sandbox. The same individually scoped normal commit completed after repository permission approval; hooks were not bypassed.

## Verification

- RED gate: 11 expected failures and 22 passing inherited nodes before implementation; Ruff passed the test files.
- Exact plan command: 33 passed across the parent-binding transaction and reconciliation modules; Ruff passed all three planned files.
- Expanded affected regression: 337 passed across relationship transaction/reconciliation, profile CAS, administrator authorization, registration lifecycle, student authorization matrix, and parent children flows.
- `git diff --check`: passed.
- Normal repository commit hooks: passed for both TDD commits; no `--no-verify` was used.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None.

## Next Phase Readiness

- CR-05 is closed locally: neither direct creation nor reconciliation can commit after either participant's authorization observation changes.
- Plan 475-23 can independently close inactive/revoked relationship-row replay without reopening this dual-account transaction boundary.

## Self-Check: PASSED

- All three modified files exist.
- RED commit `4eab0eb` and GREEN commit `9c961eb` exist in Git history in the required order.
- Every acceptance criterion, exact plan verification command, expanded affected regression, Ruff, and diff check passed.
- Stub scan found only intentional empty test collections/default values; no goal-blocking placeholder is present.
- No new endpoint, authentication path, file access, schema boundary, or unplanned threat surface was introduced.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
