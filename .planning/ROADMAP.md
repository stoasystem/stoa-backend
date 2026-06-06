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

## Current Milestone

### v2.4 Support Evidence Export Destinations And Ticket Handoff

**Milestone Goal:** Operators can turn redacted recovery, rollback, fixture, and release evidence into support-safe handoff packages for tickets or external support workflows without exposing private report artifacts or requiring unapproved third-party credentials.

This milestone builds on v1.9 support evidence packages and v2.3 release evidence automation. It starts with a contract/readiness phase so implementation can stay metadata-only, backend-mediated, admin-only, and credential-safe. Direct writes to external ticket systems remain out of scope unless an approved connector or secret-backed credential path is explicitly available.

## Phases

- [ ] **Phase 66: Support Destination Contract And CDK Readiness** - Define support handoff package schema, destination policy, privacy model, audit requirements, and infrastructure decision.
- [ ] **Phase 67: Backend Support Handoff Package APIs** - Add admin-only APIs/CLI to generate redacted support handoff packages from existing recovery/release evidence.
- [ ] **Phase 68: Admin Support Handoff UI** - Add `/admin/report-operations` controls to preview, copy, and download support-safe handoff packages.
- [ ] **Phase 69: v2.4 Release Gate And Live Verification** - Record deploy/CDK/API/UI evidence, run production read-only smoke, and close v2.4.

## Phase Details

### Phase 66: Support Destination Contract And CDK Readiness

**Goal**: Implementers have a precise support handoff package contract, destination policy, privacy model, audit plan, and infrastructure decision before adding APIs or UI.
**Depends on**: Phase 65
**Requirements**: HANDOFF-01, HANDOFF-02
**Success Criteria**:

1. Contract defines package inputs, package sections, evidence references, destination types, operator reason fields, audit metadata, and failure/skipped semantics.
2. Privacy model forbids auth tokens, passwords, S3 keys, presigned URLs, raw report JSON/HTML, raw artifact payloads, and customer data beyond approved support-safe identifiers.
3. Destination policy distinguishes copy/download/manual ticket handoff from direct third-party writes and blocks unapproved external writes.
4. CDK readiness classifies whether existing API, DynamoDB, S3, and frontend resources are sufficient or exactly what infrastructure change is required.

**Plans**: 1 planned

### Phase 67: Backend Support Handoff Package APIs

**Goal**: Admins can generate and validate redacted support handoff packages through backend-mediated tooling.
**Depends on**: Phase 66
**Requirements**: HANDOFF-03, HANDOFF-04
**Success Criteria**:

1. Backend API/CLI accepts bounded evidence references and returns a metadata-only support handoff package.
2. Handoff package can include recovery job evidence, support package evidence, release evidence, safe-fixture status, and operator notes only after redaction.
3. Backend rejects unapproved direct external destination writes and records redacted audit evidence for package generation.
4. Tests cover admin-only auth, schema validation, redaction denylist, unsupported destination refusal, audit metadata, and missing evidence references.

**Plans**: 0 complete

### Phase 68: Admin Support Handoff UI

**Goal**: Admins can preview, copy, and download support-safe handoff packages from `/admin/report-operations`.
**Depends on**: Phase 67
**Requirements**: UI-12
**Success Criteria**:

1. UI exposes support handoff controls only to admins and does not perform direct third-party writes.
2. UI renders allowlisted package metadata, evidence references, operator notes, validation failures, and copy/download controls.
3. UI never renders private S3 keys, presigned URLs, raw report JSON/HTML, auth tokens, or raw artifact payloads.
4. Playwright covers handoff preview, copy/download affordances, error states, admin-only gating, and privacy denylist.

**Plans**: 0 complete
**UI hint**: yes

### Phase 69: v2.4 Release Gate And Live Verification

**Goal**: v2.4 closes with evidence proving support handoff packages are deployed, admin-only, privacy-safe, auditable, and production-verified without customer-impacting mutation.
**Depends on**: Phase 68
**Requirements**: VERIFY-07
**Success Criteria**:

1. Release gate records backend/frontend deploy runs, commit SHAs, Lambda manifest/runtime state, CDK diff/deploy evidence, local quality gates, API request IDs, and browser smoke results.
2. Production API/browser smoke is read-only and verifies auth/privacy/UI markers without writing to external ticket systems or mutating report artifacts.
3. Direct external destination writes are verified as refused unless an approved credential path is configured.
4. Final v2.4 audit records residual risks, rollback path, and future requirements.

**Plans**: 0 complete

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 66. Support Destination Contract And CDK Readiness | v2.4 | 1/1 | Planned | - |
| 67. Backend Support Handoff Package APIs | v2.4 | 0/1 | Not started | - |
| 68. Admin Support Handoff UI | v2.4 | 0/1 | Not started | - |
| 69. v2.4 Release Gate And Live Verification | v2.4 | 0/1 | Not started | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| HANDOFF-01 | Phase 66 | Planned |
| HANDOFF-02 | Phase 66 | Planned |
| HANDOFF-03 | Phase 67 | Not started |
| HANDOFF-04 | Phase 67 | Not started |
| UI-12 | Phase 68 | Not started |
| VERIFY-07 | Phase 69 | Not started |

---
*Last updated: 2026-06-07 after planning v2.4 Phase 66*
