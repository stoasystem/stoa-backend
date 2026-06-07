# Phase 73: Admin Audit Retention UI - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning
**Mode:** Autonomous, derived from Phase 72 backend APIs

<domain>
## Phase Boundary

Admins need a compact `/admin/report-operations` surface to inspect audit retention status and generate/copy/download metadata-only retention manifests. The UI must stay operational and dense, reuse the existing report operations page patterns, and avoid destructive retention or direct WORM mutation controls.

</domain>

<decisions>
## Implementation Decisions

- Add the panel between recovery evidence export and support handoff.
- Use selected recovery job, selected report, and optional release evidence JSON as manifest references.
- Render only allowlisted status, counts, references, digest metadata, refusal reasons, and privacy status.
- Keep copy/download local to the ephemeral manifest response.
- Do not add delete, expiry, legal hold, Object Lock, or external write controls.

</decisions>

<code_context>
## Existing Code Insights

- `src/pages/admin/ReportOperationsPage.tsx` already contains recovery evidence, support handoff, and release evidence panels with compact card-like sections.
- `src/services/admin/adminApi.ts` centralizes admin report operations API types and calls.
- `src/hooks/admin/useAdminReportOperations.ts` exposes mutation hooks for adjacent admin workflows.
- `tests/e2e/admin-report-operations.spec.ts` is the focused end-to-end route coverage for this page.

</code_context>

<specifics>
## Specific Ideas

- Add API types/functions for audit retention status and manifest generation.
- Add React Query mutation hooks.
- Add an `AuditRetentionPanel` with reason input, selected job/report/release evidence toggles, status check, manifest generation, copy, and download actions.
- Extend Playwright route mocks and assertions for status and manifest flows.

</specifics>

<deferred>
## Deferred Ideas

- Persisted manifest browsing.
- WORM/Object Lock/legal-hold controls.
- Dedicated retention policy administration.

</deferred>
