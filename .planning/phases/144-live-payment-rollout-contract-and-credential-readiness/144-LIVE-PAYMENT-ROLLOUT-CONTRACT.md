# Phase 144: Live Payment Rollout Contract

**Milestone:** v4.4 Live Payment Provider Rollout
**Requirement:** PAYLIVE-01
**Status:** Ready for Phase 145 implementation
**Created:** 2026-06-11

## Purpose

Phase 144 locks the rollout contract for moving STOA's local Stripe-first subscription MVP toward controlled live payment behavior. It defines credential ownership, environment gates, Stripe-backed TWINT inclusion, smoke boundaries, rollback switches, and the implementation targets for Phases 145 and 146.

No real production charge is enabled by this phase.

## Current Backend State

Inspected files:

- `src/stoa/config.py`
- `src/stoa/services/subscription_service.py`
- `src/stoa/routers/billing.py`
- `src/stoa/routers/parents.py`
- `src/stoa/routers/admin.py`
- `tests/test_subscription_operations.py`

Current behavior:

- Parent checkout uses `POST /parents/me/subscription/checkout`.
- Webhooks enter through `POST /billing/webhooks/stripe`.
- Parent billing status uses `GET /parents/me/subscription/billing`.
- Admin billing visibility uses `GET /admin/subscriptions/billing` and `GET /admin/subscriptions/billing/{parent_id}`.
- Billing summaries are stored as `SUBSCRIPTION_BILLING#{parent_id}` / `SUMMARY`.
- Billing events are stored under the same parent billing PK with `EVENT#...` sort keys.
- Provider event dedupe uses `BILLING_PROVIDER_EVENT#stripe#{event_id}` / `SUMMARY`.
- The current checkout path synthesizes local `cs_{mode}_...` IDs and Stripe Checkout-looking URLs rather than calling the Stripe API.
- Webhook signature validation uses a local HMAC implementation compatible with Stripe's `t=...,v1=...` header shape, then parses JSON directly.
- Provider object parent resolution first checks metadata/client reference, then scans billing summary rows for customer, subscription, or checkout session IDs.
- Subscription entitlement currently becomes active on `checkout.session.completed` or `invoice.paid`; Phase 145 should tighten this around invoice/subscription truth before live enablement.

## Rollout Principles

- Stripe remains the payment provider for v4.4.
- TWINT is in scope as a Stripe-backed payment method, not as a separate provider integration.
- STOA keeps a local billing projection for entitlement, parent/admin visibility, support evidence, and exports.
- Stripe remains the source of truth for checkout sessions, invoices, payments, refunds, and subscription state.
- Live charging must fail closed unless credential, configuration, provider capability, and explicit rollout gates all pass.
- Provider secrets, webhook secrets, live price IDs, and customer billing data must not be logged into planning artifacts or operator-visible evidence.

## Credential Path

Required runtime configuration:

| Setting | Current field | Required v4.4 meaning |
|---------|---------------|-----------------------|
| Environment | `ENVIRONMENT` / `Settings.environment` | Must be `production` or `prod` before live mode can even be considered. |
| Stripe API key | `STRIPE_API_KEY` / `Settings.stripe_api_key` | Must be a live secret key for live rollout; test key remains allowed for local/test smoke. |
| Webhook signing secret | `STRIPE_WEBHOOK_SECRET` / `Settings.stripe_webhook_secret` | Must match the deployed Stripe webhook endpoint secret for the current mode. |
| Standard price | `STRIPE_STANDARD_PRICE_ID` / `Settings.stripe_standard_price_id` | Must map to the approved Standard subscription price in the matching Stripe mode. |
| Premium price | `STRIPE_PREMIUM_PRICE_ID` / `Settings.stripe_premium_price_id` | Must map to the approved Premium subscription price in the matching Stripe mode. |
| Success URL | `STRIPE_CHECKOUT_SUCCESS_URL` | Must point at the production parent subscription route for live mode. |
| Cancel URL | `STRIPE_CHECKOUT_CANCEL_URL` | Must point at the production parent subscription route for live mode. |
| Live enablement switch | `STRIPE_LIVE_CHARGES_ENABLED` | Must remain `false` until explicit rollout approval is recorded. |

Credential storage and injection:

- Production secrets should be injected through the existing AWS runtime configuration path, preferably Secrets Manager-backed Lambda environment resolution when the deployment stack owns secret references.
- Plain `.env` remains a local development mechanism only.
- Phase 145 must expose a redacted readiness status that distinguishes `test`, `live_ready_but_blocked`, `live_enabled`, and `not_configured`.
- Phase 145 must validate that all live values are from the same mode before allowing checkout.

## Stripe Product And Price Mapping

STOA keeps three product tiers:

| STOA tier | Billing behavior | Stripe requirement |
|-----------|------------------|--------------------|
| Free | No checkout | No Stripe price required. |
| Standard | Paid subscription | `STRIPE_STANDARD_PRICE_ID`, monthly recurring CHF price. |
| Premium | Paid subscription | `STRIPE_PREMIUM_PRICE_ID`, monthly recurring CHF price. |

Phase 145 must reject paid checkout if the configured price ID is missing, test/live-mismatched, or not approved for the current rollout mode.

The code should not infer live price IDs from naming conventions. It should treat configured IDs as opaque and validate through Stripe API reads where possible.

## Webhook Contract

Existing route:

- `POST /billing/webhooks/stripe`

Required Phase 145 event set:

