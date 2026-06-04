# Architecture Research: Report Recovery Operations Hardening

**Project:** STOA Backend / v1.6 Report Recovery Operations Hardening
**Researched:** 2026-06-04
**Mode:** Project architecture research
**Overall confidence:** HIGH for current integration points, MEDIUM for exact async worker limits until live AWS timeout/concurrency behavior is tested.

## Executive Recommendation

Integrate v1.6 as an extension of the existing report operations platform, not as a new recovery subsystem. Keep the public control plane in the existing FastAPI/Mangum `stoa-api` Lambda and keep durable recovery state in the existing `stoa-main` DynamoDB single table. Move the current resend/retry implementation out of `src/stoa/routers/admin.py` into a reusable recovery service, then have both synchronous single-report endpoints and async incident-wide jobs call the same service functions.

Use the existing `stoa-weekly-report` Lambda as the async report recovery worker before introducing any new AWS service. It already has a 15-minute timeout and the report-generation dependencies/permissions that the API Lambda does not have time to use at incident scale. Add a new event branch in `src/stoa/jobs/weekly_reports.py` for `job: "report_recovery_job"`, have the API Lambda create a durable job record, then invoke `stoa-weekly-report` asynchronously. CDK needs an IAM permission for `stoa-api` to invoke `stoa-weekly-report`; no new table, bucket, queue, Step Functions state machine, or Lambda is justified from the current access patterns.

Immutable audit logs should be append-only DynamoDB items colocated with existing report and job records. Keep the existing mutable `last_operation*`, `resend_*`, and `generation_retry_*` fields on report summary rows because the admin list/detail UI depends on them for fast triage. Add immutable audit events with conditional `PutItem` so every recovery request, claim, result, cancellation, and refusal is preserved even when the report summary changes later.

Production admin browser smoke belongs in the frontend test/deploy surface, but it must verify the deployed backend contract. It should use an existing real admin session or credentials supplied through a secret/manual operator flow, perform read-only UI checks by default, and assert the no-private-artifact contract. Mutation smoke remains a separate approved-fixture workflow.

The Lambda dist guard belongs in both the build pipeline and CDK synth path. The backend/infrastructure GitHub workflows already rebuild `dist`, but local CDK diff/deploy can still package stale `../stoa-backend/dist`. Add a generated build manifest to `dist` and make `StoaApiStack` fail synth/diff/deploy when the manifest hash does not match current backend source and requirements.

## Current Architecture Anchors

| Area | Current Component | Evidence | Implication |
|------|-------------------|----------|-------------|
| API control plane | `src/stoa/routers/admin.py` under `/admin` | Admin report ops list/detail/resend/retry endpoints exist and require `require_role("admin")`. | Extend this router for job/audit endpoints, but extract business logic into services first. |
| Report persistence | `src/stoa/db/repositories/report_repo.py` | Report summaries use `PK=REPORT#{report_id}`, `SK=SUMMARY`; parent/week reads use `GSI-ParentId`; cross-parent admin uses bounded scan. | Reuse single table. Add job/audit item families and repository helpers before considering a new GSI. |
| Report worker | `src/stoa/jobs/weekly_reports.py` | Existing scheduled Lambda discovers pairs and runs generation with 15-minute timeout in CDK. | Add a recovery-job event branch to this Lambda for incident-wide async work. |
| Report pipeline | `src/stoa/services/report_service.py` | Builds payload, generates content, writes S3 artifacts, persists metadata, sends SES. | Async retry jobs should call this same pipeline through a recovery service. |
| Artifact privacy | Admin responses expose booleans, not keys/content | Tests assert no `weekly-reports/`, `json_s3_key`, `html_s3_key`, presigned URLs, or raw HTML. | Job, audit, and smoke responses must preserve metadata-only output. |
| Frontend admin UI | `stoa-frontend/src/pages/admin/ReportOperationsPage.tsx` | Uses React Query hooks over `/admin/reports/ops`, detail, retry, resend, and bulk resend. | Add job/audit UI adjacent to current page rather than replacing current selected actions. |
| Infrastructure | `stoa-infra/stacks/api_stack.py` | `stoa-api` timeout 29s; `stoa-weekly-report` timeout 15m; both package from `../stoa-backend/dist`. | API creates jobs; weekly Lambda processes jobs; CDK dist guard must stop stale local assets. |
| CI/CD | backend and infra deploy workflows | Both GitHub workflows rebuild Lambda `dist`; stale issue came from local CDK deploy. | Keep workflow builds, add manifest verification for local and CI CDK paths. |

