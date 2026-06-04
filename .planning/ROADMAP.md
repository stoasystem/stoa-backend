# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.0-ROADMAP.md`.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02. Archive: `.planning/milestones/v1.1-ROADMAP.md`.
- [x] **v1.2 S3 Report Artifact Infrastructure** - Shipped 2026-06-04 after live AWS verification. Record: `.planning/milestones/s3-report-artifact-infrastructure.md`.
- [x] **v1.3 Report Artifact Security & Operations Hardening** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.3-ROADMAP.md`.
- [x] **v1.4 Report Operations Admin UI / Bulk Recovery** - Shipped 2026-06-04. Archive: `.planning/milestones/v1.4-ROADMAP.md`.

## Current Milestone

### v1.5 Report Recovery Production Rollout & Live Smoke

**Milestone Goal:** Deploy the v1.4 report recovery workflow to production-facing surfaces, verify it with safe live evidence, and give operators a repeatable runbook for selected report recovery.

This milestone turns the locally verified v1.4 workflow into an operationally ready production rollout. It focuses on frontend/backend deployment evidence, authenticated live API/UI checks, safe non-customer recovery smoke, and support-ready runbooks.

## Phases

**Phase Numbering:**

- Integer phases continue from previous milestones.
- v1.4 ended at Phase 27, so v1.5 starts at Phase 28.
- Decimal phases are reserved for urgent insertions.

- [x] **Phase 28: Release Readiness and Deployment Contract** - Define release evidence, rollback points, deployment commands, and environment contract before production mutation smoke.
- [ ] **Phase 29: Frontend Production Deployment Verification** - Deploy and verify the admin report operations UI on `app.stoaedu.ch`.
- [ ] **Phase 30: Backend Production Deployment and API Live Verification** - Deploy and verify backend report operations API behavior with authenticated and unauthenticated live checks.
- [ ] **Phase 31: Safe Recovery Smoke Fixture and Mutation Verification** - Run safe non-customer retry/resend/bulk resend smoke and record outputs.
- [ ] **Phase 32: Operations Runbook, Observability, and Milestone Closeout** - Write operator runbook, observability links/queries, rollback checklist, and final audit.

## Phase Details

### Phase 28: Release Readiness and Deployment Contract

**Goal**: Define release evidence, rollback points, deployment commands, and environment contract before production mutation smoke.
**Depends on**: Phase 27
**Requirements**: REL-01, REL-02, REL-03, REL-04
**Success Criteria**:

1. Release checklist names backend, frontend, and infra repositories, branches, commits, commands, and expected outputs.
2. Deployment contract records production API base URL, frontend app URL, AWS region/profile, Lambda names, and reports bucket.
3. Rollback points are documented for backend Lambda code, frontend assets, and any deployment pipeline failure.
4. CDK diff policy for this milestone distinguishes expected code/frontend asset changes from infrastructure/IAM drift.
5. No production recovery mutation is attempted before safe smoke target criteria are documented.

**Plans**: 1/1 plans complete

### Phase 29: Frontend Production Deployment Verification

**Goal**: Deploy and verify the admin report operations UI on `app.stoaedu.ch`.
**Depends on**: Phase 28
**Requirements**: REL-02, REL-03, LIVE-03
**Success Criteria**:

1. Frontend deployment uses the v1.4/v1.5 report operations UI commits and production API configuration.
2. `https://app.stoaedu.ch/admin/report-operations` serves the new UI bundle, not only old SPA fallback HTML.
3. Admin-authenticated browser check confirms navigation, filters, list/detail surface, and action controls render against production API.
4. Verification records frontend asset timestamp/hash/cache evidence and deployment commit SHA.
5. UI verification confirms no report ops demo fallback and no direct frontend S3 fetch path.

**Plans**: 0/1 plans complete

### Phase 30: Backend Production Deployment and API Live Verification

**Goal**: Deploy and verify backend report operations API behavior with authenticated and unauthenticated live checks.
**Depends on**: Phase 28
**Requirements**: REL-01, REL-03, LIVE-01, LIVE-02, LIVE-04, VERIFY-02
**Success Criteria**:

1. Backend deployment updates `stoa-api` and `stoa-weekly-report` code where needed and records Lambda LastUpdateStatus.
2. CDK diff/deploy evidence shows no unexpected infrastructure or IAM drift.
3. Live unauthenticated and non-admin checks reject report operations endpoints.
4. Live admin-authenticated list and detail checks return metadata-only report operation responses or explicit empty states.
5. Live API responses do not expose raw HTML/JSON, private artifact keys, public URLs, presigned URLs, or direct S3 URL markers.

**Plans**: 0/1 plans complete

### Phase 31: Safe Recovery Smoke Fixture and Mutation Verification

**Goal**: Run safe non-customer retry/resend/bulk resend smoke and record outputs.
**Depends on**: Phase 30
**Requirements**: SMOKE-01, SMOKE-02, SMOKE-03, SMOKE-04, SMOKE-05
**Success Criteria**:

1. Safe smoke target parent/student/week records are documented before mutation.
2. Smoke target contains no customer PII and has cleanup or restore expectations.
3. Generation retry smoke records status transition, audit fields, artifact availability, and privacy checks.
4. Single resend and selected bulk resend smoke record status transitions, audit fields, per-item results, and privacy checks.
5. Smoke fixture is cleaned up or restored to a documented terminal state.

**Plans**: 0/1 plans complete

### Phase 32: Operations Runbook, Observability, and Milestone Closeout

**Goal**: Write operator runbook, observability links/queries, rollback checklist, and final audit.
**Depends on**: Phase 31
**Requirements**: OPSRUN-01, OPSRUN-02, OPSRUN-03, OPSRUN-04, VERIFY-01, VERIFY-02, VERIFY-03
**Success Criteria**:

1. Operator runbook explains retry generation, single resend, selected bulk resend, stop conditions, and escalation paths.
2. Observability section includes CloudWatch log query examples, Lambda health checks, SES/delivery investigation pointers, and DynamoDB report lookup guidance.
3. Rollback checklist covers failed deployment, failed smoke, unexpected artifact state, repeated resend failure, and unauthorized access findings.
4. Final backend/frontend tests and e2e checks pass after deployment-oriented documentation and code changes.
5. Milestone audit records deployment evidence, smoke outputs, residual risks, and next operational backlog.

**Plans**: 0/1 plans complete

## Progress

**Execution Order:**
Phases execute in numeric order: 28 -> 29 -> 30 -> 31 -> 32

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 28. Release Readiness and Deployment Contract | v1.5 | 1/1 | Complete | 2026-06-04 |
| 29. Frontend Production Deployment Verification | v1.5 | 0/1 | Pending | - |
| 30. Backend Production Deployment and API Live Verification | v1.5 | 0/1 | Pending | - |
| 31. Safe Recovery Smoke Fixture and Mutation Verification | v1.5 | 0/1 | Pending | - |
| 32. Operations Runbook, Observability, and Milestone Closeout | v1.5 | 0/1 | Pending | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REL-01 | Phase 28 | Complete |
| REL-02 | Phase 28 | Complete |
| REL-03 | Phase 28 | Complete |
| REL-04 | Phase 28 | Complete |
| LIVE-01 | Phase 30 | Pending |
| LIVE-02 | Phase 30 | Pending |
| LIVE-03 | Phase 29 | Pending |
| LIVE-04 | Phase 30 | Pending |
| SMOKE-01 | Phase 31 | Pending |
| SMOKE-02 | Phase 31 | Pending |
| SMOKE-03 | Phase 31 | Pending |
| SMOKE-04 | Phase 31 | Pending |
| SMOKE-05 | Phase 31 | Pending |
| OPSRUN-01 | Phase 32 | Pending |
| OPSRUN-02 | Phase 32 | Pending |
| OPSRUN-03 | Phase 32 | Pending |
| OPSRUN-04 | Phase 32 | Pending |
| VERIFY-01 | Phase 32 | Pending |
| VERIFY-02 | Phase 32 | Pending |
| VERIFY-03 | Phase 32 | Pending |

**Coverage:**

- v1.5 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0

---
*Last updated: 2026-06-04 after completing Phase 28*
