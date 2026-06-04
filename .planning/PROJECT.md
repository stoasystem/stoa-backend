# STOA Backend

## What This Is

STOA is a learning platform backend for students, teachers/tutors, parents, and admins. This repository provides the FastAPI service that runs locally with Uvicorn and in production as an AWS Lambda/API Gateway API backed by Cognito, DynamoDB, S3, Bedrock, Rekognition, SQS, and SES.

The v1.5 report operations platform gives admins a production-verified, backend-mediated recovery workflow for weekly reports: list/detail operations metadata, retry one `generation_failed` report, resend one or more selected `email_failed` reports, use a real admin UI without exposing private report artifacts, and follow an operator runbook for safe support use.

## Core Value

Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.

## Current State

**Shipped version:** v1.5 Report Recovery Production Rollout & Live Smoke on 2026-06-04

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

## Current Milestone: v1.6 Report Recovery Operations Hardening

**Goal:** Make report recovery safe for incident-wide operations by adding async bulk recovery, immutable audit evidence, production admin browser smoke, and CI/CD protection against stale Lambda package deployments.

**Target features:**

- Incident-wide async report recovery jobs with progress, bounded execution, cancellation/stop conditions, and operator-visible results.
- Immutable audit log records for report recovery actions that preserve who did what, when, why, and with which targets.
- Production admin browser smoke that verifies the deployed UI with a real admin session without creating temporary production admin accounts.
- CI/CD Lambda dist rebuild guard so CDK diff/deploy cannot silently use stale `stoa-backend/dist` assets.

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

### Active

Milestone v1.6 requirements are being defined.

### Out of Scope

- Billing or paid subscription enforcement - not part of report automation MVP.
- PDF generation - HTML/JSON report artifacts are enough for this milestone.
- Multi-language report generation beyond the primary parent-facing language chosen for MVP.
- Stripe or billing integration - unrelated to parent real-data integration.
- Organization/school portal work - separate product surface.
- Real-time report generation on every parent page load - scheduled generation is the intended model.
- Manual admin report editor - follow-up operational feature.
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
*Last updated: 2026-06-04 after starting milestone v1.6*
