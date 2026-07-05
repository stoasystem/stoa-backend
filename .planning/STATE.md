---
gsd_state_version: 1.0
milestone: v5.19
milestone_name: Native Mobile Push And Offline Client Implementation
status: planning
last_updated: "2026-07-06T00:45:00.000Z"
last_activity: 2026-07-06
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 4
  completed_plans: 4
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-06)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v5.19 Native Mobile Push And Offline Client Implementation.

## Current Position

Phase: 271 v5.19 Native Mobile Release Gate
Plan: —
Status: Phase 271 active; next five milestone queue documented
Last activity: 2026-07-06 — Phase 270 completed; push/deep-link/offline contracts added

## Accumulated Context

### Decisions

- v5.12 is complete locally: backend-authorized curriculum editor and content migration tooling closed as `curriculum-buildout-ready`.
- v5.13 is complete locally: paid access, canonical parent billing APIs, Stripe webhook reconciliation hardening, paid-state frontend integration, and billing support evidence closed as `payment-production-ready-local`.
- v5.14 verification/login reliability was partial locally, but its focused frontend e2e blocker was closed during v5.16 evidence work.
- v5.15 is complete locally: usage-flow audit, practice teacher-help ledger coverage, idempotency hardening, quota reconciliation explanations, account-operations usage support fields, and admin core smoke closed as local stability readiness.
- v5.16 is complete locally: focused frontend e2e passed 24/24, supplemental journey e2e passed 11/11, backend product-readiness tests passed 121/121, frontend build/lint passed, and release evidence separates local implementation completeness from external provider blockers.
- The downstream planning queue assumes v5.19 completes and then runs v5.20 native build/device QA, v5.21 AI teaching operations, v5.22 support CRM/customer lifecycle automation, v5.23 enterprise stability/compliance/DR hardening, and v5.24 limited production pilot/launch readiness.
- v5.17 should not perform live customer-impacting provider mutation unless approved credentials, approved rollout flags, and approved safe fixture or rollout path exist.
- Phase 257 classified provider channels as live_ready, read_only_verifiable, safe_fixture_verifiable, locally_ready, or blocked, and documented current payment, Cognito/email, notification, support-provider, and production smoke surfaces in `257-PROVIDER-ACTIVATION-AUDIT.md`.
- Phase 258 added `GET /admin/external-activation/payment-auth-smoke`, combining Stripe/TWINT readiness with Cognito/email local-versus-live delivery readiness and deterministic blocked states.
- Phase 259 added `GET /admin/external-activation/notification-support-smoke`, combining notification WebSocket/email/push readiness with support internal queue, third-party provider, retry/sync, and CRM readiness.
- Phase 260 added `GET /admin/external-activation/production-readiness-smoke`, documenting deploy evidence requirements, read-only API/browser smoke paths, request-id policy, and production no-mutation gates.
- Phase 261 closed v5.17 as `external-provider-release-ops-ready`; live external provider activation remains blocked until approved credentials, rollout flags, safe fixtures, and operator-run production smoke evidence exist.
- Phase 262 mapped BI source surfaces and established the v5.18 taxonomy/privacy contract.
- Phase 263 added admin BI warehouse readiness/export contracts with stable idempotency, bounded aggregate rows, and default live warehouse blockers.
- Phase 264 added the aggregate admin BI dashboard across usage, billing/provider readiness, curriculum, notifications, support, release smoke, and warehouse state.
- Phase 265 added low-cardinality admin BI alert routing and runbook metadata with live APM alerting blocked by default until configured.
- Phase 266 closed v5.18 as `bi-observability-ready-local`; focused BI/source tests passed 31/31, wider BI-composed backend tests passed 83/83, and Ruff passed.
- Phase 267 scaffolded the native Expo mobile workspace under `mobile/`, added route/config/app-shell contracts, documented stack/environment policy, and passed `pytest tests/mobile/test_mobile_stack_contract.py` 4/4.
- Phase 268 added Amplify/Cognito auth wrappers, metadata-only SecureStore policy, authenticated API client, support-safe account-state mapper, sign-out cleanup hooks, and passed focused mobile auth/stack tests 10/10.
- Phase 269 added student and parent mobile adapters, journey state contracts, online/offline screen boundaries, English/Chinese labels, journey docs, and passed focused mobile journey/auth/stack tests 16/16.
- Phase 270 added Expo push contracts, backend notification token register/revoke adapters, authenticated notification deep-link validation, read-through cache policy, sensitive cache guards, online-only mutation guards, and passed focused mobile push/offline/journey/auth/stack tests 22/22.
- Current v5.19 work is Phase 271 native mobile release gate.
- Current provider/support reality includes backend support handoff/CRM gates and notification push-token contracts, but customer lifecycle messaging remains fragmented; this is routed to v5.22.
- Current AI reality includes reviewed/bounded AI teacher and assignment tooling, but quality/cost/safety/autonomy operations remain a separate milestone; this is routed to v5.21.

### Pending Todos

- Execute v5.19 Phase 271 release gate.
- Keep v5.20-v5.24 as the ordered milestone queue unless implementation reality changes during v5.19.

### Blockers/Concerns

- Live Stripe/TWINT smoke remains blocked unless approved production credentials, registered webhook endpoint, finance acceptance, and explicit rollout enablement are available.
- Live Cognito/email, notification, support-provider, BI/warehouse, APM, and native-provider checks remain external activation work unless credentials and approvals are supplied.
- Production checks must stay read-only unless an approved safe fixture or explicit external activation path is available.
- Live BI warehouse/APM activation should close with local/read-only/blocked evidence unless approved credentials and deployment targets are available.
- Native build, app-store, external support/CRM writes, and broader AI autonomy remain gated by credentials, provider approvals, and release evidence.

## Operator Next Steps

- Continue v5.19 with Phase 271 native mobile release gate.
- Re-check the v5.20-v5.24 queue at the v5.19 release gate.
