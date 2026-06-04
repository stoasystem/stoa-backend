# Technology Stack

**Project:** STOA Backend
**Milestone:** v1.6 Report Recovery Operations Hardening
**Researched:** 2026-06-04
**Overall confidence:** HIGH for reuse-first stack guidance; MEDIUM for final job caps until production report volumes and SES limits are validated.

## Scope

This research answers what stack additions or changes are needed for v1.6 only:

- Incident-wide async report recovery jobs.
- Immutable audit log evidence for recovery actions.
- Production admin browser smoke using a real admin session, without creating temporary production admin accounts.
- CI/CD protection against stale `stoa-backend/dist` Lambda deployments.

Existing v1.5 capabilities are assumed valid: FastAPI backend, DynamoDB single-table repositories, Cognito admin auth, private S3 report artifacts, SES delivery, scheduled weekly report Lambda, admin report operations APIs/UI, single retry, single resend, selected bulk resend, live smoke, and the operations runbook.

## Recommended Stack

### Runtime and Backend

| Technology | Version / Source | Purpose | Why |
|------------|------------------|---------|-----|
| FastAPI | Existing backend dependency `>=0.115.0` | Admin job APIs and status endpoints | Already owns admin auth, report ops API shape, and metadata-only privacy boundaries. No framework change is needed. |
| Pydantic | Existing backend dependency `>=2.7.0` | Request/response models for job creation, progress, targets, audit events | Existing route models are Pydantic-based; keep contracts explicit and testable. |
| boto3 | Existing backend dependency `>=1.34.0` | DynamoDB, Lambda async invoke, SES/S3 reuse | Already used in backend and Lambda. No new AWS SDK dependency is needed. |
| Existing `stoa-weekly-report` Lambda | Python 3.12 ARM64, 1024 MB, 15 min timeout in CDK | Async recovery worker entrypoint | This Lambda already has report generation code, report artifact access, table access, Bedrock, and SES permission. Add a handler branch like `job=report_recovery` rather than creating a third Lambda. |
| Existing `stoa-api` Lambda | Python 3.12 ARM64, 512 MB, 29 sec timeout in CDK | Job creation, cancellation, status, audit reads | API Gateway should return quickly after persisting job state and asynchronously invoking the worker. It should not run incident-wide recovery inline. |

### Data Store

| Technology | Version / Source | Purpose | Why |
|------------|------------------|---------|-----|
| Existing DynamoDB table `stoa-main` | CDK single table, PAY_PER_REQUEST, PITR enabled | Job metadata, job target state, append-only audit evidence | Current table already supports report metadata and conditional writes. Reuse it unless a phase proves a new access pattern cannot be served by direct key queries or bounded scans. |
| Existing `GSI-ParentId` | `parent_id` + `week_start` | Parent-scoped target discovery | Reuse when operators scope jobs by parent/week. |
| Bounded scan over report summaries | Existing v1.5 admin pattern | Cross-parent incident target discovery at pilot volume | This is already accepted for admin report ops. Snapshot targets at job creation with explicit caps and pagination. |
| No new GSI by default | N/A | Avoid premature table/index expansion | Add a GSI only if v1.6 requirements demand high-volume list-by-job-status or global audit search. Direct job detail can use primary keys. |

Recommended item shapes:

```text
# Job metadata
PK = REPORT_RECOVERY_JOB#{job_id}
SK = META

# Job target snapshot and per-target progress
PK = REPORT_RECOVERY_JOB#{job_id}
SK = TARGET#{000001}#{report_id}

# Job-local audit timeline
PK = REPORT_RECOVERY_JOB#{job_id}
SK = AUDIT#{occurred_at}#{event_id}

# Report-local audit timeline
PK = REPORT_AUDIT#{report_id}
SK = EVENT#{occurred_at}#{event_id}
```

Use `attribute_not_exists(PK)` or `attribute_not_exists(SK)` on audit `PutItem` calls so evidence is append-only at the application layer. Use conditional `UpdateItem` calls to claim targets and reports, following the existing `try_start_generation_retry` pattern.

Do not enable DynamoDB TTL for audit evidence. TTL is useful for ephemeral job target cleanup, but audit records should remain available unless the product defines a retention policy. If TTL is used for non-audit job scratch data, store epoch seconds in a dedicated TTL attribute.

### Infrastructure / CDK

| Technology | Version / Source | Purpose | Why |
|------------|------------------|---------|-----|
| Existing `ApiStack` | CDK `aws-cdk-lib>=2.140.0` | IAM and Lambda async settings | Keep source of truth in CDK. Add permissions/configuration there, not by manual console changes. |
| `lambda_.EventInvokeConfig` | CDK v2 API | Bound async worker retry behavior | Lambda async invokes retry by default. Configure recovery invocation with a short max event age and `retry_attempts=0` or `1`; job-level idempotency should own retry semantics. |
| IAM policy from API Lambda to weekly Lambda | CDK policy statement | Allow `stoa-api` to invoke `stoa-weekly-report` asynchronously | This is the only required runtime IAM expansion for API-created async jobs. Scope to the weekly report Lambda ARN. |
| IAM policy from weekly Lambda to itself | Optional CDK policy statement | Continuation only if phases require multi-chunk self-invocation | Prefer a single bounded worker run first. If continuation is added, cap hop count and make every target idempotent. |
| Existing CloudWatch Logs and monitoring stack | Existing resources | Job observability | Emit structured logs with `job_id`, `target_report_id`, `operation`, `result`, `error_class`, and counts. New dashboards/alarms can be added later if job volume justifies it. |

