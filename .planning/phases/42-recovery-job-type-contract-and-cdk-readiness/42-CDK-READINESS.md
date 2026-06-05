# Phase 42 CDK Readiness

**Status:** Existing resources are sufficient for v1.8 MVP.

## Resource Ledger

| Resource | Evidence | v1.8 consequence |
|----------|----------|------------------|
| API Lambda `stoa-api` | `/Users/zhdeng/stoa-infra/stacks/api_stack.py` defines `StoaApiFunction`. | Hosts preview/create/list/result/audit APIs. |
| Weekly Lambda `stoa-weekly-report` | `api_stack.py` defines `StoaWeeklyReportFunction` with handler `stoa.jobs.weekly_reports.handler`. | Executes async generation retry jobs. |
| API-to-weekly invocation | `self.weekly_report_function.grant_invoke(self.api_function)`. | Existing async invoke path supports new event type. |
| DynamoDB table | `database_stack.py` defines `stoa-main` with PK/SK and PAY_PER_REQUEST. | Existing job/target/audit records fit same partition shape. |
| GSI-ParentId | `database_stack.py` defines parent/week index. | Parent/week filtered previews can reuse current report listing. |
| Report S3 bucket permissions | `api_stack.py` grants report artifact read/write to weekly Lambda. | Existing retry service can store generated report artifacts. |
| SES permission | `api_stack.py` grants weekly Lambda `ses:SendEmail` and `ses:SendRawEmail`. | Retry service can send regenerated weekly report email. |
| Bedrock permission | `api_stack.py` grants weekly Lambda `bedrock:InvokeModel`. | Retry service can regenerate report content. |
| Cognito admin auth | Existing backend `require_role("admin")`. | API remains admin-only. |

## No-New-Infrastructure Decision

No CDK change is required for v1.8 unless implementation or tests prove one of these constraints fails:

- Existing Lambda timeout cannot complete bounded target sets.
- Existing DynamoDB access pattern cannot preview bounded `generation_failed` targets.
- Existing API-to-weekly invoke permission cannot dispatch the new event.
- Existing audit/job item shapes cannot distinguish job types.

Current evidence does not show any of those failures.

## Known Residual Risk

Cross-parent previews still rely on the existing bounded admin scan. v1.8 keeps conservative target/page caps and defers new GSI/table decisions until real usage proves the scan path insufficient.

