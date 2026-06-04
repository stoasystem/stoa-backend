# Phase 32 Operations Runbook: Report Recovery

## Scope

This runbook covers the production admin report operations workflow shipped in v1.4 and live-verified in v1.5:

- Inspect report operation metadata.
- Retry one `generation_failed` report.
- Resend one `email_failed` report.
- Bulk resend selected `email_failed` reports.
- Investigate delivery or artifact failures.
- Roll back backend, frontend, or infra changes.

Production identifiers:

| Item | Value |
|------|-------|
| API URL | `https://api.stoaedu.ch` |
| Frontend route | `https://app.stoaedu.ch/admin/report-operations` |
| AWS profile | `stoa` |
| AWS region | `eu-central-2` |
| API Lambda | `stoa-api` |
| Weekly report Lambda | `stoa-weekly-report` |
| DynamoDB table | `stoa-main` |
| Reports bucket | `stoa-reports-562923011260` |
| SES identity | `stoaedu.ch` |

## Operator Workflow

### 1. Inspect The Admin UI

Open:

```text
https://app.stoaedu.ch/admin/report-operations
```

Use filters to narrow by status, parent id, student id, and week. A report row is actionable only when the backend detail response shows the corresponding action enabled.

Privacy expectation:

- UI and API responses may show artifact availability booleans.
- UI and API responses must not show `weekly-reports/`, `json_s3_key`, `html_s3_key`, `s3_key`, public S3 URLs, presigned URLs, or raw HTML/JSON content.

### 2. Inspect A Report Detail

Use the UI detail panel, or call the backend with an admin token:

```bash
curl -sS "https://api.stoaedu.ch/admin/reports/{parent_id}/{student_id}/{week_start}/ops" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Confirm before acting:

- `parent_id`, `student_id`, and `week_start` match the intended report.
- `status` and `email_status` match the intended recovery action.
- `actions.retry_generation.enabled` or `actions.resend_email.enabled` is true.
- Artifact booleans match expectations.
- No private artifact keys or direct S3 URLs are present.

### 3. Retry A Generation Failure

Use only when:

- `status` is `generation_failed`.
- Detail response shows `actions.retry_generation.enabled=true`.
- The report belongs to the intended parent/student/week.

Endpoint:

```bash
curl -sS -X POST \
  "https://api.stoaedu.ch/admin/reports/{parent_id}/{student_id}/{week_start}/retry-generation" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Expected success:

- HTTP 200.
- `operation=retry_generation`.
- `operation_result=success`.
- Terminal status is usually `email_sent` / `sent`; if SES send fails, the generated artifacts may exist but status may become `email_failed`.
- Follow-up detail shows `last_operation=retry_generation`, `last_operation_by`, `last_operation_at`, and `last_operation_result`.

Stop and escalate if:

- HTTP 409: report is no longer `generation_failed` or retry is already in progress.
- HTTP 502: generation pipeline failed.
- Response contains private artifact keys or direct S3 URL markers.
- Generated report id does not match the original report id.

### 4. Resend One Failed Email

Use only when:

- `status` is `email_failed` or `email_status` is `failed`.
- Detail response shows `actions.resend_email.enabled=true`.
- `html_available=true`.
- `parent_email` is expected.

Endpoint:

```bash
curl -sS -X POST \
  "https://api.stoaedu.ch/admin/reports/{parent_id}/{student_id}/{week_start}/resend" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Expected success:

- HTTP 200.
- `operation=resend_email`.
- `operation_result=success`.
- `status=email_sent`.
- `email_status=sent`.
- Follow-up detail shows `resend_attempted_at`, `resend_completed_at`, and `last_operation_result=success`.

Stop and escalate if:

- HTTP 409: report delivery is not failed.
- HTTP 422: report is missing email or HTML artifact metadata.
- HTTP 502: SES or artifact read failed.
- Repeated resend attempts fail for the same parent/student/week.

### 5. Bulk Resend Selected Failed Emails

Use only for a bounded set of selected reports. The API limit is 25 items.

Endpoint:

```bash
curl -sS -X POST "https://api.stoaedu.ch/admin/reports/bulk-resend" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reports": [
      {"parent_id":"parent-id","student_id":"student-id","week_start":"2026-06-01"}
    ]
  }'
```

Interpret per-item results:

| Result | Meaning | Action |
|--------|---------|--------|
| `success` | Resend completed and report moved to `email_sent` / `sent`. | No further action. |
| `refused` | Report exists but is not eligible for resend. | Inspect detail; do not force resend. |
| `not_found` | No matching report. | Re-check parent/student/week identifiers. |
| `failed` | Artifact read or SES send failed. | Inspect logs and SES state; retry only after cause is understood. |

Stop and escalate if:

- More than one item fails for the same root cause.
- Any item exposes private artifact details in response text.
- The batch includes unknown customer data not explicitly selected by an operator.

## Observability

### Lambda Health

```bash
aws lambda get-function-configuration \
  --function-name stoa-api \
  --region eu-central-2 \
  --profile stoa \
  --query '{LastModified:LastModified,CodeSha256:CodeSha256,State:State,LastUpdateStatus:LastUpdateStatus}'

aws lambda get-function-configuration \
  --function-name stoa-weekly-report \
  --region eu-central-2 \
  --profile stoa \
  --query '{LastModified:LastModified,CodeSha256:CodeSha256,State:State,LastUpdateStatus:LastUpdateStatus}'
