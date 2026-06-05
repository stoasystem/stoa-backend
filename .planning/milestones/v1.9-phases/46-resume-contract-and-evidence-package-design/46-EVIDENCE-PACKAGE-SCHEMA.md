# Phase 46 Support Evidence Package Schema

**Status:** Accepted
**Date:** 2026-06-05

## Endpoint

```text
GET /admin/reports/recovery-jobs/{job_id}/support-package
```

Optional query parameters:

- `include_targets=true`
- `include_job_audit=true`
- `include_report_audit=false`
- `target_limit=50`
- `audit_limit=50`
- `note=<operator note>`

## Response

```json
{
  "exported_at": "2026-06-05T11:30:00Z",
  "request_id": "apigw-request-id",
  "scope": "support_package",
  "complete": true,
  "job": {},
  "source_job": {},
  "rollup": {
    "target_count": 25,
    "success_count": 10,
    "failed_count": 4,
    "refused_count": 3,
    "not_found_count": 2,
    "skipped_cancelled_count": 1
  },
  "targets": [],
  "job_audit": [],
  "report_audit": [],
  "operator_note": "redacted/sanitized",
  "next_tokens": {},
  "privacy": {
    "metadata_only": true,
    "private_artifact_fields_omitted": true,
    "redacted_operator_note": true
  }
}
```

## Package Contents

Required:

- export timestamp
- API request id
- selected job summary
- source job summary when `source_job_id` exists
- rollup counts
- privacy metadata

Optional and bounded:

- target summaries
- job audit timeline
- report audit references
- sanitized operator note

## Redaction

Use existing metadata sanitizer and private artifact redaction:

- omit S3 key fields
- omit presigned/public URL fields
- redact text containing private artifact markers
- never include raw HTML/JSON artifacts
- never include auth tokens

## Observability

Support package generation is read-only:

- no recovery job mutation
- no report mutation
- no S3 read/write
- logs request id, actor, scope, job id, source job id, limits, result counts, and read-only status

