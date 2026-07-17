---
phase: 473-student-content-privacy-and-practice-integrity
plan: 25
subsystem: practice-integrity
tags: [practice, privacy, dynamodb, immutable-receipts, directional-hints]

requires:
  - phase: 473-17
    provides: Source-bound privacy evidence and stable practice authorization boundaries
provides:
  - Direct answer-free challenge pointers bound to exact canonical content versions
  - Create-only immutable attempt receipts used as the sole result and mistake source
  - Closed parameter-free directional hint templates with whole-content non-derivability decisions
  - Recursive key-and-value canary coverage for every student preview route
affects: [473-26, 473-35, practice-results, curriculum-seeding]

tech-stack:
  added: []
  patterns: [content-addressed challenge identity, snapshot-only projection, closed hint catalog, fail-closed seed validation]

key-files:
  created:
    - tests/test_phase473_practice_snapshot.py
  modified:
    - src/stoa/db/repositories/practice_repo.py
    - src/stoa/models/practice.py
    - src/stoa/services/practice_projection_service.py
    - src/stoa/routers/practice.py
    - scripts/seed_practice.py
    - tests/test_practice.py
    - tests/test_curriculum_analytics.py

key-decisions:
  - "Opaque challenge IDs resolve through one answer-free pointer to one exact content-addressed canonical row; malformed, missing, duplicated, or stale identity fails closed."
  - "Post-submit answer content is copied into one create-only owner receipt and every later result or mistake projection reads that receipt without consulting mutable curriculum content."
  - "Pre-submit hints can emit only constant bytes from a closed parameter-free catalog after an exact whole-content, version, reviewer, role, policy, decision, and timestamp check."

requirements-completed: [V9PRIV-03]

duration: 14 min
completed: 2026-07-17
---

# Phase 473 Plan 25: Immutable practice attempts and non-derivable hints Summary

**Content-addressed challenge pointers, create-only result snapshots, and constant reviewed hint templates now keep practice answers stable after curriculum mutation and unavailable before durable authorization.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-17T14:45:04Z
- **Completed:** 2026-07-17T14:59:27Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- Replaced filtered challenge lookup with an answer-free opaque-ID pointer followed by one exact canonical GetItem, validated against a whole-content SHA-256 version.
- Added bounded, progress-checked challenge pagination and duplicate identity rejection, with seed validation completing before any write.
- Captured standard answer, explanation, both feedback variants, selected feedback, correctness, submitted answer, next challenge, coordinates, prompt, options, version, hash, and creation time in one conditional create-only attempt receipt.
- Removed current challenge reads from attempt-result and mistake projections, so edit, deletion, duplication, and ID reuse cannot change an existing result.
- Replaced free-form approved hints with three typed parameter-free template IDs and exact non-derivability decisions restricted to canonical `teacher` or `admin` reviewers.
- Added route-level recursive private key/value canaries across overview, curriculum catalog/lesson/exercises, roadmap, path, and lesson previews.

## Task Commits

1. **Task 1: Create failing immutable-attempt, hint, and preview contracts** - `1e6283a` (test)
2. **Task 2: Add direct versioned challenge identity and immutable attempt snapshots** - `d008a3e` (fix)
3. **Task 3: Enforce structural non-derivability and prove all preview routes answer-free** - `3177079` (fix)
4. **Regression fixture follow-up** - `9894f96` (test)

## Files Created/Modified

- `tests/test_phase473_practice_snapshot.py` - Direct pointer, pagination, immutable snapshot, semantic adversary, stale decision, and all-route recursive canary matrix.
- `src/stoa/db/repositories/practice_repo.py` - Canonical hashing/versioning, pointer resolution, bounded pagination, duplicate rejection, and complete create-only receipt persistence.
- `src/stoa/models/practice.py` - Closed directional template/reviewer enums and typed non-derivability decision.
- `src/stoa/services/practice_projection_service.py` - Snapshot-only result projection and constant content-bound hint rendering.
- `src/stoa/routers/practice.py` - Submission-time snapshot capture plus current-content-free result and mistake reads.
- `scripts/seed_practice.py` - Duplicate-first validation, versioned canonical/pointer writes, structural decisions, legacy/dynamic hint rejection, and offline dry-run.
- `tests/test_practice.py` and `tests/test_curriculum_analytics.py` - Inherited fixtures aligned to structural hints and complete durable receipts.

## Decisions Made

- Challenge versions are `sha256:<whole-content-hash>` and cover every content field except storage/version and approval metadata; unknown future content fields therefore invalidate stale pointers and hint decisions automatically.
- Pointer rows contain only identity, target key, version, and hash. They never duplicate prompt, choice, answer, explanation, feedback, or hint truth.
- A partial receipt is indistinguishable from an unavailable attempt for answer-bearing reads; defaults cannot manufacture missing answer content.
- Reviewer provenance is necessary but never sufficient: only a known template ID can select output, and answer-bearing inputs never participate in rendered bytes.

## Verification

- RED gate: **38 failed, 1 passed**, pytest exit exactly **1** before implementation.
- Task 2 pointer/snapshot/attempt gate: **12 passed**.
- Task 3 hint/preview/canary gate: **34 passed**.
- Complete snapshot/practice/privacy suite: **87 passed**.
- Combined practice/privacy/curriculum regression gate: **106 passed**.
- Full Python suite: **passed**.
- Seed dry-run: **156 items** prepared, including 60 canonical challenges and 60 direct pointers; no provider access.
- Targeted Ruff: **passed**.
- `git diff --check`: **passed**.
- Canonical role terminology gate (`tutor` forbidden in touched surface): **passed**.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated stale curriculum analytics receipt mocks**
- **Found during:** Overall practice/curriculum regression verification after Task 3
- **Issue:** Two inherited analytics tests returned partial mocked receipts and correctly hit the new no-answer-from-partial-receipt gate.
- **Fix:** Kept production validation strict and updated only the mocks to echo the complete immutable metadata supplied by the submission route.
- **Files modified:** `tests/test_curriculum_analytics.py`
- **Verification:** Combined practice/privacy/curriculum gate passes with 106 tests.
- **Committed in:** `9894f96`

**2. [Rule 3 - Blocking] Included snapshot projection service in Task 2 implementation**
- **Found during:** Task 2 snapshot-only result implementation
- **Issue:** The Task 2 action required removing current challenge reads, but its local file list omitted the projection service whose old signature required mutable challenge content.
- **Fix:** Changed the projection boundary to accept and validate only one complete receipt.
- **Files modified:** `src/stoa/services/practice_projection_service.py`
- **Verification:** Edit/delete/duplicate/ID-reuse result invariance tests pass.
- **Committed in:** `d008a3e`

**Total deviations:** 2 auto-fixed blocking issues. **Impact:** Both changes were required to enforce the plan's immutable receipt contract; no feature scope was added.

## Issues Encountered

- The managed filesystem denied initial Git index-lock creation. The normal hook-enabled commits were rerun through the approved managed escalation path.

## Known Stubs

None - empty collections and optional fields found by the scan are initialized runtime state or intentional typed optional response fields, not unwired plan behavior.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 473-26 can build privileged practice-answer behavior on the separate typed answer contract without weakening student previews.
- Existing DynamoDB environments must be reseeded/migrated to canonical challenge plus pointer rows before relying on direct lookup; this plan intentionally refuses legacy scan fallback.

## Self-Check: PASSED

- The new snapshot suite and every modified key file exist.
- Task commits `1e6283a`, `d008a3e`, `3177079`, and `9894f96` exist in repository history.
- All task acceptance gates and plan-level verification commands pass.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
