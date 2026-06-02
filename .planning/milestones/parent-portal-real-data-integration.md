# Milestone: Parent Portal Real Data Integration

**Created:** 2026-06-02
**Status:** Planned
**Primary repos:**

- Frontend: `/Users/zhdeng/stoa-frontend`
- Backend: `/Users/zhdeng/stoa-backend`
- Infrastructure/CDK: `/Users/zhdeng/stoa-infra`

## Objective

Move the parent portal from demo/mock-backed screens to real AWS-backed data.

At the end of this milestone, a real parent Cognito account should be able to log in, see linked children, open a child detail page, review a real learning summary/history, and open a report page that correctly handles both existing and missing reports.

This milestone is a real-data integration milestone, not a full weekly-report automation milestone.

## Non-Negotiable Constraints

1. All new backend work must be checked against the existing CDK in `/Users/zhdeng/stoa-infra` before implementation.
2. Do not invent new AWS services, tables, buckets, Lambdas, queues, or indexes without first proving the current CDK/resources cannot support the need.
3. Reuse the existing DynamoDB single-table design unless a specific missing access pattern requires a new GSI.
4. Any required infrastructure change must be implemented in CDK, not manually assumed.
5. Backend resource names and URLs must come from environment variables injected by CDK.
6. Frontend integration must target the real backend API contract and remove silent demo fallback from parent-critical flows.

## Existing Context

### Frontend State

The parent portal already has pages and service modules in `/Users/zhdeng/stoa-frontend`.

Relevant frontend areas:

- `src/app/router/AppRouter.tsx`
- `src/pages/parent/`
- `src/services/parent/parentApi.ts`
- `src/services/parent/parentReportApi.ts`
- `src/services/practice/practiceApi.ts`
- `src/services/demo/demoFallback.ts`

Current issue:

- Parent pages call routes such as `/parents/me/children` and `/parents/me/children/{childId}/report`.
- Backend currently exposes `/parents/{parent_id}/children` and `/parents/{parent_id}/reports/{week}`.
- Many parent-facing frontend calls still use `withDemoFallback`, so API failures can be hidden by mock data.

### Backend State

Relevant backend areas:

- `src/stoa/routers/parents.py`
- `src/stoa/routers/students.py`
- `src/stoa/routers/practice.py`
- `src/stoa/db/repositories/user_repo.py`
- `src/stoa/db/repositories/question_repo.py`
- `src/stoa/db/repositories/report_repo.py`
- `src/stoa/db/repositories/practice_repo.py`
- `src/stoa/deps.py`

Current backend capabilities:

- Parent child listing exists, but uses path parent ID.
- Weekly report lookup exists, but uses path parent ID and week.
- Student summary exists, but uses `/students/{student_id}/summary`.
- Student question history exists, but uses `/students/{student_id}/questions`.
- Practice progress and mistakes exist for students.
- Report storage exists at repository/model level, but report generation service does not exist.

### Infrastructure State

Relevant CDK areas:

- `/Users/zhdeng/stoa-infra/stacks/auth_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/database_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/api_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/notification_stack.py`
- `/Users/zhdeng/stoa-infra/stacks/monitoring_stack.py`

Known current resources:

- Cognito User Pool with app clients and role groups.
- DynamoDB single table with GSIs.
- S3 image/report/log buckets.
- Lambda FastAPI backend through API Gateway HTTP API.
- SQS FIFO teacher escalation queue.
- SES email identity.
- EventBridge schedule group exists, but weekly report generation target is not implemented in backend.

## Scope

### In Scope

- Add backend `/parents/me/...` endpoints that match the frontend parent portal contract.
- Define and implement parent-child lookup using existing DynamoDB records and current Cognito identity.
- Aggregate child summary from existing question, conversation, practice, progress, mistake, and report data where available.
- Provide child learning history from real backend data.
- Provide report lookup with correct empty state behavior.
- Align frontend parent services with backend route shape.
- Remove silent demo fallback from parent-critical pages.
- Add focused tests for parent authorization and empty states.
- Document any required CDK change if the current single-table access pattern is insufficient.

### Out of Scope

