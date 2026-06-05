# Phase 43 Verification

**Phase:** 43 - Async Generation Retry Backend
**Status:** Passed
**Verified at:** 2026-06-05T12:20:00+02:00

## Implementation Evidence

Backend now supports:

- `POST /admin/reports/recovery-jobs/retry-generation/preview`
- `POST /admin/reports/recovery-jobs/retry-generation`
- Weekly worker event `report_recovery_retry_generation`
- `job_type=retry_generation`
- target audit action `retry_generation_target`
- job audit actions `create_retry_generation_job`, `run_retry_generation_job`, and `complete_retry_generation_job`

## Verification Commands

```bash
uv run pytest -q tests/test_admin_report_ops.py tests/test_weekly_reports_job.py
```

Result:

```text
59 passed in 1.00s
```

```bash
uv run ruff check src/stoa/services/report_recovery_job_service.py src/stoa/jobs/weekly_reports.py src/stoa/routers/admin.py tests/test_admin_report_ops.py tests/test_weekly_reports_job.py
```

Result:

```text
All checks passed!
```

## Coverage

- Generation retry preview returns metadata-only targets.
- Generation retry preview rejects wrong status before scanning.
- Generation retry job creation persists stable target snapshot, writes audit, and invokes worker with `job_type=retry_generation`.
- Weekly handler routes generation retry worker events.
- Worker executes a target through existing single-report retry service and updates counters/audit.
- Resend jobs remain backward-compatible when old records omit `job_type`.

## Decision

Phase 43 passes. Proceed to Phase 44 admin UI.

