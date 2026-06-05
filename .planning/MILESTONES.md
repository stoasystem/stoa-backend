# Milestones

## Completed

### v1.0 Parent Portal Real Data Integration

**Status:** Shipped 2026-06-02
**Audit:** `.planning/v1.0-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.0-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.0-REQUIREMENTS.md`
**Phases:** 5
**Plans:** 11
**Requirements:** 38/38 v1 requirements complete

Key accomplishments:

- Added normal parent portal `/parents/me/...` backend routes for child list, summary, history, latest report, and week-specific report lookups.
- Enforced parent ownership before child-specific data reads and preserved explicit legacy route compatibility.
- Aligned frontend parent services and pages to real backend route shapes without silent demo fallback.
- Added available, empty, missing, and error states across parent-critical frontend flows.
- Verified backend parent behavior with 50 tests and frontend parent flows with focused Playwright coverage.

Known deferred items at close: 4 (see `.planning/v1.0-MILESTONE-AUDIT.md` tech debt).

### v1.1 Weekly Report Automation

**Status:** Shipped 2026-06-02
**Audit:** `.planning/v1.1-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.1-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.1-REQUIREMENTS.md`
**Phases:** 8
**Plans:** 8
**Requirements:** 34/34 v1.1 requirements complete

Key accomplishments:

- Added CDK-backed scheduled weekly report Lambda infrastructure with EventBridge Scheduler, permissions, DLQ, and monitoring.
- Built weekly learning aggregation, parent-facing Bedrock report generation with deterministic fallback, and report artifact storage.
- Stored generated report metadata and full HTML/JSON artifacts before SES delivery completion.
- Added idempotent scheduled orchestration for linked parent/student report generation.
- Exposed generated, missing, pending, failed, and email-failed report states through the parent API and frontend.
- Verified backend and frontend report flows with focused pytest, ruff, Playwright, and lint coverage.

Known deferred items at close: 5 follow-up candidates (see `.planning/v1.1-MILESTONE-AUDIT.md` residual risks and follow-ups).

### v1.2 S3 Report Artifact Infrastructure

**Status:** Shipped 2026-06-04 after live AWS verification
**Milestone record:** `.planning/milestones/s3-report-artifact-infrastructure.md`
**Phase archive:** `.planning/milestones/v1.2-phases/`
**Phases:** 5
**Plans:** 5
**Requirements:** 31/31 v1.2 requirements complete

Key accomplishments:

- Verified the deployed reports bucket is private, encrypted, access-blocked, retained in CDK, and wired into both Lambda functions.
- Locked the canonical artifact key contract as `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}`.
- Added helper-backed JSON/HTML artifact writes and reads with tests for content type, safe key inputs, and no S3 ACL usage.
- Preserved storage ordering so report metadata and email delivery only proceed after artifact writes succeed.
- Ran deployed Lambda private-object smoke on 2026-06-04; `stoa-weekly-report` wrote and read back a private JSON object under the canonical prefix.

Known deferred items at close: report bucket `enforce_ssl`, prefix-scoped IAM, smoke/orphan lifecycle cleanup, and report operations tooling.

### v1.3 Report Artifact Security & Operations Hardening

**Status:** Shipped 2026-06-04
**Audit:** `.planning/v1.3-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.3-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.3-REQUIREMENTS.md`
**Phases:** 4
**Plans:** 4
**Requirements:** 14/14 v1.3 requirements complete

Key accomplishments:

- Deployed HTTPS-only S3 transport enforcement on the existing reports bucket without bucket replacement.
- Scoped API and weekly report Lambda artifact S3 permissions to `weekly-reports/*`, preserving image bucket behavior.
- Added deterministic smoke cleanup and failed partial JSON artifact cleanup.
- Added admin-only report operations metadata and failed-delivery resend endpoints with persisted audit fields.
- Verified live AWS state with CDK diff/deploy, IAM checks, Lambda smoke, and S3 object absence checks.

Known deferred items at close: richer admin UI dashboard, bulk incident retry, PDF/multilanguage/billing report product expansions.

