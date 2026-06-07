# Phase 67: Backend Support Handoff Package APIs - Context

**Gathered:** 2026-06-07
**Status:** Ready for implementation
**Mode:** Autonomous from Phase 66 contract

<domain>
## Phase Boundary

Phase 67 adds backend-mediated support handoff package APIs. Admins can compose metadata-only handoff packages from existing recovery evidence, support evidence packages, release evidence validation, safe-fixture status, and operator notes.

The phase must not add direct third-party ticket writes, new secrets, raw report artifact reads, broad S3 permissions, or production mutation behavior.
</domain>

<decisions>
## Implementation Decisions

### API Shape

- Add one admin-only POST endpoint for support handoff package generation.
- Supported destination modes in v2.4 are `preview`, `copy`, and `download`.
- `external_write` returns a refused package result unless a future approved connector or secret-backed credential path exists.
- Unknown destination modes are rejected before evidence reads.

### Evidence Sources

- Recovery job handoff sections reuse existing sanitized support package generation.
- Release evidence sections reuse existing release evidence validation and sanitization.
- Fixture sections reuse existing safe-fixture inventory response generation.
- Operator notes are redacted before they enter package sections.

### Audit

- Package generation/refusal writes metadata-only audit evidence to the existing DynamoDB table using append-only audit row semantics.
- Audit stores package id, schema version, destination mode, validation result, evidence reference ids, request/correlation id, and refusal reasons.
- Audit does not store raw package payloads or operator-note bodies.
</decisions>

<code_context>
## Existing Code Insights

- `src/stoa/services/report_recovery_evidence_service.py` already builds sanitized recovery evidence exports and job-scoped support packages.
- `src/stoa/services/release_evidence_service.py` already validates/sanitizes release bundles, detects private markers, and builds safe-fixture inventory responses.
- `src/stoa/routers/admin.py` already contains admin-only report operations endpoints and request id/operator helpers.
- `src/stoa/db/repositories/report_repo.py` already uses conditional append audit rows for report and recovery job audit timelines.
- `tests/test_admin_report_ops.py` has focused admin route tests and privacy denylist helpers.
</code_context>

<specifics>
## Specific Implementation Notes

- Keep package output bounded: limit recovery job ids and per-section target/audit limits.
- Return allowlisted fields only.
- Reuse existing redaction helpers instead of custom string filtering where possible.
- Add tests for admin-only access, successful package generation, unsupported direct destination refusal, unknown destination rejection, missing evidence handling, privacy denial, and audit metadata.
</specifics>

<deferred>
## Deferred Ideas

- Direct writes to Zendesk, Intercom, Jira Service Management, Linear, or other support systems.
- Connector credential storage.
- Compliance-grade WORM audit storage.
- Long-term legal hold or retention automation.
</deferred>
