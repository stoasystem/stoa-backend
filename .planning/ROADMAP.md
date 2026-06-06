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

## Current Milestone

### v2.1 Report Artifact Versioning And Safe Edit Preview

**Milestone Goal:** Admins can preview and apply bounded report artifact edits through backend-mediated versioned artifacts, with rollback metadata, append-only audit evidence, and no frontend exposure of private S3 keys, presigned URLs, raw JSON, or unreviewed HTML.

This milestone upgrades v2.0 metadata-only report editing toward real artifact editing, but keeps the workflow deliberately constrained: no freeform WYSIWYG editor, no direct S3 access, no production mutation before a named safe fixture, and no new infrastructure unless Phase 54 proves current resources cannot safely support versioned artifact storage.

## Phases

- [x] **Phase 54: Artifact Editing Contract And CDK Readiness** - Define versioned artifact edit contract, storage layout, rollback boundary, privacy model, and infra requirements.
- [x] **Phase 55: Backend Artifact Edit Preview And Versioned Apply APIs** - Add admin-only preview/apply APIs that produce sanitized previews and versioned artifact writes.
- [x] **Phase 56: Admin Artifact Edit Preview UI** - Add selected-report artifact edit preview/diff/apply controls to `/admin/report-operations`.
- [ ] **Phase 57: v2.1 Release Gate And Safe Live Verification** - Record deploy/CDK/API/UI evidence and verify production read-only plus safe-fixture mutation behavior.

## Phase Details

### Phase 54: Artifact Editing Contract And CDK Readiness

**Goal**: Implementers have a precise artifact editing contract and infrastructure decision before any artifact mutation code.
**Depends on**: Phase 53
**Requirements**: SAFETY-01
**Success Criteria**:

1. Contract defines editable artifact fields/sections, validation, version IDs, rollback metadata, audit events, and operator reason requirements.
2. Storage model defines where versioned JSON/HTML artifacts are written and how current artifact pointers are updated.
3. Privacy model proves frontend receives only sanitized preview/diff metadata and never private S3 keys or presigned URLs.
4. CDK readiness classifies whether existing reports bucket/IAM/table resources are sufficient or exactly what CDK change is required.

**Plans**: 1 complete

### Phase 55: Backend Artifact Edit Preview And Versioned Apply APIs

**Goal**: Admins can preview and apply bounded report artifact edits through backend APIs.
**Depends on**: Phase 54
**Requirements**: ARTEDIT-01, ARTEDIT-02, ARTEDIT-03, ARTEDIT-04
**Success Criteria**:

1. Preview API validates allowlisted edit payloads and returns sanitized diff/preview without raw private artifact payload exposure.
2. Apply API rejects stale drafts/source artifacts, writes versioned artifacts, updates report metadata pointers atomically enough for the current DynamoDB/S3 model, and records rollback metadata.
3. Audit includes editor, reason, source artifact version, new artifact version, before/after metadata, validation result, and correlation ID.
4. Tests cover admin-only auth, validation failures, stale source rejection, private marker denylist, versioned writes, rollback metadata, and audit evidence.

**Plans**: 1 complete

### Phase 56: Admin Artifact Edit Preview UI

**Goal**: Admins can review sanitized artifact edit previews and apply versioned edits from `/admin/report-operations`.
**Depends on**: Phase 55
**Requirements**: UI-08
**Success Criteria**:

1. UI exposes artifact edit preview controls only for a selected report.
2. UI distinguishes preview from apply mutation and requires an operator reason.
3. UI renders sanitized diff/preview and apply outcome without private artifact markers.
4. Playwright covers preview/apply controls, stale/error states, and privacy denylist.

**Plans**: 1 complete
**UI hint**: yes

### Phase 57: v2.1 Release Gate And Safe Live Verification

**Goal**: v2.1 closes with evidence proving artifact editing is deployed, admin-only, auditable, privacy-safe, and production-verified without customer-impacting mutation.
**Depends on**: Phase 56
**Requirements**: VERIFY-04
**Success Criteria**:

1. Release gate records backend/frontend deploy runs, commit SHAs, Lambda manifest/runtime state, CDK diff/deploy evidence, and local quality gates.
2. Production API/browser smoke is read-only by default and verifies route/auth/privacy/bundle markers without creating customer artifact edits.
3. Any production mutation smoke uses a named non-customer safe fixture with cleanup and explicit evidence.
4. Final v2.1 audit records residual risks, rollback path, and future requirements.

**Plans**: 0 complete

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 54. Artifact Editing Contract And CDK Readiness | v2.1 | 1/1 | Complete | 2026-06-06 |
| 55. Backend Artifact Edit Preview And Versioned Apply APIs | v2.1 | 1/1 | Complete | 2026-06-06 |
| 56. Admin Artifact Edit Preview UI | v2.1 | 1/1 | Complete | 2026-06-06 |
| 57. v2.1 Release Gate And Safe Live Verification | v2.1 | 0/1 | Not Started | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SAFETY-01 | Phase 54 | Complete |
| ARTEDIT-01 | Phase 55 | Complete |
| ARTEDIT-02 | Phase 55 | Complete |
| ARTEDIT-03 | Phase 55 | Complete |
| ARTEDIT-04 | Phase 55 | Complete |
| UI-08 | Phase 56 | Complete |
| VERIFY-04 | Phase 57 | Planned |

---
*Last updated: 2026-06-06 after completing Phase 56*
