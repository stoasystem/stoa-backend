---
gsd_state_version: 1.0
milestone: v5.6
milestone_name: Core Product Operations Completion
status: Active planning
last_updated: "2026-07-02T00:00:00Z"
last_activity: 2026-07-02 — Corrected v5.6 scope from native app readiness to core paid/auth/usage product operations
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 5
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-02)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v5.6 Core Product Operations Completion.

## Current Position

Phase: 201 Core Product Operations Gap Audit And Contract
Plan: 201-01 Audit and define core product operations completion contract
Status: Active planning
Last activity: 2026-07-02 — User identified incomplete core details: paid functionality, backend usage records, login verification codes, email verification, and related operational flows.

## Accumulated Context

### Decisions

- The earlier v5.6 native app plan was premature because core product operations are not complete enough for real users.
- Native app buildout remains a future milestone after paid/auth/usage correctness.
- v5.6 now focuses on paid entitlements, usage ledger, login/email verification details, customer billing state, and admin support visibility.
- Internal development should prioritize functional completeness over broad security/compliance test expansion for this phase.

### Pending Todos

- Audit current auth, subscription, billing, quota, email verification, and admin visibility implementation.
- Define effective entitlement state and usage ledger event model.
- Define email verification and login-code product policy before implementation.
- Implement paid/auth/usage visibility for customers and admins.
- Keep native app, live APNS/FCM, app-store publication, and external support activation deferred.

### Blockers/Concerns

- Final live Stripe/TWINT activation still depends on external provider prerequisites.
- Login-code behavior must be reconciled with the current Cognito-backed password/session model.
- Usage ledger design must avoid breaking existing daily quota behavior while making usage auditable.

## Operator Next Steps

- Execute Phase 201 using `.planning/phases/201-core-product-operations-gap-audit-and-contract/201-01-PLAN.md`.
