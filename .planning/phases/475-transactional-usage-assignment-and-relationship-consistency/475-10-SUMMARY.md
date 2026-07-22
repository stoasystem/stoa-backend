---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 10
subsystem: api
tags: [practice, pydantic, dynamodb, normalization, legacy-projection]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 09
    provides: capped idempotent practice-hint admission and preserved practice route boundaries
  - phase: 473-student-content-privacy-and-practice-integrity
    provides: immutable attempt receipts and answer-free pre-submission projections
provides:
  - bounded versioned submitted-answer persistence in both compatibility fields
  - typed recorded and legacy-unknown mistake response states
  - redacted pre-persistence rejection for unsupported or oversized answers
affects: [475-13-integrated-evidence, 478-web-practice-journey, V9DATA-05]

tech-stack:
  added: []
  patterns: [object-valued request narrowing, canonical bounded JSON encoding, explicit legacy-unknown projection]

key-files:
  created:
    - tests/test_phase475_mistake_answer.py
  modified:
    - src/stoa/models/practice.py
    - src/stoa/db/repositories/practice_repo.py
    - src/stoa/services/practice_projection_service.py
    - src/stoa/routers/practice.py

key-decisions:
  - "Submitted practice answers accept one string or one flat string list, preserve Unicode and whitespace bytes, and fail before storage above 4096 serialized UTF-8 bytes, 50 items, or one list depth."
  - "Unsupported answer bodies enter the route as untrusted object values so application validation can return one coordinate-free error without echoing the submitted value."
  - "Mistake review distinguishes recorded from unknown_legacy with a nullable answer and never reads standard_answer as a fallback."

patterns-established:
  - "Answer persistence: normalize before table access, write both compatibility fields, and bind them to submitted_answer_schema_version 1."
  - "Legacy projection: absence of both submitted-answer fields returns null plus the fixed client message; malformed present values fail closed instead of being guessed."

requirements-completed: [V9DATA-05]

duration: 7 min
completed: 2026-07-22
---

# Phase 475 Plan 10: Bounded Mistake Answer And Legacy Projection Summary

**Wrong practice answers now round-trip exactly within explicit display bounds, while historical absence is represented as a typed unknown rather than an empty or substituted correct answer.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-22T00:01:35Z
- **Completed:** 2026-07-22T00:08:30Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments

- Added deterministic UTF-8 JSON sizing plus explicit 4096-byte, 50-item, and flat-list depth bounds before any practice table access.
- Persisted the exact accepted answer in both `student_answer` and `submitted_answer` with schema version 1.
- Added typed `recorded` and `unknown_legacy` mistake projections with nullable `yourAnswer` and the exact message `当时提交的答案未保存`.
- Replaced validation paths that could echo unsupported request values with one stable redacted 422 response.
- Proved scalar, list, Unicode, whitespace, bound, unsupported-shape, legacy, schema, and correct-answer non-substitution behavior without changing answer-free previews or privileged answer access.

## Task Commits

Each task was committed atomically:

1. **Task 1: Persist bounded answers and project legacy unknown explicitly** - `8afcda3` (fix)

## Files Created/Modified

- `src/stoa/models/practice.py` - Untrusted answer input plus typed mistake item/response and closed legacy-answer states.
- `src/stoa/db/repositories/practice_repo.py` - Pre-table normalization and versioned dual-field persistence.
- `src/stoa/services/practice_projection_service.py` - Deterministic answer bounds and recorded/legacy-unknown projection.
- `src/stoa/routers/practice.py` - Redacted invalid-answer response and typed mistake response route.
- `tests/test_phase475_mistake_answer.py` - Round-trip, bound, redaction, legacy, non-substitution, and schema proof.

## Decisions Made

- Preserved accepted strings byte-for-byte, including Unicode and whitespace, rather than trimming or case-normalizing the displayed answer; comparison normalization remains separate from storage.
- Limited the persisted public answer shape to one string or a flat list of strings, matching the established practice contract while making byte, depth, and item limits explicit.
- Used `submitted_answer` as the preferred current field and `student_answer` as its compatibility fallback. Only absence of both is legacy unknown; a present malformed value is not silently reclassified or replaced.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The repository sandbox initially denied `.git/index.lock`; the same scoped staging and normal hook-enabled commit succeeded with approved repository permission.
- Optional targeted mypy retains 16 pre-existing `practice_repo.py` DynamoDB table-capability errors in unchanged lines. The changed model and projection modules pass mypy.
- One optional expanded learning regression is stale after Plan 475-02 and still mocks the former non-atomic question route; the other 68 nodes in that run passed. This unrelated fixture is recorded in `deferred-items.md` and was not changed.

## Verification

- Plan command — 97 passed across the new answer tests, immutable practice snapshots, privacy separation, and practice routes; Ruff passed all planned files.
- Additional practice authorization/privacy-deletion/curriculum regression — 63 passed.
- Expanded learning regression — 68 passed and one unrelated stale question-route fixture failed as documented above.
- `.venv/bin/mypy src/stoa/models/practice.py src/stoa/services/practice_projection_service.py` — passed with no issues.
- `git diff --check` — passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 475-13 can bind the new normalization, redacted rejection, and legacy-unknown nodes into the integrated V9DATA-05 evidence gate.
- Phase 478 can render `answerState`, nullable `yourAnswer`, and the fixed legacy message without guessing historical input.

## Known Stubs

None.

## Self-Check: PASSED

- All five planned created/modified files exist in the working tree.
- Task commit `8afcda3` exists and contains exactly the five intended implementation/test files with no deletions.
- Every task acceptance criterion and the exact plan verification command pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
