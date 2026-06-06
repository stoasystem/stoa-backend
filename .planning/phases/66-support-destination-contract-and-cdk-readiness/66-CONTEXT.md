# Phase 66: Support Destination Contract And CDK Readiness - Context

**Gathered:** 2026-06-07
**Status:** Ready for implementation planning
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

Phase 66 defines the support handoff package contract, destination policy, privacy model, audit metadata, and CDK readiness before any implementation. It consumes v1.9 support evidence packages, v2.2 rollback evidence, and v2.3 release evidence automation.

The phase is documentation/readiness only. It must not write to external support systems, mutate production report artifacts, or introduce new secrets.

</domain>

<decisions>
## Implementation Decisions

### Destination Scope

- v2.4 starts with manual handoff destinations: preview, copy, and download.
- Direct third-party writes are refused unless an approved connector or secret-backed credential path exists.
- The contract should preserve stable adapter fields for later Zendesk, Intercom, Jira Service Management, Linear, or similar integrations.

### Package Scope

- Handoff packages are metadata-only and backend-mediated.
- Packages may reference recovery jobs, support evidence packages, release evidence bundles, safe-fixture status, rollback evidence, and operator notes.
- Packages must never include raw report artifacts, private S3 keys, presigned URLs, auth tokens, cookies, passwords, or AWS credentials.

### Infrastructure Posture

- Prefer existing admin APIs, DynamoDB audit rows, release evidence validation, and frontend download/copy behavior.
- Do not add new AWS resources unless the CDK readiness decision proves current resources cannot support the package contract.

</decisions>

<code_context>
## Relevant Existing Capabilities

- Recovery evidence export exists through admin-only metadata APIs.
- Support evidence packages from v1.9 already produce bounded incident evidence.
- Release evidence validation and safe-fixture status tooling from v2.3 already implement redaction, denylist checks, and mutation refusal behavior.
- `/admin/report-operations` already has admin-only operational panels for recovery, editing, rollback, release evidence validation, and fixture status.

</code_context>

<deferred>
## Deferred Ideas

- Direct support-system API writes.
- Compliance-grade WORM audit storage.
- Long-term legal hold and retention automation.
- Rich/WYSIWYG report editing.

</deferred>
