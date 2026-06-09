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

### v2.0 Controlled Report Editing MVP

**Status:** Shipped 2026-06-05
**Audit:** `.planning/milestones/v2.0-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.0-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.0-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.0-phases/`
**Goal:** Admins can safely propose and apply bounded report content edits with append-only audit evidence and no direct S3 exposure.
**Phases:** 4
**Plans:** 4
**Requirements:** 6/6 complete

Key accomplishments:

- Defined a metadata-only report editing safety contract with no raw artifact rewrite.
- Added admin-only edit draft create/read/apply APIs for `admin_note`, `editor_summary`, and `status_note`.
- Added stale draft rejection and append-only edit audit evidence.
- Added selected-report edit draft/apply controls to `/admin/report-operations`.
- Verified backend/frontend deploys, Lambda manifest/runtime evidence, CDK diff classification, API request IDs, Cognito admin group membership, production bundle markers, and production read-only browser smoke.
- Confirmed production smoke exposed no private markers and performed no production edit/recovery mutation.

Known deferred items at close: raw report artifact editing/rewrite, rich preview/diff approval workflow, WORM audit storage, support ticket/export destination integrations, PDF/multilingual delivery, billing, analytics, broader admin operations expansion, and stronger recovery orchestration if existing Lambda flow becomes insufficient.

### v2.1 Report Artifact Versioning And Safe Edit Preview

**Status:** Shipped 2026-06-06
**Audit:** `.planning/milestones/v2.1-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.1-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.1-REQUIREMENTS.md`
**Goal:** Admins can preview and apply bounded report artifact edits through backend-mediated versioned artifacts, with rollback metadata, append-only audit evidence, and no frontend exposure of private S3 keys, presigned URLs, raw JSON, or unreviewed HTML.
**Phases:** 4
**Plans:** 4
**Requirements:** 7/7 complete

Key accomplishments:

- Defined the versioned artifact editing contract, rollback boundary, privacy model, and CDK readiness decision.
- Added admin-only artifact edit preview/read/apply APIs with sanitized diffs, versioned artifact writes, stale-source rejection, rollback metadata, and redacted audit evidence.
- Added selected-report artifact edit preview/apply controls to `/admin/report-operations`.
- Verified backend/frontend deploys, Lambda manifest/runtime evidence, CDK diff classification, API request IDs, production bundle markers, and production read-only browser smoke.
- Confirmed production smoke exposed no private markers and performed no production artifact edit mutation.

Known deferred items at close: rollback endpoint/UI, rich WYSIWYG editor, safe-fixture artifact mutation smoke, WORM audit storage, support ticket/export destination integrations, PDF/multilingual delivery, billing, analytics, broader admin operations expansion, and stronger recovery orchestration if existing Lambda flow becomes insufficient.

### v2.2 Report Artifact Rollback And Safe Fixture Verification

**Status:** Shipped 2026-06-06
**Audit:** `.planning/milestones/v2.2-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.2-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.2-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.2-phases/`
**Goal:** Admins can safely roll back report artifact versions and production verification can exercise artifact mutation only through a named non-customer safe fixture with cleanup evidence.
**Phases:** 4
**Plans:** 4
**Requirements:** 6/6 complete

Key accomplishments:

- Defined the artifact rollback contract, safe-fixture protocol, privacy model, and CDK readiness decision.
- Added admin-only artifact rollback preview/read/apply APIs with sanitized metadata, stale-source rejection, no-op rejection, and redacted audit evidence.
- Added selected-report artifact rollback preview/apply controls to `/admin/report-operations`.
- Added an explicit safe-fixture smoke harness that refuses mutation unless a fixture name and mutation mode are provided.
- Verified backend/frontend deploys, Lambda runtime state, CDK diff, production read-only API/browser smoke, and the named safe-fixture mutation/rollback/cleanup flow.
- Found and fixed a report lookup bug where artifact edit child entities could be returned from the parent GSI instead of the report summary row.

Still deferred:

- Freeform WYSIWYG report editor.
- WORM audit storage.
- Support ticket/export destination integrations.
- Step Functions/SQS or dedicated recovery orchestration.
- PDF/multilingual delivery.
- Billing, analytics, and broader admin operations expansion.

### v2.3 Release Evidence Automation And Fixture Lifecycle

