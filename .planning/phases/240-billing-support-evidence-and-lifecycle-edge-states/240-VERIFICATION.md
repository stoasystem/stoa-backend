# Phase 240 Verification: Billing Support Evidence And Lifecycle Edge States

**Milestone:** v5.13 Payment And Entitlement Production Completion
**Requirement:** PAYPROD-04
**Status:** Complete
**Date:** 2026-07-05

## Backend

Repository: `/Users/zhdeng/stoa-backend`

```bash
.venv/bin/python -m pytest tests/test_subscription_operations.py -q
```

Result: Passed, 35 tests.

```bash
.venv/bin/ruff check src/stoa/services/subscription_service.py src/stoa/routers/billing.py src/stoa/routers/parents.py src/stoa/routers/admin.py tests/test_subscription_operations.py
```

Result: Passed.

## Frontend

Repository: `/Users/zhdeng/stoa-frontend`

```bash
npm run build
```

Result: Passed.

```bash
npm run lint
```

Result: Passed.

## Evidence Summary

- Backend support evidence is covered in `tests/test_subscription_operations.py`.
- Frontend commit: `/Users/zhdeng/stoa-frontend` `a584da6`.
- Live provider smoke remains blocked pending live credentials, registered webhook endpoint, finance acceptance, and explicit rollout approval.
