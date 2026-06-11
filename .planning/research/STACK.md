# Stack Research

**Domain:** Stripe-first live payment rollout for STOA subscriptions
**Researched:** 2026-06-11
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Stripe Billing + Checkout + Webhooks + Invoicing + Refunds | Current Stripe API surfaces | Live subscription checkout, recurring billing state, provider-hosted invoices/receipts, refunds, and dunning primitives | This milestone is rollout-readiness work, not billing-platform invention. Stripe already covers the needed surfaces, and STOA's v3.9 MVP already models Stripe semantics. |
| `stripe-python` | `~=15.2` | Real Stripe API client and official webhook verification path from the backend | Replace the local synthetic checkout/webhook simulation in `src/stoa/services/subscription_service.py` with Stripe's official Python SDK. Pin the minor range to avoid surprise typing/runtime drift. |
| Existing FastAPI + Lambda/API Gateway ingress | `fastapi>=0.115`, Python `>=3.12` | Keep `/parents/me/subscription/checkout`, `/billing/webhooks/stripe`, and admin billing APIs as the rollout surface | No new app server, worker, or queue is needed. The current backend already has the right request boundaries and auth model. |
| Existing DynamoDB single-table billing projection | Existing repo pattern | Internal projection for parent/admin billing views, webhook audit timeline, refund status, invoice metadata, and release evidence fields | Keep provider state normalized into STOA-owned records so operators can verify rollout without opening secrets or raw provider payloads. |
| AWS Secrets Manager-backed runtime config | Existing STOA ops pattern | Store live Stripe secret key and webhook signing secret outside git and local env files | STOA already uses a secret-backed production credential path for operational access. Live payment secrets should follow the same pattern. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `stripe` | `~=15.2` | `StripeClient`, Checkout Session creation, refund creation, invoice retrieval, customer retrieval, and SDK-backed webhook parsing/signature verification | Required in Phase 145/146 when replacing generated `cs_test_*` IDs and handwritten HMAC-only provider handling. |
| `pytest` + FastAPI `TestClient` | Existing `pytest>=8.2.0` | Deterministic coverage for live-readiness config, webhook idempotency, refund state updates, invoice metadata mapping, and dunning state transitions | Extend `tests/test_subscription_operations.py`; do not introduce a new test framework. |
| Stripe CLI | Latest stable | Local webhook forwarding and provider fixture triggering | Use for test-mode verification with `stripe listen --load-from-webhooks-api --forward-to ...` and targeted event triggers before any production smoke. |
| Existing release evidence and support-handoff services | Internal modules in `src/stoa/services/` | Redacted payment rollout evidence, refusal behavior, and support-safe export | Reuse `release_evidence_service.py` and `support_handoff_service.py` instead of inventing a payment-specific evidence system. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Stripe Dashboard / Workbench | Configure products, prices, payment methods, webhook endpoints, customer emails, and Revenue Recovery retries | Treat Dashboard configuration as source material for evidence, but keep canonical app behavior driven by backend config and saved provider IDs. |
| Stripe CLI | Replay and verify webhook flows without public production mutation | Best fit for test-mode and local endpoint checks; do not use it as a production control plane. |
| AWS Secrets Manager + existing deploy/runtime evidence flow | Secret storage and redacted rollout evidence | Mirror the established STOA pattern for secret-backed production operations. |

## STOA Integration Points

Use the existing backend seams. Do not add a parallel billing subsystem.

- `src/stoa/services/subscription_service.py`
  - Replace synthetic checkout session generation in `create_checkout_session()` with real Stripe Checkout Session creation.
  - Keep storing a STOA billing summary row plus append-only billing events, but add provider fields needed for rollout ops:
    - `provider_invoice_id`
    - `provider_invoice_hosted_url`
    - `provider_invoice_pdf`
    - `provider_receipt_number`
    - `provider_payment_intent_id`
    - `provider_charge_id`
    - `provider_refund_id`
    - `refund_status`
    - `refund_reason`
    - `dunning_status`
    - `invoice_attempt_count`
    - `next_payment_attempt_at`
    - `automatic_tax_enabled`
    - `tax_country`
    - `tax_exempt_status`
    - `balance_transaction_id`
  - Keep the existing event timeline shape, but subscribe and map more Stripe events for rollout readiness:
    - `checkout.session.completed`
    - `checkout.session.expired`
    - `customer.subscription.created`
    - `customer.subscription.updated`
    - `customer.subscription.deleted`
    - `invoice.created`
    - `invoice.finalized`
    - `invoice.paid`
    - `invoice.payment_failed`
    - `invoice.payment_action_required`
    - `invoice.overdue`
    - `refund.created`
    - `refund.updated`
    - `refund.failed`

