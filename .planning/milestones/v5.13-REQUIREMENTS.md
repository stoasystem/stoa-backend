# Requirements: v5.13 Payment And Entitlement Production Completion

**Milestone:** v5.13
**Status:** Complete 2026-07-05
**Created:** 2026-07-05
**Prior milestone:** v5.12 Curriculum Editor And Content Migration Buildout

## Purpose

Make paid access work as a real product flow instead of only local/backend readiness. v5.13 must connect checkout, provider events, entitlement activation, usage-limit behavior, parent-facing paid state, and admin/support evidence into one coherent flow.

This remains an internal development milestone unless live Stripe/TWINT credentials and rollout approval are available. Local provider fixtures and deterministic reconciliation evidence are acceptable; live smoke must be documented as blocked or completed explicitly.

## Requirements

### PAYPROD-01 Payment Reality Audit

Status: Complete 2026-07-05.

Acceptance criteria:

- Current backend checkout, subscription, entitlement, usage-limit, admin billing/support, and frontend paywall behavior is mapped to concrete files and routes.
- Implemented, stubbed, demo-fallback, locally verified, and externally blocked behavior is separated in an evidence table.
- Existing payment/entitlement milestones are reconciled so readiness evidence is not mistaken for working end-to-end paid access.
- The v5.13 implementation contract identifies the smallest complete paid-access loop and the support-safe evidence needed to operate it.

### PAYPROD-02 Checkout And User Paid-State Flow

Status: Complete 2026-07-05.

Acceptance criteria:

- Parent-facing checkout/paywall state uses real backend API state and does not hide paid-access failures behind demo fallback.
- Pending, active, failed, canceled, refunded, and manual-override states render clearly for parents/support.
- Backend returns enough subscription and entitlement status for frontend access decisions, quota explanations, and support handoff.
- Checkout/session creation and paid-state refresh are compatible with existing linked-student entitlement and usage-limit behavior.

### PAYPROD-03 Webhook Reconciliation And Entitlement Activation

Status: Complete 2026-07-05.

Acceptance criteria:

- Provider events are stored and reconciled idempotently with stable event identity.
- Successful payment activates the correct entitlement exactly once.
- Duplicate, stale, missing, failed, refunded, canceled, or conflicting events produce support-visible reconciliation status.
- Entitlement state, provider subscription state, and usage-limit checks agree after reconciliation.
- Tests cover event ordering, duplicate delivery, stale state, missing checkout context, and manual override interaction.

### PAYPROD-04 Billing Support Evidence

Status: Complete 2026-07-05.

Acceptance criteria:

- Admin/support views expose bounded payment, entitlement, invoice, refund, cancellation, and reconciliation metadata.
- Raw provider secrets, full payloads, payment method details, and sensitive customer data are not exposed.
- Manual override state is visible and distinguishable from provider-backed entitlement.
- Support evidence includes enough timestamps, provider references, reconciliation status, and request IDs to diagnose paid-access failures.

### VERIFY-47 Payment Production Completion Gate

Status: Complete 2026-07-05.

Acceptance criteria:

- Focused backend tests pass for checkout, provider event reconciliation, entitlement activation, usage-limit compatibility, and admin support evidence.
- Frontend lint/build and focused e2e pass for checkout/paywall state and admin billing evidence.
- Live smoke is recorded as blocked or completed based on credential and rollout availability.
- Docs, roadmap, state, milestone snapshots, and release evidence are updated.
- Remaining externally blocked activation items are promoted to future requirements rather than hidden in completion notes.

## Out of Scope

- Switching payment providers.
- Live customer charging without approved live credentials, registered production webhook endpoint, TWINT approval, finance acceptance, and explicit rollout enablement.
- Finance/accounting exports beyond support-safe invoice/refund visibility.
- Full dunning automation beyond clear failed-payment and support state.
- Native app purchase flows.
- Broad warehouse/BI billing analytics.

## Future Milestones

- **v5.14 Verification And Login Reliability**: make email verification and login-code behavior dependable, observable, rate-limited, and supportable.
- **v5.15 Usage, Quota, And Product Stability**: make usage accounting trustworthy across real student flows, reconcile quota/ledger drift, and add health/smoke/regression gates.
- External live activation remains separate when provider credentials and rollout approvals unblock.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PAYPROD-01 | Phase 237 | Complete |
| PAYPROD-02 | Phase 238 | Complete |
| PAYPROD-03 | Phase 239 | Complete |
| PAYPROD-04 | Phase 240 | Complete |
| VERIFY-47 | Phase 241 | Complete |
