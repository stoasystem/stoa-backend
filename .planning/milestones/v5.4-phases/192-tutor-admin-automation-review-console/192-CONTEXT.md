# Phase 192: Tutor Admin Automation Review Console - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a tutor/admin-facing frontend console for controlled assignment automation preview, refusal review, approved batch execution, and result/history visibility.

</domain>

<decisions>
## Implementation Decisions

### Scope
- Use existing v5.3 backend preview and execute routes directly.
- Do not implement automatic teacher/tutor dispatch.
- Keep no-demo-fallback behavior explicit by avoiding `withDemoFallback`.
- Reuse existing dashboard layout, card, button, input, label, and direct React Query patterns.

### the agent's Discretion
The console may use a compact operator layout with dense controls and result cards, provided backend errors remain visible.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `/Users/zhdeng/stoa-frontend/src/layouts/DashboardLayout.tsx`
- `/Users/zhdeng/stoa-frontend/src/components/common/PageContainer.tsx`
- `/Users/zhdeng/stoa-frontend/src/components/common/PageHeader.tsx`
- `/Users/zhdeng/stoa-frontend/src/components/ui/*`

### Established Patterns
- API calls use `httpClient`.
- Server state uses TanStack Query hooks.
- Existing operational pages use role-routed dashboard pages.

### Integration Points
- `POST /adaptive/students/{student_id}/assignment-automation/batches/preview`
- `POST /adaptive/students/{student_id}/assignment-automation/batches/execute`
- `GET /adaptive/students/{student_id}/assignments`

</code_context>

<specifics>
## Specific Ideas

Expose student id, policy status, subject/topic/source filters, max assignments, confidence threshold, selected candidates, refused candidates, execution results, and assignment history.

</specifics>

<deferred>
## Deferred Ideas

Persistent saved automation policies and bulk cohort automation remain future scope.

</deferred>