Do not add Step Functions, a new SQS queue, EventBridge Pipes, DynamoDB Streams, a new table, or a new Lambda for v1.6. Those are justified only if v1.6 discovers requirements for long-running multi-hour workflows, durable queue backpressure, or complex human approval states. Current needs can be met by DynamoDB job state plus asynchronous invocation of the existing weekly report Lambda.

### Frontend and Browser Smoke

| Technology | Version / Source | Purpose | Why |
|------------|------------------|---------|-----|
| Existing React admin UI | Frontend repo | Job creation/status/cancel controls | Extend `/admin/report-operations`; no broad redesign or new admin shell. |
| Existing Playwright e2e | Frontend repo already has Playwright admin report ops test | Production admin browser smoke | Reuse the browser test stack and add a production-safe spec. No new browser testing service is required. |
| Real admin session storage state | Operator-provided or CI secret | Authenticate smoke without temporary production admins | The smoke should use a real approved admin session or real admin credentials stored as secrets. It must not create Cognito users as part of production smoke. |

Recommended smoke contract:

- Add a frontend script such as `npm run smoke:prod:admin-report-ops`.
- Require `STOA_PROD_ADMIN_STORAGE_STATE` or `STOA_PROD_ADMIN_STORAGE_STATE_PATH` for normal use.
- Optionally allow `STOA_PROD_ADMIN_EMAIL` and `STOA_PROD_ADMIN_PASSWORD` in controlled CI if the team accepts credential-based login.
- Visit `https://app.stoaedu.ch/admin/report-operations`.
- Assert route loads, admin-only controls render, report ops API call succeeds, and no private artifact markers appear (`weekly-reports/`, `json_s3_key`, `html_s3_key`, `s3_key`, presigned URLs, raw HTML/JSON).
- Keep production smoke read-only by default. Mutating safe fixtures remain separate from the browser smoke.

### CI/CD and Lambda Dist Guard

| Technology | Version / Source | Purpose | Why |
|------------|------------------|---------|-----|
| Shared backend dist build script | New repo script, no dependency | Rebuild Lambda package consistently | Backend deploy and infra CDK workflows currently duplicate build commands. A shared script prevents drift. |
| Build manifest in `dist` | New JSON file, Python stdlib | Prove `dist` matches source | CDK deploys `../stoa-backend/dist`; a manifest lets CDK fail fast when local/manual deploy would use stale assets. |
| CDK synth/deploy preflight | New infra-side check | Block stale Lambda assets | v1.5 proved stale local `dist` can roll back Lambda code. Guard this in CDK, not only in runbooks. |
| Existing GitHub Actions workflows | Backend and infra repos | CI enforcement | Infra workflow already rebuilds `dist`; update it to call the shared script and run the same verifier before `cdk diff` and `cdk deploy`. |

Recommended manifest fields:

```json
{
  "schema": "stoa-lambda-dist-v1",
  "backend_git_sha": "...",
  "source_tree_hash": "...",
  "requirements_hash": "...",
  "python_version": "3.12",
  "platform": "manylinux2014_aarch64",
  "built_at": "2026-06-04T00:00:00Z"
}
```

Recommended guard behavior:

- Backend build script deletes and recreates `dist`, installs Linux ARM64 wheels, copies `src/stoa`, and writes the manifest.
- Infra `ApiStack` or a pre-synth script verifies `../stoa-backend/dist/.stoa-build-manifest.json` exists.
- The verifier recomputes `source_tree_hash` from `src/stoa`, `requirements.txt`, and deployment-relevant backend config, then compares it to the manifest.
- CDK diff/deploy fails unless the manifest matches. Allow an explicit `ALLOW_STALE_LAMBDA_DIST=1` escape hatch only for emergency rollback commands documented in the runbook.

## Integration Guidance

### Async Recovery Jobs

Use API-created DynamoDB jobs plus async invocation of `stoa-weekly-report`:

1. Admin calls `POST /admin/reports/recovery-jobs` with operation type (`resend_email`, `retry_generation`), filters or explicit targets, reason, and max bounds.
2. API validates admin role, snapshots target report IDs using existing admin list/report lookup paths, writes `META` and `TARGET#...` items, appends a `job_created` audit event, and invokes `stoa-weekly-report` with `InvocationType="Event"`.
3. Worker loads the job, conditionally marks it `running`, processes targets sequentially or with a small bounded concurrency inside the Lambda, and updates per-target result.
4. Worker checks cancellation/stop conditions before each target: job status changed to `cancel_requested`, elapsed time limit, max targets, max failures, Lambda remaining time, report no longer eligible, artifact missing, SES/generation repeated failure.
5. Worker finalizes job as `completed`, `completed_with_failures`, `stopped`, or `cancelled`, then appends audit evidence.

