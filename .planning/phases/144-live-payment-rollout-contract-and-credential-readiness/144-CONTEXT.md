# Phase 144 Context: Live Payment Rollout Contract And Credential Readiness

## Why This Phase Exists

v3.9 completed the local Stripe-first payment provider MVP: checkout session creation, provider billing status, signed webhook lifecycle, parent payment UX, and admin billing visibility. `stoa_docs` still calls for real payment-provider rollout, TWINT validation, invoices/receipts/refunds, tax/accounting, and dunning. Phase 144 defines the live rollout contract before code changes or provider configuration are changed.

## Current Foundation

- `src/stoa/services/subscription_service.py` owns subscription and provider billing behavior.
- `src/stoa/routers/billing.py` exposes Stripe webhook handling.
- `src/stoa/routers/parents.py` exposes parent subscription and checkout behavior.
- `src/stoa/routers/admin.py` exposes admin subscription and billing visibility.
- `tests/test_subscription_operations.py` covers local subscription operations, checkout, webhook completion/idempotency, bad signature rejection, and manual overrides.

## Phase Boundary

This phase is planning/contract work. It should define what Phase 145 and Phase 146 implement and what requires approved provider credentials. It should not execute real customer charges.

## Questions To Resolve

- Where are approved Stripe live credentials stored and how are they injected into backend runtime?
- Which Stripe product/price IDs map to Free, Standard, and Premium?
- Is TWINT production validation in scope for implementation now, or only readiness documentation?
- What exact admin evidence should prove checkout/webhook readiness without exposing secrets?
- Which refund, invoice, tax/accounting, and dunning fields are already available from provider events?

## Constraints

- No real production charge without explicit approval.
- Keep provider secrets out of docs and logs.
- Prefer provider-hosted invoice/refund primitives before building custom billing automation.
- Keep security/compliance work focused on touched payment paths and rollout blockers.
