---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 25
subsystem: database
tags: [dynamodb, account-deletion, identity-discovery, pagination, privacy]

requires:
  - phase: 473-student-content-privacy-and-practice-integrity
    provides: strong base-table deletion discovery and two-clean-epoch quiescence
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 22
    provides: formal parent/student relationship rows with exact participant identities
provides:
  - closed entity-aware discovery for parent, teacher, actor, and reviewed notification metadata references
  - exact-match cross-account selection without arbitrary recursive payload scanning
  - focused proof for strong pagination, repeating-cursor rejection, late writes, and two later clean epochs
affects: [475-26-relationship-deletion-scrub, 475-27-teacher-identity-scrub, 475-28-notification-identity-scrub, V9DATA-02, V9DATA-03, V9DATA-07]

tech-stack:
  added: []
  patterns: [entity-scoped identity registry, exact normalized identity matching, bounded strong discovery]

key-files:
  created:
    - tests/test_phase475_deletion_discovery.py
  modified:
    - src/stoa/db/repositories/account_deletion_repo.py

key-decisions:
  - "Cross-account discovery uses an explicit entity-to-scalar/metadata field registry; arbitrary nested payloads and substring matching remain excluded."
  - "The requested identity is normalized once, while persisted reference values must equal it exactly."
  - "Existing strong base-table pagination, repeating-cursor rejection, and two-clean-epoch state transitions remain the completeness boundary."

patterns-established:
  - "Reviewed reference discovery: register the exact persisted entity and field path before a foreign-owned row can enter deletion processing."
  - "Late-write quiescence: any matching row after a clean pass resets progress, followed by two complete clean epochs."

requirements-completed: [V9DATA-02, V9DATA-03, V9DATA-07]

duration: 7 min
completed: 2026-07-22
---

# Phase 475 Plan 25: Cross-Account Deletion Discovery Summary

**Account deletion now discovers exact foreign-owned parent, teacher, actor, and reviewed notification metadata references without broad payload inspection, while retaining bounded strong pagination and two-clean-epoch quiescence.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-22T07:53:36Z
- **Completed:** 2026-07-22T08:00:14Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Added a closed entity-aware registry for formal relationship `parent_id`, question/session `teacher_id`, notification `actor_id`, and notification metadata `owner_id`, `student_id`, and `teacher_id` references.
- Kept discovery exact-match only: near matches, free text, unregistered entities, and unregistered nested payloads remain invisible to the cross-account selector.
- Normalized the deletion subject before matching while preserving strongly consistent base-table pagination, bounded page counts, and repeated-cursor rejection.
- Added one parameterized TDD node covering seven positive fields, five negative shapes, late-page discovery, repeated cursors, and a late write that resets clean progress before two later clean epochs.

## TDD Cycle

- **RED:** The new parameterized discovery node failed 7 positive cases and passed all 5 negative cases against the pre-change selector.
- **GREEN:** Added the minimal explicit registry and exact matching path; all 12 parameter cases and inherited deletion/notification regressions pass.
- **REFACTOR:** No separate refactor was necessary; the minimal implementation passed focused, regression, Ruff, and diff gates.

## Task Commits

1. **RED: Add failing cross-account deletion discovery proof** - `9fb6b96` (test)
2. **GREEN: Discover reviewed cross-account identity references** - `12ef9ff` (feat)

## Files Created/Modified

- `tests/test_phase475_deletion_discovery.py` - Parameterized positive/negative field matrix plus strong pagination, cursor, late-write, and clean-epoch proof.
- `src/stoa/db/repositories/account_deletion_repo.py` - Closed cross-account identity-reference registry and exact entity-aware matching.

## Decisions Made

- Kept the registry in the deletion repository beside the selector so every new entity/field path is an auditable code change.
- Registered only persisted schemas reviewed by CR-10; nested `actor_id`, arbitrary payload fields, and fields on unknown entities do not match.
- Reused `_run_base_branch` unchanged because its dirty-pass reset and two-later-clean-epoch behavior already met the required quiescence contract once discovery supplies the missing rows.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The restricted sandbox initially denied `.git/index.lock`; both individually scoped TDD commits were rerun with repository write approval. Normal hooks were retained and no verification was bypassed.

## Verification

- Exact plan node — 12 passed.
- Inherited account-deletion, claim-fencing, seal, notification-deletion, and delivery-recovery regressions — 70 passed.
- Ruff over both planned files — passed.
- `git diff --check HEAD~2..HEAD` — passed.
- Normal repository commit hooks ran for both TDD commits; no `--no-verify` was used.

## User Setup Required

None - no package installation, credential, provider call, deployment, or external configuration is required.

## Known Stubs

None. Empty collections in the focused test are bounded accumulators or deliberate clean-page fixtures.

## Next Phase Readiness

- Plans 475-26 through 475-28 can now receive deterministic cross-account relationship, teacher, and notification rows for entity-specific CAS scrub.
- Live AWS, provider, Web, native, billing, and deployment scope remains outside this plan.

## Self-Check: PASSED

- Both planned implementation/test files and this summary exist.
- RED commit `9fb6b96` and GREEN commit `12ef9ff` exist in Git history in the required order.
- Exact plan verification, inherited account-deletion seal regressions, Ruff, diff check, stub scan, and threat-surface scan passed.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
