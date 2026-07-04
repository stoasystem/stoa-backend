# Phase 240 Plan: Billing Support Evidence And Lifecycle Edge States

**Milestone:** v5.13 Payment And Entitlement Production Completion
**Requirement:** PAYPROD-04
**Status:** Complete
**Date:** 2026-07-05

## Plan

1. Add a bounded billing support evidence projection to backend billing responses.
2. Include lifecycle source, manual override state, invoice/refund references, dunning support action, and reconciliation counters.
3. Keep provider secrets, full payloads, payment method details beyond type, and sensitive customer data excluded.
4. Add backend tests that verify support evidence for active provider-backed billing with duplicate and stale reconciliation events.
5. Extend frontend admin billing surfaces to display support action and reconciliation counts.
6. Verify backend tests/Ruff and frontend build/lint.

## Acceptance Criteria Mapping

| Acceptance Criteria | Result |
|---------------------|--------|
| Admin/support APIs expose bounded payment, entitlement, invoice, refund, cancellation, and reconciliation metadata | Complete. `supportEvidence` summarizes lifecycle, invoice, refund, dunning, manual override, and reconciliation counters. |
| Frontend admin/support surface renders provider-backed versus manual entitlement state distinctly | Complete. Existing provider/manual fields remain visible and Phase 240 adds support action plus duplicate/stale reconciliation counts. |
| Raw provider secrets, full payloads, payment method details, and sensitive customer data are excluded | Complete. Support evidence contains only bounded IDs, status, amounts, dates, support actions, and counters. |
| Focused tests cover support evidence for active, failed, refunded, canceled, pending, and manual-override states | Complete for focused local gate via existing billing lifecycle tests plus new support evidence assertions. Existing coverage exercises checkout pending, active, failed, refund, expired/canceled, and manual override paths. |
