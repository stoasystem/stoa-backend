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

## Current Milestone

### v2.0 Controlled Report Editing MVP

**Milestone Goal:** Admins can safely propose and apply bounded report content edits with append-only audit evidence and no direct S3 exposure.

This milestone creates a backend-mediated edit draft/apply workflow for existing weekly report artifacts. It does not add PDF generation, multilingual delivery, billing, analytics, WORM storage, or external ticketing.

## Phases

- [x] **Phase 50: Report Editing Contract And Safety Model** - Define draft/apply contract, validation, privacy, audit, and CDK readiness.
- [x] **Phase 51: Backend Report Edit Draft And Apply APIs** - Add admin-only draft/apply/read APIs and audit evidence.
- [x] **Phase 52: Admin Report Editing UI** - Add report edit draft/apply controls to `/admin/report-operations`.
- [ ] **Phase 53: v2.0 Release Gate And Final Verification** - Record deploy/CDK/API/UI/live read-only evidence and archive v2.0.

## Phase Details

### Phase 50: Report Editing Contract And Safety Model

**Goal**: Implementers have a precise report editing contract and safety model.
**Depends on**: Phase 49
**Requirements**: EDIT-01, EDIT-02, EDIT-04
**Success Criteria**:

1. Contract defines draft fields, apply behavior, validation, artifact versioning, audit actions, and rollback boundary.
2. Privacy model states raw S3 keys/presigned URLs never leave backend.
3. CDK readiness states whether new buckets/tables/GSIs/IAM permissions are required.
4. Phase 51 backend plan identifies exact files and tests.

**Plans**: 1 complete

### Phase 51: Backend Report Edit Draft And Apply APIs

**Goal**: Admins can create/read/apply bounded report edit drafts through backend APIs.
**Depends on**: Phase 50
**Requirements**: EDIT-01, EDIT-02, EDIT-03, EDIT-04
**Success Criteria**:

1. Admin-only APIs create draft metadata without exposing private S3 keys.
2. Apply validates source report state and writes updated metadata/audit.
3. Apply records before/after metadata, editor, reason, validation result, and artifact version references.
4. Tests cover auth, validation, privacy denylist, audit, stale draft/source mismatch, and read-only draft retrieval.

**Plans**: 1 complete

### Phase 52: Admin Report Editing UI

**Goal**: Admins can draft and apply report metadata edits from `/admin/report-operations`.
**Depends on**: Phase 51
**Requirements**: UI-07
**Success Criteria**:

1. UI shows edit controls only for selected reports.
2. UI distinguishes draft creation from apply mutation.
3. UI renders validation/audit outcome without private artifact markers.
4. Frontend e2e covers draft/apply flow and privacy denylist.

**Plans**: 1 complete
**UI hint**: yes

### Phase 53: v2.0 Release Gate And Final Verification

**Goal**: v2.0 closes with release evidence proving report editing is deployed, admin-only, auditable, and production-smokeable without mutation.
**Depends on**: Phase 52
**Requirements**: VERIFY-03
**Success Criteria**:

1. Release gate records backend/frontend deploy runs, commit SHAs, Lambda manifest/runtime state, and local quality gates.
2. CDK diff/deploy evidence is recorded and classified.
3. Production API/browser smoke is read-only and creates no production edit draft/apply mutation.
4. Final v2.0 audit records residual risks and future requirements.

**Plans**: 0 complete

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 50. Report Editing Contract And Safety Model | v2.0 | 1/1 | Complete | 2026-06-05 |
| 51. Backend Report Edit Draft And Apply APIs | v2.0 | 1/1 | Complete | 2026-06-05 |
| 52. Admin Report Editing UI | v2.0 | 1/1 | Complete | 2026-06-05 |
| 53. v2.0 Release Gate And Final Verification | v2.0 | 0/1 | Not Started | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| EDIT-01 | Phase 50/51 | Complete |
| EDIT-02 | Phase 50/51 | Complete |
| EDIT-03 | Phase 51 | Complete |
| EDIT-04 | Phase 50/51/53 | In Progress |
| UI-07 | Phase 52 | Complete |
| VERIFY-03 | Phase 53 | Planned |

---
*Last updated: 2026-06-05 after completing Phase 52*
