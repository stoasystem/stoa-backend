---
gsd_state_version: 1.0
milestone: v3.6
milestone_name: Full WebSocket Realtime Notifications
status: executing
last_updated: "2026-06-09T12:59:00+02:00"
last_activity: 2026-06-09
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 4
  completed_plans: 3
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v3.6 full WebSocket realtime notifications.

## Current Position

Phase: 115 Functional Release Gate And Realtime Audit
Plan: —
Status: Ready for release gate planning.
Last activity: 2026-06-09 - Phase 114 frontend realtime notification client and UX passed.

## Accumulated Context

### Decisions

- v3.5 closed as a local foundation release with durable notification events, recipient list/read/archive behavior, admin operational notifications, and teacher summary seeds.
- v3.6 promotes the remaining `stoa_docs` WebSocket requirement from future scope to active scope.
- v3.6 should preserve the existing notification center as fallback while adding authenticated realtime transport.
- Payment provider readiness moves later because full WebSocket realtime notifications were explicitly selected.
- Phase 112 established that durable notification records remain canonical history and WebSocket delivery is a realtime transport overlay.
- Phase 112 set API Gateway WebSocket as the default implementation path unless Phase 113 CDK inspection proves an existing managed entrypoint is available.
- Phase 113 added DynamoDB-backed WebSocket connection records, server-authorized subscriptions, fallback-safe notification fanout, and delivery attempt metadata.
- Phase 113 keeps empty WebSocket endpoint behavior non-destructive for local/test runs while allowing API Gateway Management API posting when configured.
- Phase 114 added feature-flagged frontend WebSocket notification client behavior in `stoa-frontend` commit `79c6628`, including heartbeat, reconnect/offline/fallback states, cache merge, and browser fixture coverage.

### Pending Todos

- Run functional release gate and update gap tracking in Phase 115.

### Blockers/Concerns

- CDK changes may still be required for API Gateway WebSocket and connection management endpoint configuration.
- Production rollout should support fallback to polling/notification center.

## Operator Next Steps

- Discuss and plan Phase 115 functional release gate and realtime audit.
