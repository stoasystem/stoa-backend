---
gsd_state_version: 1.0
milestone: v3.6
milestone_name: Full WebSocket Realtime Notifications
status: planning
last_updated: "2026-06-08T23:29:31+02:00"
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

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v3.6 full WebSocket realtime notifications.

## Current Position

Phase: 113 Backend WebSocket Connection And Event Delivery
Plan: —
Status: Ready for discuss/planning.
Last activity: 2026-06-09 - Phase 112 WebSocket transport contract and infrastructure readiness passed.

## Accumulated Context

### Decisions

- v3.5 closed as a local foundation release with durable notification events, recipient list/read/archive behavior, admin operational notifications, and teacher summary seeds.
- v3.6 promotes the remaining `stoa_docs` WebSocket requirement from future scope to active scope.
- v3.6 should preserve the existing notification center as fallback while adding authenticated realtime transport.
- Payment provider readiness moves later because full WebSocket realtime notifications were explicitly selected.
- Phase 112 established that durable notification records remain canonical history and WebSocket delivery is a realtime transport overlay.
- Phase 112 set API Gateway WebSocket as the default implementation path unless Phase 113 CDK inspection proves an existing managed entrypoint is available.

### Pending Todos

- Implement backend WebSocket connection and event delivery in Phase 113.
- Implement frontend realtime notification client and UX in Phase 114.
- Run functional release gate and update gap tracking in Phase 115.

### Blockers/Concerns

- CDK changes may be required for API Gateway WebSocket and connection management.
- WebSocket auth and per-recipient authorization must be precise enough for functional correctness.
- Production rollout should support fallback to polling/notification center.

## Operator Next Steps

- Discuss and plan Phase 113 backend WebSocket connection and event delivery.
