# Phase 146 Billing Operations And Swiss Handoff Spec

**Milestone:** v4.4 Live Payment Provider Rollout
**Requirement:** PAYLIVE-03
**Status:** Implemented

## Implementation Notes

- Parent/admin billing responses now include `latestInvoice`, `refund`, `dunning`, and `accountingHandoff`.
- Stripe invoice webhooks project provider invoice IDs, hosted invoice URLs, receipt URLs, invoice status, currency, amounts, tax provider-managed status, period bounds, and selected payment method context.
- Refund readiness is non-mutating and reports provider handoff state, required operator reason, eligible amount, currency, and provider references.
- Refund lifecycle webhook events can update refund status and accounting handoff references.
- Dunning projections expose retry and payment-failed states without exposing raw provider payloads.
- The admin accounting export endpoint returns redacted handoff rows for finance/reconciliation.
- TWINT is represented through the same Stripe payment method context as card and other provider methods.

## Invoice And Receipt Readiness

Parent and admin billing views should surface provider-backed invoice/receipt metadata when available:

- Provider invoice ID.
- Provider subscription ID.
- Hosted invoice URL or receipt URL.
- Invoice status.
- Currency.
- Amount due, amount paid, amount remaining.
- Period start and period end.
- Payment method context, including TWINT when known.

Sensitive provider payloads and payment details remain hidden.

## Refund Readiness

Refund readiness should include:

- Refund eligibility state.
- Eligible amount and currency where available.
- Required operator reason.
- Provider charge/payment intent/invoice references.
- Provider handoff state: `not_eligible`, `ready_for_provider`, `requested`, `succeeded`, `failed`, `cancelled`, or equivalent.
- Audit/status timestamps.

Direct refund execution is not enabled in Phase 146. Refund support is a readiness and provider-handoff surface only.

## Dunning Readiness

Dunning state should project Stripe subscription/invoice/payment outcomes into parent/admin visible states:

- `active`
- `past_due`
- `payment_failed`
- `retrying`
- `recovered`
- `cancelled`
- `manual_review`

Parent surfaces should explain billing action status without exposing internal provider payloads. Admin surfaces should expose enough metadata for support follow-up.

## Swiss Accounting Handoff

Accounting export or handoff metadata should include:

- Parent ID and billing account reference.
- STOA tier.
- Provider customer/subscription/invoice IDs.
- Currency and amounts.
- Tax/VAT fields when provider data is available.
- Period start/end.
- Invoice/receipt URL metadata.
- Refund references.
- Payment method context.
- Reconciliation identifiers.

If tax data is not available locally, the export should mark it as provider-managed rather than fabricating values.

## TWINT Lifecycle Handling

TWINT-originated subscriptions should flow through the same Stripe billing projections:

- Checkout eligibility.
- Invoice/payment status.
- Refund status.
- Dunning/payment failure status.
- Accounting handoff payment method context.

No separate TWINT backend model is planned unless Stripe cannot provide required subscription lifecycle data.

## Test Matrix

- Invoice metadata appears in parent/admin billing output.
- Missing invoice URL degrades gracefully.
- Refund eligibility is computed from billed states.
- Refund-ineligible states are visible and non-mutating.
- Payment failure projects dunning state.
- Accounting export includes provider IDs and currency/amount fields.
- TWINT payment method context is retained when present.
