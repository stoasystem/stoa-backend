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

The completed v5.1 milestone moves curriculum foundations into product-ready operations: rich curriculum editor UI/API handoff, production content migration pipeline, validation/rollback evidence, assignment automation readiness, and adaptive sequencing readiness. It closed as readiness-complete; full frontend editor implementation, production import, migration API/UI, candidate generation, and warehouse analytics remain separate follow-up work.

The completed v5.2 milestone turns adaptive learning memory, reviewed assignments, curriculum analytics, and curriculum product readiness into backend/API-ready adaptive sequencing and warehouse analytics: multi-signal recommendations, assignment outcome feedback, aggregate warehouse export/readiness, and operator dashboard contracts. It closed as `warehouse-ready`; live warehouse/BI deployment, frontend dashboard integration, fully autonomous tutoring, and automatic assignment delivery remain future scope.

The completed v5.3 milestone turns those v5.2 recommendations into controlled assignment automation from reviewed sources: automation policy contracts, candidate batch preview, approved-batch assignment execution, deterministic source idempotency, role-safe automation metadata, and tutor/admin/family visibility handoff. It closed as `automation-ready`; frontend implementation, live notification delivery, native apps, live warehouse/BI deployment, fully unreviewed autonomous tutoring, and external provider activation remain future scope.

The completed v5.4 milestone makes those v5.2/v5.3 learning operations usable in the frontend: tutor/admin automation review, operator learning dashboards, student assignment explanations, parent child progress explanations, and no-demo-fallback learning operations API integration. It closed as `frontend-ready`; production frontend deploy/live smoke, native apps, live warehouse/BI deployment, live notification delivery, automatic human tutor dispatch, and external provider activation remain future scope.

The completed v5.5 milestone turns the manual teacher queue/takeover workflow into backend dispatch-ready routing: teacher/tutor candidate ranking, conditional dispatch claims, stale reassignment behavior, teacher queue filtering, takeover compatibility, and admin dispatch SLA/load visibility. It closed as `dispatch-ready`; production scheduled worker/CDK wiring, live staffing calendar integration, frontend operator dashboard implementation, native push dispatch notifications, payroll/compensation automation, and live production smoke remain future scope.

The completed v5.6 milestone makes paid access real for linked students: parent-paid or manually overridden access now resolves into deterministic effective entitlement and question quota behavior.

The completed v5.7 milestone makes question usage durable and support-visible: successful quota-governed question submissions now write privacy-safe usage ledger events, can be reconciled with daily counters, and can be summarized for parents/admins without exposing private question content or billing internals.

The completed v5.8 milestone replaces placeholder email verification for new registrations with Cognito sign-up confirmation, enforces verified email before token return, adds resend/expiry/support visibility, and explicitly defers login-code/passwordless behavior until a real Cognito custom-auth flow exists.

The completed v5.9 milestone composes parent/admin account operations visibility across billing, entitlement, usage, verification, and child binding state with privacy-safe parent summaries and bounded admin support detail.

The completed v5.10 milestone makes those account operations capabilities usable in the web frontend: email verification resend/confirm UX, parent account operations UI, admin account operations console, focused frontend e2e coverage, backend contract evidence, and production read-only smoke planning.

The completed v5.11 milestone extends usage ledger coverage beyond question submissions with governed action taxonomy, privacy-safe ledger events for chat/teacher-help/practice/assignment/generation flows, multi-action reconciliation, and parent/admin account operations compatibility.

The completed v5.12 milestone implements the curriculum editor and content migration buildout that v5.1 left deferred: explicit curriculum capabilities, backend draft patch/validation/diff/audit APIs, migration dry-run/apply/evidence APIs, and a frontend admin curriculum operations console.

The completed v5.13 milestone makes paid access locally production-ready: parent-facing billing uses real subscription APIs without demo fallback, webhook reconciliation is idempotent and support-visible, stale provider events cannot regress active access, and bounded billing support evidence is visible to admins.

The partial-gate v5.14 milestone makes verification and login reliability locally stronger: backend verification confirm/resend/login edge cases are hardened, login-code/passwordless remains explicitly deferred with no token minting, and parent/admin account operations show verification recovery evidence. The final focused frontend e2e gate remains blocked by platform usage-limit approval and must stay visible until rerun.

The completed v5.15 milestone focuses on usage, quota, and product stability: real usage-flow coverage, ledger idempotency, quota reconciliation, parent/admin support explanations, and local smoke/regression gates.

The completed v5.16 milestone verifies the product end to end across auth, verification, billing, entitlement, usage/quota, curriculum, teacher help, and support views. It closed the residual v5.14 focused frontend e2e blocker and produced release evidence that separates local implementation completeness from external provider blockers.

The completed v5.17 milestone converts external provider blockers into release-operation evidence: admin-only activation smoke reports for payment/auth, notification/support, and production readiness, deterministic blocked/read-only states, rollback/disable controls, and a production read-only smoke runbook.

The completed v5.18 milestone activates local, support-safe BI observability contracts: aggregate warehouse readiness/export, operator dashboards, APM/alert routing, and analytics runbooks that separate product regressions from provider blockers.

