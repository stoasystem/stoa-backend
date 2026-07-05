# Phase 251 Release Gate

## Status

Passed for local v5.15 usage stability.

## Backend Evidence

```bash
.venv/bin/pytest tests/test_core_smoke.py tests/test_usage_ledger.py tests/test_questions.py tests/test_conversations.py tests/test_curriculum_analytics.py tests/test_adaptive_learning.py::test_assignment_generation_and_transition_record_usage_ledger
```

Result:

- `43 passed in 1.18s`

```bash
.venv/bin/ruff check src/stoa/services/core_smoke_service.py src/stoa/services/usage_ledger_service.py src/stoa/routers/admin.py src/stoa/routers/parents.py src/stoa/routers/practice.py src/stoa/routers/questions.py tests/test_core_smoke.py tests/test_usage_ledger.py tests/test_curriculum_analytics.py tests/test_questions.py
```

Result:

- `All checks passed!`

## Frontend Evidence

Phase 249 ran in `/Users/zhdeng/stoa-frontend`:

```bash
npm run build
```

Result:

- TypeScript and Vite production build passed.
- Vite emitted the existing chunk-size warning.

Frontend commit:

- `e462674 feat(249): show usage support explanations`

## Release Notes

- Usage ledger now covers practice teacher-help as a governed support-visible event.
- Question submit rejects same-key, different-intent idempotent retries before quota increment.
- Question persistence partial failure after counter/ledger writes is test-documented for reconciliation.
- Quota reconciliation now reports support-safe `drift`, `stale`, `supportAction`, and `explanation`.
- Reconciliation distinguishes `matched`, `no-usage`, `ledger-only`, `over-limit`, `stale`, `ledger-missing`, `counter-missing`, and `count-mismatch`.
- Parent/admin account operations render usage support action and explanation.
- Admin `GET /admin/core-smoke` returns a deterministic local product-flow smoke matrix.

## Explicit Blockers

- v5.14 focused frontend e2e remains blocked by platform usage-limit approval for Playwright/dev-server execution.
- Live Stripe/TWINT smoke remains blocked without approved credentials, webhook endpoint, finance acceptance, and rollout approval.
- Live Cognito/email smoke remains blocked without approved production/test credentials, configured delivery, and inbox access.
- Live notification, AI provider, external support provider, BI/warehouse, and APM rollout remain future/external activation work.

## Gate Decision

v5.15 is complete for local usage ledger, quota reconciliation, support explanation, and deterministic product smoke readiness. External activation remains out of scope and explicitly documented.