## Recommended Component Boundaries

### New Backend Components

| Component | Responsibility | Communicates With |
|-----------|----------------|-------------------|
| `src/stoa/services/report_recovery_service.py` | Shared single-report recovery operations: eligibility, atomic claim, retry generation, resend email, redaction, result model. | `report_repo`, `report_service`, `report_artifact_service`, `notify_service`, audit repository. |
| `src/stoa/services/report_recovery_job_service.py` | Create jobs, resolve candidates from filters, process bounded batches, update counters/checkpoints, handle cancellation and stop conditions. | `report_repo`, recovery service, audit repository, worker invoker. |
| `src/stoa/db/repositories/report_recovery_repo.py` or extended `report_repo.py` | Job summary, job target/result, audit append, cancellation flag, conditional state transitions. | DynamoDB `stoa-main`. |
| `src/stoa/services/lambda_invoker.py` or narrow helper | Invoke `stoa-weekly-report` asynchronously by function name/env var. | boto3 Lambda client; CDK-injected env var. |
| `src/stoa/jobs/report_recovery.py` | Worker entrypoint used by `weekly_reports.handler` for `job=report_recovery_job`. | Job service. |

### Modified Backend Components

| Component | Modification |
|-----------|--------------|
| `src/stoa/routers/admin.py` | Keep existing endpoints but delegate retry/resend/bulk resend to `report_recovery_service`. Add job endpoints and audit endpoints. |
| `src/stoa/jobs/weekly_reports.py` | Add dispatch branch: `if event.get("job") == "report_recovery_job": return report_recovery.run_job(event)`. Preserve existing weekly report and S3 smoke behavior. |
| `src/stoa/db/repositories/report_repo.py` | Add conditional claim helper for resend, job-oriented list helpers if not split into `report_recovery_repo.py`, and optional report audit query helper. |
| `src/stoa/config.py` | Add optional `WEEKLY_REPORT_FUNCTION_NAME` or `REPORT_RECOVERY_WORKER_FUNCTION_NAME`, injected by CDK. |
| Tests | Extend `tests/test_admin_report_ops.py`; add focused tests for job creation, worker processing, cancellation, audit immutability, and no private artifact markers. |

### Modified Frontend Components

| Component | Modification |
|-----------|--------------|
| `stoa-frontend/src/services/admin/adminApi.ts` | Add job create/list/detail/cancel/audit types and functions. Keep current row model. |
| `stoa-frontend/src/hooks/admin/useAdminReportOperations.ts` | Add job React Query hooks and polling while jobs are queued/running/cancellation_requested. |
| `stoa-frontend/src/pages/admin/ReportOperationsPage.tsx` | Add a jobs panel/tab and a read-only audit/history panel. Reuse existing filters and target selection. |
| `stoa-frontend/tests/e2e/admin-report-operations.spec.ts` | Add mocked async job workflow. Add separate production smoke spec for deployed route. |

### Modified Infrastructure / CI Components

| Component | Modification |
|-----------|--------------|
| `stoa-infra/stacks/api_stack.py` | Inject worker function name into `stoa-api`; grant API Lambda `lambda:InvokeFunction` on `stoa-weekly-report`; optionally grant weekly Lambda self-invoke for continuation. Add dist manifest validation before `Code.from_asset`. |
| `stoa-infra/.github/workflows/deploy.yml` | Keep rebuilding backend `dist`; add explicit manifest verification before `cdk diff` and `cdk deploy`. |
| `stoa-backend/.github/workflows/deploy.yml` | Use the same build script/manifest as infra workflow so direct Lambda updates and CDK assets are built identically. |
| New build script | Build Lambda `dist` and write `.stoa-build-manifest.json` with source hash, requirements hash, Python/runtime target, backend git SHA, and build time. |

## DynamoDB Single-Table Shape

Reuse `stoa-main`. Do not add a new table. The existing `GSI-ParentId` remains enough for parent-filtered report discovery. Cross-parent incident jobs can use the existing bounded scan path if the job request includes strict limits and checkpoints. If incident jobs later need recurring broad status/week access at high volume, add a CDK-managed GSI only after measuring scan cost and latency.

### Existing Report Summary

```text
PK = REPORT#{report_id}
SK = SUMMARY
```

