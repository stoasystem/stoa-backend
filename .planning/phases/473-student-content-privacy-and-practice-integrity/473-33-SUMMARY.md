---
phase: 473-student-content-privacy-and-practice-integrity
plan: 33
subsystem: learning-content-deletion
tags: [dynamodb-transactions, account-fence, practice, adaptive-learning, analytics, privacy, tdd]
requires:
  - phase: 473-25
    provides: immutable answer-bearing attempt receipts and answer-safe practice projections
  - phase: 473-29
    provides: canonical permanent account fence and restartable deletion branch protocol
  - phase: 473-32
    provides: conversation deletion closure and post-wave24 green baseline
provides:
  - same-fence practice, adaptive assignment, learning memory, AI draft, usage, and curriculum signal writers
  - opaque curriculum signal owner manifests with exact-once aggregate contribution reversal
  - five restartable learning-store purge branches with strict tombstones and two-clean-epoch proof
affects: [473-35, practice, adaptive-learning, ai-teacher-tools, curriculum-analytics, usage-ledger]
tech-stack:
  added: []
  patterns:
    - every student learning mutation carries one exact permanent account-fence generation
    - globally keyed curriculum signals use random IDs and owner-partition manifests instead of deterministic hashes
    - private learning rows converge to closed noncontent tombstone allowlists across strong base-table scans
key-files:
  created:
    - tests/test_phase473_practice_learning_deletion.py
  modified:
    - src/stoa/db/repositories/practice_repo.py
    - src/stoa/db/repositories/adaptive_learning_repo.py
    - src/stoa/db/repositories/ai_teacher_tools_repo.py
    - src/stoa/db/repositories/curriculum_analytics_repo.py
    - src/stoa/db/repositories/usage_ledger_repo.py
    - src/stoa/services/account_deletion_service.py
    - src/stoa/services/curriculum_analytics_service.py
    - src/stoa/routers/practice.py
key-decisions:
  - Student curriculum signals are globally anonymous and resolve to an account only through a same-transaction owner manifest under that account's deletion partition.
  - Signal deletion, aggregate decrement, owner-manifest removal, and an owner-free reconciliation receipt form one exact conditional transaction.
  - Practice and assignment usage creation retains only TTL-bound accounting taxonomy while deletion tombstones retain count, period, action, TTL, and basis.
  - Practice, assignments, memories, drafts, and curriculum signals each prove quiescence independently through item debt and two later clean scans.
patterns-established:
  - Repository write builders place the canonical fence ConditionCheck first and require owner/generation on every existing-row update.
  - Accepted AI draft assignments condition the draft source and target write in the same student-fenced transaction.
requirements-completed: [V9PRIV-01, V9PRIV-02]
duration: 19 min
completed: 2026-07-18
---

# Phase 473 Plan 33: Practice, Adaptive Learning, Draft, and Analytics Deletion Closure Summary

Practice receipts and progress, adaptive assignments and memories, AI teaching drafts, learning usage facts, and per-student curriculum signals now lose atomically to the permanent account fence and converge through five independently restartable purge branches.

## Performance

- **Duration:** 19 min
- **Started:** 2026-07-18T09:28:59Z
- **Completed:** 2026-07-18T09:47:21Z
- **Tasks:** 3
- **Files modified:** 14

## Accomplishments

- Added closed source, writer, private-field, and tombstone registries across current and legacy practice, assignment, memory, AI draft, usage, curriculum signal, and aggregate metric families.
- Replaced direct learning writes with same-table canonical-fence transactions; updates require an existing owner/generation, and accepted AI drafts cannot be copied after deletion.
- Replaced deterministic `studentHash` signal linkage with opaque random signal IDs and same-transaction owner manifests, then made deletion reverse each metric contribution exactly once.
- Registered `practice_progress`, `adaptive_assignment`, `learning_memory`, `ai_teacher_draft`, and `curriculum_signal` handlers with independent cursors, item/contribution debt, restart, and two later clean scans.
- Minimized future practice, hint, teacher-help, and assignment usage metadata and retained only explicit TTL/basis accounting facts in deletion tombstones.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing practice/adaptive/draft/memory/signal writer and purge tests** - `07aeb57` (test)
2. **Task 2: Fence every practice/adaptive/draft/memory/analytics writer and stop deterministic linkage** - `85a6fa5` (feat)
3. **Task 3: Implement five exhaustive purge branches and exact analytics reconciliation** - `db86202` (feat)

Additional correctness commit:

- `43206e0` (fix) removes stale deterministic student linkage from the warehouse schema contract.

## Files Created/Modified

