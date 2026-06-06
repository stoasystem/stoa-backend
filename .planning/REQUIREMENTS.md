# Requirements: v2.4 Support Evidence Export Destinations And Ticket Handoff

**Milestone:** v2.4
**Status:** Active
**Created:** 2026-06-07

## Goal

Operators can turn redacted recovery, rollback, fixture, and release evidence into support-safe handoff packages for tickets or external support workflows without exposing private report artifacts or requiring unapproved third-party credentials.

## Requirements

### HANDOFF-01 Support Handoff Package Contract

Implementers have a precise support handoff package contract before adding APIs or UI.

Acceptance criteria:

- Contract defines package inputs, package sections, evidence references, operator reason fields, package status, generated timestamps, and failure/skipped semantics.
- Package can represent recovery evidence, support evidence packages, release evidence, safe-fixture status, rollback evidence, and operator notes as metadata-only sections.
- Package output is suitable for manual ticket creation, copy/paste, or download without requiring an external support system.
- Contract defines stable schema/version fields for future external destination adapters.

### HANDOFF-02 Destination Policy, Privacy Model, And CDK Readiness

Support handoff destination behavior is safe by default and infrastructure-ready before implementation.

Acceptance criteria:

- Destination policy distinguishes manual copy/download destinations from direct third-party write destinations.
- Direct external writes are refused unless an approved connector or secret-backed credential path exists.
- Privacy model forbids secrets, auth tokens, passwords, S3 keys, presigned URLs, raw report JSON/HTML, raw artifact payloads, and customer data beyond approved support-safe identifiers.
- CDK readiness classifies whether existing API, DynamoDB, S3, and frontend resources are sufficient or exactly what infrastructure change is required.

### HANDOFF-03 Backend Support Handoff Package APIs

Admins can generate and validate redacted support handoff packages through backend-mediated APIs or CLI tooling.

Acceptance criteria:

- Backend accepts bounded evidence references and operator notes.
- Backend validates references, composes the metadata-only package, and returns allowlisted fields only.
- Backend records redacted audit evidence for package generation.
- Backend refuses unsupported direct external destinations.
- Tests cover admin-only auth, validation failures, redaction denylist, unsupported destination refusal, and audit metadata.

### HANDOFF-04 Handoff Observability And Audit

Support handoff package generation is traceable without exposing private artifacts.

Acceptance criteria:

- Audit includes operator, reason, package id, package schema version, evidence reference ids, destination mode, validation result, and correlation/request id.
- Audit excludes raw package payloads when they could contain operator notes or customer context beyond allowlisted identifiers.
- Existing release evidence tooling can validate the handoff package privacy boundary.
- Failed or refused handoff attempts are recorded as metadata-only audit events.

### UI-12 Admin Support Handoff UI

Admin report operations UI supports support-safe package preview, copy, and download.

Acceptance criteria:

- UI exposes support handoff controls only to admins.
- UI renders allowlisted package metadata, validation state, evidence references, operator notes, and copy/download controls.
- UI does not perform direct third-party writes.
- UI does not render secrets, S3 keys, presigned URLs, raw report JSON/HTML, or raw artifact payloads.
- Playwright covers preview, copy/download affordances, error states, admin-only gating, and privacy denylist.

### VERIFY-07 v2.4 Release Gate And Live Verification

v2.4 closes with release and live verification evidence for support handoff packages.

Acceptance criteria:

- Backend/frontend deploy evidence, commit SHAs, Lambda manifest/runtime, CDK diff/deploy evidence, local quality gates, API request IDs, and browser smoke results are recorded.
- Production smoke is read-only by default and does not mutate report artifacts or write to external ticket systems.
- Direct external destination writes are verified as refused unless an approved credential path is configured.
- Final audit records residual risks and future requirements.

## Future Requirements

- Approved direct integrations with Zendesk, Intercom, Jira Service Management, Linear, or another support system.
- Compliance-grade WORM audit storage.
- Long-term evidence retention policy and legal hold behavior.
- Rich/WYSIWYG report editor.
- PDF/multilingual delivery.
- Billing, analytics, and broader admin operations expansion.

## Out of Scope

- Direct writes to external ticket/support systems without approved connector or secret-backed credential path.
- Customer-data production mutation smoke.
- Raw report artifact export.
- New AWS resources unless Phase 66 proves current resources are insufficient.
- Compliance-grade immutable storage; v2.4 may preserve compatibility but should not implement WORM storage.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| HANDOFF-01 | Phase 66 | Planned |
| HANDOFF-02 | Phase 66 | Planned |
| HANDOFF-03 | Phase 67 | Not started |
| HANDOFF-04 | Phase 67 | Not started |
| UI-12 | Phase 68 | Not started |
| VERIFY-07 | Phase 69 | Not started |
