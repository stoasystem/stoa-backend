# Requirements: v4.2 Production Notification Delivery Readiness

**Milestone:** v4.2
**Status:** Active planning
**Created:** 2026-06-11

## Goal

Promote STOA's local realtime notification foundation into production-deliverable notification capability. v4.2 focuses on backend/infrastructure contracts, notification delivery operations, durable user preferences, email digest readiness, and release evidence. Because this is still internal development, the milestone prioritizes feature progress and practical verification over expanding broad security test scope.

## Requirements

### NOTIFYDEL-01 Production Notification Infrastructure Contract

Implementers have a concrete contract for production notification delivery before route or infrastructure changes begin.

Acceptance criteria:

- Contract identifies the production WebSocket endpoint shape, API Gateway route/integration expectations, environment variables, deployment ownership, and fallback behavior.
- Contract maps existing notification events to production delivery channels: in-app realtime, polling fallback, email digest readiness, and push-ready preference flags.
- Contract defines delivery state fields needed by operators: attempted channel, delivery result, retry/skip reason, timestamp, and request/correlation identifier when available.
- Contract separates work that can be completed in this backend repository from CDK/frontend/native work that may require another workspace.
- `stoa_docs` gap audit and remaining feature queue mark production notification delivery as the active v4.2 build area.

### NOTIFYDEL-02 WebSocket Delivery Operations And Preference APIs

Backend notification APIs support production-oriented delivery operations and user preference reads/updates.

Acceptance criteria:

- Authenticated users can read and update durable notification preferences for supported categories/channels without changing role authorization.
- Notification preference defaults preserve current in-product notification behavior for existing users.
- Backend delivery helpers can decide whether a notification should attempt realtime, remain in-app only, or be queued for digest/push readiness based on preferences and event type.
- Admin or operator-facing routes expose bounded delivery health/status signals useful during internal rollout.
- Focused tests cover preference defaults, updates, role boundaries, and delivery decision behavior.

### NOTIFYDEL-03 Email Digest And Push Preference Readiness

Notification delivery is ready for digest and push expansion without requiring production provider credentials during internal development.

Acceptance criteria:

- Backend has a digest-ready selection/preview contract for unread or relevant notifications by recipient, category, and time window.
- Digest payloads avoid private artifact leakage and use stable metadata fields that future email templates can consume.
- Push/native preference flags can be stored and surfaced even if native push provider delivery remains deferred.
- The implementation does not send broad production email/push traffic without approved provider configuration.
- Tests or documented fixtures prove digest selection, preference interaction, and no-provider fallback behavior.

### VERIFY-25 v4.2 Functional Release Gate And Notification Delivery Audit

v4.2 closes with functional evidence and an updated remaining-feature audit.

Acceptance criteria:

- Focused backend tests and relevant static checks pass or isolate documented pre-existing failures.
- Requirements, roadmap, state, and feature gap docs reflect completed v4.2 notification-delivery work.
- Release evidence includes any available build/deploy/CDK/API/browser evidence, or explicitly records why live production verification was deferred.
- Final audit lists remaining notification work: frontend/mobile visuals, native push provider rollout, production email templates, and broader notification analytics if not completed.
- The next milestone recommendation is updated from the remaining `stoa_docs` feature queue.

## Future Requirements

- Full responsive frontend/native mobile implementation and browser/mobile viewport verification.
- Full frontend visual localization and translated UI rollout.
- Live payment-provider rollout, TWINT production validation, invoices/receipts/refunds, tax/accounting, and dunning.
- Support-ticket/evidence destination integrations after approved connector or credential path exists.
- Automatic student assignment of generated exercises and longer-term adaptive sequencing.
- Rich curriculum authoring workflow, production content QA, analytics dashboards, and deeper operations reporting.

## Out of Scope

- Production mutation smoke that sends real customer notification traffic without explicit approval.
- Native mobile push provider credential rollout unless approved provider details are available.
- Marketing automation or campaign messaging.
- Replacing frontend responsive/localized UI work that belongs in the UI workspace.
- Reworking already-completed report operations security/compliance evidence beyond what v4.2 feature work needs.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| NOTIFYDEL-01 | Phase 136 | Complete |
| NOTIFYDEL-02 | Phase 137 | Planned |
| NOTIFYDEL-03 | Phase 138 | Planned |
| VERIFY-25 | Phase 139 | Planned |