Keep using this row for current report state and fast admin list/detail fields:

- `status`, `email_status`
- artifact key fields for backend-only use
- `last_operation`, `last_operation_at`, `last_operation_by`, `last_operation_result`
- retry/resend timestamps
- error class/message fields with redaction before API output

### New Job Summary

Use a direct lookup item:

```text
PK = REPORT_RECOVERY_JOB#{job_id}
SK = SUMMARY
```

Recommended fields:

| Field | Purpose |
|-------|---------|
| `entity_type = "report_recovery_job"` | Allows scan/debug filtering. |
| `job_id` | Stable ID returned to UI. Use timestamp-prefixed UUID/ULID for ordering. |
| `operation` | `retry_generation`, `resend_email`, or future `mixed_recovery`. |
| `status` | `queued`, `running`, `cancellation_requested`, `cancelled`, `completed`, `completed_with_failures`, `failed`. |
| `requested_by`, `requested_at`, `reason` | Operator evidence. `reason` should be required for incident-wide jobs. |
| `filters` | Status/week/parent/student filter snapshot. |
| `limits` | `max_items`, `max_failures`, `deadline_seconds`, `page_limit`. |
| `checkpoint` | Encoded admin page token and counts from the last processed page. |
| `counts` | `seen`, `eligible`, `processed`, `succeeded`, `refused`, `not_found`, `failed`. |
| `started_at`, `updated_at`, `completed_at` | Progress and runbook evidence. |
| `worker_invocations` | Count for continuation detection. |

### New Job List Index Item

For listing recent jobs without a new GSI, write a second summary item:

```text
PK = REPORT_RECOVERY_JOBS
SK = CREATED#{requested_at}#{job_id}
```

This item should duplicate only list-safe fields: `job_id`, `operation`, `status`, counts, `requested_by`, timestamps, and filters. Update it whenever the canonical job summary changes.

### New Job Target / Result Items

```text
PK = REPORT_RECOVERY_JOB#{job_id}
SK = TARGET#{parent_id}#{student_id}#{week_start}
```

Recommended fields:

- `report_id`
- `parent_id`, `student_id`, `week_start`
- `operation`
- `result`: `success`, `refused`, `not_found`, `failed`, `skipped_cancelled`
- `before_status`, `before_email_status`, `after_status`, `after_email_status`
- `error_class`, redacted `detail`
- `attempted_at`, `completed_at`

These drive job detail UI and operator post-incident review without exposing S3 keys or content.

### New Immutable Report Audit Events

Use append-only audit rows under the report partition:

```text
PK = REPORT#{report_id}
SK = AUDIT#{event_at}#{event_id}
```

Write with `ConditionExpression = attribute_not_exists(PK) AND attribute_not_exists(SK)`.

Recommended fields:

- `event_type`: `recovery_requested`, `recovery_claimed`, `recovery_succeeded`, `recovery_refused`, `recovery_failed`, `job_cancel_requested`, `job_cancelled`
- `actor_id`, `actor_role`
- `job_id`, `operation`, `reason`
- `parent_id`, `student_id`, `week_start`
- `before` and `after` status snapshots
- `result`, `error_class`, redacted `detail`
- `request_id` or Lambda AWS request ID when available

For job-level audit views, either duplicate compact audit rows under `PK=REPORT_RECOVERY_JOB#{job_id}`, `SK=AUDIT#{event_at}#{event_id}`, or rely on target/result rows. Duplication is acceptable because it preserves efficient job detail reads without a new GSI.

## API Integration

### Existing Endpoints To Keep

| Endpoint | Current Behavior | v1.6 Change |
|----------|------------------|-------------|
| `GET /admin/reports/ops` | List metadata-only report rows with filters and pagination. | Add optional job action affordances only if cheap; do not include audit histories in list rows. |
| `GET /admin/reports/{parent_id}/{student_id}/{week_start}/ops` | Metadata-only detail and action eligibility. | Include immutable audit summary count or latest audit event metadata if needed; keep private artifact keys out. |
| `POST /admin/reports/{...}/retry-generation` | Synchronous single retry. | Delegate to recovery service and append immutable audit events. |
| `POST /admin/reports/{...}/resend` | Synchronous single resend. | Delegate to recovery service and append immutable audit events. |
| `POST /admin/reports/bulk-resend` | Synchronous selected resend capped at 25. | Keep as the selected-item fast path; append immutable audit per target. |

