---
phase: 237
name: Payment Reality Audit And Contract Refresh
status: complete
created: 2026-07-05
completed: 2026-07-05
---

# Phase 237 Context: Payment Reality Audit And Contract Refresh

## Milestone

v5.13 Payment And Entitlement Production Completion

## Phase Boundary

Define the exact paid-access implementation contract from current backend/frontend behavior and prior readiness milestones. This phase does not change runtime behavior; it prevents v5.13 from assuming older payment readiness equals working end-to-end paid access.

## Key Findings

- Backend provider-managed subscription billing is substantially implemented in `src/stoa/services/subscription_service.py`, `src/stoa/routers/parents.py`, `src/stoa/routers/admin.py`, and `src/stoa/routers/billing.py`.
- Effective entitlement resolution is implemented in `src/stoa/services/entitlement_service.py` and already distinguishes `provider_billing`, `manual_override`, profile tiers, free tier, and blocked billing states.
- Parent/admin account operations compose billing, entitlement, verification, and usage through `src/stoa/services/account_operations_service.py`.
- Frontend has two payment surfaces:
  - Legacy `/billing` page and `src/services/billing/billingApi.ts` still call old `/billing/*` routes with demo fallback.
  - Subscription operations use real `/parents/me/subscription*` and `/admin/subscriptions/*` APIs through `parentApi.ts` and `adminApi.ts`.
- v5.13 implementation should first retire or rewire the legacy billing surface so paid-state failures are not hidden behind demo fallback.

## Authorization And Privacy Boundary

- Parent subscription APIs must remain parent-only.
- Admin billing/support APIs must remain admin-only and support-safe.
- Raw provider secrets, full webhook payloads, payment method details, and sensitive customer data must not reach frontend/admin evidence.

## External Blockers

Live Stripe/TWINT smoke remains blocked unless approved production provider credentials, webhook endpoint registration, TWINT approval, finance acceptance, and explicit rollout enablement are available.
