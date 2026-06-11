---
gsd_state_version: 1.0
milestone: v4.4
milestone_name: Live Payment Provider Rollout
status: planning
last_updated: "2026-06-11T23:02:49+02:00"
last_activity: 2026-06-11
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 4
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-11)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v4.4 live payment provider rollout.

## Current Position

Phase: 144 - Live Payment Rollout Contract And Credential Readiness
Plan: 144-01
Status: Planning
Last activity: 2026-06-11 - Refreshed the v4.4 roadmap so TWINT stays in scope for Stripe-backed rollout, Phase 145 owns checkout/webhook/gating, and Phase 146 owns the billing lifecycle surfaces.

## Accumulated Context

### Decisions

- v3.3 completed manual subscription operations for parent requests and admin tier processing.
- v3.9 completed the local Stripe-first payment provider MVP: checkout session creation, provider billing status, signed webhook lifecycle, parent payment UX, and admin billing visibility.
- v4.0 through v4.3 completed adaptive learning, notification readiness, frontend mobile polish, and visual localization foundations.
- The next `stoa_docs` feature gap is live payment-provider rollout and operator-ready billing operations.
- v4.4 should prioritize feature construction: live credential readiness, production checkout/webhook verification, Stripe-backed TWINT rollout, refund/invoice/tax/dunning readiness, and clear release evidence.
- Phase 145 owns production checkout/webhook rollout plus TWINT-capable Stripe provider primitives and livemode gating.
- Phase 146 owns refunds, invoices, dunning, Swiss tax/accounting handoff, and TWINT lifecycle behavior inside the same Stripe billing model.
- Real customer charging remains gated on approved provider credentials and explicit production rollout approval.

### Pending Todos

- Execute Phase 144 by writing the live payment rollout contract and credential readiness plan, including Stripe-backed TWINT gating.
- Plan and implement Phase 145 production checkout, webhook, and TWINT-capable Stripe gating.
- Plan and implement Phase 146 billing operations, invoice, refund, dunning, and Swiss accounting handoff readiness.
- Close Phase 147 with payment release evidence, rollout controls, and updated feature gap docs.

### Blockers/Concerns

- Live payment rollout requires approved production provider credentials before any real charging path is enabled.
- Stripe-backed TWINT rollout may still require provider account capability checks, CHF eligibility verification, or external merchant onboarding state before live enablement.
- Refund, invoice, tax/accounting, and dunning scope should prefer provider-hosted primitives and metadata handoff before building broad accounting automation.
- Broad security/compliance testing should stay proportionate to touched payment paths during this internal development stage.

## Operator Next Steps

- Start Phase 144: inspect `src/stoa/services/subscription_service.py`, `src/stoa/routers/billing.py`, `src/stoa/routers/parents.py`, `src/stoa/routers/admin.py`, and `tests/test_subscription_operations.py`; then write the live payment rollout contract.
