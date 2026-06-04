# Domain Pitfalls

**Domain:** Report recovery operations hardening for STOA production admin tooling
**Milestone:** v1.6 Report Recovery Operations Hardening
**Researched:** 2026-06-04
**Overall confidence:** HIGH for project-specific risks; HIGH for AWS documented constraints; MEDIUM for phase numbering because roadmap is not written yet.

## Executive Takeaway

v1.6 should treat incident-wide recovery as a controlled operations workflow, not as "bulk resend but bigger." The current v1.5 system is intentionally synchronous, selected, metadata-only, and capped at 25 resend targets. Scaling that pattern without a job ledger, conditional claims, immutable per-action audit records, bounded execution, and production smoke evidence will recreate the exact risks v1.5 exposed: pagination drift, missing IAM, private artifact exposure, and stale Lambda package deployment.

Recommended phase ownership:

| Phase | Suggested Name | Owns |
|-------|----------------|------|
| Phase 33 | Incident Recovery Contract and CDK Readiness | Job API contract, data model, IAM/CDK proof, stop conditions |
| Phase 34 | Async Recovery Job Backend | Job creation, target snapshot, worker loop, claims, cancellation, progress |
| Phase 35 | Immutable Recovery Audit Ledger | Append-only audit records, transaction semantics, privacy redaction, audit verification |
| Phase 36 | Production Admin Browser Smoke | Real admin-session UI smoke, no temp production admin accounts, privacy assertions |
| Phase 37 | Lambda Dist Rebuild Guard and Release Gate | CDK/build guard, package manifest, CI/CD drift checks, final live verification |

## Critical Pitfalls

### Pitfall 1: Treating Incident-Wide Recovery As A Synchronous Admin API

**What goes wrong:** A large incident recovery request runs inside the FastAPI/API Gateway request path and either times out, blocks the API Lambda, partially mutates reports, or returns an incomplete result that the operator interprets as done.

**Why it happens:** v1.5's selected bulk resend is synchronous and capped at 25 targets. Incident-wide work needs discovery, per-target mutation, email sending, progress, cancellation, and retry/resume behavior. AWS Lambda functions can run for at most 900 seconds, and API integrations are not a durable job boundary.

**Consequences:**

- Partial sends with no durable progress marker.
- Duplicate emails when the operator retries a timed-out request.
- API concurrency pressure during an incident.
- No reliable way to cancel or resume.

**Warning signs:**

- Endpoint names like `POST /admin/reports/recover-all` returning final per-item results directly.
- Loops over report scans or SES sends inside a route handler.
- No persistent job item before target processing begins.
- UI progress derived from the HTTP request still being open.

**Prevention:**

- Phase 33: Define async contract: `POST` creates a job and returns `job_id`; separate read-only job detail/progress endpoints; action endpoints for cancel/stop.
- Phase 34: Persist job state before processing: `queued`, `running`, `cancel_requested`, `stopping`, `completed`, `failed`, `cancelled`.
- Phase 34: Process in bounded chunks with cursor, deadline, max targets, max failures, and max wall-clock per invocation.
- Phase 34: Make cancellation cooperative: stop between targets/chunks, never promise to interrupt an in-flight SES send or report generation.
- Phase 34: Persist partial progress after each target or small batch.

**Phase:** Phase 33 for contract; Phase 34 for implementation.

### Pitfall 2: Building The Job Target Set From A Live Scan Without A Snapshot

**What goes wrong:** The incident job processes a moving target set. Reports updated during the scan may be skipped, processed twice, or counted incorrectly. The UI shows misleading progress because DynamoDB filter expressions are applied after read pagination.

**Why it happens:** Current cross-parent report ops listing uses bounded scan for pilot volume. DynamoDB `Scan` reads the table/index page by page, can require repeated calls through `LastEvaluatedKey`, and does not provide snapshot isolation. Filters reduce returned items after the scan reads data.

**Consequences:**

- "Recover all failed reports for week X" does not actually mean a stable set.
- Newly failed reports can enter the job mid-run without operator intent.
- Progress percentages are wrong because the denominator is unknown or shifting.
- Re-running the job becomes the only way to discover misses.

