# Phase 70 Release Gate

**Status:** Passed
**Recorded at:** 2026-06-07T11:52:01Z

## Deploy Evidence

### Backend

| Field | Value |
|-------|-------|
| Workflow | Deploy Backend |
| Run ID | `27091480178` |
| Run URL | `https://github.com/stoasystem/stoa-backend/actions/runs/27091480178` |
| Job ID | `79955768531` |
| Job name | Build Lambda package & Update function |
| Head SHA | `875a8fbe2a56c89169ba52cdf469777f72a866b7` |
| Status | completed / success |
| Created | 2026-06-07T11:39:45Z |
| Completed | 2026-06-07T11:40:51Z |

### Frontend

| Field | Value |
|-------|-------|
| Workflow | Deploy Frontend |
| Run ID | `27091612893` |
| Run URL | `https://github.com/stoasystem/stoa-frontend/actions/runs/27091612893` |
| Job ID | `79956122939` |
| Job name | Build & Deploy to S3 + CloudFront |
| Head SHA | `9171de6109e102185dc65f41c6294f644cad72de` |
| Status | completed / success |
| Created | 2026-06-07T11:45:47Z |
| Completed | 2026-06-07T11:46:47Z |

### Frontend CI

| Field | Value |
|-------|-------|
| Workflow | Frontend CI |
| Run ID | `27091612903` |
| Run URL | `https://github.com/stoasystem/stoa-frontend/actions/runs/27091612903` |
| Job ID | `79956122969` |
| Job name | build |
| Head SHA | `9171de6109e102185dc65f41c6294f644cad72de` |
| Status | completed / success |
| Created | 2026-06-07T11:45:47Z |
| Completed | 2026-06-07T11:46:28Z |

## Local Quality Gates

Backend:

```text
.venv/bin/python -m ruff check src/stoa/services/support_handoff_service.py src/stoa/routers/admin.py src/stoa/db/repositories/report_repo.py tests/test_admin_report_ops.py
```

Result: Passed, `All checks passed!`.

```text
.venv/bin/python -m pytest tests/test_admin_report_ops.py -k "support_handoff or recovery_job_support_package or recovery_evidence" -q
```

Result: Passed, `14 passed, 54 deselected in 0.92s`.

```text
python3 scripts/build_lambda_dist.py --zip /private/tmp/stoa-phase70-lambda.zip
.venv/bin/python scripts/build_lambda_dist.py --verify-only
```

Result: Passed. Local Lambda zip: `/private/tmp/stoa-phase70-lambda.zip` (29 MB).

Frontend:

```text
npm run lint
npm run build
npx playwright test tests/e2e/admin-report-operations.spec.ts
```

Result: Passed. Build emitted the existing Vite chunk-size warning for the main app bundle.

## Lambda Manifest And Runtime

| Function | State | LastUpdateStatus | LastModified | CodeSha256 | Runtime | Architecture |
|----------|-------|------------------|--------------|------------|---------|--------------|
| `stoa-api` | Active | Successful | 2026-06-07T11:40:38.000+0000 | `wDBXOh3jyY91TvwwbY1MU+XaryIv7xOoFcw4PxgnSvE=` | `python3.12` | `arm64` |
| `stoa-weekly-report` | Active | Successful | 2026-06-07T11:40:45.000+0000 | `wDBXOh3jyY91TvwwbY1MU+XaryIv7xOoFcw4PxgnSvE=` | `python3.12` | `arm64` |

Local manifest:

| Field | Value |
|-------|-------|
| `source_git_sha` | `875a8fbe2a56c89169ba52cdf469777f72a866b7` |
| `source_git_dirty` | `false` |
| `source_tree_hash` | `dabc4bfd801dd7c1346fea9aba643460395bfe18775b1b5e76b07c77fd256428` |
| `cdk_asset_hash` | `3a86599a11ef090ca6713c103111f19b2228c0fbe3d86d6c2c594eaa33f33d37` |
| Runtime target | `python3.12` |
| Architecture | `arm64` |

## CDK Diff

Command:

```text
uv run cdk diff --profile stoa-prod-admin --output /private/tmp/stoa_phase70_cdk_out
```

Result: Passed with one expected stack difference.

Classification:

- `StoaAuthStack`, `StoaDatabaseStack`, `StoaStorageStack`, `StoaNotificationStack`, `StoaAiStack`, `StoaMonitoringStack`, and `StoaFrontendStack`: no differences.
- `StoaApiStack`: Lambda `Code.S3Key` changes only for `StoaApiFunction` and `StoaWeeklyReportFunction`.
- No DynamoDB table, GSI, S3 bucket, IAM expansion, Cognito resource, API Gateway route, CloudFront resource, or public artifact path change.
- Lambda code asset drift is expected because the backend GitHub deploy updates Lambda code directly from the deploy workflow package.
