# Requirements: v1.9 Recovery Resume And Support Evidence Packages

**Milestone:** v1.9
**Status:** Active
**Created:** 2026-06-05

## Goal

Admins can resume failed/refused/not_found/skipped recovery subsets from prior jobs and generate support-safe incident evidence packages without exposing private report artifacts or creating unbounded scans.

## Requirements

### RESUME-01 Resume Preview

Admins can preview a bounded target subset from a prior recovery job before creating a resume job.

Acceptance criteria:

- Preview requires admin authorization.
- Preview requires a source `job_id`.
- Preview supports only allowed target results: `failed`, `refused`, `not_found`, `skipped_cancelled`.
- Preview returns metadata-only target samples.
- Preview records source job type and eligible/refused/missing counts.
- Preview token binds to source job, job type, result filters, operator reason, max targets, and target snapshot hash.

### RESUME-02 Resume Job Creation

Admins can create a new recovery job from a valid preview of a prior job's resumable target subset.

Acceptance criteria:

- Create requires a valid preview token.
- Create writes `source_job_id`, inherited `job_type`, reason, filters, counters, and stable target snapshots.
- Create refuses source jobs without eligible targets.
- Create invokes the existing weekly worker event for the inherited job type.
- Create writes an audit event linking source and resumed jobs.

### RESUME-03 Resume Worker Execution

Resumed jobs execute through existing recovery worker paths.

Acceptance criteria:

- Resumed `resend_email` jobs reuse the resend worker target execution path.
- Resumed `retry_generation` jobs reuse the generation retry worker target execution path.
- Target results and counters update the same way as normal recovery jobs.
- Cancellation and failure thresholds still apply.
- Source job linkage is preserved in job metadata and audit events.

### RESUME-04 Authorization, Privacy, And Audit

Resume operations are admin-only, metadata-only, and audit-linked.

Acceptance criteria:

- Non-admin users cannot preview/create resume jobs.
- Responses omit private S3 keys, presigned URLs, raw report JSON/HTML, auth tokens, and artifact payloads.
- Audit includes actor, source, source job id, resumed job id, result filters, counts, request id/correlation id, and result.
- Production live smoke remains read-only unless an approved safe fixture is explicitly named.

### EVIDENCE-01 Support Evidence Package

Admins can generate a support-safe evidence package for a recovery job.

Acceptance criteria:

- Package includes job summary, target result rollups, selected target metadata, job audit timeline, report audit references, request IDs, and redacted operator notes.
- Package supports optional `source_job_id` / resumed job linkage.
- Package remains metadata-only.
- Package has bounded limits for targets and audit events.

### EVIDENCE-02 Evidence Package Observability

Evidence package generation is observable without mutating report recovery state.

Acceptance criteria:

- Package response includes request id and export timestamp.
- Package generation does not create or mutate recovery jobs.
- Package can indicate partial results when limits truncate target/audit sections.
- Package privacy metadata records that private artifact fields are omitted.

### UI-06 Resume And Evidence Package UI

The admin report operations UI supports resume preview/start and support evidence package export.

Acceptance criteria:

- UI exposes resume controls for selected jobs with resumable target results.
- UI shows source job, inherited job type, target result filters, counts, and operator reason.
- UI can preview/start resume jobs and select the resumed job.
- UI can export/view/copy/download support-safe evidence packages.
- UI copy preserves read-only versus mutation distinction.

### VERIFY-02 v1.9 Release Gate

v1.9 closes with release and live verification evidence.

Acceptance criteria:

- Backend and frontend deploy run IDs, commit SHAs, job IDs, timestamps, and outcomes are recorded.
- Lambda build manifest and runtime state are recorded.
- CDK diff/deploy evidence is classified.
- Production API checks record request IDs and admin authorization behavior.
- Production browser smoke verifies UI presence and support package read-only behavior without creating a production resume job.
- Final milestone audit records residual risks and future requirements.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| RESUME-01 | Phase 46/47 | Complete |
| RESUME-02 | Phase 47 | Complete |
| RESUME-03 | Phase 47 | Complete |
| RESUME-04 | Phase 46/47/49 | In Progress |
| EVIDENCE-01 | Phase 46/48 | Complete |
| EVIDENCE-02 | Phase 48 | Complete |
| UI-06 | Phase 48 | Complete |
| VERIFY-02 | Phase 49 | Planned |
