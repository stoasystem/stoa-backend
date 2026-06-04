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

## Current

No active milestone. Next milestone should be opened after choosing the next product or operations focus.

---
*Last updated: 2026-06-04 after shipping v1.4*
