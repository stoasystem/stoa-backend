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

## Current Milestone

### v2.2 Report Artifact Rollback And Safe Fixture Verification

**Milestone Goal:** Admins can safely roll back report artifact versions and production verification can exercise artifact mutation only through a named non-customer safe fixture with cleanup evidence.

This milestone closes the operational safety gap left intentionally by v2.1: versioned artifact apply is deployed, but rollback controls and production mutation verification still need a bounded, auditable, fixture-only path. The milestone keeps artifact access backend-mediated, preserves version history, and does not introduce WYSIWYG editing.

## Phases

- [x] **Phase 58: Artifact Rollback Contract And Safe Fixture Plan** - Define rollback contract, target-version model, safe-fixture protocol, and CDK readiness.
- [ ] **Phase 59: Backend Artifact Rollback APIs And Fixture Harness** - Add admin-only rollback preview/apply APIs and safe-fixture smoke harness.
- [ ] **Phase 60: Admin Artifact Rollback UI** - Add selected-report rollback preview/apply controls to `/admin/report-operations`.
- [ ] **Phase 61: v2.2 Release Gate And Safe Fixture Verification** - Record deploy/CDK/API/UI evidence and verify read-only plus named safe-fixture mutation/cleanup behavior.

## Phase Details

### Phase 58: Artifact Rollback Contract And Safe Fixture Plan

**Goal**: Implementers have a precise rollback contract, production safe-fixture protocol, and infrastructure decision before rollback mutation code.
**Depends on**: Phase 57
**Requirements**: ROLLBACK-01, FIXTURE-01
**Success Criteria**:

1. Rollback contract defines source/current version checks, target version selection, validation, operator reason requirements, audit events, and sanitized response fields.
2. Contract states rollback preserves prior versioned artifacts and updates only current report artifact metadata pointers after validation.
3. Safe-fixture protocol defines fixture identity, allowed mutation path, cleanup/restore requirements, evidence fields, and refusal behavior when fixture name or mutation mode is absent.
4. CDK readiness classifies whether existing reports bucket/IAM/table resources are sufficient or exactly what CDK change is required.

**Plans**: 1 complete

### Phase 59: Backend Artifact Rollback APIs And Fixture Harness

**Goal**: Admins can preview/apply artifact rollbacks through backend APIs, and operators have a named-fixture production mutation harness.
**Depends on**: Phase 58
**Requirements**: ROLLBACK-02, ROLLBACK-03, FIXTURE-01
**Success Criteria**:

1. Rollback preview/read/apply APIs require admin authorization and return sanitized rollback/version metadata only.
2. Apply rejects stale reports, stale current artifact metadata, missing target versions, and no-op rollback targets.
3. Apply updates report metadata to the target artifact version and records redacted append-only audit evidence with before/after metadata and correlation ID.
4. Safe-fixture harness refuses to mutate without explicit fixture name/mutation mode and records cleanup/restore evidence without secrets or private artifact keys.
5. Tests cover auth, validation failures, stale rejection, no-op rejection, sanitized responses, audit privacy, and fixture harness safety.

**Plans**: 0 complete

### Phase 60: Admin Artifact Rollback UI

**Goal**: Admins can review sanitized rollback previews and apply rollback from `/admin/report-operations`.
**Depends on**: Phase 59
**Requirements**: UI-09
**Success Criteria**:

1. UI exposes rollback controls only for selected reports with rollback-eligible artifact metadata.
2. UI distinguishes rollback preview from rollback apply mutation and requires an operator reason.
3. UI renders sanitized current/target version metadata, validation state, apply outcome, and audit reference without private artifact markers.
4. Playwright covers rollback preview/apply controls, stale/error states, and privacy denylist.

**Plans**: 0 complete
**UI hint**: yes

### Phase 61: v2.2 Release Gate And Safe Fixture Verification

**Goal**: v2.2 closes with evidence proving rollback is deployed, admin-only, auditable, privacy-safe, and production-verified without customer-impacting mutation.
**Depends on**: Phase 60
**Requirements**: VERIFY-05
**Success Criteria**:

1. Release gate records backend/frontend deploy runs, commit SHAs, Lambda manifest/runtime state, CDK diff/deploy evidence, and local quality gates.
2. Production API/browser smoke is read-only by default and verifies route/auth/privacy/bundle markers without customer artifact mutation.
3. Safe-fixture mutation smoke uses a named non-customer fixture and records request IDs, artifact version metadata, rollback metadata, cleanup/restore evidence, and privacy denylist results.
4. Final v2.2 audit records residual risks, rollback path, and future requirements.

**Plans**: 0 complete

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 58. Artifact Rollback Contract And Safe Fixture Plan | v2.2 | 1/1 | Complete | 2026-06-06 |
| 59. Backend Artifact Rollback APIs And Fixture Harness | v2.2 | 0/1 | Not Started | - |
| 60. Admin Artifact Rollback UI | v2.2 | 0/1 | Not Started | - |
| 61. v2.2 Release Gate And Safe Fixture Verification | v2.2 | 0/1 | Not Started | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ROLLBACK-01 | Phase 58 | Complete |
| ROLLBACK-02 | Phase 59 | Planned |
| ROLLBACK-03 | Phase 59 | Planned |
| FIXTURE-01 | Phase 58/59 | In Progress |
| UI-09 | Phase 60 | Planned |
| VERIFY-05 | Phase 61 | Planned |

---
*Last updated: 2026-06-06 after completing Phase 58*
