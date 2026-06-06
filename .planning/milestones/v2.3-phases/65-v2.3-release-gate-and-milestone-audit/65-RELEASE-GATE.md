# Phase 65 Release Gate

**Status:** Passed
**Recorded at:** 2026-06-06T22:37:33Z

## Commits

| Area | Commit SHA | Summary | Status |
|------|------------|---------|--------|
| Backend release evidence tooling | `e7f7832` | Phase 63 backend service, CLI, admin endpoints, and tests | Deployed via backend head |
| Frontend release evidence UI | `ed9e88d` | Phase 64 admin release evidence controls | Deployed |
| Backend production head | `14fd3ff381a97accc50efa080ae0f1aa5b06e8dc` | Phase 65 release-gate planning head deployed by backend workflow | Deployed |

## Deploy Evidence

### Backend

| Field | Value |
|-------|-------|
| Workflow | Deploy Backend |
| Run ID | `27075141371` |
| Run URL | `https://github.com/stoasystem/stoa-backend/actions/runs/27075141371` |
| Job ID | `79911122433` |
| Job name | Build Lambda package & Update function |
| Head SHA | `14fd3ff381a97accc50efa080ae0f1aa5b06e8dc` |
| Status | completed / success |
| Created | 2026-06-06T22:04:29Z |
| Completed | 2026-06-06T22:05:24Z |

### Frontend

| Field | Value |
|-------|-------|
| Workflow | Deploy Frontend |
| Run ID | `27075626379` |
| Run URL | `https://github.com/stoasystem/stoa-frontend/actions/runs/27075626379` |
| Job ID | `79912414886` |
| Job name | Build & Deploy to S3 + CloudFront |
| Head SHA | `ed9e88ddffce6832207f8c51d7a619601277162f` |
| Status | completed / success |
| Created | 2026-06-06T22:28:08Z |
| Completed | 2026-06-06T22:29:01Z |

### Frontend CI

| Field | Value |
|-------|-------|
| Workflow | Frontend CI |
| Run ID | `27075626376` |
| Run URL | `https://github.com/stoasystem/stoa-frontend/actions/runs/27075626376` |
| Job ID | `79912414904` |
| Job name | build |
| Head SHA | `ed9e88ddffce6832207f8c51d7a619601277162f` |
| Status | completed / success |
| Created | 2026-06-06T22:28:08Z |
| Completed | 2026-06-06T22:28:54Z |

## Local Quality Gates

Backend:

```text
.venv/bin/python -m ruff check src/stoa/services/release_evidence_service.py src/stoa/routers/admin.py scripts/release_evidence.py tests/test_release_evidence.py
```

Result: Passed, `All checks passed!`.

```text
.venv/bin/python -m pytest tests/test_release_evidence.py -q
```

Result: Passed, `8 passed in 0.55s`.

Frontend:

```text
npm run lint -- src/services/admin/adminApi.ts src/hooks/admin/useAdminReportOperations.ts src/pages/admin/ReportOperationsPage.tsx tests/e2e/admin-report-operations.spec.ts
```

Result: Passed after recreating local `test-results/` directory expected by the repo lint scan.

```text
npm run build
```

Result: Passed. Vite emitted the existing chunk-size warning for `index-yo2lI3E7.js`.

```text
npx playwright test tests/e2e/admin-report-operations.spec.ts
```

Result: Passed, `1 passed`.

## Lambda Manifest And Runtime

Local manifest:

| Field | Value |
|-------|-------|
| `source_git_sha` | `14fd3ff381a97accc50efa080ae0f1aa5b06e8dc` |
| `source_git_dirty` | `false` |
| `source_tree_hash` | `3c9aa0811f3a0015884f9bd8aa54bf68984711358d67275e6b161fd15ac34a12` |
| `cdk_asset_hash` | `06c18e4179b90ee0bc713d178084f8133148135fc1e20a5f5d420e0ac58f768b` |
| Runtime target | `python3.12` |
| Architecture | `arm64` |

Live runtime:

| Function | State | LastUpdateStatus | LastModified | CodeSha256 | Runtime | Architecture |
|----------|-------|------------------|--------------|------------|---------|--------------|
| `stoa-api` | Active | Successful | 2026-06-06T22:05:11.000+0000 | `1hNzuzAaBv/secW+SDpE7vE22uwlHInHF38KunDebV4=` | `python3.12` | `arm64` |
| `stoa-weekly-report` | Active | Successful | 2026-06-06T22:05:18.000+0000 | `1hNzuzAaBv/secW+SDpE7vE22uwlHInHF38KunDebV4=` | `python3.12` | `arm64` |

## CDK Diff

Command:

```text
CDK_OUTDIR=/private/tmp/stoa_phase65_cdk_out uv run cdk diff --profile stoa-prod-admin
```

Result: Passed with one expected stack difference.

Classification:

- `StoaAuthStack`, `StoaDatabaseStack`, `StoaStorageStack`, `StoaNotificationStack`, `StoaAiStack`, `StoaMonitoringStack`, and `StoaFrontendStack`: no differences.
- `StoaApiStack`: Lambda `Code.S3Key` changes only for `StoaApiFunction` and `StoaWeeklyReportFunction`.
- No DynamoDB table, GSI, S3 bucket, IAM expansion, Cognito resource, API Gateway route, CloudFront, or public artifact path change.
- Lambda code asset drift is expected because the backend GitHub deploy updates Lambda code directly from the deploy workflow package.

## Release Evidence Validation

| Check | Status | Evidence |
|-------|--------|----------|
| Evidence schema validation | Passed | `scripts/release_evidence.py validate --input /private/tmp/stoa_phase65_release_bundle.json` returned `status: passed`, no missing fields, no privacy violations. |
| Redaction denylist | Passed | Valid bundle privacy result `passed: true`, `violation_count: 0`. |
| Missing field handling | Passed | Bad bundle without `frontend` and with `json_s3_key` exited `2`, returned `status: failed`, `missing_required_fields: ["frontend"]`, and two privacy violations. |
| Safe-fixture status schema | Passed | CLI fixture status for `stoa-safe-fixture-v2-2-rollback-2026-06-06` returned `approved: true`, `status: ready`, `current: original`, `privacy.passed: true`. |
| Mutation refusal | Passed | `scripts/release_evidence.py check-mutation` returned `allowed: false` with missing fixture, missing mode, and not mutation-ready reasons. |
| Existing fixture mutation harness refusal | Passed | `node scripts/report_artifact_safe_fixture_smoke.mjs` without approval flags exited `2`, `refused: true`, `mutationAttempted: false`, and no requests. |
