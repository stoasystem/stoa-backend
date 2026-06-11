# Phase 145 Context: Production Checkout, Webhook, And TWINT-Capable Stripe Gating

## Why This Phase Exists

Phase 144 defined the live payment rollout contract. Phase 145 turns that contract into backend primitives for production checkout and webhook readiness while keeping real customer charging behind explicit rollout gates.

This phase should close the core gap between the v3.9 local Stripe-first MVP and a controlled production payment rollout: Stripe SDK usage, live/test mode detection, checkout gating, webhook verification, idempotent event evidence, and TWINT-capable Swiss/CHF subscription handling.

## Current Foundation

- Parent checkout route: `POST /parents/me/subscription/checkout`.
- Stripe webhook route: `POST /billing/webhooks/stripe`.
- Parent billing route: `GET /parents/me/subscription/billing`.
- Admin billing routes: `GET /admin/subscriptions/billing` and `GET /admin/subscriptions/billing/{parent_id}`.
- Core service: `src/stoa/services/subscription_service.py`.
- Existing tests: `tests/test_subscription_operations.py`.

## Phase 144 Contract Inputs

Phase 145 should implement against:

- `.planning/phases/144-live-payment-rollout-contract-and-credential-readiness/144-LIVE-PAYMENT-ROLLOUT-CONTRACT.md`
- `PAYLIVE-02` in `.planning/REQUIREMENTS.md`
- Current v4.4 roadmap entries in `.planning/ROADMAP.md`

## Product Boundary

Build feature readiness and operator visibility. Do not enable real customer charging by default.

Live checkout must require all of:

- Production runtime mode.
- Valid live Stripe credential readiness.
- Valid live price mapping.
- Webhook secret readiness.
- Explicit live charges enablement.
- No blocking TWINT/account capability issue for TWINT-specific claims.

## Implementation Areas

- Stripe SDK dependency and wrapper/gateway.
- Billing readiness computation.
- Checkout session creation through Stripe where configured and permitted.
- TWINT-capable Stripe Checkout configuration for Swiss/CHF flows.
- Webhook raw-body verification and idempotent event processing.
- Provider lookup rows for session/customer/subscription/invoice/payment identifiers.
- Redacted admin readiness/status output.
- Focused backend tests for gating, mode mismatch, idempotency, bad signatures, and TWINT eligibility.
