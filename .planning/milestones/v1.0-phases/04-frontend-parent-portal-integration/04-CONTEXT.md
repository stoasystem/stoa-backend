---
phase: 04-frontend-parent-portal-integration
status: ready_for_planning
mode: smart-discuss-autonomous
gathered: 2026-06-02
---

# Phase 4: Frontend Parent Portal Integration - Context

**Gathered:** 2026-06-02
**Status:** Ready for execution planning
**Mode:** Smart discuss autonomous

<domain>
## Phase Boundary

This phase aligns the parent frontend in `/Users/zhdeng/stoa-frontend` to the Phase 3 backend routes:

- `GET /parents/me/children`
- `GET /parents/me/children/{child_id}/summary`
- `GET /parents/me/children/{child_id}/history`
- `GET /parents/me/children/{child_id}/report`

The goal is service and page contract alignment with explicit loading, empty, missing, and error states. This phase does not redesign the parent portal, implement monthly reports, add new backend report generation, or broaden visual styling beyond what is needed for the new data shapes.

</domain>

<decisions>
## Implementation Decisions

### Parent-Critical Flows Must Not Silently Fallback

- Remove `withDemoFallback` from normal parent portal service calls for children, summary, history, and weekly report.
- Let backend errors surface through React Query `isError` states.
- Keep mock/demo data only for explicit demo-only surfaces outside the Phase 4 normal parent flow.

### Backend Shapes Are Canonical

- `ParentChild` should use Phase 3 `ChildSummary`: `id`, `userId`, `name`, `email`, `grade`, `subjects`, `relationship`.
- `ChildLearningSummary` should use Phase 3 summary counters and `recentActivity`.
- `ChildLearningHistory` should use `{ items: ParentChildHistoryEvent[] }`.
- Weekly report service should use `ParentChildReportState`, not the older rich `ParentWeeklyReport`.

### Local Demo Backend Is Part of Verification

- The frontend repo includes a local FastAPI demo backend used by Playwright.
- Its parent endpoints currently return older shapes, so Phase 4 should update those parent endpoints to mirror Phase 3 response shapes where needed.
- This keeps Playwright useful while still preventing service-level silent fallback.

### UI Scope

- Use existing parent page layout and component patterns.
- Add explicit empty states for no children, empty summary/history data, and missing report state.
- Avoid broad redesign, monthly report work, or changes to unrelated demo/admin/organization surfaces.

</decisions>

<code_context>
## Existing Code Insights

### Frontend Service Files

- `/Users/zhdeng/stoa-frontend/src/services/parent/parentApi.ts` already calls the correct `/parents/me/...` URLs, but wraps calls in `withDemoFallback` and uses old Phase 11 types.
- `/Users/zhdeng/stoa-frontend/src/services/parent/parentReportApi.ts` calls `/parents/me/children/{childId}/report`, but expects old `ParentWeeklyReport` instead of Phase 3 `ParentChildReportState`.
- `/Users/zhdeng/stoa-frontend/src/services/parent/parentQueryKeys.ts` has child summary/history/report keys; week-specific report key is optional for this phase unless the page needs it.

### Frontend Type and Page Mismatches

- `src/types/parent.ts` expects `primarySubjects`, `stats`, object weak topics, `recentQuestions`, and `teacherHelpRecords`.
- Phase 3 backend returns `subjects`, summary counters, `weakTopics: string[]`, and `recentActivity`.
- `src/pages/parent/ParentDashboardPage.tsx` falls back to hard-coded `user-student` for practice summary.
- `src/pages/parent/ChildSummaryPage.tsx` renders old summary fields.
- `src/pages/parent/ChildLearningHistoryPage.tsx` is close, but should type and render Phase 3 event shape including nullable subject.
- `src/pages/parent/ChildReportPage.tsx` renders old rich report fields; it must handle available and missing report states.

### Demo Backend

- `/Users/zhdeng/stoa-frontend/backend/app/main.py` implements local `/parents/me/...` endpoints but returns old parent summary/report shapes.
- Updating this local backend is needed for `tests/e2e/parent-dashboard.spec.ts` after removing service fallbacks.

### Verification

- Frontend has no unit test runner in `package.json`.
- Available commands:
  - `npm run build`
  - `npm run lint`
  - `npx playwright test tests/e2e/parent-dashboard.spec.ts`
- Backend Phase 3 parent route tests already pass in `/Users/zhdeng/stoa-backend`.

</code_context>

<constraints>
## Workspace Constraint

The active writable root is `/Users/zhdeng/stoa-backend`. Phase 4 implementation edits target `/Users/zhdeng/stoa-frontend`, which is currently outside the writable root. Planning artifacts can be written in this backend repo. Frontend implementation requires explicit approval/escalation or a workspace permission change.
</constraints>

<source_audit>
## Source Audit

| Source | ID | Feature/Requirement | Status | Notes |
|--------|----|---------------------|--------|-------|
| ROADMAP | Phase 4 | Frontend service/page integration with real backend responses and no silent demo fallback. | COVERED | Plans below target services, pages, demo backend, and verification. |
| REQ | FRONT-01 | Parent frontend services call `/parents/me/...`. | COVERED | Service URLs already mostly correct; remove fallbacks and update types. |
| REQ | FRONT-02 | Dashboard renders backend child list and no-child state. | COVERED | Update child type, child card, hard-coded fallback, no-child state. |
| REQ | FRONT-03 | Summary/detail and history render backend data with empty/error states. | COVERED | Update summary/history types and pages. |
| REQ | FRONT-04 | Report view renders available and missing report states. | COVERED | Update report service/types/page. |
| REQ | FRONT-05 | Parent-critical pages surface backend failures instead of hiding behind `withDemoFallback`. | COVERED | Remove service fallback in normal parent API calls. |
| REQ | FRONT-06 | Frontend behavior verified with focused tests. | COVERED | Build, lint, and parent Playwright flow. |
</source_audit>