**Warning signs:**

- Job processes scan results directly without first writing target records.
- Job detail shows only `processed / scanned`, not `processed / target_count`.
- Empty pages with `LastEvaluatedKey` are treated as job completion.
- Filters like `status=email_failed` are trusted without per-target revalidation.

**Prevention:**

- Phase 33: Define job creation as target snapshot creation: freeze filters, actor, reason, requested time, and target identifiers.
- Phase 34: Build durable target records before mutation: one target item per `(job_id, parent_id, student_id, week_start, operation)`.
- Phase 34: Revalidate each report immediately before mutation with current status and artifact availability.
- Phase 34: Track `discovered_count`, `target_count`, `processed_count`, `success_count`, `refused_count`, `failed_count`, `skipped_count`.
- Phase 34: Keep scan page limits, max pages, and max discovered targets explicit; refuse jobs that exceed the safe bound until a CDK-managed access pattern is added.

**Phase:** Phase 33 for access-pattern decision; Phase 34 for target snapshot.

### Pitfall 3: Duplicate Sends Or Regeneration From Missing Conditional Claims

**What goes wrong:** Two admins, two browser retries, or one Lambda retry and one manual retry act on the same report. For resend, this can send duplicate parent emails. For generation retry, it can overwrite audit fields or race artifact writes.

**Why it happens:** v1.5 has a conditional claim for single generation retry, but resend currently validates status and sends synchronously without an atomic "resend claimed by operation X" transition. AWS async invocation can deliver duplicate events, and humans can resubmit actions.

**Consequences:**

- Parents receive duplicate report emails.
- Audit trail points at the last operation only, not every attempt.
- Report item says `email_sent` even though an earlier failed attempt belongs to a different job.
- Operator cannot distinguish a retry from a new action.

**Warning signs:**

- Resend worker calls SES before a conditional claim.
- No per-target operation id or idempotency key.
- Report summary stores only `last_operation`.
- Job retries have no "already completed by same operation" branch.

**Prevention:**

- Phase 34: Claim each target before side effects using conditional update on report state and target state.
- Phase 34: Use operation ids: `job_id + target_id + attempt_number` or a stable idempotency key.
- Phase 34: For resend, transition eligible reports to a short-lived `email_resend_in_progress` or equivalent claim state before reading the HTML artifact and calling SES.
- Phase 34: Treat duplicate delivery of the same job event as idempotent: already-success targets return `skipped_already_completed`, not a second send.
- Phase 35: Append an audit record for every attempted claim, refusal, failure, and success.

**Phase:** Phase 34 for conditional claims; Phase 35 for per-attempt audit.

### Pitfall 4: Relying On Mutable Report Fields As "Immutable Audit Logs"

**What goes wrong:** `last_operation`, `last_operation_by`, timestamps, and error fields are overwritten by later actions. Support cannot reconstruct who did what, why, which job touched which reports, or whether a sensitive operation was altered after the fact.

**Why it happens:** v1.5's audit fields are useful status metadata but live on the mutable report summary item. They are not an immutable audit log.

**Consequences:**

- Incident review cannot prove sequence of operations.
- A later successful resend hides prior failed or refused attempts.
- Manual DynamoDB edits can alter evidence.
- Roadmap claims "immutable audit" but implementation only provides "latest operation metadata."

**Warning signs:**

- Audit acceptance tests read only report summary fields.
- No append-only audit entity exists.
- Audit item key does not include operation id/attempt id.
- Audit entries can be updated by normal report status update helpers.

**Prevention:**

- Phase 35: Add append-only audit items in the existing single-table design unless CDK proof shows a separate resource is required.
- Phase 35: Write audit entries with `ConditionExpression attribute_not_exists(PK)` / `attribute_not_exists(SK)` so the same audit id cannot be overwritten.
- Phase 35: Use `TransactWriteItems` when report state and audit evidence must commit together. Keep transaction items small and under AWS limits.
- Phase 35: Record `actor_sub`, role, operation, job_id, target ids, requested reason, prior status, claim result, final result, error class, redacted error message, and timestamps.
- Phase 35: Keep report summary `last_operation*` as convenience metadata only; never treat it as evidence.
- Phase 35: Do not put raw HTML/JSON, S3 keys, public URLs, presigned URLs, or full parent email bodies in audit entries.