- `tests/test_phase473_practice_learning_deletion.py` - RED/GREEN registries, transaction fences, owner manifests, strict raw tombstones, exact aggregate reconciliation, and later-zero branch contracts.
- `src/stoa/db/repositories/practice_repo.py` - Fenced attempt/progress writers, strong current/legacy discovery, usage minimization, and practice tombstones.
- `src/stoa/db/repositories/adaptive_learning_repo.py` - Fenced assignment/memory puts and updates, accepted-draft source checks, family scans, and strict tombstones.
- `src/stoa/db/repositories/ai_teacher_tools_repo.py` - Fenced draft lifecycle writes, strong owner discovery, and strict draft tombstones.
- `src/stoa/db/repositories/curriculum_analytics_repo.py` - Opaque signal transaction, owner manifests, legacy hash migration, strong discovery, and exact-once metric reconciliation.
- `src/stoa/db/repositories/usage_ledger_repo.py` - Mandatory permanent-fence writes for private learning usage events.
- `src/stoa/services/account_deletion_service.py` - Five independently restartable Plan 33 handlers without aggregate finalization.
- `src/stoa/services/curriculum_analytics_service.py` - Student-hash removal from live signals and future warehouse schemas.
- `src/stoa/services/usage_ledger_service.py`, `src/stoa/services/rate_limit.py`, and `src/stoa/routers/practice.py` - Content-minimal TTL/basis learning accounting and fenced hint counters.
- `src/stoa/services/adaptive_learning_service.py` - Exact assignment generation/transition fence generation propagation and minimized accounting metadata.
- `tests/test_adaptive_learning.py` and `tests/test_curriculum_analytics.py` - Updated privacy assertions for aggregate-only analytics and content-minimal accounting.

## Decisions Made

- The owner manifest is the only future account-to-signal link; globally keyed signals contain no student ID, owner ID, or deterministic hash.
- Reconciliation retains a completed owner-free operation receipt so a lost transaction response cannot cause a second aggregate decrement.
- Existing deterministic hashes are recognized only during purge migration and are never copied into new rows or retained after reconciliation.
- Production uses DynamoDB transactions exclusively; narrow in-memory fake compatibility remains for inherited unit tests that do not expose a transaction surface.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed stale deterministic student linkage from warehouse readiness schemas**

- **Found during:** Post-task source and stub/threat audit
- **Issue:** Future learning-memory and curriculum-progress warehouse schema descriptions still advertised `studentHash` even though live curriculum signals no longer persisted it.
- **Fix:** Replaced those fields with aggregate-only dimensions/counts and added a readiness assertion that no deterministic student linkage is exposed.
- **Files modified:** `src/stoa/services/curriculum_analytics_service.py`, `tests/test_curriculum_analytics.py`
- **Verification:** Focused analytics/deletion tests, the 109-test Plan 33 gate, targeted Ruff, and the 1812-test full suite pass.
- **Committed in:** `43206e0`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The correction closes an adjacent deterministic-linkage exposure within the declared analytics service scope; no dependency, table, endpoint, or external effect was added.

## Issues Encountered

- Git metadata is read-only in the normal workspace sandbox. Required atomic commits used the approved escalated Git path with repository hooks enabled.
- The state SDK correctly counted 53/57 completed plans and reported 93%, but a later frontmatter resync applied the cross-phase 1/10 floor and wrote 10%; the curated milestone plan percentage was restored to the SDK-reported 93% after all handlers completed.

## Verification

- RED gate: seven intended assertion failures, pytest exit code exactly 1, with no collection/import failure.
- Task 2 GREEN gate: 51 selected writer/fence/draft/assignment/signal/usage tests passed.
- Final focused gate: 109 tests passed across Plan 33 deletion, practice, practice privacy, adaptive learning, AI teacher tools, curriculum analytics, and usage ledger suites.
- Targeted Ruff passed across every Plan 33 source path; `git diff --check` passed.
- Full repository regression: 1812 tests passed.
- TDD order is present in Git history: `07aeb57` precedes `85a6fa5`, `db86202`, and `43206e0`.

## Known Stubs

None.

## User Setup Required

None - no package, configuration, provider, or external-service change is required.

## Next Phase Readiness

- Plan 35 can consume the five registered branch results while retaining sole authority to seal the exact aggregate registry and finalize deletion.
- Plan 34 may proceed with notification/assistance/device delivery closure; no unresolved Plan 33 blocker remains.

## Self-Check: PASSED

- All 14 created or modified delivery paths exist.
- Commits `07aeb57`, `85a6fa5`, `db86202`, and `43206e0` exist in repository history.
- All mandatory Plan 473-33 local verification gates pass from committed source.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-18*
