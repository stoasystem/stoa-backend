---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 40
subsystem: api
tags: [practice, mypy, fastapi, type-narrowing, d14]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 10
    provides: bounded submitted-answer persistence, redacted validation, and explicit legacy-unknown projection
provides:
  - an unfiltered mypy-clean practice router
  - explicit mapping, optional-string, string, list, and attempt-result narrowing at practice API boundaries
affects: [475-integrated-evidence, V9DATA-05, practice-api]

tech-stack:
  added: []
  patterns: [runtime boundary narrowing, covariant mapping collections, typed response construction]

key-files:
  created: []
  modified:
    - src/stoa/routers/practice.py

key-decisions:
  - "Repository-backed practice values are narrowed at the route boundary before entering string- and list-typed repository APIs; valid string and list values retain their original bytes and elements."
  - "Challenge preview collections are typed as lists of Mapping values so the router satisfies list invariance without casts, ignores, Any propagation, or projection changes."

patterns-established:
  - "Practice boundary narrowing: accept repository mappings, preserve valid typed values exactly, and use existing optional/default semantics for absent or malformed fields."

requirements-completed: [V9DATA-05]

duration: 25 min
completed: 2026-07-22
---

# Phase 475 Plan 40: Practice Router Mypy Closure Summary

**The practice router now passes the exact unfiltered mypy gate through explicit boundary narrowing while preserving D-14 answer persistence, reveal timing, redacted validation, and legacy-unknown behavior.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-22T08:19:12Z
- **Completed:** 2026-07-22T08:44:21Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Removed all 15 exact-file mypy diagnostics without ignores, casts, exclusions, configuration changes, or dependency changes.
- Added explicit mapping collection annotations and runtime narrowing for optional topic IDs, string metadata fields, answer options, and the typed attempt response.
- Preserved the accepted Unicode/whitespace answer bytes, item/byte/depth bounds, redacted 422 response, persistence-before-answer-reveal ordering, correct-answer non-substitution, and legacy unknown projection.

## Task Commits

Each task was committed atomically:

1. **Task 1: Eliminate practice router mypy diagnostics** - `3f398c5` (refactor)

## Files Created/Modified

- `src/stoa/routers/practice.py` - Explicitly narrows practice repository values and types preview/attempt projections without changing route contracts.

## Decisions Made

- Used runtime `isinstance` narrowing for values crossing from generic repository mappings into typed route/repository calls, preserving valid strings and lists unchanged.
- Annotated preview collections as `list[Mapping[str, Any]]` to satisfy mutable-list invariance at the existing projection signature rather than weakening that signature or spreading `Any`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The repository sandbox initially denied creation of `.git/index.lock`; the same single-file staging and normal hook-enabled commit succeeded with the scoped repository permission.
- Unrelated concurrent user changes in `README.md`, two provisioning/seed scripts, and two AWS operator identity files were preserved and excluded from every staging operation.

## Verification

- `.venv/bin/mypy src/stoa/routers/practice.py` - passed with no issues in one source file.
- `.venv/bin/mypy --no-incremental src/stoa/routers/practice.py` - passed with no issues in one source file.
- `.venv/bin/python -m pytest -q tests/test_phase475_mistake_answer.py tests/test_practice.py` - 18 passed; one third-party Starlette deprecation warning.
- `.venv/bin/ruff check src/stoa/routers/practice.py` - passed.
- `git diff --check -- src/stoa/routers/practice.py` - passed.

## User Setup Required

None - no dependency or external service changes.

## Next Phase Readiness

- The practice router can enter the Phase 475 unfiltered mypy and integrated V9DATA-05 evidence gates.
- D-14 behavior remains covered by the focused mistake-answer and practice endpoint tests.

## Known Stubs

None. Existing empty list accumulators and optional defaults are populated or resolved within their request flows and are not placeholder data sources.

## Self-Check: PASSED

- The modified router and this Summary exist in the working tree.
- Task commit `3f398c5` exists and contains exactly `src/stoa/routers/practice.py`, with no deletions.
- Every task acceptance criterion and the exact plan verification command passed.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
