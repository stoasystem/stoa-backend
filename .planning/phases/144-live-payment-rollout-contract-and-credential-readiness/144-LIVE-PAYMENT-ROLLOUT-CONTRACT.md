# Phase 144 Live Payment Rollout Contract

**Status:** Draft placeholder pending code/config audit
**Updated:** 2026-06-11
**Requirement:** PAYLIVE-01

## Rollout Goal

Prepare STOA for controlled live subscription payments without accidentally charging customers during internal development.

## Provider Scope

Primary provider:

- Stripe remains the first live provider because v3.9 already implemented checkout, billing status, and webhook lifecycle around Stripe-compatible semantics.

TWINT:

- TWINT production validation remains a named v4.4 decision point.
- Phase 144 must confirm whether TWINT can be enabled through the existing provider account/product setup or whether it remains deferred provider-readiness scope.

## Required Configuration

Phase 144 should confirm exact variable names from code, then Phase 145 can implement missing readiness checks.

Expected configuration categories:

- Stripe API key or secret reference.
- Stripe webhook signing secret.
- Stripe Standard product/price ID.
- Stripe Premium product/price ID.
- Success and cancel return URLs.
- Provider mode: `test`, `live_ready`, or equivalent.
- Rollback switch or feature flag to disable live checkout creation.

## Safe Smoke Modes

Local/test-mode:

- Use test credentials or mocked provider responses.
- Exercise checkout creation, webhook verification, idempotency, and admin status.

Live configuration inspection:

- Confirm runtime configuration shape and provider mode without creating a real customer charge.
- Redact secrets and provider tokens from evidence.

Approved live smoke:

- Requires explicit approval and a named safe billing fixture or provider test customer.
- Must define cleanup/rollback before execution.

Default:

- No real customer charge.

## Implementation Targets

Phase 145 should inspect and update:

- `src/stoa/services/subscription_service.py`
- `src/stoa/routers/billing.py`
- `src/stoa/routers/parents.py`
- `src/stoa/routers/admin.py`
- `tests/test_subscription_operations.py`

Phase 146 should define or implement:

- Refund readiness status and operator inputs.
- Invoice/receipt metadata surfaces.
- Tax/accounting export metadata.
- Dunning states for failed/overdue payments.

## Evidence Boundaries

Release evidence may include provider mode, webhook event IDs, checkout session IDs, billing status values, and request IDs. It must not include provider secrets, raw payment method details, card data, or customer-sensitive provider payloads.
