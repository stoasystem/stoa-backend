---
gsd_state_version: 1.0
milestone: v4.4
milestone_name: Live Payment Provider Rollout
status: planning
last_updated: "2026-06-11T22:33:06+02:00"
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
Last activity: 2026-06-11 - Synced v4.3 to `origin/main`, rechecked `stoa_docs` remaining features, and selected v4.4 live payment provider rollout as the next feature-building milestone.

## Accumulated Context

### Decisions

- v3.3 completed manual subscription operations for parent requests and admin tier processing.
- v3.9 completed the local Stripe-first payment provider MVP: checkout session creation, provider billing status, signed webhook lifecycle, parent payment UX, and admin billing visibility.
- v4.0 through v4.3 completed adaptive learning, notification readiness, frontend mobile polish, and visual localization foundations.
- The next `stoa_docs` feature gap is live payment-provider rollout and operator-ready billing operations.
- v4.4 should prioritize feature construction: live credential readiness, production checkout/webhook verification, refund/invoice/tax/dunning readiness, and clear release evidence.
- Real customer charging remains gated on approved provider credentials and explicit production rollout approval.

### Pending Todos

- Execute Phase 144 by writing the live payment rollout contract and credential readiness plan.
- Plan and implement Phase 145 production checkout/webhook verification readiness.
- Plan and implement Phase 146 refund, invoice, tax, and dunning readiness.
- Close Phase 147 with payment release evidence and updated feature gap docs.

### Blockers/Concerns

- Live payment rollout requires approved production provider credentials before any real charging path is enabled.
- TWINT production validation may require provider account access or external provider setup.
- Refund, invoice, tax/accounting, and dunning scope should prefer provider-hosted primitives and metadata handoff before building broad accounting automation.
- Broad security/compliance testing should stay proportionate to touched payment paths during this internal development stage.

## Operator Next Steps

- Start Phase 144: inspect `src/stoa/services/subscription_service.py`, `src/stoa/routers/billing.py`, `src/stoa/routers/parents.py`, `src/stoa/routers/admin.py`, and `tests/test_subscription_operations.py`; then write the live payment rollout contract.
