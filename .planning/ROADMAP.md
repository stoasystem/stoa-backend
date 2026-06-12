# Roadmap: v4.8 Support Provider Expansion And CRM Automation

**Status:** Active planning
**Created:** 2026-06-12
**Research:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`

## Goal

Move the v4.5 support handoff foundation from an internal queue into approved provider-backed support operations: third-party adapter readiness, provider delivery workers, retry and two-way synchronization, support SLA analytics, and controlled CRM/customer messaging.

## Execution Bias

Build support operations functionality directly. Keep checks scoped to destination approval, metadata-only support evidence boundaries, retry/idempotency behavior, and customer-message controls. Do not broaden this milestone into unrelated security or compliance work during internal development.

## Phases

- [x] **Phase 161: Support Provider Expansion Contract And Adapter Readiness** - Define approved provider modes, payload boundaries, adapter readiness, ticket lifecycle, retry/sync contract, SLA inputs, and controlled messaging rules. (completed 2026-06-12)
- [x] **Phase 162: Approved Third-Party Support Adapter And Delivery Worker** - Add adapter configuration/readiness and delivery worker behavior for provider ticket creation while preserving internal queue fallback. (completed 2026-06-12)
- [x] **Phase 163: Retry Workers And Two-Way Ticket Synchronization** - Add bounded retry behavior and provider ticket status synchronization with stale/duplicate/conflict handling. (completed 2026-06-12)
- [x] **Phase 164: Support SLA Analytics And Controlled CRM Messaging** - Add support SLA aggregates, overdue/failure analytics, and template-gated customer/support messaging. (completed 2026-06-12)
- [ ] **Phase 165: v4.8 Support Provider Release Gate And Operations Audit** - Verify v4.8 behavior, update docs, record provider activation state, and select the next feature milestone.

## Phase Details

### Phase 161: Support Provider Expansion Contract And Adapter Readiness

**Goal**: Define the support provider expansion contract before adding third-party support writes or CRM automation.
**Depends on**: v4.5 support evidence integrations, v4.7 closeout, and `stoa_docs` remaining-feature audit
**Requirements**: SUPPORTPROV-01
**Success Criteria** (what must be TRUE):

  1. Approved destination modes, adapter ownership, credential path, readiness states, and refusal behavior are documented.
  2. Support-safe payload shape preserves metadata-only evidence boundaries and excludes private report artifacts or raw provider payloads.
  3. Ticket lifecycle, correlation IDs, dedupe keys, idempotency, retry eligibility, and two-way sync conflict rules are defined.
  4. SLA analytics inputs, aggregation windows, admin visibility, and customer-message template controls are documented.
  5. Phase 162 through Phase 165 implementation targets are explicit.

**Plans**: 0/1 plans complete

Plans:

- [x] 161-01: Define support provider expansion and adapter readiness contract.

### Phase 162: Approved Third-Party Support Adapter And Delivery Worker

**Goal**: Add controlled provider delivery for support-safe evidence packages.
**Depends on**: Phase 161
**Requirements**: SUPPORTPROV-02
**Success Criteria** (what must be TRUE):

  1. At least one approved provider adapter mode has readiness checks and redacted operator status.
  2. Delivery worker creates provider tickets or equivalent cases from support-safe evidence packages.
  3. Delivery attempts persist provider IDs, lifecycle status, correlation metadata, and redacted result evidence.
  4. Missing credentials, unapproved destination, validation failure, provider failure, and duplicate delivery are covered by tests.

**Plans**: 0/1 plans complete

Plans:

- [x] 162-01: Implement approved support adapter and delivery worker.

### Phase 163: Retry Workers And Two-Way Ticket Synchronization

**Goal**: Add retry and provider status synchronization for support deliveries.
**Depends on**: Phase 162
**Requirements**: SUPPORTPROV-03
**Success Criteria** (what must be TRUE):

  1. Failed provider deliveries are retryable with attempt limits, backoff metadata, and operator-visible status.
  2. Provider ticket state can be synchronized through webhook or polling-shaped adapters without importing raw private payloads.
  3. Stale updates, duplicates, and status conflicts are detected and surfaced.
  4. Admin support queue/detail views expose retry eligibility, sync freshness, provider state, and conflict markers.

**Plans**: 0/1 plans complete

Plans:

- [x] 163-01: Implement retry workers and two-way support ticket synchronization.

### Phase 164: Support SLA Analytics And Controlled CRM Messaging

**Goal**: Add operational SLA visibility and template-gated customer/support messaging.
**Depends on**: Phase 163
**Requirements**: SUPPORTPROV-04
**Success Criteria** (what must be TRUE):

  1. Backend computes support SLA metrics for queue, delivery, acknowledgement, first response, resolution, failure, and reopen states.
  2. Admin analytics expose overdue queues, provider failure rates, retry backlog, and message outcomes.
  3. CRM/customer messaging is limited to approved templates and support-event triggers.
  4. Send/refusal/failure evidence is persisted and correlated to support tickets.

**Plans**: 0/1 plans complete

Plans:

- [x] 164-01: Implement support SLA analytics and controlled CRM messaging.

### Phase 165: v4.8 Support Provider Release Gate And Operations Audit

**Goal**: Close v4.8 with focused verification, release evidence, and updated remaining-feature planning.
**Depends on**: Phase 164
**Requirements**: VERIFY-31
**Success Criteria** (what must be TRUE):

  1. Focused backend tests and relevant static checks pass or isolate documented pre-existing failures.
  2. Provider adapter, delivery, retry, two-way sync, SLA analytics, and controlled messaging are verified.
  3. Docs and feature-gap audit reflect completed v4.8 scope and provider activation state.
  4. Next milestone recommendation is updated from the remaining feature queue.

**Plans**: 0/1 plans complete

Plans:

- [ ] 165-01: Verify v4.8 support provider release gate.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 161 Support Provider Expansion Contract And Adapter Readiness | v4.8 | 1/1 | Complete    | 2026-06-12 |
| 162 Approved Third-Party Support Adapter And Delivery Worker | v4.8 | 1/1 | Complete    | 2026-06-12 |
| 163 Retry Workers And Two-Way Ticket Synchronization | v4.8 | 1/1 | Complete    | 2026-06-12 |
| 164 Support SLA Analytics And Controlled CRM Messaging | v4.8 | 1/1 | Complete    | 2026-06-12 |
| 165 v4.8 Support Provider Release Gate And Operations Audit | v4.8 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SUPPORTPROV-01 | Phase 161 | Complete |
| SUPPORTPROV-02 | Phase 162 | Complete |
| SUPPORTPROV-03 | Phase 163 | Complete |
| SUPPORTPROV-04 | Phase 164 | Complete |
| VERIFY-31 | Phase 165 | Planned |

---
*Last updated: 2026-06-12 after selecting v4.8 support provider expansion and CRM automation.*