Use strict caps initially:

- Resend jobs: cap target snapshot to 100 or 250 reports until SES rate and live behavior are measured.
- Generation retry jobs: cap lower, for example 25 or 50, because Bedrock/report generation is more expensive and slower than SES resend.
- Worker should stop before Lambda timeout using `context.get_remaining_time_in_millis()`.

### Immutable Audit Evidence

Write an audit event for every operator-visible state transition:

- `job_created`
- `job_started`
- `target_claimed`
- `target_refused`
- `target_succeeded`
- `target_failed`
- `job_cancel_requested`
- `job_stopped`
- `job_completed`

Each event should include:

- `event_id`
- `occurred_at`
- `operator_id`
- `operator_email` if available
- `operation`
- `reason`
- `job_id`
- `report_id`, `parent_id`, `student_id`, `week_start` when target-specific
- `before_status` / `after_status`
- `result`
- `error_class` and redacted `error_message`
- `request_id` / Lambda aws request id when available

Keep audit responses metadata-only. Never expose private S3 keys, presigned URLs, or raw artifacts in admin API responses.

Important distinction: DynamoDB append-only records are operationally immutable evidence, not legal WORM storage. If the product later requires compliance-grade immutability, S3 Object Lock is the AWS-native direction, but enabling Object Lock is an infrastructure commitment because it requires versioning and cannot be disabled once enabled on a bucket. Do not introduce that for v1.6 unless compliance explicitly requires it.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Async orchestration | API + DynamoDB job state + async invoke existing weekly Lambda | Step Functions | Adds a new AWS service and workflow model before the need is proven. Current jobs can be bounded to one Lambda run. |
| Work queue | DynamoDB target items | New SQS queue | SQS is useful for per-target queueing/backpressure, but v1.6 can process a snapshotted bounded list without queue infrastructure. |
| Worker compute | Reuse `stoa-weekly-report` | New `stoa-report-recovery` Lambda | Existing weekly Lambda already has report generation, S3, SES, Bedrock, and table permissions. A new Lambda duplicates packaging/deploy surface. |
| Audit storage | Append-only DynamoDB event items | New audit table | Existing single-table design and PITR are sufficient for operational evidence. New table is premature. |
| Compliance WORM | Defer | S3 Object Lock bucket | Stronger immutability but heavier irreversible infra commitment; not required for current operational audit evidence. |
| Production browser smoke | Existing Playwright with real admin session | Temporary Cognito admin fixture | v1.6 explicitly avoids temporary production admin accounts. |
| Lambda dist guard | Build manifest + CDK verifier | Runbook reminder only | v1.5 proved humans can accidentally deploy stale `dist`; the guard must be enforced by tooling. |

## Installation / Dependency Changes

No new Python package is required for v1.6.

No new AWS service is required by default.

Expected code/infrastructure changes:

```bash
# Backend
# Add repository/service modules, no new dependency:
# - src/stoa/db/repositories/report_recovery_job_repo.py
# - src/stoa/db/repositories/report_audit_repo.py
# - src/stoa/services/report_recovery_service.py
# - extend src/stoa/jobs/weekly_reports.py handler routing
# - extend src/stoa/routers/admin.py or split report ops routes into a focused admin report module

# Infra
# Add scoped lambda:InvokeFunction permissions and async invoke config in ApiStack.
# Add dist manifest verification before CDK diff/deploy.

# Frontend
# Add admin job UI and production read-only Playwright smoke using existing frontend tooling.
```

## Sources

- Local planning context: `.planning/PROJECT.md`, `.planning/MILESTONES.md`, `.planning/milestones/v1.5-MILESTONE-AUDIT.md`, `.planning/milestones/v1.5-phases/32-operations-runbook-observability-and-milestone-closeout/32-OPERATIONS-RUNBOOK.md`
- Local backend evidence: `src/stoa/routers/admin.py`, `src/stoa/db/repositories/report_repo.py`, `src/stoa/jobs/weekly_reports.py`
- Local infra evidence: `/Users/zhdeng/stoa-infra/stacks/api_stack.py`, `/Users/zhdeng/stoa-infra/stacks/database_stack.py`, `/Users/zhdeng/stoa-infra/.github/workflows/deploy.yml`
- AWS Lambda Invoke API: https://docs.aws.amazon.com/lambda/latest/api/API_Invoke.html
- AWS Lambda async invocation error handling config: https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-configuring.html
- AWS CDK v2 `aws_lambda.EventInvokeConfig`: https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_lambda/EventInvokeConfig.html
- DynamoDB condition expressions: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.OperatorsAndFunctions.html
- DynamoDB TTL format guidance: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/time-to-live-ttl-before-you-start.html
- S3 Object Lock configuration/constraints: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-configure.html
