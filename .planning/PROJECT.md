# STOA Backend

## What This Is

STOA is a learning platform backend for students, teachers/tutors, parents, and admins. This repository provides the FastAPI service that runs locally with Uvicorn and in production as an AWS Lambda/API Gateway API backed by Cognito, DynamoDB, S3, Bedrock, Rekognition, SQS, and SES.

The shipped report operations platform gives admins a production-verified, backend-mediated recovery workflow for weekly reports: list/detail operations metadata, retry one `generation_failed` report, resend one or more selected `email_failed` reports, run bounded async `email_failed` resend jobs, inspect append-only audit evidence, use a real admin UI without exposing private report artifacts, and follow an operator runbook for safe support use.

The completed v1.7 milestone turns that platform into a cleaner operational release gate by formalizing production admin credential ownership/rotation and adding metadata-only recovery evidence export.

The completed v1.8 milestone extends the same recovery platform to bounded async `generation_failed` retry jobs using existing recovery job and weekly report Lambda resources.

The completed v1.9 milestone adds failed/refused/not_found/skipped subset resume and support-safe evidence packages for incident operations.

The completed v2.0 milestone adds a controlled, metadata-only report edit draft/apply workflow for admins, with append-only audit evidence and no direct S3 artifact exposure.

The completed v2.1 milestone upgrades report editing toward backend-mediated versioned artifact edits with sanitized preview/diff, rollback metadata, and explicit CDK readiness before any artifact mutation implementation.

The completed v2.2 milestone closes the remaining artifact-editing operations gap by adding backend-mediated rollback, admin rollback controls, and a named safe-fixture production mutation verification path with cleanup evidence.

The completed v2.3 milestone turns manually assembled release evidence and safe-fixture verification into a repeatable, redacted operator workflow without expanding production mutation scope.

The completed v2.4 milestone turns support-safe recovery, rollback, fixture, and release evidence into manual ticket handoff packages without exposing private report artifacts or requiring unapproved third-party credentials.

The completed v2.5 milestone closes the deferred production verification gap for v2.4 support handoff by capturing deploy/runtime/CDK evidence and read-only production API/browser smoke.

The completed v2.6 milestone makes report operations audit evidence ready for stronger retention and future immutable storage without weakening privacy boundaries.

The completed v2.7 milestone turns that readiness into a CDK-governed immutable audit storage and legal hold foundation, starting with contracts and CDK readiness before any production write path is implemented.

The completed v2.8 milestone turns the v2.7 fail-closed foundation into CDK-managed immutable evidence storage deployment and configured metadata-only manifest object persistence.

The completed-local v2.9 milestone turns the v2.8 technical retention evidence into governance-ready retention policy approval and legal-hold operations, with production deploy/live smoke deferred.

The completed v3.0 milestone reconciled the original `stoa_docs` product baseline with the shipped system and closed the highest-priority MVP account/intake gaps before broader Phase 2 expansion.

The completed v3.1 milestone closed the remaining teacher-takeover MVP gaps: rich text/formula replies and response-time SLA tracking.

The completed v3.2 milestone closed the remaining visible MVP admin workflow from `stoa_docs`: content moderation for reported or abnormal learning content.

The completed v3.3 milestone makes the MVP manual subscription model usable before Stripe/TWINT integration.

The completed v3.4 milestone prepared Phase 2 learning expansion with subject taxonomy, prompt behavior, topic metadata, student profile seeds, and learning profile UI foundations.

The completed v3.5 milestone prepared notification and teacher-assistance foundations before full WebSocket rollout or automatic exercise generation.

The completed-local v3.6 milestone turns the notification foundation into full WebSocket realtime notifications.

The completed-local v3.7 milestone turns the teacher-assistance seeds and learning profile foundations into teacher-facing automatic summaries, suggested focus, draft explanations, and bounded exercise generation with review-before-use boundaries.

The completed-local v3.8 milestone turns the subject/topic/practice foundations into full curriculum rollout for math, physics, German, and English, including curriculum hierarchy, lesson/exercise bank coverage, student/parent UX, and tutor/admin curriculum signals.

The completed-local v3.9 milestone implements the first payment-provider integration MVP for STOA subscriptions: checkout, provider subscription state, webhooks, parent payment UX, and admin billing visibility.

The completed-local v4.0 milestone builds adaptive learning memory and reviewed assignment workflows from learning profile seeds, curriculum progress, AI exercise drafts, question history, and parent/tutor progress signals.

The completed-local v4.1 milestone prepared mobile-friendly and multilingual product polish foundations by defining responsive/mobile readiness contracts, localization backend support, language-safe response boundaries, and local release evidence before broader frontend/native rollout.

The completed-local v4.2 milestone promotes the local realtime notification foundation toward production-deliverable notification capability through production WebSocket delivery contracts, delivery operations, durable preferences, email digest readiness, and focused release evidence.

The completed-local v4.3 milestone moved the deferred frontend mobile and visual localization work into the `/Users/zhdeng/stoa-frontend` workspace, delivering selected responsive core-flow polish and visible English/German locale preference UI.

The completed-local v4.4 milestone moved the Stripe-first payment provider MVP toward live rollout readiness, production checkout/webhook verification, Stripe-backed TWINT inclusion, and first-pass billing operations support while keeping real customer charging externally gated.

The completed-local v4.5 milestone connects support-safe evidence packages to approved operational destinations and adds operator-visible handoff status while preserving metadata-only privacy boundaries.

The completed-local v4.6 milestone adds internal curriculum authoring, QA lifecycle, publish/rollback/archive safety, and bounded aggregate content-quality analytics while preserving published-only student/parent curriculum reads.

The completed-local v4.7 milestone turns the v4.4 payment readiness foundation into production activation automation: live Stripe/TWINT readiness checks, webhook registration readiness, direct refund execution, finance handoff, and rollout controls. Final live activation remains externally gated.

The completed-local v4.8 milestone expands the v4.5 support handoff foundation beyond the internal queue into approved third-party provider adapters, retry workers, two-way ticket synchronization, support SLA analytics, and controlled CRM/customer messaging. Final provider activation state is `provider-ready`; real external provider and CRM/customer writes remain gated on approved provider selection, credentials, destination policy, and rollout approval.

The completed-local v4.9 milestone promotes notification delivery from local WebSocket/backend readiness into production-deliverable backend capability: live WebSocket/API Gateway readiness, provider-gated email/push delivery, frontend/native notification UX handoff, native token registration records, and release evidence. Final rollout state is `deferred` pending live deployment, provider activation, frontend implementation, native app work, and explicit rollout approval.

The completed v5.0 milestone moves beyond selected responsive frontend and backend locale foundations into native/mobile rollout readiness and full localization governance: mobile app/API handoff, native notification token and offline-state handoff, translation management, broad copy QA, locale coverage, and client release evidence. It closed as `contract-ready`; frontend/native implementation and live activation remain separate follow-up work.

## Core Value

Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.

## Current State

