# Phase 49 Release Gate Evidence

**Date:** 2026-06-05
**Milestone:** v1.9 Recovery Resume And Support Evidence Packages
**Status:** Passed

## Deployment Evidence

### Backend

| Field | Value |
|-------|-------|
| Repository | `stoasystem/stoa-backend` |
| Branch | `main` |
| Deploy run | `27013104304` |
| Commit | `235b5b4995d35bca2d676b2c3ed8d2b6023bbecc` |
| Display title | `feat: add recovery resume support` |
| Result | Success |
| Created | `2026-06-05T11:49:08Z` |
| Completed | `2026-06-05T11:50:10Z` |
| Job | `Build Lambda package & Update function` / `79721300510` |

### Frontend

| Field | Value |
|-------|-------|
| Repository | `stoasystem/stoa-frontend` |
| Branch | `main` |
| Deploy run | `27013104618` |
| Commit | `210a4c56cfbfc62d047e4d319e60c5ea3a8c6144` |
| Display title | `feat: add recovery resume UI` |
| Result | Success |
| Created | `2026-06-05T11:49:08Z` |
| Completed | `2026-06-05T11:50:00Z` |
| Job | `Build & Deploy to S3 + CloudFront` / `79721302413` |

CloudFront invalidation:

| Field | Value |
|-------|-------|
| Distribution | `E27CVAMQHDMW80` |
| Invalidation | `I6MYOYAL0R8D651HPFL2ZYI8UW` |
| Status | `Completed` |
| CreateTime | `2026-06-05T11:49:57.549000+00:00` |

Production bundle check:

- `https://app.stoaedu.ch/admin/report-operations` references `/assets/index-U9Kxb5mF.js`.
- Bundle contains `Preview resume`.
- Bundle contains `Start resume`.
- Bundle contains `Support package`.
- Bundle contains `resume/preview`.
- Bundle contains `support-package`.

## Lambda Runtime Evidence

| Function | State | LastUpdateStatus | Runtime | Arch | LastModified | CodeSha256 |
|----------|-------|------------------|---------|------|--------------|------------|
| `stoa-api` | Active | Successful | python3.12 | arm64 | `2026-06-05T11:49:55.000+0000` | `A5Paco0TPYgwhhiq7/AF5ZBAumOL7iKtfINz7jenllI=` |
| `stoa-weekly-report` | Active | Successful | python3.12 | arm64 | `2026-06-05T11:50:03.000+0000` | `A5Paco0TPYgwhhiq7/AF5ZBAumOL7iKtfINz7jenllI=` |

## Lambda Dist Manifest Evidence

```text
Lambda dist built: sha=235b5b4995d35bca2d676b2c3ed8d2b6023bbecc source_tree_hash=f724d0e3dcc5
Lambda dist verified: sha=235b5b4995d35bca2d676b2c3ed8d2b6023bbecc source_tree_hash=f724d0e3dcc5
```

Manifest highlights:

| Field | Value |
|-------|-------|
| `source_git_sha` | `235b5b4995d35bca2d676b2c3ed8d2b6023bbecc` |
| `source_git_dirty` | `false` |
| `source_tree_hash` | `f724d0e3dcc5203439e159be0dce7571b2dd78768c5c997dbb81226c4d7fe969` |
| `cdk_asset_hash` | `3a06718f42b2bd787818282ba2e3fba0141fb20668fd6c66cf12e9949d1112c0` |

## Local Quality Gate

Backend:

- `uv run pytest -q`: `191 passed in 1.39s`
- `uv run ruff check src/stoa/services/report_recovery_job_service.py src/stoa/services/report_recovery_evidence_service.py src/stoa/routers/admin.py tests/test_admin_report_ops.py`: passed
- `git diff --check`: passed

Frontend:

- `npm run lint -- --max-warnings=0`: passed
- `npm run build`: passed with existing Vite chunk warning
- `npx playwright test tests/e2e/admin-report-operations.spec.ts`: `1 passed (3.7s)`
- `git diff --check`: passed

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
- `StoaApiStack`: Lambda `Code.S3Key` asset diff only for `stoa-api` and `stoa-weekly-report`.

Classification:

- No DynamoDB, Cognito, S3, SES, IAM, environment variable, API Gateway, Step Functions, SQS, new Lambda, new table, new bucket, or new GSI change is required for v1.9.
- The only CDK diff is expected direct-Lambda-deploy code asset drift.
- No CDK deploy was performed.

## Gate Decision

v1.9 release gate passed.

