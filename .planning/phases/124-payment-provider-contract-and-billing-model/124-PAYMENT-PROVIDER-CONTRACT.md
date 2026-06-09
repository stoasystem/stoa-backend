# Payment Provider Contract: v3.9

## Provider Scope

Initial provider:

- Stripe subscriptions in sandbox/test mode for internal development.
- TWINT readiness through Stripe-supported payment method configuration where available.

Live production charging is not enabled by default. It requires approved provider credentials, configured products/prices, and explicit rollout approval.

## Plan Mapping

STOA tiers:

- `free`
- `standard`
- `premium`

Provider mapping:

- `standard` maps to a recurring provider price for the standard monthly plan.
- `premium` maps to a recurring provider price for the premium monthly plan.
- `free` has no provider subscription and remains locally managed.

## Local Billing State

Subscription states:

- `none`
- `checkout_pending`
- `active`
- `past_due`
- `canceled`
- `payment_failed`
- `manual_override`
- `provider_unknown`

Minimum local fields:

- `user_id`
- `subscription_tier`
- `billing_provider`
- `billing_mode`
- `billing_status`
- `provider_customer_id`
- `provider_subscription_id`
- `provider_price_id`
- `checkout_session_id`
- `current_period_start`
- `current_period_end`
- `cancel_at_period_end`
- `last_provider_event_id`
- `last_provider_event_type`
- `last_provider_event_at`
- `updated_at`

## Webhook Mapping

Initial event categories:

- checkout completed.
- subscription created/updated/deleted.
- invoice paid.
- invoice payment failed.
- provider customer updated.

Webhook handling must be idempotent by provider event id and must not downgrade a manual override unless the provider-managed subscription is explicitly reattached.

## Parent UX Contract

- Parent can view current local plan and provider billing status.
- Parent can start checkout for `standard` or `premium`.
- Parent sees checkout return/cancel states.
- Parent sees payment failure/past-due states without needing admin tools.

## Admin UX Contract

- Admin can see local tier, billing provider, provider status, last event summary, and manual override context.
- Admin can keep using manual tier override while provider integration is being rolled out.
- Admin UI should make provider-managed versus manual subscriptions visually distinct.

## Functional Verification Priorities

- Checkout session creation validates plan and role.
- Webhook lifecycle updates local subscription state idempotently.
- Manual override compatibility is preserved.
- Parent/admin UI uses backend billing state and distinguishes manual/provider paths.
