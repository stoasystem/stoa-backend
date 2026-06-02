---
phase: 17-deployed-private-object-smoke
status: passed
score: 0.86
verified: 2026-06-03
requirements: [SMOKE-01, SMOKE-02, SMOKE-03, SMOKE-04, SMOKE-05]
---

# Phase 17 Verification

## Verdict

`passed`

This phase passes for adding and testing the Lambda-event smoke mechanism. Actual deployed Lambda invocation was not run locally because AWS CLI is not installed; Phase 18 must record deployed-state confidence separately.

## Must-Haves

| Requirement | Result | Evidence |
|-------------|--------|----------|
| SMOKE-01 | passed | `weekly_reports.handler(...)` routes only `event["job"] == "report_artifact_s3_smoke"` to the smoke helper. No HTTP route was added. `tests/test_weekly_reports_job.py` proves the smoke event does not run the normal weekly job. |
| SMOKE-02 | passed | `run_report_artifact_s3_smoke` writes `weekly-reports/smoke-parent/smoke-student/{week_start}/report.json`; tests assert the default key for `2026-06-01`. |
| SMOKE-03 | passed | The smoke helper immediately calls `get_report_json(...)` for the same key and verifies marker/key readback; tests use a fake S3 client that serves the object written by `put_object`. |
| SMOKE-04 | passed | Smoke output returns `status`, `bucket`, `key`, `content_type`, `readback_ok`, and `cleanup`; tests assert no artifact content, public URL, or presigned URL fields are returned. |
| SMOKE-05 | passed | The smoke helper uses direct private S3 `put_object` and `get_object`; it does not call bucket listing, public URL generation, access logs, frontend routes, or presigned URL APIs. |

## Automated Checks Run

- `uv run pytest`
  - Result: 111 passed.
- `git diff --check`
  - Result: passed.
- `python -m py_compile src/stoa/services/report_artifact_service.py src/stoa/jobs/weekly_reports.py`
  - Result: passed.

## Human Verification

Deploy-capable invocation still required for live proof:

```text
aws lambda invoke \
  --function-name stoa-weekly-report \
  --payload '{"job":"report_artifact_s3_smoke","week_start":"2026-06-01"}' \
  /tmp/stoa-report-artifact-smoke.json
```

Expected result fields: `status=passed`, `readback_ok=true`, `content_type=application/json`, `key` under `weekly-reports/`, no object content.

## Residual Risks

- Live deployed Lambda env/IAM state remains unverified on this machine because AWS CLI is unavailable.
- Smoke cleanup is intentionally not performed; result records `cleanup=not_performed`.
