---
gsd_state_version: 1.0
milestone: v3.8
milestone_name: Full Curriculum Rollout
status: complete
last_updated: "2026-06-09T15:12:43+02:00"
last_activity: 2026-06-09
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 4
  completed_plans: 4
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-09)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v3.8 full curriculum rollout complete; next milestone selection.

## Current Position

Phase: 123 Functional Release Gate And Curriculum Audit
Plan: 123-01
Status: Complete.
Last activity: 2026-06-09 - v3.8 full curriculum rollout passed local functional release gate.

## Accumulated Context

### Decisions

- v3.4 added subject taxonomy, topic seeds, and student learning profile foundations.
- Existing practice routes and `practice_repo` already model subjects, topics, lessons, challenges, progress, mistakes, and attempts.
- v3.7 added reviewed exercise draft generation, but left full curriculum-aligned exercise banks and long-term adaptive sequencing as future scope.
- v3.8 completed the full multi-subject curriculum rollout for local functional scope.
- v3.8 should preserve existing practice progress and challenge attempt behavior while adding richer curriculum catalog/content metadata.
- Phase 120 defined the curriculum hierarchy, content lifecycle states, lesson/exercise fields, and existing-practice compatibility contract.
- Phase 121 added curriculum catalog, lesson detail, exercise bank, and progress APIs on top of existing practice content/progress records.
- Phase 122 added student, parent, and tutor curriculum rollout UI signals backed by the new curriculum APIs.
- Phase 123 closed the local functional release gate with backend, frontend, and Playwright evidence and updated the feature gap audit.

### Pending Todos

- Select the next milestone. Recommended next: v3.9 Payment Provider Readiness.

### Blockers/Concerns

- Curriculum rollout must not claim unsupported content is active.
- Automatic exercise assignment and full adaptive sequencing remain future scope.
- Existing practice data access patterns should be reused unless Phase 120 proves they cannot support curriculum catalog needs.

## Operator Next Steps

- Start v3.9 Payment Provider Readiness or adjust the next milestone sequence.
