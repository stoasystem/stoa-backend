# Phase 125 Context: Backend Checkout Subscription And Webhook APIs

**Milestone:** v3.9 Payment Provider Integration MVP
**Requirement:** PAY-02
**Status:** Complete

## Phase Boundary

Add backend checkout session, billing status, webhook, and admin billing inspection APIs while preserving manual subscription operations.

## Implementation Decisions

- Extend `subscription_service` instead of creating a separate billing domain so manual subscription requests, provider checkout, and admin overrides share one product boundary.
- Keep Stripe as the provider vocabulary but generate deterministic sandbox/test checkout session records without introducing a hard Stripe SDK dependency or live network call.
- Store provider billing records under `SUBSCRIPTION_BILLING#{parent_id}` and billing events under the same partition.
- Deduplicate webhook events with `BILLING_PROVIDER_EVENT#stripe#{event_id}` marker records.
- Verify Stripe-style signatures manually with HMAC SHA-256 over the raw request body whenever `stripe_webhook_secret` is configured.
- In production, refuse unsigned webhooks.
- Preserve manual override behavior: admin-applied manual subscription requests set billing status to `manual_override`, and provider events do not downgrade a manual override.

## Existing Code Context

- v3.3 manual subscription operations live in `src/stoa/services/subscription_service.py`.
- Parent subscription endpoints live in `src/stoa/routers/parents.py`.
- Admin subscription request endpoints live in `src/stoa/routers/admin.py`.
- Tests for manual subscription behavior live in `tests/test_subscription_operations.py`.

## Deferred

- Real provider network calls and live production charge enablement.
- Tax/accounting automation, invoices, receipts, refunds, and dunning lifecycle.
