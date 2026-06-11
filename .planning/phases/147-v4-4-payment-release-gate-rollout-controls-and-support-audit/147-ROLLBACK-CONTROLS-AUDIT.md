---
phase: 147
status: passed
captured_at: 2026-06-11
---

# v4.4 Rollback And Disable Controls Audit

## Disable Controls

- `STRIPE_LIVE_CHARGES_ENABLED=false` blocks new production live checkout creation even when live credentials are otherwise present.
- Missing Stripe API key, webhook secret, Standard price ID, Premium price ID, or Stripe SDK forces `not_configured`.
- Non-live API keys in production are treated as blockers.
- `STRIPE_TWINT_ENABLED=false` disables TWINT eligibility.
- `STRIPE_TWINT_CAPABILITY_CONFIRMED=false` keeps TWINT in a capability-unconfirmed state.
- Webhook signing secret is required by default; unsigned local/test webhooks require explicit `STRIPE_ALLOW_UNSIGNED_TEST_WEBHOOKS=true`.

## Rollback Behavior

- New checkout creation fails closed when live charges are disabled.
- Existing billing records remain readable through parent/admin billing endpoints after checkout is disabled.
- Webhook idempotency prevents duplicate provider events from reapplying transitions.
- Replacement checkout expiry preserves already-active subscriptions.
- Direct refund execution is not enabled, so rollback does not require reversing local refund mutations.

## Operator Procedure

1. Set `STRIPE_LIVE_CHARGES_ENABLED=false` to stop new live checkout sessions.
2. If needed, remove or rotate Stripe live credentials and webhook secrets to force `not_configured`.
3. Set `STRIPE_TWINT_ENABLED=false` or leave `STRIPE_TWINT_CAPABILITY_CONFIRMED=false` to block TWINT exposure while keeping other billing metadata readable.
4. Confirm parent/admin billing endpoints still show existing billing state and latest provider evidence.
5. Record any live provider/customer actions in the provider dashboard outside this repository if real charging has ever been approved.

## Verdict

Rollback and disable controls are sufficient for the local v4.4 release gate. Production rollout still requires external approval and live provider setup.
