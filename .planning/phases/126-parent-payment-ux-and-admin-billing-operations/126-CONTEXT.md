# Phase 126 Context: Parent Payment UX And Admin Billing Operations

**Milestone:** v3.9 Payment Provider Integration MVP
**Requirement:** UI-24
**Status:** Complete

## Phase Boundary

Expose provider checkout/status to parents and billing visibility to admins through real backend APIs.

## Implementation Decisions

- Reuse the existing parent `ParentSubscriptionOperationsCard` rather than creating a separate payment page.
- Preserve manual subscription request UX and add provider checkout as an adjacent paid-plan path.
- Show provider-managed, manual, checkout-pending, payment-failure, and no-provider states explicitly.
- Extend the existing admin subscription request page with a provider billing visibility section instead of adding another admin route.
- Keep UI dense and operational: status badges, compact facts, event summaries, and clear manual/provider distinction.

## Existing Code Context

- Parent manual subscription UI: `src/components/parent/ParentSubscriptionOperationsCard.tsx`.
- Admin manual subscription UI: `src/pages/admin/AdminSubscriptionRequestsPage.tsx`.
- Parent subscription API hooks: `src/hooks/parent/useParentSubscriptionOperations.ts`.
- Admin subscription API hooks: `src/hooks/admin/useAdminSubscriptionRequests.ts`.

## Deferred

- Embedded checkout.
- Billing portal management.
- Refunds, invoices, dunning, tax/accounting, and live-charge rollout UX.
