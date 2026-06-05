# Phase 37 Operations Runbook: v1.6 Report Recovery

## Scope

This runbook covers the v1.6 hardened report recovery workflow:

- Inspect report operation metadata.
- Inspect append-only report and job audit evidence.
- Preview bounded async `email_failed` resend jobs.
- Start async resend jobs only after preview review and operator reason.
- Poll job progress and per-target results.
- Request cooperative cancellation.
- Investigate stalled jobs, repeated failures, SES/Lambda/DynamoDB issues, and Lambda package provenance.

Production identifiers:

| Item | Value |
|------|-------|
| API URL | `https://api.stoaedu.ch` |
| Frontend route | `https://app.stoaedu.ch/admin/report-operations` |
| AWS profile used for v1.6 evidence | `stoa-prod-admin` |
| AWS region | `eu-central-2` |
| API Lambda | `stoa-api` |
| Weekly report Lambda | `stoa-weekly-report` |
| DynamoDB table | `stoa-main` |
| Reports bucket | `stoa-reports-562923011260` |
| Production admin credential path | AWS Secrets Manager `stoa/production/admin/stoaedu.ad@gmail.com` |

## Operator Workflow

### 1. Open Admin Report Operations

Open:

```text
https://app.stoaedu.ch/admin/report-operations
```

Use a real long-lived admin account. Do not create temporary production admin accounts for smoke or operations.

Privacy expectation:

- UI and API responses may show report metadata, status, counters, artifact availability booleans, redacted errors, and audit labels.
- UI and API responses must not show `weekly-reports/`, `json_s3_key`, `html_s3_key`, `s3_key`, public S3 URLs, presigned URLs, auth tokens, raw report HTML, or raw report JSON.

### 2. Preview An Async Resend Job

Use the async resend panel on `/admin/report-operations`.

Before preview:

- Select an explicit status scope, normally `email_failed`.
- Add a week when possible.
- Add parent/student scope if the incident is narrow.
- Enter an operator reason that names the incident or operational context.

Expected preview evidence:

- Operation is `resend_email`.
- Eligible/refused/missing counts are visible.
- Sample rows are metadata-only.
- No private artifact markers appear.

Do not start the job if:

- Counts are unexpectedly broad.
- Refused rows indicate the filter is wrong.
- The reason is missing or vague.
- The UI/API exposes private artifact markers.

### 3. Start A Bounded Async Resend Job

Start only after preview review.

Semantics:

- Target set is snapshotted at job creation.
- Worker re-reads and rechecks eligibility before each target.
- Worker conditionally claims resend before SES side effects.
- Cancellation stops future targets; it does not roll back completed sends.
- Current MVP caps are conservative: max 25 targets and max 5 scan pages.

### 4. Monitor Job Progress

Use the Recovery jobs panel.

Track:

- `queued`
- `running`
- `cancellation_requested`
- `cancelled`
- `completed`
- `completed_with_failures`
- `failed`

Review counters:

- pending
- attempted
- success
- refused
- not found
- failed
- skipped cancelled

Stop and escalate if:

- Failure count grows for the same root cause.
- SES or Lambda access errors appear.
- Job remains queued/running longer than expected without progress.
- Any result or audit response exposes private artifact markers.

### 5. Cancel A Job

Use cancellation only when the job is `queued`, `running`, or `cancellation_requested`.

Cancellation guarantees:

- It records a cancellation request.
- It stops future target attempts when the worker observes the request.
- It does not recall emails already sent.
- It does not roll back already completed target outcomes.

### 6. Inspect Audit Evidence

Use report and job audit timelines in the UI, or call admin-only audit APIs with a real admin token.

Audit records are append-only application-level evidence. They are not compliance-grade WORM storage.

Expected audit fields include:

- actor/operator
- action
- reason
- target identifiers
- before/after metadata
- result
- redacted error class/message
- request/job correlation
- source surface
- timestamp

## Observability

### Lambda State