### New Endpoints

| Endpoint | Purpose | Notes |
|----------|---------|-------|
| `POST /admin/reports/recovery-jobs` | Create an incident-wide async job. | Body should include `operation`, filters, `reason`, `max_items`, `max_failures`; return `202` with `job_id`. |
| `GET /admin/reports/recovery-jobs` | List recent jobs. | Query `PK=REPORT_RECOVERY_JOBS`, capped and newest-first. |
| `GET /admin/reports/recovery-jobs/{job_id}` | Job summary and progress. | Query canonical summary plus first page of target/result rows. |
| `GET /admin/reports/recovery-jobs/{job_id}/results` | Paginated job results. | Query `PK=REPORT_RECOVERY_JOB#{job_id}`, `SK begins_with TARGET#`. |
| `PATCH /admin/reports/recovery-jobs/{job_id}` | Request cancellation. | Only transition `queued/running -> cancellation_requested`; worker performs final stop. |
| `GET /admin/reports/{parent_id}/{student_id}/{week_start}/audit` | Report-specific immutable audit history. | Resolve report, query `PK=REPORT#{report_id}`, `SK begins_with AUDIT#`; metadata-only response. |

### Recovery Job Request Contract

```json
{
  "operation": "resend_email",
  "filters": {
    "status": "email_failed",
    "week_start": "2026-06-01",
    "parent_id": null,
    "student_id": null
  },
  "reason": "SES incident recovery INC-1234",
  "max_items": 500,
  "max_failures": 25,
  "page_limit": 50
}
```

Rules:

- `reason` is required for async jobs.
- `max_items`, `max_failures`, and `page_limit` are mandatory bounded execution controls.
- `operation=retry_generation` requires `status=generation_failed`.
- `operation=resend_email` requires `status=email_failed` or `email_status=failed`.
- Responses must never include private S3 keys, raw artifact content, presigned URLs, or direct S3 markers.

## Async Worker Data Flow

```text
Admin UI
  -> POST /admin/reports/recovery-jobs
  -> stoa-api validates admin role, filters, reason, bounds
  -> writes job SUMMARY + job list item + job requested audit
  -> invokes stoa-weekly-report asynchronously with {"job":"report_recovery_job","job_id":"..."}
  -> returns 202

stoa-weekly-report
  -> weekly_reports.handler dispatches to report_recovery.run_job
  -> conditionally transitions job queued/cancellation_requested-safe state to running
  -> resolves candidates through report_repo.list_reports_for_admin
  -> per target:
       checks cancellation and stop limits
       validates eligibility
       atomically claims report operation
       calls shared recovery service
       writes immutable audit event
       writes TARGET result
       updates job counts/checkpoint
  -> completes, fails, cancels, or self-invokes continuation if bounded page/deadline reached

Admin UI
  -> polls GET /admin/reports/recovery-jobs/{job_id}
  -> displays progress, stop reason, counts, and metadata-only per-target results
```

### Bounded Execution Rules

The worker must stop when any condition is true:

- job status becomes `cancellation_requested`
- `max_items` reached
- `max_failures` reached
- Lambda safety deadline is near, e.g. stop with at least 60 seconds remaining
- no next page/candidates remain
- report list pagination token is invalid
- repeated AWS access/permission error occurs

For continuation, prefer a self-invocation of the same `stoa-weekly-report` Lambda with the same `job_id` and updated checkpoint. This requires a CDK-granted `lambda:InvokeFunction` permission for the weekly Lambda role on itself. If self-invocation is not added in the first phase, cap `max_items` conservatively so one 15-minute worker invocation is enough.

### Atomic Claims

The current retry path already has `try_start_generation_retry(...)`. Incident-wide resend needs the same protection. Add a narrow conditional helper such as `try_start_email_resend(report_id, operator, attempted_at, job_id=None)` that only transitions eligible failed-delivery reports to an in-progress operation. Without this, two admins or a job plus a single resend can race and duplicate emails.

Recommended claim fields:

- `last_operation = "resend_email"` or `"retry_generation"`
- `last_operation_result = "in_progress"`
- `last_operation_job_id = job_id`
- `last_operation_by = operator`
- `last_operation_at = attempted_at`
- operation-specific attempted timestamp

## Frontend Integration

Keep `/admin/report-operations` as the first screen. Add operational depth, not a separate admin product area.

Recommended layout:

