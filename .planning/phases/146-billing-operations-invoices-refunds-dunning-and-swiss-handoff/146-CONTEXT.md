# Phase 146 Context: Billing Operations, Invoices, Refunds, Dunning, And Swiss Handoff

## Why This Phase Exists

Phase 145 prepares production checkout and webhook primitives. Phase 146 adds the billing operations surfaces needed after a payment exists: invoice/receipt metadata, refund readiness, dunning state projection, Swiss accounting handoff, and TWINT lifecycle handling through the same Stripe billing model.

The goal is first-pass operational readiness, not a full accounting platform.

## Current Foundation

- v3.9 added checkout, billing status, webhook lifecycle, parent payment UX, and admin billing visibility.
- Phase 144 defined refund, invoice, tax/accounting, and dunning as v4.4 rollout scope.
- Phase 145 should provide provider lookup rows, webhook event evidence, and payment method context needed by this phase.

## Implementation Areas

- Billing operations service or helpers layered on the existing subscription service.
- Parent/admin invoice and receipt metadata surfaces.
- Refund eligibility and operator handoff state.
- Dunning state projection for overdue, payment failed, retry, recovery, and escalation states.
- Swiss accounting export metadata for reconciliation.
- TWINT-originated payment context where Stripe exposes it.

## Product Boundary

Prefer provider-hosted artifacts and metadata handoff before custom finance automation.

No direct provider refund mutation should be enabled unless the phase defines explicit operator inputs, approval boundary, and rollback/error handling.
