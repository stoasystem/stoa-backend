# Phase 33: Recovery Contract, CDK Readiness, And Dist Guard - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

This phase establishes the v1.6 recovery contract and deployment guard before any async recovery backend work starts. It must define how operators and implementers should reason about job state, audit guarantees, target snapshots, stop conditions, cancellation, privacy, and Lambda package provenance. It also must prove the existing CDK/Lambda packaging path can fail fast when `../stoa-backend/dist` is missing or stale.

</domain>

<decisions>
## Implementation Decisions

### Recovery Contract
- Treat v1.6 async recovery as a bounded, operator-confirmed `resend_email` MVP; incident-wide generation retry remains deferred.
- Define immutable audit as application-enforced append-only DynamoDB evidence, not legal WORM storage.
- Keep recovery metadata-only and backend-mediated; job/audit/verification surfaces must not expose private S3 keys or raw artifacts.
- Model cancellation as cooperative: future target attempts stop, completed sends are not rolled back.

### CDK Readiness
- Reuse existing `stoa-api`, `stoa-weekly-report`, `stoa-main`, SES, S3, Cognito, and Playwright stack for v1.6 by default.
- Do not add Step Functions, SQS, new tables, new buckets, new Lambdas, or new GSIs in Phase 33.
- Add a scoped CDK synth-time guard before Lambda assets are read.
- Leave future async worker invoke permission to Phase 35, where the backend job endpoint and worker event branch will be implemented.

### Lambda Dist Guard
- Backend direct deploy and infra CDK deploy must use one shared backend build script.
- The build script must write a manifest with source/dependency/runtime/handler provenance.
- CDK must verify the manifest before synth/diff/deploy and fail fast unless `ALLOW_STALE_LAMBDA_DIST=1` is explicitly set.
- CDK asset hashing should use a deterministic source/dependency hash so audit timestamp changes do not create meaningless Lambda asset drift.

### the agent's Discretion
Implementation details are at the agent's discretion where they preserve the requirements and existing repo conventions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Backend deploy workflow already builds `dist` and `lambda.zip` for direct Lambda updates.
- Infra deploy workflow already checks out `stoa-backend` next to `stoa-infra` and builds `../stoa-backend/dist` before CDK diff/deploy.
- `stacks/api_stack.py` creates both `stoa-api` and `stoa-weekly-report` from the same `../stoa-backend/dist` asset.
- Existing weekly report handler entry points are `stoa.main.handler` and `stoa.jobs.weekly_reports.handler`.

### Established Patterns
- Backend tests use focused pytest files and ruff checks.
- Infra uses simple Python CDK stack modules with standard library helpers acceptable for synth-time validation.
- Build artifacts under `dist/` are intentionally gitignored.

### Integration Points
- Backend: `.github/workflows/deploy.yml`, `scripts/build_lambda_dist.py`, `tests/test_lambda_dist_build.py`.
- Infra: `.github/workflows/deploy.yml`, `stacks/api_stack.py`, `stacks/lambda_dist_guard.py`.
- Planning: Phase 33 requirements `GUARD-01` through `GUARD-05`.

</code_context>

<specifics>
## Specific Ideas

Use a deterministic `cdk_asset_hash` in the manifest so CDK diff only reflects real source/dependency/runtime changes, not manifest build timestamps.

</specifics>

<deferred>
## Deferred Ideas

- Async worker Lambda invoke permission belongs in Phase 35 with the backend job implementation.
- Append-only audit implementation belongs in Phase 34.
- Production browser smoke belongs in Phase 36.
- Live deployment and final runbook updates belong in Phase 37.

</deferred>
