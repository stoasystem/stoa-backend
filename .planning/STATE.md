---
gsd_state_version: 1.0
milestone: v5.6
milestone_name: Native Mobile App And Offline Push Readiness
status: Active planning
last_updated: "2026-06-16T08:26:01Z"
last_activity: 2026-06-16 — Started v5.6 native mobile app and offline push readiness planning
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 5
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-16)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v5.6 Native Mobile App And Offline Push Readiness.

## Current Position

Phase: 201 Native Mobile App And Offline Push Readiness Contract
Plan: 201-01 Define native mobile app offline and push readiness contract
Status: Active planning
Last activity: 2026-06-16 — Started v5.6 planning after v5.5 dispatch-ready completion.

## Accumulated Context

### Decisions

- `stoa_docs` still leaves several Phase 2 product expansion items: native apps, live notification delivery, rich curriculum editor implementation, production content import, live warehouse/BI, and external activation.
- Final live payment activation remains blocked by approved live Stripe credentials, registered production webhook endpoint, TWINT capability approval, finance acceptance, and explicit rollout enablement.
- External support provider/CRM writes remain blocked by provider selection, credentials, destination policy, templates, and rollout approval.
- Internal development should continue with buildable product functionality instead of waiting on external activation prerequisites.
- v5.6 will focus on native mobile app, offline read-through, push/deep links, and role workflows because it reuses v5.0 mobile readiness, v4.9 notification readiness, v5.3/v5.4 learning operations, and v5.5 teacher dispatch.

### Pending Todos

- Complete Phase 201 contract and ownership mapping.
- Decide whether implementation belongs in `/Users/zhdeng/stoa-frontend`, a native workspace, or backend contract/API updates.
- Identify backend API gaps for mobile push-token lifecycle, offline read-through metadata, and deep-link payloads.
- Keep v5.7 candidates visible: frontend rich curriculum editor implementation, production content import, live warehouse/BI deployment, or external activation if prerequisites unblock.

### Blockers/Concerns

- Live APNS/FCM provider credentials and app-store release are external prerequisites and should not block internal app/readiness work.
- Payment and external support activation remain externally gated.
- Fully unreviewed autonomous tutoring remains out of scope.

## Operator Next Steps

- Execute Phase 201 using `.planning/phases/201-native-mobile-app-and-offline-push-readiness-contract/201-01-PLAN.md`.
