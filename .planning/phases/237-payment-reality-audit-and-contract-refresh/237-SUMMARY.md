# Phase 237 Summary: Payment Reality Audit And Contract Refresh

## Outcome

Phase 237 is complete. v5.13 now has a concrete implementation contract grounded in current backend and frontend files.

## Main Finding

The backend provider billing and entitlement foundation is stronger than the parent-facing `/billing` frontend surface. The main product gap is that `/billing` still uses legacy `/billing/*` client calls with demo fallback, while the real paid-access APIs live under `/parents/me/subscription*`.

## Contract

- Use `/parents/me/subscription` and `/parents/me/subscription/billing` as canonical parent paid-state APIs.
- Use `/parents/me/subscription/checkout` for checkout/session creation.
- Use `/admin/subscriptions/billing*` and account operations for support-safe evidence.
- Do not use demo fallback for paid-state, checkout, entitlement, or billing-support decisions.
- Keep live provider smoke gated on credentials and rollout approval.

## Next Phase

Phase 238 should rewire checkout/paywall paid-state integration to the real parent subscription APIs and focused frontend/backend tests.
