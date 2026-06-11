---
phase: 144
plan: 144-01
status: complete
completed_at: 2026-06-11
---

# Plan 144-01 Summary: Live Payment Rollout Contract

## Completed

- Inspected the current subscription checkout, billing, webhook, parent, admin, configuration, and subscription test surfaces.
- Documented the current local/test billing implementation and live rollout gaps.
- Defined the Stripe credential path, price mapping, webhook contract, safe smoke modes, and rollback switches.
- Locked TWINT as an in-scope Stripe-backed payment method for v4.4.
- Mapped Phase 145 implementation targets for checkout, webhook, livemode gating, provider lookup rows, and TWINT-capable Stripe handling.
- Mapped Phase 146 implementation targets for invoices, refunds, dunning, Swiss accounting handoff, and TWINT lifecycle behavior.

## Files Changed

- `.planning/phases/144-live-payment-rollout-contract-and-credential-readiness/144-CONTEXT.md`
- `.planning/phases/144-live-payment-rollout-contract-and-credential-readiness/144-01-PLAN.md`
- `.planning/phases/144-live-payment-rollout-contract-and-credential-readiness/144-LIVE-PAYMENT-ROLLOUT-CONTRACT.md`
- `.planning/phases/144-live-payment-rollout-contract-and-credential-readiness/144-VERIFICATION.md`

## Verification

- `.venv/bin/python -m pytest tests/test_subscription_operations.py`

## Notes For Phase 145

- Replace synthetic Checkout session generation with a Stripe SDK-backed gateway while preserving fail-closed test/live gates.
- Add explicit readiness states for `test`, `not_configured`, `live_ready_but_blocked`, and `live_enabled`.
- Use provider lookup rows instead of scan-based provider object resolution.
- Keep TWINT inside Stripe Checkout/Billing unless provider validation proves that unsupported.
