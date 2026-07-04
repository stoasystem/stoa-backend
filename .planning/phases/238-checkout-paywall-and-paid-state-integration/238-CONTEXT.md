# Phase 238 Context: Checkout Paywall And Paid-State Integration

**Milestone:** v5.13 Payment And Entitlement Production Completion
**Requirement:** PAYPROD-02 Checkout And User Paid-State Flow
**Status:** Complete
**Date:** 2026-07-05

## Starting Point

Phase 237 confirmed that backend parent subscription APIs already expose the canonical paid-state contract at `/parents/me/subscription*`, including provider billing state and effective entitlements. The remaining gap was the parent-facing `/billing` frontend surface, which still read legacy `/billing/*` endpoints through demo fallback and therefore could mask paid-access API failures.

## Scope

- Rewire `/billing` subscription, feature access, usage-limit explanation, and hosted checkout creation to the real parent subscription APIs.
- Preserve local product catalog display for pricing cards while removing demo fallback from paid-state decisions.
- Render a visible billing unavailable state when parent subscription API calls fail.
- Add focused e2e coverage that proves `/billing` no longer silently falls back to mock subscription data.

## Out Of Scope

- Live Stripe/TWINT smoke with production credentials.
- Provider event reconciliation hardening; this moves to Phase 239.
- Admin support evidence expansion; this moves to Phase 240.
- Full invoice/refund/dunning UI.

## Code References

Frontend commit:

- `/Users/zhdeng/stoa-frontend` commit `a2887e5` (`feat(238): use real parent subscription billing state`)

Touched frontend files:

- `/Users/zhdeng/stoa-frontend/src/services/billing/billingApi.ts`
- `/Users/zhdeng/stoa-frontend/src/pages/billing/BillingPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/types/subscriptionOperations.ts`
- `/Users/zhdeng/stoa-frontend/tests/e2e/billing-pricing.spec.ts`

Backend contract files verified:

- `src/stoa/routers/parents.py`
- `src/stoa/services/subscription_service.py`
- `src/stoa/services/entitlement_service.py`
- `tests/test_subscription_operations.py`
