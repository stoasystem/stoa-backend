# Project Research Summary

**Project:** STOA Backend
**Domain:** Report recovery operations hardening for production admin tooling
**Milestone:** v1.6 Report Recovery Operations Hardening
**Researched:** 2026-06-04
**Confidence:** HIGH for reuse-first architecture and safety requirements; MEDIUM for final live execution caps until production volume, SES quota, and Lambda runtime behavior are validated.

## Executive Summary

STOA v1.6 is an operations-hardening milestone for weekly report recovery, not a product expansion milestone. The existing v1.5 platform already gives admins metadata-only report list/detail, single generation retry, single resend, selected bulk resend, production API smoke, and a runbook. v1.6 should make that platform safe for incident-wide recovery by adding durable async jobs, append-only audit evidence, real production admin browser smoke, and a deployment guard that prevents stale Lambda assets from being redeployed.

The recommended approach is reuse-first: keep FastAPI as the admin control plane, keep the existing DynamoDB single table for job/audit records, and use the existing `stoa-weekly-report` Lambda as the async recovery worker. Do not introduce Step Functions, SQS, a new table, a new bucket, a new Lambda, or new GSIs by default. The roadmap should first extract shared recovery services and define the job/audit contract, then build a bounded async resend job path, job/audit UI, production read-only browser smoke, and the Lambda `dist` provenance guard before any CDK deploy that touches Lambda assets.

The key risks are broad incident mutations without stable target snapshots, duplicate emails from missing conditional claims, audit logs that are only mutable report fields, private artifact leakage through new job/audit/smoke surfaces, authorization gaps on new admin endpoints, and CDK deployments packaging stale `stoa-backend/dist`. Mitigate these with explicit filters, preflight preview, required operator reason, durable target records, per-target eligibility rechecks, conditional claims, append-only audit writes, admin-only route tests, metadata-only response allowlists, read-only production smoke using a real admin session, and a build manifest verified before CDK diff/deploy.

## Key Findings

### Stack Additions And Reuse Decisions

v1.6 does not need new Python packages or new AWS services by default. The core implementation should extend existing dependencies and resources that already own report operations, report artifacts, SES delivery, Cognito admin authorization, and CDK-managed Lambda deployment.

**Core technologies:**
- FastAPI / Pydantic: admin job, audit, status, and cancellation APIs with explicit request/response models.
- Existing `stoa-api` Lambda: quick job creation, status reads, cancellation requests, and audit browsing; it must not process incident-wide recovery inline.
- Existing `stoa-weekly-report` Lambda: async recovery worker branch because it already has report generation, report artifact, Bedrock, SES, table, and 15-minute runtime context.
- Existing DynamoDB table `stoa-main`: job metadata, durable target snapshots, per-target results, and append-only audit rows using conditional writes.
- Existing React admin UI and Playwright frontend tests: extend `/admin/report-operations`; add production read-only browser smoke with a real admin session or approved storage state.
- Existing CDK `ApiStack`: inject worker function name, grant `stoa-api` scoped `lambda:InvokeFunction` on `stoa-weekly-report`, and enforce Lambda `dist` manifest verification before synth/diff/deploy.

**Critical version / provenance requirements:**
- Lambda packaging must target Python 3.12, ARM64, and Linux-compatible wheels as the current CDK runtime expects.
- `dist/.stoa-build-manifest.json` should record backend git SHA, source tree hash, requirements hash, Python/runtime target, platform, architecture, and build time.
- CDK and CI must fail fast when `dist` is missing, stale, or lacks expected handlers/modules. An emergency `ALLOW_STALE_LAMBDA_DIST=1` escape hatch is acceptable only if documented in the runbook.

### Feature Table Stakes

