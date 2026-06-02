# Roadmap: STOA Weekly Report Automation

## Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Phases 1-5 shipped 2026-06-02. Archive: `.planning/milestones/v1.0-ROADMAP.md`.
- [ ] **v1.1 Weekly Report Automation** - Phases 6-13 planned.

## Overview

v1.1 turns the parent report page from a lookup surface into an automated weekly report flow. The milestone starts with CDK-backed infrastructure, then builds weekly aggregation, Bedrock report generation, durable report storage, SES delivery, scheduled orchestration, parent API/frontend rendering, and focused verification.

## Phases

- [x] **Phase 6: CDK Report Automation Foundation** - CDK defines the scheduled report Lambda, resource configuration, failure handling, and monitoring. (completed 2026-06-02)
- [x] **Phase 7: Weekly Learning Aggregation** - Backend creates truthful weekly report payloads from linked student activity. (completed 2026-06-02)
- [ ] **Phase 8: Bedrock Report Generation** - Backend turns weekly payloads into validated parent-facing generated report content with deterministic fallback.
- [ ] **Phase 9: Report Storage and Email Delivery** - Backend stores report metadata/artifacts before sending SES email and preserving delivery failures.
- [ ] **Phase 10: Scheduled Job Orchestration** - Scheduled handler runs weekly generation idempotently and returns structured job counts.
- [ ] **Phase 11: Generated Report API and Frontend Display** - Parent report API and page render generated report details, missing reports, and failure states.
- [ ] **Phase 12: Backend Report Flow Verification** - Backend tests prove aggregation, generation, storage, idempotency, email failure, and API behavior.
- [ ] **Phase 13: Frontend Report State Verification** - Frontend tests prove generated, missing, and email-failed report states render correctly.

## Phase Details

### Phase 6: CDK Report Automation Foundation

**Goal**: Weekly report automation infrastructure exists in CDK before backend code depends on it.
**Depends on**: Phase 5
**Requirements**: CDK-01, CDK-02, CDK-03, CDK-04, CDK-05, CDK-06
**Success Criteria** (what must be TRUE):

  1. CDK defines a separate scheduled weekly report Lambda handler instead of routing scheduler events through API Gateway or Mangum.
  2. The report Lambda receives `S3_REPORTS_BUCKET` and has reports bucket read/write, DynamoDB read/write, Bedrock invoke, and SES send permissions from CDK.
  3. EventBridge Scheduler invokes the report Lambda on the intended weekly schedule with CDK-defined retry and failure handling.
  4. CloudWatch logs, metrics, or alarms expose report job failures without relying on manual AWS setup.

**Plans**: 1/1 complete

### Phase 7: Weekly Learning Aggregation

**Goal**: Backend can build a truthful weekly learning payload for each linked parent/student/week.
**Depends on**: Phase 6
**Requirements**: AGGR-01, AGGR-02
**Success Criteria** (what must be TRUE):

  1. Report aggregation includes weekly question, AI answer, teacher help, practice progress, mistake, and weak-topic data for a linked student.
  2. Empty or sparse weekly activity produces a valid deterministic report payload that does not fabricate learning activity.

**Plans**: 1/1 complete

### Phase 8: Bedrock Report Generation

**Goal**: Backend can generate validated parent-facing report content from compact weekly report input.
**Depends on**: Phase 7
**Requirements**: AI-01, AI-02, AI-03, AI-04
**Success Criteria** (what must be TRUE):

  1. Bedrock receives compact structured weekly report input rather than raw or excessive student activity data.
  2. Valid Bedrock output is accepted only when it parses as strict JSON with summary, strengths, weak topics, recommendations, and optional teacher note.
  3. Malformed or failed Bedrock output produces deterministic parent-facing fallback content.
  4. Generated parent-facing copy does not expose internal provider, model, or implementation terms.

**Plans**: TBD

### Phase 9: Report Storage and Email Delivery