**Phase:** Phase 35.

### Pitfall 5: Claiming True Immutability Without A Matching Storage/IAM Control

**What goes wrong:** The product says audit logs are immutable, but admins or application code can still update/delete them through the same DynamoDB write path.

**Why it happens:** Application-level append-only logic is not the same as WORM storage. DynamoDB can enforce conditional creation per write, but broad IAM or helper functions can still mutate existing audit items if not constrained. S3 Object Lock or CloudTrail digest validation provide stronger evidence, but they require explicit CDK/resource support.

**Consequences:**

- Security review finds the audit log is mutable.
- A bug or operator script deletes audit evidence.
- Recovery support loses non-repudiation during an incident.

**Warning signs:**

- Audit repository exposes generic `update_audit` or `delete_audit`.
- Lambda role has broad write/delete permissions without item-level safeguards.
- Tests only verify successful creation, not overwrite refusal.
- No decision on whether "immutable" means application append-only or storage-level WORM.

**Prevention:**

- Phase 33: Define the immutability level required for v1.6: application append-only in DynamoDB, or stronger storage-level WORM if required.
- Phase 35: If using DynamoDB, keep audit APIs create-only, add overwrite tests, and avoid TTL on audit records.
- Phase 35: Consider a hash chain per job (`previous_audit_hash`, `audit_hash`) so tampering is detectable even if storage is not WORM.
- Phase 35: If true WORM is required, prove current CDK resources can or cannot support S3 Object Lock/CloudTrail-style integrity before adding resources.
- Phase 35: Document the exact guarantee honestly in the runbook.

**Phase:** Phase 33 for guarantee definition; Phase 35 for implementation.

### Pitfall 6: Private Report Artifact Leakage Through Job, Audit, Or Smoke Outputs

**What goes wrong:** New job details, audit records, browser traces, screenshots, logs, or per-target errors expose `weekly-reports/...` keys, raw report HTML/JSON, `json_s3_key`, `html_s3_key`, `s3_key`, public S3 URLs, or presigned URLs.

**Why it happens:** v1.5 carefully redacts metadata responses, but incident-wide workflows add new surfaces: job detail, target result, audit item, browser console/network capture, CI logs, and screenshots.

**Consequences:**

- Violates the core decision that report artifacts remain private and backend-mediated.
- CI artifacts can retain private customer report identifiers.
- Browser smoke evidence becomes unsafe to share.

**Warning signs:**

- Job target detail returns raw stored report item.
- Audit payload stores exception strings without redaction.
- Playwright traces/videos/screenshots are uploaded unredacted.
- Tests check admin detail privacy but not job/audit endpoints.

**Prevention:**

- Phase 33: Include a privacy response contract for every new endpoint.
- Phase 34 and 35: Reuse or extend `_redact_private_artifact_text` for job errors and audit errors.
- Phase 34 and 35: Return artifact availability booleans only; never return artifact keys or direct S3 locations.
- Phase 36: Browser smoke must assert DOM, network responses, console output, and saved artifacts do not contain private artifact markers.
- Phase 36: Store only redacted smoke evidence.

**Phase:** Phase 33 contract; Phase 34/35 backend enforcement; Phase 36 smoke verification.

### Pitfall 7: Incident-Wide Recovery Blowing Through SES Or Root-Cause Stop Conditions

**What goes wrong:** A job continues sending or retrying after SES throttling, IAM `AccessDenied`, artifact read failure, bad recipient data, or a privacy regression. The incident job amplifies a configuration bug across many families.

**Why it happens:** The v1.5 workflow is selected and operator-paced. Incident-wide automation needs blast-radius controls and fail-fast rules.

**Consequences:**

- Large duplicate/failed email waves.
- SES reputation or quota pressure.
- Many report items marked failed for the same infrastructure cause.
- Operators lose time sorting per-item failures instead of stopping the job.

**Warning signs:**

