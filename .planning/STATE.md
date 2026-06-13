---
gsd_state_version: 1.0
milestone: v4.9
milestone_name: Production Notification And Native Delivery Rollout
status: planning
last_updated: "2026-06-13T00:00:00+02:00"
last_activity: 2026-06-13
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 5
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-13)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v4.9 production notification and native delivery rollout.

## Current Position

Phase: 166 - Production Notification Rollout Contract And Ownership
Plan: 166-01
Status: Planned
Last activity: 2026-06-13 - Synced v4.8 completion to remote and selected v4.9 from the `stoa_docs` remaining-feature queue.

## Accumulated Context

### Decisions

- v3.6 completed local functional WebSocket realtime notifications with backend connection records, fanout helpers, delivery attempt metadata, frontend WebSocket client behavior, notification center cache sync, reconnect/offline states, and polling fallback.
- v4.2 completed backend-local production notification delivery readiness: production WebSocket contracts, durable preferences, preference-aware delivery state/status behavior, email digest preview readiness, push-ready preference metadata, and clean local release evidence.
- v4.3 completed selected frontend mobile/localization rollout but did not complete native apps or production notification visuals.
- v4.8 completed support provider expansion and CRM automation with provider activation state `provider-ready`.
- `stoa_docs` remaining feature queue now recommends production notification and native delivery rollout.
- v4.9 should prioritize live WebSocket/API Gateway readiness, provider-backed email/push delivery, frontend/native notification handoff, native token registration, and live smoke evidence.
- Internal development mode means verification should stay focused on delivery behavior, preferences, provider configuration, fallback behavior, and rollout evidence rather than broad unrelated security/compliance sweeps.

### Pending Todos

- Execute Phase 166 production notification rollout contract and ownership planning.
- Add live WebSocket/API Gateway deployment readiness in Phase 167.
- Add provider-backed email digest and push delivery in Phase 168.
- Add frontend/native notification UX and token registration handoff in Phase 169.
- Close v4.9 with release-gate evidence and next milestone selection in Phase 170.

### Blockers/Concerns

- Live WebSocket deployment may require CDK/API Gateway ownership decisions beyond the local service behavior already implemented.
- Provider-backed email/push delivery requires approved provider credentials, templates, sender/domain configuration, and native token provider setup.
- Frontend/native visuals and token registration may require `/Users/zhdeng/stoa-frontend` or future native app workspaces.
- Real user notification sends should remain gated until provider configuration and rollout approval are explicit.

## Operator Next Steps

- Start Phase 166 using `.planning/phases/166-production-notification-rollout-contract-and-ownership/166-01-PLAN.md`.