**Production-verified shipped version:** v3.2 Content Moderation And Internal Operations on 2026-06-08
**Latest completed milestone:** v5.0 Native Mobile And Full Localization Governance on 2026-06-14 (contract-ready release gate)
**Active milestone:** None — awaiting next milestone selection

Delivered:

- Parent-owned child listing through `GET /parents/me/children`.
- Parent-owned child summary through `GET /parents/me/children/{child_id}/summary`.
- Parent-owned child learning history through `GET /parents/me/children/{child_id}/history`.
- Parent-owned report lookup through `GET /parents/me/children/{child_id}/report` and week-specific `GET /parents/me/children/{child_id}/reports/{week}`.
- Frontend parent services and pages use real backend route shapes and no longer silently hide parent-critical API failures behind demo fallback.
- Focused backend and frontend tests cover parent authorization, empty states, missing reports, and route contract alignment.
- CDK defines a scheduled weekly report Lambda, EventBridge Scheduler target, permissions, retry/DLQ behavior, and monitoring.
- Backend aggregates weekly student learning activity, generates parent-facing content with Bedrock and deterministic fallback, stores metadata/artifacts, and sends SES email.
- Scheduled orchestration is idempotent by `(parent_id, student_id, week_start)`.
- Parent API and frontend render generated, missing, pending, failed, and email-failed report states.
- Focused backend and frontend tests verify the report flow.
- Report artifacts use the canonical private key contract `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}`.
- `stoa-api` and `stoa-weekly-report` are deployed with `S3_REPORTS_BUCKET=stoa-reports-562923011260`.
- Deployed smoke invoked `stoa-weekly-report` and proved a private JSON artifact can be written and read back from S3 without public URLs or frontend S3 access.
- The reports bucket now enforces HTTPS-only S3 transport through CDK-managed bucket policy.
- API and weekly report Lambda report artifact S3 actions are scoped to `weekly-reports/*`.
- Deterministic smoke artifacts are deleted after smoke readback, and failed partial JSON writes are cleaned up best-effort.
- Admin-only report operations endpoints expose metadata and failed-delivery resend without public S3 URLs or raw artifact content.
- Admin report operations list/detail APIs expose generation, delivery, artifact availability, operation metadata, filters, pagination, and action eligibility.
- Admins can retry one `generation_failed` report through an atomic conditional claim and persisted retry audit fields.
- Admins can bulk resend selected `email_failed` reports and receive per-item `success`, `refused`, `not_found`, and `failed` results.
- Frontend `/admin/report-operations` uses real admin report operations APIs for filtering, detail inspection, retry, resend, selected bulk resend, and result rendering.
- Focused backend tests, frontend e2e, and live AWS checks verify report operations authorization, privacy boundaries, deployed Lambda state, API health/auth gate, and CDK diff.
- Production frontend `/admin/report-operations` route and bundle were verified with production API configuration and no private artifact markers.
- Production backend report operations API verifies admin-auth list/detail, bounded-scan pagination, valid non-admin rejection, and metadata-only response boundaries.
- Safe non-customer generation retry, single resend, and selected bulk resend smoke passed, with temporary Cognito/DynamoDB/S3 fixture cleanup confirmed.
- `stoa-api` has scoped SES send permission for report recovery email paths, and `StoaApiStack` final CDK diff is clean.
- Operators have a report recovery runbook covering retry/resend/bulk resend, observability, rollback, escalation, and known limits.
- Lambda package builds produce a manifest and CDK/CI guard against stale backend Lambda assets.
- Existing recovery actions write application-enforced append-only audit evidence.
- Admins can preview and create bounded async `email_failed` resend jobs with stable target snapshots, progress, cancellation, per-target results, and job/report audit evidence.
- Frontend `/admin/report-operations` exposes async job and audit workflows.
- Production read-only admin browser smoke verified the deployed route, auth, GET APIs, metadata-only privacy boundary, and no production mutation.
- v1.6 runbook, release gate, live verification evidence, and final audit are complete.
- Backend admin-only `GET /admin/reports/recovery-evidence` exports bounded metadata-only recovery job, target, and audit evidence without private artifact exposure or recovery mutation.
- Frontend `/admin/report-operations` exposes read-only recovery evidence export controls with metadata-only JSON preview, copy, and download.
- v1.7 release gate captured backend/frontend deploy evidence, Lambda manifest evidence, CDK diff classification, admin-only API request IDs, Cognito group membership, and production read-only browser smoke for evidence export with no production mutation.
- Backend recovery jobs support async `retry_generation` preview/create/execute/cancel/result/audit using the existing weekly report Lambda worker.
- Frontend `/admin/report-operations` exposes `Resend email` and `Retry generation` async recovery job modes.
- v1.8 release gate captured backend/frontend deploy evidence, Lambda manifest/runtime evidence, CDK diff classification, API request IDs, Cognito group membership, production bundle markers, and production read-only browser smoke for generation retry UI with no production mutation.
- Backend recovery jobs support failed/refused/not_found/skipped subset resume with preview/create APIs, stable target snapshots, source job links, and audit evidence.
- Backend support evidence packages export bounded metadata-only incident evidence for recovery jobs without private artifact exposure.
- Frontend `/admin/report-operations` exposes resume preview/create controls and support evidence package controls.
- v1.9 release gate captured backend/frontend deploy evidence, Lambda manifest/runtime evidence, CDK diff classification, API request IDs, Cognito group membership, production bundle markers, and production read-only browser smoke for resume/support UI with no production mutation.
- Backend report editing supports metadata-only edit draft create/read/apply for `admin_note`, `editor_summary`, and `status_note`.
- Report edit apply rejects stale drafts and writes append-only `apply_report_edit` audit evidence.
- Frontend `/admin/report-operations` exposes selected-report edit draft/apply controls.
- v2.0 release gate captured backend/frontend deploy evidence, Lambda manifest/runtime evidence, CDK diff classification, API request IDs, Cognito group membership, production bundle markers, and production read-only browser smoke for edit draft/apply UI with no production mutation.
- Backend artifact editing supports admin-only sanitized preview/read/apply APIs with versioned JSON/HTML artifact writes, stale-source rejection, rollback metadata, and redacted audit evidence.
- Frontend `/admin/report-operations` exposes selected-report artifact edit preview/apply controls without private S3 keys, presigned URLs, raw JSON, or raw unreviewed HTML.
- v2.1 release gate captured backend/frontend deploy evidence, Lambda manifest/runtime evidence, CDK diff classification, API request IDs, production bundle markers, and production read-only browser smoke for artifact edit preview/apply UI with no production mutation.
- Backend artifact rollback supports admin-only preview/read/apply APIs that switch current report artifact metadata pointers to validated prior versions while preserving version history.
- Frontend `/admin/report-operations` exposes selected-report artifact rollback preview/apply controls with required operator reason and sanitized version metadata.
- The safe-fixture harness refuses mutation by default and passed production mutation/rollback/cleanup verification for `stoa-safe-fixture-v2-2-rollback-2026-06-06`.
- v2.2 release gate captured backend/frontend deploy evidence, Lambda runtime evidence, CDK diff classification, production read-only API/browser smoke, and named safe-fixture mutation evidence.
- Phase 61 found and fixed a report lookup bug where artifact edit child entities could be returned from the parent GSI instead of the report summary row.
- Backend release evidence tooling validates redacted release bundles, reports missing required fields, inspects the approved safe fixture, and refuses unapproved production mutation.
- Frontend `/admin/report-operations` exposes read-only release evidence validation and safe-fixture status controls without rendering private artifact data.
- v2.3 release gate captured backend/frontend deploy evidence, Lambda manifest/runtime evidence, CDK diff classification, production API/browser smoke for release evidence endpoints/UI, privacy denylist results, and safe-fixture refusal evidence with no production mutation.
- Backend support handoff package APIs generate metadata-only, redacted handoff packages from recovery, release, fixture, and operator-note evidence.
- Support handoff package generation records append-only audit rows and refuses unapproved direct external support-system writes.
- Frontend `/admin/report-operations` exposes support handoff preview, copy, download, and refusal controls without rendering private artifact data.
- v2.4 local release gate captured backend/frontend quality gates, release evidence validation, privacy/refusal evidence, and milestone audit; v2.5 closed the production deploy/live smoke gap.
- v2.5 production closeout deployed backend/frontend support handoff changes, recorded Lambda runtime and CDK evidence, and passed production API/browser smoke for the support handoff workflow with no report artifact mutation or external support-system write.
- v2.6 defined a metadata-only audit retention contract, immutability boundary, privacy model, and no-new-CDK-resource readiness decision for retention manifests/status.
- Backend audit retention APIs expose admin-only status and manifest generation with canonical digests, privacy validation, destructive action refusal, and redacted append-only audit metadata.
- Frontend `/admin/report-operations` exposes audit retention status, manifest preview, copy, download, digest rendering, and refusal controls without rendering private artifact data.
- v2.6 release verification captured backend/frontend deploy evidence, Lambda runtime state, CDK diff classification, production API smoke, and production browser smoke with no report artifact mutation, no audit deletion, and no external write.
- v2.7 defined immutable audit storage and legal hold contracts with CDK as the source of truth for future WORM/Object Lock storage.
- Backend immutable evidence APIs expose admin-only status/persist metadata behavior, fail closed with `not_configured` while CDK-managed immutable storage is absent, and write create-only metadata objects before marking manifest references persisted when storage is configured.
- Backend legal hold APIs expose metadata-only status/apply/release behavior with append-only audit evidence, compare-and-set current-state writes, and no audit row deletion.
- Frontend `/admin/report-operations` exposes immutable evidence and legal hold controls with separate read-only status and explicit operator-reason mutation actions.
- v2.7 release verification captured backend/frontend deploy evidence, Lambda runtime state, CDK diff classification, production API smoke, guarded production browser smoke, and integration-audit remediation evidence with no report artifact mutation, audit deletion, immutable write, legal-hold mutation, or external write during smoke.
- v2.8 deployed CDK-managed immutable evidence storage with S3 Object Lock GOVERNANCE retention, API-only runtime configuration, scoped metadata-prefix S3 permissions, live immutable manifest persistence, DynamoDB metadata verification, S3 Object Lock header verification, and production browser smoke.
- v2.9 locally completed retention governance and legal-hold operations with governance contracts, backend metadata recording APIs, admin UI controls, local quality gates, and explicit production deploy/live smoke deferral.
- v3.1 completed teacher reply quality and SLA operations with a versioned rich reply/formula contract, backend sanitization/refusal, SLA timing fields, tutor reply composer and SLA badges, admin Teacher SLA metrics, deployment, and production-safe smoke.
- v3.2 completed content moderation report actions, moderation cases, admin queue/detail/actions, deployment, and production-safe smoke for internal operations.
- v3.3 completed parent subscription plan/request workflows, admin subscription request processing, tier application, parent/admin UI, and local release-gate verification for the manual MVP billing model.
- v3.4 added subject taxonomy, prompt behavior by subject, subject/topic backend support, student profile seeds, and learning profile UI foundations.
- v3.5 completed notification event contracts, backend event surfaces, teacher assistance summary seeds, and tutor/admin notification/summary UI foundations.
- v3.6 completed local functional WebSocket realtime transport, authenticated connection lifecycle, event fanout, realtime frontend client behavior, and fallback to the existing notification center.
- v3.7 completed teacher-facing automatic summaries, suggested teaching focus, draft follow-up explanations, and bounded practice exercise generation with teacher/admin review before use.
- v3.8 completed full curriculum hierarchy, lesson/exercise bank coverage, student/parent curriculum UX, and tutor/admin curriculum signals for math, physics, German, and English.
- v3.9 completed local functional payment-provider integration with subscription checkout, provider-managed billing state, webhook lifecycle handling, parent payment UX, and admin billing visibility.
- v4.0 added durable learning memory snapshots, next-practice recommendations, reviewed assignment workflows, student/tutor assignment route contracts, and parent progress signals.
- v4.1 completed mobile/responsive readiness contracts, durable locale preference APIs, language-safe adaptive response metadata, canonical-value stability tests, and local release evidence for backend polish readiness.
- v4.2 completed production notification delivery readiness contracts, durable notification preferences, preference-aware delivery decisions, admin delivery status, digest preview readiness, push preference readiness, and clean full backend release-gate checks.
- v4.3 completed selected frontend mobile responsive polish, backend-backed English/German language preference UI, `/auth/me` locale refresh behavior, and targeted browser release-gate evidence in `/Users/zhdeng/stoa-frontend`.