- `checkout.session.completed`
- `checkout.session.expired`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.paid`
- `invoice.payment_failed`

Recommended Phase 146 event additions:

- `invoice.updated`
- `charge.refunded`
- `refund.created`
- `refund.updated`
- Any Stripe Billing recovery events needed by the selected dunning configuration.

Webhook processing requirements:

- Use the official Stripe SDK webhook construction/verification path once `stripe-python` is added.
- Persist Stripe `livemode`, event ID, event type, created timestamp, request/correlation identifiers where available, and processing result.
- Deduplicate by provider event ID before mutating billing state.
- Resolve parents through provider lookup rows rather than billing summary scans.
- Treat `invoice.paid` plus current subscription truth as the entitlement source for live paid access.
- Preserve manual override behavior, but make its precedence visible in billing evidence.

## TWINT Scope

TWINT is explicitly in scope for v4.4 as a Stripe-backed payment method.

Required Phase 145 behavior:

- Add readiness evidence showing whether the Stripe account can present TWINT for eligible Swiss/CHF subscription Checkout flows.
- Keep TWINT behind the same live rollout gates as card checkout.
- Use Stripe Checkout and dynamic payment method configuration where supported.
- Store payment method context from Stripe events when available so parent/admin billing surfaces can distinguish card, TWINT, and unknown provider methods without exposing sensitive payment details.

Required Phase 146 behavior:

- Surface TWINT-originated subscriptions, invoices, refunds, and dunning states through the same billing model as other Stripe subscriptions.
- Include payment-method context in accounting handoff metadata when Stripe provides it.
- Avoid building a separate TWINT backend branch unless Stripe capability validation proves Checkout cannot support the required flow.

Readiness cannot be claimed from dashboard enablement alone. It requires account capability/state evidence, Swiss/CHF eligibility, and Checkout presentation or provider configuration evidence.

## Safe Smoke Modes

| Mode | Purpose | Allowed actions | Must not do |
|------|---------|-----------------|-------------|
| Local/test mode | Developer verification | Test Stripe keys or synthetic fixtures, local webhook payloads, focused tests. | Use live keys or live customer data. |
| Live configuration inspection | Production readiness check | Redacted environment/config checks, Stripe object reads, webhook endpoint status, price mapping validation. | Create real customer charges. |
| Approved live canary | Controlled rollout after approval | Allowlisted parent/customer, live Checkout, real webhook verification, immediate evidence capture. | Broad customer rollout or unbounded checkout access. |
| Rollback verification | Prove disable path | Flip rollout gate off, verify checkout refuses live flow and existing billing remains readable. | Delete provider data or mutate customer payment state unnecessarily. |

Default posture remains no real charge.

## Rollback Switches

Minimum switches for Phase 145:

- `STRIPE_LIVE_CHARGES_ENABLED=false` must block new live checkout creation.
- Missing or invalid live credentials must block new live checkout creation.
- Missing or invalid live price IDs must block new live checkout creation.
- Missing webhook secret in production must reject webhook processing.
- Admin readiness should show the blocking reason in redacted form.

Operational rollback should disable new checkout while leaving:

- Billing status reads available.
- Webhook processing available for already-created provider events, unless explicitly disabled for incident response.
- Manual admin subscription override available as a support fallback.

## Phase 145 Implementation Targets

Phase 145 should deliver:

- `stripe-python` dependency and a Stripe gateway wrapper for SDK calls.
- Billing readiness service that computes `test`, `not_configured`, `live_ready_but_blocked`, and `live_enabled`.
- Real Stripe Checkout session creation in non-synthetic paths.
- Livemode-aware price/customer/session handling.
- TWINT-capable Checkout configuration for eligible Swiss/CHF subscription flows.
- Provider lookup rows for customer, subscription, checkout session, invoice, payment intent, charge, and refund IDs as they become available.
- SDK-backed raw-body webhook verification.
- Webhook idempotency and operator-visible event evidence.
- Admin readiness/status response without secrets.
- Focused tests for gating, test/live mismatch, webhook idempotency, bad signatures, and TWINT eligibility state.

## Phase 146 Implementation Targets

Phase 146 should deliver:

- Billing operations service for invoice, refund, dunning, and accounting handoff surfaces.
- Parent/admin invoice and receipt metadata using provider-hosted artifacts.
- Refund eligibility, request/handoff state, result projection, and audit evidence.
- Tax/accounting export fields for Swiss reconciliation.
- Dunning state projection for overdue, failed payment, retry, recovery, and escalation states.
- Payment-method context, including TWINT when Stripe provides it, in billing projections and exports.
- Focused tests or fixtures for invoice metadata, refund state, dunning state, export fields, and TWINT-originated lifecycle data.

## Open External Dependencies

- Approved Stripe live API key and webhook secret.
- Approved live Standard and Premium CHF recurring price IDs.
- Confirmation that STOA's Stripe account can use TWINT for the target subscription flow.
- Production webhook endpoint registration in Stripe.
- Finance confirmation that Stripe-hosted invoice artifacts plus exported metadata are sufficient for Swiss accounting handoff.

## Acceptance Traceability

| PAYLIVE-01 criterion | Contract coverage |
|----------------------|-------------------|
| Stripe live credential path, webhook endpoint, price mapping, env vars, rollback switches | Credential Path, Stripe Product And Price Mapping, Webhook Contract, Rollback Switches |
| TWINT included through Stripe with capability checks and rollout gates | TWINT Scope, Safe Smoke Modes, Phase 145 Implementation Targets |
| Safe smoke modes and no-real-charge default | Safe Smoke Modes |
| Existing code paths mapped to rollout changes | Current Backend State, Phase 145 Implementation Targets, Phase 146 Implementation Targets |
| Gap docs mark live payment rollout active | Requirements, roadmap, state, and research docs updated before Phase 144 execution |

