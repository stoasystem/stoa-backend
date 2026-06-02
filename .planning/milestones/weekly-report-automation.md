# Milestone: Weekly Report Automation

**Created:** 2026-06-02
**Status:** Planned
**Follows:** Parent Portal Real Data Integration
**Primary repos:**

- Frontend: `/Users/zhdeng/stoa-frontend`
- Backend: `/Users/zhdeng/stoa-backend`
- Infrastructure/CDK: `/Users/zhdeng/stoa-infra`

## Objective

Automatically generate weekly learning reports for linked parent/student pairs, store the generated report, send it to parents by email, and render the richer generated report in the parent portal.

The previous parent milestone makes the portal able to query existing or missing reports. This milestone creates those reports automatically and makes the resulting report content useful to parents.

## Non-Negotiable Constraints

1. All AWS resource changes must be implemented in `/Users/zhdeng/stoa-infra` CDK.
2. Do not create resources manually in AWS and then assume they exist in code.
3. Reuse the existing DynamoDB table, reports S3 bucket, Cognito user pool, Bedrock permissions model, SES identity, and monitoring stack where possible.
4. New report automation infrastructure is allowed only when it is represented in CDK and wired to existing resources.
5. Report generation must be idempotent by `(parent_id, student_id, week_start)`.
6. Report emails must never expose another student's data.
7. Generated report content must be stored before email send is considered complete.
8. Frontend must render real generated report content and handle generation/email failure states explicitly.

## Existing Context

### Backend State

Existing report-related backend code:

- `src/stoa/models/report.py`
- `src/stoa/db/repositories/report_repo.py`
- `src/stoa/services/notify_service.py`
- `src/stoa/routers/parents.py`

Current capabilities:

- `WeeklyReportResponse` exists, but is minimal.
- `report_repo.put_report` stores report summary items.
- `report_repo.get_report_by_week` and `list_reports_for_parent` query by parent.
- `notify_service.send_weekly_report_email` sends HTML email through SES.
- No `report_service.py` exists.
- No weekly report job handler exists.
- No Bedrock report-summary generation exists.
- No S3 report artifact storage exists in backend.

### Infrastructure State

Relevant CDK files:

- `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/notification_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/api_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/monitoring_stack.py`

Current infrastructure:

- `StorageStack` creates private reports bucket `stoa-reports-{account}`.
- `NotificationStack` creates SES email identity for `stoaedu.ch`.
- `NotificationStack` creates an EventBridge Scheduler schedule group named `stoa-schedules`.
- `ApiStack` creates the FastAPI Lambda.
- `ApiStack` currently injects `S3_IMAGES_BUCKET`, but does not inject `S3_REPORTS_BUCKET`.
- `ApiStack` grants image bucket access, but does not grant report bucket access.
- No actual EventBridge schedule target is wired to a weekly report Lambda handler.

### Frontend State

Relevant frontend files:

- `src/pages/parent/ChildReportPage.tsx`
- `src/services/parent/parentReportApi.ts`
- `src/types/parentReport.ts`
- parent report components under `src/components/parent/`

Current state:

- The parent portal has types for both compact report state and richer legacy/demo report content.
- `ParentChildReportState` supports `status: "available" | "missing"`.
- Rich `ParentWeeklyReport` types exist for demo-style report pages.
- Frontend should be updated to render generated report fields from the backend rather than mock-only content.

## Scope

### In Scope

- Add backend `report_service.py` for weekly report aggregation and generation.
- Add a scheduled weekly report Lambda handler.
- Wire EventBridge Scheduler to the report handler in CDK.
- Use Bedrock to generate parent-readable summary/recommendations.
- Store report metadata in DynamoDB.
- Store full report HTML/JSON artifact in S3 reports bucket.
- Send weekly report email through SES.
- Add retry/idempotency behavior.
- Add monitoring and failure visibility.
- Update parent frontend to render generated report content.
- Add backend tests for report aggregation, idempotency, and email failure handling.
- Add frontend tests for generated report display and missing/failed states.

