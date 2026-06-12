---
phase: 164-support-sla-analytics-and-controlled-crm-messaging
status: context
created: 2026-06-12
autonomous: true
---

# Phase 164 Context

## Goal

Add operational SLA visibility and template-gated customer/support messaging on top of the provider delivery, retry, and sync records completed in Phases 162-163.

## Inputs

- Phase 162 added `third_party_support` delivery records with provider readiness, provider result/error metadata, and retry-visible failure state.
- Phase 163 added bounded retry mutation and provider ticket synchronization metadata, including provider status, sync freshness, duplicate handling, stale update refusal, and conflict markers.
- Requirement `SUPPORTPROV-04` requires:
  - SLA metrics for queued, delivered, acknowledged, first response, resolved, failed, and reopened states.
  - Admin analytics for overdue queues, provider failure rates, retry backlog, and customer-message outcomes.
  - Controlled CRM/customer messaging with approved templates for receipt, status update, resolution, and escalation.
  - Send/refusal/failure evidence persisted and correlated to support tickets.

## Current Code Shape

- `report_repo.list_support_handoff_delivery_summaries` provides recent delivery summary records with filters.
- `support_destination_service.support_handoff_delivery_response` is the redacted public response shaper for delivery records.
- Admin delivery list/detail/retry/sync endpoints live in `src/stoa/routers/admin.py`.
- Support delivery audit events already use `put_support_handoff_delivery_audit_event`.
- Existing tests in `tests/test_admin_report_ops.py` monkeypatch repository functions heavily, so Phase 164 can add focused service/API tests without needing DynamoDB.

## Assumptions

- This phase should not send real CRM/email traffic. Local sends should persist metadata-only evidence when explicitly approved.
- Messaging should fail closed unless both destination and template are approved.
- Template rendering should be fixed and deterministic; custom message bodies are out of scope.
- Analytics should consume bounded delivery summaries and stay metadata-only.
- SLA thresholds can be conservative defaults exposed through service constants rather than new external configuration.

## Risks

- Delivery records may not always have full timestamp history. Analytics should degrade gracefully and classify missing timestamps as unknown rather than failing.
- Raw provider/customer payloads must not leak through message evidence or analytics responses.
- Provider statuses may be mixed between legacy internal states and normalized third-party lifecycle states.

## Decision

Implement a new `support_sla_service` that:

- Builds aggregate SLA analytics from redacted delivery summaries.
- Computes overdue and duration metrics from safe timestamps.
- Creates controlled CRM/customer message evidence for approved templates and destinations.
- Persists message audit rows through small repository helpers and includes message outcome counts in analytics.

Add admin endpoints for:

- `GET /admin/reports/support-handoff-sla`
- `POST /admin/reports/support-handoff-deliveries/{delivery_id}/messages`

Keep all behavior local/provider-neutral and metadata-only.
