# Phase 54 Artifact Editing Contract

**Status:** Accepted for Phase 55 implementation
**Scope:** v2.1 backend-mediated report artifact preview/apply workflow

## Goal

Admins can preview and apply bounded report artifact edits without direct S3 access, raw artifact exposure, or in-place artifact overwrite.

## Editable Scope

Phase 55 may edit only allowlisted JSON artifact fields that can be rendered back to safe parent-facing HTML:

| Field | Type | Limit | Notes |
|-------|------|-------|-------|
| `title` | string | 200 chars | Optional report title/headline. |
| `summary` | string | 2000 chars | Parent-facing overview text. |
| `highlights` | list of strings | 10 items, 400 chars each | Positive learning highlights. |
| `concerns` | list of strings | 10 items, 400 chars each | Areas needing attention. |
| `recommendations` | list of strings | 10 items, 400 chars each | Suggested parent/student actions. |

Out of scope for Phase 55:

- Arbitrary JSON patch paths.
- Raw HTML submitted by the frontend.
- Freeform WYSIWYG editing.
- Direct S3 key edits.
- Report identity fields such as `parent_id`, `student_id`, `week_start`, and `report_id`.

## Preview Lifecycle

1. Admin selects a report through existing admin report operations.
2. Backend loads report summary metadata and current private JSON/HTML artifacts.
3. Backend validates proposed fields against the allowlist and private-marker denylist.
4. Backend creates a draft/preview row under `PK=REPORT#{report_id}`, `SK=ARTIFACT_EDIT_DRAFT#{draft_id}`.
5. Preview response returns sanitized field-level diffs, validation result, opaque draft ID, source artifact version, and source report `updated_at`.

Preview response must not include:

- Private S3 keys.
- Presigned URLs.
- Raw report JSON.
- Raw unreviewed HTML.
- Auth/session tokens.
- Full artifact payloads.

## Apply Lifecycle

1. Admin submits `draft_id` and a non-empty operator reason.
2. Backend reloads the draft and report summary.
3. Backend rejects apply if the report summary `updated_at`, current artifact version, or current artifact metadata differs from the draft source snapshot.
4. Backend reads the current JSON artifact, applies validated fields, and renders sanitized HTML server-side.
5. Backend writes new JSON and HTML artifacts under versioned keys.
6. Backend conditionally updates the report summary to point at the new current artifact version and new current artifact keys.
7. Backend marks the draft applied.
8. Backend writes append-only audit evidence.

## Versioned Storage Layout

Canonical current keys remain valid:

- `weekly-reports/{parent_id}/{student_id}/{week_start}/report.json`
- `weekly-reports/{parent_id}/{student_id}/{week_start}/report.html`

Versioned artifact apply writes:

- `weekly-reports/{parent_id}/{student_id}/{week_start}/versions/{version_id}/report.json`
- `weekly-reports/{parent_id}/{student_id}/{week_start}/versions/{version_id}/report.html`

The first versioned apply should treat existing canonical keys as the prior version and write the new version under `versions/{version_id}/`. The report summary then stores the new current artifact pointers.

## Report Summary Metadata

Phase 55 should add or update these metadata fields on the report summary row:

| Field | Purpose |
|-------|---------|
| `artifact_version_id` | Opaque current artifact version ID. |
| `artifact_version_created_at` | Current artifact version creation timestamp. |
| `artifact_version_created_by` | Admin/operator ID for current version. |
| `json_s3_key` | Server-side current JSON key, never returned to frontend. |
| `html_s3_key` | Server-side current HTML key, never returned to frontend. |
| `previous_artifact_version_id` | Opaque prior version ID for rollback metadata. |
| `previous_json_s3_key` | Server-side prior JSON key for rollback metadata. |
| `previous_html_s3_key` | Server-side prior HTML key for rollback metadata. |
| `last_operation` | `edit_report_artifact`. |
| `last_operation_result` | `success`, `refused`, or `failed`. |

Frontend/API responses may expose opaque version IDs and timestamps, but not `json_s3_key`, `html_s3_key`, `previous_json_s3_key`, or `previous_html_s3_key`.

## Audit Evidence

Every preview and apply/refusal event writes to the existing report audit timeline.

Required audit metadata:

- `action`: `create_report_artifact_edit_preview` or `apply_report_artifact_edit`.
- `actor`.
- `reason`.
- `source`.
- `result`.
- `draft_id`.
- `source_artifact_version_id`.
- `new_artifact_version_id` when apply succeeds.
- `previous_artifact_version_id`.
- `validation_result`.
- Sanitized `before` and `after` metadata snapshots.
- `correlation_id`.
- `event_at`.

Audit payloads must remain metadata-only and redacted.

## Privacy Denylist

Validation and response sanitization must reject or redact:

- `weekly-reports/`
- `json_s3_key`
- `html_s3_key`
- `s3_key`
- `presignedUrl`
- `presigned_url`
- `X-Amz-`
- `https://s3`
- raw `<html` content
- bearer/auth/session token markers

## Rollback Boundary

Phase 55 records rollback metadata only. It does not need to implement a rollback endpoint. Operators can identify the prior version from audit/server-side metadata, but the frontend must not receive private prior S3 keys.

## Implementation Notes For Phase 55

- Prefer a new service module, for example `report_artifact_edit_service.py`, to avoid expanding metadata-only `report_edit_service.py` beyond its original scope.
- Reuse `report_artifact_service.get_report_json`, `get_report_html`, content types, and canonical key validation.
- Add versioned-key helpers to `report_artifact_service.py`.
- Add conditional repository helpers instead of broad table scans.
- Add focused unit tests before production smoke.
