# Phase 60 UI Spec: Admin Artifact Rollback

## Surface

`/admin/report-operations`, inside the selected report detail panel.

## Controls

- `Rollback reason` textarea with default operator reason: `Restore previous artifact version`.
- `Preview rollback` button:
  - Disabled when reason is blank.
  - Disabled when `report.actions.rollback_artifact.enabled === false`.
  - Calls rollback preview endpoint.
- `Apply rollback` button:
  - Disabled until a draft rollback preview exists.
  - Calls rollback apply endpoint with the same operator reason.

## Display

The preview panel displays:

- Rollback preview id.
- Current artifact version id, defaulting visually to `original` when absent.
- Rollback target artifact version id, defaulting visually to `original` when absent.
- Validation result.
- Preview/apply status.
- Operation result message after preview/apply.

## Privacy

The UI intentionally does not render:

- S3 keys.
- Presigned URLs.
- Raw JSON artifact payloads.
- Raw HTML artifact payloads.
- Private source/target key field names such as `source_json_s3_key`.

## Error States

Backend refusal and stale-state errors are shown through the same operation message area as existing admin report mutations. The backend remains the source of truth for missing target, no-op, stale report, and stale artifact metadata checks.
