# Phase 51 Context

**Phase:** Backend Report Edit Draft And Apply APIs
**Milestone:** v2.0 Controlled Report Editing MVP
**Started:** 2026-06-05

## Inputs

- Phase 50 accepted a metadata-only editing MVP.
- Editable fields are restricted to `admin_note`, `editor_summary`, and `status_note`.
- Raw report HTML/JSON editing, S3 artifact rewrite, presigned URLs, and broad S3 scans remain out of scope.

## Existing Extension Points

- Report summary records live under `PK=REPORT#{report_id}`, `SK=SUMMARY`.
- Report audit events already use append-only `AUDIT#...` records in the report partition.
- Admin report operations routes already enforce `require_role("admin")`.
- Existing redaction helpers remove `weekly-reports/`, S3 field names, and presigned URL markers.

## Implementation Decision

Report edit drafts are stored in the same report partition as `SK=EDIT_DRAFT#{draft_id}` items. Apply updates only report metadata fields on the `SUMMARY` row and appends `apply_report_edit` audit evidence.

No CDK, S3, Lambda permissions, tables, GSIs, or IAM changes were required.
