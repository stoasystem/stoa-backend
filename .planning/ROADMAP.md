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
- [x] **v1.8 Incident Generation Retry Jobs** - Shipped 2026-06-05. Archive: `.planning/milestones/v1.8-ROADMAP.md`.

## Current Milestone

### v1.9 Recovery Resume And Support Evidence Packages

**Milestone Goal:** Admins can resume failed/refused/not_found/skipped recovery subsets from prior jobs and generate support-safe incident evidence packages without exposing private report artifacts or creating unbounded scans.

This milestone builds on v1.8 by turning recovery jobs into restartable incident workflows. It deliberately reuses existing recovery job, target, audit, and evidence export resources unless implementation evidence proves a gap.

## Phases

**Phase Numbering:**

- Integer phases continue from previous milestones.
- v1.8 ended at Phase 45, so v1.9 starts at Phase 46.
- Decimal phases are reserved for urgent insertions.

- [x] **Phase 46: Resume Contract And Evidence Package Design** - Define subset resume semantics, safety bounds, audit actions, and support package schema.
- [x] **Phase 47: Failed/Skipped Subset Resume Backend** - Add backend preview/create support for resume-from-job recovery jobs.
- [x] **Phase 48: Support Evidence Package UI** - Add UI controls for resume preview/start and support evidence packages.
- [ ] **Phase 49: v1.9 Release Gate And Live Verification** - Consolidate build/deploy/CDK/API/UI evidence and production read-only smoke.

## Phase Details

### Phase 46: Resume Contract And Evidence Package Design

**Goal**: Implementers have a precise contract for creating a new recovery job from failed/refused/not_found/skipped targets of an existing job, plus a support-safe evidence package schema.
**Depends on**: Phase 45
**Requirements**: RESUME-01, EVIDENCE-01, RESUME-04
**Success Criteria** (what must be TRUE):

1. Contract defines eligible source job statuses, target result filters, inherited job type behavior, preview token binding, limits, cancellation, audit actions, and privacy boundary.
2. Support evidence package schema defines job summary, target result rollups, audit timeline, request IDs, redacted operator notes, and denylisted fields.
3. CDK readiness states whether new Step Functions, SQS, Lambda, table, bucket, or GSI resources are required.
4. Phase 47 backend plan identifies exact files and tests to change.

**Plans**: 1 complete

### Phase 47: Failed/Skipped Subset Resume Backend

**Goal**: Admins can preview and create bounded resume jobs from failed/refused/not_found/skipped targets of a prior recovery job.
**Depends on**: Phase 46
**Requirements**: RESUME-01, RESUME-02, RESUME-03, RESUME-04
**Success Criteria** (what must be TRUE):

1. Preview API returns metadata-only source target samples filtered by allowed target results.
2. Create API writes a new recovery job with `source_job_id`, inherited `job_type`, stable target snapshots, audit events, and bounded limits.
3. Existing worker execution paths can process resumed resend and generation retry jobs without new infrastructure.
4. Tests cover admin-only auth, non-admin rejection, bounds, stale preview token, no eligible targets, source job mismatch, privacy denylist, and audit linkage.

**Plans**: 1 complete

### Phase 48: Support Evidence Package UI

**Goal**: Admins can inspect failed recovery jobs, preview/start a resume job, and export a support-safe evidence package from `/admin/report-operations`.
**Depends on**: Phase 47
**Requirements**: EVIDENCE-01, EVIDENCE-02, UI-06
**Success Criteria** (what must be TRUE):

1. UI exposes resume controls only when a selected recovery job has resumable target results.
2. UI distinguishes source job, resumed job, job type, target result filters, and operator reason.
3. Support package export shows metadata-only evidence, redacted notes, request IDs, and privacy markers omitted.
4. Frontend tests cover resume preview/create, package export, disabled states, and privacy denylist.

**Plans**: 1 complete
**UI hint**: yes

### Phase 49: v1.9 Release Gate And Live Verification

**Goal**: v1.9 closes with release evidence proving subset resume and support packages are deployed, bounded, admin-only, auditable, and production-smokeable without mutation.
**Depends on**: Phase 48
**Requirements**: VERIFY-02
**Success Criteria** (what must be TRUE):

1. Release gate records Lambda build manifest, backend/frontend deploy runs, commit SHAs, Lambda runtime state, and local quality gates.
2. CDK diff/deploy evidence is recorded, with no-new-infra or exact required infra changes classified.
3. Production API checks include request IDs for health, auth gate, list jobs, and read-only support package APIs.
4. Production browser smoke verifies `/admin/report-operations` resume/support package UI without creating a production resume job.
5. Final v1.9 audit records implementation evidence, live verification, residual risks, deferred follow-up, and archive readiness.

**Plans**: 0 complete

## Progress

**Execution Order:**
Phases execute in numeric order: 46 -> 47 -> 48 -> 49

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 46. Resume Contract And Evidence Package Design | v1.9 | 1/1 | Complete | 2026-06-05 |
| 47. Failed/Skipped Subset Resume Backend | v1.9 | 1/1 | Complete | 2026-06-05 |
| 48. Support Evidence Package UI | v1.9 | 1/1 | Complete | 2026-06-05 |
| 49. v1.9 Release Gate And Live Verification | v1.9 | 0/1 | Not Started | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| RESUME-01 | Phase 46/47 | Complete |
| RESUME-02 | Phase 47 | Complete |
| RESUME-03 | Phase 47 | Complete |
| RESUME-04 | Phase 46/47/49 | In Progress |
| EVIDENCE-01 | Phase 46/48 | Complete |
| EVIDENCE-02 | Phase 48 | Complete |
| UI-06 | Phase 48 | Complete |
| VERIFY-02 | Phase 49 | Planned |

**Coverage:**

- v1.9 requirements: 8 total
- Complete: 0
- Mapped to phases: 8
- Unmapped: 0

## Next Candidates

Deferred from v1.8:

- Step Functions/SQS/new table/new bucket/new Lambda/new GSI if existing Lambda flow becomes insufficient.
- Compliance-grade WORM audit storage if legal/security requires it.
- External support ticket integration when an approved connector/credential path exists.
- Report editing, PDF generation, multilingual delivery, billing, analytics, and broader admin operations expansion.

---
*Last updated: 2026-06-05 after completing Phase 48*