The completed v5.19 milestone establishes native mobile source readiness: Expo/React Native app shell, Cognito-compatible auth/session contracts, student/parent journey adapters, native push/deep-link contracts, bounded offline/read-through policy, localization fixtures, and release evidence.

The completed v5.20-v5.24 sequence adds local contracts for native build/device readiness, AI teaching operations, customer lifecycle messaging, enterprise hardening, and limited pilot launch readiness. v5.24 ends with a conditional pilot recommendation, not a real-user activation approval.

The completed v5.25 milestone burns down the remaining activation blockers in local contract form before any real pilot users are enabled: payment, notifications, support CRM, BI/APM, mobile release/TestFlight, production restore, live tabletop, staffing, cohort, and rollback. It adds a safe-start gate that defaults to `hold` until required blockers are cleared or explicitly disabled.

The v5.26-v5.29 pilot execution, remediation, controlled expansion, and public launch readiness milestones are now contract-complete locally: STOA has metadata-only evidence contracts and tests for pilot execution controls, outcome decisions, remediation gates, expansion gates, and public-launch readiness gates. Real-user pilot execution, expansion, paid marketing, provider writes, and public launch remain externally gated by explicit operational approval and live evidence.

The completed v5.30 milestone moves from local contracts to live approval and provider/readiness evidence. It adds live approval, provider/mobile evidence, restore/tabletop/launch-room evidence, and live activation gates that default to `hold` until complete approved evidence is supplied.

The v5.31-v5.34 live pilot execution, live remediation, controlled expansion execution, and public launch/post-launch operations milestones are now contract-complete locally. Real pilot execution, expansion, public launch, paid marketing, and uncontrolled provider writes remain gated by explicit approval and live evidence.

The v5.35-v5.39 real pilot start, live operations feedback, revenue conversion, learning quality, and platform/internal operations scale milestones are now contract-complete locally. Each gate defaults to hold or remediation until current approved evidence is supplied.

The v6.0 milestone is complete locally. It adds current real evidence inventory, account/payment/usage smoke, notification/support/mobile/provider evidence, launch packet dry-run, and a pilot start decision gate. The local default remains `hold`; real pilot start still requires current approved external evidence.

The v6.1 milestone is complete locally. It adds first-cohort/blocker remediation contracts for account/login/verification/role fixes, entitlement/usage/notification/support fixes, first-learning-action/mobile friction fixes, and a remediation release gate.

The v6.2 milestone is complete locally. It adds paid conversion, usage/quota reliability, verification/recovery, billing lifecycle support, and revenue reliability gate contracts. v6.3 receives learning/product-quality risks separately from closed billing/account risks.

## Core Value

Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.

## Current State

**Production-verified shipped version:** v3.2 Content Moderation And Internal Operations on 2026-06-08
**Latest completed milestone:** v6.2 Paid Conversion Usage And Account Reliability Completion on 2026-07-08 (local revenue/account reliability contracts; default hold)
**Residual partial gate:** real-user activation, controlled growth, paid marketing, and public launch still require current approved external evidence, provider/mobile evidence, approved accounts, support staffing, production restore/tabletop evidence, launch-room readiness, and support capacity.
**Active milestone:** none — awaiting v6.3 start
**Next planned milestones:** v6.3 Learning Outcome And AI Curriculum Quality Sprint; v6.4 Operations Scale Release And Observability Hardening.

## Completed Milestone: v6.0 Real Evidence Capture And Pilot Start Execution

**Goal:** Move beyond local pilot/launch contracts by adding current real evidence contracts, account/payment/usage/verification/notification/support/mobile smoke contracts, and a pilot start gate with honest start/hold output.

**Target features:**
- Real evidence inventory across production/admin/provider/mobile/support access and approvals.
- Account, payment, usage ledger, quota, login/email verification, notification, support, and mobile smoke with approved accounts.
- Pilot cohort launch packet with communications, support staffing, dashboards, rollback, pause criteria, and dry-run evidence.
- Pilot start decision gate that starts a narrow cohort only on `start_limited_pilot`; otherwise it produces an executable blocker package.

Prior milestone outcome:

- v5.25 safe-start contracts default to `hold`.
- v5.26-v5.29 are locally contract-complete for pilot execution, remediation, expansion, and public launch readiness, but they do not approve real users.
- Real-user activation remains conditional on explicit approval and live evidence.

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

Roadmap archive: `.planning/milestones/v4.7-ROADMAP.md`
Requirements archive: `.planning/milestones/v4.7-REQUIREMENTS.md`

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

Roadmap archive: `.planning/milestones/v4.8-ROADMAP.md`
Requirements archive: `.planning/milestones/v4.8-REQUIREMENTS.md`

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

Roadmap archive: `.planning/milestones/v4.9-ROADMAP.md`
Requirements archive: `.planning/milestones/v4.9-REQUIREMENTS.md`

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

## Latest Completed Milestone: v5.1 Rich Curriculum Editor And Production Content Migration

