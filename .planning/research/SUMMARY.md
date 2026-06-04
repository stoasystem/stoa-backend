# Project Research - Summary

**Milestone:** v1.4 Report Operations Admin UI / Bulk Recovery
**Date:** 2026-06-04

## Stack Additions

Default recommendation: no new AWS service and no new frontend table dependency for the initial v1.4 roadmap.

Use:

- Existing FastAPI admin router and report services.
- Existing DynamoDB single-table repository, with bounded pagination.
- Existing Lambda/API Gateway deployment model.
- Existing React admin layout/components plus React Query.

Conditional additions:

- Add a CDK-managed DynamoDB GSI only if the first backend phase proves current report indexes cannot support an admin report operations list safely.
- Add `@tanstack/react-table` only if the admin UI needs richer row selection/sorting than the existing component set can support cleanly.

## Table Stakes

- Admin report operations page with filters, paginated results, detail, action eligibility, and clear empty/error/loading states.
- Metadata-only report detail that includes generation, delivery, artifact key, and audit fields.
- Single `generation_failed` retry that targets one parent/student/week report.
- Selected bulk resend for `email_failed` reports with per-item results.
- Strict admin-only access and no raw/private S3 content exposure.
- Audit fields for actor, action, attempt/completion time, result, and errors.

## Architecture Notes

- `generation_failed` retry cannot reuse the scheduled job's claim path directly because the failed report record already exists.
- A report operations service should extract action logic from `admin.py` so single resend, bulk resend, and generation retry share validation/audit behavior.
- Admin list APIs should return opaque pagination tokens based on DynamoDB continuation state.
- Bulk resend should be capped and per-item, not incident-wide asynchronous recovery in v1.4.

## Watch Outs

- Avoid duplicate emails by validating current status immediately before resend and recording operation results.
- Avoid unbounded scans; prove current index sufficiency first.
- Avoid raw report content or S3 URLs in admin responses.
- Avoid demo fallback in admin report ops UI.
- Avoid adding Step Functions/queues until synchronous bounded recovery is insufficient.

## Sources

- AWS Lambda retry behavior: https://docs.aws.amazon.com/lambda/latest/dg/invocation-retries.html
- AWS Lambda async retry and duplicate-delivery behavior: https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html
- DynamoDB query pagination: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html
- TanStack Table sorting/features: https://tanstack.com/table/latest/docs/api/features/sorting
- Step Functions redrive: https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html
