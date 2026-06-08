---
gsd_state_version: 1.0
milestone: v3.3
milestone_name: Subscription Operations MVP
status: complete
last_updated: "2026-06-08T15:17:00+02:00"
last_activity: 2026-06-08
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 4
  completed_plans: 4
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v3.3 complete; ready to choose the next milestone.

## Current Position

Phase: 103 v3.3 Functional Release Gate And Billing Readiness
Plan: 103-01
Status: Complete.
Last activity: 2026-06-08 - completed v3.3 release gate with backend commit 58abccf and frontend commit 4e11e51.

## Accumulated Context

### Decisions

- v3.0 closed account lifecycle, parent binding, OCR correction, daily quota hardening, and v2.9 production verification gaps from `stoa_docs`.
- v3.1 closed teacher rich text/formula replies and response-time SLA tracking.
- v3.2 shipped content moderation report actions, moderation cases, admin queue/detail/actions, deploy evidence, and production-safe smoke.
- v3.3 completed manual subscription operations because `stoa_docs` defines manual paid onboarding before Stripe/TWINT: parents contact STOA, admins update `subscription_tier`, and transfers happen outside the product.
- v3.3 shipped usable parent/admin subscription workflows and deferred actual payment-provider integration.

### Pending Todos

- Choose the next milestone. Candidate: Stripe/TWINT provider integration or another Phase 2 expansion from the gap audit.

### Blockers/Concerns

- Payment processing, invoices, refunds, tax handling, and Stripe/TWINT webhooks remain future scope after v3.3.
- Existing `subscription_tier` behavior drives daily quota and is now also updated by the explicit admin subscription request apply action.
- Production verification can use read-only or safe-fixture paths; internal development should not over-index on broad compliance evidence.

## Operator Next Steps

- Review v3.3 release gate and select the next product expansion milestone.
