# Requirements: v2.8 CDK-Managed Immutable Evidence Storage Deployment

**Milestone:** v2.8
**Status:** Active
**Created:** 2026-06-07

## Goal

Deploy and enable CDK-managed immutable evidence storage for report operations retention manifests, then prove full metadata-only immutable manifest object persistence in production without exposing private artifacts, deleting audit rows, or mutating customer report artifacts.

## Requirements

### IMSTORE-01 Immutable Evidence Storage CDK Design And Deploy Readiness

Implementers have a verified CDK design, safety model, retention policy boundary, deploy plan, rollback/no-rollback expectations, and production verification plan before creating immutable storage resources.

Acceptance criteria:

- Design identifies the exact CDK stack/resource path, environment variables, IAM permissions, encryption, retention/object-lock posture, removal policy, and deploy evidence required.
- Design records AWS/CDK constraints that affect resource creation, update, rollback, retention periods, legal hold, and object deletion semantics.
- Design preserves v2.7 fail-closed behavior until backend runtime configuration and deploy evidence are present.
- Privacy model continues to forbid raw report artifacts, S3 keys, presigned URLs, auth tokens, cookies, passwords, AWS secrets, raw report JSON, and raw report HTML in immutable objects, logs, UI, API responses, and committed evidence.
- Phase 79 records production safety boundaries and a release gate that avoids customer report mutation.

### IMSTORE-02 CDK-Managed Immutable Evidence Storage Resource

Infrastructure defines and deploys the approved immutable evidence storage resource and API Lambda configuration.

Acceptance criteria:

- CDK creates the immutable evidence storage resource and injects required backend environment variables.
- API Lambda permissions are scoped to the approved immutable evidence resource/prefix and do not broaden report artifact access.
- CDK diff/deploy evidence, workflow run IDs, commit SHAs, and timestamps are recorded.
- Tests or static checks prove the stack exports/injects the expected settings and does not weaken existing report bucket privacy.

### IMSTORE-03 Backend Immutable Manifest Object Persistence Enablement

Backend immutable manifest persistence is enabled against the CDK-managed resource and remains metadata-only.

Acceptance criteria:

- Backend status changes from `not_configured` to configured only when CDK-injected settings are present.
- Persist API writes create-only metadata objects with stable identity, canonical digest metadata, and append-only audit rows.
- Read/status APIs return operator-safe references and verification metadata, not private storage identifiers or raw object payloads.
- Tests cover configured writes, duplicate/idempotency behavior, object-write failure, privacy denylist, audit rows, and missing-config refusal.

### VERIFY-11 v2.8 Release Gate And Live Immutable Storage Verification

v2.8 closes with deploy and live verification evidence proving immutable storage is configured, privacy-safe, and correctly gated.

Acceptance criteria:

- Release evidence records Lambda build manifest, backend deploy evidence, infra deploy evidence, CDK diff/deploy evidence, commit SHAs, timestamps, admin-only API request IDs, and production browser smoke.
- Production smoke proves immutable evidence status is configured and manifest persistence works only for approved metadata-only evidence or an approved non-customer safe fixture.
- Evidence proves no raw report artifacts, S3 keys, presigned URLs, raw JSON/HTML, auth tokens, cookies, passwords, or AWS secrets are exposed.
- Evidence proves no production audit deletion, no customer report artifact mutation, and no external support-system write.
- Final audit records any residual compliance/legal gaps, including retention-period approval and operational legal-hold procedure.

## Future Requirements

- Compliance/legal approval of exact retention periods and legal hold operating procedure.
- Direct support ticket/evidence retention integrations after an approved connector or secret-backed credential path exists.
- Dedicated Step Functions/SQS orchestration if immutable verification becomes asynchronous or long-running.
- Rich/WYSIWYG report editor.
- PDF/multilingual report delivery.
- Billing and analytics product expansion.

## Out of Scope

- Manual AWS console changes.
- Deleting existing audit rows.
- Retaining raw report artifacts or private storage identifiers in committed evidence.
- Direct third-party support-system writes.
- Customer report artifact mutation during smoke.
- Claiming broad regulatory compliance beyond the specific CDK-managed immutable storage behavior that release evidence proves.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| IMSTORE-01 | Phase 79 | Complete |
| IMSTORE-02 | Phase 80 | Planned |
| IMSTORE-03 | Phase 81 | Planned |
| VERIFY-11 | Phase 82 | Planned |
