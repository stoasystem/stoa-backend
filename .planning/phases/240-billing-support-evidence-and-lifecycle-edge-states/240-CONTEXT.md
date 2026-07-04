# Phase 240 Context: Billing Support Evidence And Lifecycle Edge States

**Milestone:** v5.13 Payment And Entitlement Production Completion
**Requirement:** PAYPROD-04 Billing Support Evidence
**Status:** Complete
**Date:** 2026-07-05

## Starting Point

Backend billing records already exposed provider status, invoice metadata, refund metadata, dunning state, accounting handoff, manual override fields, and recent events. Frontend admin views already listed provider billing records and account operations billing events.

The remaining gap was a bounded support summary that ties those fields together so support/admin users do not need to infer lifecycle, invoice/refund, dunning, manual override, and reconciliation state from raw nested provider-shaped data.

## Scope

- Add a support-safe `supportEvidence` projection to billing responses.
- Include lifecycle source, manual override status, invoice/refund summary, dunning support action, and reconciliation event counts.
- Expose duplicate and stale ignored provider event counts without raw provider payloads.
- Render support evidence in admin subscription billing detail and account operations billing evidence surfaces.

## Code References

Backend:

- `src/stoa/services/subscription_service.py`
- `src/stoa/routers/admin.py`
- `src/stoa/routers/parents.py`
- `tests/test_subscription_operations.py`

Frontend:

- `/Users/zhdeng/stoa-frontend/src/pages/admin/AdminSubscriptionRequestsPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/admin/AdminAccountOperationsPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/types/subscriptionOperations.ts`
- `/Users/zhdeng/stoa-frontend/src/types/parentAccountOperations.ts`

## Out Of Scope

- Live provider smoke.
- Raw provider payload storage or display.
- Full finance export beyond existing accounting handoff evidence.