- Job has no `dry_run`/preview count.
- No global cap on targets per job.
- No max failures, max consecutive failures, or failure-class stop rule.
- SES throttling is treated as ordinary per-item failure.

**Prevention:**

- Phase 33: Require job preview/dry-run output before mutation: target count, operation type, week, filters, and reason.
- Phase 34: Add hard caps: max targets, max runtime per chunk, max consecutive failures, max total failures, and stop-on error classes.
- Phase 34: Stop immediately on `AccessDenied`, missing SES permission, private artifact marker in response/log candidate, or repeated artifact read failure.
- Phase 34: Rate-limit SES sends and keep concurrency conservative until production quotas are verified.
- Phase 37: Add incident stop/escalation guidance to the updated runbook.

**Phase:** Phase 33 for policy; Phase 34 for enforcement; Phase 37 for runbook closeout.

### Pitfall 8: Misleading Cancellation Semantics

**What goes wrong:** The UI says a job is cancelled, but targets already claimed or in-flight still send. Operators think the incident stopped when some side effects are still completing.

**Why it happens:** Cancellation in a Lambda/SES workflow is cooperative. You can stop before the next target, not rewind or interrupt an already-started external send.

**Consequences:**

- Operator communications become inaccurate.
- Audit trail has "cancelled" job with later target successes.
- Follow-up jobs accidentally reprocess in-flight items.

**Warning signs:**

- Job status changes directly from `running` to `cancelled`.
- Target states do not distinguish `claimed`, `in_progress`, `sent`, `cancel_skipped`.
- No heartbeat/deadline for stale in-progress targets.

**Prevention:**

- Phase 34: Model cancellation as `cancel_requested` -> `stopping` -> terminal status after worker observes it.
- Phase 34: Store target-level terminal reasons: `cancel_skipped`, `already_sent`, `refused`, `failed`, `success`.
- Phase 34: Include heartbeat/lease timestamps so stale `in_progress` targets can be marked stalled and reviewed.
- Phase 36: Browser smoke should verify cancel UI language is precise: "Stop requested" until worker confirms no more targets will start.

**Phase:** Phase 34; Phase 36 for UI evidence.

### Pitfall 9: Production Browser Smoke Using Fake Auth Or Temporary Production Admin Accounts

**What goes wrong:** Browser smoke passes locally or with a synthetic account but does not prove the production admin route works for a real admin session. Or it creates temporary production admins, adding cleanup and authorization risk.

**Why it happens:** v1.5 left real admin browser click-through as residual manual evidence. Playwright auth storage state is useful, but mishandling it can hide auth drift or leak credentials.

**Consequences:**

- Production UI can be broken while route-marker checks pass.
- CI stores admin cookies/tokens in artifacts.
- Temporary admin accounts remain in Cognito.
- Smoke mutates customer data by accident.

**Warning signs:**

- Smoke bypasses Cognito or injects fake JWTs into production.
- Test creates a production admin user.
- Storage state file is committed or uploaded.
- Smoke only checks bundle text, not rendered authenticated UI and backend calls.

**Prevention:**

- Phase 36: Use a real existing admin session provided through a secret or operator-supplied storage state; do not create temporary production admin accounts.
- Phase 36: Keep smoke read-only by default: open `/admin/report-operations`, verify filters/detail metadata, auth gate, no private markers, and no mutation buttons clicked unless a safe fixture is explicitly selected.
- Phase 36: Store auth state outside the repo, exclude it from traces/artifacts, and redact screenshots/logs.
- Phase 36: Add a separate auth-setup assertion so stale storage state fails loudly before UI checks.
- Phase 36: Keep local/e2e tests for mutation behavior; reserve production browser smoke for deployed route, auth, privacy, and read-only confidence unless a fixture plan exists.

**Phase:** Phase 36.

### Pitfall 10: Lambda Dist Guard Checking The Wrong Thing

**What goes wrong:** CI/CD adds a "dist guard" that still allows stale Lambda assets, or blocks valid deploys because hashes are nondeterministic. CDK diff/deploy continues to read `../stoa-backend/dist` that may not match current source.

