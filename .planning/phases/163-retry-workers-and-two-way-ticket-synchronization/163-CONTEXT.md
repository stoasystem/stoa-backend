# Phase 163: Retry Workers And Two-Way Ticket Synchronization - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning
**Mode:** Autonomous smart discuss with user-approved defaults

<domain>
## Phase Boundary

Phase 163 adds bounded retry behavior and provider ticket synchronization on top of Phase 162 provider delivery records. It should let admins retry failed provider deliveries through controlled service/API behavior and normalize provider ticket status updates through a metadata-only sync path.

This phase should not add SLA analytics dashboards or customer messaging; those remain Phase 164 scope.

</domain>

<decisions>
## Implementation Decisions

### Retry Behavior
- Retry only `third_party_support` deliveries with `delivery_failed` or `failed` status and retry visibility enabled.
- Use a small bounded attempt limit with operator-visible attempt count, retry exhaustion, next eligible timestamp, and redacted failure reason.
- Reuse the deterministic provider ticket behavior from Phase 162; retry should not duplicate tickets if the existing delivery already has a provider ticket.
- Expose retry through an admin-only endpoint on the existing delivery resource.

### Provider Sync
- Add a provider-neutral sync input that accepts provider event ID, provider status, provider updated timestamp, and safe optional operator fields.
- Normalize provider statuses into STOA lifecycle values and store redacted provider status labels.
- Ignore duplicate events by provider event ID and refuse stale updates older than the current `provider_updated_at`.
- Surface unmappable statuses and terminal-state conflicts as `sync_conflict` with redacted conflict reason.

### Privacy And Persistence
- Do not import or persist raw provider payloads.
- Persist only sync metadata: provider event IDs, provider updated timestamp, last synced timestamp, provider status, lifecycle status, safe assignee/priority labels, and conflict markers.
- Keep existing delivery list/detail response as the operator visibility surface.

### the agent's Discretion
Use existing report repository update patterns and focused tests in `tests/test_admin_report_ops.py`. Keep API additions minimal and backend-only.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 162 added `third_party_support`, provider readiness fields, provider ticket metadata, and `delivery_failed` retry visibility.
- `support_destination_service.transition_delivery_status` already persists lifecycle transitions and audit events.
- `report_repo.update_support_handoff_delivery_status` updates delivery summaries and feed rows.
- `tests/test_admin_report_ops.py` has support delivery record fixtures and monkeypatched repository helpers.

### Established Patterns
- Admin mutation endpoints live in `src/stoa/routers/admin.py` and use `require_role("admin")`.
- Service helpers return metadata-only response shapes through `support_handoff_delivery_response`.
- Delivery audit events are append-only and scoped under the delivery ID.

### Integration Points
- Add route request models near existing support handoff request models.
- Extend repository update helper with optional provider/sync metadata fields.
- Add service functions for retry and sync to keep route logic thin.

</code_context>

<specifics>
## Specific Ideas

- Use `max_attempts=3` for retry eligibility.
- Map provider statuses: `new/open` -> `acknowledged`, `pending` -> `in_progress`, `waiting_on_customer` -> `waiting_on_customer`, `solved/closed/resolved` -> `resolved`, `reopened` -> `reopened`.
- Duplicate sync event IDs should return the current delivery response with no state mutation.

</specifics>

<deferred>
## Deferred Ideas

- Phase 164 owns SLA aggregates, overdue queues, provider failure analytics, and controlled CRM/customer messaging.
- Real provider webhook signature verification remains deferred until a named provider is selected.

</deferred>