- Automatic weekly report generation.
- EventBridge schedule target implementation.
- SES weekly email sending workflow.
- PDF generation.
- Stripe or billing integration.
- Organization/school portal work.
- Live classroom work.
- Full admin analytics.
- Broad frontend redesign.

## API Contract

Prefer adding `/parents/me/...` endpoints because the parent identity is already available from JWT and this avoids clients passing parent IDs.

### Required Backend Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/parents/me/children` | List children linked to the current parent |
| GET | `/parents/me/children/{child_id}/summary` | Child learning summary for parent dashboard/detail |
| GET | `/parents/me/children/{child_id}/history` | Child learning timeline |
| GET | `/parents/me/children/{child_id}/report` | Current/latest weekly report or empty state |
| GET | `/parents/me/children/{child_id}/reports/{week}` | Specific weekly report by week |

### Optional Backend Endpoint

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/parents/me/children/{child_id}/practice-summary` | Practice-specific summary if frontend needs a separate call |

### Compatibility

Existing endpoints may remain:

- `/parents/{parent_id}/children`
- `/parents/{parent_id}/reports/{week}`

But parent portal frontend should use `/parents/me/...` for normal logged-in parent flows.

## Data Contract

### Child List

Response:

```json
{
  "items": [
    {
      "id": "student-id",
      "userId": "student-id",
      "name": "Anna Keller",
      "email": "student@example.com",
      "grade": "Grade 8",
      "subjects": ["Mathematics"],
      "relationship": "child"
    }
  ]
}
```

Minimum source:

- User profile records in DynamoDB.
- Existing parent-child link fields.

If no children are linked:

```json
{ "items": [] }
```

### Child Summary

Response should include enough data for the parent dashboard/detail:

```json
{
  "student": {
    "id": "student-id",
    "name": "Anna Keller",
    "grade": "Grade 8"
  },
  "questionsAskedThisWeek": 0,
  "aiResolvedThisWeek": 0,
  "teacherHelpRequestsThisWeek": 0,
  "practiceLessonsCompletedThisWeek": 0,
  "weakTopics": [],
  "recentActivity": []
}
```

Aggregation sources:

- `question_repo.list_by_student`
- conversation records if available
- `practice_repo.get_progress`
- `practice_repo.get_mistakes`
- `report_repo.get_report_by_week`

### Child History

Response:

```json
{
  "items": [
    {
      "id": "event-id",
      "type": "question|conversation|practice|teacher_help|report",
      "title": "Question answered",
      "summary": "AI provided step-by-step guidance.",
      "subject": "Mathematics",
      "createdAt": "2026-06-02T10:00:00Z"
    }
  ]
}
```

Rules:

- Return newest first.
- Limit to a sane default, such as 20.
- Use real data only.
- Empty history returns `{ "items": [] }`.

### Child Report

If a report exists:

```json
{
  "status": "available",
  "report": {
    "report_id": "report-id",
    "week_start": "2026-06-01",
    "student_id": "student-id",
    "summary": "...",
    "recommendations": "..."
  }
}
```

If no report exists:

```json
{
  "status": "missing",
  "report": null,
  "message": "No weekly report is available yet."
}
```

Do not fabricate report content from mock data.

## Authorization Rules

1. Parent can only access children linked to that parent.
2. Admin can access parent/child records only through explicit admin routes, not normal `/parents/me/...` flows.
3. Student cannot access parent endpoints.
4. Teacher/tutor cannot access parent endpoints unless a separate support/admin workflow is explicitly added.
5. Every child-specific endpoint must verify ownership before reading or returning child data.

## Implementation Plan

### Phase 1: Contract and CDK Audit

- Read `stoa-infra` CDK resources and confirm:
  - DynamoDB table name and GSI names.
  - Cognito groups and app clients.
  - Lambda environment variables.
  - Current report bucket and report-related permissions.
- Read frontend parent service calls and confirm required backend paths.
- Read backend repositories and identify current access patterns.
- Decide whether current table/indexes support parent-child lookup without a new GSI.

Deliverable:

- Short implementation note in the milestone work log or PR description: "No infra change required" or exact CDK changes needed.

### Phase 2: Backend Parent API

- Add `/parents/me/children`.
- Add `/parents/me/children/{child_id}/summary`.
- Add `/parents/me/children/{child_id}/history`.
- Add `/parents/me/children/{child_id}/report`.
- Add `/parents/me/children/{child_id}/reports/{week}` if needed by frontend.
- Keep response shapes stable and frontend-friendly.
- Add parent-child ownership helper.
- Avoid table scans where existing indexes can support the query.

Backend files likely touched:

- `src/stoa/routers/parents.py`
- `src/stoa/db/repositories/user_repo.py`
- `src/stoa/db/repositories/question_repo.py`
- `src/stoa/db/repositories/practice_repo.py`
- `src/stoa/db/repositories/report_repo.py`
- `src/stoa/models/report.py`

### Phase 3: Frontend Parent Integration

- Update parent services to call the new backend endpoints.
- Remove silent `withDemoFallback` for parent-critical flows.
- Keep explicit empty/error states.
- Confirm parent pages display:
  - child list
  - child summary
  - child history
  - report missing/available states

Frontend files likely touched:

- `src/services/parent/parentApi.ts`
- `src/services/parent/parentReportApi.ts`
- `src/pages/parent/ParentDashboardPage.tsx`
- `src/pages/parent/ChildSummaryPage.tsx`
- `src/pages/parent/ChildLearningHistoryPage.tsx`
- `src/pages/parent/ChildReportPage.tsx`
- parent hooks/components as needed

### Phase 4: Test Data and Verification

- Create or document one parent test account and one linked student account.
- Seed or verify enough student activity data for summary/history:
  - at least one question or conversation
  - at least one practice progress or mistake record
  - optional report record
- Verify no-child parent empty state.
- Verify missing-report state.

### Phase 5: Tests

Backend tests:

- Parent can list only their own children.
- Parent cannot access another parent's child summary/history/report.
- Student cannot call parent endpoints.
- Empty child list returns stable empty response.
- Missing report returns `status=missing`, not a 500 or mock content.

Frontend tests:

- Parent dashboard renders real API response.
- Parent dashboard renders no-child empty state.
- Child report page renders missing-report state.
- Parent service paths match backend `/parents/me/...` routes.

## Acceptance Criteria

This milestone is complete when:

- A real parent account can log in through the frontend.
- Parent dashboard loads children from backend, not mock data.
- Parent can open child summary backed by real backend aggregation.
- Parent can open child history backed by real backend data.
- Parent report page handles both existing and missing reports correctly.
- Parent-critical frontend pages no longer silently hide backend failures with demo data.
- Backend authorization prevents cross-parent child access.
- Required backend and frontend tests pass.
- Any infrastructure dependency is either confirmed existing in CDK or implemented in CDK.

## Risks and Watchpoints

### Parent-Child Identity Mismatch

Registration currently creates local user IDs while authenticated JWTs use Cognito `sub`.

Risk:

- Parent/child links may not resolve consistently if records use different IDs.

Mitigation:

- Decide and document the canonical user identifier for parent-child ownership.
- Update lookup helpers to resolve by email or Cognito subject only as a compatibility fallback.

### Scan-Based Child Lookup

Current parent child lookup scans by `parent_id`.

Risk:

- Works for small MVP data but may not scale or may miss paginated results.

Mitigation:

- Check `database_stack.py` for available GSIs before implementing.
- If no suitable index exists, document whether this milestone accepts scan for MVP or requires a new GSI in CDK.

### Frontend Demo Fallback Masks Errors

Risk:

- Parent pages can appear complete while backend data is missing.

Mitigation:

- Remove fallback from parent-critical flows, or gate it behind an explicit demo mode only.

### Report Generation Not Implemented

Risk:

- Users expect reports to exist after opening report pages.

Mitigation:

- This milestone only handles query/display/empty states.
- Automatic report generation is a separate follow-up milestone.

## Explicit Follow-Up Milestone

After this milestone, the next likely milestone is:

**Milestone: Weekly Report Automation**

Scope:

- `report_service.py`
- weekly aggregation
- Bedrock summary generation
- S3 report artifact storage if needed
- EventBridge schedule target
- SES weekly email send
- operational monitoring and retry behavior
