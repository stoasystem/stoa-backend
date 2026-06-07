# Requirements: v2.6 Audit Retention And Immutable Evidence Readiness

**Milestone:** v2.6
**Status:** Active
**Created:** 2026-06-07

## Goal

Make report operations audit evidence ready for stronger retention and future immutable storage by defining retention contracts, CDK decisions, backend evidence sealing/manifest behavior, admin visibility, and release verification without weakening existing privacy boundaries.

## Requirements

### AUDITRET-01 Audit Retention Contract And CDK Readiness

Implementers have a precise audit retention contract and infrastructure decision before adding retention/sealing behavior.

Acceptance criteria:

- Contract defines audit event classes, retention categories, retention clocks, sealing metadata, verification metadata, deletion/expiry semantics, and operator-facing status.
- Contract distinguishes application-enforced append-only audit, retained evidence manifests, and compliance-grade immutable/WORM storage.
- Privacy model forbids retaining raw report artifacts, S3 keys, presigned URLs, auth tokens, passwords, cookies, AWS secrets, or raw unreviewed report JSON/HTML in audit retention evidence.
- CDK readiness classifies whether existing DynamoDB/S3/resources are sufficient for v2.6, or exactly what CDK-managed resource change would be required for future WORM storage.

### AUDITRET-02 Backend Audit Evidence Sealing And Retention Manifest

Admins and operators can generate metadata-only retention manifests for audit evidence without exposing private artifacts.

Acceptance criteria:

- Backend can produce a bounded retention manifest for selected report operation/recovery/release/support-handoff audit evidence.
- Manifest includes hashes or stable metadata sufficient to detect evidence drift without storing raw payloads.
- Manifest generation writes redacted audit metadata and refuses unsupported destructive retention actions.
- Tests cover admin-only auth, manifest schema, privacy denylist, drift metadata, refusal behavior, and audit rows.

### AUDITRET-03 Audit Retention Observability

Operators can inspect retained/sealed audit evidence status without private artifact exposure.

Acceptance criteria:

- Backend exposes admin-only retention status for supported audit scopes.
- Status distinguishes sealed, unsealed, expired/skipped, refused, and unsupported scopes.
- Status output remains metadata-only and release-evidence validation can check its privacy boundary.
- Tests cover status output, failure states, and denylist behavior.

### UI-13 Admin Audit Retention UI

Admin report operations UI exposes audit retention manifest/status controls.

Acceptance criteria:

- UI exposes retention status/manifest controls only to admins.
- UI renders allowlisted retention metadata, evidence references, validation failures, and copy/download controls.
- UI does not perform destructive retention deletion or direct WORM mutation.
- UI does not render secrets, S3 keys, presigned URLs, raw report JSON/HTML, or raw artifact payloads.
- Playwright covers retention status, manifest preview/download, error states, admin-only gating, and privacy denylist.

### VERIFY-09 v2.6 Release Gate And Live Verification

v2.6 closes with release and live verification evidence for audit retention readiness.

Acceptance criteria:

- Backend/frontend deploy evidence, commit SHAs, Lambda manifest/runtime, CDK diff/deploy evidence, local quality gates, API request IDs, and browser smoke results are recorded.
- Production smoke is read-only by default and does not mutate report artifacts, delete audit records, or write to external systems.
- Any retention/sealing operation is metadata-only unless a CDK-approved immutable storage path exists.
- Final audit records residual risks and future requirements, including whether WORM storage remains future scope.

## Future Requirements

- Compliance-grade WORM audit storage with CDK-managed resources if approved.
- Legal hold and retention policy administration.
- Cross-system support ticket/evidence retention integrations.
- Dedicated orchestration if retention verification needs asynchronous workflows.
- Rich/WYSIWYG report editor.
- PDF/multilingual delivery.

## Out of Scope

- Manual AWS console changes.
- Deleting existing audit rows.
- Retaining raw report artifacts or private storage identifiers in committed evidence.
- New AWS resources unless Phase 71 proves they are required and defines the CDK path.
- Claiming compliance-grade immutability without deployed CDK-managed immutable storage evidence.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUDITRET-01 | Phase 71 | Complete |
| AUDITRET-02 | Phase 72 | Complete |
| AUDITRET-03 | Phase 72 | Complete |
| UI-13 | Phase 73 | Complete |
| VERIFY-09 | Phase 74 | Not started |
