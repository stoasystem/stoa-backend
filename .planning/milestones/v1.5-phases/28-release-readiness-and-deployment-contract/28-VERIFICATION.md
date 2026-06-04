---
phase: 28
phase_name: Release Readiness and Deployment Contract
status: passed
verified: 2026-06-04
requirements:
  - REL-01
  - REL-02
  - REL-03
  - REL-04
---

# Phase 28 Verification: Release Readiness and Deployment Contract

## Verdict

`passed`

Phase 28 produced the release readiness contract required before v1.5 production deployment verification and recovery mutation smoke.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REL-01 | complete | `28-RELEASE-READINESS.md` defines backend readiness commands, backend deploy workflow evidence, Lambda configuration checks for `stoa-api` and `stoa-weekly-report`, expected Lambda `State=Active`, `LastUpdateStatus=Successful`, and `S3_REPORTS_BUCKET=stoa-reports-562923011260`, plus CDK diff classification. |
| REL-02 | complete | `28-RELEASE-READINESS.md` defines frontend readiness commands, production build env expectations, `https://app.stoaedu.ch/admin/report-operations` checks, frontend asset/cache evidence, no report-ops demo fallback, and no direct frontend S3 fetch expectations. |
| REL-03 | complete | `28-RELEASE-READINESS.md` defines expected evidence for backend/frontend/infra SHAs, deployment timestamp, API URL, frontend route response, frontend asset/cache timestamp or hash, Lambda states, Lambda env, and CDK diff classification. |
| REL-04 | complete | `28-RELEASE-READINESS.md` defines backend Lambda rollback, frontend asset rollback, infra rollback, stop conditions, and a blocking Mutation Safety Gate before live recovery mutation smoke. |

## Contract Assertions

- Repository ledger includes `/Users/zhdeng/stoa-backend`, `/Users/zhdeng/stoa-frontend`, and `/Users/zhdeng/stoa-infra`.
- Production environment contract includes `AWS profile: stoa` and `AWS region: eu-central-2`.
- Lambda contract includes `stoa-api`, `stoa-weekly-report`, and `stoa-reports-562923011260`.
- Frontend route contract includes `https://app.stoaedu.ch/admin/report-operations`.
- Mutation Safety Gate requires parent ID, student ID, week start, original status, expected terminal status, cleanup/restore expectation, and no-customer-PII confirmation.
- CDK diff classification separates expected Lambda `Code.S3Key` drift from unexpected IAM, bucket, API route, DynamoDB, or policy drift.

## Automated Checks

- `git diff --check` - passed during Phase 28 execution.
- `rg -n "REL-01|REL-02|REL-03|REL-04|stoa-api|stoa-weekly-report|stoa-reports-562923011260|Mutation Safety Gate|CDK Diff Classification" .planning/phases/28-release-readiness-and-deployment-contract/28-RELEASE-READINESS.md` - passed during Phase 28 execution.

## Residual Risks

- Phase 28 does not prove live frontend deployment. That remains Phase 29.
- Phase 28 does not prove live backend deployment or authenticated API behavior. That remains Phase 30.
- Phase 28 does not identify or mutate a safe recovery smoke target. That remains Phase 31.
