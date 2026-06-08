---
gsd_state_version: 1.0
milestone: v3.6
milestone_name: Full WebSocket Realtime Notifications
status: planning
last_updated: "2026-06-08T23:29:31+02:00"
last_activity: 2026-06-08
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 4
  completed_plans: 1
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v3.6 full WebSocket realtime notifications.

## Current Position

Phase: 112 Full WebSocket Transport Contract And Infra Readiness
Plan: 112-01
Status: Planned.
Last activity: 2026-06-08 - selected full WebSocket realtime notifications as the next milestone after v3.5 notification foundation.

## Accumulated Context

### Decisions

- v3.5 closed as a local foundation release with durable notification events, recipient list/read/archive behavior, admin operational notifications, and teacher summary seeds.
- v3.6 promotes the remaining `stoa_docs` WebSocket requirement from future scope to active scope.
- v3.6 should preserve the existing notification center as fallback while adding authenticated realtime transport.
- Payment provider readiness moves later because full WebSocket realtime notifications were explicitly selected.

### Pending Todos

- Complete Phase 112 WebSocket transport contract and infrastructure readiness docs.
- Implement backend WebSocket connection and event delivery in Phase 113.
- Implement frontend realtime notification client and UX in Phase 114.
- Run functional release gate and update gap tracking in Phase 115.

### Blockers/Concerns

- CDK changes may be required for API Gateway WebSocket and connection management.
- WebSocket auth and per-recipient authorization must be precise enough for functional correctness.
- Production rollout should support fallback to polling/notification center.

## Operator Next Steps

- Execute Phase 112 and proceed to backend WebSocket delivery.
