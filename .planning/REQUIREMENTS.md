# Requirements: v3.3 Subscription Operations MVP

**Milestone:** v3.3
**Status:** Active
**Created:** 2026-06-08

## Goal

Make the MVP manual subscription model usable for internal operations before Stripe/TWINT integration. Parents should see plans and submit upgrade/cancel intents; admins should process those requests and update tiers with an auditable operational trail. This is a product-building milestone, so verification focuses on functional flows and basic role gating.

## Requirements

### SUBOPS-01 Subscription Operations Contract And Entitlement Model

Implementers have a precise subscription request, entitlement, and admin workflow contract before backend changes.

Acceptance criteria:

- Contract defines plan tiers: Free, Standard, Premium.
- Contract defines parent-facing intents: request upgrade, request downgrade, request cancellation, and view current plan.
- Contract defines admin-facing lifecycle: `requested`, `in_review`, `approved`, `applied`, `rejected`, `cancelled`.
- Contract defines entitlement effects for daily AI quota, teacher support eligibility/priority, and weekly report access.
- Contract confirms whether existing user profile and DynamoDB single-table patterns support the MVP without new infrastructure.

### SUBOPS-02 Backend Subscription Request And Admin Tier APIs

Backend supports manual subscription operations.

Acceptance criteria:

- Parent users can read their current plan and submit bounded subscription requests.
- Admins can list/filter subscription requests by status, tier, parent, and date.
- Admins can approve/reject/apply/cancel a request and update the target user's `subscription_tier` when applying.
- Backend records request metadata, operator, reason/note, status history, and effective date.
- Focused tests cover parent request creation, admin list/detail/actions, tier apply behavior, invalid transitions, and non-admin rejection.

### UI-18 Parent Subscription Management And Admin Queue

Frontend exposes practical subscription operations for internal development.

Acceptance criteria:

- Parent UI shows current plan, tier limits, teacher support/weekly report benefits, and request actions.
- Parent UI supports upgrade/downgrade/cancel intent submission with status feedback.
- Admin UI includes subscription request queue, filters, detail, status actions, tier apply controls, and notes.
- UI handles empty, loading, error, submitted, rejected, applied, and cancelled states.
- Targeted browser verification confirms the parent/admin workflow is usable.

### VERIFY-16 v3.3 Functional Release Gate And Billing Readiness

v3.3 closes with lightweight functional evidence and updated Phase 2 gap tracking.

Acceptance criteria:

- Backend and frontend focused quality gates relevant to subscription operations pass.
- Deploy/build evidence and commit SHAs are recorded if code ships in this milestone.
- Gap audit marks manual subscription operations as active/closed and keeps Stripe/TWINT as future provider integration.
- Final audit lists remaining Phase 2 product expansions: payment-provider integration, multi-subject, student memory, AI teacher tools, realtime notifications, mobile/multilingual polish, and support integrations.

## Future Requirements

- Stripe/TWINT payment-provider integration.
- Broad multi-subject rollout for physics, German, and English.
- Student memory/personalization.
- AI teacher assistance tools such as summaries and exercise generation.
- WebSocket realtime notifications.
- Mobile responsive polish and full multilingual rollout.

## Out of Scope

- Charging cards, handling TWINT payments, invoices, refunds, taxes, or payment webhooks.
- Automated subscription provisioning from a payment provider.
- Broad Phase 2 curriculum expansion.
- Extensive security/compliance testing beyond functional role gating and data sanity checks.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SUBOPS-01 | Phase 100 | Complete |
| SUBOPS-02 | Phase 101 | Complete |
| UI-18 | Phase 102 | Planned |
| VERIFY-16 | Phase 103 | Planned |
