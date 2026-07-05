---
gsd_state_version: 1.0
milestone: v5.17
milestone_name: External Provider Activation Smoke And Release Operations
status: Active
last_updated: "2026-07-05T14:00:00.000Z"
last_activity: 2026-07-05 — Planned the next three milestones from current reality and selected v5.17 external provider activation smoke/release operations as active
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 5
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-05)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v5.17 External Provider Activation Smoke And Release Operations.

## Current Position

Phase: 257 Provider Activation Reality Audit And Release Contract
Plan: Map live-provider readiness surfaces, settings, credentials, rollout flags, existing tests, and missing evidence.
Status: Active
Last activity: 2026-07-05 — v5.16 is complete locally; v5.17 starts by turning external provider blockers into approved readiness, smoke, refusal, rollback, and release-operation evidence.

## Accumulated Context

### Decisions

- v5.12 is complete locally: backend-authorized curriculum editor and content migration tooling closed as `curriculum-buildout-ready`.
- v5.13 is complete locally: paid access, canonical parent billing APIs, Stripe webhook reconciliation hardening, paid-state frontend integration, and billing support evidence closed as `payment-production-ready-local`.
- v5.14 verification/login reliability was partial locally, but its focused frontend e2e blocker was closed during v5.16 evidence work.
- v5.15 is complete locally: usage-flow audit, practice teacher-help ledger coverage, idempotency hardening, quota reconciliation explanations, account-operations usage support fields, and admin core smoke closed as local stability readiness.
- v5.16 is complete locally: focused frontend e2e passed 24/24, supplemental journey e2e passed 11/11, backend product-readiness tests passed 121/121, frontend build/lint passed, and release evidence separates local implementation completeness from external provider blockers.
- The next three milestones should be v5.17 external provider activation smoke/release operations, v5.18 warehouse BI observability/product analytics activation, and v5.19 native mobile push/offline client implementation.
- v5.17 should not perform live customer-impacting provider mutation unless approved credentials, approved rollout flags, and approved safe fixture or rollout path exist.

### Pending Todos

- Phase 257: audit provider readiness surfaces and write the v5.17 release contract.
- Phase 258: define and verify payment plus Cognito/email smoke operations.
- Phase 259: define and verify notification plus support provider smoke operations.
- Phase 260: consolidate production deploy readiness and read-only browser/API smoke.
- Phase 261: close v5.17 with activation evidence, blocked-prerequisite table, rollback controls, and v5.18 handoff.

### Blockers/Concerns

- Live Stripe/TWINT smoke remains blocked unless approved production credentials, registered webhook endpoint, finance acceptance, and explicit rollout enablement are available.
- Live Cognito/email, notification, support-provider, BI/warehouse, APM, and native-provider checks remain external activation work unless credentials and approvals are supplied.
- Production checks must stay read-only unless an approved safe fixture or explicit external activation path is available.
- If provider credentials remain unavailable, v5.17 should close with refusal/readiness evidence and release runbooks rather than claiming live activation.

## Operator Next Steps

- Start Phase 257 by mapping provider readiness settings/routes/tests/docs for payment, Cognito/email, notifications, support handoff, and production read-only smoke.
