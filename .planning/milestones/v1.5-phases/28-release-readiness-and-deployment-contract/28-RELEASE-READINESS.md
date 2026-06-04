---
phase: 28
phase_name: Release Readiness and Deployment Contract
status: ready
created: 2026-06-04
---

# Phase 28 Release Readiness Contract

## Release Scope

This contract defines the evidence and stop conditions required before v1.5 performs production report recovery deployment verification and mutation smoke.

In scope:

- Backend report operations release readiness for `stoa-api` and `stoa-weekly-report`.
- Frontend report operations UI release readiness for `https://app.stoaedu.ch/admin/report-operations`.
- Infrastructure/CDK diff classification before production mutation smoke.
- Rollback entry points for backend Lambda code, frontend assets, and unexpected infra drift.
- Mutation Safety Gate for safe non-customer recovery smoke targets.

Out of scope for Phase 28:

- Running frontend deployment.
- Running backend deployment.
- Invoking authenticated admin report operations APIs.
- Running production `generation_failed` retry, `email_failed` resend, or selected bulk resend.

## Repository And Commit Ledger

| Repository | Path | Branch check | SHA evidence |
|------------|------|--------------|--------------|
| Backend | `/Users/zhdeng/stoa-backend` | `git status --short --branch` | `git rev-parse HEAD` |
| Frontend | `/Users/zhdeng/stoa-frontend` | `git status --short --branch` | `git rev-parse HEAD` |
| Infrastructure/CDK | `/Users/zhdeng/stoa-infra` | `git status --short --branch` | `git rev-parse HEAD` |

Before Phase 29 or Phase 30 starts, each repository must be clean or the active uncommitted changes must be explicitly named in the phase verification record.

## Production Environment Contract

- AWS profile: stoa
- AWS region: eu-central-2
- API base URL: `https://api.stoaedu.ch`
- Frontend app URL: `https://app.stoaedu.ch`
- Report operations route: `https://app.stoaedu.ch/admin/report-operations`
- API Lambda: `stoa-api`
- Weekly report Lambda: `stoa-weekly-report`
- Reports bucket: `stoa-reports-562923011260`
- Required Lambda env: `S3_REPORTS_BUCKET=stoa-reports-562923011260`
- Active CDK deployment context: `--context env=dev`, unless Phase 29 or Phase 30 records a newer deployment context with evidence.

## Deployment Commands

### Backend Readiness

Run from `/Users/zhdeng/stoa-backend`:

- `git status --short --branch`
- `git rev-parse HEAD`
- `uv run pytest tests/test_admin_report_ops.py tests/test_parent_children.py`
- `uv run ruff check`

Backend deploy workflow evidence:

- GitHub Actions workflow: `.github/workflows/deploy.yml`
- Deploy role: `arn:aws:iam::562923011260:role/stoa-github-backend-deploy`
- Package update loop targets both `stoa-api` and `stoa-weekly-report`.
- Preflight must prove `lambda:GetFunctionConfiguration` is available for both Lambdas before code update.

Post-deploy Lambda checks:

- `aws lambda get-function-configuration --function-name stoa-api --region eu-central-2 --profile stoa`
- `aws lambda get-function-configuration --function-name stoa-weekly-report --region eu-central-2 --profile stoa`

Expected Lambda evidence:

- `State=Active`
- `LastUpdateStatus=Successful`
- `S3_REPORTS_BUCKET=stoa-reports-562923011260`

### Frontend Readiness

Run from `/Users/zhdeng/stoa-frontend`:

- `git status --short --branch`
- `git rev-parse HEAD`
- `npm run build`
- `npm run lint`
- `npx playwright test tests/e2e/admin-report-operations.spec.ts`

Frontend deploy workflow evidence:

- GitHub Actions workflow: `.github/workflows/deploy.yml`
- Production build env includes `VITE_API_MODE=production`.
- Production build env includes `VITE_API_BASE_URL=https://api.stoaedu.ch`.
- Production build env includes `VITE_ENABLE_DEMO_API=false`.
- Production build env includes `VITE_SHOW_DEMO_ACCOUNTS=false`, `VITE_SHOW_DEMO_BADGES=false`, and `VITE_SHOW_DEMO_SURFACES=false`.
- Deploy role: `arn:aws:iam::562923011260:role/stoa-github-frontend-deploy`
- Workflow syncs static assets to S3 and invalidates CloudFront cache.

Post-deploy frontend checks:

- `curl -I https://app.stoaedu.ch/admin/report-operations`
- `curl -s https://app.stoaedu.ch/admin/report-operations | head`
- Browser check with admin authentication during Phase 29.

Expected frontend evidence:

- `https://app.stoaedu.ch/admin/report-operations` serves HTTP 200.
- The route loads the deployed SPA bundle.
- Asset timestamp/hash/cache evidence is recorded.
- The UI uses production API config and no report-ops demo fallback.
- The UI has no direct frontend S3 fetch path.

### Infrastructure/CDK Readiness

Run from `/Users/zhdeng/stoa-infra`:

- `git status --short --branch`
- `git rev-parse HEAD`
- `uv run cdk diff --all --profile stoa --context env=dev`

If CDK prints `Unknown option(s): --all. These will be ignored`, record it as a CLI compatibility warning and still classify the diff that follows.

## Expected Evidence

Each live verification phase must record:

