---
gsd_state_version: 1.0
milestone: v4.3
milestone_name: Frontend Mobile And Visual Localization Rollout
status: planning
last_updated: "2026-06-11T13:29:57+02:00"
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
**Current focus:** v4.3 frontend mobile and visual localization rollout.

## Current Position

Phase: 140 - Frontend Workspace Contract And Mobile UAT Plan
Plan: 140-01
Status: Planning
Last activity: 2026-06-11 - Synced v4.2 to `origin/main`, rechecked `stoa_docs` remaining features, confirmed `/Users/zhdeng/stoa-frontend` exists, and selected v4.3 as the next feature-building milestone.

## Accumulated Context

### Decisions

- v3.6 completed local functional WebSocket realtime notifications and v4.2 completed backend notification delivery readiness.
- v3.7 added reviewed AI exercise drafts but intentionally did not assign them automatically.
- v3.8 added curriculum catalog, exercise bank, progress APIs, and student/parent/tutor curriculum UX.
- v3.9 completed the local payment provider integration MVP.
- v4.0 delivered durable memory snapshots, next-practice recommendations, reviewed assignment APIs, and student/tutor/parent route contracts.
- v4.1 delivered the backend mobile/multilingual foundation: `en`/`de` locale policy, durable locale preferences, additive route metadata, and deferred frontend/native ownership.
- v4.2 delivered backend-local production notification delivery readiness: notification preferences, delivery decisions, admin status, digest preview readiness, and push-ready metadata.
- The next `stoa_docs` feature gap is frontend mobile and visual localization. `/Users/zhdeng/stoa-frontend` exists and should be the implementation workspace for v4.3.
- v4.3 should prioritize visible feature construction: responsive core flows, real mobile browser verification, language preference UI, and selected English/German translated copy.

### Pending Todos

- Execute Phase 140 by auditing `/Users/zhdeng/stoa-frontend` and writing the mobile/localization execution contract.
- Plan and implement Phase 141 responsive student, parent, and tutor flow polish in the frontend workspace.
- Plan and implement Phase 142 visual localization and language preference UI.
- Close Phase 143 with frontend build/browser evidence and updated feature gap docs.

### Blockers/Concerns

- Current writable workspace is `/Users/zhdeng/stoa-backend`; implementation work for v4.3 should switch to or receive write approval for `/Users/zhdeng/stoa-frontend`.
- Backend canonical values must remain stable; frontend should localize display labels and copy.
- Native mobile apps remain out of scope unless a native workspace is selected.
- Broad security/compliance testing should not displace feature construction during this internal development stage.

## Operator Next Steps

- Start Phase 140 in `/Users/zhdeng/stoa-frontend`: map routes/components/API clients, define mobile UAT targets, and create the frontend execution contract.
