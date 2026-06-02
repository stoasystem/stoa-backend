# Phase 1 Infrastructure Audit

**Milestone:** Parent Portal Real Data Integration
**Phase:** 1 - Infrastructure and Contract Grounding
**Requirements covered:** INFRA-01, INFRA-02, INFRA-03
**Status:** Complete with one CDK prerequisite for report bucket runtime access

## Source Scope

This audit uses the current source files as the authority:

| Area | Source |
|------|--------|
| DynamoDB table and GSIs | `/Users/zhdeng/stoa-infra/stacks/database_stack.py` |
| Cognito user pool and app clients | `/Users/zhdeng/stoa-infra/stacks/auth_stack.py` |
| S3 image/report buckets | `/Users/zhdeng/stoa-infra/stacks/storage_stack.py` |
| Lambda, API Gateway, authorizer, env vars, IAM grants | `/Users/zhdeng/stoa-infra/stacks/api_stack.py` |
| SQS, SES, schedule group | `/Users/zhdeng/stoa-infra/stacks/notification_stack.py` |
| Monitoring resources | `/Users/zhdeng/stoa-infra/stacks/monitoring_stack.py` |
| Backend settings | `src/stoa/config.py` and `.env.example` |
| Backend AWS clients/table access | `src/stoa/deps.py` and `src/stoa/db/dynamodb.py` |

## CDK Resource Ledger

