---
phase: 473-student-content-privacy-and-practice-integrity
plan: 22
subsystem: attachment-retention
tags: [dynamodb-consistent-read, deletion-fence, s3-versioning, quota-reconciliation]

requires:
  - phase: 473-19
    provides: Exact provider-version absence and cleanup convergence primitives
  - phase: 473-21
    provides: Exact conversation attachment replay and lease-fenced execution
provides:
  - Strong exhaustive owner attachment and association enumeration
  - Durable account/resource deletion fences with cursor and quiescence facts
  - Exact-version deletion, atomic quota finalization, and staging cleanup-debt replay
affects: [473-35, 479-provider-integration, 480-deployed-observability]

tech-stack:
  added: []
  patterns:
    - Strong base-table pagination instead of eventual-index absence inference
    - Transactional association checks against account and resource lifecycle fences
    - Provider absence proof before idempotent quota/reference finalization

key-files:
  created:
    - tests/test_phase473_retention_reconciliation.py
  modified:
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/services/attachment_service.py
    - tests/test_attachment_security.py

key-decisions:
  - "Deletion authority comes from a strongly consistent exhaustive base-table read; the owner GSI is never used to prove reference absence."
  - "Every question and conversation association transaction condition-checks both the exact resource fence and the owner account fence."
  - "Provider deletion and repository/quota finalization are separate durable stages; exact listed VersionId absence must precede one atomic finalization transaction."
  - "Immutable promotion records staging cleanup debt before provider deletion and clears coordinates only after exact absence proof."

patterns-established:
  - "Fenced quiescence: active generation, validated page cursor, and repeated complete passes remain durable until all references and debts disappear."
  - "Deletion convergence: object_deletion_pending -> object_absence_proven -> quota_finalize_pending -> complete remains retryable after every lost response."

requirements-completed: [V9PRIV-01, V9PRIV-02]

duration: 13 min
completed: 2026-07-17
---

# Phase 473 Plan 22: Exhaustive Retention and Deletion Reconciliation Summary

**Strong authoritative pagination, transactional account/resource fences, and exact-version reconciliation now prevent truncated deletion, late associations, duplicate quota decrements, and lost cleanup debt.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-17T20:07:19Z
- **Completed:** 2026-07-17T20:20:08Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Replaced first-page eventual GSI retention reads with bounded, strongly consistent base-table pagination that validates cursor shape/progress, deduplicates exact keys, and joins metadata with associations across pages.
- Added durable resource and account fence generations, persisted scan cursors and quiescence counts, and conditioned every question/conversation association transaction on both fences being inactive.
- Added closed typed retention dispositions and stages; release and purge no longer use counts as proof of completion and retain their fences on conflict, concealed missing data, pending tombstones, or cleanup debt.
- Separated provider deletion from exact VersionId absence proof and one atomic attachment/quota finalization, including delete/finalize commit-then-raise recovery and exact-once quota decrement behavior.
- Made immutable promotion persist staging cleanup debt before deletion and replay that debt through the same exact-absence boundary before clearing server-only coordinates.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing exhaustive retention and reconciliation tests** - `bd9ec28` (test)
2. **Task 2: Add durable fences and exhaustive authoritative reference enumeration** - `7fccde8` (feat)
3. **Task 3: Make deletion, quota, reference, and cleanup debt fully resumable** - `e965f4a` (fix)
4. **Acceptance hardening: Persist fenced scan cursor and quiescence facts** - `fb0d27b` (fix)

## Files Created/Modified

- `tests/test_phase473_retention_reconciliation.py` - RED/GREEN matrix for strong pagination, malformed/repeating cursors, split-page joins, lifecycle fences, exact absence, lost responses, quota finalization, cleanup debt, and typed outcomes.
- `src/stoa/db/repositories/attachment_repo.py` - Fence keys and transitions, strong owner scans, cursor/quiescence persistence, association condition checks, exact deletion stages, and promotion cleanup-debt state.
- `src/stoa/services/attachment_service.py` - Typed release/purge orchestration, fenced quiescence, exact provider absence reconciliation, ambiguous finalize rereads, and staging-debt replay.
- `tests/test_attachment_security.py` - Inherited transaction-order and exact-version provider fake contracts aligned with lifecycle fence and absence semantics.

