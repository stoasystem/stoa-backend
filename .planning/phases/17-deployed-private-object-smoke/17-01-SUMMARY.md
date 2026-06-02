---
phase: 17-deployed-private-object-smoke
plan: 01
subsystem: backend
tags: [lambda, s3, smoke, weekly-reports]
requires: [SMOKE-01, SMOKE-02, SMOKE-03, SMOKE-04, SMOKE-05]
provides:
  - Weekly Lambda report artifact smoke event
  - Private JSON put/get smoke helper
  - Smoke output contract tests
affects: [weekly-report-lambda, report-artifacts]
tech-stack:
  added: []
  patterns:
    - Lambda-event-only smoke command
    - Smoke output returns metadata without object content
key-files:
  created:
    - .planning/phases/17-deployed-private-object-smoke/17-VERIFICATION.md
  modified:
    - src/stoa/services/report_artifact_service.py
    - src/stoa/jobs/weekly_reports.py
    - tests/test_report_artifact_service.py
    - tests/test_weekly_reports_job.py
key-decisions:
  - "Use `job=report_artifact_s3_smoke` as the narrow weekly Lambda smoke event."
  - "Smoke writes only deterministic JSON under `weekly-reports/smoke-parent/smoke-student/{week_start}/report.json`."
  - "Smoke output records metadata and readback status, not artifact content."
patterns-established:
  - "Runtime smoke helpers accept injected S3 clients for deterministic local proof."
requirements-completed: [SMOKE-01, SMOKE-02, SMOKE-03, SMOKE-04, SMOKE-05]
duration: 30min
completed: 2026-06-03
---

# Phase 17: Deployed Private-Object Smoke Summary

## Performance

- **Duration:** 30 min
- **Started:** 2026-06-03
- **Completed:** 2026-06-03
- **Tasks:** 4
- **Files modified:** 5

## Accomplishments

- Added `report_artifact_service.run_report_artifact_s3_smoke(...)` to write and read a deterministic private JSON object using S3 `put_object` and `get_object`.
- Added weekly report Lambda handler routing for `{"job": "report_artifact_s3_smoke"}`.
- Added smoke tests proving canonical key, bucket, content type, readback success, no ACL, no object content in output, and no public/presigned URL fields.
- Added handler routing test proving the smoke event does not run the scheduled weekly report job.

## Verification

- `uv run pytest` - 111 passed.
- `git diff --check` - passed.
- `python -m py_compile src/stoa/services/report_artifact_service.py src/stoa/jobs/weekly_reports.py` - passed.

## Deviations from Plan

- The deployed Lambda was not invoked from this machine because AWS CLI is unavailable locally. The code path and fake-client smoke behavior are verified; deployed runtime proof remains evidence debt for Phase 18 or a deploy-capable environment.

## Next Phase Readiness

Phase 18 can close the milestone with durable evidence and explicitly record deployed-state confidence if live invocation remains unavailable.