Roadmap archive: `.planning/milestones/v5.1-ROADMAP.md`
Requirements archive: `.planning/milestones/v5.1-REQUIREMENTS.md`
Audit: `.planning/milestones/v5.1-MILESTONE-AUDIT.md`

**Status:** Completed 2026-06-14; rollout state readiness-complete.

**Goal:** Move curriculum foundations into product-ready operations with rich editor readiness, production content migration, assignment automation readiness, and adaptive sequencing readiness.

**Completed features:**

- Rich curriculum editor and migration contract.
- Admin rich curriculum editor UI and API readiness.
- Production content migration pipeline and validation.
- Assignment automation and adaptive sequencing readiness.
- v5.1 curriculum product release gate and handoff.

Outcome: v5.1 completed the curriculum product readiness layer while final payment/support external activation remains blocked on external prerequisites. Frontend editor implementation, backend rich-field expansion, production content import, migration API/UI, candidate generation, duplicate prevention, warehouse analytics, and fully autonomous tutoring remain deferred.

## Latest Completed Milestone: v5.2 Adaptive Sequencing And Warehouse Analytics

Roadmap archive: `.planning/milestones/v5.2-ROADMAP.md`
Requirements archive: `.planning/milestones/v5.2-REQUIREMENTS.md`
Audit: `.planning/milestones/v5.2-MILESTONE-AUDIT.md`
Phase evidence: `.planning/milestones/v5.2-phases/`

**Status:** Completed backend/API release gate 2026-06-15.

**Goal:** Turn adaptive learning memory, reviewed assignments, curriculum analytics, and curriculum product readiness into deeper adaptive sequencing and warehouse-backed analytics readiness.

**Completed phases:**

- Phase 181: Adaptive Sequencing And Warehouse Analytics Contract.
- Phase 182: Adaptive Sequencing Recommendation Engine.
- Phase 183: Assignment Outcome Feedback Loop.
- Phase 184: Warehouse Analytics Export And Operator Dashboards.
- Phase 185: v5.2 Adaptive Sequencing Analytics Release Gate.

**Outcome:** v5.2 closed as `warehouse-ready` for backend/API readiness. Live warehouse/BI deployment, frontend dashboard integration, fully autonomous tutoring, automatic assignment delivery, and final payment/support provider activation remain deferred.

## Latest Completed Milestone: v5.4 Frontend Learning Operations And Automation Dashboards

Roadmap archive: `.planning/milestones/v5.4-ROADMAP.md`
Requirements archive: `.planning/milestones/v5.4-REQUIREMENTS.md`
Audit: `.planning/milestones/v5.4-MILESTONE-AUDIT.md`
Phase evidence: `.planning/milestones/v5.4-phases/`

**Status:** Completed frontend-ready release gate 2026-06-15.

**Goal:** Make v5.2/v5.3 backend learning operations product-usable in tutor/admin/student/parent frontend workflows.

**Completed phases:**

- Phase 191: Frontend Learning Operations And Automation Dashboard Contract.
- Phase 192: Tutor Admin Automation Review Console.
- Phase 193: Learning Operations Dashboard Integration.
- Phase 194: Student Parent Assignment Explanation UX.
- Phase 195: v5.4 Frontend Learning Operations Release Gate.

**Outcome:** v5.4 closed as `frontend-ready` with `/Users/zhdeng/stoa-frontend` implementation commits `3364a39` and `ebeebba`. Verification passed `npm run build`, `npm run lint`, and `npx playwright test tests/e2e/learning-operations.spec.ts`. Production frontend deploy/live smoke, native apps, live warehouse/BI deployment, live notification delivery, automatic human teacher/tutor dispatch, and external provider activation remain deferred.

## Latest Completed Milestone: v5.5 Automatic Teacher Dispatch And SLA Load Balancing

Roadmap archive: `.planning/milestones/v5.5-ROADMAP.md`
Requirements archive: `.planning/milestones/v5.5-REQUIREMENTS.md`
Audit: `.planning/milestones/v5.5-MILESTONE-AUDIT.md`
Phase evidence: `.planning/milestones/v5.5-phases/`

**Status:** Completed dispatch-ready backend release gate 2026-06-15.

**Function purpose:** Reduce waiting time after a student requests human help by automatically routing escalated questions to eligible teachers/tutors, reassigning timed-out requests, and exposing queue/SLA health to operators.

**Implementation strategy:** Reuse existing request-teacher, teacher queue, takeover, reply, resolve, notification, and SLA primitives. Add a dispatch planner, conditional claim metadata, timeout/reassignment worker, teacher queue filters, and operator dispatch dashboard. This is dispatch routing, not AI auto-answering.

**Completed phases:**

- Phase 196: Teacher Dispatch And SLA Load Balancing Contract.
- Phase 197: Dispatch Planner And Candidate Ranking.
- Phase 198: Automatic Dispatch Claim And Reassignment Worker.
- Phase 199: Teacher Queue And Operator Dispatch Visibility.
- Phase 200: v5.5 Teacher Dispatch Release Gate.

