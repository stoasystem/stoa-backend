---
phase: 24
phase_name: Generation Failure Retry
status: passed
verified: 2026-06-04
requirements:
  - GEN-01
  - GEN-02
  - GEN-03
  - GEN-04
---

# Phase 24 Verification: Generation Failure Retry

## Verdict

`passed`

Phase 24 delivers a single-report admin retry endpoint for `generation_failed` weekly reports.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| GEN-01 | complete | `POST /admin/reports/{parent_id}/{student_id}/{week_start}/retry-generation` targets one report triple and first atomically claims the failed report. |
| GEN-02 | complete | Retry reuses `report_service.store_and_send_weekly_report`, which preserves the canonical report ID and artifact key builder; endpoint verifies stored report ID matches the original failed report ID. |
| GEN-03 | complete | Tests prove retry refuses `generated`, `email_sent`, `email_failed`, and `generation_claimed`. |
| GEN-04 | complete | Success and failure paths write retry attempt/completion or failure fields, operator, operation, result, and error metadata. |

## Automated Checks

- `uv run pytest tests/test_admin_report_ops.py tests/test_parent_children.py` - 85 passed.
- `uv run ruff check src/stoa/db/repositories/report_repo.py src/stoa/routers/admin.py tests/test_admin_report_ops.py tests/test_parent_children.py` - passed.

## Review Closure

- BLOCKER fixed: concurrent retry races are guarded by a conditional DynamoDB update that only claims reports still in `generation_failed`.
- WARNING fixed: private artifact key paths and S3 key field names are redacted from stored and returned retry error text.
- WARNING fixed: non-admin retry requests are covered and rejected with `403`.

## Privacy Checks

Retry response exposes only artifact availability booleans. Tests assert the response does not expose:

- `json_s3_key`
- `html_s3_key`
- `weekly-reports/`

Persisted operation error metadata is also redacted before response serialization.

## Residual Risks

- The retry path is synchronous and single-report only. Large incident recovery remains out of scope for v1.4 Phase 24.
