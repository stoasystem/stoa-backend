# Phase 6: CDK Report Automation Foundation - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning

<domain>

## Phase Boundary

This phase delivers CDK-defined weekly report automation infrastructure before backend report generation code depends on it. It should wire a separate scheduled Lambda handler, reports bucket access, DynamoDB/Bedrock/SES permissions, EventBridge Scheduler invocation, retry/failure handling, and CloudWatch visibility.

</domain>

<decisions>

## Implementation Decisions

### Infrastructure Boundary

- Implement all AWS resource changes in `/Users/zhdeng/stoa-infra` CDK.
- Do not create or assume manually provisioned AWS resources.
- Prefer a separate scheduled Lambda handler for weekly reports rather than invoking the Mangum API handler with scheduled events.
- Reuse existing DynamoDB table, reports S3 bucket, SES identity, EventBridge schedule group, Bedrock permissions model, and monitoring stack where possible.

### Lambda Shape

- The report Lambda should reuse the backend deployment artifact but expose a normal scheduled-event handler such as `stoa.jobs.weekly_reports.handler`.
- CDK should pass the existing table name, reports bucket name, Cognito/client settings if needed by future report code, and the Bedrock model ID through environment variables.
- Permissions should be scoped through existing CDK resource grants where possible, with IAM policy statements only where service-level permissions require them.

### Scheduling and Operations

- EventBridge Scheduler should target the report Lambda directly.
- Retry/failure behavior should be CDK-defined, either through scheduler retry policy, DLQ/failure destination, or the closest current CDK-supported equivalent.
- Monitoring should make report Lambda failures visible through CloudWatch alarms or dashboard widgets.

### the agent's Discretion

All remaining implementation choices are at the agent's discretion, provided they preserve the non-negotiable milestone constraints and avoid manual AWS setup.

</decisions>

<code_context>

## Existing Code Insights

### Reusable Assets

- `/Users/zhdeng/stoa-infra/stacks/storage_stack.py` already creates `self.reports_bucket` as a private retained S3 bucket.
- `/Users/zhdeng/stoa-infra/stacks/database_stack.py` provides the shared DynamoDB table consumed by `ApiStack`.
- `/Users/zhdeng/stoa-infra/stacks/notification_stack.py` already creates `self.teacher_queue` and `StoaScheduleGroup`.
- `/Users/zhdeng/stoa-infra/stacks/api_stack.py` creates `self.api_function`, grants table/image/teacher queue permissions, and adds Bedrock/Rekognition/Cognito IAM policies.
- `/Users/zhdeng/stoa-infra/stacks/monitoring_stack.py` currently accepts only the API Lambda and adds API alarms/dashboard widgets.

### Established Patterns

- CDK stacks are small Python classes under `/Users/zhdeng/stoa-infra/stacks/`.
- `app.py` instantiates stacks and passes concrete resource objects between them.
- Lambda deployment code uses `lambda_.Code.from_asset("../stoa-backend/dist")`.
- Runtime is Python 3.12 on ARM64 in `eu-central-2`.
- Existing service permissions use CDK grants for resource-owned permissions and `iam.PolicyStatement` for Bedrock/Rekognition/Cognito service permissions.

### Integration Points

- `ApiStack` needs access to `storage.reports_bucket` if it remains responsible for function resource creation.
- `NotificationStack` can either keep scheduler group-only ownership or receive the report Lambda to create the schedule target.
- `MonitoringStack` needs the report Lambda if it should create report job alarms/dashboard widgets.
- Backend already has `Settings.s3_reports_bucket`, so CDK env injection should use `S3_REPORTS_BUCKET`.

</code_context>

<specifics>

## Specific Ideas

- Keep schedule invocation off API Gateway/Mangum.
- Store generated reports before email completion in later phases, so Phase 6 must make reports bucket access available.
- Prefer explicit CDK wiring over comments such as "target injected after deploy."

</specifics>

<deferred>

## Deferred Ideas

- Backend `stoa.jobs.weekly_reports.handler` implementation belongs to later phases.
- Report aggregation, Bedrock prompt/JSON parsing, S3 artifact writes, SES email status updates, and frontend display are out of scope for Phase 6 unless a lightweight placeholder is necessary to satisfy Lambda handler packaging.

</deferred>
