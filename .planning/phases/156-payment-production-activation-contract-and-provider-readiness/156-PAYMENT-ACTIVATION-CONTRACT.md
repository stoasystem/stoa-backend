# Phase 156 Payment Production Activation Contract

**Milestone:** v4.7 Payment Production Activation And Provider Automation
**Requirement:** PAYACT-01
**Status:** Draft placeholder pending Phase 156 execution
**Created:** 2026-06-12

## Activation Goal

Move STOA from local payment readiness to controlled production activation for Stripe-backed subscriptions, including TWINT where provider capability allows.

## Required Activation Inputs

- Approved live Stripe API credential path.
- Approved live webhook signing secret path.
- Approved live Standard and Premium CHF recurring price IDs.
- Stripe account capability evidence for TWINT in the target flow.
- Production webhook endpoint registered with the required event set.
- Finance acceptance of invoice/refund/tax/dunning/reconciliation metadata.
- Explicit rollout approval for live checkout and direct refund execution.

## Provider Readiness Targets

Phase 157 should add admin-only readiness checks for:

- Credential mode and availability.
- Price mapping and currency consistency.
- TWINT capability and payment method availability.
- Webhook endpoint registration and required events.
- Refund capability.
- Accounting/tax metadata availability.

## Refund Activation Targets

Phase 158 should add controlled direct refund execution with:

- Admin authorization.
- Eligible billing state.
- Provider charge/payment reference.
- Operator reason.
- Idempotency key.
- Provider result persistence.
- Billing projection update.
- Audit evidence.

## Webhook And Rollout Targets

Phase 159 should add:

- Webhook registration readiness checks.
- Last-observed event evidence.
- Independent live checkout and refund rollout controls.
- Canary or blocked rollout state reporting.
- Rollback behavior that disables new live checkout without hiding existing billing status.

## Release Gate Targets

Phase 160 should record whether production activation is:

- `activated`
- `blocked`
- `deferred`
- `approved_canary_only`

The release gate must distinguish working provider automation from actual live customer charging.
