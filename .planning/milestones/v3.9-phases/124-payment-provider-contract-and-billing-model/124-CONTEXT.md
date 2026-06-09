# Phase 124 Context: Payment Provider Contract And Billing Model

**Milestone:** v3.9 Payment Provider Integration MVP
**Requirement:** PAY-01
**Status:** Planned

## Why This Phase Exists

`stoa_docs` Phase 2 calls for Stripe subscription payment support with credit card/TWINT. v3.3 already shipped manual subscription operations, so the next product step is provider-backed checkout and billing state while preserving manual admin overrides.

## Product Scope

- Stripe-first subscription checkout contract.
- TWINT readiness through provider-supported payment method configuration.
- STOA plan-to-provider product/price mapping.
- Provider-managed subscription lifecycle and local billing state.
- Webhook event mapping, idempotency, and billing event history.
- Parent checkout/status UX and admin billing visibility implications.

## Completion Criteria

Phase 124 completes when the provider scope, billing state model, tier mapping, webhook lifecycle, idempotency rules, manual override interaction, and functional verification checklist are written and internally consistent.
