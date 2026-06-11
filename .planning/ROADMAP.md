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
- [x] **v4.4 Live Payment Provider Rollout** - Completed local release gate 2026-06-11.

## v4.5 Support Evidence Integrations And Operations Handoff

**v4.5 Support Evidence Integrations And Operations Handoff** - Active planning.

Goal: connect existing support-safe evidence packages to approved operational destinations and add operator-visible handoff status while preserving metadata-only privacy and fail-closed external-write behavior.

## Phases

**Phase Numbering:**

- Integer phases continue across milestones.
- Decimal phases are reserved for urgent insertions and marked INSERTED.

- [x] **Phase 148: Support Destination Contract And Credential Readiness** - Define approved destination modes, credential/config readiness, metadata-only payload rules, attachment limits, and refusal behavior. (completed 2026-06-12)
- [x] **Phase 149: Support Evidence Export Destination Integration** - Implement a credential-gated delivery service and one approved destination adapter while retaining preview/copy/download fallback. (completed 2026-06-12)
- [ ] **Phase 150: Operator Queue And Handoff Status Visibility** - Add handoff lifecycle status, bounded filters, detail visibility, retry/refusal evidence, and admin-only queue views.
- [ ] **Phase 151: v4.5 Support Integration Release Gate** - Verify support integration behavior, refusal paths, redacted evidence, status visibility, and remaining-feature updates.

## Phase Details

### Phase 148: Support Destination Contract And Credential Readiness

**Goal**: Define the support destination contract, provider credential path, metadata-only payload rules, and refusal behavior before enabling external support writes.
**Depends on**: v4.4 closeout and existing v2.4/v2.5 support handoff package workflow
**Requirements**: SUPPORTINT-01
**Success Criteria** (what must be TRUE):

  1. Approved destination modes are enumerated, including manual modes plus candidate internal queue, shared mailbox, Zendesk, Freshdesk, and Help Scout destinations.
  2. Credential references, environment variables, secret ownership, provider account requirements, and operator approval gates are documented for the selected destination path.
  3. Readiness checks can distinguish configured, missing, refused, and dry-run-safe states without exposing secrets.
  4. Metadata-only payload, attachment, redaction, and outbound digest rules are defined so implementation cannot leak raw report artifacts or private provider data.

**Plans**: 1/1 plans complete

Plans:

- [x] 148-01: Define support destination contract and credential readiness.

### Phase 149: Support Evidence Export Destination Integration

**Goal**: Deliver a redacted support handoff package to one approved destination path with fail-closed readiness checks, idempotency, and audit/status records.
**Depends on**: Phase 148
**Requirements**: SUPPORTINT-02
**Success Criteria** (what must be TRUE):

  1. Delivery validates destination readiness and package privacy before any provider adapter call.
  2. The selected destination adapter maps only support-safe package summaries, package IDs, evidence references, tags, and approved custom fields.
  3. Delivery records capture lifecycle status, correlation IDs, idempotency key, provider object references, retry count, and redacted refusal/failure reasons.
  4. Provider failures, missing credentials, unapproved destinations, and privacy failures are recorded as failed/refused while manual fallback remains available.

**Plans**: 1/1 plans complete

Plans:

- [x] 149-01: Implement support handoff destination delivery and fallback.

### Phase 150: Operator Queue And Handoff Status Visibility

**Goal**: Give operators bounded admin visibility into support handoff delivery status, recent activity, failure/refusal reasons, and retry state.
**Depends on**: Phase 149
**Requirements**: SUPPORTINT-03
**Success Criteria** (what must be TRUE):

  1. Admin-only list/detail APIs expose recent support handoff records with bounded filters for status, destination, package ID, and date range.
  2. Operators can distinguish created, queued, sent, failed, refused, and retried handoffs with provider references where available.
  3. Retry behavior is explicit, bounded, idempotent, and unavailable for privacy-failed or unapproved destinations.
  4. Queue/status outputs do not expose raw report artifacts, secrets, authorization headers, presigned URLs, or unredacted outbound payloads.

**Plans**: 0/1 plans complete

Plans:

- [ ] 150-01: Add support handoff queue, status, and retry visibility.

### Phase 151: v4.5 Support Integration Release Gate

**Goal**: Close v4.5 with support-integration verification, privacy evidence, refusal-path checks, and updated remaining-feature planning.
**Depends on**: Phase 150
**Requirements**: VERIFY-28
**Success Criteria** (what must be TRUE):

  1. Focused backend/frontend checks pass for the selected delivery path, refusal paths, queue/status visibility, and existing manual fallback.
  2. Release evidence captures destination configuration status with secrets redacted, provider/write deferral or approval state, and privacy validation results.
  3. Tests prove unapproved destinations, missing credentials, provider failures, duplicate retries, and privacy violations fail closed.
  4. Requirements, roadmap, state, feature-gap audit, and remaining-feature queue reflect completed v4.5 scope and unresolved support integration work.

**Plans**: 0/1 plans complete

Plans:

- [ ] 151-01: Verify v4.5 support integration release gate.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 148 Support Destination Contract And Credential Readiness | v4.5 | 1/1 | Complete   | 2026-06-12 |
| 149 Support Evidence Export Destination Integration | v4.5 | 1/1 | Complete   | 2026-06-12 |
| 150 Operator Queue And Handoff Status Visibility | v4.5 | 0/1 | Planned | — |
| 151 v4.5 Support Integration Release Gate | v4.5 | 0/1 | Planned | — |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SUPPORTINT-01 | Phase 148 | Complete |
| SUPPORTINT-02 | Phase 149 | Complete |
| SUPPORTINT-03 | Phase 150 | Planned |
| VERIFY-28 | Phase 151 | Planned |

---
*Last updated: 2026-06-12 after research-first v4.5 planning.*
