---
gsd_state_version: 1.0
milestone: v3.8
milestone_name: Full Curriculum Rollout
status: executing
last_updated: "2026-06-09T14:52:00+02:00"
last_activity: 2026-06-09
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 4
  completed_plans: 1
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-09)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v3.8 full curriculum rollout.

## Current Position

Phase: 121 Backend Curriculum Catalog And Exercise Bank APIs
Plan: —
Status: Ready for backend planning.
Last activity: 2026-06-09 - Phase 120 curriculum rollout contract completed.

## Accumulated Context

### Decisions

- v3.4 added subject taxonomy, topic seeds, and student learning profile foundations.
- Existing practice routes and `practice_repo` already model subjects, topics, lessons, challenges, progress, mistakes, and attempts.
- v3.7 added reviewed exercise draft generation, but left full curriculum-aligned exercise banks and long-term adaptive sequencing as future scope.
- v3.8 promotes full multi-subject curriculum rollout from future expansion to active scope.
- v3.8 should preserve existing practice progress and challenge attempt behavior while adding richer curriculum catalog/content metadata.
- Phase 120 defined the curriculum hierarchy, content lifecycle states, lesson/exercise fields, and existing-practice compatibility contract.

### Pending Todos

- Implement backend curriculum catalog and exercise bank APIs in Phase 121.
- Implement student/parent curriculum UX and tutor/admin curriculum signals in Phase 122.
- Run functional release gate and update gap tracking in Phase 123.

### Blockers/Concerns

- Curriculum rollout must not claim unsupported content is active.
- Automatic exercise assignment and full adaptive sequencing remain future scope.
- Existing practice data access patterns should be reused unless Phase 120 proves they cannot support curriculum catalog needs.

## Operator Next Steps

- Plan and execute Phase 121 backend curriculum catalog and exercise bank APIs.
