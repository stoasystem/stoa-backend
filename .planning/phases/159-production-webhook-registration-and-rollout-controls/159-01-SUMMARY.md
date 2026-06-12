---
phase: 159
plan: 01
subsystem: payments
tags:
  - stripe
  - webhooks
  - rollout
key-files:
  - src/stoa/services/subscription_service.py
  - src/stoa/routers/admin.py
  - tests/test_subscription_operations.py
metrics:
  tests: "PYTHONPATH=src .venv/bin/pytest tests/test_subscription_operations.py"
---

# Summary 159-01: Webhook Readiness And Rollout Controls

## Delivered

- Added persisted payment rollout controls with independent checkout and refund states: `disabled`, `canary`, `enabled`, and `rolled_back`.
- Added admin endpoints:
  - `GET /admin/subscriptions/billing/rollout-controls`
  - `PATCH /admin/subscriptions/billing/rollout-controls`
- Wired effective rollout controls into production checkout readiness.
- Wired effective refund controls into direct refund execution.
- Extended provider readiness rollout evidence with activation state and effective control status.
- Verified webhook readiness evidence includes HTTPS endpoint mode, signing secret availability, required event subscriptions, quick-ack expectation, and last observed provider event.
- Added tests for default controls, admin updates, checkout rollback, refund rollback preserving export visibility, and webhook last-observed evidence.

## Safety Boundary

- Rollback blocks new live checkout/refund operations only.
- Existing billing, refund history, and accounting export visibility are preserved.
- Canary is visible in rollout state but not treated as generally allowed for live-changing operations.

## Verification

- `PYTHONPATH=src .venv/bin/pytest tests/test_subscription_operations.py` - passed, 32 tests.
- `PYTHONPATH=src .venv/bin/ruff check src/stoa/services/subscription_service.py src/stoa/routers/admin.py tests/test_subscription_operations.py` - passed.
- `git diff --check` - passed.

## Self-Check

PASSED. PAYACT-04 webhook readiness and rollout-control acceptance criteria are covered by code and tests.
