---
phase: 145
plan: 145-01
status: complete
completed_at: 2026-06-11
---

# Plan 145-01 Summary: Production Checkout, Webhook, And TWINT-Capable Stripe Gating

## Completed

- Added Stripe SDK dependency wiring through `pyproject.toml`, `uv.lock`, and `requirements.txt`.
- Added Stripe/TWINT readiness configuration flags.
- Added fail-closed billing readiness states: `test`, `not_configured`, `live_ready_but_blocked`, and `live_enabled`.
- Updated checkout creation to enforce production live gates and expose redacted readiness/TWINT metadata.
- Added a lazy Stripe SDK Checkout adapter while preserving fixture-backed local/test behavior.
- Added SDK-backed webhook verification when `stripe` is installed, with the existing HMAC-compatible verifier retained as local/test fallback.
- Added provider lookup rows and lookup-first webhook parent resolution for Stripe customer, subscription, checkout session, invoice, payment intent, charge, and refund IDs.
- Enriched billing summaries/events with livemode, persisted readiness, TWINT status, selected payment method context, processing result, and idempotency evidence.
- Kept subscription entitlement changes tied to authoritative invoice/subscription events rather than checkout completion, and preserved active subscriptions when replacement checkout sessions expire.
- Required webhook signatures by default outside an explicit unsigned-test escape hatch.
- Exposed readiness/TWINT metadata through parent and admin billing surfaces.
- Added focused tests for production gate blocking, missing configuration, TWINT readiness metadata, provider lookup resolution, authoritative webhook entitlement transitions, and webhook evidence.

## Verification

- `.venv/bin/python -m pytest tests/test_subscription_operations.py`
- `.venv/bin/ruff check src/stoa/config.py src/stoa/services/subscription_service.py src/stoa/routers/parents.py src/stoa/routers/admin.py tests/test_subscription_operations.py`

## Notes For Phase 146

- Invoice, refund, dunning, and Swiss accounting handoff remain deliberately out of this phase.
- Selected payment-method context is now available for Phase 146 to include TWINT-originated lifecycle data in invoice/refund/dunning surfaces.
- Provider lookup rows are available for additional invoice, payment intent, charge, and refund IDs as Phase 146 expands event handling.