- **Reports tab/panel:** existing filters, table, inspect, retry, resend, selected bulk resend.
- **Recovery jobs tab/panel:** create async job from current filters, require reason and bounds, show recent jobs and progress.
- **Job detail drawer/panel:** counts, status, stop reason, result table, cancellation button when running.
- **Audit panel in report detail:** latest immutable events for selected report, with actor, reason, operation, result, and timestamps.

Polling:

- Poll job detail every 5-10 seconds while `queued`, `running`, or `cancellation_requested`.
- Stop polling for terminal states.
- Invalidate report operations list after job completion or cancellation.

Privacy:

- Reuse existing frontend no-private-marker tests.
- Never render raw backend error strings without backend redaction.
- Do not show S3 keys, object URLs, presigned URLs, or artifact content in audit/job result views.

## Production Admin Browser Smoke

Add a frontend Playwright production smoke that uses deployed URLs and a real admin session without creating production admin accounts.

Recommended structure:

| Item | Recommendation |
|------|----------------|
| Test file | `stoa-frontend/tests/e2e/admin-report-operations.production.spec.ts` or `tests/smoke/production-admin-report-operations.spec.ts`. |
| Auth | Use an existing admin account via secret-backed credentials or a pre-generated Playwright `storageState` supplied by the operator. Do not create/delete Cognito users. |
| Scope | Read-only by default: login/session validation, route load, filter submit, list/detail response, no private artifact markers. |
| Mutation | Separate manual smoke using approved non-customer fixture only; do not mix with browser route smoke. |
| Execution | Manual GitHub workflow or local operator command with `PRODUCTION_SMOKE=true`, `BASE_URL=https://app.stoaedu.ch`, `API_BASE_URL=https://api.stoaedu.ch`. |
| Evidence | Capture URL, bundle identifier, API URL, admin user identifier hash/email domain only if needed, screenshots/traces on failure, and body text privacy assertion. |

This smoke should prove the real browser/admin route works with production auth and backend responses. It should not become a broad incident recovery mutator.

## CDK / CI Lambda Dist Guard

### Current Risk

`stoa-infra/stacks/api_stack.py` packages both `stoa-api` and `stoa-weekly-report` from `../stoa-backend/dist`. GitHub workflows rebuild this directory, but local CDK deploys can still synthesize and deploy stale assets. v1.5 already observed stale `dist` temporarily rolling production Lambda code back.

### Recommended Guard

Add a backend build script that writes:

```text
dist/.stoa-build-manifest.json
```

Manifest fields:

- `source_hash`: hash of `src/stoa/**/*.py`
- `requirements_hash`: hash of `requirements.txt` and optionally `pyproject.toml`
- `python_version`: `3.12`
- `platform`: `manylinux2014_aarch64`
- `architecture`: `arm64`
- `backend_git_sha`
- `built_at`

Add a verifier used by CDK and CI:

```text
verify current src/requirements hash == dist/.stoa-build-manifest.json
verify dist/stoa/main.py exists
verify dist/stoa/jobs/weekly_reports.py exists
verify dist/stoa/services/report_service.py exists
```

Then call the verifier:

- in `stoa-infra/stacks/api_stack.py` before `lambda_.Code.from_asset("../stoa-backend/dist")`
- in `stoa-infra/.github/workflows/deploy.yml` after `Build Lambda dist` and before `CDK Diff` / `CDK Deploy`
- in `stoa-backend/.github/workflows/deploy.yml` before zipping direct Lambda packages

Synth-time failure in CDK is the important part because it prevents local `cdk diff` and `cdk deploy` from silently using stale assets.

## Suggested Phase Order

1. **Architecture Grounding and Service Extraction**
   - Extract current retry/resend logic from `admin.py` into `report_recovery_service.py`.
   - Preserve existing endpoint behavior and tests.
   - Add immutable audit append helper and write audit for existing single-report actions.
   - Rationale: Async jobs must reuse proven single-target operations and audit must cover both old and new workflows.

2. **DynamoDB Job/Audit Persistence**
   - Add job summary/list/result/audit item shapes and repository helpers.
   - Add conditional resend claim.
   - Add tests for append-only audit, job state transitions, cancellation request, and token/checkpoint persistence.
   - Rationale: Persistence and atomicity are prerequisites for incident-wide work.