**Outcome:** v5.5 closed as `dispatch-ready` with backend implementation commit `7f1d759`, audit commit `849b97a`, and release gate commit `e5ce750`. Verification passed 16 focused backend tests and targeted Ruff. Production scheduled worker/CDK wiring, live staffing calendar integration, frontend operator dashboard implementation, native push dispatch notifications, payroll/compensation automation, and live production smoke remain deferred.

## Completed Milestone: v5.6 Effective Entitlements And Paid Access Enforcement

Roadmap archive: `.planning/milestones/v5.6-ROADMAP.md`
Requirements archive: `.planning/milestones/v5.6-REQUIREMENTS.md`
Phase evidence: `.planning/milestones/v5.6-phases/`

**Status:** Completed local backend release gate 2026-07-03 with rollout state `entitlement-ready`.

**Function purpose:** Make paid access real for linked students. Parent billing or manual overrides must resolve into an effective student entitlement and enforce the correct question quota.

**Implementation strategy:** Build from the Phase 201 code audit. Existing billing updates parent profile tiers, while question quota reads the student's own tier; close that entitlement gap first. Keep billing/webhook/manual flows stable, implement a resolver service, enforce it in question quota, and expose entitlement summary. Defer usage ledger, verification, and full operations visibility to v5.7-v5.9.

**Completed phases:**

- Phase 202: Entitlement Contract And Access Policy.
- Phase 203: Entitlement Resolver Service And Parent Child Mapping.
- Phase 204: Student Paid Access Enforcement.
- Phase 205: Entitlement Visibility And Focused Tests.
- Phase 206: v5.6 Entitlement Release Gate.

**Outcome:** v5.6 added an effective entitlement resolver, made question quota use effective entitlement limits, exposed parent/admin entitlement summaries, and passed focused entitlement/question/subscription tests plus Ruff. Production deploy/live smoke remains separate.

**Follow-up milestones:**

- v5.8 Email Verification And Login Code Policy.
- v5.9 Parent Admin Operations Visibility.

## Completed Milestone: v5.7 Usage Ledger And Quota Reconciliation

Roadmap archive: `.planning/milestones/v5.7-ROADMAP.md`
Requirements archive: `.planning/milestones/v5.7-REQUIREMENTS.md`

**Status:** Completed local backend release gate 2026-07-03 with rollout state `usage-ledger-ready`.

**Function purpose:** Turn quota usage from counter-only behavior into durable, queryable usage ledger events and reconcile those events with existing daily quota counters.

**Implementation strategy:** Keep the existing atomic daily counter as the enforcement primitive. Add a privacy-safe usage ledger for quota-governed actions, starting with question submissions, then add repeatable reconciliation and enough parent/admin support visibility to explain usage state. Keep email verification, login-code policy, and the full operations console in v5.8 and v5.9.

**Completed phases:**

- Phase 207: Usage Ledger Contract And Idempotency.
- Phase 208: Question Usage Ledger Recording.
- Phase 209: Quota Counter Reconciliation.
- Phase 210: Usage Visibility And Focused Tests.
- Phase 211: v5.7 Usage Ledger Release Gate.

**Outcome:** v5.7 added privacy-safe usage ledger events for question submissions, optional idempotency keys, counter-versus-ledger reconciliation, bounded counter repair, parent child usage summaries, and admin usage/reconciliation support endpoints. Focused usage ledger, question, entitlement, and subscription operation tests plus Ruff passed. Full operations console remains v5.9 scope.

**Follow-up milestones:**

- v5.8 Email Verification And Login Code Policy.
- v5.9 Parent Admin Operations Visibility.

## Completed Milestone: v5.8 Email Verification And Login Code Policy

Roadmap archive: `.planning/milestones/v5.8-ROADMAP.md`
Requirements archive: `.planning/milestones/v5.8-REQUIREMENTS.md`
Audit archive: `.planning/milestones/v5.8-MILESTONE-AUDIT.md`

**Status:** Completed local backend release gate 2026-07-03 with rollout state `policy-deferred`.

**Function purpose:** Replace placeholder or ambiguous account verification behavior with an explicit backend contract for registration, email verification states, resend/expiry handling, and login-code/passwordless policy.

**Implementation strategy:** Define the verification state and route policy first, then enforce it through registration and account lifecycle paths without breaking existing role onboarding or parent/student binding. Add safe resend/expiry behavior and bounded support visibility, then either implement a Cognito-compatible login-code flow or gate/defer unsupported behavior so clients cannot mistake placeholders for production authentication.

**Completed phases:**

- Phase 212: Email Verification Contract And Account State Policy.
- Phase 213: Registration Verification Enforcement.
- Phase 214: Verification Resend And Expiry Operations.
- Phase 215: Login Code Policy And Auth Lifecycle Tests.
- Phase 216: v5.8 Verification Release Gate.

**Outcome:** v5.8 added Cognito `sign_up`/`confirm_sign_up` email verification for new registrations, blocked token return until verification is complete, added resend/expired-state handling, exposed bounded admin verification support status, and explicitly deferred login-code/passwordless behavior without minting placeholder tokens. Focused auth lifecycle, entitlement, usage, and Ruff checks passed.

