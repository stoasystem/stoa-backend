# Phase 258 Payment/Auth Smoke Evidence

## New Release Endpoint

- Route: `GET /admin/external-activation/payment-auth-smoke`
- Role: admin only
- Mutation: none
- Secrets: redacted
- Raw provider payloads: excluded
- Login codes: excluded

## Payment Contract

The payment section reuses `subscription_service.get_provider_readiness(settings)` and reports:

- Stripe credential mode and configured/missing status.
- Webhook endpoint/signing readiness.
- TWINT capability/readiness.
- Finance handoff readiness.
- Checkout/refund rollout controls.
- Refund activation status.
- Smoke mode and whether live customer mutation is allowed.

Live payment mutation remains disabled unless readiness is live, checkout rollout allows it, and `stripe_live_charges_enabled` is enabled. Otherwise the smoke mode is `read_only` and `customerMutationAllowed=false`.

## Cognito/Email Contract

The Cognito/email section reports:

- Cognito user pool and role client-id configuration.
- Email verification policy: `cognito_sign_up_confirm_sign_up`.
- Login-code policy: `deferred_cognito_custom_auth_required`.
- Local auth behavior evidence: pending verification, token block until verified, resend cooldown, and support recovery visibility.
- Live delivery blockers for approved test inbox and recorded production delivery smoke.

Configured Cognito local behavior is classified as `locally_ready`, while production email delivery remains `blocked` until live delivery evidence exists.

## Fail-Closed Evidence

Blocked payment provider readiness returns `payment.classification=blocked` and `payment.safeToMutate=false`.

Missing Cognito configuration returns `cognitoEmail.classification=blocked`.

Production Cognito email delivery returns `liveDelivery.classification=blocked` until an approved inbox and production delivery smoke evidence are recorded.
