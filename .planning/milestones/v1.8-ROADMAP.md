# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.0-ROADMAP.md`.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.1-ROADMAP.md`.
- [x] **v1.2 S3 Report Artifact Infrastructure** - Shipped 2026-06-04 after live AWS verification. Record: `.planning/milestones/s3-report-artifact-infrastructure.md`.
- [x] **v1.3 Report Artifact Security & Operations Hardening** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.3-ROADMAP.md`.
- [x] **v1.4 Report Operations Admin UI / Bulk Recovery** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.4-ROADMAP.md`.
- [x] **v1.5 Report Recovery Production Rollout & Live Smoke** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.5-ROADMAP.md`.
- [x] **v1.6 Report Recovery Operations Hardening** - Shipped 2026-06-05. Archive: `.planning/milestones/v1.6-ROADMAP.md`.
- [x] **v1.7 Recovery Evidence Export & Admin Credential Operations** - Shipped 2026-06-05. Archive: `.planning/milestones/v1.7-ROADMAP.md`.

## Current Milestone

### v1.8 Incident Generation Retry Jobs

**Milestone Goal:** Admins can run bounded async `generation_failed` recovery jobs using the existing recovery job/audit platform and weekly report Lambda without expanding production mutation scope beyond approved admin actions.

This milestone promotes the highest-value deferred recovery expansion from v1.7: incident-wide generation retry. It deliberately reuses existing Lambda, DynamoDB, Cognito, admin UI, and audit/export resources unless implementation evidence proves a gap.

## Phases

**Phase Numbering:**

- Integer phases continue from previous milestones.
- v1.7 ended at Phase 41, so v1.8 starts at Phase 42.
- Decimal phases are reserved for urgent insertions.

- [x] **Phase 42: Recovery Job Type Contract And CDK Readiness** - Prove `retry_generation` can reuse existing recovery job resources and define the job contract.
- [x] **Phase 43: Async Generation Retry Backend** - Add preview/create/execute/cancel/result/audit support for `retry_generation` jobs.
- [x] **Phase 44: Admin Generation Retry Job UI** - Add generation retry job controls to `/admin/report-operations`.
- [ ] **Phase 45: v1.8 Release Gate And Read-only Production Verification** - Consolidate build/deploy/CDK/API/UI evidence and production read-only smoke.

## Phase Details

### Phase 42: Recovery Job Type Contract And CDK Readiness

**Goal**: Implementers have a precise `retry_generation` job contract and evidence that existing resources can support the MVP.
**Depends on**: Phase 41
**Requirements**: GENJOB-01, GENJOB-04
**Success Criteria** (what must be TRUE):

1. Contract defines job type, target eligibility, preview token binding, state transitions, cancellation, stop conditions, audit actions, and privacy boundary.
2. Existing API Lambda, weekly report Lambda, DynamoDB job/target/audit records, Cognito admin auth, and admin UI route are reviewed before implementation.
3. CDK readiness states whether new Step Functions, SQS, Lambda, table, bucket, or GSI resources are required.
4. Phase 43 backend plan identifies exact files and tests to change.

**Plans**: 1 complete

### Phase 43: Async Generation Retry Backend

**Goal**: Admins can preview, create, execute, cancel, inspect, and audit bounded async `retry_generation` recovery jobs.
**Depends on**: Phase 42
**Requirements**: GENJOB-01, GENJOB-02, GENJOB-03, GENJOB-04
**Success Criteria** (what must be TRUE):

1. Preview/create APIs support `retry_generation` jobs with bounded filters and operation-bound preview tokens.
2. Weekly report worker executes `report_recovery_retry_generation` events through existing single-report retry service.
3. Job counters, statuses, target results, cancellation, failure threshold, and time-floor behavior work for generation retry jobs.
4. Tests cover admin-only auth, non-admin rejection, bounds, stale preview token, no eligible targets, success/refused/not_found/failed/skipped outcomes, audit, and privacy denylist.

**Plans**: 1 complete

### Phase 44: Admin Generation Retry Job UI

**Goal**: Admins can operate async generation retry jobs from `/admin/report-operations` without confusing them with resend jobs.
**Depends on**: Phase 43
**Requirements**: GENJOB-05
**Success Criteria** (what must be TRUE):

1. UI exposes a job type selector for resend email versus retry generation.
2. Preview/start controls call the correct backend endpoints and show operation-specific counts, labels, disabled states, and mutation warnings.
3. Job/result/audit panels render generation retry jobs and target outcomes without private artifact markers.
4. Frontend tests cover both job types, error states, and metadata-only rendering.

**Plans**: 1 complete
**UI hint**: yes

### Phase 45: v1.8 Release Gate And Read-only Production Verification

**Goal**: v1.8 closes with release evidence proving generation retry jobs are deployed, bounded, admin-only, auditable, and production-smokeable without mutation.
**Depends on**: Phase 44
**Requirements**: GENJOB-06
**Success Criteria** (what must be TRUE):

1. Release gate records Lambda build manifest, backend/frontend deploy runs, commit SHAs, Lambda runtime state, and local quality gates.
2. CDK diff/deploy evidence is recorded, with no-new-infra or exact required infra changes classified.
3. Production API checks include request IDs for health, auth gate, list jobs, and read-only UI APIs.
4. Production browser smoke verifies `/admin/report-operations` generation retry job UI without creating a production job or invoking retry mutation.
5. Final v1.8 audit records implementation evidence, live verification, residual risks, deferred follow-up, and archive readiness.

**Plans**: 0 complete

## Progress

**Execution Order:**
Phases execute in numeric order: 42 -> 43 -> 44 -> 45

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 42. Recovery Job Type Contract And CDK Readiness | v1.8 | 1/1 | Complete | 2026-06-05 |
| 43. Async Generation Retry Backend | v1.8 | 1/1 | Complete | 2026-06-05 |
| 44. Admin Generation Retry Job UI | v1.8 | 1/1 | Complete | 2026-06-05 |
| 45. v1.8 Release Gate And Read-only Production Verification | v1.8 | 0/1 | Not Started | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| GENJOB-01 | Phase 42/43 | Complete |
| GENJOB-02 | Phase 43 | Complete |
| GENJOB-03 | Phase 43 | Complete |
| GENJOB-04 | Phase 43/45 | In Progress |
| GENJOB-05 | Phase 44 | Complete |
| GENJOB-06 | Phase 45 | Planned |

**Coverage:**

- v1.8 requirements: 6 total
- Complete: 3
- Mapped to phases: 6
- Unmapped: 0

## Next Candidates

Deferred from v1.6:

- Resume failed/skipped recovery subsets as a new audit-linked job.
- Support ticket or incident note integration.
- Stronger orchestration resources if evidence requires Step Functions, SQS, a dedicated worker Lambda, a new table, a new bucket, or a new GSI.
- Compliance-grade WORM audit storage if legal/security requires it.
- Report editing, PDF generation, multilingual delivery, billing, analytics, and broader admin operations expansion.

---
*Last updated: 2026-06-05 after completing Phase 44*
