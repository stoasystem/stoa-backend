---
phase: 20-prefix-scoped-report-artifact-iam
status: passed
score: 1.0
verified: 2026-06-04
requirements: [IAM-01, IAM-02, IAM-03, IAM-04]
---

# Phase 20 Verification

## Verdict

`passed`

Phase 20 delivered prefix-scoped report artifact IAM for both Lambdas and deployed it successfully. Live IAM policies show reports bucket object actions now target only `weekly-reports/*`, API image bucket permissions remain intact, no reports bucket-level permissions are retained, and deployed weekly report smoke still passes.

## Must-Haves

| Requirement | Result | Evidence |
|-------------|--------|----------|
| IAM-01 | passed | API Lambda live inline policy `StoaApiFunctionServiceRoleDefaultPolicyA7202E0D` contains report artifact actions only on `arn:aws:s3:::stoa-reports-562923011260/weekly-reports/*`, narrowed to `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject`. Broad reports bucket and reports bucket `/*` resources were removed from the API policy. |
| IAM-02 | passed | Weekly report Lambda live inline policy `StoaWeeklyReportFunctionServiceRoleDefaultPolicyCAB3D477` contains report artifact actions only on `arn:aws:s3:::stoa-reports-562923011260/weekly-reports/*`, narrowed to `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject`. Deployed smoke returned `status: passed` and `readback_ok: true`. |
| IAM-03 | passed | API Lambda live inline policy still contains `arn:aws:s3:::stoa-images-562923011260` and `arn:aws:s3:::stoa-images-562923011260/*` with the existing image bucket read/write/list action set. `images_bucket.grant_read_write(self.api_function)` remains unchanged in CDK source. |
| IAM-04 | passed | No reports bucket-level permissions are retained. Current report artifact write/read/smoke code uses `PutObject`, `GetObject`, and future cleanup-compatible `DeleteObject` under object ARNs, so `ListBucket` is not required. This rationale is recorded in `20-CONTEXT.md` and `20-01-SUMMARY.md`. |

## Automated Checks Run

- `PYTHONPATH=src pytest tests/test_report_artifact_service.py tests/test_weekly_reports_job.py`
  - Result: 27 passed, 1 pytest config warning.
- `git diff --check`
  - Result: passed.
- `git -C /Users/zhdeng/stoa-infra diff --check`
  - Result: passed.
- `cdk synth StoaApiStack --profile stoa`
  - Result: passed; known JSII warning for untested Node 26.
- `cdk diff StoaApiStack --profile stoa`
  - Result: expected IAM changes; no storage changes; known Lambda asset hash drift included.
- `cdk deploy StoaApiStack --profile stoa --require-approval never`
  - Result: passed; IAM policy updates and Lambda code reference updates completed.
- `cdk diff StoaApiStack --profile stoa`
  - Result: no differences after deployment.
- `aws iam get-role-policy` for API and weekly report Lambda roles
  - Result: report artifact resources are scoped to `weekly-reports/*` with only get/put/delete object actions; image bucket resources preserved for API.
- `aws lambda get-function-configuration --function-name stoa-weekly-report --profile stoa`
  - Result: `State=Active`, `LastUpdateStatus=Successful`, `S3_REPORTS_BUCKET=stoa-reports-562923011260`.
- `aws lambda invoke --function-name stoa-weekly-report --payload '{"job":"report_artifact_s3_smoke"}' --cli-binary-format raw-in-base64-out --profile stoa /tmp/stoa-weekly-report-phase20-smoke.json`
  - Result: status code 200; smoke response passed.
- `aws s3api head-object --bucket stoa-reports-562923011260 --key weekly-reports/smoke-parent/smoke-student/2026-06-01/report.json --profile stoa`
  - Result: object exists with `ContentType=application/json` and `ServerSideEncryption=AES256`.

## Human Verification

None required. Verification used tests, CDK diff/deploy, live IAM checks, and deployed Lambda smoke.

## Residual Risks

- The deterministic smoke object remains because cleanup is intentionally owned by Phase 21.
- CDK/JSII continues to warn that Node 26 is not a tested runtime for the installed CDK library. Synth, diff, and deploy completed successfully.
