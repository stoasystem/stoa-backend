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

Goal: move the local Stripe-first payment provider MVP toward controlled live rollout, Stripe-backed TWINT inclusion, operator-ready billing operations, and payment release evidence with explicit rollout controls.

## Phases

**Phase Numbering:**

- Integer phases continue across milestones.
- Decimal phases are reserved for urgent insertions and marked INSERTED.

- [x] **Phase 144: Live Payment Rollout Contract And Credential Readiness** - Defined the live Stripe rollout contract, explicit TWINT inclusion, smoke boundaries, and rollback switches before enabling production payment behavior.
- [x] **Phase 145: Production Checkout, Webhook, And TWINT-Capable Stripe Gating** - Added production checkout/webhook primitives, livemode gating, and Stripe-backed TWINT eligibility handling for Swiss subscription flows.
- [ ] **Phase 146: Billing Operations, Invoices, Refunds, Dunning, And Swiss Handoff** - Add post-checkout billing operations and accounting-facing lifecycle support inside the same Stripe billing model, including TWINT behavior.
- [ ] **Phase 147: v4.4 Payment Release Gate, Rollout Controls, And Support Audit** - Capture rollout evidence, verify rollback/disable controls, update planning docs, and close the milestone with an explicit remaining-work audit.

## Phase Details

### Phase 144: Live Payment Rollout Contract And Credential Readiness

**Goal**: Define the live payment rollout contract, provider credential path, production smoke boundaries, and implementation targets before payment code changes.
**Depends on**: v4.3 closeout and v3.9 payment provider MVP
**Requirements**: PAYLIVE-01
**Success Criteria** (what must be TRUE):

  1. Implementers and operators can point to the exact Stripe live credential path, webhook endpoint, product and price mapping, environment variables, and rollback switches needed for rollout.
  2. TWINT is explicitly defined as an in-scope Stripe-backed payment method for v4.4, with required account or capability checks and any remaining rollout blockers recorded.
  3. Safe smoke modes distinguish local or test verification, approved live configuration inspection, and the default no-real-charge posture.
  4. Existing checkout, status, and webhook code paths plus remaining gap docs are mapped to Phases 145 through 147 so v4.4 is the active payment rollout build area.

**Plans**: 1/1 plans complete

Plans:

- [x] 144-01: Define live payment rollout, Stripe credential, and TWINT gating contract.

### Phase 145: Production Checkout, Webhook, And TWINT-Capable Stripe Gating

**Goal**: Make checkout and webhook paths production-ready with livemode-aware Stripe primitives, explicit rollout gating, and TWINT-capable Swiss subscription handling.
**Depends on**: Phase 144
**Requirements**: PAYLIVE-02
**Success Criteria** (what must be TRUE):

  1. Checkout session creation clearly distinguishes local or test behavior, live-ready-but-blocked state, and explicitly enabled live rollout before any subscription flow can proceed.
  2. Eligible Swiss and CHF subscription flows use Stripe Checkout configuration that can surface TWINT when account capability and rollout gates allow it.
  3. Webhook processing records provider mode, event type, processing result, idempotency status, and request or correlation identifiers that operators can inspect without provider secrets.
  4. Admin billing status surfaces and focused tests cover livemode gating, webhook idempotency, failure states, and non-live fallback behavior.

**Plans**: 1/1 plans complete

Plans:

- [x] 145-01: Implement production checkout, webhook, and TWINT-capable Stripe gating primitives.

### Phase 146: Billing Operations, Invoices, Refunds, Dunning, And Swiss Handoff

**Goal**: Add first-pass billing operations readiness for post-checkout support, finance handoff, and TWINT lifecycle behavior inside the shared Stripe billing model.
**Depends on**: Phase 145
**Requirements**: PAYLIVE-03
**Success Criteria** (what must be TRUE):

  1. Operators can determine refund eligibility, required inputs, provider handoff state, and audit or status fields for billed subscriptions, including TWINT-originated charges handled through Stripe.
  2. Parents and admins can access provider-hosted invoice or receipt links plus the billing metadata needed to understand the subscription lifecycle.
  3. Billing exports include Swiss accounting handoff fields for invoices, refunds, taxes, reconciliation identifiers, and payment-method context from the same Stripe model.
  4. Past-due, payment-failed, retry, recovery, and escalation boundaries are visible to parents and admins, including TWINT lifecycle behavior where Stripe projects the same subscription into dunning or refund states.

**Plans**: 0/1 plans complete

Plans:

- [ ] 146-01: Implement billing operations, Swiss handoff, and TWINT lifecycle readiness.

### Phase 147: v4.4 Payment Release Gate, Rollout Controls, And Support Audit

**Goal**: Close v4.4 with payment-focused verification, explicit rollout and rollback controls, and an updated remaining-feature audit.
**Depends on**: Phase 146
**Requirements**: VERIFY-27
**Success Criteria** (what must be TRUE):

  1. Focused backend tests and relevant static checks pass, or any pre-existing failures are isolated and documented in the release evidence.
  2. Release evidence captures provider configuration state, checkout and webhook verification, billing operations outcomes, and explicit live-charge deferral or approval status.
  3. Operators have verified rollback, disable, and controlled rollout entry points for live charging before the milestone can be considered closed.
  4. Requirements, roadmap, state, feature-gap docs, and the remaining-feature queue reflect the shipped v4.4 scope and any unresolved payment or TWINT blockers.

**Plans**: 0/1 plans complete

Plans:

- [ ] 147-01: Verify v4.4, rollout controls, and payment release evidence.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 144 Live Payment Rollout Contract And Credential Readiness | v4.4 | 1/1 | Complete | 2026-06-11 |
| 145 Production Checkout, Webhook, And TWINT-Capable Stripe Gating | v4.4 | 1/1 | Complete | 2026-06-11 |
| 146 Billing Operations, Invoices, Refunds, Dunning, And Swiss Handoff | v4.4 | 0/1 | Planned | - |
| 147 v4.4 Payment Release Gate, Rollout Controls, And Support Audit | v4.4 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PAYLIVE-01 | Phase 144 | Complete |
| PAYLIVE-02 | Phase 145 | Complete |
| PAYLIVE-03 | Phase 146 | Planned |
| VERIFY-27 | Phase 147 | Planned |

---
*Last updated: 2026-06-11 after completing Phase 145 production checkout and webhook gating*