| Resource | Status | Source Evidence | Parent Portal Consequence |
|----------|--------|-----------------|---------------------------|
| DynamoDB table `stoa-main` | confirmed | `/Users/zhdeng/stoa-infra/stacks/database_stack.py:15` creates `dynamodb.Table`; line 18 sets `table_name="stoa-main"`; lines 19-20 define `PK` and `SK`. | Backend should continue using `settings.dynamodb_table_name` and single-table key patterns. |
| DynamoDB `GSI-Email` | confirmed | `/Users/zhdeng/stoa-infra/stacks/database_stack.py:28` describes user email lookup; lines 29-32 define `index_name="GSI-Email"` with partition key `email`. | Parent profile resolution can use email lookup through `user_repo.get_user_by_email`. |
| DynamoDB `GSI-StudentId` | confirmed | `/Users/zhdeng/stoa-infra/stacks/database_stack.py:35` describes questions by student; lines 36-40 define partition key `student_id` and sort key `created_at`. | Later summary/history implementation can use existing question student access pattern. |
| DynamoDB `GSI-ParentId` | confirmed but not sufficient for child profiles | `/Users/zhdeng/stoa-infra/stacks/database_stack.py:43` states weekly reports by parent and week; lines 44-48 define partition key `parent_id` and sort key `week_start`. | This supports report lookup by `parent_id` plus `week_start`; it does not itself prove efficient child profile lookup unless student profile items include both `parent_id` and `week_start`, which they should not. |
| DynamoDB `GSI-TeacherId` | confirmed | `/Users/zhdeng/stoa-infra/stacks/database_stack.py:51` describes teacher sessions; lines 52-56 define partition key `teacher_id` and sort key `started_at`. | Not required for this milestone. |
| Cognito user pool `stoa-users` | confirmed | `/Users/zhdeng/stoa-infra/stacks/auth_stack.py:15` creates `cognito.UserPool`; line 18 sets `user_pool_name="stoa-users"`; lines 19-34 configure email sign-in, verification, password policy, recovery, and custom attributes. | Parent authentication uses this user pool; `/parents/me/...` must trust validated Cognito access tokens, not client-provided parent IDs. |
| Cognito custom attributes | confirmed | `/Users/zhdeng/stoa-infra/stacks/auth_stack.py:30` starts `custom_attributes`; lines 31-33 define `role`, `grade`, and `subscription_tier`. | Role may be available from `custom:role`, but access-token group membership is the primary role path in backend auth. |
| Cognito student client | confirmed | `/Users/zhdeng/stoa-infra/stacks/auth_stack.py:37` documents one client per role; line 38 creates the student client. | JWT authorizer accepts student client tokens, but backend parent route guards must reject student role. |
| Cognito parent client | confirmed | `/Users/zhdeng/stoa-infra/stacks/auth_stack.py:39` creates the parent client. | Normal parent portal flows should use this app client. |
| Cognito teacher client | confirmed | `/Users/zhdeng/stoa-infra/stacks/auth_stack.py:40` creates the teacher client. | Backend parent route guards must reject teacher/tutor role for normal parent endpoints. |
| Cognito admin client | confirmed | `/Users/zhdeng/stoa-infra/stacks/auth_stack.py:41` creates the admin client. | Admin should not use normal `/parents/me/...` parent flows unless a separate admin route is added. |
| Lambda function `stoa-api` | confirmed | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:40` creates `lambda_.Function`; line 43 sets `function_name="stoa-api"`; lines 44-49 set Python 3.12, ARM64, handler, code asset, memory, and timeout. | Parent API implementation belongs in this backend Lambda. |
| Lambda environment variables | partially confirmed | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:50` starts `environment`; lines 51-60 inject `ENVIRONMENT`, `DYNAMODB_TABLE_NAME`, `S3_IMAGES_BUCKET`, `TEACHER_QUEUE_URL`, Cognito IDs, and `BEDROCK_MODEL_ID`. | Required parent runtime settings are mostly injected. `S3_REPORTS_BUCKET` is missing from Lambda injection. |
| Lambda DynamoDB permission | confirmed | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:65` grants read/write access to the table. | Parent routes can read user/report/question/practice items through the table. |
| Lambda image bucket permission | confirmed | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:66` grants read/write to images bucket. | Not directly required for parent portal data integration. |
| Lambda teacher queue permission | confirmed | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:67` grants send permissions to teacher queue. | Not required for parent portal route implementation except existing escalation flows. |
| Lambda Bedrock permission | confirmed | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:70` adds `bedrock:InvokeModel`. | Report generation is out of scope; parent summary/history should not require new Bedrock calls in this milestone. |
| Lambda Rekognition permission | confirmed | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:74` adds `rekognition:DetectText`. | Not required for parent portal route implementation. |
| Lambda Cognito admin permissions | confirmed | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:80` adds Cognito policy; lines 82-88 include create, password, get user, add to group, auth, and signout; line 89 scopes to the user pool ARN. | Parent identity resolution can use `AdminGetUser` as existing student/auth flows already do. |
| HTTP API JWT authorizer | confirmed | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:92` creates a Cognito JWT authorizer; lines 95-101 accept all four role app clients. | API Gateway accepts parent/student/teacher/admin tokens; backend role dependencies must enforce parent-only behavior. |
| Public auth/health routes | confirmed | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:119` adds public routes for `/auth/register`, `/auth/login`, `/auth/refresh`, and `/health`. | Parent auth flow remains available. |
| Protected proxy routes | confirmed | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:134` adds protected catch-all routes; lines 137-145 require JWT for non-OPTIONS methods. | New parent routes will be protected by the JWT authorizer plus backend role/ownership checks. |
| Image bucket | confirmed | `/Users/zhdeng/stoa-infra/stacks/storage_stack.py:27` creates images bucket; line 30 names it `stoa-images-{account}`; lines 31-42 configure privacy, encryption, CORS, logs, retain, lifecycle. | Not directly required for parent real-data flows. |
| Report bucket | confirmed but not wired to Lambda | `/Users/zhdeng/stoa-infra/stacks/storage_stack.py:46` creates reports bucket; line 49 names it `stoa-reports-{account}`; lines 50-54 configure privacy, encryption, logs, and retain. | The bucket exists, but `ApiStack` does not receive it, inject `S3_REPORTS_BUCKET`, or grant Lambda report-bucket permissions. If later phases read/write report S3 objects, they must add a CDK-backed API stack wiring change. |
| Teacher SQS FIFO queue | confirmed | `/Users/zhdeng/stoa-infra/stacks/notification_stack.py:29` creates `TeacherEscalationQueue`; line 32 names it `stoa-teacher-escalation.fifo`; lines 33-36 configure FIFO, dedupe, visibility, and DLQ. | Not required for parent data integration except existing teacher-help data may appear in history. |
| SES identity | confirmed but out of scope | `/Users/zhdeng/stoa-infra/stacks/notification_stack.py:39` describes SES identity; lines 40-43 create `stoaedu.ch`. | Weekly report email workflow is explicitly out of scope. |
| EventBridge schedule group | confirmed but out of scope | `/Users/zhdeng/stoa-infra/stacks/notification_stack.py:46` describes scheduler; lines 48-51 create `stoa-schedules`. | EventBridge target implementation is explicitly out of scope. |
| CloudWatch dashboard and alarms | confirmed | `/Users/zhdeng/stoa-infra/stacks/monitoring_stack.py:23` creates `stoa-alerts`; lines 26-36 create error alarm; lines 39-50 create latency alarm; lines 53-68 create dashboard widgets. | No parent-specific monitoring change is required in this milestone. |

## Environment Variable Source Of Truth

| Backend Setting / Env Var | Backend Source | CDK Injection Status | Implementation Consequence |
|---------------------------|----------------|----------------------|-----------------------------|
| `ENVIRONMENT` | `src/stoa/config.py:11`; `.env.example:2` | confirmed in `/Users/zhdeng/stoa-infra/stacks/api_stack.py:51` | No change needed. |
| `AWS_REGION` | `src/stoa/config.py:18`; `.env.example:6` | not injected directly; CDK/Lambda runtime region is available to boto3 and backend default is `eu-central-2` | Acceptable for current region, but code reads `settings.aws_region`; CDK can inject `AWS_REGION` if multi-region deployment becomes necessary. |
| `AWS_ACCOUNT_ID` | `src/stoa/config.py:19`; `.env.example:7` | not injected | Not required for parent portal data integration. |
| `DYNAMODB_TABLE_NAME` | `src/stoa/config.py:22`; `.env.example:10`; `src/stoa/db/dynamodb.py:9-10` uses it | confirmed in `/Users/zhdeng/stoa-infra/stacks/api_stack.py:52` | Use existing setting in all new repository/route code. |
| `S3_IMAGES_BUCKET` | `src/stoa/config.py:25`; `.env.example:13` | confirmed in `/Users/zhdeng/stoa-infra/stacks/api_stack.py:53` | Not directly required for parent portal data integration. |
| `S3_REPORTS_BUCKET` | `src/stoa/config.py:26`; `.env.example:14` | missing from Lambda env in `/Users/zhdeng/stoa-infra/stacks/api_stack.py:50-61` | Required only if later implementation reads/writes report S3 objects. Current DynamoDB report lookup can proceed without it. Add CDK wiring if S3 report artifacts become part of the current implementation. |
| `S3_PRESIGN_EXPIRY_SECONDS` | `src/stoa/config.py:27`; `.env.example:15` | not injected | Not required for parent portal data integration. |
| `COGNITO_USER_POOL_ID` | `src/stoa/config.py:30`; `.env.example:18`; JWT issuer uses it in `src/stoa/deps.py:96-99` | confirmed in `/Users/zhdeng/stoa-infra/stacks/api_stack.py:55` | No change needed. |
| `COGNITO_STUDENT_CLIENT_ID` | `src/stoa/config.py:31`; `.env.example:19`; auth maps it in `src/stoa/routers/auth.py:83-89` | confirmed in `/Users/zhdeng/stoa-infra/stacks/api_stack.py:56` | No change needed. |
| `COGNITO_PARENT_CLIENT_ID` | `src/stoa/config.py:32`; `.env.example:20`; auth maps it in `src/stoa/routers/auth.py:83-89` | confirmed in `/Users/zhdeng/stoa-infra/stacks/api_stack.py:57` | No change needed. |
| `COGNITO_TEACHER_CLIENT_ID` | `src/stoa/config.py:33`; `.env.example:21`; auth maps it in `src/stoa/routers/auth.py:83-89` | confirmed in `/Users/zhdeng/stoa-infra/stacks/api_stack.py:58` | No change needed. |
| `COGNITO_ADMIN_CLIENT_ID` | `src/stoa/config.py:34`; `.env.example:22`; auth maps it in `src/stoa/routers/auth.py:83-89` | confirmed in `/Users/zhdeng/stoa-infra/stacks/api_stack.py:59` | No change needed. |
| `BEDROCK_MODEL_ID` | `src/stoa/config.py:45`; `.env.example:25` | confirmed in `/Users/zhdeng/stoa-infra/stacks/api_stack.py:60` | Not required for this milestone because report generation is out of scope. |
| `TEACHER_QUEUE_URL` | `src/stoa/config.py:61`; `.env.example:34` | confirmed in `/Users/zhdeng/stoa-infra/stacks/api_stack.py:54` | Existing teacher escalation flow remains configured. |

## Report Storage And Permissions

The report bucket exists in CDK, but the API Lambda does not currently receive the report bucket object, environment variable, or permissions:

| Item | Status | Evidence | Required Action |
|------|--------|----------|-----------------|
| Report S3 bucket resource | confirmed | `/Users/zhdeng/stoa-infra/stacks/storage_stack.py:46-54` | No action for DynamoDB-only report lookup. |
| `S3_REPORTS_BUCKET` backend setting | exists in backend | `src/stoa/config.py:26`; `.env.example:14` | No backend setting change needed. |
| `S3_REPORTS_BUCKET` Lambda env injection | missing | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:50-61` injects images bucket but not reports bucket. | Add CDK wiring before any backend report S3 access. |
| Lambda report bucket IAM grant | missing | `/Users/zhdeng/stoa-infra/stacks/api_stack.py:64-67` grants table, images bucket, and teacher queue only. | Add `reports_bucket.grant_read_write` or narrower grant before any backend report S3 access. |