**Why it happens:** v1.5 found CDK deploy from stale local `dist` temporarily reintroduced old Lambda code. The backend GitHub workflow builds and directly updates Lambda from `lambda.zip`, while infra CDK deploys can independently package local `dist` assets. These are two deployment paths with different package sources.

**Consequences:**

- CDK deploy overwrites a newer backend release with an older local package.
- CI reports clean infrastructure diff while Lambda code is wrong.
- Operators cannot tell which source commit produced the deployed Lambda package.

**Warning signs:**

- Guard only checks that `dist/` exists.
- Guard compares Lambda `CodeSha256` without knowing the source manifest.
- CDK diff/deploy can run without rebuilding backend package.
- `stoa-api` and `stoa-weekly-report` code hashes change during IAM-only work.

**Prevention:**

- Phase 37: Make CDK diff/deploy fail when Lambda asset source is stale, missing, or lacks a manifest matching current backend source/lockfile.
- Phase 37: Generate a deterministic package manifest inside `dist` with backend git SHA, source tree hash, dependency lock/requirements hash, build command, timestamp, and handler inventory.
- Phase 37: Prefer CDK asset bundling or a mandatory pre-CDK build step over relying on a manually maintained `dist` directory.
- Phase 37: Distinguish IAM-only infra deploys from Lambda asset deploys; if Lambda asset hash changes, require package evidence.
- Phase 37: Add post-deploy verification that both `stoa-api` and `stoa-weekly-report` are Active, Successful, and match the expected package manifest/hash.

**Phase:** Phase 37.

### Pitfall 11: CI/CD Deploy Paths Fighting Each Other

**What goes wrong:** Backend CI updates Lambda code directly, then infra CDK later deploys a different local asset. The final production state depends on the last deploy path, not the intended source of truth.

**Why it happens:** Current `.github/workflows/deploy.yml` builds `lambda.zip` and calls `aws lambda update-function-code` for both Lambdas. v1.5 also documents CDK deployments using `../stoa-backend/dist` as Lambda assets.

**Consequences:**

- Drift between GitHub backend deploy evidence and CDK stack state.
- Rollback guidance is ambiguous.
- A clean CDK diff can still be paired with stale Lambda code if asset packaging is out of band.

**Warning signs:**

- Release checklist does not say which pipeline owns Lambda code.
- Backend and infra pipelines build packages differently.
- No single package manifest is shared by both paths.
- Rollback instructions mention commits but not package provenance.

**Prevention:**

- Phase 37: Decide and document Lambda code source of truth: CDK-built asset, backend CI direct update, or CI-produced artifact consumed by CDK.
- Phase 37: Make the non-authoritative path fail or become read-only verification.
- Phase 37: Use the same package build script locally and in CI.
- Phase 37: Add release evidence fields: package manifest hash, backend commit, infra commit, Lambda CodeSha256 for both functions, and deploy path used.

**Phase:** Phase 37.

### Pitfall 12: Adding New AWS Resources Before Proving Existing CDK Cannot Support The Need

**What goes wrong:** v1.6 adds Step Functions, new queues, new tables, or new buckets prematurely, expanding IAM and operational surface before the existing single-table/Lambda/API architecture has been evaluated.

**Why it happens:** "Async job" and "immutable audit" often trigger new-service designs. The project constraints explicitly require checking current CDK/resources first.

**Consequences:**

- Larger roadmap than needed.
- More IAM and deployment drift risk.
- New observability and rollback paths.
- Delayed delivery of the core hardening.

**Warning signs:**

- Phase plans start with new AWS services rather than access-pattern proof.
- No evidence ledger for current DynamoDB/S3/Lambda/API Gateway support.
- IAM permissions are broadened before endpoint behavior is specified.

**Prevention:**

- Phase 33: Start with CDK/resource evidence: existing table, GSIs, Lambda env vars, IAM actions, reports bucket/log bucket capabilities, API Gateway route support.
- Phase 33: Add resources only when an access pattern or immutability guarantee cannot be safely met with current resources.
- Phase 33: If new resources are required, make CDK changes first and include a rollback path before backend code depends on them.

**Phase:** Phase 33.

## Moderate Pitfalls

