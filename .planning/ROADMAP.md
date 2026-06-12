# Roadmap: v4.7 Payment Production Activation And Provider Automation

**Status:** Active implementation
**Created:** 2026-06-12
**Research:** `.planning/research/SUMMARY.md`

## Goal

Turn the v4.4 payment readiness foundation into controlled production activation: approved live Stripe/TWINT credentials, provider-readiness API checks, direct refund execution, webhook registration readiness, finance handoff, and explicit rollout controls.

## Execution Bias

Build production payment activation features directly. Keep safety checks scoped to payment activation boundaries: live credentials, checkout gates, refund execution, webhook registration, and finance evidence. Do not spend this milestone on broad unrelated security testing.

## Phases

- [x] **Phase 156: Payment Production Activation Contract And Provider Readiness** - Define live credential ownership, TWINT capability validation, price mapping, webhook registration, finance acceptance, rollout gates, and provider automation targets.
- [x] **Phase 157: Live Provider Readiness API Checks** - Add admin-only readiness checks for credentials, price mapping, TWINT eligibility, webhook endpoint state, refund capability, and accounting metadata.
- [ ] **Phase 158: Direct Refund Execution And Finance Handoff** - Add controlled refund execution, idempotency, audit evidence, billing projection updates, and finance handoff export.
- [ ] **Phase 159: Production Webhook Registration And Rollout Controls** - Verify webhook registration requirements, expose rollout controls for checkout/refunds, and capture readiness evidence.
- [ ] **Phase 160: v4.7 Payment Activation Release Gate** - Verify provider readiness, refund execution, finance handoff, rollout controls, docs, and next milestone recommendation.

## Phase Details

### Phase 156: Payment Production Activation Contract And Provider Readiness

**Goal**: Define the production payment activation contract before enabling provider automation or direct refund mutation.
**Depends on**: v4.4 payment readiness foundation and v4.6 closeout
**Requirements**: PAYACT-01
**Success Criteria** (what must be TRUE):

  1. Live credential ownership, injection path, redacted validation, and blocker states are documented.
  2. Standard/Premium live price IDs, CHF expectations, TWINT customer-location/onboarding requirements, 5,000 CHF maximum, no-manual-capture behavior, and `twint_payments` capability checks are documented.
  3. HTTPS webhook endpoint registration requirements, signing secret ownership, quick 2xx handler expectations, and required event set are documented.
  4. Finance acceptance expectations for invoice/refund/tax/dunning/reconciliation evidence are documented.
  5. Phase 157 through Phase 160 implementation targets are explicit.

**Plans**: 1/1 plans complete

Plans:

- [x] 156-01: Define payment production activation and provider readiness contract.

### Phase 157: Live Provider Readiness API Checks

**Goal**: Add admin-only provider readiness checks that verify production payment setup without creating real charges by default.
**Depends on**: Phase 156
**Requirements**: PAYACT-02
**Success Criteria** (what must be TRUE):

  1. Readiness checks cover credential mode, price mapping, TWINT eligibility/capability status, webhook endpoint readiness, refund capability, and accounting metadata availability.
  2. Missing credentials, test-only credentials, pending/inactive TWINT capability, and provider API failures return redacted blocker states.
  3. Admin responses expose actionable operator status without secrets or raw provider payloads.
  4. Focused tests cover missing/test/live/provider-failure/readiness-success fixtures.

**Plans**: 1/1 plans complete

Plans:

- [x] 157-01: Implement live provider readiness API checks.

### Phase 158: Direct Refund Execution And Finance Handoff

**Goal**: Add controlled refund execution and finance handoff export.
**Depends on**: Phase 157
**Requirements**: PAYACT-03
**Success Criteria** (what must be TRUE):

  1. Refund execution requires eligible billing state, provider reference, admin authorization, operator reason, idempotency key, remaining refundable amount, and refund-window eligibility.
  2. Refund result, provider reference, lifecycle status, billing projection, and audit evidence are persisted.
  3. Finance handoff export includes invoice, refund, tax/accounting, payment method, reconciliation, and dunning metadata.
  4. Tests cover approval, refusal, idempotency, provider failure, and export shape.

**Plans**: 0/1 plans complete

Plans:

- [ ] 158-01: Implement direct refund execution and finance handoff export.

### Phase 159: Production Webhook Registration And Rollout Controls

**Goal**: Add production webhook readiness and rollout controls for checkout and refunds.
**Depends on**: Phase 158
**Requirements**: PAYACT-04
**Success Criteria** (what must be TRUE):

  1. Webhook readiness checks verify HTTPS endpoint mode, secret availability, required event subscriptions, quick 2xx handler readiness, and last observed event status.
  2. Live checkout and direct refunds can be enabled/disabled independently through explicit rollout controls.
  3. Rollout state is visible to admins without exposing secrets.
  4. Release evidence can distinguish activated, blocked, deferred, and canary-only rollout states.

**Plans**: 0/1 plans complete

Plans:

- [ ] 159-01: Implement webhook readiness and rollout controls.

### Phase 160: v4.7 Payment Activation Release Gate

**Goal**: Close v4.7 with focused verification and updated remaining-feature planning.
**Depends on**: Phase 159
**Requirements**: VERIFY-30
**Success Criteria** (what must be TRUE):

  1. Focused backend tests and relevant checks pass or isolate documented pre-existing failures.
  2. Provider readiness, refund execution, finance handoff, webhook registration, and rollout controls are verified.
  3. Docs and feature-gap audit reflect completed v4.7 scope and live activation status.
  4. Next milestone recommendation is updated from the remaining feature queue.

**Plans**: 0/1 plans complete

Plans:

- [ ] 160-01: Verify v4.7 payment activation release gate.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 156 Payment Production Activation Contract And Provider Readiness | v4.7 | 1/1 | Complete | 2026-06-12 |
| 157 Live Provider Readiness API Checks | v4.7 | 1/1 | Complete | 2026-06-12 |
| 158 Direct Refund Execution And Finance Handoff | v4.7 | 0/1 | Planned | - |
| 159 Production Webhook Registration And Rollout Controls | v4.7 | 0/1 | Planned | - |
| 160 v4.7 Payment Activation Release Gate | v4.7 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PAYACT-01 | Phase 156 | Complete |
| PAYACT-02 | Phase 157 | Complete |
| PAYACT-03 | Phase 158 | Planned |
| PAYACT-04 | Phase 159 | Planned |
| VERIFY-30 | Phase 160 | Planned |

---
*Last updated: 2026-06-12 after completing Phase 157 live provider readiness checks.*
