---
gsd_state_version: 1.0
milestone: v4.7
milestone_name: Payment Production Activation And Provider Automation
status: implementing
last_updated: "2026-06-12T14:10:00+02:00"
last_activity: 2026-06-12
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 5
  completed_plans: 4
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-12)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v4.7 payment production activation and provider automation.

## Current Position

Phase: 160 - v4.7 Payment Activation Release Gate
Plan: 160-01
Status: Ready to plan
Last activity: 2026-06-12 - Completed Phase 159 production webhook readiness evidence and persisted independent rollout controls for checkout and refunds.

## Accumulated Context

### Decisions

- v4.4 completed local live-payment readiness: Stripe/TWINT gates, checkout/webhook readiness, invoice/receipt metadata, non-mutating refund handoff, dunning projections, Swiss accounting export metadata, and rollout controls.
- v4.5 completed support evidence integration through the controlled internal queue path, leaving third-party support provider adapters as future scope.
- v4.6 completed curriculum authoring and analytics foundation with publish/rollback/archive safety and aggregate content-quality views.
- `stoa_docs` remaining feature queue now recommends payment production activation and provider automation.
- v4.7 should prioritize live Stripe/TWINT provider readiness checks, webhook endpoint registration readiness, direct refund execution, finance handoff, and explicit rollout controls.
- Real customer charging remains blocked until live credentials, provider readiness, finance acceptance, and explicit rollout approval are present.
- Phase 156 accepted the production payment activation contract. TWINT is in scope with CHF, Switzerland customer-location, 5,000 CHF maximum, recurring support, no manual capture, 180-day refund-window, merchant onboarding, and `twint_payments` capability requirements.
- Phase 157 added read-only provider readiness checks and kept refund mutation disabled by default.
- Phase 158 added direct refund execution behind `STRIPE_REFUNDS_ENABLED`, with idempotency replay, TWINT refund-window enforcement, provider failure no-mutation behavior, and finance export refund evidence.
- Phase 159 added persisted rollout controls. Checkout and refunds can be independently enabled, disabled, canary-marked, or rolled back; rollback blocks new live-changing operations while preserving billing history and finance exports.

### Pending Todos

- Close Phase 160 with payment activation release evidence and updated feature gap docs.

### Blockers/Concerns

- Approved Stripe live credentials, live webhook secret, and live price IDs are external dependencies.
- TWINT production validation may require Stripe account capability checks or merchant onboarding state.
- Real customer charging and direct refunds must remain disabled until explicit rollout approval.
- Keep safety checks focused on payment activation boundaries during this internal development milestone.

## Operator Next Steps

- Start Phase 160 release gate verification and update v4.7 final activation evidence.
