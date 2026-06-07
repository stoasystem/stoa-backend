# Phase 77: Admin Immutable Evidence And Legal Hold UI - Context

**Gathered:** 2026-06-07
**Status:** Complete
**Mode:** Autonomous, derived from Phase 76 backend APIs

<domain>
## Phase Boundary

Phase 77 adds admin `/admin/report-operations` UI controls for immutable evidence status, immutable manifest persistence attempts, legal hold status, and legal hold apply/release metadata. The UI must preserve the existing dense operational report-ops design and keep immutable storage visibly CDK-gated/not-configured when backend config is absent.

</domain>

<decisions>
## Implementation Decisions

### Surface Placement
- Add a distinct Immutable evidence panel adjacent to Audit retention.
- Keep the existing Audit retention panel semantics unchanged.
- Reuse the selected recovery job/report/release evidence reference builder.
- Show CDK-gated storage state separately from legal hold state.

### Controls
- Provide explicit buttons for immutable status, manifest persistence, legal hold status, apply hold, release hold, copy JSON, and download JSON.
- Require operator reasons for persistence and legal hold state changes.
- Reuse existing compact section, badge, detail row, and JSON preview patterns.
- Keep destructive storage/delete actions absent.

### Privacy
- Render only allowlisted backend metadata and redacted JSON previews.
- Preserve denylist assertions for report artifact keys, S3 keys, presigned URLs, raw JSON/HTML, auth tokens, cookies, passwords, and AWS secrets.
- Do not show backend storage resource names, bucket names, object keys, or raw object payloads.

### the agent's Discretion
All implementation choices not fixed above follow the existing admin report operations UI conventions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/pages/admin/ReportOperationsPage.tsx` already contains local state, mutations, selection references, and panel composition for report operations.
- `src/services/admin/adminApi.ts` already defines audit-retention types/client functions.
- `src/hooks/admin/useAdminReportOperations.ts` already wraps admin report ops mutations.
- `tests/e2e/admin-report-operations.spec.ts` already mocks audit-retention routes and asserts privacy denylist cleanliness.

### Established Patterns
- Operational UI uses compact bordered sections rather than landing-page styling.
- Copy/download controls serialize metadata JSON client-side.
- Playwright route mocks live inside the single admin report operations flow.

### Integration Points
- Add immutable/legal-hold types and client functions beside audit retention.
- Add mutation hooks beside audit retention hooks.
- Add `ImmutableEvidencePanel` after `AuditRetentionPanel`.
- Extend the existing e2e test with immutable/legal-hold mocks and assertions.

</code_context>

<specifics>
## Specific Ideas

Frontend commit `c1e2676` in `/Users/zhdeng/stoa-frontend` contains the Phase 77 UI implementation.

</specifics>

<deferred>
## Deferred Ideas

- Production deploy/live browser smoke is Phase 78.
- CDK-managed immutable storage resources remain outside Phase 77.

</deferred>
