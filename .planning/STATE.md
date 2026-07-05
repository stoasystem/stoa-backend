---
gsd_state_version: 1.0
milestone: v5.16
milestone_name: End-To-End Product Readiness And Release Evidence
status: Active
last_updated: "2026-07-05T13:09:12.000Z"
last_activity: 2026-07-05 — Completed Phase 253 focused frontend e2e gate with 24 Playwright tests passing after test-locator stabilization
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 5
  completed_plans: 2
  percent: 40
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-05)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v5.16 End-To-End Product Readiness And Release Evidence.

## Current Position

Phase: 254 Backend Product Smoke Evidence Expansion
Plan: Verify core smoke, account operations, billing support evidence, usage reconciliation, and curriculum readiness outputs with focused backend tests.
Status: Active
Last activity: 2026-07-05 — Phase 253 closed the v5.14 focused frontend e2e blocker: final focused suite passed 24/24 after locator precision fixes.

## Accumulated Context

### Decisions

- v5.10 is complete: email verification UX, parent account operations UI, admin account operations console, focused frontend e2e, backend contract evidence, and production read-only smoke planning.
- v5.11 is complete: governed multi-action usage ledger taxonomy, chat/teacher-help/practice/assignment/generation instrumentation, reconciliation, account operations compatibility, 72 focused backend tests, and Ruff.
- v5.12 is complete locally: backend-authorized curriculum editor and content migration tooling closed as `curriculum-buildout-ready`.
- v5.13 is complete locally: paid access, canonical parent billing APIs, Stripe webhook reconciliation hardening, paid-state frontend integration, and billing support evidence closed as `payment-production-ready-local`.
- v5.14 is a partial local gate: backend verification/login reliability and frontend build passed, but focused frontend e2e remains blocked by platform usage-limit approval.
- v5.15 is complete locally: usage-flow audit, practice teacher-help ledger coverage, idempotency hardening, quota reconciliation explanations, account-operations usage support fields, and admin core smoke closed as local stability readiness.
- The next milestone should be a new stability/release-readiness milestone, not a renamed phase: v5.16 will verify end-to-end product journeys and release evidence across auth, billing, usage, curriculum, teacher help, and support views.
- Phase 252 is complete: release-critical backend and frontend surfaces are mapped to concrete files/tests; v5.12-v5.15 local evidence is reconciled; v5.14 focused frontend e2e remains a Phase 253 gate; live providers are classified as external blockers.
- Phase 253 is complete: focused frontend e2e for auth, account operations, subscription operations, billing/pricing, and admin curriculum passed 24/24; frontend commit `7e9e385` stabilized duplicate-text locators.
- External activation remains deferred until prerequisites unblock: live Stripe/TWINT, Cognito/email delivery, notification providers, external support provider, APNS/FCM, production warehouse/BI, APM, and rollout approvals.

### Pending Todos

- Phase 254: verify backend core smoke and release evidence surfaces are sufficient for support-safe triage.
- Phase 255: verify cross-surface parent, student, and admin journeys without demo fallback.
- Phase 256: close v5.16 with release evidence, blocker classification, and next milestone recommendation.

### Blockers/Concerns

- Frontend implementation work is in `/Users/zhdeng/stoa-frontend`, outside this backend repo's write root; running/fixing frontend e2e may require approval or a separate frontend-capable execution path.
- v5.14 focused frontend e2e remains blocked until external-write/dev-server execution permission is available for `/Users/zhdeng/stoa-frontend`.
- Live Stripe/TWINT smoke remains blocked unless approved production credentials, registered webhook endpoint, finance acceptance, and explicit rollout enablement are available.
- Live Cognito/email, notification, support-provider, BI/warehouse, APM, and native-provider checks remain external activation work unless credentials and approvals are supplied.
- Production checks must stay read-only unless an approved safe fixture or explicit external activation path is available.

## Operator Next Steps

- Run Phase 254 backend focused tests for core smoke, usage ledger, subscription/account operations, auth lifecycle, curriculum, questions, and conversations.
- Check whether core smoke and support outputs expose enough support-safe status metadata for release triage.
