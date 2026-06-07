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
- [x] **v2.4 Support Evidence Export Destinations And Ticket Handoff** - Shipped 2026-06-07; production verification closed by v2.5. Archive: `.planning/milestones/v2.4-ROADMAP.md`.
- [x] **v2.5 Production Support Handoff Verification Closeout** - Shipped 2026-06-07. Archive: `.planning/milestones/v2.5-ROADMAP.md`.

## Current Milestone

### v2.6 Audit Retention And Immutable Evidence Readiness

**Milestone Goal:** Make report operations audit evidence ready for stronger retention and future immutable storage without weakening privacy boundaries.

This milestone starts with a contract/readiness phase. It should not claim compliance-grade WORM storage, delete audit rows, or add AWS resources unless the CDK decision explicitly proves that path is required and safe.

## Phases

- [x] **Phase 71: Audit Retention Contract And CDK Readiness** - Define retention/sealing contract, WORM boundary, privacy model, and infrastructure decision.
- [ ] **Phase 72: Backend Audit Retention Manifest APIs** - Add admin-only retention manifest/status APIs with metadata-only drift evidence and refusal behavior.
- [ ] **Phase 73: Admin Audit Retention UI** - Add `/admin/report-operations` controls to inspect retention status and preview/download manifests.
- [ ] **Phase 74: v2.6 Release Gate And Live Verification** - Record deploy/CDK/API/UI evidence, run production read-only smoke, and close v2.6.

## Phase Details

### Phase 71: Audit Retention Contract And CDK Readiness

**Goal**: Implementers have a precise audit retention contract, immutability boundary, privacy model, and infrastructure decision before backend implementation.
**Depends on**: Phase 70
**Requirements**: AUDITRET-01
**Success Criteria**:

1. Contract defines audit event classes, retention categories, retention clocks, sealing metadata, verification metadata, deletion/expiry semantics, and operator-facing status.
2. Contract distinguishes application-enforced append-only audit, metadata-only retention manifests, and compliance-grade immutable/WORM storage.
3. Privacy model forbids raw report artifacts, S3 keys, presigned URLs, auth tokens, passwords, cookies, AWS secrets, and raw unreviewed report JSON/HTML in retained evidence.
4. CDK readiness classifies whether existing resources are sufficient for metadata-only manifests/status or exactly what CDK-managed resource change would be required for future WORM storage.

**Plans**: 1 complete
**Completed**: 2026-06-07

### Phase 72: Backend Audit Retention Manifest APIs

**Goal**: Admins can generate metadata-only retention manifests and inspect retention status for supported audit scopes.
**Depends on**: Phase 71
**Requirements**: AUDITRET-02, AUDITRET-03
**Success Criteria**:

1. Backend accepts bounded audit references and returns manifest/status output with allowlisted metadata only.
2. Manifest includes hashes/counts/stable metadata sufficient to detect evidence drift without storing raw payloads.
3. Backend refuses destructive retention actions and unsupported WORM claims.
4. Tests cover admin-only auth, manifest schema, status states, privacy denylist, drift metadata, refusal behavior, and audit rows.

**Plans**: 0 complete

### Phase 73: Admin Audit Retention UI

**Goal**: Admins can inspect retention status and preview/download metadata-only manifests from `/admin/report-operations`.
**Depends on**: Phase 72
**Requirements**: UI-13
**Success Criteria**:

1. UI exposes retention status/manifest controls only to admins.
2. UI renders allowlisted retention metadata, evidence references, validation failures, and copy/download controls.
3. UI does not perform destructive retention deletion or direct WORM mutation.
4. Playwright covers retention status, manifest preview/download, error states, admin-only gating, and privacy denylist.

**Plans**: 0 complete
**UI hint**: yes

### Phase 74: v2.6 Release Gate And Live Verification

**Goal**: v2.6 closes with evidence proving audit retention readiness is deployed, admin-only, privacy-safe, and production-verified without destructive retention behavior.
**Depends on**: Phase 73
**Requirements**: VERIFY-09
**Success Criteria**:

1. Release gate records backend/frontend deploy runs, commit SHAs, Lambda manifest/runtime state, CDK diff/deploy evidence, local quality gates, API request IDs, and browser smoke results.
2. Production smoke is read-only by default and does not mutate report artifacts, delete audit records, or write to external systems.
3. Any retention/sealing operation is metadata-only unless a CDK-approved immutable storage path exists.
4. Final v2.6 audit records residual risks and whether compliance-grade WORM storage remains future scope.

**Plans**: 0 complete

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 71. Audit Retention Contract And CDK Readiness | v2.6 | 1/1 | Complete | 2026-06-07 |
| 72. Backend Audit Retention Manifest APIs | v2.6 | 0/1 | Not started | - |
| 73. Admin Audit Retention UI | v2.6 | 0/1 | Not started | - |
| 74. v2.6 Release Gate And Live Verification | v2.6 | 0/1 | Not started | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUDITRET-01 | Phase 71 | Complete |
| AUDITRET-02 | Phase 72 | Not started |
| AUDITRET-03 | Phase 72 | Not started |
| UI-13 | Phase 73 | Not started |
| VERIFY-09 | Phase 74 | Not started |

---
*Last updated: 2026-06-07 after completing Phase 71*