- Backend commit SHA.
- Frontend commit SHA.
- Infra commit SHA.
- Deployment timestamp.
- API URL used.
- Frontend route response.
- Frontend asset/cache timestamp or hash.
- `stoa-api` Lambda `State=Active`.
- `stoa-api` Lambda `LastUpdateStatus=Successful`.
- `stoa-api` Lambda `S3_REPORTS_BUCKET=stoa-reports-562923011260`.
- `stoa-weekly-report` Lambda `State=Active`.
- `stoa-weekly-report` Lambda `LastUpdateStatus=Successful`.
- `stoa-weekly-report` Lambda `S3_REPORTS_BUCKET=stoa-reports-562923011260`.
- CDK diff classification.
- Any warning about unsupported local Node/CDK versions.

## CDK Diff Classification Policy

| Diff category | Classification | Action |
|---------------|----------------|--------|
| Lambda `Code.S3Key` asset hash only for `stoa-api` or `stoa-weekly-report` | Expected code asset drift | Allowed if paired with intended backend deploy evidence. |
| Frontend asset/cache deployment evidence only | Expected frontend deploy drift | Allowed if paired with intended frontend deploy evidence. |
| IAM policy changes | Unexpected infrastructure drift | Block Phase 31 mutation smoke until reviewed. |
| S3 bucket policy or bucket replacement changes | Unexpected infrastructure drift | Block Phase 31 mutation smoke until reviewed. |
| API Gateway route/domain changes | Unexpected infrastructure drift | Block Phase 31 mutation smoke until reviewed. |
| DynamoDB table or GSI changes | Unexpected infrastructure drift | Block Phase 31 mutation smoke until reviewed. |
| Report bucket env var removal or rename | Blocking runtime drift | Block Phase 29-31 until fixed. |
| Lambda state not `Active` or update status not `Successful` | Blocking deployment state | Block Phase 29-31 until fixed. |

CDK diff evidence must distinguish expected Lambda code asset hash changes from infrastructure or IAM drift.

## Rollback Entry Points

### Backend Lambda rollback

- Roll back by re-running the backend deploy workflow from the last known-good backend commit SHA.
- If using direct AWS CLI rollback, update both `stoa-api` and `stoa-weekly-report` with the same known-good `lambda.zip`, then wait for both functions to reach `LastUpdateStatus=Successful`.
- Re-check `S3_REPORTS_BUCKET=stoa-reports-562923011260` after rollback.

### Frontend asset rollback

- Roll back by re-running the frontend deploy workflow from the last known-good frontend commit SHA.
- Confirm S3 sync completes and CloudFront invalidation is issued.
- Re-check `https://app.stoaedu.ch/admin/report-operations` after invalidation.

### Infra rollback

- Do not deploy unexpected infra drift as part of v1.5 live smoke.
- If an infra deploy causes unexpected drift, stop live mutation smoke and restore the last known-good infra commit through CDK deploy after reviewing the affected stack.
- Re-run CDK diff after rollback and record the result.

## Stop Conditions

Stop Phase 29-31 progression if any of these conditions are true:

- Unexpected IAM drift appears in CDK diff.
- Unexpected bucket drift appears in CDK diff.
- Unexpected API route drift appears in CDK diff.
- Unexpected DynamoDB drift appears in CDK diff.
- Unexpected policy drift appears in CDK diff.
- `stoa-api` is not `State=Active`.
- `stoa-api` does not have `LastUpdateStatus=Successful`.
- `stoa-weekly-report` is not `State=Active`.
- `stoa-weekly-report` does not have `LastUpdateStatus=Successful`.
- Either Lambda lacks `S3_REPORTS_BUCKET=stoa-reports-562923011260`.
- Frontend `/admin/report-operations` serves stale assets after deployment.
- Safe smoke target criteria are incomplete.

## Mutation Safety Gate

No live recovery mutation may run until Phase 31 records a safe smoke target with all of these fields:

| Field | Required value |
|-------|----------------|
| Parent ID | Explicit non-customer parent identifier |
| Student ID | Explicit non-customer student identifier |
| Week start | ISO date for the target report week |
| Original status | `generation_failed` or `email_failed`, depending on action |
| Expected terminal status | Expected status after retry or resend |
| Cleanup/restore expectation | Exact final state after smoke |
| No-customer-PII confirmation | Explicit yes/no recorded before mutation |
| Artifact privacy expectation | No raw HTML/JSON, private S3 key, public URL, presigned URL, or direct S3 URL in API/UI output |

Blocked actions before this gate is complete:

- Production `generation_failed` retry.
- Production `email_failed` single resend.
- Production selected bulk resend.

## Phase 29 Handoff

Phase 29 should use this contract to verify frontend deployment:

- Confirm frontend SHA.
- Confirm production build env.
- Confirm route response and deployed asset/cache evidence.
- Confirm admin-authenticated UI renders against production API.
- Confirm no report ops demo fallback and no direct frontend S3 fetch.

## Phase 30 Handoff

Phase 30 should use this contract to verify backend deployment:

- Confirm backend SHA.
- Confirm Lambda update state for `stoa-api` and `stoa-weekly-report`.
- Confirm CDK diff classification.
- Confirm unauthenticated and non-admin report operations rejection.
- Confirm admin-authenticated list/detail metadata-only behavior.

## Phase 31 Handoff

Phase 31 may run live recovery mutation smoke only after:

- Phase 29 frontend deployment verification passes or records an accepted non-blocking UI limitation.
- Phase 30 backend live verification passes.
- Safe smoke target fields are complete.
- No stop condition is active.

---
*Phase 28 release readiness contract created 2026-06-04.*
