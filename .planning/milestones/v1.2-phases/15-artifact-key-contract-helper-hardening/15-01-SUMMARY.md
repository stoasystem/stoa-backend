---
phase: 15-artifact-key-contract-helper-hardening
plan: 01
subsystem: backend
tags: [s3, reports, artifacts, helper, tests]
requires: [ARTIFACT-01, ARTIFACT-02, ARTIFACT-03, ARTIFACT-04, ARTIFACT-05, STORAGE-01, STORAGE-02, STORAGE-03, STORAGE-04, STORAGE-08]
provides:
  - Canonical report artifact key helper
  - JSON/HTML private S3 write helper
  - JSON artifact read helper
affects: [weekly-report-storage, report-artifacts]
tech-stack:
  added: []
  patterns:
    - Strict report artifact key validation before S3 writes
    - Helper-level S3 client injection for deterministic tests and smoke reuse
key-files:
  created:
    - src/stoa/services/report_artifact_service.py
    - tests/test_report_artifact_service.py
    - .planning/phases/15-artifact-key-contract-helper-hardening/15-VERIFICATION.md
  modified:
    - src/stoa/services/report_service.py
    - tests/test_report_service.py
key-decisions:
  - "Use only `weekly-reports/` as the canonical report artifact prefix."
  - "Artifact key IDs must already be safe backend identifiers; unsafe strings fail closed instead of being sanitized into keys."
  - "The JSON read helper validates canonical JSON artifact keys before calling S3."
patterns-established:
  - "Weekly report storage delegates artifact keys and S3 put/get behavior to `report_artifact_service`."
requirements-completed: [ARTIFACT-01, ARTIFACT-02, ARTIFACT-03, ARTIFACT-04, ARTIFACT-05, STORAGE-01, STORAGE-02, STORAGE-03, STORAGE-04, STORAGE-08]
duration: 40min
completed: 2026-06-03
---

# Phase 15: Artifact Key Contract and Helper Hardening Summary

## Performance

- **Duration:** 40 min
- **Started:** 2026-06-03
- **Completed:** 2026-06-03
- **Tasks:** 4
- **Files modified:** 5

## Accomplishments

- Added `report_artifact_service` with `build_report_artifact_keys`, `write_report_artifacts`, and `get_report_json`.
- Locked exact artifact keys to `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}`.
- Hardened parent ID, student ID, and week start validation so blank, email-like, display-name-like, slash-containing, and invalid date inputs fail closed.
- Moved weekly report artifact writes from inline `put_object` calls to the helper while preserving JSON-before-HTML ordering.
- Added helper tests for exact keys, invalid inputs, write content types/no ACL, and JSON readback.
- Upgraded report storage tests from suffix assertions to full exact key assertions.

## Verification

- `PYTHONPATH=src pytest tests/test_report_artifact_service.py tests/test_report_service.py tests/test_report_flow.py tests/test_weekly_reports_job.py` - 49 passed, 1 warning from system Python config.
- `uv run pytest` - 109 passed.

## Deviations from Plan

None.

## Next Phase Readiness

Phase 16 can now focus on failure ordering and privacy boundaries with artifact keys and helper behavior locked behind tests.
