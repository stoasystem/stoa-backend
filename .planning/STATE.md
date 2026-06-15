---
gsd_state_version: 1.0
milestone: v5.5
milestone_name: Automatic Teacher Dispatch And SLA Load Balancing
status: planning
last_updated: "2026-06-15T23:55:00+02:00"
last_activity: 2026-06-15 - Synced v5.4 completion to remote and selected v5.5 teacher dispatch from the stoa_docs remaining-feature queue.
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 5
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-15)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v5.5 automatic teacher dispatch and SLA load balancing.

## Current Position

Phase: 196 - Teacher Dispatch And SLA Load Balancing Contract
Plan: 196-01
Status: Planned
Last activity: 2026-06-15 - Remote sync completed for v5.4 and v5.5 selected after checking `stoa_docs`, existing teacher queue code, and remaining product gaps.

## Accumulated Context

### Decisions

- `stoa_docs` includes teacher request, teacher queue, takeover, reply, resolve, response SLA, and auto-reassignment risk mitigation.
- Existing backend already supports request-teacher escalation, manual queue, teacher takeover, reply, resolve, notifications, and SLA metrics.
- v5.5 should add automatic routing and reassignment, not automatic answering.
- v5.5 should preserve manual takeover compatibility while improving queue health and response time.
- External payment/support activation remains blocked on prerequisites; internal development should continue with dispatch functionality.

### Pending Todos

- Execute Phase 196 teacher dispatch and SLA load balancing contract planning.
- Implement dispatch planner and candidate ranking in Phase 197.
- Implement automatic dispatch claim and reassignment worker in Phase 198.
- Implement teacher queue and operator dispatch visibility in Phase 199.
- Close v5.5 with release-gate evidence and next milestone selection in Phase 200.

### Blockers/Concerns

- Teacher/tutor availability may initially be a local profile/metadata contract rather than live calendar integration.
- Dispatch must avoid double assignment and must preserve teacher manual takeover semantics.
- Student-facing state should stay simple and should not expose internal teacher scoring.
- Broad security/compliance testing is not the priority during this internal development milestone.

## Operator Next Steps

- Start Phase 196 using `.planning/phases/196-teacher-dispatch-and-sla-load-balancing-contract/196-01-PLAN.md`.
