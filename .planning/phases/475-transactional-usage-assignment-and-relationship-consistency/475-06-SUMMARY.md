---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 06
subsystem: database
tags: [dynamodb, transactions, parent-binding, authorization, idempotency]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: strict active bidirectional parent authorization
  - phase: 473-student-content-privacy-and-practice-integrity
    provides: permanent student account fences and transactional persistence adapter
provides:
  - one conditional transaction for forward binding, reverse binding, and student profile projection
  - typed created, replayed, conflict, and retryable parent-binding outcomes
  - registration and administrator repair callers routed through one logical relationship writer
affects: [475-07-parent-binding-reconciliation, 475-08-profile-cas, V9DATA-03]

tech-stack:
  added: []
  patterns: [strong-read replay reconciliation, conditional same-identity updates, pending-before-authority registration]

key-files:
  created:
    - tests/test_phase475_parent_binding_transaction.py
  modified:
    - src/stoa/db/repositories/user_repo.py
    - src/stoa/routers/admin.py
    - src/stoa/routers/auth.py
    - tests/test_admin_authorization.py
    - tests/test_auth_account_lifecycle.py

key-decisions:
  - "Binding rows use conditional Updates that admit only absence or the exact parent/student/relationship/version identity; created_at and version remain stable across replay."
  - "Student registration persists only a non-authoritative pending profile before invoking the relationship transaction, then returns the strong durable profile after success."
  - "Repository conflicts expose a closed typed outcome; the admin route returns a coordinate-free 409 and never selects or overwrites either parent."

patterns-established:
  - "Relationship writer: strong-read exact replay first, four-operation conditional transaction second, strong-read reconciliation after ambiguity."
  - "Legacy profile parent_id remains a projection only; authorization continues to require matching active forward and reverse rows."

requirements-completed: [V9DATA-03]

duration: 12 min
completed: 2026-07-21
---

# Phase 475 Plan 06: Atomic Parent Relationship Projection Summary

**Parent and student relationship rows plus the student's profile link now commit behind one account fence, replay idempotently, and preserve conflicting parents for explicit administrator review.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-21T21:33:34Z
- **Completed:** 2026-07-21T21:46:01Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments

- Added `ParentBindingDisposition`, `ParentBindingResult`, `build_parent_binding_transaction()`, and `put_parent_student_relationship()` with one student fence, two conditional formal-row updates, and one narrow profile update.
- Made exact active replay return the original binding without another transaction or relationship version/history change, while strong rereads classify ambiguous writes safely.
- Preserved different-parent, different-student, different-relationship, and different-version state as conflicts with no automatic winner or overwrite.
- Migrated public registration and capability-authorized admin repair away from profile-then-binding writes; strict bidirectional authorization remains unchanged.
- Added deterministic transaction-shape, per-operation failure, replay, concurrent conflict, authorization-denial, and admin-safe response coverage.

## Task Commits

Each task was committed atomically:

1. **Task 1: Compose both relationship directions and profile link atomically** - `967279d` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/user_repo.py` - Atomic relationship builder, typed outcomes, replay/conflict reconciliation, and compatibility wrapper.
- `src/stoa/routers/admin.py` - Single-writer repair path with safe structured conflict and retryable responses.
- `src/stoa/routers/auth.py` - Pending profile preparation followed by the atomic relationship writer after account persistence.
- `tests/test_phase475_parent_binding_transaction.py` - Transaction shape, failure injection, replay, conflict, concurrency, and call-site proof.
- `tests/test_admin_authorization.py` - Capability-scoped single mutation and structured conflict assertions.
- `tests/test_auth_account_lifecycle.py` - Registration ordering and lifecycle regression coverage for the new primitive.

## Decisions Made

- Used conditional `Update` operations rather than unconditional `Put` operations so absent rows can be created while exact existing identity/version coordinates are the only replaceable state.
- Preserved formal-row `created_at` and `version` on replay; a preflight strong read avoids even a second transaction for an already identical relationship.
- Kept the profile update limited to `parent_id`, `relationship`, and `parent_binding_status`; legacy profile fields still cannot authorize access.
- Represented registration's pre-transaction state as `pending_parent_binding`, which has no authorization meaning and is replaced only when all three projections commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Preserved real registration lifecycle coverage**
- **Found during:** Task 1 (Compose both relationship directions and profile link atomically)
- **Issue:** The plan migrated registration runtime calls but did not list the existing lifecycle test module whose mocks and ordering assertions depended on the removed two-step writer.
- **Fix:** Updated the existing registration/admin lifecycle tests and asserted the student profile is persisted without `parent_id` before the atomic relationship primitive runs.
- **Files modified:** `tests/test_auth_account_lifecycle.py`
- **Verification:** The complete auth lifecycle and admin authorization suites pass (177 tests), and the expanded relationship regression set passes (303 tests).
- **Committed in:** `967279d`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** The additional test change is limited to proving the planned registration migration and prevents a future return of the profile-before-binding partial-write window.

## Issues Encountered

- Targeted mypy still reports 51 pre-existing provider-boundary errors across the three changed runtime modules: seven unchanged `user_repo.py` table capability errors, one unrelated locale response narrowing error in `auth.py`, and 43 unrelated admin projection/table capability errors. The new relationship code adds no mypy errors; details are recorded in `deferred-items.md`.

## Verification

- Plan verification command — 28 passed, 232 deselected; Ruff passed all planned files.
- Acceptance-criteria node gate — 16 passed, covering every injected operation failure, replay, conflict preservation, single-writer migration, and strict bidirectional authorization.
- Expanded relationship/auth regression — 303 passed across the new transaction tests, admin authorization, student authorization matrix, parent routes, and auth lifecycle.
- `git diff --check` — passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Plan 475-07 to build preview/apply reconciliation on the typed atomic relationship primitive.
- Plan 475-08 can independently add the shared profile version/CAS protocol without changing this relationship authority boundary.

## Self-Check: PASSED

- The created transaction test and all five modified implementation/regression files exist.
- Task commit `967279d` exists and contains the six intended implementation/test files with no deletions.
- Every task acceptance criterion and the plan-level automated verification command pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-21*
