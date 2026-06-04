---
phase: 21-smoke-and-orphan-artifact-cleanup
plan: 01
subsystem: backend
tags: [s3, cleanup, smoke, weekly-reports, lambda]
requires: [CLEAN-01, CLEAN-02, CLEAN-03]
provides:
  - Explicit smoke artifact cleanup
  - Partial JSON artifact cleanup on HTML write failure
  - Deployed cleanup smoke evidence
affects: [report-artifacts, weekly-report-smoke, lambda-code]
tech-stack:
  added: []
  patterns:
    - Delete deterministic smoke objects after readback
    - Best-effort cleanup of partial writes while preserving original storage failure
key-files:
  created:
    - .planning/phases/21-smoke-and-orphan-artifact-cleanup/21-CONTEXT.md
    - .planning/phases/21-smoke-and-orphan-artifact-cleanup/21-01-PLAN.md
    - .planning/phases/21-smoke-and-orphan-artifact-cleanup/21-01-SUMMARY.md
    - .planning/phases/21-smoke-and-orphan-artifact-cleanup/21-VERIFICATION.md
    - .planning/phases/21-smoke-and-orphan-artifact-cleanup/21-REVIEW.md
  modified:
    - src/stoa/services/report_artifact_service.py
    - tests/test_report_artifact_service.py
    - tests/test_report_flow.py
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
    - .planning/STATE.md
    - .planning/PROJECT.md
key-decisions:
  - "Use explicit `delete_object` cleanup instead of lifecycle rules because target cleanup keys are known and do not require bucket listing."
  - "Partial JSON cleanup is best-effort and preserves the original artifact write failure."
requirements-completed: [CLEAN-01, CLEAN-02, CLEAN-03]
duration: 45min
completed: 2026-06-04
---

# Phase 21: Smoke and Orphan Artifact Cleanup Summary

## Performance

- **Duration:** 45 min
- **Started:** 2026-06-04
- **Completed:** 2026-06-04
- **Tasks:** 5
- **Files modified:** 7

## Accomplishments

- Updated `run_report_artifact_s3_smoke` to delete the deterministic smoke JSON object after successful readback.
- Changed smoke output from `cleanup: not_performed` to clear cleanup states:
  - `cleanup: performed` when delete succeeds.
  - `cleanup: failed` with `cleanup_error_class` when delete fails.
  - smoke status fails when cleanup fails.
- Updated `write_report_artifacts` so a failed HTML write triggers best-effort deletion of the already-written JSON artifact before re-raising the original write failure.
- Added tests for:
  - successful real report writes not deleting artifacts.
  - HTML write failure deleting the partial JSON object.
  - cleanup delete failure preserving the original HTML write error.
  - smoke write/read/delete behavior.
  - smoke cleanup failure reporting.
- Rebuilt `lambda.zip`, updated both `stoa-api` and `stoa-weekly-report`, then deployed `StoaApiStack` through CDK to sync CloudFormation Lambda asset references.
- Live smoke after CDK sync returned `cleanup: performed`.
- `head-object` for the deterministic smoke key returned 404 after smoke, proving the object was deleted.
- Post-deploy `cdk diff StoaApiStack --profile stoa` reported no differences.

## Verification

- `PYTHONPATH=src pytest tests/test_report_artifact_service.py tests/test_report_flow.py tests/test_weekly_reports_job.py` - 33 passed, 1 pytest config warning.
- `git diff --check` - passed.
- `aws lambda update-function-code` for `stoa-api` and `stoa-weekly-report` - passed.
- `aws lambda wait function-updated` for both functions - passed.
- `aws lambda invoke --function-name stoa-weekly-report --payload '{"job":"report_artifact_s3_smoke"}' --cli-binary-format raw-in-base64-out --profile stoa /tmp/stoa-weekly-report-phase21-smoke-final.json` - returned status code 200 and `cleanup: performed`.
- `cdk diff StoaApiStack --profile stoa` before CDK sync - only Lambda `Code.S3Key` drift to the current Phase 21 asset.
- `cdk deploy StoaApiStack --profile stoa --require-approval never` - passed and updated Lambda code references.
- `cdk diff StoaApiStack --profile stoa` after CDK sync - no differences.
- Final smoke after CDK sync returned status code 200 and `cleanup: performed`.
- Final `aws s3api head-object` for `weekly-reports/smoke-parent/smoke-student/2026-06-01/report.json` returned 404 Not Found.

## Deviations from Plan

- The plan allowed lifecycle cleanup, but explicit delete was more precise and did not require bucket listing or broad retention rules.
- After direct Lambda update, CDK deploy was also run to sync CloudFormation's Lambda asset references and leave `cdk diff` clean.

## Next Phase Readiness

Phase 22 can now build report operations visibility/recovery on top of hardened bucket transport, prefix-scoped IAM, and smoke/partial cleanup.