**Status:** Shipped 2026-06-06
**Audit:** `.planning/milestones/v2.3-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.3-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.3-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.3-phases/`
**Goal:** Operators can produce repeatable, redacted release evidence bundles and manage the named non-customer safe fixture lifecycle without expanding production mutation scope.
**Phases:** 4
**Plans:** 4
**Requirements:** 5/5 complete

Key accomplishments:

- Defined the release evidence bundle contract, redaction model, and safe-fixture lifecycle.
- Added backend release evidence validation, fixture inventory, mutation refusal checks, CLI tooling, admin validate/status endpoints, and focused tests.
- Added read-only release evidence and safe-fixture status controls to `/admin/report-operations`.
- Verified backend/frontend deploys, Lambda manifest/runtime evidence, CDK diff classification, local quality gates, production API/browser smoke, and privacy denylist results.
- Confirmed safe-fixture mutation paths refuse by default and skipped optional mutation smoke without explicit mutation approval.

Known deferred items at close: compliance-grade WORM audit storage, support ticket/export integrations, richer editor/report delivery/product expansion, and dedicated orchestration if the Lambda flow becomes insufficient.

### v2.4 Support Evidence Export Destinations And Ticket Handoff

**Status:** Shipped 2026-06-07; production verification closed by v2.5
**Audit:** `.planning/milestones/v2.4-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.4-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.4-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.4-phases/`
**Goal:** Operators can turn redacted recovery, rollback, fixture, and release evidence into support-safe handoff packages for tickets or external support workflows without exposing private report artifacts or requiring unapproved third-party credentials.
**Phases:** 4
**Plans:** 4
**Requirements:** 6/6 complete locally

Key accomplishments:

- Defined the support handoff package contract, destination refusal policy, privacy model, audit metadata, and no-new-CDK-resource readiness decision.
- Added admin-only backend support handoff package generation with metadata-only recovery, release, fixture, and operator-note sections.
- Added append-only support handoff audit rows and refusal behavior for direct external writes.
- Added frontend `/admin/report-operations` support handoff controls for preview, copy, download, and refusal states.
- Verified backend and frontend quality gates, privacy denylist coverage, release evidence validation, and mutation/refusal behavior locally.

Known deferred items at close: direct support-system writes remain out of scope until an approved connector or secret-backed credential path exists.

### v2.5 Production Support Handoff Verification Closeout

**Status:** Shipped 2026-06-07
**Audit:** `.planning/milestones/v2.5-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.5-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.5-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.5-phases/`
**Goal:** Close the v2.4 production verification gap by deploying support handoff changes and recording read-only production evidence.
**Phases:** 1
**Plans:** 1
**Requirements:** 4/4 complete

Key accomplishments:

- Verified backend deploy workflow `27091480178` for commit `875a8fbe2a56c89169ba52cdf469777f72a866b7`.
- Verified frontend CI `27091612903` and deploy workflow `27091612893` for commit `9171de6109e102185dc65f41c6294f644cad72de`.
- Recorded Lambda runtime state and CDK diff classification.
- Passed production support handoff API and browser smoke with no report artifact mutation, no external support-system write, and no privacy denylist hits.

Known deferred items at close: direct support-system integrations, compliance-grade WORM audit storage, and broader report product expansion remain future work.

### v2.6 Audit Retention And Immutable Evidence Readiness

**Status:** Shipped 2026-06-07
**Audit:** `.planning/milestones/v2.6-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.6-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.6-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.6-phases/`
**Goal:** Make report operations audit evidence ready for stronger retention and future immutable storage without weakening privacy boundaries.
**Phases:** 4
**Plans:** 4
**Requirements:** 5/5 complete

Key accomplishments:

- Defined a metadata-only audit retention contract, immutability boundary, privacy model, and no-new-CDK-resource readiness decision.
- Added admin-only backend audit retention status and manifest APIs with canonical digests, privacy validation, destructive action refusal, and redacted audit metadata.
- Added frontend `/admin/report-operations` audit retention controls for status, manifest preview, copy, download, digest rendering, and refusal states.
- Verified backend/frontend deploys, Lambda runtime state, CDK diff classification, production API smoke, and production browser smoke.
- Confirmed no report artifact mutation, no audit deletion, and no external write during production smoke; only a metadata-only audit retention refusal row was written.