## Last Production-Verified Milestone

**v3.2 Content Moderation And Internal Operations** shipped on 2026-06-08.

Goal: close the remaining MVP admin content moderation workflow from `stoa_docs` with report actions, moderation cases, admin queue/detail/actions, and lightweight functional verification.

Completed phases:

- Phase 96: Content Moderation Contract And Data Model.
- Phase 97: Backend Moderation Reporting And Admin APIs.
- Phase 98: Moderation Reporting And Admin Queue UI.
- Phase 99: v3.2 Functional Release Gate And Docs Alignment.

## Latest Completed Milestone

### v4.5 Support Evidence Integrations And Operations Handoff

Goal: connect support-safe evidence packages to approved operational destinations and add operator-visible handoff status while preserving metadata-only privacy and fail-closed external-write behavior.

Completed phases:

- Phase 148: Support Destination Contract And Credential Readiness.
- Phase 149: Support Evidence Export Destination Integration.
- Phase 150: Operator Queue And Handoff Status Visibility.
- Phase 151: v4.5 Support Integration Release Gate.

## Latest Completed Milestone: v4.7 Payment Production Activation And Provider Automation

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`

**Status:** Completed backend release gate 2026-06-12; final live activation deferred pending external provider prerequisites.

**Goal:** Turn the v4.4 payment readiness foundation into controlled production activation automation.

**Target features:**

- Payment production activation contract and provider readiness.
- Live provider readiness API checks.
- Direct refund execution and finance handoff.
- Production webhook registration and rollout controls.
- v4.7 payment activation release gate.
- v4.8 support provider expansion contract, approved provider delivery, retry/sync, SLA analytics, controlled CRM message evidence, and release gate.

Outcome: v4.7 completed live Stripe/TWINT provider readiness checks, webhook readiness evidence, controlled direct refund execution, finance handoff export updates, and independent checkout/refund rollout controls. Final live activation is deferred until approved credentials, webhook registration, TWINT approval, finance acceptance, and explicit rollout enablement are available.

## Latest Milestone: v4.8 Support Provider Expansion And CRM Automation

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`

