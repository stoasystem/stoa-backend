# Phase 238 Plan: Checkout Paywall And Paid-State Integration

**Milestone:** v5.13 Payment And Entitlement Production Completion
**Requirement:** PAYPROD-02
**Status:** Complete
**Date:** 2026-07-05

## Plan

1. Replace legacy `/billing/subscription`, `/billing/usage`, and `/billing/feature-access` reads with `/parents/me/subscription`.
2. Map backend `ParentSubscription.billing` and `effectiveEntitlements` into the existing billing page view models.
3. Replace hosted checkout session creation with `/parents/me/subscription/checkout`.
4. Remove paid-state demo fallback so subscription API errors surface in the UI.
5. Extend e2e coverage for both successful virtual checkout flow and subscription API failure behavior.
6. Verify frontend build/lint/e2e and backend subscription contract tests.

## Acceptance Criteria Mapping

| Acceptance Criteria | Result |
|---------------------|--------|
| Parent-facing paid state uses real backend API state | Complete. `/billing` reads `/parents/me/subscription` for subscription, usage, and feature access. |
| No silent demo fallback for paid access failures | Complete. `withDemoFallback` was removed from the billing paid-state client and e2e covers API failure rendering. |
| Pending/active/failed/canceled/manual override states are represented | Complete for parent-facing mapped state: provider/manual active maps to active, checkout pending maps to trial, canceled maps to expired, failed/past-due maps to inactive with feature blocks. Refund-specific support state remains Phase 240. |
| Backend returns enough status fields | Complete for Phase 238. Existing parent subscription response includes billing status, tier, provider references, period metadata, and effective entitlements. |
| Focused tests cover checkout and failure rendering | Complete. Billing e2e covers virtual checkout and parent subscription API failure. Backend subscription tests still pass. |
