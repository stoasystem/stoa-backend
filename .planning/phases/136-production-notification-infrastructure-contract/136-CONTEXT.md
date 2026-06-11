# Phase 136 Context: Production Notification Infrastructure Contract

## Why This Phase Exists

`stoa_docs` still calls for production-ready realtime notifications beyond the local functional WebSocket milestone. v3.6 proved connection lifecycle, event fanout, frontend realtime client behavior, and fallback locally. v4.2 now needs a production-delivery contract before implementation changes harden the backend or CDK surface.

## Current Foundation

- Durable notification events and list/read/archive APIs exist.
- Local WebSocket transport and connection repository/service behavior were completed in v3.6.
- Frontend realtime client and notification center fallback were completed locally in v3.6.
- v4.1 completed backend locale/mobile contracts but intentionally left full frontend/native work outside this repository.

## Phase Boundary

This phase is planning/contract work. It should define what Phase 137 and Phase 138 implement, including what requires CDK or frontend/native work outside this repository.

## Key Files To Inspect

- `src/stoa/services/notification_service.py`
- `src/stoa/services/websocket_service.py`
- `src/stoa/db/repositories/notification_repo.py`
- `src/stoa/db/repositories/websocket_repo.py`
- `src/stoa/routers/notifications.py`
- `src/stoa/routers/admin.py`
- `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`

## Constraints

- Internal development should favor feature progress over broad security test expansion.
- Do not send real customer notification traffic during smoke without explicit approval.
- Native push provider credentials and production email provider rollout are deferred unless explicitly approved.
- CDK/API Gateway work may require an infrastructure workspace or existing CDK surface confirmation.
