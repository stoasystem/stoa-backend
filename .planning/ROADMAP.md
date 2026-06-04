# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.0-ROADMAP.md`.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.1-ROADMAP.md`.
- [x] **v1.2 S3 Report Artifact Infrastructure** - Shipped 2026-06-04 after live AWS verification. Record: `.planning/milestones/s3-report-artifact-infrastructure.md`.
- [x] **v1.3 Report Artifact Security & Operations Hardening** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.3-ROADMAP.md`.

## Current Milestone

### v1.4 Report Operations Admin UI / Bulk Recovery

**Milestone Goal:** Turn the API-only report operations surface into an admin-usable recovery workflow for report generation and delivery failures.

This milestone adds an admin report operations page, backend list/detail APIs, single-report `generation_failed` retry, selected bulk resend for `email_failed`, and end-to-end verification that recovery remains private, admin-only, and auditable.

## Phases

**Phase Numbering:**

- Integer phases continue from previous milestones.
- v1.3 ended at Phase 22, so v1.4 starts at Phase 23.
- Decimal phases are reserved for urgent insertions.

- [ ] **Phase 23: Report Operations List and Detail API** - Admins can list, filter, page, and inspect report operation metadata without AWS Console access.
- [ ] **Phase 24: Generation Failure Retry** - Admins can retry one `generation_failed` report safely without regenerating unrelated successful reports.
- [ ] **Phase 25: Bulk Email Resend Recovery** - Admins can resend selected `email_failed` reports and receive per-report results.
- [ ] **Phase 26: Admin Report Operations UI** - Admins can use a frontend operations page for report triage, detail inspection, and recovery actions.
- [ ] **Phase 27: Report Recovery Verification and Live Evidence** - The full recovery workflow is verified for authorization, privacy, tests, and deployed behavior.

## Phase Details

### Phase 23: Report Operations List and Detail API

**Goal**: Admins can list, filter, page, and inspect report operation metadata without AWS Console access.
**Depends on**: Phase 22
**Requirements**: OPS-01, OPS-02, OPS-03, OPS-04, OPS-05
**Success Criteria**:

1. `GET /admin/reports/ops` returns report operation rows with status, email status, error metadata, last operation, and updated timestamps.
2. The list API supports bounded `limit` pagination and explicit filters for status, week start, parent ID, and student ID where supported by the access pattern.
3. The phase records evidence that the current DynamoDB access pattern is safe for pilot usage or implements a CDK-managed index before broad use.
4. Existing detail endpoint returns generation metadata and action eligibility/disabled reasons in addition to v1.3 artifact/delivery/operation metadata.
5. Backend tests cover list filters, pagination, detail metadata, and action eligibility.

**Plans**: 0/1 plans complete

### Phase 24: Generation Failure Retry

**Goal**: Admins can retry one `generation_failed` report safely without regenerating unrelated successful reports.
**Depends on**: Phase 23
**Requirements**: GEN-01, GEN-02, GEN-03, GEN-04
**Success Criteria**:

1. Admin retry endpoint targets one parent, student, and week report.
2. Retry preserves the canonical report ID and `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}` artifact keys.
3. Retry refuses successful, pending, generated, `email_sent`, and `email_failed` reports with clear status-specific errors.
4. Retry records operator, operation, attempt/completion or failure timestamps, result, and error class/message.
5. Backend tests prove successful retry, refused statuses, audit fields, and no unrelated report regeneration.

**Plans**: 0/1 plans complete

### Phase 25: Bulk Email Resend Recovery

**Goal**: Admins can resend selected `email_failed` reports and receive per-report results.
**Depends on**: Phase 24
**Requirements**: DEL-01, DEL-02, DEL-03, DEL-04
**Success Criteria**:

1. Bulk resend endpoint accepts selected report identifiers and enforces a maximum batch size.
2. Each selected report is validated independently and returns success, refused, not-found, or failed result.
3. Resend uses private HTML artifacts through backend-mediated S3 reads and never returns raw report content.
4. Per-report audit fields record operator, operation, attempt/completion or failure timestamps, result, and error class/message.
5. Backend tests cover mixed success/refusal/failure batches and verify failed items do not block other items.

**Plans**: 0/1 plans complete

### Phase 26: Admin Report Operations UI

**Goal**: Admins can use a frontend operations page for report triage, detail inspection, and recovery actions.
**Depends on**: Phase 25
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05
**Success Criteria**:

1. Admin navigation exposes a report operations route and page.
2. The page shows filters, loading state, empty state, error state, paginated results, and status badges.
3. Admin can inspect one report row in a detail panel or detail view without leaving the workflow.
4. Admin can trigger eligible retry/resend actions and see single-action or per-item results.
5. The frontend uses real admin report operations APIs without silent demo fallback.

**Plans**: 0/1 plans complete

### Phase 27: Report Recovery Verification and Live Evidence

**Goal**: The full recovery workflow is verified for authorization, privacy, tests, and deployed behavior.
**Depends on**: Phase 26
**Requirements**: SEC-01, SEC-02, VER-01, VER-02, VER-03
**Success Criteria**:

1. Tests prove all list, detail, retry, and bulk resend endpoints reject non-admin users.
2. API and UI tests prove no raw report HTML/JSON, public S3 URLs, presigned URLs, or direct frontend S3 fetch paths are exposed.
3. Focused backend tests cover list/detail access, status filtering, generation retry, bulk resend, per-item results, and audit fields.
4. Focused frontend tests cover navigation, filters/states, detail inspection, action eligibility, bulk selection, and result rendering.
5. Live verification records deployed API state, frontend route behavior, and at least one safe recovery smoke path.

**Plans**: 0/1 plans complete

## Progress

**Execution Order:**
Phases execute in numeric order: 23 -> 24 -> 25 -> 26 -> 27

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 23. Report Operations List and Detail API | v1.4 | 0/1 | Pending | - |
| 24. Generation Failure Retry | v1.4 | 0/1 | Pending | - |
| 25. Bulk Email Resend Recovery | v1.4 | 0/1 | Pending | - |
| 26. Admin Report Operations UI | v1.4 | 0/1 | Pending | - |
| 27. Report Recovery Verification and Live Evidence | v1.4 | 0/1 | Pending | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| OPS-01 | Phase 23 | Pending |
| OPS-02 | Phase 23 | Pending |
| OPS-03 | Phase 23 | Pending |
| OPS-04 | Phase 23 | Pending |
| OPS-05 | Phase 23 | Pending |
| GEN-01 | Phase 24 | Pending |
| GEN-02 | Phase 24 | Pending |
| GEN-03 | Phase 24 | Pending |
| GEN-04 | Phase 24 | Pending |
| DEL-01 | Phase 25 | Pending |
| DEL-02 | Phase 25 | Pending |
| DEL-03 | Phase 25 | Pending |
| DEL-04 | Phase 25 | Pending |
| UI-01 | Phase 26 | Pending |
| UI-02 | Phase 26 | Pending |
| UI-03 | Phase 26 | Pending |
| UI-04 | Phase 26 | Pending |
| UI-05 | Phase 26 | Pending |
| SEC-01 | Phase 27 | Pending |
| SEC-02 | Phase 27 | Pending |
| VER-01 | Phase 27 | Pending |
| VER-02 | Phase 27 | Pending |
| VER-03 | Phase 27 | Pending |

**Coverage:**

- v1.4 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

---
*Last updated: 2026-06-04 after v1.4 roadmap creation*
