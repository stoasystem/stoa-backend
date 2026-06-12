# Phase 148: Support Destination Contract And Credential Readiness - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 148 defines the contract that must exist before STOA can turn metadata-only support handoff packages into provider-bound delivery. It should enumerate supported destination modes, credential/config readiness requirements, payload and attachment limits, redaction rules, refusal behavior, and implementation targets for later phases. It should not perform live provider writes or replace the existing manual preview/copy/download flow.

</domain>

<decisions>
## Implementation Decisions

### Destination Modes
- Keep existing `preview`, `copy`, and `download` modes as the safe manual baseline.
- Keep existing `external_write` refusal as a compatibility/safety mode; do not turn it into a provider adapter.
- Define explicit future provider modes: `internal_queue`, `shared_mailbox`, `zendesk_ticket`, `freshdesk_ticket`, and `helpscout_conversation`.
- Require unknown destination modes to fail before evidence reads, matching the current route/test behavior.

### Credential And Readiness Model
- Readiness should be an admin-visible computed contract, not a secret display surface.
- Store or expose credential references and presence flags only: never token values, authorization headers, API keys, cookies, or provider secrets.
- Readiness states should distinguish configured, missing credential/config, refused/unapproved, and dry-run-safe.
- Provider-specific required fields should remain in allowlisted destination configuration, not in the core package schema.

### Payload And Privacy Rules
- Provider payloads should be generated from the already-redacted support package summary, package ID, schema version, evidence reference IDs, safe tags, and approved custom fields.
- Raw report JSON/HTML, S3 object keys, presigned URLs, raw provider/customer payloads, and secrets remain prohibited.
- Attachments are disabled by default for external delivery; if enabled later, they must be redacted package JSON/markdown only with explicit size/type limits.
- Outbound audit should store delivery metadata, provider object references, refusal/failure reasons, privacy result, and payload digest rather than raw outbound payloads.

### Phase Handoff
- Phase 148 should produce a durable contract document and plan the code seams for Phase 149 delivery.
- The preferred first implementation path is a narrow approved destination plus adapter seam, not broad CRM automation.
- Idempotency, retry classification, lifecycle status, and operator queue visibility belong in the contract so Phases 149 and 150 do not invent incompatible state.
- Broad two-way ticket synchronization, SLA analytics, customer messaging campaigns, and additional live providers remain deferred.

### the agent's Discretion
All implementation choices not listed above are at the agent's discretion, provided they preserve metadata-only evidence boundaries and fail closed for unapproved destinations.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/support_handoff_service.py` builds support handoff packages with schema version, package ID, redacted reason/operator, evidence references, sections, validation status, destination status, and audit references.
- `support_handoff_service.ALLOWED_DESTINATIONS` currently supports `preview`, `copy`, and `download`; `REFUSED_DESTINATIONS` currently contains `external_write`.
- `support_handoff_service.write_audit_event()` records append-only metadata-only support handoff audit rows via `report_repo.put_support_handoff_audit_event()`.
- `tests/test_admin_report_ops.py` already covers admin-only access, metadata composition, free-text credential redaction, failed release evidence refusal, external write refusal before evidence reads, and unknown destination rejection.

### Established Patterns
- Unknown destination modes are rejected before evidence reads in `src/stoa/routers/admin.py`.
- `external_write` currently returns a refused package and skips evidence reads, which is the correct fail-closed precedent for unapproved provider writes.
- Current audit events store metadata and reference IDs, not raw package payloads.
- Existing privacy checks reuse release evidence marker scanning and support handoff free-text credential redaction.

### Integration Points
- `src/stoa/routers/admin.py` owns the admin support handoff package route and request model.
- `src/stoa/services/support_handoff_service.py` should remain the package composition boundary.
- A future destination/readiness module can provide destination contracts to the route/service without mixing provider-specific fields into package composition.
- `src/stoa/db/repositories/report_repo.py` is the likely persistence point for delivery/readiness status records in later phases.

</code_context>

<specifics>
## Specific Ideas

- Define destination contract in a Phase 148 artifact before code changes.
- Use official-provider research from `.planning/research/SUMMARY.md`, including Zendesk/Freshdesk/Help Scout/SES constraints.
- Keep implementation compatible with existing tests that assert external write refusal and no evidence reads for unknown/refused destinations.
- Make the contract explicit that Phase 149 may pick one approved delivery path and should keep manual fallback.

</specifics>

<deferred>
## Deferred Ideas

- Actual provider write implementation is deferred to Phase 149.
- Operator queue/detail/retry UI and APIs are deferred to Phase 150.
- Two-way CRM sync, SLA analytics, customer messaging campaigns, and additional provider rollout remain future milestone scope.

</deferred>
