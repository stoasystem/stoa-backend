---
gsd_state_version: 1.0
milestone: v4.2
milestone_name: Production Notification Delivery Readiness
status: planning
last_updated: "2026-06-11T12:47:45+02:00"
last_activity: 2026-06-11
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 4
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-11)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v4.2 production notification delivery readiness.

## Current Position

Phase: 136 - Production Notification Infrastructure Contract
Plan: 136-01
Status: Planning
Last activity: 2026-06-11 - Selected v4.2 after syncing v4.1 docs to `origin/main` and rechecking the `stoa_docs` remaining feature queue.

## Accumulated Context

### Decisions

- v3.4 added subject taxonomy, topic seeds, and student learning profile foundations.
- v3.6 completed local functional WebSocket realtime notifications, including backend connection records, event fanout helpers, frontend realtime client behavior, and polling fallback.
- v3.7 added reviewed AI exercise drafts but intentionally did not assign them automatically.
- v3.8 added curriculum catalog, exercise bank, progress APIs, and student/parent/tutor curriculum UX.
- v3.9 completed the local payment provider integration MVP.
- v4.0 delivered durable memory snapshots, next-practice recommendations, reviewed assignment APIs, and student/tutor/parent route contracts.
- v4.1 delivered the backend mobile/multilingual foundation: `en`/`de` locale policy, durable locale preferences, additive route metadata, and deferred frontend/native ownership.
- The next backend-feasible `stoa_docs` feature gap is production notification delivery readiness. Full frontend/native mobile and visual localization remain important, but they require the UI workspace.
- v4.2 should prioritize feature construction for internal development: production WebSocket delivery contract, notification preferences, delivery operations, email digest readiness, and push-ready preference metadata.

### Pending Todos

- Execute Phase 136: define production notification infrastructure and channel contract.
- Plan and implement Phase 137 notification preference APIs and delivery operations.
- Plan and implement Phase 138 email digest and push preference readiness.
- Close Phase 139 with functional release evidence and updated feature gap audit.

### Blockers/Concerns

- This workspace is backend-only; actual frontend/native responsive UI and visual localization implementation may require another workspace.
- CDK/API Gateway WebSocket deployment work may require the infrastructure repository or explicit CDK surface in this repository.
- Native push provider rollout and production email sending should wait for approved provider credentials and explicit rollout decision.
- Production mutation smoke should not send real customer notifications without explicit approval.

## Operator Next Steps

- Start Phase 136 and write the production notification delivery contract.
