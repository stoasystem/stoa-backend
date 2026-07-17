---
phase: 473-student-content-privacy-and-practice-integrity
plan: 30
subsystem: moderation-content-deletion
tags: [dynamodb-transactions, privacy, moderation, resumable-jobs, tdd]
requires:
  - phase: 473-29
    provides: permanent deny-first account fence and resumable deletion command
provides:
  - authoritative question-owner and account-generation lineage on moderation summaries and events
  - exact-fence transactional moderation writers and owner-bound notification handoff
  - strong paginated moderation discovery with legacy event owner resolution
  - strict noncontent tombstones and two-zero-epoch moderation branch completion
affects: [473-31, 473-34, 473-35]
tech-stack:
  added: []
  patterns:
    - strongly loaded question ownership becomes immutable moderation lineage
    - all moderation writes share the permanent account fence generation
    - summary and event deletion coordinates persist independently across restarts
key-files:
  created:
    - tests/test_phase473_derived_content_purge.py
  modified:
    - src/stoa/db/repositories/moderation_repo.py
    - src/stoa/services/moderation_service.py
    - src/stoa/services/notification_service.py
    - src/stoa/services/account_deletion_service.py
    - tests/test_moderation.py
key-decisions:
  - Authoritative moderation ownership comes from the strongly read question; reporter, actor, and assignee identities never substitute for the student owner.
  - Summary and event rows use one strong base-table discovery pass while persisting separate family continuation coordinates and rejecting divergent resume state.
  - Moderation deletion retains only opaque row identities, lifecycle status/timestamps, and privacy generation; no content hashes or actor pseudonyms survive.
patterns-established:
  - Initial summary and event creation is one fence-conditioned transaction; later updates and events independently require the same existing owned summary and generation.
  - Unresolved lineage and conditional failures remain durable retry debt, and quiescence requires two later zero-unsanitized-row epochs.
requirements-completed: [V9PRIV-01, V9PRIV-02]
duration: 13 min
completed: 2026-07-17
---

# Phase 473 Plan 30: Moderation History Ownership, Fencing, and Purge Summary

Moderation summaries, inline history, and event pages now carry authoritative student lineage, lose every writer race to the permanent account fence, and scrub to restart-safe noncontent tombstones.

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-17T23:00:25Z
- **Completed:** 2026-07-17T23:13:26Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Added a closed moderation row/private-field/writer registry and exact account-generation lineage for every new summary and event.
- Made initial case/event creation atomic; updates, notes, resolutions, and later events now require the existing owned summary and exact active permanent fence.
- Added owner/generation-required moderation notification handoff so Plan 34 cannot receive an ownerless private copy.
- Added strong base-table discovery across every page, including legacy events without `student_id`, with unavailable or conflicting question lineage retained as debt.
- Added strict summary/event tombstones, independent family continuation coordinates, opaque item debt, and two later zero scans before the `moderation_support` branch is quiescent.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing moderation ownership, writer-race, and raw-row purge tests** - `a071094` (test)
2. **Task 2: Propagate authoritative ownership and fence every moderation writer** - `78f09a3` (feat)
3. **Task 3: Implement exhaustive moderation summary/event scrub and branch progress** - `4297fd7` (feat)

Additional correctness commits:

- `34091d7` (fix) excludes privacy-deleted tombstones from active moderation reads.
- `391c9e9` (fix) persists and validates separate summary/event continuation coordinates.

## Files Created/Modified

- `src/stoa/db/repositories/moderation_repo.py` - Closed schema registry, exact-fence writers, authoritative legacy owner resolution, strong pagination, tombstone scrub, and active-read exclusion.
- `src/stoa/services/moderation_service.py` - Question-derived owner/generation propagation through creation, notes, updates, resolution, events, and notification calls.
- `src/stoa/services/notification_service.py` - Required moderation owner envelope with privacy generation on every handoff.
- `src/stoa/services/account_deletion_service.py` - Registered restartable `moderation_support` handler with family cursors, debt, and two clean epochs.
- `tests/test_phase473_derived_content_purge.py` - RED/GREEN ownership, fence, raw-row canary, pagination, lineage-debt, restart, and quiescence coverage.
- `tests/test_moderation.py` - Updated real moderation service fixtures for privacy generation and atomic initial persistence.

## Decisions Made

- The strongly read question is the only owner authority for moderation creation and legacy reconciliation. Reporter, event actor, admin assignee, and inline history identities are private content, not ownership facts.
- One strong base-table scan covers both source-registered moderation families without GSI consistency fiction; the command persists summary/event coordinates separately so malformed or divergent restart state fails closed.
- A scrubbed moderation row is a noncontent tombstone, not an active case/event. Active moderation reads explicitly exclude it while deletion discovery recognizes it as already sanitized.
- The branch is registered with the existing exact 17-branch account-deletion registry but cannot finalize the account; Plan 35 remains the sole sealing/finalization authority.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Excluded scrubbed tombstones from active moderation reads**

- **Found during:** Task 3 final audit
- **Issue:** Legacy active read queries still matched sanitized `moderation_case` and event tombstones, which could project malformed deleted rows through admin APIs.
- **Fix:** `get_case`, `list_cases`, and `list_case_events` now exclude `privacy_deleted` rows, with a repository regression test.
- **Files modified:** `src/stoa/db/repositories/moderation_repo.py`, `tests/test_phase473_derived_content_purge.py`
- **Verification:** The 17-test moderation gate and final 58-test regression gate pass.
- **Committed in:** `34091d7`

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** The fix prevents newly introduced privacy tombstones from re-entering legacy active response paths; no unrelated scope was added.

## Issues Encountered

- Git metadata is read-only in the normal workspace sandbox. Required atomic commits used the approved escalated Git path, and normal repository hooks ran for every commit.

## Verification

- RED gate: 8 intended behavior failures with pytest exit code exactly 1 and no collection/import error.
- Task 2 GREEN gate: 5 selected owner/fence/writer tests passed; the full inherited moderation suite also passed.
- Task 3 GREEN gate: 16 focused tests and targeted Ruff passed before the two final correctness refinements.
- Final gate: 58 tests passed across account deletion, derived moderation purge, moderation APIs, and notifications.
- Ruff passed for all Plan 30 source and test paths; `git diff --check` passed.
- Source registry, strong base-table pagination, malformed/repeating cursor refusal, raw private-canary denial, conditional writer races, restart progress, and two-zero-epoch quiescence are executable tests.
- TDD order is present in Git history: `a071094` precedes `78f09a3` and `4297fd7`.

## Known Stubs

None.

## User Setup Required

None - no dependency, external service, or configuration change is required.

## Next Phase Readiness

- Plan 31 can add the next independent derived-content branch to the same deletion command.
- Plan 34 can consume the owner/generation-bound moderation notification handoff.
- Plan 35 remains the only plan allowed to seal all 17 branches and finalize the permanent account lifecycle.
- No unresolved blockers.

## Self-Check: PASSED

- All six created or modified deliverable paths exist.
- Commits `a071094`, `78f09a3`, `4297fd7`, `34091d7`, and `391c9e9` exist in repository history.
- All mandatory Plan 473-30 verification gates passed from the committed source.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