## Decisions Made

- Use strongly consistent base-table scans for retention closure. DynamoDB does not support strong reads on GSIs, so an owner index may accelerate discovery but cannot establish final absence.
- Keep both resource and account fences in the existing single table. Association transactions check both rows atomically, avoiding a new table, index, or infrastructure dependency.
- Treat provider delete acknowledgement as ambiguous. Only a complete validated version listing that excludes the exact immutable VersionId permits finalization.
- Keep attachment removal and quota decrement in one conditional transaction. A post-commit transport failure is reconciled by strongly rereading the attachment tombstone; a remaining row keeps the operation retryable.

## Verification

- RED gate: **10 failed**, and the wrapper confirmed pytest exit status 1.
- Task 2 fence/pagination gate: **7 passed, 227 deselected**; explicit strong/fence checks: **6 passed, 4 deselected**.
- Task 2 adjacent transaction regression: **59 passed, 196 deselected**.
- Task 3 deletion/debt gate: **31 passed, 203 deselected**.
- Complete new and inherited attachment suites: **234 passed**.
- Final retention/attachment/question/conversation/replay/provider matrix: **411 passed**.
- Targeted Ruff on all modified production and test paths: **passed**.
- `git diff --check`: **passed**.
- Coordinate-bearing logger denial on modified production paths: **passed**.
- Real S3 and deployed scheduler/IaC behavior: **NOT RUN** (Phase 479).
- Production/deployed log capture: **NOT RUN** (Phase 480).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated inherited atomic-transaction expectations for fence checks**
- **Found during:** Task 2 adjacent regression verification
- **Issue:** Existing message/question transaction tests asserted the pre-fence operation list exactly and failed when the two required condition checks became part of the same transaction.
- **Fix:** Updated the inherited expectations to require both resource and account fence operations and selected the message operation by semantic kind rather than position.
- **Files modified:** `tests/test_attachment_security.py`
- **Verification:** The full new and inherited attachment suites pass (234 tests).
- **Committed in:** `7fccde8`, `e965f4a`

**2. [Rule 2 - Missing Critical] Persisted page cursors and completed quiescence passes under the fence generation**
- **Found during:** Final Task 2 acceptance audit after Task 3
- **Issue:** The first GREEN implementation safely restarted an interrupted exhaustive scan, but did not durably record bounded page progress and quiescence facts required by the plan.
- **Fix:** Added generation-conditional cursor updates, cursor-shape validation, quiescence-pass increments, and service wiring for production repositories while retaining narrow test-fake compatibility.
- **Files modified:** `src/stoa/db/repositories/attachment_repo.py`, `src/stoa/services/attachment_service.py`
- **Verification:** The 234-test attachment gate and final 411-test matrix pass; Ruff and diff checks pass.
- **Committed in:** `fb0d27b`

---

**Total deviations:** 2 auto-fixed (1 blocking compatibility fix, 1 missing critical durability fix)
**Impact on plan:** Both changes were required to preserve inherited verification and satisfy the plan's lifecycle-durability contract; no new infrastructure or product scope was added.

## Issues Encountered

None unresolved.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None.

## Next Phase Readiness

- Retention and deletion reconciliation are locally ready for later Phase 473 evidence closure.
- Real provider/version behavior and deployed cleanup scheduling remain explicitly assigned to Phase 479; deployed privacy-log evidence remains Phase 480-owned.

## Self-Check: PASSED

- The created retention reconciliation test file and all modified production/test files exist.
- Task commits `bd9ec28`, `7fccde8`, `e965f4a`, and `fb0d27b` exist in repository history.
- Every task acceptance gate and the final plan-level verification matrix pass.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