### Pitfall 13: Audit Records Becoming Too Large Or Too Sensitive

**What goes wrong:** Audit entries store raw exception payloads, report content, email body, full artifacts, or unbounded target lists. DynamoDB item size limits or privacy constraints are hit.

**Prevention:** Phase 35 should store compact audit records and put target-level details in separate target/audit items. Error messages must be capped and redacted, following the existing 240-character error-message pattern.

**Phase:** Phase 35.

### Pitfall 14: Progress UI Hiding Refused And Skipped Work

**What goes wrong:** The UI reports "80% successful" while refusing many targets because statuses changed, artifacts were missing, or cancellation skipped them.

**Prevention:** Phase 34 should define target terminal states. Phase 36 should verify the UI renders success, failed, refused, skipped, already-completed, and cancel-skipped separately.

**Phase:** Phase 34 and Phase 36.

### Pitfall 15: Stalled Job Or Target States With No Recovery Path

**What goes wrong:** A Lambda timeout or exception leaves a job `running` or target `in_progress` forever.

**Prevention:** Phase 34 should add leases/heartbeats, `last_heartbeat_at`, `lease_expires_at`, max attempt counts, and operator-visible `stalled` detection. Phase 37 runbook should explain how to inspect and safely resume or abandon a stalled job.

**Phase:** Phase 34 and Phase 37.

### Pitfall 16: Generation Retry And Email Resend Sharing One Over-Broad Job Type

**What goes wrong:** A single "recover incident" job mixes regeneration and resend semantics. Generation retries call Bedrock, write artifacts, and may send email; resends read existing HTML and call SES.

**Prevention:** Phase 33 should define separate operation types with separate eligibility, caps, stop conditions, and confirmation copy. Phase 34 should implement one operation path at a time if needed.

**Phase:** Phase 33 and Phase 34.

### Pitfall 17: Missing Authorization Tests On New Job And Audit Endpoints

**What goes wrong:** Existing report ops endpoints are admin-only, but new job/audit endpoints accidentally allow parent/student/teacher/tutor access or expose job details through predictable ids.

**Prevention:** Phase 34 and 35 must add role tests for every new route: unauthenticated 401, invalid token 401, non-admin 403, admin 200. Job ids should not grant access without admin role.

**Phase:** Phase 34 and Phase 35.

### Pitfall 18: Runbook Lagging Behind New Incident Controls

**What goes wrong:** Operators use v1.5 selected-resend guidance for v1.6 incident jobs and miss new stop/cancel/audit/release checks.

**Prevention:** Phase 37 should update the runbook with async job creation, dry-run, progress, cancellation, audit lookup, stalled job recovery, browser smoke evidence, and Lambda package drift response.

**Phase:** Phase 37.

## Minor Pitfalls

### Pitfall 19: Opaque Job IDs That Are Hard To Support

**What goes wrong:** Operators cannot map a job to incident, week, actor, or reason without opening every item.

**Prevention:** Use opaque ids for security, but store searchable metadata: operation type, week, status filter, actor, reason, created_at, and summary counts.

**Phase:** Phase 34.

### Pitfall 20: Browser Smoke Becoming Too Brittle

**What goes wrong:** Smoke fails on harmless UI copy or layout changes.

**Prevention:** Assert stable contracts: route loads, admin identity/session accepted, API calls succeed, report ops controls render, privacy markers absent. Avoid pixel-perfect assertions.

**Phase:** Phase 36.

### Pitfall 21: Over-Trusting Bundle Marker Checks

**What goes wrong:** Production bundle contains expected strings, but runtime config, auth, API calls, or UI rendering still fail.

**Prevention:** Keep bundle marker checks as a cheap preflight only. Phase 36 must include real browser runtime evidence with a real admin session.

**Phase:** Phase 36.

## Phase-Specific Warning Matrix

