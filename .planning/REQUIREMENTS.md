# Requirements: v3.9 Payment Provider Integration MVP

**Milestone:** v3.9
**Status:** Active
**Created:** 2026-06-09

## Goal

Implement the first payment-provider integration for STOA subscriptions after the manual subscription operations MVP. This milestone focuses on product functionality: provider contract, checkout/subscription lifecycle, webhook-driven billing state, parent payment UX, and admin billing visibility.

## Requirements

### PAY-01 Payment Provider Contract And Billing Model

Implementers have a concrete provider and billing-domain contract before backend/frontend changes.

Acceptance criteria:

- Contract defines provider scope for Stripe-first subscription checkout with TWINT readiness where supported by provider configuration.
- Contract maps STOA tiers to provider prices/products and local subscription fields.
- Contract defines subscription lifecycle states: none, checkout_pending, active, past_due, canceled, payment_failed, manual_override, and provider_unknown.
- Contract defines idempotency, webhook event mapping, billing history shape, and manual admin override interaction.
- Contract defines internal-development safeguards: sandbox/test mode by default and no live charge path without approved provider credentials.

### PAY-02 Backend Checkout Subscription And Webhook APIs

Backend supports checkout session creation, subscription status reads, and webhook-driven billing updates.

Acceptance criteria:

- Parent users can create a provider checkout session for an allowed STOA plan.
- Backend stores billing customer/subscription references, provider mode, tier, status, timestamps, and last provider event metadata.
- Webhook handler validates provider event shape, deduplicates events, and updates local subscription state.
- Admin can inspect billing status, recent billing events, and manual override interactions.
- Focused tests cover checkout request shape, tier validation, webhook idempotency, lifecycle transitions, and manual override compatibility.

### UI-24 Parent Payment UX And Admin Billing Operations

Frontend exposes subscription checkout and billing status in parent/admin workflows.

Acceptance criteria:

- Parent subscription UI can start checkout, show current plan, show provider status, and handle return/cancel states.
- Parent UI distinguishes manual subscription, provider-managed subscription, and payment failure states.
- Admin billing UI shows provider status, billing event summary, and manual override context.
- UI uses real backend billing APIs and keeps demo/payment mock behavior clearly separated.
- Targeted browser verification confirms parent checkout entry and admin billing visibility.

### VERIFY-22 v3.9 Functional Release Gate And Billing Audit

v3.9 closes with functional evidence and updated `stoa_docs` gap tracking.

Acceptance criteria:

- Backend and frontend focused quality gates relevant to payment-provider integration pass.
- Gap audit marks Stripe/TWINT subscription payment integration active or closed and records residual live-charge/provider-credential scope if needed.
- Final audit lists remaining product expansions: adaptive learning memory/automatic assignment, production WebSocket infrastructure, push/native/email notifications, mobile/multilingual polish, support integrations, and rich content authoring.

## Future Requirements

- Live provider charging with approved production credentials and safe rollout plan.
- TWINT-specific production validation if not covered by Stripe configuration.
- Invoices, receipts, refunds, dunning, tax/VAT, and accounting export.
- Adaptive learning memory and automatic assignment.
- Production notification delivery and mobile/multilingual polish.

## Out of Scope

- Real production charges without approved provider credentials.
- Accounting/tax automation.
- Refund operations beyond provider status visibility.
- Broad security/compliance program beyond required payment correctness and provider webhook integrity.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PAY-01 | Phase 124 | Complete |
| PAY-02 | Phase 125 | Complete |
| UI-24 | Phase 126 | Planned |
| VERIFY-22 | Phase 127 | Planned |
