# Phase 37 Release Gate Evidence

**Date:** 2026-06-05
**Milestone:** v1.6 Report Recovery Operations Hardening
**Status:** Passed

## Deployment Evidence

### Backend

| Field | Value |
|-------|-------|
| Repository | `stoasystem/stoa-backend` |
| Branch | `main` |
| Deploy run | `26983049612` |
| Commit | `7aeb6d4a369796b1244481373c52a0449caacab7` |
| Display title | `ci: upgrade GitHub Actions runtime actions` |
| Result | Success |
| Completed | `2026-06-04T22:21:17Z` |

Backend deploy job evidence:

- Checkout succeeded.
- Python 3.12 setup succeeded.
- Lambda deployment package built.
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
| Deploy run | `26983049968` |
| Commit | `b8af433d7dc6f598fef1c142b960cd504c17b2f4` |
| Display title | `ci: upgrade GitHub Actions runtime actions` |
| Result | Success |
| Completed | `2026-06-04T22:21:06Z` |

Frontend deploy job evidence:

- Checkout succeeded.
- Node.js 20 setup succeeded.
- `npm ci` succeeded.
- `npm run lint` succeeded.
- Production build succeeded with `VITE_API_BASE_URL=https://api.stoaedu.ch`.
- S3 sync succeeded.
- `index.html` uploaded with no-cache headers.
- CloudFront invalidation succeeded.

## Lambda Runtime Evidence

Captured 2026-06-05.

| Function | State | LastUpdateStatus | Runtime | Arch | LastModified | CodeSha256 |
|----------|-------|------------------|---------|------|--------------|------------|
| `stoa-api` | Active | Successful | python3.12 | arm64 | `2026-06-04T22:21:01.000+0000` | `xP1TYqxW02AQUo0HN/IZ3rP7rH7Iu4YYLZGYncasxjw=` |
| `stoa-weekly-report` | Active | Successful | python3.12 | arm64 | `2026-06-04T22:21:09.000+0000` | `xP1TYqxW02AQUo0HN/IZ3rP7rH7Iu4YYLZGYncasxjw=` |

Required environment evidence:

- `stoa-api` has `WEEKLY_REPORT_FUNCTION_NAME=stoa-weekly-report`.
- Both functions have `ENVIRONMENT=production`.
- Both functions point to `DYNAMODB_TABLE_NAME=stoa-main`.
- Both functions point to `S3_REPORTS_BUCKET=stoa-reports-562923011260`.
- Both functions point to Cognito user pool `eu-central-2_Ss93YQzjJ`.

## Lambda Dist Guard Evidence

Command:

```bash
python scripts/build_lambda_dist.py --verify-only
```

Result:

```text
Lambda dist verified: sha=42ec78fa8004f3754051295c028581ccb8b4240a source_tree_hash=5fca464ec6fd
```

Notes:

- Local dist verification passed.
- The latest production backend source-of-truth is the GitHub deploy run from clean checkout, not the local dirty manifest SHA.
- The deterministic `cdk_asset_hash` ignores build timestamp and protects CDK asset drift from meaningless manifest-time changes.

## CDK Diff Evidence

Command:

```bash
AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 uv run cdk diff StoaApiStack --context env=dev
```

Result:

```text
Stack StoaAuthStack
There were no differences

Stack StoaDatabaseStack
There were no differences

Stack StoaStorageStack
There were no differences

Stack StoaNotificationStack
There were no differences

Stack StoaApiStack
There were no differences

Number of stacks with differences: 0
```

Known warning:

- CDK/JSII printed the existing untested Node v26 warning.
- The warning did not block synth/diff and does not represent stack drift.

## Local Quality Gate

```bash
uv run pytest -q
```

Result:

```text
177 passed in 1.34s
```

```bash
uv run ruff check scripts/provision_production_admin.py tests/test_provision_production_admin.py
```

Result:

```text
All checks passed!
```

```bash
git diff --check
```

Result: passed.

## Gate Decision

v1.6 release gate passed.

Residual follow-up:

- Rotate/own the production admin credential per STOA policy.
- Keep production browser smoke read-only unless a named safe fixture and explicit approval path are defined.
- Treat incident-wide generation retry, stronger orchestration, WORM audit storage, export/ticket integration, and report editing as future work.
