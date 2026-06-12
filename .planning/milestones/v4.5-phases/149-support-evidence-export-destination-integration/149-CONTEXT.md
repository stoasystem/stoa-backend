# Phase 149: Support Evidence Export Destination Integration - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 149 implements the first approved support handoff destination path using the Phase 148 contract. The selected destination is `internal_queue`: a STOA-owned metadata-only delivery/status record that validates destination readiness and package privacy before recording a delivery lifecycle result. Manual `preview`, `copy`, and `download` remain fallback modes, and all third-party destinations remain refused until separate credential-backed approvals exist.

</domain>

<decisions>
## Implementation Decisions

### Destination Selection
- Implement `internal_queue` as the only approved Phase 149 delivery path.
- Keep `external_write` refused as a compatibility/safety mode.
- Keep `shared_mailbox`, `zendesk_ticket`, `freshdesk_ticket`, and `helpscout_conversation` refused in Phase 149 unless explicitly added by a later approved phase.
- Preserve existing manual `preview`, `copy`, and `download` behavior as fallback.

### Readiness And Approval
- `internal_queue` readiness uses `none_required` credential references, `none_required` env vars, `stoa_backend` as secret owner, and `none_required` provider prerequisites.
- Gate `internal_queue` delivery behind `SUPPORT_INTERNAL_QUEUE_APPROVED=true` or an equivalent fail-closed runtime/config flag.
- Missing or false approval should create a refused delivery result with redacted reason; it must not be recorded as sent.
- Destination readiness and package privacy must be checked before writing delivery/status records.

### Delivery Record
- Create provider-neutral delivery/status records with delivery ID, package ID, destination mode, status, actor, timestamps, correlation ID, idempotency key, retry count, redacted refusal/failure reasons, privacy result, evidence reference IDs, and payload digest.
- Separate package validation status from delivery lifecycle status.
- Use statuses compatible with Phase 148: `created`, `refused`, `queued`, `sent`, `failed`, and `retried`.
- For `internal_queue`, provider object reference is an internal delivery/status ID only.

### Payload And Privacy
- Delivery payload must be generated from redacted package summary/reference data only.
- Do not store raw outbound payload bodies unless they are explicitly metadata-only and needed; prefer payload digest and summary metadata.
- Do not include raw report JSON/HTML, S3 object keys, presigned URLs, authorization headers, cookies, API keys, OAuth tokens, or provider/customer payloads.
- Attachments remain disabled.

### the agent's Discretion
The implementation may choose exact module/function names, table key shape, and route names, provided they fit existing service/repository/admin-route conventions and preserve the Phase 148 contract.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/support_handoff_service.py` builds the package, privacy result, manual output modes, and support handoff audit events.
- `src/stoa/routers/admin.py` owns `SupportHandoffPackageRequest` and `POST /admin/reports/support-handoff-package`.
- `src/stoa/db/repositories/report_repo.py` already has `put_support_handoff_audit_event()` and `list_support_handoff_audit_events()` patterns for support handoff metadata.
- `tests/test_admin_report_ops.py` has focused support handoff coverage and should be extended rather than duplicated elsewhere.

### Established Patterns
- Destination validation currently happens before evidence reads.
- Refused external writes skip evidence reads.
- Audit metadata stores references and redacted results, not raw payload bodies.
- Tests use monkeypatched repository helpers and `TestClient(_app_for_user(...))` for admin route coverage.

### Integration Points
- A new support destination/delivery service can sit downstream of package composition and upstream of repository persistence.
- Admin routes can add a new endpoint or extend the package endpoint only if manual modes remain backward-compatible.
- Repository helpers should follow existing support handoff audit row conventions and avoid introducing new infrastructure for this first internal path.

</code_context>

<specifics>
## Specific Ideas

- Prefer a focused `internal_queue` path over third-party adapter work in this phase.
- Add tests for approved `internal_queue`, missing approval refusal, privacy-failed refusal, duplicate/idempotent delivery behavior, and manual fallback preservation.
- Keep third-party destination strings refused with explicit redacted reasons if surfaced.
- Use Phase 148 contract artifact as canonical reference.

</specifics>

<deferred>
## Deferred Ideas

- Operator list/detail queue visibility belongs to Phase 150.
- Third-party ticket/mailbox delivery belongs to future approved provider phases.
- Two-way support-system synchronization, SLA analytics, and customer messaging remain out of scope.

</deferred>
