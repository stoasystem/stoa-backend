# Requirements: STOA Weekly Report Automation

**Defined:** 2026-06-02
**Milestone:** v1.1 Weekly Report Automation
**Core Value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.

## v1.1 Requirements

### Infrastructure and CDK

- [x] **CDK-01**: CDK defines a separate scheduled weekly report Lambda handler, not an API Gateway or Mangum event path.
- [x] **CDK-02**: Report Lambda receives `S3_REPORTS_BUCKET` and has read/write permissions for the reports bucket.
- [x] **CDK-03**: Report Lambda has DynamoDB read/write, Bedrock invoke, and SES send permissions.
- [x] **CDK-04**: EventBridge Scheduler invokes the report Lambda on the intended weekly schedule.
- [x] **CDK-05**: Report job has retry and failure handling through CDK-defined infrastructure.
- [x] **CDK-06**: Monitoring exposes report job failures through CloudWatch logs, metrics, or alarms.

### Backend Job

- [x] **JOB-01**: Scheduled handler accepts EventBridge scheduled events and defaults to the previous Zurich calendar week.
- [x] **JOB-02**: Job discovers eligible linked parent/student pairs.
- [x] **JOB-03**: Report generation is idempotent by `(parent_id, student_id, week_start)`.
- [x] **JOB-04**: Duplicate job runs skip existing generated or email-sent reports.
- [x] **JOB-05**: Job returns structured counts for attempted, generated, skipped, emailed, and failed reports.

### Aggregation and AI

- [x] **AGGR-01**: Report service aggregates weekly question, AI answer, teacher help, practice progress, mistake, and weak-topic data.
- [x] **AGGR-02**: Empty or sparse weekly data produces a valid deterministic report payload, not fabricated activity.
- [x] **AI-01**: Bedrock receives compact structured weekly report input.
- [x] **AI-02**: Bedrock output is parsed as strict JSON with summary, strengths, weak topics, recommendations, and optional teacher note.
- [x] **AI-03**: Malformed or failed Bedrock output falls back to deterministic parent-facing content.
- [x] **AI-04**: Parent-facing generated copy does not expose internal provider or model terms.

### Storage and Email

- [x] **STORE-01**: Report metadata is stored in DynamoDB with status, stats, summary, recommendations, S3 key, timestamps, and error fields.
- [x] **STORE-02**: Full report HTML and JSON artifacts are stored in the private reports S3 bucket.
- [x] **STORE-03**: Generated report content is stored before email send is considered complete.
- [x] **EMAIL-01**: SES sends weekly report email only to the linked parent email.
- [x] **EMAIL-02**: Email includes student name, week range, summary, recommendations, and parent portal link.
- [x] **EMAIL-03**: Email failure keeps the generated report available and marks `email_failed`.
- [x] **EMAIL-04**: Report logs include identifiers, counts, and error classes, but do not log full student question content.

### Parent API and Frontend

- [x] **API-01**: Parent report endpoint returns generated report detail with week range, stats, summary, weak topics, recommendations, generated timestamp, and email status.
- [x] **API-02**: Parent report endpoint preserves a clear missing state for weeks with no generated report.
- [x] **API-03**: Parent report endpoint exposes generation or email failure state without leaking cross-student data.
- [x] **FRONT-01**: Parent report page renders generated report summary, week range, stats, weak topics, recommendations, and generated timestamp.
- [x] **FRONT-02**: Parent report page renders email failed, pending, or sent state where useful.
- [x] **FRONT-03**: Parent report page preserves the missing report state.
- [x] **FRONT-04**: Generated report page no longer relies on mock-only rich report assumptions.

### Verification

- [x] **TEST-01**: Backend tests cover week-window calculation and report idempotency.
- [x] **TEST-02**: Backend tests cover aggregation for empty and mixed weekly activity.
- [x] **TEST-03**: Backend tests cover Bedrock JSON parser and fallback behavior.
- [x] **TEST-04**: Backend tests cover DynamoDB metadata and S3 artifact writes.
- [x] **TEST-05**: Backend tests cover SES failure marking `email_failed`.
- [x] **TEST-06**: Backend tests cover parent endpoint generated, missing, and failed report responses.
- [x] **TEST-07**: Frontend tests cover generated report detail rendering.
- [x] **TEST-08**: Frontend tests cover missing and email-failed report states.

## Future Requirements

### Report Operations

- **OPS-01**: Admin can manually retry weekly report generation for a parent/student/week.
- **OPS-02**: Admin can manually resend a generated report email.
- **OPS-03**: Parent notification preferences control whether weekly report email is sent.

### Report Formats

- **FMT-01**: Parent can export a weekly report as PDF.
- **FMT-02**: Report generation supports multiple parent-facing languages.
- **FMT-03**: Report artifacts include a delivery audit trail.

### Commercial and Organization Features

- **BILL-01**: Report access can be gated by subscription or billing status.
- **ORG-01**: Organization or school admins can view aggregate report delivery status.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Billing or paid subscription enforcement | Not part of report automation MVP. |
| PDF generation | HTML/JSON report artifacts are enough for this milestone. |
| Multi-language report generation | Defer until primary-language report flow is reliable. |
| Organization or school reports | Separate product surface and access model. |
| Real-time report generation on every parent page load | Scheduled generation is the intended operating model. |
| Manual admin report editor | Operational feature after automated generation exists. |
| Teacher payroll or tutor performance reporting | Unrelated to parent weekly learning reports. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CDK-01 | Phase 6 | Complete |
| CDK-02 | Phase 6 | Complete |
| CDK-03 | Phase 6 | Complete |
| CDK-04 | Phase 6 | Complete |
| CDK-05 | Phase 6 | Complete |
| CDK-06 | Phase 6 | Complete |
| AGGR-01 | Phase 7 | Complete |
| AGGR-02 | Phase 7 | Complete |
| AI-01 | Phase 8 | Complete |
| AI-02 | Phase 8 | Complete |
| AI-03 | Phase 8 | Complete |
| AI-04 | Phase 8 | Complete |
| STORE-01 | Phase 9 | Complete |
| STORE-02 | Phase 9 | Complete |
| STORE-03 | Phase 9 | Complete |
| EMAIL-01 | Phase 9 | Complete |
| EMAIL-02 | Phase 9 | Complete |
| EMAIL-03 | Phase 9 | Complete |
| EMAIL-04 | Phase 9 | Complete |
| JOB-01 | Phase 10 | Complete |
| JOB-02 | Phase 10 | Complete |
| JOB-03 | Phase 10 | Complete |
| JOB-04 | Phase 10 | Complete |
| JOB-05 | Phase 10 | Complete |
| API-01 | Phase 11 | Complete |
| API-02 | Phase 11 | Complete |
| API-03 | Phase 11 | Complete |
| FRONT-01 | Phase 11 | Complete |
| FRONT-02 | Phase 11 | Complete |
| FRONT-03 | Phase 11 | Complete |
| FRONT-04 | Phase 11 | Complete |
| TEST-01 | Phase 12 | Complete |
| TEST-02 | Phase 12 | Complete |
| TEST-03 | Phase 12 | Complete |
| TEST-04 | Phase 12 | Complete |
| TEST-05 | Phase 12 | Complete |
| TEST-06 | Phase 12 | Complete |
| TEST-07 | Phase 13 | Complete |
| TEST-08 | Phase 13 | Complete |

**Coverage:**

- v1.1 requirements: 39 total
- Mapped to phases: 39
- Unmapped: 0

---
*Requirements defined: 2026-06-02*
*Last updated: 2026-06-02 after completing Phase 6*
