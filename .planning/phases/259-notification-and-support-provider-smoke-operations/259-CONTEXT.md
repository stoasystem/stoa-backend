# Phase 259 Context: Notification And Support Provider Smoke Operations

## Scope

Phase 259 makes notification and support-provider activation state visible as release smoke evidence. It does not send customer email, push notifications, CRM messages, or third-party support tickets by default.

## Existing Surfaces

- Notification preferences, digest preview/send refusal, push token registration, and admin delivery status exist in `notification_service` and `routers/notifications.py`.
- WebSocket readiness exists in `websocket_service`.
- Support handoff package delivery, provider retry, provider sync, and bounded CRM messages exist in `support_destination_service` and `support_sla_service`.
- Admin support handoff delivery/SLA routes expose lifecycle evidence without raw provider payloads.

## Decisions

- Add a combined admin smoke endpoint for notification/support release operations.
- Compute readiness from injected `Settings` instead of module-level service settings so production/runtime dependency overrides are honored.
- Keep smoke as read-only unless provider approval, credentials, destination approval, and send flags are all present.
- Represent token registration and preference gating as product-supported local/read-only evidence, not proof of provider push delivery.
- Preserve refusal evidence as a first-class success mode when external provider prerequisites are missing.

## Blocked-State Contract

- Notification email/push send readiness is blocked when providers, approvals, templates, endpoints, or credentials are missing.
- WebSocket live delivery is read-only/blocked until endpoint, routes, deploy, cleanup, and live smoke are present.
- Support third-party delivery is blocked until provider approval and credentials exist.
- Support CRM messaging is blocked until messaging approval, destination approval, and approved templates exist.
