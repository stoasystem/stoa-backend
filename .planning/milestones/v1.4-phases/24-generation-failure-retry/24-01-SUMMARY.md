---
plan_id: 24-01
phase: 24
phase_name: Generation Failure Retry
status: complete
completed: 2026-06-04
---

# Plan 24-01 Summary: Generation Failure Retry

## Completed

- Added admin-only `POST /admin/reports/{parent_id}/{student_id}/{week_start}/retry-generation`.
- Retry accepts only reports with `status == "generation_failed"`.
- Retry atomically claims a failed report by conditionally transitioning it to `generation_retrying` before running generation side effects.
- Retry targets one parent/student/week report and reuses the existing report generation, artifact storage, metadata, and email delivery flow.
- Retry validates that the generated/stored report ID matches the original failed report ID before writing retry audit fields.
- Retry writes success audit fields:
  - `generation_retry_attempted_at`
  - `generation_retry_completed_at`
  - `last_operation=retry_generation`
  - `last_operation_result=success`
  - `last_operation_by`
  - `last_operation_at`
- Retry failure preserves `generation_failed` and writes generation error plus failed operation audit fields.
- Retry redacts private `weekly-reports/*` artifact keys and S3 key field names from persisted/returned error text.
- Retry response returns artifact availability booleans only, not private artifact keys.
- Added focused tests for successful retry, refused statuses, concurrent claim refusal, admin-only access, failed retry audit, repository claim behavior, and privacy output.

## Review Closure

- Fixed blocker: concurrent admin retries are now gated by `report_repo.try_start_generation_retry`, a DynamoDB conditional update from `generation_failed` to `generation_retrying`.
- Fixed warning: retry failures and persisted operation metadata redact private report artifact keys before client exposure.
- Fixed warning: added non-admin retry rejection coverage.

## Verification

- `uv run pytest tests/test_admin_report_ops.py tests/test_parent_children.py` - 85 passed.
- `uv run ruff check src/stoa/db/repositories/report_repo.py src/stoa/routers/admin.py tests/test_admin_report_ops.py tests/test_parent_children.py` - passed.

## Notes

- Successful retry can still result in `email_failed` if the generation/storage succeeds but SES delivery fails. That is intentional: Phase 24 concerns generation recovery, while delivery recovery is covered by Phase 25.