### Out of Scope

- Billing or paid subscription enforcement.
- PDF generation.
- Multi-language report generation beyond the primary parent-facing language chosen for MVP.
- Organization/school reports.
- Real-time report generation on every parent page load.
- Manual admin report editor.
- Teacher payroll or tutor performance reporting.

## Architecture

Preferred flow:

```text
EventBridge Scheduler
  -> Weekly Report Lambda handler
  -> Find parent/student links
  -> Aggregate weekly learning data from DynamoDB
  -> Generate parent-facing summary with Bedrock
  -> Store report item in DynamoDB
  -> Store full report artifact in S3 reports bucket
  -> Send SES email to parent
  -> Emit logs/metrics
```

The scheduled handler should not depend on API Gateway request events. It should have a normal Lambda handler, for example:

```text
stoa.jobs.weekly_reports.handler
```

The handler can live in the same backend package and deployment artifact, but CDK must wire it as an explicit scheduled Lambda target.

## Backend Contract

### New Backend Modules

Expected new modules:

- `src/stoa/services/report_service.py`
- `src/stoa/jobs/weekly_reports.py`

Optional helper modules:

- `src/stoa/services/report_render_service.py`
- `src/stoa/services/report_email_service.py`

### Report Service Responsibilities

`report_service.py` should provide:

- Determine the report week window.
- Find eligible parent/student pairs.
- Aggregate weekly question data.
- Aggregate teacher help activity.
- Aggregate practice progress and mistakes.
- Build deterministic report input for Bedrock.
- Generate summary and recommendations.
- Build report metadata record.
- Build full report artifact.
- Store DynamoDB record.
- Store S3 artifact.
- Trigger email send.

### Scheduled Job Responsibilities

`weekly_reports.py` should:

- Accept scheduled Lambda events.
- Compute target week, defaulting to the previous Zurich calendar week.
- Run generation for all eligible parent/student pairs.
- Avoid duplicate report generation.
- Return structured counts:
  - attempted
  - generated
  - skipped_existing
  - email_sent
  - failed

## Data Model

### DynamoDB Report Item

Use existing report repository as the base, but extend the report shape.

Recommended item fields:

```json
{
  "PK": "REPORT#{report_id}",
  "SK": "SUMMARY",
  "report_id": "parent#student#2026-06-01",
  "parent_id": "parent-id",
  "student_id": "student-id",
  "week_start": "2026-06-01",
  "week_end": "2026-06-07",
  "status": "generated|email_sent|email_failed",
  "usage_count": 0,
  "ai_resolved": 0,
  "teacher_resolved": 0,
  "teacher_help_requests": 0,
  "practice_lessons_completed": 0,
  "weak_knowledge_points": [],
  "summary": "...",
  "recommendations": "...",
  "s3_key": "reports/parent-id/student-id/2026-06-01/report.html",
  "generated_at": "2026-06-08T05:00:00Z",
  "email_sent_at": "2026-06-08T05:01:00Z",
  "error": null
}
```

### Idempotency

Report generation must be idempotent by:

```text
parent_id + student_id + week_start
```

Recommended `report_id`:

```text
{parent_id}#{student_id}#{week_start}
```

Before generating:

- Query by parent/week/student or deterministic report ID.
- If a generated or email_sent report already exists, skip unless forced by an explicit admin/manual mode.

## S3 Artifact Contract

Store full report artifacts in existing reports bucket.

Recommended keys:

```text
reports/{parent_id}/{student_id}/{week_start}/report.html
reports/{parent_id}/{student_id}/{week_start}/report.json
```

Minimum artifact:

- HTML email/report body.
- JSON source payload used to render the frontend report.

Access:

- Bucket remains private.
- Parent portal should fetch report data through backend API, not directly from public S3.
- Backend can return structured report content from DynamoDB or read the S3 JSON artifact when needed.

