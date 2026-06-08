---
gsd_state_version: 1.0
milestone: v3.3
milestone_name: Subscription Operations MVP
status: planning
last_updated: "2026-06-08T15:10:00+02:00"
last_activity: 2026-06-08
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 4
  completed_plans: 3
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** Phase 103 v3.3 functional release gate and billing readiness.

## Current Position

Phase: 103 v3.3 Functional Release Gate And Billing Readiness
Plan: —
Status: Ready for release-gate planning.
Last activity: 2026-06-08 - completed Phase 102 parent/admin subscription operations UI in frontend commit 4e11e51.

## Accumulated Context

### Decisions

- v3.0 closed account lifecycle, parent binding, OCR correction, daily quota hardening, and v2.9 production verification gaps from `stoa_docs`.
- v3.1 closed teacher rich text/formula replies and response-time SLA tracking.
- v3.2 shipped content moderation report actions, moderation cases, admin queue/detail/actions, deploy evidence, and production-safe smoke.
- v3.3 starts with manual subscription operations because `stoa_docs` defines manual paid onboarding before Stripe/TWINT: parents contact STOA, admins update `subscription_tier`, and transfers happen outside the product.
- v3.3 should build usable parent/admin subscription workflows now and defer actual payment-provider integration.

### Pending Todos

- Run lightweight functional release gate and update gap tracking in Phase 103.

### Blockers/Concerns

- Payment processing, invoices, refunds, tax handling, and Stripe/TWINT webhooks remain out of scope for v3.3.
- Existing `subscription_tier` behavior drives daily quota and is now also updated by the explicit admin subscription request apply action.
- Production verification can use read-only or safe-fixture paths; internal development should not over-index on broad compliance evidence.

## Operator Next Steps

- Execute Phase 103 release gate: record backend/frontend verification, commit SHAs, gap audit updates, and remaining Phase 2 product expansions.
