# Code Review: Phase 125 Backend Checkout Subscription And Webhook APIs

**status:** clean
**reviewed:** 2026-06-09

## Scope

- `src/stoa/config.py`
- `src/stoa/main.py`
- `src/stoa/routers/admin.py`
- `src/stoa/routers/billing.py`
- `src/stoa/routers/parents.py`
- `src/stoa/services/subscription_service.py`
- `tests/test_subscription_operations.py`

## Findings

No blocking findings.

## Review Notes

- Webhook handler requires raw request body and rejects invalid signatures when a signing secret is configured.
- Production unsigned webhook payloads fail closed.
- Provider events are deduplicated before subscription state changes.
- Manual override status is preserved against later provider events.
- Existing manual subscription tests still pass.
