# Project Research - Architecture

**Milestone:** v1.4 Report Operations Admin UI / Bulk Recovery
**Date:** 2026-06-04

## Current Report Flow

1. Weekly Lambda discovers linked parent/student pairs.
2. For each pair, it checks for an existing report.
3. It tries to claim report generation by conditionally inserting a report record.
4. It builds learning payload, generates report content, writes JSON/HTML artifacts, writes metadata, and sends email.
5. If generation/storage fails after claim, the record becomes `generation_failed`.
6. If email fails after artifacts/metadata succeed, the record becomes `email_failed`.
7. v1.3 admin endpoints can inspect one report and resend one `email_failed` report.

Important retry constraint:

- `generation_failed` records already exist in DynamoDB.
- `try_claim_report_generation` cannot be reused directly for retry because its conditional put fails when the existing failed record is present.
- A retry service must explicitly validate and transition the existing failed record instead of relying on the scheduled job's initial claim path.

## Proposed v1.4 Backend Shape

### Report Repository

Add admin-oriented access helpers:

- `list_reports_for_admin(...)` with status/week/parent/student filters, limit, and continuation token.
- `update_report_status_conditionally(...)` or a narrow helper for operation claim/lock fields.
- Optional `get_report_by_id(report_id)` if bulk actions use report IDs instead of path triples.

Pilot data-access approach:

- Use bounded `Scan` over report summary records for cross-parent admin view if Phase 23 confirms no suitable GSI exists.
- Return `LastEvaluatedKey` as an opaque token.
- Keep scan filters explicit and capped.
- If scan proves unacceptable, add a CDK-managed GSI for report status/week before building broad admin list UX.

### Report Operations Service

Create or extract a service module for admin recovery operations:

- `get_report_operation_summary(...)`
- `retry_generation_failed_report(parent_id, student_id, week_start, operator)`
- `resend_failed_report_email(parent_id, student_id, week_start, operator)`
- `bulk_resend_failed_reports(items, operator, max_items=...)`

The existing `admin.py` endpoint logic should delegate to this service so list/detail/action behavior is reusable and testable.

### API Endpoints

Likely endpoints:

- `GET /admin/reports/ops`
  - Query params: `status`, `week_start`, `parent_id`, `student_id`, `limit`, `next_token`.
  - Returns rows, counters if cheap, and `next_token`.

- `GET /admin/reports/{parent_id}/{student_id}/{week_start}/ops`
  - Existing endpoint; extend response with generation metadata and action eligibility.

- `POST /admin/reports/{parent_id}/{student_id}/{week_start}/retry-generation`
  - Only accepts `generation_failed`.
  - Returns operation result and updated status.

- `POST /admin/reports/bulk-resend`
  - Body contains selected report identifiers.
  - Only sends `email_failed` reports.
  - Returns per-item results.

### Frontend

Add:

- `/admin/reports` route.
- Admin nav item "Report Ops" or "Reports".
- `src/services/admin/reportOperationsApi.ts`.
- `src/hooks/admin/useAdminReportOperationsQuery.ts` and action mutation hooks.
- `src/pages/admin/ReportOperationsPage.tsx`.
- Focused components for filters, list/table, detail panel, confirmation dialog, and operation result summary.

Use current admin visual style:

- `DashboardLayout`, `PageContainer`, `PageHeader`.
- Compact cards and tables, not a marketing layout.
- Status badges and action buttons.
- React Query invalidation after retry/resend.

## Data Flow

```text
Admin UI filters
  -> GET /admin/reports/ops
  -> report_repo admin list
  -> rows + next_token

Admin opens row
  -> GET /admin/reports/{parent}/{student}/{week}/ops
  -> metadata only

Admin retries generation_failed
  -> POST /admin/reports/{parent}/{student}/{week}/retry-generation
  -> report ops service validates status
  -> build payload -> generate -> write artifacts -> store metadata -> send email
  -> audit result

Admin bulk resends email_failed
  -> POST /admin/reports/bulk-resend
  -> per-item status validation
  -> read private HTML artifact through backend
  -> SES send
  -> per-item audit/result
```

## Build Order

1. Backend admin list/detail/action contract.
2. Generation retry service.
3. Bulk resend service.
4. Frontend admin page and navigation.
5. Live verification and deploy evidence.