**Must have for v1.6:**
- Incident recovery job creation from explicit filters: operation type, week/status scope, optional parent/student scope, max bounds, and required reason.
- Preflight preview before mutation: eligible/refused/missing counts, filter snapshot, operation type, sample metadata, and no private artifact keys or raw content.
- Stable async job record: `queued`, `running`, `cancellation_requested`, `cancelled`, `completed`, `completed_with_failures`, and `failed` states with durable progress.
- Durable target snapshot: freeze target identifiers at job creation so progress and audit refer to a stable set.
- Per-target execution evidence: `success`, `refused`, `not_found`, `failed`, `skipped_cancelled`, and related redacted error fields.
- Bounded execution: max targets, page limits, time budget, failure caps, stop-on root-cause errors, conservative SES pacing, and Lambda remaining-time checks.
- Cooperative cancellation: stop future target attempts; do not imply rollback or interruption of in-flight SES/report generation side effects.
- Eligibility recheck and conditional claim at execution time: every target must be reread and atomically claimed before side effects.
- Immutable operational audit records: append-only events for job lifecycle, claims, refusals, successes, failures, cancellations, and existing single/bulk recovery actions.
- Admin-only audit browsing: report and job timelines exposed through metadata-only admin APIs/UI.
- Production admin browser smoke: real admin session, read-only by default, route/API/auth verification, and privacy marker assertions.
- Lambda dist rebuild guard: shared build script, deterministic manifest, CDK synth-time verification, CI enforcement, and runbook guidance.

**Should have if the table stakes are stable:**
- Dry-run export of target metadata for support/security review.
- Failure clustering by root cause to make stop/escalation decisions easier.
- Resume failed/skipped subset as a new audit-linked job attempt.
- Audit CSV download with metadata only.
- Smoke evidence artifacts that prove route/API/privacy behavior without retaining secrets.
- Dist guard error messages that name stale/missing files and the rebuild command.

**Explicitly defer beyond v1.6 MVP:**
- Step Functions, SQS, new tables, new buckets, new Lambdas, or new GSIs unless a phase proves existing Lambda/table access patterns cannot satisfy bounded jobs.
- Compliance-grade WORM audit storage such as S3 Object Lock unless legal/security explicitly requires it.
- Default production mutation browser smoke. Keep production smoke read-only unless a named non-customer fixture and explicit approval path exist.
- Incident-wide generation retry as the first async operation. Start with resend for `email_failed`; generation retry is slower, more expensive, and touches Bedrock/artifact rewrite paths.
- Support-ticket integrations, job templates, report editing, PDF generation, billing, analytics, multilingual expansion, or broad admin redesign.

### Architecture Plan

v1.6 should extend the existing report operations platform rather than creating a separate recovery subsystem. Move the current retry/resend logic out of `src/stoa/routers/admin.py` into shared recovery services, then have existing single-report endpoints and new async jobs call the same service functions. The API Lambda creates jobs, reads status, and requests cancellation; the weekly report Lambda processes bounded recovery work through a new event branch.

**Major components:**
1. `report_recovery_service.py` - shared single-target resend/retry eligibility, conditional claim, side effect execution, redacted result modeling, and audit writes.
2. `report_recovery_job_service.py` - job creation, target snapshotting, worker processing, counters, checkpoints, cancellation, stop conditions, and worker invocation.
3. Recovery repository helpers - DynamoDB job summary/list/result items, append-only audit events, conditional state transitions, and paginated result/audit reads.
4. `weekly_reports.handler` recovery branch - dispatch `{"job":"report_recovery_job","job_id":"..."}` to the worker without disturbing scheduled weekly reports or smoke branches.
5. Admin route extensions - `POST /admin/reports/recovery-jobs`, list/detail/results/cancel endpoints, and report/job audit endpoints under admin-only authorization.
6. Frontend `/admin/report-operations` extensions - jobs panel, job detail/progress/cancel/results, report audit panel, mocked e2e, and no-private-marker checks.
7. CDK/build guard - scoped invoke permissions, worker function env var, manifest-generating backend build script, and synth-time stale-dist verification.

**Recommended DynamoDB item families:**
- `PK=REPORT_RECOVERY_JOB#{job_id}`, `SK=SUMMARY` for canonical job state.
- `PK=REPORT_RECOVERY_JOBS`, `SK=CREATED#{requested_at}#{job_id}` for recent job listing without a new GSI.
- `PK=REPORT_RECOVERY_JOB#{job_id}`, `SK=TARGET#{...}` for durable target snapshot and per-target results.
- `PK=REPORT#{report_id}`, `SK=AUDIT#{event_at}#{event_id}` for report-local append-only audit evidence.
- Optional duplicated job-local audit rows under `PK=REPORT_RECOVERY_JOB#{job_id}`, `SK=AUDIT#{...}` when efficient job timelines are needed.