## Bedrock Generation

### Input

Bedrock should receive compact, structured weekly data:

- student name/grade
- week window
- questions asked
- AI-resolved count
- teacher-help count
- practice lessons completed
- mistakes/weak topics
- notable recent activity

### Output

Require strict JSON output:

```json
{
  "summary": "Parent-facing weekly summary...",
  "strengths": ["..."],
  "weakTopics": [
    {
      "topic": "Fractions",
      "level": "medium",
      "summary": "..."
    }
  ],
  "recommendations": [
    {
      "title": "Review fraction simplification",
      "description": "...",
      "priority": "medium"
    }
  ],
  "teacherNote": null
}
```

Validation:

- Parse JSON robustly.
- Reject empty or malformed output.
- Redact internal model/provider terms.
- Fall back to deterministic template summary when Bedrock fails.

## Email Contract

SES email should:

- Use verified sender domain from CDK.
- Send to parent email from user profile/Cognito-linked profile.
- Include student name and week.
- Include report summary and recommendations.
- Include link to parent portal report page.

Subject:

```text
STOA Wochenbericht: {student_name} ({week_start} - {week_end})
```

Failure behavior:

- If email fails after report storage, keep the report.
- Mark status `email_failed`.
- Store error summary.
- Retry email on the next retry attempt or explicit retry job.

## CDK Requirements

### Required CDK Checks

Before coding, verify:

- Reports bucket is passed to the backend/report Lambda.
- Lambda has read/write permissions to reports bucket.
- Lambda has DynamoDB read/write permissions.
- Lambda has Bedrock invoke permission.
- Lambda has SES send permission.
- EventBridge Scheduler has permission to invoke report Lambda.
- Monitoring stack has alarms for report job failures.

### Expected CDK Changes

Likely required:

- Add `S3_REPORTS_BUCKET` env var to report Lambda.
- Grant report Lambda read/write access to reports bucket.
- Add SES send permission to report Lambda.
- Add EventBridge Scheduler target to invoke weekly report Lambda.
- Add retry policy / DLQ or failure destination for the scheduled job.
- Add CloudWatch alarm on job errors.

Implementation options:

1. Add a separate scheduled Lambda using the same backend package:
   - Handler: `stoa.jobs.weekly_reports.handler`
   - Pros: clean scheduled-event contract.
   - Cons: new Lambda resource required in CDK.

2. Reuse the API Lambda only if a dedicated non-API handler can be exposed and CDK can invoke it correctly.
   - Do not invoke the Mangum API handler with scheduled events unless a wrapper explicitly handles that event type.

Preferred option: separate scheduled Lambda in CDK, reusing the same deployment artifact and existing AWS resources.

## Frontend Contract

Parent report pages should move from compact/missing state toward generated report detail.

Backend should return:

```json
{
  "status": "available",
  "report": {
    "reportId": "report-id",
    "parentId": "parent-id",
    "studentId": "student-id",
    "weekStart": "2026-06-01",
    "weekEnd": "2026-06-07",
    "summary": "...",
    "stats": [
      { "label": "Questions answered", "value": "12", "description": "..." }
    ],
    "weakTopics": [],
    "recommendations": [],
    "generatedAt": "2026-06-08T05:00:00Z",
    "emailStatus": "sent|failed|pending"
  }
}
```

Frontend should render:

- report summary
- week range
- activity stats
- weak topics
- recommendations
- generated timestamp
- email status where useful
- missing state
- generation/email failure state

Frontend files likely touched:

- `src/types/parentReport.ts`
- `src/services/parent/parentReportApi.ts`
- `src/pages/parent/ChildReportPage.tsx`
- parent report components under `src/components/parent/`

## Implementation Plan

### Phase 1: CDK and Data Audit

