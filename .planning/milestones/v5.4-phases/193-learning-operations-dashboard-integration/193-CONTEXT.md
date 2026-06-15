# Phase 193: Learning Operations Dashboard Integration - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a frontend learning operations dashboard that consumes curriculum analytics, warehouse readiness, and warehouse export summaries.

</domain>

<decisions>
## Implementation Decisions

### Scope
- Use existing backend analytics routes directly.
- Treat `not_configured` live warehouse state as a normal internal-development state.
- Avoid demo fallback and render backend errors visibly.

### the agent's Discretion
Use compact cards and lists for operational scanning rather than a marketing-style layout.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Existing dashboard layout and UI components.
- Existing analytics event client.

### Established Patterns
- Admin/organization operational pages route through `AppRouter.tsx`.
- API modules live under `src/services/**`; hooks live under `src/hooks/**`.

### Integration Points
- `GET /admin/curriculum/analytics/dashboard`
- `GET /admin/curriculum/analytics/warehouse-readiness`
- `GET /admin/curriculum/analytics/warehouse-export`

</code_context>

<specifics>
## Specific Ideas

Show summary metrics, sequencing coverage, quality hotspots, interventions, warehouse readiness, no-live-warehouse state, and export summary.

</specifics>

<deferred>
## Deferred Ideas

Live BI/warehouse deployment and scheduled export orchestration remain future scope.

</deferred>
