---
gsd_state_version: 1.0
milestone: v3.6
milestone_name: Full WebSocket Realtime Notifications
status: complete
last_updated: "2026-06-09T13:01:25+02:00"
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

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v3.6 full WebSocket realtime notifications.

## Current Position

Phase: v3.6 milestone complete
Plan: —
Status: Complete for local functional release gate.
Last activity: 2026-06-09 - Phase 115 release gate and realtime audit passed.

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
- Phase 115 passed backend focused pytest/Ruff, backend full pytest, frontend lint/build/browser checks, and updated gap audit/release evidence.

### Pending Todos

- Choose the next milestone.

### Blockers/Concerns

- Production API Gateway WebSocket route/integration/CDK deployment and live endpoint smoke remain future rollout scope.
- Push/native/email notification delivery remains future scope.

## Operator Next Steps

- Select and plan the next milestone.
