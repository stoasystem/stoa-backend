# Phase 57 Release Gate

**Status:** Passed
**Recorded at:** 2026-06-06T12:05:00+02:00

## Commits

- Backend artifact editing feature commit: `38ed661` (`feat: add report artifact edit preview APIs`)
- Backend release evidence commit at deploy time: `ad14cb4ea036ddadeacf1875d6c8986207e7d592` (`docs(56): record artifact edit preview UI`)
- Frontend artifact edit UI commit: `e0f76e4e58578bc3603fc14186804400cd4283b2` (`feat: add artifact edit preview UI`)

## Deploy Evidence

### Backend

- Workflow: Deploy Backend
- Run ID: `27059322157`
- Run URL: `https://github.com/stoasystem/stoa-backend/actions/runs/27059322157`
- Job: Build Lambda package & Update function
- Job ID: `79869305705`
- Head SHA: `ad14cb4ea036ddadeacf1875d6c8986207e7d592`
- Status: success
- Created: `2026-06-06T10:02:02Z`
- Completed: `2026-06-06T10:02:55Z`

Passed steps included Linux arm64 Lambda package build, provenance verification, package summary, OIDC AWS credentials, preflight update permissions, Lambda code update, and Lambda update wait.

### Frontend

- Workflow: Deploy Frontend
- Run ID: `27059324879`
- Run URL: `https://github.com/stoasystem/stoa-frontend/actions/runs/27059324879`
- Job: Build & Deploy to S3 + CloudFront
- Job ID: `79869312212`
- Head SHA: `e0f76e4e58578bc3603fc14186804400cd4283b2`
- Status: success
- Created: `2026-06-06T10:02:08Z`
- Completed: `2026-06-06T10:03:04Z`

Passed steps included lint, production build, S3 asset sync, `index.html` upload, and CloudFront invalidation.

### Frontend CI

- Workflow: Frontend CI
- Run ID: `27059324878`
- Run URL: `https://github.com/stoasystem/stoa-frontend/actions/runs/27059324878`
- Job: build
- Job ID: `79869312244`
- Head SHA: `e0f76e4e58578bc3603fc14186804400cd4283b2`
- Status: success
- Created: `2026-06-06T10:02:08Z`
- Completed: `2026-06-06T10:02:52Z`

## Local Quality Gates

Backend:

```text
.venv/bin/python -m ruff check src/stoa/services/report_artifact_edit_service.py src/stoa/services/report_artifact_service.py src/stoa/db/repositories/report_repo.py src/stoa/routers/admin.py tests/test_admin_report_ops.py
```

Result: passed.

```text
.venv/bin/python -m pytest tests/test_admin_report_ops.py tests/test_report_artifact_service.py -q
```

Result: 73 passed.

```text
.venv/bin/python -m pytest -q
```

Result: 202 passed.

Frontend:

```text
npm run lint -- src/services/admin/adminApi.ts src/hooks/admin/useAdminReportOperations.ts src/pages/admin/ReportOperationsPage.tsx tests/e2e/admin-report-operations.spec.ts
```

Result: passed.

```text
npm run build
```

Result: passed with the existing Vite chunk-size warning only.

```text
npx playwright test tests/e2e/admin-report-operations.spec.ts
```

Result: 1 passed.

## Lambda Manifest

Deploy workflow built the full Linux arm64 package and verified provenance successfully.

Local manifest smoke was also generated with:

```text
.venv/bin/python scripts/build_lambda_dist.py --skip-install --zip lambda.zip
.venv/bin/python scripts/build_lambda_dist.py --verify-only
```

Manifest:

- `source_git_sha`: `ad14cb4ea036ddadeacf1875d6c8986207e7d592`
- `source_git_dirty`: `false`
- `source_tree_hash`: `a255b91fe8d9b8b148920d94ccdc6d7bd9c550392d20331c3ca2264868eca13d`
- `cdk_asset_hash`: `60776c428215ff9850180cce9581bd635aa0a5f60ff95bbcb0f3d11921a8585e`
- `runtime_target`: `python3.12`
- `architecture`: `arm64`
- handlers verified:
  - `stoa.main.handler`
  - `stoa.jobs.weekly_reports.handler`

Note: local full dependency packaging with the repo `.venv` was blocked because that virtualenv lacks `pip`; the GitHub deploy workflow completed the full package build and deploy successfully.

## Lambda Runtime

Region: `eu-central-2`

`stoa-api`:

- State: `Active`
- LastUpdateStatus: `Successful`
- LastModified: `2026-06-06T10:02:42.000+0000`
- CodeSha256: `AB6/ZjjOToDmxF329Zc8jm+eaCiTgWZ/mZ1DHaR0bYs=`
- Runtime: `python3.12`
- Architecture: `arm64`

`stoa-weekly-report`:

- State: `Active`
- LastUpdateStatus: `Successful`
- LastModified: `2026-06-06T10:02:49.000+0000`
- CodeSha256: `AB6/ZjjOToDmxF329Zc8jm+eaCiTgWZ/mZ1DHaR0bYs=`
- Runtime: `python3.12`
- Architecture: `arm64`

## CDK Diff

Command:

```text
uv run cdk diff --profile stoa-prod-admin
```

Result:

- `StoaAuthStack`: no differences.
- `StoaDatabaseStack`: no differences.
- `StoaStorageStack`: no differences.
- `StoaNotificationStack`: no differences.
- `StoaAiStack`: no differences.
- `StoaMonitoringStack`: no differences.
- `StoaFrontendStack`: no differences.
- `StoaApiStack`: Lambda `Code.S3Key` asset drift only for `StoaApiFunction` and `StoaWeeklyReportFunction`.

Classification: expected Lambda code asset drift only. No table, bucket, GSI, IAM, Cognito, API Gateway, report bucket, or CloudFront infrastructure change.
