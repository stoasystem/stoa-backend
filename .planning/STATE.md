---
gsd_state_version: 1.0
milestone: v3.7
milestone_name: AI Teacher Tools And Exercise Generation
status: planning
last_updated: "2026-06-09T13:20:20+02:00"
last_activity: 2026-06-09
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 4
  completed_plans: 1
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-09)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v3.7 AI teacher tools and exercise generation.

## Current Position

Phase: 116 AI Teacher Tools Contract And Generation Model
Plan: 116-01
Status: Planned.
Last activity: 2026-06-09 - selected AI teacher tools, automatic summaries, and exercise generation as the next milestone after v3.6 WebSocket realtime notifications.

## Accumulated Context

### Decisions

- v3.4 added subject taxonomy, topic seeds, and student learning profile foundations.
- v3.5 added durable notification events and teacher assistance summary seeds.
- v3.6 added local functional WebSocket notification delivery.
- v3.7 promotes the remaining `stoa_docs` AI teacher tools / automatic summaries / exercise generation scope from future expansion to active scope.
- v3.7 keeps teacher/admin review in the loop; generated replies/exercises are drafts, not automatic student delivery.

### Pending Todos

- Complete Phase 116 AI teacher tools contract and generation model docs.
- Implement backend teacher summary and exercise draft APIs in Phase 117.
- Implement tutor AI tools and exercise draft UI in Phase 118.
- Run functional release gate and update gap tracking in Phase 119.

### Blockers/Concerns

- Generated content must remain draft/reviewed until an explicit teacher/admin action.
- Full curriculum-aligned exercise bank remains future scope.
- Existing Bedrock/AI service behavior should be reused unless Phase 116 proves a new model path is needed.

## Operator Next Steps

- Execute Phase 116 and proceed to backend AI teacher tool draft APIs.