```

Expected:

- `State=Active`
- `LastUpdateStatus=Successful`

### API Health

```bash
curl -sS https://api.stoaedu.ch/health
```

Expected:

```json
{"status":"ok","version":"0.1.0"}
```

### CloudWatch Logs

Recent report recovery errors:

```bash
aws logs start-query \
  --log-group-name /aws/lambda/stoa-api \
  --start-time "$(date -u -v-2H +%s)" \
  --end-time "$(date -u +%s)" \
  --query-string 'fields @timestamp, @message | filter @message like /report|resend|retry|SendEmail|weekly-reports|ClientError|AccessDenied/ | sort @timestamp desc | limit 50' \
  --region eu-central-2 \
  --profile stoa
```

Weekly report job errors:

```bash
aws logs start-query \
  --log-group-name /aws/lambda/stoa-weekly-report \
  --start-time "$(date -u -v-24H +%s)" \
  --end-time "$(date -u +%s)" \
  --query-string 'fields @timestamp, @message | filter @message like /Weekly report|email failed|report_id|error_class/ | sort @timestamp desc | limit 100' \
  --region eu-central-2 \
  --profile stoa
```

Use `aws logs get-query-results --query-id <id>` to read results.

### SES Delivery Investigation

Check that `stoa-api` and `stoa-weekly-report` roles have send permission for `stoaedu.ch` before investigating application behavior.

```bash
aws ses get-identity-verification-attributes \
  --identities stoaedu.ch \
  --region eu-central-2 \
  --profile stoa
```

If sends fail with `AccessDenied`, check the `StoaApiStack` IAM policy first. Phase 31 required `stoa-api` to have:

```text
ses:SendEmail
ses:SendRawEmail
arn:aws:ses:eu-central-2:562923011260:identity/stoaedu.ch
```

### DynamoDB Report Lookup

If you know the report id:

```bash
aws dynamodb get-item \
  --table-name stoa-main \
  --key '{"PK":{"S":"REPORT#weekly-report-{parent_id}-{student_id}-{week_start}"},"SK":{"S":"SUMMARY"}}' \
  --region eu-central-2 \
  --profile stoa
```

Inspect:

- `status`
- `email_status`
- `last_operation`
- `last_operation_result`
- `generation_error_class`
- `email_error_class`
- artifact fields only for backend investigation, not for frontend exposure.

### S3 Artifact Checks

Use only for backend/operator investigation:

```bash
aws s3api head-object \
  --bucket stoa-reports-562923011260 \
  --key weekly-reports/{parent_id}/{student_id}/{week_start}/report.html \
  --region eu-central-2 \
  --profile stoa
```

Do not share S3 keys, object URLs, or object contents with customers.

### CDK Drift

Run from `/Users/zhdeng/stoa-infra`:

```bash
uv run cdk diff StoaApiStack --profile stoa --context env=dev
```

Expected after v1.5 close:

- 0 stacks with differences.

Important packaging warning:

- `StoaApiStack` packages Lambda code from `../stoa-backend/dist`.
- Rebuild backend `dist` from current source before any CDK deploy that touches Lambda assets.
- A stale `dist` can overwrite production Lambda code with older endpoints and old response shapes.

## Rollback

### Backend Lambda Rollback

Use when backend endpoints regress, response privacy breaks, or Lambda code is stale.

1. Identify the last known-good backend commit and package.
2. Rebuild Lambda package from that commit.
3. Update both Lambdas or run the backend deploy workflow from that commit.
4. Wait for both functions:

```bash
aws lambda wait function-updated --function-name stoa-api --region eu-central-2 --profile stoa
aws lambda wait function-updated --function-name stoa-weekly-report --region eu-central-2 --profile stoa
```

5. Confirm API health and admin report ops response shape.

### Frontend Rollback

Use when `/admin/report-operations` serves stale or broken UI.

1. Re-run frontend deploy workflow from the last known-good frontend commit.
2. Confirm `VITE_API_BASE_URL=https://api.stoaedu.ch`.
3. Confirm demo surfaces are disabled.
4. Confirm CloudFront invalidation completes.
5. Re-check the production route and bundle markers.

### Infra Rollback

Use when CDK diff/deploy introduces unexpected IAM, bucket, route, or DynamoDB drift.

1. Stop live recovery mutation work.
2. Restore the last known-good infra commit.
3. Run `uv run cdk diff StoaApiStack --profile stoa --context env=dev`.
4. Deploy only after the diff is understood.
5. Re-run Lambda state checks and API health.

## Escalation Checklist

Escalate to engineering when any condition is true:

- Admin or non-admin authorization behavior changes unexpectedly.
- API/UI exposes private report artifact keys, raw HTML/JSON, public S3 URLs, presigned URLs, or direct S3 markers.
- Retry generation fails twice for the same report.
- Single resend or bulk resend returns repeated `failed` results for the same cause.
- SES returns `AccessDenied`, identity verification errors, or sending quota errors.
- S3 artifact state conflicts with report metadata.
- CDK diff shows unexpected IAM, S3, API Gateway, or DynamoDB changes.
- Lambda state is not `Active` or update status is not `Successful`.
- Cleanup of any smoke fixture fails.

## Known Limits

- Bulk resend is synchronous and capped at 25 selected reports per request.
- There is no incident-wide async recovery job yet.
- Report recovery audit fields are mutable fields on the report record, not an immutable audit log.
- Operators cannot edit report content through this workflow.
- PDF and multilingual report delivery are out of scope.
- Billing-gated report access remains future product work.

