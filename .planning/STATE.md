---
gsd_state_version: 1.0
milestone: v5.11
milestone_name: Additional Usage Ledger Coverage
status: planning
last_updated: "2026-07-04T15:54:43.956Z"
last_activity: 2026-07-04
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-04)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v5.11 Additional Usage Ledger Coverage.

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-07-04 — Milestone v5.11 started

## Accumulated Context

### Decisions

- v5.6-v5.9 are complete as local backend milestones.
- v5.10 is frontend-first: email verification UX, parent account operations UI, admin account operations console, and production read-only readiness.
- Phase 222 completed the current-reality refresh and corrected stale v5.6-v5.9 planning assumptions.
- Phase 223 completed frontend email verification resend/confirm clients, register/login verification states, shared verification UI, and focused auth e2e coverage.
- Phase 224 completed the parent account operations API client/query, dashboard card, detail route, support-state UI, and focused parent account operations e2e coverage.
- Phase 225 completed the admin account operations API client/query, direct lookup route, subscription handoff links, support-state detail UI, billing evidence/events display, and focused admin account operations e2e coverage.
- Phase 226 completed the v5.10 readiness gate: frontend lint/build, 15 focused frontend e2e tests, 35 backend focused contract tests, release evidence, and production read-only smoke planning.
- Backend entitlement, usage ledger, email verification, and account operations primitives should not be reopened unless frontend integration exposes a concrete contract bug.
- Additional usage ledger action coverage remains future scope after question-submission ledger readiness.
- Passwordless/login-code remains deferred until Cognito custom-auth trigger and replay/rate-limit design exists.
- Native app buildout remains future work after web frontend account operations are usable.

### Pending Todos

- Start v5.11 Additional Usage Ledger Coverage when ready.

### Blockers/Concerns

- Frontend workspace is outside this backend repo; implementation work may need `/Users/zhdeng/stoa-frontend`.
- Production deploy/live smoke remains separate from local functional readiness.
- Final live Stripe/TWINT activation still depends on external provider prerequisites.

## Operator Next Steps

- Recommended next step: start v5.11 Additional Usage Ledger Coverage for chat, hints, teacher-help, and practice/generation actions that should appear in paid limits or support explanations.
