# Requirements: Report Recovery Operations Hardening

**Defined:** 2026-06-04
**Core Value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Milestone:** v1.6 Report Recovery Operations Hardening

## v1.6 Requirements

### Release Guard and Recovery Contract

- [ ] **GUARD-01**: Operators have a documented v1.6 recovery contract covering job types, state transitions, target snapshots, stop conditions, cancellation semantics, privacy boundaries, and audit guarantees before backend implementation starts.
- [ ] **GUARD-02**: CDK readiness evidence proves the existing `stoa-api`, `stoa-weekly-report`, DynamoDB table, SES permissions, S3 buckets, and Cognito admin authorization are sufficient for the v1.6 MVP or records the exact CDK changes required.
- [ ] **GUARD-03**: Lambda package builds write a `dist/.stoa-build-manifest.json` with backend source SHA/hash, dependency hash, runtime target, architecture/platform, build timestamp, and handler inventory.
- [ ] **GUARD-04**: CDK synth/diff/deploy paths fail fast when the backend Lambda `dist` artifact is missing, stale, built for the wrong runtime/platform, or missing expected handlers/modules.
- [ ] **GUARD-05**: Operators have a documented emergency override for the stale-dist guard that is explicit, auditable, and not enabled by default.

### Immutable Recovery Audit

- [ ] **AUDIT-01**: Existing single retry, single resend, and selected bulk resend recovery actions write append-only DynamoDB audit events in addition to existing mutable report summary fields.
- [ ] **AUDIT-02**: Audit writes are conditionally append-only, have no TTL, reject overwrite attempts, and document that v1.6 provides application-enforced immutability rather than compliance-grade WORM storage.
- [ ] **AUDIT-03**: Audit events record actor, action, reason, target identifiers, before/after recovery status metadata, result, redacted error details, timestamps, request/job correlation IDs, and source surface.
- [ ] **AUDIT-04**: Admin-only audit read APIs expose report-local and job-local timelines as metadata-only responses without private S3 keys, raw report JSON/HTML, presigned URLs, auth tokens, or customer-sensitive browser artifacts.
- [ ] **AUDIT-05**: Backend tests cover admin authorization, non-admin rejection, append-only enforcement, redaction, pagination, and audit events for successful, refused, failed, and cancelled recovery paths.

### Async Incident Recovery Jobs

- [ ] **JOB-01**: Admin can create a dry-run preflight preview for an async `resend_email` recovery job from explicit filters, including week/status scope, optional parent/student scope, max bounds, required reason, eligible/refused/missing counts, and metadata-only sample rows.
- [ ] **JOB-02**: Admin can create a bounded async `resend_email` job only after confirming the preview scope and providing a required operator reason.
- [ ] **JOB-03**: Job creation persists a stable target snapshot so progress, cancellation, results, and audit evidence reference a fixed target set even if report records change later.
- [ ] **JOB-04**: Job state is durable and observable through `queued`, `running`, `cancellation_requested`, `cancelled`, `completed`, `completed_with_failures`, and `failed` states with counters and timestamps.
- [ ] **JOB-05**: The existing `stoa-api` Lambda invokes the existing `stoa-weekly-report` Lambda asynchronously for recovery job work using scoped IAM permission and without processing incident-wide sends inside an API request.
- [ ] **JOB-06**: The recovery worker rereads each target, rechecks eligibility, atomically claims resend work before SES side effects, and records `success`, `refused`, `not_found`, `failed`, or `skipped_cancelled` per target.
- [ ] **JOB-07**: Async job execution enforces conservative caps for target count, page count, Lambda time remaining, failure threshold, SES pacing, and root-cause stop conditions.
- [ ] **JOB-08**: Admin can request cooperative cancellation, and the system clearly records that cancellation stops future target attempts without rolling back completed sends.
- [ ] **JOB-09**: Backend and infra tests cover job preview/create/list/detail/results/cancel, duplicate invocation/idempotency, conditional resend claims, worker stop conditions, metadata-only boundaries, and scoped Lambda invoke permission.

