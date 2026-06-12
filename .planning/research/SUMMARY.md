# Project Research Summary

**Project:** STOA backend
**Domain:** Payment production activation and provider automation
**Researched:** 2026-06-12
**Confidence:** HIGH

## Executive Summary

v4.7 should turn STOA's v4.4 Stripe/TWINT readiness foundation into controlled production activation without silently enabling real customer charging. The correct milestone shape is contract first, then provider-readiness checks, direct refund execution, webhook/rollout controls, and a release gate that records whether live activation is approved, blocked, deferred, or canary-only.

Official Stripe documentation confirms TWINT remains a Switzerland-focused payment method with CHF presentment, recurring payment support, no manual capture support, full and partial refunds, and a 5,000 CHF maximum amount. Stripe also documents merchant onboarding constraints for TWINT: a functional public website, visible legal/contact information, CHF pricing at checkout, and capability verification before the `twint_payments` capability becomes active. These facts should shape v4.7 readiness gates instead of relying only on local configuration.

The milestone should keep all live-changing operations fail-closed. Readiness checks may call provider APIs when live credentials exist, but checkout and refund mutation must remain independently gated by explicit rollout approval. Webhook readiness should verify HTTPS endpoint registration, signing secret ownership, required event subscriptions, and recent observed event health.

## Key Findings

### TWINT Production Constraints

- Customer location: Switzerland.
- Presentment currency: CHF.
- Maximum amount: 5,000 CHF.
- Recurring payments: supported.
- Manual capture: not supported.
- Refunds and partial refunds: supported.
- TWINT refunds can be issued up to 180 days after payment completion.
- TWINT must be enabled in Stripe payment method settings or through supported capability/payment-method configuration flows.
- `twint_payments` capability status can be `active`, `inactive`, or `pending`.
- Onboarding can remain pending until TWINT website/legal/contact/CHF requirements are verified.

Sources:

- https://docs.stripe.com/payments/twint
- https://docs.stripe.com/api/accounts/object

### Refund Execution Constraints

- Stripe refund creation requires a Charge or PaymentIntent.
- Partial refunds are allowed up to the remaining unrefunded amount.
- Stripe raises errors for already-refunded charges, invalid identifiers, or over-refunds.
- STOA should require admin authorization, operator reason, idempotency key, provider reference, and eligible billing state before calling provider refund mutation.

Source:

- https://docs.stripe.com/api/refunds/create

### Webhook Readiness Constraints

- Production webhook endpoints must be publicly reachable over HTTPS.
- Stripe sends events as JSON payloads and uses signing secrets for verification.
- The handler should return a 2xx response quickly before expensive downstream work.
- STOA readiness should track endpoint mode, signing secret presence, required event subscriptions, and last observed provider event.

Source:

- https://docs.stripe.com/webhooks

## Implications For v4.7 Requirements

- PAYACT-01 should explicitly include TWINT public website/legal/contact/CHF onboarding requirements, `twint_payments` capability status, 5,000 CHF maximum, no manual capture, and 180-day refund window.
- PAYACT-02 should implement readiness checks that distinguish missing credentials, test-mode credentials, pending TWINT capability, inactive TWINT capability, active TWINT capability, missing live prices, and provider API failures.
- PAYACT-03 should implement direct refunds with idempotency and lifecycle persistence while enforcing provider remaining-amount and eligibility constraints.
- PAYACT-04 should verify HTTPS webhook endpoint registration, signing secret ownership, required events, and separate rollout gates for checkout and refunds.
- VERIFY-30 should record whether live payment activation is activated, blocked, deferred, or canary-only, and must explicitly state if no real customer charge or refund was executed.

## Recommended Phase Order

1. Phase 156: contract and provider readiness handoff.
2. Phase 157: admin-only provider readiness checks.
3. Phase 158: controlled direct refund execution and finance handoff.
4. Phase 159: webhook registration readiness and rollout controls.
5. Phase 160: release gate and feature-gap update.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| TWINT constraints | HIGH | Based on current official Stripe TWINT documentation. |
| Refund mutation design | HIGH | Based on current Stripe Refund API behavior and existing STOA billing state patterns. |
| Webhook readiness | HIGH | Based on current Stripe webhook guidance and existing STOA webhook handlers. |
| Rollout controls | HIGH | Continues established v4.4 fail-closed rollout patterns. |

## Sources

- Stripe TWINT payments: https://docs.stripe.com/payments/twint
- Stripe Account capabilities: https://docs.stripe.com/api/accounts/object
- Stripe Refund API: https://docs.stripe.com/api/refunds/create
- Stripe webhooks: https://docs.stripe.com/webhooks

---
*Research completed: 2026-06-12*
*Ready for roadmap: yes*
