---
status: resolved
trigger: "update lambda function code failed"
created: 2026-06-03
updated: 2026-06-03
---

# Debug Session: update-lambda-function-code-failed

## Symptoms

- expected_behavior: Lambda function code update/deploy should succeed.
- actual_behavior: Lambda function code update failed.
- error_messages: unknown; user has not pasted AWS/CDK error output yet.
- timeline: unknown; reported after v1.2 backend changes and cleanup.
- reproduction: unknown; likely CDK deploy or Lambda code update against `stoa-api`/`stoa-weekly-report`.

## Current Focus

- hypothesis: The observed GitHub Actions `update-function-code` failure is an IAM authorization gap for `stoa-weekly-report`; local `dist/` freshness was also an issue for local CDK deploys but not the Actions root cause.
- test: Confirm denied action/resource from the GitHub Actions log, add permission for the backend deploy role, add preflight dry-run, and rebuild local `dist/`.
- expecting: After the infra policy is deployed, the backend workflow preflight and `update-function-code` loop can update both `stoa-api` and `stoa-weekly-report`.
- next_action: push backend changes and verify backend deploy workflow
- reasoning_checkpoint: GitHub Actions failure log proves packaging reached AWS and `stoa-api` updated successfully; failure is an IAM authorization gap for `stoa-weekly-report`, not an application import/package failure.
- tdd_checkpoint:

## Evidence

- 2026-06-03: Latest failed backend deploy run `26852709108` failed in `Update Lambda function code`.
- `stoa-api` update succeeded in the same step with `CodeSize: 30295529` and `LastUpdateStatus: InProgress`.
- The second update failed with `AccessDeniedException`: assumed role `arn:aws:sts::562923011260:assumed-role/stoa-github-backend-deploy/GitHubActions` is not authorized for `lambda:UpdateFunctionCode` on `arn:aws:lambda:eu-central-2:562923011260:function:stoa-weekly-report`.
- Earlier local CDK evidence: `stoa-infra/stacks/api_stack.py` uses `lambda_.Code.from_asset("../stoa-backend/dist")`, while local `dist/` was empty. That can break local CDK deploys, but it is not the root cause of the observed GitHub Actions `update-function-code` failure because that workflow rebuilds `dist` and `lambda.zip`.
- `aws` CLI is not installed locally, so the IAM role cannot be patched directly from this workstation session.
- timestamp: 2026-06-02T22:59:47.724Z
  observation: Rebuilt local `dist/` with the CI-compatible Python 3.12 manylinux2014 aarch64 dependency install and copied `src/stoa` into `dist/stoa`.
  supports: Local CDK/package freshness issue is fixed separately from the observed IAM failure.
- timestamp: 2026-06-02T22:59:47.724Z
  observation: Verified `dist/stoa/services/report_artifact_service.py` and `dist/stoa/jobs/weekly_reports.py` exist; `python3 -m compileall -q dist/stoa` passed; zipped asset `/private/tmp/stoa-lambda-debug.zip` is 30M.
  supports: Fresh Lambda package contains the new report artifact module and remains below direct zip upload size limits.
- timestamp: 2026-06-02T22:59:47.724Z
  observation: `python3` syntax parse of `/Users/zhdeng/stoa-infra/stacks/api_stack.py` passed after the IAM policy attachment change.
  supports: Infra fix has no Python syntax error; CDK synth/deploy remains unverified locally because `cdk` is not on PATH.
- timestamp: 2026-06-03
  observation: `CDK_OUTDIR=/private/tmp/stoa-cdk-synth .venv/bin/python app.py` synthesized successfully. `/private/tmp/stoa-cdk-synth/StoaApiStack.template.json` contains `GithubBackendLambdaUpdatePolicy` as `AWS::IAM::Policy` with `Action: lambda:UpdateFunctionCode`, resources for both `StoaApiFunction` and `StoaWeeklyReportFunction`, and `Roles: ["stoa-github-backend-deploy"]`.
  supports: The infra CDK change will attach the missing backend deploy role permission when deployed.
- timestamp: 2026-06-03
  observation: Pushed infra commit `9aaf6a7` and GitHub Actions run `26853237769` completed successfully, including `CDK Deploy`.
  supports: The missing IAM role permission has been applied in AWS.

## Eliminated

- Lambda zip package build failure: eliminated for the observed GitHub Actions failure, because AWS accepted and applied the same package to `stoa-api`.
- Missing new module in Actions package: eliminated for the observed failure by successful `stoa-api` code update before the authorization failure.

## Resolution

- root_cause: `stoa-github-backend-deploy` lacks identity-based permission for `lambda:UpdateFunctionCode` on `stoa-weekly-report`.
- fix: Added a backend workflow dry-run preflight so missing permissions fail before partially updating any Lambda function. Added a CDK policy attachment in `stoa-infra` so the existing `stoa-github-backend-deploy` role can update both `stoa-api` and `stoa-weekly-report`.
- verification: GitHub failure log confirms the exact denied action/resource. Local `dist` was rebuilt and verified to include the new weekly report files; infra syntax parse passed; CDK synth produced the expected IAM policy resource; infra GitHub Actions run `26853237769` deployed successfully. Final production verification is the backend deploy workflow after pushing backend.
- files_changed: `.github/workflows/deploy.yml`, `.planning/debug/update-lambda-function-code-failed.md`, `/Users/zhdeng/stoa-infra/stacks/api_stack.py`; gitignored `dist/` rebuilt locally.