Current parent report display can use DynamoDB `report_repo.get_report_by_week` without S3. If later phases decide to read report artifacts from S3 during this milestone, that implementation must first modify CDK to pass `reports_bucket` into `ApiStack`, inject `S3_REPORTS_BUCKET`, and grant the Lambda access.

## Parent Portal Infrastructure Consequences

- INFRA-01 is satisfied: the table, indexes, Cognito user pool/app clients, Lambda, API Gateway authorizer, image/report buckets, teacher queue, SES identity, EventBridge schedule group, and monitoring resources are all source-cited.
- INFRA-02 is partly satisfied by this audit and fully resolved in `PARENT-IDENTITY-ACCESS-CONTRACT.md`: `GSI-ParentId` exists but is designed for reports by `parent_id` and `week_start`, not direct child profile listing.
- INFRA-03 is satisfied for DynamoDB, Cognito, image bucket, teacher queue, and Bedrock settings. It is not satisfied for `S3_REPORTS_BUCKET` if report S3 objects are used by later phases.
- Normal parent API implementation can proceed without inventing new AWS services.
- No new table, bucket, queue, Lambda, EventBridge target, SES workflow, or PDF-generation infrastructure is needed for the current DynamoDB-backed parent portal scope.

## Out Of Scope Confirmations

No implementation was performed for:

- Parent `/parents/me/...` API endpoints.
- Frontend service/page changes.
- Weekly report generation.
- EventBridge schedule target implementation.
- SES weekly email workflow.
- PDF generation.
- Stripe or billing.
- Organization/school portal work.
- Live classroom work.
- Broad frontend redesign.
