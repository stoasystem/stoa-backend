---
phase: 02-parent-child-list-and-access-rules
plan: 02
subsystem: api
tags: [fastapi, parent-portal, legacy-routes, authorization]
requires:
  - phase: 02-parent-child-list-and-access-rules
    provides: Parent resolver and child lookup helpers from plan 01
provides:
  - Legacy /parents/{parent_id}/children local-profile authorization
  - Legacy /parents/{parent_id}/reports/{week} local-profile authorization
  - Focused pytest coverage for legacy compatibility
affects: [parent-api, reports, authorization]
tech-stack:
  added: []
  patterns:
    - Legacy parent path routes compare path parent_id with resolved local parent profile ID
key-files:
  created: []
  modified:
    - src/stoa/routers/parents.py
    - tests/test_parent_children.py
key-decisions:
  - "Admin compatibility remains only on legacy path-ID routes."
  - "Legacy report route preserves existing 404 behavior for missing reports."
patterns-established:
  - "Parent path-ID routes should not compare parent_id to raw JWT sub."
requirements-completed: [PARENT-08, AUTHZ-01, AUTHZ-03, AUTHZ-04, AUTHZ-05]
duration: 20min
completed: 2026-06-02
---

# Phase 2 Plan 02 Summary

**Legacy parent child/report routes preserved with local-profile parent authorization**

## Performance

- **Duration:** 20 min
- **Started:** 2026-06-02
- **Completed:** 2026-06-02
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Updated legacy `/parents/{parent_id}/children` authorization to compare path `parent_id` with `resolved.parent_user_id`.
- Updated legacy `/parents/{parent_id}/reports/{week}` authorization the same way while preserving `WeeklyReportResponse` and missing-report 404 behavior.
- Preserved admin compatibility on legacy path-ID routes while tests prove admin is rejected from `/parents/me/children`.

## Task Commits

1. **Parent child list access implementation** - `224dda7` (`feat(02): add parent child list access`)

## Files Created/Modified

- `src/stoa/routers/parents.py` - Legacy route authorization aligned with local parent profile IDs.
- `tests/test_parent_children.py` - Legacy route compatibility and access-boundary tests.

## Decisions Made

- Kept legacy route surface and response behavior intact.
- Limited admin compatibility to legacy routes only.

## Deviations from Plan

Implemented with Plan 02-01 in one commit because both plans shared the same route helper and test module.

## Issues Encountered

None beyond the `uv` cache sandbox issue recorded in Plan 01 summary.

## User Setup Required

None.

## Next Phase Readiness

Phase 3 can add child-specific summary/history/report routes using the same resolver and ownership invariant.

---
*Phase: 02-parent-child-list-and-access-rules*
*Completed: 2026-06-02*
