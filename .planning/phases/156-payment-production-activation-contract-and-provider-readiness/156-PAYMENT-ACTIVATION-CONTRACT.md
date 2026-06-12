# Phase 156 Payment Production Activation Contract

**Milestone:** v4.7 Payment Production Activation And Provider Automation
**Requirement:** PAYACT-01
**Status:** Accepted
**Created:** 2026-06-12

## Activation Goal

Move STOA from local payment readiness to controlled production activation for Stripe-backed subscriptions, including TWINT where provider capability allows. This contract authorizes provider-readiness automation and implementation work only. It does not authorize unapproved real customer charging or direct refund mutation.

## Non-Negotiable Activation Boundary

- Live checkout and direct refund execution must remain fail-closed until explicit rollout approval is present.
- Readiness checks may inspect live provider state when approved credentials are configured, but must not create PaymentIntents, Checkout Sessions, refunds, subscriptions, or charges as part of readiness.
- Operator responses must redact API keys, webhook secrets, raw provider payloads, card details, customer payment details, and any provider values not needed for action.
- Every live-changing operation needs a separate gate, audit trail, and rollback path.

## Required Activation Inputs

- Approved live Stripe API credential injected through the production secret path used by `Settings.stripe_api_key`.
- Approved live webhook signing secret injected through the production secret path used by `Settings.stripe_webhook_secret`.
- Approved live Standard and Premium recurring price IDs injected through `Settings.stripe_standard_price_id` and `Settings.stripe_premium_price_id`.
- Explicit business approval for live checkout through `Settings.stripe_live_charges_enabled` or the v4.7 rollout control that supersedes it.
- TWINT enablement through `Settings.stripe_twint_enabled`, `Settings.stripe_twint_capability_confirmed`, and provider capability evidence for `twint_payments`.
- Production webhook endpoint registered with the required event set and a signing secret owned by backend operations.
- Finance acceptance of invoice, receipt, refund, tax, dunning, and reconciliation metadata.
- Explicit rollout approval for live checkout and direct refund execution as independent controls.

## Credential And Mode Contract

Phase 157 must expose an admin-only readiness response with these mode states:

- `not_configured`: required credentials or price IDs are missing.
- `test`: configured API key is test-mode and cannot activate production charging.
- `live_ready_but_blocked`: live-looking credentials and required config are present, but live checkout is still gated off.
- `live_enabled`: live-looking credentials are present and explicit checkout rollout approval is active.
- `provider_api_failed`: configured credentials could not be validated against the provider, and activation must remain blocked.

The readiness response must include only redacted credential evidence:

- `apiKeyMode`: `missing`, `test`, `live`, or `unknown`.
- `webhookSecretConfigured`: boolean only.
- `standardPriceConfigured` and `premiumPriceConfigured`: boolean only plus redacted price ID suffixes when useful.
- `blockers`: actionable strings safe for admin display.
- `warnings`: non-blocking setup concerns safe for admin display.

## Price Mapping And TWINT Contract

Standard and Premium subscription checkout must remain mapped to live recurring Stripe Price IDs before activation. The expected production subscription properties are:

- Currency: CHF.
- Billing: recurring subscription price.
- Tiers: Standard and Premium only for v4.7 activation.
- Price mapping must be verified before checkout activation; missing or non-recurring live prices block activation.

TWINT is in scope for v4.7 and must be included in payment readiness. Official provider constraints to enforce or surface:

- Customer location: Switzerland.
- Presentment currency: CHF.
- Maximum amount: 5,000 CHF.
- Recurring payments: supported.
- Manual capture: not supported; checkout must not require manual capture for TWINT.
- Refunds: full and partial refunds supported up to 180 days after payment completion.
- Provider capability: Stripe account `capabilities.twint_payments` must be checked where provider API access is available and reported as `active`, `pending`, `inactive`, or `unknown`.
- Merchant onboarding: production TWINT readiness depends on a functional public website, visible legal/contact information, and CHF checkout pricing.

TWINT readiness states:

- `disabled`: STOA TWINT feature flag is off.
- `capability_unconfirmed`: local confirmation is missing.
- `pending`: provider capability exists but is not active.
- `inactive`: provider capability is inactive.
- `eligible`: local flags, provider capability, CHF pricing, and live rollout state are compatible.
- `unknown`: provider capability could not be read, so activation must remain blocked unless an operator records approved external evidence.

## Provider Readiness Response Contract

Phase 157 should return a structured admin-only payload covering:

- `state`: one of the credential and mode states above.
- `checkoutAllowed`: whether new live checkout can be created.
- `refundsAllowed`: whether direct refund mutation can be attempted.
- `providerMode`: `missing`, `test`, `live`, or `unknown`.
- `credentials`: redacted credential configuration evidence.
- `prices`: Standard/Premium configured state, live-mode provider lookup state, recurring flag, currency, and safe blockers.
- `twint`: local flags, provider capability status, onboarding constraints, amount/currency constraints, and safe blockers.
- `webhook`: endpoint URL mode, secret availability, required event set, registration status when known, and last observed event timestamp when known.
- `finance`: invoice/refund/tax/dunning/reconciliation metadata availability.
- `rollout`: checkout gate, refund gate, canary state, and rollback status.

Readiness checks must fail closed when provider API calls fail or return ambiguous state.

## Webhook Registration Contract

Production webhook readiness must verify:

- Endpoint is publicly reachable through HTTPS.
- Endpoint routes to the Stripe webhook handler and uses the production signing secret.
- Handler verifies Stripe signatures by default and only allows unsigned test webhooks when explicitly configured for tests.
- Handler returns a 2xx response quickly after signature verification and event acceptance; expensive downstream processing must not delay acknowledgement.
- Required event subscriptions include the event families already handled by STOA subscription billing: checkout session completion, subscription lifecycle, invoice lifecycle, charge/refund lifecycle, customer lifecycle, and provider refund updates.
- Readiness captures `lastObservedProviderEventAt`, `lastObservedEventType`, and whether required event categories have been observed in the target environment.

## Direct Refund Execution Contract

Phase 158 may add refund mutation only behind explicit controls:

- Caller must be an authorized admin.
- Billing record must be in an eligible paid or partially refundable state.
- Provider payment reference must be available: PaymentIntent or Charge ID.
- Operator must provide a reason.
- Operator must provide an idempotency key for the refund request.
- Requested amount must be positive and no greater than remaining refundable amount.
- TWINT refunds must remain inside the 180-day refund window when the payment method is TWINT.
- Provider failures must not mutate STOA billing state as if the refund succeeded.
- Successful refund persistence must include provider refund ID, status, amount, currency, reason, idempotency key, operator identity, timestamps, and finance handoff metadata.

## Finance Acceptance Contract

Finance acceptance requires visible, exportable evidence for:

- Invoice ID, hosted invoice URL, receipt URL where available, amount due, amount paid, currency, tax/accounting metadata, and reconciliation IDs.
- Refund ID, amount, currency, provider status, reason, idempotency key, operator, and timestamps.
- Payment method type including TWINT where used.
- Dunning state, failed invoice counts, next action due, and collection status.
- Swiss accounting export fields already introduced in v4.4, extended with direct refund results from Phase 158.

Finance export and admin billing views must not expose raw provider payloads or sensitive payment details.

## Rollout Contract

Checkout and refund rollout must be independently controllable:

- `checkout`: disabled, canary, enabled, or rolled_back.
- `refunds`: disabled, canary, enabled, or rolled_back.
- `provider_readiness`: not_configured, blocked, ready, or degraded.
- `activation_state`: activated, blocked, deferred, or approved_canary_only.

Rollback must disable new live checkout and/or direct refund execution while preserving existing billing status, invoice state, refund history, and finance exports.

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

## Implementation Handoff

Phase 157 implementation targets:

- Add an admin-only provider readiness endpoint.
- Read current Stripe config, live/test mode, price mapping, TWINT flags, webhook secret, and accounting metadata.
- Add provider adapter seams for Stripe account capability and price lookup without creating charges.
- Add tests for missing credentials, test credentials, live-ready-but-blocked, provider API failure, TWINT pending/inactive, and readiness success.

Phase 158 implementation targets:

- Add admin-only direct refund execution.
- Require eligible billing state, provider reference, operator reason, idempotency key, remaining amount validation, and TWINT refund window validation.
- Persist refund result and audit evidence.
- Extend finance export with direct refund result fields.
- Add tests for success, ineligible state, duplicate idempotency, provider failure, and finance export shape.

Phase 159 implementation targets:

- Add webhook registration readiness fields: HTTPS endpoint, signing secret, required events, quick-ack handler expectation, and last observed provider event.
- Add checkout/refund rollout controls visible to admins.
- Ensure rollback disables new live-changing operations without hiding existing billing history.
- Add tests for rollout enable/disable, canary state, rollback, and webhook readiness status.

Phase 160 implementation targets:

- Run focused backend tests and static checks.
- Verify provider readiness, refunds, finance handoff, webhook readiness, and rollout controls.
- Update requirements, roadmap, state, feature-gap docs, and release evidence.
- Record final activation status as `activated`, `blocked`, `deferred`, or `approved_canary_only`.