### Pitfalls And Watch-Outs

1. **Synchronous incident-wide recovery** - avoid route-handler loops over scans, sends, or generation. API requests create jobs and return `202`; the worker processes bounded targets.
2. **Moving target sets** - avoid processing live scan results directly. Snapshot target records at job creation, then revalidate each report before mutation.
3. **Duplicate sends or regeneration** - add conditional claims and idempotency keys before SES/report generation side effects. Treat duplicate async invocation as already-completed or refused, not another send.
4. **Mutable-only audit** - existing `last_operation*` report fields are triage metadata, not evidence. Add append-only audit rows with overwrite tests and no TTL.
5. **Overstated immutability** - DynamoDB conditional writes provide application-enforced append-only evidence, not legal WORM storage. Document that guarantee honestly unless WORM is explicitly required.
6. **Private artifact leakage** - job, audit, smoke, logs, traces, screenshots, and error messages must not expose `weekly-reports/`, `json_s3_key`, `html_s3_key`, `s3_key`, presigned URLs, public S3 URLs, raw HTML, or raw JSON.
7. **Authorization gaps** - every new job and audit endpoint needs unauthenticated, invalid-token, non-admin, and admin tests. Opaque job IDs must not bypass admin role checks.
8. **Misleading cancellation** - model cancellation as request/observed/terminal states. Cancellation stops future attempts; it does not roll back completed sends.
9. **Fake production smoke auth** - do not bypass Cognito or create temporary production admin accounts. Use an existing admin session or approved secret-backed credentials, and keep auth state out of repo/artifacts.
10. **Stale Lambda dist provenance** - a guard that only checks `dist/` exists is insufficient. Verify source/requirements hashes and handler inventory before CDK diff/deploy.

## Recommended MVP Scope

The v1.6 MVP should ship a safe, auditable async resend workflow before expanding to higher-risk recovery modes.

**Include in MVP:**
- Service extraction for existing single retry, single resend, and selected bulk resend.
- Append-only audit foundation that also covers existing v1.5 recovery actions.
- Async `resend_email` job for explicit `email_failed` week/status scope with preflight preview, required reason, target snapshot, strict caps, progress, cancellation, per-target results, and audit.
- Admin job/audit APIs and UI panels adjacent to existing `/admin/report-operations`.
- Production read-only admin browser smoke with real admin session/storage state and privacy assertions.
- Lambda `dist` build manifest and CDK/CI guard before any Lambda asset deploy.
- Runbook updates for job creation, stop conditions, audit lookup, browser smoke, and stale package remediation.

**Exclude from MVP unless validated during phase planning:**
- Async incident-wide generation retry.
- Self-invoking multi-hop continuation if conservative one-invocation caps are sufficient for initial resend jobs.
- New AWS resources or indexes.
- Compliance WORM storage.
- Production mutation browser smoke.
- Job templates, CSV export, ticket-system integration, analytics, or UI redesign.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 33: Recovery Contract, CDK Readiness, And Dist Guard

**Rationale:** v1.6 touches infrastructure and production recovery behavior. The roadmap should prove existing resources are enough, define immutability and privacy guarantees, and block stale Lambda assets before any CDK deploy that grants worker invocation permissions.

**Delivers:** Job/audit API contract, target snapshot model, state machine, caps/stop policy, immutability definition, privacy response contract, CDK evidence ledger, shared Lambda build manifest, and synth-time stale-dist verifier.

**Addresses:** CI/CD Lambda dist rebuild guard, no unnecessary AWS services, Lambda dist provenance risk, privacy/authorization contract.

**Avoids:** Premature Step Functions/SQS/new table, stale CDK asset deploys, audit immutability ambiguity, and broad endpoint design drift.

### Phase 34: Recovery Service Extraction And Audit Foundation

**Rationale:** Async jobs must reuse the same eligibility and side-effect paths as existing single-report operations. Audit must be present before new incident-wide work starts creating evidence.