Known deferred items at close: compliance-grade WORM/Object Lock storage, legal hold administration, retention policy administration, and full manifest object persistence remain future scope.

### v2.7 Immutable Audit Storage And Legal Hold Foundation

**Status:** Shipped 2026-06-07
**Audit:** `.planning/milestones/v2.7-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.7-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.7-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.7-phases/`
**Goal:** Implement the foundation for CDK-managed immutable audit evidence storage and legal hold/retention policy administration for report operations audit evidence while preserving metadata-only privacy boundaries.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 5/5 complete

Key accomplishments:

- Defined immutable audit storage and legal hold contracts with CDK-managed resources as the only approved path to compliance-grade immutability.
- Added backend admin-only immutable evidence status/persist and legal hold status/apply/release metadata APIs, with immutable persistence failing closed while CDK-managed immutable storage is absent and create-only metadata object writes when configured.
- Added legal-hold compare-and-set current-state writes and consistent reads after integration audit identified the missing contract behavior.
- Added frontend `/admin/report-operations` immutable evidence and legal hold controls with separate read-only status and explicit operator-reason mutation actions.
- Verified backend/frontend deploys, Lambda runtime state, CDK diff classification, production API smoke, guarded production browser smoke, and remediation code review.
- Confirmed no report artifact mutation, no audit deletion, no immutable write, no legal-hold mutation, and no external write during production smoke.

Known deferred items at close: compliance-grade WORM/Object Lock storage, CDK-managed immutable storage resource deployment, legal/compliance retention-period review, and full immutable manifest object persistence remain future scope.

### v2.8 CDK-Managed Immutable Evidence Storage Deployment

**Status:** Shipped 2026-06-07
**Audit:** `.planning/milestones/v2.8-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.8-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.8-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.8-phases/`
**Goal:** Deploy and enable CDK-managed immutable evidence storage for report operations retention manifests, then prove full metadata-only immutable manifest object persistence in production without exposing private artifacts, deleting audit rows, or mutating customer report artifacts.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Key accomplishments:

- Defined the CDK-managed immutable evidence storage design, deploy readiness, backend configuration contract, and production verification boundary.
- Deployed a retained, versioned, Object Lock-enabled immutable evidence metadata bucket through `stoa-infra` commit `c3d0d60` and workflow run `27098074719`.
- Injected immutable storage runtime settings into `stoa-api` and verified API IAM is limited to `s3:GetObject`/`s3:PutObject` on the approved metadata prefix.
- Added backend coverage for CDK env readiness and duplicate/reference-exists refusal while preserving create-only object writer and privacy guarantees.
- Persisted one approved metadata-only immutable manifest in production and verified API, DynamoDB, S3 Object Lock headers, and browser smoke.

Known deferred items at close: formal legal/compliance approval of the 365-day GOVERNANCE retention period and operational legal-hold procedure.

### v2.9 Retention Governance And Legal Hold Operations

**Status:** Complete local-only 2026-06-07; production verification deferred
**Started:** 2026-06-07
**Audit:** `.planning/milestones/v2.9-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v2.9-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v2.9-REQUIREMENTS.md`
**Phase archive:** `.planning/milestones/v2.9-phases/`
**Goal:** Make immutable evidence retention and legal-hold operations governable before broad compliance claims are made.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Key accomplishments:

- Defined the retention governance contract, approval packet, legal-hold runbook specification, owner model, review cadence, break-glass expectations, and privacy boundary.
- Added admin-only backend retention governance status, retention approval metadata recording, and legal-hold review metadata recording with append-only audit evidence, stale-write refusal, and privacy denylist tests.
- Added frontend `/admin/report-operations` governance controls for approval status, approval recording, legal-hold review recording, copy/download evidence payloads, and Playwright privacy coverage in `stoa-frontend` commit `b88c673`.
- Completed a local-only release gate with backend focused ruff, backend full pytest, frontend lint/build, targeted Playwright, and explicit production deploy/live smoke deferral.

Known deferred items at close: backend/frontend production deployment, production admin API smoke for governance endpoints, production browser smoke for governance controls, and formal legal/compliance approval of the exact retention period and legal-hold operating procedure. Broad compliance claims remain out of scope.

### v3.0 STOA Docs Gap Closeout And Account Intake Hardening

