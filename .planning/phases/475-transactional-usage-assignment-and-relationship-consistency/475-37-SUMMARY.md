---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 37
subsystem: api
tags: [mypy, fastapi, dynamodb, teacher-takeover, authorization]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 21
    provides: active canonical-teacher account and PROFILE observation fence for takeover
provides:
  - exact-file mypy-clean teacher router
  - runtime-narrowed DynamoDB operation and response boundaries
  - explicit authenticated-teacher and Pydantic response construction
affects: [475-44-coverage-registry, V9DATA-02, CR-04, D-08]

tech-stack:
  added: []
  patterns: [operation-specific runtime Protocol narrowing, object-to-text response validation]

key-files:
  created: []
  modified:
    - src/stoa/routers/teachers.py

key-decisions:
  - "Teacher DynamoDB values remain object-typed until operation-specific runtime Protocol checks and explicit Mapping/list/text narrowing establish safe use."
  - "The router passes the exact authorized teacher PROFILE key and observed version into takeover while preserving the existing winner replay, loser concealment, and notification recovery paths."

patterns-established:
  - "Teacher route persistence boundary: validate table capability, mapping keys, collection shape, and response text before business use."

requirements-completed: [V9DATA-02]

duration: 5 min
completed: 2026-07-22
---

# Phase 475 Plan 37: Teacher Router Type Boundary Summary

**The teacher router is exact-file mypy-clean through explicit authenticated-teacher, DynamoDB capability, persisted-value, and response-model narrowing without changing takeover or reply behavior.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-22T15:28:59Z
- **Completed:** 2026-07-22T15:34:55Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Removed all 49 exact-file mypy diagnostics from `src/stoa/routers/teachers.py` without ignores, casts, exclusions, config changes, or dependency changes.
- Added least-capability runtime Protocol checks and explicit Mapping/list/text narrowing for DynamoDB-backed teacher queue, help-request, message, note, and availability data.
- Preserved CR-04's exact active-teacher PROFILE key/version observation, D-08's coordinate-free loser response, deterministic winner replay, and notification-effect recovery behavior.
- Constructed typed availability slots and AI draft list responses explicitly so Pydantic and static collection contracts agree.

## Task Commits

Each task was committed atomically:

1. **Task 1: Eliminate teacher router mypy diagnostics** - `1d73c84` (fix)

## Files Created/Modified

- `src/stoa/routers/teachers.py` - Narrows authenticated facts, provider capabilities, persisted rows, optional text, collections, and response models at the route boundary.

## Decisions Made

- Kept DynamoDB handles typed as `object` until the exact requested operation is proven through a runtime-checkable Protocol; malformed provider responses fail closed before their values reach authorization or response construction.
- Preserved the takeover repository call and public outcomes while narrowing the authenticated teacher ID and passing the same authorization-time PROFILE key/version observation required by Plan 21.
- Reused one `_now` implementation and direct `Attr`/`Key` imports as type-only cleanup; route paths, effect order, status transitions, and valid response bytes remain unchanged.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The baseline contained 49 target-file diagnostics; the first implementation pass reduced them to five, and the final narrowing pass cleared the exact gate.

## Verification

- `.venv/bin/mypy src/stoa/routers/teachers.py` - passed with zero diagnostics.
- `.venv/bin/python -m pytest -q tests/test_phase475_teacher_takeover.py tests/test_phase475_teacher_takeover_effect.py` - 19 passed, one third-party deprecation warning.
- `.venv/bin/ruff check src/stoa/routers/teachers.py` - passed.
- `git diff --check HEAD~1 HEAD` - passed.
- Commit isolation inspection confirms `1d73c84` contains only `src/stoa/routers/teachers.py`; the five user-owned README/scripts/AWS identity paths remain unstaged.

## User Setup Required

None - no dependency, credential, schema, service, or deployment change is required.

## Known Stubs

None. The stub scan matched only typed optional fields, empty local accumulators, and default-value helpers; no placeholder or unwired production path was introduced.

## Next Phase Readiness

- The teacher router now satisfies the honest unfiltered mypy gate after the CR-04 fence.
- Plan 475-44 and final Phase 475 evidence can consume the type-clean teacher boundary with takeover privacy and replay contracts intact.

## Self-Check: PASSED

- `src/stoa/routers/teachers.py` and this summary exist.
- Task commit `1d73c84` exists and contains no tracked deletion.
- Exact mypy, takeover/effect regressions, Ruff, diff check, stub scan, and commit isolation all pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