- `src/stoa/routers/billing.py`
  - Keep raw-body webhook handling, but switch verification to the Stripe SDK rather than maintaining a handwritten verifier as the live path.
  - Persist provider mode, Stripe event ID, event type, dedupe result, request correlation ID, and mapped operator-visible status.

- `src/stoa/routers/parents.py`
  - Keep `/parents/me/subscription/checkout` as the backend-controlled redirect entrypoint.
  - Add parent-visible invoice/receipt fields only as links or provider IDs, not full provider payloads.
  - Surface dunning-safe states such as `past_due`, `payment_failed`, `action_required`, and next retry timestamp.

- `src/stoa/routers/admin.py`
  - Extend `/admin/subscriptions/billing` and `/admin/subscriptions/billing/{parent_id}` with operator fields for invoice, refund, and dunning verification.
  - Admin responses should show redacted readiness evidence, not secrets and not raw payment method data.

- `tests/test_subscription_operations.py`
  - Keep the current local coverage shape.
  - Add tests for:
    - live-ready vs test-mode gating
    - webhook idempotency across invoice and refund events
    - refund creation eligibility and refusal states
    - invoice metadata projection
    - dunning state transitions
    - non-live fallback behavior

- Existing release evidence modules
  - Reuse the repo's metadata-only, denylist-backed evidence style for payment rollout proof.
  - Payment evidence should include provider mode, checkout session ID, webhook event IDs, invoice/refund IDs, request IDs, and verification timestamps.
  - Payment evidence should exclude secrets, raw payment method details, cookies, and full customer payloads.

## Provider Configuration Patterns

- Keep plan mapping in Stripe Prices, not hardcoded amounts in STOA.
  - Continue using env-backed `stripe_standard_price_id` and `stripe_premium_price_id`.
  - Add explicit documentation for live vs test price IDs and who owns them.

- Keep live rollout gated by config.
  - The current `stripe_live_charges_enabled` switch is the right primitive.
  - Recommended runtime states:
    - `test`: test secret, test webhook secret, test prices, no live charge.
    - `live_ready`: live credentials present and webhook endpoint verified, but checkout creation still refused by flag/policy.
    - `live_enabled`: explicit approval to create live Checkout Sessions.

- Use metadata and `client_reference_id` on Checkout Sessions and subscriptions.
  - Persist `stoa_parent_id`, requested tier, and STOA correlation IDs so webhook reconciliation does not depend on dashboard-only searching.

- Keep Stripe-hosted billing artifacts.
  - Use hosted invoice URLs, invoice PDFs, receipt URLs, and Stripe customer emails instead of generating custom STOA PDFs or receipt emails.

- Enable TWINT through Stripe, not through a separate integration.
  - Stripe's TWINT docs show Checkout, Subscriptions, and Invoicing support, with recurring payments in Switzerland.
  - For this milestone, TWINT readiness means:
    - validate the Stripe account is eligible
    - enable TWINT in Dashboard payment methods
    - verify CHF recurring price compatibility in Checkout/subscription flows
    - confirm webhook and invoice states still map through the same Stripe surfaces
  - Do not add TWINT-specific backend branching unless Stripe Checkout proves insufficient in production validation.

- Use Stripe dunning primitives before custom automation.
  - Stripe Billing's Smart Retries and Revenue Recovery settings are the default choice for failed recurring payments.
  - STOA should project the resulting invoice/subscription states into parent/admin views, not build its own retry scheduler in v4.4.

- Keep Swiss tax/accounting handoff export-first.
  - For v4.4, export metadata needed by accounting rather than building a direct ERP connector.
  - Minimum export set:
    - customer name/email/country
    - Stripe customer ID
    - subscription ID
    - invoice ID
    - invoice number / receipt number when present
    - hosted invoice URL / invoice PDF link when present
    - currency
    - gross amount
    - total excluding tax
    - total tax
    - refund amount and refund status
    - balance transaction ID
    - fee / net values when retrieved from Stripe balance transaction data
    - tax-exempt status and customer tax IDs when present
  - Stripe Tax can stay optional. I verified Stripe Tax's general capability and invoice fields, but did not independently confirm a STOA-specific Swiss registration posture from current account data, so treat full automation here as a later decision.

## Installation

