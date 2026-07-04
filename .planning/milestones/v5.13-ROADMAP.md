# Roadmap: v5.13 Payment And Entitlement Production Completion

**Status:** Active
**Created:** 2026-07-05
**Prior milestone:** v5.12 Curriculum Editor And Content Migration Buildout

## Goal

Make paid access work as a real product flow instead of only backend readiness: checkout/session creation, provider webhook reconciliation, entitlement activation, usage-limit enforcement, admin support visibility, refund/invoice state, and release evidence.

## Why This Is The Current Milestone

v5.6 created effective entitlement and quota enforcement foundations, v5.7/v5.11 expanded usage accounting, and earlier payment milestones added provider readiness. Those pieces still need a fresh product-level closeout so user-facing paid access, provider events, entitlement state, quota behavior, and support evidence agree end to end.

This is a new business-critical product milestone, not a continuation of v5.12 curriculum work.

## Current Reality To Verify

- Backend has entitlement, subscription, usage ledger, account operations, and admin support primitives from prior milestones.
- Frontend has account operations and subscription surfaces, but v5.13 must verify they use real paid-state APIs and do not hide failures behind demo fallback.
- Live Stripe/TWINT activation remains externally gated unless credentials and rollout approval are available.
- Manual override remains a support path, not a replacement for provider-backed paid access.

## Implementation Strategy

- Start with a reality audit and contract refresh before changing code.
- Implement the smallest complete paid-access loop before provider edge cases.
- Treat provider webhooks as source-of-truth events and reconcile idempotently.
- Keep manual admin override visible and distinct from provider-backed entitlement.
- Add support-safe admin evidence without raw provider payloads or sensitive payment details.
- Verify locally with deterministic provider fixtures; document live smoke as blocked or completed.

## Phases

- [x] **Phase 237: Payment Reality Audit And Contract Refresh** - Map current payment, entitlement, quota, support, and frontend paid-state behavior; define the v5.13 implementation contract.
- [ ] **Phase 238: Checkout Paywall And Paid-State Integration** - Complete parent-facing checkout/paywall state against real backend subscription and entitlement APIs.
- [ ] **Phase 239: Webhook Reconciliation And Entitlement Activation** - Harden provider event ingestion/reconciliation and activate entitlements idempotently.
- [ ] **Phase 240: Billing Support Evidence And Lifecycle Edge States** - Expose support-safe invoice/refund/cancellation/manual-override/reconciliation evidence.
- [ ] **Phase 241: v5.13 Payment Production Completion Gate** - Verify backend/frontend behavior, docs, state, release evidence, and next milestone decision.

## Phase Details

### Phase 237: Payment Reality Audit And Contract Refresh

**Goal**: Define the exact paid-access implementation contract from current backend/frontend behavior and prior readiness milestones.
**Depends on**: v5.12 completion.
**Requirements**: PAYPROD-01
**Status**: Complete 2026-07-05.
**Evidence**: `.planning/phases/237-payment-reality-audit-and-contract-refresh/237-PAYMENT-REALITY-AUDIT.md`, `.planning/phases/237-payment-reality-audit-and-contract-refresh/237-SUMMARY.md`, `.planning/phases/237-payment-reality-audit-and-contract-refresh/237-VERIFICATION.md`.
**Success Criteria**:

1. Current backend checkout, provider event, subscription, entitlement, usage-limit, and admin support code paths are mapped to files/routes/services.
2. Current frontend checkout/paywall/subscription/account-operations behavior is mapped to clients, routes, demo fallback boundaries, and missing states.
3. Implemented, stubbed, locally verified, and externally blocked behavior is separated in an evidence table.
4. v5.13 scope, out-of-scope live activation, and release evidence expectations are documented.

### Phase 238: Checkout Paywall And Paid-State Integration

**Goal**: Make parent-facing checkout and paid-state surfaces reflect real backend state.
**Depends on**: Phase 237.
**Requirements**: PAYPROD-02
**Status**: Planned.
**Success Criteria**:

1. Parent-facing subscription/paywall surfaces load real checkout, subscription, entitlement, and quota state without silent demo fallback for paid access.
2. Pending, active, failed, canceled, refunded, and manual-override states render clearly with next actions.
3. Backend exposes any missing status fields needed by frontend paid-state and support handoff.
4. Focused frontend/backend tests cover checkout status, entitlement visibility, failure rendering, and manual override distinction.

### Phase 239: Webhook Reconciliation And Entitlement Activation

**Goal**: Ensure provider events activate and reconcile entitlements exactly once.
**Depends on**: Phase 238.
**Requirements**: PAYPROD-03
**Status**: Planned.
**Success Criteria**:

1. Provider event identity, storage, reconciliation status, and entitlement activation are idempotent.
2. Successful payment activates the correct linked-student entitlement exactly once.
3. Duplicate, stale, failed, refunded, canceled, missing-context, and conflicting events are support-visible.
4. Entitlement state and usage-limit checks agree after reconciliation.
5. Focused backend tests cover event ordering, duplicate delivery, stale state, missing context, and manual override interaction.

### Phase 240: Billing Support Evidence And Lifecycle Edge States

**Goal**: Give support/admin enough bounded evidence to diagnose paid-access failures.
**Depends on**: Phase 239.
**Requirements**: PAYPROD-04
**Status**: Planned.
**Success Criteria**:

1. Admin/support APIs expose bounded payment, entitlement, invoice, refund, cancellation, and reconciliation metadata.
2. Frontend admin/support surface renders provider-backed versus manual entitlement state distinctly.
3. Raw provider secrets, full payloads, payment method details, and sensitive customer data are excluded.
4. Focused tests cover support evidence for active, failed, refunded, canceled, pending, and manual-override states.

### Phase 241: v5.13 Payment Production Completion Gate

**Goal**: Close v5.13 with evidence that paid access is locally complete and externally blocked items are explicit.
**Depends on**: Phase 240.
**Requirements**: VERIFY-47
**Status**: Planned.
**Success Criteria**:

1. Focused backend tests pass for checkout, reconciliation, entitlement activation, usage-limit compatibility, and support evidence.
2. Frontend lint/build and focused e2e pass for paid-state and admin billing evidence workflows.
3. Live provider smoke is recorded as blocked or completed based on credential and rollout availability.
4. Docs, roadmap, requirements, state, remaining-feature audit, and milestone evidence are updated.
5. Next milestone recommendation is explicit and separates verification/login reliability from usage/quota/product stability.

## Future Milestone Directions

- **v5.14 Verification And Login Reliability**: email verification, login-code/passwordless policy, resend limits, delivery observability, abuse controls, and support recovery.
- **v5.15 Usage, Quota, And Product Stability**: usage metering gaps, quota reconciliation, user-visible usage explanations, support views, health checks, and regression gates.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 237 Payment Reality Audit And Contract Refresh | v5.13 | 1/1 | Complete | 2026-07-05 |
| 238 Checkout Paywall And Paid-State Integration | v5.13 | 0/1 | Active | - |
| 239 Webhook Reconciliation And Entitlement Activation | v5.13 | 0/1 | Planned | - |
| 240 Billing Support Evidence And Lifecycle Edge States | v5.13 | 0/1 | Planned | - |
| 241 v5.13 Payment Production Completion Gate | v5.13 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PAYPROD-01 | Phase 237 | Complete |
| PAYPROD-02 | Phase 238 | Active |
| PAYPROD-03 | Phase 239 | Planned |
| PAYPROD-04 | Phase 240 | Planned |
| VERIFY-47 | Phase 241 | Planned |
