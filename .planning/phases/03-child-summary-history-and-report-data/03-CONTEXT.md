# Phase 3: Child Summary, History, and Report Data - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning
**Mode:** Smart discuss autonomous

<domain>
## Phase Boundary

This phase implements child-specific parent backend routes under `/parents/me/children/{child_id}/...`: summary, learning history, current/latest report, and week-specific report lookup. Every endpoint must resolve the authenticated parent, verify the requested child belongs to that parent, then read real backend data. Missing data must produce stable empty/missing states, not fabricated mock content.

This phase does not implement automatic report generation, Bedrock report summaries, S3 report artifacts, EventBridge targets, SES weekly email workflows, frontend integration, PDF generation, or broad UI changes.

</domain>

<decisions>
## Implementation Decisions

### Ownership First

- Reuse Phase 2 `_resolve_parent_profile` and child lookup helpers.
- Add a child ownership helper that verifies `child_id` is in the resolved parent's linked children before any summary/history/report read.
- Deny cross-parent access before reading child-specific question, practice, or report data.

### Summary Data

- Build summary from real available sources only.
- Use `question_repo.list_by_student(child_id, limit=500)` for question counts, AI-resolved count, teacher-help/resolved count, weak topics, and recent activity.
- Use `practice_repo.get_progress(child_id)` and `practice_repo.get_mistakes(child_id)` for practice completion and weak-topic hints where available.
- Return zeroes and empty arrays when records are absent.
- Do not call Bedrock or fabricate report/summary prose.

### History Data

- Return newest-first `{ "items": [...] }` with a sane default limit, e.g. 20.
- Include question events from question records.
- Include practice progress/mistake events where timestamps exist.
- Include report events only when real report records are available through repository access.
- Conversation events may be deferred if current repository access is not reliable enough without a new scan-heavy route; do not invent data.

### Report Data

- Current/latest report endpoint should return `{ "status": "available", "report": ... }` if a real report exists and `{ "status": "missing", "report": null, "message": "No weekly report is available yet." }` otherwise.
- Week-specific endpoint should use existing `report_repo.get_report_by_week(parent_user_id, week)`, but only after child ownership is verified.
- If report records are parent/week scoped and not child-specific, filter/verify `student_id == child_id` before returning a report.
- Keep S3 report artifacts out of scope because Phase 1 found missing `S3_REPORTS_BUCKET` Lambda injection and permissions.

### the agent's Discretion

- Add route-local Pydantic models in `src/stoa/routers/parents.py` unless a shared model is clearly warranted.
- Add small repository helpers only when needed to avoid unsafe scans or duplicated query logic.
- Extend `tests/test_parent_children.py` or add a dedicated parent child data test file, whichever keeps tests readable.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- Phase 2 added `_resolve_parent_profile`, `_scan_children_for_parent`, and `/parents/me/children`.
- `question_repo.list_by_student(student_id, limit=..., last_key=...)` queries `GSI-StudentId` newest-first.
- `practice_repo.get_progress(user_id)` reads progress records under `PK=PROGRESS#{user_id}`.
- `practice_repo.get_mistakes(user_id)` reads mistake records under `PK=MISTAKES#{user_id}`.
- `report_repo.get_report_by_week(parent_id, week_start)` queries `GSI-ParentId`.
- `src/stoa/routers/students.py` has existing student summary/question-history logic that can inform aggregation.

### Established Patterns

- Parent routes already use route-local Pydantic models.
- Tests for parent routes use FastAPI dependency overrides and monkeypatch route helpers/repositories.
- Existing report model is legacy `WeeklyReportResponse`; new parent portal report state can be route-local.
- Existing practice/question repositories return raw DynamoDB dicts.

### Integration Points

- Phase 4 frontend services will call the new `/parents/me/children/{child_id}/...` routes.
- Phase 5 will broaden backend and frontend verification.
- Legacy `/parents/{parent_id}/reports/{week}` remains compatibility surface; this phase focuses on `/parents/me/...` normal parent portal routes.

</code_context>

<specifics>
## Specific Ideas

- Add routes:
  - `GET /parents/me/children/{child_id}/summary`
  - `GET /parents/me/children/{child_id}/history`
  - `GET /parents/me/children/{child_id}/report`
  - `GET /parents/me/children/{child_id}/reports/{week}`
- Use route order so `/me/children/{child_id}/...` routes are declared before `/{parent_id}/...` legacy routes.
- Summary response should include `student`, `questionsAskedThisWeek`, `aiResolvedThisWeek`, `teacherHelpRequestsThisWeek`, `practiceLessonsCompletedThisWeek`, `weakTopics`, and `recentActivity`.
- History event fields should include `id`, `type`, `title`, `summary`, `subject`, and `createdAt`.
- Missing report response should not be HTTP 404 on the new `/parents/me/...` route.

</specifics>

<deferred>
## Deferred Ideas

- Frontend service/page integration remains Phase 4.
- Full test data documentation remains Phase 5.
- Weekly report generation and email/PDF/S3 artifact workflows remain a follow-up milestone.
- Dedicated conversation repository can be deferred if Phase 3 can satisfy current requirements using question/practice/report records.

</deferred>
