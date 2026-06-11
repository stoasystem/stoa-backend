---
gsd_state_version: 1.0
milestone: v4.4
milestone_name: Live Payment Provider Rollout
status: planning
last_updated: "2026-06-11T23:02:49+02:00"
last_activity: 2026-06-11
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 4
  completed_plans: 1
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-11)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v4.4 live payment provider rollout.

## Current Position

Phase: 145 - Production Checkout, Webhook, And TWINT-Capable Stripe Gating
Plan: —
Status: Planning
Last activity: 2026-06-11 - Completed Phase 144 live payment rollout contract and verified focused subscription tests with the project virtualenv.

## Accumulated Context

### Decisions

- v3.3 completed manual subscription operations for parent requests and admin tier processing.
- v3.9 completed the local Stripe-first payment provider MVP: checkout session creation, provider billing status, signed webhook lifecycle, parent payment UX, and admin billing visibility.
- v4.0 through v4.3 completed adaptive learning, notification readiness, frontend mobile polish, and visual localization foundations.
- The next `stoa_docs` feature gap is live payment-provider rollout and operator-ready billing operations.
- v4.4 should prioritize feature construction: live credential readiness, production checkout/webhook verification, Stripe-backed TWINT rollout, refund/invoice/tax/dunning readiness, and clear release evidence.
- Phase 145 owns production checkout/webhook rollout plus TWINT-capable Stripe provider primitives and livemode gating.
- Phase 146 owns refunds, invoices, dunning, Swiss tax/accounting handoff, and TWINT lifecycle behavior inside the same Stripe billing model.
- Phase 144 completed the live payment rollout contract and confirmed no real customer charge was enabled.
- Real customer charging remains gated on approved provider credentials and explicit production rollout approval.

### Pending Todos

- Phase 145 development docs are ready for production checkout, webhook, and TWINT-capable Stripe gating implementation.
- Phase 146 development docs are ready for billing operations, invoice, refund, dunning, and Swiss accounting handoff implementation.
- Phase 147 development docs are ready for payment release evidence, rollout controls, and milestone closeout.
- Next implementation step is Phase 145 code work.

### Blockers/Concerns

- Live payment rollout requires approved production provider credentials before any real charging path is enabled.
- Stripe-backed TWINT rollout may still require provider account capability checks, CHF eligibility verification, or external merchant onboarding state before live enablement.
- Refund, invoice, tax/accounting, and dunning scope should prefer provider-hosted primitives and metadata handoff before building broad accounting automation.
- Broad security/compliance testing should stay proportionate to touched payment paths during this internal development stage.

## Operator Next Steps

- Start Phase 145 implementation using `.planning/phases/145-production-checkout-webhook-and-twint-capable-stripe-gating/145-01-PLAN.md`.
