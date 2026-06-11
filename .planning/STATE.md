---
gsd_state_version: 1.0
milestone: v4.4
milestone_name: Live Payment Provider Rollout
status: planning
last_updated: "2026-06-11T23:02:49+02:00"
last_activity: 2026-06-11
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 4
  completed_plans: 2
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-11)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v4.4 live payment provider rollout.

## Current Position

Phase: 146 - Billing Operations, Invoices, Refunds, Dunning, And Swiss Handoff
Plan: —
Status: Planning
Last activity: 2026-06-11 - Completed Phase 145 production checkout/webhook gating, Stripe dependency wiring, TWINT readiness metadata, and focused subscription verification.

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
- Phase 145 completed fail-closed readiness states, provider lookup rows, TWINT eligibility metadata, and redacted parent/admin billing readiness surfaces.
- Real customer charging remains gated on approved provider credentials and explicit production rollout approval.

### Pending Todos

- Phase 146 development docs are ready for billing operations, invoice, refund, dunning, and Swiss accounting handoff implementation.
- Phase 147 development docs are ready for payment release evidence, rollout controls, and milestone closeout.
- Next implementation step is Phase 146 code work.

### Blockers/Concerns

- Live payment rollout requires approved production provider credentials before any real charging path is enabled.
- Stripe-backed TWINT rollout may still require provider account capability checks, CHF eligibility verification, or external merchant onboarding state before live enablement.
- Refund, invoice, tax/accounting, and dunning scope should prefer provider-hosted primitives and metadata handoff before building broad accounting automation.
- Broad security/compliance testing should stay proportionate to touched payment paths during this internal development stage.

## Operator Next Steps

- Start Phase 146 implementation using `.planning/phases/146-billing-operations-invoices-refunds-dunning-and-swiss-handoff/146-01-PLAN.md`.
