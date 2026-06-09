# Phase 113: Backend WebSocket Connection And Event Delivery - Context

**Gathered:** 2026-06-09
**Status:** Ready for planning
**Mode:** Autonomous smart discuss; user delegated all grey-area decisions to the agent.

<domain>
## Phase Boundary

Implement backend WebSocket connection and delivery behavior for v3.6. This phase owns authenticated connection records, subscription authorization, notification event fanout, delivery attempt recording, disconnect cleanup, stale cleanup, and focused backend tests. It must preserve the v3.5 notification center as durable history and treat WebSocket delivery as a fallback-safe realtime transport overlay.

</domain>

<decisions>
## Implementation Decisions

### Connection Storage And Lifecycle
- Store active connection records in the existing DynamoDB table with `PK=WS_CONN#{connection_id}`, `SK=META`, and `entity_type=websocket_connection` to match the repo's single-table pattern and avoid adding a new table from the backend repo.
- Store `connection_id`, `user_id`, `role`, `subscribed_channels`, `connected_at`, `last_seen_at`, `expires_at`, and optional `endpoint_url` on each connection.
- Use TTL-compatible `expires_at` plus explicit cleanup on heartbeat, disconnect, fanout gone/failed responses, and stale scans.
- Model heartbeat as a client message that refreshes `last_seen_at` and `expires_at`; missed heartbeat is non-fatal because notification history remains durable.

### Authentication And Subscription Authorization
- Authenticate WebSocket connect/subscribe flows with the existing Cognito/JWT validation semantics from `src/stoa/deps.py`; local tests may inject decoded user claims without external Cognito calls.
- Normalize frontend `tutor` to backend-visible teacher/tutor behavior where existing notification recipients use `tutor`, while backend role guards continue to use established role semantics.
- Authorize subscriptions server-side from stored connection user id and role. Do not trust client-supplied channel names after subscription.
- Support user-specific channels (`user:{user_id}`) and role broadcast channels (`role:{role}`) when the current user is allowed to receive that role's notification events.

### Event Fanout And Delivery Recording
- Keep `notification_service.create_event` as the durable notification creation path and layer WebSocket fanout after the repository write.
- Build WebSocket envelopes from existing notification response fields plus `deliveryId` and `deliveryAttempt`.
- Record delivery attempts/results in metadata or side records without making failed realtime delivery mark the durable notification as failed.
- Treat missing endpoint configuration, no active connections, stale connections, and gone responses as non-destructive fanout outcomes.

### Cleanup And Verification
- Provide explicit disconnect cleanup by connection id.
- Provide stale cleanup that removes connection records whose expiry is older than the current time.
- Focus tests on repository/service behavior: lifecycle, authorization, fanout target filtering, stale cleanup, delivery attempt results, and durable fallback persistence.
- Avoid production mutation or external AWS WebSocket calls in tests; use fakes/mocks for connection management delivery.

### the agent's Discretion
The agent may choose exact module boundaries, helper names, and whether delivery attempt details live in event metadata or small side records, provided the durable notification center remains canonical and focused tests verify the contract.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/notification_service.py` creates/list/marks durable notification events and already emits teacher, moderation, and subscription notification types.
- `src/stoa/db/repositories/notification_repo.py` stores notification events in the single DynamoDB table.
- `src/stoa/deps.py` validates Cognito access tokens and resolves roles from Cognito groups, custom role, or DynamoDB profile fallback.
- Existing tests monkeypatch repositories and route dependencies directly, avoiding external AWS calls.

### Established Patterns
- Backend code uses route-local Pydantic models, service modules for business logic, and repository helpers for DynamoDB access.
- DynamoDB records use uppercase entity prefixes in `PK` and `SK`, plus `entity_type` for filtered scans.
- Best-effort notification side effects should not break primary workflows outside production.
- API responses use frontend-facing camelCase while internal Python data remains snake_case.

### Integration Points
- Fanout should integrate with `notification_service.create_event` and the existing emit helpers.
- Connection storage should live beside notification repository behavior in `src/stoa/db/repositories/`.
- WebSocket behavior should be service-level first so Phase 114 frontend work can consume a stable envelope contract.
- Infrastructure-specific endpoint configuration belongs in `src/stoa/config.py` and can be disabled locally.

</code_context>

<specifics>
## Specific Ideas

- Preserve existing notification list/read/archive APIs as the fallback path.
- Use API Gateway WebSocket semantics as the default runtime model, but keep implementation testable without a live API Gateway endpoint.
- Include delivery attempt metadata for observability without changing user-visible notification state on realtime failure.

</specifics>

<deferred>
## Deferred Ideas

- Native mobile push notifications remain out of scope.
- Email notification digests remain out of scope.
- CDK implementation details beyond backend readiness/configuration are deferred to infrastructure work or release-gate evidence.

</deferred>

---
*Phase: 113-backend-websocket-connection-and-event-delivery*
*Context gathered: 2026-06-09 via autonomous smart discuss*
