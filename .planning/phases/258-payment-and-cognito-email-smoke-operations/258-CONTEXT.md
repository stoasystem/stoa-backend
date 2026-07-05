# Phase 258 Context: Payment And Cognito Email Smoke Operations

## Scope

Phase 258 turns the payment and account-entry provider activation state into a release-readable smoke contract. It does not enable live customer-impacting mutations by default.

## Existing Surfaces

- Stripe/TWINT readiness already exists at `GET /admin/subscriptions/billing/provider-readiness`.
- Payment rollout controls already exist at `GET/PATCH /admin/subscriptions/billing/rollout-controls`.
- Stripe webhook processing already records bounded billing event evidence.
- Cognito-backed registration and verification policy is modeled in `account_verification_service`.
- Account verification support state already exists at `GET /admin/account-verification/{user_id}`.

## Decisions

- Reuse payment provider readiness instead of duplicating Stripe checks.
- Add a combined admin smoke endpoint for release operations, not a customer-facing endpoint.
- Treat payment smoke as read-only unless checkout/refund rollout and live readiness explicitly allow mutation.
- Treat Cognito local policy behavior as locally verifiable, while production email delivery remains blocked until approved test inbox and delivery evidence are recorded.
- Return redacted state only: no API keys, webhook secrets, raw provider payloads, or login codes.

## Blocked-State Contract

- Missing live payment config must return `blocked` and `safeToMutate=false`.
- Live-ready payment without rollout approval must return `read_only_verifiable`.
- Missing Cognito pool/client config must return `blocked`.
- Configured Cognito policy without production delivery proof must return `locally_ready` plus explicit live-delivery blockers.