### Admin Job UI and Production Browser Smoke

- [ ] **UI-01**: Admin report operations UI exposes an async jobs surface for previewing `email_failed` resend scope, entering a reason, starting a job, polling progress, viewing results, and requesting cancellation.
- [ ] **UI-02**: Admin UI exposes report and job audit timelines with precise labels for immutable evidence, mutable triage fields, cancellation semantics, and refused/failed target outcomes.
- [ ] **UI-03**: Frontend API services and e2e tests verify job/audit workflows, role boundaries, metadata-only response rendering, and no private artifact marker exposure.
- [ ] **UI-04**: Production admin browser smoke uses a real existing admin session or approved secret-backed credential path without creating temporary production admin accounts.
- [ ] **UI-05**: Production browser smoke is read-only by default, verifies route/API/auth/privacy behavior, redacts evidence artifacts, and does not mutate customer reports.

### Runbook, Release Gate, and Live Verification

- [ ] **OPS-01**: Report recovery runbook covers async job creation, preview review, cancellation, stop conditions, audit lookup, stalled job handling, SES/Lambda/DynamoDB observability, and escalation.
- [ ] **OPS-02**: Release checklist captures Lambda build manifest, backend source provenance, Lambda CodeSha/source evidence, CDK diff/deploy evidence, and stale-dist guard results.
- [ ] **OPS-03**: Live verification proves admin-only job/audit APIs, read-only production browser smoke, metadata-only privacy boundaries, and clean CDK diff/deploy state.
- [ ] **OPS-04**: Final milestone audit records implementation evidence, research decisions, live verification outputs, residual risks, and deferred follow-up work.

## Future Requirements

Deferred to a future milestone.

### Recovery Expansion

- **FUT-01**: Admin can run incident-wide async `generation_failed` retry after async resend, audit, cancellation, and stop conditions prove reliable.
- **FUT-02**: Admin can resume a failed/skipped subset as a new audit-linked job attempt.
- **FUT-03**: Admin can export metadata-only recovery targets, job results, and audit events for support/security review.
- **FUT-04**: Recovery jobs integrate with support tickets or incident notes.

### Stronger Infrastructure

- **FUT-05**: Recovery orchestration can move to Step Functions, SQS, or a dedicated worker Lambda if v1.6 evidence proves the existing weekly Lambda cannot safely handle bounded jobs.
- **FUT-06**: Audit evidence can move to compliance-grade WORM storage such as S3 Object Lock if legal/security requires stronger immutability than application-enforced append-only DynamoDB rows.
- **FUT-07**: Recovery job access patterns can add a new GSI or table if existing single-table listing and query patterns prove insufficient.

### Product Expansion

- **FUT-08**: Admin can edit report content before resend.
- **FUT-09**: Admin can manage PDF report generation and delivery.
- **FUT-10**: Admin can manage multilingual report delivery.
- **FUT-11**: Report access can be gated by billing/subscription state.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Step Functions, SQS, new table, new bucket, new Lambda, or new GSI by default | v1.6 research recommends reuse-first; add new AWS resources only if a phase proves the existing stack cannot satisfy bounded jobs. |
| Compliance-grade WORM audit storage | v1.6 targets application-enforced append-only evidence; stronger legal immutability is a separate security/compliance decision. |
| Incident-wide generation retry MVP | Generation retry touches Bedrock, artifact writes, and higher-cost paths; start with safer `email_failed` resend jobs. |
| Production mutation browser smoke | v1.6 production browser smoke is read-only by default to avoid customer-impacting report operations. |
| Public or presigned S3 report URLs | Report artifacts remain private and backend-mediated. |
| Support ticket integration, report editing, PDF, multilingual delivery, billing, analytics, or broad admin redesign | These are product/ops expansions beyond this hardening milestone. |

## Traceability

Traceability is filled by the active v1.6 roadmap.

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
*Requirements defined: 2026-06-04*
*Last updated: 2026-06-04 after v1.6 roadmap creation*
