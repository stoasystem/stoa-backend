---
gsd_state_version: 1.0
milestone: v4.5
milestone_name: Support Evidence Integrations And Operations Handoff
status: planning
last_updated: "2026-06-12T00:01:13+02:00"
last_activity: 2026-06-12
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 4
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-12)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v4.5 support evidence integrations and operations handoff.

## Current Position

Phase: 148 - Support Destination Contract And Credential Readiness
Plan: —
Status: Ready for Phase 148 planning
Last activity: 2026-06-12 - v4.5 research, requirements, and roadmap initialized

## Accumulated Context

### Decisions

- v3.3 completed manual subscription operations for parent requests and admin tier processing.
- v3.9 completed the local Stripe-first payment provider MVP: checkout session creation, provider billing status, signed webhook lifecycle, parent payment UX, and admin billing visibility.
- v4.0 through v4.3 completed adaptive learning, notification readiness, frontend mobile polish, and visual localization foundations.
- The next active feature gap is support evidence integrations and operations handoff.
- v4.5 should prioritize a controlled support destination contract, credential readiness, one approved delivery path, and operator-visible handoff status.
- Phase 145 owns production checkout/webhook rollout plus TWINT-capable Stripe provider primitives and livemode gating.
- Phase 146 owns refunds, invoices, dunning, Swiss tax/accounting handoff, and TWINT lifecycle behavior inside the same Stripe billing model.
- Phase 144 completed the live payment rollout contract and confirmed no real customer charge was enabled.
- Phase 145 completed fail-closed readiness states, provider lookup rows, TWINT eligibility metadata, and redacted parent/admin billing readiness surfaces.
- Phase 146 completed invoice/receipt metadata, non-mutating refund readiness, dunning projections, Swiss accounting handoff export, and TWINT lifecycle propagation.
- Phase 147 completed the v4.4 release gate and confirmed real customer charging remains deferred until external approval and live provider setup.
- Real customer charging remains gated on approved provider credentials and explicit production rollout approval.
- v4.5 research confirmed existing support handoff packages already preserve metadata-only manual preview/copy/download behavior and refuse unapproved external writes.
- Phase 148 owns the support destination contract, credential/config readiness, payload rules, attachment policy, and refusal behavior before delivery implementation.

### Pending Todos

- Plan Phase 148: support destination contract and credential readiness.

### Blockers/Concerns

- Live payment rollout requires approved production provider credentials before any real charging path is enabled.
- Stripe-backed TWINT rollout may still require provider account capability checks, CHF eligibility verification, or external merchant onboarding state before live enablement.
- Refund execution remains intentionally non-mutating; operators receive provider handoff metadata rather than direct refund mutation.
- Swiss tax/accounting fields are provider-managed when provider data is unavailable locally.
- Broad security/compliance testing should stay proportionate to touched payment paths during this internal development stage.
- Support destination delivery must remain fail-closed until an approved destination mode, credential path, payload mapping, idempotency, and audit/status lifecycle are defined.

## Operator Next Steps

- Plan Phase 148.
