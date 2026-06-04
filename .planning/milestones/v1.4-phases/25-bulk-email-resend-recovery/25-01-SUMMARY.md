---
plan_id: 25-01
phase: 25
phase_name: Bulk Email Resend Recovery
status: complete
completed: 2026-06-04
---

# Plan 25-01 Summary: Bulk Email Resend Recovery

## Completed

- Added admin-only `POST /admin/reports/bulk-resend`.
- Added request validation for 1-25 selected report identifiers.
- Bulk resend processes selected reports in input order and returns per-item results:
  - `success`
  - `refused`
  - `not_found`
  - `failed`
- Reused the existing single-report private HTML artifact read and email send path.
- Refactored single-report resend into a helper so single and bulk paths share audit behavior.
- Preserved private artifact boundaries: response returns operation metadata only, not raw HTML, S3 keys, URLs, or presigned URLs.
- Added focused tests for admin-only access, batch size enforcement, mixed result batches, continued processing after failures, audit fields, and response privacy.

## Verification

- `uv run pytest tests/test_admin_report_ops.py tests/test_parent_children.py` - 88 passed.
- `uv run ruff check src/stoa/routers/admin.py tests/test_admin_report_ops.py tests/test_parent_children.py` - passed.

## Notes

- Bulk resend remains synchronous and capped at 25 selected reports. Large incident-wide recovery remains future scope.
- Failed sends preserve `email_failed` and write the same resend audit fields as the single-report endpoint.
