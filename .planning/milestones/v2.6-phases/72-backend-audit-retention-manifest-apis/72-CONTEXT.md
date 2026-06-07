# Phase 72: Backend Audit Retention Manifest APIs - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning
**Mode:** Autonomous, derived from Phase 71 contract

<domain>
## Phase Boundary

Admins need backend-mediated audit retention status and metadata-only manifest generation for report operations evidence. The backend must make evidence retention-ready by producing stable digests and operator-facing status without storing raw report artifacts or claiming compliance-grade immutable storage.

</domain>

<decisions>
## Implementation Decisions

- Expose admin-only manifest and status endpoints under `/admin/reports/audit-retention/*`.
- Support the Phase 71 allowlist first: recovery job refs, report refs, support handoff refs, and inline release evidence validation.
- Return full manifests ephemerally and write only redacted append-only audit metadata for generation/refusal.
- Refuse destructive retention, Object Lock/WORM/legal hold, unsupported scopes, and privacy denylist failures.
- Reuse existing recovery evidence sanitizers and release evidence denylist validation.

</decisions>

<code_context>
## Existing Code Insights

- `src/stoa/routers/admin.py` already hosts report operations, recovery evidence, release evidence, and support handoff APIs behind `require_role("admin")`.
- `src/stoa/services/report_recovery_evidence_service.py` already projects jobs, targets, and audit rows into metadata-only summaries.
- `src/stoa/services/release_evidence_service.py` already validates and scans values for private artifact/secrets markers.
- `src/stoa/db/repositories/report_repo.py` already conditionally appends report, recovery job, and support handoff audit rows.

</code_context>

<specifics>
## Specific Ideas

- Add a `report_audit_retention_service` that builds status and manifest responses.
- Compute SHA-256 digests from sanitized canonical JSON.
- Add repository helpers for retention audit writes and support handoff audit listing.
- Add focused tests to `tests/test_admin_report_ops.py` for auth, schema, privacy, refusal, status, and audit rows.

</specifics>

<deferred>
## Deferred Ideas

- CDK-managed WORM/Object Lock storage.
- Legal hold administration.
- Retention expiry/deletion workflows.
- Persisting full manifest objects as durable evidence records.

</deferred>
