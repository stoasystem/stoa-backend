# STOA Backend

## What This Is

STOA is a learning platform backend for students, teachers/tutors, parents, and admins. This repository provides the FastAPI service that runs locally with Uvicorn and in production as an AWS Lambda/API Gateway API backed by Cognito, DynamoDB, S3, Bedrock, Rekognition, SQS, and SES.

The v1.0 parent portal integration now serves normal parent flows through authenticated `/parents/me/...` backend routes. A real parent Cognito account can see linked children, open child detail views, review real learning summary/history, and open report pages that correctly handle both existing and missing reports.

## Core Value

Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.

## Current State

**Shipped version:** v1.0 Parent Portal Real Data Integration on 2026-06-02

Delivered:

- Parent-owned child listing through `GET /parents/me/children`.
- Parent-owned child summary through `GET /parents/me/children/{child_id}/summary`.
- Parent-owned child learning history through `GET /parents/me/children/{child_id}/history`.
- Parent-owned report lookup through `GET /parents/me/children/{child_id}/report` and week-specific `GET /parents/me/children/{child_id}/reports/{week}`.
- Frontend parent services and pages use real backend route shapes and no longer silently hide parent-critical API failures behind demo fallback.
- Focused backend and frontend tests cover parent authorization, empty states, missing reports, and route contract alignment.

## Current Milestone: v1.1 Weekly Report Automation

**Goal:** Automatically generate weekly learning reports for linked parent/student pairs, store the generated report, send it to parents by email, and render the richer generated report in the parent portal.

**Target features:**

- CDK defines the scheduled weekly report Lambda target, EventBridge Scheduler wiring, reports bucket env/permissions, SES/Bedrock/DynamoDB permissions, retry/failure behavior, and monitoring alarms.
- Backend adds weekly report aggregation/generation services and a scheduled Lambda handler that is idempotent by `(parent_id, student_id, week_start)`.
- Bedrock generates parent-facing summary, weak topics, and recommendations with strict JSON validation and deterministic fallback.
- Reports store metadata in DynamoDB and full HTML/JSON artifacts in the private S3 reports bucket before email is considered complete.
- SES sends weekly report email to the parent and preserves generated reports when email delivery fails.
- Parent frontend renders generated report content, missing state, and generation/email failure states from real backend responses.
- Backend and frontend tests cover aggregation, idempotency, Bedrock parser/fallback, S3/SES failure behavior, and generated report UI.

## Requirements

### Validated

Existing codebase capabilities inferred from the mapped backend:

- FastAPI backend is composed under `src/stoa/main.py` with route modules for auth, students, parents, practice, questions, conversations, teachers/tutors, admin, and files.
- Cognito JWT validation and role resolution exist in `src/stoa/deps.py`.
- DynamoDB single-table repositories exist for users, questions, practice, and reports.
- Student summary, student question history, practice progress, mistakes, and report storage are available as data sources for parent-visible aggregation.

v1.0 shipped requirements:

- Parent users can list only their linked children through `/parents/me/children` - v1.0.
- Parent users can open a linked child summary backed by real backend aggregation - v1.0.
- Parent users can open a linked child learning history backed by real backend data - v1.0.
- Parent users can open child report pages that distinguish available reports from missing reports without fabricated content - v1.0.
- Parent-critical frontend flows use real backend API contracts and do not silently fall back to demo data - v1.0.
- Authorization prevents parents, students, teachers, tutors, and admins from using normal parent routes outside their intended access rules - v1.0.
- Required infrastructure assumptions are confirmed against CDK before backend implementation - v1.0.

### Active

- [ ] Weekly report automation, including scheduled generation and delivery.
- [ ] CDK report automation wiring, including scheduled Lambda, reports bucket access, SES/Bedrock/DynamoDB permissions, retries/failure handling, and monitoring.
- [ ] Backend weekly report aggregation and generation for linked parent/student pairs.
- [ ] Bedrock-generated parent-facing report summary and recommendations with validated JSON output and deterministic fallback.
- [ ] DynamoDB report metadata and S3 report artifact storage.
- [ ] SES weekly report email delivery with failure status preservation.
- [ ] Parent frontend generated report detail display with missing and failed states.
- [ ] Backend and frontend verification for the weekly report flow.
- [ ] Cleanup or integration of the unused parent practice-summary demo fallback path if it intersects with generated report display.

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
- Report storage exists at repository/model level, but report generation service does not exist.

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
- EventBridge schedule group exists, but weekly report generation target is not implemented in backend.

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
| Prefer a separate scheduled Lambda handler for weekly reports | EventBridge Scheduler should not invoke the Mangum API handler directly | Pending in v1.1 |
| Store generated report before email completion | Parents must still be able to view reports if SES delivery fails | Pending in v1.1 |

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
*Last updated: 2026-06-02 after starting milestone v1.1*
