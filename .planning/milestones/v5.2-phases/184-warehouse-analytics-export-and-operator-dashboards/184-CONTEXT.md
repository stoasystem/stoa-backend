# Phase 184: Warehouse Analytics Export And Operator Dashboards - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Prepare warehouse-backed learning analytics without requiring a live warehouse. This phase adds backend/admin contracts for warehouse readiness, bounded export rows, and operator dashboard summaries built from existing curriculum quality, assignment outcome, and sequencing signals.

</domain>

<decisions>
## Implementation Decisions

### Warehouse Readiness
- Expose readiness as an admin analytics endpoint with schema version, export state, blockers, warnings, sources, and privacy contract.
- Treat live warehouse deployment as not configured during internal development.
- Keep export allowed as a local/API readiness concept, not a claim that BI infrastructure exists.

### Export Contract
- Export aggregate metric rows by default.
- Use bounded, redacted rows with no raw answers, answer keys, or student identifiers.
- Include source schema metadata for memory, assignments, curriculum progress, content quality, and aggregation windows.

### Operator Dashboard
- Provide cohort/operator summaries from available aggregate metrics.
- Surface sequencing coverage, assignment starts/skips/archives/completions, quality hotspots, stale content/intervention hints, and empty states.
- Keep dashboards useful for tutor/admin operations without drilling into private student data.

### the agent's Discretion
Implement Phase 184 in existing curriculum analytics service/repository/admin router. Avoid new infrastructure resources, scheduled jobs, or warehouse credentials.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `curriculum_analytics_service.content_quality_summary` already returns aggregate-only metrics and privacy flags.
- `curriculum_analytics_repo.list_metrics` reads aggregate metric rows.
- `admin.py` exposes `/admin/curriculum/analytics/content-quality` for admin/tutor/teacher roles.
- Phase 183 added assignment started/skipped/archived/completed counters.

### Established Patterns
- Admin analytics routes use Pydantic response models and role guard `require_role("admin", "tutor", "teacher")`.
- Analytics privacy contracts are explicit in response payloads.
- Tests monkeypatch the analytics repository and verify response shape through FastAPI.

### Integration Points
- `src/stoa/services/curriculum_analytics_service.py`
- `src/stoa/db/repositories/curriculum_analytics_repo.py`
- `src/stoa/routers/admin.py`
- `tests/test_curriculum_analytics.py`

</code_context>

<specifics>
## Specific Ideas

Add `/admin/curriculum/analytics/warehouse-readiness`, `/admin/curriculum/analytics/warehouse-export`, and `/admin/curriculum/analytics/dashboard`.

</specifics>

<deferred>
## Deferred Ideas

- Live warehouse/BI deployment.
- Scheduled export jobs.
- Cross-system joins beyond stable aggregate keys.

</deferred>