**Status:** Shipped 2026-06-08
**Started:** 2026-06-07
**Audit:** `.planning/milestones/v3.0-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v3.0-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.0-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Reconcile `stoa_docs` with the shipped backend/frontend state, close the highest-priority MVP product gaps that remain, and production-verify the v2.9 governance work before broader Phase 2 expansion.
**Phases:** 5
**Plans:** 5/5 complete
**Requirements:** 5/5 complete

Planned phases:

- Phase 87: STOA Docs Gap Audit And v3 Scope Readiness - Complete.
- Phase 88: v2.9 Governance Production Verification Closeout - Complete.
- Phase 89: Account Lifecycle And Parent Binding Gap Closeout - Complete.
- Phase 90: OCR Correction And Daily Question Quota Hardening - Complete.
- Phase 91: v3.0 Release Gate And Docs Alignment - Complete.

---
Key accomplishments:

- Produced a source-linked `stoa_docs` feature gap audit and updated it after closeout.
- Production-verified v2.9 retention governance/legal-hold operations.
- Added Cognito forgot/reset endpoints, explicit email verification metadata, formal parent-student bindings, and admin repair.
- Added edit-before-AI OCR correction, safe OCR metadata, private image-key suppression, and atomic daily question quota counters.
- Deployed backend changes, fixed API Gateway public route coverage for password reset endpoints, and passed final non-mutating production smoke.

Known deferred items at close: real email verification policy change, teacher rich text/formula polish, SLA tracking, content moderation, broad Phase 2 expansion, and unrelated `StoaNotificationStack` SES identity drift.

### v3.1 Teacher Reply Quality And SLA Operations

**Status:** Shipped 2026-06-08
**Started:** 2026-06-08
**Audit:** `.planning/milestones/v3.1-MILESTONE-AUDIT.md`
**Roadmap archive:** `.planning/milestones/v3.1-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v3.1-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Close the remaining teacher-takeover MVP gaps from `stoa_docs`: rich text/formula replies and response-time SLA tracking.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 92: Teacher Rich Reply And SLA Contract Readiness - Complete.
- Phase 93: Backend Rich Reply Metadata And SLA Tracking - Complete.
- Phase 94: Teacher Reply Composer And SLA Visibility UI - Complete.
- Phase 95: v3.1 Release Gate And STOA Docs Alignment - Complete.

---
Key accomplishments:

- Defined the versioned safe teacher rich reply/formula contract.
- Added backend rich reply sanitization/refusal and teacher SLA timing fields.
- Added tutor composer, formula rendering, SLA badges, and admin Teacher SLA stats.
- Completed backend/frontend deploys and production-safe smoke.

Known deferred items at close: content moderation workflow, production mutation verification for teacher rich replies with a named fixture, realtime/WebSocket teacher notifications, and broad Phase 2 expansion.

### v3.2 Content Moderation And Internal Operations

**Status:** Shipped 2026-06-08
**Started:** 2026-06-08
**Roadmap:** `.planning/milestones/v3.2-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.2-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Close the remaining MVP admin content moderation workflow from `stoa_docs`.
**Phases:** 4
**Audit:** `.planning/milestones/v3.2-MILESTONE-AUDIT.md`
**Phase archive:** `.planning/milestones/v3.2-phases/`
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 96: Content Moderation Contract And Data Model.
- Phase 97: Backend Moderation Reporting And Admin APIs.
- Phase 98: Moderation Reporting And Admin Queue UI.
- Phase 99: v3.2 Functional Release Gate And Docs Alignment.

---
Key accomplishments:

- Defined the moderation case contract, lifecycle, data model, and API/UI workflow.
- Added backend report creation and admin moderation list/detail/action APIs.
- Added student/tutor report actions and admin moderation queue/detail/actions UI.
- Completed backend/frontend deploys, production-safe smoke, and gap audit update.

Known deferred items at close: manual subscription operations, Stripe/TWINT payment-provider integration, broad multi-subject rollout, student memory/personalization, AI teacher tools, WebSocket realtime notifications, and mobile/multilingual polish.

### v3.3 Subscription Operations MVP

**Status:** Completed local release gate 2026-06-08
**Started:** 2026-06-08
**Roadmap:** `.planning/milestones/v3.3-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.3-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Make the MVP manual subscription model usable before Stripe/TWINT integration.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 100: Subscription Operations Contract And Entitlement Model.
- Phase 101: Backend Subscription Request And Admin Tier APIs.
- Phase 102: Parent Subscription Management UI And Admin Queue.
- Phase 103: v3.3 Functional Release Gate And Billing Readiness.