- Confirm reports bucket CDK wiring.
- Confirm current DynamoDB GSI support for report queries.
- Confirm SES identity status and sender domain assumptions.
- Confirm whether parent-child links are available after the prior milestone.
- Decide scheduled Lambda resource shape.

Deliverable:

- Implementation note: exact CDK resources/env/permissions to add.

### Phase 2: Backend Report Aggregation

- Create `report_service.py`.
- Implement week-window calculation using Zurich business semantics.
- Implement parent/student pair discovery.
- Aggregate:
  - questions
  - AI answers
  - teacher help activity
  - practice lessons/progress
  - mistakes/weak topics
- Build deterministic report payload.

### Phase 3: Bedrock Summary Generation

- Add report-specific prompt.
- Require strict JSON output.
- Add parser/validator.
- Add deterministic fallback if Bedrock fails.
- Avoid exposing internal provider/model terms in parent-facing copy.

### Phase 4: Storage

- Extend report model/repository as needed.
- Store compact metadata in DynamoDB.
- Store full HTML/JSON report artifacts in S3.
- Ensure idempotent writes.

### Phase 5: Email Delivery

- Extend email helper or create dedicated report email helper.
- Generate HTML email body.
- Send through SES.
- Mark status and timestamps in DynamoDB.
- Store failure state without deleting generated reports.

### Phase 6: Scheduled Job and CDK

- Add scheduled Lambda handler.
- Update CDK to deploy/wire scheduled Lambda.
- Configure EventBridge Scheduler.
- Add retry/failure behavior.
- Add CloudWatch logs/alarms.

### Phase 7: Frontend Report Display

- Update report API types.
- Render generated report content.
- Show email/generated status.
- Preserve missing state for weeks with no report.
- Remove mock-only rich report assumptions from generated-report page.

### Phase 8: Verification

- Unit-test report aggregation.
- Unit-test Bedrock parser/fallback.
- Integration-test report repository writes.
- Integration-test job idempotency.
- Integration-test email failure handling with mocked SES.
- Frontend-test report available/missing/failure states.
- Run one manual job against a test parent/student pair.

## Acceptance Criteria

This milestone is complete when:

- CDK defines the scheduled weekly report Lambda target.
- EventBridge Scheduler invokes the report job on the intended weekly schedule.
- The report job generates one report per eligible parent/student/week.
- Duplicate scheduler runs do not create duplicate reports.
- Report metadata is stored in DynamoDB.
- Full report artifact is stored in S3 reports bucket.
- Bedrock-generated summary/recommendations are stored and rendered.
- SES sends a weekly report email to the parent.
- Email failure leaves the generated report available and marks `email_failed`.
- CloudWatch logs and at least one alarm expose job failures.
- Parent frontend displays generated report content from the backend.
- Missing reports still render a clear missing state.
- Backend and frontend tests for the report flow pass.

## Tests

### Backend Unit Tests

- week window calculation
- report ID/idempotency
- aggregation from empty data
- aggregation from mixed question/practice/teacher activity
- Bedrock JSON parser
- Bedrock fallback output
- email body rendering

### Backend Integration Tests

- store report metadata in DynamoDB
- store report artifact in S3
- job skips existing report
- SES failure marks report as `email_failed`
- parent endpoint returns generated report detail

### Frontend Tests

- generated report detail renders
- missing report state renders
- email failed status renders without blocking report view
- report API response maps correctly to UI types

## Operational Notes

- Log every report generation attempt with `parent_id`, `student_id`, `week_start`, and `report_id`.
- Do not log student question content in full.
- Record counts and error classes.
- Prefer structured JSON logs.
- Keep Bedrock prompt inputs compact to control cost.
- Consider a manual retry path after this milestone if operations need it.

## Follow-Up Candidates

After this milestone:

- Manual admin report regeneration.
- Parent notification preferences.
- Multi-language report generation.
- PDF export.
- Report delivery audit trail.
- Billing-gated report access.