**Delivers:** `report_recovery_service.py`, delegated existing retry/resend/bulk endpoints, conditional resend claim helper, append-only audit repository/writer, audit records for existing single retry/resend/selected bulk resend, overwrite/refusal/redaction tests, and admin-only audit read endpoints if feasible.

**Addresses:** Immutable audit table stakes, duplicate-send prevention, shared recovery behavior, authorization and metadata-only boundaries.

**Avoids:** Mutable-only audit, duplicated business logic, missing conditional claims, and raw artifact/error leakage.

### Phase 35: Async Resend Job Backend

**Rationale:** Incident-wide recovery needs durable job state, target snapshots, bounded worker execution, cancellation, and per-target results before any UI can safely expose it.

**Delivers:** Job create/list/detail/results/cancel APIs; target snapshot persistence; API Lambda async invoke of `stoa-weekly-report`; weekly Lambda recovery worker branch; bounded processing; stop conditions; cooperative cancellation; per-target results; immutable job/target audit events; focused backend and infra tests.

**Addresses:** Incident-wide async recovery jobs, operator-visible progress/results, execution-time eligibility recheck, cancellation semantics, and SES/Lambda blast-radius controls.

**Avoids:** Synchronous incident recovery, moving target sets, duplicate async side effects, stalled jobs without evidence, and misleading progress.

### Phase 36: Admin Job/Audit UI And Production Browser Smoke

**Rationale:** The UI depends on stable backend job and audit contracts. Production browser smoke should validate the deployed admin experience after the real route/API surface exists.

**Delivers:** `/admin/report-operations` jobs panel/tab, preflight/confirmation reason flow, job progress polling, job detail results, cancel control with precise language, report/job audit panel, frontend e2e, production read-only Playwright smoke using a real admin session/storage state, privacy marker assertions, and redacted smoke evidence.

**Addresses:** Operator-facing job workflow, admin-only audit browsing, production admin browser smoke, UI privacy boundary, and real auth coverage without temporary production admin accounts.

**Avoids:** Fake auth smoke, production customer mutations, brittle pixel assertions, leaked storage state, and UI copy that implies rollback.

### Phase 37: Runbook, Release Gate, And Live Verification

**Rationale:** Operators need procedures for incident jobs, audit evidence, cancellation, stalled jobs, production smoke, and package provenance before v1.6 can be considered hardened.

**Delivers:** Updated report recovery runbook, release checklist with package manifest/hash evidence, Lambda CodeSha/source provenance checks, CDK diff/deploy evidence, production read-only browser smoke evidence, job/audit API live smoke where safe, and final milestone audit.

**Addresses:** Operational readiness, CI/CD drift response, incident stop/escalation guidance, privacy/authorization evidence, and Lambda deployment source-of-truth documentation.

**Avoids:** Runbook lag, deploy paths fighting each other, insufficient release evidence, and support using v1.5 procedures for v1.6 incident jobs.

### Phase Ordering Rationale

- Put the dist guard in the first phase because later async backend work requires CDK invoke permissions; no Lambda-asset CDK deploy should happen while stale `dist` remains possible.
- Extract shared recovery logic before async jobs so single-report and incident-wide operations cannot drift.
- Establish append-only audit early so existing and new recovery actions both produce durable evidence.
- Build backend job semantics before UI because progress, cancellation, target states, and audit fields need stable contracts.
- Run production browser smoke after the deployed UI/API exist, and keep it read-only by default.
- Close with runbook and live verification because incident-wide operations are only safe when operators have stop, audit, smoke, and package-provenance procedures.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 33:** Research exact CDK asset/build integration and decide the authoritative Lambda deployment path across backend direct deploy and infra CDK deploy.
- **Phase 33:** Validate whether v1.6 "immutable audit" means application append-only DynamoDB records or stronger WORM evidence. Default recommendation is application append-only.
- **Phase 35:** Validate production-safe job caps against report volume, SES sending quotas, Lambda remaining-time behavior, and whether self-invocation continuation is needed.
- **Phase 36:** Choose the approved real admin session mechanism for production browser smoke without temporary production admin accounts and without leaking auth state.

