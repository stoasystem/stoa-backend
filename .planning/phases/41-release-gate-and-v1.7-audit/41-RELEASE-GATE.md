# Phase 41 Release Gate Evidence

**Date:** 2026-06-05
**Milestone:** v1.7 Recovery Evidence Export & Admin Credential Operations
**Status:** Passed

## Deployment Evidence

### Backend

| Field | Value |
|-------|-------|
| Repository | `stoasystem/stoa-backend` |
| Branch | `main` |
| Deploy run | `27006793949` |
| Commit | `0dd4d511f36e10e3910258bed5ee74e8e693f05a` |
| Display title | `docs: complete phase 40 export ui smoke` |
| Result | Success |
| Created | `2026-06-05T09:23:47Z` |
| Completed | `2026-06-05T09:24:40Z` |
| Job | `Build Lambda package & Update function` / `79700279119` |

Backend deploy job evidence:

- Checkout succeeded.
- Python 3.12 setup succeeded.
- Lambda deployment package built for linux arm64 wheels.
- Lambda dist provenance verification succeeded.
- Package summary printed manifest.
- AWS OIDC credentials configured.
- `update-function-code --dry-run` succeeded for `stoa-api` and `stoa-weekly-report`.
- Both Lambda functions were updated.
- `aws lambda wait function-updated` succeeded for both functions.

### Frontend

| Field | Value |
|-------|-------|
| Repository | `stoasystem/stoa-frontend` |
| Branch | `main` |
| Deploy run | `27006709864` |
| Commit | `12e2ab6f148447b3b59044de332a1908d1353c9a` |
| Display title | `feat: add recovery evidence export UI` |
| Result | Success |
| Created | `2026-06-05T09:21:59Z` |
| Completed | `2026-06-05T09:22:52Z` |
| Job | `Build & Deploy to S3 + CloudFront` / `79700000817` |

Frontend deploy job evidence:

- Checkout succeeded at commit `12e2ab6f148447b3b59044de332a1908d1353c9a`.
- Node.js 20 setup succeeded.
- `npm ci` succeeded.
- `npm run lint` succeeded.
- Production build succeeded with `VITE_API_BASE_URL=https://api.stoaedu.ch`.
- S3 static asset sync succeeded.
- `index.html` uploaded with no-cache headers.
- CloudFront invalidation created.

CloudFront invalidation:

| Field | Value |
|-------|-------|
| Distribution | `E27CVAMQHDMW80` |
| Invalidation | `I8M741ULIKSS7I1O22N15AZIA5` |
| Status | `Completed` |
| CreateTime | `2026-06-05T09:22:49.229000+00:00` |
| Paths | `/*` |

Production bundle check:

- `https://app.stoaedu.ch/admin/report-operations` references `/assets/index-B4cSya8v.js`.
- Bundle contains `Recovery evidence export`.
- Bundle contains `Export recent jobs`.
- Bundle contains `recovery-evidence`.
- Bundle contains `https://api.stoaedu.ch`.

## Lambda Runtime Evidence

Captured after backend deploy run `27006793949`.

| Function | State | LastUpdateStatus | Runtime | Arch | LastModified | CodeSha256 |
|----------|-------|------------------|---------|------|--------------|------------|
| `stoa-api` | Active | Successful | python3.12 | arm64 | `2026-06-05T09:24:27.000+0000` | `3v1gxkxB0iIyqiIFJILbTf9MFIcUC8r+fWGz1A3v6po=` |
| `stoa-weekly-report` | Active | Successful | python3.12 | arm64 | `2026-06-05T09:24:34.000+0000` | `3v1gxkxB0iIyqiIFJILbTf9MFIcUC8r+fWGz1A3v6po=` |

## Lambda Dist Manifest Evidence

Command:

```bash
python scripts/build_lambda_dist.py --zip lambda.zip
python scripts/build_lambda_dist.py --verify-only
python -m json.tool dist/.stoa-build-manifest.json
```

Result:

```text
Lambda dist built: sha=0dd4d511f36e10e3910258bed5ee74e8e693f05a source_tree_hash=ae12c2f437fb
Lambda dist verified: sha=0dd4d511f36e10e3910258bed5ee74e8e693f05a source_tree_hash=ae12c2f437fb
```

Manifest highlights:

| Field | Value |
|-------|-------|
| `source_git_sha` | `0dd4d511f36e10e3910258bed5ee74e8e693f05a` |
| `source_git_dirty` | `false` |
| `source_tree_hash` | `ae12c2f437fbb8d75733a7ac41ab596cd7c19b3da72fa57febef2539ced481b7` |
| `cdk_asset_hash` | `6bead4527b0d879d1cef8b398ea8d0d66fffd1bf53a249e8ce9e52f7aa33008f` |
| `runtime_target` | `python3.12` |
| `platform` | `manylinux2014_aarch64` |
| `architecture` | `arm64` |

## Local Quality Gate

Backend:

```bash
uv run pytest -q
```

Result: `183 passed in 1.41s`.

```bash
uv run ruff check src/stoa/routers/admin.py src/stoa/services/report_recovery_service.py src/stoa/services/report_recovery_evidence_service.py tests/test_admin_report_ops.py
```

Result: `All checks passed!`.

```bash
git diff --check
```

Result: passed.

Frontend:

```bash
npm run lint -- --max-warnings=0
```

Result: passed.

```bash
npm run build
```

Result: passed. Vite reported the existing large chunk warning.

```bash
npx playwright test tests/e2e/admin-report-operations.spec.ts
```

Result: `1 passed`.

```bash
git diff --check
```

Result: passed.

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

- No DynamoDB, Cognito, S3, SES, IAM, environment variable, or API Gateway infrastructure change is required for v1.7.
- The only CDK diff is expected Lambda code asset drift because the backend deploy workflow updates Lambda code directly from the GitHub-built zip rather than via CloudFormation asset S3 keys.
- No CDK deploy was performed for Phase 41.
- Follow-up: decide whether the backend deploy model should update CloudFormation asset state or whether code asset drift should remain accepted release-gate evidence.

Known warning:

- CDK/JSII printed the existing untested Node v26 warning.
- The warning did not block synth/diff.

## Gate Decision

v1.7 release gate passed.

The only residual release-gate item is the expected CDK Lambda code asset diff caused by direct Lambda deploys. It does not indicate infrastructure drift for tables, buckets, Cognito, IAM, API Gateway, or environment configuration.

