---
phase: 20-prefix-scoped-report-artifact-iam
plan: 01
subsystem: infra
tags: [cdk, iam, s3, weekly-reports, least-privilege]
requires: [IAM-01, IAM-02, IAM-03, IAM-04]
provides:
  - Prefix-scoped reports bucket IAM for API Lambda
  - Prefix-scoped reports bucket IAM for weekly report Lambda
  - Deployed scoped-IAM live smoke evidence
affects: [report-artifacts, lambda-iam, stoa-infra]
tech-stack:
  added: []
  patterns:
    - Grant report artifact object actions explicitly on `weekly-reports/*`
    - Keep image bucket grants separate from report artifact grants
key-files:
  created:
    - .planning/milestones/v1.3-phases/20-prefix-scoped-report-artifact-iam/20-CONTEXT.md
    - .planning/milestones/v1.3-phases/20-prefix-scoped-report-artifact-iam/20-01-PLAN.md
    - .planning/milestones/v1.3-phases/20-prefix-scoped-report-artifact-iam/20-01-SUMMARY.md
    - .planning/milestones/v1.3-phases/20-prefix-scoped-report-artifact-iam/20-VERIFICATION.md
  modified:
    - /Users/zhdeng/stoa-infra/stacks/api_stack.py
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
    - .planning/STATE.md
    - .planning/PROJECT.md
key-decisions:
  - "Current report artifact writes/reads do not require reports bucket-level `ListBucket`; no reports bucket-level permissions are preserved."
- "Keep only `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject` under `weekly-reports/*`; remove tag/version/multipart actions after code review."
requirements-completed: [IAM-01, IAM-02, IAM-03, IAM-04]
duration: 45min
completed: 2026-06-04
---

# Phase 20: Prefix-Scoped Report Artifact IAM Summary

## Performance

- **Duration:** 45 min
- **Started:** 2026-06-04
- **Completed:** 2026-06-04
- **Tasks:** 5
- **Files modified:** 5

## Accomplishments

- Replaced broad `reports_bucket.grant_read_write(...)` on `stoa-api` and `stoa-weekly-report` with `_grant_report_artifact_read_write(...)`.
- Scoped report artifact S3 actions to `arn:aws:s3:::stoa-reports-562923011260/weekly-reports/*`.
- Preserved API Lambda image bucket permissions through the unchanged `images_bucket.grant_read_write(self.api_function)`.
- Avoided reports bucket-level permissions because current report artifact read/write/smoke behavior does not list the bucket.
- Narrowed object actions to `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject` after code review found tag/version/multipart actions exceeded observed runtime need.
- Ran CDK synth and confirmed both Lambda policies use the scoped `weekly-reports/*` report artifact ARN.
- Ran `cdk diff StoaApiStack --profile stoa`; diff removed broad reports bucket grants and added scoped object grants. The known Lambda asset hash drift was also shown.
- Deployed `StoaApiStack`; CloudFormation updated the two IAM policies and Lambda code references successfully.
- Confirmed post-deploy `cdk diff StoaApiStack --profile stoa` has no differences.
- Queried live IAM policies for both Lambda roles and confirmed report artifact statements are prefix-scoped.
- Invoked deployed `stoa-weekly-report` smoke; it wrote and read back the deterministic JSON artifact successfully.

## Verification

- `PYTHONPATH=src pytest tests/test_report_artifact_service.py tests/test_weekly_reports_job.py` - 27 passed, 1 pytest config warning.
- `git diff --check` - passed.
- `git -C /Users/zhdeng/stoa-infra diff --check` - passed.
- `cdk synth StoaApiStack --profile stoa` - passed; JSII emitted the known Node 26 warning.
- `cdk diff StoaApiStack --profile stoa` - passed with expected IAM changes plus known Lambda `Code.S3Key` drift.
- `cdk deploy StoaApiStack --profile stoa --require-approval never` - passed.
- `cdk diff StoaApiStack --profile stoa` after deployment - no differences.
- `aws iam get-role-policy` for API Lambda role - reports statement resource is `arn:aws:s3:::stoa-reports-562923011260/weekly-reports/*` with `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject`; image bucket resources remain `arn:aws:s3:::stoa-images-562923011260` and `/*`.
- `aws iam get-role-policy` for weekly report Lambda role - reports statement resource is `arn:aws:s3:::stoa-reports-562923011260/weekly-reports/*` with `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject`.
- `aws lambda invoke --function-name stoa-weekly-report --payload '{"job":"report_artifact_s3_smoke"}' --cli-binary-format raw-in-base64-out --profile stoa /tmp/stoa-weekly-report-phase20-smoke.json` - status code 200.
- Smoke output: `{"status":"passed","bucket":"stoa-reports-562923011260","key":"weekly-reports/smoke-parent/smoke-student/2026-06-01/report.json","content_type":"application/json","readback_ok":true,"cleanup":"not_performed"}`.
- `aws s3api head-object` for the smoke key - content type `application/json`, SSE `AES256`, last modified `2026-06-04T14:22:01+00:00`.

## Deviations from Plan

- `cdk deploy StoaApiStack` also updated dependency stacks' CDK metadata and Lambda code references as expected by CDK dependency deployment. `StoaStorageStack` had no changes; post-deploy ApiStack diff is clean.

## Next Phase Readiness

Phase 21 can now implement smoke/orphan cleanup with delete access already available only inside `weekly-reports/*`.
