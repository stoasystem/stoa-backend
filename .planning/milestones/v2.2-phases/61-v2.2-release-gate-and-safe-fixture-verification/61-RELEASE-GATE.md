# Phase 61 Release Gate

**Status:** Passed
**Recorded at:** 2026-06-06T18:49:03Z

## Commits

- Backend rollback API commit: `1d3b434` (`feat: add report artifact rollback APIs`)
- Backend release evidence commit at primary deploy time: `5e1c673109a5f851ea64e730f9e5826a8fb0c0ae` (`docs(60): record artifact rollback UI`)
- Backend Phase 61 evidence commit: `7a53f32e4952ed7e839c13e6a4414a54c4be680e` (`docs(61): record release gate blocker`)
- Backend safe-fixture lookup fix commit: `123faad299d0fc6051b7677c8b75cb96df63c9e3` (`fix: ignore report child entities in parent lookups`)
- Frontend rollback UI commit: `6062b5dd13274a778abd52874ad3f72d828a7287` (`feat: add artifact rollback UI`)

## Deploy Evidence

### Backend

- Workflow: Deploy Backend
- Run ID: `27067184710`
- Run URL: `https://github.com/stoasystem/stoa-backend/actions/runs/27067184710`
- Job: Build Lambda package & Update function
- Job ID: `79889989806`
- Head SHA: `5e1c673109a5f851ea64e730f9e5826a8fb0c0ae`
- Status: success
- Created: `2026-06-06T16:07:59Z`
- Completed: `2026-06-06T16:08:54Z`

Passed steps included Linux arm64 Lambda package build, provenance verification, package summary, OIDC AWS credentials, preflight update permissions, Lambda code update, and Lambda update wait.

Post-evidence docs-only backend deploy:

- Workflow: Deploy Backend
- Run ID: `27069363195`
- Run URL: `https://github.com/stoasystem/stoa-backend/actions/runs/27069363195`
- Job: Build Lambda package & Update function
- Job ID: `79895730781`
- Head SHA: `7a53f32e4952ed7e839c13e6a4414a54c4be680e`
- Status: success
- Created: `2026-06-06T17:42:31Z`
- Completed: `2026-06-06T17:43:31Z`

This run was triggered by the Phase 61 evidence/blocker commit after read-only verification. It passed the same package build, provenance verification, preflight, update, and waiter steps.

Safe-fixture blocker fix backend deploy:

- Workflow: Deploy Backend
- Run ID: `27070767161`
- Run URL: `https://github.com/stoasystem/stoa-backend/actions/runs/27070767161`
- Job: Build Lambda package & Update function
- Job ID: `79899468017`
- Head SHA: `123faad299d0fc6051b7677c8b75cb96df63c9e3`
- Status: success
- Created: `2026-06-06T18:45:59Z`
- Completed: `2026-06-06T18:47:04Z`

This run deployed the report lookup fix that prevents `GSI-ParentId` child entities such as artifact edit drafts from being returned as report summary rows during selected-report operations.

### Frontend

- Workflow: Deploy Frontend
- Run ID: `27067175038`
- Run URL: `https://github.com/stoasystem/stoa-frontend/actions/runs/27067175038`
- Job: Build & Deploy to S3 + CloudFront
- Job ID: `79889963562`
- Head SHA: `6062b5dd13274a778abd52874ad3f72d828a7287`
- Status: success
- Created: `2026-06-06T16:07:30Z`
- Completed: `2026-06-06T16:08:26Z`

Passed steps included dependency install, lint, production build, S3 sync, no-cache `index.html` upload, and CloudFront invalidation.

### Frontend CI

- Workflow: Frontend CI
- Run ID: `27067175047`
- Run URL: `https://github.com/stoasystem/stoa-frontend/actions/runs/27067175047`
- Job: build
- Job ID: `79889963523`
- Head SHA: `6062b5dd13274a778abd52874ad3f72d828a7287`
- Status: success
- Created: `2026-06-06T16:07:30Z`
- Completed: `2026-06-06T16:08:14Z`

## Local Quality Gates

Backend:

```text
.venv/bin/python -m ruff check src/stoa/services/report_artifact_edit_service.py src/stoa/db/repositories/report_repo.py src/stoa/routers/admin.py tests/test_admin_report_ops.py
```

Result: passed.

```text
.venv/bin/python -m pytest tests/test_admin_report_ops.py tests/test_report_artifact_service.py -q
```

Result: 79 passed.

```text
.venv/bin/python -m pytest -q
```

Result before lookup fix: 208 passed.

```text
.venv/bin/python -m ruff check src/stoa/db/repositories/report_repo.py tests/test_parent_children.py
```

Result after lookup fix: passed.

```text
.venv/bin/python -m pytest tests/test_parent_children.py tests/test_admin_report_ops.py -q
```

Result after lookup fix: 141 passed.

```text
.venv/bin/python -m pytest -q
```

Result after lookup fix: 209 passed.

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

## Lambda Manifest And Runtime

Local dist was rebuilt after the stale-dist guard blocked the first CDK diff attempt:

```text
.venv/bin/python scripts/build_lambda_dist.py --skip-install --zip lambda.zip
.venv/bin/python scripts/build_lambda_dist.py --verify-only
```

Manifest summary:

- `source_git_sha`: `123faad299d0fc6051b7677c8b75cb96df63c9e3`
- `source_tree_hash`: `9e18eaa0f101e064aa57c5f2cfb152e0e32c07382156111847bb409beaf4ba63`
- `cdk_asset_hash`: `e4a87d2c057a5a43d35fd33ecca8e5c9f3dc97931899d6e69713ef8d4cea8928`
- runtime target: `python3.12`
- architecture: `arm64`

Live runtime in `eu-central-2`:

`stoa-api`:

- State: `Active`
- LastUpdateStatus: `Successful`
- LastModified: `2026-06-06T18:46:49.000+0000`
- CodeSha256: `IHtuyeT+hxuWa8CT7sycmCKVslWWbKzZe6qhiVjHp/k=`
- Runtime: `python3.12`
- Architecture: `arm64`

`stoa-weekly-report`:

- State: `Active`
- LastUpdateStatus: `Successful`
- LastModified: `2026-06-06T18:46:57.000+0000`
- CodeSha256: `IHtuyeT+hxuWa8CT7sycmCKVslWWbKzZe6qhiVjHp/k=`
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

Classification: expected Lambda code asset drift only from direct GitHub Lambda deploys. No table, bucket, GSI, IAM, Cognito, API Gateway, report bucket, or CloudFront infrastructure change.
