# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02.
- [x] **v1.2 S3 Report Artifact Infrastructure** - Shipped 2026-06-04.
- [x] **v1.3 Report Artifact Security & Operations Hardening** - Shipped 2026-06-04.
- [x] **v1.4 Report Operations Admin UI / Bulk Recovery** - Shipped 2026-06-04.
- [x] **v1.5 Report Recovery Production Rollout & Live Smoke** - Shipped 2026-06-04.
- [x] **v1.6 Report Recovery Operations Hardening** - Shipped 2026-06-05.
- [x] **v1.7 Recovery Evidence Export & Admin Credential Operations** - Shipped 2026-06-05.
- [x] **v1.8 Incident Generation Retry Jobs** - Shipped 2026-06-05.
- [x] **v1.9 Recovery Resume And Support Evidence Packages** - Shipped 2026-06-05.
- [x] **v2.0 Controlled Report Editing MVP** - Shipped 2026-06-05.
- [x] **v2.1 Report Artifact Versioning And Safe Edit Preview** - Shipped 2026-06-06.
- [x] **v2.2 Report Artifact Rollback And Safe Fixture Verification** - Shipped 2026-06-06.
- [x] **v2.3 Release Evidence Automation And Fixture Lifecycle** - Shipped 2026-06-06.
- [x] **v2.4 Support Evidence Export Destinations And Ticket Handoff** - Shipped 2026-06-07; production verification closed by v2.5.
- [x] **v2.5 Production Support Handoff Verification Closeout** - Shipped 2026-06-07.
- [x] **v2.6 Audit Retention And Immutable Evidence Readiness** - Shipped 2026-06-07.
- [x] **v2.7 Immutable Audit Storage And Legal Hold Foundation** - Shipped 2026-06-07.
- [x] **v2.8 CDK-Managed Immutable Evidence Storage Deployment** - Shipped 2026-06-07.
- [x] **v2.9 Retention Governance And Legal Hold Operations** - Complete local-only 2026-06-07; production verification closed by v3.0.
- [x] **v3.0 STOA Docs Gap Closeout And Account Intake Hardening** - Shipped 2026-06-08.
- [x] **v3.1 Teacher Reply Quality And SLA Operations** - Shipped 2026-06-08.
- [x] **v3.2 Content Moderation And Internal Operations** - Shipped 2026-06-08.
- [x] **v3.3 Subscription Operations MVP** - Completed local release gate 2026-06-08.
- [x] **v3.4 Learning Expansion Foundation** - Completed local release gate 2026-06-08.
- [x] **v3.5 Realtime And Teacher Assistance Foundation** - Completed local release gate 2026-06-08.
- [x] **v3.6 Full WebSocket Realtime Notifications** - Completed local release gate 2026-06-09.
- [x] **v3.7 AI Teacher Tools And Exercise Generation** - Completed local release gate 2026-06-09.
- [x] **v3.8 Full Curriculum Rollout** - Completed local release gate 2026-06-09.

## Current Milestone

**v3.9 Payment Provider Integration MVP** - Active.

Goal: implement subscription checkout, provider webhook billing state, parent payment UX, and admin billing visibility for the first payment-provider integration.

## Phases

- [x] **Phase 124: Payment Provider Contract And Billing Model** - Complete 2026-06-09.
- [ ] **Phase 125: Backend Checkout Subscription And Webhook APIs** - Planned.
- [ ] **Phase 126: Parent Payment UX And Admin Billing Operations** - Planned.
- [ ] **Phase 127: Functional Release Gate And Billing Audit** - Planned.

| Phase | Name | Status | Requirement |
|-------|------|--------|-------------|
| 124 | Payment Provider Contract And Billing Model | Complete | PAY-01 |
| 125 | Backend Checkout Subscription And Webhook APIs | Planned | PAY-02 |
| 126 | Parent Payment UX And Admin Billing Operations | Planned | UI-24 |
| 127 | Functional Release Gate And Billing Audit | Planned | VERIFY-22 |

## Phase Details

### Phase 124: Payment Provider Contract And Billing Model

**Goal:** Define provider scope, billing state, tier mapping, webhook lifecycle, and manual override behavior before implementation.

**Requirement:** PAY-01
**Plans:** 1/1 plans complete

**Success Criteria**:
1. Contract defines Stripe-first subscription checkout with TWINT readiness where provider configuration supports it.
2. Contract maps STOA `free`, `standard`, and `premium` tiers to provider product/price behavior.
3. Contract defines local billing fields, subscription states, provider references, billing history, and manual override interaction.
4. Contract defines webhook event mapping, idempotency behavior, sandbox/live mode boundaries, and no-live-charge safeguards.

### Phase 125: Backend Checkout Subscription And Webhook APIs

**Goal:** Add backend checkout session, billing status, webhook, and admin billing inspection APIs while preserving manual subscription operations.

**Requirement:** PAY-02
**Plans:** 0/1 plans complete

**Success Criteria**:
1. Parent users can create sandbox/test checkout sessions only for allowed STOA plans.
2. Backend stores provider customer/subscription references, mode, tier, billing status, timestamps, and last provider event metadata.
3. Webhook handler validates provider event shape, deduplicates provider events, and maps lifecycle changes into local subscription state.
4. Admin can inspect billing status, recent provider events, and manual override context.
5. Focused tests cover checkout request shape, tier validation, webhook idempotency, lifecycle transitions, and manual override compatibility.

### Phase 126: Parent Payment UX And Admin Billing Operations

**Goal:** Expose provider checkout/status to parents and billing visibility to admins through real backend APIs.

**Requirement:** UI-24
**Plans:** 0/1 plans complete

**Success Criteria**:
1. Parent subscription UI can start checkout, show current plan, show provider status, and handle return/cancel states.
2. Parent UI distinguishes manual subscription, provider-managed subscription, checkout-pending, past-due, canceled, and payment-failure states.
3. Admin billing UI shows provider status, billing event summary, provider/manual distinction, and manual override context.
4. UI uses real backend billing APIs and keeps demo/payment mock behavior clearly separated.
5. Targeted browser verification confirms parent checkout entry and admin billing visibility.

### Phase 127: Functional Release Gate And Billing Audit

**Goal:** Close v3.9 with focused backend/frontend evidence and update Phase 2 gap tracking for payment-provider integration and residual live-charge scope.

**Requirement:** VERIFY-22
**Plans:** 0/1 plans complete

**Success Criteria**:
1. Backend and frontend focused quality gates relevant to payment-provider integration pass.
2. Gap audit marks Stripe/TWINT subscription payment integration active or closed and records residual live-charge/provider-credential scope.
3. Final audit lists remaining product expansions including adaptive learning memory/automatic assignment, production WebSocket infrastructure, push/native/email notifications, mobile/multilingual polish, support integrations, and rich content authoring.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 124 | v3.9 | 1/1 | Complete | 2026-06-09 |
| 125 | v3.9 | 0/1 | Planned | - |
| 126 | v3.9 | 0/1 | Planned | - |
| 127 | v3.9 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PAY-01 | Phase 124 | Complete |
| PAY-02 | Phase 125 | Planned |
| UI-24 | Phase 126 | Planned |
| VERIFY-22 | Phase 127 | Planned |

---
*Last updated: 2026-06-09 after completing Phase 124*
