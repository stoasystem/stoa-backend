---
phase: 21-smoke-and-orphan-artifact-cleanup
status: passed
score: 1.0
verified: 2026-06-04
requirements: [CLEAN-01, CLEAN-02, CLEAN-03]
---

# Phase 21 Verification

## Verdict

`passed`

Phase 21 implemented explicit cleanup for smoke artifacts and failed partial JSON writes. Tests prove real successful reports are not deleted, partial JSON artifacts are cleaned best-effort on HTML write failure, and deployed smoke writes/reads/deletes the deterministic smoke artifact with `cleanup: performed`.

## Must-Haves

| Requirement | Result | Evidence |
|-------------|--------|----------|
| CLEAN-01 | passed | `run_report_artifact_s3_smoke` deletes the deterministic smoke JSON object after readback. Live smoke returned `cleanup: performed`, and `head-object` for the smoke key returned 404 Not Found afterward. |
| CLEAN-02 | passed | `write_report_artifacts` wraps the HTML write and calls `delete_object` for the already-written JSON key when HTML write fails, then re-raises the original write failure. Tests cover successful cleanup and cleanup failure preserving the original HTML write error. |
| CLEAN-03 | passed | Tests assert successful real report writes perform no deletes, failed partial writes delete only the JSON partial key, and smoke deletes only the deterministic smoke key. Live smoke deletion target is `weekly-reports/smoke-parent/smoke-student/2026-06-01/report.json`, not a real parent report path. |

## Automated Checks Run

- `PYTHONPATH=src pytest tests/test_report_artifact_service.py tests/test_report_flow.py tests/test_weekly_reports_job.py`
  - Result: 33 passed, 1 pytest config warning.
- `git diff --check`
  - Result: passed.
- `aws lambda update-function-code --function-name stoa-api --zip-file fileb://lambda.zip --profile stoa`
  - Result: passed.
- `aws lambda update-function-code --function-name stoa-weekly-report --zip-file fileb://lambda.zip --profile stoa`
  - Result: passed.
- `aws lambda wait function-updated` for both functions
  - Result: passed.
- `aws lambda get-function-configuration --function-name stoa-weekly-report --profile stoa`
  - Result: `State=Active`, `LastUpdateStatus=Successful`, `CodeSha256=7AbZKONb9w0WO5wwtsrCvPxG+fqX4dJbyVC47oIhOFQ=`.
- `aws lambda invoke --function-name stoa-weekly-report --payload '{"job":"report_artifact_s3_smoke"}' --cli-binary-format raw-in-base64-out --profile stoa /tmp/stoa-weekly-report-phase21-smoke-cdk-sync.json`
  - Result: status code 200; output `status: passed`, `readback_ok: true`, `cleanup: performed`.
- `aws s3api head-object --bucket stoa-reports-562923011260 --key weekly-reports/smoke-parent/smoke-student/2026-06-01/report.json --profile stoa`
  - Result: 404 Not Found after smoke cleanup.
- `cdk deploy StoaApiStack --profile stoa --require-approval never`
  - Result: passed; CloudFormation Lambda asset reference synced to the current Phase 21 package.
- `cdk diff StoaApiStack --profile stoa`
  - Result: no differences after CDK sync.

## Human Verification

None required. Verification used tests, Lambda update/wait, live smoke, S3 object absence check, and CDK post-deploy diff.

## Residual Risks

- Historical smoke artifacts from before Phase 21 may still exist if they used different keys. The deterministic smoke path verified in v1.2/v1.3 is now cleaned up on each smoke run.
- Broad orphan discovery/listing remains out of scope because it would require bucket listing and an operational policy decision. Phase 21 covers current deterministic smoke and partial-write cleanup paths.
