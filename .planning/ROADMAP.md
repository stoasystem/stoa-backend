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
- [x] **v3.9 Payment Provider Integration MVP** - Completed local release gate 2026-06-09.
- [x] **v4.0 Adaptive Learning Memory And Assignment** - Completed local backend release gate 2026-06-10.
- [x] **v4.1 Mobile And Multilingual Polish Foundation** - Completed local backend release gate 2026-06-11.
- [x] **v4.2 Production Notification Delivery Readiness** - Completed local backend release gate 2026-06-11.
- [x] **v4.3 Frontend Mobile And Visual Localization Rollout** - Completed local frontend release gate 2026-06-11.

## v4.4 Live Payment Provider Rollout

**v4.4 Live Payment Provider Rollout** - Active planning.

Goal: move the local Stripe-first payment provider MVP toward controlled live rollout, production checkout/webhook readiness, refund/invoice/tax/dunning operations, and focused release evidence.

## Phases

**Phase Numbering:**

- Integer phases continue across milestones.
- Decimal phases are reserved for urgent insertions and marked INSERTED.

- [ ] **Phase 144: Live Payment Rollout Contract And Credential Readiness** - Define live credential path, provider mode, price/product mapping, TWINT status, smoke modes, and rollback switches.
- [ ] **Phase 145: Production Checkout And Webhook Verification** - Harden checkout/webhook behavior for production readiness, idempotency evidence, admin visibility, and no-real-charge fallback.
- [ ] **Phase 146: Refunds Invoices Tax And Dunning Readiness** - Add or define operator-ready refund, invoice/receipt, tax/accounting, and dunning state support.
- [ ] **Phase 147: v4.4 Payment Release Gate And Support Audit** - Verify focused payment behavior, update docs, capture evidence, and recommend the next feature milestone.

## Phase Details

### Phase 144: Live Payment Rollout Contract And Credential Readiness

**Goal**: Define the live payment rollout contract, provider credential path, production smoke boundaries, and implementation targets before payment code changes.
**Depends on**: v4.3 closeout and v3.9 payment provider MVP
**Requirements**: PAYLIVE-01
**Success Criteria** (what must be TRUE):

  1. Stripe live-mode credential path, webhook endpoint, product/price mapping, environment variables, and rollback switches are documented.
  2. TWINT production validation status and v4.4 implementation boundary are explicit.
  3. Safe smoke modes distinguish local/test-mode checks, configuration inspection, and no-real-charge default behavior.
  4. Existing checkout/status/webhook code paths are mapped to Phase 145 implementation targets.

**Plans**: 0/1 plans complete

Plans:

- [ ] 144-01: Define live payment rollout and credential readiness contract.

### Phase 145: Production Checkout And Webhook Verification

**Goal**: Make checkout and webhook paths production-ready with operator-visible lifecycle evidence.
**Depends on**: Phase 144
**Requirements**: PAYLIVE-02
**Success Criteria** (what must be TRUE):

  1. Checkout session creation exposes configured live-readiness state without accidentally charging customers.
  2. Webhook processing records provider mode, event type, result, idempotency, and request/correlation identifiers.
  3. Admin billing surfaces expose provider lifecycle status needed for internal rollout.
  4. Focused tests cover live-readiness config, idempotency, failure states, and fallback behavior.

**Plans**: 0/1 plans complete

Plans:

- [ ] 145-01: Implement production checkout and webhook verification readiness.

### Phase 146: Refunds Invoices Tax And Dunning Readiness

**Goal**: Add first-pass billing operations readiness for post-checkout support.
**Depends on**: Phase 145
**Requirements**: PAYLIVE-03
**Success Criteria** (what must be TRUE):

  1. Refund readiness contract or implementation covers eligible states, operator inputs, provider handoff, and status fields.
  2. Invoice/receipt readiness exposes provider-hosted invoice metadata where available.
  3. Tax/accounting handoff identifies exportable billing metadata for Swiss accounting workflows.
  4. Dunning readiness covers overdue/payment-failed states and parent/admin visibility.

**Plans**: 0/1 plans complete

Plans:

- [ ] 146-01: Implement refund invoice tax and dunning readiness.

### Phase 147: v4.4 Payment Release Gate And Support Audit

**Goal**: Close v4.4 with payment-focused verification and updated remaining-feature planning.
**Depends on**: Phase 146
**Requirements**: VERIFY-27
**Success Criteria** (what must be TRUE):

  1. Focused backend tests and relevant checks pass or isolate documented pre-existing failures.
  2. Payment requirements, roadmap, state, feature gap audit, and remaining-feature queue reflect completed v4.4 work.
  3. Provider configuration, webhook, checkout, refund/invoice/dunning readiness evidence is captured.
  4. Next milestone recommendation is updated from the remaining feature queue.

**Plans**: 0/1 plans complete

Plans:

- [ ] 147-01: Verify v4.4 and update release documentation.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 144 Live Payment Rollout Contract And Credential Readiness | v4.4 | 0/1 | Planned | - |
| 145 Production Checkout And Webhook Verification | v4.4 | 0/1 | Planned | - |
| 146 Refunds Invoices Tax And Dunning Readiness | v4.4 | 0/1 | Planned | - |
| 147 v4.4 Payment Release Gate And Support Audit | v4.4 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PAYLIVE-01 | Phase 144 | Planned |
| PAYLIVE-02 | Phase 145 | Planned |
| PAYLIVE-03 | Phase 146 | Planned |
| VERIFY-27 | Phase 147 | Planned |

---
*Last updated: 2026-06-11 after selecting v4.4 live payment provider rollout*
