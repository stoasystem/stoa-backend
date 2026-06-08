---
gsd_state_version: 1.0
milestone: v3.3
milestone_name: Subscription Operations MVP
status: planning
last_updated: "2026-06-08T14:28:12+02:00"
last_activity: 2026-06-08
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 4
  completed_plans: 1
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** Phase 101 backend subscription request and admin tier APIs.

## Current Position

Phase: 101 Backend Subscription Request And Admin Tier APIs
Plan: —
Status: Ready for discussion/planning.
Last activity: 2026-06-08 - completed Phase 100 subscription operations contract and entitlement model.

## Accumulated Context

### Decisions

- v3.0 closed account lifecycle, parent binding, OCR correction, daily quota hardening, and v2.9 production verification gaps from `stoa_docs`.
- v3.1 closed teacher rich text/formula replies and response-time SLA tracking.
- v3.2 shipped content moderation report actions, moderation cases, admin queue/detail/actions, deploy evidence, and production-safe smoke.
- v3.3 starts with manual subscription operations because `stoa_docs` defines manual paid onboarding before Stripe/TWINT: parents contact STOA, admins update `subscription_tier`, and transfers happen outside the product.
- v3.3 should build usable parent/admin subscription workflows now and defer actual payment-provider integration.

### Pending Todos

- Implement backend parent subscription request and admin processing APIs in Phase 101.
- Implement parent plan/request UI and admin subscription queue UI in Phase 102.
- Run lightweight functional release gate and update gap tracking in Phase 103.

### Blockers/Concerns

- Payment processing, invoices, refunds, tax handling, and Stripe/TWINT webhooks remain out of scope for v3.3.
- Existing `subscription_tier` behavior already drives daily quota; Phase 101 should preserve that behavior while adding manual subscription request/tier operations.
- Production verification can use read-only or safe-fixture paths; internal development should not over-index on broad compliance evidence.

## Operator Next Steps

- Discuss and plan Phase 101 backend subscription operations APIs.