**Status:** Completed local backend release gate on 2026-06-12.

**Goal:** Expand the v4.5 internal support queue into approved provider-backed support operations and controlled CRM/customer messaging.

**Target features:**

- Support provider expansion contract and adapter readiness.
- Approved third-party support adapter and delivery worker.
- Retry workers and two-way ticket synchronization.
- Support SLA analytics and controlled CRM messaging.
- v4.8 support provider release gate and operations audit.

Outcome: v4.8 completed provider-neutral support adapter readiness, approved/configured third-party delivery, bounded retry, provider ticket sync, SLA analytics, and controlled CRM/customer message evidence. Final provider activation state is `provider-ready`: backend behavior is implemented and verified, but real external support-provider and CRM/customer writes remain gated on approved provider selection, credentials, destination policy, templates, and rollout approval.

## Completed Milestone: v4.9 Production Notification And Native Delivery Rollout

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`

**Status:** Complete locally; external rollout deferred.

**Goal:** Move notification delivery from local WebSocket/backend readiness into production-deliverable capability.

**Completed features:**

- Production notification rollout contract and ownership.
- Live WebSocket/API Gateway deployment readiness.
- Provider-backed email digest and push delivery.
- Frontend/native notification UX and token registration handoff.
- v4.9 production notification release gate and live smoke boundary evidence.

Outcome: v4.9 completed backend rollout readiness and handoff work. Live WebSocket/API Gateway smoke, real provider activation, frontend implementation, and native app work remain externally gated.

## Latest Completed Milestone: v5.0 Native Mobile And Full Localization Governance

Roadmap archive: `.planning/milestones/v5.0-ROADMAP.md`
Requirements archive: `.planning/milestones/v5.0-REQUIREMENTS.md`
Audit: `.planning/milestones/v5.0-MILESTONE-AUDIT.md`

**Status:** Completed 2026-06-14; rollout state `contract-ready`.

**Goal:** Move beyond selected responsive frontend and backend locale foundations into native/mobile rollout readiness and full localization governance.

**Completed features:**

- Native mobile and localization governance contract.
- Mobile app API readiness and client handoff.
- Native notification token and offline-state handoff.
- Localization governance, translation QA, and locale coverage.
- v5.0 native mobile localization release gate and handoff.

Outcome: v5.0 completed a contract-ready mobile/localization handoff. Frontend demo fallback cleanup, native app/APNS/FCM/offline implementation, live push/provider activation, semantic copy-owner review, hardcoded-string inventory, mobile visual text-fit QA, RTL, and future locale activation remain deferred.

## Requirements

### Validated

Existing codebase capabilities inferred from the mapped backend:

- FastAPI backend is composed under `src/stoa/main.py` with route modules for auth, students, parents, practice, questions, conversations, teachers/tutors, admin, and files.
- Cognito JWT validation and role resolution exist in `src/stoa/deps.py`.
- DynamoDB single-table repositories exist for users, questions, practice, and reports.
- Student summary, student question history, practice progress, mistakes, and report storage are available as data sources for parent-visible aggregation.

Shipped requirements:

- Parent users can list only their linked children through `/parents/me/children` - v1.0.
- Parent users can open a linked child summary backed by real backend aggregation - v1.0.
- Parent users can open a linked child learning history backed by real backend data - v1.0.
- Parent users can open child report pages that distinguish available reports from missing reports without fabricated content - v1.0.
- Parent-critical frontend flows use real backend API contracts and do not silently fall back to demo data - v1.0.
- Authorization prevents parents, students, teachers, tutors, and admins from using normal parent routes outside their intended access rules - v1.0.
- Required infrastructure assumptions are confirmed against CDK before backend implementation - v1.0.
- Weekly report automation infrastructure, generation, storage, email delivery, API display, frontend rendering, and verification shipped - v1.1.
- Reports bucket HTTPS-only transport enforcement was deployed and live-verified without bucket replacement - v1.3 Phase 19.
- API and weekly report Lambda report artifact S3 actions are scoped to `weekly-reports/*`, with image bucket permissions preserved - v1.3 Phase 20.
- Deterministic smoke artifacts and failed partial JSON artifacts have explicit cleanup paths, with live smoke proving cleanup performed - v1.3 Phase 21.
- Admin-only report operations metadata and failed-delivery resend endpoints are deployed with audit/status fields - v1.3 Phase 22.
- Admin report operations list/detail APIs, single generation retry, selected bulk resend, and admin UI shipped - v1.4.
- Report operations recovery authorization, privacy, backend tests, frontend e2e, and live deployment state evidence shipped - v1.4.
- Report recovery production rollout, live admin-auth API verification, safe non-customer retry/resend/bulk smoke, scoped API SES permission, operations runbook, and final CDK diff verification shipped - v1.5.

### Completed

Milestone v4.5 requirements are complete:

- SUPPORTINT-01: support destination contract and credential readiness - Phase 148.
- SUPPORTINT-02: support evidence export destination integration - Phase 149.
- SUPPORTINT-03: operator queue and handoff status visibility - Phase 150.
- VERIFY-28: v4.5 support integration release gate - Phase 151.

Milestone v4.4 requirements are archived in `.planning/milestones/v4.4-REQUIREMENTS.md` and are complete:

- PAYLIVE-01: live payment rollout contract and credential readiness - Phase 144.
- PAYLIVE-02: production checkout and webhook verification - Phase 145.
- PAYLIVE-03: refunds invoices tax and dunning readiness - Phase 146.
- VERIFY-27: v4.4 payment release gate and support audit - Phase 147.

Milestone v4.3 requirements are archived in `.planning/milestones/v4.3-REQUIREMENTS.md` and are complete:

- MOBILEUI-01: frontend workspace contract and mobile UAT plan - Phase 140.
- MOBILEUI-02: responsive student/parent/tutor core flow polish - Phase 141.
- I18NUI-01: visual localization and language preference UI - Phase 142.
- VERIFY-26: v4.3 browser release gate and localization audit - Phase 143.

Milestone v4.2 requirements are archived in `.planning/milestones/v4.2-REQUIREMENTS.md` and are complete:

- NOTIFYDEL-01: production notification infrastructure contract - Phase 136.
- NOTIFYDEL-02: WebSocket delivery operations and preference APIs - Phase 137.
- NOTIFYDEL-03: email digest and push preference readiness - Phase 138.
- VERIFY-25: v4.2 functional release gate and notification delivery audit - Phase 139.

Milestone v4.1 requirements are archived in `.planning/milestones/v4.1-REQUIREMENTS.md` and are complete:

- MOBILE-01: mobile-ready backend contract and gap audit - Phase 132.
- I18N-01: durable locale preference foundation - Phase 133.
- I18N-02: language-safe role route metadata - Phase 134.
- VERIFY-24: v4.1 release gate and deferred UI evidence - Phase 135.

Milestone v4.0 requirements are archived in `.planning/milestones/v4.0-REQUIREMENTS.md` and are complete:

- ADAPT-01: adaptive learning memory and assignment contract - Phase 128.
- ADAPT-02: backend learning memory and reviewed assignment APIs - Phase 129.
- UI-25: student/tutor assignment UX and parent progress signals - Phase 130.
- VERIFY-23: v4.0 functional release gate and personalization audit - Phase 131.

Milestone v3.9 requirements are archived in `.planning/milestones/v3.9-REQUIREMENTS.md` and are complete:

- PAY-01: payment provider contract and billing model - Phase 124.
- PAY-02: backend checkout subscription and webhook APIs - Phase 125.
- UI-24: parent payment UX and admin billing operations - Phase 126.
- VERIFY-22: v3.9 functional release gate and billing audit - Phase 127.

Milestone v3.8 requirements are archived in `.planning/milestones/v3.8-REQUIREMENTS.md` and are complete:

- CURRIC-01: full curriculum rollout contract and content model - Phase 120.
- CURRIC-02: backend curriculum catalog and exercise bank APIs - Phase 121.
- UI-23: student/parent curriculum UX and tutor signals - Phase 122.
- VERIFY-21: v3.8 functional release gate and curriculum audit - Phase 123.

Milestone v3.7 requirements are archived in `.planning/milestones/v3.7-REQUIREMENTS.md` and are complete:

- AITOOL-01: AI teacher tools contract and generation model - Phase 116.
- AITOOL-02: backend teacher summary and exercise draft APIs - Phase 117.
- UI-22: tutor AI tools and exercise draft UI - Phase 118.
- VERIFY-20: v3.7 functional release gate and AI tools audit - Phase 119.

Milestone v3.6 requirements are archived in `.planning/milestones/v3.6-REQUIREMENTS.md` and are complete:

- WS-01: full WebSocket transport contract and infrastructure readiness - Phase 112.
- WS-02: backend WebSocket connection and event delivery - Phase 113.
- UI-21: realtime notification client and UX - Phase 114.
- VERIFY-19: v3.6 functional release gate and realtime audit - Phase 115.

Milestone v3.5 requirements are archived in `.planning/milestones/v3.5-REQUIREMENTS.md` and are complete:

- NOTIFY-01: realtime notification and teacher assistance contract - Phase 108.
- NOTIFY-02: backend notification events and teacher summary seeds - Phase 109.
- UI-20: tutor/admin notification and summary UI - Phase 110.
- VERIFY-18: v3.5 functional release gate and expansion audit - Phase 111.

Milestone v3.4 requirements are archived in `.planning/milestones/v3.4-REQUIREMENTS.md` and are complete:

- LEARN-01: multi-subject taxonomy and prompt contract - Phase 104.
- LEARN-02: backend subject/topic support and student profile seeds - Phase 105.
- UI-19: student and parent learning profile UI - Phase 106.
- VERIFY-17: v3.4 functional release gate and expansion audit - Phase 107.

Milestone v3.3 requirements are archived in `.planning/milestones/v3.3-REQUIREMENTS.md` and are complete:

- SUBOPS-01: subscription operations contract and entitlement model - Phase 100.
- SUBOPS-02: backend subscription request and admin tier APIs - Phase 101.
- UI-18: parent subscription management and admin queue - Phase 102.
- VERIFY-16: v3.3 functional release gate and billing readiness - Phase 103.

Milestone v3.2 requirements are archived in `.planning/milestones/v3.2-REQUIREMENTS.md` and are complete:

- MOD-01: content moderation contract and data model readiness - Phase 96.
- MOD-02: backend moderation reporting and admin APIs - Phase 97.
- UI-17: moderation reporting and admin queue UI - Phase 98.
- VERIFY-15: v3.2 functional release gate and STOA docs alignment - Phase 99.

Milestone v3.1 requirements are archived in `.planning/milestones/v3.1-REQUIREMENTS.md` and are complete:

- TEACHOPS-01: teacher reply and SLA contract readiness - Phase 92.
- TEACHOPS-02: backend rich reply metadata and SLA tracking - Phase 93.
- UI-16: teacher reply composer and SLA visibility - Phase 94.
- VERIFY-14: v3.1 release gate and STOA docs alignment - Phase 95.

Milestone v3.0 requirements are archived in `.planning/milestones/v3.0-REQUIREMENTS.md` and are complete:

- DOCGAP-01: STOA docs feature gap audit and scope readiness - Phase 87.
- PRODVERIFY-13: v2.9 governance production verification closeout - Phase 88.
- AUTH-05: account lifecycle and parent binding gap closeout - Phase 89.
- QUESTION-07: OCR correction and daily question quota hardening - Phase 90.
- VERIFY-13: v3.0 release gate and docs alignment - Phase 91.

Milestone v2.9 requirements are archived in `.planning/milestones/v2.9-REQUIREMENTS.md` and are complete locally with production deploy/live smoke deferred:

- GOV-01: retention policy and legal hold governance readiness - Phase 83.
- GOV-02: backend retention approval and legal-hold review metadata - Phase 84.
- UI-15: admin retention governance and legal-hold runbook UI - Phase 85.
- VERIFY-12: v2.9 release gate and governance verification - Phase 86.

Milestone v2.8 requirements are archived in `.planning/milestones/v2.8-REQUIREMENTS.md` and are complete:

- IMSTORE-01: immutable evidence storage CDK design and deploy readiness - Phase 79.
- IMSTORE-02: CDK-managed immutable evidence storage resource - Phase 80.
- IMSTORE-03: backend immutable manifest object persistence enablement - Phase 81.
- VERIFY-11: v2.8 release gate and live immutable storage verification - Phase 82.

Milestone v2.7 requirements are archived in `.planning/milestones/v2.7-REQUIREMENTS.md` and are complete:

- IMMUTABLE-01: immutable audit storage contract and CDK readiness - Phase 75.
- IMMUTABLE-02: backend immutable retention manifest persistence - Phase 76.
- LEGALHOLD-01: legal hold and retention policy metadata - Phase 76.
- UI-14: admin immutable evidence and legal hold UI - Phase 77.
- VERIFY-10: v2.7 release gate and live verification - Phase 78.

Milestone v2.6 requirements are archived in `.planning/milestones/v2.6-REQUIREMENTS.md` and are complete:

- AUDITRET-01: audit retention contract and CDK readiness - Phase 71.
- AUDITRET-02: backend audit evidence sealing and retention manifest - Phase 72.
- AUDITRET-03: audit retention observability - Phase 72.
- UI-13: admin audit retention UI - Phase 73.
- VERIFY-09: v2.6 release gate and live verification - Phase 74.

Milestone v2.5 requirements are archived in `.planning/milestones/v2.5-REQUIREMENTS.md` and are complete:

- PRODVERIFY-01: v2.4 deploy evidence - Phase 70.
- PRODVERIFY-02: read-only production support handoff API smoke - Phase 70.
- PRODVERIFY-03: read-only production browser smoke - Phase 70.
- VERIFY-08: v2.5 closeout audit - Phase 70.

Milestone v2.4 requirements are archived in `.planning/milestones/v2.4-REQUIREMENTS.md` and are complete; production verification is closed by v2.5:

- HANDOFF-01: support handoff package contract - Phase 66.
- HANDOFF-02: destination policy, privacy model, and CDK readiness - Phase 66.
- HANDOFF-03: backend support handoff package APIs - Phase 67.
- HANDOFF-04: handoff observability and audit - Phase 67.
- UI-12: admin support handoff UI - Phase 68.
- VERIFY-07: v2.4 release gate and live verification - Phase 69; production verification closed by v2.5.

Milestone v2.3 requirements are archived in `.planning/milestones/v2.3-REQUIREMENTS.md` and are complete:

- EVIDENCE-AUTO-01: release evidence contract and redaction model - Phase 62.
- EVIDENCE-AUTO-02: backend release evidence collection tooling - Phase 63.
- FIXTURE-02: safe fixture lifecycle and inventory - Phases 62/63.
- UI-10: admin release evidence and fixture status UI - Phase 64.
- VERIFY-06: v2.3 release gate and milestone audit - Phase 65.

Milestone v1.7 requirements are archived in `.planning/milestones/v1.7-REQUIREMENTS.md` and are complete:

- ADMIN-01: production admin credential ownership, rotation, emergency disable, and access review procedure - Phase 38.
- ADMIN-02: Cognito admins group verification procedure that avoids exposing passwords, tokens, or session secrets - Phase 38.
- EXPORT-01: admin-only bounded metadata export for recovery job, target, result, and audit evidence - Phase 39.
- EXPORT-02: export privacy boundary that omits private S3 keys, presigned URLs, raw report JSON/HTML, auth tokens, and artifact payloads - Phase 39.
- EXPORT-03: read-only export observability and evidence logging - Phase 39.
- UI-01: read-only admin evidence export UI on `/admin/report-operations` - Phase 40.
- VERIFY-01: release gate and live evidence package for v1.7 closeout - Phase 41.

Milestone v1.8 requirements are archived in `.planning/milestones/v1.8-REQUIREMENTS.md` and are complete:

- GENJOB-01: generation retry preview - Phase 42/43.
- GENJOB-02: generation retry job creation - Phase 43.
- GENJOB-03: generation retry worker execution - Phase 43.
- GENJOB-04: authorization, privacy, and audit - Phase 43/45.
- GENJOB-05: admin UI - Phase 44.
- GENJOB-06: release gate - Phase 45.

Milestone v1.9 requirements are archived in `.planning/milestones/v1.9-REQUIREMENTS.md` and are complete:

- RESUME-01: resume preview - Phase 46/47.
- RESUME-02: resume job creation - Phase 47.
- RESUME-03: resume worker execution - Phase 47.
- RESUME-04: authorization, privacy, and audit - Phase 46/47/49.
- EVIDENCE-01: support evidence package - Phase 46/48.
- EVIDENCE-02: evidence package observability - Phase 48.
- UI-06: resume and evidence package UI - Phase 48.
- VERIFY-02: v1.9 release gate - Phase 49.

Milestone v2.0 requirements are archived in `.planning/milestones/v2.0-REQUIREMENTS.md` and are complete:

- EDIT-01: edit draft lifecycle - Phase 50/51.
- EDIT-02: apply edit - Phase 50/51.
- EDIT-03: audit evidence - Phase 51.
- EDIT-04: privacy and storage safety - Phase 50/51/53.
- UI-07: admin editing UI - Phase 52.
- VERIFY-03: v2.0 release gate - Phase 53.

Milestone v2.1 requirements are archived in `.planning/milestones/v2.1-REQUIREMENTS.md` and are complete:

- SAFETY-01: artifact editing contract and CDK readiness - Phase 54.
- ARTEDIT-01: artifact edit draft and preview - Phase 55.
- ARTEDIT-02: versioned artifact apply - Phase 55.
- ARTEDIT-03: audit and rollback evidence - Phase 55.
- ARTEDIT-04: privacy and storage safety - Phase 55.
- UI-08: admin artifact edit preview UI - Phase 56.
- VERIFY-04: v2.1 release gate - Phase 57.

Milestone v2.2 requirements are archived in `.planning/milestones/v2.2-REQUIREMENTS.md` and are complete:

- ROLLBACK-01: artifact rollback contract and CDK readiness - Phase 58.
- ROLLBACK-02: backend artifact rollback preview/apply APIs - Phase 59.
- ROLLBACK-03: rollback audit and safety evidence - Phase 59.
- FIXTURE-01: named safe artifact fixture protocol and harness - Phase 58/59.
- UI-09: admin artifact rollback UI - Phase 60.
- VERIFY-05: v2.2 release gate and safe fixture verification - Phase 61.

### Out of Scope

- Historical billing note: billing or paid subscription enforcement was not part of the original report automation MVP; v3.9 completed a local functional provider-backed subscription billing MVP.
- PDF generation - HTML/JSON report artifacts are enough for this milestone.
- Multi-language report generation beyond the primary parent-facing language chosen for MVP.
- Live payment rollout note: broad ERP/accounting automation, custom invoice rendering, and any non-Stripe TWINT or multi-provider orchestration remain outside the v4.4 rollout scope.
- Support integration note: unapproved external writes, raw report artifact exposure, presigned URLs, broad CRM automation, and customer messaging campaigns remain outside the v4.5 support handoff scope.
- Organization/school portal work - separate product surface.
- Real-time report generation on every parent page load - scheduled generation is the intended model.
- Freeform WYSIWYG report editor - v2.2 remains bounded artifact operations with sanitized preview/rollback controls.
- Live classroom work - separate product surface.
- Full admin analytics - separate admin analytics scope.
- Broad frontend redesign - v1.0 was integration and state correctness.

## Context

### Repositories

- Backend: `/Users/zhdeng/stoa-backend`
- Frontend: `/Users/zhdeng/stoa-frontend`
- Infrastructure/CDK: `/Users/zhdeng/stoa-infra`

### Backend Context

Relevant backend files:

- `src/stoa/routers/parents.py`
- `src/stoa/routers/students.py`
- `src/stoa/routers/practice.py`
- `src/stoa/db/repositories/user_repo.py`
- `src/stoa/db/repositories/question_repo.py`
- `src/stoa/db/repositories/report_repo.py`
- `src/stoa/db/repositories/practice_repo.py`
- `src/stoa/deps.py`

Current backend capabilities:

- Parent child listing exists through `/parents/me/children`.
- Child summary, learning history, latest report, and week-specific report lookups exist through `/parents/me/children/{child_id}/...`.
- Legacy `/parents/{parent_id}/...` child/report routes remain compatible for explicit legacy/admin use.
- Student summary, question history, practice progress, mistakes, conversations, and report storage are available as data sources for parent-visible aggregation.
- Weekly report aggregation, Bedrock/fallback generation, storage, email delivery, and scheduled job orchestration exist in backend services/jobs.

### Frontend Context

Relevant frontend files:

- `/Users/zhdeng/stoa-frontend/src/app/router/AppRouter.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/parent/`
- `/Users/zhdeng/stoa-frontend/src/services/parent/parentApi.ts`
- `/Users/zhdeng/stoa-frontend/src/services/parent/parentReportApi.ts`
- `/Users/zhdeng/stoa-frontend/src/services/demo/demoFallback.ts`

Current frontend state:

- Parent-critical child list, summary, history, and report services call `/parents/me/...` routes directly.
- Parent-critical pages render explicit loading, error, empty, missing, and available states.
- Demo fallback is no longer used for normal parent-critical child, summary, history, and report flows.

### Infrastructure Context

Relevant CDK files:

- `/Users/zhdeng/stoa-infra/stacks/auth_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/database_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/api_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/notification_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/monitoring_stack.py`

Known current resources:

- Cognito User Pool with app clients and role groups.
- DynamoDB single table with GSIs.
- S3 image/report/log buckets.
- Lambda FastAPI backend through API Gateway HTTP API.
- SQS FIFO teacher escalation queue.
- SES email identity.
- EventBridge schedule group and weekly report Lambda target exist in CDK.
- Infra CI builds `stoa-backend/dist` before CDK diff/deploy because Lambda assets are gitignored build artifacts.

## Constraints

- **Infrastructure first:** All new backend work must be checked against existing CDK in `/Users/zhdeng/stoa-infra` before implementation.
- **AWS resources:** Do not invent new AWS services, tables, buckets, Lambdas, queues, or indexes without proving current CDK/resources cannot support the need.
- **DynamoDB:** Reuse the existing single-table design unless a specific missing access pattern requires a new GSI.
- **CDK source of truth:** Any required infrastructure change must be implemented in CDK, not manually assumed.
- **Configuration:** Backend resource names and URLs must come from environment variables injected by CDK.
- **Frontend contract:** Frontend integration must target the real backend API contract and avoid silent demo fallback from parent-critical flows.
- **Authorization:** Every child-specific parent endpoint must verify ownership before reading or returning child data.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Prefer `/parents/me/...` routes for parent portal flows | Parent identity is already available from JWT and clients should not pass parent IDs for normal logged-in parent workflows | Good - shipped in v1.0 |
| Keep existing path-ID parent endpoints compatible where useful | Existing routes may still serve legacy or internal use cases while the portal moves to `/parents/me/...` | Good - legacy compatibility preserved in v1.0 |
| Treat report generation as a follow-up milestone | v1.0 needed query/display/empty states, not scheduled generation, emails, or PDFs | Good - deferred to next milestone candidate |
| Check CDK before backend data-access changes | The milestone explicitly depended on current DynamoDB/Cognito/Lambda resource definitions | Good - Phase 1 created the evidence ledger |
| Use local DynamoDB parent profile `user_id` as canonical parent ownership ID | Cognito `sub` can differ from local user IDs used by existing records | Good - used by parent resolver and ownership checks |
| Remove `withDemoFallback` from parent-critical flows | Parent portal correctness depends on surfacing real backend failures instead of replacing them with demo data | Good - shipped in frontend integration |
| Prefer a separate scheduled Lambda handler for weekly reports | EventBridge Scheduler should not invoke the Mangum API handler directly | Good - shipped in v1.1 |
| Store generated report before email completion | Parents must still be able to view reports if SES delivery fails | Good - shipped in v1.1 |
| Use `weekly-reports/` as the canonical private report artifact prefix | Matches shipped v1.1 behavior and avoids migrating existing artifact references | Good - verified in v1.2 |
| Keep report artifacts backend-mediated and private | Parent access must stay ownership-checked through backend routes, with no public S3 URL or direct frontend S3 fetch | Good - verified in v1.2 |
| Start v1.3 with security hardening before broader report product expansion | Live verification proved artifact storage works; the next risk is operational safety around that storage contract | Good - shipped in v1.3 |
| Use explicit smoke/partial cleanup instead of broad lifecycle cleanup | Cleanup keys are known and can use scoped `DeleteObject` without bucket listing | Good - shipped in v1.3 |
| Keep report operations backend-mediated and admin-only | Support needs metadata and resend controls without public S3 URLs or raw artifact exposure | Good - shipped in v1.3 |
| Build v1.4 as an admin recovery workflow before broader report product expansion | v1.3 shipped secure API-only controls; the next value is making them usable for support and adding safe batch recovery | Good - shipped in v1.4 |
| Start v1.5 with production rollout and safe live smoke before incident-wide automation | v1.4 shipped recovery code and local/e2e verification, but production UI deployment and safe mutation smoke remained residual gaps | Good - shipped in v1.5 |
| Keep recovery operations backend-mediated and metadata-only in production | Safe support tooling must not expose private report artifacts or direct S3 paths | Good - verified in v1.5 |
| Treat stale `../stoa-backend/dist` as a deployment risk | CDK deploys Lambda assets from local build output and can overwrite current code if not rebuilt | Good - documented in v1.5 runbook |
| Keep v1.6 browser smoke read-only by default | Production browser verification should prove route/auth/privacy without mutating customer report data | Good - verified in Phase 36 |
| Use secret-backed long-lived production admin credentials for smoke | v1.6 forbids temporary production admin smoke accounts but needs real admin auth | Good - credential path created in Phase 36; ownership/rotation remains operational follow-up |
| Start v1.7 with credential operations and metadata-only export | v1.6 proved the recovery workflow works; the next low-risk value is reusable evidence and credential lifecycle hygiene before larger mutation/orchestration work | Good - shipped in v1.7 |
| Start v1.8 with async generation retry jobs | v1.7 proved reusable evidence/export and credential operations; the next highest-value recovery expansion is bounded incident-wide generation retry using existing job infrastructure | Good - shipped in v1.8 |
| Start v1.9 with recovery subset resume and support evidence packages | v1.8 proved both resend and generation retry async jobs; the next operational gap is restarting failed subsets and packaging metadata-only support evidence | Good - shipped in v1.9 |
| Start v2.0 with metadata-only controlled report editing | Report editing is useful for support, but raw artifact rewrite needs a stronger safety model; bounded metadata fields give an auditable MVP without S3 exposure | Good - shipped in v2.0 |
| Start v2.1 with versioned artifact edit preview before freeform editing | v2.0 proved metadata edits; raw artifact editing needs versioned storage, rollback metadata, sanitized preview, and CDK readiness before customer-impacting mutation | Good - shipped in v2.1 |
| Start v2.2 with rollback and safe-fixture verification | v2.1 shipped versioned artifact apply but intentionally skipped production mutation smoke; rollback and named fixture cleanup are the next safety boundary before broader artifact editing use | Good - shipped in v2.2 |
| Start v2.3 with release evidence automation and fixture lifecycle | v2.2 proved safe-fixture mutation/cleanup, but the evidence workflow remains manually assembled and the production fixture needs repeatable lifecycle controls | Good - shipped in v2.3 |
| Start v2.4 with support evidence handoff packages | v2.3 made release and fixture evidence repeatable; the next support gap is package handoff into tickets without exposing private artifacts or adding unapproved integrations | Good - shipped in v2.4 |
| Start v2.5 with production support handoff verification closeout | v2.4 closed locally with production live smoke deferred; the next priority is deploy evidence and read-only production verification before support use | Good - shipped in v2.5 |
| Start v2.6 with audit retention and immutable evidence readiness | Support and release evidence are now production-verified; recurring deferred risk is stronger audit retention/WORM readiness without exposing private artifacts | Good - shipped in v2.6 |
| Start v2.7 with immutable audit storage and legal hold foundation | v2.6 proved metadata-only readiness but deferred compliance-grade WORM/Object Lock storage, legal hold administration, retention policy administration, and full manifest object persistence | Good - shipped in v2.7 |
| Start v2.8 with CDK-managed immutable evidence storage deployment | v2.7 shipped fail-closed backend/UI foundations but left CDK-managed immutable storage resource deployment and full immutable manifest object persistence as residual gaps | Good - shipped in v2.8 |
| Start v2.9 with retention governance and legal hold operations | v2.8 proved technical Object Lock-backed immutable evidence persistence but left formal retention-period approval and legal-hold operating procedure as residual gaps | Complete locally; production deploy/live smoke deferred |
| Start v3.0 with stoa_docs gap closeout and account intake hardening | `stoa_docs` MVP is mostly implemented, but account lifecycle, parent binding, OCR correction, robust question quota, and v2.9 production verification remain high-priority gaps | Good - shipped in v3.0 |
| Start v3.1 with teacher reply quality and SLA operations | After v3.0, remaining MVP-level gaps are concentrated in teacher rich text/formula replies and response-time tracking | Good - shipped in v3.1 |
| Start v3.2 with content moderation and internal operations | After v3.1, the only remaining visible MVP admin workflow in `stoa_docs` is content moderation; internal development should prioritize usable feature flow over broad security/compliance evidence | Good - shipped in v3.2 |
| Start v3.3 with subscription operations MVP | `stoa_docs` defines manual paid onboarding before Stripe/TWINT; parent/admin subscription workflows are the next direct product and business-function gap | Good - local release gate complete |
| Start v3.4 with learning expansion foundation | `stoa_docs` Phase 2 calls for multi-subject support, student memory, and AI teacher tools; taxonomy and profile seeds should precede broad curriculum or exercise generation | Good - local release gate complete |
| Start v3.5 with notification and teacher assistance foundation | `stoa_docs` Phase 2 calls for realtime notifications and AI teacher tools; event and summary foundations should precede WebSocket rollout or automatic exercise generation | Good - local release gate complete |
| Start v3.6 with full WebSocket realtime notifications | User explicitly selected full WebSocket realtime notifications after v3.5 foundation; existing durable notification events can now become realtime transport payloads | Good - local release gate complete |
| Start v3.7 with AI teacher tools and exercise generation | `stoa_docs` Phase 2 calls for AI teacher tools, automatic summaries, and practice generation; v3.4 learning profile seeds and v3.5 assistance seeds provide enough foundation for reviewed draft generation | Good - local release gate complete |
| Start v3.8 with full curriculum rollout | `stoa_docs` Phase 2 calls for broad multi-subject curriculum expansion; v3.4 subject/topic foundations and existing practice lesson/challenge data can now be promoted into full curriculum catalog and exercise bank scope | Good - local release gate complete |
| Start v3.9 with payment provider integration MVP | `stoa_docs` Phase 2 calls for Stripe subscription payment and credit card/TWINT support; v3.3 manual subscription operations provide the local entitlement model and admin override surface needed for provider-backed billing | Good - local release gate complete |
| Start v4.0 with adaptive learning memory and assignment | `stoa_docs` Phase 2 calls for personalized learning memory; v3.4 profile seeds, v3.7 AI exercise drafts, and v3.8 curriculum progress now provide enough signal for reviewed assignment workflows | Complete locally - backend release gate passed |
| Start v4.1 with mobile and multilingual polish foundation | Mobile and multilingual polish are recurring deferred product gaps after the Phase 2 learning and billing foundations; backend contracts and language-safe boundaries should precede broader frontend/native rollout | Complete locally - backend release gate passed |
| Start v4.2 with production notification delivery readiness | `stoa_docs` still calls for realtime notification delivery beyond local WebSocket behavior; this backend workspace can advance production delivery contracts, preferences, digest readiness, and operator-visible delivery state while frontend/native work remains separate | Complete locally - backend release gate passed |
| Start v4.3 with frontend mobile and visual localization rollout | v4.1 delivered backend locale/mobile contracts and `/Users/zhdeng/stoa-frontend` exists; the next visible product gap is mobile-responsive UI and English/German visual localization | Complete locally - frontend release gate passed |
| Start v4.4 with live payment provider rollout | v3.9 delivered the local Stripe-first billing MVP, but `stoa_docs` still has business-critical payment gaps around live credentials, checkout/webhook verification, Stripe-backed TWINT rollout, refunds, invoices, tax/accounting, and dunning | Complete locally - backend release gate passed |
| Start v4.5 with support evidence integrations | Support handoff packages already exist, but approved destination integration and operator-visible handoff status remain manual gaps | Complete locally - backend release gate passed |
| Plan v4.6 curriculum authoring and analytics | v3.8 and v4.0 created curriculum and adaptive-learning foundations; the next product value is internal authoring, QA, and actionable content analytics | Complete locally - backend release gate passed |
| Start v4.7 payment production activation | v4.4 delivered local payment readiness, but live provider activation still needs approved Stripe/TWINT readiness checks, webhook registration, direct refunds, finance handoff, and explicit rollout controls | Complete locally - backend release gate passed; final live activation deferred |
| Start v4.8 support provider expansion | v4.5 delivered internal queue support handoff, but approved third-party adapters, retry workers, two-way sync, SLA analytics, and controlled CRM/customer messaging remain the next support operations gap | Complete locally - backend release gate passed; provider activation state `provider-ready` |
| Start v4.9 production notification rollout | v3.6 delivered local realtime notifications and v4.2 delivered backend production readiness, but live WebSocket/API Gateway deployment, provider-backed email/push, frontend/native visuals, token registration, and live smoke remain the next notification gap | Complete locally - backend release gate passed; rollout state `deferred` |
| Start v5.0 native mobile and localization governance | v4.1 delivered backend mobile/locale foundations, v4.3 delivered selected frontend mobile/localization, and v4.9 delivered notification/native handoff; the next gap is native/mobile rollout readiness and full localization governance | Complete - contract-ready release gate passed |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? Move to Out of Scope with reason
2. Requirements validated? Move to Validated with phase reference
3. New requirements emerged? Add to Active
4. Decisions to log? Add to Key Decisions
5. "What This Is" still accurate? Update if drifted

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check - still the right priority?
3. Audit Out of Scope - reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-14 after completing v5.0 native mobile localization governance*
