# Requirements: v2.7 Immutable Audit Storage And Legal Hold Foundation

**Milestone:** v2.7
**Status:** Active
**Created:** 2026-06-07

## Goal

Implement the foundation for CDK-managed immutable audit evidence storage and legal hold/retention policy administration for report operations audit evidence, without exposing private report artifacts, deleting existing audit rows, or claiming compliance-grade immutability before deploy evidence proves it.

## Requirements

### IMMUTABLE-01 Immutable Audit Storage Contract And CDK Readiness

Implementers have a precise immutable audit storage contract, legal hold boundary, retention policy model, migration plan, and CDK decision before adding production writes.

Acceptance criteria:

- Contract defines immutable object shape, object identity, digest/signature metadata, retention clocks, legal hold states, policy ownership, verification metadata, and operator-visible status.
- Contract distinguishes current application-enforced append-only audit rows, v2.6 metadata-only retention manifests, and v2.7 CDK-managed immutable object persistence.
- Privacy model forbids raw report artifacts, S3 keys, presigned URLs, auth tokens, passwords, cookies, AWS secrets, raw unreviewed report JSON, and raw report HTML in immutable objects or committed evidence.
- CDK readiness classifies whether a new CDK-managed immutable resource is required and records the exact stack/resource/env-var/deploy evidence required before backend production writes are allowed.
- Plan explicitly refuses manual AWS console changes and destructive audit deletion.

### IMMUTABLE-02 Backend Immutable Retention Manifest Persistence

Admins can persist metadata-only retention manifests to an approved immutable storage path after CDK readiness is satisfied.

Acceptance criteria:

- Backend writer persists canonical metadata-only retention manifests with stable object identity and digest metadata.
- Writer refuses persistence when immutable storage configuration is missing, not CDK-approved, or privacy validation fails.
- Backend exposes admin-only read/status APIs for immutable manifest references without returning private storage identifiers or raw object payloads.
- Tests cover admin-only authorization, schema validation, digest stability, privacy denylist, configuration refusal, and append-only audit rows.

### LEGALHOLD-01 Legal Hold And Retention Policy Metadata

Admins can apply and inspect legal hold/retention policy metadata for supported report operations evidence scopes.

Acceptance criteria:

- Backend models legal hold states, policy IDs, retention clocks, reason fields, actor metadata, and release/refusal semantics.
- Legal hold changes are metadata-only, append-only audited, and do not delete or mutate prior audit rows.
- Unsupported scopes and destructive retention actions are refused with operator-safe reasons.
- Tests cover policy metadata, hold/release validation, refusal behavior, authorization, and audit evidence.

### UI-14 Admin Immutable Evidence And Legal Hold UI

Admin report operations UI exposes immutable evidence status and legal hold controls.

Acceptance criteria:

- UI exposes immutable evidence status, manifest persistence status, legal hold status, policy metadata, validation failures, and copy/download controls only to admins.
- UI uses allowlisted fields and does not render secrets, S3 keys, presigned URLs, raw report JSON/HTML, or raw artifact payloads.
- UI separates read-only status from any persistence/hold action and requires explicit operator reason fields for state-changing actions.
- Playwright covers status rendering, legal hold controls, refusal states, admin gating, and privacy denylist.

### VERIFY-10 v2.7 Release Gate And Live Verification

v2.7 closes with release evidence proving immutable storage and legal hold behavior are correctly gated and privacy-safe.

Acceptance criteria:

- Release gate records Lambda build manifest, backend deploy evidence, frontend deploy evidence, CDK diff/deploy evidence, commit SHAs, timestamps, admin-only API request IDs, and production read-only browser smoke.
- Evidence proves production UI/API do not expose raw report artifacts, S3 keys, presigned URLs, raw JSON/HTML, auth tokens, cookies, or AWS secrets.
- Evidence proves no production audit deletion and no customer report artifact mutation.
- Any production state-changing smoke uses only a named non-customer safe fixture or a metadata-only approved immutable/hold path with cleanup/rollback expectations documented.
- Final audit records whether compliance-grade WORM storage is deployed and what residual gaps remain.

## Future Requirements

- Direct support ticket/evidence retention integrations after an approved connector or secret-backed credential path exists.
- Dedicated Step Functions/SQS orchestration if immutable verification becomes asynchronous or long-running.
- Compliance/legal review of WORM retention periods and legal hold operating procedure.
- Rich/WYSIWYG report editor.
- PDF/multilingual report delivery.
- Billing and analytics product expansion.

## Out of Scope

- Manual AWS console changes.
- Deleting existing audit rows.
- Retaining raw report artifacts or private storage identifiers in committed evidence.
- Direct third-party support-system writes.
- Claiming compliance-grade WORM/Object Lock storage before CDK-managed deploy and live verification evidence are recorded.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| IMMUTABLE-01 | Phase 75 | Complete |
| IMMUTABLE-02 | Phase 76 | Planned |
| LEGALHOLD-01 | Phase 76 | Planned |
| UI-14 | Phase 77 | Planned |
| VERIFY-10 | Phase 78 | Planned |
