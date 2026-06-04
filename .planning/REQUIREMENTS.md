# Requirements: Report Recovery Production Rollout & Live Smoke

**Defined:** 2026-06-04
**Core Value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.

## v1.5 Requirements

### Deployment Readiness

- [x] **REL-01**: Backend release workflow can deploy the v1.4 report operations code to `stoa-api` and `stoa-weekly-report` without unexpected infrastructure drift. Completed in Phase 28 release readiness contract.
- [x] **REL-02**: Frontend release workflow can deploy the `/admin/report-operations` UI bundle to `app.stoaedu.ch` with production API configuration and no report-ops demo fallback. Completed in Phase 28 release readiness contract.
- [x] **REL-03**: Release evidence records commit SHAs, deployment timestamps, frontend asset/cache state, API URL, and Lambda code/update status. Completed in Phase 28 release readiness contract.
- [x] **REL-04**: Rollback entry points are identified before mutation smoke runs, including backend Lambda code rollback and frontend asset rollback. Completed in Phase 28 release readiness contract.

### Production API and UI Verification

- [ ] **LIVE-01**: Live admin report operations list endpoint is verified with an admin-authenticated request and returns metadata-only report operation rows or an explicit empty state. Partial in Phase 30: temporary admin token returned HTTP 200, but empty first page returned `next_token=true` and the token produced HTTP 400.
- [ ] **LIVE-02**: Live detail endpoint is verified for a safe report target and returns artifact availability, generation, delivery, operation metadata, and action eligibility without private artifact keys. Blocked in Phase 30 until admin-auth list returns or a fixture provides a safe target row.
- [x] **LIVE-03**: Live frontend `/admin/report-operations` renders the deployed UI for an admin user and uses the production API base URL. Completed in Phase 29 with production route/bundle evidence and local admin e2e; production admin click-through remains residual manual evidence.
- [ ] **LIVE-04**: Live unauthenticated and non-admin access checks reject report operations API/UI access. Partial in Phase 30: unauthenticated and invalid-token checks returned 401; valid non-admin token check is blocked without a production non-admin token.

### Safe Recovery Smoke

- [ ] **SMOKE-01**: A safe non-customer report recovery smoke target is prepared or identified with documented parent/student/week identifiers and cleanup expectations.
- [ ] **SMOKE-02**: Safe `generation_failed` retry smoke runs on the approved target and records status transition, audit fields, artifact availability, and absence of private artifact leakage.
- [ ] **SMOKE-03**: Safe `email_failed` single resend smoke runs on the approved target and records delivery status transition plus resend audit fields.
- [ ] **SMOKE-04**: Safe selected bulk resend smoke runs on approved targets and records per-item `success`, `refused`, `not_found`, or `failed` results.
- [ ] **SMOKE-05**: Smoke data is cleaned up or restored to a documented terminal state without affecting customer reports.

### Observability and Operations

- [ ] **OPSRUN-01**: Operators have a report recovery runbook that explains when to retry generation, resend email, bulk resend, and stop for engineering review.
- [ ] **OPSRUN-02**: Operators have CloudWatch/AWS Console queries or dashboard links for report recovery logs, Lambda health, SES delivery failures, and DynamoDB report records.
- [ ] **OPSRUN-03**: Recovery actions have a rollback/escalation checklist for failed smoke, repeated resend failure, unexpected artifact state, and unauthorized access findings.
- [ ] **OPSRUN-04**: Known limits are documented, including synchronous selected bulk resend cap and no incident-wide async recovery job yet.

### Verification and Closeout

- [ ] **VERIFY-01**: Backend focused tests and frontend e2e tests still pass after deployment-oriented changes.
- [ ] **VERIFY-02**: CDK diff evidence distinguishes expected Lambda/frontend asset changes from infrastructure or IAM drift.
- [ ] **VERIFY-03**: Final milestone audit records live deployment evidence, smoke outputs, residual risks, and next operational backlog.

## Future Requirements

Deferred to a future milestone.

### Incident Automation

- **FUT-01**: Admin can start asynchronous incident-wide report recovery jobs with progress tracking.
- **FUT-02**: Report recovery writes immutable audit log entries beyond mutable fields on the report record.
- **FUT-03**: Report recovery integrates with support tickets or incident notes.

### Report Product Expansion

- **FUT-04**: Admin can regenerate already successful reports as an explicit content-refresh workflow.
- **FUT-05**: Admin can manage PDF report generation.
- **FUT-06**: Admin can manage multilingual report delivery.
- **FUT-07**: Report access can be gated by billing/subscription state.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Incident-wide async recovery jobs | v1.5 focuses on production rollout, safe live smoke, and runbooks for selected recovery. |
| Immutable audit log table | Mutable report audit fields are enough for rollout; immutable audit storage is a future operations expansion. |
| Editing report content | This milestone verifies recovery operations, not report authoring. |
| Public or presigned S3 report URLs | Report artifacts remain backend-mediated and private. |
| PDF, multilingual reports, or billing-gated reports | Product expansion remains separate from production rollout readiness. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REL-01 | Phase 28 | Complete |
| REL-02 | Phase 28 | Complete |
| REL-03 | Phase 28 | Complete |
| REL-04 | Phase 28 | Complete |
| LIVE-01 | Phase 30 | Partial - admin auth passed, pagination gap remains |
| LIVE-02 | Phase 30 | Blocked - no safe detail target row |
| LIVE-03 | Phase 29 | Complete |
| LIVE-04 | Phase 30 | Partial - no valid production non-admin token |
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
*Requirements defined: 2026-06-04*
*Last updated: 2026-06-04 after Phase 30 live verification gaps*
