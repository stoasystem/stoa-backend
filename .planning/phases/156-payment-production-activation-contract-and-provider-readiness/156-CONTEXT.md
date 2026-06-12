# Phase 156 Context: Payment Production Activation Contract And Provider Readiness

## Why This Phase Exists

v4.4 made payment rollout locally ready but stopped short of production activation because live Stripe credentials, TWINT account capability, webhook endpoint registration, direct refund execution, and finance acceptance were external blockers. v4.7 starts by converting those blockers into a concrete activation contract and implementation handoff.

## Current Foundation

- v3.9 added local Stripe-first checkout, billing status, webhook lifecycle, parent payment UX, and admin billing visibility.
- v4.4 added Stripe/TWINT readiness gates, invoice/receipt metadata, non-mutating refund handoff, dunning projections, Swiss accounting export metadata, and release-gate evidence.
- `stoa_docs` remaining feature queue now recommends payment production activation and provider automation.

## Phase Boundary

This phase is planning/contract work. It should define what Phase 157 through Phase 160 implement and what remains externally blocked. It should not execute real customer charges.

## Key Files To Inspect

- `src/stoa/config.py`
- `src/stoa/services/subscription_service.py`
- `src/stoa/routers/billing.py`
- `src/stoa/routers/parents.py`
- `src/stoa/routers/admin.py`
- `tests/test_subscription_operations.py`
- `.planning/phases/144-live-payment-rollout-contract-and-credential-readiness/`
- `.planning/phases/145-production-checkout-webhook-and-twint-capable-stripe-gating/`
- `.planning/phases/146-billing-operations-invoices-refunds-dunning-and-swiss-handoff/`
- `.planning/phases/147-v4-4-payment-release-gate-rollout-controls-and-support-audit/`

## Constraints

- Real customer charging requires explicit approval and provider readiness.
- Secrets must stay out of docs and logs.
- Direct refund execution must be idempotent and operator-driven.
- Finance handoff should prefer provider-hosted artifacts and metadata before broad accounting automation.
- Security/compliance checks should stay focused on payment activation boundaries.
