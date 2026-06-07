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
- [x] **v2.3 Release Evidence Automation And Fixture Lifecycle** - Shipped 2026-06-06. Archive: `.planning/milestones/v2.3-ROADMAP.md`.
- [x] **v2.4 Support Evidence Export Destinations And Ticket Handoff** - Local release gate complete 2026-06-07; production live smoke deferred. Archive: `.planning/milestones/v2.4-ROADMAP.md`.

## Current Milestone

### v2.5 Production Support Handoff Verification Closeout

**Milestone Goal:** Close the v2.4 production verification gap by deploying support handoff changes and recording read-only production evidence.

This milestone intentionally contains one release-verification phase. It should not add support handoff features, mutate production report artifacts, or write to external support systems.

## Phases

- [x] **Phase 70: Production Support Handoff Verification Closeout** - Capture deploy/runtime/CDK evidence, run production read-only API/browser smoke, and close the deferred v2.4 verification gap.

## Phase Details

### Phase 70: Production Support Handoff Verification Closeout

**Goal**: Deploy or verify deployment of v2.4 support handoff backend/frontend changes and record production read-only support handoff evidence.
**Depends on**: Phase 69
**Requirements**: PRODVERIFY-01, PRODVERIFY-02, PRODVERIFY-03, VERIFY-08
**Success Criteria**:

1. Backend/frontend deploy run IDs, commit SHAs, job IDs, timestamps, and statuses are recorded.
2. Lambda manifest/runtime and CDK diff/deploy classification are recorded for production.
3. Production API smoke verifies `/health`, auth gate, admin support handoff preview, `external_write` refusal, request IDs, and privacy denylist without mutation.
4. Production browser smoke verifies `/admin/report-operations` support handoff UI markers and privacy boundary with mutation/external-write guards.
5. Final audit closes the v2.4 deferred production verification gap or records a blocker with owner/follow-up.

**Plans**: 1 complete

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 70. Production Support Handoff Verification Closeout | v2.5 | 1/1 | Complete | 2026-06-07 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PRODVERIFY-01 | Phase 70 | Complete |
| PRODVERIFY-02 | Phase 70 | Complete |
| PRODVERIFY-03 | Phase 70 | Complete |
| VERIFY-08 | Phase 70 | Complete |

---
*Last updated: 2026-06-07 after completing v2.5 Phase 70*
