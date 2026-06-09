---
gsd_state_version: 1.0
milestone: v3.9
milestone_name: Payment Provider Integration MVP
status: planning
last_updated: "2026-06-09T16:45:39+02:00"
last_activity: 2026-06-09
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 4
  completed_plans: 1
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-09)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v3.9 payment provider integration MVP.

## Current Position

Phase: 124 Payment Provider Contract And Billing Model
Plan: 124-01
Status: Planned.
Last activity: 2026-06-09 - checked `stoa_docs` remaining functionality and selected payment-provider integration as the next product-build milestone after v3.8 curriculum rollout.

## Accumulated Context

### Decisions

- v3.3 completed manual subscription operations with parent plan/request UI and admin tier processing.
- `stoa_docs` Phase 2 explicitly calls for Stripe subscription payment with credit card/TWINT support.
- v3.8 completed local functional full curriculum rollout, leaving payment integration as the most direct remaining business-function gap.
- v3.9 should prioritize product construction: checkout/session APIs, webhook billing state, parent payment UX, and admin billing visibility.
- Internal development can use provider sandbox/test mode; live production charges still require approved provider credentials and rollout approval.

### Pending Todos

- Complete Phase 124 payment provider contract and billing model docs.
- Implement backend checkout/subscription/webhook APIs in Phase 125.
- Implement parent payment UX and admin billing operations in Phase 126.
- Run functional release gate and update gap tracking in Phase 127.

### Blockers/Concerns

- Real production charging is high impact and must remain gated behind explicit production credentials and rollout approval.
- Manual subscription overrides must continue to work while provider-managed subscriptions are introduced.
- Provider-specific TWINT behavior may require final validation after provider credentials/configuration are available.

## Operator Next Steps

- Execute Phase 124 and proceed to backend payment provider APIs.
