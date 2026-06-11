# Phase 146 Billing Operations And Swiss Handoff Spec

**Milestone:** v4.4 Live Payment Provider Rollout
**Requirement:** PAYLIVE-03
**Status:** Planned

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

Direct refund execution is optional for v4.4. If implemented, it must be explicit and operator-driven.

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
