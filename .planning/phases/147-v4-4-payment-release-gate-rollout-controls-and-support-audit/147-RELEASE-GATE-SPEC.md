# Phase 147 Payment Release Gate Spec

**Milestone:** v4.4 Live Payment Provider Rollout
**Requirement:** VERIFY-27
**Status:** Implemented

## Implementation Notes

- Focused payment tests and static checks passed.
- Release evidence, rollback controls audit, and remaining payment work audit were captured.
- Requirements, roadmap, state, milestone history, and remaining feature queue were updated.
- Live customer charging remains explicitly deferred.

## Evidence Required

- Focused subscription/payment tests pass.
- Focused static checks pass for payment routes/services/config/tests.
- Phase 144 rollout contract exists and identifies credential path, TWINT inclusion, safe smoke modes, and rollback switches.
- Phase 145 checkout/webhook readiness exists and keeps live charges fail-closed without explicit enablement.
- Phase 146 billing operations readiness exists for invoice, refund, dunning, accounting handoff, and TWINT lifecycle projection.

## Rollout Gate

Live charging remains blocked unless all of the following are true:

- `ENVIRONMENT` is production.
- Stripe live API key is configured and redacted readiness reports it present.
- Stripe webhook signing secret is configured.
- Standard and Premium live price IDs are configured.
- Stripe SDK is installed.
- `STRIPE_LIVE_CHARGES_ENABLED=true`.
- TWINT rollout requires `STRIPE_TWINT_CAPABILITY_CONFIRMED=true` in addition to the shared live gate.
- External approval exists for real customer charging.

## Rollback And Disable Controls

- Set `STRIPE_LIVE_CHARGES_ENABLED=false` to block new live checkout creation.
- Remove or invalidate live Stripe credentials or price IDs to force `not_configured`.
- Disable TWINT exposure with `STRIPE_TWINT_ENABLED=false` or leave capability unconfirmed.
- Keep webhook signing secret required by default; unsigned local/test webhooks require explicit opt-in.
- Existing billing records remain readable after checkout is disabled.

## Remaining Work Audit

The milestone can close with real charging deferred if the audit records:

- Live Stripe credentials and webhook endpoint still require external approval/configuration.
- TWINT live capability still requires Stripe account/provider confirmation.
- Direct refund execution remains a future explicit operator workflow.
- Full accounting integration remains a future integration after finance destination acceptance.
- Broader provider automation and support/CRM handoff are future milestones.
