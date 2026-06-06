# Phase 64: Admin Release Evidence And Fixture Status UI - Context

**Gathered:** 2026-06-06
**Status:** Ready for implementation
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

Phase 64 adds admin-facing release evidence validation and safe-fixture status controls to the existing `/admin/report-operations` surface. The UI must consume the Phase 63 backend endpoints without triggering report mutation.

</domain>

<decisions>
## Implementation Decisions

- Add the release evidence controls to the existing admin report operations page rather than creating a new route.
- Keep the interaction read-only: validate pasted/synthetic release evidence JSON and load fixture status only.
- Render compact status metrics and redacted JSON output consistent with the existing recovery evidence export UI.
- Avoid labels that collide with existing report operation controls used by Playwright and operators.

</decisions>

<code_context>
## Existing Code Insights

- Frontend repo: `/Users/zhdeng/stoa-frontend`.
- Main page: `src/pages/admin/ReportOperationsPage.tsx`.
- Admin API wrappers: `src/services/admin/adminApi.ts`.
- React Query hooks: `src/hooks/admin/useAdminReportOperations.ts`.
- Focused Playwright test: `tests/e2e/admin-report-operations.spec.ts`.

</code_context>

<deferred>
## Deferred Ideas

- Persisting release evidence bundles.
- Pulling live deploy run metadata directly from GitHub.
- A separate release management route.

</deferred>