### v1.4 Report Operations Admin UI / Bulk Recovery

**Status:** Shipped 2026-06-04
**Audit:** `.planning/v1.4-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.4-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.4-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v1.4-phases/`
**Phases:** 5
**Plans:** 5
**Requirements:** 23/23 v1.4 requirements complete

Key accomplishments:

- Added admin report operations list/detail APIs with filters, bounded pagination, generation metadata, delivery metadata, and action eligibility.
- Added atomic single-report retry for `generation_failed` reports with retry audit fields.
- Added selected bulk resend for `email_failed` reports with per-item results and shared resend audit fields.
- Added frontend `/admin/report-operations` UI for filtering, detail inspection, single actions, selected bulk resend, and result rendering.
- Verified backend authorization/privacy, frontend e2e workflow, Lambda deployed state, API health/auth gate, and CDK diff.

Known deferred items at close: live frontend deployment of the new UI bundle, production recovery mutation smoke with an approved safe failed report target, incident-wide async recovery jobs.

### v1.5 Report Recovery Production Rollout & Live Smoke

**Status:** Shipped 2026-06-04
**Audit:** `.planning/milestones/v1.5-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.5-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.5-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v1.5-phases/`
**Phases:** 5
**Plans:** 5
**Requirements:** 20/20 v1.5 requirements complete

Key accomplishments:

- Verified backend and frontend release readiness, rollback entry points, deployment contract, and production evidence requirements.
- Verified production `/admin/report-operations` route and bundle markers with production API configuration and no private artifact markers.
- Fixed and verified admin report ops bounded-scan pagination, admin-auth list/detail behavior, and valid non-admin rejection.
- Ran safe non-customer generation retry, single resend, and selected bulk resend smoke with cleanup confirmation.
- Added scoped `stoa-api` SES send permission for report recovery email paths and restored current Lambda package alignment through CDK.
- Published report recovery operations runbook with observability, rollback, escalation, and known limits.

Known deferred items at close: production admin browser click-through before real support use, incident-wide async recovery jobs, immutable audit logs, support ticket integration, report editing, PDF/multilingual/billing report product expansions, and broad repo lint debt outside focused report operations files.

### v1.6 Report Recovery Operations Hardening

**Status:** Shipped 2026-06-05
**Audit:** `.planning/milestones/v1.6-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.6-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.6-REQUIREMENTS.md`
**Goal:** Make report recovery safe for incident-wide operations by adding async bulk recovery, immutable audit evidence, production admin browser smoke, and CI/CD protection against stale Lambda package deployments.
**Phases:** 5
**Plans:** 5
**Requirements:** 28/28 complete

Key accomplishments:

- Added Lambda build manifest and CDK/CI stale-dist guard for backend Lambda package provenance.
- Added shared recovery services and application-enforced append-only audit evidence.
- Added bounded async `email_failed` resend jobs with preview, stable target snapshots, progress, per-target results, worker execution, and cooperative cancellation.
- Added admin job/audit UI on `/admin/report-operations`.
- Provisioned a long-lived production admin credential path and completed read-only production admin browser smoke with no production mutation and no private artifact marker exposure.
- Published v1.6 runbook, release gate, live verification evidence, and final milestone audit.

Known deferred items at close: incident-wide generation retry, resume failed/skipped subset, metadata-only export, support ticket integration, stronger orchestration resources if evidence requires them, compliance-grade WORM audit storage, report editing, PDF/multilingual/billing/analytics expansion, and production admin credential ownership/rotation policy.

### v1.7 Recovery Evidence Export & Admin Credential Operations

**Status:** Shipped 2026-06-05
**Audit:** `.planning/milestones/v1.7-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.7-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.7-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v1.7-phases/`
**Goal:** Make production report recovery easier to operate, audit, and hand off without expanding production mutation scope.
**Phases:** 4
**Plans:** 4
**Requirements:** 7/7 complete

Key accomplishments:

- Documented long-lived production admin credential ownership, rotation, access review, emergency disable, and Cognito group verification.
- Added admin-only bounded metadata-only recovery evidence export without private artifact exposure or recovery mutation.
- Added read-only recovery evidence export controls to `/admin/report-operations`.
- Verified backend/frontend deploys, Lambda manifest, Lambda runtime state, CDK diff classification, API request IDs, and production browser smoke.
- Confirmed production smoke used the secret-backed admin path, exposed no private markers, and performed no production recovery mutation.

Known deferred items at close: incident-wide generation retry, failed/skipped subset resume, Step Functions/SQS or dedicated worker orchestration, WORM audit storage, support ticket/export destination integration, report editing, PDF/multilingual delivery, billing, analytics, and broader admin operations expansion.

### v1.8 Incident Generation Retry Jobs

**Status:** Shipped 2026-06-05
**Audit:** `.planning/milestones/v1.8-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.8-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.8-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v1.8-phases/`
**Goal:** Admins can run bounded async `generation_failed` recovery jobs using the existing recovery job/audit platform and weekly report Lambda without expanding production mutation scope beyond approved admin actions.
**Phases:** 4
**Plans:** 4
**Requirements:** 6/6 complete

Key accomplishments:

- Defined the `retry_generation` recovery job contract and confirmed existing Lambda/DynamoDB/admin resources are sufficient.
- Added backend preview/create/execute/cancel/result/audit support for async `retry_generation` jobs.
- Routed weekly worker events through `report_recovery_retry_generation` without new infrastructure.
- Added admin report operations UI controls for resend versus generation retry job types.
- Verified backend/frontend deploys, Lambda manifest, Lambda runtime state, CDK diff classification, API request IDs, and production read-only browser smoke.
- Confirmed production smoke exposed the `Retry generation` UI, used the secret-backed admin path, exposed no private markers, and performed no production recovery mutation.

Known deferred items at close: failed/skipped subset resume, support evidence packages, Step Functions/SQS or dedicated worker orchestration if existing Lambda flow becomes insufficient, WORM audit storage, support ticket integration, report editing, PDF/multilingual delivery, billing, analytics, and broader admin operations expansion.

### v1.9 Recovery Resume And Support Evidence Packages

**Status:** Shipped 2026-06-05
**Audit:** `.planning/milestones/v1.9-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v1.9-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v1.9-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v1.9-phases/`
**Goal:** Admins can resume failed/refused/not_found/skipped recovery subsets from prior jobs and generate support-safe incident evidence packages.
**Phases:** 4
**Plans:** 4
**Requirements:** 8/8 complete

Key accomplishments:

- Added backend resume preview/create support for failed/refused/not_found/skipped recovery subsets.
- Preserved source job linkage, stable target snapshots, per-target source result metadata, and append-only audit evidence.
- Added backend support evidence packages with bounded metadata-only job, target, result, and audit summaries.
- Added frontend resume and support package controls on `/admin/report-operations`.
- Verified backend/frontend deploys, Lambda manifest, Lambda runtime state, CDK diff classification, API request IDs, Cognito group membership, production bundle markers, and production read-only browser smoke.
- Confirmed production smoke exposed no private markers and performed no production recovery mutation.

Known deferred items at close: controlled report editing, Step Functions/SQS or dedicated worker orchestration if existing Lambda flow becomes insufficient, compliance-grade WORM audit storage, support ticket destination integration, PDF/multilingual delivery, billing, analytics, and broader admin operations expansion.

## Current

### v2.0 Controlled Report Editing MVP

**Status:** Active
**Requirements:** `.planning/REQUIREMENTS.md`
**Roadmap:** `.planning/ROADMAP.md`
**Goal:** Admins can safely propose and apply bounded report content edits with append-only audit evidence and no direct S3 exposure.
**Phases:** 4 planned
**Requirements:** active

Planned work:

- Phase 50: Report Editing Contract And Safety Model.
- Phase 51: Backend Report Edit Draft And Apply APIs.
- Phase 52: Admin Report Editing UI.
- Phase 53: v2.0 Release Gate And Final Verification.

---
*Last updated: 2026-06-05 after archiving v1.9 and starting v2.0*