**Goal**: Generated reports are durable before delivery, and SES delivery failures preserve report availability.
**Depends on**: Phase 8
**Requirements**: STORE-01, STORE-02, STORE-03, EMAIL-01, EMAIL-02, EMAIL-03, EMAIL-04
**Success Criteria** (what must be TRUE):

  1. DynamoDB stores report metadata with status, stats, summary, recommendations, S3 key, timestamps, and error fields.
  2. The private reports S3 bucket stores full HTML and JSON report artifacts before email completion is recorded.
  3. SES sends weekly report email only to the linked parent email and includes student name, week range, summary, recommendations, and parent portal link.
  4. Email failure keeps the generated report available and marks the report as `email_failed`.
  5. Report logs include identifiers, counts, and error classes without logging full student question content.

**Plans**: TBD

### Phase 10: Scheduled Job Orchestration

**Goal**: The scheduled handler runs weekly report generation idempotently for eligible linked parent/student pairs.
**Depends on**: Phase 9
**Requirements**: JOB-01, JOB-02, JOB-03, JOB-04, JOB-05
**Success Criteria** (what must be TRUE):

  1. The scheduled handler accepts EventBridge scheduled events and defaults to the previous Zurich calendar week.
  2. The job discovers eligible linked parent/student pairs for the target week.
  3. Report generation is idempotent by `(parent_id, student_id, week_start)`.
  4. Duplicate runs skip existing generated or email-sent reports.
  5. The job returns structured counts for attempted, generated, skipped, emailed, and failed reports.

**Plans**: TBD

### Phase 11: Generated Report API and Frontend Display

**Goal**: Parents can view generated report details and clear report states through the real parent portal contract.
**Depends on**: Phase 10
**Requirements**: API-01, API-02, API-03, FRONT-01, FRONT-02, FRONT-03, FRONT-04
**Success Criteria** (what must be TRUE):

  1. The parent report endpoint returns generated report detail with week range, stats, summary, weak topics, recommendations, generated timestamp, and email status.
  2. The parent report endpoint preserves a clear missing state for weeks with no generated report.
  3. Generation or email failure states are visible to the owning parent without leaking cross-student data.
  4. The parent report page renders generated report summary, week range, stats, weak topics, recommendations, generated timestamp, and useful email status.
  5. The generated report page preserves missing state and no longer depends on mock-only rich report assumptions.

**Plans**: TBD
**UI hint**: yes

### Phase 12: Backend Report Flow Verification

**Goal**: Backend tests cover the weekly report flow before the milestone is considered reliable.
**Depends on**: Phase 11
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06
**Success Criteria** (what must be TRUE):

  1. Backend tests cover Zurich week-window calculation and idempotent report generation.
  2. Backend tests cover empty and mixed weekly aggregation plus Bedrock parser and fallback behavior.
  3. Backend tests cover DynamoDB metadata and S3 artifact writes.
  4. Backend tests cover SES failure marking `email_failed`.
  5. Backend tests cover parent endpoint generated, missing, and failed report responses.

**Plans**: TBD

### Phase 13: Frontend Report State Verification

**Goal**: Frontend tests prove parents see generated report, missing report, and email-failed states correctly.
**Depends on**: Phase 12
**Requirements**: TEST-07, TEST-08
**Success Criteria** (what must be TRUE):

  1. Frontend tests cover generated report detail rendering.
  2. Frontend tests cover missing and email-failed report states.

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:** Phase 6 -> Phase 7 -> Phase 8 -> Phase 9 -> Phase 10 -> Phase 11 -> Phase 12 -> Phase 13

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 6. CDK Report Automation Foundation | v1.1 | 1/1 | Complete    | 2026-06-02 |
| 7. Weekly Learning Aggregation | v1.1 | 1/1 | Complete    | 2026-06-02 |
| 8. Bedrock Report Generation | v1.1 | 0/TBD | Not started | - |
| 9. Report Storage and Email Delivery | v1.1 | 0/TBD | Not started | - |
| 10. Scheduled Job Orchestration | v1.1 | 0/TBD | Not started | - |
| 11. Generated Report API and Frontend Display | v1.1 | 0/TBD | Not started | - |
| 12. Backend Report Flow Verification | v1.1 | 0/TBD | Not started | - |
| 13. Frontend Report State Verification | v1.1 | 0/TBD | Not started | - |
