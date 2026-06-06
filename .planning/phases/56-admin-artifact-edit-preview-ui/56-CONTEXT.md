# Phase 56: Admin Artifact Edit Preview UI - Context

**Gathered:** 2026-06-06
**Status:** Complete
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

Phase 56 adds the admin-facing controls for the Phase 55 artifact edit preview/apply APIs. The UI must stay on `/admin/report-operations`, operate only on a selected report, distinguish preview from apply, require an operator reason, and render only sanitized backend responses.

</domain>

<decisions>
## Implementation Decisions

### UI Placement
- Add the artifact edit preview panel inside the selected report detail area on `ReportOperationsPage`.
- Keep preview/apply unavailable until a report is selected and the backend marks `edit_artifact` enabled.
- Keep the UI compact and operational, matching the existing admin report operations page rather than introducing a separate editor route.

### API Integration
- Add typed admin API helpers for create preview and apply preview.
- Add React Query mutations in `useAdminReportOperations`.
- Let the backend remain authoritative for validation, diffs, version IDs, audit references, and stale-source errors.

### Safety And Privacy
- Treat preview as the non-mutating review step and apply as the explicit mutation step.
- Require operator reason text before preview and reuse it as the default apply approval reason.
- Render structured sanitized diff rows and outcome metadata only.
- Do not render S3 keys, presigned URLs, raw JSON, raw HTML, or token-like markers.

### the agent's Discretion
- Use a simple bounded edit form for the Phase 54 allowlisted summary/recommendation fields.
- Use existing page-level message patterns for success and error states.

</decisions>

<code_context>
## Changed Frontend Files

- `/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts`
- `/Users/zhdeng/stoa-frontend/src/hooks/admin/useAdminReportOperations.ts`
- `/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx`
- `/Users/zhdeng/stoa-frontend/tests/e2e/admin-report-operations.spec.ts`

## Frontend Commit

- `e0f76e4 feat: add artifact edit preview UI`

</code_context>

<deferred>
## Deferred Ideas

- Rich text editing and WYSIWYG controls remain out of scope.
- Rollback UI remains future scope; Phase 56 displays apply/audit metadata only.
- Production browser smoke and safe live verification remain Phase 57 scope.

</deferred>
