# Phase 50 Report Editing Contract

**Status:** Accepted
**Date:** 2026-06-05

## Editable Fields

MVP editable fields are bounded to report metadata that is already safe to expose in admin report operations:

- `admin_note`
- `editor_summary`
- `status_note`

Deferred:

- raw report HTML editing
- raw report JSON editing
- S3 artifact rewrite
- PDF generation

## Draft API

```text
POST /admin/reports/{parent_id}/{student_id}/{week_start}/edit-drafts
GET /admin/reports/{parent_id}/{student_id}/{week_start}/edit-drafts/{draft_id}
POST /admin/reports/{parent_id}/{student_id}/{week_start}/edit-drafts/{draft_id}/apply
```

Draft record fields:

- `draft_id`
- `report_id`
- `parent_id`
- `student_id`
- `week_start`
- `source_updated_at`
- `created_by`
- `created_at`
- `reason`
- `proposed_fields`
- `status`: `draft` or `applied`

## Apply Behavior

Apply validates:

- report exists
- draft exists
- draft is not already applied
- draft source report id matches current report
- draft `source_updated_at` matches current report `updated_at`
- proposed fields are in the allowlist

Apply writes:

- report metadata fields
- `last_operation=edit_report`
- `last_operation_result=success`
- `last_operation_by`
- `last_operation_at`
- append-only report audit event `apply_report_edit`

## Privacy Boundary

Responses must omit:

- `weekly-reports/`
- S3 keys
- presigned URLs
- raw report HTML
- raw report JSON
- auth/session tokens
- artifact payloads

## Production Safety

Production release smoke must verify route/UI availability without creating or applying a production edit draft.

