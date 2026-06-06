# Phase 55: Backend Artifact Edit Preview And Versioned Apply APIs - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

Phase 55 implements admin-only backend APIs for bounded report artifact edit previews and versioned apply. It must use Phase 54's contract, preserve backend-mediated S3 access, write new artifact versions instead of overwriting prior artifacts in place, update report metadata conditionally, and emit append-only audit evidence.

</domain>

<decisions>
## Implementation Decisions

### API Contract
- Add preview, read-preview, and apply endpoints under existing admin report routes.
- Preview accepts a non-empty reason and allowlisted proposed artifact fields.
- Apply accepts an existing preview/draft ID plus a non-empty operator approval reason.
- Responses expose sanitized diff/preview, opaque draft/version IDs, timestamps, validation status, and operation result only.

### Artifact Editing
- Implement artifact editing in a new service module instead of expanding metadata-only `report_edit_service.py`.
- Edit only the generated report `content` section; never allow identity fields, S3 keys, raw HTML, or arbitrary JSON patch.
- Render HTML server-side from sanitized content so the frontend never submits raw HTML.
- Store backend-only source artifact keys inside the draft row for stale checks and apply, but never return those keys to the frontend.

### Versioned Apply
- Add versioned key helpers under the existing `weekly-reports/{parent_id}/{student_id}/{week_start}/versions/{version_id}/` prefix.
- Write JSON and HTML versioned artifacts before conditionally updating report summary metadata.
- Compare report `updated_at`, current artifact version, and source JSON/HTML keys before apply.
- Record previous current artifact version/key metadata server-side for rollback evidence.

### Audit And Privacy
- Use existing report audit events with new action names for preview and apply.
- Redact or remove private artifact fields from audit payloads before persistence.
- Reject proposed values containing private artifact markers or auth/session token markers.
- Tests must assert route responses and audit events do not contain private artifact markers.

### the agent's Discretion
- Exact Pydantic model names and helper names may follow existing admin route conventions.
- The sanitized diff can be field-level and structured rather than rendered HTML diff.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `report_artifact_service.py` provides S3 JSON/HTML read/write helpers and canonical key validation.
- `report_edit_service.py` provides a useful draft/apply/audit/stale-check pattern.
- `report_repo.py` already stores report summary, edit draft, and audit rows under `REPORT#{report_id}`.
- `tests/test_admin_report_ops.py` has fixtures and privacy denylist assertions for admin report operations.

### Established Patterns
- Admin endpoints use `Depends(require_role("admin"))`.
- Mutations go through service modules and route-specific HTTP error mappers.
- Tests monkeypatch repository/service calls rather than requiring AWS resources.
- Private S3 markers are redacted before appearing in user-visible API responses.

### Integration Points
- `src/stoa/services/report_artifact_service.py`
- `src/stoa/services/report_artifact_edit_service.py`
- `src/stoa/db/repositories/report_repo.py`
- `src/stoa/routers/admin.py`
- `tests/test_admin_report_ops.py`
- `tests/test_report_artifact_service.py`

</code_context>

<specifics>
## Specific Ideas

- Use `ARTIFACT_EDIT_DRAFT#{draft_id}` rows for artifact edit previews.
- Use `edit_report_artifact` as the report `last_operation`.
- Use `create_report_artifact_edit_preview` and `apply_report_artifact_edit` as audit actions.

</specifics>

<deferred>
## Deferred Ideas

- Rollback endpoint.
- WORM audit storage.
- Frontend UI controls, handled by Phase 56.
- Production live mutation, handled only through Phase 57 safe-fixture rules.

</deferred>
