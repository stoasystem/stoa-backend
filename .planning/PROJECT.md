# STOA Backend

## What This Is

STOA is a learning platform backend for students, teachers/tutors, parents, and admins. This repository provides the FastAPI service that runs locally with Uvicorn and in production as an AWS Lambda/API Gateway API backed by Cognito, DynamoDB, S3, Bedrock, Rekognition, SQS, and SES.

The current milestone moves the parent portal from demo/mock-backed screens to real AWS-backed data. A real parent Cognito account should be able to log in, see linked children, open child detail views, review real learning summary/history, and open report pages that correctly handle both existing and missing reports.

## Core Value

Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.

## Current Milestone: v1.0 Parent Portal Real Data Integration

**Goal:** Replace parent portal mock/demo-backed flows with authenticated `/parents/me/...` backend data, ownership checks, stable empty states, and frontend service alignment.

**Target features:**
- Parent-owned child listing through `GET /parents/me/children`.
- Parent-owned child summary through `GET /parents/me/children/{child_id}/summary`.
- Parent-owned child learning history through `GET /parents/me/children/{child_id}/history`.
- Parent-owned report lookup through `GET /parents/me/children/{child_id}/report` and week-specific lookup when needed.
- Frontend parent services use real backend routes and no longer silently hide parent-critical API failures behind demo fallback.
- Focused backend and frontend tests cover parent authorization, empty states, missing reports, and route contract alignment.

## Requirements

### Validated

Existing codebase capabilities inferred from the mapped backend:

- FastAPI backend is composed under `src/stoa/main.py` with route modules for auth, students, parents, practice, questions, conversations, teachers/tutors, admin, and files.
- Cognito JWT validation and role resolution exist in `src/stoa/deps.py`.
- DynamoDB single-table repositories exist for users, questions, practice, and reports.
- Parent routes already expose parent child/report functionality, but use path parent IDs and do not match the preferred frontend `/parents/me/...` contract.
- Student summary, student question history, practice progress, mistakes, and report storage are available as data sources for parent-visible aggregation.

### Active

- [ ] Parent users can list only their linked children through `/parents/me/children`.
- [ ] Parent users can open a linked child summary backed by real backend aggregation.
- [ ] Parent users can open a linked child learning history backed by real backend data.
- [ ] Parent users can open child report pages that distinguish available reports from missing reports without fabricated content.
- [ ] Parent-critical frontend flows use real backend API contracts and do not silently fall back to demo data.
- [ ] Authorization prevents parents, students, teachers, tutors, and admins from using normal parent routes outside their intended access rules.
- [ ] Required infrastructure assumptions are confirmed against CDK before backend implementation.

### Out of Scope

- Automatic weekly report generation - separate follow-up milestone.
- EventBridge schedule target implementation - belongs to weekly report automation.
- SES weekly email sending workflow - belongs to weekly report automation.
- PDF generation - not required for current parent report display/empty-state flows.
- Stripe or billing integration - unrelated to parent real-data integration.
- Organization/school portal work - outside this parent portal milestone.
- Live classroom work - outside this parent portal milestone.
- Full admin analytics - outside this parent portal milestone.
- Broad frontend redesign - this milestone is integration and state correctness.

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

- Parent child listing exists, but uses path parent ID.
- Weekly report lookup exists, but uses path parent ID and week.
- Student summary exists, but uses `/students/{student_id}/summary`.
- Student question history exists, but uses `/students/{student_id}/questions`.
- Practice progress and mistakes exist for students.
- Report storage exists at repository/model level, but report generation service does not exist.

### Frontend Context

Relevant frontend files:

- `/Users/zhdeng/stoa-frontend/src/app/router/AppRouter.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/parent/`
- `/Users/zhdeng/stoa-frontend/src/services/parent/parentApi.ts`
- `/Users/zhdeng/stoa-frontend/src/services/parent/parentReportApi.ts`
- `/Users/zhdeng/stoa-frontend/src/services/practice/practiceApi.ts`
- `/Users/zhdeng/stoa-frontend/src/services/demo/demoFallback.ts`

Current frontend issue:

- Parent pages call routes such as `/parents/me/children` and `/parents/me/children/{childId}/report`.
- Backend currently exposes `/parents/{parent_id}/children` and `/parents/{parent_id}/reports/{week}`.
- Parent-facing frontend calls still use `withDemoFallback`, so API failures can be hidden by mock data.

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
- **Frontend contract:** Frontend integration must target the real backend API contract and remove silent demo fallback from parent-critical flows.
- **Authorization:** Every child-specific parent endpoint must verify ownership before reading or returning child data.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Prefer `/parents/me/...` routes for parent portal flows | Parent identity is already available from JWT and clients should not pass parent IDs for normal logged-in parent workflows | Pending |
| Keep existing path-ID parent endpoints compatible where useful | Existing routes may still serve legacy or internal use cases while the portal moves to `/parents/me/...` | Pending |
| Treat report generation as a follow-up milestone | This milestone needs query/display/empty states, not scheduled generation, emails, or PDFs | Pending |
| Check CDK before backend data-access changes | The milestone explicitly depends on current DynamoDB/Cognito/Lambda resource definitions | Pending |

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
*Last updated: 2026-06-02 after starting milestone v1.0*