**Follow-up milestone:** v5.9 Parent Admin Operations Visibility used the verified account lifecycle state as part of broader support-grade visibility for entitlement, billing, usage, and verification.

## Completed Milestone: v5.9 Parent Admin Operations Visibility

Roadmap archive: `.planning/milestones/v5.9-ROADMAP.md`
Requirements archive: `.planning/milestones/v5.9-REQUIREMENTS.md`
Audit archive: `.planning/milestones/v5.9-MILESTONE-AUDIT.md`
Phase evidence: `.planning/milestones/v5.9-phases/`

**Status:** Completed local backend release gate 2026-07-03 with rollout state `operations-visible`.

**Function purpose:** Give parents and admins one support-grade view of account operations state across entitlement, billing, usage, verification, and parent/student binding health.

**Implementation strategy:** Add a shared aggregation service that reuses existing v5.6 entitlement, v5.7 usage ledger/reconciliation, and v5.8 verification helpers. Expose a parent-scoped summary and an admin-scoped support detail without raw learning content, provider payload internals, private artifact keys, auth tokens, or verification codes.

**Completed phases:**

- Phase 217: Account Operations Visibility Contract.
- Phase 218: Parent Account Operations Summary.
- Phase 219: Admin Parent Operations Detail.
- Phase 220: Privacy Regression Tests And Operations Evidence.
- Phase 221: v5.9 Operations Visibility Release Gate.

**Outcome:** v5.9 added `/parents/me/account-operations` and `/admin/account-operations/parents/{parent_id}` backed by a shared account operations aggregation service. Responses compose billing, entitlement, usage, verification, child binding, and support-state signals while staying metadata-only. Focused parent/admin operations tests and Ruff passed.

**Known deferred items:** frontend/native account operations UI, production deploy/live smoke, broad CRM/customer messaging, analytics warehouse/cross-account search, native apps, final live Stripe/TWINT activation, and actual Cognito custom-auth passwordless login-code support.

## Completed Milestone: v5.10 Account Operations Frontend And Production Readiness

Roadmap: `.planning/milestones/v5.10-ROADMAP.md`
Requirements: `.planning/milestones/v5.10-REQUIREMENTS.md`
Completed phases: `.planning/phases/222-current-reality-refresh-and-frontend-account-ops-contract/`, `.planning/phases/223-email-verification-ux-integration/`, `.planning/phases/224-parent-account-operations-ui/`, `.planning/phases/225-admin-account-operations-console/`, `.planning/phases/226-v5-10-frontend-and-production-readiness-gate/`

**Status:** Complete. Phase 226 passed frontend lint/build, 15 focused frontend e2e tests, 35 backend focused contract tests, release gate evidence, and production read-only smoke planning.

**Function purpose:** Make the completed backend account operations stack usable in the frontend: email verification UX, parent account operations UI, admin support detail, and production read-only readiness.

**Implementation strategy:** Keep v5.6-v5.9 backend primitives stable unless frontend integration finds a concrete contract bug. Add typed frontend clients and query keys first, then parent/admin/auth surfaces, then focused frontend evidence and a production read-only smoke checklist.

**Completed phases:**

- Phase 222: Reality Refresh And Frontend Account Operations Contract. (complete)
- Phase 223: Email Verification UX Integration. (complete)
- Phase 224: Parent Account Operations UI. (complete)
- Phase 225: Admin Account Operations Console. (complete)
- Phase 226: v5.10 Frontend And Production Readiness Gate. (complete)

**Deferred beyond v5.10:** additional usage ledger action coverage, Cognito custom-auth passwordless login-code, native/mobile app buildout, live Stripe/TWINT activation, external provider activation, and warehouse/BI.

## Completed Milestone: v5.11 Additional Usage Ledger Coverage

Roadmap: `.planning/milestones/v5.11-ROADMAP.md`
Requirements: `.planning/milestones/v5.11-REQUIREMENTS.md`
Audit: `.planning/milestones/v5.11-MILESTONE-AUDIT.md`

**Goal:** Extend usage ledger coverage beyond question submissions so paid-limit behavior and parent/admin support explanations cover the rest of the learning actions.

**Target features:**
- Governed usage action taxonomy for chat, hints, teacher-help, and practice/generation actions.
- Idempotent, privacy-safe ledger events for eligible successful backend flows.
- Reconciliation and summaries that explain usage beyond questions.
- Parent/admin account operations compatibility without raw learning content or provider payload exposure.
- Focused backend verification and minimal frontend support-state updates if summaries require them.

**Phase progress:**

- Phase 227: Usage Action Taxonomy And Ledger Contract. (complete)
- Phase 228: Chat And Teacher-Help Ledger Instrumentation. (complete)
- Phase 229: Practice And Generation Ledger Instrumentation. (complete)
- Phase 230: Multi-Action Reconciliation And Account Operations Summaries. (complete)
- Phase 231: v5.11 Privacy Regression And Release Gate. (complete)