```bash
# Core backend addition
python -m pip install "stripe~=15.2"

# Existing test stack remains
python -m pip install -e ".[dev]"

# Optional local provider tooling
# Install Stripe CLI from Stripe's official instructions for your OS
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Stripe-hosted Checkout + Billing + Invoicing | Custom payment UI plus direct PaymentIntent orchestration | Only if STOA later needs a highly customized checkout flow that Stripe-hosted Checkout cannot support. Not justified for rollout readiness. |
| Stripe-enabled TWINT within Checkout | Separate TWINT PSP integration | Only if commercial, settlement, or product constraints force TWINT outside Stripe. Current docs indicate Stripe can cover TWINT in Checkout, Subscriptions, and Invoicing. |
| Stripe Smart Retries / Revenue Recovery | STOA-managed retry cron and bespoke dunning rules | Only after live evidence shows Stripe's built-in retry controls are insufficient. |
| Export-first Swiss accounting handoff | Direct Bexio / Abacus / ERP connector now | Only once finance operations confirm a stable target system and approved credentials path. This milestone should stop at metadata handoff readiness. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Separate TWINT SDK or second PSP in v4.4 | Adds a second payment state machine and second webhook/invoice/refund surface before Stripe rollout is proven | Keep TWINT inside Stripe's payment-method configuration first |
| Custom invoice PDFs, custom receipt emails, or STOA-hosted billing documents | Reinvents provider-hosted artifacts that Stripe already supplies and increases legal/formatting risk | Surface Stripe hosted invoice/receipt links and metadata |
| Custom dunning scheduler | Duplicates Stripe Billing retry logic and creates conflicting truth about overdue state | Use Stripe Revenue Recovery / Smart Retries and project results into STOA |
| Full tax engine or Swiss accounting integration in this milestone | Too much scope for a rollout-readiness milestone; legal/commercial details are not fully verified here | Export accounting-ready metadata and defer direct integration |
| Handwritten webhook verification as the long-term live path | The current HMAC code is fine for the local MVP, but the official SDK is the safer live integration surface | Use `stripe-python` webhook parsing / signature verification |

## Stack Patterns by Variant

**If live charging is still not approved:**
- Use real Stripe test mode only.
- Keep `stripe_live_charges_enabled=false`.
- Allow local/test Checkout Session creation, webhook forwarding, refund simulation, and release evidence capture without live customer charging.

**If live credentials are configured but rollout approval is still withheld:**
- Support `live_ready` inspection in admin/release evidence.
- Validate secret presence, live price IDs, webhook secret presence, and registered endpoint shape.
- Refuse live checkout creation by policy until explicit approval.

**If TWINT is enabled in the Stripe account:**
- Let Stripe Checkout surface it as an eligible payment method for Swiss customers and CHF prices.
- Reuse the same webhook, invoice, refund, and billing projection pipeline.
- Do not create STOA-specific TWINT endpoints or status models unless production validation exposes a real gap.

**If Swiss tax automation becomes mandatory later:**
- Enable Stripe Tax deliberately and attach product tax codes plus customer location completeness checks.
- Keep that as a later follow-up, not part of the minimal v4.4 rollout stack.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `stripe~=15.2` | Python `>=3.9` | Verified from current PyPI package metadata; STOA's Python 3.12 runtime is compatible. |
| `stripe~=15.2` | Existing `httpx>=0.27.0` | Useful if async Stripe calls are adopted later, but v4.4 can stay synchronous. |
| `fastapi>=0.115.0` | `pydantic>=2.7.0` | Already the repo baseline; no new web framework work is required. |
| Stripe webhook endpoint API version | Tested account/webhook version | Keep webhook payload assumptions aligned with the Stripe account/webhook version you verify in evidence; do not silently rely on older local fixture shapes. |

## Sources

- Internal codebase: `src/stoa/services/subscription_service.py`, `src/stoa/routers/billing.py`, `src/stoa/routers/parents.py`, `src/stoa/routers/admin.py`, `tests/test_subscription_operations.py`
- Internal operations pattern: `src/stoa/services/release_evidence_service.py`, `src/stoa/services/support_handoff_service.py`
- Stripe Checkout subscriptions: https://docs.stripe.com/payments/checkout/build-subscriptions
- Stripe webhooks: https://docs.stripe.com/webhooks
- Stripe event types: https://docs.stripe.com/api/events/types
- Stripe Checkout Session create API: https://docs.stripe.com/api/checkout/sessions/create
- Stripe TWINT: https://docs.stripe.com/payments/twint
- Stripe subscription webhooks: https://docs.stripe.com/billing/subscriptions/webhooks
- Stripe refunds: https://docs.stripe.com/refunds
- Stripe Refund create API: https://docs.stripe.com/api/refunds/create
- Stripe invoices object: https://docs.stripe.com/api/invoices/object
- Stripe receipts: https://docs.stripe.com/receipts
- Stripe Smart Retries / Revenue Recovery: https://docs.stripe.com/billing/revenue-recovery/smart-retries
- Stripe Tax overview: https://docs.stripe.com/tax
- PyPI `stripe` package metadata: https://pypi.org/pypi/stripe/json

---
*Stack research for: Stripe-first live payment rollout for STOA subscriptions*
*Researched: 2026-06-11*