```bash
AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 aws lambda get-function-configuration \
  --function-name stoa-api \
  --region eu-central-2 \
  --query '{FunctionName:FunctionName,LastModified:LastModified,CodeSha256:CodeSha256,State:State,LastUpdateStatus:LastUpdateStatus,Runtime:Runtime,Architectures:Architectures}'

AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 aws lambda get-function-configuration \
  --function-name stoa-weekly-report \
  --region eu-central-2 \
  --query '{FunctionName:FunctionName,LastModified:LastModified,CodeSha256:CodeSha256,State:State,LastUpdateStatus:LastUpdateStatus,Runtime:Runtime,Architectures:Architectures}'
```

Expected:

- `State=Active`
- `LastUpdateStatus=Successful`
- `Runtime=python3.12`
- `Architectures=["arm64"]`

### API Health And Auth Gate

```bash
curl -i -sS https://api.stoaedu.ch/health
curl -i -sS https://api.stoaedu.ch/admin/reports/recovery-jobs
```

Expected:

- Health returns 200 and `{"status":"ok","version":"0.1.0"}`.
- Unauthenticated admin endpoint returns 401.

### CloudWatch Logs

Recent API recovery events:

```bash
aws logs start-query \
  --log-group-name /aws/lambda/stoa-api \
  --start-time "$(date -u -v-2H +%s)" \
  --end-time "$(date -u +%s)" \
  --query-string 'fields @timestamp, @message | filter @message like /recovery|resend|audit|AccessDenied|ClientError|weekly-reports/ | sort @timestamp desc | limit 100' \
  --region eu-central-2 \
  --profile stoa-prod-admin
```

Weekly worker events:

```bash
aws logs start-query \
  --log-group-name /aws/lambda/stoa-weekly-report \
  --start-time "$(date -u -v-24H +%s)" \
  --end-time "$(date -u +%s)" \
  --query-string 'fields @timestamp, @message | filter @message like /report_recovery|recovery job|resend|cancel|failed/ | sort @timestamp desc | limit 100' \
  --region eu-central-2 \
  --profile stoa-prod-admin
```

### DynamoDB Investigation

Use only for backend/operator investigation.

Job summary item:

```text
PK=REPORT_RECOVERY_JOB#{job_id}
SK=SUMMARY
```

Job target items:

```text
PK=REPORT_RECOVERY_JOB#{job_id}
SK=TARGET#{...}
```

Report audit items:

```text
PK=REPORT#{report_id}
SK=AUDIT#{event_at}#{event_id}
```

Job listing index item:

```text
PK=REPORT_RECOVERY_JOBS
SK=CREATED#{created_at}#{job_id}
```

Do not share raw DynamoDB records with customers.

### Lambda Dist Guard

Before CDK diff/deploy from infra:

```bash
cd /Users/zhdeng/stoa-backend
python scripts/build_lambda_dist.py --verify-only

cd /Users/zhdeng/stoa-infra
AWS_PROFILE=stoa-prod-admin AWS_REGION=eu-central-2 uv run cdk diff StoaApiStack --context env=dev
```

Expected:

- Dist verification passes.
- CDK diff reports 0 stacks with differences unless an intentional release is in progress.

Emergency override:

- `ALLOW_STALE_LAMBDA_DIST=1` exists only for explicit emergency rollback.
- Do not set it in normal synth/diff/deploy workflows.
- Record who approved the override and why.

## Escalation

Escalate to engineering when any condition is true:

- Admin authorization fails open or non-admin users can access recovery operations.
- Any UI/API/smoke artifact exposes private S3 keys, presigned URLs, raw HTML, raw JSON, or auth tokens.
- Async job target counts exceed the expected incident scope.
- Multiple targets fail for the same root cause.
- SES returns access, identity, quota, or reputation errors.
- Worker jobs stall without progress.
- CDK diff shows unexpected Lambda/IAM/DynamoDB/S3 changes.
- Lambda CodeSha differs unexpectedly between `stoa-api` and `stoa-weekly-report` after a backend deploy.

## Credential Ownership

The production admin credential for Phase 36/37 verification is stored at:

```text
AWS Secrets Manager: stoa/production/admin/stoaedu.ad@gmail.com
```

Operational follow-up:

- Assign owner for this account.
- Rotate the password after handoff if required by STOA policy.
- Limit secret read access to operators who need production admin smoke or support access.
- Do not commit storage state, access tokens, passwords, screenshots with secrets, or trace artifacts containing auth state.
