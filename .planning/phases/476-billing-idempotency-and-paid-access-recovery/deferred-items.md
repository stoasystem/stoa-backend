# Phase 476 Deferred Items

## Pre-existing static typing debt

- `src/stoa/routers/conversations.py` has 17 pre-existing targeted mypy errors in DynamoDB object typing, route projection values, and the authorization-spec function attribute. Plan 476-18 removed its two newly exposed token-count errors but did not broaden scope into the inherited typing debt.
