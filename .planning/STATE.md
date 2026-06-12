---
gsd_state_version: 1.0
milestone: v4.7
milestone_name: Payment Production Activation And Provider Automation
status: implementing
last_updated: "2026-06-12T13:15:00+02:00"
last_activity: 2026-06-12
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 5
  completed_plans: 2
  percent: 40
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-12)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v4.7 payment production activation and provider automation.

## Current Position

Phase: 158 - Direct Refund Execution And Finance Handoff
Plan: 158-01
Status: Ready to plan
Last activity: 2026-06-12 - Completed Phase 157 admin-only live provider readiness API checks with redacted Stripe/TWINT credential, price, webhook, refund, finance, and rollout evidence.

## Accumulated Context

### Decisions

- v4.4 completed local live-payment readiness: Stripe/TWINT gates, checkout/webhook readiness, invoice/receipt metadata, non-mutating refund handoff, dunning projections, Swiss accounting export metadata, and rollout controls.
- v4.5 completed support evidence integration through the controlled internal queue path, leaving third-party support provider adapters as future scope.
- v4.6 completed curriculum authoring and analytics foundation with publish/rollback/archive safety and aggregate content-quality views.
- `stoa_docs` remaining feature queue now recommends payment production activation and provider automation.
- v4.7 should prioritize live Stripe/TWINT provider readiness checks, webhook endpoint registration readiness, direct refund execution, finance handoff, and explicit rollout controls.
- Real customer charging remains blocked until live credentials, provider readiness, finance acceptance, and explicit rollout approval are present.
- Phase 156 accepted the production payment activation contract. TWINT is in scope with CHF, Switzerland customer-location, 5,000 CHF maximum, recurring support, no manual capture, 180-day refund-window, merchant onboarding, and `twint_payments` capability requirements.
- Phase 157 added read-only provider readiness checks. Direct refund mutation remains disabled and must be implemented under explicit controls in Phase 158.

### Pending Todos

- Plan and implement Phase 158 direct refund execution and finance handoff.
- Plan and implement Phase 159 production webhook registration and rollout controls.
- Close Phase 160 with payment activation release evidence and updated feature gap docs.

### Blockers/Concerns

- Approved Stripe live credentials, live webhook secret, and live price IDs are external dependencies.
- TWINT production validation may require Stripe account capability checks or merchant onboarding state.
- Real customer charging and direct refunds must remain disabled until explicit rollout approval.
- Keep safety checks focused on payment activation boundaries during this internal development milestone.

## Operator Next Steps

- Start Phase 158 by planning controlled direct refund execution and finance handoff from the Phase 156 contract and Phase 157 readiness endpoint.
