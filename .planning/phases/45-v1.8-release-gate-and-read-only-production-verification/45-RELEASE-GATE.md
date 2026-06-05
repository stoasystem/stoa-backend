# Phase 45 Release Gate Evidence

**Date:** 2026-06-05
**Milestone:** v1.8 Incident Generation Retry Jobs
**Status:** Passed

## Deployment Evidence

### Backend

| Field | Value |
|-------|-------|
| Repository | `stoasystem/stoa-backend` |
| Branch | `main` |
| Deploy run | `27011890471` |
| Commit | `462b17f62540e257bc506c66c6aa6acfab106d93` |
| Display title | `feat: add async generation retry jobs` |
| Result | Success |
| Created | `2026-06-05T11:20:44Z` |
| Completed | `2026-06-05T11:21:46Z` |
| Job | `Build Lambda package & Update function` / `79717253006` |

Backend deploy job evidence:

- Checkout succeeded.
- Python 3.12 setup and uv install succeeded.
- Lambda deployment package built for linux arm64 wheels.
- Lambda dist provenance verification succeeded.
- Package summary printed manifest.
- AWS OIDC credentials configured.
- `update-function-code --dry-run` succeeded for `stoa-api` and `stoa-weekly-report`.
- Both Lambda functions were updated.
- `aws lambda wait function-updated` succeeded.

### Frontend

| Field | Value |
|-------|-------|
| Repository | `stoasystem/stoa-frontend` |
| Branch | `main` |
| Deploy run | `27011890698` |
| Commit | `2bfa01b3826b5d76eb0f347175f098b60b96558c` |
| Display title | `feat: add generation retry recovery UI` |
| Result | Success |
| Created | `2026-06-05T11:20:45Z` |
| Completed | `2026-06-05T11:21:42Z` |
| Job | `Build & Deploy to S3 + CloudFront` / `79717254068` |

Frontend deploy job evidence:

- Checkout succeeded at commit `2bfa01b3826b5d76eb0f347175f098b60b96558c`.
- Node.js setup and `npm ci` succeeded.
- `npm run lint` succeeded.
- Production build succeeded.
- S3 static asset sync succeeded.
- `index.html` uploaded with no-cache headers.
- CloudFront invalidation created.

CloudFront invalidation:

| Field | Value |
|-------|-------|
| Distribution | `E27CVAMQHDMW80` |
| Invalidation | `I7L1OJG03YRK911CCZKE9UU81U` |
| Status | `Completed` |
| CreateTime | `2026-06-05T11:21:38.982000+00:00` |

Production bundle check:

- `https://app.stoaedu.ch/admin/report-operations` references `/assets/index-vx0oD8c3.js`.
- Bundle contains `Async recovery job`.
- Bundle contains `Retry generation`.
- Bundle contains `generation_failed`.
- Bundle contains `recovery-jobs/retry-generation`.

## Lambda Runtime Evidence

Captured after backend deploy run `27011890471`.

| Function | State | LastUpdateStatus | Runtime | Arch | LastModified | CodeSha256 |
|----------|-------|------------------|---------|------|--------------|------------|
| `stoa-api` | Active | Successful | python3.12 | arm64 | `2026-06-05T11:21:31.000+0000` | `DoZZnSyeRv4hx56zmkUv5luZYwhMnqrdCS+5l3pJtdk=` |
| `stoa-weekly-report` | Active | Successful | python3.12 | arm64 | `2026-06-05T11:21:38.000+0000` | `DoZZnSyeRv4hx56zmkUv5luZYwhMnqrdCS+5l3pJtdk=` |

## Lambda Dist Manifest Evidence

Commands:

```bash
python scripts/build_lambda_dist.py --zip lambda.zip
python scripts/build_lambda_dist.py --verify-only
python -m json.tool dist/.stoa-build-manifest.json
```

Result:

```text
Lambda dist built: sha=462b17f62540e257bc506c66c6aa6acfab106d93 source_tree_hash=daba911cb30f
Lambda dist verified: sha=462b17f62540e257bc506c66c6aa6acfab106d93 source_tree_hash=daba911cb30f
```

Manifest highlights:

| Field | Value |
|-------|-------|
| `source_git_sha` | `462b17f62540e257bc506c66c6aa6acfab106d93` |
| `source_git_dirty` | `false` |
| `source_tree_hash` | `daba911cb30f9d315d07ae38224d6c61daa036e47f85d64f30a7be8860aeb046` |
| `cdk_asset_hash` | `0a4d145921a521bb7de15319fd9858ca08ca6932531365b8997bb665185a0a34` |
| `runtime_target` | `python3.12` |
| `platform` | `manylinux2014_aarch64` |
| `architecture` | `arm64` |

## Local Quality Gate

Backend:

```bash
uv run pytest -q
```

Result: `188 passed in 1.60s`.

```bash
uv run ruff check src/stoa/services/report_recovery_job_service.py src/stoa/jobs/weekly_reports.py src/stoa/routers/admin.py tests/test_admin_report_ops.py tests/test_weekly_reports_job.py
```

Result: `All checks passed!`.

```bash
git diff --check
```

Result: passed.

Frontend:

```bash
npm run lint -- --max-warnings=0
npm run build
npx playwright test tests/e2e/admin-report-operations.spec.ts
git diff --check
```

Results:

- Lint passed.
- Build passed with the existing Vite large chunk warning.
- Playwright admin report operations e2e passed: `1 passed (3.5s)`.
- Diff whitespace check passed.

## CDK Diff Evidence

Command:

```bash
AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 uv run cdk diff StoaApiStack --context env=dev
```

Result:

- `StoaAuthStack`: no differences.
- `StoaDatabaseStack`: no differences.
- `StoaStorageStack`: no differences.
- `StoaNotificationStack`: no differences.
- `StoaApiStack`: one Lambda `Code.S3Key` asset diff for `stoa-api` and `stoa-weekly-report`.

CDK output showed:

```text
Resources
[~] AWS::Lambda::Function StoaApiFunction
  [~] Code .S3Key
[~] AWS::Lambda::Function StoaWeeklyReportFunction
  [~] Code .S3Key

Number of stacks with differences: 1
```

Classification:

- No DynamoDB, Cognito, S3, SES, IAM, environment variable, API Gateway, Step Functions, SQS, new Lambda, new table, new bucket, or new GSI infrastructure change is required for v1.8.
- The only CDK diff is expected Lambda code asset drift because the backend deploy workflow updates Lambda code directly from the GitHub-built zip rather than via CloudFormation asset S3 keys.
- No CDK deploy was performed for Phase 45.

Known warning:

- CDK/JSII printed the existing untested Node v26 warning.
- The warning did not block synth/diff.

## Gate Decision

v1.8 release gate passed.

The only residual release-gate item is the expected CDK Lambda code asset diff caused by direct Lambda deploys. It does not indicate infrastructure drift for tables, buckets, Cognito, IAM, API Gateway, orchestration, or environment configuration.

