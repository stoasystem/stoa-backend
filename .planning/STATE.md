---
gsd_state_version: 1.0
milestone: v4.4
milestone_name: Live Payment Provider Rollout
status: complete
last_updated: "2026-06-11T23:58:00+02:00"
last_activity: 2026-06-11
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 4
  completed_plans: 4
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-11)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v4.4 live payment provider rollout.

## Current Position

Phase: 147 - v4.4 Payment Release Gate, Rollout Controls, And Support Audit
Plan: 147-01
Status: Complete
Last activity: 2026-06-11 - Completed v4.4 payment release gate, rollback controls audit, remaining payment work audit, planning updates, and focused subscription verification.

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
- Phase 146 completed invoice/receipt metadata, non-mutating refund readiness, dunning projections, Swiss accounting handoff export, and TWINT lifecycle propagation.
- Phase 147 completed the v4.4 release gate and confirmed real customer charging remains deferred until external approval and live provider setup.
- Real customer charging remains gated on approved provider credentials and explicit production rollout approval.

### Pending Todos

- v4.5 support integration planning is ready as the recommended next milestone.

### Blockers/Concerns

- Live payment rollout requires approved production provider credentials before any real charging path is enabled.
- Stripe-backed TWINT rollout may still require provider account capability checks, CHF eligibility verification, or external merchant onboarding state before live enablement.
- Refund execution remains intentionally non-mutating; operators receive provider handoff metadata rather than direct refund mutation.
- Swiss tax/accounting fields are provider-managed when provider data is unavailable locally.
- Broad security/compliance testing should stay proportionate to touched payment paths during this internal development stage.

## Operator Next Steps

- Start v4.5 support evidence integrations and operations handoff when ready.