---
Key accomplishments:

- Defined the subscription operations contract, request lifecycle, entitlement model, and manual billing boundary.
- Added backend parent subscription plan/request APIs and admin subscription request processing/apply APIs.
- Added parent subscription management UI and admin subscription queue/detail/actions UI.
- Completed focused local release-gate evidence and kept Stripe/TWINT as future scope.

Known deferred items at close: Stripe/TWINT payment-provider integration, broad multi-subject rollout, student memory/personalization, AI teacher tools, WebSocket realtime notifications, and mobile/multilingual polish.

### v3.4 Learning Expansion Foundation

**Status:** Complete
**Started:** 2026-06-08
**Completed:** 2026-06-08
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Prepare Phase 2 learning expansion without jumping directly into a broad curriculum rollout.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 104: Multi-Subject Taxonomy And Prompt Contract.
- Phase 105: Backend Subject/Topic Support And Student Profile Seeds.
- Phase 106: Student And Parent Learning Profile UI.
- Phase 107: v3.4 Functional Release Gate And Expansion Audit.

Known deferred items at close: Stripe/TWINT payment-provider integration, full multi-subject curriculum content and exercises, student memory/personalization beyond profile seeds, AI teacher assistance tools, WebSocket realtime notifications, mobile responsive polish, full multilingual rollout, and support integrations.

### v3.5 Realtime And Teacher Assistance Foundation

**Status:** Complete
**Started:** 2026-06-08
**Completed:** 2026-06-08
**Audit:** `.planning/milestones/v3.5-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v3.5-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.5-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Prepare realtime and teacher-assistance expansion without jumping directly into a broad WebSocket rollout or automatic exercise generation.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 108: Realtime Notification And Teacher Assistance Contract.
- Phase 109: Backend Notification Events And Teacher Summary Seeds.
- Phase 110: Tutor/Admin Notification And Summary UI.
- Phase 111: v3.5 Functional Release Gate And Expansion Audit.

Key accomplishments:

- Defined bounded notification event and teacher assistance summary seed contracts.
- Added backend notification event persistence, recipient list/read/archive APIs, admin notification listing, and teacher assistance summary seeds.
- Emitted notification events from teacher request/takeover/reply, moderation, and subscription workflows without changing their core behavior.
- Added frontend notification center, admin operational notifications, and tutor assistance seed UI.
- Completed local release-gate evidence with backend tests, focused lint, frontend lint/build, and targeted Playwright evidence.

Known deferred items at close: Stripe/TWINT payment-provider integration, production WebSocket realtime delivery, push/email notification delivery, mobile responsive polish, full multilingual rollout, and support integrations. Automatic exercise generation and richer AI teacher tools were promoted to v3.7.

### v3.6 Full WebSocket Realtime Notifications

**Status:** Completed local release gate 2026-06-09
**Started:** 2026-06-08
**Completed:** 2026-06-09
**Audit:** `.planning/milestones/v3.6-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v3.6-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.6-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Turn the v3.5 in-product notification foundation into full WebSocket realtime notifications for core learning and operations workflows.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 112: Full WebSocket Transport Contract And Infra Readiness.
- Phase 113: Backend WebSocket Connection And Event Delivery.
- Phase 114: Realtime Notification Client And UX.
- Phase 115: v3.6 Functional Release Gate And Realtime Audit.

Key accomplishments:

- Defined authenticated WebSocket lifecycle, subscription, envelope, and fallback contracts.
- Added backend connection records, authorized subscription behavior, notification fanout, stale cleanup, and delivery attempt metadata.
- Added frontend WebSocket client behavior, reconnect/heartbeat/offline handling, notification cache sync, and polling fallback UX.
- Completed local backend pytest/Ruff evidence, frontend lint/build/browser fixture evidence, and documented residual production WebSocket infrastructure rollout.

