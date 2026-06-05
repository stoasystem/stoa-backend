# v1.8 Final Milestone Audit

**Milestone:** v1.8 Incident Generation Retry Jobs
**Date:** 2026-06-05
**Status:** Passed - ready to archive

## Original Intent

Promote the highest-value deferred recovery expansion from v1.7: incident-wide `generation_failed` retry through bounded async jobs using the existing recovery job, audit, and weekly Lambda infrastructure.

## Delivered Evidence

| Requirement | Status | Evidence |
|-------------|--------|----------|
| GENJOB-01 | Complete | Phase 42/43 define and implement generation retry preview with bounded filters, metadata-only target samples, and operation-bound preview tokens. |
| GENJOB-02 | Complete | Phase 43 adds creation of `retry_generation` recovery jobs with stable target snapshots, audit events, and weekly worker invocation. |
| GENJOB-03 | Complete | Phase 43 worker routing executes `report_recovery_retry_generation` through existing single-report retry service and updates job counters/results. |
| GENJOB-04 | Complete | Phase 43 tests and Phase 45 live checks prove admin-only access, no private artifact exposure, and audit-linked job operations. |
| GENJOB-05 | Complete | Frontend commit `2bfa01b3826b5d76eb0f347175f098b60b96558c` adds resend/generation retry job mode selection and Playwright coverage. |
| GENJOB-06 | Complete | `45-RELEASE-GATE.md` and `45-LIVE-VERIFICATION.md` capture build, deploy, CDK, API, and production read-only browser smoke evidence. |

## Implementation Evidence

Backend:

- Commit `462b17f62540e257bc506c66c6aa6acfab106d93` added async generation retry jobs and v1.8 planning evidence.
- Deploy run `27011890471`: success.
- Lambda functions `stoa-api` and `stoa-weekly-report` are `Active` with `LastUpdateStatus=Successful`.
- Tests: `188 passed`.
- Focused Ruff gate: passed.
- Lambda dist manifest: `source_git_dirty=false`, `source_tree_hash=daba911cb30f...`.

Frontend:

- Commit `2bfa01b3826b5d76eb0f347175f098b60b96558c` added generation retry recovery UI.
- Deploy run `27011890698`: success.
- CloudFront invalidation `I7L1OJG03YRK911CCZKE9UU81U`: completed.
- Lint/build/e2e: passed.
- Production bundle contains `Retry generation` and `recovery-jobs/retry-generation`.

Live verification:

- API login request ID: `efDE2iF35icENGw=`.
- Authenticated generation-failed ops request ID: `efDFfiGuZicENGw=`.
- Browser recovery jobs request ID: `efDFwiHBZicENGw=`.
- Browser smoke final URL: `https://app.stoaedu.ch/admin/report-operations`.
- Browser smoke `retryGenerationVisible=true`.
- Browser smoke privacy hits: none.
- Browser smoke production mutation: none.

## Residual Risks

- CDK diff still shows Lambda code asset S3Key drift because backend deploys update Lambda code directly through GitHub Actions instead of CloudFormation asset deployment. No resource, permission, environment, DynamoDB, Cognito, S3, API Gateway, orchestration, or GSI drift was found.
- Production smoke is intentionally read-only. Mutation paths are covered by local API/worker/frontend tests and deploy evidence, not by creating a production retry job.
- Existing Lambda-based worker orchestration remains the MVP. Step Functions/SQS/dedicated worker infrastructure should be revisited only if operational evidence shows timeouts, contention, or retry coordination issues.
- Operators must continue using bounded filters and preview before creating generation retry jobs.

## Deferred Follow-up

Future requirements, not part of v1.8:

- Resume failed/skipped/refused recovery subsets from a prior job.
- Support ticket or incident evidence package integration.
- Step Functions/SQS or dedicated worker orchestration if existing Lambda flow becomes insufficient.
- Compliance-grade WORM audit storage.
- Report editing.
- PDF generation.
- Multilingual delivery expansion.
- Billing, analytics, and broader admin operations expansion.

## Archive Readiness

v1.8 is ready to archive because:

- All 4 phases are complete.
- All 6 v1.8 requirements are complete.
- Backend and frontend deploy evidence is recorded.
- Lambda runtime and manifest evidence is recorded.
- CDK diff evidence is classified.
- Production API and browser smoke passed without mutation or private artifact exposure.
- Residual risks and future requirements are explicitly recorded.

