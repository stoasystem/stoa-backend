# Project Research - Stack

**Milestone:** v1.4 Report Operations Admin UI / Bulk Recovery
**Date:** 2026-06-04

## Scope

Research only the stack implications for adding an admin report operations UI, single `generation_failed` retry, and selected bulk resend to the existing STOA backend/frontend.

## Existing Stack Evidence

Backend:

- FastAPI routes live under `src/stoa/routers/`.
- Admin routes already exist in `src/stoa/routers/admin.py`.
- Weekly report orchestration exists in `src/stoa/jobs/weekly_reports.py`.
- Report persistence is in `src/stoa/db/repositories/report_repo.py`.
- Report generation/storage/email logic is in `src/stoa/services/report_service.py`.
- Report artifact S3 read/write helpers are in `src/stoa/services/report_artifact_service.py`.
- DynamoDB is a single-table design; report records are stored as `PK=REPORT#{report_id}`, `SK=SUMMARY`, with a parent/week GSI currently used for parent report lookups.

Frontend:

- React 19, React Router 7, React Query 5, Axios, Tailwind, Radix UI, lucide-react.
- Admin routes and navigation are defined in `/Users/zhdeng/stoa-frontend/src/app/router/AppRouter.tsx` and `routeConfig.ts`.
- Admin pages already use `DashboardLayout`, `PageContainer`, `PageHeader`, `Card`, `Badge`, and existing admin components.
- `@tanstack/react-query` is present; `@tanstack/react-table` is not installed.

Infrastructure:

- Existing Lambda/API Gateway and weekly report Lambda are CDK-managed.
- v1.3 already scoped report artifact S3 access to `weekly-reports/*`.
- Project constraint remains infrastructure-first: do not add AWS services, buckets, tables, Lambdas, queues, or indexes without proving current resources cannot support the milestone.

## External Findings

- AWS Lambda direct invocation does not automatically retry user-code errors; manual retry paths must be idempotent and must account for partial prior execution. Source: https://docs.aws.amazon.com/lambda/latest/dg/invocation-retries.html
- Lambda asynchronous invocation can deliver duplicate events and can retry errors; if v1.4 uses async invocation later, recovery operations must be duplicate-safe. Source: https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html
- DynamoDB pagination is based on `LastEvaluatedKey` and `ExclusiveStartKey`; admin list APIs should expose a continuation token rather than assuming full-table reads. Source: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html
- TanStack Table supports sorting, filtering, pagination, and row selection, but the dependency is not currently installed. Source: https://tanstack.com/table/latest/docs/api/features/sorting
- Step Functions redrive exists for failed standard workflow executions, but STOA does not currently model weekly report generation as Step Functions executions. Adding Step Functions would be infrastructure expansion, not a minimal v1.4 prerequisite. Source: https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html

## Stack Recommendation

Use the existing stack for v1.4:

- Backend: extend `admin.py`, `report_repo.py`, and report services.
- Frontend: add admin report ops page/service/hooks using React Query and existing UI components.
- Infrastructure: no new AWS service by default.
- Data access: start with a bounded admin report scan/query path with pagination and explicit filter limitations; only add a new GSI if Phase 23 proves scan is unacceptable for pilot volume.
- UI table: build a focused internal operations table/list with existing components first. Add `@tanstack/react-table` only if row selection/sorting complexity becomes high enough to justify a new dependency.

## Stack Non-Goals

- Do not add Step Functions for v1.4 recovery unless existing Lambda/API paths prove insufficient.
- Do not expose direct S3 URLs, presigned URLs, or raw report HTML/JSON in frontend.
- Do not add a generic admin audit-log service before report-specific audit fields prove insufficient.
