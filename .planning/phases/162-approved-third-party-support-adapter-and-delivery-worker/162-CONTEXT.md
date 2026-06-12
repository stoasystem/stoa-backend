# Phase 162: Approved Third-Party Support Adapter And Delivery Worker - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning
**Mode:** Autonomous smart discuss with user-approved defaults

<domain>
## Phase Boundary

Phase 162 adds controlled provider delivery for support-safe evidence packages. It should extend the existing support handoff delivery endpoint and service so `third_party_support` can report readiness, fail closed when approval or credentials are missing, and create a deterministic provider-ticket-shaped delivery record only when the destination is explicitly approved and configured.

This phase should not implement retry workers, provider webhook/polling sync, SLA analytics, or CRM/customer messaging; those remain Phase 163 and Phase 164 scope.

</domain>

<decisions>
## Implementation Decisions

### Provider Adapter Shape
- Implement `third_party_support` as the first generic approved provider mode rather than selecting a named vendor mode in this phase.
- Missing provider approval, credentials, or readiness must fail closed with a persisted refused delivery record and no external write.
- Local/provider success behavior may use a deterministic fake provider adapter for tests when explicitly approved and configured.
- Keep the initial adapter abstraction inside `support_destination_service.py`; split to a separate module later only if complexity grows.

### Delivery Persistence And API Contract
- Extend the existing `POST /admin/reports/support-handoff-delivery` endpoint so `internal_queue` and `third_party_support` share request shape and audit behavior.
- Persist provider-neutral fields on the existing delivery record: provider ticket ID/reference, safe URL, provider status, readiness, attempt metadata, and redacted result/error metadata.
- Duplicate delivery requests with the same deterministic idempotency key must return the existing delivery record rather than creating a second ticket.
- Persist only payload digest and metadata summary. Do not persist raw outbound payload snapshots.

### Failure Handling And Tests
- Cover approved provider success, missing credentials/readiness, unapproved destination refusal, validation/privacy failure, provider failure, and duplicate/idempotent delivery.
- Provider failures should persist a metadata-only `failed` delivery with redacted error information and retry eligibility for Phase 163.
- Unknown destination modes should continue to reject before evidence reads.
- Existing `internal_queue` behavior and tests must continue to pass unchanged.

### Operator Visibility
- Provider readiness and delivery responses should expose only redacted operator status: readiness state, blocker reasons, provider ticket reference/URL when safe, lifecycle status, retryable flag, and payload digest.
- Provider-specific raw payloads, credentials, auth tokens, raw report artifacts, S3 keys under `weekly-reports/`, presigned URLs, and raw private customer content remain excluded.
- The queue/detail response shape should include provider fields when present without requiring a new endpoint.

### the agent's Discretion
Implementation details are at the agent's discretion where not constrained above. Prefer narrow changes, existing service/repository patterns, and focused tests in `tests/test_admin_report_ops.py`.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/support_handoff_service.py` builds metadata-only support packages and performs privacy denylist checks.
- `src/stoa/services/support_destination_service.py` already owns delivery/refusal persistence, idempotency keys, retry visibility, delivery response shaping, and delivery audit events.
- `src/stoa/routers/admin.py` owns admin-only package/delivery/list/detail endpoints.
- `src/stoa/db/repositories/report_repo.py` persists support handoff delivery summaries/feed/audit rows.
- `tests/test_admin_report_ops.py` already has support handoff fixtures and coverage for package, delivery, queue, detail, privacy, refusal, and idempotency behavior.

### Established Patterns
- FastAPI route models live in `src/stoa/routers/admin.py`.
- Settings flags are added to `src/stoa/config.py` as `BaseSettings` fields.
- Delivery records are provider-neutral DynamoDB summary rows with feed rows and append-only audit events.
- Response shaping redacts text through service helpers before returning operator-visible data.
- Tests monkeypatch repository writes and use `Settings(...)` dependency overrides.

### Integration Points
- Extend `SupportHandoffPackageRequest` only if provider-specific test controls are needed; otherwise reuse `destination_mode`.
- Extend `support_destination_service.CONTRACT_DEFINED_REFUSED_DESTINATIONS` and delivery routing to recognize `third_party_support`.
- Reuse `support_handoff_service.build_package` and `write_audit_event` for approved provider package creation.
- Keep unsupported/unknown destination rejection before evidence reads.

</code_context>

<specifics>
## Specific Ideas

- Add settings such as `support_third_party_provider_approved`, `support_third_party_provider_api_key`, and a fake-provider failure toggle or endpoint value if useful for deterministic tests.
- Use provider ticket identifiers derived from the delivery id or idempotency key, so tests can assert duplicate requests return the same provider ticket.
- Store provider error categories after redaction, not raw exception strings containing secrets.

</specifics>

<deferred>
## Deferred Ideas

- Phase 163: bounded retry worker behavior, retry backoff metadata, webhook/polling-shaped provider status synchronization, stale/duplicate/conflict handling.
- Phase 164: SLA analytics, overdue classification, provider failure-rate analytics, controlled CRM/customer messaging templates and send evidence.
- Named real vendor API integration remains deferred until provider selection, approved credentials, and production write policy are available.

</deferred>
