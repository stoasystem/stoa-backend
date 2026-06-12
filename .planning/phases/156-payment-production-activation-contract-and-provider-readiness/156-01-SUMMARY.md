# Summary 156-01: Payment Production Activation And Provider Readiness Contract

**Status:** Complete
**Requirement:** PAYACT-01
**Completed:** 2026-06-12

## Delivered

- Replaced the placeholder activation contract with an accepted production payment activation contract.
- Documented live credential ownership, injection paths, redacted readiness states, and fail-closed blocker behavior.
- Documented Standard/Premium CHF recurring price expectations and TWINT production constraints: Switzerland customer location, CHF presentment, 5,000 CHF maximum, recurring support, no manual capture, full/partial refunds, 180-day refund window, merchant onboarding, and `twint_payments` capability status.
- Documented HTTPS webhook registration, signing secret ownership, quick 2xx handler expectation, required event families, and last-observed event evidence.
- Documented direct refund execution controls, idempotency, operator reason, remaining refundable amount validation, audit persistence, and finance handoff evidence.
- Documented rollout controls for independent checkout/refund activation, canary state, rollback, and final activation status.
- Wrote concrete Phase 157 through Phase 160 implementation handoff targets.

## Verification

- Current v4.4 payment implementation and release artifacts were reviewed before writing the contract.
- Official Stripe TWINT, account capability, refund, and webhook documentation from `.planning/research/SUMMARY.md` was incorporated.
- No real customer charge, refund, Checkout Session, PaymentIntent, or provider mutation was performed.