Phases with standard patterns where research-phase can usually be skipped:
- **Phase 34:** Service extraction, repository helpers, conditional writes, Pydantic models, and role tests follow established backend patterns.
- **Phase 36:** Mocked frontend e2e, React Query polling, and no-private-marker checks follow existing admin report operations patterns once the production auth mechanism is settled.
- **Phase 37:** Runbook and release evidence updates are standard documentation/verification work after implementation details are known.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Reuse decisions are grounded in current FastAPI, boto3, DynamoDB, Lambda, CDK, React admin UI, and Playwright surfaces; no new package or AWS service is required by default. |
| Features | HIGH | Table stakes are directly derived from v1.6 targets, v1.5 shipped capabilities, operator runbook limits, and documented residual risks. |
| Architecture | HIGH | Integration points are concrete: `admin.py`, report repository, weekly report Lambda, existing frontend admin page/hooks/API, and CDK `ApiStack`. |
| Pitfalls | HIGH | Risks map to observed v1.5 issues, AWS Lambda/DynamoDB/SES/CDK constraints, and privacy/authorization requirements. |
| Execution Caps | MEDIUM | Exact target limits, failure thresholds, SES pacing, and continuation strategy need live-volume validation during planning/execution. |
| Production Smoke Auth | MEDIUM | Shape is clear, but the approved real admin session or secret-backed credential procedure must be chosen with operators. |

**Overall confidence:** HIGH for roadmap direction; MEDIUM for final operational limits and production-auth mechanics.

### Gaps To Address

- **Immutable guarantee:** Decide and document whether v1.6 requires application-enforced append-only DynamoDB evidence or compliance-grade WORM. Default to append-only DynamoDB with conditional writes, overwrite tests, no TTL, and honest runbook language.
- **Lambda deployment source of truth:** Decide whether backend direct Lambda update, CDK asset deploy, or a shared artifact path is authoritative. At minimum, both deploy paths must use the same manifest-generating build script and provenance evidence.
- **Job caps and continuation:** Validate initial `resend_email` caps against production report counts, SES quotas, Lambda runtime, and DynamoDB scan/query behavior. Start conservative.
- **Production smoke auth:** Define how operators provide real admin storage state or secret-backed credentials without creating temporary production admin accounts, committing tokens, or uploading traces with auth state.
- **Generation retry expansion:** Treat incident-wide generation retry as a deferred follow-up until async resend, audit, cancellation, and stop conditions prove reliable.

## Sources

### Primary (HIGH confidence)
- `.planning/PROJECT.md` - v1.6 milestone goal, target features, current v1.5 shipped state, constraints, and key decisions.
- `.planning/research/STACK.md` - reuse-first stack recommendations, dependency/version guidance, Lambda/DynamoDB/CDK/frontend smoke choices, and dist manifest contract.
- `.planning/research/FEATURES.md` - table stakes, differentiators, anti-features, MVP recommendation, and operator safety/privacy boundaries.
- `.planning/research/ARCHITECTURE.md` - component boundaries, DynamoDB item shapes, API integration, worker data flow, frontend integration, production smoke, and CDK guard design.
- `.planning/research/PITFALLS.md` - critical/moderate/minor pitfalls, phase warning matrix, quality gate coverage, and roadmap gaps.
- Local code/repo evidence cited by researchers: `src/stoa/routers/admin.py`, `src/stoa/db/repositories/report_repo.py`, `src/stoa/services/report_service.py`, `src/stoa/jobs/weekly_reports.py`, `tests/test_admin_report_ops.py`, `/Users/zhdeng/stoa-infra/stacks/api_stack.py`, and frontend admin report operations files.

### Official / Vendor Sources
- AWS Lambda Invoke and async invocation docs - async worker invocation, retry/idempotency, timeout, and error handling constraints.
- AWS DynamoDB condition expressions, scan/pagination, TTL, and transaction docs - append-only writes, target snapshots, and bounded scan risks.
- AWS CDK assets and `aws_lambda.EventInvokeConfig` docs - Lambda asset packaging and async invoke configuration.
- Amazon SES sending quota docs - incident resend pacing and stop-condition planning.
- Amazon S3 Object Lock and CloudTrail integrity docs - stronger immutability options explicitly deferred unless required.
- Playwright authentication/storage state docs - real-session browser smoke mechanics.

---
*Research completed: 2026-06-04*
*Ready for roadmap: yes*
