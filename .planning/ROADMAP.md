# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.0-ROADMAP.md`.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.1-ROADMAP.md`.
- [x] **v1.2 S3 Report Artifact Infrastructure** - Shipped 2026-06-04 after live AWS verification. Record: `.planning/milestones/s3-report-artifact-infrastructure.md`.
- [x] **v1.3 Report Artifact Security & Operations Hardening** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.3-ROADMAP.md`.
- [x] **v1.4 Report Operations Admin UI / Bulk Recovery** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.4-ROADMAP.md`.
- [x] **v1.5 Report Recovery Production Rollout & Live Smoke** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.5-ROADMAP.md`.

## Current Milestone

### v1.6 Report Recovery Operations Hardening

**Milestone Goal:** Make report recovery safe for incident-wide operations by adding async bulk recovery, immutable audit evidence, production admin browser smoke, and CI/CD protection against stale Lambda package deployments.

This milestone hardens the v1.5 report operations platform for broader incidents. It defines the recovery contract and Lambda package guard first, adds append-only recovery audit evidence, builds bounded async resend jobs, exposes the job/audit workflow to admins, and closes with runbook, release-gate, and live verification evidence.

## Phases

**Phase Numbering:**

- Integer phases continue from previous milestones.
- v1.5 ended at Phase 32, so v1.6 starts at Phase 33.
- Decimal phases are reserved for urgent insertions.

- [ ] **Phase 33: Recovery Contract, CDK Readiness, And Dist Guard** - Define the v1.6 recovery contract, prove CDK readiness, and block stale Lambda package deployment paths.
- [ ] **Phase 34: Recovery Service Extraction And Audit Foundation** - Make existing recovery actions use shared service paths and append-only audit evidence.
- [ ] **Phase 35: Async Resend Job Backend** - Add bounded async `email_failed` resend jobs with stable targets, progress, cancellation, results, and worker execution.
- [ ] **Phase 36: Admin Job/Audit UI And Production Browser Smoke** - Expose job/audit workflows in the admin UI and verify the deployed route with read-only production browser smoke.
- [ ] **Phase 37: Runbook, Release Gate, And Live Verification** - Update operations guidance, release evidence, live verification, and final milestone audit.

## Phase Details

### Phase 33: Recovery Contract, CDK Readiness, And Dist Guard

**Goal**: Operators and implementers have a precise v1.6 recovery contract, proven infrastructure readiness, and a fail-fast guard against stale Lambda package deployments.
**Depends on**: Phase 32
**Requirements**: GUARD-01, GUARD-02, GUARD-03, GUARD-04, GUARD-05
**Success Criteria** (what must be TRUE):

1. Operators can read the v1.6 recovery contract covering job types, state transitions, target snapshots, stop conditions, cancellation semantics, privacy boundaries, and audit guarantees before backend implementation starts.
2. CDK readiness evidence shows whether the existing `stoa-api`, `stoa-weekly-report`, DynamoDB table, SES permissions, S3 buckets, and Cognito admin authorization support the MVP or names the exact required CDK changes.
3. Lambda package builds produce `dist/.stoa-build-manifest.json` with source provenance, dependency hash, runtime target, platform/architecture, build timestamp, and handler inventory.
4. CDK synth/diff/deploy and CI fail fast when backend Lambda `dist` is missing, stale, built for the wrong runtime/platform, or missing expected handlers/modules.
5. Operators have an explicit documented emergency override for the stale-dist guard that is auditable and disabled by default.

**Plans**: TBD

### Phase 34: Recovery Service Extraction And Audit Foundation

**Goal**: Existing recovery actions produce shared, append-only audit evidence without exposing private report artifacts or drifting into duplicated recovery logic.
**Depends on**: Phase 33
**Requirements**: AUDIT-01, AUDIT-02, AUDIT-03, AUDIT-04
**Success Criteria** (what must be TRUE):

1. Existing single retry, single resend, and selected bulk resend actions write append-only audit events alongside existing mutable report summary fields.
2. Audit events record actor, action, reason, targets, before/after recovery metadata, result, redacted errors, timestamps, request/job correlation IDs, and source surface.
3. Attempts to overwrite existing audit events are rejected, audit records have no TTL, and documentation states that v1.6 immutability is application-enforced rather than compliance-grade WORM storage.
4. Admin-only audit read APIs expose report-local and job-local timelines as metadata-only responses.
5. Audit API responses omit private S3 keys, raw report JSON/HTML, presigned URLs, auth tokens, and customer-sensitive browser artifacts.

**Plans**: TBD

### Phase 35: Async Resend Job Backend

**Goal**: Admins can run bounded async `email_failed` resend jobs with fixed targets, observable progress, cancellation, per-target results, and audit-backed worker execution.
**Depends on**: Phase 34
**Requirements**: JOB-01, JOB-02, JOB-03, JOB-04, JOB-05, JOB-06, JOB-07, JOB-08, JOB-09, AUDIT-05
**Success Criteria** (what must be TRUE):

1. Admin can create a dry-run `resend_email` preview from explicit filters and required reason, then see eligible/refused/missing counts and metadata-only sample rows before mutation.
2. Admin can create a bounded async resend job only after preview confirmation, and the job persists a stable target snapshot with durable state, counters, and timestamps.
3. The API Lambda invokes the weekly report Lambda asynchronously for recovery work, and the worker rereads targets, rechecks eligibility, conditionally claims resend work, and records per-target outcomes.
4. Job execution enforces conservative caps for target count, page count, Lambda time remaining, failure threshold, SES pacing, and root-cause stop conditions.
5. Admin can request cooperative cancellation, and backend/infra tests cover job APIs, idempotency, conditional claims, stop conditions, metadata-only boundaries, scoped invoke permission, and audit events for cancelled recovery paths.

**Plans**: TBD

### Phase 36: Admin Job/Audit UI And Production Browser Smoke

**Goal**: Admins can operate async recovery jobs and inspect audit evidence through the deployed admin UI, with read-only production browser smoke proving route, auth, and privacy behavior.
**Depends on**: Phase 35
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05
**Success Criteria** (what must be TRUE):

1. Admin report operations UI lets admins preview `email_failed` resend scope, enter a reason, start a job, poll progress, view results, and request cancellation.
2. Admin UI shows report and job audit timelines with precise labels for immutable evidence, mutable triage fields, cancellation semantics, and refused/failed target outcomes.
3. Frontend API services and e2e tests verify job/audit workflows, role boundaries, metadata-only rendering, and absence of private artifact markers.
4. Production admin browser smoke uses a real existing admin session or approved secret-backed credential path without creating temporary production admin accounts.
5. Production browser smoke is read-only by default, verifies route/API/auth/privacy behavior, redacts evidence artifacts, and does not mutate customer reports.

**Plans**: TBD
**UI hint**: yes

### Phase 37: Runbook, Release Gate, And Live Verification

**Goal**: Operators have v1.6 procedures, release-gate evidence, live verification outputs, and a final audit proving the hardened recovery workflow is ready.
**Depends on**: Phase 36
**Requirements**: OPS-01, OPS-02, OPS-03, OPS-04
**Success Criteria** (what must be TRUE):

1. Report recovery runbook explains async job creation, preview review, cancellation, stop conditions, audit lookup, stalled job handling, SES/Lambda/DynamoDB observability, and escalation.
2. Release checklist records Lambda build manifest evidence, backend source provenance, Lambda CodeSha/source evidence, CDK diff/deploy evidence, and stale-dist guard results.
3. Live verification proves admin-only job/audit APIs, read-only production browser smoke, metadata-only privacy boundaries, and clean CDK diff/deploy state.
4. Final milestone audit records implementation evidence, research decisions, live verification outputs, residual risks, and deferred follow-up work.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 33 -> 34 -> 35 -> 36 -> 37

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 33. Recovery Contract, CDK Readiness, And Dist Guard | v1.6 | 0/TBD | Ready for planning | - |
| 34. Recovery Service Extraction And Audit Foundation | v1.6 | 0/TBD | Not started | - |
| 35. Async Resend Job Backend | v1.6 | 0/TBD | Not started | - |
| 36. Admin Job/Audit UI And Production Browser Smoke | v1.6 | 0/TBD | Not started | - |
| 37. Runbook, Release Gate, And Live Verification | v1.6 | 0/TBD | Not started | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| GUARD-01 | Phase 33 | Pending |
| GUARD-02 | Phase 33 | Pending |
| GUARD-03 | Phase 33 | Pending |
| GUARD-04 | Phase 33 | Pending |
| GUARD-05 | Phase 33 | Pending |
| AUDIT-01 | Phase 34 | Pending |
| AUDIT-02 | Phase 34 | Pending |
| AUDIT-03 | Phase 34 | Pending |
| AUDIT-04 | Phase 34 | Pending |
| AUDIT-05 | Phase 35 | Pending |
| JOB-01 | Phase 35 | Pending |
| JOB-02 | Phase 35 | Pending |
| JOB-03 | Phase 35 | Pending |
| JOB-04 | Phase 35 | Pending |
| JOB-05 | Phase 35 | Pending |
| JOB-06 | Phase 35 | Pending |
| JOB-07 | Phase 35 | Pending |
| JOB-08 | Phase 35 | Pending |
| JOB-09 | Phase 35 | Pending |
| UI-01 | Phase 36 | Pending |
| UI-02 | Phase 36 | Pending |
| UI-03 | Phase 36 | Pending |
| UI-04 | Phase 36 | Pending |
| UI-05 | Phase 36 | Pending |
| OPS-01 | Phase 37 | Pending |
| OPS-02 | Phase 37 | Pending |
| OPS-03 | Phase 37 | Pending |
| OPS-04 | Phase 37 | Pending |

**Coverage:**

- v1.6 requirements: 28 total
- Mapped to phases: 28
- Unmapped: 0

---
*Last updated: 2026-06-04 after v1.6 roadmap creation*
