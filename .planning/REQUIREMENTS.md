# Requirements: v2.0 Controlled Report Editing MVP

**Milestone:** v2.0
**Status:** Active
**Created:** 2026-06-05

## Goal

Admins can safely propose and apply bounded report content edits with append-only audit evidence and no direct S3 exposure.

## Requirements

### EDIT-01 Edit Draft Lifecycle

Admins can create and read report edit drafts.

Acceptance criteria:

- Draft APIs require admin authorization.
- Drafts bind to parent id, student id, week start, report id, source updated timestamp, editor, reason, and proposed fields.
- Draft responses omit private S3 keys, presigned URLs, raw report JSON/HTML, auth tokens, and artifact payloads.
- Drafts are bounded to a small allowlist of editable metadata/content fields for the MVP.

### EDIT-02 Apply Edit

Admins can apply a valid draft to a report through the backend.

Acceptance criteria:

- Apply requires admin authorization and a valid draft id.
- Apply rejects stale drafts when source report metadata changed.
- Apply validates proposed fields before mutation.
- Apply writes updated report metadata and append-only audit.

### EDIT-03 Audit Evidence

Report edits produce audit evidence.

Acceptance criteria:

- Audit includes editor, reason, draft id, before/after metadata, validation result, and source/apply timestamps.
- Audit remains metadata-only and redacted.
- Existing report audit APIs show edit events.

### EDIT-04 Privacy And Storage Safety

Report editing does not expose or directly manipulate private artifacts from the frontend.

Acceptance criteria:

- Frontend never receives S3 keys, presigned URLs, raw HTML, or raw JSON.
- Backend does not perform broad S3 scans.
- MVP may update report metadata fields only; artifact rewrite is deferred unless safety evidence requires it.
- CDK diff remains no-new-infra unless explicitly justified.

### UI-07 Admin Editing UI

Admin report operations UI supports draft/apply editing controls.

Acceptance criteria:

- UI exposes draft controls for selected reports.
- UI distinguishes draft creation from apply mutation.
- UI shows validation/audit outcome and private marker denylist remains clean.
- Playwright covers draft/apply flow.

### VERIFY-03 v2.0 Release Gate

v2.0 closes with release and live verification evidence.

Acceptance criteria:

- Backend/frontend deploy evidence, commit SHAs, Lambda manifest/runtime, and quality gates are recorded.
- CDK diff/deploy evidence is classified.
- Production smoke is read-only and does not create/apply production edits.
- Final audit records residual risks and future requirements.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| EDIT-01 | Phase 50/51 | Complete |
| EDIT-02 | Phase 50/51 | Complete |
| EDIT-03 | Phase 51 | Complete |
| EDIT-04 | Phase 50/51/53 | In Progress |
| UI-07 | Phase 52 | Complete |
| VERIFY-03 | Phase 53 | Planned |
