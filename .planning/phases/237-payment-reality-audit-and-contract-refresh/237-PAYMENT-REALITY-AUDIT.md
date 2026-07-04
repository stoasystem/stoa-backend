# Phase 237 Payment Reality Audit

## Backend Reality

| Area | Files | Current state | v5.13 implication |
|------|-------|---------------|-------------------|
| Parent subscription summary | `src/stoa/routers/parents.py`, `src/stoa/services/subscription_service.py` | Implemented through `/parents/me/subscription`, `/parents/me/subscription/billing`, checkout, and request APIs. | Phase 238 should make frontend paid-state use these real APIs. |
| Checkout/session creation | `subscription_service.create_checkout_session` | Implemented with provider readiness gates, Stripe/TWINT mode, local checkout event, provider lookup rows, and `checkout_pending` billing record. | Keep; ensure frontend uses this path instead of legacy `/billing/checkout-session`. |
| Stripe webhook route | `src/stoa/routers/billing.py` | Implemented as `/billing/webhooks/stripe` with raw body and signature header. | Phase 239 should verify reconciliation edge cases and support-visible failure states. |
| Provider event dedupe | `subscription_service.handle_stripe_webhook`, `_provider_event_seen`, `_apply_billing_transition` | Event dedupe exists with billing event rows and provider lookup rows. | Phase 239 should harden tests for duplicate, stale, missing context, and manual override interactions. |
| Entitlement resolution | `src/stoa/services/entitlement_service.py` | Implemented for active provider billing, manual override, checkout pending, failed/past-due, canceled, parent profile, student profile, and free tier. | Phase 239 must ensure reconciliation updates produce matching usage-limit behavior. |
| Account operations | `src/stoa/services/account_operations_service.py` | Parent/admin operations compose billing, entitlement, verification, and usage. | Phase 240 should expand support-safe billing evidence if fields are missing. |
| Admin billing visibility | `src/stoa/routers/admin.py`, `subscription_service.list_admin_billing`, `get_admin_billing` | Implemented for list/detail/provider readiness/rollout/accounting/refund APIs. | Phase 240 should expose missing frontend fields and lifecycle states. |
| Refunds and rollout controls | `subscription_service.execute_billing_refund`, rollout helpers | Implemented behind rollout and live-key gates with idempotency. | Phase 240 should verify support evidence and UI visibility. |

## Frontend Reality

| Area | Files | Current state | v5.13 implication |
|------|-------|---------------|-------------------|
| Legacy billing page | `/Users/zhdeng/stoa-frontend/src/pages/billing/BillingPage.tsx` | Uses `useBillingPlansQuery`, `useBillingUsageQuery`, `useFeatureAccessQuery`, `useSubscriptionQuery` from legacy billing API. | Must be rewired or clearly retired in Phase 238. |
| Legacy billing API | `/Users/zhdeng/stoa-frontend/src/services/billing/billingApi.ts` | Calls `/billing/plans`, `/billing/subscription`, `/billing/usage`, `/billing/feature-access`, `/billing/checkout-session` with `withDemoFallback` for reads. | Paid-access failures can be hidden. Phase 238 must remove demo fallback for paid-state decisions and use real parent subscription APIs. |
| Parent subscription operations | `/Users/zhdeng/stoa-frontend/src/services/parent/parentApi.ts`, hooks under `src/hooks/parent` | Uses real `/parents/me/subscription*` APIs. | Reuse as the canonical parent paid-state client. |
| Admin subscription UI | `AdminSubscriptionRequestsPage.tsx`, admin hooks/types | Uses real `/admin/subscriptions/*` APIs for request queue and provider billing visibility. | Phase 240 should enrich lifecycle evidence and edge-state display. |
| Account operations UI | `AdminAccountOperationsPage.tsx`, `ParentAccountOperationsPage.tsx` | Shows billing, entitlement, usage, verification, and support state. | Keep as support context; add missing billing lifecycle evidence if needed. |

## Contract Decisions

- Canonical parent paid-state source: `/parents/me/subscription` and `/parents/me/subscription/billing`.
- Canonical parent checkout source: `/parents/me/subscription/checkout`.
- Canonical admin support evidence source: `/admin/subscriptions/billing*` plus account operations detail.
- Legacy `/billing/*` frontend API is not allowed to decide paid access after Phase 238.
- Demo fallback is not allowed for paid-state, checkout, entitlement, or billing-support decisions.
- Manual override remains valid but must be visibly distinct from provider-backed entitlement.

## Phase 238 First Target

Rewire parent-facing checkout/paywall surfaces to real parent subscription APIs and remove demo fallback from paid-state decisions. Keep the UI narrow: real status, plan/action selection, checkout link, blocked/error states, and entitlement/usage explanation.

## Externally Blocked

- Live Stripe charges.
- Registered production webhook smoke.
- TWINT production capability approval.
- Finance acceptance and explicit rollout enablement.
