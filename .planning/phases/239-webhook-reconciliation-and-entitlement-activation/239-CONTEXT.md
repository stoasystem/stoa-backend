# Phase 239 Context: Webhook Reconciliation And Entitlement Activation

**Milestone:** v5.13 Payment And Entitlement Production Completion
**Requirement:** PAYPROD-03 Webhook Reconciliation And Entitlement Activation
**Status:** Complete
**Date:** 2026-07-05

## Starting Point

The backend already supported Stripe webhook ingestion, checkout-session correlation, invoice-paid activation, refund metadata, failed-payment dunning, manual override protection, and provider lookup rows. Existing tests covered the happy activation path, duplicate acknowledgement, failed payment, refunds, checkout expiration, and signature enforcement.

Phase 239 focused on reconciliation edges that could still make support evidence incomplete or allow an older provider event to regress current paid state.

## Scope

- Make duplicate provider events support-visible, not only acknowledged.
- Ignore stale provider events that are older than the current billing record's last provider event.
- Preserve current billing status, entitlement tier, and parent profile subscription tier when stale events arrive.
- Include processing result in webhook responses and event history.
- Add focused regression coverage for duplicate evidence and stale event ordering.

## Code References

- `src/stoa/services/subscription_service.py`
- `src/stoa/routers/billing.py`
- `tests/test_subscription_operations.py`

## Out Of Scope

- Live Stripe/TWINT smoke with production credentials.
- Full provider backfill/replay dashboard.
- Admin UI expansion for invoice/refund/cancellation evidence; this moves to Phase 240.
