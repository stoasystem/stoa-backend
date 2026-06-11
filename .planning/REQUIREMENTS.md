# Requirements: v4.5 Support Evidence Integrations And Operations Handoff

**Milestone:** v4.5
**Status:** Active planning
**Created:** 2026-06-12
**Research:** `.planning/research/SUMMARY.md`

## Goal

Connect STOA's existing support-safe evidence packages and operations metadata to approved support destinations, reducing manual copy/download handoff while preserving metadata-only evidence boundaries.

The milestone should prove a controlled destination workflow, not a broad CRM platform. Existing `preview`, `copy`, and `download` modes remain supported, and unapproved external writes remain fail-closed.

## Requirements

### SUPPORTINT-01 Support Destination Contract And Credential Readiness

Implementers and operators have a precise destination, credential, payload, and refusal contract before any live support-system write is enabled.

Acceptance criteria:

- Contract defines approved destination modes, including manual modes plus candidate `internal_queue`, `shared_mailbox`, `zendesk_ticket`, `freshdesk_ticket`, and `helpscout_conversation`.
- Contract identifies credential references, environment variables, secret ownership, provider account requirements, and operator approval gates for each selected destination.
- Readiness checks expose configured, missing, refused, and dry-run-safe states without exposing secrets.
- Metadata-only payload rules define allowed subject/body/reference/custom-field data, attachment policy, redaction rules, and outbound payload digest behavior.
- Existing `external_write` refusal remains in place unless replaced by an explicitly approved destination mode with tests.

### SUPPORTINT-02 Support Evidence Export Destination Integration

Backend support handoff can deliver a support-safe package to one approved destination path while retaining manual fallback.

Acceptance criteria:

- Delivery service validates destination readiness and package privacy before provider calls.
- Selected destination adapter maps only the redacted support package summary, package ID, evidence references, tags, and approved custom fields.
- Delivery records include lifecycle status, request/correlation IDs, timestamps, idempotency key, provider object ID/URL when available, retry count, and redacted refusal/failure reasons.
- Provider failures, missing credentials, and unapproved destinations are recorded as failed/refused, not as generated-package success.
- Existing preview/copy/download behavior remains available and covered by focused tests.

### SUPPORTINT-03 Operator Queue And Handoff Status Visibility

Operators can inspect recent support handoff activity and understand whether a package is created, queued, sent, failed, refused, or retried.

Acceptance criteria:

- Admin-only list/detail APIs expose recent support handoff delivery records with bounded filters for status, destination, package ID, and date range.
- Detail views include provider references, redacted failure/refusal reasons, retry count, correlation ID, and privacy validation summary.
- Retry behavior is explicit, bounded, idempotent, and unavailable for privacy-failed or unapproved destinations.
- Queue/status records do not expose raw report artifacts, secrets, authorization headers, presigned URLs, or unredacted outbound payloads.
- Support workflow remains usable when external delivery is unavailable through clear manual fallback status.

### VERIFY-28 v4.5 Support Integration Release Gate

v4.5 closes with focused verification and updated remaining-feature planning.

Acceptance criteria:

- Focused backend and frontend checks pass for the selected delivery path, refusal paths, status visibility, and existing manual fallback.
- Release evidence captures destination configuration status with secrets redacted, provider/write deferral or approval state, and privacy validation results.
- Tests prove unapproved destinations, missing credentials, provider failures, duplicate retries, and privacy violations fail closed.
- Requirements, roadmap, state, feature-gap audit, and remaining-feature queue reflect completed v4.5 support integration work.
- Remaining work is explicit for additional support providers, two-way synchronization, SLA analytics, and broader CRM/customer messaging automation.

## Future Requirements

- Additional live support destination writes after separate provider approval.
- Two-way ticket synchronization and webhook ingestion.
- Support SLA analytics beyond first-pass handoff status.
- Broad CRM/customer messaging campaigns.
- Native mobile support flows.

## Out of Scope

- Unapproved external writes.
- Raw report artifact exposure.
- Direct S3 artifact links or presigned URLs.
- Storing provider credentials in code, planning docs, payloads, or audit rows.
- Broad customer messaging campaigns.
- Replacing existing metadata-only report operations evidence boundaries.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SUPPORTINT-01 | Phase 148 | Planned |
| SUPPORTINT-02 | Phase 149 | Planned |
| SUPPORTINT-03 | Phase 150 | Planned |
| VERIFY-28 | Phase 151 | Planned |
