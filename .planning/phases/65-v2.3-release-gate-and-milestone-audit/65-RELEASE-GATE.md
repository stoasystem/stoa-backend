# Phase 65 Release Gate

**Status:** Planned
**Recorded at:** TBD

## Commits

| Area | Commit SHA | Summary | Status |
|------|------------|---------|--------|
| Backend release evidence tooling | TBD | Phase 63 implementation | Pending |
| Frontend release evidence UI | TBD | Phase 64 implementation | Pending |
| Phase 65 evidence docs | TBD | Release gate docs | Pending |

## Deploy Evidence

### Backend

| Field | Value |
|-------|-------|
| Workflow | Deploy Backend |
| Run ID | TBD |
| Run URL | TBD |
| Job ID | TBD |
| Head SHA | TBD |
| Status | Pending |
| Created | TBD |
| Completed | TBD |

### Frontend

| Field | Value |
|-------|-------|
| Workflow | Deploy Frontend |
| Run ID | TBD |
| Run URL | TBD |
| Job ID | TBD |
| Head SHA | TBD |
| Status | Pending |
| Created | TBD |
| Completed | TBD |

### Frontend CI

| Field | Value |
|-------|-------|
| Workflow | Frontend CI |
| Run ID | TBD |
| Run URL | TBD |
| Job ID | TBD |
| Head SHA | TBD |
| Status | Pending |
| Created | TBD |
| Completed | TBD |

## Local Quality Gates

Backend:

```text
.venv/bin/python -m ruff check src/stoa/services/release_evidence_service.py src/stoa/routers/admin.py scripts/release_evidence.py tests/test_release_evidence.py
```

Result: Pending.

```text
.venv/bin/python -m pytest tests/test_release_evidence.py -q
```

Result: Pending.

Frontend:

```text
npm run lint -- src/services/admin/adminApi.ts src/hooks/admin/useAdminReportOperations.ts src/pages/admin/ReportOperationsPage.tsx tests/e2e/admin-report-operations.spec.ts
```

Result: Pending.

```text
npm run build
```

Result: Pending.

```text
npx playwright test tests/e2e/admin-report-operations.spec.ts
```

Result: Pending.

## Lambda Manifest And Runtime

Local manifest:

| Field | Value |
|-------|-------|
| `source_git_sha` | TBD |
| `source_tree_hash` | TBD |
| `cdk_asset_hash` | TBD |
| Runtime target | `python3.12` expected |
| Architecture | `arm64` expected |

Live runtime:

| Function | State | LastUpdateStatus | LastModified | CodeSha256 | Runtime | Architecture |
|----------|-------|------------------|--------------|------------|---------|--------------|
| `stoa-api` | TBD | TBD | TBD | TBD | TBD | TBD |
| `stoa-weekly-report` | TBD | TBD | TBD | TBD | TBD | TBD |

## CDK Diff

Command:

```text
uv run cdk diff --profile stoa-prod-admin
```

Result: Pending.

Expected classification:

- No DynamoDB table, GSI, S3 bucket, IAM expansion, Cognito resource, API Gateway route, CloudFront, or public artifact path change.
- Lambda code asset drift may be expected if direct GitHub Lambda deploys updated code outside CDK asset deployment.

## Release Evidence Validation

| Check | Status | Evidence |
|-------|--------|----------|
| Evidence schema validation | Pending | TBD |
| Redaction denylist | Pending | TBD |
| Missing field handling | Pending | TBD |
| Safe-fixture status schema | Pending | TBD |
| Mutation refusal | Pending | TBD |
