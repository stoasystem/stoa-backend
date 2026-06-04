# Phase 22: Report Operations Visibility and Recovery - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Auto-generated (backend operations phase)

<domain>
## Phase Boundary

Phase 22 adds backend-mediated admin operations for inspecting report artifact/delivery metadata and resending failed report emails. It should not expose raw report content or public S3 URLs, and it should not regenerate unrelated successful reports.

In scope:
- Admin-only report operations metadata endpoint for parent/student/week.
- Admin-only resend endpoint for failed email delivery on a specific report.
- Internal private HTML artifact read for resend.
- Audit/status fields persisted through `report_repo.update_report_status`.
- Tests for authorization, metadata visibility, resend targeting, and audit evidence.

Out of scope:
- Frontend admin dashboard.
- Public or presigned S3 URLs.
- Raw artifact content in API responses.
- Bulk retries or broad incident tooling.
- Regenerating report content for unrelated reports.

</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
- Add minimal admin API endpoints under the existing `/admin` router rather than introducing a new service or frontend surface.
- Keep operations restricted to `require_role("admin")`.
- Allow resend only for reports whose delivery failed (`status=email_failed` or `email_status=failed`).
- Read HTML privately from S3 only inside the resend operation; never return raw HTML in the response.
- Use existing report metadata and `update_report_status` fields for audit rather than adding a new table.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/routers/admin.py` already hosts admin-only routes with `require_role("admin")`.
- `src/stoa/db/repositories/report_repo.py` has `get_report_for_child_by_week` and `update_report_status`.
- `src/stoa/services/notify_service.py` can send weekly report email with an injected SES client.
- `src/stoa/services/report_artifact_service.py` can already read JSON artifacts and validate canonical keys.

### Established Patterns
- Parent access remains backend-mediated and ownership-checked on parent routes.
- Admin routes return operational metadata and avoid exposing internal DynamoDB keys where not needed.
- Status transitions are persisted through `report_repo.update_report_status`.

### Integration Points
- Resend uses `html_s3_key` from existing report metadata.
- Audit fields are attached to the existing report summary item.

</code_context>

<specifics>
## Specific Ideas

Use two endpoints:
- `GET /admin/reports/{parent_id}/{student_id}/{week_start}/ops`
- `POST /admin/reports/{parent_id}/{student_id}/{week_start}/resend`

</specifics>

<deferred>
## Deferred Ideas

- Admin UI dashboard.
- Bulk incident retry.
- Regeneration tooling for `generation_failed` reports.

</deferred>
