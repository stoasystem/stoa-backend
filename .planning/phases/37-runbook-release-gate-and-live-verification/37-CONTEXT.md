# Phase 37: Runbook, Release Gate, And Live Verification - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 37 closes v1.6 by turning the shipped recovery hardening work into operator-ready procedures and release evidence. It covers async resend job operations, audit lookup, cancellation, stop conditions, stalled jobs, observability, Lambda package provenance, CDK diff/deploy evidence, production read-only browser smoke, and the final milestone audit.

This phase is documentation and verification only. It does not add new AWS resources, change recovery behavior, run production recovery mutations, or expand the recovery product surface.
</domain>

<decisions>
## Implementation Decisions

- Use the v1.5 runbook as the base and extend it for v1.6 async jobs and append-only audit evidence.
- Treat Phase 36 production browser smoke evidence as the browser proof for OPS-03.
- Use GitHub deploy runs plus Lambda CodeSha/configuration as the production deployment evidence.
- Use CDK diff with dependency stacks as the clean infrastructure evidence.
- Keep production mutation browser smoke out of scope; v1.6 browser verification remains read-only.
- Carry credential ownership/rotation for `stoa/production/admin/stoaedu.ad@gmail.com` as an operational residual risk.
</decisions>

<code_context>
## Existing Code Insights

- Backend deploy workflow builds `lambda.zip`, verifies `dist/.stoa-build-manifest.json`, dry-runs updates, updates both `stoa-api` and `stoa-weekly-report`, and waits for update completion.
- Frontend deploy workflow builds production config for `https://api.stoaedu.ch`, syncs S3, uploads no-cache `index.html`, and invalidates CloudFront.
- `scripts/build_lambda_dist.py` verifies runtime, platform, architecture, source tree hash, dependency hash, handler inventory, and deterministic `cdk_asset_hash`.
- `scripts/provision_production_admin.py` provisions the long-lived production admin account across Cognito and DynamoDB.
</code_context>

<specifics>
## Specific Evidence Available

- Backend deploy run `26983049612`, commit `7aeb6d4a369796b1244481373c52a0449caacab7`, success.
- Frontend deploy run `26983049968`, commit `b8af433d7dc6f598fef1c142b960cd504c17b2f4`, success.
- Phase 36 production browser smoke at `2026-06-04T23:51:36Z`, route loaded, GET admin APIs returned 200, no mutations, no private markers.
- Lambda `stoa-api` and `stoa-weekly-report` are Active and LastUpdateStatus Successful with shared CodeSha `xP1TYqxW02AQUo0HN/IZ3rP7rH7Iu4YYLZGYncasxjw=`.
- API health returned 200 with request ID `eddxOg695icEMLA=`.
- Unauthenticated recovery jobs endpoint returned 401 with request ID `eddxOiDjZicEMog=`.
- CDK diff for `StoaApiStack` and dependency stacks reported 0 stacks with differences.
- `uv run pytest -q` passed: 177 tests.
- `uv run ruff check scripts/provision_production_admin.py tests/test_provision_production_admin.py` passed.
- `git diff --check` passed.
</specifics>

<deferred>
## Deferred Ideas

- Incident-wide `generation_failed` retry.
- Resume failed/skipped subsets as a new job.
- Metadata-only export of jobs, targets, and audit evidence.
- Support ticket integration.
- Step Functions, SQS, dedicated worker Lambda, new table, new bucket, or new GSI.
- Compliance-grade WORM audit storage.
- Report editing, PDF, multilingual delivery, billing, analytics, and broad admin redesign.
</deferred>
