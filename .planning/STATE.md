---
gsd_state_version: 1.0
milestone: v5.17
milestone_name: External Provider Activation Smoke And Release Operations
status: Completed
last_updated: "2026-07-05T18:20:00.000Z"
last_activity: 2026-07-05 — Phase 261 completed v5.17 external provider release gate
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 5
  completed_plans: 5
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-05)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v5.17 External Provider Activation Smoke And Release Operations is complete; next planned focus is v5.18 Warehouse BI Observability And Product Analytics Activation.

## Current Position

Phase: 261 v5.17 External Provider Release Gate
Plan: Close with provider activation evidence, blocked-prerequisite table, rollback controls, and next milestone decision.
Status: Complete
Last activity: 2026-07-05 — v5.17 closed as external-provider-release-ops-ready with focused tests, provider activation evidence, rollback controls, and next milestone recommendation.

## Accumulated Context

### Decisions

- v5.12 is complete locally: backend-authorized curriculum editor and content migration tooling closed as `curriculum-buildout-ready`.
- v5.13 is complete locally: paid access, canonical parent billing APIs, Stripe webhook reconciliation hardening, paid-state frontend integration, and billing support evidence closed as `payment-production-ready-local`.
- v5.14 verification/login reliability was partial locally, but its focused frontend e2e blocker was closed during v5.16 evidence work.
- v5.15 is complete locally: usage-flow audit, practice teacher-help ledger coverage, idempotency hardening, quota reconciliation explanations, account-operations usage support fields, and admin core smoke closed as local stability readiness.
- v5.16 is complete locally: focused frontend e2e passed 24/24, supplemental journey e2e passed 11/11, backend product-readiness tests passed 121/121, frontend build/lint passed, and release evidence separates local implementation completeness from external provider blockers.
- The next three milestones should be v5.17 external provider activation smoke/release operations, v5.18 warehouse BI observability/product analytics activation, and v5.19 native mobile push/offline client implementation.
- v5.17 should not perform live customer-impacting provider mutation unless approved credentials, approved rollout flags, and approved safe fixture or rollout path exist.
- Phase 257 classified provider channels as live_ready, read_only_verifiable, safe_fixture_verifiable, locally_ready, or blocked, and documented current payment, Cognito/email, notification, support-provider, and production smoke surfaces in `257-PROVIDER-ACTIVATION-AUDIT.md`.
- Phase 258 added `GET /admin/external-activation/payment-auth-smoke`, combining Stripe/TWINT readiness with Cognito/email local-versus-live delivery readiness and deterministic blocked states.
- Phase 259 added `GET /admin/external-activation/notification-support-smoke`, combining notification WebSocket/email/push readiness with support internal queue, third-party provider, retry/sync, and CRM readiness.
- Phase 260 added `GET /admin/external-activation/production-readiness-smoke`, documenting deploy evidence requirements, read-only API/browser smoke paths, request-id policy, and production no-mutation gates.
- Phase 261 closed v5.17 as `external-provider-release-ops-ready`; live external provider activation remains blocked until approved credentials, rollout flags, safe fixtures, and operator-run production smoke evidence exist.

### Pending Todos

- Start v5.18 Warehouse BI Observability And Product Analytics Activation.

### Blockers/Concerns

- Live Stripe/TWINT smoke remains blocked unless approved production credentials, registered webhook endpoint, finance acceptance, and explicit rollout enablement are available.
- Live Cognito/email, notification, support-provider, BI/warehouse, APM, and native-provider checks remain external activation work unless credentials and approvals are supplied.
- Production checks must stay read-only unless an approved safe fixture or explicit external activation path is available.
- If provider credentials remain unavailable, v5.17 should close with refusal/readiness evidence and release runbooks rather than claiming live activation.

## Operator Next Steps

- v5.17 is complete. Next operator action is to start v5.18.