Known deferred items at close: production API Gateway WebSocket/CDK route wiring, deploy/live smoke evidence, push/native notifications, email notification digests, payment provider integration, mobile polish, multilingual rollout, and support integrations. Richer AI teacher tools and automatic exercise generation were promoted to v3.7.

### v3.7 AI Teacher Tools And Exercise Generation

**Status:** Completed local release gate 2026-06-09
**Started:** 2026-06-09
**Completed:** 2026-06-09
**Audit:** `.planning/milestones/v3.7-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v3.7-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.7-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Add teacher-facing automatic summaries, suggested focus, draft explanations, and bounded exercise generation with teacher/admin review.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 116: AI Teacher Tools Contract And Generation Model.
- Phase 117: Backend Teacher Summary And Exercise Draft APIs.
- Phase 118: Tutor AI Tools And Exercise Draft UI.
- Phase 119: v3.7 Functional Release Gate And AI Tools Audit.

Key accomplishments:

- Defined reviewed-draft contracts for summaries, suggested focus, draft explanations, bounded exercises, input sources, lifecycle, and no-auto-send behavior.
- Added backend AI teacher draft persistence and tutor/admin APIs for summary draft generation, exercise draft generation, list/detail, regenerate, accept, reject, and archive.
- Added tutor request detail UI for summary drafts and exercise drafts with explicit `Draft only` and `not delivered` status.
- Completed backend pytest/focused Ruff evidence, frontend lint/build/browser evidence, and updated the feature gap audit.

Known deferred items at close: automatic student assignment or delivery, long-term adaptive sequencing, production AI quality/cost monitoring, payment-provider integration, production realtime infrastructure rollout, push/native/email notifications, mobile/multilingual polish, and support integrations. Full curriculum-aligned exercise banks were promoted to v3.8.

### v3.8 Full Curriculum Rollout

**Status:** Completed local release gate 2026-06-09
**Started:** 2026-06-09
**Completed:** 2026-06-09
**Audit:** `.planning/milestones/v3.8-MILESTONE-AUDIT.md`
**Roadmap:** `.planning/milestones/v3.8-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.8-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Roll out full curriculum structure and exercise bank coverage for math, physics, German, and English on top of the existing subject/topic/practice foundations.
**Phases:** 4
**Plans:** 4/4 complete
**Requirements:** 4/4 complete

Completed phases:

- Phase 120: Full Curriculum Rollout Contract And Content Model.
- Phase 121: Backend Curriculum Catalog And Exercise Bank APIs.
- Phase 122: Student/Parent Curriculum UX And Tutor Signals.
- Phase 123: Functional Release Gate And Curriculum Audit.

Key accomplishments:

- Defined curriculum hierarchy, supported subjects, grade/language metadata, content lifecycle states, lesson fields, exercise fields, and backfill behavior.
- Added backend curriculum catalog, lesson detail, exercise bank, and progress APIs while preserving existing practice progress and challenge-attempt behavior.
- Added student, parent, and tutor curriculum rollout UI signals for math, physics, German, and English.
- Preserved inactive/draft/preview/archived content boundaries and answer-key authorization.
- Completed backend pytest/Ruff evidence, frontend lint/build evidence, targeted Playwright evidence, and feature gap audit closeout.

Known deferred items at close: automatic student assignment or delivery of generated exercises, long-term adaptive sequencing, rich curriculum authoring workflow, production content QA/analytics, payment-provider integration, production realtime infrastructure rollout, push/native/email notifications, mobile/multilingual polish, and support integrations.

## Active

### v3.9 Payment Provider Integration MVP

**Status:** Active
**Started:** 2026-06-09
**Roadmap:** `.planning/milestones/v3.9-ROADMAP.md`
**Requirements:** `.planning/milestones/v3.9-REQUIREMENTS.md`
**Feature gap audit:** `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
**Goal:** Implement subscription checkout, provider webhook billing state, parent payment UX, and admin billing visibility for the first payment-provider integration.
**Phases:** 4
**Plans:** 2/4 complete
**Requirements:** 2/4 complete

Planned phases:

- Phase 124: Payment Provider Contract And Billing Model - Complete.
- Phase 125: Backend Checkout Subscription And Webhook APIs - Complete.
- Phase 126: Parent Payment UX And Admin Billing Operations.
- Phase 127: Functional Release Gate And Billing Audit.

---
*Last updated: 2026-06-09 after planning v3.9*
