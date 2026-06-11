# Phase 145 Checkout, Webhook, And TWINT Gating Spec

**Milestone:** v4.4 Live Payment Provider Rollout
**Requirement:** PAYLIVE-02
**Status:** Planned

## Readiness States

Phase 145 should expose a redacted payment readiness state:

- `not_configured`: required Stripe configuration is missing or inconsistent.
- `test`: test-mode configuration is usable for local/internal verification.
- `live_ready_but_blocked`: live-mode configuration is internally consistent, but `STRIPE_LIVE_CHARGES_ENABLED` blocks live checkout.
- `live_enabled`: live-mode configuration and explicit rollout gate allow checkout creation.

Readiness output must include blocking reasons in operator-readable terms without exposing secrets.

## Checkout Rules

- Free tier never creates Stripe Checkout.
- Standard and Premium require configured price IDs for the active provider mode.
- Live price IDs are treated as opaque values and should be validated through Stripe object reads where practical.
- Live checkout refuses unless all rollout gates pass.
- Test-mode checkout remains available for local/test verification.
- Checkout metadata should include parent/user identifiers needed for webhook resolution.

## TWINT Rules

TWINT is in scope as a Stripe Checkout payment method.

- TWINT eligibility requires Swiss/CHF subscription context.
- TWINT remains behind the same checkout gates as other live payment methods.
- Stripe account capability or payment-method configuration evidence must be recorded before claiming TWINT readiness.
- Billing projections should store payment method context when Stripe provides it.
- No separate TWINT provider branch should be added unless Stripe capability validation proves it necessary.

## Webhook Rules

Required event support:

- `checkout.session.completed`
- `checkout.session.expired`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.paid`
- `invoice.payment_failed`

Processing requirements:

- Verify raw webhook body through Stripe SDK semantics.
- Deduplicate by Stripe event ID before mutating billing state.
- Persist `livemode`, event type, created timestamp, processing result, idempotency status, and request/correlation ID where available.
- Resolve parent/customer relationships through provider lookup rows.
- Treat invoice/subscription truth as the live entitlement basis.
- Keep manual override behavior visible and compatible.

## Admin Visibility

Admin billing readiness should show:

- Provider readiness state.
- Live checkout gate state.
- Webhook configuration state.
- Price mapping state.
- TWINT eligibility or blocking reason.
- Last relevant webhook processing result when available.

It must not show API keys, webhook secrets, raw provider payloads, payment method details, or customer card data.

## Test Matrix

- Missing configuration blocks paid checkout.
- Test configuration allows test-mode checkout behavior.
- Live configuration with live charges disabled blocks live checkout.
- Live/test price or key mismatch is rejected.
- Bad webhook signature is rejected.
- Duplicate webhook event is idempotent.
- TWINT eligibility is surfaced only for supported Swiss/CHF flows.
- Admin readiness output is redacted.
