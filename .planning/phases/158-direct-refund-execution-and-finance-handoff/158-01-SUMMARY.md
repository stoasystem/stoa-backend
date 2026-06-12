---
phase: 158
plan: 01
subsystem: payments
tags:
  - stripe
  - refunds
  - finance
key-files:
  - src/stoa/config.py
  - src/stoa/services/subscription_service.py
  - src/stoa/routers/admin.py
  - tests/test_subscription_operations.py
metrics:
  tests: "PYTHONPATH=src .venv/bin/pytest tests/test_subscription_operations.py"
---

# Summary 158-01: Direct Refund Execution And Finance Handoff

## Delivered

- Added `stripe_refunds_enabled` as an explicit direct refund execution gate.
- Added admin endpoint `POST /admin/subscriptions/billing/{parent_id}/refunds`.
- Implemented refund validation for eligible billing state, provider reference, amount, operator reason, idempotency key, remaining refundable amount, live key requirement, and TWINT 180-day refund window.
- Added Stripe refund creation seam with idempotency key propagation.
- Persisted direct refund result into billing invoice, refund summary, billing event, provider lookup, idempotency record, and accounting handoff.
- Extended accounting handoff refund details with refunded amount, currency, reason, idempotency key, operator, timestamp, and provider handoff status.
- Added focused tests for approved refund, ineligible refusal, duplicate idempotency replay, provider failure no-mutation behavior, expired TWINT window, and finance export shape.

## Safety Boundary

- Refund mutation is disabled by default.
- Provider failure returns a safe 502 and does not update billing as successful.
- Duplicate idempotency replay does not call the provider again.
- Checkout activation remains independent from refund execution.

## Verification

- `PYTHONPATH=src .venv/bin/pytest tests/test_subscription_operations.py` - passed, 27 tests.
- `PYTHONPATH=src .venv/bin/ruff check src/stoa/config.py src/stoa/services/subscription_service.py src/stoa/routers/admin.py tests/test_subscription_operations.py` - passed.
- `git diff --check` - passed.

## Self-Check

PASSED. PAYACT-03 refund execution and finance handoff acceptance criteria are covered by code and focused tests.