| Phase Topic | Likely Pitfall | Warning Signs | Mitigation |
|-------------|----------------|---------------|------------|
| Phase 33 - Contract/CDK readiness | Async/audit design adds unsupported resources or misses access-pattern limits | No CDK evidence ledger; new services assumed | Prove existing resources first; define target snapshot, job states, immutable guarantee, and privacy contract |
| Phase 34 - Async backend | Duplicate sends, moving target set, stalled jobs | No target ledger; no conditional claims; no leases | Snapshot targets, claim conditionally, persist progress, use idempotency keys and cooperative cancellation |
| Phase 35 - Audit ledger | Mutable or sensitive audit records | Audit only stored on report summary; raw errors/artifact keys in audit | Append-only audit items, transactional writes, overwrite tests, redaction, no TTL |
| Phase 36 - Browser smoke | Fake auth or leaked admin state | Temporary admin account creation; committed storage state; traces with tokens | Use real existing admin session via secret/operator state, keep smoke read-only, redact artifacts, assert privacy markers absent |
| Phase 37 - Dist guard/release | Stale Lambda deployment drift | CDK deploy reads old `dist`; guard checks existence only | Deterministic build manifest, fail stale assets, unify deploy source of truth, post-deploy CodeSha/package evidence |

## Quality Gate Coverage

| Required Risk Area | Covered By |
|--------------------|------------|
| Async incident-wide recovery | Pitfalls 1, 2, 3, 7, 8, 14, 15, 16 |
| Immutable recovery audit logs | Pitfalls 4, 5, 13 |
| Production admin browser smoke | Pitfalls 6, 9, 20, 21 |
| CI/CD Lambda dist rebuild guard | Pitfalls 10, 11 |
| Privacy/security/authorization | Pitfalls 3, 4, 5, 6, 9, 17 |
| Production deployment drift | Pitfalls 10, 11, 18 |

## Sources

Project sources:

- `.planning/PROJECT.md` - v1.6 milestone goal, constraints, decisions, shipped v1.5 state.
- `.planning/STATE.md` - residual v1.6 concerns and stale `dist` deployment risk.
- `.planning/milestones/v1.5-MILESTONE-AUDIT.md` - v1.5 issues found/resolved and next operational backlog.
- `.planning/milestones/v1.5-phases/32-operations-runbook-observability-and-milestone-closeout/32-OPERATIONS-RUNBOOK.md` - current production report recovery runbook and privacy expectations.
- `src/stoa/routers/admin.py` - current report ops list/detail/retry/resend/bulk-resend implementation.
- `src/stoa/db/repositories/report_repo.py` - current report data access, admin bounded scan, pagination token behavior, generation retry claim.
- `.github/workflows/deploy.yml` - backend CI Lambda zip deployment path.

Official sources:

- AWS Lambda timeout documentation: https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html
- AWS Lambda async retry/idempotency guidance: https://docs.aws.amazon.com/lambda/latest/dg/invocation-retries.html
- AWS Lambda async error handling and duplicate-event warning: https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html
- DynamoDB Scan behavior and pagination: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Scan.html
- DynamoDB Scan API consistency and `LastEvaluatedKey`: https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Scan.html
- DynamoDB conditional writes / item operations: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithItems.html
- DynamoDB transactions / `TransactWriteItems`: https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html
- S3 Object Lock overview for WORM-style immutability: https://docs.aws.amazon.com/AmazonS3/latest/dev/object-lock-overview.html
- CloudTrail log file integrity validation: https://docs.aws.amazon.com/en_en/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html
- AWS CDK assets documentation: https://docs.aws.amazon.com/cdk/v2/guide/assets.html
- Playwright authentication/storage state documentation: https://playwright.dev/docs/auth
- Amazon SES sending quotas: https://docs.aws.amazon.com/ses/latest/dg/manage-sending-quotas.html

## Gaps For Roadmap Follow-Up

- The roadmap must decide whether "immutable audit" means application-enforced append-only DynamoDB records or storage-level WORM evidence. The former is likely enough for v1.6 operations hardening; the latter needs CDK/resource proof.
- The roadmap must decide the authoritative Lambda deployment path. Keeping both direct backend `update-function-code` and CDK local-asset deployments without a shared package manifest leaves a persistent drift hazard.
- The safe production browser smoke still needs a concrete credential/session handling procedure. Do not proceed with production browser smoke until the no-temp-admin-account constraint is satisfied.