3. **Async Worker and Admin Job API**
   - Add job create/list/detail/cancel endpoints.
   - Add worker event branch in `weekly_reports.handler`.
   - Add API Lambda async invocation of weekly Lambda and CDK invoke permission.
   - Add bounded processing, progress updates, stop conditions, and no-private-output tests.
   - Rationale: This is the core incident-wide capability and touches backend plus infra.

4. **Frontend Job and Audit UI**
   - Add job creation/progress/cancel/result surfaces to `/admin/report-operations`.
   - Add audit history panel.
   - Add mocked e2e coverage and no-private-marker assertions.
   - Rationale: UI depends on the API contract and job states being stable.

5. **Production Browser Smoke**
   - Add read-only production Playwright smoke with real admin session support.
   - Run against deployed UI/API and record evidence.
   - Rationale: It depends on the deployed UI/API and should validate the completed admin surface.

6. **Lambda Dist Guard**
   - Can be done early if infra deployment is needed for Phase 3, but should be complete before any CDK deploy that modifies Lambda asset stacks.
   - Add build manifest and CDK synth-time validation.
   - Rationale: Prevents the v1.5 stale package failure mode during this milestone's infra changes.

If the roadmap wants to reduce deployment risk, make Phase 6 the first infra-touching phase, then proceed to Phase 3. The hard dependency is: no CDK deploy for async worker permissions should happen without the dist guard in place.

## Anti-Patterns To Avoid

### Adding Step Functions/SQS Before Proving Need

The current CDK already has a long-running weekly report Lambda and DynamoDB state. A new orchestrator may become useful later, but v1.6 can start with durable job records plus async invocation. Add new AWS resources only if measured worker continuation, retries, or visibility cannot be satisfied with the existing Lambda/table pattern.

### Running Incident-Wide Recovery In The API Request

`stoa-api` is behind API Gateway and configured with a 29-second Lambda timeout. Incident-wide retry/resend in that request path will either time out or force unsafe small batches. The API should create/cancel/read jobs; the worker should process jobs.

### Mutable-Only Audit

The current report summary audit fields are useful triage metadata but are overwritten by later operations. They are not evidence. Keep them, but add append-only audit rows for accountability.

### Non-Atomic Resend

Current resend reads the report and sends email without an atomic in-progress claim. That is acceptable for one selected admin action but unsafe for incident-wide jobs. Add a conditional claim before any async resend.

### Exposing Artifact Keys In Job/Audit Results

Job/audit views can accidentally leak backend-only S3 keys through captured error messages. Continue backend redaction and frontend privacy assertions for every new response shape.

### CDK Comment-Only Packaging Warnings

The runbook warning is not enough. The guard must fail `cdk diff`/`cdk deploy` when `dist` is stale or missing required modules.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Existing integration points | HIGH | Verified against required files plus `report_service.py`, `weekly_reports.py`, frontend admin API/page/hooks, tests, and CDK stacks. |
| Single-table job/audit design | HIGH | Uses primary-key item families and existing report partitions; no new GSI needed for initial access patterns. |
| Existing weekly Lambda as worker | MEDIUM-HIGH | CDK confirms 15-minute Lambda and required report permissions; needs implementation/testing for async invocation, continuation, and cancellation behavior. |
| Production browser smoke shape | MEDIUM-HIGH | Frontend Playwright coverage exists; exact production auth secret/session mechanism should be chosen with operators. |
| Dist guard | HIGH | Failure mode is documented in v1.5; manifest plus synth-time verification directly addresses it. |

## Sources

- `.planning/PROJECT.md`
- `.planning/MILESTONES.md`
- `.planning/milestones/v1.5-MILESTONE-AUDIT.md`
- `.planning/milestones/v1.5-phases/32-operations-runbook-observability-and-milestone-closeout/32-OPERATIONS-RUNBOOK.md`
- `src/stoa/routers/admin.py`
- `src/stoa/db/repositories/report_repo.py`
- `src/stoa/services/report_service.py`
- `src/stoa/jobs/weekly_reports.py`
- `src/stoa/deps.py`
- `tests/test_admin_report_ops.py`
- `/Users/zhdeng/stoa-infra/stacks/api_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/database_stack.py`
- `/Users/zhdeng/stoa-infra/.github/workflows/deploy.yml`
- `/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts`
- `/Users/zhdeng/stoa-frontend/src/hooks/admin/useAdminReportOperations.ts`
- `/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx`
- `/Users/zhdeng/stoa-frontend/tests/e2e/admin-report-operations.spec.ts`
