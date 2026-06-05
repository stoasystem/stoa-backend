# Phase 52 Context

**Phase:** Admin Report Editing UI
**Milestone:** v2.0 Controlled Report Editing MVP
**Started:** 2026-06-05

## Inputs

- Phase 51 delivered admin-only edit draft create/read/apply backend APIs.
- The existing `/admin/report-operations` page already selects one report for detail inspection and renders report audit evidence.
- Editing must remain metadata-only and must not expose S3 keys, presigned URLs, raw HTML, or raw JSON.

## UI Placement

The edit draft controls live inside the selected report detail panel. This keeps the workflow scoped to one selected report and avoids showing mutation controls when no report is selected.

## Workflow

1. Admin selects a report with `Inspect`.
2. Admin enters an edit reason and one or more allowlisted fields.
3. Admin creates a draft.
4. Admin applies the draft as a separate mutation.
5. UI shows draft/apply result and refreshes audit evidence.