**Status:** Complete. Phase 231 passed 72 focused backend tests, Ruff, release gate evidence, and milestone audit.

**Deferred beyond v5.11:** production deploy/live smoke, frontend visual polish for expanded usage summaries, warehouse/BI export, live Stripe/TWINT activation, and cleanup archive movement after archive target verification.

## Completed Milestone: v5.12 Curriculum Editor And Content Migration Buildout

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`
Milestone roadmap: `.planning/milestones/v5.12-ROADMAP.md`
Milestone requirements: `.planning/milestones/v5.12-REQUIREMENTS.md`
Milestone audit: `.planning/milestones/v5.12-MILESTONE-AUDIT.md`

**Status:** Complete. Phase 236 passed the local release gate on 2026-07-05 with backend/frontend evidence and release state `curriculum-buildout-ready`.

**Function purpose:** Build the internal curriculum tooling that v5.1 left as readiness/deferred scope: special curriculum authorization, rich editor APIs/UI, structured validation, diff/review/audit workflows, production content migration dry-run/apply, evidence, rollback metadata, and operator console.

**Implementation strategy:** Preserve current published curriculum reads, adaptive assignment behavior, and v5.11 usage ledger compatibility. Treat curriculum editing as a backend-granted capability, not a default teacher/tutor permission. Implement backend authorization plus editor/migration APIs first, then frontend operator tooling, then focused release evidence. Keep external activation, warehouse deployment, native apps, broad CMS/collaboration, and unreviewed AI publication outside this milestone.

**Completed phases:**

- Phase 232: Curriculum Buildout Reality Refresh And Contract. (complete)
- Phase 233: Backend Special Authorization Editor Patch Validation Diff And Audit APIs. (complete)
- Phase 234: Backend Content Migration Service And APIs. (complete)
- Phase 235: Frontend Curriculum Editor And Migration Console. (complete)
- Phase 236: v5.12 Curriculum Buildout Release Gate. (complete)

**Deferred beyond v5.12:** native apps, live Stripe/TWINT activation, external support provider activation, live notification provider/native push activation, warehouse/BI deployment, broad collaborative CMS, and unreviewed AI publication.

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

Milestone v5.7 requirements are complete:

- LEDGER-01: usage ledger contract and idempotency - Phase 207.
- LEDGER-02: question usage ledger recording - Phase 208.
- RECON-01: quota counter reconciliation - Phase 209.
- USAGE-01: usage visibility and support summaries - Phase 210.
- VERIFY-40: v5.7 usage ledger release gate - Phase 211.

Milestone v5.8 requirements are complete:

- EMAIL-01: email verification contract and state model - Phase 212.
- EMAIL-02: registration verification enforcement - Phase 213.
- EMAIL-03: verification resend and expiry operations - Phase 214.
- LOGIN-01: login code policy and token compatibility - Phase 215.
- VERIFY-41: v5.8 verification release gate - Phase 216.

Milestone v5.9 requirements are complete:

- OPSVIS-01: operations visibility contract - Phase 217.
- PARENTOPS-01: parent account operations summary - Phase 218.
- ADMINOPS-01: admin account operations detail - Phase 219.
- OPSVERIFY-01: privacy and regression verification - Phase 220.
- VERIFY-42: v5.9 operations visibility release gate - Phase 221.

Milestone v5.10 requirements are complete:

- FRONTOPS-01: reality refresh and frontend contract - Phase 222.
- FRONTOPS-02: email verification UX integration - Phase 223.
- FRONTOPS-03: parent account operations UI - Phase 224.
- FRONTOPS-04: admin account operations console - Phase 225.
- VERIFY-43: v5.10 frontend and production readiness gate - Phase 226.

Milestone v5.11 requirements are complete:

- USAGE-01: governed usage action taxonomy - Phase 227.
- USAGE-02: chat and teacher-help ledger instrumentation - Phase 228.
- USAGE-03: practice and generation ledger instrumentation - Phase 229.
- RECON-02: multi-action reconciliation and usage summaries - Phase 230.
- OPS-01: parent/admin account operations compatibility - Phase 230.
- VERIFY-44: v5.11 usage coverage release gate - Phase 231.

### Active

Milestone v5.12 requirements are active:

- CURRBUILD-01: curriculum buildout reality refresh and contract - Phase 232. (complete)
- CURRBUILD-02: backend special authorization editor patch validation diff and audit APIs - Phase 233.
- CURRBUILD-03: backend content migration service and APIs - Phase 234.
- CURRBUILD-04: frontend curriculum editor and migration console - Phase 235.
- VERIFY-45: v5.12 curriculum buildout release gate - Phase 236.

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
| Start v5.1 rich curriculum editor and migration | v3.8/v4.6 delivered curriculum catalog, authoring lifecycle, and analytics foundations; final external activation remains blocked, so the next buildable product gap is rich editor UI, production content migration, assignment automation readiness, and adaptive sequencing readiness | Complete - readiness release gate passed |
| Start v5.2 adaptive sequencing and warehouse analytics | v5.1 completed curriculum product readiness while external activation remained blocked; the next buildable product gap was deeper recommendation sequencing, assignment outcome feedback, warehouse-ready analytics, and operator dashboards | ✓ Good |
| Start v5.3 controlled assignment automation | v5.2 completed recommendation, outcome, analytics, and operator dashboard readiness; final external activation remained blocked, so the next buildable product gap was controlled assignment automation from reviewed sources | Complete - automation-ready release gate passed |
| Start v5.4 frontend learning operations and automation dashboards | v5.2/v5.3 completed backend/API readiness, but the learning operations flows still needed usable frontend review, dashboard, and family explanation surfaces | Complete - frontend-ready release gate passed |
| Start v5.5 automatic teacher dispatch and SLA load balancing | `stoa_docs` still identifies teacher response time, queue/takeover, multiple-teacher rotation, and timeout reassignment as product concerns; v5.4 closed learning operations UI, so the next buildable support gap is dispatch routing for human help requests | Complete - dispatch-ready release gate passed |
| Promote final-polish work into complete milestones | Entitlements, usage ledger, account verification, and operations visibility are each complete product capabilities, not small phases; v5.6 focused only on paid entitlement enforcement, with v5.7-v5.9 planned for the remaining capabilities | Complete - entitlement-ready release gate passed |
| Start v5.8 email verification and login-code policy | v5.7 made quota usage durable and support-visible; the next account lifecycle risk is ambiguous email verification and placeholder login-code behavior before broader parent/admin operations visibility | Complete - policy-deferred release gate passed |
| Start v5.9 parent admin operations visibility | v5.6-v5.8 delivered entitlement, usage, and verification primitives; support now needs one bounded operations view that composes those states without exposing private content or provider internals | Complete - operations-visible release gate passed |
| Start v5.10 account operations frontend and production readiness | v5.6-v5.9 backend primitives are complete, but current frontend had no account-operations clients/routes and no complete email verification confirm/resend UX | Complete - frontend-account-ops-ready release gate passed |
| Start v5.11 additional usage ledger coverage | v5.7 made question usage durable; parent/admin account operations now need privacy-safe support explanations for chat, hints, teacher-help, and practice/generation usage actions | Complete - multi-action-usage-ledger-ready release gate passed |
| Start v5.12 curriculum editor and content migration buildout | v5.1 was readiness-complete but left rich editor frontend, draft patch/diff/validation APIs, migration service/API/UI, evidence, and rollback metadata deferred; this is the highest-value internally buildable gap after v5.11, with curriculum editing restricted to backend-authorized operators rather than all teachers/tutors | Complete - curriculum-buildout-ready release gate passed |
| Plan v5.13 payment and entitlement production completion | User testing indicates paid access and business-critical account behavior still need real product completion; after v5.12, run a fresh reality audit and close checkout/paywall, webhook reconciliation, entitlement activation, quota compatibility, and admin billing evidence | Complete - payment-production-ready-local release gate passed |
| Plan v5.14 verification and login reliability | User testing indicates login code, email verification, resend/confirm, and activation edge cases need a dedicated reliability milestone rather than being treated as small polish | Historical partial gate - focused frontend e2e blocker closed by v5.16 |
| Plan v5.15 usage, quota, and product stability | User testing indicates backend usage recording and visible quota behavior need real-flow verification, reconciliation, support explanations, smoke checks, and stability gates | Complete - usage-stability-ready-local release gate passed |
| Start v5.16 end-to-end product readiness and release evidence | v5.12-v5.15 local work is mostly complete but fragmented across auth, billing, usage, curriculum, frontend e2e, and smoke evidence; next value is one cross-surface readiness gate that separates regressions from external-provider blockers | Complete - product-readiness-evidence-local release gate passed |
| Start v5.17 external provider activation smoke and release operations | v5.16 closed local product readiness; remaining risk is external provider activation and production release operations for payment, Cognito/email, notifications, support handoff, and read-only smoke | Complete - external-provider-release-ops-ready release gate passed |
| Plan v5.18 warehouse BI observability and product analytics activation | v5.15 stabilized usage semantics and v5.17 classified provider states; analytics should activate after those dimensions are clean enough for dashboards and alerts | Complete - bi-observability-ready-local release gate passed |
| Plan v5.19 native mobile push and offline client implementation | Web product readiness, provider-state clarity, and observability should precede native app implementation so the mobile client inherits stable contracts and clear push/offline boundaries | Complete - native-mobile-source-ready-local release gate passed |
| Plan v5.20 native build distribution and device QA | v5.19 source implementation must be turned into installable internal device builds before app-store or production mobile rollout claims are credible | Complete - native-distribution-ready-local-contracts release gate passed |
| Plan v5.21 AI teaching quality cost and safety operations | AI teacher tools exist in reviewed/bounded form, but quality evaluation, cost/latency observability, safety escalation, and autonomy boundaries need a dedicated operational milestone | Complete - ai-operations-ready-local-contracts release gate passed |
| Plan v5.22 support CRM customer messaging and lifecycle automation | Support handoff, CRM gates, notifications, account operations, billing, and learning-progress signals exist in pieces; customer lifecycle messaging needs an end-to-end governed workflow | Complete - customer-lifecycle-ready-local-contracts release gate passed |
| Plan v5.23 enterprise stability compliance and disaster recovery hardening | After mobile, AI, and customer lifecycle surfaces are connected, restore drills, SLOs, incident response, rollback, access/credential, audit, and compliance evidence become the launch-limiting risk | Complete - enterprise-hardening-ready-local-contracts release gate passed |
| Plan v5.24 limited production pilot and launch readiness | After mobile/device, AI operations, lifecycle messaging, and enterprise hardening gates are credible, the next useful milestone is a narrow go/no-go pilot or launch plan with cohort, monitoring, support, rollback, and acceptance evidence | Complete - limited-pilot-ready-local-contracts release gate passed |
| Plan v5.25 pilot activation blocker burn-down and safe start decision | v5.24 is conditional; unresolved payment, notification, support CRM, BI/APM, mobile release, restore, and tabletop blockers make direct pilot execution unsafe | Complete - pilot-safe-start-contracts release gate passed; default hold |
| Plan v5.26 limited pilot execution and outcome evidence | After v5.25 safe-start approval, the product needs real cohort evidence before expansion | Contract complete locally; real execution gated |
| Plan v5.27 pilot remediation product fit and reliability hardening | Pilot findings should drive focused fixes before cohort growth | Contract complete locally; real remediation gated on live pilot findings |
| Plan v5.28 controlled expansion revenue and operations scale | Expansion should validate revenue, teacher/support capacity, mobile/provider readiness, and operational scale before public launch prep | Contract complete locally; real expansion gated |
| Plan v5.29 public launch readiness growth and self-serve onboarding | Self-serve and public launch readiness should follow controlled expansion evidence, not precede it | Contract complete locally; public launch gated |
| Plan v5.30 live pilot approval and provider activation execution | Local contracts do not approve real users; live approval and provider/readiness evidence must clear the safe-start gate first | Complete - live activation contracts added; default hold |
| Plan v5.31 real limited pilot execution operations | Real pilot execution should only start after v5.30 returns `start_limited_pilot` | Contract complete locally; real execution gated |
| Plan v5.32 live pilot remediation and reliability fixes | Live pilot findings should drive fixes before expansion | Contract complete locally; real fixes gated on live pilot findings |
| Plan v5.33 controlled expansion execution and revenue validation | Expansion must validate revenue, support, teacher, mobile, provider, and operational scale under real use | Contract complete locally; real expansion gated |
| Plan v5.34 public launch execution and post-launch operations | Public launch execution requires controlled expansion evidence and final approval | Contract complete locally; public launch gated |
| Plan v5.35 real pilot blocker burn-down and launch execution | v5.30-v5.34 are metadata-only execution contracts; the real work now is clearing or disabling start blockers so the pilot gate can honestly move from hold to start | Complete locally; real pilot start gated by current evidence |
| Plan v5.36 live pilot operations feedback and product fixes | After v5.35 starts a cohort, real usage must drive activation, support, billing, mobile, AI, teacher, and learning fixes before expansion | Contract complete locally; real operations gated by v5.35 start |
| Plan v5.37 revenue conversion and self-serve growth completion | Paid conversion and growth should be completed from real parent friction, entitlement reconciliation, lifecycle messaging, and support load, not readiness assumptions | Contract complete locally; growth gated by revenue and support evidence |
| Plan v5.38 learning outcomes curriculum and AI quality scale | Learning quality is the core product value; curriculum, exercises, recommendations, AI tools, and progress reporting need real-evidence improvement before broader growth | Contract complete locally; scale gated by learning and AI quality evidence |
| Plan v5.39 platform reliability and internal operations scale | Larger cohorts require repeatable reliability, observability, admin, teacher, support, release, and rollback operations instead of founder-operated manual work | Contract complete locally; larger expansion gated by operations evidence |
| Start v6.0 real evidence capture and pilot start execution | v5.30-v5.39 created the local gate chain; the next useful work is current approved real evidence and an honest start/hold decision | Complete locally; real start still gated by approved evidence |
| Plan v6.1 first cohort product remediation sprint | Real account/payment/usage/login/notification/support/mobile/learning evidence should drive shipped fixes before expansion | Complete locally; real cohort/remediation gated by approved evidence |
| Plan v6.2 paid conversion usage and account reliability completion | Paid access, usage ledger, quota, verification, lifecycle, and billing support must be reliable before controlled growth | Complete locally; controlled growth gated by current evidence and support capacity |
| Plan v6.3 learning outcome and AI curriculum quality sprint | Learning outcome is the core product value; curriculum, exercises, AI tools, recommendations, and progress reporting need real-evidence quality work | Planned |
| Plan v6.4 operations scale release and observability hardening | Larger cohorts require repeatable observability, support/admin/teacher workflows, release discipline, rollback, and incident ownership | Planned |

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
*Last updated: 2026-07-08 after completing v6.0 real evidence execution contracts*
